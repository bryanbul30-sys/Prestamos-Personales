"""App web para llevar el control de prestamos personales.

Corre con:  streamlit run app.py
"""
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import config
from sheets_client import get_spreadsheet

st.set_page_config(page_title="Control de Prestamos", page_icon="\U0001F4B0", layout="wide")

FRECUENCIAS = ["Diario", "Semanal", "Quincenal", "Mensual"]
PAGOS_PREFILL_ROWS = 500

# Columnas mas importantes primero, para que se vean sin hacer scroll
# horizontal en pantallas angostas (celular).
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


def reordenar(df, orden):
    cols = [c for c in orden if c in df.columns]
    cols += [c for c in df.columns if c not in cols]
    return df[cols]


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
    filled = [v for v in values[1:] if str(v).strip() != ""]
    return len(filled) + 2


def fmt_money(v):
    try:
        return f"₡{float(v):,.0f}"
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

st.title("\U0001F4B0 Control de Prestamos")
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

with tab_resumen:
    resumen_ws = sh.worksheet(config.SHEET_RESUMEN)
    kpis = resumen_ws.get("A4:B11")
    if len(kpis) > 1:
        rows = kpis[1:]
        cols = st.columns(4)
        for i, (label, value) in enumerate(rows):
            display = fmt_money(value) if "Prestado" in label or "cobrado" in label or "pendiente" in label else value
            cols[i % 4].metric(label, display)

    st.divider()
    if not prestamos_df.empty and "Estado" in prestamos_df.columns:
        atrasados = prestamos_df[prestamos_df["Estado"] == "Atrasado"]
        if not atrasados.empty:
            st.subheader("⚠️ Prestamos atrasados")
            st.dataframe(
                atrasados[["Cliente", "Saldo pendiente", "Fecha ultimo pago", "Dias desde referencia"]],
                use_container_width=True, hide_index=True,
            )
        else:
            st.success("Ningun prestamo atrasado ahora mismo.")

with tab_prestamos:
    st.subheader("Prestamos registrados")
    if prestamos_df.empty:
        st.info("Aun no hay prestamos registrados.")
    else:
        st.dataframe(reordenar(prestamos_df, PRESTAMOS_COLS_ORDEN), use_container_width=True, hide_index=True)

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
        st.dataframe(reordenar(pagos_df, PAGOS_COLS_ORDEN), use_container_width=True, hide_index=True)
