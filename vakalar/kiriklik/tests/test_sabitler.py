"""`sabitler`: spec'teki değerler birebir (Global Constraints)."""

import dataclasses
from datetime import date

import pytest

from kiriklik import sabitler


def test_degerler():
    assert sabitler.TEST_SEZONLARI == ("AW24", "SS25")
    assert sabitler.KARAR == {"AW24": date(2024, 12, 9), "SS25": date(2025, 6, 2)}
    assert all(d.weekday() == 0 for d in sabitler.KARAR.values())      # karar günü pazartesi
    assert sabitler.ASORTI == (1, 2, 2, 1, 1) and sum(sabitler.ASORTI) == 7
    assert sabitler.FIZIKSEL_TIPLER == ("AVM", "Cadde")
    assert (sabitler.ATIL_PENCERE_GUN, sabitler.ATIL_ESIK_OPTION, sabitler.ATIL_ESIK_SKU) == (28, 2, 1)
    assert sabitler.ATIL_DUYARLILIK == (1, 2, 3)
    assert sabitler.VARIS_GUN == 3
    assert sabitler.GAP_REL == 0.005 and sabitler.DUGUM_SINIRI == 200_000
    assert sabitler.CBC_SECENEKLERI == ("passC 1", "proximity on", "rins on", "dins on")


def test_maliyet_paketleri():
    p = {ad: (v.toplama_birim_tl, v.kargo_rota_tl, v.yipranma_orani)
         for ad, v in sabitler.MALIYET_PAKETLERI.items()}
    assert p == {"dusuk": (5.0, 300.0, 0.03), "orta": (10.0, 500.0, 0.05), "yuksek": (20.0, 900.0, 0.08)}
    assert sabitler.KARAR_PAKETI == "orta" and sabitler.KARAR_PAKETI in sabitler.MALIYET_PAKETLERI


def test_paket_degistirilemez():
    with pytest.raises(dataclasses.FrozenInstanceError):
        sabitler.MALIYET_PAKETLERI["orta"].kargo_rota_tl = 1.0
