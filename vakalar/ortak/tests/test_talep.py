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
    """M2 × X hiç stoklu olmadı (bütün günler boş): zincir yedeği. Göreli hızlar
    (option-günü başına satış ÷ zincirinki): M1 (4+2)/2 = 3, M2 2/1 = 2, zincir 8/3
    -> r_M1 = 9/8, r_M2 = 3/4. Zincir hızı 4 / (9/8), M2'nin tahmini × 3/4 = 8/3.
    Pencerenin ilk günü Naif için zincirde de geçmiş yok: son yedek sonlu ve > 0."""
    df = birlestir(_seri("M1", "X-STD", range(60), 4), _seri("M1", "Y-STD", range(60), 2),
                   _seri("M2", "Y-STD", range(60), 2),
                   _seri("M2", "X-STD", range(60), 0, durum="bos"))
    hedef = df[(df["magaza_id"] == "M2") & (df["urun_id"] == "X-STD")]
    n, b = _iki(_gozlem(df), hedef)
    for s in (n, b):
        assert np.isfinite(s.to_numpy()).all() and (s.to_numpy() > 0).all()
    assert b.to_numpy() == pytest.approx(np.full(60, 8 / 3))
    assert n.iloc[30] == pytest.approx(8 / 3)
    assert n.iloc[0] == pytest.approx(2.0)          # M2'nin alt kategorideki SKU-gün hızı


def test_zincir_yedegi_option_hizina_gore():
    """X'i 10 mağazadan yalnız ikisi taşır (3/gün); ONL 20 option taşır (her biri
    1/gün, alt kategori satışının en büyük payı) ama X'i hiç stoklamaz. ONL'nin X
    tahmini option-günü başına hızdan gelir (≤ 3), satış payından değil (payla
    7,5 çıkıyordu): r_M0 = (8/6)/(76/72), r_ONL = 1/(76/72); tahmin 3 / r_M0 × r_ONL."""
    gun = range(60)
    parcalar = [_seri(f"M{i}", f"Y{j}-STD", gun, 1) for i in range(10) for j in range(5)]
    parcalar += [_seri(f"M{i}", "X-STD", gun, 3) for i in range(2)]
    parcalar += [_seri("ONL", f"Y{j}-STD", gun, 1) for j in range(20)]
    parcalar += [_seri("ONL", "X-STD", gun, 0, durum="bos")]
    df = birlestir(*parcalar)
    hedef = df[(df["magaza_id"] == "ONL") & (df["urun_id"] == "X-STD")]
    n, b = _iki(_gozlem(df), hedef)
    zincir = 76 / 72
    beklenen = 3 / ((8 / 6) / zincir) * (1 / zincir)
    assert b.to_numpy() == pytest.approx(np.full(60, beklenen))
    assert n.iloc[30] == pytest.approx(beklenen)
    assert (b.to_numpy() <= 3).all()


def test_naif_eski_kendi_gecmisine_bakar():
    """Hücre 0–29. günler 3/gün, sonra boş. 80. günün son 28 gününde ne hücre ne
    option stoklu; Naif zincire (M2'de 10/gün) atlamaz, kendi son 28 stoklu
    option-gününe bakar: 3."""
    df = birlestir(_seri("M1", "X-STD", range(30), 3),
                   _seri("M1", "X-STD", range(30, 100), 0, durum="bos"),
                   _seri("M2", "X-STD", range(100), 10))
    n, _ = _iki(_gozlem(df), _hedef(df, "M1", "X-STD", 80))
    assert n.iloc[0] == pytest.approx(3.0)


def test_tukenen_gun_havuza_girmez():
    """`gozlem`e `tukenen` (sansürlü) satır karışsa da sonuç değişmez."""
    df = birlestir(_seri("M1", "OPT-STD", range(30), 2),
                   _seri("M1", "OPT-STD", range(30, 33), 0, durum="bos"),
                   _seri("M1", "OPT-STD", range(33, 60), 6))
    kirli = birlestir(df, _seri("M1", "OPT-STD", [32], 100, durum="tukenen"))
    hedef = _hedef(df, "M1", "OPT-STD", 31)
    temiz = _iki(_gozlem(df), hedef)
    karisik = _iki(kirli, hedef)
    for a, b in zip(temiz, karisik):
        pd.testing.assert_series_equal(a, b)


def test_sonlu_olmayan_karakter_hata():
    df = _seri("M1", "OPT-STD", range(30), 2)
    df["oran"] = df["oran"].astype("float32")
    df.loc[5, "oran"] = np.nan
    with pytest.raises(ValueError, match="karakter"):
        talep.Basit(carpanlar=carpanlar.Carpanlar(esneklik_kampanya={"*": 1.0})).egit(df)


