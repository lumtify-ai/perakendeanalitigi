"""kayip: Poisson koşullu fazla, kayıp tablosu ve özet."""

import logging
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest
from conftest import ekle, oyuncak_baglan, oyuncak_tablolar

from perakende_analitik import kayip, stok

S, M, L = "MDL0001-SYH-S", "MDL0001-SYH-M", "MDL0001-SYH-L"
LISTE, ALIS = 250.0, 100.0   # oyuncak ürün tablosu


# ----------------------------------------------------------- Poisson fazlası

def _dogrudan(lam: float, s: int) -> float:
    """E[D | D >= s] - s, üst kuyruğun doğrudan (log uzayında) toplamıyla."""
    if lam <= 0:
        return 0.0
    k_son = int(s + lam + 40 * math.sqrt(lam + 1) + 200)
    logp = [-lam + k * math.log(lam) - math.lgamma(k + 1) for k in range(s, k_son + 1)]
    m = max(logp)
    w = [math.exp(x - m) for x in logp]
    pay = math.fsum(k * wi for k, wi in zip(range(s, k_son + 1), w))
    payda = math.fsum(w)
    return pay / payda - s


def test_poisson_kosullu_fazla_bilinen():
    assert kayip.poisson_kosullu_fazla(np.array([2.0]), np.array([0]))[0] == pytest.approx(2.0)
    assert kayip.poisson_kosullu_fazla(np.array([2.0]), np.array([2]))[0] == pytest.approx(0.9114, abs=1e-3)


def test_poisson_kosullu_fazla_dogrudan_toplamla_ayni():
    lamlar = [0.01, 0.5, 2.0, 10.0, 50.0]
    sler = [0, 1, 2, 5, 20, 80]
    lam = np.repeat(lamlar, len(sler))
    s = np.tile(sler, len(lamlar))
    sonuc = kayip.poisson_kosullu_fazla(lam, s)
    beklenen = np.array([_dogrudan(l, int(k)) for l, k in zip(lam, s)])
    assert np.isfinite(sonuc).all() and (sonuc >= 0).all()
    np.testing.assert_allclose(sonuc, beklenen, rtol=1e-9, atol=0)


def test_poisson_kosullu_fazla_kuyruk_ve_uc_degerler():
    # s >> lam: P(D >= s) ~ 1e-100'ler; sonuç sonlu ve lam/(s+1)'e yakın
    lam = np.array([0.01, 0.5, 2.0, 0.0, 3.0, 1e-9])
    s = np.array([200, 400, 300, 5, 0, 7])
    sonuc = kayip.poisson_kosullu_fazla(lam, s)
    assert np.isfinite(sonuc).all()
    np.testing.assert_allclose(sonuc[:3], lam[:3] / (s[:3] + 1), rtol=5e-2)
    assert sonuc[3] == 0.0                      # lam 0 -> 0
    assert sonuc[4] == pytest.approx(3.0)       # s 0 -> lam
    assert sonuc[5] == pytest.approx(1e-9 / 8, rel=1e-3)
    # büyük lam: üstel alt taşma yok
    buyuk = kayip.poisson_kosullu_fazla(np.array([900.0, 900.0]), np.array([850, 1000]))
    np.testing.assert_allclose(
        buyuk, [_dogrudan(900.0, 850), _dogrudan(900.0, 1000)], rtol=1e-9)


def test_poisson_kosullu_fazla_bos_ve_hatali_girdi():
    assert kayip.poisson_kosullu_fazla(np.array([]), np.array([], dtype=int)).shape == (0,)
    with pytest.raises(ValueError, match="sonlu"):
        kayip.poisson_kosullu_fazla(np.array([np.nan]), np.array([1]))
    with pytest.raises(ValueError, match="negatif"):
        kayip.poisson_kosullu_fazla(np.array([1.0]), np.array([-1]))
    with pytest.raises(ValueError, match="uzunluk"):
        kayip.poisson_kosullu_fazla(np.array([1.0, 2.0]), np.array([1]))


def test_kuyruk_satiri_sayilir_ve_kayda_yazilir(caplog):
    lam = np.array([0.01, 2.0, 0.01])
    s = np.array([100, 2, 50])                   # birinci ve üçüncü: P(D >= s) < 1e-12
    with caplog.at_level(logging.INFO, logger="perakende_analitik.kayip"):
        sonuc, n = kayip.poisson_kosullu_fazla_say(lam, s)
    assert n == 2 and len(sonuc) == 3
    assert "2" in caplog.text and "kuyruk" in caplog.text


