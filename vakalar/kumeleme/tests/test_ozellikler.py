"""`kumeleme.ozellikler`: karışım, beden, mevsim, çeşitten arındırma, ölçek; standartlama; kimlik.

Oyuncak testlerin bir kısmı `conftest`in 12 mağazalı fikstürünü, bir kısmı burada elle kurulan
küçük tabloları (`_mini`: iki mağaza, elle hesaplanabilir sayılar) kullanır. `veri` işaretli test
yayımlanan v4 verisini ister.
"""

import time
import tracemalloc

import numpy as np
import pandas as pd
import pytest
from conftest import KARAR, doldur, oyuncak_baglan

from kumeleme import kaynak, ozellikler as oz, sabitler

KUMELENIR = [f"M0{i}" for i in range(1, 9)]          # fikstürde kümelenen mağazalar (M09 yeni)
PAY_BLOKLARI = {"karisim", "beden", "mevsim", "karisim_stoklu", "beden_stoklu", "mevsim_stoklu"}

_URUN = [   # urun_id, option_id, line, sezon_kodu, dalga, lansman, cikis, ust, alt, segment, kalip, beden_seti, beden, sira
    ("C-BLZ-S", "O-BLZ", "Collection", "AW24", 1, "2024-09-02", None,
     "Üst Giyim", "Bluz", "giris", "slim", "Kadın Harf", "S", 2),
    ("C-BLZ-L", "O-BLZ", "Collection", "AW24", 1, "2024-09-02", None,
     "Üst Giyim", "Bluz", "giris", "slim", "Kadın Harf", "L", 4),
    ("C-JEN-38", "O-JEN", "Collection", "AW24", 1, "2024-09-02", None,
     "Alt Giyim", "Jean", "premium", "regular", "Kadın Numara", "38", 3),
    ("C-JEN-40", "O-JEN", "Collection", "AW24", 1, "2024-09-02", None,
     "Alt Giyim", "Jean", "premium", "regular", "Kadın Numara", "40", 4),
    ("C-KZK-M", "O-KZK", "Collection", "AW24", 1, "2024-09-02", None,
     "Üst Giyim", "Kazak", "orta", "oversize", "Kadın Harf", "M", 3),
    ("B-TSH-M", "O-TSH", "Basic", "DEVAMLI", 0, "2022-07-04", None,
     "Üst Giyim", "Tişört", "orta", "relaxed", "Kadın Harf", "M", 3),
    ("N-CNT", "O-CNT", "NOS", "DEVAMLI", 0, "2022-07-04", None,
     "Aksesuar", "Çanta", "orta", "regular", "Standart", "STD", 1),
    ("X-OUT", "O-OUT", "Outlet", "AW24", 1, "2024-09-02", None,
     "Üst Giyim", "Tişört", "giris", "slim", "Kadın Harf", "M", 3),
]
OCAK = pd.date_range("2025-01-06", periods=4, freq="7D")       # pencerenin son dört haftası


def _mini(tablolar, satis, stok=()):
    """Fikstürün mağaza tablosu + verilen satış/stok satırları ve `_URUN`."""
    t = {"magaza": tablolar["magaza"],
         "satis": doldur("satis", [(pd.Timestamp(d), m, u, a, 100.0 * a, 0.0, None)
                                   for d, m, u, a in satis]),
         "stok": doldur("stok", [(pd.Timestamp(d), m, u, 10, g) for d, m, u, g in stok])}
    return t, doldur("urun", _URUN)


def _oz(t, urun, aile, magazalar=("M01", "M02")):
    return oz.ozellik_tablosu(t, list(magazalar), urun, KARAR, aile)


def _fikstur(tablolar, aile):
    return oz.ozellik_tablosu(tablolar, KUMELENIR, tablolar["urun"], KARAR, aile)


