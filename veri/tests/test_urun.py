import numpy as np
import pytest
from perakende_veri import sabitler
from perakende_veri.urun import urunleri_uret


@pytest.fixture
def urunler():
    return urunleri_uret(np.random.default_rng(sabitler.TOHUM))


def test_sku_sayisi(urunler):
    beklenen = sabitler.MODEL_SAYISI * len(sabitler.RENKLER) * len(sabitler.BEDENLER)
    assert len(urunler) == beklenen


def test_her_model_tam_beden_setine_sahip(urunler):
    beden_sayilari = urunler.groupby(["model_kodu", "renk"])["beden"].nunique()
    assert (beden_sayilari == len(sabitler.BEDENLER)).all()


def test_ayni_model_ayni_fiyat(urunler):
    # Beden ve renk fiyatı değiştirmez; transfer analizinde bu varsayım kritik
    fiyat_cesitliligi = urunler.groupby("model_kodu")["liste_fiyati"].nunique()
    assert (fiyat_cesitliligi == 1).all()


def test_liste_fiyati_alis_fiyatindan_yuksek(urunler):
    assert (urunler["liste_fiyati"] > urunler["alis_fiyati"]).all()


def test_iki_koleksiyon_var(urunler):
    assert urunler["koleksiyon"].nunique() == 2
