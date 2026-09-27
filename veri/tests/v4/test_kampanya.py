"""Testler: Görev 9 kampanya takvimi, gizli esneklik, günün fiyatı.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §5.2
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-9-brief.md
"""

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler
from perakende_veri.v4.kampanya import (
    esneklik,
    fiyat_carpani,
    gunun_fiyati,
    kampanya_orani,
    kampanya_takvimi,
    kampanyalari_uret,
)
from perakende_veri.v4.magaza import Olcek, magazalari_uret
from perakende_veri.v4.rastgele import dunya_akisi
from perakende_veri.v4.takvim import gun_indisi
from perakende_veri.v4.urun import urunleri_uret


@pytest.fixture(scope="module")
def k():
    """Tam mağaza tablosu (bölge çeşitliliği için) + küçük ölçekli option
    evreni (kategori/line çeşitliliği ölçekten bağımsız); kampanya kendi
    (dünyadan bağımsız) sabit tohumlu rng'siyle çekilir."""
    magazalar, gizli = magazalari_uret(dunya_akisi())
    urunler, optionlar = urunleri_uret(dunya_akisi(), Olcek.KUCUK)
    rng = np.random.default_rng(42)
    kampanya = kampanyalari_uret(rng, magazalar, optionlar)
    return {
        "magazalar": magazalar,
        "gizli": gizli,
        "optionlar": optionlar,
        "kampanya": kampanya,
    }


def test_kampanya_sayilari(k):
    """Tam yıllarda (2023-2025) yıl başına tam sayılar: 1 BF, 10 kategori,
    4 ikinci ürün. (2022 yarım yıldır, ayrı kurala tabi, burada kontrol
    edilmez.)"""
    kamp = k["kampanya"]
    for yil in (2023, 2024, 2025):
        yilki = kamp[kamp.baslangic.dt.year == yil]
        assert (yilki.tip == "black_friday").sum() == 1
        assert (yilki.tip == "kategori").sum() == 10
        assert (yilki.tip == "ikinci_urun").sum() == 4


def test_kampanya_2022_yarim_yil(k):
    """2022 (ısınmanın ikinci yarısı) yıllık sayının yarısını üretir."""
    kamp = k["kampanya"]
    yilki = kamp[kamp.baslangic.dt.year == 2022]
    assert (yilki.tip == "black_friday").sum() == 1
    assert (yilki.tip == "kategori").sum() == 5
    assert (yilki.tip == "ikinci_urun").sum() == 2


def test_black_friday_kapsam_ve_oran(k):
    kamp = k["kampanya"]
    bf = kamp[(kamp.tip == "black_friday") & (kamp.baslangic.dt.year == 2023)].iloc[0]
    assert bf.baslangic == pd.Timestamp(sabitler.BLACK_FRIDAY[1])
    assert (bf.bitis - bf.baslangic).days == 3  # 4 gün dahil (Cum..Pzt)
    assert bf.oran == pytest.approx(0.30)
    assert bf.kapsam_ust_kategori == ""
    assert bf.kapsam_line == ""
    assert bf.kapsam_bolge == ""


def test_indirim_toplanmaz():
    """Markdown ve kampanya toplanmaz, en yükseği geçerli olur."""
    b, o = gunun_fiyati(
        np.array([100.0]), np.array([0.3]), np.array([0.4]), np.array([True])
    )
    assert o[0] == pytest.approx(0.4)
    assert b[0] == pytest.approx(60.0)


def test_islem_indirimi_yalniz_tam_fiyatta():
    b, o = gunun_fiyati(
        np.array([100.0, 100.0]),
        np.array([0.0, 0.0]),
        np.array([0.0, 0.0]),
        np.array([True, False]),
    )
    assert o[0] == pytest.approx(sabitler.ISLEM_INDIRIM_ORANI)
    assert o[1] == 0.0
    assert b[0] == pytest.approx(70.0)
    assert b[1] == pytest.approx(100.0)


def test_fiyat_sinirlari():
    rng = np.random.default_rng(3)
    n = 500
    liste = rng.uniform(10, 2000, n)
    md = rng.choice([0.0, 0.2, 0.3, 0.4, 0.5, 0.7], n)
    kamp = rng.choice([0.0, 0.2, 0.3, 0.4], n)
    islem = rng.random(n) < 0.5
    birim, oran = gunun_fiyati(liste, md, kamp, islem)
    assert np.all(birim > 0)
    assert np.all(birim <= liste + 1e-9)
    assert np.all(oran >= 0)
    assert np.all(oran < 1)


