"""talep: Naif ve Basit kestiriciler, komşu hızları.

Satışlar deterministiktir (gürültüsüz); beklenen tahmin elle hesaplanır.
Çarpanlar nötrdür (`Carpanlar()`: hepsi 1) ya da testte açıkça verilir.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sentetik import birlestir, cerceve

from perakende_analitik import carpanlar, talep

BAS = pd.Timestamp("2023-01-02")   # pazartesi


def _seri(magaza: str, urun: str, gunler, satis, durum="stoklu", **oz) -> pd.DataFrame:
    gunler = np.asarray(list(gunler))
    return cerceve(BAS + pd.to_timedelta(gunler, unit="D"), magaza, urun,
                   np.broadcast_to(np.asarray(satis), gunler.shape), durum=durum, **oz)


def _gozlem(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["durum"] == "stoklu"].reset_index(drop=True)


def _hedef(df: pd.DataFrame, magaza: str, urun: str, gun: int) -> pd.DataFrame:
    t = BAS + pd.Timedelta(days=gun)
    return df[(df["magaza_id"] == magaza) & (df["urun_id"] == urun) & (df["tarih"] == t)]


def _iki(gozlem, hedef, c=None):
    naif = talep.Naif()
    naif.egit(gozlem)
    basit = talep.Basit(carpanlar=c or carpanlar.Carpanlar())
    basit.egit(gozlem)
    return naif.tahmin(hedef), basit.tahmin(hedef)


# ------------------------------------------------------------------ Basit

def test_basit_iki_yana_bakar():
    """Stoksuzluktan önce 2/gün, sonra 6/gün: Basit (±14) iki yanı görür (4),
    Naif yalnız geriye bakar (2)."""
    df = birlestir(_seri("M1", "OPT-STD", range(30), 2),
                   _seri("M1", "OPT-STD", range(30, 33), 0, durum="bos"),
                   _seri("M1", "OPT-STD", range(33, 60), 6))
    n, b = _iki(_gozlem(df), _hedef(df, "M1", "OPT-STD", 31))
    assert n.iloc[0] == pytest.approx(2.0)
    assert b.iloc[0] == pytest.approx(4.0)
    assert b.iloc[0] > n.iloc[0]


def test_kismi_beden_stoksuzlugu():
    """S 3, M 5, L 2 adet/gün; M 20–34. günler boş. Option hızı stoklu S ve L'den
    (payları 0,3 + 0,2) 10/gün kurulur; M'nin tahmini 10 × 0,5 = 5."""
    df = birlestir(_seri("M1", "OPT-S", range(60), 3), _seri("M1", "OPT-L", range(60), 2),
                   _seri("M1", "OPT-M", [*range(20), *range(35, 60)], 5),
                   _seri("M1", "OPT-M", range(20, 35), 0, durum="bos"))
    n, b = _iki(_gozlem(df), _hedef(df, "M1", "OPT-M", 27))
    assert b.iloc[0] == pytest.approx(5.0)
    assert n.iloc[0] == pytest.approx(5.0)          # son 28 günde M'nin 20 stoklu günü


def test_naif_az_stoklu_gunde_option_hizi():
    """M 5–40. günler boş; 30. günün son 28 gününde M'nin yalnız 3 stoklu günü var
    (< 7): Naif mağaza × option hızına (10/gün) × M payına (0,5) düşer."""
    df = birlestir(_seri("M1", "OPT-S", range(60), 3), _seri("M1", "OPT-L", range(60), 2),
                   _seri("M1", "OPT-M", [*range(5), *range(41, 60)], 5),
                   _seri("M1", "OPT-M", range(5, 41), 0, durum="bos"))
    n, _ = _iki(_gozlem(df), _hedef(df, "M1", "OPT-M", 30))
    assert n.iloc[0] == pytest.approx(5.0)


def test_basit_en_yakin_28_stoklu_gun():
    """±14'te stoklu gün yoksa en yakın 28 stoklu gün; ürün bir daha gelmediyse
    (boşluğun bir ucu açık) bunlar yalnız geride kalır: 22–49. günler (3/gün)."""
    df = birlestir(_seri("M1", "OPT-STD", range(22), 1), _seri("M1", "OPT-STD", range(22, 50), 3),
                   _seri("M1", "OPT-STD", range(50, 120), 0, durum="bos"))
    _, b = _iki(_gozlem(df), _hedef(df, "M1", "OPT-STD", 100))
    assert b.iloc[0] == pytest.approx(3.0)


def test_basit_karakteri_kullanir():
    """Satış = 10 × hafta günü çarpanı (hafta sonu 1,5, hafta içi 0,8). Boş bir
    cumartesinin tahmini 10 × 1,5 = 15; çarpansız ortalama ~10 olurdu."""
    hf = {("magaza", g): (1.5 if g >= 5 else 0.8) for g in range(7)}
    gunler = np.arange(60)
    df = cerceve(BAS + pd.to_timedelta(gunler, unit="D"), "M1", "OPT-STD",
                 np.where(gunler % 7 >= 5, 15, 8), durum=np.where(gunler == 33, "bos", "stoklu"))
    assert (BAS + pd.Timedelta(days=33)).dayofweek == 5
    _, b = _iki(_gozlem(df), _hedef(df, "M1", "OPT-STD", 33), carpanlar.Carpanlar(hafta_gunu=hf))
    assert b.iloc[0] == pytest.approx(15.0)


