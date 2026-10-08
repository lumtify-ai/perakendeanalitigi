from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from blok_transfer.cekirdek import veri
from blok_transfer.cekirdek.parametreler import Parametreler

from conftest import HAFTALAR, KARAR

KARAR_TARIHI = date.fromisoformat(KARAR)
EVREN = {"MA", "MB", "MC", "MD", "ME"}


def test_varsayilan_parametreler():
    p = Parametreler()
    assert p.hiz_penceresi_hafta == 8
    assert p.ufuk_hafta == 8
    assert p.soguma_hafta == 2
    assert p.min_koli == 6
    assert p.adet_maliyeti_tl == 25.0
    assert p.rota_sabiti_tl == 500.0
    assert p.buyuk_cover == 999.0
    assert p.verici_cover_esigi == 6.0
    assert p.alici_cover_tavani == 0.0
    assert p.min_satis == 1.0
    # v4 ile gelenler
    assert p.tepe_hafta == 52
    assert p.olcum_hafta == 8
    assert p.mip_zaman_limiti_sn == 3600
    assert p.mip_dugum_limiti == 50_000            # Görev 5 ölçümü (kayıt defteri, Ruling)


# --- karar anı (spec §3.1) -------------------------------------------------

def _takvimli(son_foto: date, indirim: date = date(2025, 12, 1)):
    """Sentetik: pazartesi fotoğrafları 2025-09-01 .. son_foto; AW25 2026 başına
    dek, sonra SS26. Üç dalganın indirimi aynı."""
    c = duckdb.connect()
    c.execute("create table stok (tarih timestamp, magaza_id varchar, urun_id varchar, adet bigint)")
    c.execute("create table takvim (tarih timestamp, sezon_kodu varchar)")
    c.execute("""create table sezon (sezon_kodu varchar, dalga bigint, lansman_tarihi timestamp,
                 indirim_baslangic timestamp, cikis_tarihi timestamp)""")
    t = date(2025, 9, 1)
    while t <= son_foto:
        c.execute("insert into stok values (?, 'MA', 'U1', 1)", [t])
        t += timedelta(days=7)
    t = date(2025, 8, 1)
    while t <= date(2026, 3, 1):
        c.execute("insert into takvim values (?, ?)", [t, "AW25" if t < date(2026, 1, 1) else "SS26"])
        t += timedelta(days=1)
    for dalga in (1, 2, 3):
        c.execute("insert into sezon values ('AW25', ?, '2025-08-18', ?, '2026-02-23')", [dalga, indirim])
    c.execute("insert into sezon values ('SS26', 1, '2026-02-02', '2026-06-01', '2026-07-01')")
    return c


def test_karar_ani_kurali():
    # Son fotoğraf 2026-01-12: ileri pencere (8 hafta) için t <= 2025-11-17.
    # 11-24: pencere eksik; 12-01 ve sonrası: indirim başladı (t < indirim sert);
    # 2026'daki pazartesiler: SS26. En geç olan 11-17.
    c = _takvimli(date(2026, 1, 12))
    assert veri.karar_ani(c) == date(2025, 11, 17)


def test_karar_ani_indirimle_sinirlanir():
    # Pencere 4 hafta: 12-15'e dek uygun, ama 12-01 indirimi başlamış: 11-24.
    c = _takvimli(date(2026, 1, 12))
    assert veri.karar_ani(c, olcum_hafta=4) == date(2025, 11, 24)


def test_karar_ani_ileri_pencere_eksikse_geri_gelir():
    # Stok 2025-12-29'da bitiyor: t <= 2025-11-03.
    c = _takvimli(date(2025, 12, 29))
    assert veri.karar_ani(c) == date(2025, 11, 3)


def test_karar_ani_yoksa_hata():
    c = _takvimli(date(2026, 1, 12))
    with pytest.raises(ValueError, match="AW25"):
        veri.karar_ani(c, olcum_hafta=40)
    with pytest.raises(ValueError, match="XX99"):
        veri.karar_ani(c, sezon_kodu="XX99")


# --- evren ------------------------------------------------------------------

def test_evren_online_kapali_acilmamis_tadilat_disarida(con):
    magazalar = {r[0] for r in con.execute("select magaza_id from bt_magaza").fetchall()}
    assert magazalar == EVREN
    # ME'nin tadilatı bitmiş: evrende kalır. MF kapalı, MG açılmamış, MH tadilatta, ONL online.
    assert {"ONL", "MF", "MG", "MH"}.isdisjoint(magazalar)
    tipler = dict(con.execute("select magaza_id, tip from bt_magaza").fetchall())
    assert tipler["MC"] == "Outlet" and tipler["MA"] == "Cadde"


def test_evren_disi_magazalarin_satiri_gorunumlerde_yok(con):
    for gorunum in ("bt_stok", "bt_satis", "bt_sevkiyat"):
        magazalar = {r[0] for r in con.execute(f"select distinct magaza_id from {gorunum}").fetchall()}
        assert magazalar <= EVREN, gorunum
    # ham tabloda ise varlar (görünüm gerçekten süzüyor)
    ham = {r[0] for r in con.execute("select distinct magaza_id from satis").fetchall()}
    assert {"ONL", "MF", "MH"} <= ham


