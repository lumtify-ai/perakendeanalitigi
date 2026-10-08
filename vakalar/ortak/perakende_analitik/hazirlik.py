"""Hazırlık adımları: günlük tablo, çarpanlar ve kestirici başına kayıp tablosu.

Vakalar (yok-satma, blok-transfer) bu adımları kendi akışlarından, kendi pencere
ve önbellek kurallarıyla çağırır; akış (CLI, önbellek, ölçüm) vakada kalır, adımın
kendisi burada durur.

    gunluk_yaz     `stok.gunluk_magaza` + `stok.gunluk_online`, `pencere` içindeki
                   bütün uygun satırlar (stoklu dahil). Yıl yıl kurulur ve parquet'e
                   satır grubu olarak eklenir: bütün pencere bellekte hiç birlikte
                   durmaz.
    carpanlar_yaz  `carpanlar.ogren`, yalnız `ogrenme_bitis`e dek stoklu günlerle
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
