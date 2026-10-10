import numpy as np
import pandas as pd
import pytest
from conftest import oyuncak_tablolar, sentetik_gunluk
from perakende_analitik.carpanlar import Carpanlar

from rpt import aday, egri, kaynak, miktar

NOTR = Carpanlar()
LANSMAN = pd.Timestamp("2025-02-10")      # oyuncak tabloların lansmanı


def _duz(n=10, hedef="indirim"):
    return egri.Egri(paylar={(1,): np.full(n, 1.0 / n)}, grup=("dalga",), yontem="x", hedef=hedef,
                     sezonlar=())


# ------------------------------------------------------------ karar sabahı durumu


def _rptli_tablolar():
    t = oyuncak_tablolar()
    gun = lambda n: LANSMAN + pd.Timedelta(days=n)  # noqa: E731
    rpt = pd.DataFrame({"siparis_id": ["SP2", "SP2"], "tip": "rpt", "option_id": "OPT-A",
                        "urun_id": ["A-S", "A-M"], "tedarikci_id": "T01", "siparis_tarihi": gun(3),
                        "planlanan_teslim": gun(30), "gerceklesen_teslim": gun(31), "adet": [200, 100]})
    t["siparis"] = pd.concat([t["siparis"], rpt], ignore_index=True)
    return t


def test_durum_tablodan_elle():
    """Oyuncak tablolar, karar sabahı = 2. pazartesi (lansman + 7)."""
    t = _rptli_tablolar()
    d = aday.durum_tablodan(t, LANSMAN + pd.Timedelta(days=7), ["OPT-A", "YOK"]).set_index("option_id")
    a = d.loc["OPT-A"]
    # satış (mağaza + online, ilk 7 gün): M1 14 + 7, ONL 7 + 2, M2 3
    assert a["satilan"] == 33
    # depodan mağazalara (7. günden önce çıkan): ilk dağıtım 103 + replenishment 12
    assert a["gonderilen"] == 115 and a["str"] == pytest.approx(33 / 115)
    assert a["depo"] == 93 + 50                      # o sabahın depo fotoğrafı
    assert a["magaza"] == 5 + 5 + 0 + 5              # o sabahın mağaza fotoğrafı
    assert a["yolda"] == 12                          # 6. gün çıkan, 8. gün varan
    assert a["acik"] == 300 and a["rpt_sayisi"] == 1  # 3. gün verilen, henüz gelmemiş RPT
    assert a["stoklu_magaza_payi"] == 1.0            # M1 ve M2 (M bedeni) stoklu
    assert a["kirik_magaza_payi"] == 0.5             # M2'nin S bedeni boş
    assert (d.loc["YOK", list(aday.DURUM_KOLONLARI)] == 0).all()


def test_durum_tablodan_gelecegi_gormez():
    t = _rptli_tablolar()
    k = LANSMAN + pd.Timedelta(days=7)
    a = aday.durum_tablodan(t, k, ["OPT-A"])
    b = dict(t)
    b["satis"] = t["satis"].assign(adet=np.where(t["satis"]["tarih"] >= k, 99, t["satis"]["adet"]))
    b["stok"] = t["stok"].assign(adet=np.where(t["stok"]["tarih"] > k, 99, t["stok"]["adet"]))
    b["depo_stok"] = t["depo_stok"].assign(adet=np.where(t["depo_stok"]["tarih"] > k, 0,
                                                         t["depo_stok"]["adet"]))
    sv = t["sevkiyat"].copy()
    sv.loc[sv["tarih"] >= k, "adet"] = 999
    yolda = (sv["tarih"] < k) & (sv["varis_tarihi"] >= k)
    assert yolda.any()
    sv.loc[yolda, "varis_tarihi"] = k + pd.Timedelta(days=20)      # gelecekteki varış günü bilinmez
    b["sevkiyat"] = sv
    sp = t["siparis"].copy()
    sp.loc[sp["tip"] == "rpt", "gerceklesen_teslim"] = k + pd.Timedelta(days=1)  # gelecek teslim
    b["siparis"] = pd.concat([sp, sp.assign(siparis_id="SP9", siparis_tarihi=k)], ignore_index=True)
    b["magaza"] = t["magaza"].assign(kapanis_tarihi=k + pd.Timedelta(days=3))     # gelecek kapanış
    pd.testing.assert_frame_equal(a, aday.durum_tablodan(b, k, ["OPT-A"]))
    # test boş geçmiyor: dünkü satış değişince STR değişir
    c = dict(t)
    c["satis"] = t["satis"].assign(adet=np.where(t["satis"]["tarih"] == k - pd.Timedelta(days=1), 9,
                                                 t["satis"]["adet"]))
    assert aday.durum_tablodan(c, k, ["OPT-A"])["str"].iloc[0] > a["str"].iloc[0]


