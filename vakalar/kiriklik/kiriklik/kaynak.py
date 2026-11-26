"""Yayımlanan v4 biçimindeki tablolardan karar girdisi (kırıklık transferinin karar anı).

Kural: bu modül karar modülüdür; gizli gerçeğe (`perakende_veri`, `gizli_*` tabloları) ve ölçüm tarafına
(`hakem`, `simulasyon`, `olcutler`, `oyun`, `allocation.motor`) dokunmaz. Yalnız yayımlanan tabloları adıyla
okur; bu yüzden `karar_girdisi` herhangi bir DuckDB bağlantısı alır: yol 0'da yayımlanan v4 dosyası, yol
p > 0'da o yolun Lumoda koşusundan aynı tablo adlarıyla kurulmuş geçici bir DuckDB.

**Karar anı.** Sezon başına tek karar günü vardır (`sabitler.KARAR`, pazartesi). Gözlenen olay tabloları
(`satis`, `stok`, `siparis`, `magaza_olay`) karar gününden önceye kesilir; pazartesi stok fotoğrafı
(`stok`, `depo_stok`) karar gününün kendisidir ve dahil, o günün satışı hariçtir.

**Hücre.** Fiziksel mağaza (`sabitler.FIZIKSEL_TIPLER`) × sezonun Collection SKU'ları (`Standart` beden
seti hariç); stok satırı olmayan hücre stok 0'dır. `stok` tablosundaki hayalet satırlar (mağazanın çeşidinde
olmayan SKU'da tek pazartesi fotoğrafı) ayıklanmaz: karar fotoğrafına düşerse aynen alınır.

**Açık sipariş** (replenishment'ın karar anında kapatabileceği bedenler için, tasarım §0 K18): karardan önce
verilmiş, karar gününe kadar teslim edilmemiş (`gerceklesen_teslim` boş ya da `>= karar`: karardan sonraki
teslim karar anında bilinmez, sipariş açıktır) ve planlanan teslimi indirim gününden önce olan adetler.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
from perakende_analitik import kaynak as ortak

from kiriklik import sabitler

VERITABANI = ortak.VARSAYILAN_YOL


def baglan(yol: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """v4 DuckDB dosyasına salt okunur bağlanır (ortak `kaynak.baglan`; `PERAKENDE_V4_DB` ya da varsayılan)."""
    return ortak.baglan(yol)


@dataclass(frozen=True, eq=False)
class KararGirdisi:
    """Bir test sezonunun karar günü girdisi (yalnız açık bilgi).

    `hucre` [magaza_id, urun_id, option_id, beden_sira, stok, depo, acik_siparis, liste_fiyati, alis_fiyati];
    `satis` [magaza_id, urun_id, tarih, adet, tutar] ham (iade satırları negatif adet, mükerrer kopya düşmüş,
    `tarih < karar`); `stoklu` [magaza_id, urun_id, tarih, stoklu_gun] (pazartesi fotoğrafları `<= karar`);
    `magaza` [magaza_id, ad, sehir, bolge, tip, uygun]; `optionlar` [option_id, alt_kategori, ust_kategori,
    dalga, lansman_tarihi, liste_fiyati, alis_fiyati]. `depo` ve `acik_siparis` SKU düzeyindedir (depo mağazaya
    bölünmez); her mağaza satırında aynı değer tekrarlanır, toplamları mağaza sayısıyla katlanır.

    `takvim` [tarih, tatil_mi] ve `kampanya` [kampanya_id, tip, baslangic, bitis, kapsam_ust_kategori, kapsam_line,
    kapsam_bolge, oran] açık plan bilgisidir (resmî tatiller ve kampanya takvimi önceden bilinir): karar gününden
    sonrası kesilmez. `kampanya` yayımlanan `kampanya` tablosunun bütün satırlarıdır (Black Friday, kategori, ikinci
    ürün; Ruling R33), kapsam sütunlarıyla; kapsamın (mağaza, option) çiftine eşlenmesi `tahmin.kampanya_oranlari`."""
    sezon: str
    karar: date
    indirim: date
    cikis: date
    hucre: pd.DataFrame
    satis: pd.DataFrame
    stoklu: pd.DataFrame
    magaza: pd.DataFrame
    optionlar: pd.DataFrame
    takvim: pd.DataFrame
    kampanya: pd.DataFrame


def sezon_dates(con: duckdb.DuckDBPyConnection, sezon: str) -> tuple[date, date]:
    """Yayımlanan `sezon` tablosundan (indirim başlangıcı, çıkış tarihi); sezonun dalgaları aynı iki tarihi
    taşır, yoksa ya da dalgalar ayrışıyorsa `ValueError`."""
    satir = con.execute(
        "select distinct indirim_baslangic, cikis_tarihi from sezon where sezon_kodu = ?", [sezon]).fetchall()
    if len(satir) != 1:
        raise ValueError(f"sezon {sezon!r}: yayımlanan `sezon` tablosunda tek (indirim, çıkış) çifti yok: {satir}")
    indirim, cikis = satir[0]
    return pd.Timestamp(indirim).date(), pd.Timestamp(cikis).date()


# Kapsamdaki SKU'lar ve fiziksel mağazalar; her sorguya `with` olarak girer (parametreler: sezon, line, beden
# seti; mağaza tipleri). Bağlantıya geçici görünüm yazılmaz, bağlantı salt okunur kalır.
_SKU = """
    sku as (
        select urun_id, option_id, beden_sira, liste_fiyati, alis_fiyati
        from urun where sezon_kodu = ? and line = ? and beden_seti <> ?)"""
_MAG = """
    mag as (
        select magaza_id, ad, sehir, bolge, tip from magaza where tip in ({tipler}))"""


def _on_ek(tipler: tuple[str, ...]) -> tuple[str, list]:
    """`with sku, mag` öneki ve parametreleri."""
    yer = ", ".join("?" for _ in tipler)
    sql = "with" + _SKU + "," + _MAG.format(tipler=yer)
    return sql, [None, sabitler.LINE, sabitler.STANDART_BEDEN_SETI, *tipler]


def _tablo_kontrol(con: duckdb.DuckDBPyConnection, tablolar: tuple[str, ...]) -> None:
    """Bağlantıda olmayan yayımlanan tablo için açık `ValueError` (örn. yol p'nin geçici DuckDB'si eksik kurulmuşsa)."""
    var = {r[0] for r in con.execute("select table_name from information_schema.tables").fetchall()}
    eksik = [t for t in tablolar if t not in var]
    if eksik:
        raise ValueError(f"karar girdisi için bağlantıda yayımlanan tablo yok: {eksik}")


def karar_girdisi(con: duckdb.DuckDBPyConnection, sezon: str) -> KararGirdisi:
    """`sezon`un karar günü girdisi. Karar günü `sabitler.KARAR`'dan; test sezonu dışı `ValueError`, bağlantıda
    `takvim` ya da `kampanya` tablosu yoksa `ValueError`."""
    if sezon not in sabitler.KARAR:
        raise ValueError(f"test sezonu değil: {sezon!r} (geçerli: {sabitler.TEST_SEZONLARI})")
    _tablo_kontrol(con, ("takvim", "kampanya"))
    karar = sabitler.KARAR[sezon]
    indirim, cikis = sezon_dates(con, sezon)
    on_ek, par = _on_ek(sabitler.FIZIKSEL_TIPLER)
    par[0] = sezon

    def sorgu(govde: str, *args) -> pd.DataFrame:
        return con.execute(f"{on_ek} {govde}", [*par, *args]).fetchdf()

    hucre = sorgu("""
        , foto as (select magaza_id, urun_id, sum(adet) as adet from stok where tarih = ? group by 1, 2),
        depo as (select urun_id, sum(adet) as adet from depo_stok where tarih = ? group by 1),
        acik as (
            select urun_id, sum(adet) as adet from siparis
            where siparis_tarihi < ? and (gerceklesen_teslim is null or gerceklesen_teslim >= ?)
              and planlanan_teslim < ?
            group by 1)
        select m.magaza_id, s.urun_id, s.option_id, s.beden_sira,
               coalesce(f.adet, 0)::bigint as stok, coalesce(d.adet, 0)::bigint as depo,
               coalesce(a.adet, 0)::bigint as acik_siparis, s.liste_fiyati, s.alis_fiyati
        from mag m cross join sku s
        left join foto f on f.magaza_id = m.magaza_id and f.urun_id = s.urun_id
        left join depo d on d.urun_id = s.urun_id
        left join acik a on a.urun_id = s.urun_id
        order by m.magaza_id, s.option_id, s.beden_sira""",
        karar, karar, karar, karar, indirim)

    satis = sorgu("""
        select t.magaza_id, t.urun_id, t.tarih, t.adet, t.tutar
        from (select distinct * from satis where tarih < ?) t
        join sku s using (urun_id) join mag m using (magaza_id)
        order by t.tarih, t.magaza_id, t.urun_id""", karar)

    stoklu = sorgu("""
        select t.magaza_id, t.urun_id, t.tarih, t.stoklu_gun
        from stok t join sku s using (urun_id) join mag m using (magaza_id)
        where t.tarih <= ?
        order by t.tarih, t.magaza_id, t.urun_id""", karar)

    magaza = sorgu("""
        select m.magaza_id, m.ad, m.sehir, m.bolge, m.tip,
               coalesce(
                   (x.acilis_tarihi is null or x.acilis_tarihi <= ?)
                   and (x.kapanis_tarihi is null or x.kapanis_tarihi > ?)
                   and not exists (select 1 from magaza_olay o
                                   where o.magaza_id = m.magaza_id and o.olay = 'kapanis'
                                     and o.karar_tarihi <= ?)
                   and not exists (select 1 from magaza_olay o
                                   where o.magaza_id = m.magaza_id and o.olay = 'tadilat'
                                     and o.karar_tarihi <= ? and o.olay_tarihi <= ?
                                     and (o.bitis_tarihi is null or o.bitis_tarihi > ?)),
                   false) as uygun
        from mag m join magaza x using (magaza_id)
        order by m.magaza_id""", karar, karar, karar, karar, karar, karar)

    optionlar = sorgu("""
        select u.option_id, any_value(u.alt_kategori) as alt_kategori, any_value(u.ust_kategori) as ust_kategori,
               any_value(u.dalga) as dalga, min(u.lansman_tarihi) as lansman_tarihi,
               any_value(s.liste_fiyati) as liste_fiyati, any_value(s.alis_fiyati) as alis_fiyati
        from urun u join sku s using (urun_id)
        group by u.option_id
        order by u.option_id""")

    takvim = con.execute("select tarih, tatil_mi from takvim order by tarih").fetchdf()
    kampanya = con.execute("""
        select kampanya_id, tip, baslangic, bitis, coalesce(kapsam_ust_kategori, '') as kapsam_ust_kategori,
               coalesce(kapsam_line, '') as kapsam_line, coalesce(kapsam_bolge, '') as kapsam_bolge, oran
        from kampanya order by baslangic, kampanya_id""").fetchdf()

    return KararGirdisi(sezon=sezon, karar=karar, indirim=indirim, cikis=cikis, hucre=hucre, satis=satis,
                        stoklu=stoklu, magaza=magaza, optionlar=optionlar, takvim=takvim,
                        kampanya=kampanya)
