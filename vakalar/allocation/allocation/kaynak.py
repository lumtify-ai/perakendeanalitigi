"""Yayımlanan v4 verisinden okuma, hücre haritası, günlük satış / stoklu matrisleri.

Kural: bu modül gizli gerçeğe (`perakende_veri`), motora (`allocation.motor`) ve hakeme
dokunmaz. Veri `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`) üstünden ortak
paketin bağlantısıyla okunur; harita, çağıranın verdiği dünya nesnesinin yalnız kamuya
açık alanlarını (`magazalar`, `urunler`, `optionlar`, `sezon`, `takvim`, `hucre_*`,
`sku_option`) okur (`lam`, `gizli_*`, `esneklik*`, `ilk_siparisler`, `sapma_*` okunmaz).

**Gün ekseni.** Dünyanın gün indisi: 0 = `takvim`in ilk günü (v4'te 2022-07-04, ısınma
başı; pazartesi), `takvim` satır sırası. Yayımlanan tablolar yalnız 2023-01-01'den
başlar; öncesinin satırı yoktur, matrislerde 0 / `False` kalır ("veri yok", stoksuzluk
değil).

**Günlük matrisler** (`gunluk_matrisler`): `[gün, C]`, C = dünyanın hücre sayısı (ONL
dahil). Motorun `Gorunum.satis_gecmisi` / `stoklu_gecmisi`yle aynı anlamdadır, ama
yayımlanan tablolardan kurulur:

    satış    `satis` tablosunun brüt (pozitif) satırları; iade (negatif satır) düşülmez;
             mükerrer satır tek sayılır (ortak `temiz_satis`). Fiziksel hücrede raftan,
             ONL'de depodan satıştır. `int16` (`Gorunum.satis_gecmisi` gibi).
    stoklu   hücre-günün satış öncesi stoğu > 0.

Stoklu günün yeniden kurulması. Yayımlanan `stok` tablosu yalnız pazartesi sabahı
fotoğrafıdır; günlük stok ondan türetilir. Bu türetme ortak `perakende_analitik.stok`
modülündedir (`gunluk_magaza`: fotoğraf + varışlar - çıkışlar - önceki günlerin net
satışı; `gunluk_online`: ertesi sabahın depo stoğu + günün net online satışı) ve bu
modül onu aynen çağırır; kendi yeniden kurulumunu yazmaz. Böylece "stoklu", RPT / DM
vakalarının `hazirlik.gunluk_yaz` tablosundaki `durum != 'bos'` ile ve motorun
`stoklu_gecmisi`yle (satıştan önceki raf > 0; `Gorunum.satis_oncesi_gecmisi` > 0) aynı
tanımdır; tükenen gün (gün içinde biten raf) stoklu sayılır. Fark yalnız uygunluktadır:
ortak tablonun uygun saymadığı hücre-gün (tam olmayan hafta, kapalı mağaza, lansman
öncesi, çeşit dışı, hiç stoklanmamış hücre) `False` kalır; motorun bayrağı orada da raf
> 0 ise `True` olabilirdi. Uygunluğun iki kuralı bütün tabloya bakar (`bit`'ten bağımsız):
hücrenin ertesi pazartesi fotoğrafının varlığı ve "hiç stoklanmamış hücre" (stok
değerinin kendisi `bit`'ten sonraki günü hiç kullanmaz).

`tablolar` bir koşunun `tablolar`'ı ya da `yayimlanan_tablolar(con)` olabilir; gerekli
tablolar `GUNLUK_TABLOLARI`.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from perakende_analitik import kaynak as ortak
from perakende_analitik import stok

from allocation import sabitler

VERITABANI = ortak.VARSAYILAN_YOL

# Günlük stok kurulumunun (ortak `stok`, `temiz_satis`, `cesit_hucreleri`) okuduğu tablolar
GUNLUK_TABLOLARI = ("satis", "stok", "sevkiyat", "magaza", "magaza_olay", "urun", "depo_stok",
                    "siparis")
_AD = re.compile(r"^[a-z_]+$")


def baglan(yol: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """v4 DuckDB dosyasına salt okunur bağlanır (ortak `kaynak.baglan`)."""
    return ortak.baglan(yol)


def yayimlanan_tablolar(con, adlar: Sequence[str] = GUNLUK_TABLOLARI) -> dict[str, pd.DataFrame]:
    """`adlar` tablolarını DataFrame olarak okur (ad -> tablo, `adlar` sırasıyla).

    Büyük tablolarda kimlikler `category` gelir (DuckDB ENUM); `gunluk_matrisler` bunları
    olduğu gibi kullanır."""
    for ad in adlar:
        if not _AD.match(ad):
            raise ValueError(f"geçersiz tablo adı: {ad!r}")
    return {ad: con.execute(f"select * from {ad}").df() for ad in adlar}


# ---------------------------------------------------------------------------
# Hücre haritası
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Harita:
    """Politikaların kullandığı salt okunur indis dizileri (yalnız dünyanın açık alanlarından).

    `eq=False`: dizi alanlarıyla alan alan `==` belirsizdir; eşitlik ve `hash` kimliktendir.

    İndis uzayları: hücre `c` [C], SKU `s` [S], option `o` [O], mağaza `m` [M].

    hucre_magaza, hucre_option, hucre_sku  [C]  hücrenin mağaza / option / SKU indisi
    hucre_online                           [C]  bool; ONL hücresi
    sku_option                             [S]  SKU'nun option indisi
    sku_beden_sira                         [S]  SKU'nun beden sırası (1..; `urunler.beden_sira`)
    option_line, option_sezon              [O]  option'ın line'ı / sezon kodu (str)
    option_dalga                           [O]  option'ın dalgası (1..3; sürekli mal 0)
    magaza_istanbul                        [M]  bool; şehir İstanbul (Ali; Anadolu Veli)
    magaza_fiziksel                        [M]  bool; ONL ve Outlet tipi mağaza hariç
    """

    hucre_magaza: np.ndarray
    hucre_option: np.ndarray
    hucre_sku: np.ndarray
    hucre_online: np.ndarray
    sku_option: np.ndarray
    sku_beden_sira: np.ndarray
    option_line: np.ndarray
    option_sezon: np.ndarray
    option_dalga: np.ndarray
    magaza_istanbul: np.ndarray
    magaza_fiziksel: np.ndarray

    def __post_init__(self):
        for ad in self.__dataclass_fields__:
            a = getattr(self, ad).view()
            a.flags.writeable = False
            object.__setattr__(self, ad, a)


def harita_kur(w) -> Harita:
    """Dünyanın açık alanlarından harita kurar (diziler kopyadır; `w`ye bağlı kalmaz)."""
    o, m = w.optionlar, w.magazalar
    tip = m["tip"].astype(str).to_numpy()
    return Harita(
        hucre_magaza=np.array(w.hucre_magaza, dtype=np.int64),
        hucre_option=np.array(w.hucre_option, dtype=np.int64),
        hucre_sku=np.array(w.hucre_sku, dtype=np.int64),
        hucre_online=np.array(w.hucre_online, dtype=bool),
        sku_option=np.array(w.sku_option, dtype=np.int64),
        sku_beden_sira=w.urunler["beden_sira"].to_numpy().astype(np.int64),
        option_line=o["line"].to_numpy().astype(str),
        option_sezon=o["sezon_kodu"].to_numpy().astype(str),
        option_dalga=o["dalga"].fillna(0).to_numpy().astype(np.int64),
        magaza_istanbul=(m["sehir"].astype(str) == "İstanbul").to_numpy(dtype=bool),
        magaza_fiziksel=~np.isin(tip, ("Online", "Outlet")),
    )


def oyun_optionlari(w, sezon: str) -> np.ndarray:
    """`sezon`un `LINE` (Collection) option'larının indisleri (`optionlar` satır sırasıyla)."""
    o = w.optionlar
    return np.flatnonzero((o["line"].astype(str) == sabitler.LINE).to_numpy()
                          & (o["sezon_kodu"].astype(str) == sezon).to_numpy()).astype(np.int64)