# ------------------------------------------------------------ karar kaydı


@pytest.fixture(scope="module")
def sentetik():
    g, opt, _ = sentetik_gunluk([("O1", "SS25", LANSMAN, 12, 1), ("O2", "SS25", LANSMAN, 12, 1)],
                                magaza_sayisi=24)
    return g, opt


def _sifir_durum(t, ids):
    return pd.DataFrame({"option_id": list(ids), **{k: 0.0 for k in aday.DURUM_KOLONLARI}})


def test_karar_kaydi_gelecegi_gormez(sentetik):
    g, opt = sentetik
    a = aday.karar_kaydi(g, opt, ["SS25"], lambda t: NOTR, _sifir_durum, haftalar=(3, 5))
    assert list(a["h"]) == [3, 3, 5, 5] and set(a["option_id"]) == {"O1", "O2"}
    assert (a["karar_ani"] == LANSMAN + pd.to_timedelta(7 * a["h"], unit="D")).all()
    b5 = a[a["h"] == 5]
    assert (b5["D"] > b5["x"]).all()                    # sansür 3. haftada başlar
    t5 = LANSMAN + pd.Timedelta(days=35)
    bozuk = g.copy()
    sonra = bozuk["tarih"] >= t5
    bozuk.loc[sonra, "brut_satis"] = bozuk.loc[sonra, "brut_satis"] * 4 + 1
    bozuk.loc[sonra, "durum"] = "bos"
    pd.testing.assert_frame_equal(a, aday.karar_kaydi(bozuk, opt, ["SS25"], lambda t: NOTR, _sifir_durum,
                                                      haftalar=(3, 5)))
    # [t3, t5) arası değişiklik yalnız h = 5'i etkiler
    ara = g.copy()
    sec = (ara["tarih"] >= LANSMAN + pd.Timedelta(days=21)) & (ara["tarih"] < t5)
    ara.loc[sec, "brut_satis"] += 1
    c = aday.karar_kaydi(ara, opt, ["SS25"], lambda t: NOTR, _sifir_durum, haftalar=(3, 5))
    pd.testing.assert_frame_equal(a[a["h"] == 3], c[c["h"] == 3])
    assert (c.loc[c["h"] == 5, "x"].to_numpy() > a.loc[a["h"] == 5, "x"].to_numpy()).all()


def test_egitim_yalniz_gecmis_sezonlardan():
    kayit = pd.DataFrame({"option_id": list("ABCDE"), "sezon_kodu": ["SS24", "AW24", "SS25", "AW24", "SS23"],
                          "rpt_sayisi": [0, 0, 0, 1, 0], "h": 3})
    e = aday.egitim_satirlari(kayit, "SS25")
    assert list(e["option_id"]) == ["A", "B", "E"]
    assert list(aday.egitim_satirlari(kayit, "AW24")["option_id"]) == ["A", "E"]
    X = pd.DataFrame(np.random.default_rng(0).normal(size=(40, len(aday.OZELLIKLER))), columns=aday.OZELLIKLER)
    X["etiket_duz"] = X["str"] > 0
    with pytest.raises(ValueError, match="SS25"):
        aday.Modeller(X.assign(sezon_kodu=["SS24"] * 39 + ["SS25"]), "SS25")
    m = aday.Modeller(X.assign(sezon_kodu="AW24"), "SS25")
    assert m.n == 40 and m.sezonlar == ("AW24",)


# ------------------------------------------------------------ özellikler


def _opt_bir(mense="Uzak Doğu"):
    return pd.DataFrame({"option_id": ["A"], "sezon_kodu": ["SS25"], "dalga": [1], "rpt_hafta": [2],
                         "ilk_alim": [1000], "moq_option": [300], "satis_hafta": [10.0],
                         "liste_fiyati": [100.0], "alis_fiyati": [40.0], "mense": [mense],
                         "lansman_tarihi": [LANSMAN], "indirim_baslangic": [LANSMAN + pd.Timedelta(days=70)]})


