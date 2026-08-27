from datetime import date
from perakende_veri import sabitler


def test_sabitler_tutarli():
    assert sabitler.TOHUM == 42
    assert sabitler.VERI_SURUMU == "v2"
    assert sabitler.BASLANGIC == date(2025, 1, 1)
    assert sabitler.BITIS == date(2025, 12, 31)
    assert sabitler.MODEL_SAYISI == 80
    assert sabitler.MAGAZA_SAYISI == 25
    assert sabitler.MARKA == "Lumoda"
    assert len(sabitler.RENKLER) == 3
    assert sabitler.BEDEN_KADEME_SAYISI == 5


def test_sku_sayisi_beklenen():
    beklenen = (
        sabitler.MODEL_SAYISI
        * len(sabitler.RENKLER)
        * sabitler.BEDEN_KADEME_SAYISI
    )
    assert beklenen == 1200


def test_her_cinsiyet_kategori_ciftinin_beden_seti_var():
    for cinsiyet in sabitler.CINSIYETLER:
        for ust_kategori in sabitler.KATEGORILER:
            ad, bedenler = sabitler.BEDEN_SETLERI[(cinsiyet, ust_kategori)]
            assert len(bedenler) == sabitler.BEDEN_KADEME_SAYISI
            assert len(set(bedenler)) == sabitler.BEDEN_KADEME_SAYISI
            assert ad


def test_her_alt_kategorinin_kesim_havuzu_var():
    for altlar in sabitler.KATEGORILER.values():
        for alt in altlar:
            assert sabitler.KESIMLER[alt]


def test_line_paylari_toplami_bir():
    assert abs(sum(sabitler.LINE_PAYLARI) - 1.0) < 1e-9
    assert len(sabitler.LINELER) == len(sabitler.LINE_PAYLARI)
