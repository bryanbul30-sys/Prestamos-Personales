"""App web para llevar el control de prestamos personales.

Corre con:  streamlit run app.py
"""
import html
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import config
from sheets_client import get_spreadsheet

st.set_page_config(page_title="Control de Prestamos", page_icon="\U0001F4B0", layout="wide")

FRECUENCIAS = ["Diario", "Semanal", "Quincenal", "Mensual"]
PAGOS_PREFILL_ROWS = 500

# Orden completo, usado en el expander "Ver todos los detalles".
PRESTAMOS_COLS_ORDEN = [
    "Cliente", "Estado", "Saldo pendiente", "Monto prestado",
    "Fecha ultimo pago", "ID Prestamo", "Fecha inicio",
    "Tasa interes (%/periodo)", "Frecuencia de pago", "Total pagado",
    "Interes cobrado", "Dias desde referencia", "Dias max permitidos",
]
PAGOS_COLS_ORDEN = [
    "Cliente", "Fecha de pago", "Monto pagado", "Saldo nuevo",
    "ID Prestamo", "ID Pago", "Saldo anterior", "Interes del periodo",
    "Abono a capital",
]

COLUMNAS_DINERO = {
    "Monto prestado", "Saldo pendiente", "Total pagado", "Interes cobrado",
    "Monto pagado", "Saldo anterior", "Interes del periodo", "Abono a capital",
    "Saldo nuevo", "Monto",
}
COLUMNAS_PORCENTAJE = {"Tasa interes (%/periodo)", "Interés"}

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
</style>
"""


def reordenar(df, orden):
    cols = [c for c in orden if c in df.columns]
    cols += [c for c in df.columns if c not in cols]
    return df[cols]


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
    """Primera fila libre despues de la ultima realmente usada. No cuenta
    celdas llenas (eso falla si hay huecos en el medio, p.ej. por un
    prestamo eliminado) -- busca el indice de fila mas alto con datos."""
    values = ws.col_values(ord(input_col_letter) - ord("A") + 1)
    ultima_usada = 1  # fila de encabezados
    for i, v in enumerate(values, start=1):
        if str(v).strip() != "":
            ultima_usada = i
    return ultima_usada + 1


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


def fmt_money(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        # Miles con punto (formato usado en CR), no con coma.
        return f"₡{float(v):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return v


def fmt_pct(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        # La hoja guarda la tasa como decimal (0.1 = 10%).
        n = float(v) * 100
        s = f"{n:.1f}".rstrip("0").rstrip(".")
        return f"{s}%"
    except (TypeError, ValueError):
        return v


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

st.markdown("## \U0001F4B0 Control de Prestamos")
st.caption("Seguimiento de prestamos, pagos e intereses")
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

tab_resumen, tab_prestamos, tab_pago = st.tabs(["Resumen", "Prestamos", "Registrar pago"])

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
    st.subheader("Prestamos registrados")
    if prestamos_df.empty:
        st.info("Aun no hay prestamos registrados.")
    else:
        resumen_df = prestamos_df.copy()
        resumen_df["Monto"] = (
            pd.to_numeric(resumen_df["Saldo pendiente"], errors="coerce")
            * pd.to_numeric(resumen_df["Tasa interes (%/periodo)"], errors="coerce")
        )
        resumen_df = resumen_df.rename(columns={"Tasa interes (%/periodo)": "Interés"})
        render_tabla(resumen_df[["Cliente", "Interés", "Monto", "Saldo pendiente", "Estado"]])
        with st.expander("Ver todos los detalles (fechas, montos historicos, ID)"):
            render_tabla(prestamos_df, PRESTAMOS_COLS_ORDEN)

    st.divider()
    st.subheader("Registrar nuevo prestamo")
    with st.form("nuevo_prestamo", clear_on_submit=True):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente")
        fecha_inicio = c2.date_input("Fecha de inicio", value=date.today())
        monto = c1.number_input("Monto prestado (₡)", min_value=0, step=1000)
        tasa = c2.number_input("Tasa de interes por periodo (%)", min_value=0.0, step=0.5, format="%.2f")
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
        st.divider()
        st.subheader("Eliminar prestamo")
        opciones_borrar = {
            f"{r['ID Prestamo']} - {r['Cliente']} (saldo {fmt_money(r['Saldo pendiente'])})": r["ID Prestamo"]
            for _, r in prestamos_df.iterrows()
        }
        etiqueta_borrar = st.selectbox("Prestamo a eliminar", list(opciones_borrar.keys()))
        id_borrar = opciones_borrar[etiqueta_borrar]

        if st.session_state.get("confirmar_borrado") == id_borrar:
            st.warning(
                f"Esto elimina el prestamo {id_borrar} y todos sus pagos registrados. "
                "No se puede deshacer. ¿Confirmas?"
            )
            cconf, ccancel = st.columns(2)
            if cconf.button("Si, eliminar definitivamente", type="primary"):
                eliminar_prestamo(sh, id_borrar)
                st.session_state.pop("confirmar_borrado", None)
                load_df.clear()
                st.success(f"Prestamo {id_borrar} eliminado.")
                st.rerun()
            if ccancel.button("Cancelar"):
                st.session_state.pop("confirmar_borrado", None)
                st.rerun()
        else:
            if st.button("Eliminar este prestamo"):
                st.session_state["confirmar_borrado"] = id_borrar
                st.rerun()

with tab_pago:
    st.subheader("Registrar pago recibido")
    if prestamos_df.empty:
        st.info("Primero registra al menos un prestamo en la pestana Prestamos.")
    else:
        activos = prestamos_df[prestamos_df["Estado"] != "Pagado"] if "Estado" in prestamos_df.columns else prestamos_df
        opciones = {
            f"{r['ID Prestamo']} - {r['Cliente']} (saldo {fmt_money(r['Saldo pendiente'])})": r["ID Prestamo"]
            for _, r in activos.iterrows()
        }
        if not opciones:
            st.info("No hay prestamos activos (todos estan pagados).")
        else:
            with st.form("nuevo_pago", clear_on_submit=True):
                etiqueta = st.selectbox("Prestamo", list(opciones.keys()))
                fecha_pago = st.date_input("Fecha de pago", value=date.today())
                monto_pagado = st.number_input("Monto pagado (₡)", min_value=0, step=1000)
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
                            id_prestamo = opciones[etiqueta]
                            # Columna C (Cliente) es formula -- no se escribe.
                            ws.update([[id_prestamo]], f"B{row}", value_input_option="USER_ENTERED")
                            ws.update(
                                [[fecha_pago.strftime("%Y-%m-%d"), monto_pagado]],
                                f"D{row}:E{row}", value_input_option="USER_ENTERED",
                            )
                            st.success("Pago guardado.")
                            load_df.clear()
                            st.rerun()

    st.divider()
    st.subheader("Historial de pagos")
    if pagos_df.empty:
        st.info("Aun no hay pagos registrados.")
    else:
        render_tabla(pagos_df, PAGOS_COLS_ORDEN)
