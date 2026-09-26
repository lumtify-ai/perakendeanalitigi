"""Karar anının hesapları — v3 motorunun `Gorunum`u üstünde.

Faz A'nın tablo tabanlı `sansur.duzeltilmis_talep`'inin motor içi eşidir:
politika bir pazartesi sabahı yalnız görünümü okur (bugüne kadarki satış
ve stoklu gün matrisleri, anlık mağaza ve depo stoğu, açık siparişler).
Aynı fonksiyonlar hem politikada (oneri, dağıtım) hem de öğrenme satırı
kaydında (`Kaydedici`) kullanılır; eğitim ile karar aynı kodu görür.
`test_anlik.py`, gerçek veride tablo tabanlı kestirimle eşitliği sınar.

Görünüm gelecekteki teslim gününü (`acik_siparisler[..]["gerceklesen_gun"]`)
de taşır. Kâhin dışında hiçbir politika onu okumaz: miktar kararı
planlanan günü, dağıtım yalnız gelmiş siparişi kullanır.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Indeks:
    """Dünyanın option → hücre / SKU dizinleri (bir kez hesaplanır)."""

    hucre: list          # option → hücre indisleri (cesit sırası)
    sku: list            # option → SKU indisleri
    agirlik: np.ndarray  # [C] ilk dağıtım + 1 (stoksuz hücre ataması)

    @classmethod
    def kur(cls, dunya) -> "Indeks":
        O = len(dunya.optionlar)
        sira = np.argsort(dunya.hucre_option, kind="stable")
        sinir = np.searchsorted(dunya.hucre_option[sira], np.arange(O + 1))
        hucre = [sira[sinir[o]:sinir[o + 1]] for o in range(O)]
        sira_s = np.argsort(dunya.sku_option, kind="stable")
        sinir_s = np.searchsorted(dunya.sku_option[sira_s], np.arange(O + 1))
        sku = [sira_s[sinir_s[o]:sinir_s[o + 1]] for o in range(O)]
        return cls(hucre=hucre, sku=sku, agirlik=dunya.ilk_dagitim_hucre.astype(float) + 1.0)


def hucre_duzeltme(s: np.ndarray, st: np.ndarray, gun: np.ndarray, sku: np.ndarray,
                   agirlik: np.ndarray) -> np.ndarray:
    """Hücre başına günlük hız (stoklu gün düzeltmeli, stoksuza atamalı).

    s, st   hücrenin penceredeki satışı ve stoklu günü
    gun     (kullanılmaz; imza tablo sürümüyle aynı kalsın diye yok sayılır)
    Stoksuz hücre: aynı SKU'nun stoklu hücrelerinin birleşik hızı ×
    ağırlık / o hücrelerin ortalama ağırlığı; SKU'da stoklu hücre yoksa
    option düzeyinde aynısı (sansur.duzeltilmis_talep ile birebir).
    """
    s = s.astype(float)
    st = st.astype(float)
    stoklu = st > 0
    hiz = np.full(len(s), np.nan)
    hiz[stoklu] = s[stoklu] / st[stoklu]
    if (~stoklu).any():
        if stoklu.any():
            sk_u, ters = np.unique(sku, return_inverse=True)
            n = len(sk_u)
            ss = np.bincount(ters, np.where(stoklu, s, 0.0), n)
            sst = np.bincount(ters, np.where(stoklu, st, 0.0), n)
            sw = np.bincount(ters, np.where(stoklu, agirlik, 0.0), n)
            sn = np.bincount(ters, stoklu.astype(float), n)
            r_sku = np.divide(ss, sst, out=np.full(n, np.nan), where=sst > 0)
            wbar = np.divide(sw, sn, out=np.full(n, np.nan), where=sn > 0)
            atanan = r_sku[ters] * agirlik / wbar[ters]
            r_opt = s[stoklu].sum() / st[stoklu].sum()
            atanan_o = r_opt * agirlik / agirlik[stoklu].mean()
            atanan = np.where(np.isnan(atanan), atanan_o, atanan)
            hiz[~stoklu] = atanan[~stoklu]
        else:
            hiz[~stoklu] = 0.0
    return hiz


def duzeltilmis(g, o: int, idx: Indeks, bas: int | None = None, son: int | None = None):
    """Option o için [bas, son) penceresinde (varsayılan: lansman → bugün)
    çıplak satış x, düzeltilmiş talep D ve hücre hızları."""
    w = g.dunya
    bas = int(w.optionlar.at[o, "lansman_gun"]) if bas is None else bas
    son = g.gun if son is None else son
    c = idx.hucre[o]
    if son <= bas:
        return 0.0, 0.0, np.zeros(len(c))
    S = g.satis_gecmisi[bas:son, c]
    F = g.stoklu_gecmisi[bas:son, c]
    s, st = S.sum(axis=0), F.sum(axis=0)
    hiz = hucre_duzeltme(s, st, None, w.hucre_sku[c], idx.agirlik[c])
    return float(s.sum()), float((hiz * (son - bas)).sum()), hiz


OZET_KOLONLARI = ("option", "gun", "h", "x", "D", "str", "depo", "magaza", "acik",
                  "stoklu_magaza_payi", "kirik_magaza_payi", "rpt_sayisi")


def ozet(g, o: int, idx: Indeks) -> dict:
    """Option o'nun bu sabahki ham durumu (eğriden bağımsız)."""
    w = g.dunya
    lan = int(w.optionlar.at[o, "lansman_gun"])
    x, D, _ = duzeltilmis(g, o, idx)
    c = idx.hucre[o]
    stok = g.magaza_stok[c]
    mg = w.hucre_magaza[c]
    mu, ters = np.unique(mg, return_inverse=True)
    dolu = np.bincount(ters, stok > 0, len(mu)) > 0
    bos_beden = np.bincount(ters, stok == 0, len(mu)) > 0
    acik = sum(int(np.sum(s["adetler"])) for s in g.acik_siparisler if s["option"] == o)
    gonderilen = g.gonderilen_option[o]
    return {
        "option": o, "gun": g.gun, "h": (g.gun - lan) / 7.0, "x": x, "D": D,
        "str": g.satilan_option[o] / gonderilen if gonderilen > 0 else 0.0,
        "depo": int(g.depo[idx.sku[o]].sum()), "magaza": int(stok.sum()), "acik": acik,
        "stoklu_magaza_payi": float(dolu.mean()) if len(mu) else 0.0,
        "kirik_magaza_payi": float((dolu & bos_beden).mean()) if len(mu) else 0.0,
        "rpt_sayisi": int(g.rpt_sayisi[o]),
    }


class Kaydedici:
    """RPT politikasını sarar; her pazartesi pencere içindeki Collection
    option'larının `ozet`ini kaydeder (aday modeli ve kalibrasyon satırları).

    Kararı değiştirmez: sarılan politikanın dönüşünü aynen döndürür.
    """

    def __init__(self, temel, dunya, idx: Indeks | None = None, haftalar=(2, 3, 4, 5, 6)):
        self.temel = temel
        self.idx = idx or Indeks.kur(dunya)
        opt = dunya.optionlar
        self.lansman = opt["lansman_gun"].to_numpy()
        self.aday = np.flatnonzero((opt["line"] == "Collection").to_numpy())
        self.haftalar = set(haftalar)
        self.satirlar = []

    def __call__(self, g):
        h_gun = g.gun - self.lansman[self.aday]
        for o, hg in zip(self.aday, h_gun):
            if hg >= 0 and hg % 7 == 0 and hg // 7 in self.haftalar:
                self.satirlar.append(ozet(g, int(o), self.idx))
        return self.temel(g) if self.temel is not None else {}

    def tablo(self) -> pd.DataFrame:
        return pd.DataFrame(self.satirlar, columns=list(OZET_KOLONLARI))
