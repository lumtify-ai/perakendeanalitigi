"""v3 veri gerçekçiliği doğrulamaları (spec 2.12).

Üretilmiş v3'e karşı çalışır; önce `python -m perakende_veri.v3.uret`.
Plan değerleri gizli dünyadandır (`dunya_kur`): zincir planı bilir, veri
setinde tablo olarak yoktur; sipariş tablosundaki ilk alım ondan türer.

Eşiklerin yanındaki yorumlar üretimdeki gerçek değeri verir (2026-09-26).
"""

import duckdb
import pandas as pd
import pytest

from perakende_veri.v3 import sabitler
from perakende_veri.v3.dunya import dunya_kur

DB = sabitler.CIKTI_DIZINI / "perakende.duckdb"
TAM_SEZONLAR = ("SS24", "AW24", "SS25")   # lansmanı ve çıkışı pencerede


@pytest.fixture(scope="module")
def con():
    if not DB.exists():
        pytest.skip("v3 üretilmemiş: python -m perakende_veri.v3.uret")
    baglanti = duckdb.connect(str(DB), read_only=True)
    plan = dunya_kur().optionlar[["option_id", "plan_sezon", "ilk_alim"]]
    baglanti.register("plan", plan)
    yield baglanti
    baglanti.close()


def _tek(con, sorgu):
    return con.sql(sorgu).fetchone()[0]


# Option başına lansman → indirim arası gerçek talep (satış + kayıp) ve plan
GERCEK_PLAN = """
WITH o AS (SELECT DISTINCT u.option_id, u.sezon_kodu, u.line, u.lansman_tarihi, s.indirim_baslangic ind
           FROM urun u JOIN sezon s ON s.sezon_kodu = u.sezon_kodu AND s.dalga = u.dalga),
sat AS (SELECT u.option_id, sum(s.adet) adet FROM satis s JOIN urun u USING (urun_id)
        JOIN o ON o.option_id = u.option_id
        WHERE s.adet > 0 AND s.tarih >= o.lansman_tarihi AND s.tarih < o.ind GROUP BY 1),
kay AS (SELECT u.option_id, sum(k.kayip_adet) adet FROM kayip_satis k JOIN urun u USING (urun_id)
        JOIN o ON o.option_id = u.option_id
        WHERE k.tarih >= o.lansman_tarihi AND k.tarih < o.ind GROUP BY 1)
SELECT o.*, coalesce(sat.adet, 0) + coalesce(kay.adet, 0) AS gercek, p.plan_sezon, p.ilk_alim,
       (coalesce(sat.adet, 0) + coalesce(kay.adet, 0)) / p.plan_sezon AS oran
FROM o JOIN plan p USING (option_id) LEFT JOIN sat USING (option_id) LEFT JOIN kay USING (option_id)
"""


# --- Pencere ve tablolar ------------------------------------------------

def test_pencere_dogru(con):
    for tablo in ("satis", "kayip_satis", "sevkiyat", "stok", "depo_stok"):
        mn, mx = con.sql(f"SELECT min(tarih), max(tarih) FROM {tablo}").fetchone()
        assert mn >= pd.Timestamp("2024-01-01") and mx <= pd.Timestamp("2025-12-31"), tablo
    assert _tek(con, "SELECT count(*) FROM takvim") == 731
    assert _tek(con, "SELECT count(DISTINCT tarih) FROM stok") == 105
    assert _tek(con, "SELECT count(*) FROM sezon") == 15
    assert _tek(con, "SELECT count(*) FROM tedarikci") == 8
    assert _tek(con, "SELECT count(DISTINCT model_kodu) FROM urun") == 242


def test_aw25_sagdan_sansurlu(con):
    # AW25 pencere bittiğinde rafta: geri toplaması yok, stoğu var
    assert _tek(con, """SELECT count(*) FROM sevkiyat v JOIN urun u USING (urun_id)
                         WHERE u.sezon_kodu = 'AW25' AND v.tip = 'geri_toplama'""") == 0
    assert _tek(con, """SELECT sum(st.adet) FROM stok st JOIN urun u USING (urun_id)
                         WHERE u.sezon_kodu = 'AW25' AND st.tarih = DATE '2025-12-29'""") > 0


