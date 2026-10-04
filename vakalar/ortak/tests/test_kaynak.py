"""kaynak.py: salt okunur bağlantı, mükerrer ayıklama, çeşit hücreleri."""

import pytest

from perakende_analitik import kaynak


def test_baglan_yoksa_acik_hata(tmp_path):
    with pytest.raises(FileNotFoundError, match="lumoda-v4.duckdb"):
        kaynak.baglan(tmp_path / "yok.duckdb")


def test_mukerrer_satis_ayiklanir(oyuncak_con):
    # oyuncak satis'te (2025-01-07, M001, MDL0001-SYH-M, 2, ...) iki kez var
    ham = oyuncak_con.execute(
        "select count(*) from satis where tarih='2025-01-07' and magaza_id='M001' "
        "and urun_id='MDL0001-SYH-M' and adet>0").fetchone()[0]
    assert ham == 2
    ad = kaynak.temiz_satis(oyuncak_con)
    n = oyuncak_con.execute(f"select count(*) from {ad} where tarih='2025-01-07' "
                            "and magaza_id='M001' and urun_id='MDL0001-SYH-M' and adet>0").fetchone()[0]
    assert n == 1


def test_temiz_satis_baska_satirlara_dokunmaz(oyuncak_con):
    ad = kaynak.temiz_satis(oyuncak_con)
    ham = oyuncak_con.execute("select count(*) from satis").fetchone()[0]
    temiz = oyuncak_con.execute(f"select count(*) from {ad}").fetchone()[0]
    assert ham - temiz == 1


def test_hayalet_stok_cesitte_degil(oyuncak_con):
    # M002 × MDL0001-SYH-L: stok satırı var, hiç sevkiyat yok
    var = oyuncak_con.execute(
        "select count(*) from stok where magaza_id='M002' and urun_id='MDL0001-SYH-L'").fetchone()[0]
    assert var > 0
    ad = kaynak.cesit_hucreleri(oyuncak_con)
    assert ("M002", "MDL0001-SYH-L") not in set(
        oyuncak_con.execute(f"select magaza_id, urun_id from {ad}").fetchall())


def test_cesit_gercek_hucreler_ve_online(oyuncak_con):
    ad = kaynak.cesit_hucreleri(oyuncak_con)
    hucre = set(oyuncak_con.execute(f"select magaza_id, urun_id from {ad}").fetchall())
    assert ("M001", "MDL0001-SYH-M") in hucre
    # her SKU için ONL
    for s in ("S", "M", "L"):
        assert ("ONL", f"MDL0001-SYH-{s}") in hucre
    # depoya giden sevk (hedef DEPO) çeşit yapmaz
    assert not any(m == "DEPO" for m, _ in hucre)


def test_cesit_varissiz_satissiz_hucreler(oyuncak_con):
    """Varışı ve satışı olmayan hücreler: yalnız tek fotoğraflı, adet > 0 olan
    hayalettir. Hücreler M003'te (temel senaryoya dokunmaz)."""
    oyuncak_con.execute("""
        insert into stok values
          ('2025-01-06', 'M003', 'MDL0001-SYH-S', 2, 7),   -- (a) iki ayrı pazartesi, adet > 0
          ('2025-01-13', 'M003', 'MDL0001-SYH-S', 2, 7),
          ('2025-01-06', 'M003', 'MDL0001-SYH-M', 0, 0),   -- (b) tek fotoğraf, adet 0
          ('2025-01-06', 'M003', 'MDL0001-SYH-L', 3, 7),   -- (c) tek fotoğraf, adet > 0 + satış
          ('2025-01-06', 'M003', 'MDL0001-SYH-XL', 3, 7);  -- (d) hayalet: tek fotoğraf, adet > 0
        insert into satis values ('2025-01-08', 'M003', 'MDL0001-SYH-L', 1, 250, 0, NULL)""")
    assert oyuncak_con.execute(
        "select count(*) from sevkiyat where hedef = 'M003'").fetchone()[0] == 0
    ad = kaynak.cesit_hucreleri(oyuncak_con)
    hucre = set(oyuncak_con.execute(f"select magaza_id, urun_id from {ad}").fetchall())
    assert ("M003", "MDL0001-SYH-S") in hucre        # (a) çok fotoğraflı: gerçek
    assert ("M003", "MDL0001-SYH-M") in hucre        # (b) adet 0: hayalet olamaz
    assert ("M003", "MDL0001-SYH-L") in hucre        # (c) satışı var: gerçek
    assert ("M003", "MDL0001-SYH-XL") not in hucre   # (d) hayalet
    assert ("M002", "MDL0001-SYH-L") not in hucre    # temel senaryonun hayaleti


def test_cesit_varmayan_sevk_saymaz(oyuncak_con):
    # varis_tarihi boş (tek taraflı transfer / yolda) bir sevk hücreyi çeşide sokmaz
    oyuncak_con.execute(
        "insert into sevkiyat values ('2025-01-08', NULL, 'M001', 'M002', 'MDL0001-SYH-L', 1, "
        "'elle_transfer', NULL)")
    ad = kaynak.cesit_hucreleri(oyuncak_con)
    assert ("M002", "MDL0001-SYH-L") not in set(
        oyuncak_con.execute(f"select magaza_id, urun_id from {ad}").fetchall())


@pytest.mark.veri
def test_gercek_v4_mukerrer_sayisi(v4_con):
    # README: 200 mükerrer satış satırı
    ham = v4_con.execute("select count(*) from satis").fetchone()[0]
    temiz = v4_con.execute(f"select count(*) from {kaynak.temiz_satis(v4_con)}").fetchone()[0]
    assert ham - temiz == 200


@pytest.mark.veri
def test_gercek_v4_hayalet_stok_cesitte_degil(v4_con):
    # README: 150 hayalet stok satırı (çeşitte olmayan SKU'da pazartesi stoğu)
    ad = kaynak.cesit_hucreleri(v4_con)
    n = v4_con.execute(
        f"select count(*) from stok s anti join {ad} c "
        "on s.magaza_id::varchar = c.magaza_id and s.urun_id::varchar = c.urun_id").fetchone()[0]
    assert n == 150
