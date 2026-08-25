from datetime import date

import pytest

from blok_transfer.cekirdek import metrikler
from blok_transfer.cekirdek.parametreler import Parametreler

KARAR = date(2025, 12, 29)


def hucre(df, m, o):
    satir = df[(df.magaza_id == m) & (df.option_id == o)]
    assert len(satir) == 1, f"({m},{o}) için {len(satir)} satır"
    return satir.iloc[0]


def test_hiz_stoklu_haftalarin_ortalamasi(con):
    df = metrikler.hizlar(con, KARAR, 8)
    assert hucre(df, "MA", "OPT1").hiz == pytest.approx(0.5)
    # MC-OPT1: 8 haftanın 4'ü stoklu, her stoklu haftada 1 → 1.0 (0.5 DEĞİL)
    assert hucre(df, "MC", "OPT1").hiz == pytest.approx(1.0)


def test_hiz_iadeyi_netler(con):
    df = metrikler.hizlar(con, KARAR, 8)
    assert hucre(df, "MB", "OPT1").hiz == pytest.approx(4.0)  # 12-08: +5 −1


def test_hic_stoklu_haftasi_olmayan_hucre_donmez(con):
    df = metrikler.hizlar(con, KARAR, 8)
    assert df[(df.magaza_id == "MC") & (df.option_id == "OPT2")].hiz.iloc[0] == pytest.approx(2.0)
    assert len(df[(df.magaza_id == "MD") & (df.option_id == "OPT2")]) == 0


def test_stok_fotografi_karar_gunu(con):
    df = metrikler.stok_fotografi(con, KARAR)
    assert hucre(df, "MA", "OPT1").adet == 12
    assert hucre(df, "MB", "OPT2").adet == 1
    assert len(df[(df.magaza_id == "MC") & (df.option_id == "OPT1")]) == 0  # 0 stok dönmez


def test_kiriklik_etikete_degil_siraya_bakar(con):
    df = metrikler.kiriklar(con, KARAR)
    ciftler = set(zip(df.magaza_id, df.option_id))
    assert ciftler == {("MB", "OPT1"), ("MB", "OPT2")}  # MA/MD tam set, MC stoksuz


def test_cover_ve_sifir_hizda_buyuk_deger(con):
    p = Parametreler()
    df = metrikler.coverlar(con, KARAR, p)
    assert hucre(df, "MA", "OPT1").cover == pytest.approx(24.0)   # 12 / 0.5
    assert hucre(df, "MA", "OPT2").cover == pytest.approx(p.buyuk_cover)  # hiç satış


def test_str_kumulatif(con):
    df = metrikler.strler(con, KARAR)
    assert hucre(df, "MB", "OPT1").str_orani == pytest.approx(0.8)   # 32/40
    assert hucre(df, "MA", "OPT2").str_orani == pytest.approx(0.0)   # 0/8
