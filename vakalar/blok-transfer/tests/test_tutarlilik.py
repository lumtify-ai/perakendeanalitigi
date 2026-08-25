"""Gerçek veri setiyle tutarlılık: veri/README.md 431 kırık çift ilan ediyor."""
from blok_transfer.cekirdek import metrikler, veri


def test_kirik_cift_sayisi_readme_ile_tutarli():
    con = veri.baglan()
    assert len(metrikler.kiriklar(con, veri.karar_tarihi(con))) == 431
