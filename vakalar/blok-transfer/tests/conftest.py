"""Mini Lumoda (v4 şeması): 5 evren mağazası + 3 evren dışı + ONL, 3 option,
8 haftalık geçmiş + karar günü fotoğrafı.

kayip_satis tablosu BİLEREK yok — çekirdek ona dokunamaz (spec §2).
Fikstür `gorunumler(c, KARAR)` çağırıp döner: testler ham tabloyu da (`stok`,
`satis`...), temiz `bt_*` görünümlerini de okuyabilir.
Beklenen değerler (Görev 4-7 testleri bu sayılara kilitli; v2 fikstürüyle aynı):
  hız:   MA-OPT1 0.5 · MB-OPT1 4.0 (iade netli) · MC-OPT1 1.0 (4 stoklu hafta)
         MD-OPT1 0.125 · MB-OPT2 3.0 · MC-OPT2 2.0 · MA-OPT2 hiç satış → satır yok
  karar günü stok: MA-OPT1 12 · MB-OPT1 5 (kırık) · MD-OPT1 10 · MA-OPT2 8
         MB-OPT2 1 (kırık) · MC-* 0
  kırıklar: (MB,OPT1) ve (MB,OPT2)
  STR:   MA-OPT1 0.25 · MB-OPT1 0.8 · MC-OPT1 1.0 · MA-OPT2 0.0 · MC-OPT2 1.0
  soğuma: (MD,OPT1) — 2025-12-22 sevkiyatı
  ME-OPT1 hız 2.0 · karar günü stok 5 · cover 2.5 · tam set
v4 ile eklenenler (v2 sayılarını değiştirmez):
  MA-OPT3    tek bedenli (`Standart`, sıra 1): stok 4, hız 0.25
  ONL        online satış satırları (evren dışı; `magaza_id = 'ONL'`)
  MF         kapalı (`kapanis_tarihi` < KARAR) · MG henüz açılmamış
  MH         karar anında tadilatta (`magaza_olay`); ME'nin tadilatı bitmiş, evrende kalır
  mükerrer   MA-OPT1-3 için 2025-11-03 satış satırının tam kopyası → hız yine 0.5
  hayalet    MD-OPT2-3: tek pazartesi (2025-12-15), adet 2, varışsız, satışsız
  Meşru hücreler hayalet sayılmasın diye (cesit: tek foto + adet>0 = hayalet),
  yalnız karar gününde görünen her SKU'ya HAFTALAR[0]'da adet-0 satırı eklenir;
  option toplamları değişmez.
"""
from datetime import date

import duckdb
import pytest

from blok_transfer.cekirdek.veri import gorunumler

KARAR = "2025-12-29"
HAFTALAR = ["2025-11-03", "2025-11-10", "2025-11-17", "2025-11-24",
            "2025-12-01", "2025-12-08", "2025-12-15", "2025-12-22"]


def _tablolar(c):
    c.execute("""create table magaza (magaza_id varchar, ad varchar, sehir varchar, tip varchar,
                 kapasite bigint, acilis_tarihi timestamp, kapanis_tarihi timestamp)""")
    c.execute("""create table magaza_olay (magaza_id varchar, olay varchar,
                 karar_tarihi timestamp, olay_tarihi timestamp, bitis_tarihi timestamp)""")
    c.execute("""create table urun (urun_id varchar, option_id varchar, model_adi varchar,
                 alt_kategori varchar, line varchar, sezon_kodu varchar, beden_seti varchar,
                 beden varchar, beden_sira bigint, liste_fiyati double, alis_fiyati double)""")
    c.execute("create table satis (tarih timestamp, magaza_id varchar, urun_id varchar, adet bigint)")
    c.execute("create table stok (tarih timestamp, magaza_id varchar, urun_id varchar, adet bigint)")
    c.execute("""create table sevkiyat (tarih timestamp, varis_tarihi timestamp, kaynak varchar,
                 hedef varchar, urun_id varchar, adet bigint, tip varchar)""")


