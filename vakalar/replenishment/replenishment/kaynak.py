"""Yayımlanan v4 verisinden okuma ve dünyanın açık alanlarından hücre haritası.

İki iş, tek kural: bu modül gizli gerçeğe (`perakende_veri`), motora
(`replenishment.motor`) ve hakeme dokunmaz. Veri `veri/cikti/v4/perakende.duckdb`
(ya da `PERAKENDE_V4_DB`) üstünden ortak paketin bağlantısı ve temizlik
görünümleriyle okunur; harita, çağıranın verdiği dünya nesnesinin yalnız
kamuya açık alanlarını okur (`hucre_*`, `sku_option`, `sku_beden_payi`,
`optionlar`, `urunler`).

**Veri.**

    fiziksel_magazalar   84 fiziksel mağaza; Ali (İstanbul) / Veli (Anadolu) ayrımı `istanbul`
    haftalik_replenishment
                         depodan fiziksel mağazaya `replenishment` sevkleri, çıkış
                         pazartesisine göre haftalık
    etkin_optionlar      pencereyle kesişen yaşam süreli option'lar (line ile)
    line_haritasi        option -> line

**Günlük matrisler** (`[gün, C]`, C = dünyanın hücre sayısı, ONL hücreleri dahil).
Motorun `Gorunum.satis_gecmisi` / `stoklu_gecmisi` ile aynı anlamdadır; Görev 7'nin
çevrimdışı yolu bunlardan kurulur:

    gunluk_satis_matrisi   brüt satış (pozitif satırlar; iade düşmez) `temiz_satis`
                           üstünden, yani mükerrer satır tek sayılır. Fiziksel hücrede
                           raftan, ONL'de depodan satıştır.
    gunluk_stoklu_matrisi  satış öncesi stok > 0. Fiziksel hücre `stok.gunluk_magaza`,
                           ONL `stok.gunluk_online` tanımıyla; ortak tablonun "uygun"
                           saymadığı hücre-gün (tam olmayan hafta, kapalı mağaza,
                           lansman öncesi, çeşit dışı) `False`.

Matrisin hücre ekseni, `hucre_anahtari(w)`nin `"magaza_id|urun_id"` sırasıdır; anahtar
evreninde olmayan satır sessizce düşer.

**Harita** (`harita_kur`): politikaların hücre / mağaza-option / SKU / option
indislerini her çağrıda yeniden türetmemesi için bir kez kurulan, salt okunur
indis dizileri.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from perakende_analitik import kaynak as ortak
from perakende_analitik import stok

VERITABANI = ortak.VARSAYILAN_YOL
ONLINE = "ONL"


def baglan(yol: Path | str | None = None):
    """v4 DuckDB dosyasına salt okunur bağlanır (ortak `kaynak.baglan`)."""
    return ortak.baglan(yol)


def _gun(g) -> date:
    return pd.Timestamp(g).date()


# ---------------------------------------------------------------------------
# Mağaza, option, replenishment
# ---------------------------------------------------------------------------


def fiziksel_magazalar(con) -> pd.DataFrame:
    """Online hariç mağazalar: `magaza_id, ad, sehir, bolge, istanbul`.

    `istanbul`: şehir İstanbul ise Ali'nin, değilse Veli'nin mağazası. Ayrım
    şehirden yapılır; Marmara bölgesi İstanbul'dan geniştir (Bursa, Kocaeli)."""
    df = con.execute("""
        select magaza_id::varchar as magaza_id, ad::varchar as ad, sehir::varchar as sehir,
               bolge::varchar as bolge
        from magaza where tip::varchar <> 'Online' order by magaza_id::varchar
    """).df()
    df["istanbul"] = (df["sehir"] == "İstanbul").to_numpy(dtype=bool)
    return df


def haftalik_replenishment(con, bas, bit) -> pd.DataFrame:
    """`[bas, bit]` çıkış tarihli, hedefi fiziksel mağaza olan `replenishment` sevkleri.

    Sütunlar: `hafta` (çıkış pazartesisi, Timestamp), `adet`. Hedefi DEPO ya da
    ONL olan, `ilk_dagitim` / `outlet_akisi` / transfer tipleri sayılmaz. Yolda
    kalan (varış tarihi boş) sevk çıkış haftasında sayılır."""
    df = con.execute("""
        select date_trunc('week', s.tarih)::date as hafta, sum(s.adet)::bigint as adet
        from sevkiyat s join magaza m on m.magaza_id::varchar = s.hedef::varchar
        where s.tip::varchar = 'replenishment' and m.tip::varchar <> 'Online'
          and s.tarih::date between ? and ?
        group by 1 order by 1
    """, [_gun(bas), _gun(bit)]).df()
    df["hafta"] = pd.to_datetime(df["hafta"])
    return df