# --- kirli kayıtlar -----------------------------------------------------------

def test_mukerrer_satis_hizi_degistirmez(con):
    ham = con.execute("select sum(adet) from satis where magaza_id = 'MA' and urun_id like 'OPT1-%'").fetchone()[0]
    temiz = con.execute("select sum(adet) from bt_satis where magaza_id = 'MA' and urun_id like 'OPT1-%'").fetchone()[0]
    assert ham == 5          # mükerrer kopya ham tabloda var
    assert temiz == 4        # görünümde düşer
    assert temiz / 8 == 0.5  # hız (8 haftalık pencere)


def test_hayalet_stok_gorunumde_yok(con):
    assert con.execute("select count(*) from stok where magaza_id='MD' and urun_id='OPT2-3'").fetchone()[0] == 1
    assert con.execute("select count(*) from bt_stok where magaza_id='MD' and urun_id='OPT2-3'").fetchone()[0] == 0


def test_fikstur_karar_gunu_mesru_satirlar_bt_stokta_kalir(con):
    """Fikstürün meşru karar-günü SKU satırları hayalet sayılıp düşmemeli;
    aksi halde beklenen bütün sayılar sessizce değişir."""
    beklenen = {tuple(r) for r in con.execute(
        "select magaza_id, urun_id, adet from stok where tarih = ? and magaza_id in "
        "('MA','MB','MC','MD','ME')", [KARAR]).fetchall()}
    kalan = {tuple(r) for r in con.execute(
        "select magaza_id, urun_id, adet from bt_stok where tarih = ?", [KARAR]).fetchall()}
    assert beklenen and beklenen == kalan
    # option toplamları: MA-OPT1 12, MB-OPT1 5, MD-OPT1 10, MA-OPT2 8, MB-OPT2 1, ME-OPT1 5, MA-OPT3 4
    toplam = {(m, o): t for m, o, t in con.execute(
        "select b.magaza_id, u.option_id, sum(b.adet) from bt_stok b join urun u using (urun_id) "
        "where b.tarih = ? group by 1, 2", [KARAR]).fetchall()}
    assert toplam[("MA", "OPT1")] == 12 and toplam[("MB", "OPT1")] == 5
    assert toplam[("MD", "OPT1")] == 10 and toplam[("MA", "OPT2")] == 8
    assert toplam[("MB", "OPT2")] == 1 and toplam[("ME", "OPT1")] == 5
    assert toplam[("MA", "OPT3")] == 4


# --- sevkiyat -----------------------------------------------------------------

def test_sevkiyat_varis_tarihli_ve_hedefli(con):
    con.execute("insert into sevkiyat values ('2025-12-15', '2025-12-17', 'DEPO', 'MB', 'OPT2-2', 7, 'replenishment')")
    con.execute("insert into sevkiyat values ('2025-12-15', NULL, 'DEPO', 'MB', 'OPT2-3', 9, 'replenishment')")  # yolda
    veri.gorunumler(con, KARAR_TARIHI)
    satirlar = con.execute(
        "select tarih, magaza_id, urun_id, adet, tip from bt_sevkiyat where urun_id in ('OPT2-2','OPT2-3')"
    ).fetchall()
    assert [(r[1], r[2], r[3], r[4]) for r in satirlar] == [("MB", "OPT2-2", 7, "replenishment")]
    assert satirlar[0][0].date() == date(2025, 12, 17)      # tarih = varış tarihi
    assert con.execute("select count(*) from bt_sevkiyat where tarih is null").fetchone()[0] == 0


# --- gerçek veri ----------------------------------------------------------------

@pytest.mark.veri
def test_gercek_veride_karar_ani():
    con = veri.baglan()
    assert veri.karar_ani(con) == date(2025, 11, 3)


@pytest.mark.veri
def test_gercek_veride_evren_ve_gorunumler():
    con = veri.baglan()
    karar = veri.karar_ani(con)
    veri.gorunumler(con, karar)
    n, = con.execute("select count(*) from bt_magaza").fetchone()
    assert 70 <= n <= 84
    assert con.execute("select count(*) from bt_magaza where magaza_id = 'ONL'").fetchone()[0] == 0
    assert con.execute("select count(*) from bt_stok where magaza_id = 'ONL'").fetchone()[0] == 0
    # hayalet ve mükerrer düşer: temiz görünümler ham tablodan küçük
    assert con.execute("select count(*) from bt_satis").fetchone()[0] < con.execute("select count(*) from satis").fetchone()[0]
    assert con.execute("select count(*) from bt_stok").fetchone()[0] < con.execute("select count(*) from stok").fetchone()[0]


def test_dosya_yoksa_acik_hata():
    with pytest.raises(FileNotFoundError, match="perakende_veri.v4.uret"):
        veri.baglan(Path("yok/boyle/bir.duckdb"))
