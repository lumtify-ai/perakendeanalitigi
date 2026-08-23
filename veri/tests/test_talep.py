import pytest
from perakende_veri import sabitler, talep


def test_beden_dagilimi_toplami_bir():
    dagilim = talep.beden_dagilimi()
    assert set(dagilim) == set(sabitler.BEDENLER)
    assert pytest.approx(sum(dagilim.values()), abs=1e-9) == 1.0


def test_orta_bedenler_daha_cok_satar():
    dagilim = talep.beden_dagilimi()
    assert dagilim["M"] > dagilim["XS"]
    assert dagilim["L"] > dagilim["XL"]


def test_dis_giyim_kista_daha_cok_satar():
    kis = talep.sezon_carpani("Dış Giyim", "Sonbahar/Kış")
    yaz = talep.sezon_carpani("Dış Giyim", "İlkbahar/Yaz")
    assert kis > yaz * 2


def test_outlet_daha_yuksek_hacim():
    assert talep.magaza_tipi_carpani("Outlet") > talep.magaza_tipi_carpani("Cadde")


def test_hafta_sonu_ve_tatil_artisi():
    salı = talep.gun_carpani(1, False)
    cumartesi = talep.gun_carpani(5, False)
    tatil = talep.gun_carpani(1, True)
    assert cumartesi > salı
    assert tatil > salı
