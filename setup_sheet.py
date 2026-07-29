"""
Construye (una sola vez) la estructura de la Hoja de Google: pestanas
Prestamos, Pagos y Resumen, con formulas, formato y validacion de datos.

Correlo despues de:
  1. Crear tu cuenta de servicio y guardar el JSON como credenciales.json
     en esta misma carpeta (ver README.md).
  2. Compartir la Hoja de Google con el correo de esa cuenta de servicio
     (rol Editor).

Es seguro volver a correrlo: si las pestanas ya existen, las vuelve a
dejar en el estado inicial (headers + formulas), pero NO borra pagos o
prestamos que ya hayas escrito en las columnas de entrada -- para eso,
haz una copia de respaldo de la hoja antes de re-correrlo.
"""

import gspread

import config
from calculos import DIAS_POR_FRECUENCIA
from sheets_client import get_spreadsheet

FONT = "Arial"
HEADER_BG = {"red": 0.12, "green": 0.31, "blue": 0.47}
HEADER_FG = {"red": 1, "green": 1, "blue": 1}
INPUT_FG = {"red": 0, "green": 0, "blue": 1}
YELLOW_BG = {"red": 1, "green": 1, "blue": 0}

CUR_FMT = {"type": "CURRENCY", "pattern": '"₡"#,##0'}
PCT_FMT = {"type": "PERCENT", "pattern": "0.0%"}
DATE_FMT = {"type": "DATE", "pattern": "dd/mm/yyyy"}

PRESTAMOS_HEADERS = [
    "ID Prestamo", "Cliente", "Fecha inicio", "Monto prestado",
    "Tasa interes (%/periodo)", "Frecuencia de pago", "Saldo pendiente",
    "Total pagado", "Interes cobrado", "Fecha ultimo pago",
    "Dias desde referencia", "Dias max permitidos", "Estado",
]

PAGOS_HEADERS = [
    "ID Pago", "ID Prestamo", "Cliente", "Fecha de pago", "Monto pagado",
    "Saldo anterior", "Interes del periodo", "Abono a capital", "Saldo nuevo",
]

# Cuantas filas de formulas de arrastre (Saldo anterior/Interes/Abono/Saldo
# nuevo en Pagos) se pre-escriben. Se puede arrastrar mas abajo a mano si
# se llenan todas.
PAGOS_PREFILL_ROWS = 500


def _ifs_dias_por_frecuencia(expr_frecuencia, default):
    """IFS(expr="Diario",1, expr="Semanal",7, ...) a partir de
    DIAS_POR_FRECUENCIA -- para no repetir esos numeros sueltos en cada
    formula que los necesita."""
    partes = [f'{expr_frecuencia}="{frec}",{dias}' for frec, dias in DIAS_POR_FRECUENCIA.items()]
    partes.append(f"TRUE,{default}")
    return f"IFS({','.join(partes)})"


def _ifs_factor_frecuencia(expr_frecuencia):
    """Igual que _ifs_dias_por_frecuencia pero como fraccion de un mes de
    30 dias (el factor de prorrateo sobre la tasa mensual)."""
    partes = [f'{expr_frecuencia}="{frec}",{dias}/30' for frec, dias in DIAS_POR_FRECUENCIA.items()]
    partes.append("TRUE,1")
    return f"IFS({','.join(partes)})"


def get_or_create_ws(sh, title, rows, cols):
    try:
        ws = sh.worksheet(title)
        ws.resize(rows=rows, cols=cols)
        return ws
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=rows, cols=cols)


