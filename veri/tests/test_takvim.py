import pandas as pd
import pytest
from perakende_veri.takvim import takvim_uret


@pytest.fixture
def takvim():
    return takvim_uret()


def test_tam_yil(takvim):
    assert len(takvim) == 365
    assert takvim["tarih"].min() == pd.Timestamp("2025-01-01")
    assert takvim["tarih"].max() == pd.Timestamp("2025-12-31")


def test_sezon_atamasi(takvim):
    mart = takvim.loc[takvim["tarih"] == pd.Timestamp("2025-05-15"), "sezon"].iloc[0]
    kasim = takvim.loc[takvim["tarih"] == pd.Timestamp("2025-11-15"), "sezon"].iloc[0]
    assert mart == "İlkbahar/Yaz"
    assert kasim == "Sonbahar/Kış"


def test_tatil_gunleri_isaretli(takvim):
    yilbasi = takvim.loc[takvim["tarih"] == pd.Timestamp("2025-01-01"), "tatil_mi"].iloc[0]
    sira_gun = takvim.loc[takvim["tarih"] == pd.Timestamp("2025-02-11"), "tatil_mi"].iloc[0]
    assert bool(yilbasi) is True
    assert bool(sira_gun) is False
