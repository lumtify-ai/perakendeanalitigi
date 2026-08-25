"""Gerçek veri setiyle tutarlılık: veri/README.md 431 kırık çift ilan ediyor."""
from dataclasses import replace

import pytest

from blok_transfer import degerlendirme
from blok_transfer.cekirdek import metrikler, veri
from blok_transfer.cekirdek.parametreler import Parametreler


def test_kirik_cift_sayisi_readme_ile_tutarli():
    con = veri.baglan()
    assert len(metrikler.kiriklar(con, veri.karar_tarihi(con))) == 431


def test_gercek_veride_mip_greedyden_kotu_olamaz():
    con = veri.baglan()
    karar = veri.karar_tarihi(con)
    p = Parametreler()  # cover 6, min_satis 1 — orta senaryo
    g_plan, g_ozet = degerlendirme.boru_hatti(con, karar, p, "greedy")
    m_plan, m_ozet = degerlendirme.boru_hatti(con, karar, p, "mip")
    assert len(g_plan.hareketler) > 0, "orta senaryoda hic hareket cikmamasi supheli"
    if m_plan.durum == "optimal":
        assert m_ozet["net_kazanc_tl"] >= g_ozet["net_kazanc_tl"] - 1e-6