def _kayit_bir():
    return pd.DataFrame({"option_id": ["A"], "sezon_kodu": ["SS25"], "h": [2], "x": [150.0], "D": [200.0],
                         "satilan": [600.0], "gonderilen": [1000.0], "str": [0.6], "depo": [50.0],
                         "magaza": [30.0], "yolda": [10.0], "acik": [10.0], "stoklu_magaza_payi": [0.9],
                         "kirik_magaza_payi": [0.3], "rpt_sayisi": [0]})


def test_ozellikler_elle():
    """Düz eğri (k_h = h/10), h = 2, D = 200 ⇒ sezon 1.000; L = 2 ⇒ geliş 4. hafta."""
    e = _duz()
    eg = {("duzeltilmis", "indirim"): e, ("duzeltilmis", "cikis"): e, ("ham", "indirim"): e}
    bel = miktar.Belirsizlik(mu={2: 0.0}, sigma={2: 1e-6}, n={2: 9}, sezonlar=("AW24",))
    r = aday.ozellikler(_kayit_bir(), _opt_bir(), eg, bel, {"A": 30.0}).iloc[0]
    assert r["hiz_q1"] == pytest.approx(0.1)          # 200 / 2 / 1.000
    assert r["d_q1"] == pytest.approx(1.0)            # 200 / 0,2 / 1.000
    assert r["frr_q1"] == pytest.approx(0.75)         # 150 / 0,2 / 1.000
    assert r["ip"] == 100 and r["kapsama"] == pytest.approx(1.0)
    assert r["hafta_indirime"] == 8 and r["L"] == 2 and r["uzak"] == 1.0
    assert r["kalan_tf"] == pytest.approx(0.6)
    # geliş öncesi talep 200 ⇒ gelişte 0 stok; gelişten sonra 600
    assert r["ekstra_q1"] == pytest.approx(0.6) and r["moq_oran"] == pytest.approx(0.5)
    assert r["q_nv"] == 600 and r["q_etiket"] == 600 and r["p_ind"] == 30.0
    assert set(aday.OZELLIKLER) <= set(r.index)
    assert aday.ozellikler(_kayit_bir(), _opt_bir("Yakın"), eg, bel, {"A": 30.0})["uzak"].iloc[0] == 0.0


def test_banu_kurali_elle():
    k = pd.concat([_kayit_bir()] * 5, ignore_index=True)
    k["h"] = [2, 3, 3, 3, 7]
    k["str"] = [0.9, 0.55, 0.54, 0.9, 0.9]
    o = _opt_bir().assign(rpt_hafta=2)
    ozl = aday.ozellikler(k, o, {key: _duz() for key in (("duzeltilmis", "indirim"), ("duzeltilmis", "cikis"),
                                                         ("ham", "indirim"))},
                          miktar.Belirsizlik({2: 0.0}, {2: 0.1}, {2: 9}, ()), {"A": 30.0})
    ozl.loc[3, "rpt_sayisi"] = 1
    # h = 2 erken, 3 tetik, %54 eşik altı, RPT'si var, h = 7 geç
    assert aday.banu_kurali(ozl).tolist() == [False, True, False, False, False]
    # yetişme: lansman + 3 hafta + L ≥ indirim ⇒ yok (70 gün; L = 7 ⇒ 21 + 49 = 70)
    assert not aday.banu_kurali(ozl.assign(L=7)).any()


# ------------------------------------------------------------ etiket


def test_haftalik_elle():
    opt = pd.DataFrame({"option_id": ["A"], "lansman_tarihi": [LANSMAN],
                        "indirim_baslangic": [LANSMAN + pd.Timedelta(days=17)],
                        "cikis_tarihi": [LANSMAN + pd.Timedelta(days=28)]})
    gun = [0, 8, 16, 17, 27, 28, -1]
    talep = pd.DataFrame({"tarih": [LANSMAN + pd.Timedelta(days=d) for d in gun], "option_id": "A",
                          "magaza_id": "M1", "talep": [5, 3, 2, 4, 1, 9, 7]})
    w = aday.haftalik(talep, opt).set_index("h")
    assert w["tf"].tolist() == [5, 3, 2, 0] and w["tum"].tolist() == [5, 3, 6, 1]