def test_magazada_olmayan_beden_payi_yeniden_olceklenir():
    """M1 yalnız S ve M taşır (payları 1/3, 2/3); L'yi hiç stoklamadı, zincir payını
    alır. M1'in S, M, L payları toplamı 1; S'nin tahmini (λ × pay) değişmez."""
    df = birlestir(_seri("M1", "OPT-S", range(40), 1), _seri("M1", "OPT-M", range(40), 2),
                   _seri("M2", "OPT-S", range(40), 1), _seri("M2", "OPT-M", range(40), 1),
                   _seri("M2", "OPT-L", range(40), 2),
                   _seri("M1", "OPT-L", range(40), 0, durum="bos"),
                   _seri("M1", "OPT-S", [40], 0, durum="bos"))
    b = talep.Basit(carpanlar=carpanlar.Carpanlar())
    b.egit(_gozlem(df))
    h = b._havuz
    satir = df[(df["magaza_id"] == "M1") & (df["tarih"] == BAS)]
    m, u, o, _, _ = h.k.hedef(satir)
    assert h.pay(m, u, o).sum() == pytest.approx(1.0)
    assert b.tahmin(_hedef(df, "M1", "OPT-S", 40)).iloc[0] == pytest.approx(1.0)


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


# --------------------------------------------------------------------- ML

def _ml_serisi(gun: int = 280, hafta_sonu: float = 20.0, hafta_ici: float = 10.0) -> pd.DataFrame:
    """İki mağaza × dört SKU, günlük satış hafta içi 10, cumartesi ve pazar 20."""
    gunler = np.arange(gun)
    satis = np.where(((BAS + pd.to_timedelta(gunler, unit="D")).dayofweek >= 5), hafta_sonu, hafta_ici)
    return birlestir(*[_seri(m, u, gunler, satis) for m in ("M1", "M2")
                       for u in ("A-S", "A-M", "B-S", "B-M")])


def test_ml_deterministik():
    df = _ml_serisi()
    hedef = df[df["tarih"] >= BAS + pd.Timedelta(days=250)]
    sonuc = []
    for _ in range(2):
        k = talep.ML(ornek=2000)
        k.egit(df)
        sonuc.append(k.tahmin(hedef))
    pd.testing.assert_series_equal(sonuc[0], sonuc[1])
    assert list(sonuc[0].index) == list(hedef.index)


def test_ml_hafta_sonunu_ogrenir():
    """Cumartesi 20, salı 10 satılan seride aynı hücrenin cumartesi tahmini salıdan yüksek."""
    df = _ml_serisi()
    k = talep.ML()
    k.egit(df)
    h = df[(df["magaza_id"] == "M1") & (df["urun_id"] == "A-S")]
    cumartesi = h[h["hafta_gunu"] == 5].iloc[20:25]
    sali = h[h["hafta_gunu"] == 1].iloc[20:25]
    c, s = k.tahmin(cumartesi), k.tahmin(sali)
    assert (c.to_numpy() > s.to_numpy()).all()
    assert c.mean() == pytest.approx(20, rel=0.15)
    assert s.mean() == pytest.approx(10, rel=0.15)


def test_ml_hepsi_sifir_satis_sifir_tahmin():
    """Eğitim satışlarının toplamı 0 ise (Poisson kurulamaz) model yok, tahmin 0."""
    df = _ml_serisi(gun=200, hafta_sonu=0, hafta_ici=0)
    k = talep.ML(ornek=1000)
    k.egit(df)
    assert k._model is None
    t = k.tahmin(df.iloc[:50])
    assert (t.to_numpy() == 0).all() and list(t.index) == list(df.index[:50])


def test_ml_negatif_tahmin_yok():
    """Eğitilmiş modelden bilinmeyen mağaza / SKU / şehir / line ve NaN özellikli satırlar da
    sonlu ve >= 0 tahmin alır."""
    df = _ml_serisi()
    k = talep.ML(ornek=3000)
    k.egit(df)
    assert k._model is not None
    yeni = _seri("M9", "Z-S", range(30), 0, durum="bos", sehir="Yeni", line="Yeni")
    yeni.loc[3, "markdown_orani"] = np.nan
    yeni.loc[4, "oran"] = np.nan
    t = k.tahmin(birlestir(df.iloc[:50], yeni))
    assert len(t) == 80
    assert np.isfinite(t.to_numpy()).all() and (t.to_numpy() >= 0).all()
    assert (t.to_numpy()[50:] > 0).all()           # model gerçekten çalıştı (sıfır dalı değil)


