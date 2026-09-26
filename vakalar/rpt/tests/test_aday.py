import numpy as np
import pandas as pd
import pytest

from rpt import aday, sansur


@pytest.mark.veri
def test_egitim_yalniz_gecmis_sezonlardan(yol0):
    w = yol0["baglam"].dunya
    sez = w.optionlar["sezon_kodu"].to_numpy()
    for G, beklenen in (("AW24", {"SS24"}), ("SS25", {"SS24", "AW24"})):
        e = yol0["aday"][G]["egitim"]
        assert set(sez[e["option"]]) == beklenen
        assert (e["rpt_sayisi"] == 0).all()
        assert set(sez[yol0["aday"][G]["sinama"]["option"]]) == {G}


@pytest.mark.veri
def test_anlik_kestirim_tablo_kestirimiyle_ayni(veri, yol0):
    """Motor içi (Gorunum) düzeltilmiş talep = Faz A'nın tablo tabanlı kestirimi."""
    e = yol0["aday"]["SS25"]["egitim"]
    w = yol0["baglam"].dunya
    oid = w.optionlar["option_id"].to_numpy()
    hh = veri["hh"]
    for h in (2, 3):
        sat = e[e["h"] == h]
        k = sansur.duzeltilmis_talep(hh[hh["option_id"].isin(oid[sat["option"]])], h).set_index("option_id")
        np.testing.assert_allclose(sat["x"].to_numpy(), k.loc[oid[sat["option"]], "x"].to_numpy())
        np.testing.assert_allclose(sat["D"].to_numpy(), k.loc[oid[sat["option"]], "D"].to_numpy(), rtol=1e-9)


def test_etiket_elle():
    """Tek option, haftalık talep elle: geliş h+L=4, IP 100, Q = 300."""
    opt = pd.DataFrame({"option_id": ["A"], "liste_fiyati": [100.0], "alis_fiyati": [40.0]})

    class W:
        optionlar = opt

    haftalik = pd.DataFrame({"option_id": "A", "h": range(8), "tf": [50] * 6 + [0, 0],
                             "tum": [50] * 6 + [80, 80]})
    ozl = pd.DataFrame({"option": [0], "h": [2.0], "L": [2], "ip": [100.0], "q_etiket": [300], "moq": [300]})
    r = aday.etiketle(ozl, W, haftalik, np.array([60.0]), "x").iloc[0]
    # Geliş öncesi 2 hafta 100 talep ⇒ stok biter; gelişten sonra tam fiyat 2×50 = 100 < 150
    assert r["tf_x"] == 100 and not r["etiket_x"]
    # indirim dönemi 160 talep, RPT'den kalan 200 ⇒ 160 indirimli
    assert r["kar_x"] == pytest.approx(100 * 100 + 60 * 160 - 40 * 300)


@pytest.mark.veri
def test_modeller_banu_kuralindan_isabetli(yol0):
    t = yol0["aday"]["SS25"]["sinama"]
    m = yol0["baglam"].modeller["SS25"]
    banu = aday.degerlendir(aday.banu_kurali(t, yol0["baglam"].dunya), t)
    lgbm = aday.degerlendir(m.olasilik(t, "lgbm") >= 0.5, t)
    assert lgbm["isabet"] > banu["isabet"]
