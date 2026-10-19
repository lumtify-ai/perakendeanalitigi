"""Benzer ürün endeksi (kural tabanlı): yeni bir option'ın mağaza payı, ona benzeyen geçmiş
option'ların o mağazadaki göreli hızından.

Kural: bu modül gizli gerçeğe (`perakende_veri`), motora (`allocation.motor`) ve hakeme
dokunmaz; girdisi `ogrenme.ogrenme_tablosu`dur.

**Benzerlik** açık öznitelik hiyerarşisiyle (`HIYERARSI`, en özelden en genele; son düzey
`()` mağazanın bütün geçmiş Collection'ı). Yeni option için düzey, yeni option'la o düzeyin
bütün sütunlarında eşleşen en az `en_az` geçmiş option'ı olan ilk düzeydir; hiçbirinde
yoksa son düzey.

**Göreli hız.** Her geçmiş option `o'` için mağazanın göreli hızı

    göreli(m, o') = talep(m, o') / ortalama_{m' ∈ aday(o')} talep(m', o')

`aday(o')` = o option'da gözlemi olan mağazalar (`stoklu_gun > 0`; talep sansür düzeltmeli).
Ölçeği ve aday kümesi farklı option'lar böylece aynı birimde birleşir. Gözlemli mağazalarında
hiç satmamış option (ortalama 0) bilgi taşımaz, öğrenilmez.

**Endeks.** Mağazanın endeksi, seçilen düzeydeki benzer option'larda göreli hızının
ortalamasıdır. O düzeyde gözlemi olmayan aday mağaza bir üst (daha genel) düzeyin değerini
alır; hiçbir düzeyde gözlemi olmayan (ör. sonradan açılan) aday mağaza ortalama mağazadır
(endeks 1). Aday olmayan mağazada 0.

**Mutlak öngörü** (kapsama tavanı için): mağazanın endeksini veren benzer option'lardaki
ortalama erken talebi × (yeni option'ın ilk alımı ÷ aynı option'ların ortalama ilk alımı).
Geçmişi olmayan aday mağazada gözlemli adayların ortalaması; hiçbir adayın geçmişi yoksa NaN
(öngörü yok: tavan bağlanamaz). Aday olmayanda 0.

**Mevsim.** `ogren(..., mevsim="SS")` öğrenme tablosunu yalnız SS sezonlarına daraltır (spec
§3.3: SS option'ları SS23 + SS24 Collection'ından öğrenir). Öğrenme tablosu AW sezonlarını da
taşır (LightGBM onları özellik olarak kullanır); `benzer` kolu mevsimi açıkça seçer.

**Kimlik.** `Endeks.kimlik` öğrenilenlerin içerik özetidir (SHA-256; satır sırasından ve
nesne kimliğinden bağımsız); politika kimliği üstünden koşu önbelleği anahtarına girer.
`sabitle()` özeti bir kez hesaplayıp saklayan kopya verir.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

HIYERARSI = (("alt_kategori", "fiyat_segmenti", "kalip"), ("alt_kategori", "fiyat_segmenti"),
             ("alt_kategori",), ("ust_kategori",), ())
# hiyerarşinin kullandığı öznitelik sütunları (ilk görünme sırasıyla)
SUTUNLAR = tuple(dict.fromkeys(s for duzey in HIYERARSI for s in duzey))
MEVSIMLER = ("SS", "AW")


def _salt(a: np.ndarray, dtype) -> np.ndarray:
    a = np.array(a, dtype=dtype, copy=True)
    a.flags.writeable = False
    return a


@dataclass(frozen=True, eq=False)
class Endeks:
    """Öğrenilen benzer ürün bilgisi (salt okunur). K geçmiş option, M mağaza.

    en_az      düzey eşiği (en az bu kadar benzer geçmiş option)
    option     [K] geçmiş option indisi (artan)
    oznitelik  sütun (`SUTUNLAR`) -> [K] str
    ilk_alim   [K] geçmiş option'ın ilk alımı
    talep      [K, M] sansür düzeltmeli erken talep; NaN = gözlem yok
    goreli     [K, M] göreli hız (talep ÷ option'ın gözlemli mağaza ortalaması); NaN = yok

    `eq=False`: eşitlik nesne kimliğinden; içerik eşitliği `kimlik` ile."""

    en_az: int
    option: np.ndarray
    oznitelik: Mapping[str, np.ndarray]
    ilk_alim: np.ndarray
    talep: np.ndarray
    goreli: np.ndarray
    _kimlik: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        K = len(self.option)
        object.__setattr__(self, "en_az", int(self.en_az))
        object.__setattr__(self, "option", _salt(self.option, np.int64))
        object.__setattr__(self, "oznitelik", {s: _salt(np.asarray(self.oznitelik[s]).astype(str), str)
                                               for s in SUTUNLAR})
        object.__setattr__(self, "ilk_alim", _salt(self.ilk_alim, np.float64))
        object.__setattr__(self, "talep", _salt(self.talep, np.float64))
        object.__setattr__(self, "goreli", _salt(self.goreli, np.float64))
        if self.talep.shape != self.goreli.shape or self.talep.shape[0] != K or self.ilk_alim.shape != (K,):
            raise ValueError("Endeks: dizi boyutları tutarsız")
        if any(len(v) != K for v in self.oznitelik.values()):
            raise ValueError("Endeks: öznitelik uzunluğu K değil")

    def __reduce__(self):
        return (_endeks_geri, (self.en_az, self.option, dict(self.oznitelik), self.ilk_alim, self.talep,
                               self.goreli, self._kimlik))

    # --- kimlik --------------------------------------------------------------

    def _ozet(self) -> str:
        h = hashlib.sha256()
        h.update(json.dumps({"en_az": self.en_az, "hiyerarsi": HIYERARSI, "boyut": list(self.talep.shape),
                             "oznitelik": {s: self.oznitelik[s].tolist() for s in SUTUNLAR}},
                            ensure_ascii=False).encode("utf-8"))
        for ad, a, tur in (("option", self.option, "<i8"), ("ilk_alim", self.ilk_alim, "<f8"),
                           ("talep", self.talep, "<f8"), ("goreli", self.goreli, "<f8")):
            a = np.where(np.isnan(a), np.nan, a) if a.dtype.kind == "f" else a   # tek NaN biçimi
            h.update(b"\0" + ad.encode("ascii") + b"\0")
            h.update(np.ascontiguousarray(a, dtype=tur).tobytes())
        return h.hexdigest()

    @property
    def kimlik(self) -> str:
        """İçerik özeti (SHA-256 hex): sabitlenmişse saklanan, değilse hesaplanan."""
        return self._kimlik if self._kimlik is not None else self._ozet()

    def sabitle(self) -> "Endeks":
        """Kimliği bir kez hesaplayıp saklayan kopya (zaten sabitse kendisi)."""
        if self._kimlik is not None:
            return self
        e = Endeks(en_az=self.en_az, option=self.option, oznitelik=self.oznitelik,
                   ilk_alim=self.ilk_alim, talep=self.talep, goreli=self.goreli)
        object.__setattr__(e, "_kimlik", e._ozet())
        return e

    # --- sorgu ---------------------------------------------------------------

    def _hesap(self, oznitelik: Mapping, adaylar: np.ndarray):
        """(endeks [M], düzey, mutlak [M], değişim katsayısı [M]; NaN = tanımsız)."""
        adaylar = np.asarray(adaylar, dtype=bool)
        M = len(adaylar)
        K, Mt = self.talep.shape
        if M < Mt:
            raise ValueError(f"adaylar {M} mağaza; endeks {Mt} mağazadan öğrenildi")
        G = np.full((K, M), np.nan)
        T = np.full((K, M), np.nan)
        G[:, :Mt], T[:, :Mt] = self.goreli, self.talep

        eslesme = []
        for duzey in HIYERARSI:
            e = np.ones(K, dtype=bool)
            for s in duzey:
                e &= self.oznitelik[s] == str(oznitelik[s])
            eslesme.append(e)
        secilen = next((i for i, e in enumerate(eslesme) if e.sum() >= self.en_az), len(HIYERARSI) - 1)

        ilk_alim = float(oznitelik["ilk_alim"])
        endeks, mutlak = np.zeros(M), np.zeros(M)
        dk = np.full(M, np.nan)
        kalan = adaylar.copy()
        for e in eslesme[secilen:]:
            idx = np.flatnonzero(kalan)
            if idx.size == 0:
                break
            g = G[np.ix_(e, idx)]
            gozlem = ~np.isnan(g)
            n = gozlem.sum(axis=0)
            yeni = n > 0
            if not yeni.any():
                continue
            m, g, gozlem, n = idx[yeni], g[:, yeni], gozlem[:, yeni], n[yeni]
            ort = np.where(gozlem, g, 0.0).sum(axis=0) / n
            endeks[m] = ort
            t = np.where(gozlem, T[np.ix_(e, m)], 0.0).sum(axis=0) / n
            ia = (np.where(gozlem, self.ilk_alim[e][:, None], 0.0)).sum(axis=0) / n
            mutlak[m] = np.divide(t * ilk_alim, ia, out=np.full(len(m), np.nan), where=ia > 0)
            iki = (n >= 2) & (ort > 0)
            if iki.any():
                sapma = np.where(gozlem, g - ort, 0.0)[:, iki]
                std = np.sqrt((sapma ** 2).sum(axis=0) / (n[iki] - 1))
                dk[m[iki]] = std / ort[iki]
            kalan[m] = False
        gozlemli = adaylar & ~kalan
        endeks[kalan] = 1.0
        mutlak[kalan] = np.nanmean(mutlak[gozlemli]) if gozlemli.any() and np.isfinite(mutlak[gozlemli]).any() \
            else np.nan
        return endeks, secilen, mutlak, dk

    def endeks(self, oznitelik: Mapping, adaylar: np.ndarray) -> tuple[np.ndarray, int, np.ndarray]:
        """Yeni option için `(endeks [M], düzey, mutlak öngörü [M])` (modül notu).

        oznitelik  yeni option'ın `SUTUNLAR` değerleri ve `ilk_alim`ı (ör.
                   `ogrenme.option_oznitelikleri(w, [o]).iloc[0]`)
        adaylar    [M] bool; M öğrenilen mağaza sayısından küçük olamaz
        düzey      `HIYERARSI` indisi (seçilen düzey; tek tek mağazalar daha genel düzeye
                   düşmüş olabilir)"""
        endeks, duzey, mutlak, _ = self._hesap(oznitelik, adaylar)
        return endeks, duzey, mutlak


def _endeks_geri(en_az, option, oznitelik, ilk_alim, talep, goreli, kimlik) -> Endeks:
    """Pickle'dan `Endeks`: içerik yeniden donar; saklı kimlik içerikle tutmalı."""
    e = Endeks(en_az=en_az, option=option, oznitelik=oznitelik, ilk_alim=ilk_alim, talep=talep,
               goreli=goreli)
    if kimlik is None:
        return e
    s = e.sabitle()
    if s.kimlik != kimlik:
        raise ValueError("Endeks: saklı kimlik içerikle tutmuyor")
    return s


