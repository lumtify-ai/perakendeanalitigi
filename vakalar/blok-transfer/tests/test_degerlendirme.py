from datetime import date

import duckdb
import pandas as pd
import pytest

from blok_transfer import degerlendirme
from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cozuculer.tip import Plan

KARAR = date(2025, 12, 29)
P = Parametreler()


def ornek_plan():
    return Plan(
        hareketler=pd.DataFrame([
            dict(verici="MA", alici="MB", option_id="OPT1", adet=12, w=500.0),
            dict(verici="MA", alici="MC", option_id="OPT2", adet=8, w=600.0),
        ]),
        durum="optimal",
        sure_sn=0.01,
    )


def test_ozet_metikleri():
    ozet = degerlendirme.ozetle(ornek_plan(), P)
    assert ozet["option_sayisi"] == 2
    assert ozet["tasinan_adet"] == 20
    assert ozet["bosalan_magaza"] == 1                       # tek verici: MA
    assert ozet["net_kazanc_tl"] == pytest.approx(1100 - 2 * 500)  # 2 rota sabiti
    assert ozet["sure_sn"] == pytest.approx(0.01)


def test_kayip_satis_yalniz_burada_okunur():
    # Ayrı mini con: urun + kayip_satis (çekirdek fikstüründe bu tablo YOK)
    c = duckdb.connect()
    c.execute("create table urun (urun_id varchar, option_id varchar)")
    for opt in ("OPT1", "OPT2"):
        for sira in range(1, 6):
            c.execute("insert into urun values (?, ?)", [f"{opt}-{sira}", opt])
    c.execute("create table kayip_satis (tarih timestamp, magaza_id varchar, urun_id varchar, kayip_adet bigint)")
    c.execute("insert into kayip_satis values ('2025-12-01', 'MB', 'OPT1-3', 12)")
    c.execute("insert into kayip_satis values ('2025-12-01', 'MC', 'OPT2-2', 6)")
    c.execute("insert into kayip_satis values ('2025-12-01', 'MC', 'OPT1-2', 2)")
    c.execute("insert into kayip_satis values ('2025-12-01', 'MD', 'OPT2-1', 5)")
    c.execute("insert into kayip_satis values ('2025-01-05', 'MB', 'OPT1-3', 99)")  # pencere dışı
    oran = degerlendirme.kayip_satis_yakalama(ornek_plan(), c, KARAR)
    assert oran == pytest.approx(18 / 25)                    # (12+6) / (12+6+2+5)


def test_boru_hatti_fiksturde_mip_rotayi_birlestirir(con):
    # Mini evren rota konsolidasyonunu kendiliğinden gösterir:
    # greedy skora bakar → OPT1→MB (500) + OPT2→MC (600), 2 rota → net 100.
    # MIP rota sabitini görür → OPT1 ve OPT2 birlikte MC'ye, 1 rota →
    # (100 + 600) − 500 = 200.
    g_plan, g_ozet = degerlendirme.boru_hatti(con, KARAR, P, "greedy")
    assert set(zip(g_plan.hareketler.alici, g_plan.hareketler.option_id)) == {
        ("MB", "OPT1"), ("MC", "OPT2")
    }
    assert g_ozet["net_kazanc_tl"] == pytest.approx(100.0)

    m_plan, m_ozet = degerlendirme.boru_hatti(con, KARAR, P, "mip")
    assert m_plan.durum == "optimal"
    assert set(zip(m_plan.hareketler.alici, m_plan.hareketler.option_id)) == {
        ("MC", "OPT1"), ("MC", "OPT2")
    }
    assert m_ozet["net_kazanc_tl"] == pytest.approx(200.0)