def setup_prestamos(sh):
    ws = get_or_create_ws(sh, config.SHEET_PRESTAMOS, rows=1000, cols=13)

    ws.update([PRESTAMOS_HEADERS], "A1:M1", value_input_option="USER_ENTERED")
    ws.format("A1:M1", {
        "backgroundColor": HEADER_BG,
        "textFormat": {"foregroundColor": HEADER_FG, "bold": True, "fontFamily": FONT},
        "wrapStrategy": "WRAP",
    })

    # Nota: los rangos van acotados (p.ej. B2:B1000) y no abiertos (B2:B).
    # Los rangos de columna abiertos dentro de ARRAYFORMULA combinados con
    # SUMIF/COUNTIF/MAXIFS producen errores ("Argument must be a range" /
    # "Unresolved sheet name") en Google Sheets -- se probo en vivo.
    formulas = {
        "A2": '=ARRAYFORMULA(IF(B2:B1000="","","P"&TEXT(ROW(B2:B1000)-1,"000")))',
        "G2": '=ARRAYFORMULA(IF(B2:B1000="","",D2:D1000-SUMIF(Pagos!$B$2:$B1000,A2:A1000,Pagos!$H$2:$H1000)))',
        "H2": '=ARRAYFORMULA(IF(B2:B1000="","",SUMIF(Pagos!$B$2:$B1000,A2:A1000,Pagos!$E$2:$E1000)))',
        "I2": '=ARRAYFORMULA(IF(B2:B1000="","",SUMIF(Pagos!$B$2:$B1000,A2:A1000,Pagos!$G$2:$G1000)))',
        "J2": '=ARRAYFORMULA(IF(B2:B1000="","",IF(COUNTIF(Pagos!$B$2:$B1000,A2:A1000)=0,"",MAXIFS(Pagos!$D$2:$D1000,Pagos!$B$2:$B1000,A2:A1000))))',
        "K2": '=ARRAYFORMULA(IF(B2:B1000="","",IF(J2:J1000="",TODAY()-C2:C1000,TODAY()-J2:J1000)))',
        "L2": (
            '=ARRAYFORMULA(IF(B2:B1000="","",'
            f"{_ifs_dias_por_frecuencia('F2:F1000', 30)}+Resumen!$B$2))"
        ),
        "M2": '=ARRAYFORMULA(IF(B2:B1000="","",IF(G2:G1000<=0,"Pagado",IF(K2:K1000>L2:L1000,"Atrasado","Al dia"))))',
    }
    for cell, formula in formulas.items():
        ws.update([[formula]], cell, value_input_option="USER_ENTERED")

    ws.format("B2:B1000", {"textFormat": {"foregroundColor": INPUT_FG, "fontFamily": FONT}})
    ws.format("C2:C1000", {"textFormat": {"foregroundColor": INPUT_FG, "fontFamily": FONT}, "numberFormat": DATE_FMT})
    ws.format("D2:D1000", {"textFormat": {"foregroundColor": INPUT_FG, "fontFamily": FONT}, "numberFormat": CUR_FMT})
    ws.format("E2:E1000", {"textFormat": {"foregroundColor": INPUT_FG, "fontFamily": FONT}, "numberFormat": PCT_FMT})
    ws.format("F2:F1000", {"textFormat": {"foregroundColor": INPUT_FG, "fontFamily": FONT}})
    ws.format("G2:I1000", {"numberFormat": CUR_FMT})
    ws.format("J2:J1000", {"numberFormat": DATE_FMT})

    ws.freeze(rows=1)
    return ws