# --------------------------------------------------------------- kayip_yaz

def _gunluk(satirlar: list[tuple]) -> pd.DataFrame:
    """(tarih, magaza, urun, durum, satis_oncesi, brut_satis) -> günlük tablo (R9, R10)."""
    df = pd.DataFrame(satirlar, columns=["tarih", "magaza_id", "urun_id", "durum",
                                         "satis_oncesi", "brut_satis"])
    df["tarih"] = pd.to_datetime(df["tarih"]).astype("datetime64[ns]")
    df["option_id"] = df["urun_id"].str.rsplit("-", n=1).str[0]
    df["net_satis"] = df["brut_satis"]
    df["durum"] = pd.Categorical(df["durum"], categories=stok.DURUMLAR)
    for c in ("magaza_id", "urun_id", "option_id"):
        df[c] = df[c].astype("category")
    for c in ("satis_oncesi", "brut_satis", "net_satis"):
        df[c] = df[c].astype("int32")
    return df[["tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi", "brut_satis",
               "net_satis", "durum"]]


def _uc_durum():
    g = _gunluk([("2025-01-08", "M001", S, "bos", 0, 0),
                 ("2025-01-09", "M001", S, "tukenen", 2, 2),
                 ("2025-01-10", "M001", S, "stoklu", 3, 1),
                 ("2025-01-11", "M001", S, "tukenen", 5, 5)])
    t = pd.Series([1.5, 2.0, 0.7, 0.4], index=g.index)
    return g, t


def test_bos_gunde_kayip_tahmin():
    g, t = _uc_durum()
    k = kayip.kayip_yaz(g, t)
    r = k.iloc[0]
    assert r["durum"] == "bos" and r["satis"] == 0
    assert r["kayip"] == pytest.approx(1.5) and r["kayip_saf"] == pytest.approx(1.5)
    assert r["tahmini_talep"] == pytest.approx(1.5)


def test_tukenen_gunde_kayip_saftan_buyuk():
    g, t = _uc_durum()
    k = kayip.kayip_yaz(g, t)
    r = k.iloc[1]          # lam 2, s 2: kayip 0.9114, saf max(0, 2 - 2) = 0
    assert r["satis"] == 2
    assert r["kayip"] == pytest.approx(0.9114, abs=1e-3) and r["kayip_saf"] == 0.0
    r = k.iloc[3]          # lam 0.4, s 5: saf 0, kayip ~ lam/(s+1) > 0
    assert r["kayip"] > 0 and r["kayip_saf"] == 0.0
    tuk = k[k["durum"] == "tukenen"]
    assert (tuk["kayip"] >= tuk["kayip_saf"]).all() and (tuk["kayip"] > 0).all()


def test_stoklu_gunde_kayip_sifir():
    g, t = _uc_durum()
    r = kayip.kayip_yaz(g, t).iloc[2]
    assert r["kayip"] == 0.0 and r["kayip_saf"] == 0.0
    assert r["tahmini_talep"] == pytest.approx(0.7) and r["satis"] == 1


def test_kayip_yaz_sema_ve_turler():
    g, t = _uc_durum()
    k = kayip.kayip_yaz(g, t)
    assert list(k.columns) == list(g.columns) + ["tahmini_talep", "satis", "kayip", "kayip_saf"]
    for c in ("tahmini_talep", "kayip", "kayip_saf"):
        assert k[c].dtype == np.float64
    assert k["tarih"].dtype == np.dtype("datetime64[ns]")
    assert k["durum"].cat.categories.tolist() == list(stok.DURUMLAR)
    assert k.index.equals(g.index) and len(k) == len(g)
    assert k["satis"].tolist() == g["brut_satis"].tolist()


def test_kayip_yaz_sifir_tahmin_sifir_kayip():
    g = _gunluk([("2025-01-08", "M001", S, "bos", 0, 0), ("2025-01-09", "M001", S, "tukenen", 4, 4)])
    k = kayip.kayip_yaz(g, pd.Series([0.0, 0.0], index=g.index))
    assert (k["kayip"] == 0).all() and (k["kayip_saf"] == 0).all()