def _alt_blok_paylari(Z):
    """Blok → {alt blok: o alt bloğun bloğun toplam varyansındaki payı}."""
    v = Z.var(ddof=0)
    alt = pd.Series([oz.alt_blok(c) for c in Z.columns], index=Z.columns)
    blok = pd.Series([c.split("/", 1)[0] for c in Z.columns], index=Z.columns)
    pay = {}
    for b in blok.unique():
        vb = v[blok == b]
        pay[b] = (vb.groupby(alt[blok == b]).sum() / vb.sum()).to_dict()
    return pay


def _pay_gruplari(X):
    """Payı bire toplanması gereken sütun grupları: son bileşen dışındaki ön ek."""
    gruplar: dict[str, list[str]] = {}
    for c in X.columns:
        if c.split("/", 1)[0] in PAY_BLOKLARI:
            gruplar.setdefault(c.rsplit("/", 1)[0], []).append(c)
    return gruplar


# ------------------------------------------------------------------ pencere ve aileler


def test_pencere_tamamlanmis_haftalar():
    assert oz.pencere(KARAR) == (pd.Timestamp("2023-02-06"), pd.Timestamp("2025-02-03"))
    # karar günü pazartesiyse o hafta tamamlanmadı: pencere bir önceki pazar biter
    assert oz.pencere(pd.Timestamp("2025-02-10")) == (pd.Timestamp("2023-02-13"), pd.Timestamp("2025-02-10"))
    assert oz.pencere(KARAR, hafta=1) == (pd.Timestamp("2025-01-27"), pd.Timestamp("2025-02-03"))
    assert sabitler.OZELLIK_HAFTA == 104


def test_aileler():
    assert oz.AILELER == {"S1": ("karisim",), "S2": ("karisim", "beden", "mevsim"),
                          "S4": ("karisim_stoklu", "beden_stoklu", "mevsim_stoklu"),
                          "S5": ("karisim", "beden", "mevsim", "olcek")}
    assert set(b for v in oz.AILELER.values() for b in v) == set(oz.BLOKLAR)


def test_bilinmeyen_aile_ve_satissiz_magaza(tablolar):
    with pytest.raises(ValueError, match="aile"):
        _fikstur(tablolar, "S3")
    with pytest.raises(ValueError, match="YOK"):           # pencerede satışı olmayan mağaza
        oz.ozellik_tablosu(tablolar, ["M01", "YOK"], tablolar["urun"], KARAR, "S1")
    with pytest.raises(ValueError):
        oz.ozellik_tablosu(tablolar, [], tablolar["urun"], KARAR, "S1")
    stoksuz = {ad: df for ad, df in tablolar.items() if ad != "stok"}
    with pytest.raises(KeyError, match="stok"):
        oz.ozellik_tablosu(stoksuz, KUMELENIR, tablolar["urun"], KARAR, "S4")
    assert not oz.ozellik_tablosu(stoksuz, KUMELENIR, tablolar["urun"], KARAR, "S5").empty


# ------------------------------------------------------------------ paylar


@pytest.mark.parametrize("aile", list(oz.AILELER))
def test_paylar_bire_toplanir(tablolar, aile):
    X = _fikstur(tablolar, aile)
    assert list(X.index) == KUMELENIR and X.index.name == "magaza_id"
    assert not X.isna().any().any()
    assert {c.split("/", 1)[0] for c in X.columns} == set(oz.AILELER[aile])
    gruplar = _pay_gruplari(X)
    assert gruplar                                                    # pay bloğu var
    for ad, cols in gruplar.items():
        np.testing.assert_allclose(X[cols].sum(axis=1), 1.0, rtol=0, atol=1e-12, err_msg=ad)
        assert (X[cols] >= 0).all().all()


