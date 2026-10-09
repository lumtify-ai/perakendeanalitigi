from datetime import date

import pandas as pd
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
    assert hucre(df, "MA", "OPT3").str_orani == pytest.approx(0.25)  # 2/8
    # mükerrer satış payı şişirmez: MA-OPT1 4 satış / 16 sevk
    assert hucre(df, "MA", "OPT1").str_orani == pytest.approx(0.25)


def test_str_evren_disi_magaza_yok(con):
    # MF kapalı, MG henüz açılmamış, MH tadilatta, ONL online: sevkiyatları sayılmaz
    df = metrikler.strler(con, KARAR)
    assert set(df.magaza_id) == {"MA", "MB", "MC", "MD", "ME"}


def test_evren_disi_magaza_metrik_uretmez(con):
    p = Parametreler()
    for df in (metrikler.hizlar(con, KARAR, 8), metrikler.stok_fotografi(con, KARAR),
               metrikler.kiriklar(con, KARAR), metrikler.coverlar(con, KARAR, p)):
        assert not set(df.magaza_id) & {"MF", "MG", "MH", "ONL"}


def test_hayalet_stok_verici_olmaz(con):
    # MD-OPT3-1: yalnız karar günü, adet 7, varışsız, satışsız = hayalet.
    # Süzülmezse cover 999 ile verici olurdu.
    con.execute("insert into stok values ('2025-12-29', 'MD', 'OPT3-1', 7)")
    p = Parametreler()
    stok = metrikler.stok_fotografi(con, KARAR)
    assert set(stok[stok.magaza_id == "MD"].option_id) == {"OPT1"}
    cover = metrikler.coverlar(con, KARAR, p)
    assert ("MD", "OPT3") not in set(zip(cover.magaza_id, cover.option_id))
    # fikstürdeki hayalet (MD-OPT2-3, 12-15) hız penceresinde stoklu hafta üretmez
    hiz = metrikler.hizlar(con, KARAR, 8)
    assert len(hiz[(hiz.magaza_id == "MD") & (hiz.option_id == "OPT2")]) == 0


def test_std_option_kirik_sayilmaz(con):
    # OPT3 tek bedenli (sıra 1): ara kademesi yok, hiçbir koşulda kırık değil
    df = metrikler.kiriklar(con, KARAR)
    assert "OPT3" not in set(df.option_id)


def test_karar_sonrasi_satirlar_metrikleri_degistirmez(con, con_ileri):
    p = Parametreler()
    # karar günü satışı da sayılmaz (Ruling R6: fotoğraf o günün satışından önce)
    con_ileri.execute("insert into satis values (?, 'MA', 'OPT1-3', 9)", [KARAR])
    for f in (lambda c: metrikler.hizlar(c, KARAR, 8),
              lambda c: metrikler.strler(c, KARAR),
              lambda c: metrikler.stok_fotografi(c, KARAR),
              lambda c: metrikler.kiriklar(c, KARAR),
              lambda c: metrikler.coverlar(c, KARAR, p)):
        pd.testing.assert_frame_equal(
            f(con).sort_values(["magaza_id", "option_id"]).reset_index(drop=True),
            f(con_ileri).sort_values(["magaza_id", "option_id"]).reset_index(drop=True),
        )
