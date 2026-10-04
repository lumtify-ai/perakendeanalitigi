"""Günlük mağaza stoğunu pazartesi fotoğrafından yeniden kurar.

`stok` tablosu yalnız pazartesi sabahı fotoğrafı tutar. Motorun günlük sırası:
pazartesi fotoğrafı günün hareketlerinden önce çekilir; sonra varışlar
(`sevkiyat.varis_tarihi = d`) ve çıkışlar (`sevkiyat.tarih = d`, kaynak mağaza)
işlenir; sonra satışlar; müşteri iadeleri en son rafa döner (negatif `satis`
satırları). Buna göre bir hücrenin (mağaza × SKU) gün başı satışa açık stoğu:

    satis_oncesi(d) = S(pzt) + Σ varış(pzt..d) − Σ çıkış(pzt..d) − Σ net_satis(pzt..d−1)

Her hafta kendi pazartesi fotoğrafına çapalanır; hata haftadan haftaya
birikmez. Tek taraflı transferde (çıkış var, `varis_tarihi` boş) stok negatife
inebilir; `satis_oncesi ≤ 0` hepsi `bos` sayılır.

    bos       satis_oncesi <= 0
    tukenen   satis_oncesi > 0 ve brut_satis >= satis_oncesi (gün içinde bitti)
    stoklu    diğerleri

`brut_satis` günün pozitif satış satırlarının toplamı, `net_satis` iadeler
dahil toplamıdır. Satış, `kaynak.temiz_satis` üzerinden okunur (mükerrer
satır tek sayılır). `ONL` bu fonksiyonda yoktur (çevrimiçi: `gunluk_online`).

Uygun hücre-gün (yalnız bunlar döner):

    a. hücrenin hem o pazartesi hem ertesi pazartesi `stok` satırı var (tam
       hafta; pencerenin son günlerinde ertesi fotoğraf yoksa o hafta düşer);
    b. hücre `kaynak.cesit_hucreleri`nde;
    c. mağaza o gün açık: `acilis_tarihi <= d`, `kapanis_tarihi` boş ya da
       `> d`, tadilat `[olay_tarihi, bitis_tarihi)` dışında;
    d. `d >= urun.lansman_tarihi`;
    e. hücre pencere boyunca hiç stoklanmamış değil: bütün pazartesi
       fotoğrafları 0, hiç varışı ve hiç satışı yok (gerçek v4'te 728 hücre).
       Hiç ikmal edilmemiş ürün bir çeşit kararıdır, stoksuzluk değil. Bu
       kural `bas`, `bit`ten bağımsız, bütün tabloya bakar.

Bellek: sonuç ~22 M hücre-gün/yıl (2025); kimlikler `category` (int32 kod), sayılar
`int32`, `tarih` `datetime64[ns]` (8 bayt). Satır
başına ~26 bayt; üç yıllık bütün pencere (67,7 M satır) ~1,8 GB, 2025 yalnız 0,58 GB (ölçüldü).
Kimlikleri düz metin olarak çekmemek için SQL kodları üretir, kategoriler
ayrıca okunur.
"""

from datetime import date

import duckdb
import pandas as pd

from perakende_analitik import kaynak

DURUMLAR = ["stoklu", "tukenen", "bos"]


def _gun(g) -> date:
    return pd.Timestamp(g).date()


def _kategoriler(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str], list[str]]:
    """(magaza, urun, option) kategori evreni: boyut tablolarının tamamı, sıralı.
    SQL'in ürettiği tamsayı kodlar bu listelere indeks olur; böylece mağaza ve
    online tabloları `pd.concat`te kategori türünü korur."""
    magazalar = [r[0] for r in con.execute(
        "select magaza_id::varchar from magaza order by 1").fetchall()]
    urunler = [r[0] for r in con.execute(
        "select urun_id::varchar from urun order by 1").fetchall()]
    opsiyonlar = [r[0] for r in con.execute(
        "select distinct option_id::varchar from urun order by 1").fetchall()]
    return magazalar, urunler, opsiyonlar