def etkin_optionlar(con, bas, bit) -> pd.DataFrame:
    """`[bas, bit]` ile yaşam süresi kesişen option'lar: `option_id, line`.

    Etkin: `lansman_tarihi <= bit` ve (`cikis_tarihi` boş ya da `> bas`).
    Basic ve NOS'un çıkışı yoktur (sürekli)."""
    return con.execute("""
        select option_id::varchar as option_id, any_value(line::varchar) as line
        from urun
        where lansman_tarihi::date <= ? and (cikis_tarihi is null or cikis_tarihi::date > ?)
        group by option_id order by option_id
    """, [_gun(bit), _gun(bas)]).df()


def line_haritasi(con) -> dict[str, str]:
    """option_id -> line (bütün option'lar)."""
    return dict(con.execute(
        "select option_id::varchar, any_value(line::varchar) from urun group by option_id order by 1"
    ).fetchall())


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

    def hucre(self, magaza, urun) -> np.ndarray:
        """magaza / urun: kategori kodu değil, kimlik dizileri (str)."""
        mi, ui = self.magazalar.get_indexer(magaza), self.urunler.get_indexer(urun)
        sonuc = np.full(len(mi), -1, dtype=np.int64)
        var = (mi >= 0) & (ui >= 0)
        sonuc[var] = self.tablo[mi[var], ui[var]]
        return sonuc

    def kategorik(self, magaza: pd.Categorical, urun: pd.Categorical) -> np.ndarray:
        """Kategori kodlarından (milyonlarca satır): kategorileri bir kez eşler."""
        mk = self.magazalar.get_indexer(pd.Index(magaza.categories.astype(str)))
        uk = self.urunler.get_indexer(pd.Index(urun.categories.astype(str)))
        mi, ui = mk[magaza.codes], uk[urun.codes]
        sonuc = np.full(len(mi), -1, dtype=np.int64)
        var = (mi >= 0) & (ui >= 0)
        sonuc[var] = self.tablo[mi[var], ui[var]]
        return sonuc


def _gun_sayisi(bas: date, bit: date) -> int:
    n = (bit - bas).days + 1
    if n < 1:
        raise ValueError(f"bit ({bit}) bas'tan ({bas}) önce")
    return n


def gunluk_satis_matrisi(con, w_hucre_anahtari: pd.Index, bas, bit) -> np.ndarray:
    """int32 `[gün, C]` brüt satış, gün 0 = `bas`, `[bas, bit]` dahil.

    `temiz_satis` üzerinden: mükerrer satır tek sayılır, iade (negatif satır)
    düşülmez. Anahtar evreninde olmayan (hayalet) hücre satışı atılır."""
    bas, bit = _gun(bas), _gun(bit)
    n, C = _gun_sayisi(bas, bit), len(w_hucre_anahtari)
    ts = ortak.temiz_satis(con)
    df = con.execute(f"""
        select (tarih::date - date '{bas}')::int as g, magaza_id::varchar as m, urun_id::varchar as u,
               sum(adet)::int as adet
        from {ts} where adet > 0 and tarih::date between date '{bas}' and date '{bit}'
        group by 1, 2, 3
    """).df()
    sonuc = np.zeros((n, C), dtype=np.int32)
    h = _HucreIndisi(w_hucre_anahtari).hucre(df["m"].to_numpy().astype(str), df["u"].to_numpy().astype(str))
    var = h >= 0
    # (gün, mağaza, ürün) sorguda tekil; atama toplamaya eşittir
    sonuc[df["g"].to_numpy()[var], h[var]] = df["adet"].to_numpy()[var]
    return sonuc


def gunluk_stoklu_matrisi(con, w_hucre_anahtari: pd.Index, bas, bit) -> np.ndarray:
    """bool `[gün, C]`: hücre-günün satış öncesi stoğu > 0 (`durum != 'bos'`).

    Fiziksel hücreler `stok.gunluk_magaza`, ONL `stok.gunluk_online` tanımıyla.
    Ortak tablonun uygun saymadığı hücre-gün `False`."""
    bas, bit = _gun(bas), _gun(bit)
    n, C = _gun_sayisi(bas, bit), len(w_hucre_anahtari)
    idx = _HucreIndisi(w_hucre_anahtari)
    sonuc = np.zeros((n, C), dtype=bool)
    for kur in (stok.gunluk_magaza, stok.gunluk_online):   # sırayla: tablolar büyük
        tablo = kur(con, bas, bit)
        h = idx.kategorik(tablo["magaza_id"].array, tablo["urun_id"].array)
        g = ((tablo["tarih"] - pd.Timestamp(bas)).dt.days).to_numpy()
        durum = tablo["durum"].cat
        var = (h >= 0) & (durum.codes.to_numpy() != durum.categories.get_loc("bos"))
        sonuc[g[var], h[var]] = True
    return sonuc


