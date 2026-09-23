import numpy as np
from replenishment.dunya import dunya_kur


def test_option_magaza_bes_bedenli_ve_sirali():
    d = dunya_kur()
    assert d.oc_hucre.shape[1] == 5
    # her satırın hücreleri aynı mağaza ve aynı option'a ait
    for oc in range(0, len(d.oc_hucre), 97):
        magazalar = set(d.hucre_magaza[d.oc_hucre[oc]])
        assert magazalar == {d.oc_magaza[oc]}


def test_gun_indeksi():
    d = dunya_kur()
    assert d.gun("2025-01-01") == 0
    assert d.gun("2025-09-01") == 243
    assert str(d.tarihler[243]) == "2025-09-01"


def test_zincir_beden_payi_toplami_bir():
    assert abs(dunya_kur().zincir_beden_payi.sum() - 1) < 1e-9
