from dataclasses import replace
from datetime import date

from blok_transfer.cekirdek import adaylar
from blok_transfer.cekirdek.parametreler import Parametreler

KARAR = date(2025, 12, 29)
P = Parametreler()  # cover_esigi=6, min_satis=1


def ciftler(df):
    return set(zip(df.verici, df.alici, df.option_id))


def test_beklenen_uc_aday(con):
    df = adaylar.uret(con, KARAR, P)
    assert ciftler(df) == {
        ("MA", "MB", "OPT1"),   # kırık + hızlı alıcı
        ("MA", "MC", "OPT1"),   # stoksuz alıcı
        ("MA", "MC", "OPT2"),   # stoksuz outlet alıcı
    }


def test_soguma_vericiyi_eler(con):
    # MD-OPT1: cover 10/0.125 = 80 ≥ 6 ama 2025-12-22 sevkiyatı soğumada
    df = adaylar.uret(con, KARAR, P)
    assert not (df.verici == "MD").any()


def test_line_kurali_outlet_urunu_vitrine_gitmez(con):
    # MB-OPT2 kırık ve hızlı (3/hafta) ama OPT2 line=Outlet, MB tip=Cadde
    df = adaylar.uret(con, KARAR, P)
    assert ("MA", "MB", "OPT2") not in ciftler(df)


def test_esikler_senaryo_parametresi(con):
    dar = adaylar.uret(con, KARAR, replace(P, min_satis=2.0))
    assert ("MA", "MC", "OPT1") not in ciftler(dar)          # MC-OPT1 hız 1 < 2
    cok_dar = adaylar.uret(con, KARAR, replace(P, cover_esigi=30.0))
    assert ciftler(cok_dar) == {("MA", "MC", "OPT2")}        # MA-OPT1 cover 24 < 30
    assert cok_dar.iloc[0].adet == 8                         # blok = vericinin tüm stoğu


def test_kapasite_boslugu(con):
    b = adaylar.kapasite_boslugu(con, KARAR)
    assert b == {"MA": 980, "MB": 994, "MC": 5000, "MD": 990}


def test_cok_siki_esikte_bos_ama_dogru_bicimli_cerceve(con):
    # Eşikler her şeyi elediğinde çökmemeli; kolonlar korunmalı (çözücüler
    # boş çerçeveyi bu kolonlarla bekliyor).
    bos = adaylar.uret(con, KARAR, replace(P, min_satis=99.0))
    assert len(bos) == 0
    assert list(bos.columns) == adaylar.KOLONLAR