# ---------------------------------------------------------------------------
# Hücre haritası
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Harita:
    """Politikaların kullandığı salt okunur indis dizileri (yalnız dünyanın açık alanlarından).

    `eq=False`: dizi alanlarıyla alan alan `==` belirsizdir; eşitlik ve `hash` kimliktendir.

    İndis uzayları: hücre `c` [C], mağaza–option çifti `oc` [OC], SKU `s` [S],
    option `o` [O], mağaza `m`.

    hucre_magaza, hucre_option, hucre_sku  [C]  hücrenin mağaza / option / SKU indisi
    hucre_online                           [C]  bool; ONL hücresi
    oc                                     [C]  hücrenin mağaza–option çifti indisi
    oc_magaza, oc_option                   [OC] çiftin mağaza / option indisi
                                                (çiftler `(mağaza, option)` artan sırada)
    oc_online                              [OC] bool; ONL çifti (fiziksel çiftler `~oc_online`)
    sku_option                             [S]  SKU'nun option indisi
    line                                   [O]  option'ın line'ı (str)
    option_kategori                        [O]  option'ın üst kategorisi (str)
    option_beden_seti                      [O]  option'ın beden seti (str; "Kadın Harf", "Standart", ...)
    sku_beden                              [S]  SKU'nun beden sırası (1..; `urunler.beden_sira`)
    sku_beden_payi                         [S]  zincir beden eğrisi payı (option içinde toplam 1)

    Son dört alan beden bölmesi içindir (`ihtiyac`): bir mağazanın aynı üst
    kategori ve beden setindeki option'ları aynı beden sırasında havuzlanır.
    """

    hucre_magaza: np.ndarray
    hucre_option: np.ndarray
    hucre_sku: np.ndarray
    hucre_online: np.ndarray
    oc: np.ndarray
    oc_magaza: np.ndarray
    oc_option: np.ndarray
    oc_online: np.ndarray
    sku_option: np.ndarray
    line: np.ndarray
    option_kategori: np.ndarray
    option_beden_seti: np.ndarray
    sku_beden: np.ndarray
    sku_beden_payi: np.ndarray

    def __post_init__(self):
        for ad in self.__dataclass_fields__:
            a = getattr(self, ad).view()
            a.flags.writeable = False
            object.__setattr__(self, ad, a)


def harita_kur(w) -> Harita:
    """Dünyanın açık alanlarından (`hucre_*`, `sku_option`, `sku_beden_payi`,
    `optionlar`, `urunler`) harita kurar.

    `w` bir dünya nesnesidir (bu modül `perakende_veri`yi içe aktarmaz); gizli
    alanlara (`lam`, `gizli_*`, `esneklik*`, ...) dokunmaz."""
    hm = np.asarray(w.hucre_magaza, dtype=np.int64)
    ho = np.asarray(w.hucre_option, dtype=np.int64)
    O = len(w.optionlar)
    cift, oc = np.unique(hm * O + ho, return_inverse=True)
    hucre_online = np.asarray(w.hucre_online, dtype=bool)
    oc_online = np.zeros(len(cift), dtype=bool)
    oc_online[oc] = hucre_online
    return Harita(
        hucre_magaza=hm.copy(), hucre_option=ho.copy(), hucre_sku=np.asarray(w.hucre_sku, dtype=np.int64).copy(),
        hucre_online=hucre_online.copy(), oc=oc.reshape(-1).astype(np.int64),
        oc_magaza=cift // O, oc_option=cift % O, oc_online=oc_online,
        sku_option=np.asarray(w.sku_option, dtype=np.int64).copy(),
        line=w.optionlar["line"].to_numpy().astype(str),
        option_kategori=w.optionlar["ust_kategori"].to_numpy().astype(str),
        option_beden_seti=w.optionlar["beden_seti"].to_numpy().astype(str),
        sku_beden=w.urunler["beden_sira"].to_numpy().astype(np.int64),
        sku_beden_payi=np.asarray(w.sku_beden_payi, dtype=float).copy(),
    )
