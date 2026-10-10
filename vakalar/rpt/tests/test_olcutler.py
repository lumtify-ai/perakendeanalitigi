import numpy as np
import pandas as pd
import pytest

from rpt import motor, olcutler


def test_gercek_gunluk_elle():
    d = pd.Timestamp("2025-02-10")
    satis = pd.DataFrame({"tarih": [d, d, d], "magaza_id": ["M1", "M1", "M2"],
                          "urun_id": ["A-S", "A-S", "B-S"], "adet": [3, -1, 2]})
    ikame = pd.DataFrame({"tarih": [d], "magaza_id": ["M1"], "urun_id": ["A-S"], "adet": [1]})
    kars = pd.DataFrame({"tarih": [d, d], "magaza_id": ["M1", "M3"], "urun_id": ["A-S", "A-S"],
                         "talep": [6, 4], "kendi_satis": [2, 0], "karsilanmayan": [4, 4]})
    urun = pd.DataFrame({"urun_id": ["A-S", "B-S"], "option_id": ["A", "B"]})
    g = olcutler.gercek_gunluk(satis, kars, ikame, urun).set_index(["magaza_id", "urun_id"])
    assert g.loc[("M1", "A-S"), "talep"] == 3 - 1 + 4      # = hakemin talebi (6)
    assert g.loc[("M3", "A-S"), "talep"] == 4
    assert g.loc[("M2", "B-S"), "talep"] == 2
    assert len(olcutler.gercek_gunluk(satis, kars, ikame, urun, opsiyonlar=["B"])) == 1


# ---------------------------------------------------------------------------
# Elle kurulmuş küçük koşu
# ---------------------------------------------------------------------------

LAN = pd.Timestamp("2025-02-10")        # pazartesi
IND = pd.Timestamp("2025-03-10")        # indirim başı (4 hafta)
CIK = pd.Timestamp("2025-04-07")        # çıkış
SON = pd.Timestamp("2025-04-30")        # pencerenin son günü (takvim)


def _g(n):
    return LAN + pd.Timedelta(days=n)


