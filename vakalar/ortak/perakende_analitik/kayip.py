"""Kayıp satış: stoksuz günün kaybını yazar ve toplar (spec §4.5).

Girdi günlük tablodur (`stok.gunluk_magaza` / `stok.gunluk_online`) ve her
satıra bir beklenen günlük talep λ̂ (`talep.py` kestiricilerinden). Çağıran
yalnız `bos` ve `tukenen` satırları verir; `stoklu` satır da kabul edilir
(kayıp 0).

    bos       satış 0, talep tamamen karşılanmadı; kayip = λ̂, kayip_saf = λ̂
    tukenen   gün içinde stok bitti: talebin satışı (s = satis_oncesi = brut_satis)
              geçtiği biliniyor. D ~ Poisson(λ̂) için
                  kayip     = E[D | D >= s] - s
                  kayip_saf = max(0, λ̂ - s)        (karşılaştırma için)
              kayip >= kayip_saf: E[D | D >= s] >= max(λ̂, s).
    stoklu    kayip = kayip_saf = 0

**Poisson koşullu fazla.** k·p(k) = λ·p(k-1) olduğundan
E[D | D >= s] = λ·P(D >= s-1) / P(D >= s) ve P(D >= s-1) = P(D >= s) + p(s-1);
fazla = λ - s + s·p(s) / P(D >= s) (s >= 1). İki bölgede hesaplanır:

    s <= λ    P(D >= s) = 1 - Σ_{k<s} p(k) >= ~1/2: kesinti yok; pmf log
              uzayında (`math.lgamma`), aynı s'li satırlar birlikte vektörel.
    s >  λ    P(D >= s)/p(s) = 1 + T, T = λ/(s+1) + λ²/((s+1)(s+2)) + ...
              oranı λ/(s+k) < 1 olan sonlu ilerleyen seri; fazla = λ - s·T/(1+T).
              p(s) hiç hesaplanmadığından s >> λ'da alt taşma yoktur ve kuyruk
              yaklaşımına (λ/(s+1)) gerek kalmaz; fazla onunla uyumludur ve
              onu kuyruğun yüksek mertebeleriyle düzeltir.

P(D >= s) < 1e-12 olan satırlar (kuyruk satırı) yalnız bilgi için sayılır,
kayıt defterine yazılır ve `kayip_yaz` çıktısının `attrs["kuyruk_satir"]`ında
bulunur; bu satırlar da yukarıdaki kesin formülle hesaplanır.

`ozet(kayip_df, duzey, con)` kayıp adedini, etiket fiyatıyla TL'yi ve brüt
marjı toplar: etiket = `liste_fiyati × (1 − oran)` (günün oranı),
kayip_tl = Σ kayip × etiket, kayip_marj = Σ kayip × (etiket − alis_fiyati).
"""

import logging
import math

import duckdb
import numpy as np
import pandas as pd

from perakende_analitik import ozellikler

kayit = logging.getLogger(__name__)

KUYRUK_ESIGI = 1e-12     # P(D >= s) bunun altındaysa satır "kuyruk satırı" sayılır
_SERI_TAVAN = 1_000_000  # üst seri yineleme tavanı (λ/(s+k) < 1: pratikte yüzlerce)


def _lgamma_tablosu(en_buyuk: int) -> np.ndarray:
    """lgamma(k + 1), k = 0 .. en_buyuk."""
    return np.fromiter((math.lgamma(k + 1) for k in range(en_buyuk + 1)),
                       dtype=np.float64, count=en_buyuk + 1)


def _alt_bolge(lam: np.ndarray, s: int) -> np.ndarray:
    """s <= λ: aynı `s`li satırlar için fazla = λ - s + s·p(s) / (1 - cdf(s-1))."""
    lg = _lgamma_tablosu(s)
    log_lam = np.log(lam)
    cdf = np.zeros_like(lam)
    for k in range(s):
        cdf += np.exp(-lam + k * log_lam - lg[k])
    ps = np.exp(-lam + s * log_lam - lg[s])
    return lam - s + s * ps / (1.0 - cdf)