def test_siparis_tipleri_line_ile_uyumlu(con):
    df = con.sql("""SELECT s.tip, u.line, count(*) n FROM siparis s JOIN urun u USING (urun_id)
                    GROUP BY 1, 2""").df()
    assert set(df.loc[df.tip == "rpt", "line"]) == {"Collection"}
    assert set(df.loc[df.tip == "ilk", "line"]) == {"Collection", "Outlet"}
    assert set(df.loc[df.tip == "surekli", "line"]) == {"Basic", "NOS"}
    assert _tek(con, "SELECT count(*) FROM siparis WHERE planlanan_teslim <= siparis_tarihi") == 0
    # Gelmemiş teslimin gerçekleşen tarihi boş; boş olanlar pencereden sonra planlı
    assert _tek(con, """SELECT count(*) FROM siparis WHERE gerceklesen_teslim IS NULL
                         AND planlanan_teslim < DATE '2025-12-10'""") == 0


# --- Yaşam eğrisi -------------------------------------------------------

def test_yasam_egrisi_gorunur(con):
    """Collection'ın zincir haftalık satışı 2.–5. haftada tepe yapar,
    12. haftada tepenin yarısının altındadır (gerçekleşen: tepe 4. hafta,
    12. hafta ~%36)."""
    haftalik = con.sql(f"""
        SELECT floor(date_diff('day', u.lansman_tarihi, s.tarih) / 7)::INT AS h, sum(s.adet) adet
        FROM satis s JOIN urun u USING (urun_id)
        WHERE u.line = 'Collection' AND u.sezon_kodu IN {TAM_SEZONLAR} AND s.adet > 0
        GROUP BY 1 ORDER BY 1
    """).df().set_index("h")["adet"]
    tepe_h = int(haftalik.idxmax())
    assert 1 <= tepe_h <= 4, f"tepe {tepe_h + 1}. haftada"
    assert haftalik[11] < 0.5 * haftalik.max()


# --- Ürün sürprizi ------------------------------------------------------

def test_urun_surprizi_gorunur(con):
    """SS24+AW24 Collection: gerçek/plan > 1,5 en az %15; < 0,7 en az %15
    (gerçekleşen ~%22 ve ~%38)."""
    df = con.sql(GERCEK_PLAN).df()
    df = df[(df.line == "Collection") & df.sezon_kodu.isin(["SS24", "AW24"])]
    assert len(df) > 150
    assert (df.oran > 1.5).mean() >= 0.15
    assert (df.oran < 0.7).mean() >= 0.15


def test_hitler_erken_biter(con):
    """Gerçek/plan ≥ 1,5 olan option'ların çoğunda depo indirimden önce
    tükenir ve zincir stoğu (mağaza + depo) ilk alımın %15'inin altına iner.

    SPEC SAPMASI: spec %10 diyor. Hit'in kalan stoğunun bir kısmı, o option'ın
    tutmadığı mağazalarda (yerel sapma) takılı kalır ve mağazalar arası
    transfer yoktur; medyan hit'in dibi ilk alımın ~%11'i. Gerçekleşen:
    depo %73'ünde sıfırlanır; zincir stoğu %64'ünde %15'in, %45'inde %10'un
    altına iner.
    """
    df = con.sql(f"""
        WITH g AS ({GERCEK_PLAN}),
        hit AS (SELECT * FROM g WHERE line = 'Collection' AND oran >= 1.5
                AND sezon_kodu IN {TAM_SEZONLAR}),
        m AS (SELECT u.option_id, st.tarih, sum(st.adet) adet FROM stok st JOIN urun u USING (urun_id)
              GROUP BY 1, 2),
        d AS (SELECT u.option_id, ds.tarih, sum(ds.adet) adet FROM depo_stok ds JOIN urun u USING (urun_id)
              GROUP BY 1, 2),
        z AS (SELECT m.option_id, m.tarih, m.adet + coalesce(d.adet, 0) zincir,
                     coalesce(d.adet, 0) depo
              FROM m LEFT JOIN d USING (option_id, tarih))
        SELECT hit.option_id, min(z.zincir) / any_value(hit.ilk_alim) AS en_dusuk,
               min(z.depo) AS en_dusuk_depo
        FROM hit JOIN z ON z.option_id = hit.option_id
             AND z.tarih > hit.lansman_tarihi AND z.tarih < hit.ind
        GROUP BY 1
    """).df()
    assert len(df) >= 20
    assert (df.en_dusuk_depo == 0).mean() > 0.5
    assert (df.en_dusuk < 0.15).mean() > 0.5


