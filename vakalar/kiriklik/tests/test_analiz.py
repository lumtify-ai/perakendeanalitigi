"""analiz.py: referans pazartesisi ve hafta numarası (oyuncak takvimle); `veri` işaretli: yayımlanan v4'te uygunluk
hunisi tasarımın keşif sayılarını (§0 ve K18) yeniden üretir ve referans pazartesisinin fotoğrafı karar anının
girdisiyle aynı kırıklığı verir."""

from datetime import date

import pytest

import analiz
from kiriklik import sabitler


def test_referans_ve_hafta(con):
    """Referans pazartesisi indirim − 28'den sonraki ilk pazartesidir; test sezonunda karar günü. Hafta indirim gününün
    haftasına göre."""
    g = analiz.sezon_gunleri(con, "AW24")
    assert g["referans"] == sabitler.KARAR["AW24"] == date(2024, 12, 9) and g["lansman"] == date(2024, 8, 19)
    assert analiz.hafta_no(date(2024, 12, 30), g) == 0 and analiz.hafta_no(date(2024, 12, 9), g) == -3
    p = analiz.pazartesiler(g)
    assert p[0] == date(2024, 8, 19) and p[-1] == date(2025, 2, 17) and all(d.weekday() == 0 for d in p)


@pytest.mark.veri
def test_analiz_kesif_sayilari(veri_con):
    """Tasarım §0 keşif olguları ve K18: AW24 4.051 stoklu, 1.873 kırık, dar tanımla 1.407, 1.126 depoda yok, 819 uygun;
    SS25 4.258, 1.985, 931, 651. Haftalık serinin referans pazartesisi karar girdisiyle aynı kırıklığı verir."""
    beklenen = {"AW24": (4051, 1873, 1126, 819, 819), "SS25": (4258, 1985, 931, 651, 651)}
    for z, b in beklenen.items():
        h = analiz.huni(veri_con, z)
        assert tuple(x["cift"] for x in h["basamaklar"]) == b
        assert h["neden"]["uygun"] == b[-1] and h["neden"]["magaza"] == 0
    h = analiz.huni(veri_con, "AW24")
    assert h["ozet"]["dar_kirik_cift"] == 1407 and round(100 * h["ozet"]["net_oran"], 1) == 20.2
    assert (h["kesif"]["sku"], h["kesif"]["sku_depolu"], h["kesif"]["option_deposuz"]) == (905, 392, 42)
    s = analiz.sezon_blogu(veri_con, "AW24")
    assert {a: s["referans"]["butun"][a] for a in analiz.OZET_ALANLARI} == {a: h["ozet"][a] for a in analiz.OZET_ALANLARI}
    assert s["referans"]["hafta"] == -3 and len(s["haftalik"]) == 27


def test_beden_sirasi_ozetle_esit():
    """Beden sırası tablosunun toplamları aynı fotoğrafın `olcu.ozet`'ine eşittir; değilse `ValueError` (tanım tek)."""
    import pandas as pd

    from kiriklik import olcu
    foto = pd.DataFrame([("M1", "O1", i + 1, a) for i, a in enumerate((1, 0, 0, 1, 1))]
                        + [("M2", "O1", i + 1, a) for i, a in enumerate((1, 1, 2, 1, 1))]
                        + [("M3", "O1", i + 1, 0) for i in range(5)],
                        columns=["magaza_id", "option_id", "beden_sira", "stok"])
    oz = olcu.ozet(olcu.cift_tablosu(foto))
    t = analiz.beden_sirasi(foto, oz)
    assert [x["kirik_cift"] for x in t] == [0, 1, 1, 0, 0] and [x["eksik_adet"] for x in t] == [0, 3, 2, 0, 0]
    assert t[1]["pay"] == 0.5
    with pytest.raises(ValueError, match="olcu.ozet"):
        analiz.beden_sirasi(foto, oz | {"eksik_adet": oz["eksik_adet"] + 1})
