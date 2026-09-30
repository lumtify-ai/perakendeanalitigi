"""Görev 12: yorumların online sipariş satırlarına atanması."""

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4.crm.yorum import (
    AZAMI_KULLANIM,
    GEVSEME_BASAMAKLARI,
    YORUM_SUTUNLARI,
    GIZLI_SUTUNLARI,
    kutuphane_yukle,
    metin_sec,
    yorum_uret_ayrintili,
    yorumlari_uret,
)
from perakende_veri.v4.crm.rastgele import crm_uretici


@pytest.fixture(scope="module")
def kutuphane():
    return kutuphane_yukle()


@pytest.fixture(scope="module")
def sonuc(kucuk_girdi, kucuk_crm, kutuphane):
    return yorum_uret_ayrintili(crm_uretici(kucuk_crm.D, "yorum"), kucuk_crm, kucuk_girdi, kutuphane)


@pytest.fixture(scope="module")
def birlesik(sonuc):
    """yorum + gizli + aday satırı (fiş günü, teslim, bayraklar)."""
    y = sonuc.yorum.merge(sonuc.gizli, on="yorum_id")
    return y.merge(sonuc.aday, left_on="fis_satir_id", right_on="satir_id", how="left")


# ---------------------------------------------------------------------------
# Şema
# ---------------------------------------------------------------------------


def test_sutunlar(sonuc):
    assert list(sonuc.yorum.columns) == list(YORUM_SUTUNLARI)
    assert list(sonuc.gizli.columns) == list(GIZLI_SUTUNLARI)
    assert len(sonuc.yorum) == len(sonuc.gizli)
    assert (sonuc.yorum["yorum_id"].to_numpy() == np.arange(len(sonuc.yorum))).all()
    gizli = {"konular", "duygu", "nedenler", "kutuphane_id", "uslup", "gevseme"}
    assert not gizli & set(sonuc.yorum.columns)


def test_yorumlari_uret_ayni_cift(kucuk_girdi, kucuk_crm, kutuphane, sonuc):
    y, g = yorumlari_uret(crm_uretici(kucuk_crm.D, "yorum"), kucuk_crm, kucuk_girdi, kutuphane)
    pd.testing.assert_frame_equal(y, sonuc.yorum)
    pd.testing.assert_frame_equal(g, sonuc.gizli)


def test_satir_basina_en_fazla_bir_yorum(sonuc):
    assert sonuc.yorum["fis_satir_id"].is_unique


def test_yorum_online_satis_satirinda_ve_musteri_urun_dogru(kucuk_crm, kucuk_girdi, sonuc):
    fs = kucuk_crm.tablo("fis_satir")
    fis = kucuk_crm.tablo("fis")
    y = sonuc.yorum.merge(fs[["satir_id", "fis_id", "sku", "adet"]], left_on="fis_satir_id",
                          right_on="satir_id", how="left")
    assert y["fis_id"].notna().all()
    assert (y["adet"] > 0).all()
    y = y.merge(fis[["fis_id", "magaza", "musteri", "tip"]], on="fis_id")
    assert (y["magaza"] == kucuk_crm.nufus.magaza.onl).all()
    assert (y["tip"] == 0).all()
    assert (y["musteri"] == y["musteri_id"]).all()
    urun_id = kucuk_girdi.dunya.urunler["urun_id"].to_numpy()
    assert (urun_id[y["sku"].to_numpy()] == y["urun_id"].to_numpy()).all()


# ---------------------------------------------------------------------------
# Oran, puan
# ---------------------------------------------------------------------------


def test_oran_kucukte_bantta(sonuc):
    oran = len(sonuc.yorum) / sonuc.aday_sayisi
    assert 0.03 <= oran <= 0.10, oran


def test_ortalama_puan_kucukte(sonuc):
    # Spec bandı 4,0–4,4 (Görev 12b: 7.000 metin, hediye süzgeci; KUCUK 5
    # tohumda 4,01–4,04).
    assert 4.0 <= sonuc.yorum["puan"].mean() <= 4.4


