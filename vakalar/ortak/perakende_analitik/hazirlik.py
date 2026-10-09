"""Hazırlık adımları: günlük tablo, çarpanlar ve kestirici başına kayıp tablosu.

Vakalar (yok-satma, blok-transfer) bu adımları kendi akışlarından, kendi pencere
ve önbellek kurallarıyla çağırır; akış (CLI, önbellek, ölçüm) vakada kalır, adımın
kendisi burada durur.

    gunluk_yaz     `stok.gunluk_magaza` + `stok.gunluk_online`, `pencere` içindeki
                   bütün uygun satırlar (stoklu dahil). Yıl yıl kurulur ve parquet'e
                   satır grubu olarak eklenir: bütün pencere bellekte hiç birlikte
                   durmaz.
    carpanlar_yaz  `carpanlar.ogren`, yalnız `ogrenme_bitis`e dek stoklu günlerle
    carpanlar_kapanmis
                   karar anı çarpanları: `carpanlar.ogren`, yalnız karar anında
                   kapanmış sezonların stoklu günleriyle (`talep.Basit(karar_ani=t)`
                   için; dosyaya yazmaz, `Carpanlar` döndürür)
    kestirici      "naif" / "basit" / "ml"
    kayip_yaz      bir kestiricinin kayıp tablosu: `egit` bütün pencerenin stoklu
                   günleriyle, `tahmin` ve `kayip.kayip_yaz` yalnız `bos` ve
                   `tukenen` satırlarına (R5); sonra `agac.kaynak_ata`

`kayip_yaz` iki isteğe bağlı kısıt alır. `hedef_araligi=(bas, bit)` tahmini ve
kaybı yalnız `[bas, bit)` içindeki `bos`/`tukenen` satırlarına yazar; eğitim
havuzu değişmez, yani kestirici aralıksız çağrıdakiyle aynı gözlemlerden öğrenir.
`agacli=False` `agac.kaynak_ata`yı atlar (`kaynak` ve `firsat` sütunları olmaz).

Yazımlar atomiktir: önce `<dosya>.yaziliyor`, sonra `replace`; yazım yarıda
kesilirse hedef dosya olduğu gibi kalır ve ara dosya silinir. Bellek: her adım
parquet'ten yalnız ihtiyaç duyduğu sütun ve satırları okur; `ozellikler.ekle`
yalnız kestiricinin okuduğu sütunları hesaplar; kestiriciler arasında her şey
bırakılır (`gc.collect`). Gizli gerçeğe (`hakem`) dokunulmaz.
"""

import gc
import pickle
from collections.abc import Callable
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from perakende_analitik import agac, carpanlar, kayip, ozellikler, stok, talep

GUNLUK_SUTUNLARI = ["tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi",
                    "brut_satis", "net_satis", "durum"]
# gözlem havuzundan okunan günlük sütunları (satis_oncesi ve net_satis hiçbir
# kestiricide okunmaz; durum yalniz_stoklu ve ML'in havuz üyeliği için)
_GOZLEM_SUTUNLARI = ["tarih", "magaza_id", "urun_id", "option_id", "brut_satis", "durum"]

# `carpanlar.ogren` ve `carpanlar.karakter`in okuduğu özellik sütunları
CARPAN_OZELLIKLERI = ["hafta_gunu", "tatil", "black_friday", "indirim_baslangici",
                      "markdown_orani", "kampanya_orani", "kampanya_id", "oran", "yas_gun",
                      "line", "ust_kategori", "alt_kategori", "kanal"]
# kestirici -> egit / tahmin'in okuduğu özellik sütunları
KESTIRICI_OZELLIKLERI = {
    "naif": ["line", "alt_kategori"],
    "basit": ["hafta_gunu", "tatil", "black_friday", "indirim_baslangici", "oran", "yas_gun",
              "line", "ust_kategori", "alt_kategori", "kanal"],
    "ml": sorted(set(talep.ML_SAYISAL) | set(talep.ML_KATEGORIK) | {"line", "alt_kategori"}),
}


# --------------------------------------------------------------- yardımcılar

def _oku(yol: Path, sutunlar: list[str], durumlar: tuple[str, ...],
         bitis: pd.Timestamp | None = None,
         aralik: tuple[date, date] | None = None) -> pd.DataFrame:
    """gunluk.parquet'ten istenen sütunlar, yalnız `durumlar`daki satırlar;
    `bitis` verilirse o güne dek (dahil), `aralik=(bas, bit)` verilirse
    `[bas, bit)` içindekiler. Kategoriler yazıldığı gibi döner (bütün evren)."""
    filtre = [("durum", "in", list(durumlar))]
    if bitis is not None:
        filtre.append(("tarih", "<=", bitis))
    if aralik is not None:
        filtre.append(("tarih", ">=", pd.Timestamp(aralik[0])))
        filtre.append(("tarih", "<", pd.Timestamp(aralik[1])))
    return pd.read_parquet(yol, columns=sutunlar, filters=filtre).reset_index(drop=True)