def test_karisim_line_gruplari_ayri(tablolar):
    X = _fikstur(tablolar, "S1")
    assert {c.split("/")[1] for c in X.columns} == {"Collection", "Basic+NOS"}
    assert {c.split("/")[2] for c in X.columns} == {"alt_kategori", "fiyat_segmenti", "kalip"}
    # Basic+NOS grubu haftada genç profilde 3 Pantolon + 1 Çanta, aile profilinde 4 + 1: Çanta payı
    # genç mağazada 1/4, aile mağazasında 1/5 (iadeler düşülmez)
    c = "karisim/Basic+NOS/alt_kategori/Çanta"
    assert X.loc["M01", c] == pytest.approx(1 / 4) and X.loc["M05", c] == pytest.approx(1 / 5)


def test_iade_haric(tablolar):
    t, urun = _mini(tablolar, [
        ("2025-01-06", "M01", "C-BLZ-S", 5), ("2025-01-07", "M01", "C-BLZ-S", -3),   # iade düşülmez
        ("2025-01-06", "M01", "C-JEN-38", 5),
        ("2025-01-06", "M02", "C-BLZ-S", 1), ("2025-01-06", "M02", "C-JEN-38", 3),
        ("2025-01-06", "M01", "B-TSH-M", 2), ("2025-01-06", "M02", "B-TSH-M", 2),
    ])
    X = _oz(t, urun, "karisim")
    assert X.loc["M01", "karisim/Collection/alt_kategori/Bluz"] == pytest.approx(0.5)
    assert X.loc["M02", "karisim/Collection/alt_kategori/Jean"] == pytest.approx(0.75)


def test_mukerrer_tek_outlet_line_disarida(tablolar):
    satis = [("2025-01-06", "M01", "C-BLZ-S", 5), ("2025-01-06", "M01", "C-JEN-38", 5),
             ("2025-01-06", "M01", "C-JEN-38", 5),                                   # mükerrer satır
             ("2025-01-06", "M01", "X-OUT", 100),                                    # Outlet line
             ("2025-01-06", "M02", "C-BLZ-S", 1), ("2025-01-06", "M02", "C-JEN-38", 3),
             ("2025-01-06", "M01", "B-TSH-M", 2), ("2025-01-06", "M02", "B-TSH-M", 2)]
    t, urun = _mini(tablolar, satis)
    X = _oz(t, urun, "karisim")
    assert X.loc["M01", "karisim/Collection/alt_kategori/Jean"] == pytest.approx(0.5)
    assert not [c for c in X.columns if "Outlet" in c]
    assert X.loc["M01", "karisim/Collection/fiyat_segmenti/giris"] == pytest.approx(0.5)


def test_beden_seti_icinde(tablolar):
    """Beden eğrisi her beden setinin içindeki sıra payıdır; setlerin eğrileri eşit ağırlıkla
    ortalanır (mağazanın kadın/erkek ya da harf/numara karışımı eğriyi kaydırmaz). Tek bedenli set
    (Standart) eğri taşımaz."""
    t, urun = _mini(tablolar, [
        ("2025-01-06", "M01", "C-BLZ-S", 10), ("2025-01-06", "M01", "C-BLZ-L", 10),   # Kadın Harf 2 / 4
        ("2025-01-06", "M01", "C-JEN-38", 30),                                        # Kadın Numara 3
        ("2025-01-06", "M01", "N-CNT", 50),                                           # Standart: dışarıda
        ("2025-01-06", "M02", "C-BLZ-S", 5),
    ])
    X = _oz(t, urun, "beden")
    assert list(X.columns) == ["beden/2", "beden/3", "beden/4"]
    np.testing.assert_allclose(X.loc["M01"].to_numpy(), [0.25, 0.5, 0.25])
    np.testing.assert_allclose(X.loc["M02"].to_numpy(), [1.0, 0.0, 0.0])            # yalnız Kadın Harf