def test_puan_nedenden(birlesik):
    """Puan gevşetilmemiş yorumlarda puan nedenin aralığında."""
    puan_sabit = np.array([pf == 0 for _, pf in GEVSEME_BASAMAKLARI])
    b = birlesik[puan_sabit[birlesik["gevseme"].to_numpy()]]
    ned = b["nedenler"].fillna("")
    olumsuz = ned.str.contains("kalite|beden|kargo")
    iade_beden = ned.str.contains("beden") & b["iade"]
    assert b.loc[iade_beden, "puan"].between(1, 2).all()
    assert b.loc[olumsuz, "puan"].between(1, 3).all()
    assert b.loc[ned == "", "puan"].between(4, 5).all()
    assert b.loc[ned == "fiyat", "puan"].between(4, 5).all()
    nedensiz = b.loc[ned == "", "puan"]
    assert (nedensiz == 5).mean() > 0.5


def test_neden_bayrakla_tutarli(birlesik):
    ned = birlesik["nedenler"].fillna("")
    assert birlesik.loc[ned.str.contains("kalite"), "hatali_tedarikci"].all()
    assert birlesik.loc[ned.str.contains("beden"), "beden_uyumsuz"].all()
    assert birlesik.loc[ned.str.contains("kargo"), "gecikme"].all()
    assert birlesik.loc[ned.str.contains("fiyat"), "derin_indirim"].all()


# ---------------------------------------------------------------------------
# Nedenler görünür
# ---------------------------------------------------------------------------


def test_hatali_tedarikcide_kalite_konusu_iki_kat(birlesik):
    kalite = birlesik["konular"].str.contains("kumas_kalite")
    h = birlesik["hatali_tedarikci"]
    pay_h, pay_d = kalite[h].mean(), kalite[~h].mean()
    assert pay_h > 2 * pay_d, (pay_h, pay_d)


def test_gecikmede_kargo_sikayeti(birlesik):
    kargo = birlesik["konular"].str.contains("kargo_teslimat") & (birlesik["puan"] <= 3)
    g = birlesik["gecikme"]
    assert kargo[g].mean() > 3 * kargo[~g].mean()


# ---------------------------------------------------------------------------
# Metin
# ---------------------------------------------------------------------------


def test_yer_tutucu_kalmaz(sonuc):
    assert not sonuc.yorum["metin"].str.contains(r"[{}]").any()


def test_yer_tutucu_sku_ile_dolar(birlesik, kutuphane, kucuk_girdi):
    u = kucuk_girdi.dunya.urunler
    kut = kutuphane.set_index("id")
    renkli = birlesik[kut.loc[birlesik["kutuphane_id"], "yer_tutucu"].map(lambda y: "renk" in y).to_numpy()]
    assert len(renkli) > 0
    renk = u["renk"].to_numpy()[renkli["sku"].to_numpy()]
    for r, m in zip(renk, renkli["metin"]):
        kucuk = r.replace("İ", "i").replace("I", "ı").lower()
        assert kucuk in m.replace("İ", "i").replace("I", "ı").lower(), (r, m)
    bedenli = birlesik[kut.loc[birlesik["kutuphane_id"], "yer_tutucu"].map(lambda y: "beden" in y).to_numpy()]
    assert len(bedenli) > 0
    beden = u["beden"].to_numpy()[bedenli["sku"].to_numpy()]
    assert (beden != "STD").all()
    for b, m in zip(beden, bedenli["metin"]):
        assert b in m, (b, m)


def test_metin_kutuphaneden(birlesik, kutuphane):
    kut = kutuphane.set_index("id")
    duz = ~kut.loc[birlesik["kutuphane_id"], "yer_tutucu"].map(bool).to_numpy()
    assert (kut.loc[birlesik["kutuphane_id"][duz], "metin"].to_numpy() == birlesik["metin"][duz].to_numpy()).all()
    assert (kut.loc[birlesik["kutuphane_id"], "puan"].to_numpy() == birlesik["puan"].to_numpy()).all()
    assert (kut.loc[birlesik["kutuphane_id"], "duygu"].to_numpy() == birlesik["duygu"].to_numpy()).all()


