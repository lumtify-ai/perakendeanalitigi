"""carpanlar: hafta günü, özel gün, kampanya / markdown esnekliği, yaşam eğrisi, beden payı.

Dünyalar sentetiktir (`sentetik.cerceve`, `ozellikler.ekle` biçimi); gerçek
çarpanı bilinen Poisson satışlardan öğrenilen çarpan sınanır.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sentetik import cerceve

from perakende_analitik import carpanlar

BAS = pd.Timestamp("2023-01-02")   # pazartesi


def _izgara(gun_sayisi: int, magazalar: list[str], urunler: list[str]):
    """gün × mağaza × ürün ızgarası: (gün indisi, mağaza, ürün) düz diziler."""
    t, m, u = np.meshgrid(np.arange(gun_sayisi), np.arange(len(magazalar)),
                          np.arange(len(urunler)), indexing="ij")
    t, m, u = t.ravel(), m.ravel(), u.ravel()
    return t, np.array(magazalar, dtype=object)[m], np.array(urunler, dtype=object)[u], m, u


# ---------------------------------------------------------------- hafta günü

def test_hafta_gunu_carpani_sentetik():
    """Hafta sonu ×1,5 (mağaza), ×1,2 (online); mevsim dalgası ve tatil/kampanya
    günleri karıştırıcı. Öğrenilen oran 1,5 ± 0,02 ve 1,2 ± 0,02."""
    rng = np.random.default_rng(1)
    magazalar = [f"M{i:02d}" for i in range(10)] + ["ONL"]
    urunler = [f"OPT{i:02d}-STD" for i in range(10)]
    t, m, u, mi, _ = _izgara(364, magazalar, urunler)
    tarih = BAS + pd.to_timedelta(t, unit="D")
    hg = t % 7
    onl = m == "ONL"
    hafta_sonu = hg >= 5
    lam = np.where(onl, 80.0, 4.0) * (1 + 0.5 * np.sin(2 * np.pi * t / 364))
    lam = lam * np.where(hafta_sonu, np.where(onl, 1.2, 1.5), 1.0)
    tatil = np.isin(t, [50, 51, 52, 200])            # tatil günü talebi ×3: dışarıda kalmalı
    kamp = np.isin(t, np.arange(120, 130)) & (mi < 5)
    lam = lam * np.where(tatil, 3.0, 1.0) * np.where(kamp, 2.0, 1.0)
    df = cerceve(tarih, m, u, rng.poisson(lam), tatil=tatil,
                 kampanya_orani=np.where(kamp, 0.3, 0.0),
                 kampanya_id=np.where(kamp, "K1", None))
    c = carpanlar.ogren(df)
    for kanal, oran in (("magaza", 1.5), ("online", 1.2)):
        f = [c.hafta_gunu[(kanal, g)] for g in range(7)]
        assert np.mean(f) == pytest.approx(1.0)
        hafta_ici = np.mean(f[:5])
        assert f[5] / hafta_ici == pytest.approx(oran, abs=0.02)
        assert f[6] / hafta_ici == pytest.approx(oran, abs=0.02)


# ----------------------------------------------------------------- esneklik

def _kampanya_dunyasi(eps: float = 1.2, icsel_markdown: bool = False, ozel: bool = False,
                      sok: float = 0.1, mevsim: float = 0.3,
                      tohum: int = 7) -> pd.DataFrame:
    """İki bölge × 8 mağaza × 20 option, 182 gün. Bölge A'da dört dışsal kampanya
    (oranlar 0,3 / 0,2 / 0,3 / 0,4; 10 gün). Talep (1 − oran)^(−eps) ile artar;
    günlük ortak şok (log sapması `sok`) ve mevsim (91 günlük dalga, genlik
    `mevsim`) iki bölgede aynıdır.

    icsel_markdown: option 10–19 'zayıf'tır; 60. günden sonra talebi günde %5
    söner ve Lumoda kuralı onlara 84. gün (pazartesi) %30 markdown verir.
    ozel: 40–41. ve 100. günler tatil (talep ×1,4); 151–154. günler Black
    Friday (cuma–pazartesi; bütün hücrelerde %30 kampanya, trafik yalnız cuma ×1,5)."""
    rng = np.random.default_rng(tohum)
    magazalar = [f"A{i}" for i in range(8)] + [f"B{i}" for i in range(8)]
    urunler = [f"OPT{i:02d}-STD" for i in range(20)]
    t, m, u, mi, ui = _izgara(182, magazalar, urunler)
    taban = rng.uniform(4, 8, size=(16, 20))[mi, ui]
    gunluk_sok = np.exp(rng.normal(0, sok, size=182))[t]
    lam = taban * gunluk_sok * (1 + mevsim * np.sin(2 * np.pi * t / 91)) * np.where(t % 7 >= 5, 1.3, 1.0)

    kamp_oran = np.zeros(len(t))
    kamp_id = np.full(len(t), None, dtype=object)
    for kid, bas, oran in (("K1", 30, 0.3), ("K2", 75, 0.2), ("K3", 120, 0.3), ("K4", 160, 0.4)):
        k = (mi < 8) & (t >= bas) & (t < bas + 10)
        kamp_oran[k], kamp_id[k] = oran, kid
    tatil = np.zeros(len(t), dtype=bool)
    bf = np.zeros(len(t), dtype=bool)
    if ozel:
        tatil = np.isin(t, [40, 41, 100])
        bf = np.isin(t, [151, 152, 153, 154])
        kamp_oran[bf], kamp_id[bf] = 0.3, "BF"
        lam = lam * np.where(tatil, 1.4, 1.0) * np.where(t == 151, 1.5, 1.0)
    md = np.zeros(len(t))
    if icsel_markdown:
        zayif = ui >= 10
        lam = lam * np.where(zayif & (t > 60), np.exp(-0.05 * (t - 60)), 1.0)
        md[zayif & (t >= 84)] = 0.3
    oran = np.maximum(md, kamp_oran)
    lam = lam * (1 - oran) ** (-eps)
    tarih = BAS + pd.to_timedelta(t, unit="D")
    return cerceve(tarih, m, u, rng.poisson(lam), markdown_orani=md, kampanya_orani=kamp_oran,
                   kampanya_id=kamp_id, tatil=tatil, black_friday=bf)


def test_esneklik_kampanyadan_geri_kazanilir():
    c = carpanlar.ogren(_kampanya_dunyasi(eps=1.2))
    assert c.esneklik_kampanya["Üst Giyim"] == pytest.approx(1.2, abs=0.1)
    assert c.esneklik_kampanya["*"] == pytest.approx(1.2, abs=0.1)


def test_markdown_esnekligi_icsel_secimde_yanli():
    """Markdown talebi sönen hücreye gelir: markdown kademesinin iki yanından
    ölçülen ε̂ gerçeğin (1,2) çok altında; kampanya DiD'si doğru kalır."""
    c = carpanlar.ogren(_kampanya_dunyasi(eps=1.2, icsel_markdown=True))
    kamp = c.esneklik_kampanya["Üst Giyim"]
    md = c.esneklik_markdown["Üst Giyim"]
    assert kamp == pytest.approx(1.2, abs=0.1)
    assert np.isfinite(md)
    assert md < kamp - 0.5


