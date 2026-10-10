"""Testler: `dunya_kur(..., ilk_alim_orani=..., ilk_alim_sezonu=...)`
(Depodan Mağazaya v4, Görev 1).

Brief: .superpowers/sdd/2026-10-10-dm-v4/task-1-brief.md

`ilk_alim_orani=1.0` (varsayılan) bugünkü davranıştır: yayımlanan v4 bu
yolla üretilmiştir. Bir oran verilirse yalnız `ilk_alim_sezonu`'ndaki
sezonluk option'ların **talep tahmini** o oranla çarpılır; MOQ tabanı,
`YUVARLAMA_ADET` yuvarlaması ve tedarikçi kapasitesi bundan sonra işler.
Dünyanın geri kalanı (ürünler, mağazalar, beklenen talep, sürprizler)
oranla değişmez.

Hızlı testler KUCUK dünyada; tam karşılaştırma (`yavas`, `veri`) TAM
dünyayı yayımlanan yolla yeniden üretir ve 18 tabloyu `cikti/v4/parquet`
ile karşılaştırır (~5 dk, ~6-10 GB).
"""

import io

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler
from perakende_veri.v4.dunya import dunya_kur
from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.motor import simule_et

SEZON = "AW25"
ORAN = 0.5


def _esit(a, b, ad: str = "") -> None:
    """İki değer birebir aynı (DataFrame, dizi, sözlük, liste ya da skaler)."""
    if isinstance(a, pd.DataFrame):
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), obj=ad)
    elif isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b, err_msg=ad)
        assert a.dtype == b.dtype, ad
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), ad
        for k in a:
            _esit(a[k], b[k], f"{ad}.{k}")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), ad
        for i, (x, y) in enumerate(zip(a, b)):
            _esit(x, y, f"{ad}[{i}]")
    else:
        assert a == b, ad


@pytest.fixture(scope="module")
def yarim():
    return dunya_kur(Olcek.KUCUK, ilk_alim_orani=ORAN)


def _secili(w) -> np.ndarray:
    """[O] bool: ilk alım sezonunun sezonluk option'ları."""
    o = w.optionlar
    return ((o["sezon_kodu"] == SEZON) & (o["sezon_kodu"] != sabitler.DEVAMLI)).to_numpy()


# ---------------------------------------------------------------------------
# Varsayılan = bugünkü davranış
# ---------------------------------------------------------------------------


def test_varsayilan_oran_ayni_dunya(kucuk_dunya):
    """Parametresiz dünya ile `ilk_alim_orani=1.0` dünyası: ilk alım, ilk
    siparişler (sapma, hatalı adet çekilişleri dahil), option ve ürün
    tabloları birebir aynı."""
    acik = dunya_kur(Olcek.KUCUK, ilk_alim_orani=1.0)
    w = kucuk_dunya
    _esit(w.ilk_alim, acik.ilk_alim, "ilk_alim")
    _esit(w.ilk_siparisler, acik.ilk_siparisler, "ilk_siparisler")
    _esit(w.optionlar, acik.optionlar, "optionlar")
    _esit(w.urunler, acik.urunler, "urunler")
    assert w.ilk_alim[_secili(w)].sum() > 0


# ---------------------------------------------------------------------------
# Oran yalnız seçili sezonu değiştirir
# ---------------------------------------------------------------------------


def test_oran_yalniz_secili_sezonu_degistirir(kucuk_dunya, yarim):
    w, y = kucuk_dunya, yarim
    sec = _secili(w)
    assert sec.sum() > 0

    # Seçili sezon: hiçbiri artmaz, çoğu küçülür (kalanlar MOQ tabanında).
    assert (y.ilk_alim[sec] <= w.ilk_alim[sec]).all()
    assert (y.ilk_alim[sec] < w.ilk_alim[sec]).sum() > 0
    assert y.ilk_alim[sec].sum() < w.ilk_alim[sec].sum()

    # Öteki sezonların ilk alımı, ürünler, option'lar ve beklenen talep aynı.
    np.testing.assert_array_equal(y.ilk_alim[~sec], w.ilk_alim[~sec])
    _esit(w.urunler, y.urunler, "urunler")
    _esit(w.optionlar, y.optionlar, "optionlar")
    _esit(w.magazalar, y.magazalar, "magazalar")
    for d in (0, 50, 200, 400):
        np.testing.assert_array_equal(w.lam.gun(d), y.lam.gun(d), err_msg=f"lam gün {d}")

    # İlk siparişler: öteki sezonların siparişi aynı (sapma ve hatalı çekilişi
    # AW25'in sırasını bozmaz), seçili sezonun siparişi küçülür.
    assert len(w.ilk_siparisler) == len(y.ilk_siparisler)
    for a, b in zip(w.ilk_siparisler, y.ilk_siparisler):
        assert a["option"] == b["option"]
        if not sec[a["option"]]:
            _esit(a, b, f"siparis option {a['option']}")
        else:
            assert b["adetler"].sum() <= a["adetler"].sum()


def test_oran_ilk_alimla_ilk_siparisler_tutarli(yarim):
    """İlk siparişlerin adetleri ilk alımın SKU'lara bölüşümüdür."""
    y = yarim
    for s in y.ilk_siparisler:
        assert s["adetler"].sum() == y.ilk_alim[s["option"]]


def test_oran_deterministik(yarim):
    ikinci = dunya_kur(Olcek.KUCUK, ilk_alim_orani=ORAN)
    _esit(yarim.ilk_alim, ikinci.ilk_alim, "ilk_alim")
    _esit(yarim.ilk_siparisler, ikinci.ilk_siparisler, "ilk_siparisler")


