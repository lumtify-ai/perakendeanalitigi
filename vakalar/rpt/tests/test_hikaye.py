import pandas as pd
import pytest
from conftest import oyuncak_tablolar

from rpt import hikaye, kaynak


def test_bitis_haftasi():
    panel = pd.DataFrame({
        "option_id": ["A"] * 5 + ["B"] * 5,
        "h": list(range(5)) * 2,
        "depo_stok": [400, 300, 100, 5, 0, 400, 300, 200, 100, 50],
        "magaza_stok": [0, 500, 300, 150, 100, 0, 500, 400, 300, 200],
    })
    opt = pd.DataFrame({"option_id": ["A", "B"], "ilk_alim": [1000, 1000]})
    b = hikaye.bitis_haftasi(panel, opt)
    # A: h=3'te depo 5 ≤ 20 ve 155 ≤ 200 → 3; B hiç bitmez
    assert b["A"] == 3
    assert "B" not in b.index


# ---------------------------------------------------------------------------
# Mağaza tablosu (oyuncak: elle izlenebilir)
# ---------------------------------------------------------------------------


def test_magaza_tablosu_oyuncak(oyuncak):
    t, opt = oyuncak
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    m = hikaye.magaza_tablosu(t, hh, "OPT-A", 2).set_index("magaza_id")
    assert set(m.index) == {"M1", "M2"}      # ONL fiziksel mağaza değil
    # M1 her gün stoklu: iki hafta, 14 gün; satış (2 + 1) × 14
    assert m.loc["M1", "satis"] == 42
    assert m.loc["M1", "stoklu_gun_ort"] == 14 and m.loc["M1", "stoksuz_gun_ort"] == 0
    assert m.loc["M1", "acik_gun"] == 14
    # M2: S bedeni ilk 3 gün stoklu, M bedeni 14 gün; beden ortalaması (3 + 14) / 2
    assert m.loc["M2", "satis"] == 3
    assert m.loc["M2", "stoklu_gun_ort"] == pytest.approx(8.5)
    assert m.loc["M2", "stoksuz_gun_ort"] == pytest.approx(5.5)
    # 2. pazartesi fotoğrafı: M2'nin S bedeni 0, M bedeni 5
    assert m.loc["M2", "stok"] == 5 and m.loc["M2", "stoklu_beden"] == 1 and m.loc["M2", "beden"] == 2
    assert m.loc["M1", "stoklu_beden"] == 2
    assert m.loc["M1", "ad"] == "Bir"
    # satışa göre sıralı
    assert list(hikaye.magaza_tablosu(t, hh, "OPT-A", 2)["magaza_id"]) == ["M1", "M2"]


def test_magaza_tablosu_gercek_talep_yok(oyuncak):
    """v4'te kayıp tablosu yok: gerçek talep sütunları magaza_tablosu'nda bulunmaz."""
    t, opt = oyuncak
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    m = hikaye.magaza_tablosu(t, hh, "OPT-A", 2)
    assert not {"kayip", "gercek_talep", "talep"} & set(m.columns)


# ---------------------------------------------------------------------------
# RPT siparişleri ve akıbeti: elle hesaplı küçük tablolar
# ---------------------------------------------------------------------------


