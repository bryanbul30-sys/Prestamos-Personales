from calculos import DIAS_POR_FRECUENCIA
from setup_sheet import _ifs_dias_por_frecuencia, _ifs_factor_frecuencia


def test_ifs_dias_por_frecuencia_incluye_todas_las_frecuencias():
    formula = _ifs_dias_por_frecuencia("F2:F1000", 30)
    assert formula.startswith("IFS(") and formula.endswith(")")
    for frecuencia, dias in DIAS_POR_FRECUENCIA.items():
        assert f'F2:F1000="{frecuencia}",{dias}' in formula
    assert "TRUE,30" in formula  # valor por defecto


def test_ifs_factor_frecuencia_prorratea_sobre_30_dias():
    formula = _ifs_factor_frecuencia("X")
    for frecuencia, dias in DIAS_POR_FRECUENCIA.items():
        assert f'X="{frecuencia}",{dias}/30' in formula
    assert "TRUE,1" in formula  # valor por defecto: no prorratea