def _kosu(rpt: bool) -> motor.Kosu:
    """İki SS25 Collection option'ı (A: tek SKU A-S; B: B-S, B-M), bir AW24 ve bir
    SS25 Outlet option'ı (ölçülmez). `rpt` ise A'ya 100'lük RPT (8 hatalı), A'nın
    satışı ve gerçeği ona göre."""
    urun = pd.DataFrame({
        "urun_id": ["A-S", "B-S", "B-M", "C-S", "D-S"],
        "option_id": ["A", "B", "B", "C", "D"],
        "sezon_kodu": ["SS25", "SS25", "SS25", "AW24", "SS25"],
        "line": ["Collection", "Collection", "Collection", "Collection", "Outlet"],
        "dalga": [1, 1, 1, 1, 1], "alis_fiyati": [40.0, 10.0, 10.0, 5.0, 5.0],
        "liste_fiyati": [100.0, 30.0, 30.0, 10.0, 10.0], "tedarikci_id": ["T1", "T2", "T2", "T1", "T1"],
        "lansman_tarihi": LAN, "cikis_tarihi": CIK,
    })
    sezon = pd.DataFrame({"sezon_kodu": ["SS25", "AW24"], "dalga": [1, 1], "lansman_tarihi": [LAN, LAN],
                          "indirim_baslangic": [IND, IND], "cikis_tarihi": [CIK, CIK]})
    ted = pd.DataFrame({"tedarikci_id": ["T1", "T2"], "mense": ["Yerli", "Uzak Doğu"], "moq_option": [100, 300]})
    sp = [("SP1", "ilk", "A", "A-S", _g(-30), _g(-7), 200),
          ("SP2", "ilk", "B", "B-S", _g(-30), _g(-7), 50), ("SP2", "ilk", "B", "B-M", _g(-30), _g(-7), 30),
          ("SP3", "ilk", "C", "C-S", _g(-30), _g(-7), 999)]
    kal = [("SP1", _g(-7), 32, 10), ("SP2", _g(-7), 32, 0), ("SP3", _g(-7), 32, 0)]
    if rpt:
        sp.append(("SP4", "rpt", "A", "A-S", _g(14), _g(35), 100))
        kal.append(("SP4", _g(35), 32, 8))
    siparis = pd.DataFrame(sp, columns=["siparis_id", "tip", "option_id", "urun_id", "siparis_tarihi",
                                        "gerceklesen_teslim", "adet"])
    kalite = pd.DataFrame(kal, columns=["siparis_id", "teslim_tarihi", "numune", "hatali"])
    # A: tam fiyat 150 (+60 RPT'yle), indirimde 20 (+10), bir iade; B: 40 + 5
    a_tf, a_ind = (210, 30) if rpt else (150, 20)
    satis = pd.DataFrame([
        (_g(3), "M1", "A-S", a_tf, a_tf * 100.0), (_g(40), "M1", "A-S", a_ind, a_ind * 70.0),
        (_g(41), "M1", "A-S", -1, -70.0),
        (_g(5), "M1", "B-S", 40, 1200.0), (_g(50), "ONL", "B-M", 5, 105.0),
        (_g(5), "M1", "C-S", 7, 70.0), (_g(5), "M1", "D-S", 3, 30.0),
    ], columns=["tarih", "magaza_id", "urun_id", "adet", "tutar"])
    # Gerçek: A'nın tam fiyat talebi 260; RPT'siz 110 karşılanmaz (70 kalıcı, 40 ikame),
    # RPT'li 50 (30 kalıcı, 20 ikame); indirimde A 5 karşılanmaz (iki kolda); B 3 kalıcı
    a_k_tf, a_kal_tf = (50, 30) if rpt else (110, 70)
    gercek = pd.DataFrame([
        (_g(10), "M1", "A-S", 260, 260 - a_k_tf, a_k_tf, a_k_tf - a_kal_tf, a_kal_tf),
        (_g(45), "M1", "A-S", a_ind + 5, a_ind, 5, 0, 5),
        (_g(10), "M1", "B-S", 43, 40, 3, 0, 3),
        (_g(10), "M1", "C-S", 50, 7, 43, 0, 43),
    ], columns=["tarih", "magaza_id", "urun_id", "talep", "kendi_satis", "karsilanmayan",
                "ikameye_giden", "kalici_kayip"])
    # Pencere sonu: A depoda 30 (RPT'siz 5), B depoda 10; son pazartesi mağazada A 2
    depo = pd.DataFrame([(SON, "A-S", 30 if rpt else 5), (SON, "B-S", 10), (SON - pd.Timedelta(days=1), "A-S", 99)],
                        columns=["tarih", "urun_id", "adet"])
    son_pzt = pd.Timestamp("2025-04-28")
    stok = pd.DataFrame([(son_pzt, "M1", "A-S", 2, 0), (_g(7), "M1", "A-S", 9, 7), (_g(14), "M1", "A-S", 0, 3),
                         (_g(7), "M1", "B-S", 5, 7), (_g(42), "M1", "A-S", 1, 7)],
                        columns=["tarih", "magaza_id", "urun_id", "adet", "stoklu_gun"])
    sevkiyat = pd.DataFrame([(_g(-1), "DEPO", "M1", "A-S", 120, "ilk_dagitim"),
                             (_g(36), "DEPO", "M1", "A-S", 50 if rpt else 0, "replenishment"),
                             (_g(60), "M1", "DEPO", "A-S", 4, "stok_devri"),
                             (_g(-1), "DEPO", "M1", "B-S", 40, "ilk_dagitim")],
                            columns=["tarih", "kaynak", "hedef", "urun_id", "adet", "tip"])
    takvim = pd.DataFrame({"tarih": pd.date_range("2025-01-01", SON)})
    t = {"urun": urun, "sezon": sezon, "tedarikci": ted, "siparis": siparis, "kalite_kontrol": kalite,
         "satis": satis, "depo_stok": depo, "stok": stok, "sevkiyat": sevkiyat, "takvim": takvim}
    return motor.Kosu(tablolar=t, gercek=gercek, meta={})


