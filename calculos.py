"""Calculos puros de la app (sin Streamlit ni Google Sheets) para poder
probarlos con pytest de forma aislada.

IMPORTANTE: la tasa de interes se guarda siempre como tasa MENSUAL. El
interes de cada pago se prorratea dividiendo esa tasa entre la cantidad
de pagos que entran en un mes (ver PAGOS_POR_MES) -- no es un prorrateo
por dias calendario.

Esta misma regla esta implementada por separado como formula de Google
Sheets en setup_sheet.py (columna G de Pagos, la que manda de verdad
sobre el saldo real). Si cambias el factor o la formula de interes aca,
cambia tambien la formula equivalente en setup_sheet.py -- no hay forma
de compartir codigo entre Python y una formula de hoja de calculo.
"""

import calendar
from datetime import date, timedelta

# Cuantos pagos entran en un mes, segun la frecuencia -- define el
# prorrateo del interes (factor = 1 / pagos_por_mes). Fuente unica:
# setup_sheet.py genera a partir de este mismo diccionario la formula de
# Google Sheets equivalente ("Interes del periodo" en Pagos).
PAGOS_POR_MES = {"Diario": 30, "Semanal": 4, "Quincenal": 2, "Mensual": 1}

FACTOR_FRECUENCIA = {frec: 1 / pagos for frec, pagos in PAGOS_POR_MES.items()}

# Dias calendario reales entre pagos, segun la frecuencia. No tiene
# relacion con el prorrateo de interes de arriba -- se usa solo para
# "Dias max permitidos" (Prestamos!L en setup_sheet.py), que decide
# cuanto puede pasar sin pagar antes de marcar un prestamo Atrasado.
DIAS_POR_FRECUENCIA = {"Diario": 1, "Semanal": 7, "Quincenal": 15, "Mensual": 30}

# Fechas fijas de pago dentro del mes (no "cada N dias desde el ultimo
# pago", sino dias de calendario fijos). Diario no tiene lista fija: el
# proximo pago es siempre el dia siguiente.
DIAS_PAGO_MES = {
    "Semanal": [7, 15, 22, 30],
    "Quincenal": [15, 30],
    "Mensual": [30],
}


def _fecha_checkpoint(anio, mes, dia):
    # Si el mes no llega a ese dia (ej. dia 30 en febrero), usa el ultimo
    # dia real del mes.
    ultimo_dia_mes = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(dia, ultimo_dia_mes))


def proximo_pago(fecha_referencia, frecuencia):
    """Proxima fecha de pago fija segun el calendario (no relativa a la
    fecha de referencia): Mensual = dia 30, Quincenal = 15 y 30, Semanal
    = 7/15/22/30 de cada mes. Diario no tiene fechas fijas, es siempre el
    dia siguiente."""
    if frecuencia == "Diario":
        return fecha_referencia + timedelta(days=1)

    dias_checkpoint = DIAS_PAGO_MES.get(frecuencia, DIAS_PAGO_MES["Mensual"])
    anio, mes = fecha_referencia.year, fecha_referencia.month
    siguiente_mes = mes + 1 if mes < 12 else 1
    siguiente_anio = anio if mes < 12 else anio + 1

    candidatos = [_fecha_checkpoint(anio, mes, d) for d in dias_checkpoint]
    candidatos += [_fecha_checkpoint(siguiente_anio, siguiente_mes, d) for d in dias_checkpoint]

    return min(c for c in candidatos if c > fecha_referencia)


def factor_frecuencia(frecuencia):
    return FACTOR_FRECUENCIA.get(frecuencia, 1)


def calcular_pago(saldo_anterior, tasa_mensual, frecuencia, monto_pagado):
    """Interes, abono a capital y saldo nuevo para un pago normal.

    Si el pago no alcanza a cubrir el interes del periodo, no se abona
    capital ese periodo (el interes no cubierto no se acumula ni genera
    interes sobre interes). El abono nunca supera el saldo pendiente
    (si pagan de mas, el sobrante no se resta del saldo).
    """
    # Redondeado a colones enteros -- no tiene sentido cobrar centavos, y
    # evita que se acumulen residuos fraccionarios de un pago a otro.
    interes = round(saldo_anterior * tasa_mensual * factor_frecuencia(frecuencia))
    abono = min(saldo_anterior, max(0, monto_pagado - interes))
    saldo_nuevo = saldo_anterior - abono
    return {
        "saldo_anterior": saldo_anterior,
        "interes": interes,
        "monto_pagado": monto_pagado,
        "abono": abono,
        "saldo_nuevo": saldo_nuevo,
    }


def calcular_abono_capital(saldo_anterior, monto_pagado):
    """Pago que va 100% a capital, sin cobrar interes -- para cuando el
    cliente ya pago el interes de este periodo en un pago anterior y
    ahora hace un abono extra."""
    abono = min(saldo_anterior, monto_pagado)
    saldo_nuevo = saldo_anterior - abono
    return {
        "saldo_anterior": saldo_anterior,
        "interes": 0,
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


# Umbral para distinguir un atraso leve de uno grave, en dias por encima
# del maximo permitido (no en dias desde el ultimo pago).
DIAS_ATRASO_GRAVE = 5

CATEGORIAS_PRESTAMO = ("pagado", "atrasado_grave", "atrasado_leve", "con_pagos", "nuevo")


def clasificar_prestamo(estado, dias_atraso, tiene_pagos):
    """Categoria visual de un prestamo (para colorear su fila):

    - "pagado": saldo en cero, prestamo cerrado.
    - "atrasado_grave": atrasado con mas de DIAS_ATRASO_GRAVE dias por
      encima del maximo permitido.
    - "atrasado_leve": atrasado pero dentro de esos dias de tolerancia.
    - "con_pagos": al dia y ya registro al menos un pago.
    - "nuevo": al dia pero todavia no ha pagado nada (prestamo reciente).

    dias_atraso es "Dias desde referencia" - "Dias max permitidos" (solo
    tiene sentido cuando estado es "Atrasado"; se ignora en otro caso).
    """
    if estado == "Pagado":
        return "pagado"
    if estado == "Atrasado":
        return "atrasado_grave" if dias_atraso > DIAS_ATRASO_GRAVE else "atrasado_leve"
    return "con_pagos" if tiene_pagos else "nuevo"


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
