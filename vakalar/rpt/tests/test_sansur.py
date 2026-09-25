import numpy as np
import pandas as pd
import pytest

from rpt import egri, kaynak, sansur


def _duz_egri(pay=(0.25, 0.25, 0.25, 0.25)):
    return egri.Egri(paylar={(1,): np.array(pay)}, grup=("dalga",), yontem="duzeltilmis",
                     hedef="indirim", sezonlar=("SS24",))


def test_oyuncak_stoklu_gun_duzeltmesi(oyuncak):
    t, opt = oyuncak
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    d = sansur.duzeltilmis_talep(hh, 2).iloc[0]
    # M1-S 28 (her gün stoklu), M1-M 14, M2-S 3 satış / 3 stoklu gün × 14 açık
    # gün = 14, M2-M 0: çıplak 45, düzeltilmiş 56 = ilk iki haftanın gerçek talebi
    assert d["x"] == 45
    assert d["D"] == pytest.approx(56.0)
    gercek = hh[hh["h"] < 2]
    assert (gercek["satis"] + gercek["kayip"]).sum() == 56


def test_stoksuz_hucreye_atama(oyuncak):
    t, opt = oyuncak
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    m = (hh["magaza_id"] == "M2") & (hh["urun_id"] == "A-S")
    hh.loc[m, ["satis", "stoklu_gun"]] = 0
    d = sansur.duzeltilmis_talep(hh, 2).iloc[0]
    # M2-S'nin hızı: A-S'nin stoklu hücresinin (M1) hızı 2/gün × ilk dağıtım
    # ağırlığı (3+1) / (60+1) × 14 açık gün
    beklenen = 28 + 14 + 0 + 2.0 * 4 / 61 * 14
    assert d["D"] == pytest.approx(beklenen)


def test_kestirim_katmanlari(oyuncak):
    t, opt = oyuncak
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    ham = _duz_egri((0.4, 0.3, 0.2, 0.1))
    duz = _duz_egri()
    k = sansur.kestir(hh, opt, 2, ham, duz).iloc[0]
    W = 17 / 7
    assert k["a"] == 45
    assert k["b"] == pytest.approx(56 / 2 * W)
    assert k["c"] == pytest.approx(45 / 0.7)
    assert k["d"] == pytest.approx(56 / 0.5)
    assert k["a_hiz"] == pytest.approx(45 / 2 * W)
    assert k["c_duz_egri"] == pytest.approx(45 / 0.5)
    assert k["plan"] == 50.0


def test_kestirim_kayip_satisi_okumaz(oyuncak):
    t, opt = oyuncak
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    a = sansur.kestir(hh, opt, 2, _duz_egri(), _duz_egri())
    hh2 = hh.assign(kayip=hh["kayip"] * 100 + 7, kayip_io=999)
    b = sansur.kestir(hh2, opt, 2, _duz_egri(), _duz_egri())
    pd.testing.assert_frame_equal(a, b)


def test_hata_olcutleri_elle():
    tahmin = pd.Series([110.0, 50.0])
    gercek = pd.Series([100.0, 100.0])
    m = sansur.hata_olcutleri(tahmin, gercek)
    assert m["mape"] == pytest.approx((0.10 + 0.50) / 2)
    assert m["wape"] == pytest.approx(60 / 200)
    assert m["yanlilik"] == pytest.approx(-40 / 200)
    assert m["n"] == 2


def test_gercek_talep(oyuncak):
    t, opt = oyuncak
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    g = sansur.gercek_talep(hh).iloc[0]
    # indirim 17. gün: M1 17×3 + M2 3 satış + 14 kayıp
    assert g["gercek_io"] == 17 * 3 + 3 + 14
    assert g["gercek_cikis"] == 28 * 3 + 3 + 25


@pytest.mark.veri
def test_kestirim_kirpilmis_veriyle_ayni(veri):
    """h. pazartesi sabahına kırpılmış tablolardan kurulan panelle aynı sonuç."""
    t, opt, hh = veri["t"], veri["opt"], veri["hh"]
    o = opt[(opt["sezon_kodu"] == "SS25") & (opt["line"] == "Collection") & (opt["dalga"] == 1)]
    e = _duz_egri(np.full(20, 0.05))
    h = 3
    sabah = o["lansman_tarihi"].iloc[0] + pd.Timedelta(days=7 * h)
    tam = sansur.kestir(hh[hh["option_id"].isin(o["option_id"])], o, h, e, e)
    kirpik_hh = kaynak.hucre_hafta(kaynak.tarihten_once(t, sabah), o, ("SS25",))
    kirpik = sansur.kestir(kirpik_hh, o, h, e, e)
    pd.testing.assert_frame_equal(tam.sort_values("option_id").reset_index(drop=True),
                                  kirpik.sort_values("option_id").reset_index(drop=True))
