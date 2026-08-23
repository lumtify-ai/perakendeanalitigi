import pytest
from perakende_veri import sabitler, talep


# --- Beden eğrisi -------------------------------------------------------

def test_beden_dagilimi_toplami_bir():
    dagilim = talep.beden_dagilimi()
    assert set(dagilim) == set(range(1, sabitler.BEDEN_KADEME_SAYISI + 1))
    assert pytest.approx(sum(dagilim.values()), abs=1e-9) == 1.0


def test_beden_egrisi_etikete_degil_siraya_bagli():
    """Tişört S/M/L gider, pantolon 32/34 gider; eğri ikisinde de aynıdır.

    Orta kademeler satar, uçlar durur. Etiket üzerinden tanımlansaydı
    numara setleri için ayrı bir eğri tutmak gerekirdi.
    """
    dagilim = talep.beden_dagilimi()
    assert dagilim[3] > dagilim[1]   # orta > en küçük
    assert dagilim[3] > dagilim[5]   # orta > en büyük
    assert dagilim[4] > dagilim[5]


# --- Kategori, mağaza, gün ---------------------------------------------

def test_dis_giyim_kista_daha_cok_satar():
    kis = talep.sezon_carpani("Dış Giyim", "Sonbahar/Kış")
    yaz = talep.sezon_carpani("Dış Giyim", "İlkbahar/Yaz")
    assert kis > yaz * 2


def test_outlet_daha_yuksek_hacim():
    assert talep.magaza_tipi_carpani("Outlet") > talep.magaza_tipi_carpani("Cadde")


def test_hafta_sonu_ve_tatil_artisi():
    sali = talep.gun_carpani(1, False)
    cumartesi = talep.gun_carpani(5, False)
    tatil = talep.gun_carpani(1, True)
    assert cumartesi > sali
    assert tatil > sali


def test_cinsiyet_carpani_tanimli():
    for cinsiyet in sabitler.CINSIYETLER:
        assert talep.cinsiyet_carpani(cinsiyet) > 0
    assert talep.cinsiyet_carpani("Kadın") > talep.cinsiyet_carpani("Erkek")


# --- Line ---------------------------------------------------------------

def test_her_line_tanimli():
    for line in sabitler.LINELER:
        assert talep.line_hacim_carpani(line) > 0
        assert talep.line_moda_riski(line) > 0


def test_nos_sezondan_neredeyse_etkilenmez():
    """NOS ürünün stoğu asla bitmemeli; talebi de yıl boyu düz olmalı."""
    def oran(line):
        return (
            talep.line_sezon_carpani(line, "Dış Giyim", "Sonbahar/Kış")
            / talep.line_sezon_carpani(line, "Dış Giyim", "İlkbahar/Yaz")
        )

    assert oran("Collection") > oran("Basic") > oran("NOS")
    assert oran("NOS") < 1.6


def test_collection_sezon_carpanini_oldugu_gibi_alir():
    assert talep.line_sezon_carpani("Collection", "Dış Giyim", "Sonbahar/Kış") == pytest.approx(
        talep.sezon_carpani("Dış Giyim", "Sonbahar/Kış")
    )


def test_nos_en_cok_outlet_en_az_satar():
    assert talep.line_hacim_carpani("NOS") > talep.line_hacim_carpani("Basic")
    assert talep.line_hacim_carpani("Outlet") < talep.line_hacim_carpani("Collection")


def test_collection_moda_riski_en_yuksek():
    """Collection bir mağazada tutar, diğerinde tutmaz; NOS her yerde tutar."""
    assert talep.line_moda_riski("Collection") > talep.line_moda_riski("Basic")
    assert talep.line_moda_riski("Basic") > talep.line_moda_riski("NOS")
