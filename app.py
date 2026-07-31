"""App web para llevar el control de prestamos personales.

Corre con:  streamlit run app.py
"""
import html
import urllib.parse
from datetime import date, datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import config
from calculos import (
    FACTOR_FRECUENCIA,
    calcular_abono_capital,
    calcular_pago,
    clasificar_prestamo,
    fmt_money,
    fmt_pct,
    proximo_pago,
    redondear_500,
    siguiente_fila_libre,
)
from setup_sheet import formula_fila_pagos
from sheets_client import get_spreadsheet

st.set_page_config(page_title="Control de Prestamos", page_icon="\U0001F4B0", layout="wide")

FRECUENCIAS = ["Diario", "Semanal", "Quincenal", "Mensual"]
PAGOS_PREFILL_ROWS = 500

# Orden completo, usado en el expander "Ver todos los detalles". No
# incluye "Dias max permitidos": es un dato interno (umbral que usa la
# hoja para calcular el Estado), no algo util para leer directamente.
PRESTAMOS_COLS_ORDEN = [
    "Cliente", "Estado", "Saldo pendiente", "Monto prestado",
    "Fecha ultimo pago", "ID Prestamo", "Fecha inicio",
    "Tasa interes (%/periodo)", "Frecuencia de pago", "Total pagado",
    "Interes cobrado", "Dias desde referencia",
]
PAGOS_COLS_ORDEN = [
    "Tipo", "Cliente", "Fecha de pago", "Monto pagado", "Saldo nuevo",
    "ID Prestamo", "ID Pago", "Saldo anterior", "Interes del periodo",
    "Abono a capital",
]

COLUMNAS_DINERO = {
    "Monto prestado", "Saldo pendiente", "Total pagado", "Interes cobrado",
    "Monto pagado", "Saldo anterior", "Interes del periodo", "Abono a capital",
    "Saldo nuevo", "Monto",
}
COLUMNAS_PORCENTAJE = {"Tasa interes (%/periodo)", "Interés"}

# Colores de la etiqueta de Estado (usado en el detalle expandido).
ESTADO_COLORES = {
    "Al dia": ("rgba(34, 197, 94, 0.15)", "#16a34a"),
    "Atrasado": ("rgba(239, 68, 68, 0.15)", "#dc2626"),
    "Pagado": ("rgba(59, 130, 246, 0.15)", "#2563eb"),
}

# Color de fondo de cada fila en la lista de prestamos, segun
# clasificar_prestamo(): verde = nuevo sin pagos, morado = ya viene
# pagando, naranja = atraso leve, rojo = atraso grave. Los prestamos
# pagados no aparecen en la lista principal (van al archivo).
CATEGORIA_COLOR = {
    "nuevo": "rgba(34, 197, 94, 0.14)",
    "con_pagos": "rgba(168, 85, 247, 0.14)",
    "atrasado_leve": "rgba(249, 115, 22, 0.16)",
    "atrasado_grave": "rgba(239, 68, 68, 0.16)",
}

TABLA_CSS = """
<style>
.tabla-scroll { overflow-x: auto; margin-bottom: 1rem; }
.tabla-app { border-collapse: collapse; width: 100%; white-space: nowrap; }
.tabla-app th {
    text-align: left; padding: 0.4rem 0.75rem;
    border-bottom: 2px solid rgba(128, 128, 128, 0.35); font-weight: 600;
}
.tabla-app td {
    padding: 0.4rem 0.75rem; border-bottom: 1px solid rgba(128, 128, 128, 0.15);
}
.tabla-app td.num {
    text-align: right; font-size: 1.15rem; font-weight: 600;
    font-variant-numeric: tabular-nums;
}
.badge-estado {
    display: inline-block; padding: 0.15rem 0.65rem; border-radius: 999px;
    font-weight: 600; font-size: 0.85rem; white-space: nowrap;
}
</style>
"""


def _badge_estado(valor):
    texto = _celda(valor)
    fondo, color = ESTADO_COLORES.get(valor, ("rgba(128, 128, 128, 0.15)", "inherit"))
    return f'<span class="badge-estado" style="background:{fondo};color:{color};">{texto}</span>'


