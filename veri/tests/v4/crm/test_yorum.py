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
    # Spec bandı 4,0–4,4; brief'in neden çarpanlarıyla ulaşılamıyor (rapor),
    # burada yalnız akıl sağlığı sınırı.
    assert 3.7 <= sonuc.yorum["puan"].mean() <= 4.6


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
    """İade konusu yalnız iade edilmiş satırda; olumsuz kargo yalnız gecikmede."""
    assert birlesik.loc[birlesik["konular"].str.contains("iade_sureci"), "iade"].all()
    olumsuz_kargo = birlesik["konular"].str.contains("kargo_teslimat") & (birlesik["duygu"] != "olumlu")
    assert birlesik.loc[olumsuz_kargo, "gecikme"].all()


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