def test_kategori_ve_alt_kategori_uyumu(birlesik, kutuphane, kucuk_girdi):
    u = kucuk_girdi.dunya.urunler
    kut = kutuphane.set_index("id").loc[birlesik["kutuphane_id"]]
    sku = birlesik["sku"].to_numpy()
    assert (kut["kategori_grubu"].to_numpy() == u["ust_kategori"].to_numpy()[sku]).all()
    alt = kut["alt_kategori"].to_numpy()
    dolu = pd.notna(alt)
    assert dolu.any()
    assert (alt[dolu] == u["alt_kategori"].to_numpy()[sku][dolu]).all()


def test_celiski_yok(birlesik):
    """İade konusu yalnız iade edilmiş satırda; olumsuz kargo yalnız gecikmede,
    olumlu kargo yalnız gecikmeyen satırda."""
    assert birlesik.loc[birlesik["konular"].str.contains("iade_sureci"), "iade"].all()
    olumsuz_kargo = birlesik["konular"].str.contains("kargo_teslimat") & (birlesik["duygu"] != "olumlu")
    assert birlesik.loc[olumsuz_kargo, "gecikme"].all()
    olumlu_kargo = birlesik["konular"].str.contains("kargo_teslimat") & (birlesik["duygu"] == "olumlu")
    assert olumlu_kargo.any()
    assert not birlesik.loc[olumlu_kargo, "gecikme"].any()


def test_ayni_metin_en_fazla_25(sonuc):
    assert sonuc.gizli["kutuphane_id"].value_counts().max() <= AZAMI_KULLANIM


# ---------------------------------------------------------------------------
# Tarih
# ---------------------------------------------------------------------------


def test_tarih_teslimattan_sonra(birlesik):
    from perakende_veri.v4.tablolar import pencere
    from perakende_veri.v4.takvim import gun_indisi

    gun = np.array([gun_indisi(t) for t in birlesik["tarih"].dt.date])
    teslim = birlesik["gun"].to_numpy() + birlesik["teslim_gun"].to_numpy()
    assert (gun >= teslim + 1).all() and (gun <= teslim + 10).all()
    bas, son = pencere()
    assert (birlesik["gun"] >= bas).all() and (gun <= son).all()


# ---------------------------------------------------------------------------
# Seçim ve gevşetme (küçük sentetik kütüphane)
# ---------------------------------------------------------------------------


def test_metin_sec_kapasite_gevsetme_ve_dusme():
    # 1 aday anahtarı, 3 metin: basamak 0'da 1, basamak 1'de 1 metin daha;
    # sınır 2 → 4 yorum sığar, 5. düşer.
    adaylar = {0: [np.array([0]), np.array([0, 1]), np.array([], dtype=np.int64),
                   np.array([], dtype=np.int64), np.array([], dtype=np.int64),
                   np.array([], dtype=np.int64)]}
    anahtar = np.zeros(5, dtype=np.int64)
    u = np.linspace(0.1, 0.9, 5)
    secim, basamak = metin_sec(lambda k, b: adaylar[k][b], anahtar, np.arange(5), u,
                               n_metin=3, azami=2)
    assert (secim[:2] == 0).all() and (basamak[:2] == 0).all()
    assert (secim[2:4] == 1).all() and (basamak[2:4] == 1).all()
    assert secim[4] == -1 and basamak[4] == -1
    assert np.bincount(secim[secim >= 0]).max() <= 2


def test_gevseme_paylari_raporlanir(sonuc):
    assert sum(sonuc.gevseme_sayilari) + sonuc.dusen_kapasite == sonuc.yazar_sayisi - sonuc.dusen_tarih
    assert sum(sonuc.gevseme_sayilari) == len(sonuc.yorum)


def test_determinizm(kucuk_girdi, kucuk_crm, kutuphane, sonuc):
    y, _ = yorumlari_uret(crm_uretici(kucuk_crm.D, "yorum"), kucuk_crm, kucuk_girdi, kutuphane)
    y2, _ = yorumlari_uret(crm_uretici(kucuk_crm.D, "yorum", tohum=1), kucuk_crm, kucuk_girdi, kutuphane)
    assert y.equals(sonuc.yorum)
    assert not y2.equals(y)


