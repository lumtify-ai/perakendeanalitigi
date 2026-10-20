"""`kumeleme.sabitler`: Global Constraints'teki değerler."""

import pandas as pd
import pytest

from kumeleme import sabitler


def test_karar_gunleri():
    assert sabitler.KARAR_GUNU == pd.Timestamp("2025-02-07")
    assert sabitler.KAL_KARAR_GUNU == pd.Timestamp("2024-02-09")
    # ikisi de cuma: lansman ertesi pazartesi
    assert sabitler.KARAR_GUNU.weekday() == sabitler.KAL_KARAR_GUNU.weekday() == 4


def test_esikler_ve_ciro_sinifi():
    assert sabitler.GECMIS_HAFTA_ESIGI == 26
    assert sabitler.TAM_YIL_HAFTA == 52
    assert sabitler.OZELLIK_HAFTA == 104
    assert (sabitler.CIRO_A, sabitler.CIRO_B) == (0.20, 0.30)
    assert sabitler.CIRO_A + sabitler.CIRO_B < 1          # C kalan
    assert sabitler.K3_EN_AZ == 3


def test_kume_sabitleri():
    assert list(sabitler.K_ARALIK) == [3, 4, 5, 6, 7, 8, 9, 10]
    assert sabitler.EN_KUCUK_KUME == 3 and sabitler.KMEANS_N_INIT == 50


def test_tohum_ve_yol():
    assert sabitler.TOHUM == 20261020 and sabitler.YOL_SAYISI == 5


@pytest.mark.veri
def test_karar_gunleri_yayimlanan_lansmana_uyar():
    """Karar günü, sezonun ilk Collection dalgasının lansmanından 3 gün önce (cuma → pazartesi)."""
    from kumeleme import kaynak
    con = kaynak.baglan()
    try:
        ilk = con.execute("select sezon_kodu, min(lansman_tarihi) as l from urun "
                          "where line = 'Collection' and sezon_kodu in ('SS24', 'SS25') "
                          "group by 1").df().set_index("sezon_kodu")["l"]
    finally:
        con.close()
    assert ilk["SS25"] == sabitler.KARAR_GUNU + pd.Timedelta(days=3)
    assert ilk["SS24"] == sabitler.KAL_KARAR_GUNU + pd.Timedelta(days=3)
