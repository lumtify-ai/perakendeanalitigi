"""Yayımlanan v4 verisini okur; kirli kayıtları ayıklayan görünümler kurar.

Kestiriciler yalnız yayımlanan tabloları okur (`veri/cikti/v4/perakende.duckdb`;
ortam değişkeni `PERAKENDE_V4_DB` ile geçersiz kılınabilir). Gizli gerçeğe
(`perakende_veri`) dokunmazlar; o yalnız `hakem.py`'nin işidir.

İki görünüm iki kirli kaydı çözer (v4 README, "Kirli kayıtlar"):

    temiz_satis     mükerrer satış satırı (aynı satırın ikinci kopyası düşer;
                    motor bir hücrenin bir gününe tek satış satırı yazar)
    cesit_hucreleri hayalet stok (mağazanın çeşidinde olmayan SKU'da pazartesi
                    stoğu): çeşit = varışlı sevkiyat hedefleri + satışı olan
                    hücreler + `stok` hücreleri − hayalet + her SKU için `ONL`;
                    hayalet = varışsız, satışsız, tek pazartesi fotoğraflı,
                    adet > 0 hücre (ayrıntı `cesit_hucreleri` açıklamasında)

Bedelsiz satış (`tutar` 0) bu modülde elenmez: adet gerçektir, yalnız fiyat
analizinde dikkat ister.
"""

import os
from pathlib import Path

import duckdb

DEPO_KOKU = Path(__file__).resolve().parents[3]
VARSAYILAN_YOL = Path(
    os.environ.get("PERAKENDE_V4_DB") or DEPO_KOKU / "veri" / "cikti" / "v4" / "perakende.duckdb")

INDIRME = "https://github.com/lumtify-ai/perakendeanalitigi/releases/tag/veri-v4"


def baglan(yol: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """v4 DuckDB dosyasına salt okunur bağlanır."""
    yol = Path(yol) if yol is not None else VARSAYILAN_YOL
    if not yol.exists():
        raise FileNotFoundError(
            f"{yol} yok. Ya yayımlanan veriyi indirin: {INDIRME} "
            "(lumoda-v4.duckdb dosyasını bu yola `perakende.duckdb` adıyla koyun, "
            "ya da PERAKENDE_V4_DB ortam değişkeniyle gösterin), ya da yerelde üretin: "
            "cd veri && python -m perakende_veri.v4.uret"
        )
    return duckdb.connect(str(yol), read_only=True)


def temiz_satis(con: duckdb.DuckDBPyConnection) -> str:
    """`temiz_satis` görünümünü kurar, adını döndürür.

    Tam aynı satırların ikinci kopyası düşer. İade (negatif adet) satırları
    ve bedelsiz satışlar kalır."""
    con.execute("create or replace temp view temiz_satis as select distinct * from satis")
    return "temiz_satis"


def cesit_hucreleri(con: duckdb.DuckDBPyConnection) -> str:
    """`cesit` görünümünü kurar, adını döndürür.

    Sütunlar: `magaza_id`, `urun_id` (ikisi de VARCHAR). Çeşit şunların
    birleşimidir:

    1. Hedefi o mağaza olan ve varış tarihi dolu en az bir sevkiyatın
       vardığı mağaza × SKU çiftleri (yolda kalanlar ve tek taraflı
       transferler saymaz).
    2. Satışı olan fiziksel mağaza × SKU çiftleri. Pencere öncesinde dağıtılmış
       (sevkiyatı pencerede görünmeyen) devamlı mal buradan girer; gerçek v4'te
       9.460 hücre, 39.903 adet.
    3. `stok`ta görünen çiftler, HAYALET stok hariç.
    4. Her SKU için `ONL` (online bütün kataloğu satar).

    Hayalet stok: hiç varışı ve satışı olmayan hücrede tek bir pazartesi
    fotoğrafı ve adet > 0 (README: 1-3 adet, `stoklu_gun` 7). Gerçek v4'te bu
    imza tam 150 hücreyi tutar, README'nin 150'siyle aynı; pencere öncesinden
    kalan ve hiç satmayan gerçek hücreler birden çok pazartesi görünür, o
    yüzden çakışmaz."""
    con.execute("""
        create or replace temp view cesit as
        with varis as (
            select distinct hedef::varchar as magaza_id, urun_id::varchar as urun_id
            from sevkiyat
            where varis_tarihi is not null and hedef::varchar <> 'DEPO'),
        satisli as (
            select distinct magaza_id::varchar as magaza_id, urun_id::varchar as urun_id
            from satis where magaza_id::varchar <> 'ONL'),
        fotolu as (
            select magaza_id::varchar as magaza_id, urun_id::varchar as urun_id,
                   count(*) as n, max(adet) as en_cok
            from stok group by 1, 2),
        hayalet as (
            select f.magaza_id, f.urun_id from fotolu f
            where f.n = 1 and f.en_cok > 0
              and not exists (select 1 from varis v
                              where v.magaza_id = f.magaza_id and v.urun_id = f.urun_id)
              and not exists (select 1 from satisli s
                              where s.magaza_id = f.magaza_id and s.urun_id = f.urun_id))
        select magaza_id, urun_id from varis
        union select magaza_id, urun_id from satisli
        union select f.magaza_id, f.urun_id from fotolu f
              where not exists (select 1 from hayalet h
                                where h.magaza_id = f.magaza_id and h.urun_id = f.urun_id)
        union select 'ONL', urun_id::varchar from urun
    """)
    return "cesit"