def _atomik(yol: Path, ek: str, yaz: Callable[[Path], None]) -> None:
    """`yaz(gecici)` ile ara dosyayı yazar, başarılıysa `yol`un üstüne taşır;
    hata olursa ara dosya silinir, `yol` dokunulmaz kalır."""
    gecici = yol.with_suffix(ek)
    try:
        yaz(gecici)
        gecici.replace(yol)
    except BaseException:
        gecici.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------- adımlar

def gunluk_yaz(con, yol: Path, pencere: tuple[date, date]) -> int:
    """Mağaza ve online günlük tablosu `pencere` (iki ucu dahil) boyunca yıl yıl;
    satır sayısını döndürür."""
    sayac = [0]

    def yaz(gecici: Path) -> None:
        yazici = None
        try:
            for yil in range(pencere[0].year, pencere[1].year + 1):
                bas, bit = max(date(yil, 1, 1), pencere[0]), min(date(yil, 12, 31), pencere[1])
                for parca in (stok.gunluk_magaza, stok.gunluk_online):
                    df = parca(con, bas, bit)
                    tablo = pa.Table.from_pandas(df[GUNLUK_SUTUNLARI], preserve_index=False)
                    del df
                    if yazici is None:
                        yazici = pq.ParquetWriter(gecici, tablo.schema)
                    yazici.write_table(tablo)
                    sayac[0] += tablo.num_rows
                    del tablo
                    gc.collect()
        finally:
            if yazici is not None:
                yazici.close()

    _atomik(yol, ".parquet.yaziliyor", yaz)
    return sayac[0]


def carpanlar_yaz(con, gunluk: Path, yol: Path, ogrenme_bitis: date) -> int:
    """`ogrenme_bitis`e dek (dahil) stoklu günlerden çarpanlar; öğrenilen satır
    sayısını döndürür."""
    df = _oku(gunluk, _GOZLEM_SUTUNLARI, ("stoklu",), pd.Timestamp(ogrenme_bitis))
    df = ozellikler.ekle(con, df, CARPAN_OZELLIKLERI)
    c = carpanlar.ogren(df)
    n = len(df)
    del df
    gc.collect()

    def yaz(gecici: Path) -> None:
        with open(gecici, "wb") as f:
            pickle.dump(c, f)

    _atomik(yol, ".pkl.yaziliyor", yaz)
    return n


def _ilk_tarih(gunluk: Path) -> pd.Timestamp:
    """gunluk.parquet'in ilk günü (satır grubu istatistiklerinden; yoksa sütundan)."""
    meta = pq.ParquetFile(gunluk).metadata
    i = meta.schema.to_arrow_schema().get_field_index("tarih")
    enler = []
    for g in range(meta.num_row_groups):
        st = meta.row_group(g).column(i).statistics
        if st is None or not st.has_min_max:
            enler = None
            break
        enler.append(pd.Timestamp(st.min))
    if enler:
        return min(enler)
    return pd.Timestamp(pd.read_parquet(gunluk, columns=["tarih"])["tarih"].min())


def kapanmis_sezonlar(con, gunluk: Path, karar_ani: date) -> pd.DataFrame:
    """`karar_ani`de kapanmış ve günlük pencereye bütünüyle giren sezonlar:
    `sezon_kodu, lansman, cikis` (dalgaların en erken lansmanı, en geç çıkışı);
    `cikis < karar_ani` ve `lansman >=` günlük tablonun ilk günü (pencerenin
    başında yarım kalan sezon, v4'te AW22, kullanılmaz)."""
    s = con.execute("""
        select sezon_kodu::varchar as sezon_kodu, min(lansman_tarihi) as lansman,
               max(cikis_tarihi) as cikis
        from sezon group by 1 order by 2
    """).fetchdf()
    t = pd.Timestamp(karar_ani)
    return s[(s["cikis"] < t) & (s["lansman"] >= _ilk_tarih(gunluk))].reset_index(drop=True)