def rpt_tablolari():
    """Oyuncağa iki RPT'li option: OPT-A (çıkış 2025-03-10) ve OPT-Q (aynı dönem).

    OPT-A: RPT 200 sipariş (S 120 + M 80), kalite reddi 10 → giren 190; 2025-02-24
    gelir. Gelişten çıkışa depodan mağazalara 70 çıkar. Çıkış sabahı depoda 150
    (S 120, M 30). Çıkış gününden sonra depodan outlet akışıyla 130 çıkar; 40 adet
    mağazalardan depoya döner (stok_devri); son pazartesi depo 60.
    FIFO: RPT çıkışta depoda 150 (= min(190, 150)), mağazaya 40 gitti; önceden duran
    mal yok (P = 0), outlet akışı 130 RPT'den alır → depoda 20 kalır.

    OPT-Q (sentetik ikinci option, tek SKU): RPT 100, çıkışta depo 300 → RPT'nin
    tamamı depoda; önceden duran 200; outlet akışı 250 → RPT'den yalnız 50 çıkar,
    depoda 50 kalır; mağazaya 0.
    """
    t = oyuncak_tablolar()
    gun = lambda n: pd.Timestamp("2025-02-10") + pd.Timedelta(days=n)  # noqa: E731
    cikis = gun(28)
    q = t["urun"].iloc[[0]].assign(urun_id="Q-S", option_id="OPT-Q", model_kodu="MDLQ")
    t["urun"] = pd.concat([t["urun"], q], ignore_index=True)
    sp = pd.DataFrame({
        "siparis_id": ["SP2", "SP2", "SP3"], "tip": "rpt", "option_id": ["OPT-A", "OPT-A", "OPT-Q"],
        "urun_id": ["A-S", "A-M", "Q-S"], "tedarikci_id": "T01",
        "siparis_tarihi": gun(-1), "planlanan_teslim": gun(14), "gerceklesen_teslim": gun(14),
        "adet": [120, 80, 100]})
    t["siparis"] = pd.concat([t["siparis"], sp], ignore_index=True)
    t["kalite_kontrol"] = pd.concat([t["kalite_kontrol"], pd.DataFrame({
        "siparis_id": ["SP2", "SP3"], "teslim_tarihi": [gun(14), gun(14)], "numune": [20, 20],
        "hatali": [10, 0]})], ignore_index=True)
    depo = t["depo_stok"]
    t["depo_stok"] = pd.concat([depo, pd.DataFrame([
        (cikis, "A-S", 120), (cikis, "A-M", 30), (cikis, "Q-S", 300),
        (gun(35), "A-S", 40), (gun(35), "A-M", 20), (gun(35), "Q-S", 350),
    ], columns=["tarih", "urun_id", "adet"])], ignore_index=True)
    ek = pd.DataFrame({
        "tarih": [gun(16), gun(16), cikis, cikis, cikis, cikis, cikis, cikis],
        "varis_tarihi": [gun(17), gun(17), gun(29), gun(29), gun(29), gun(29), gun(29), gun(29)],
        "kaynak": ["DEPO", "DEPO", "DEPO", "DEPO", "DEPO", "M1", "M2", "DEPO"],
        "hedef": ["M1", "M2", "M1", "M2", "M1", "DEPO", "DEPO", "M1"],
        "urun_id": ["A-S", "A-M", "A-S", "A-M", "Q-S", "A-S", "A-M", "Q-S"],
        "adet": [50, 20, 100, 30, 150, 25, 15, 100],
        "tip": ["replenishment", "replenishment", "outlet_akisi", "outlet_akisi", "outlet_akisi",
                "stok_devri", "stok_devri", "outlet_akisi"],
        "paket_id": None})
    t["sevkiyat"] = pd.concat([t["sevkiyat"], ek], ignore_index=True)
    opt = kaynak.optionlar(t)
    return t, opt


def test_rpt_siparisleri_oyuncak():
    t, opt = rpt_tablolari()
    r = hikaye.rpt_siparisleri(t, opt).set_index("option_id")
    assert r.loc["OPT-A", "adet"] == 200 and r.loc["OPT-A", "red"] == 10 and r.loc["OPT-A", "giren"] == 190
    assert r.loc["OPT-Q", "giren"] == 100
    # lansman 2025-02-10, sipariş 1 gün önce (−1/7 hafta), geliş 14. gün (2 hafta)
    assert r.loc["OPT-A", "gelis_h"] == pytest.approx(2.0)
    assert r.loc["OPT-A", "indirimden_sonra"] == False  # noqa: E712  (indirim 17. gün)
    assert r.loc["OPT-A", "indirime_kalan_gun"] == 3


def test_rpt_akibeti_oyuncak_fifo():
    t, opt = rpt_tablolari()
    ak = hikaye.rpt_akibeti(t, opt, "SS25").set_index("option_id")
    a = ak.loc["OPT-A"]
    assert a["rpt"] == 200 and a["rpt_giren"] == 190
    assert a["depo_cikista"] == 150 and a["rpt_depoda_cikista"] == 150
    assert a["rpt_cikisa_kadar"] == 40
    # geliş (14. gün) → çıkış (28. gün): mağazalara 70, online net 14 (her gün S'den 1)
    assert a["gelisten_cikisa_cikan"] == 70 and a["online_gelisten_cikisa"] == 14
    assert a["rpt_magazaya_alt"] == 26 and a["rpt_magazaya_ust"] == 40
    assert a["cikis_sonrasi_cikan"] == 130 and a["rpt_outlete"] == 130
    assert a["stok_devri"] == 40 and a["depo_son"] == 60
    assert a["rpt_depoda_kalan"] == 20
    q = ak.loc["OPT-Q"]
    assert q["rpt_giren"] == 100 and q["depo_cikista"] == 300 and q["rpt_depoda_cikista"] == 100
    assert q["rpt_cikisa_kadar"] == 0 and q["rpt_magazaya_alt"] == 0 and q["rpt_magazaya_ust"] == 0
    assert q["cikis_sonrasi_cikan"] == 250 and q["rpt_outlete"] == 50 and q["rpt_depoda_kalan"] == 50
    # kovalar giren adedi tam bölüşür; kalan, pencere sonu depo stoğunu aşamaz
    assert (ak["rpt_cikisa_kadar"] + ak["rpt_outlete"] + ak["rpt_depoda_kalan"] == ak["rpt_giren"]).all()
    assert (ak["rpt_depoda_kalan"] <= ak["depo_son"]).all()
    assert (ak["rpt_magazaya_alt"] <= ak["rpt_magazaya_ust"]).all()


