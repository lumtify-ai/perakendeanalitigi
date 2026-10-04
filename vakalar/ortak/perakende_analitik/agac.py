"""Kayıp satışın kaynak ağacı: her kayıp hücre-günden hangi süreç sorumlu (spec §4.6).

`kaynak_ata(kayip_df, con)` Kayıp tablosunun (stok.gunluk_* + `kayip.kayip_yaz`
sütunları; yalnız `bos` / `tukenen` günler, mağazalar ve `ONL`) her satırına tek
dal atar ve `kaynak` ile `firsat` sütunlarını ekler. Satır sırası, indeks ve
bütün girdi sütunları korunur; girdi değişmez.

Kurallar, bu sırayla, ilk tutan kazanır:

    1. lojistik     hücreye giden bir sevk için `tarih + beklenen(kaynak, m) <= d <
                    varis_tarihi` (varış beklenenden geç). Beklenen süre rotanın
                    (kaynak, hedef) en sık `varis - tarih` değeridir (beraberlikte
                    küçük); rotanın geçmişi yoksa `yol_suresi[m]` (R19). `varis_tarihi` boş
                    sevk (kirli tek taraflı transfer) lojistik DEĞİLDİR. `ONL`
                    sevkin ucu olmadığı için online'da hiç tutmaz
    2. magaza       mal mağaza deposunda; v4'te ölçülemez, hiçbir satır buraya
                    düşmez (kural yine de dal listesinde durur)
    3. fırsat       mağazada x = d - yol_suresi[m]; fırsat = x'e denk gelen ya da
                    ondan önceki son pazartesi. Online'da fırsat = d.
                    `firsat < 2023-01-01` -> bilinmiyor (depo_stok pencerede başlar)
    4. allocation   (yalnız mağaza) fırsatta depoda o SKU vardı:
                    depo_stok(fırsat) + Σ siparis.adet (gerceklesen_teslim = fırsat) > 0.
                    Motor sırası: pazartesi tedarikçi teslimleri depoya
                    replenishment ÇIKIŞINDAN önce girer, `depo_stok(d)` ise teslimlerden
                    ÖNCEKİ sabah fotoğrafıdır; bu yüzden fırsat günü teslimi eklenir
                    (brüt; hatalı mal oranı yayımlanmış veriden bilinmez).
                    Fırsattan bir gün önce (önceki gece) giren mal sayılmaz
    5. tedarik      o SKU için `planlanan_teslim <= fırsat` ve (`gerceklesen_teslim >
                    fırsat` ya da boş) olan sipariş var: zamanında gelseydi
                    fırsatta depoda olurdu
    6. planlama     diğerleri (yeterince alınmamış ya da RPT verilmemiş)

`yol_suresi` sözlüğünde olmayan (depodan hiç sevk almamış) mağaza için bilinen
yolların üst medyanı kullanılır. Online'ın fırsatı `d` olduğundan online için
yalnız tedarik / planlama çıkar (pencere içinde `bilinmiyor` de olmaz).

Hız ve bellek: girdi ~16 M satıra çıkabilir. Satır başına Python yok. Fırsat
numpy tamsayı aritmetiğiyle (gün sayısı), allocation ve tedarik farklı
(SKU, fırsat) çiftleri üzerinde DuckDB'de (en çok SKU x pazartesi ~1,3 M çift)
hesaplanıp satırlara dağıtılır; lojistik yalnız geç varan sevklerin
(mağaza, SKU) anahtarına düşen satırlar üzerinde aralık birleşimiyle.
"""

import duckdb
import numpy as np
import pandas as pd

from perakende_analitik import ozellikler

DALLAR = ("lojistik", "magaza", "allocation", "tedarik", "planlama", "bilinmiyor")
_LOJISTIK, _MAGAZA, _ALLOCATION, _TEDARIK, _PLANLAMA, _BILINMIYOR = range(6)

_ONLINE = "ONL"
_PENCERE_BASI = np.datetime64("2023-01-01", "D").astype(np.int64)   # 1970'ten gün sayısı
_PAZARTESI_KAYDIRMA = 3   # 1970-01-01 perşembe: (gün + 3) % 7 == 0  <=>  pazartesi


def _kategori(seri: pd.Series) -> tuple[np.ndarray, pd.Index]:
    """Anahtar sütununun (kodlar int32, kategoriler); `category` ise yeniden kodlanmaz."""
    kat = seri if isinstance(seri.dtype, pd.CategoricalDtype) else seri.astype("category")
    return kat.cat.codes.to_numpy().astype(np.int32), kat.cat.categories


