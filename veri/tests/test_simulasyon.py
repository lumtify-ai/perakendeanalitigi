import numpy as np
import pandas as pd
import pytest
from perakende_veri import sabitler
from perakende_veri.magaza import magazalari_uret
from perakende_veri.simulasyon import cesit_ata, simule_et
from perakende_veri.takvim import takvim_uret
from perakende_veri.urun import urunleri_uret


@pytest.fixture(scope="module")
def sonuc():
    rng = np.random.default_rng(sabitler.TOHUM)
    magazalar = magazalari_uret(rng)
    urunler = urunleri_uret(rng)
    takvim = takvim_uret()
    return simule_et(rng, magazalar, urunler, takvim)


# --- Çeşit ataması ------------------------------------------------------

def test_cesit_atamasi_kismi():
    rng = np.random.default_rng(sabitler.TOHUM)
    magazalar = magazalari_uret(rng)
    urunler = urunleri_uret(rng)
    cesit = cesit_ata(rng, magazalar, urunler)
    # Hiçbir mağaza tüm SKU'ları taşımaz; transfer ihtiyacı buradan doğar
    assert cesit.groupby("magaza_id").size().max() < len(urunler)


def test_cesit_option_butunlugu_korur():
    # Bir mağaza bir modeli taşıyorsa tüm beden ve renklerini taşır.
    # Beden bütünlüğü moda perakendesinin temel kuralıdır.
    rng = np.random.default_rng(sabitler.TOHUM)
    magazalar = magazalari_uret(rng)
    urunler = urunleri_uret(rng)
    cesit = cesit_ata(rng, magazalar, urunler).merge(urunler, on="urun_id")
    beden_sayisi = cesit.groupby(["magaza_id", "option_id"])["beden"].nunique()
    assert (beden_sayisi == len(sabitler.BEDENLER)).all()


# --- Üretilen tablolar --------------------------------------------------

def test_dort_tablo_uretilir(sonuc):
    assert set(sonuc) == {"satis", "stok", "sevkiyat", "kayip_satis"}


def test_satis_cekirdek_semaya_uyar(sonuc):
    # Spec bölüm 6: satis = tarih, magaza_id, urun_id, adet, tutar, indirim_tutari
    assert list(sonuc["satis"].columns) == [
        "tarih", "magaza_id", "urun_id", "adet", "tutar", "indirim_tutari",
    ]


def test_satis_bos_degil(sonuc):
    assert len(sonuc["satis"]) > 10_000


# --- Stok ---------------------------------------------------------------

def test_stok_negatif_olamaz(sonuc):
    assert (sonuc["stok"]["adet"] >= 0).all()


def test_stok_haftalik_fotograf(sonuc):
    assert set(sonuc["stok"]["tarih"].dt.dayofweek) == {0}


def test_stok_fotografi_ikmalden_once_cekilir(sonuc):
    """Yıl sonu fotoğrafı mağazalar arası dengesizliği göstermeli.

    Fotoğraf ikmalden sonra çekilirse bütün raflar dolu görünür ve
    transfer probleminin varlık sebebi veriden silinir.
    """
    stok = sonuc["stok"]
    son = stok[stok["tarih"] == stok["tarih"].max()]
    assert (son["adet"] == 0).sum() > 0, "son fotoğrafta hiç tükenmiş SKU yok"


# --- Ocak boşluğu -------------------------------------------------------

def test_yilin_ilk_gunlerinde_satis_var(sonuc):
    """Açılış stoğu olmadan ilk ikmale kadar veri boş kalır.

    Ocak'ın tamamen boş olması aylık grafikte anında görülür ve veri
    setinin inandırıcılığını bitirir.
    """
    satis = sonuc["satis"]
    ocak_ilk_hafta = satis[satis["tarih"] < pd.Timestamp("2025-01-08")]
    assert len(ocak_ilk_hafta) > 0


def test_her_ayda_satis_var(sonuc):
    aylik = sonuc["satis"].groupby(sonuc["satis"]["tarih"].dt.month)["adet"].sum()
    assert len(aylik) == 12
    assert (aylik > 0).all()


# --- Kayıp satış --------------------------------------------------------

def test_kayip_satis_ayri_tabloda(sonuc):
    kayip = sonuc["kayip_satis"]
    assert list(kayip.columns) == ["tarih", "magaza_id", "urun_id", "kayip_adet"]
    assert (kayip["kayip_adet"] > 0).all()


def test_tam_stoksuzluk_kaydediliyor(sonuc):
    """Rafın tamamen boş olduğu gün kayıp satışın en önemli hâlidir.

    Yalnızca kısmi stoksuzluk kaydedilirse kayıp satış sistematik olarak
    olduğundan az görünür ve transfer önerisinin değeri gösterilemez.
    """
    satis, kayip = sonuc["satis"], sonuc["kayip_satis"]
    satan = set(zip(satis["tarih"], satis["magaza_id"], satis["urun_id"]))
    tam_stoksuz = [
        anahtar
        for anahtar in zip(kayip["tarih"], kayip["magaza_id"], kayip["urun_id"])
        if anahtar not in satan
    ]
    assert len(tam_stoksuz) > 0