def setup_pagos(sh):
    ws = get_or_create_ws(sh, config.SHEET_PAGOS, rows=1000, cols=9)

    ws.update([PAGOS_HEADERS], "A1:I1", value_input_option="USER_ENTERED")
    ws.format("A1:I1", {
        "backgroundColor": HEADER_BG,
        "textFormat": {"foregroundColor": HEADER_FG, "bold": True, "fontFamily": FONT},
        "wrapStrategy": "WRAP",
    })

    ws.update([['=ARRAYFORMULA(IF(B2:B1000="","","PG"&TEXT(ROW(B2:B1000)-1,"0000")))']],
              "A2", value_input_option="USER_ENTERED")
    ws.update([['=ARRAYFORMULA(IF(B2:B1000="","",IFERROR(VLOOKUP(B2:B1000,Prestamos!$A$2:$B1000,2,FALSE),"ID invalido")))']],
              "C2", value_input_option="USER_ENTERED")

    # F, G, H, I dependen del saldo acumulado de pagos anteriores del MISMO
    # prestamo, asi que se escriben fila por fila (no como ARRAYFORMULA).
    #
    # La tasa en Prestamos!E es SIEMPRE mensual, sin importar la frecuencia
    # de pago del prestamo. El interes de cada pago se prorratea segun esa
    # frecuencia (mismos dias de referencia que Prestamos!L: Diario=1,
    # Semanal=7, Quincenal=15, Mensual=30, sobre un mes de 30 dias).
    rows_fgh_i = []
    for row in range(2, PAGOS_PREFILL_ROWS + 1):
        f = (f'=IF(B{row}="","",IFERROR(VLOOKUP(B{row},Prestamos!$A:$D,4,FALSE)'
             f'-SUMIFS($H$1:H{row - 1},$B$1:B{row - 1},B{row}),"ID invalido"))')
        frecuencia = f'IFERROR(VLOOKUP(B{row},Prestamos!$A:$F,6,FALSE),"")'
        factor = _ifs_factor_frecuencia(frecuencia)
        g = (f'=IF(B{row}="","",IF(F{row}="ID invalido","",'
             f'F{row}*IFERROR(VLOOKUP(B{row},Prestamos!$A:$E,5,FALSE),0)*{factor}))')
        h = f'=IF(B{row}="","",IF(F{row}="ID invalido","",MAX(0,E{row}-G{row})))'
        i = f'=IF(B{row}="","",IF(F{row}="ID invalido","",F{row}-H{row}))'
        rows_fgh_i.append([f, g, h, i])
    ws.update(rows_fgh_i, f"F2:I{PAGOS_PREFILL_ROWS}", value_input_option="USER_ENTERED")

    ws.format("B2:B1000", {"textFormat": {"foregroundColor": INPUT_FG, "fontFamily": FONT}})
    ws.format("D2:D1000", {"textFormat": {"foregroundColor": INPUT_FG, "fontFamily": FONT}, "numberFormat": DATE_FMT})
    ws.format("E2:E1000", {"textFormat": {"foregroundColor": INPUT_FG, "fontFamily": FONT}, "numberFormat": CUR_FMT})
    ws.format("F2:I1000", {"numberFormat": CUR_FMT})

    ws.freeze(rows=1)
    return ws


def setup_resumen(sh):
    ws = get_or_create_ws(sh, config.SHEET_RESUMEN, rows=20, cols=3)

    ws.update([["Resumen General - Control de Prestamos"]], "A1", value_input_option="USER_ENTERED")
    ws.format("A1", {"textFormat": {"bold": True, "fontSize": 14, "fontFamily": FONT}})

    ws.update([
        ["Dias de gracia antes de marcar Atrasado", 3,
         "Supuesto ajustable: dias extra de tolerancia sumados al ciclo de pago antes de marcar un prestamo como Atrasado."],
    ], "A2:C2", value_input_option="USER_ENTERED")
    ws.format("B2", {"backgroundColor": YELLOW_BG, "textFormat": {"foregroundColor": INPUT_FG, "fontFamily": FONT}})
    ws.format("C2", {"textFormat": {"italic": True, "fontSize": 9, "fontFamily": FONT}})

    rows = [
        ["Indicador", "Valor"],
        ["Total prestado (historico)", "=SUM(Prestamos!D2:D1000)"],
        ["Capital pendiente actual", "=SUM(Prestamos!G2:G1000)"],
        ["Total cobrado (capital+interes)", "=SUM(Prestamos!H2:H1000)"],
        ["Interes total cobrado", "=SUM(Prestamos!I2:I1000)"],
        # Ojo: se compara contra la columna B (Cliente, entrada manual) y no A
        # (ID, resultado de ARRAYFORMULA) -- las celdas vacias de una columna
        # generada por ARRAYFORMULA no se detectan igual con el criterio "<>"
        # que una celda realmente vacia; se probo en vivo.
        ["Prestamos activos", '=COUNTIFS(Prestamos!B2:B1000,"<>",Prestamos!M2:M1000,"<>Pagado")'],
        ["Prestamos atrasados", '=COUNTIF(Prestamos!M2:M1000,"Atrasado")'],
        ["Prestamos pagados", '=COUNTIF(Prestamos!M2:M1000,"Pagado")'],
    ]
    ws.update(rows, "A4:B11", value_input_option="USER_ENTERED")
    ws.format("A4:B4", {"textFormat": {"bold": True, "fontFamily": FONT}})
    ws.format("B5:B8", {"numberFormat": CUR_FMT})

    ws.update([["Consejo: usa el filtro (icono de embudo) de la pestana Prestamos, columna Estado, "
                "para ver solo los Atrasados."]], "A13", value_input_option="USER_ENTERED")
    ws.format("A13", {"textFormat": {"italic": True, "fontSize": 9, "fontFamily": FONT}})

    ws.columns_auto_resize(0, 3)
    return ws