def _yol_tablosu(con: duckdb.DuckDBPyConnection) -> tuple[dict[str, int], int]:
    """(mağaza -> yol süresi, sözlükte olmayan mağaza için yedek: üst medyan)."""
    yol = ozellikler.yol_suresi(con)
    yedek = int(sorted(yol.values())[len(yol) // 2]) if yol else 0
    return yol, yedek


def _gec_sevkler(con, yol: dict[str, int], yedek: int) -> pd.DataFrame:
    """Beklenenden geç varan sevkler: magaza_id, urun_id, lo (beklenen varış gün sayısı),
    hi (gerçek varış). Boş `varis_tarihi` hiç gelmez (NULL karşılaştırması tutmaz).

    Beklenen süre rotaya (kaynak, hedef) özgüdür: o rotanın dolu `varis_tarihi`li
    sevklerindeki en sık `varis - tarih` (beraberlikte küçük). Rotanın hiç geçmişi
    yoksa hedef mağazanın depo yolu kullanılır (R19)."""
    tablo = pd.DataFrame({"magaza_id": list(yol), "yol": np.asarray(list(yol.values()),
                                                                      dtype=np.int32)})
    con.register("_yol_tablosu", tablo)
    try:
        return con.execute(f"""
            with g as (
                select kaynak::varchar as kaynak, hedef::varchar as hedef,
                       urun_id::varchar as urun_id,
                       date_diff('day', date '1970-01-01', tarih::date) as t0,
                       date_diff('day', date '1970-01-01', varis_tarihi::date) as hi
                from sevkiyat where varis_tarihi is not null),
            rota as (
                select kaynak, hedef, hi - t0 as sure from g
                group by kaynak, hedef, hi - t0
                qualify row_number() over (partition by kaynak, hedef
                                           order by count(*) desc, hi - t0) = 1),
            s as (
                select g.hedef as magaza_id, g.urun_id,
                       g.t0 + coalesce(r.sure, y.yol, {yedek}) as lo, g.hi
                from g left join rota r on r.kaynak = g.kaynak and r.hedef = g.hedef
                       left join _yol_tablosu y on y.magaza_id = g.hedef
                where g.hedef not in ('{_ONLINE}', 'DEPO'))
            select magaza_id, urun_id, lo::int as lo, hi::int as hi from s where lo < hi
        """).fetchdf()
    finally:
        con.unregister("_yol_tablosu")


def _lojistik(con, yol, yedek, mk, mkat, uk, ukat, gun) -> np.ndarray:
    """Her satır için: geç varan bir sevkin [lo, hi) aralığında mı (bool)."""
    sonuc = np.zeros(len(gun), dtype=bool)
    gec = _gec_sevkler(con, yol, yedek)
    if gec.empty:
        return sonuc
    m_kod = mkat.get_indexer(gec["magaza_id"])
    u_kod = ukat.get_indexer(gec["urun_id"])
    tutan = (m_kod >= 0) & (u_kod >= 0)
    if not tutan.any():
        return sonuc
    nu = np.int64(len(ukat))
    iv = pd.DataFrame({"anahtar": m_kod[tutan].astype(np.int64) * nu + u_kod[tutan],
                       "lo": gec["lo"].to_numpy()[tutan], "hi": gec["hi"].to_numpy()[tutan]})
    anahtar = mk.astype(np.int64) * nu + uk
    aday = np.flatnonzero(np.isin(anahtar, iv["anahtar"].to_numpy()))
    if not len(aday):
        return sonuc
    satir = pd.DataFrame({"sira": aday.astype(np.int64), "anahtar": anahtar[aday],
                          "gun": gun[aday]})
    con.register("_lj_satir", satir)
    con.register("_lj_aralik", iv)
    try:
        bulunan = con.execute("""
            select distinct s.sira from _lj_satir s
            join _lj_aralik a on a.anahtar = s.anahtar and s.gun >= a.lo and s.gun < a.hi
        """).fetchnumpy()["sira"]
    finally:
        con.unregister("_lj_satir")
        con.unregister("_lj_aralik")
    sonuc[bulunan] = True
    return sonuc


def _firsatta_depo_ve_tedarik(con, uk, ukat, firsat) -> tuple[np.ndarray, np.ndarray]:
    """Satır başına (fırsatta depoda mal var, tedarik gecikmesi var); farklı
    (SKU, fırsat) çiftleri üzerinden hesaplanıp satırlara dağıtılır."""
    f0 = int(firsat.min())
    aralik = np.int64(int(firsat.max()) - f0 + 1)
    anahtar = uk.astype(np.int64) * aralik + (firsat - f0)
    cift, ters = np.unique(anahtar, return_inverse=True)
    pairs = pd.DataFrame({"pid": np.arange(len(cift), dtype=np.int64),
                          "uk": (cift // aralik).astype(np.int32),
                          "f": (cift % aralik + f0).astype(np.int32)})
    urunler = pd.DataFrame({"uk": np.arange(len(ukat), dtype=np.int32),
                            "urun_id": np.asarray(ukat, dtype=object)})
    con.register("_ag_cift", pairs)
    con.register("_ag_urun", urunler)
    try:
        ham = con.execute("""
            with p as (
                select c.pid, u.urun_id, date '1970-01-01' + c.f * interval 1 day as fd
                from _ag_cift c join _ag_urun u using (uk)),
            d as (select urun_id::varchar as urun_id, tarih::date as tarih, sum(adet) as adet
                  from depo_stok group by 1, 2),
            g as (select urun_id::varchar as urun_id, gerceklesen_teslim::date as tarih,
                         sum(adet) as adet
                  from siparis where gerceklesen_teslim is not null group by 1, 2),
            t as (select p.pid, count(*) as n
                  from p join siparis s on s.urun_id::varchar = p.urun_id
                      and s.planlanan_teslim::date <= p.fd
                      and (s.gerceklesen_teslim is null or s.gerceklesen_teslim::date > p.fd)
                  group by 1)
            select p.pid, coalesce(d.adet, 0) + coalesce(g.adet, 0) > 0 as depoda,
                   coalesce(t.n, 0) > 0 as tedarik
            from p
            left join d on d.urun_id = p.urun_id and d.tarih = p.fd
            left join g on g.urun_id = p.urun_id and g.tarih = p.fd
            left join t on t.pid = p.pid
        """).fetchnumpy()
    finally:
        con.unregister("_ag_cift")
        con.unregister("_ag_urun")
    depoda = np.zeros(len(cift), dtype=bool)
    tedarik = np.zeros(len(cift), dtype=bool)
    depoda[ham["pid"]] = ham["depoda"]
    tedarik[ham["pid"]] = ham["tedarik"]
    return depoda[ters], tedarik[ters]


def kaynak_ata(kayip_df: pd.DataFrame, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Her satıra tek kaynak ata; `kaynak` (category, kategoriler `DALLAR`) ve
    `firsat` (datetime64[ns]) sütunlarını ekler. Girdi sütunları paylaşılır
    (kopyalanmaz), satır sırası ve indeks aynen kalır."""
    cikti = kayip_df.copy(deep=False)
    n = len(kayip_df)
    if n == 0:
        cikti["kaynak"] = pd.Categorical([], categories=DALLAR)
        cikti["firsat"] = pd.Series([], dtype="datetime64[ns]", index=cikti.index)
        return cikti

    gun = (kayip_df["tarih"].to_numpy().astype("datetime64[D]").astype(np.int64)
           .astype(np.int32))
    mk, mkat = _kategori(kayip_df["magaza_id"])
    uk, ukat = _kategori(kayip_df["urun_id"])

    yol, yedek = _yol_tablosu(con)
    yol_kat = np.array([-1 if m == _ONLINE else yol.get(m, yedek) for m in mkat],
                       dtype=np.int32)
    yol_satir = yol_kat[mk]
    online = yol_satir < 0

    # fırsat: mağazada x = d - yol'a denk gelen ya da ondan önceki son pazartesi
    x = gun - np.where(online, 0, yol_satir)
    firsat = np.where(online, gun, x - (x + _PAZARTESI_KAYDIRMA) % 7).astype(np.int32)

    bilinmiyor = firsat < _PENCERE_BASI
    lojistik = _lojistik(con, yol, yedek, mk, mkat, uk, ukat, gun)

    kod = np.full(n, _PLANLAMA, dtype=np.int8)
    bakilacak = np.flatnonzero(~bilinmiyor)
    if len(bakilacak):
        depoda, tedarik = _firsatta_depo_ve_tedarik(con, uk[bakilacak], ukat,
                                                    firsat[bakilacak])
        alt = np.full(len(bakilacak), _PLANLAMA, dtype=np.int8)
        alt[tedarik] = _TEDARIK
        alt[depoda & ~online[bakilacak]] = _ALLOCATION
        kod[bakilacak] = alt
    kod[bilinmiyor] = _BILINMIYOR
    kod[lojistik] = _LOJISTIK

    cikti["kaynak"] = pd.Categorical.from_codes(kod, categories=list(DALLAR))
    cikti["firsat"] = firsat.astype("datetime64[D]").astype("datetime64[ns]")
    return cikti