def test_etiket_elle():
    """Tek option, haftalık talep elle: geliş h+L=4, IP 100, Q = 300."""
    haftalik = pd.DataFrame({"option_id": "A", "h": range(8), "tf": [50] * 6 + [0, 0],
                             "tum": [50] * 6 + [80, 80]})
    ozl = pd.DataFrame({"option_id": ["A"], "h": [2], "L": [2], "ip": [100.0], "q_etiket": [300],
                        "moq": [300], "p": [100.0], "c": [40.0], "p_ind": [60.0]})
    r = aday.etiketle(ozl, haftalik, "x").iloc[0]
    # Geliş öncesi 2 hafta 100 talep ⇒ stok biter; gelişten sonra tam fiyat 2×50 = 100 < 150
    assert r["tf_x"] == 100 and not r["etiket_x"]
    # indirim dönemi 160 talep, RPT'den kalan 200 ⇒ 160 indirimli
    assert r["kar_x"] == pytest.approx(100 * 100 + 60 * 160 - 40 * 300)
    # haftalığı olmayan option: negatif, kâr −c·Q değil 0 (sipariş tablosunda yok)
    yok = aday.etiketle(ozl.assign(option_id="B"), haftalik, "x").iloc[0]
    assert not yok["etiket_x"] and yok["kar_x"] == 0.0


def test_etiket_duz_r4_ile():
    """Etiket (ii): Basit, karar anı = oyunun ilk lansman sabahı (R4); oyun başladıktan
    sonraki satırlar etiketi değiştirmez; oyun sezonu satırı reddedilir."""
    gecmis_lan, oyun_lan = pd.Timestamp("2024-02-12"), pd.Timestamp("2024-08-19")
    g, opt, _ = sentetik_gunluk([("P1", "SS24", gecmis_lan, 14, 1), ("P2", "SS24", gecmis_lan, 14, 1),
                                 ("G1", "AW24", oyun_lan, 8, 1)], magaza_sayisi=20)
    ozl = pd.DataFrame({"option_id": ["P1", "P2"], "sezon_kodu": "SS24", "h": [3, 4], "L": [2, 3],
                        "ip": [50.0, 80.0], "q_etiket": [60, 60], "moq": [60, 60], "p": 100.0,
                        "c": 40.0, "p_ind": 60.0})
    a = aday.etiket_duz(ozl, g, opt, "AW24", lambda t: NOTR)
    elle = aday.etiket(ozl, egri.gecmis_talep(g, opt, "AW24", NOTR), opt, "duz")
    pd.testing.assert_frame_equal(a, elle)
    assert a["etiket_duz"].any()
    bozuk = g.copy()
    sonra = bozuk["tarih"] >= oyun_lan
    bozuk.loc[sonra, "brut_satis"] = bozuk.loc[sonra, "brut_satis"] * 9 + 4
    bozuk.loc[sonra, "durum"] = "bos"
    pd.testing.assert_frame_equal(a, aday.etiket_duz(ozl, bozuk.drop(columns="gercek_talep"), opt, "AW24",
                                                     lambda t: NOTR))
    with pytest.raises(ValueError, match="AW24"):
        aday.etiket_duz(ozl.assign(sezon_kodu=["SS24", "AW24"]), g, opt, "AW24", lambda t: NOTR)


def test_uyum_ve_degerlendir_elle():
    ozl = pd.DataFrame({"option_id": ["A", "A", "B", "C"], "h": [2, 3, 2, 2],
                        "etiket_gercek": [True, True, False, False], "etiket_duz": [True, False, False, True],
                        "kar_gercek": [100.0, 50.0, -30.0, -10.0]})
    u = aday.uyum(ozl)
    assert (u["ikisi"], u["yalniz_gercek"], u["yalniz_duz"], u["hicbiri"]) == (1, 1, 1, 1)
    assert u["uyum"] == 0.5
    d = aday.degerlendir(np.array([True, False, True, False]), ozl, "gercek")
    assert (d["tp"], d["fp"], d["fn"], d["tn"]) == (1, 1, 1, 1)
    assert d["yanlis_alarm_tl"] == 30.0 and d["kacirma_tl"] == 50.0
    assert d["ilk_alarm_option"] == 2 and d["ilk_alarm_kar_tl"] == 100.0 - 30.0