def test_rpt_akibeti_v4_akislarina_duyarli():
    """Akıbet v4 akışlarından kurulur: çıkış sonrası outlet akışı ve çıkıştaki depo
    değişirse kovalar değişir (boş test olmasın)."""
    t, opt = rpt_tablolari()
    taban = hikaye.rpt_akibeti(t, opt, "SS25").set_index("option_id")
    # outlet akışı olmasaydı: RPT çıkışta depoda 150 kalırdı ve hiçbiri outlet'e akmazdı
    t2 = dict(t)
    t2["sevkiyat"] = t["sevkiyat"][t["sevkiyat"]["tip"] != "outlet_akisi"].reset_index(drop=True)
    ak = hikaye.rpt_akibeti(t2, opt, "SS25").set_index("option_id")
    assert taban.loc["OPT-A", "rpt_outlete"] == 130 and ak.loc["OPT-A", "rpt_outlete"] == 0
    assert ak.loc["OPT-A", "rpt_depoda_kalan"] == 150
    # çıkışta depo daha küçükse çıkışa dek çıkan RPT büyür (FIFO alt sınırı)
    t3 = dict(t)
    d = t["depo_stok"].copy()
    d.loc[(d["tarih"] == pd.Timestamp("2025-03-10")) & (d["urun_id"] == "A-S"), "adet"] = 60
    t3["depo_stok"] = d
    ak3 = hikaye.rpt_akibeti(t3, opt, "SS25").set_index("option_id")
    assert ak3.loc["OPT-A", "depo_cikista"] == 90 and ak3.loc["OPT-A", "rpt_cikisa_kadar"] == 100
    assert ak3.loc["OPT-A", "rpt_depoda_kalan"] == 0       # önceden duran mal yok, 130 > 90
    assert ak3.loc["OPT-A", "rpt_outlete"] == 90


@pytest.mark.veri
def test_rpt_akibeti_tutarli(veri):
    t, opt = veri["t"], veri["opt"]
    r = hikaye.rpt_siparisleri(t, opt)
    assert (r["adet"] > 0).all()
    oyun = r[r["sezon_kodu"].isin(("AW24", "SS25"))]
    assert (oyun["giren"] <= oyun["adet"]).all() and (oyun["giren"] > 0).all()
    toplam = 0
    for sezon in ("AW24", "SS25"):
        ak = hikaye.rpt_akibeti(t, opt, sezon)
        toplam += len(ak)
        girdi = r.loc[r["sezon_kodu"] == sezon]
        assert ak["rpt"].sum() == girdi["adet"].sum()
        assert ak["rpt_giren"].sum() == girdi["giren"].sum()
        # kovalar giren adedi tam bölüşür ve negatif olmaz
        kovalar = ak[["rpt_cikisa_kadar", "rpt_outlete", "rpt_depoda_kalan"]]
        assert (kovalar >= 0).all().all()
        assert (kovalar.sum(axis=1) == ak["rpt_giren"]).all()
        # v4 akışlarına bağlı sınırlar (boş doğrulama değil): depoda kalan RPT pencere
        # sonu depo stoğunu, outlet'e akan RPT çıkış sonrası depodan çıkan adedi aşamaz,
        # mağazaya giden alt sınır üst sınırı aşamaz; çıkışa dek çıkan RPT, aynı sürede depodan
        # mağazalara giden ve online satılan toplamı aşamaz (FIFO alt sınırı gerçek akışla tutarlı)
        assert (ak["rpt_depoda_kalan"] <= ak["depo_son"]).all()
        assert (ak["rpt_outlete"] <= ak["cikis_sonrasi_cikan"]).all()
        assert (ak["rpt_magazaya_alt"] <= ak["rpt_magazaya_ust"]).all()
        assert (ak["rpt_cikisa_kadar"] <= ak["gelisten_cikisa_cikan"] + ak["online_gelisten_cikisa"]).all()
        assert (ak["rpt_depoda_cikista"] <= ak["depo_cikista"]).all()
        # çıkış sabahı depoda mal var ve çıkıştan sonra depodan outlet akışıyla mal çıkıyor
        assert (ak["depo_cikista"] > 0).any() and (ak["cikis_sonrasi_cikan"] > 0).any()
        # RPT'nin bir kısmı çıkışta depoda, bir kısmı çıkışa dek çıkmış: iki kova da dolu
        assert ak["rpt_depoda_cikista"].sum() > 0 and ak["rpt_cikisa_kadar"].sum() > 0
    assert toplam > 0
    # Lumoda'nın kuralı: option başına en fazla bir RPT, yalnız Collection
    assert r.groupby("option_id").size().max() == 1
    assert set(opt.set_index("option_id").loc[r["option_id"], "line"]) == {"Collection"}
    # lansmandan 3–6 hafta sonra verilir
    assert r["siparis_h"].between(3, 6).all()