def add_data_validation(sh):
    prestamos_id = sh.worksheet(config.SHEET_PRESTAMOS).id
    pagos_id = sh.worksheet(config.SHEET_PAGOS).id

    requests = [
        {  # Frecuencia de pago -> lista fija
            "setDataValidation": {
                "range": {"sheetId": prestamos_id, "startRowIndex": 1, "endRowIndex": 1000,
                          "startColumnIndex": 5, "endColumnIndex": 6},
                "rule": {
                    "condition": {"type": "ONE_OF_LIST", "values": [
                        {"userEnteredValue": v} for v in
                        ["Diario", "Semanal", "Quincenal", "Mensual"]
                    ]},
                    "showCustomUi": True,
                    "strict": True,
                },
            }
        },
        {  # ID Prestamo en Pagos -> debe existir en Prestamos!A
            "setDataValidation": {
                "range": {"sheetId": pagos_id, "startRowIndex": 1, "endRowIndex": 1000,
                          "startColumnIndex": 1, "endColumnIndex": 2},
                "rule": {
                    "condition": {"type": "ONE_OF_RANGE", "values": [
                        {"userEnteredValue": f"={config.SHEET_PRESTAMOS}!$A$2:$A$1000"}
                    ]},
                    "showCustomUi": True,
                    "strict": True,
                },
            }
        },
        {  # Estado: Atrasado en rojo, Pagado en verde, Al dia en azul claro
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": prestamos_id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 12, "endColumnIndex": 13}],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Atrasado"}]},
                        "format": {"backgroundColor": {"red": 0.97, "green": 0.8, "blue": 0.68}},
                    },
                },
                "index": 0,
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": prestamos_id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 12, "endColumnIndex": 13}],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Pagado"}]},
                        "format": {"backgroundColor": {"red": 0.78, "green": 0.88, "blue": 0.71}},
                    },
                },
                "index": 1,
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": prestamos_id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 12, "endColumnIndex": 13}],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Al dia"}]},
                        "format": {"backgroundColor": {"red": 0.85, "green": 0.88, "blue": 0.95}},
                    },
                },
                "index": 2,
            }
        },
    ]
    sh.batch_update({"requests": requests})


def add_example(sh):
    prestamos = sh.worksheet(config.SHEET_PRESTAMOS)
    pagos = sh.worksheet(config.SHEET_PAGOS)
    if prestamos.acell("B2").value:
        return  # ya hay datos, no pisar nada
    prestamos.update([["Cliente Ejemplo", "2026-06-01", 100000, 0.10, "Quincenal"]],
                      "B2:F2", value_input_option="USER_ENTERED")
    # Columna C de Pagos es formula (Cliente, lookup) -- NO escribir ahi.
    # Se escribe B (ID Prestamo) y D:E (Fecha, Monto) por separado.
    pagos.update([["P001"], ["P001"]], "B2:B3", value_input_option="USER_ENTERED")
    pagos.update([
        ["2026-06-15", 15000],
        ["2026-06-30", 12000],
    ], "D2:E3", value_input_option="USER_ENTERED")


def remove_default_sheet(sh):
    for title in ("Sheet1", "Hoja 1", "Hoja1"):
        try:
            ws = sh.worksheet(title)
            sh.del_worksheet(ws)
        except gspread.WorksheetNotFound:
            pass


def main():
    sh = get_spreadsheet()
    setup_resumen(sh)
    setup_prestamos(sh)
    setup_pagos(sh)
    add_data_validation(sh)
    add_example(sh)
    remove_default_sheet(sh)
    sh.reorder_worksheets([sh.worksheet(config.SHEET_RESUMEN),
                            sh.worksheet(config.SHEET_PRESTAMOS),
                            sh.worksheet(config.SHEET_PAGOS)])
    print("Listo. Estructura creada en:", sh.url)


if __name__ == "__main__":
    main()
