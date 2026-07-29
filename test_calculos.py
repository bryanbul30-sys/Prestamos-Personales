import pytest

from calculos import DIAS_POR_FRECUENCIA, FACTOR_FRECUENCIA, calcular_pago, fmt_money, fmt_pct, siguiente_fila_libre


def test_calcular_pago_quincenal_abona_capital():
    # 100.000 al 10% mensual, quincenal -> interes = mitad del mes = 5.000
    r = calcular_pago(saldo_anterior=100_000, tasa_mensual=0.10, frecuencia="Quincenal", monto_pagado=20_000)
    assert r["interes"] == 5_000
    assert r["abono"] == 15_000
    assert r["saldo_nuevo"] == 85_000


def test_calcular_pago_mensual_no_prorratea():
    r = calcular_pago(saldo_anterior=100_000, tasa_mensual=0.10, frecuencia="Mensual", monto_pagado=20_000)
    assert r["interes"] == 10_000
    assert r["abono"] == 10_000
    assert r["saldo_nuevo"] == 90_000


def test_calcular_pago_semanal_y_diario():
    semanal = calcular_pago(100_000, 0.10, "Semanal", 20_000)
    assert semanal["interes"] == pytest.approx(100_000 * 0.10 * 7 / 30)

    diario = calcular_pago(100_000, 0.10, "Diario", 20_000)
    assert diario["interes"] == pytest.approx(100_000 * 0.10 * 1 / 30)


def test_calcular_pago_no_cubre_interes_no_abona_capital():
    # Pago menor o igual al interes: no se abona capital ese periodo.
    r = calcular_pago(saldo_anterior=100_000, tasa_mensual=0.10, frecuencia="Quincenal", monto_pagado=3_000)
    assert r["interes"] == 5_000
    assert r["abono"] == 0
    assert r["saldo_nuevo"] == 100_000


def test_calcular_pago_frecuencia_desconocida_no_prorratea():
    # Frecuencia invalida/desconocida cae al factor 1 (no prorratea), no revienta.
    r = calcular_pago(100_000, 0.10, "Bisemanal", 20_000)
    assert r["interes"] == 10_000


def test_fmt_money_usa_punto_de_miles():
    assert fmt_money(100000) == "₡100.000"
    assert fmt_money(1234567) == "₡1.234.567"
    assert fmt_money(0) == "₡0"


def test_fmt_money_valores_nulos():
    assert fmt_money(None) == ""
    assert fmt_money(float("nan")) == ""


def test_fmt_pct_convierte_decimal_a_porcentaje():
    assert fmt_pct(0.10) == "10%"
    assert fmt_pct(0.125) == "12.5%"
    assert fmt_pct(0.15) == "15%"


def test_fmt_pct_valores_nulos():
    assert fmt_pct(None) == ""
    assert fmt_pct(float("nan")) == ""


def test_factor_frecuencia_se_deriva_de_dias_por_frecuencia():
    # FACTOR_FRECUENCIA tiene que ser exactamente DIAS_POR_FRECUENCIA / 30
    # -- son la misma fuente que usa setup_sheet.py para generar las
    # formulas de la hoja. Si esto falla, Python y la hoja quedaron
    # calculando el prorrateo de forma distinta.
    assert set(FACTOR_FRECUENCIA) == set(DIAS_POR_FRECUENCIA)
    for frecuencia, dias in DIAS_POR_FRECUENCIA.items():
        assert FACTOR_FRECUENCIA[frecuencia] == pytest.approx(dias / 30)
    assert DIAS_POR_FRECUENCIA["Mensual"] == 30
    assert FACTOR_FRECUENCIA["Quincenal"] == pytest.approx(0.5)


def test_siguiente_fila_libre_sin_huecos():
    valores = ["Cliente", "Fer", "Jose"]
    assert siguiente_fila_libre(valores) == 4


def test_siguiente_fila_libre_con_hueco_en_el_medio():
    # Fila 3 vacia (prestamo eliminado): el siguiente alta debe ir despues
    # de la ULTIMA fila usada (5), no en la 3 (eso pisaria la fila 4).
    valores = ["Cliente", "Fer", "", "Bray", "Jose"]
    assert siguiente_fila_libre(valores) == 6


def test_siguiente_fila_libre_solo_encabezado():
    assert siguiente_fila_libre(["Cliente"]) == 2