def test_mevsim_satisli_gun_basina(tablolar):
    """Mevsim payı ay başına satışlı gün başına satıştan kurulur: bir ayda daha çok gün satmak
    (açılış, tadilat, pencere kenarı) o ayın payını büyütmez."""
    satis = []
    for ay in pd.date_range("2024-02-01", "2025-01-01", freq="MS"):
        gun = 4 if ay.month == 3 else 2
        for m in ("M01", "M02"):
            satis += [(ay + pd.Timedelta(days=g), m, "C-BLZ-S", 1) for g in range(gun)]
    satis.append(("2024-07-01", "M02", "C-BLZ-L", 1))               # M02 Temmuz'un 1'inde 2 adet
    t, urun = _mini(tablolar, satis)
    X = _oz(t, urun, "mevsim")
    assert list(X.columns) == [f"mevsim/{a:02d}" for a in range(1, 13)]
    np.testing.assert_allclose(X.loc["M01"].to_numpy(), np.full(12, 1 / 12))
    assert X.loc["M02", "mevsim/07"] == pytest.approx(1.5 / 12.5)
    assert X.attrs["doldurulan"] == {"mevsim": 0}


def test_mevsim_eksik_ay_notr(tablolar):
    """Mağazanın satışlı günü olmayan ay (açılmadan önce) nötr doldurulur: mağazanın gözlenen
    aylardaki düzeyinde, mağazaların o ay için medyan hızı."""
    satis = []
    for ay in pd.date_range("2024-02-01", "2025-01-01", freq="MS"):
        for m in ("M01", "M02", "M03"):
            if m == "M02" and ay.month == 5:
                continue                                          # M02 Mayıs'ta hiç satmadı
            satis += [(ay, m, "C-BLZ-S", 2 if m == "M02" else 1)]
    t, urun = _mini(tablolar, satis)
    X = _oz(t, urun, "mevsim", ("M01", "M02", "M03"))
    np.testing.assert_allclose(X.loc["M02"].to_numpy(), np.full(12, 1 / 12))
    assert X.attrs["doldurulan"] == {"mevsim": 1}


# ------------------------------------------------------------------ çeşitten arındırma


def _cesit_satis_stok():
    satis, stok = [], []
    for j, d in enumerate(OCAK):
        foto = d + pd.Timedelta(days=7)
        for m in ("M01", "M02"):
            satis += [(d, m, "C-BLZ-S", 10), (d, m, "B-TSH-M", 1)]
            stok += [(foto, m, "C-BLZ-S", 7), (foto, m, "B-TSH-M", 7)]
        satis.append((d, "M01", "C-JEN-38", 10))
        stok.append((foto, "M01", "C-JEN-38", 7))
        if j == 0:                                     # M02 Jean'i yalnız ilk hafta taşır, hızlı satar
            satis.append((d, "M02", "C-JEN-38", 20))
            stok.append((foto, "M02", "C-JEN-38", 7))
    return satis, stok


def test_cesitten_arindirma_oyuncak(tablolar):
    """Çeşidi dar ama hızlı satan mağaza ham payda düşük, arındırılmışta yüksek."""
    t, urun = _mini(tablolar, *_cesit_satis_stok())
    ham = _oz(t, urun, "karisim")
    ari = _oz(t, urun, "karisim_stoklu")
    c = "alt_kategori/Jean"
    assert ham.loc["M01", f"karisim/Collection/{c}"] == pytest.approx(0.5)
    assert ham.loc["M02", f"karisim/Collection/{c}"] == pytest.approx(20 / 60)         # ham: düşük
    assert ari.loc["M01", f"karisim_stoklu/Collection/{c}"] == pytest.approx(0.5)
    assert ari.loc["M02", f"karisim_stoklu/Collection/{c}"] == pytest.approx(2 / 3)    # arındırılmış: yüksek
    assert ari.attrs["doldurulan"] == {"karisim_stoklu": 0}


