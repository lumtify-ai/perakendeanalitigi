from datetime import date
from perakende_veri import sabitler


def test_sabitler_tutarli():
    assert sabitler.TOHUM == 42
    assert sabitler.VERI_SURUMU == "v1"
    assert sabitler.BASLANGIC == date(2025, 1, 1)
    assert sabitler.BITIS == date(2025, 12, 31)
    assert len(sabitler.BEDENLER) == 5
    assert len(sabitler.RENKLER) == 3
    assert sabitler.MODEL_SAYISI == 80
    assert sabitler.MAGAZA_SAYISI == 25


def test_sku_sayisi_beklenen():
    beklenen = sabitler.MODEL_SAYISI * len(sabitler.RENKLER) * len(sabitler.BEDENLER)
    assert beklenen == 1200
