import pandas as pd
import pulp
import pytest
from dataclasses import replace

from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cozuculer import greedy, mip

P = replace(Parametreler(), rota_sabiti_tl=0.0, min_koli=1)


def aday(verici, alici, option, adet, w):
    return dict(verici=verici, alici=alici, option_id=option, adet=adet, w=w)


def test_optimal_durum_ve_amac():
    df = pd.DataFrame([
        aday("MA", "MB", "OPT1", 12, 500.0),
        aday("MA", "MC", "OPT1", 12, 100.0),
        aday("MA", "MC", "OPT2", 8, 600.0),
    ])
    plan = mip.cozumle(df, {"MB": 100, "MC": 100}, P)
    assert plan.durum == "optimal"
    assert plan.hareketler.w.sum() == pytest.approx(1100.0)
    assert plan.amac == pytest.approx(1100.0)            # rota sabiti 0


def test_amac_rota_sabitini_duser():
    p = replace(P, rota_sabiti_tl=100.0)
    df = pd.DataFrame([aday("A", "J", "O1", 6, 500.0)])
    assert mip.cozumle(df, {"J": 100}, p).amac == pytest.approx(400.0)


# Dallanma gerektiren örnek: 8 blok × 3 alıcı (genelleştirilmiş atama).
# Skor adetle neredeyse orantılı (≈ 10 TL/adet), kapasite 29: LP gevşetmesi
# kesirli kalır, CBC kökte kanıtlayamaz. Üç adaylı bir sırt çantası işe
# yaramıyor: CBC onu kesmelerle kökte çözüyor, düğüm limiti hiç bağlamıyor.
GAP_BLOKLAR = [  # (adet, alıcı başına skor J0, J1, J2)
    (6, (62, 62, 66)), (10, (105, 105, 104)), (24, (241, 243, 247)),
    (25, (257, 259, 256)), (22, (228, 229, 225)), (6, (61, 66, 68)),
    (15, (157, 157, 159)), (10, (109, 103, 104)),
]


def gap_ornegi():
    df = pd.DataFrame([
        aday(f"V{b}", f"J{j}", f"O{b}", adet, float(w))
        for b, (adet, skorlar) in enumerate(GAP_BLOKLAR)
        for j, w in enumerate(skorlar)
    ])
    return df, {"J0": 29, "J1": 29, "J2": 29}


def test_dugum_limitinde_durum_limit():
    """PuLP limitte durunca da LpStatusOptimal döner; durum sol_status'tan okunur.

    Düğüm limiti 1'de CBC olurlu bir çözümle durur (kanıt yok) → "limit".
    Asla "optimal" değil."""
    df, kapasite = gap_ornegi()
    plan = mip.cozumle(df, kapasite, replace(P, mip_dugum_limiti=1))
    assert plan.durum == "limit"
    assert len(plan.hareketler) > 0 and plan.amac is not None
    # olurlu: blok tek hedefe, kapasite aşılmaz
    assert not plan.hareketler.duplicated(["verici", "option_id"]).any()
    assert (plan.hareketler.groupby("alici").adet.sum() <= 29).all()


def test_ayni_girdi_ayni_plan():
    df, kapasite = gap_ornegi()
    p = replace(P, mip_dugum_limiti=1)
    a = mip.cozumle(df, kapasite, p)
    b = mip.cozumle(df, kapasite, p)
    pd.testing.assert_frame_equal(a.hareketler, b.hareketler)
    assert (a.durum, a.amac) == (b.durum, b.amac)


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
    assert plan.amac == 0.0


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


def test_cbc_seri_ve_dugum_limitli_cagrilir(monkeypatch):
    """threads=0 (seri) ve maxNodes = p.mip_dugum_limiti. threads=1 CBC 2.10.3'te
    paralel kod yolunu açar: aynı girdide takılma ve çökme gözlendi."""
    gorulen = {}
    asil = pulp.PULP_CBC_CMD

    def yakala(**kwargs):
        gorulen.update(kwargs)
        return asil(**kwargs)

    monkeypatch.setattr(pulp, "PULP_CBC_CMD", yakala)
    df, kapasite = gap_ornegi()
    mip.cozumle(df, kapasite, replace(P, mip_dugum_limiti=7, mip_zaman_limiti_sn=60))
    assert gorulen["threads"] == 0
    assert gorulen["maxNodes"] == 7
    assert gorulen["timeLimit"] == 60


def test_cozumsuz_durum_hata_ve_bos_plan(monkeypatch):
    """Süre limitinde tam sayı çözüm bulunamazsa CBC'nin değişken değerleri
    LP gevşetmesinden gelir: plan değildir. Durum "hata", hareket yok."""
    asil = pulp.LpProblem.solve

    def cozumsuz(self, *args, **kwargs):
        sonuc = asil(self, *args, **kwargs)
        self.sol_status = pulp.LpSolutionNoSolutionFound
        return sonuc

    monkeypatch.setattr(pulp.LpProblem, "solve", cozumsuz)
    df, kapasite = gap_ornegi()
    plan = mip.cozumle(df, kapasite, P)
    assert plan.durum == "hata"
    assert plan.amac is None
    assert len(plan.hareketler) == 0