def test_temel_olasilik_kapasiteye_gore_kuculur():
    from perakende_veri.v4.crm.yorum import HEDEF_YORUM_UST, TEMEL_OLASILIK, temel_olasilik

    az = np.ones(1000)
    assert temel_olasilik(az) == TEMEL_OLASILIK
    cok = np.full(10 * int(HEDEF_YORUM_UST / TEMEL_OLASILIK), 1.5)
    t = temel_olasilik(cok)
    assert t < TEMEL_OLASILIK
    assert t * cok.sum() == pytest.approx(HEDEF_YORUM_UST)


def test_hatali_tedarikci_ust_ceyrek(sonuc, kucuk_girdi):
    from perakende_veri.v4.crm.yorum import KALITE_ESIK_CEYREK

    w = kucuk_girdi.dunya
    h = w.gizli_tedarikci["hatali_orani"]
    ust = set(w.gizli_tedarikci.loc[h > h.quantile(KALITE_ESIK_CEYREK), "tedarikci_id"])
    assert 0 < len(ust) <= len(h) // 4 + 1
    tid = w.urunler["tedarikci_id"].to_numpy()[sonuc.aday["sku"].to_numpy()]
    assert (sonuc.aday["hatali_tedarikci"].to_numpy() == np.isin(tid, list(ust))).all()


def test_aday_satirlari_kargo_verilince_ayni(kucuk_girdi, kucuk_crm, sonuc):
    from perakende_veri.v4.crm.kargo import kargo_tablosu
    from perakende_veri.v4.crm.yorum import aday_satirlari

    a = aday_satirlari(kucuk_crm, kucuk_girdi, kargo=kargo_tablosu(kucuk_crm, kucuk_girdi))
    pd.testing.assert_frame_equal(a, sonuc.aday)


# ---------------------------------------------------------------------------
# Demografi (Görev 12b)
# ---------------------------------------------------------------------------


def test_hediye_satiri_yorum_yazmaz(sonuc, kucuk_girdi, kucuk_crm):
    """Müşteri ≠ ürün cinsiyeti (Unisex ve Aksesuar hariç) hediye sayılır ve
    yorum almaz."""
    from perakende_veri.v4.crm.sabitler import CINSIYETLER

    a = sonuc.aday
    u = kucuk_girdi.dunya.urunler
    sku = a["sku"].to_numpy()
    mus = a["musteri"].to_numpy()
    assert (a["musteri_cins"].to_numpy() == kucuk_crm.nufus.cinsiyet[mus]).all()
    assert (a["musteri_yas"].to_numpy() == kucuk_crm.nufus.yas_grubu[mus]).all()
    uc = u["cinsiyet"].to_numpy()[sku]
    mc = np.array(CINSIYETLER)[a["musteri_cins"].to_numpy()]
    aks = u["ust_kategori"].to_numpy()[sku] == "Aksesuar"
    beklenen = (uc != "Unisex") & ~aks & (mc != uc)
    assert (a["hediye"].to_numpy() == beklenen).all()
    assert 0.03 < a["hediye"].mean() < 0.30, a["hediye"].mean()
    yazilan = a.set_index("satir_id").loc[sonuc.yorum["fis_satir_id"], "hediye"]
    assert not yazilan.any()


def test_musteri_ve_urun_cinsiyeti_esit(birlesik, kucuk_crm, kucuk_girdi):
    from perakende_veri.v4.crm.sabitler import CINSIYETLER

    u = kucuk_girdi.dunya.urunler
    sku = birlesik["sku"].to_numpy()
    uc = u["cinsiyet"].to_numpy()[sku]
    mc = np.array(CINSIYETLER)[kucuk_crm.nufus.cinsiyet[birlesik["musteri_id"].to_numpy()]]
    serbest = (uc == "Unisex") | (u["ust_kategori"].to_numpy()[sku] == "Aksesuar")
    assert (mc[~serbest] == uc[~serbest]).all()
    assert (~serbest).sum() > 0.5 * len(birlesik)