def _ust_bolge(lam: np.ndarray, s: np.ndarray) -> tuple[np.ndarray, int]:
    """s > λ: fazla = λ - s·T/(1+T); (fazla, P(D >= s) < eşik olan satır sayısı)."""
    sf = s.astype(np.float64)
    terim = lam / (sf + 1.0)
    toplam = terim.copy()
    etkin = np.arange(len(lam))
    for j in range(2, _SERI_TAVAN):
        etkin = etkin[terim[etkin] > 1e-17 * (1.0 + toplam[etkin])]
        if not len(etkin):
            break
        terim[etkin] *= lam[etkin] / (sf[etkin] + j)
        toplam[etkin] += terim[etkin]
    fazla = lam - sf * toplam / (1.0 + toplam)
    # log P(D >= s) = log p(s) + log(1 + T)
    benzersiz, ters = np.unique(s, return_inverse=True)
    lg = np.fromiter((math.lgamma(int(k) + 1) for k in benzersiz), np.float64, len(benzersiz))[ters]
    log_q = -lam + sf * np.log(lam) - lg + np.log1p(toplam)
    return fazla, int(np.count_nonzero(log_q < math.log(KUYRUK_ESIGI)))


def poisson_kosullu_fazla_say(lam: np.ndarray, s: np.ndarray) -> tuple[np.ndarray, int]:
    """`poisson_kosullu_fazla` ve P(D >= s) < 1e-12 olan satır sayısı."""
    lam = np.asarray(lam, dtype=np.float64)
    s = np.asarray(s)
    if lam.shape != s.shape or lam.ndim != 1:
        raise ValueError(f"lam ve s ayni uzunlukta 1 boyutlu olmali: {lam.shape} / {s.shape}")
    if not np.isfinite(lam).all():
        raise ValueError("lam sonlu olmali")
    if (lam < 0).any():
        raise ValueError("lam negatif olamaz")
    if len(s) and s.min() < 0:
        raise ValueError("s negatif olamaz")
    s = s.astype(np.int64)

    sonuc = np.zeros(len(lam))
    sifir_s = (s == 0) & (lam > 0)
    sonuc[sifir_s] = lam[sifir_s]
    pozitif = (s > 0) & (lam > 0)
    alt = np.flatnonzero(pozitif & (s <= lam))
    ust = np.flatnonzero(pozitif & (s > lam))
    for deger in np.unique(s[alt]):
        idx = alt[s[alt] == deger]
        sonuc[idx] = _alt_bolge(lam[idx], int(deger))
    kuyruk = 0
    if len(ust):
        sonuc[ust], kuyruk = _ust_bolge(lam[ust], s[ust])
    sonuc = np.maximum(sonuc, 0.0)
    kayit.info("kuyruk satiri: P(D >= s) < %g olan %d satir (%d hesaplanan satirdan)",
               KUYRUK_ESIGI, kuyruk, len(lam))
    return sonuc, kuyruk


def poisson_kosullu_fazla(lam: np.ndarray, s: np.ndarray) -> np.ndarray:
    """E[D | D >= s] - s, D ~ Poisson(lam); lam = 0 için 0, s = 0 için lam."""
    return poisson_kosullu_fazla_say(lam, s)[0]


def _hizala(tahmin: pd.Series, indeks: pd.Index) -> np.ndarray:
    """Tahmini `indeks`e hizalar (indeksler aynıysa kopyalamaz); eksik satır hata."""
    if not tahmin.index.equals(indeks):
        if not (indeks.is_unique and tahmin.index.is_unique):
            raise ValueError("tahmin indeksi gunluk ile hizalanamadi (indeks tekil degil)")
        tahmin = tahmin.reindex(indeks)
        if tahmin.isna().any():
            raise ValueError("tahmin indeksi gunluk ile hizalanamadi (eksik satir)")
    return tahmin.to_numpy(dtype=np.float64)


