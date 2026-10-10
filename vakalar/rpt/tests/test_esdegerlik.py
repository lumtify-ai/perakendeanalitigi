"""Kilit: oyunun koşuları gerçeklikle bağlı ve kollar arası fark yalnız kararlardan.

`veri` işaretli: yol 0'ın hazırlığı ve koşuları (`oyun.hazirlik(0)`; önbellekten,
yoksa ~25 dk + koşu başına ~4 dk; sonuçlar `cikti/kosular/`'da kalır).

* Hazırlık koşusu, yayımlanan v4'ü üreten koşunun ta kendisidir (aynı anahtar;
  yayımlananla eşitliği `test_motor.py::test_mevcut_kol_yayimlanan_tablolarla_ayni`).
* Sarmalayıcılar motoru bozmaz: `mevcut` kolu (Lumoda'nın RPT'sini sarar) +
  dağıtım kuralı a (Lumoda'nın replenishment'ını sarar) = hazırlık koşusu.
* RPT yokken dağıtım kuralı etkisiz (KÜÇÜK'te her kural `test_dagitim.py`'de;
  burada TAM'da en karmaşığı, d).
* Kollar arası gürültü yok: aynı tohumda rpt_yok iki kez koşulunca birebir aynı;
  oyun sezonunun ilk lansmanından önce bütün kollar aynı.
"""

import numpy as np
import pandas as pd
import pytest

from rpt import motor, oyun

BUYUK = ("satis", "sevkiyat", "depo_stok", "stok", "siparis", "fiyat")


@pytest.fixture(scope="module")
def yol0():
    if not motor.VERI_YOLU.exists():
        pytest.skip("v4 verisi yok")
    return oyun.hazirlik(0)


def _ayni(a, b, tablolar=BUYUK, gercek=True):
    for ad in tablolar:
        pd.testing.assert_frame_equal(a.tablo(ad), b.tablo(ad), obj=ad)
    if gercek:
        pd.testing.assert_frame_equal(a.tablo("gercek"), b.tablo("gercek"), obj="gercek")


@pytest.mark.veri
def test_hazirlik_kosusu_yayimlanan_dunya(yol0):
    k = motor.kos(ad="lumoda", parametreler={}, tembel=True)
    assert yol0.kosu.meta["anahtar"] == k.meta["anahtar"]
    assert yol0.talep_tohumu is None and yol0.kosu.meta["talep_tohumu"] is None


@pytest.mark.veri
def test_sarmalayicilar_motoru_bozmaz(yol0):
    """Mevcut kolu + kural a (iki sarmalayıcı, kendi önbellek anahtarıyla) =
    Lumoda'nın varsayılan koşusu: bütün tablolar ve gizli gerçek birebir."""
    k = oyun.kos(yol0, "mevcut", "a")
    assert k.meta["anahtar"] != yol0.kosu.meta["anahtar"]
    _ayni(k, yol0.kosu, tablolar=sorted(k.meta["tablolar"]))
    assert len(k.kayitlar["rpt"]) > 50          # oyun option'larına Banu'nun RPT'leri


@pytest.mark.veri
@pytest.mark.parametrize("kural", ["d"])
def test_kural_rptsiz_kolda_etkisiz(yol0, kural):
    """Kurallar yalnız RPT'si gelmiş oyun option'ına dokunur: rpt_yok'ta fark yok."""
    _ayni(oyun.kos(yol0, "rpt_yok", kural), oyun.kos(yol0, "rpt_yok", "a"))


@pytest.mark.veri
def test_ayni_tohum_ayni_kosu(yol0):
    """Aynı tohumda rpt_yok iki kez (önbelleksiz ikinci koşu) birebir aynı."""
    a = oyun.kos(yol0, "rpt_yok", "a")
    b = motor.kos(rpt=oyun.kol_politikasi(yol0, "rpt_yok"),
                  replenishment=oyun.dagitim_politikasi(yol0, "a"), ad="ikinci", parametreler={},
                  onbellek=None)
    for ad in BUYUK:
        pd.testing.assert_frame_equal(a.tablo(ad), b.tablo(ad), obj=ad)
    pd.testing.assert_frame_equal(a.tablo("gercek"), b.tablo("gercek"), obj="gercek")


@pytest.mark.veri
def test_oyundan_once_kollar_ayni(yol0):
    """Oyunun ilk lansmanından önce (AW24) öneri kolu ve rpt_yok birebir aynı satış,
    stok ve talebi görür: operasyon ve müşteri rastgeleliği politikadan bağımsız."""
    opt = yol0.ogrenilen.optionlar
    sinir = pd.Timestamp(opt.loc[opt["sezon_kodu"] == oyun.OYUN[0], "lansman_tarihi"].min())
    a = oyun.kos(yol0, "rpt_yok", "a")
    b = oyun.kos(yol0, "oneri", "a")
    for ad in ("satis", "stok", "gercek"):
        x, y = a.tablo(ad), b.tablo(ad)
        x = x[pd.to_datetime(x["tarih"]) < sinir].reset_index(drop=True)
        y = y[pd.to_datetime(y["tarih"]) < sinir].reset_index(drop=True)
        assert len(x) > 1_000_000
        pd.testing.assert_frame_equal(x, y, obj=ad)
    # ...ve oyunda fark yaratır (öneri RPT verir)
    assert len(b.kayitlar["rpt"]) > 0
    assert not np.array_equal(a.tablo("siparis")["adet"].to_numpy(), b.tablo("siparis")["adet"].to_numpy())
