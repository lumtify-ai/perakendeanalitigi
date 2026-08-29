import pandas as pd
import pytest

import getiri


def mini_plan() -> pd.DataFrame:
    """İki hareketli, elle hesaplanabilir plan.

    brüt kâr    10×600 + 5×120 = 6.600
    liste       10×1000 + 5×200 = 11.000
    maliyet değ. 10×400 + 5×80  = 4.400
    adet 15 · rota 2 (MA→MB, MA→MC)
    """
    return pd.DataFrame([
        dict(verici="MA", alici="MB", adet=10, liste=1000.0, alis=400.0),
        dict(verici="MA", alici="MC", adet=5, liste=200.0, alis=80.0),
    ])


def test_hesap_elle_dogrulanabilir():
    # orta paket: toplama 10×15=150 · kargo 500×2=1.000 · yıpranma 0,05×4.400=220
    # maliyet 1.370 · fark (60−10)/100 = 0,50
    # net 0,50×6.600 − 1.370 = 1.930
    sonuc = getiri.hesapla(mini_plan(), getiri.MALIYET_PAKETLERI["orta"], 60, 10)
    assert sonuc["net_kar_tl"] == pytest.approx(1930.0)
    assert sonuc["ciro_etkisi_tl"] == pytest.approx(5500.0)     # 0,50 × 11.000
    assert sonuc["hareket_basina_kar_tl"] == pytest.approx(965.0)
    assert sonuc["basabas_ihtimal_yuzde"] == pytest.approx(30.8)  # 10 + 1.370/6.600


def test_basabas_net_kari_sifirlar():
    """Başabaş ihtimal, tanımı gereği net kârı sıfıra getiren p_a'dır.

    Tolerans yuvarlamadan gelir: başabaş bir ondalığa yuvarlandığı için
    p_a en fazla 0,05 puan sapar, bu da 6.600 TL brüt kârda ~3,3 TL eder.
    """
    paket = getiri.MALIYET_PAKETLERI["yuksek"]
    bb = getiri.hesapla(mini_plan(), paket, 60, 10)["basabas_ihtimal_yuzde"]
    assert getiri.hesapla(mini_plan(), paket, bb, 10)["net_kar_tl"] == pytest.approx(0.0, abs=5.0)


def test_alici_vericiden_kotuyse_zarar():
    # Izgarada böyle bir kombinasyon yok ama fonksiyon kabul eder ve zarar döner.
    sonuc = getiri.hesapla(mini_plan(), getiri.MALIYET_PAKETLERI["dusuk"], 20, 40)
    assert sonuc["net_kar_tl"] < 0


def test_bos_plan_acik_hata():
    bos = pd.DataFrame(columns=["verici", "alici", "adet", "liste", "alis"])
    with pytest.raises(ValueError, match="boş"):
        getiri.hesapla(bos, getiri.MALIYET_PAKETLERI["orta"], 60, 10)


def test_paketler_spec_degerleri():
    assert getiri.MALIYET_PAKETLERI["dusuk"] == getiri.Paket(5.0, 300.0, 0.03)
    assert getiri.MALIYET_PAKETLERI["orta"] == getiri.Paket(10.0, 500.0, 0.05)
    assert getiri.MALIYET_PAKETLERI["yuksek"] == getiri.Paket(20.0, 900.0, 0.08)
