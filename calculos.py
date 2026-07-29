"""Calculos puros de la app (sin Streamlit ni Google Sheets) para poder
probarlos con pytest de forma aislada.

IMPORTANTE: la tasa de interes se guarda siempre como tasa MENSUAL. El
interes de cada pago se prorratea segun la frecuencia (mismos dias de
referencia que "Dias max permitidos" en Prestamos: mes de 30 dias).

Esta misma regla esta implementada por separado como formula de Google
Sheets en setup_sheet.py (columna G de Pagos, la que manda de verdad
sobre el saldo real). Si cambias el factor o la formula de interes aca,
cambia tambien la formula equivalente en setup_sheet.py -- no hay forma
de compartir codigo entre Python y una formula de hoja de calculo.
"""

# Fuente unica de estos dias: setup_sheet.py genera a partir de este mismo
# diccionario las formulas de Google Sheets que usan el mismo prorrateo
# ("Dias max permitidos" en Prestamos e "Interes del periodo" en Pagos),
# en vez de tener los numeros sueltos y repetidos en varios lugares.
DIAS_POR_FRECUENCIA = {"Diario": 1, "Semanal": 7, "Quincenal": 15, "Mensual": 30}

FACTOR_FRECUENCIA = {frec: dias / 30 for frec, dias in DIAS_POR_FRECUENCIA.items()}


def factor_frecuencia(frecuencia):
    return FACTOR_FRECUENCIA.get(frecuencia, 1)


def calcular_pago(saldo_anterior, tasa_mensual, frecuencia, monto_pagado):
    """Interes, abono a capital y saldo nuevo para un pago.

    Si el pago no alcanza a cubrir el interes del periodo, no se abona
    capital ese periodo (el interes no cubierto no se acumula ni genera
    interes sobre interes).
    """
    interes = saldo_anterior * tasa_mensual * factor_frecuencia(frecuencia)
    abono = max(0, monto_pagado - interes)
    saldo_nuevo = saldo_anterior - abono
    return {
        "saldo_anterior": saldo_anterior,
        "interes": interes,
        "monto_pagado": monto_pagado,
        "abono": abono,
        "saldo_nuevo": saldo_nuevo,
    }


def _es_nulo(v):
    return v is None or (isinstance(v, float) and v != v)  # nan != nan


def fmt_money(v):
    if _es_nulo(v):
        return ""
    try:
        # Miles con punto (formato usado en CR), no con coma.
        return f"₡{float(v):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return v


def fmt_pct(v):
    if _es_nulo(v):
        return ""
    try:
        # La hoja guarda la tasa como decimal (0.1 = 10%).
        n = float(v) * 100
        s = f"{n:.1f}".rstrip("0").rstrip(".")
        return f"{s}%"
    except (TypeError, ValueError):
        return v


def siguiente_fila_libre(valores):
    """Primera fila libre despues de la ultima realmente usada, a partir de
    una lista de valores de una columna (incluyendo el encabezado en el
    indice 0). No cuenta celdas llenas (eso falla si hay huecos en el
    medio, p.ej. por un prestamo eliminado) -- busca el indice de fila mas
    alto con datos."""
    ultima_usada = 1  # fila de encabezados
    for i, v in enumerate(valores, start=1):
        if str(v).strip() != "":
            ultima_usada = i
    return ultima_usada + 1