def carpanlar_kapanmis(con, gunluk: Path, karar_ani: date) -> carpanlar.Carpanlar:
    """Karar anında bilinen çarpanlar: `carpanlar.ogren`, yalnız `karar_ani`de
    kapanmış sezonların (`kapanmis_sezonlar`) stoklu günleriyle.

    Satırlar: `tarih < karar_ani`, `durum = stoklu` ve ya ürünün sezonu kapanmış
    ya da ürün devamlı (`DEVAMLI`) ve gün kapanmış sezonların aralığında
    `[ilk lansman, son çıkış)`. Devamlı ürünlerin günleri böylece karar anına dek
    haftadan haftaya büyümez: çarpanlar yalnız kapanmış sezon kümesiyle değişir
    (çağıran sezon başına önbellekleyebilir). Özellik sütunları `carpanlar_yaz`ınki
    (`CARPAN_OZELLIKLERI`). Kapanmış sezon yoksa ValueError."""
    sezonlar = kapanmis_sezonlar(con, gunluk, karar_ani)
    if sezonlar.empty:
        raise ValueError(f"carpanlar_kapanmis: {karar_ani} tarihinde kapanmış sezon yok")
    bas, son = sezonlar["lansman"].min(), sezonlar["cikis"].max()
    t = pd.Timestamp(karar_ani)
    df = _oku(gunluk, _GOZLEM_SUTUNLARI, ("stoklu",), aralik=(bas, t))
    urun = con.execute("select urun_id::varchar as urun_id, sezon_kodu::varchar as sezon "
                       "from urun").fetchdf()
    kapali = set(sezonlar["sezon_kodu"])
    # ürün kategorisi başına: 1 kapanmış sezon, 2 devamlı, 0 öteki (satır başına Python yok)
    tur = urun.set_index("urun_id")["sezon"].map(
        lambda z: 1 if z in kapali else (2 if z == "DEVAMLI" else 0))
    kat = df["urun_id"].astype("category")
    kod = tur.reindex(kat.cat.categories.astype(str)).fillna(0).to_numpy(np.int8)
    kodlar = kat.cat.codes.to_numpy()
    satir = np.where(kodlar >= 0, kod[np.maximum(kodlar, 0)], 0)
    sec = (satir == 1) | ((satir == 2) & (df["tarih"] < son).to_numpy())
    df = df[sec].reset_index(drop=True)
    df = ozellikler.ekle(con, df, CARPAN_OZELLIKLERI)
    c = carpanlar.ogren(df)
    del df
    gc.collect()
    return c


def kestirici(ad: str, carpan: Path):
    """`ad` kestiricisi ("naif", "basit", "ml"); Basit için `carpan` pickle'ı okunur."""
    if ad == "naif":
        return talep.Naif()
    if ad == "basit":
        with open(carpan, "rb") as f:
            return talep.Basit(carpanlar=pickle.load(f))
    if ad == "ml":
        return talep.ML()
    raise ValueError(f"bilinmeyen kestirici: {ad}")


def kayip_yaz(con, ad: str, gunluk: Path, carpan: Path, yol: Path,
              hedef_araligi: tuple[date, date] | None = None, agacli: bool = True) -> dict:
    """Bir kestiricinin kayıp tablosu (bos + tukenen satırları).

    `hedef_araligi=(bas, bit)` verilirse yalnız `[bas, bit)` içindeki satırlara
    tahmin ve kayıp yazılır; eğitim havuzu (bütün pencerenin stoklu günleri)
    değişmez. `agacli=False` kaynak ağacını atlar (`kaynak`, `firsat` olmaz).
    Dönüş: havuz_satir, hedef_satir, kuyruk_satir, toplam_kayip."""
    gerek = KESTIRICI_OZELLIKLERI[ad]
    k = kestirici(ad, carpan)

    gozlem = _oku(gunluk, _GOZLEM_SUTUNLARI, ("stoklu",))
    havuz = len(gozlem)
    gozlem = ozellikler.ekle(con, gozlem, gerek)
    k.egit(gozlem)
    del gozlem
    gc.collect()

    hedef = _oku(gunluk, GUNLUK_SUTUNLARI, ("bos", "tukenen"), aralik=hedef_araligi)
    tahmin = k.tahmin(ozellikler.ekle(con, hedef, gerek))
    del k
    gc.collect()
    kd = kayip.kayip_yaz(hedef, tahmin)
    kuyruk = int(kd.attrs.get("kuyruk_satir", 0))
    del tahmin, hedef
    if agacli:
        kd = agac.kaynak_ata(kd, con)

    _atomik(yol, ".parquet.yaziliyor", lambda gecici: kd.to_parquet(gecici, index=False))
    ozet = {"havuz_satir": havuz, "hedef_satir": len(kd),
            "kuyruk_satir": kuyruk,
            "toplam_kayip": float(kd["kayip"].sum())}
    del kd
    gc.collect()
    return ozet