def reordenar(df, orden):
    cols = [c for c in orden if c in df.columns]
    cols += [c for c in df.columns if c not in cols]
    return df[cols]


def _tipo_pago(fila):
    # Un ajuste (ver _registrar_ajuste) siempre tiene Monto pagado en 0
    # -- un pago real nunca se guarda con 0. Se distingue de un vistazo
    # en el historial en vez de leerse como un pago normal de ₡0.
    try:
        monto_pagado = float(fila["Monto pagado"])
        abono = float(fila["Abono a capital"])
    except (TypeError, ValueError):
        return "Pago"
    if monto_pagado == 0 and abono != 0:
        return "➕ Prestamo adicional" if abono < 0 else "🔧 Ajuste"
    return "Pago"


def con_tipo_pago(df):
    d = df.copy()
    d["Tipo"] = d.apply(_tipo_pago, axis=1)
    return d


def _celda(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return html.escape(str(v))


def render_tabla(df, orden=None):
    """Tabla en HTML propia (en vez de st.dataframe) para poder controlar el
    formato de miles y el tamano de letra de los montos, cosa que
    st.dataframe no permite (dibuja las celdas en un canvas). Se pierde
    poder ordenar/redimensionar columnas con el mouse, aceptable para el
    volumen de datos de un uso personal."""
    d = reordenar(df, orden) if orden else df
    encabezados = "".join(f"<th>{html.escape(str(c))}</th>" for c in d.columns)
    filas = []
    for _, r in d.iterrows():
        celdas = []
        for c in d.columns:
            valor = r[c]
            if c in COLUMNAS_DINERO:
                celdas.append(f'<td class="num">{fmt_money(valor)}</td>')
            elif c in COLUMNAS_PORCENTAJE:
                celdas.append(f'<td class="num">{fmt_pct(valor)}</td>')
            elif c == "Estado":
                celdas.append(f"<td>{_badge_estado(valor)}</td>")
            else:
                celdas.append(f"<td>{_celda(valor)}</td>")
        filas.append(f"<tr>{''.join(celdas)}</tr>")
    tabla_html = (
        f'<div class="tabla-scroll"><table class="tabla-app">'
        f"<thead><tr>{encabezados}</tr></thead><tbody>{''.join(filas)}</tbody>"
        f"</table></div>"
    )
    st.markdown(TABLA_CSS + tabla_html, unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def _sheet():
    return get_spreadsheet()


@st.cache_data(ttl=15, show_spinner=False)
def load_df(ws_name, numeric_cols=None):
    ws = _sheet().worksheet(ws_name)
    records = ws.get_all_records(value_render_option="UNFORMATTED_VALUE")
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df = df[df.iloc[:, 0].astype(str).str.strip() != ""]
    for col in df.columns:
        if "Fecha" in col:
            # Sheets devuelve fechas como numero de serie (dias desde 1899-12-30)
            # cuando se piden valores sin formato; se convierten para mostrar.
            serial = pd.to_numeric(df[col], errors="coerce")
            parsed = pd.to_datetime(serial, unit="D", origin="1899-12-30")
            df[col] = parsed.dt.strftime("%d/%m/%Y").fillna("")
    return df.reset_index(drop=True)


def next_row(ws, input_col_letter):
    values = ws.col_values(ord(input_col_letter) - ord("A") + 1)
    return siguiente_fila_libre(values)


def eliminar_prestamo(sh, id_prestamo):
    """Vacia los datos de entrada del prestamo (y de sus pagos) sin borrar
    la fila. El ID de cada prestamo se calcula segun la posicion de su fila
    (formula ARRAYFORMULA en la columna A) -- si se borrara la fila entera,
    todo lo de abajo correria una posicion y sus ID cambiarian, invalidando
    los pagos ya registrados de esos otros prestamos. Vaciar en vez de
    borrar deja a los demas intactos."""
    ws_p = sh.worksheet(config.SHEET_PRESTAMOS)
    celda = ws_p.find(id_prestamo, in_column=1)
    if celda:
        ws_p.batch_clear([f"B{celda.row}:F{celda.row}"])

    ws_pg = sh.worksheet(config.SHEET_PAGOS)
    celdas_pago = ws_pg.findall(id_prestamo, in_column=2)
    if celdas_pago:
        rangos = []
        for c in celdas_pago:
            rangos.append(f"B{c.row}")
            rangos.append(f"D{c.row}:E{c.row}")
        ws_pg.batch_clear(rangos)
        # F:I normalmente son formulas, pero un abono extra a capital
        # (sin interes) las sobreescribe con valores fijos en esa fila
        # puntual -- hay que restaurar la formula, no solo vaciar, para
        # que la fila quede reutilizable para el siguiente pago.
        for c in celdas_pago:
            ws_pg.update([formula_fila_pagos(c.row)], f"F{c.row}:I{c.row}", value_input_option="USER_ENTERED")


def _mostrar_mensaje_whatsapp(pago):
    st.success("Pago guardado.")
    mensaje = (
        f"Hola {pago['cliente']}\n\n"
        f"Resumen de tu pago del {pago['fecha']}:\n"
        f"Saldo anterior: {fmt_money(pago['saldo_anterior'])}\n"
        f"Interes: {fmt_money(pago['interes'])}\n"
        f"Monto pagado: {fmt_money(pago['monto_pagado'])}\n"
        f"Abono a capital: {fmt_money(pago['abono'])}\n"
        f"Saldo actual: {fmt_money(pago['saldo_nuevo'])}"
    )
    st.text_area("Mensaje para compartir", mensaje, height=170, key=f"msg_{pago['id_prestamo']}")
    link_wsp = "https://wa.me/?text=" + urllib.parse.quote(mensaje)
    cwsp, ccerrar = st.columns([1, 1])
    cwsp.link_button("📲 Enviar por WhatsApp", link_wsp)
    if ccerrar.button("Cerrar", key=f"cerrar_{pago['id_prestamo']}"):
        del st.session_state["ultimo_pago"]
        st.session_state["panel_abierto"] = None
        st.rerun()


def _panel_pago(sh, fila):
    id_prestamo = fila["ID Prestamo"]
    if st.session_state.get("ultimo_pago", {}).get("id_prestamo") == id_prestamo:
        _mostrar_mensaje_whatsapp(st.session_state["ultimo_pago"])
        return

    with st.form(f"pago_{id_prestamo}", clear_on_submit=True):
        fecha_pago = st.date_input("Fecha de pago", value=date.today(), key=f"fecha_{id_prestamo}")
        monto_pagado = st.number_input("Monto pagado (₡)", min_value=0, step=1000, key=f"monto_{id_prestamo}")
        solo_capital = st.checkbox(
            "Es un abono extra a capital (el interes de este periodo ya esta pagado)",
            key=f"solocapital_{id_prestamo}",
            help="Marca esto si el cliente ya pago el interes de este periodo en un "
                 "pago anterior y este pago es solo para bajar el saldo, sin cobrar "
                 "interes de nuevo.",
        )
        submitted = st.form_submit_button("Guardar pago")
        if submitted:
            if monto_pagado <= 0:
                st.warning("El monto pagado debe ser mayor a cero.")
            else:
                ws = sh.worksheet(config.SHEET_PAGOS)
                row = next_row(ws, "B")
                if row > PAGOS_PREFILL_ROWS:
                    st.error(
                        f"Se alcanzo el limite de {PAGOS_PREFILL_ROWS} pagos precargados. "
                        "Pideme que extienda las formulas de la hoja Pagos."
                    )
                else:
                    saldo_anterior = float(fila["Saldo pendiente"])
                    if solo_capital:
                        resultado = calcular_abono_capital(saldo_anterior, monto_pagado)
                    else:
                        resultado = calcular_pago(
                            saldo_anterior=saldo_anterior,
                            tasa_mensual=float(fila["Tasa interes (%/periodo)"]),
                            frecuencia=fila["Frecuencia de pago"],
                            monto_pagado=monto_pagado,
                        )
                    # Columna C (Cliente) es formula -- no se escribe.
                    ws.update([[id_prestamo]], f"B{row}", value_input_option="USER_ENTERED")
                    ws.update(
                        [[fecha_pago.strftime("%Y-%m-%d"), monto_pagado]],
                        f"D{row}:E{row}", value_input_option="USER_ENTERED",
                    )
                    # F:I se escriben como valores fijos (no se dejan como
                    # formula) para "congelar" el interes con la tasa de
                    # HOY. Si no se hiciera asi, la formula original
                    # recalcularia este pago con la tasa que tenga el
                    # prestamo en el futuro (se probo en vivo: si se
                    # cambia la tasa despues, el interes de pagos viejos
                    # cambia con ella). Congelando, se puede renegociar la
                    # tasa de un prestamo sin alterar lo ya cobrado.
                    ws.update(
                        [[
                            resultado["saldo_anterior"], resultado["interes"],
                            resultado["abono"], resultado["saldo_nuevo"],
                        ]],
                        f"F{row}:I{row}", value_input_option="USER_ENTERED",
                    )
                    st.session_state["ultimo_pago"] = {
                        "id_prestamo": id_prestamo,
                        "cliente": fila["Cliente"],
                        "fecha": fecha_pago.strftime("%d/%m/%Y"),
                        **resultado,
                    }
                    load_df.clear()
                    st.rerun()


def _registrar_ajuste(sh, id_prestamo, saldo_actual, saldo_nuevo, fecha=None):
    """Agrega una fila de Pagos con interes 0 que mueve el saldo de
    saldo_actual a saldo_nuevo, sin tocar el historial de pagos
    anteriores. "Monto pagado" queda en 0 (no es un pago real recibido)
    -- el historial (render_tabla en la tabla de Pagos) reconoce estas
    filas por eso y las etiqueta como ajuste/prestamo adicional en vez
    de un pago normal. Abono a capital negativo = se le presto mas
    (sube el saldo); positivo = se le corrige el saldo hacia abajo."""
    ws_pg = sh.worksheet(config.SHEET_PAGOS)
    row_pg = next_row(ws_pg, "B")
    ajuste_a_capital = saldo_actual - saldo_nuevo
    fecha = fecha or date.today()
    ws_pg.update([[id_prestamo]], f"B{row_pg}", value_input_option="USER_ENTERED")
    ws_pg.update(
        [[fecha.strftime("%Y-%m-%d"), 0]],
        f"D{row_pg}:E{row_pg}", value_input_option="USER_ENTERED",
    )
    ws_pg.update(
        [[saldo_actual, 0, ajuste_a_capital, saldo_nuevo]],
        f"F{row_pg}:I{row_pg}", value_input_option="USER_ENTERED",
    )


def _panel_prestar_mas(sh, fila):
    """Presta un monto adicional a un cliente que ya tiene un prestamo
    activo (p.ej. pide mas dinero sobre lo que ya debe). Se suma al
    saldo pendiente y queda en el historial de pagos como un ajuste
    identificable, sin tocar los pagos anteriores."""
    id_prestamo = fila["ID Prestamo"]
    saldo_actual = float(fila["Saldo pendiente"])
    with st.form(f"prestarmas_{id_prestamo}", clear_on_submit=True):
        fecha = st.date_input("Fecha", value=date.today(), key=f"fechamas_{id_prestamo}")
        monto_extra = st.number_input(
            "Monto adicional que le prestas (₡)", min_value=0, step=1000, key=f"extra_{id_prestamo}",
        )
        submitted = st.form_submit_button("Prestar este monto")
        if submitted:
            if monto_extra <= 0:
                st.warning("El monto debe ser mayor a cero.")
            else:
                saldo_nuevo = saldo_actual + monto_extra
                _registrar_ajuste(sh, id_prestamo, saldo_actual, saldo_nuevo, fecha)
                st.success(f"Se sumaron {fmt_money(monto_extra)} al saldo de {fila['Cliente']}.")
                st.session_state["panel_abierto"] = None
                load_df.clear()
                st.rerun()


def _panel_editar(sh, fila):
    """Edita como esta el prestamo AHORA (cliente, saldo pendiente, tasa,
    frecuencia) -- no los datos originales de cuando se dio el prestamo.

    Tasa y frecuencia se pueden editar siempre: los pagos ya registrados
    guardan su interes como valor fijo en el momento en que se hicieron
    (ver _panel_pago), no como formula que consulte la tasa actual --
    asi que cambiarla aca solo afecta los pagos que se registren de ahora
    en adelante (por ejemplo, para renegociar la tasa de un prestamo).

    El saldo, si el prestamo ya tiene pagos, no se ajusta tocando el
    Monto prestado sino agregando un "ajuste" como fila nueva de Pagos
    con interes 0 y el abono a capital necesario para llegar al saldo
    pedido -- mantiene "Monto prestado" como el monto original real."""
    id_prestamo = fila["ID Prestamo"]
    saldo_actual = float(fila["Saldo pendiente"])
    tiene_pagos = bool(fila["Fecha ultimo pago"])

    with st.form(f"editar_{id_prestamo}", clear_on_submit=False):
        st.caption("Edita como esta el prestamo ahora mismo (no los datos de cuando se dio).")
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente", value=fila["Cliente"])
        saldo_nuevo = c2.number_input(
            "Saldo pendiente actual (₡)", min_value=0, step=1000, value=round(saldo_actual),
        )
        tasa = c1.number_input(
            "Tasa de interes mensual (%)", min_value=0.0, step=0.5, format="%.2f",
            value=float(fila["Tasa interes (%/periodo)"]) * 100,
            help="Los pagos ya hechos quedan con la tasa que tenian en su momento. "
                 "Cambiar esto (p.ej. para renegociar) solo afecta los pagos nuevos.",
        )
        frecuencia = c2.selectbox(
            "Frecuencia de pago", FRECUENCIAS, index=FRECUENCIAS.index(fila["Frecuencia de pago"]),
        )
        guardar = st.form_submit_button("Guardar cambios")
        if guardar:
            if not cliente:
                st.warning("Completa el nombre del cliente.")
            else:
                ws = sh.worksheet(config.SHEET_PRESTAMOS)
                celda = ws.find(id_prestamo, in_column=1)

                if not tiene_pagos:
                    # Sin pagos todavia: el saldo se ajusta directo via
                    # Monto prestado (no hay historial de por medio).
                    fecha_inicio_actual = datetime.strptime(fila["Fecha inicio"], "%d/%m/%Y").strftime("%Y-%m-%d")
                    ws.update(
                        [[cliente, fecha_inicio_actual, saldo_nuevo, tasa / 100, frecuencia]],
                        f"B{celda.row}:F{celda.row}", value_input_option="USER_ENTERED",
                    )
                else:
                    ws.update([[cliente]], f"B{celda.row}", value_input_option="USER_ENTERED")
                    ws.update(
                        [[tasa / 100, frecuencia]],
                        f"E{celda.row}:F{celda.row}", value_input_option="USER_ENTERED",
                    )
                    if round(saldo_nuevo) != round(saldo_actual):
                        ws_pg = sh.worksheet(config.SHEET_PAGOS)
                        row_pg = next_row(ws_pg, "B")
                        _registrar_ajuste(sh, id_prestamo, saldo_actual, saldo_nuevo)
                st.success("Prestamo actualizado.")
                st.session_state["panel_abierto"] = None
                load_df.clear()
                st.rerun()


def _panel_detalle(sh, fila, pagos_df):
    id_prestamo = fila["ID Prestamo"]
    d1, d2, d3 = st.columns(3)
    d1.metric("Monto prestado", fmt_money(fila["Monto prestado"]))
    d2.metric("Total pagado", fmt_money(fila["Total pagado"]))
    d3.metric("Interes cobrado", fmt_money(fila["Interes cobrado"]))
    st.caption(
        f"ID: {id_prestamo} · Inicio: {fila['Fecha inicio']} · "
        f"Frecuencia: {fila['Frecuencia de pago']} · "
        f"Ultimo pago: {fila['Fecha ultimo pago'] or 'aun no paga'}"
    )

    historial = pagos_df[pagos_df["ID Prestamo"] == id_prestamo] if not pagos_df.empty else pagos_df
    if historial.empty:
        st.caption("Todavia no tiene pagos registrados.")
    else:
        render_tabla(con_tipo_pago(historial), PAGOS_COLS_ORDEN)

    if st.session_state.get("confirmar_borrado") == id_prestamo:
        st.warning(
            f"Esto elimina el prestamo {id_prestamo} y todos sus pagos registrados. "
            "No se puede deshacer. ¿Confirmas?"
        )
        cconf, ccancel = st.columns(2)
        if cconf.button("Si, eliminar definitivamente", key=f"conf_del_{id_prestamo}", type="primary"):
            eliminar_prestamo(sh, id_prestamo)
            st.session_state.pop("confirmar_borrado", None)
            st.session_state["panel_abierto"] = None
            load_df.clear()
            st.success(f"Prestamo {id_prestamo} eliminado.")
            st.rerun()
        if ccancel.button("Cancelar", key=f"canc_del_{id_prestamo}"):
            st.session_state.pop("confirmar_borrado", None)
            st.rerun()
    else:
        if st.button("🗑️ Eliminar este prestamo", key=f"del_{id_prestamo}"):
            st.session_state["confirmar_borrado"] = id_prestamo
            st.rerun()


# Dentro de un st.form, Enter normalmente envia el formulario de una vez
# (comportamiento nativo de <form> en HTML), sin importar en que campo este
# el cursor. Esto hace que avance al siguiente campo de texto/numero en vez
# de enviar, y en el ultimo campo si envia. No toca selectbox ni date_input
# (esos ya tienen su propio manejo de Enter para abrir/confirmar opciones).
ENTER_AVANZA_CAMPO_JS = """
<script>
const doc = window.parent.document;

function esCampoDeAvance(el) {
    if (!el || el.tagName !== 'INPUT') return false;
    if (el.type !== 'text' && el.type !== 'number') return false;
    if (el.getAttribute('role') === 'combobox') return false;
    if (el.closest('[data-baseweb="select"]')) return false;
    if (el.closest('[data-baseweb="datepicker"]')) return false;
    if (el.closest('[data-baseweb="calendar"]')) return false;
    return true;
}

function attachEnterNav(form) {
    if (form.dataset.enterNavAttached) return;
    form.dataset.enterNavAttached = '1';
    form.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        if (!esCampoDeAvance(e.target)) return;
        e.preventDefault();
        e.stopPropagation();
        const focusables = Array.from(
            form.querySelectorAll('input, select, textarea, [tabindex]')
        ).filter((el) => el.offsetParent !== null && !el.disabled);
        const idx = focusables.indexOf(e.target);
        if (idx > -1 && idx < focusables.length - 1) {
            focusables[idx + 1].focus();
        } else {
            const btn = form.querySelector('button[kind="formSubmit"], button[type="submit"]');
            if (btn) btn.click();
        }
    });
}

function attachAll() {
    doc.querySelectorAll('.stForm').forEach(attachEnterNav);
}

attachAll();
new MutationObserver(attachAll).observe(doc.body, { childList: true, subtree: true });
</script>
"""

# Los campos de monto (numero) se ven con letra mas grande, a juego con los
# montos de las tablas.
CAMPOS_MONTO_CSS = """
<style>
div[data-testid="stNumberInput"] input {
    font-size: 1.25rem !important;
    font-weight: 600 !important;
}
</style>
"""

def verificar_password():
    """Si hay un secret 'app_password' configurado (deploy en la nube),
    pide contrasena antes de mostrar nada mas. En local, sin ese secret,
    no pide nada -- ya esta protegido por necesitar credenciales.json."""
    try:
        clave_esperada = st.secrets.get("app_password")
    except Exception:
        clave_esperada = None

    if not clave_esperada:
        return True
    if st.session_state.get("autenticado"):
        return True

    clave = st.text_input("Contraseña", type="password")
    if clave:
        if clave == clave_esperada:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    return False


st.markdown("## \U0001F4B0 Control de Prestamos")
st.caption("Seguimiento de prestamos, pagos e intereses")

if not verificar_password():
    st.stop()

st.markdown(CAMPOS_MONTO_CSS, unsafe_allow_html=True)
components.html(ENTER_AVANZA_CAMPO_JS, height=0)

try:
    sh = _sheet()
except FileNotFoundError:
    st.error(
        f"No encuentro el archivo de credenciales '{config.CREDENTIALS_FILE}'. "
        "Revisa el paso 1 del README.md."
    )
    st.stop()
except Exception as e:
    st.error(f"No pude conectar con la Hoja de Google: {e}")
    st.stop()

prestamos_df = load_df(config.SHEET_PRESTAMOS)
pagos_df = load_df(config.SHEET_PAGOS)

tab_resumen, tab_prestamos = st.tabs(["Resumen", "Prestamos"])

KPIS_FINANCIEROS = [
    "Total prestado (historico)", "Capital pendiente actual",
    "Total cobrado (capital+interes)", "Interes total cobrado",
]
KPIS_ESTADO = [
    ("Prestamos activos", "\U0001F7E2"), ("Prestamos atrasados", "\U0001F534"),
    ("Prestamos pagados", "✅"),
]

with tab_resumen:
    resumen_ws = sh.worksheet(config.SHEET_RESUMEN)
    kpis = resumen_ws.get("A4:B11")
    if len(kpis) > 1:
        datos = dict(kpis[1:])

        st.markdown("##### Resumen financiero")
        cols = st.columns(4)
        for i, label in enumerate(KPIS_FINANCIEROS):
            if label in datos:
                cols[i].metric(label, fmt_money(datos[label]))

        st.markdown("##### Estado de prestamos")
        cols = st.columns(3)
        for i, (label, icono) in enumerate(KPIS_ESTADO):
            if label in datos:
                cols[i].metric(f"{icono} {label}", datos[label])

    st.divider()
    if not prestamos_df.empty and "Estado" in prestamos_df.columns:
        atrasados = prestamos_df[prestamos_df["Estado"] == "Atrasado"]
        if not atrasados.empty:
            st.subheader("⚠️ Prestamos atrasados")
            render_tabla(atrasados[["Cliente", "Saldo pendiente", "Fecha ultimo pago", "Dias desde referencia"]])
        else:
            st.success("Ningun prestamo atrasado ahora mismo.")

with tab_prestamos:
    if prestamos_df.empty:
        st.info("Aun no hay prestamos registrados.")
    else:
        base_df = prestamos_df.copy()
        factor = base_df["Frecuencia de pago"].map(FACTOR_FRECUENCIA).fillna(1)
        base_df["Monto"] = (
            pd.to_numeric(base_df["Saldo pendiente"], errors="coerce")
            * pd.to_numeric(base_df["Tasa interes (%/periodo)"], errors="coerce")
            * factor
        ).apply(redondear_500)
        # Proximo pago = siguiente fecha fija de calendario (15/30, etc.)
        # despues del ultimo pago (o del inicio, si aun no pago nada).
        fecha_ref = base_df["Fecha ultimo pago"].replace("", pd.NA).fillna(base_df["Fecha inicio"])
        fecha_ref = pd.to_datetime(fecha_ref, format="%d/%m/%Y", errors="coerce")
        base_df["Proximo pago"] = [
            proximo_pago(f.date(), frec).strftime("%d/%m/%Y") if pd.notna(f) else ""
            for f, frec in zip(fecha_ref, base_df["Frecuencia de pago"])
        ]

        dias_atraso = (
            pd.to_numeric(base_df["Dias desde referencia"], errors="coerce")
            - pd.to_numeric(base_df["Dias max permitidos"], errors="coerce")
        ).fillna(0)
        tiene_pagos = base_df["Fecha ultimo pago"] != ""
        base_df["Categoria"] = [
            clasificar_prestamo(estado, da, tp)
            for estado, da, tp in zip(base_df["Estado"], dias_atraso, tiene_pagos)
        ]

        visibles = base_df[base_df["Estado"] != "Pagado"].reset_index(drop=True)
        pagados = base_df[base_df["Estado"] == "Pagado"].reset_index(drop=True)

        st.subheader("Prestamos activos")
        if visibles.empty:
            st.info("No hay prestamos activos (todos estan pagados).")
        else:
            hcols = st.columns([1.9, 1.3, 0.8, 1.3, 1.3, 0.45, 0.45, 0.45, 0.45])
            for h, texto in zip(hcols, ["Cliente", "Saldo pendiente", "Interes", "Monto", "Proximo pago", "", "", "", ""]):
                h.markdown(f"**{texto}**")

            for _, fila in visibles.iterrows():
                id_prestamo = fila["ID Prestamo"]
                key = f"fila_{id_prestamo}"
                with st.container(key=key, border=True):
                    c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(
                        [1.9, 1.3, 0.8, 1.3, 1.3, 0.45, 0.45, 0.45, 0.45]
                    )
                    c1.markdown(f"**{fila['Cliente']}**")
                    c2.markdown(fmt_money(fila["Saldo pendiente"]))
                    c3.markdown(fmt_pct(fila["Tasa interes (%/periodo)"]))
                    c4.markdown(fmt_money(fila["Monto"]))
                    c5.markdown(fila["Proximo pago"])
                    ver_click = c6.button("👁️", key=f"ver_{id_prestamo}", help="Ver detalle")
                    pagar_click = c7.button("💰", key=f"pagar_{id_prestamo}", help="Registrar pago")
                    mas_click = c8.button("➕", key=f"mas_{id_prestamo}", help="Prestar mas (sumar al saldo)")
                    editar_click = c9.button("✏️", key=f"editar_{id_prestamo}", help="Editar prestamo")

                    panel = st.session_state.get("panel_abierto")
                    if panel and panel[0] == id_prestamo:
                        st.markdown("---")
                        if panel[1] == "detalle":
                            _panel_detalle(sh, fila, pagos_df)
                        elif panel[1] == "pago":
                            _panel_pago(sh, fila)
                        elif panel[1] == "mas":
                            _panel_prestar_mas(sh, fila)
                        elif panel[1] == "editar":
                            _panel_editar(sh, fila)

                color = CATEGORIA_COLOR.get(fila["Categoria"], "transparent")
                st.markdown(
                    f"<style>.st-key-{key} {{ background: {color}; border-radius: 12px; }}</style>",
                    unsafe_allow_html=True,
                )

                if ver_click or pagar_click or mas_click or editar_click:
                    if ver_click:
                        tipo = "detalle"
                    elif pagar_click:
                        tipo = "pago"
                    elif mas_click:
                        tipo = "mas"
                    else:
                        tipo = "editar"
                    actual = st.session_state.get("panel_abierto")
                    st.session_state["panel_abierto"] = None if actual == (id_prestamo, tipo) else (id_prestamo, tipo)
                    st.rerun()

            st.caption("🟢 Nuevo · 🟣 Ya viene pagando · 🟠 Atrasado (hasta 5 dias) · 🔴 Atrasado (mas de 5 dias)")

    st.divider()
    with st.expander("➕ Agregar nuevo prestamo"):
        with st.form("nuevo_prestamo", clear_on_submit=True):
            c1, c2 = st.columns(2)
            cliente = c1.text_input("Cliente")
            fecha_inicio = c2.date_input("Fecha de inicio", value=date.today())
            monto = c1.number_input("Monto prestado (₡)", min_value=0, step=1000)
            tasa = c2.number_input(
                "Tasa de interes mensual (%)", min_value=0.0, step=0.5, format="%.2f",
                help="Siempre mensual. Si la frecuencia de pago es Quincenal, Semanal o "
                     "Diario, el interes de cada pago se prorratea automaticamente.",
            )
            frecuencia = c1.selectbox("Frecuencia de pago", FRECUENCIAS)
            submitted = st.form_submit_button("Guardar prestamo")
            if submitted:
                if not cliente or monto <= 0:
                    st.warning("Completa al menos Cliente y Monto prestado.")
                else:
                    ws = sh.worksheet(config.SHEET_PRESTAMOS)
                    row = next_row(ws, "B")
                    ws.update(
                        [[cliente, fecha_inicio.strftime("%Y-%m-%d"), monto, tasa / 100, frecuencia]],
                        f"B{row}:F{row}", value_input_option="USER_ENTERED",
                    )
                    st.success(f"Prestamo de {cliente} guardado.")
                    load_df.clear()
                    st.rerun()

    if not prestamos_df.empty:
        with st.expander(f"📁 Prestamos pagados ({len(pagados)})"):
            if pagados.empty:
                st.caption("Todavia no hay prestamos completamente pagados.")
            else:
                render_tabla(pagados[["Cliente", "Monto prestado", "Total pagado", "Interes cobrado"]])

    if not pagos_df.empty:
        with st.expander("Ver historial completo de pagos"):
            render_tabla(con_tipo_pago(pagos_df), PAGOS_COLS_ORDEN)
