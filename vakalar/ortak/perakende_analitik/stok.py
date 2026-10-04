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
satır tek sayılır). `ONL` bu fonksiyonda yoktur (çevrimiçi ayrı fonksiyon).

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
`int32`, `tarih` Arrow `date32` (4 bayt, değerleri `datetime.date`). Satır
başına ~22 bayt; üç yıllık bütün pencere (67,7 M satır) 1,5 GB, 2025 yalnız 0,5 GB.
Kimlikleri düz metin olarak çekmemek için SQL kodları üretir, kategoriler
ayrıca okunur.
"""

from datetime import date

import duckdb
import pandas as pd
import pyarrow as pa

from perakende_analitik import kaynak

DURUMLAR = ["stoklu", "tukenen", "bos"]


def _gun(g) -> date:
    return pd.Timestamp(g).date()


def gunluk_magaza(con: duckdb.DuckDBPyConnection, bas: date, bit: date) -> pd.DataFrame:
    """[bas, bit] aralığındaki uygun mağaza hücre-günlerinin günlük tablosu.

    Sütunlar: tarih, magaza_id, urun_id, option_id, satis_oncesi, brut_satis,
    net_satis, durum. Sıra: tarih, magaza_id, urun_id."""
    bas, bit = _gun(bas), _gun(bit)
    satis = kaynak.temiz_satis(con)
    cesit = kaynak.cesit_hucreleri(con)

    magazalar = [r[0] for r in con.execute(
        "select magaza_id::varchar from magaza order by 1").fetchall()]
    urunler = [r[0] for r in con.execute(
        "select urun_id::varchar from urun order by 1").fetchall()]
    opsiyonlar = [r[0] for r in con.execute(
        "select distinct option_id::varchar from urun order by 1").fetchall()]

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

    return pd.DataFrame({
        "tarih": pd.Series(pd.arrays.ArrowExtensionArray(
            pa.array(ham["gun"].astype("int32"), type=pa.int32()).cast(pa.date32()))),
        "magaza_id": pd.Categorical.from_codes(ham["magaza"], categories=magazalar),
        "urun_id": pd.Categorical.from_codes(ham["urun"], categories=urunler),
        "option_id": pd.Categorical.from_codes(ham["opsiyon"], categories=opsiyonlar),
        "satis_oncesi": ham["satis_oncesi"].astype("int32"),
        "brut_satis": ham["brut_satis"].astype("int32"),
        "net_satis": ham["net_satis"].astype("int32"),
        "durum": pd.Categorical.from_codes(ham["durum"], categories=DURUMLAR),
    })