# --- Sevkiyat -----------------------------------------------------------

def test_sevkiyat_kaydediliyor(sonuc):
    sevkiyat = sonuc["sevkiyat"]
    assert list(sevkiyat.columns) == ["tarih", "magaza_id", "urun_id", "adet"]
    assert (sevkiyat["adet"] > 0).all()


def test_acilis_sevkiyati_yilin_ilk_gunu(sonuc):
    assert sonuc["sevkiyat"]["tarih"].min() == pd.Timestamp(sabitler.BASLANGIC)


def test_str_hesaplanabilir(sonuc):
    """STR = satılan / gönderilen. Sevkiyat kaydı olmadan hesaplanamaz."""
    gonderilen = sonuc["sevkiyat"].groupby("magaza_id")["adet"].sum()
    satilan = sonuc["satis"].groupby("magaza_id")["adet"].sum()
    str_orani = (satilan / gonderilen).dropna()
    assert len(str_orani) == sabitler.MAGAZA_SAYISI
    assert (str_orani > 0).all()
    assert (str_orani < 1).all(), "satış sevkiyatı aşamaz"


# --- İade ve kirli kayıt (spec bölüm 6 gereği) --------------------------

def test_iade_var(sonuc):
    # Gerçek POS verisinde iade negatif satır olarak görünür
    satis = sonuc["satis"]
    iadeler = satis[satis["adet"] < 0]
    assert len(iadeler) > 0
    assert (iadeler["tutar"] < 0).all()
    oran = -iadeler["adet"].sum() / satis.loc[satis["adet"] > 0, "adet"].sum()
    assert 0.02 < oran < 0.12, f"iade oranı gerçekçi değil: {oran:.3f}"


def test_kirli_kayit_var(sonuc):
    satis = sonuc["satis"]
    # Bedelsiz görünen satır (manuel giriş hatası)
    assert ((satis["adet"] > 0) & (satis["tutar"] == 0)).sum() > 0
    # Mükerrer kayıt
    mukerrer = satis.duplicated(subset=["tarih", "magaza_id", "urun_id"]).sum()
    assert mukerrer > 0


def test_kirli_kayit_azinlikta(sonuc):
    # Kusur inandırıcılık içindir; veriyi kullanılamaz hale getirmemeli
    satis = sonuc["satis"]
    bedelsiz = ((satis["adet"] > 0) & (satis["tutar"] == 0)).sum()
    assert bedelsiz / len(satis) < 0.001


# --- Tekrar üretilebilirlik --------------------------------------------

def test_tekrar_uretilebilir():
    def uret():
        rng = np.random.default_rng(sabitler.TOHUM)
        m = magazalari_uret(rng)
        u = urunleri_uret(rng)
        return simule_et(rng, m, u, takvim_uret())

    a, b = uret(), uret()
    for ad in a:
        assert a[ad].equals(b[ad]), ad


# --- Dengesizlik: transfer probleminin varlık sebebi ---------------------

def test_magazalar_arasi_beden_dengesizligi_var(sonuc):
    """Aynı modelin aynı bedeni bir mağazada tükenirken diğerinde yığılmalı.

    İkmal her mağazayı kendi gerçek talebine göre doldurursa plan hep
    doğru çıkar ve dengesizlik oluşmaz. Gerçek hayatta plan zincir
    geneline göre kurulur, talep ise yereldir — fark buradan doğar.
    """
    urunler = urunleri_uret(np.random.default_rng(sabitler.TOHUM))
    stok = sonuc["stok"]
    son = stok[stok["tarih"] == stok["tarih"].max()].merge(
        urunler[["urun_id", "model_kodu", "beden"]], on="urun_id"
    )
    ozet = son.groupby(["model_kodu", "beden"])["adet"].agg(["min", "max"])
    dengesiz = ((ozet["min"] == 0) & (ozet["max"] > 10)).sum()
    assert dengesiz > 20, f"yalnızca {dengesiz} dengesiz (model, beden) çifti"


def test_olu_stok_var(sonuc):
    """Yıl boyu hiç satmamış ama stok tutan mağaza-SKU çiftleri olmalı."""
    stok, satis = sonuc["stok"], sonuc["satis"]
    son = stok[stok["tarih"] == stok["tarih"].max()]
    satan = set(zip(satis["magaza_id"], satis["urun_id"]))
    olu = [
        1
        for m, u, a in zip(son["magaza_id"], son["urun_id"], son["adet"])
        if a > 0 and (m, u) not in satan
    ]
    assert len(olu) > 50, f"yalnızca {len(olu)} ölü stok çifti"


def test_tarih_tiplerinin_hepsi_ayni(sonuc):
    tipler = {ad: str(df["tarih"].dtype) for ad, df in sonuc.items()}
    assert len(set(tipler.values())) == 1, tipler