def kayip_yaz(gunluk: pd.DataFrame, tahmin: pd.Series) -> pd.DataFrame:
    """Günlük tabloya `tahmini_talep`, `satis`, `kayip`, `kayip_saf` ekler.

    `tahmin`, `gunluk`un indeksine göre hizalanır (λ̂ >= 0, sonlu). `satis` =
    `brut_satis`. Yeni çerçeve girdi sütunlarını paylaşır (kopyalamaz).
    `attrs["kuyruk_satir"]`: P(D >= s) < 1e-12 olan satır sayısı."""
    lam = _hizala(tahmin, gunluk.index)
    if not np.isfinite(lam).all():
        raise ValueError("tahmin sonlu olmali")
    if (lam < 0).any():
        raise ValueError("tahmin negatif olamaz")

    durum = gunluk["durum"]
    bos = (durum == "bos").to_numpy()
    tukenen = (durum == "tukenen").to_numpy()
    s = gunluk["satis_oncesi"].to_numpy()

    kayip = np.zeros(len(gunluk))
    saf = np.zeros(len(gunluk))
    kayip[bos] = saf[bos] = lam[bos]
    idx = np.flatnonzero(tukenen)
    kayip[idx], kuyruk = poisson_kosullu_fazla_say(lam[idx], s[idx])
    saf[idx] = np.maximum(0.0, lam[idx] - s[idx])

    cikti = gunluk.copy(deep=False)
    cikti["tahmini_talep"] = lam
    cikti["satis"] = gunluk["brut_satis"].to_numpy()
    cikti["kayip"] = kayip
    cikti["kayip_saf"] = saf
    cikti.attrs["kuyruk_satir"] = kuyruk
    return cikti


def _fiyatlar(con: duckdb.DuckDBPyConnection, urun_id: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Satır başına (liste_fiyati, alis_fiyati), `urun` tablosundan float64."""
    fiyat = con.execute("select urun_id::varchar as urun_id, liste_fiyati::double as liste, "
                        "alis_fiyati::double as alis from urun").fetchdf().set_index("urun_id")
    kat = urun_id if isinstance(urun_id.dtype, pd.CategoricalDtype) else urun_id.astype("category")
    f = fiyat.reindex(kat.cat.categories.astype(str))
    kod = kat.cat.codes.to_numpy()
    if (kod < 0).any() or f.to_numpy()[np.unique(kod)].size and             np.isnan(f.to_numpy()[np.unique(kod)]).any():
        raise ValueError("urun tablosunda fiyati olmayan urun_id var")
    return f["liste"].to_numpy()[kod], f["alis"].to_numpy()[kod]


def ozet(kayip_df: pd.DataFrame, duzey: list[str], con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """`duzey` sütunlarına göre kayıp adedi, TL ve brüt marj toplamı (duzey sırasıyla sıralı).

    `duzey` sütunları `kayip_df`te olabilir ya da türetilir: `yil`, `hafta`
    (haftanın pazartesisi) `tarih`ten; `ozellikler.OZELLIKLER`'den biri
    (`kanal`, `ust_kategori`, `line`, ...) `ozellikler.ekle` ile. Boş `duzey`
    zincir toplamıdır (tek satır). `oran` yoksa `ozellikler.ekle` ile eklenir.
    Fiyatlar `urun` tablosundan float64 okunur; `oran` float32 gürültüsünden
    arındırılmak için 7 ondalığa yuvarlanır."""
    duzey = list(duzey)
    turetilen = {"yil", "hafta"}
    eksik = [c for c in duzey if c not in kayip_df.columns and c not in turetilen]
    bilinmeyen = [c for c in eksik if c not in ozellikler.OZELLIKLER]
    if bilinmeyen:
        raise ValueError(f"bilinmeyen duzey sutunu: {bilinmeyen}")
    istenen = ([] if "oran" in kayip_df.columns else ["oran"]) + [c for c in eksik if c != "oran"]
    df = ozellikler.ekle(con, kayip_df, istenen) if istenen else kayip_df

    liste, alis = _fiyatlar(con, df["urun_id"])
    oran = np.round(df["oran"].to_numpy(dtype=np.float64), 7)
    etiket = liste * (1.0 - oran)
    adet = df["kayip"].to_numpy(dtype=np.float64)
    deger = pd.DataFrame({"kayip_adet": adet, "kayip_tl": adet * etiket,
                          "kayip_marj": adet * (etiket - alis)}, index=df.index)

    anahtar = {}
    for c in duzey:
        if c == "yil" and c not in df.columns:
            anahtar[c] = df["tarih"].dt.year.astype("int32")
        elif c == "hafta" and c not in df.columns:
            anahtar[c] = (df["tarih"] - pd.to_timedelta(df["tarih"].dt.dayofweek, unit="D")
                          ).dt.normalize()
        else:
            anahtar[c] = df[c]
    if not duzey:
        return deger.sum().to_frame().T
    deger = pd.concat([pd.DataFrame(anahtar, index=df.index), deger], axis=1)
    return deger.groupby(duzey, observed=True, sort=True).sum().reset_index()