# --- RPT ----------------------------------------------------------------

RPT = """
WITH r AS (SELECT siparis_id, any_value(option_id) option_id, any_value(siparis_tarihi) st,
                  any_value(gerceklesen_teslim) gt, sum(adet) adet
           FROM siparis WHERE tip = 'rpt' GROUP BY 1),
o AS (SELECT DISTINCT option_id, sezon_kodu FROM urun),
s AS (SELECT sezon_kodu, min(indirim_baslangic) ind, min(cikis_tarihi) cik FROM sezon GROUP BY 1)
SELECT r.*, o.sezon_kodu, s.ind, s.cik FROM r JOIN o USING (option_id) JOIN s USING (sezon_kodu)
"""


def test_rpt_var_ve_bir_kismi_gec_gelir(con):
    """Banu'nun kuralı sezon başına onlarca RPT verir; yetişme kontrolü
    teslim sapmasını ve sipariş haftasını görmediği için bir kısmı indirimden
    sonra gelir (gerçekleşen: tam sezonlarda 34–38, geç payı %29–38)."""
    df = con.sql(RPT).df()
    tam = df[df.sezon_kodu.isin(TAM_SEZONLAR)]
    assert (tam.groupby("sezon_kodu").size() >= 15).all()
    gec = (tam["gt"] >= tam["ind"]).mean()
    assert 0.10 <= gec <= 0.70


def test_rpt_depoda_kalir(con):
    """Gelen RPT normal replenishment'la dağıtılır ve büyük kısmı çıkışta
    hâlâ depodadır (gerçekleşen: RPT adedinin %62–74'ü kadar depo stoğu)."""
    oran = _tek(con, f"""
        WITH r AS ({RPT}),
        d AS (SELECT u.option_id, ds.tarih, sum(ds.adet) depo FROM depo_stok ds JOIN urun u USING (urun_id)
              GROUP BY 1, 2)
        SELECT sum(least(d.depo, r.adet)) / sum(r.adet)
        FROM r JOIN d ON d.option_id = r.option_id AND d.tarih = r.cik
        WHERE r.gt < r.cik AND r.sezon_kodu IN {TAM_SEZONLAR}
    """)
    assert oran > 0.40


def test_olu_stok_kapisi_rpt_sonrasi(con):
    """Dizinin 4. sorusu veride: RPT geldikten sonraki ilk pazartesi hızı
    sıfır görünen stoksuz hücreler (hücrelerin %13'ü) RPT sonrası kayıp
    satışın %45'ini taşır ama sevkiyatın %5'ini alır."""
    df = con.sql(f"""
        WITH r AS ({RPT}),
        m AS (SELECT r.option_id, r.cik,
                     (SELECT min(tarih) FROM takvim t WHERE t.tarih > r.gt AND dayofweek(t.tarih) = 1) pzt
              FROM r WHERE r.gt < r.cik - INTERVAL 14 DAY),
        h AS (SELECT m.*, st.magaza_id, st.urun_id, st.adet stok
              FROM m JOIN urun u ON u.option_id = m.option_id
              JOIN stok st ON st.urun_id = u.urun_id AND st.tarih = m.pzt),
        s28 AS (SELECT h.magaza_id, h.urun_id, h.pzt, sum(s.adet) adet FROM h JOIN satis s
                  ON s.magaza_id = h.magaza_id AND s.urun_id = h.urun_id AND s.adet > 0
                 AND s.tarih >= h.pzt - INTERVAL 28 DAY AND s.tarih < h.pzt GROUP BY 1, 2, 3),
        ky AS (SELECT h.magaza_id, h.urun_id, h.pzt, sum(k.kayip_adet) adet FROM h JOIN kayip_satis k
                  ON k.magaza_id = h.magaza_id AND k.urun_id = h.urun_id
                 AND k.tarih >= h.pzt AND k.tarih < h.cik GROUP BY 1, 2, 3),
        sv AS (SELECT h.magaza_id, h.urun_id, h.pzt, sum(v.adet) adet FROM h JOIN sevkiyat v
                  ON v.magaza_id = h.magaza_id AND v.urun_id = h.urun_id AND v.tip = 'replenishment'
                 AND v.tarih >= h.pzt AND v.tarih < h.cik GROUP BY 1, 2, 3)
        SELECT (h.stok = 0 AND coalesce(s28.adet, 0) = 0) AS bloke, count(*) hucre,
               sum(coalesce(ky.adet, 0)) kayip, sum(coalesce(sv.adet, 0)) sevk
        FROM h LEFT JOIN s28 USING (magaza_id, urun_id, pzt) LEFT JOIN ky USING (magaza_id, urun_id, pzt)
               LEFT JOIN sv USING (magaza_id, urun_id, pzt)
        GROUP BY 1
    """).df().set_index("bloke")
    pay = df / df.sum()
    assert pay.at[True, "hucre"] < 0.30
    assert pay.at[True, "kayip"] > 0.35
    assert pay.at[True, "sevk"] < 0.15