def test_ozel_gun_fiyat_etkisi_cikarilir():
    """Tatil ×1,4; Black Friday cuması trafiği ×1,5, dört gün %30 kampanya. Fiyat
    etkisi (ε̂ kampanyadan) çıkarılınca BF çarpanı trafiğe iner (yoksa ~2,3
    olurdu), sonraki günlerinki 1'e.
    Günlük ortak şok yok: tek bir günün şoku o günün özel etkisinden ayırt edilemez.
    Mevsim dalgası yumuşak (genlik 0,1): komşu kıyası yerel doğrusal eğilim varsayar."""
    c = carpanlar.ogren(_kampanya_dunyasi(eps=1.2, ozel=True, sok=0.0, mevsim=0.1))
    assert c.ozel_gun["tatil"] == pytest.approx(1.4, abs=0.05)
    assert (BAS + pd.Timedelta(days=151)).dayofweek == 4
    assert c.ozel_gun["black_friday"] == pytest.approx(1.5, abs=0.1)
    assert c.ozel_gun["black_friday_devami"] == pytest.approx(1.0, abs=0.07)
    assert "indirim_baslangici" not in c.ozel_gun or c.ozel_gun["indirim_baslangici"] == 1.0


# -------------------------------------------------------------------- yaşam

def test_yasam_egrisi_sentetik():
    """Collection option'ları farklı haftalarda lanse olur; talep yaşa göre bilinen
    eğriyi izler. İndeks 0–4. haftanın ortalamasına normalize, %3 içinde."""
    rng = np.random.default_rng(3)
    egri = np.array([1.0, 1.3, 1.6, 1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4])
    magazalar = [f"M{i}" for i in range(10)]
    urunler = [f"OPT{i:02d}-STD" for i in range(20)]
    t, m, u, _, ui = _izgara(140, magazalar, urunler)
    lansman = (ui % 4) * 7                          # 0, 7, 14, 21. gün
    yas = t - lansman
    ok = (yas >= 0) & (yas < 70)
    t, m, u, yas = t[ok], m[ok], u[ok], yas[ok]
    lam = 5.0 * egri[yas // 7] * np.where(t % 7 >= 5, 1.5, 1.0)
    tarih = BAS + pd.to_timedelta(t, unit="D")
    df = cerceve(tarih, m, u, rng.poisson(lam), yas_gun=yas, line="Collection")
    y = carpanlar.ogren(df).yasam
    y = y[(y["line"] == "Collection") & (y["alt_kategori"] == "Gömlek")].set_index("yas_hafta")
    beklenen = egri / egri[:5].mean()
    np.testing.assert_allclose(y["indeks"].reindex(range(10)).to_numpy(), beklenen, rtol=0.03)


# --------------------------------------------------------------- beden payı

def test_beden_payi_seyrekse_zincir():
    """Pay stoklu günlerin satış hızındandır (stoklu gün sayısından bağımsız);
    mağaza × option'da 30'dan az stoklu SKU-gün varsa mağaza satırı yoktur,
    zincir satırı (`*`) kullanılır."""
    satir = []
    # M1: S 3/gün 20 gün, M 6/gün 10 gün (M seyrek stoklu ama hızı yüksek) -> 30 SKU-gün
    for g in range(20):
        satir.append((g, "M1", "OPT-S", 3))
    for g in range(10):
        satir.append((g, "M1", "OPT-M", 6))
    # M2: yalnız 10 SKU-gün -> seyrek
    for g in range(5):
        satir.append((g, "M2", "OPT-S", 1))
        satir.append((g, "M2", "OPT-M", 1))
    g, mm, uu, s = zip(*satir)
    df = cerceve(BAS + pd.to_timedelta(np.array(g), unit="D"), np.array(mm), np.array(uu),
                 np.array(s))
    bp = carpanlar.beden_payi(df).set_index(["magaza_id", "urun_id"])["pay"]
    assert bp[("M1", "OPT-S")] == pytest.approx(1 / 3)
    assert bp[("M1", "OPT-M")] == pytest.approx(2 / 3)
    assert ("M2", "OPT-S") not in bp.index
    # zincir: S (60+5)/(20+5), M (60+5)/(10+5)
    rs, rm = 65 / 25, 65 / 15
    assert bp[("*", "OPT-S")] == pytest.approx(rs / (rs + rm))
    assert bp[("*", "OPT-M")] == pytest.approx(rm / (rs + rm))


# ------------------------------------------------------------------ karakter

def test_karakter_carpimi():
    c = carpanlar.Carpanlar(
        hafta_gunu={("magaza", 5): 1.4, ("magaza", 0): 0.9},
        ozel_gun={"tatil": 1.3, "black_friday": 1.8, "black_friday_devami": 1.2,
                  "indirim_baslangici": 1.1},
        esneklik_kampanya={"Üst Giyim": 1.5, "*": 1.0},
        yasam=pd.DataFrame({"line": ["Collection"] * 3, "alt_kategori": ["Gömlek"] * 3,
                            "yas_hafta": [0, 1, 2], "indeks": [1.0, 1.2, 0.7]}),
    )
    tarih = pd.to_datetime(["2023-01-07", "2023-01-02", "2023-01-02", "2023-01-02", "2023-01-06"])
    df = cerceve(tarih, "M1", "OPT-S", 1, tatil=[True, False, False, False, True],
                 black_friday=[False, True, False, False, True], oran=[0.0, 0.3, 0.0, 0.2, 0.0],
                 ust_kategori=["Üst Giyim", "Üst Giyim", "Üst Giyim", "Aksesuar", "Üst Giyim"],
                 line=["Collection", "Collection", "Basic", "Collection", "Basic"],
                 yas_gun=[8, 30, -1, 3, -1])
    df.index = [10, 20, 30, 40, 50]
    k = carpanlar.karakter(df, c)
    assert list(k.index) == [10, 20, 30, 40, 50]
    np.testing.assert_allclose(k.to_numpy(), [
        1.4 * 1.3 * 1.2,                       # cumartesi, tatil, yaş haftası 1
        0.9 * 1.2 * 0.7 ** -1.5 * 0.7,         # BF pazartesisi (devamı), %30, yaş haftası 4 -> 2
        0.9,                                   # devamlı
        0.9 * 0.8 ** -1.0 * 1.0,               # üst kategori yok -> "*"
        1.8,                                   # BF cuması ve tatil: tek tür, BF önce gelir
    ])


# --------------------------------------------------------------- gerçek veri

@pytest.mark.veri
def test_gercek_v4_carpanlar_bir_ceyrek(v4_con):
    from perakende_analitik import ozellikler, stok
    bas, bit = date(2024, 7, 1), date(2024, 9, 30)
    g = pd.concat([stok.gunluk_magaza(v4_con, bas, bit), stok.gunluk_online(v4_con, bas, bit)],
                  ignore_index=True)
    g = ozellikler.ekle(v4_con, g[g["durum"] == "stoklu"].reset_index(drop=True))
    c = carpanlar.ogren(g)
    for kanal in ("magaza", "online"):
        f = np.array([c.hafta_gunu[(kanal, h)] for h in range(7)])
        assert np.isfinite(f).all() and (f > 0).all()
        assert f.mean() == pytest.approx(1.0)
    assert all(np.isfinite(v) and v > 0 for v in c.ozel_gun.values())
    assert 0.5 < c.esneklik_kampanya["*"] < 4.0
    assert np.isfinite(c.yasam["indeks"]).all() and (c.yasam["indeks"] > 0).all()
    assert (c.beden_payi.groupby(["magaza_id", "option_id"], observed=True)["pay"].sum()
            .to_numpy() == pytest.approx(1.0))