def test_hic_stoklu_gunu_olmayan_hucre():
    """M2 × X hiç stoklu olmadı (bütün günler boş): zincir yedeği. Zincirde X'in
    hızı (M1'de 4/gün, M1'in alt kategori payı 0,75) × M2'nin payı (0,25) = 4/3.
    Pencerenin ilk günü Naif için zincirde de geçmiş yok: son yedek sonlu ve > 0."""
    df = birlestir(_seri("M1", "X-STD", range(60), 4), _seri("M1", "Y-STD", range(60), 2),
                   _seri("M2", "Y-STD", range(60), 2),
                   _seri("M2", "X-STD", range(60), 0, durum="bos"))
    hedef = df[(df["magaza_id"] == "M2") & (df["urun_id"] == "X-STD")]
    n, b = _iki(_gozlem(df), hedef)
    for s in (n, b):
        assert np.isfinite(s.to_numpy()).all() and (s.to_numpy() > 0).all()
    assert b.to_numpy() == pytest.approx(np.full(60, 4 / 3))
    assert n.iloc[30] == pytest.approx(4 / 3)
    assert n.iloc[0] == pytest.approx(2.0)          # M2'nin alt kategorideki SKU-gün hızı


def test_tahmin_sadece_gozlenen_sutunlari_okur():
    """Hedef çerçevesine `kayip` (ya da başka bir sütun) eklemek sonucu değiştirmez;
    sıra ve indeks girdininkidir."""
    df = birlestir(_seri("M1", "OPT-S", range(60), 3), _seri("M1", "OPT-L", range(60), 2),
                   _seri("M1", "OPT-M", [*range(20), *range(35, 60)], 5),
                   _seri("M1", "OPT-M", range(20, 35), 0, durum="bos"),
                   _seri("M2", "OPT-M", range(60), 0, durum="bos"))
    gozlem = _gozlem(df)
    hedef = df[df["durum"] != "stoklu"].sample(frac=1.0, random_state=0)
    hedef.index = np.arange(len(hedef))[::-1] * 3 + 7
    kirli = hedef.copy()
    kirli["kayip"] = np.random.default_rng(0).uniform(0, 100, len(kirli))
    for k in (talep.Naif(), talep.Basit(carpanlar=carpanlar.Carpanlar())):
        k.egit(gozlem)
        a, b = k.tahmin(hedef), k.tahmin(kirli)
        assert list(a.index) == list(hedef.index)
        pd.testing.assert_series_equal(a, b)
        assert np.isfinite(a.to_numpy()).all() and (a.to_numpy() >= 0).all()


def test_bos_hedef():
    df = _seri("M1", "OPT-STD", range(10), 2)
    for k in (talep.Naif(), talep.Basit(carpanlar=carpanlar.Carpanlar())):
        k.egit(df)
        s = k.tahmin(df.iloc[:0])
        assert len(s) == 0 and s.dtype == np.float64


# ------------------------------------------------------------- komşu hızları

def test_komsu_hizlar_iki_yanli_gun_haric():
    """Hücre: gün g'de g adet; 5. gün boş. Option'da kardeş beden her gün 1 adet."""
    df = birlestir(_seri("M1", "OPT-S", [*range(5), *range(6, 11)], [*range(5), *range(6, 11)]),
                   _seri("M1", "OPT-S", [5], 0, durum="bos"),
                   _seri("M1", "OPT-M", range(11), 1))
    k = talep.komsu_hizlar(df, komsu_gun=2)
    assert list(k.index) == list(df.index)
    s = df["urun_id"] == "OPT-S"
    gun = (df["tarih"] - BAS).dt.days
    satir5 = k[s & (gun == 5)].iloc[0]          # 3 + 4 + 6 + 7
    assert (satir5["komsu_hucre_satis"], satir5["komsu_hucre_gun"]) == (20, 4)
    assert (satir5["komsu_opsiyon_satis"], satir5["komsu_opsiyon_gun"]) == (20 + 4, 8)
    satir3 = k[s & (gun == 3)].iloc[0]          # 1 + 2 + 4 (5 boş, 3 hariç)
    assert (satir3["komsu_hucre_satis"], satir3["komsu_hucre_gun"]) == (7, 3)
    assert (satir3["komsu_opsiyon_satis"], satir3["komsu_opsiyon_gun"]) == (7 + 4, 7)
    assert k["komsu_hucre_gun"].dtype == np.int32

    # hedef ayrı verilirse havuz `gunluk`un stoklu günleridir
    h = talep.komsu_hizlar(df[df["durum"] == "stoklu"], komsu_gun=2, hedef=df[s & (gun == 5)])
    assert h.iloc[0]["komsu_hucre_satis"] == 20


# --------------------------------------------------------------- gerçek veri

@pytest.mark.veri
def test_gercek_v4_naif_basit_bir_ay(v4_con):
    from perakende_analitik import ozellikler, stok
    bas, bit = date(2024, 8, 15), date(2024, 10, 15)
    g = pd.concat([stok.gunluk_magaza(v4_con, bas, bit), stok.gunluk_online(v4_con, bas, bit)],
                  ignore_index=True)
    g = ozellikler.ekle(v4_con, g)
    gozlem = g[g["durum"] == "stoklu"].reset_index(drop=True)
    eylul = (g["tarih"] >= "2024-09-01") & (g["tarih"] <= "2024-09-30")
    hedef = g[eylul & (g["durum"] != "stoklu")]
    c = carpanlar.ogren(gozlem)
    for k in (talep.Naif(), talep.Basit(carpanlar=c)):
        k.egit(gozlem)
        t = k.tahmin(hedef)
        assert t.index.equals(hedef.index)
        assert np.isfinite(t.to_numpy()).all() and (t.to_numpy() >= 0).all()
        # stoksuz günün tahmini ortalaması stoklu günlerin ortalamasıyla aynı mertebede
        assert 0.1 < t.mean() / gozlem["brut_satis"].mean() < 10