def test_modeller_ayrilabilir_veriyi_ogrenir():
    rng = np.random.default_rng(1)
    X = pd.DataFrame(rng.normal(size=(300, len(aday.OZELLIKLER))), columns=aday.OZELLIKLER)
    X["etiket_duz"] = X["d_q1"] + 0.2 * rng.normal(size=300) > 0.3
    m = aday.Modeller(X.assign(sezon_kodu="SS24"), "AW24")
    for model in ("lojistik", "lgbm"):
        dogru = (m.olasilik(X, model) >= 0.5) == X["etiket_duz"]
        assert dogru.mean() > 0.85
    assert m.katsayilar().index[0] == "d_q1"


# ------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_banu_kurali_yayimlanan_rptleri_uretir(veri):
    """Karar sabahı durumu yayımlanan tablolardan: Banu'nun kuralı (STR ≥ %55, h 3–6,
    yetişme, RPT'siz) v4'ün yayımladığı RPT siparişlerini birebir üretir."""
    t, opt = veri["t"], veri["opt"]
    col = opt[(opt["line"] == "Collection") & opt["sezon_kodu"].isin(kaynak.TAM_SEZONLAR)]
    parca = []
    for lansman, o in col.groupby("lansman_tarihi"):
        for h in range(2, 8):
            k = pd.Timestamp(lansman) + pd.Timedelta(days=7 * h)
            d = aday.durum_tablodan(t, k, o["option_id"])
            parca.append(d.assign(h=h, karar_ani=k, x=0.0, D=0.0))
    kayit = pd.concat(parca, ignore_index=True)
    uc = egri.Egri(paylar={(d,): np.full(30, 1 / 30) for d in (1, 2, 3)}, grup=("dalga",), yontem="x",
                   hedef="x", sezonlar=())
    e = {key: uc for key in (("duzeltilmis", "indirim"), ("duzeltilmis", "cikis"), ("ham", "indirim"))}
    ozl = aday.ozellikler(kayit.merge(col[["option_id", "sezon_kodu"]], on="option_id"), opt, e,
                          miktar.Belirsizlik({2: 0.0}, {2: 0.1}, {2: 1}, ()),
                          dict.fromkeys(col["option_id"], 0.0))
    tahmin = ozl.loc[aday.banu_kurali(ozl), ["option_id", "karar_ani"]]
    sp = t["siparis"]
    rpt = sp[(sp["tip"] == "rpt") & sp["option_id"].isin(col["option_id"])]
    gercek = rpt[["option_id", "siparis_tarihi"]].drop_duplicates()
    assert len(gercek) > 400
    a = set(map(tuple, tahmin.astype({"karar_ani": "datetime64[ns]"}).to_numpy().tolist()))
    b = set(map(tuple, gercek.astype({"siparis_tarihi": "datetime64[ns]"}).to_numpy().tolist()))
    assert a == b


@pytest.mark.veri
def test_modeller_banu_kuralindan_isabetli():
    """SS25 sınama satırlarında (rpt_yok kolunun dünyası, kolun karar anında
    gördüğüyle; `oyun.sinama`) LightGBM'in isabeti Banu'nun kuralından yüksek,
    gerçek (i) etiketle (Görev 6 ön koşusu, yayımlanan dünyada: 0,741 / 0,680).
    Yol 0'ın hazırlığı ve rpt_yok koşusu önbellekten (yoksa ~35 dk)."""
    from rpt import motor, oyun

    if not motor.VERI_YOLU.exists():
        pytest.skip("v4 verisi yok")
    H = oyun.hazirlik(0)
    s = oyun.sinama(H, oyun.kos(H, "rpt_yok", "a"))
    s = s[s["sezon_kodu"] == "SS25"]
    assert len(s) > 500 and (s["rpt_sayisi"] == 0).all()
    lgbm = aday.degerlendir(s["p_lgbm"].to_numpy() >= aday.ESIK, s, "gercek")
    banu = aday.degerlendir(s["banu"].to_numpy(bool), s, "gercek")
    assert lgbm["isabet"] > banu["isabet"]
    assert lgbm["duyarlilik"] > banu["duyarlilik"]