def erken_kesim(w, sezon: str) -> pd.Timestamp:
    """Erken talep penceresinin en geç kesimi: sezonun `indirim_baslangic`'ı - 29 gün.

    Markdown indirim başlangıcından 28 gün önce başlayabilir; kesim bir gün öncesidir
    (SS25: 2025-06-30 - 29 = 2025-06-01). `sezon` yoksa `KeyError`."""
    s = w.sezon
    ind = s.loc[s["sezon_kodu"].astype(str) == sezon, "indirim_baslangic"].unique()
    if len(ind) == 0:
        raise KeyError(sezon)
    if len(ind) > 1:
        raise ValueError(f"{sezon}: dalgalar farklı indirim_baslangic taşıyor")
    return pd.Timestamp(ind[0]).normalize() - pd.Timedelta(days=sabitler.ERKEN_KESIM_GUN)


# ---------------------------------------------------------------------------
# Günlük matrisler
# ---------------------------------------------------------------------------


def hucre_anahtari(w) -> pd.Index:
    """Dünyanın hücre ekseni: `"magaza_id|urun_id"` dizgileri, `hucre_magaza` /
    `hucre_sku` sırasıyla (`w.magazalar`, `w.urunler` tablolarından)."""
    m = w.magazalar["magaza_id"].to_numpy().astype(str)[np.asarray(w.hucre_magaza)]
    u = w.urunler["urun_id"].to_numpy().astype(str)[np.asarray(w.hucre_sku)]
    return pd.Index(np.char.add(np.char.add(m, "|"), u))


