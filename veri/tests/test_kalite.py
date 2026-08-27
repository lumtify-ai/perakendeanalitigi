"""Veri gerçekçiliği doğrulamaları.

Bu testler üretilmiş veri setine karşı çalışır; önce
`python -m perakende_veri.uret` çalıştırılmalıdır.

Diğer testler kodun doğru çalıştığını sınar. Bunlar verinin **inandırıcı**
olduğunu sınar. Sentetik verinin klasik tuzağı teknik olarak kusursuz ama
sektör gözünde sahte görünmesidir; aşağıdaki eşikler o tuzağın nöbetçisidir.
"""

import duckdb
import pytest

from perakende_veri import sabitler


@pytest.fixture(scope="module")
def con():
    db = sabitler.CIKTI_DIZINI / "perakende.duckdb"
    if not db.exists():
        pytest.skip("Veri seti üretilmemiş: python -m perakende_veri.uret")
    baglanti = duckdb.connect(str(db), read_only=True)
    yield baglanti
    baglanti.close()


def _tek(con, sorgu: str):
    return con.sql(sorgu).fetchone()[0]


# --- Mevsimsellik -------------------------------------------------------

def test_mevsimsellik_gorunuyor(con):
    sonuc = con.sql("""
        SELECT t.sezon, sum(s.adet) AS adet
        FROM satis s
        JOIN takvim t ON t.tarih = s.tarih
        JOIN urun u ON u.urun_id = s.urun_id
        WHERE u.ust_kategori = 'Dış Giyim' AND s.adet > 0
        GROUP BY 1
    """).df().set_index("sezon")["adet"]
    assert sonuc["Sonbahar/Kış"] > sonuc["İlkbahar/Yaz"] * 2


def test_nos_urun_yil_boyu_satar(con):
    """NOS ürünün sezon dalgalanması Collection'dan düşük olmalı.

    NOS = Never Out of Stock. Stoğu asla bitmemesi gereken çekirdek ürün
    yıl boyu satar; Collection sezonuyla gelir gider.
    """
    oranlar = con.sql("""
        SELECT u.line,
               sum(s.adet) FILTER (WHERE t.sezon = 'Sonbahar/Kış')::DOUBLE
             / sum(s.adet) FILTER (WHERE t.sezon = 'İlkbahar/Yaz') AS oran
        FROM satis s
        JOIN takvim t ON t.tarih = s.tarih
        JOIN urun u ON u.urun_id = s.urun_id
        WHERE u.ust_kategori = 'Dış Giyim' AND s.adet > 0
        GROUP BY 1
    """).df().set_index("line")["oran"]
    assert oranlar["Collection"] > oranlar["NOS"]


def test_her_ayda_satis_var(con):
    aylar = _tek(con, "SELECT count(DISTINCT month(tarih)) FROM satis")
    assert aylar == 12


# --- Dengesizlik: transfer probleminin varlık sebebi --------------------

def test_beden_dengesizligi_magazalar_arasi(con):
    """Aynı modelin aynı bedeni bazı mağazalarda tükenirken bazılarında yığılmalı."""
    adet = _tek(con, """
        WITH son AS (SELECT max(tarih) AS t FROM stok)
        SELECT count(*) FROM (
            SELECT u.model_kodu, u.beden
            FROM stok st
            JOIN urun u ON u.urun_id = st.urun_id
            JOIN son ON st.tarih = son.t
            GROUP BY 1, 2
            HAVING min(st.adet) = 0 AND max(st.adet) > 10
        )
    """)
    assert adet > 20, f"yalnızca {adet} dengesiz (model, beden) çifti"


def test_kiriklik_var(con):
    """Beden seti bozulması moda transferinin en özgün problemidir.

    Kırıklık = option'ın stoğu var ama ara bedenleri (S/M/L) tükenmiş.
    Kalan uçlar (XS/XL) tek başına satmaz; toplanıp teklenmesi gerekir.
    """
    adet = _tek(con, """
        WITH son AS (SELECT max(tarih) AS t FROM stok)
        SELECT count(*) FROM (
            SELECT st.magaza_id, u.option_id
            FROM stok st
            JOIN urun u ON u.urun_id = st.urun_id
            JOIN son ON st.tarih = son.t
            GROUP BY 1, 2
            HAVING sum(st.adet) > 0
               AND count(*) FILTER (WHERE st.adet = 0 AND u.beden_sira IN (2, 3, 4)) > 0
        )
    """)
    assert adet > 100, f"yalnızca {adet} kırık beden seti"


def test_olu_stok_var(con):
    """Yıl boyu hiç satmamış ama stok tutan mağaza-SKU çiftleri olmalı."""
    adet = _tek(con, """
        WITH son AS (SELECT max(tarih) AS t FROM stok)
        SELECT count(*)
        FROM stok st
        JOIN son ON st.tarih = son.t
        WHERE st.adet > 0
          AND NOT EXISTS (
              SELECT 1 FROM satis s
              WHERE s.magaza_id = st.magaza_id AND s.urun_id = st.urun_id
          )
    """)
    assert adet > 50, f"yalnızca {adet} ölü stok çifti"