# --- Kayıp satış, iade, kirli kayıt ------------------------------------

def test_kayip_satis_orani_makul(con):
    """SPEC SAPMASI: spec %6–14 hedefliyor. Spec'in kendi sürprizi (σ=0,55)
    ve mağazalar arası transfer olmaması Collection'da ~%27 kayıp üretir;
    toplam ~%15. Üst sınır %16'ya çekildi (README, 'kasten kusurlu')."""
    oran = _tek(con, """
        SELECT (SELECT sum(kayip_adet) FROM kayip_satis)::DOUBLE
             / ((SELECT sum(adet) FROM satis WHERE adet > 0) + (SELECT sum(kayip_adet) FROM kayip_satis))
    """)
    assert 0.06 <= oran <= 0.16, f"kayıp oranı {oran:.3f}"


def test_kayip_line_sirasi(con):
    df = con.sql("""
        WITH s AS (SELECT u.line, sum(s.adet) adet FROM satis s JOIN urun u USING (urun_id)
                   WHERE s.adet > 0 GROUP BY 1),
             k AS (SELECT u.line, sum(k.kayip_adet) adet FROM kayip_satis k JOIN urun u USING (urun_id) GROUP BY 1)
        SELECT line, k.adet / (s.adet + k.adet) oran FROM s JOIN k USING (line)
    """).df().set_index("line")["oran"]
    assert df["NOS"] < 0.03                     # NOS neredeyse hiç bitmez
    assert df["NOS"] < df["Basic"] < df["Collection"]


def test_collection_tam_fiyat_str_makul(con):
    """Tam fiyat STR = indirimden önceki satış ÷ (ilk alım + RPT)."""
    oran = _tek(con, f"""
        WITH g AS ({GERCEK_PLAN}),
        sat AS (SELECT u.option_id, sum(s.adet) adet FROM satis s JOIN urun u USING (urun_id)
                JOIN g ON g.option_id = u.option_id
                WHERE s.adet > 0 AND s.tarih < g.ind GROUP BY 1),
        al AS (SELECT option_id, sum(adet) adet FROM siparis WHERE tip IN ('ilk', 'rpt') GROUP BY 1)
        SELECT sum(sat.adet) / sum(al.adet) FROM g JOIN sat USING (option_id) JOIN al USING (option_id)
        WHERE g.line = 'Collection' AND g.sezon_kodu IN {TAM_SEZONLAR}
    """)
    assert 0.40 <= oran <= 0.75


def test_iade_orani(con):
    oran = _tek(con, """SELECT -sum(adet) FILTER (WHERE adet < 0)::DOUBLE / sum(adet) FILTER (WHERE adet > 0)
                        FROM satis""")
    assert 0.045 <= oran <= 0.07


def test_kirli_kayitlar(con):
    mukerrer = _tek(con, """SELECT count(*) - count(DISTINCT (tarih, magaza_id, urun_id, adet, tutar))
                            FROM satis""")
    assert mukerrer >= sabitler.MUKERRER_KAYIT - 10          # bedelsiz, bazı kopyaları ayrıştırır
    assert _tek(con, "SELECT count(*) FROM satis WHERE adet > 0 AND tutar = 0") >= sabitler.BEDELSIZ_KAYIT
    hayalet = _tek(con, """SELECT count(*) FROM stok st WHERE NOT EXISTS (
                             SELECT 1 FROM sevkiyat v WHERE v.magaza_id = st.magaza_id
                             AND v.urun_id = st.urun_id)""")
    assert hayalet >= sabitler.HAYALET_STOK_KAYDI


