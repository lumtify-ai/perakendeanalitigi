import pandas as pd

from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cozuculer import greedy

P = Parametreler()  # min_koli=6


def aday(verici, alici, option, adet, w):
    return dict(verici=verici, alici=alici, option_id=option, adet=adet, w=w)


def test_siralama_tek_hedef_ve_negatif_durur():
    df = pd.DataFrame([
        aday("MA", "MB", "OPT1", 12, 500.0),
        aday("MA", "MC", "OPT1", 12, 100.0),   # aynı blok, tek hedef → elenir
        aday("MA", "MC", "OPT2", 8, 600.0),
        aday("MB", "MC", "OPT3", 7, -50.0),    # w ≤ 0 → alınmaz
    ])
    plan = greedy.cozumle(df, {"MB": 1000, "MC": 1000}, P)
    assert plan.durum == "optimal"
    ciftler = set(zip(plan.hareketler.verici, plan.hareketler.alici, plan.hareketler.option_id))
    assert ciftler == {("MA", "MB", "OPT1"), ("MA", "MC", "OPT2")}


def test_kapasite_asilmaz():
    df = pd.DataFrame([
        aday("MA", "MB", "OPT1", 10, 500.0),
        aday("MC", "MB", "OPT2", 8, 400.0),    # boşluk 12−10=2 < 8 → atlanır
        aday("MC", "MD", "OPT2", 8, 300.0),    # MD'ye gider
    ])
    plan = greedy.cozumle(df, {"MB": 12, "MD": 100}, P)
    ciftler = set(zip(plan.hareketler.verici, plan.hareketler.alici))
    assert ciftler == {("MA", "MB"), ("MC", "MD")}


def test_min_koli_rota_post_filtresi():
    # Rota MA→MB toplam 4 < 6 → rota iptal; MA→MC 7 ≥ 6 → kalır
    df = pd.DataFrame([
        aday("MA", "MB", "OPT1", 4, 900.0),
        aday("MA", "MC", "OPT2", 7, 100.0),
    ])
    plan = greedy.cozumle(df, {"MB": 100, "MC": 100}, P)
    assert set(plan.hareketler.alici) == {"MC"}


def test_deterministik_esit_skor():
    df = pd.DataFrame([
        aday("MB", "MC", "OPT2", 6, 100.0),
        aday("MA", "MC", "OPT1", 6, 100.0),
    ])
    p1 = greedy.cozumle(df, {"MC": 100}, P)
    p2 = greedy.cozumle(df.iloc[::-1].reset_index(drop=True), {"MC": 100}, P)
    assert p1.hareketler.verici.tolist() == p2.hareketler.verici.tolist() == ["MA", "MB"]