def test_esneklik_gelirle_azalir(k):
    """Gelir arttıkça esneklik azalır (aynı üst kategori, outlet olmayan
    mağazalar arasında)."""
    gizli = k["gizli"]
    optionlar = k["optionlar"]
    eps = esneklik(gizli, optionlar)

    dusuk_idx = gizli.index[(gizli.gelir == "dusuk") & (gizli.segment != "outlet")]
    orta_idx = gizli.index[(gizli.gelir == "orta") & (gizli.segment != "outlet")]
    yuksek_idx = gizli.index[(gizli.gelir == "yuksek") & (gizli.segment != "outlet")]
    assert len(dusuk_idx) and len(orta_idx) and len(yuksek_idx)

    ortalama_dusuk = eps[dusuk_idx].mean()
    ortalama_orta = eps[orta_idx].mean()
    ortalama_yuksek = eps[yuksek_idx].mean()
    assert ortalama_dusuk > ortalama_orta > ortalama_yuksek


def test_esneklik_outlet_carpani(k):
    """Outlet segmenti, aynı gelir düzeyindeki diğer mağazalara göre daha
    esnek (× ESNEKLIK_OUTLET_CARPANI)."""
    gizli = k["gizli"]
    optionlar = k["optionlar"]
    eps = esneklik(gizli, optionlar)

    outlet_idx = gizli.index[gizli.segment == "outlet"]
    assert len(outlet_idx) > 0
    o = outlet_idx[0]
    beklenen_gelir_carpani = sabitler.ESNEKLIK_GELIR[gizli.loc[o, "gelir"]]
    ust0 = optionlar["ust_kategori"].iloc[0]
    beklenen = (
        sabitler.ESNEKLIK_UST[ust0]
        * beklenen_gelir_carpani
        * sabitler.ESNEKLIK_OUTLET_CARPANI
    )
    assert eps[o, 0] == pytest.approx(beklenen)


def test_fiyat_carpani_monoton():
    eps = np.array([1.5, 1.5, 1.5, 1.5])
    oran = np.array([0.0, 0.2, 0.4, 0.6])
    carpan = fiyat_carpani(oran, eps)
    assert np.all(np.diff(carpan) > 0)


def test_fiyat_carpani_sifir_oranda_bir():
    assert fiyat_carpani(np.array([0.0]), np.array([2.0]))[0] == pytest.approx(1.0)


def test_kampanya_talepten_bagimsiz(k):
    """Aynı tohum → aynı kampanya tablosu, aradan başka rng çekilişleri
    geçse de (kampanya kendi ayrı alt rng'sini kullanır)."""
    magazalar, optionlar = k["magazalar"], k["optionlar"]

    rng1 = np.random.default_rng(7)
    kamp1 = kampanyalari_uret(rng1, magazalar, optionlar)

    # Aradan başka (talebe benzer) bir akıştan bolca sayı tüketmek kampanya
    # tablosunu etkilememeli: kampanya kendi rng nesnesini alır.
    baska_akis = np.random.default_rng(999)
    baska_akis.integers(0, 100, size=5000)
    baska_akis.random(5000)

    rng2 = np.random.default_rng(7)
    kamp2 = kampanyalari_uret(rng2, magazalar, optionlar)

    pd.testing.assert_frame_equal(kamp1, kamp2)


def test_kampanya_orani_black_friday(k):
    """Black Friday günü, tüm hücrelerde (ONL dahil) oran = 0,30."""
    magazalar, optionlar, kamp = k["magazalar"], k["optionlar"], k["kampanya"]
    d = gun_indisi(sabitler.BLACK_FRIDAY[1])
    oran = kampanya_orani(kamp, d, magazalar, optionlar)
    assert oran.shape == (len(magazalar), len(optionlar))
    assert np.all(oran == pytest.approx(0.30))


def test_kampanya_orani_kampanyasiz_gun_sifir(k):
    """1 Ocak 2022 (ısınmadan önce, hiçbir kampanya yok) → tüm oranlar 0."""
    magazalar, optionlar, kamp = k["magazalar"], k["optionlar"], k["kampanya"]
    d = gun_indisi(sabitler.ISINMA_BASLANGIC)  # ısınmanın ilk günü, BF'den önce
    oran = kampanya_orani(kamp, d, magazalar, optionlar)
    assert np.all(oran == 0.0)


def test_kampanya_takvimi_tutarli(k):
    """`kampanya_takvimi`'nin döndürdüğü fonksiyon, `kampanya_orani` ile
    her gün için aynı sonucu vermeli (önbellek yalnız hız içindir)."""
    from perakende_veri.v4.takvim import D as GUN_SAYISI

    magazalar, optionlar, kamp = k["magazalar"], k["optionlar"], k["kampanya"]
    sorgula = kampanya_takvimi(kamp, magazalar, optionlar, GUN_SAYISI)

    for d in [0, gun_indisi(sabitler.BLACK_FRIDAY[1]), gun_indisi(sabitler.BLACK_FRIDAY[1]) + 2,
              gun_indisi(sabitler.BLACK_FRIDAY[1]) + 10, GUN_SAYISI - 1]:
        beklenen = kampanya_orani(kamp, d, magazalar, optionlar)
        np.testing.assert_array_equal(sorgula(d), beklenen)
