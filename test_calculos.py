from datetime import date

import pytest

from calculos import (
    FACTOR_FRECUENCIA,
    PAGOS_POR_MES,
    calcular_abono_capital,
    calcular_pago,
    clasificar_prestamo,
    fmt_money,
    fmt_pct,
    proximo_pago,
    redondear_500,
    siguiente_fila_libre,
)


def test_redondear_500():
    assert redondear_500(0) == 0
    assert redondear_500(249) == 0
    assert redondear_500(250) == 500  # empate redondea hacia arriba
    assert redondear_500(4750) == 5000
    assert redondear_500(4200) == 4000
    assert redondear_500(5000) == 5000


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
    # El prorrateo es "1 dividido entre pagos por mes", no por dias
    # calendario: semanal se divide entre 4 (no entre 30/7).
    semanal = calcular_pago(100_000, 0.10, "Semanal", 20_000)
    assert semanal["interes"] == round(100_000 * 0.10 / 4)

    # 100.000 * 10% / 30 = 333.33... -> se redondea al multiplo de 500
    # mas cercano (500 en este caso, ya que 333 esta mas cerca de 500 que de 0).
    diario = calcular_pago(100_000, 0.10, "Diario", 20_000)
    assert diario["interes"] == 500


def test_calcular_pago_redondea_interes_y_abono_a_multiplos_de_500():
    r = calcular_pago(saldo_anterior=100_000, tasa_mensual=0.10, frecuencia="Diario", monto_pagado=20_000)
    assert r["interes"] == 500
    assert r["abono"] == 19_500  # 20.000 - 500, ya es multiplo de 500

    # Un caso donde el abono en bruto NO cae justo en un multiplo de 500.
    r2 = calcular_pago(saldo_anterior=100_000, tasa_mensual=0.10, frecuencia="Diario", monto_pagado=20_200)
    assert r2["interes"] == 500
    assert r2["abono"] == 19_500  # 20.200-500=19.700 -> redondea a 19.500


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


def test_calcular_pago_no_supera_el_saldo_si_pagan_de_mas():
    # Saldo 10.000, interes 1.000, pagan 50.000: el abono no puede
    # superar el saldo (no queda en negativo).
    r = calcular_pago(saldo_anterior=10_000, tasa_mensual=0.10, frecuencia="Mensual", monto_pagado=50_000)
    assert r["abono"] == 10_000
    assert r["saldo_nuevo"] == 0


def test_calcular_abono_capital_no_cobra_interes():
    r = calcular_abono_capital(saldo_anterior=50_000, monto_pagado=20_000)
    assert r["interes"] == 0
    assert r["abono"] == 20_000
    assert r["saldo_nuevo"] == 30_000


def test_calcular_abono_capital_no_supera_el_saldo():
    r = calcular_abono_capital(saldo_anterior=15_000, monto_pagado=20_000)
    assert r["abono"] == 15_000
    assert r["saldo_nuevo"] == 0


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


def test_factor_frecuencia_se_deriva_de_pagos_por_mes():
    # FACTOR_FRECUENCIA tiene que ser exactamente 1 / PAGOS_POR_MES -- son
    # la misma fuente que usa setup_sheet.py para generar la formula de
    # la hoja. Si esto falla, Python y la hoja quedaron calculando el
    # prorrateo de forma distinta.
    assert set(FACTOR_FRECUENCIA) == set(PAGOS_POR_MES)
    for frecuencia, pagos in PAGOS_POR_MES.items():
        assert FACTOR_FRECUENCIA[frecuencia] == pytest.approx(1 / pagos)
    assert PAGOS_POR_MES == {"Diario": 30, "Semanal": 4, "Quincenal": 2, "Mensual": 1}
    assert FACTOR_FRECUENCIA["Semanal"] == pytest.approx(0.25)
    assert FACTOR_FRECUENCIA["Quincenal"] == pytest.approx(0.5)


def test_clasificar_prestamo_pagado():
    assert clasificar_prestamo("Pagado", dias_atraso=0, tiene_pagos=True) == "pagado"
    # Pagado manda sin importar dias_atraso/tiene_pagos.
    assert clasificar_prestamo("Pagado", dias_atraso=99, tiene_pagos=False) == "pagado"


def test_clasificar_prestamo_atrasado_leve_vs_grave():
    assert clasificar_prestamo("Atrasado", dias_atraso=1, tiene_pagos=True) == "atrasado_leve"
    assert clasificar_prestamo("Atrasado", dias_atraso=5, tiene_pagos=True) == "atrasado_leve"
    assert clasificar_prestamo("Atrasado", dias_atraso=6, tiene_pagos=True) == "atrasado_grave"
    assert clasificar_prestamo("Atrasado", dias_atraso=30, tiene_pagos=False) == "atrasado_grave"


def test_clasificar_prestamo_al_dia_nuevo_vs_con_pagos():
    assert clasificar_prestamo("Al dia", dias_atraso=0, tiene_pagos=False) == "nuevo"
    assert clasificar_prestamo("Al dia", dias_atraso=0, tiene_pagos=True) == "con_pagos"


def test_proximo_pago_mensual_es_el_30():
    assert proximo_pago(date(2026, 7, 10), "Mensual") == date(2026, 7, 30)
    # Justo en el checkpoint: el proximo es el del mes siguiente.
    assert proximo_pago(date(2026, 7, 30), "Mensual") == date(2026, 8, 30)


def test_proximo_pago_quincenal_15_y_30():
    assert proximo_pago(date(2026, 7, 10), "Quincenal") == date(2026, 7, 15)
    assert proximo_pago(date(2026, 7, 16), "Quincenal") == date(2026, 7, 30)
    assert proximo_pago(date(2026, 7, 30), "Quincenal") == date(2026, 8, 15)


def test_proximo_pago_semanal_7_15_22_30():
    assert proximo_pago(date(2026, 7, 1), "Semanal") == date(2026, 7, 7)
    assert proximo_pago(date(2026, 7, 7), "Semanal") == date(2026, 7, 15)
    assert proximo_pago(date(2026, 7, 20), "Semanal") == date(2026, 7, 22)
    assert proximo_pago(date(2026, 7, 31), "Semanal") == date(2026, 8, 7)


def test_proximo_pago_diario_es_el_dia_siguiente():
    assert proximo_pago(date(2026, 7, 29), "Diario") == date(2026, 7, 30)


def test_proximo_pago_respeta_meses_cortos():
    # Febrero 2026 (no bisiesto) tiene 28 dias -- el checkpoint "30" cae
    # en el ultimo dia real del mes.
    assert proximo_pago(date(2026, 2, 1), "Mensual") == date(2026, 2, 28)
    assert proximo_pago(date(2026, 1, 31), "Mensual") == date(2026, 2, 28)


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