def _sevk(c, tarih, hedef, urun_id, adet):
    """Depodan `hedef`e replenishment; varış tarihi = tarih."""
    c.execute("insert into sevkiyat values (?, ?, 'DEPO', ?, ?, ?, 'replenishment')",
              [tarih, tarih, hedef, urun_id, adet])


@pytest.fixture
def con():
    c = duckdb.connect()
    _tablolar(c)

    c.execute("""insert into magaza values
        ('MA', 'Mağaza A', 'İstanbul', 'Cadde', 1000, '2020-01-01', NULL),
        ('MB', 'Mağaza B', 'İstanbul', 'Cadde', 1000, '2020-01-01', NULL),
        ('MC', 'Mağaza C', 'Ankara', 'Outlet', 5000, '2020-01-01', NULL),
        ('MD', 'Mağaza D', 'Ankara', 'Cadde', 1000, '2020-01-01', NULL),
        ('ME', 'Mağaza E', 'İzmir', 'Cadde', 1000, '2020-01-01', NULL),
        ('MF', 'Mağaza F', 'İzmir', 'Cadde', 1000, '2020-01-01', '2025-12-01'),
        ('MG', 'Mağaza G', 'Bursa', 'Cadde', 1000, '2026-01-12', NULL),
        ('MH', 'Mağaza H', 'Bursa', 'Cadde', 1000, '2020-01-01', NULL),
        ('ONL', 'Online', NULL, 'Online', 0, '2020-01-01', NULL)""")
    c.execute("""insert into magaza_olay values
        ('MF', 'kapanis', '2025-10-20', '2025-12-01', NULL),
        ('MG', 'acilis', '2025-11-20', '2026-01-12', NULL),
        ('MH', 'tadilat', '2025-11-24', '2025-12-15', '2026-01-19'),
        ('ME', 'tadilat', '2025-05-05', '2025-06-02', '2025-07-07')""")

    # (option, line, beden_seti, beden sayısı)
    for opt, line, set_, n in [("OPT1", "Basic", "Giyim", 5), ("OPT2", "Outlet", "Giyim", 5),
                               ("OPT3", "Basic", "Standart", 1)]:
        for sira in range(1, n + 1):
            beden = "Standart" if set_ == "Standart" else ["XS", "S", "M", "L", "XL"][sira - 1]
            c.execute("insert into urun values (?, ?, ?, 'Tişört', ?, 'AW25', ?, ?, ?, 100.0, 40.0)",
                      [f"{opt}-{sira}", opt, f"Model {opt}", line, set_, beden, sira])

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
        ("MA", "OPT3"): [4],               # tek bedenli, 4
        ("MH", "OPT1"): [2, 2, 2, 2, 2],   # tadilatta: evren dışı
    }
    for (m, opt), adetler in karar_stok.items():
        for sira, adet in enumerate(adetler, start=1):
            c.execute("insert into stok values (?, ?, ?, ?)", [KARAR, m, f"{opt}-{sira}", adet])
            if sira > 1:
                # meşru hücre hayalet sayılmasın: erken haftaya adet-0 satırı
                # (foto sayısı 2 olur), option toplamı değişmez
                c.execute("insert into stok values (?, ?, ?, 0)", [HAFTALAR[0], m, f"{opt}-{sira}"])

    # --- geçmiş 8 haftanın stok fotoğrafları (option toplamı tek SKU'da) ---
    gecmis_stok = {("MA", "OPT1"): 12, ("MB", "OPT1"): 5, ("MD", "OPT1"): 10,
                   ("MA", "OPT2"): 8, ("MB", "OPT2"): 6, ("MC", "OPT2"): 5,
                   ("ME", "OPT1"): 5, ("MA", "OPT3"): 4, ("MH", "OPT1"): 10}
    for hafta in HAFTALAR:
        for (m, opt), adet in gecmis_stok.items():
            c.execute("insert into stok values (?, ?, ?, ?)", [hafta, m, f"{opt}-1", adet])
        # MC-OPT1 yalnız ilk 4 hafta stoklu
        mc1 = 3 if hafta in HAFTALAR[:4] else 0
        c.execute("insert into stok values (?, ?, 'OPT1-1', ?)", [hafta, "MC", mc1])

    # --- evren dışı mağazaların stoğu (kapalı MF, henüz açılmamış MG) ---
    for hafta in HAFTALAR[:4]:
        c.execute("insert into stok values (?, 'MF', 'OPT1-1', 6)", [hafta])
    c.execute("insert into stok values (?, 'MG', 'OPT1-1', 10)", [KARAR])

    # --- hayalet: MD'de çeşitte olmayan SKU, tek pazartesi, adet 2, varışsız, satışsız ---
    c.execute("insert into stok values ('2025-12-15', 'MD', 'OPT2-3', 2)")

    # --- satışlar (haftanın pazartesisine tarihli) ---
    for hafta in ["2025-11-03", "2025-11-17", "2025-12-01", "2025-12-15"]:
        c.execute("insert into satis values (?, 'MA', 'OPT1-3', 1)", [hafta])   # hız 0.5
    # mükerrer kayıt: 2025-11-03 satırının tam kopyası (temiz_satis düşürür)
    c.execute("insert into satis values ('2025-11-03', 'MA', 'OPT1-3', 1)")
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
    for hafta in ["2025-11-03", "2025-12-01"]:
        c.execute("insert into satis values (?, 'MA', 'OPT3-1', 1)", [hafta])   # hız 0.25
    # evren dışı: online (her SKU'yu satar), kapalı MF, tadilattaki MH
    for hafta in HAFTALAR:
        c.execute("insert into satis values (?, 'ONL', 'OPT1-3', 7)", [hafta])
        c.execute("insert into satis values (?, 'ONL', 'OPT2-1', 5)", [hafta])
    c.execute("insert into satis values ('2025-11-10', 'MF', 'OPT1-1', 2)")
    c.execute("insert into satis values ('2025-12-08', 'MH', 'OPT1-1', 3)")

    # --- sevkiyat (STR paydaları + soğuma); varış tarihi = tarih ---
    _sevk(c, "2025-10-06", "MA", "OPT1-1", 16)   # STR 4/16
    _sevk(c, "2025-10-06", "MB", "OPT1-1", 40)   # STR 32/40
    _sevk(c, "2025-10-06", "MC", "OPT1-1", 4)    # STR 4/4
    _sevk(c, "2025-10-06", "MA", "OPT2-1", 8)    # STR 0/8
    _sevk(c, "2025-10-06", "MC", "OPT2-1", 16)   # STR 16/16
    _sevk(c, "2025-12-22", "MD", "OPT1-1", 5)    # SOĞUMA
    _sevk(c, "2025-10-06", "ME", "OPT1-1", 20)   # STR 16/20
    _sevk(c, "2025-10-06", "MA", "OPT3-1", 8)
    # evren dışı mağazalara sevkiyat
    _sevk(c, "2025-10-06", "MF", "OPT1-1", 12)
    _sevk(c, "2025-12-22", "MG", "OPT1-1", 10)
    _sevk(c, "2025-10-06", "MH", "OPT1-1", 10)

    gorunumler(c, date.fromisoformat(KARAR))
    return c


@pytest.fixture
def con_ileri(con):
    """`con` + karar sonrası (karar+1 hafta) satış, varış ve stok fotoğrafı.

    Çekirdeğin karar anından sonrasına bakmadığını kilitlemek için (Görev 4);
    görünümler tarih sınırı koymaz, bu satırlar `bt_*` içinde görünür."""
    sonraki = "2026-01-05"
    con.execute("insert into satis values (?, 'MA', 'OPT1-3', 9)", [sonraki])
    con.execute("insert into satis values (?, 'MB', 'OPT1-3', 9)", [sonraki])
    con.execute("insert into sevkiyat values (?, ?, 'DEPO', 'MB', 'OPT1-1', 20, 'replenishment')",
                [sonraki, sonraki])
    for opt in ("OPT1", "OPT2"):
        for sira in range(1, 6):
            con.execute("insert into stok values (?, 'MB', ?, 4)", [sonraki, f"{opt}-{sira}"])
    return con


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
