"""Mini Lumoda: 5 mağaza, 2 option, 8 haftalık geçmiş + karar günü fotoğrafı.

kayip_satis tablosu BİLEREK yok — çekirdek ona dokunamaz (spec §2).
Beklenen değerler (Task 2-7 testleri bu sayılara kilitli):
  hız:   MA-OPT1 0.5 · MB-OPT1 4.0 (iade netli) · MC-OPT1 1.0 (4 stoklu hafta)
         MD-OPT1 0.125 · MB-OPT2 3.0 · MC-OPT2 2.0 · MA-OPT2 hiç satış → satır yok
  karar günü stok: MA-OPT1 12 · MB-OPT1 5 (kırık) · MD-OPT1 10 · MA-OPT2 8
         MB-OPT2 1 (kırık) · MC-* 0
  kırıklar: (MB,OPT1) ve (MB,OPT2)
  STR:   MA-OPT1 0.25 · MB-OPT1 0.8 · MC-OPT1 1.0 · MA-OPT2 0.0 · MC-OPT2 1.0
  soğuma: (MD,OPT1) — 2025-12-22 sevkiyatı
  ME-OPT1 hız 2.0 · karar günü stok 5 · cover 2.5 · tam set
"""
import duckdb
import pytest

KARAR = "2025-12-29"
HAFTALAR = ["2025-11-03", "2025-11-10", "2025-11-17", "2025-11-24",
            "2025-12-01", "2025-12-08", "2025-12-15", "2025-12-22"]


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("create table magaza (magaza_id varchar, tip varchar, kapasite bigint)")
    c.execute("""create table urun (urun_id varchar, option_id varchar, line varchar,
                 beden_sira bigint, liste_fiyati double)""")
    c.execute("create table satis (tarih timestamp, magaza_id varchar, urun_id varchar, adet bigint)")
    c.execute("create table stok (tarih timestamp, magaza_id varchar, urun_id varchar, adet bigint)")
    c.execute("create table sevkiyat (tarih timestamp, magaza_id varchar, urun_id varchar, adet bigint)")

    c.execute("""insert into magaza values
        ('MA', 'Cadde', 1000), ('MB', 'Cadde', 1000),
        ('MC', 'Outlet', 5000), ('MD', 'Cadde', 1000),
        ('ME', 'Cadde', 1000)""")

    for opt, line in [("OPT1", "Basic"), ("OPT2", "Outlet")]:
        for sira in range(1, 6):
            c.execute("insert into urun values (?, ?, ?, ?, 100.0)",
                      [f"{opt}-{sira}", opt, line, sira])

    # --- karar günü stok fotoğrafı (SKU düzeyi; sıfır satırlar dahil) ---
    karar_stok = {
        ("MA", "OPT1"): [3, 2, 3, 2, 2],   # tam set, 12
        ("MB", "OPT1"): [2, 0, 0, 0, 3],   # kırık, 5
        ("MC", "OPT1"): [0, 0, 0, 0, 0],
        ("MD", "OPT1"): [2, 2, 2, 2, 2],   # tam set, 10
        ("MA", "OPT2"): [2, 1, 2, 1, 2],   # tam set, 8
        ("MB", "OPT2"): [1, 0, 0, 0, 0],   # kırık, 1
        ("MC", "OPT2"): [0, 0, 0, 0, 0],
        ("ME", "OPT1"): [1, 1, 1, 1, 1],   # tam set, 5 — hızlı satan, cover 2.5
    }
    for (m, opt), adetler in karar_stok.items():
        for sira, adet in enumerate(adetler, start=1):
            c.execute("insert into stok values (?, ?, ?, ?)", [KARAR, m, f"{opt}-{sira}", adet])

    # --- geçmiş 8 haftanın stok fotoğrafları (option toplamı tek SKU'da) ---
    gecmis_stok = {("MA", "OPT1"): 12, ("MB", "OPT1"): 5, ("MD", "OPT1"): 10,
                   ("MA", "OPT2"): 8, ("MB", "OPT2"): 6, ("MC", "OPT2"): 5,
                   ("ME", "OPT1"): 5}
    for hafta in HAFTALAR:
        for (m, opt), adet in gecmis_stok.items():
            c.execute("insert into stok values (?, ?, ?, ?)", [hafta, m, f"{opt}-1", adet])
        # MC-OPT1 yalnız ilk 4 hafta stoklu
        mc1 = 3 if hafta in HAFTALAR[:4] else 0
        c.execute("insert into stok values (?, ?, 'OPT1-1', ?)", [hafta, "MC", mc1])

    # --- satışlar (haftanın pazartesisine tarihli) ---
    for hafta in ["2025-11-03", "2025-11-17", "2025-12-01", "2025-12-15"]:
        c.execute("insert into satis values (?, 'MA', 'OPT1-3', 1)", [hafta])   # hız 0.5
    for hafta in HAFTALAR:                                                       # MB-OPT1: 4/hafta
        if hafta == "2025-12-08":
            c.execute("insert into satis values (?, 'MB', 'OPT1-3', 5)", [hafta])
            c.execute("insert into satis values (?, 'MB', 'OPT1-3', -1)", [hafta])  # iade
        else:
            c.execute("insert into satis values (?, 'MB', 'OPT1-3', 4)", [hafta])
    for hafta in HAFTALAR[:4]:                                                   # MC-OPT1: stoklu 4 haftada 1'er
        c.execute("insert into satis values (?, 'MC', 'OPT1-2', 1)", [hafta])
    c.execute("insert into satis values ('2025-11-03', 'MD', 'OPT1-1', 1)")      # hız 0.125
    for hafta in HAFTALAR:
        c.execute("insert into satis values (?, 'MB', 'OPT2-1', 3)", [hafta])    # hız 3
        c.execute("insert into satis values (?, 'MC', 'OPT2-1', 2)", [hafta])    # hız 2
        c.execute("insert into satis values (?, 'ME', 'OPT1-2', 2)", [hafta])   # hız 2.0

    # --- sevkiyat (STR paydaları + soğuma) ---
    c.execute("insert into sevkiyat values ('2025-10-06', 'MA', 'OPT1-1', 16)")  # STR 4/16
    c.execute("insert into sevkiyat values ('2025-10-06', 'MB', 'OPT1-1', 40)")  # STR 32/40
    c.execute("insert into sevkiyat values ('2025-10-06', 'MC', 'OPT1-1', 4)")   # STR 4/4
    c.execute("insert into sevkiyat values ('2025-10-06', 'MA', 'OPT2-1', 8)")   # STR 0/8
    c.execute("insert into sevkiyat values ('2025-10-06', 'MC', 'OPT2-1', 16)")  # STR 16/16
    c.execute("insert into sevkiyat values ('2025-12-22', 'MD', 'OPT1-1', 5)")   # SOĞUMA
    c.execute("insert into sevkiyat values ('2025-10-06', 'ME', 'OPT1-1', 20)")  # STR 16/20
    return c


@pytest.fixture
def con_kayipli(con):
    """`con` + kayip_satis tablosu.

    Çekirdek fikstüründe (`con`) bu tablo BİLEREK yoktur: çekirdeğin ona
    dokunmadığı böyle kilitlenir (spec §2). Değerlendirme katmanı ise onu
    okumak zorunda; ölçüt oradan gelir. İki fikstür bu ayrımı korur.
    """
    con.execute(
        "create table kayip_satis (tarih timestamp, magaza_id varchar, "
        "urun_id varchar, kayip_adet bigint)"
    )
    con.execute("insert into kayip_satis values ('2025-12-01', 'MB', 'OPT1-3', 12)")
    con.execute("insert into kayip_satis values ('2025-12-01', 'MC', 'OPT2-2', 6)")
    con.execute("insert into kayip_satis values ('2025-12-01', 'MD', 'OPT2-1', 2)")
    return con
