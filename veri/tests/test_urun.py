import numpy as np
import pytest
from perakende_veri import sabitler
from perakende_veri.urun import urunleri_uret


@pytest.fixture(scope="module")
def urunler():
    return urunleri_uret(np.random.default_rng(sabitler.TOHUM))


# --- Ölçek --------------------------------------------------------------

def test_sku_sayisi(urunler):
    beklenen = (
        sabitler.MODEL_SAYISI
        * len(sabitler.RENKLER)
        * sabitler.BEDEN_KADEME_SAYISI
    )
    assert len(urunler) == beklenen


def test_model_option_sku_sayilari(urunler):
    assert urunler["model_kodu"].nunique() == sabitler.MODEL_SAYISI
    assert urunler["option_id"].nunique() == sabitler.MODEL_SAYISI * len(sabitler.RENKLER)
    assert urunler["urun_id"].is_unique


# --- Kimlik biçimi ------------------------------------------------------

def test_sku_kimligi_okunabilir(urunler):
    """SKU = ürün kodu - renk kodu - beden.

    Kimliğin kendisi okunabilir olmalı: bir rapor satırına bakan kişi
    hangi model, hangi renk, hangi beden olduğunu id'den görebilmeli.
    """
    satir = urunler.iloc[0]
    assert satir["urun_id"] == f"{satir['model_kodu']}-{satir['renk_kodu']}-{satir['beden']}"
    assert satir["option_id"] == f"{satir['model_kodu']}-{satir['renk_kodu']}"


def test_option_model_ve_renk_kombinasyonudur(urunler):
    # Blok Transfer'in karar birimi option'dır
    assert (urunler.groupby("option_id")["model_kodu"].nunique() == 1).all()
    assert (urunler.groupby("option_id")["renk"].nunique() == 1).all()


def test_modelin_kodu_ve_adi_vardir(urunler):
    assert (urunler["model_adi"].str.len() > 0).all()
    # Bir model kodunun tek bir adı olur
    assert (urunler.groupby("model_kodu")["model_adi"].nunique() == 1).all()


# --- Hiyerarşi ----------------------------------------------------------

def test_hiyerarsi_kolonlari_dolu(urunler):
    for kolon in ["cinsiyet", "ust_kategori", "alt_kategori", "line", "uretici"]:
        assert kolon in urunler.columns, kolon
        assert urunler[kolon].notna().all(), kolon


def test_hiyerarsi_model_duzeyinde_sabit(urunler):
    # Hiyerarşi ürünün kimliğidir; renk ve beden değişse de değişmez
    for kolon in ["cinsiyet", "ust_kategori", "alt_kategori", "line", "uretici"]:
        assert (urunler.groupby("model_kodu")[kolon].nunique() == 1).all(), kolon


def test_alt_kategori_tek_ust_kategoriye_bagli(urunler):
    # Hiyerarşi bir ağaçtır, grafik değil
    assert (urunler.groupby("alt_kategori")["ust_kategori"].nunique() == 1).all()


def test_dort_line_da_var(urunler):
    assert set(urunler["line"]) == set(sabitler.LINELER)


def test_sezon_kolonu_yok(urunler):
    # Sezon grup / koleksiyon kırılımı bu örneklerde gerekmiyor;
    # mevsimsellik bilgisini line taşır
    for kolon in ["sezon_grup", "koleksiyon", "mevsimsellik"]:
        assert kolon not in urunler.columns, kolon


# --- Beden setleri ------------------------------------------------------

def test_her_model_tam_beden_setine_sahip(urunler):
    beden_sayilari = urunler.groupby("option_id")["beden"].nunique()
    assert (beden_sayilari == sabitler.BEDEN_KADEME_SAYISI).all()


def test_beden_seti_cinsiyet_ve_kategoriye_gore_degisir(urunler):
    """Tişört S/M/L gider, pantolon 32/34 gider; kadın ve erkek farklıdır."""
    kadin_ust = set(
        urunler.loc[
            (urunler["cinsiyet"] == "Kadın") & (urunler["ust_kategori"] == "Üst Giyim"),
            "beden",
        ]
    )
    kadin_alt = set(
        urunler.loc[
            (urunler["cinsiyet"] == "Kadın") & (urunler["ust_kategori"] == "Alt Giyim"),
            "beden",
        ]
    )
    erkek_ust = set(
        urunler.loc[
            (urunler["cinsiyet"] == "Erkek") & (urunler["ust_kategori"] == "Üst Giyim"),
            "beden",
        ]
    )
    assert kadin_ust == {"XS", "S", "M", "L", "XL"}
    assert kadin_alt == {"34", "36", "38", "40", "42"}
    assert erkek_ust == {"S", "M", "L", "XL", "XXL"}
    assert kadin_ust != erkek_ust


def test_beden_sira_set_icinde_artar(urunler):
    """Kırıklık analizi beden etiketine değil sıraya bakar."""
    assert set(urunler["beden_sira"]) == {1, 2, 3, 4, 5}
    for _, grup in urunler.groupby("beden_seti"):
        sirali = grup.drop_duplicates("beden").sort_values("beden_sira")
        # Numara setlerinde etiket de artan olmalı
        if sirali["beden"].str.isdigit().all():
            sayilar = sirali["beden"].astype(int).tolist()
            assert sayilar == sorted(sayilar)


def test_beden_seti_adi_kayitli(urunler):
    assert (urunler["beden_seti"].str.len() > 0).all()
    assert (urunler.groupby("option_id")["beden_seti"].nunique() == 1).all()


# --- Fiyat --------------------------------------------------------------

def test_ayni_model_ayni_fiyat(urunler):
    # Beden ve renk fiyatı değiştirmez; transfer analizinde bu varsayım kritik
    assert (urunler.groupby("model_kodu")["liste_fiyati"].nunique() == 1).all()


def test_liste_fiyati_alis_fiyatindan_yuksek(urunler):
    assert (urunler["liste_fiyati"] > urunler["alis_fiyati"]).all()


def test_marka_lumoda(urunler):
    assert set(urunler["marka"]) == {"Lumoda"}


# --- Tekrar üretilebilirlik --------------------------------------------

def test_tekrar_uretilebilir():
    a = urunleri_uret(np.random.default_rng(sabitler.TOHUM))
    b = urunleri_uret(np.random.default_rng(sabitler.TOHUM))
    assert a.equals(b)
