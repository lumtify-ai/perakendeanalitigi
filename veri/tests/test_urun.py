import numpy as np
import pytest
from perakende_veri import sabitler
from perakende_veri.urun import urunleri_uret


@pytest.fixture(scope="module")
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


# --- Ürün hiyerarşisi ---------------------------------------------------

def test_option_model_ve_renk_kombinasyonudur(urunler):
    # Blok Transfer'in karar birimi option'dır: bir option = model × renk
    beklenen = sabitler.MODEL_SAYISI * len(sabitler.RENKLER)
    assert urunler["option_id"].nunique() == beklenen
    # Bir option içinde tek model, tek renk
    assert (urunler.groupby("option_id")["model_kodu"].nunique() == 1).all()
    assert (urunler.groupby("option_id")["renk"].nunique() == 1).all()


def test_her_option_tam_beden_setine_sahip(urunler):
    assert (urunler.groupby("option_id")["beden"].nunique() == len(sabitler.BEDENLER)).all()


def test_beden_sirasi_kirikliK_tespiti_icin_var(urunler):
    # "Ara bedenler tükenmiş" tespiti sıralama olmadan yapılamaz
    sira = urunler.drop_duplicates("beden").set_index("beden")["beden_sira"].to_dict()
    assert sira == {"XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5}


def test_hiyerarsi_kolonlari_dolu(urunler):
    hiyerarsi = [
        "cinsiyet", "ana_kategori", "alt_kategori", "line",
        "mevsimsellik", "uretici", "sezon_grup", "koleksiyon",
    ]
    for kolon in hiyerarsi:
        assert kolon in urunler.columns, kolon
        assert urunler[kolon].notna().all(), kolon
        assert (urunler[kolon].astype(str).str.len() > 0).all(), kolon


def test_hiyerarsi_model_duzeyinde_sabit(urunler):
    # Hiyerarşi ürünün kimliğidir; beden/renk değiştirse de değişmez
    for kolon in ["cinsiyet", "ana_kategori", "alt_kategori", "line", "mevsimsellik", "uretici"]:
        assert (urunler.groupby("model_kodu")[kolon].nunique() == 1).all(), kolon


def test_alt_kategori_ana_kategoriye_bagli(urunler):
    # Bir alt kategori tek bir ana kategoriye aittir — hiyerarşi ağaçtır, grafik değil
    assert (urunler.groupby("alt_kategori")["ana_kategori"].nunique() == 1).all()


def test_iki_sezon_grubu_var(urunler):
    assert set(urunler["sezon_grup"]) == {"S1", "S2"}


def test_hem_sezonluk_hem_devamli_urun_var(urunler):
    # Devamlı (NOS) ürünler yıl boyu satar; sezonluk olanlar sezonuyla gelir gider.
    # Transfer kararı ikisinde farklı işler.
    assert set(urunler["mevsimsellik"]) == {"Sezonluk", "Devamlı"}


def test_tekrar_uretilebilir():
    a = urunleri_uret(np.random.default_rng(sabitler.TOHUM))
    b = urunleri_uret(np.random.default_rng(sabitler.TOHUM))
    assert a.equals(b)
