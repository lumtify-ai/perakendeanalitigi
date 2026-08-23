import numpy as np
import pytest
from perakende_veri import sabitler
from perakende_veri.magaza import magazalari_uret


@pytest.fixture
def magazalar():
    return magazalari_uret(np.random.default_rng(sabitler.TOHUM))


def test_dogru_sayida_magaza(magazalar):
    assert len(magazalar) == sabitler.MAGAZA_SAYISI


def test_magaza_id_benzersiz_ve_bicimli(magazalar):
    assert magazalar["magaza_id"].is_unique
    assert magazalar["magaza_id"].iloc[0] == "M001"


def test_her_tip_temsil_ediliyor(magazalar):
    assert set(magazalar["tip"]) == set(sabitler.MAGAZA_TIPLERI)


def test_outlet_magazalar_daha_buyuk(magazalar):
    # Outlet mağazalar cadde mağazalarından ortalama daha geniştir
    outlet = magazalar.loc[magazalar["tip"] == "Outlet", "metrekare"].mean()
    cadde = magazalar.loc[magazalar["tip"] == "Cadde", "metrekare"].mean()
    assert outlet > cadde


def test_tekrar_uretilebilir():
    a = magazalari_uret(np.random.default_rng(sabitler.TOHUM))
    b = magazalari_uret(np.random.default_rng(sabitler.TOHUM))
    assert a.equals(b)


def test_magaza_adlari_benzersiz(magazalar):
    # Bir zincirde aynı adlı iki mağaza olmaz; rapor okunamaz hale gelir
    assert magazalar["ad"].is_unique


def test_istanbul_agirlikli(magazalar):
    # Türkiye moda perakendesinde mağaza dağılımı İstanbul ağırlıklıdır
    istanbul = (magazalar["sehir"] == "İstanbul").sum()
    assert istanbul >= 5


def test_kapasite_metrekareyle_tutarli(magazalar):
    # Kapasite (taşınabilir azami adet) transfer kısıtının girdisidir
    assert (magazalar["kapasite"] > 0).all()
    buyuk = magazalar.nlargest(3, "metrekare")["kapasite"].mean()
    kucuk = magazalar.nsmallest(3, "metrekare")["kapasite"].mean()
    assert buyuk > kucuk