class _HucreIndisi:
    """(magaza_id, urun_id) kimliklerinden hücre indisine; evren dışı -1."""

    def __init__(self, anahtar: pd.Index):
        parca = anahtar.to_series().str.split("|", n=1, expand=True)
        self.magazalar = pd.Index(pd.unique(parca[0]))
        self.urunler = pd.Index(pd.unique(parca[1]))
        self.tablo = np.full((len(self.magazalar), len(self.urunler)), -1, dtype=np.int64)
        self.tablo[self.magazalar.get_indexer(parca[0]), self.urunler.get_indexer(parca[1])] = (
            np.arange(len(anahtar)))

    def _eslestir(self, mi: np.ndarray, ui: np.ndarray) -> np.ndarray:
        sonuc = np.full(len(mi), -1, dtype=np.int64)
        var = (mi >= 0) & (ui >= 0)
        sonuc[var] = self.tablo[mi[var], ui[var]]
        return sonuc

    def hucre(self, magaza, urun) -> np.ndarray:
        """magaza / urun: kimlik dizileri (str)."""
        return self._eslestir(self.magazalar.get_indexer(magaza), self.urunler.get_indexer(urun))

    def kategorik(self, magaza: pd.Categorical, urun: pd.Categorical) -> np.ndarray:
        """Kategori kodlarından (milyonlarca satır): kategorileri bir kez eşler."""
        mk = self.magazalar.get_indexer(pd.Index(magaza.categories.astype(str)))
        uk = self.urunler.get_indexer(pd.Index(urun.categories.astype(str)))
        return self._eslestir(mk[magaza.codes], uk[urun.codes])


def _yillar(bas: pd.Timestamp, son: pd.Timestamp):
    """[bas, son] aralığını takvim yıllarına böler (bellek: yıllık günlük tablo)."""
    for yil in range(bas.year, son.year + 1):
        yield max(bas, pd.Timestamp(yil, 1, 1)), min(son, pd.Timestamp(yil, 12, 31))


def gunluk_matrisler(tablolar: Mapping[str, pd.DataFrame], w, bit: pd.Timestamp
                     ) -> tuple[np.ndarray, np.ndarray]:
    """`bit`'ten (dahil değil) önceki günlerin `(satış int16 [gün, C], stoklu bool [gün, C])`.

    Gün 0 = dünyanın `takvim`inin ilk günü; satır sayısı `bit - takvim[0]` gün. Tanımlar
    modül notunda. `bit` takvimin dışındaysa (`bit < takvim[0]` ya da `bit > takvim[-1] + 1`)
    `ValueError`. Hücre ekseni `hucre_anahtari(w)`; anahtar evreninde olmayan satır
    (hayalet hücre) sessizce düşer."""
    eksik = [ad for ad in GUNLUK_TABLOLARI if ad not in tablolar]
    if eksik:
        raise KeyError(f"tablolar eksik: {eksik}")
    gun0 = pd.Timestamp(w.takvim["tarih"].iloc[0]).normalize()
    bit = pd.Timestamp(bit).normalize()
    n = (bit - gun0).days
    if not 0 <= n <= len(w.takvim):
        raise ValueError(f"bit ({bit.date()}) dünya takviminin ({gun0.date()}, {len(w.takvim)} gün) dışında")
    anahtar = hucre_anahtari(w)
    satis = np.zeros((n, len(anahtar)), dtype=np.int16)
    stoklu = np.zeros((n, len(anahtar)), dtype=bool)
    if n == 0:
        return satis, stoklu
    son = bit - pd.Timedelta(days=1)
    idx = _HucreIndisi(anahtar)

    con = duckdb.connect(":memory:")
    try:
        for ad in GUNLUK_TABLOLARI:
            con.register(ad, tablolar[ad])
        ts = ortak.temiz_satis(con)
        for bas_y, son_y in _yillar(gun0, son):
            df = con.execute(f"""
                select (tarih::date - date '{gun0.date()}')::int as g, magaza_id::varchar as m,
                       urun_id::varchar as u, sum(adet)::bigint as adet
                from {ts} where adet > 0 and tarih::date between date '{bas_y.date()}' and date '{son_y.date()}'
                group by 1, 2, 3
            """).df()
            h = idx.hucre(df["m"].to_numpy().astype(str), df["u"].to_numpy().astype(str))
            var = h >= 0
            adet = df["adet"].to_numpy()[var]
            if adet.size and adet.max() > np.iinfo(np.int16).max:
                raise OverflowError("hücre-gün satışı int16'yı aşıyor")
            # (gün, mağaza, ürün) sorguda tekil; atama toplamaya eşittir
            satis[df["g"].to_numpy()[var], h[var]] = adet
            del df

        ilk = tablolar["stok"]["tarih"].min()
        if pd.notna(ilk):       # fotoğraf yoksa stoklu hiçbir yerde kurulamaz
            for bas_y, son_y in _yillar(max(gun0, pd.Timestamp(ilk).normalize()), son):
                for kur in (stok.gunluk_magaza, stok.gunluk_online):   # sırayla: tablolar büyük
                    tablo = kur(con, bas_y.date(), son_y.date())
                    h = idx.kategorik(tablo["magaza_id"].array, tablo["urun_id"].array)
                    g = (tablo["tarih"] - gun0).dt.days.to_numpy()
                    durum = tablo["durum"].cat
                    var = (h >= 0) & (durum.codes.to_numpy() != durum.categories.get_loc("bos"))
                    stoklu[g[var], h[var]] = True
                    del tablo
    finally:
        con.close()
    return satis, stoklu