def test_cesit_option_gunu_skularin_en_cogu(tablolar):
    """Option-gün = haftada option'ın SKU'larının en çok stoklu günü (SKU-günlerin toplamı değil)."""
    satis, stok = _cesit_satis_stok()
    stok = stok + [(d + pd.Timedelta(days=7), "M01", "C-JEN-40", 7) for d in OCAK]   # aynı option, ikinci SKU
    t, urun = _mini(tablolar, satis, stok)
    ari = _oz(t, urun, "karisim_stoklu")
    assert ari.loc["M01", "karisim_stoklu/Collection/alt_kategori/Jean"] == pytest.approx(0.5)


def test_hayalet_stok_haric_ve_notr_doldurma(tablolar):
    """Pencerede tek fotoğraflı, adetli ve hiç satmamış hücre hayalet stoktur (çeşit değil): o
    kategori o mağazada gözlenmemiş sayılır ve nötr doldurulur. İki fotoğraflı satışsız hücre gerçek
    stoktur: hız 0."""
    satis, stok = [], []
    for d in OCAK:
        foto = d + pd.Timedelta(days=7)
        for m in ("M01", "M02"):
            satis += [(d, m, "C-BLZ-S", 10), (d, m, "C-JEN-38", 10), (d, m, "B-TSH-M", 1)]
            stok += [(foto, m, "C-BLZ-S", 7), (foto, m, "C-JEN-38", 7), (foto, m, "B-TSH-M", 7)]
        satis.append((d, "M01", "C-KZK-M", 5))
        stok.append((foto, "M01", "C-KZK-M", 7))
    hayalet = stok + [(OCAK[1] + pd.Timedelta(days=7), "M02", "C-KZK-M", 7)]          # tek fotoğraf
    t, urun = _mini(tablolar, satis, hayalet)
    ari = _oz(t, urun, "karisim_stoklu")
    cols = [c for c in ari.columns if "/alt_kategori/" in c]
    np.testing.assert_allclose(ari.loc["M02", cols].to_numpy(), ari.loc["M01", cols].to_numpy())
    assert ari.attrs["doldurulan"]["karisim_stoklu"] == 3         # Kazak: alt kategori, segment, kalıp

    gercek = stok + [(OCAK[k] + pd.Timedelta(days=7), "M02", "C-KZK-M", 7) for k in (1, 2)]
    t, urun = _mini(tablolar, satis, gercek)
    ari = _oz(t, urun, "karisim_stoklu")
    assert ari.loc["M02", "karisim_stoklu/Collection/alt_kategori/Kazak"] == 0.0


# ------------------------------------------------------------------ ölçek, bağlantı, sızıntı


def test_olcek(tablolar):
    X = _fikstur(tablolar, "S5")
    o = [c for c in X.columns if c.startswith("olcek/")]
    assert o == ["olcek/log_gunluk_ciro", "olcek/log_kapasite", "olcek/log_metrekare"]
    m = tablolar["magaza"].set_index("magaza_id")
    s = tablolar["satis"]
    s = s[(s["tarih"] >= pd.Timestamp("2023-02-06")) & (s["tarih"] < pd.Timestamp("2025-02-03"))]
    for mid in ("M01", "M06"):
        sm = s[s["magaza_id"] == mid]
        gun = sm.loc[sm["adet"] > 0, "tarih"].dt.normalize().nunique()
        assert X.loc[mid, "olcek/log_gunluk_ciro"] == pytest.approx(np.log(sm["tutar"].sum() / gun))
        assert X.loc[mid, "olcek/log_metrekare"] == pytest.approx(np.log(m.loc[mid, "metrekare"]))
        assert X.loc[mid, "olcek/log_kapasite"] == pytest.approx(np.log(m.loc[mid, "kapasite"]))


def test_baglanti_ile_tablolar_ayni(tablolar):
    con = oyuncak_baglan(tablolar)
    try:
        for aile in oz.AILELER:
            pd.testing.assert_frame_equal(
                oz.ozellik_tablosu(con, KUMELENIR, tablolar["urun"], KARAR, aile), _fikstur(tablolar, aile))
        assert {r[0] for r in con.execute("select table_name from duckdb_tables() union all "
                                          "select view_name from duckdb_views() where not internal"
                                          ).fetchall()} == set(tablolar)       # geçici nesne kalmadı
    finally:
        con.close()