def test_ml_komsu_ozelligi_kendi_gununu_gormez():
    """Eğitim satırı kendi SKU-gününü görmez (100. günün 1000 satışı özellikte yok), ama aynı
    gün stoklu kardeş bedenin satışını görür (500): option penceresi 28 + 500 + 28 satış,
    28 + 29 gün; hücre penceresi hedef günü hariç tutar."""
    df = birlestir(_seri("M1", "A-S", range(200), 1), _seri("M1", "A-M", range(200), 1),
                   _seri("M2", "A-S", range(200), 1))
    gun100 = (df["tarih"] == BAS + pd.Timedelta(days=100)) & (df["urun_id"] == "A-S")
    df.loc[gun100 & (df["magaza_id"] == "M1"), "brut_satis"] = 1000
    df.loc[(df["tarih"] == BAS + pd.Timedelta(days=100)) & (df["urun_id"] == "A-M"), "brut_satis"] = 500
    k = talep.ML(ornek=10 ** 6)
    k.egit(df)
    satir = df[gun100 & (df["magaza_id"] == "M1")]
    x = k._matris(satir)
    assert x["komsu_hucre_satis"].iloc[0] == 28 and x["komsu_hucre_gun"].iloc[0] == 28
    assert x["komsu_opsiyon_satis"].iloc[0] == 28 + 500 + 28 and x["komsu_opsiyon_gun"].iloc[0] == 57
    assert x["opsiyon_hiz"].iloc[0] == pytest.approx(556 / 57)


def test_ml_tahmin_aninda_stoklu_kardesi_gorur():
    """Stoksuz (bos) hedef günde stoklu kardeş bedenin o günkü satışı (500) option özelliğine
    girer; hedefin kendisi havuzda olmadığından hiçbir şey düşülmez. Aynı satır `stoklu`
    olarak verilirse (geri test) kendi SKU-günü düşülür."""
    df = birlestir(_seri("M1", "A-S", [*range(100), *range(101, 200)], 1),
                   _seri("M1", "A-S", [100], 0, durum="bos"),
                   _seri("M1", "A-M", range(200), 1))
    df.loc[(df["tarih"] == BAS + pd.Timedelta(days=100)) & (df["urun_id"] == "A-M"), "brut_satis"] = 500
    k = talep.ML(ornek=10 ** 6)
    k.egit(_gozlem(df))
    hedef = df[(df["urun_id"] == "A-S") & (df["tarih"] == BAS + pd.Timedelta(days=100))]
    x = k._matris(hedef)
    assert x["komsu_opsiyon_satis"].iloc[0] == 28 + 500 + 28 and x["komsu_opsiyon_gun"].iloc[0] == 57
    assert x["komsu_hucre_satis"].iloc[0] == 28 and x["komsu_hucre_gun"].iloc[0] == 28
    # stoklu satır (A-S, 101. gün) havuzdadır: kendi SKU-günü düşer
    # A-S 29 günün 28'i stoklu, kendisi çıkınca 27; A-M 29 gün (28 + 500 satış)
    stoklu = df[(df["urun_id"] == "A-S") & (df["tarih"] == BAS + pd.Timedelta(days=101))]
    y = k._matris(stoklu)
    assert y["komsu_opsiyon_gun"].iloc[0] == 27 + 29
    assert y["komsu_opsiyon_satis"].iloc[0] == 27 + 28 + 500


def test_ml_yalniz_2023_2024_ogrenir_ve_tukeneni_havuza_almaz():
    """Model yalnız 2023–2024 satırlarıyla eğitilir (2025 satışı model girdisi olmaz) ve
    `tukenen` satır havuza girmez."""
    df = birlestir(_seri("M1", "A-S", range(30), 2), _seri("M1", "A-S", [40], 99, durum="tukenen"))
    k = talep.ML()
    k.egit(df)
    assert k._model.n_features_in_ == len(k._sutunlar)
    assert k._egitim_satir == 30
    ileri = df.iloc[:5].copy()
    ileri["tarih"] = pd.Timestamp("2025-03-01") + pd.to_timedelta(np.arange(5), unit="D")
    k2 = talep.ML()
    k2.egit(birlestir(df, ileri))
    assert k2._egitim_satir == 30
    with pytest.raises(ValueError, match="2023"):
        talep.ML().egit(ileri)


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
    for k in (talep.Naif(), talep.Basit(carpanlar=c), talep.ML(ornek=300_000)):
        k.egit(gozlem)
        t = k.tahmin(hedef)
        assert t.index.equals(hedef.index)
        assert np.isfinite(t.to_numpy()).all() and (t.to_numpy() >= 0).all()
        # stoksuz günün tahmini ortalaması stoklu günlerin ortalamasıyla aynı mertebede
        assert 0.1 < t.mean() / gozlem["brut_satis"].mean() < 10
