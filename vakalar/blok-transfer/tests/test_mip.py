import pandas as pd
import pytest
from dataclasses import replace

from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cozuculer import greedy, mip

P = replace(Parametreler(), rota_sabiti_tl=0.0, min_koli=1)


def aday(verici, alici, option, adet, w):
    return dict(verici=verici, alici=alici, option_id=option, adet=adet, w=w)


def test_kucuk_ornekte_bilinen_optimum():
    df = pd.DataFrame([
        aday("MA", "MB", "OPT1", 12, 500.0),
        aday("MA", "MC", "OPT1", 12, 100.0),
        aday("MA", "MC", "OPT2", 8, 600.0),
    ])
    plan = mip.cozumle(df, {"MB": 100, "MC": 100}, P)
    assert plan.durum == "optimal"
    assert plan.hareketler.w.sum() == pytest.approx(1100.0)


def test_kapasitede_mip_greedyyi_gecer():
    # j boşluğu 10: greedy w=10'luk 10 adedi alır (toplam 10);
    # MIP 6+4 adetlik iki bloğu alır (toplam 15)
    df = pd.DataFrame([
        aday("A", "J", "O1", 10, 10.0),
        aday("B", "J", "O2", 6, 8.0),
        aday("C", "J", "O3", 4, 7.0),
    ])
    kapasite = {"J": 10}
    assert greedy.cozumle(df, kapasite, P).hareketler.w.sum() == pytest.approx(10.0)
    assert mip.cozumle(df, kapasite, P).hareketler.w.sum() == pytest.approx(15.0)


def test_min_kolide_mip_kucuk_bloklari_birlestirir():
    # Blok adedi vericinin stoğudur: (A,O2) her iki adayda da 3.
    # Greedy: O1→J (50), sonra O2→K (12 > 10) → post-filter iki rotayı da
    # iptal eder (J: 4 < 6, K: 3 < 6) → toplam 0.
    # MIP: O1 ve O2'yi J'de birleştirir (7 adet ≥ 6) → 60.
    p = replace(P, min_koli=6)
    df = pd.DataFrame([
        aday("A", "J", "O1", 4, 50.0),
        aday("A", "J", "O2", 3, 10.0),
        aday("A", "K", "O2", 3, 12.0),
    ])
    kapasite = {"J": 100, "K": 100}
    assert greedy.cozumle(df, kapasite, p).hareketler.w.sum() == pytest.approx(0.0)
    m = mip.cozumle(df, kapasite, p)
    assert m.hareketler.w.sum() == pytest.approx(60.0)


def test_rota_sabiti_kucuk_kazanci_caydirir():
    p = replace(P, rota_sabiti_tl=1000.0)
    df = pd.DataFrame([aday("A", "J", "O1", 6, 500.0)])
    assert len(mip.cozumle(df, {"J": 100}, p).hareketler) == 0
    p2 = replace(P, rota_sabiti_tl=100.0)
    assert len(mip.cozumle(df, {"J": 100}, p2).hareketler) == 1


def test_bos_aday_bos_plan():
    from blok_transfer.cozuculer.tip import bos_hareketler
    plan = mip.cozumle(bos_hareketler(), {}, P)
    assert plan.durum == "optimal" and len(plan.hareketler) == 0


def test_kur_modeli_ve_degiskenleri_verir():
    """Formülasyon tek yerde kalmalı: rapor da çözücü de aynı kurulumu görür."""
    import pandas as pd
    from blok_transfer.cozuculer import mip
    from blok_transfer.cekirdek.parametreler import Parametreler

    df = pd.DataFrame([
        dict(verici="MA", alici="MB", option_id="OPT1", adet=10, w=500.0),
        dict(verici="MA", alici="MC", option_id="OPT2", adet=8, w=400.0),
    ])
    model, x, y = mip.kur(df, {"MB": 100, "MC": 100}, Parametreler())
    assert len(x) == 2                                   # aday başına bir x
    assert set(y) == {("MA", "MB"), ("MA", "MC")}        # rota başına bir y
    assert len(model.constraints) > 0