def test_baska_sezon_secilebilir(kucuk_dunya):
    """`ilk_alim_sezonu`: oran yalnız o sezona uygulanır."""
    w = kucuk_dunya
    d = dunya_kur(Olcek.KUCUK, ilk_alim_orani=ORAN, ilk_alim_sezonu="AW24")
    o = w.optionlar["sezon_kodu"].to_numpy()
    aw24 = o == "AW24"
    assert (d.ilk_alim[aw24] < w.ilk_alim[aw24]).sum() > 0
    np.testing.assert_array_equal(d.ilk_alim[~aw24], w.ilk_alim[~aw24])


# ---------------------------------------------------------------------------
# MOQ tabanı
# ---------------------------------------------------------------------------


def test_dusuk_oranda_moq_tabani():
    """Çok düşük oranda seçili sezonun her option'ı tedarikçisinin MOQ'sunda
    kalır (MOQ'nun altına inilmez), 10'un katıdır."""
    w = dunya_kur(Olcek.KUCUK, ilk_alim_orani=0.01)
    sec = _secili(w)
    mense = w.gizli_tedarikci["mense"].to_numpy()
    ted = w.optionlar["tedarikci_id"].map(
        {t: i for i, t in enumerate(w.tedarikciler["tedarikci_id"])}
    ).to_numpy()
    moq = np.array([sabitler.MENSE_V4[m]["moq"] for m in mense[ted]])
    assert (w.ilk_alim[sec] >= moq[sec]).all()
    assert (w.ilk_alim[sec] == moq[sec]).all()  # %1: hepsi tabanda
    assert (w.ilk_alim[sec] % sabitler.YUVARLAMA_ADET == 0).all()


def test_oran_tedarikciyi_degistirmez(kucuk_dunya, yarim):
    """Oran yalnız adedi değiştirir: tedarikçi atamasi, maliyet (urunler) ve
    ilk siparişlerin tedarikçi/teslim günleri aynı (KUCUK)."""
    _esit(kucuk_dunya.optionlar, yarim.optionlar, "optionlar")
    _esit(kucuk_dunya.urunler, yarim.urunler, "urunler")
    for a, b in zip(kucuk_dunya.ilk_siparisler, yarim.ilk_siparisler):
        for k in ("tedarikci", "siparis_gun", "planlanan_gun", "gerceklesen_gun"):
            assert a[k] == b[k], k


@pytest.mark.yavas
def test_tam_olcekte_tedarikci_alim_duzeyinden_bagimsiz():
    """TAM dünyada 0,4 ve 1,0 alım düzeyi aynı tedarikçi atamasını, maliyeti
    ve teslim sürelerini verir (`ted_idx` = ilk siparişlerin `tedarikci`'si
    ve `optionlar.tedarikci_id`); yalnız adet değişir. Yalnız dünya kurulur,
    simülasyon yok."""
    w1 = dunya_kur(Olcek.TAM)
    w4 = dunya_kur(Olcek.TAM, ilk_alim_orani=0.4)
    _esit(w1.optionlar, w4.optionlar, "optionlar")
    _esit(w1.urunler, w4.urunler, "urunler")
    assert len(w1.ilk_siparisler) == len(w4.ilk_siparisler) > 0
    for a, b in zip(w1.ilk_siparisler, w4.ilk_siparisler):
        for k in ("option", "tedarikci", "siparis_gun", "planlanan_gun", "gerceklesen_gun"):
            assert a[k] == b[k], k
    sec = _secili(w1)
    assert (w4.ilk_alim[sec] <= w1.ilk_alim[sec]).all()
    assert w4.ilk_alim[sec].sum() < w1.ilk_alim[sec].sum()
    np.testing.assert_array_equal(w4.ilk_alim[~sec], w1.ilk_alim[~sec])


def test_gecersiz_oran():
    for kotu in (0.0, -0.5):
        with pytest.raises(ValueError):
            dunya_kur(Olcek.KUCUK, ilk_alim_orani=kotu)


# ---------------------------------------------------------------------------
# Tam karşılaştırma: varsayılan yol yayımlanan v4'ü yeniden üretir
# ---------------------------------------------------------------------------


def _parquet_turu(df: pd.DataFrame) -> pd.DataFrame:
    """Yayımlama yolundaki Parquet gidiş-dönüşü (`disa_aktar.yaz`:
    `to_parquet(index=False)`), bellekte."""
    tampon = io.BytesIO()
    df.to_parquet(tampon, index=False)
    tampon.seek(0)
    return pd.read_parquet(tampon)


@pytest.mark.yavas
@pytest.mark.veri
def test_tam_kosu_yayimlanan_v4_ile_ayni():
    """`ilk_alim_orani=1.0` ile açıkça kurulan TAM dünya, `simule_et` ve
    `yayimla` yayımlanan 18 tabloyu birebir verir (Parquet gidiş-dönüşünden
    sonra `cikti/v4/parquet/<tablo>.parquet` ile aynı: değer, tür, sıra)."""
    from perakende_veri.v4.uret import yayimla

    parquet = sabitler.CIKTI_DIZINI / "parquet"
    if not parquet.exists():
        pytest.skip("yayımlanan v4 yok (python -m perakende_veri.v4.uret)")

    dunya = dunya_kur(Olcek.TAM, ilk_alim_orani=1.0)
    ham = simule_et(dunya)
    tablolar = yayimla(dunya, ham)
    del ham

    yayimlanan = sorted(p.stem for p in parquet.glob("*.parquet"))
    assert sorted(tablolar) == yayimlanan
    assert len(yayimlanan) == 18
    for ad in yayimlanan:
        pd.testing.assert_frame_equal(
            _parquet_turu(tablolar[ad]), pd.read_parquet(parquet / f"{ad}.parquet"), obj=ad,
        )
