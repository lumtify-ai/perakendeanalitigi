"""rapor.py ve senaryolar.py'nin saf yardımcı fonksiyonları için testler.

`rapor.py`'nin kendisi `cikti/` altındaki gerçek JSON'ları okur; burada
disk yerine küçük sahte sözlükler/dosyalarla yalnız özetleme matematiği
(min/medyan/max/aynı yön, iki senaryo kümesi arası fark) ve
`senaryolar.uret`'in şekli test edilir.
"""
import json

import pytest

from rapor import (
    forecast_etkisi_eslesmeleri,
    kombinasyon_farki,
    koli_farki_eslesmeleri,
    politika_etkisi_eslesmeleri,
    ss_farki_eslesmeleri,
    yirmi_yol_ozeti,
)
from senaryolar import KOLI_SECENEKLERI, PARAMETRELER, YONTEM_SECENEKLERI, uret


def test_yirmi_yol_ozeti():
    o = yirmi_yol_ozeti([-1.0, 2.0, 3.0, 4.0])
    assert o == {"min": -1.0, "medyan": 2.5, "max": 4.0, "pozitif": 3, "n": 4}


def test_yirmi_yol_ozeti_tek_eleman():
    assert yirmi_yol_ozeti([5.0]) == {"min": 5.0, "medyan": 5.0, "max": 5.0, "pozitif": 1, "n": 1}


def test_yirmi_yol_ozeti_ciftteki_medyan_ortalamasi():
    o = yirmi_yol_ozeti([1.0, 3.0])
    assert o["medyan"] == 2.0


# --- kombinasyon_farki: iki senaryo kümesi arası fark, yol başına ---

_SAHTE_VERI = {
    1: {
        "tahmin_taban|60|A|ros": {"bulunabilirlik": 70.0},
        "kural|60|A|ros": {"bulunabilirlik": 65.0},
        "tahmin_taban|80|A|ros": {"bulunabilirlik": 72.0},
        "kural|80|A|ros": {"bulunabilirlik": 68.0},
    },
    2: {
        "tahmin_taban|60|A|ros": {"bulunabilirlik": 60.0},
        "kural|60|A|ros": {"bulunabilirlik": 64.0},
        "tahmin_taban|80|A|ros": {"bulunabilirlik": 61.0},
        "kural|80|A|ros": {"bulunabilirlik": 63.0},
    },
}


def test_kombinasyon_farki_yol_basina_ortalama():
    eslesmeler = [("tahmin_taban|60|A|ros", "kural|60|A|ros"),
                  ("tahmin_taban|80|A|ros", "kural|80|A|ros")]
    farklar = kombinasyon_farki(_SAHTE_VERI, [1, 2], eslesmeler, "bulunabilirlik")
    # yol 1: (70-65 + 72-68)/2 = 4.5 ; yol 2: (60-64 + 61-63)/2 = -3.0
    assert farklar == pytest.approx([4.5, -3.0])


def test_forecast_etkisi_eslesmeleri_kural_ros_ile_tahmin_taban_esler():
    eslesmeler = forecast_etkisi_eslesmeleri([60, 80], ["A", "B"])
    assert ("tahmin_taban|60|A|ros", "kural|60|A|ros") in eslesmeler
    assert ("tahmin_taban|80|B|ros", "kural|80|B|ros") in eslesmeler
    assert len(eslesmeler) == 4


def test_politika_etkisi_eslesmeleri_tahmin_ile_tahmin_taban_esler():
    eslesmeler = politika_etkisi_eslesmeleri([60], ["A", "B", "C"])
    assert ("tahmin|60|A|-", "tahmin_taban|60|A|ros") in eslesmeler
    assert len(eslesmeler) == 3


def test_koli_farki_eslesmeleri():
    eslesmeler = koli_farki_eslesmeleri([60, 80, 100], "ros", "A", "B")
    assert ("kural|60|B|ros", "kural|60|A|ros") in eslesmeler
    assert len(eslesmeler) == 3


def test_ss_farki_eslesmeleri():
    eslesmeler = ss_farki_eslesmeleri([60, 80, 100], ["A", "B", "C"], "sabit", "ros")
    assert ("kural|60|A|ros", "kural|60|A|sabit") in eslesmeler
    assert len(eslesmeler) == 9


# --- senaryolar.uret: 27 kadran anahtarı, her ozet 6 ölçütlü ---

def _sahte_yol0(tmp_path):
    yol0 = tmp_path / "yol0"
    yol0.mkdir()
    olcut = {
        "bulunabilirlik": 70.0, "kayip_orani": 20.0, "satisa_donme_gun": 5.0,
        "magaza_stok_son": 1000.0, "toplama_maliyeti_tl": 50000.0,
        "kirik_cift": 30.0, "stoklu_cift_sayisi": 100.0, "bos_cift_sayisi": 20.0,
        "kirik_cift_pay_yuzde": 30.0,
    }
    for alim in PARAMETRELER[0]["degerler"]:
        for yontem in YONTEM_SECENEKLERI:
            for koli in KOLI_SECENEKLERI:
                ss = "ros" if yontem in ("kural", "tahmin_taban") else "-"
                dosya = f"{yontem}_{alim}_{koli}_{ss}.json"
                (yol0 / dosya).write_text(json.dumps(olcut), encoding="utf-8")
    return tmp_path


def test_senaryolar_uret_yirmi_yedi_anahtar_alti_olcut(tmp_path):
    cikti = _sahte_yol0(tmp_path)
    sonuc = uret(cikti)
    assert len(sonuc) == 27
    for anahtar, girdi in sonuc.items():
        assert anahtar.count("|") == 2
        assert set(girdi["ozet"]) == {
            "bulunabilirlik", "kayip_orani", "satisa_donme_gun",
            "magaza_stok_son", "toplama_maliyeti_tl", "kirik_cift_pay_yuzde",
        }
        assert girdi["satirlar"] == []