def test_ozet_elle():
    o = olcutler.ozet(_kosu(rpt=True), "SS25").set_index("option_id")
    assert list(o.index) == ["A", "B"]                         # yalnız SS25 Collection
    a, b = o.loc["A"], o.loc["B"]
    assert (a["ilk_alim"], a["ilk_giren"], a["rpt"], a["rpt_giren"]) == (200, 190, 100, 92)
    assert a["rpt_siparis_tarihi"] == _g(14) and a["mense"] == "Yerli" and a["moq"] == 100
    assert (a["satis_tf"], a["satis_ind"], a["iade"]) == (210, 30, 1)
    assert a["gelir"] == pytest.approx(210 * 100 + 30 * 70 - 70)
    assert a["maliyet"] == pytest.approx(40 * (190 + 92))
    assert a["kar"] == pytest.approx(a["gelir"] - a["maliyet"])
    assert (a["talep"], a["karsilanmayan"], a["karsilanmayan_tf"]) == (295, 55, 50)
    assert (a["kalici_kayip"], a["ikameye_giden"]) == (35, 20)
    assert a["kalan_son"] == 30 + 2                            # depo son gün + son pazartesi raf
    assert a["rpt_bosa"] == 32                                 # min(rpt_giren 92, kalan 32)
    assert a["magazaya"] == 170
    assert a["stoklu_pay_tf"] == pytest.approx((7 + 3) / 14)   # (lansman, indirim] fotoğrafları
    assert (b["ilk_alim"], b["rpt"], b["rpt_bosa"], b["satis_tf"], b["satis_ind"]) == (80, 0, 0, 40, 5)
    assert b["mense"] == "Uzak Doğu" and b["kalan_son"] == 10
    assert pd.isna(b["rpt_siparis_tarihi"])


def test_ozet_tabana_gore():
    taban = olcutler.ozet(_kosu(rpt=False), "SS25")
    o = olcutler.ozet(_kosu(rpt=True), "SS25", taban=taban).set_index("option_id")
    a, b = o.loc["A"], o.loc["B"]
    assert a["kurtarilan"] == (110 + 5) - (50 + 5)
    assert (a["kurtarilan_kalici"], a["kurtarilan_ikame"], a["kurtarilan_tf"]) == (40, 20, 60)
    assert a["d_satis_tf"] == 60 and a["d_satis_ind"] == 10
    assert a["d_kar"] == pytest.approx((60 * 100 + 10 * 70) - 40 * 92)
    assert not a["yanlis_alarm"]                               # 60 ≥ MOQ/2 = 50
    assert b["kurtarilan"] == 0 and b["d_kar"] == 0 and not b["yanlis_alarm"]

    oz = olcutler.sezon_ozeti(o.reset_index())
    assert oz["option"] == 2 and oz["rpt_option"] == 1 and oz["rpt"] == 100
    assert oz["kurtarilan"] == 60 and oz["kurtarilan_kalici"] == 40 and oz["kurtarilan_ikame"] == 20
    assert oz["yanlis_alarm"] == 0 and oz["rpt_bosa"] == 32
    assert oz["d_kar"] == pytest.approx(a["d_kar"])
    assert oz["kar"] == pytest.approx(o["kar"].sum())
    assert oz["rpt_ek_tf"] == 60 and oz["rpt_str"] == pytest.approx(70 / 92)


def test_yanlis_alarm_ve_kacirilan():
    """RPT'nin tam fiyat ek satışı MOQ/2'nin altındaysa yanlış alarm; kâhinin kâr
    artırdığı, kolun RPT vermediği option kaçırılan fırsattır."""
    taban = olcutler.ozet(_kosu(rpt=False), "SS25")
    kol = olcutler.ozet(_kosu(rpt=True), "SS25", taban=taban)
    kol2 = olcutler.ozet(_kosu(rpt=True), "SS25", taban=taban.assign(satis_tf=taban["satis_tf"] + 20))
    assert bool(kol2.set_index("option_id").loc["A", "yanlis_alarm"])  # ek 40 < MOQ/2 = 50
    assert olcutler.sezon_ozeti(kol2)["yanlis_alarm"] == 1
    rptsiz = olcutler.ozet(_kosu(rpt=False), "SS25", taban=taban)
    oz = olcutler.sezon_ozeti(rptsiz, kahin=kol)
    assert oz["kacirilan"] == 1 and oz["kacirilan_tl"] == pytest.approx(kol.set_index("option_id").loc["A", "d_kar"])


def test_tembel_ve_bellek_ayni(tmp_path):
    """`KosuKaydi` (diskten süzerek okur) ile bellekteki `Kosu` aynı özeti verir."""
    k = _kosu(rpt=True)
    d = tmp_path / "k"
    d.mkdir()
    for ad, df in k.tablolar.items():
        df.to_parquet(d / f"tablo_{ad}.parquet", index=False)
    k.gercek.to_parquet(d / "gercek.parquet", index=False)
    kk = motor.KosuKaydi(dizin=d, meta={"tablolar": sorted(k.tablolar), "kayitlar": []})
    pd.testing.assert_frame_equal(olcutler.ozet(kk, "SS25"), olcutler.ozet(k, "SS25"), check_dtype=False)
    assert np.isfinite(olcutler.ozet(kk, "SS25")["kar"]).all()