def test_demografik_ipucu_celismez(birlesik, kutuphane, kucuk_crm):
    """cinsiyet_ipucu doluysa müşteri cinsiyeti, yas_ipucu doluysa müşterinin
    yaş grubu tutar (her yorum için)."""
    from perakende_veri.v4.crm.sabitler import CINSIYETLER, YAS_GRUPLARI

    kut = kutuphane.set_index("id").loc[birlesik["kutuphane_id"]]
    mus = birlesik["musteri_id"].to_numpy()
    mc = np.array(CINSIYETLER)[kucuk_crm.nufus.cinsiyet[mus]]
    my = np.array(YAS_GRUPLARI)[kucuk_crm.nufus.yas_grubu[mus]]
    kullanilan = 0
    for ci, yi, c, y in zip(kut["cinsiyet_ipucu"], kut["yas_ipucu"], mc, my):
        if isinstance(ci, str):
            assert ci == c
            kullanilan += 1
        if isinstance(yi, list):
            assert y in yi
            kullanilan += 1
    assert kullanilan > 0


def _sentetik(n, cins, yas, kutuphane_kayitlari):
    """Tek SKU'lu (Üst Giyim, Kadın) sentetik aday tablosu ve kütüphane."""
    u = pd.DataFrame({"urun_id": ["U0"], "ust_kategori": ["Üst Giyim"], "alt_kategori": ["Tişört"],
                      "beden": ["M"], "renk": ["Mavi"], "cinsiyet": ["Unisex"]})
    a = pd.DataFrame({
        "satir_id": np.arange(n), "fis_id": np.arange(n), "gun": np.full(n, 1100), "musteri": np.arange(n),
        "sku": np.zeros(n, dtype=np.int64), "teslim_gun": np.full(n, 2), "iade": False,
        "beden_uyumsuz": False, "gecikme": False, "hatali_tedarikci": False, "derin_indirim": False,
        "indirimli": False, "musteri_cins": np.full(n, cins, dtype=np.int8),
        "musteri_yas": np.full(n, yas, dtype=np.int8), "hediye": False,
    })
    taban = {"kategori_grubu": "Üst Giyim", "alt_kategori": None, "duygu": "olumlu",
             "konular": ["genel_begeni"], "uslup": "duz", "yer_tutucu": []}
    kut = pd.DataFrame([{**taban, **k} for k in kutuphane_kayitlari])
    return a, u, kut


@pytest.mark.parametrize("cins, yas, beklenen", [
    (1, 0, {"E"}), (0, 0, {"G"}), (0, 4, {"Y"}), (1, 4, {"E", "Y"}),
])
def test_demografi_suzgeci_gevsemez(cins, yas, beklenen):
    """İpucu tutmayan metin hiçbir gevşeme basamağında seçilmez."""
    from perakende_veri.v4.crm.yorum import yorumlari_ata

    kayitlar = [
        {"id": "E", "puan": 5, "cinsiyet_ipucu": "Erkek", "yas_ipucu": None, "metin": "e"},
        {"id": "Y", "puan": 4, "cinsiyet_ipucu": None, "yas_ipucu": ["55+"], "metin": "y"},
        {"id": "G", "puan": 5, "cinsiyet_ipucu": None, "yas_ipucu": ["18-24"], "metin": "g"},
    ]
    if cins == 1:      # erkek müşteri: genç ipucu yalnız 18-24'e
        kayitlar[2]["cinsiyet_ipucu"] = "Kadın"
    a, u, kut = _sentetik(3000, cins, yas, kayitlar)
    s = yorumlari_ata(np.random.default_rng(0), a, u, kut, son_gun=2000)
    assert s.yazar_sayisi > 50
    assert set(s.gizli["kutuphane_id"]) <= beklenen
    assert len(s.yorum) == min(s.yazar_sayisi - s.dusen_tarih, 25 * len(beklenen))


def test_eksik_tedarikci_sessiz_gecmez(kucuk_girdi):
    from perakende_veri.v4.crm.yorum import bayraklari_ekle

    u = kucuk_girdi.dunya.urunler
    gted = kucuk_girdi.dunya.gizli_tedarikci
    a = pd.DataFrame({"sku": [0], "adet": [1], "indirim_tutari": [0.0], "beden_uyumsuz": [False]})
    eksik = gted[gted["tedarikci_id"] != u["tedarikci_id"].iloc[0]]
    with pytest.raises(AssertionError):
        bayraklari_ekle(a, u, eksik)
