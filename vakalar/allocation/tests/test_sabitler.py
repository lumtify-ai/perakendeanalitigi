"""`allocation.sabitler`: Global Constraints'teki değerler, v4 üretecinin payıyla tutarlılık."""

from perakende_veri.v4 import sabitler as v4

from allocation import sabitler


def test_lumoda_ilk_payi_v4_ile_ayni():
    assert v4.ILK_DAGITIM_PAYI == sabitler.LUMODA_ILK_PAYI == 0.70


def test_sezon_ve_line():
    assert (sabitler.OYUN_SEZONU, sabitler.KAL_SEZONU, sabitler.LINE) == ("SS25", "SS24", "Collection")


def test_tutma_duzeyleri_ve_demo():
    assert sabitler.TUTMA_DUZEYLERI == (0.0, 0.15, 0.30, 0.45)
    assert sabitler.DEMO_TUTMA == (0.0, 0.15, 0.30)
    assert set(sabitler.DEMO_TUTMA) <= set(sabitler.TUTMA_DUZEYLERI)


def test_pencere_ve_hiz_sabitleri():
    assert sabitler.ERKEN_GUN == 42
    assert (sabitler.HIZ_GECMIS_GUN, sabitler.HIZ_HEDEF_GUN) == (14, 28)
    assert sabitler.BELIRSIZLIK_TBAR == 0.30 and sabitler.TAVAN_KAPSAMA == 1.0


def test_yol_ve_tohum():
    assert sabitler.YOL_SAYISI == 5 and sabitler.TALEP_TOHUM_TABANI == 20261019