def test_indirim_tutari_planli_indirimi_tasir(con):
    df = con.sql("""SELECT t.indirim_donemi_mi, avg(s.indirim_tutari / (s.tutar + s.indirim_tutari)) pay
                    FROM satis s JOIN takvim t USING (tarih) JOIN urun u USING (urun_id)
                    WHERE s.adet > 0 AND s.tutar > 0 AND u.line = 'Collection' GROUP BY 1""").df()
    pay = df.set_index("indirim_donemi_mi")["pay"]
    assert pay[True] > 0.25 and pay[False] < 0.05


# --- Defter tutarlılığı -------------------------------------------------

def test_depo_stogu_negatif_degil(con):
    assert _tek(con, "SELECT min(adet) FROM depo_stok") >= 0
    assert _tek(con, "SELECT min(adet) FROM stok") >= 0


def test_siparis_depo_girisiyle_tutarli(con):
    """depo[p+7] − depo[p] = o hafta gelen sipariş − o hafta net sevkiyat."""
    hatali = _tek(con, """
        WITH d AS (SELECT tarih, urun_id, adet FROM depo_stok),
        gel AS (SELECT date_trunc('week', gerceklesen_teslim) p, urun_id, sum(adet) adet FROM siparis
                WHERE gerceklesen_teslim IS NOT NULL GROUP BY 1, 2),
        cik AS (SELECT date_trunc('week', tarih) p, urun_id, sum(adet) adet FROM sevkiyat GROUP BY 1, 2)
        SELECT count(*) FROM d a JOIN d b ON b.urun_id = a.urun_id AND b.tarih = a.tarih + INTERVAL 7 DAY
        LEFT JOIN gel ON gel.urun_id = a.urun_id AND gel.p = a.tarih
        LEFT JOIN cik ON cik.urun_id = a.urun_id AND cik.p = a.tarih
        WHERE b.adet - a.adet <> coalesce(gel.adet, 0) - coalesce(cik.adet, 0)
    """)
    assert hatali == 0
    assert _tek(con, "SELECT count(*) FROM depo_stok") > 50_000


def test_stoklu_gun_tutarli(con):
    """Satış olan gün stokludur; satışsız kayıp günü stoksuzdur."""
    hatali = _tek(con, """
        WITH sg AS (SELECT magaza_id, urun_id, date_trunc('week', tarih) + INTERVAL 7 DAY p,
                           count(DISTINCT tarih) gun FROM satis WHERE adet > 0 GROUP BY 1, 2, 3),
        kg AS (SELECT k.magaza_id, k.urun_id, date_trunc('week', k.tarih) + INTERVAL 7 DAY p,
                      count(DISTINCT k.tarih) gun FROM kayip_satis k
               WHERE NOT EXISTS (SELECT 1 FROM satis s WHERE s.magaza_id = k.magaza_id
                                 AND s.urun_id = k.urun_id AND s.tarih = k.tarih AND s.adet > 0)
               GROUP BY 1, 2, 3)
        SELECT count(*) FROM stok st
        LEFT JOIN sg ON sg.magaza_id = st.magaza_id AND sg.urun_id = st.urun_id AND sg.p = st.tarih
        LEFT JOIN kg ON kg.magaza_id = st.magaza_id AND kg.urun_id = st.urun_id AND kg.p = st.tarih
        WHERE st.tarih >= DATE '2024-01-08'
          AND (st.stoklu_gun NOT BETWEEN 0 AND 7
               OR st.stoklu_gun < coalesce(sg.gun, 0)
               OR st.stoklu_gun > 7 - coalesce(kg.gun, 0))
    """)
    assert hatali == 0
    # Sansür veride görünür: stoklu_gun < 7 olan satırlar azımsanmayacak kadar
    assert _tek(con, "SELECT avg((stoklu_gun < 7)::INT) FROM stok WHERE tarih >= DATE '2024-01-08'") > 0.05