def ogren(tablo: pd.DataFrame, en_az: int, mevsim: str | None = None) -> Endeks:
    """Öğrenme tablosundan (`ogrenme.ogrenme_tablosu`) `Endeks`.

    Gözlem = `stoklu_gun > 0` ve talebi tanımlı satır. `mevsim` ("SS" / "AW") verilirse yalnız o
    mevsimin sezonları (`sezon_kodu` öneki). Mağaza ekseni tablonun en büyük mağaza indisine
    kadardır; sorguda aday dizisinin uzunluğuna genişler.

    Kayan noktalı her toplama (option ortalaması) satır sırasından bağımsızdır: tablo önce
    (option, mağaza) sırasına dizilir, ortalama `[K, M]` matrisin satırında mağaza sırasıyla
    alınır; böylece `kimlik` yalnız içeriğe bağlıdır. Bir (option, mağaza) çifti birden çok
    gözlem satırı taşıyamaz (`ValueError`)."""
    if int(en_az) < 1:
        raise ValueError(f"en_az >= 1 olmalı: {en_az}")
    if mevsim is not None and mevsim not in MEVSIMLER:
        raise ValueError(f"mevsim {MEVSIMLER}'den biri olmalı: {mevsim!r}")
    t = tablo[(tablo["stoklu_gun"] > 0).to_numpy() & tablo["talep"].notna().to_numpy()]
    if mevsim is not None:
        t = t[t["sezon_kodu"].astype(str).str.startswith(mevsim).to_numpy()]
    t = t.sort_values(["option", "magaza"], kind="stable", ignore_index=True)
    if t.duplicated(["option", "magaza"]).any():
        raise ValueError("ogren: aynı (option, mağaza) için birden çok gözlem satırı")
    tum = np.unique(t["option"].to_numpy().astype(np.int64))
    M = int(t["magaza"].max()) + 1 if len(t) else 0
    talep = np.full((len(tum), M), np.nan)
    talep[np.searchsorted(tum, t["option"].to_numpy()), t["magaza"].to_numpy()] = (
        t["talep"].to_numpy(dtype=np.float64))
    # satır başına en az bir gözlem var (tum gözlemli option'lardan); toplama mağaza sırasıyla
    ort = np.nansum(talep, axis=1) / (~np.isnan(talep)).sum(axis=1) if len(tum) else np.zeros(0)
    tut = ort > 0                       # hiç satmamış option bilgi taşımaz
    optionlar, talep, ort = tum[tut], talep[tut], ort[tut]
    goreli = talep / ort[:, None]
    ilk = t.drop_duplicates("option").set_index("option").reindex(optionlar)
    return Endeks(en_az=int(en_az), option=optionlar,
                  oznitelik={s: ilk[s].astype(str).to_numpy() for s in SUTUNLAR},
                  ilk_alim=ilk["ilk_alim"].to_numpy(dtype=np.float64), talep=talep, goreli=goreli)


def belirsizlik(endeks: Endeks, oznitelik: Mapping, adaylar: np.ndarray) -> float:
    """Benzer option'ların göreli hızlarının mağaza başına değişim katsayısının (std, ddof=1 ÷
    ortalama) mutlak öngörüyle ağırlıklı ortalaması; aday ölçü (Görev 7 seçer).

    Her aday mağaza, endeksini veren düzeyin option'larıyla; orada iki gözlemi olmayan mağaza
    ortalamaya girmez. Hiçbir mağazada tanımlı değilse NaN."""
    _, _, mutlak, dk = endeks._hesap(oznitelik, adaylar)
    w = np.where(np.isfinite(dk) & np.isfinite(mutlak), mutlak, 0.0)
    if not (w > 0).any():
        return float("nan")
    return float((w * np.where(w > 0, dk, 0.0)).sum() / w.sum())