def test_kayip_yaz_indeks_hizasi_ve_hatalar():
    g, t = _uc_durum()
    g2 = g.iloc[::-1]                       # sıra ters, indeksle hizalanır
    k = kayip.kayip_yaz(g2, t)
    assert k.index.equals(g2.index)
    assert k["tahmini_talep"].tolist() == [0.4, 0.7, 2.0, 1.5]
    with pytest.raises(ValueError, match="sonlu"):
        kayip.kayip_yaz(g, pd.Series([1.0, np.nan, 1.0, 1.0], index=g.index))
    with pytest.raises(ValueError, match="negatif"):
        kayip.kayip_yaz(g, pd.Series([1.0, -1.0, 1.0, 1.0], index=g.index))
    with pytest.raises(ValueError, match="hizal"):
        kayip.kayip_yaz(g, t.iloc[:3])


def test_kayip_yaz_vektorel_buyuk_girdi_dogrudan_toplamla_ayni():
    rng = np.random.default_rng(1)
    n = 3000
    s = rng.integers(0, 12, n)
    lam = rng.gamma(1.5, 1.0, n)
    durum = np.where(s > 0, "tukenen", "bos")
    g = _gunluk([("2025-01-08", "M001", S, d, int(x), int(x)) for d, x in zip(durum, s)])
    k = kayip.kayip_yaz(g, pd.Series(lam, index=g.index))
    beklenen = np.array([_dogrudan(l, int(x)) for l, x in zip(lam, s)])
    np.testing.assert_allclose(k["kayip"].to_numpy(), beklenen, rtol=1e-9)
    assert (k["kayip"] >= k["kayip_saf"] - 1e-12).all()


def test_kayip_yaz_kuyruk_sayisi_attrs():
    g = _gunluk([("2025-01-08", "M001", S, "tukenen", 100, 100),
                 ("2025-01-09", "M001", S, "tukenen", 1, 1)])
    k = kayip.kayip_yaz(g, pd.Series([0.01, 1.0], index=g.index))
    assert k.attrs["kuyruk_satir"] == 1


# -------------------------------------------------------------------- ozet

@pytest.fixture
def ozet_con():
    t = oyuncak_tablolar()
    ekle(t, "fiyat", [("2025-01-06", "MDL0001-SYH", "normal", 0.30),
                      ("2025-01-13", "MDL0001-SYH", "normal", 0.10)])
    con = oyuncak_baglan(t)
    yield con
    con.close()


def _ozet_girdi():
    g = _gunluk([("2025-01-08", "M001", S, "bos", 0, 0),        # hafta 01-06: oran .30
                 ("2025-01-09", "M001", M, "bos", 0, 0),        # oran .30
                 ("2025-01-14", "M001", S, "bos", 0, 0),        # hafta 01-13: oran .10
                 ("2025-01-14", "ONL", S, "bos", 0, 0)])        # online hattı, panel yok: 0
    return g, pd.Series([2.0, 1.0, 4.0, 3.0], index=g.index)


def test_ozet_tl_ve_marj_etiket_fiyatiyla(ozet_con):
    g, t = _ozet_girdi()
    k = kayip.kayip_yaz(g, t)
    o = kayip.ozet(k, ["magaza_id"], ozet_con)
    assert list(o.columns) == ["magaza_id", "kayip_adet", "kayip_tl", "kayip_marj"]
    assert o["magaza_id"].tolist() == ["M001", "ONL"]
    m001 = o.iloc[0]
    etiket = [LISTE * 0.70, LISTE * 0.70, LISTE * 0.90]
    adet = [2.0, 1.0, 4.0]
    assert m001["kayip_adet"] == pytest.approx(7.0)
    assert m001["kayip_tl"] == pytest.approx(sum(a * e for a, e in zip(adet, etiket)))
    assert m001["kayip_marj"] == pytest.approx(sum(a * (e - ALIS) for a, e in zip(adet, etiket)))
    onl = o.iloc[1]
    assert onl["kayip_tl"] == pytest.approx(3.0 * LISTE)
    assert onl["kayip_marj"] == pytest.approx(3.0 * (LISTE - ALIS))


def test_ozet_oran_float32_gurultusu_yok(ozet_con):
    g, t = _ozet_girdi()
    o = kayip.ozet(kayip.kayip_yaz(g, t), [], ozet_con)
    assert len(o) == 1
    assert o["kayip_tl"].iloc[0] == pytest.approx(
        2 * 175.0 + 1 * 175.0 + 4 * 225.0 + 3 * 250.0, rel=1e-12)