def _tablo(ham: dict, kategoriler: tuple[list[str], list[str], list[str]]) -> pd.DataFrame:
    """SQL'in kod sütunlarından günlük tablo (R9 türleri, R10 durum kategorisi)."""
    magazalar, urunler, opsiyonlar = kategoriler
    return pd.DataFrame({
        "tarih": ham["gun"].astype("int64").astype("datetime64[D]").astype("datetime64[ns]"),
        "magaza_id": pd.Categorical.from_codes(ham["magaza"], categories=magazalar),
        "urun_id": pd.Categorical.from_codes(ham["urun"], categories=urunler),
        "option_id": pd.Categorical.from_codes(ham["opsiyon"], categories=opsiyonlar),
        "satis_oncesi": ham["satis_oncesi"].astype("int32"),
        "brut_satis": ham["brut_satis"].astype("int32"),
        "net_satis": ham["net_satis"].astype("int32"),
        "durum": pd.Categorical.from_codes(ham["durum"], categories=DURUMLAR),
    })


def gunluk_magaza(con: duckdb.DuckDBPyConnection, bas: date, bit: date) -> pd.DataFrame:
    """[bas, bit] aralığındaki uygun mağaza hücre-günlerinin günlük tablosu.

    Sütunlar: tarih, magaza_id, urun_id, option_id, satis_oncesi, brut_satis,
    net_satis, durum. Sıra: tarih, magaza_id, urun_id."""
    bas, bit = _gun(bas), _gun(bit)
    satis = kaynak.temiz_satis(con)
    cesit = kaynak.cesit_hucreleri(con)

    kategoriler = _kategoriler(con)

    ham = con.execute(f"""
        with
        mk as (select magaza_id::varchar as m, row_number() over (order by magaza_id::varchar) - 1 as kod
               from magaza),
        uk as (select urun_id::varchar as u, option_id::varchar as o,
                      row_number() over (order by urun_id::varchar) - 1 as kod,
                      lansman_tarihi::date as lansman
               from urun),
        ok as (select o, row_number() over (order by o) - 1 as kod
               from (select distinct option_id::varchar as o from urun)),
        pzt as (select unnest(generate_series(date_trunc('week', date '{bas}'),
                                              date_trunc('week', date '{bit}'),
                                              interval 7 day))::date as p),
        -- hiç stoklanmamış hücre: tüm fotoğraflar 0, varış yok, satış yok
        hic as (
            select magaza_id::varchar as m, urun_id::varchar as u
            from stok group by 1, 2 having max(adet) <= 0
            except select hedef::varchar, urun_id::varchar from sevkiyat
                   where varis_tarihi is not null
            except select magaza_id::varchar, urun_id::varchar from {satis}),
        hucre as (
            select magaza_id::varchar as m, urun_id::varchar as u from {cesit}
            where magaza_id::varchar <> 'ONL'
            except select m, u from hic),
        -- tam hafta: o pazartesi ve ertesi pazartesi fotoğrafı var
        hafta as (
            select h.m, h.u, a.tarih::date as p, a.adet as s
            from stok a
            join hucre h on h.m = a.magaza_id::varchar and h.u = a.urun_id::varchar
            where a.tarih::date in (select p from pzt)
              and exists (select 1 from stok b
                          where b.magaza_id = a.magaza_id and b.urun_id = a.urun_id
                            and b.tarih::date = a.tarih::date + 7)),
        varis as (
            select hedef::varchar as m, urun_id::varchar as u, varis_tarihi::date as g, sum(adet) as n
            from sevkiyat where varis_tarihi is not null and hedef::varchar <> 'DEPO'
            group by 1, 2, 3),
        cikis as (
            select kaynak::varchar as m, urun_id::varchar as u, tarih::date as g, sum(adet) as n
            from sevkiyat where kaynak::varchar <> 'DEPO'
            group by 1, 2, 3),
        sat as (
            select magaza_id::varchar as m, urun_id::varchar as u, tarih::date as g,
                   sum(adet) as net, sum(adet) filter (where adet > 0) as brut
            from {satis} group by 1, 2, 3),
        tadilat as (
            select magaza_id::varchar as m, olay_tarihi::date as bas,
                   coalesce(bitis_tarihi::date, date '9999-12-31') as bit
            from magaza_olay where olay::varchar = 'tadilat'),
        izgara as (
            select h.m, h.u, h.p, h.s, k::int as k, h.p + k::int as d
            from hafta h, range(7) t(k)
            where h.p + k::int <= date '{bit}'),
        kur as (
            select i.m, i.u, i.p, i.k, i.d,
                   i.s + sum(coalesce(v.n, 0)) over w - sum(coalesce(c.n, 0)) over w
                       - (sum(coalesce(a.net, 0)) over w - coalesce(a.net, 0)) as satis_oncesi,
                   coalesce(a.brut, 0) as brut_satis,
                   coalesce(a.net, 0) as net_satis
            from izgara i
            left join varis v on v.m = i.m and v.u = i.u and v.g = i.d
            left join cikis c on c.m = i.m and c.u = i.u and c.g = i.d
            left join sat a on a.m = i.m and a.u = i.u and a.g = i.d
            window w as (partition by i.m, i.u, i.p order by i.k
                         rows between unbounded preceding and current row))
        select (kur.d - date '1970-01-01')::int as gun,
               mk.kod as magaza, uk.kod as urun, ok.kod as opsiyon,
               kur.satis_oncesi::int as satis_oncesi,
               kur.brut_satis::int as brut_satis,
               kur.net_satis::int as net_satis,
               case when kur.satis_oncesi <= 0 then 2
                    when kur.brut_satis >= kur.satis_oncesi then 1 else 0 end::tinyint as durum
        from kur
        join mk on mk.m = kur.m
        join uk on uk.u = kur.u
        join ok on ok.o = uk.o
        join magaza ma on ma.magaza_id::varchar = kur.m
        where kur.d between date '{bas}' and date '{bit}'
          and ma.acilis_tarihi::date <= kur.d
          and (ma.kapanis_tarihi is null or ma.kapanis_tarihi::date > kur.d)
          and kur.d >= uk.lansman
          and not exists (select 1 from tadilat td
                          where td.m = kur.m and kur.d >= td.bas and kur.d < td.bit)
        order by kur.d, mk.kod, uk.kod
    """).fetchnumpy()

    return _tablo(ham, kategoriler)