def test_ozellik_karar_sonrasini_gormez(tablolar):
    """Karar gününden sonraki satış ve stok satırlarını bozmak özellikleri değiştirmez."""
    temel = {a: _fikstur(tablolar, a) for a in oz.AILELER}
    bozuk = dict(tablolar)
    s = tablolar["satis"].copy()
    sonra = s["tarih"] >= KARAR
    assert sonra.any()
    s.loc[sonra, "adet"] *= 100
    s.loc[sonra, "tutar"] *= 100
    bozuk["satis"] = pd.concat([s, doldur("satis", [
        ("2025-03-03", "M01", "SKU-BAS-36", 500, 5000.0, 0.0, None),
        ("2025-02-07", "M02", "SKU-NOS-STD", 50, 500.0, 0.0, None)])], ignore_index=True)
    k = tablolar["stok"].copy()
    sonra = k["tarih"] > KARAR
    assert sonra.any()
    k.loc[sonra, "stoklu_gun"] = 0
    k.loc[sonra, "adet"] = 999
    bozuk["stok"] = pd.concat([k, doldur("stok", [("2025-02-10", "M01", "SKU-NOS-STD", 5, 7)])],
                              ignore_index=True)
    for aile, X in temel.items():
        pd.testing.assert_frame_equal(_fikstur(bozuk, aile), X)


def test_ozellik_pencere_kenarlari(tablolar):
    """Pencerenin başından önceki satış, `bas` günkü fotoğraf (pencere öncesi haftayı anlatır) ve
    karar haftasının karar gününden önceki günleri (2025-02-03 … 06; hafta tamamlanmadı) okunmaz."""
    temel = {a: _fikstur(tablolar, a) for a in oz.AILELER}
    bas, bit = oz.pencere(KARAR)
    assert (bas, bit) == (pd.Timestamp("2023-02-06"), pd.Timestamp("2025-02-03"))
    bozuk = dict(tablolar)
    s = tablolar["satis"].copy()
    karar_haftasi = (s["tarih"] >= bit) & (s["tarih"] < KARAR)
    assert karar_haftasi.any()                                     # fikstürde 2025-02-03 satırları var
    s.loc[karar_haftasi, "adet"] *= 100
    s.loc[karar_haftasi, "tutar"] *= 100
    ek = [(d, "M01", "SKU-BAS-36", 40, 400.0, 0.0, None)
          for d in ("2025-02-04", "2025-02-05", "2025-02-06", "2023-02-05", "2023-01-30")]
    bozuk["satis"] = pd.concat([s, doldur("satis", ek)], ignore_index=True)
    bozuk["stok"] = pd.concat([tablolar["stok"], doldur("stok", [
        (bas, m, sku, 10, 7) for m in KUMELENIR for sku in ("SKU-BAS-36", "SKU-NOS-STD")]
        + [(bas, "M02", "SKU-AW24", 3, 7)])], ignore_index=True)    # bas fotoğrafı: dışarıda
    for aile, X in temel.items():
        pd.testing.assert_frame_equal(_fikstur(bozuk, aile), X)
        assert _fikstur(bozuk, aile).attrs == X.attrs