def test_ozet_oran_varsa_ozelliklerden_eklenmez(ozet_con):
    g, t = _ozet_girdi()
    k = kayip.kayip_yaz(g, t)
    k["oran"] = np.float32(0.5)
    o = kayip.ozet(k, [], ozet_con)
    assert o["kayip_tl"].iloc[0] == pytest.approx(10.0 * LISTE * 0.5)


def test_ozet_turetilmis_duzeyler_ve_siralama(ozet_con):
    g, t = _ozet_girdi()
    k = kayip.kayip_yaz(g, t)
    o = kayip.ozet(k, ["yil", "hafta", "kanal"], ozet_con)
    assert list(o.columns) == ["yil", "hafta", "kanal", "kayip_adet", "kayip_tl", "kayip_marj"]
    assert o["yil"].tolist() == [2025, 2025, 2025]
    assert o["hafta"].tolist() == [pd.Timestamp("2025-01-06"), pd.Timestamp("2025-01-13"),
                                   pd.Timestamp("2025-01-13")]
    assert o["kanal"].tolist() == ["magaza", "magaza", "online"]
    assert o["kayip_adet"].tolist() == pytest.approx([3.0, 4.0, 3.0])
    assert o["hafta"].dtype == np.dtype("datetime64[ns]")
    # hafta: pazartesi (01-08 çarşamba -> 01-06)
    o2 = kayip.ozet(k, ["hafta", "magaza_id", "ust_kategori"], ozet_con)
    assert o2["ust_kategori"].tolist() == ["Üst Giyim"] * 3
    assert o2["kayip_adet"].sum() == pytest.approx(10.0)


def test_ozet_toplam_kayip_degismez_ve_stoklu_katki_yok(ozet_con):
    g = _gunluk([("2025-01-08", "M001", S, "stoklu", 3, 1), ("2025-01-08", "M001", M, "bos", 0, 0)])
    k = kayip.kayip_yaz(g, pd.Series([5.0, 2.0], index=g.index))
    o = kayip.ozet(k, ["durum"], ozet_con)
    assert o["durum"].tolist() == ["stoklu", "bos"]      # gözlenmeyen kategori çıkmaz
    assert o["kayip_adet"].tolist() == pytest.approx([0.0, 2.0])


def test_ozet_bilinmeyen_duzey(ozet_con):
    g, t = _ozet_girdi()
    with pytest.raises(ValueError, match="duzey"):
        kayip.ozet(kayip.kayip_yaz(g, t), ["yok_boyle_sutun"], ozet_con)


# --------------------------------------------------------------- gerçek veri

@pytest.mark.veri
def test_gercek_v4_kayip_yaz_ve_ozet(v4_con, caplog):
    from perakende_analitik import ozellikler, talep
    bas, bit = date(2024, 9, 1), date(2024, 10, 31)
    g = pd.concat([stok.gunluk_magaza(v4_con, bas, bit), stok.gunluk_online(v4_con, bas, bit)],
                  ignore_index=True)
    g = ozellikler.ekle(v4_con, g)
    gozlem = g[g["durum"] == "stoklu"].reset_index(drop=True)
    hedef = g[(g["durum"] != "stoklu") & (g["tarih"] >= "2024-10-01")]
    k = talep.Naif()
    k.egit(gozlem)
    t = k.tahmin(hedef)
    with caplog.at_level(logging.INFO, logger="perakende_analitik.kayip"):
        kd = kayip.kayip_yaz(hedef[stok_sutunlari()], t)
    assert np.isfinite(kd["kayip"]).all() and (kd["kayip"] >= kd["kayip_saf"] - 1e-9).all()
    o = kayip.ozet(kd, ["yil", "kanal"], v4_con)
    assert (o["kayip_tl"] > 0).all() and (o["kayip_marj"] <= o["kayip_tl"]).all()
    print("kuyruk_satir", kd.attrs["kuyruk_satir"], "toplam_satir", len(kd),
          "tukenen", int((kd["durum"] == "tukenen").sum()))


def stok_sutunlari() -> list[str]:
    return ["tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi", "brut_satis",
            "net_satis", "durum"]