def gunluk_online(con: duckdb.DuckDBPyConnection, bas: date, bit: date) -> pd.DataFrame:
    """[bas, bit] aralığındaki uygun online (`ONL`) SKU-günlerinin günlük tablosu.

    Online, merkez depodan satar. Motorun günlük sırası: önce günün depo
    hareketleri (tedarikçi teslimi, DEPO'ya varışlar, DEPO'dan çıkışlar;
    replenishment dahil), sonra online satış, en son online iadeler depoya
    döner. `depo_stok(d)` her günün hareketlerinden ÖNCE çekilen sabah
    fotoğrafıdır. Dolayısıyla satışa açık stok bir sonraki sabah fotoğrafından
    geriye doğru kurulur:

        satis_oncesi(d) = depo_stok(d+1) + net_satis_ONL(d)

    Teslim günlerinde depo zinciri (`depo_stok(d+1) = depo_stok(d) + varış −
    çıkış − net_satis`) tutmaz: fark yayımlanmayan hatalı mal adedidir (hatalı
    mal depoya girmez). d+1 formülü bunu kendiliğinden doğru yakalar.

    Son gün (`depo_stok`un son tarihi, v4'te pencere sonu 2025-12-31) için
    d+1 fotoğrafı yoktur; ileri kurulum kullanılır:

        satis_oncesi(d) = depo_stok(d) + Σ siparis.adet (gerceklesen_teslim = d)
                          + Σ varış(hedef DEPO, d) − Σ çıkış(kaynak DEPO, d)

    İleri kurulum teslim günündeki hatalı adedi bilmez (yayımlanmıyor); o
    günün `satis_oncesi`sini en çok hatalı adet kadar fazla verebilir. Bu
    yalnız son gün için geçerlidir. `depo_stok`un son tarihinden sonraki
    günler döndürülmez (kurmaya dayanak yok).

    Bir SKU-günün `depo_stok` satırı yoksa depo stoğu 0 sayılır (uygun
    pencerede olmayan SKU zaten dönmez). Durum kuralı mağazadakiyle aynı:
    `satis_oncesi <= 0` bos; `brut_satis >= satis_oncesi` tukenen; diğeri stoklu.

    Uygun gün: `lansman_tarihi <= d < cikis_tarihi` (çıkış boşsa pencere
    sonuna dek). Satış `kaynak.temiz_satis` üzerinden okunur. Sütunlar ve
    sıra `gunluk_magaza`yla aynı (`magaza_id` hep `ONL`); kategori evreni de
    aynı olduğundan iki tablo `pd.concat` ile kategori türünü korur."""
    bas, bit = _gun(bas), _gun(bit)
    satis = kaynak.temiz_satis(con)
    kategoriler = _kategoriler(con)

    ham = con.execute(f"""
        with
        mk as (select kod from (
                   select magaza_id::varchar as m,
                          row_number() over (order by magaza_id::varchar) - 1 as kod
                   from magaza) where m = 'ONL'),
        uk as (select urun_id::varchar as u, option_id::varchar as o,
                      row_number() over (order by urun_id::varchar) - 1 as kod,
                      lansman_tarihi::date as lansman, cikis_tarihi::date as cikis
               from urun),
        ok as (select o, row_number() over (order by o) - 1 as kod
               from (select distinct option_id::varchar as o from urun)),
        son as (select max(tarih::date) as g from depo_stok),
        gun as (select unnest(generate_series(date '{bas}', date '{bit}',
                                              interval 1 day))::date as d),
        depo as (select urun_id::varchar as u, tarih::date as g, adet from depo_stok),
        sat as (
            select urun_id::varchar as u, tarih::date as g,
                   sum(adet) as net, sum(adet) filter (where adet > 0) as brut
            from {satis} where magaza_id::varchar = 'ONL' group by 1, 2),
        teslim as (
            select urun_id::varchar as u, gerceklesen_teslim::date as g, sum(adet) as n
            from siparis where gerceklesen_teslim is not null group by 1, 2),
        varis as (
            select urun_id::varchar as u, varis_tarihi::date as g, sum(adet) as n
            from sevkiyat where hedef::varchar = 'DEPO' and varis_tarihi is not null
            group by 1, 2),
        cikis as (
            select urun_id::varchar as u, tarih::date as g, sum(adet) as n
            from sevkiyat where kaynak::varchar = 'DEPO' group by 1, 2),
        kur as (
            select g.d, uk.kod as urun, uk.o,
                   coalesce(a.net, 0) as net, coalesce(a.brut, 0) as brut,
                   case when g.d < son.g
                        then coalesce(dn.adet, 0) + coalesce(a.net, 0)
                        else coalesce(db.adet, 0) + coalesce(t.n, 0)
                             + coalesce(v.n, 0) - coalesce(c.n, 0) end as satis_oncesi
            from gun g
            cross join son
            join uk on uk.lansman <= g.d and (uk.cikis is null or g.d < uk.cikis)
            left join depo dn on dn.u = uk.u and dn.g = g.d + 1
            left join depo db on db.u = uk.u and db.g = g.d
            left join sat a on a.u = uk.u and a.g = g.d
            left join teslim t on t.u = uk.u and t.g = g.d
            left join varis v on v.u = uk.u and v.g = g.d
            left join cikis c on c.u = uk.u and c.g = g.d
            where g.d <= son.g)
        select (kur.d - date '1970-01-01')::int as gun,
               mk.kod as magaza, kur.urun as urun, ok.kod as opsiyon,
               kur.satis_oncesi::int as satis_oncesi,
               kur.brut::int as brut_satis,
               kur.net::int as net_satis,
               case when kur.satis_oncesi <= 0 then 2
                    when kur.brut >= kur.satis_oncesi then 1 else 0 end::tinyint as durum
        from kur cross join mk
        join ok on ok.o = kur.o
        order by kur.d, kur.urun
    """).fetchnumpy()

    return _tablo(ham, kategoriler)