def test_verici_esigi_ayirt_edici(con):
    """Yüksek cover'lı, soğumada olmayan hücre havuzu eşikle daralmalı.

    Blok Transfer demosunun verici kadranı buna dayanır. İkmal her hücreye
    giderse soğuma filtresi geriye yalnız zaten çok yüksek cover'lı
    hücreleri bırakır; eşiği 6'dan 14'e çekmek hiçbir şeyi değiştirmez ve
    kadran ölür (v1'de olan buydu: 195 → 190).
    """
    def havuz(esik: int) -> int:
        return _tek(con, f"""
            WITH son AS (SELECT max(tarih) AS t FROM stok),
            stok_son AS (
                SELECT st.magaza_id, u.option_id, sum(st.adet) AS adet
                FROM stok st JOIN urun u ON u.urun_id = st.urun_id, son
                WHERE st.tarih = son.t
                GROUP BY 1, 2 HAVING sum(st.adet) > 0
            ),
            hiz AS (
                SELECT s.magaza_id, u.option_id, sum(s.adet)::DOUBLE / 8 AS haftalik
                FROM satis s JOIN urun u ON u.urun_id = s.urun_id, son
                WHERE s.tarih >= son.t - INTERVAL 8 WEEK AND s.tarih < son.t
                GROUP BY 1, 2
            ),
            sicak AS (
                SELECT DISTINCT sv.magaza_id, u.option_id
                FROM sevkiyat sv JOIN urun u ON u.urun_id = sv.urun_id, son
                WHERE sv.tarih > son.t - INTERVAL 2 WEEK
            )
            SELECT count(*) FROM stok_son k
            LEFT JOIN hiz ON hiz.magaza_id = k.magaza_id
                         AND hiz.option_id = k.option_id
            WHERE (hiz.haftalik IS NULL OR hiz.haftalik <= 0
                   OR k.adet / hiz.haftalik >= {esik})
              AND NOT EXISTS (
                  SELECT 1 FROM sicak
                  WHERE sicak.magaza_id = k.magaza_id
                    AND sicak.option_id = k.option_id)
        """)

    genis, dar = havuz(6), havuz(14)
    assert genis > 250, f"verici havuzu yalnızca {genis} hücre"
    assert dar < genis * 0.9, f"eşik ayırt etmiyor: {genis} → {dar}"


# --- Kayıp satış ve STR -------------------------------------------------

def test_kayip_satis_makul_aralikta(con):
    oran = _tek(con, """
        SELECT (SELECT sum(kayip_adet) FROM kayip_satis)::DOUBLE
             / ((SELECT sum(adet) FROM satis WHERE adet > 0)
                + (SELECT sum(kayip_adet) FROM kayip_satis))
    """)
    # Sıfır kayıp inandırıcı değil; %25 üstü kötü yönetilen bir zincir demek
    assert 0.01 < oran < 0.25, f"kayıp satış oranı {oran:.1%}"


def test_str_makul_aralikta(con):
    """STR = satılan / gönderilen. Sevkiyat kaydı olmadan hesaplanamaz."""
    oran = _tek(con, """
        SELECT (SELECT sum(adet) FROM satis)::DOUBLE
             / (SELECT sum(adet) FROM sevkiyat)
    """)
    assert 0.5 < oran < 1.0, f"STR {oran:.1%}"


def test_iade_orani_makul(con):
    oran = _tek(con, """
        SELECT -(SELECT sum(adet) FROM satis WHERE adet < 0)::DOUBLE
              / (SELECT sum(adet) FROM satis WHERE adet > 0)
    """)
    assert 0.02 < oran < 0.12, f"iade oranı {oran:.1%}"


# --- Bütünlük -----------------------------------------------------------

@pytest.mark.parametrize(
    "tablo", ["satis", "stok", "sevkiyat", "kayip_satis"]
)
def test_referans_butunlugu(con, tablo):
    yetim_urun = _tek(con, f"""
        SELECT count(*) FROM {tablo} h
        LEFT JOIN urun u ON u.urun_id = h.urun_id WHERE u.urun_id IS NULL
    """)
    yetim_magaza = _tek(con, f"""
        SELECT count(*) FROM {tablo} h
        LEFT JOIN magaza m ON m.magaza_id = h.magaza_id WHERE m.magaza_id IS NULL
    """)
    assert yetim_urun == 0
    assert yetim_magaza == 0


def test_stok_negatif_degil(con):
    assert _tek(con, "SELECT count(*) FROM stok WHERE adet < 0") == 0


def test_tarih_araligi_dogru(con):
    ilk, son = con.sql("SELECT min(tarih), max(tarih) FROM satis").fetchone()
    assert ilk.date() == sabitler.BASLANGIC
    assert son.date() == sabitler.BITIS


# --- Kasten bırakılmış kusurlar -----------------------------------------

def test_kirli_kayitlar_duruyor(con):
    """Veri fazla temiz olmamalı; kusurlar kasten üretilir ve belgelenir."""
    bedelsiz = _tek(con, "SELECT count(*) FROM satis WHERE adet > 0 AND tutar = 0")
    assert bedelsiz > 0

    hayalet = _tek(con, """
        SELECT count(*) FROM (
            SELECT DISTINCT st.magaza_id, st.urun_id FROM stok st
            WHERE NOT EXISTS (
                SELECT 1 FROM sevkiyat sv
                WHERE sv.magaza_id = st.magaza_id AND sv.urun_id = st.urun_id
            )
        )
    """)
    assert hayalet > 0, "mağazanın çeşidinde olmayan üründe stok görünmüyor"


def test_kirli_kayitlar_azinlikta(con):
    """Kusur inandırıcılık içindir; veriyi kullanılamaz hale getirmemeli."""
    oran = _tek(con, """
        SELECT count(*) FILTER (WHERE adet > 0 AND tutar = 0)::DOUBLE / count(*)
        FROM satis
    """)
    assert oran < 0.001


# --- İndirilebilirlik ---------------------------------------------------

def test_veri_boyutu_indirilebilir():
    toplam = sum(
        f.stat().st_size for f in (sabitler.CIKTI_DIZINI / "csv").glob("*.csv")
    )
    # 80 MB üstü indirilebilir olmaktan çıkar
    assert toplam < 80 * 1024 * 1024, f"CSV toplamı {toplam / 1024 / 1024:.0f} MB"