def test_dusen_satis_sayilir(tablolar):
    """Stoklu günü 0 olan hücrenin satışı hıza girmez; alt blok başına `attrs["dusen_satis"]`."""
    # Kazak'ı hiç stoklamadan satan mağaza: satış düşer, kategori nötr doldurulur
    satis, stok = _cesit_satis_stok()
    satis = satis + [(OCAK[0], "M02", "C-KZK-M", 6), (OCAK[0], "M01", "C-KZK-M", 5)]
    stok = stok + [(OCAK[k] + pd.Timedelta(days=7), "M01", "C-KZK-M", 7) for k in (0, 1)]
    t, urun = _mini(tablolar, satis, stok)
    assert "dusen_satis" not in _oz(t, urun, "karisim").attrs
    ari = _oz(t, urun, "karisim_stoklu")
    d = ari.attrs["dusen_satis"]
    assert d["karisim_stoklu/Collection/alt_kategori"] == 6
    assert d["karisim_stoklu/Collection/kalip"] == d["karisim_stoklu/Collection/fiyat_segmenti"] == 6
    assert d["karisim_stoklu/Basic+NOS/alt_kategori"] == 0
    assert ari.attrs["doldurulan"]["karisim_stoklu"] == 3


# ------------------------------------------------------------------ standartlama


def test_standart_aile_agirligi_esit(tablolar):
    X = _fikstur(tablolar, "S5")
    X["beden/9"] = 0.25                                        # sabit sütun: bilgi taşımaz, düşer
    Z = oz.standartla(X, oz.AILELER["S5"])
    assert list(Z.index) == list(X.index)
    assert "beden/9" not in Z.columns
    assert set(Z.columns) < set(X.columns)
    for blok in oz.AILELER["S5"]:
        cols = [c for c in Z.columns if c.split("/", 1)[0] == blok]
        assert cols, blok
        v = Z[cols].var(ddof=0)
        assert v.sum() == pytest.approx(1.0), blok                 # her aile toplam varyansı 1
        np.testing.assert_allclose(Z[cols].mean(), 0.0, atol=1e-12)
    pay = _alt_blok_paylari(Z)
    assert len(pay["karisim"]) == 6                                # 2 line grubu × 3 nitelik
    np.testing.assert_allclose(list(pay["karisim"].values()), 1 / 6)
    assert pay["beden"] == {"beden": pytest.approx(1.0)} and pay["olcek"] == {"olcek": pytest.approx(1.0)}
    pd.testing.assert_frame_equal(oz.standartla(X, "S5"), Z)


def test_standart_alt_bloklar_esit_sutun_sayisindan_bagimsiz():
    """Karışımda alt bloklar (grup, nitelik) sütun sayısından bağımsız eşit varyans alır (R7);
    `agirlik="sutun"` ablasyonunda sütunlar eşittir, alt bloğun payı sütun sayısıyla orantılıdır."""
    rng = np.random.default_rng(1)
    cols = ([f"karisim/Collection/alt_kategori/{k}" for k in "abcd"]
            + [f"karisim/Collection/kalip/{k}" for k in "xy"]
            + [f"karisim/Basic+NOS/fiyat_segmenti/{k}" for k in "uvw"]
            + [f"mevsim/{a:02d}" for a in (1, 2, 3, 4, 5)])
    X = pd.DataFrame(rng.random((9, len(cols))), index=[f"M{i}" for i in range(9)], columns=cols)
    Z = oz.standartla(X, ("karisim", "mevsim"))
    pay = _alt_blok_paylari(Z)
    assert pay["karisim"] == pytest.approx({"karisim/Collection/alt_kategori": 1 / 3,
                                            "karisim/Collection/kalip": 1 / 3,
                                            "karisim/Basic+NOS/fiyat_segmenti": 1 / 3})
    for b in ("karisim", "mevsim"):
        assert Z[[c for c in Z.columns if c.startswith(b + "/")]].var(ddof=0).sum() == pytest.approx(1.0)
    S = oz.standartla(X, ("karisim", "mevsim"), agirlik="sutun")
    assert _alt_blok_paylari(S)["karisim"] == pytest.approx({"karisim/Collection/alt_kategori": 4 / 9,
                                                             "karisim/Collection/kalip": 2 / 9,
                                                             "karisim/Basic+NOS/fiyat_segmenti": 3 / 9})
    np.testing.assert_allclose(S[[c for c in S.columns if c.startswith("karisim/")]].var(ddof=0), 1 / 9)
    pd.testing.assert_frame_equal(S.filter(like="mevsim/"), Z.filter(like="mevsim/"))   # tek alt blok: aynı
    with pytest.raises(ValueError, match="ağırlık"):
        oz.standartla(X, ("karisim", "mevsim"), agirlik="esit")


def test_standart_hatalar(tablolar):
    X = _fikstur(tablolar, "S2")
    with pytest.raises(ValueError, match="olcek"):
        oz.standartla(X, oz.AILELER["S5"])                       # bloğun sütunu yok
    with pytest.raises(ValueError, match="mevsim"):
        oz.standartla(X, ("karisim", "beden"))                   # listelenmeyen bloğun sütunu
    Y = X.copy()
    Y.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        oz.standartla(Y, "S2")


# ------------------------------------------------------------------ kimlik


def test_kimlik_siradan_bagimsiz(tablolar):
    X = _fikstur(tablolar, "S2")
    k = oz.ozellik_kimligi(X)
    assert len(k) == 64 and k == oz.ozellik_kimligi(X.copy())
    rng = np.random.default_rng(0)
    karisik = X.iloc[rng.permutation(len(X)), rng.permutation(X.shape[1])]
    assert oz.ozellik_kimligi(karisik) == k
    assert oz.ozellik_kimligi(X + 1e-15) == k                  # toplama sırasının son bit gürültüsü
    Y = X.copy()
    Y.iloc[2, 3] += 1e-6
    assert oz.ozellik_kimligi(Y) != k
    assert oz.ozellik_kimligi(X.rename(columns={X.columns[0]: "x"})) != k
    assert oz.ozellik_kimligi(X.rename(index={"M01": "M99"})) != k
    assert oz.ozellik_kimligi(_fikstur(tablolar, "S1")) != k


# ------------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_ozellik_tablosu_ss25():
    """SS25 karar günü, 67 kümelenen mağaza: S1/S2/S4/S5 NaN'sız; boyut, süre, bellek kayda."""
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con, ("magaza", "magaza_olay", "urun"))
        satis = con.execute(
            "select distinct tarih::date::timestamp as tarih, magaza_id::varchar as magaza_id, "
            "1 as adet from satis where adet > 0 and tarih < ?", [sabitler.KARAR_GUNU]).df()
        k = kaynak.kapsam(t["magaza"], t["magaza_olay"], satis, sabitler.KARAR_GUNU)
        del satis
        ids = sorted(k.loc[k["kumelenir"], "magaza_id"])
        assert len(ids) == 67
        kayit = []
        for aile in ("S1", "S2", "S4", "S5"):
            tracemalloc.start()
            bas = time.perf_counter()
            X = oz.ozellik_tablosu(con, ids, t["urun"], sabitler.KARAR_GUNU, aile)
            sure = time.perf_counter() - bas
            tepe = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            assert list(X.index) == ids
            assert not X.isna().any().any(), aile
            assert np.isfinite(X.to_numpy()).all()
            for ad, cols in _pay_gruplari(X).items():
                np.testing.assert_allclose(X[cols].sum(axis=1), 1.0, atol=1e-12, err_msg=ad)
            Z = oz.standartla(X, aile)
            assert not Z.isna().any().any()
            for b, pay in _alt_blok_paylari(Z).items():
                np.testing.assert_allclose(list(pay.values()), 1 / len(pay), err_msg=b)
            kayit.append(f"{aile}: {X.shape[0]}x{X.shape[1]} (standart {Z.shape[1]}), {sure:.1f} s, "
                         f"Python tepe {tepe / 2**20:.0f} MB, doldurulan {X.attrs['doldurulan']}, "
                         f"düşen satış {X.attrs.get('dusen_satis', {})}, "
                         f"kimlik {oz.ozellik_kimligi(X)[:12]}")
    finally:
        con.close()
    print("\n" + "\n".join(kayit))
