"""RPT geldiğinde depodan mağazalara dağıtım kuralları.

Dört kural, v3 motorunun `dagitim_politikasi` arayüzünde (hücre başına istek):

    mevcut   bugünkü replenishment (v3 varsayılanı): 28 günlük plan hedefi +
             ölü stok kapısı. Stoksuz kalan hücre satamaz, satamayınca son 28
             günlük hızı sıfır görünür, hızı sıfır olan hücreye mal gitmez.
    b        stoklu gün hızı: hücrenin son (en fazla) 28 STOKLU gününün satışı,
             yaşam eğrisiyle bugüne taşınır (seviye a_c = satış ÷ Σ eğri
             ağırlığı, hedef = a_c × önümüzdeki 28 günün eğri ağırlığı). Hiç
             stoklu günü olmayan hücre bugünkü kurala düşer; stokluyken
             satmamış hücre (gerçekten ölü) mal almaz.
    c        yeniden lansman: RPT'nin geldiği ilk pazartesi, gelen adet ilk
             dağıtım gibi dağıtılır — SKU'nun mağaza payı, option'ın ilk üç
             haftasının stoklu gün düzeltmeli talebinden. "Paya kadar doldur":
             mağazadaki stok + gelen, paylara göre bölünür, istek = pay −
             stok. Sonraki pazartesiler (b).
    d        (c) + depoda tutma: gelenin %30'u depoda kalır, ertesi pazartesi
             (b) ile çıkar.

ATFEDİLEBİLİRLİK. Kurallar yalnız oyun sezonlarının RPT'si GELMİŞ Collection
option'larına uygulanır; öteki bütün hücreler bugünkü kuralla dağıtılır.
RPT'siz bir kolda (b), (c), (d) bugünkü kuralla birebir aynı sonucu verir
(`test_kural_rptsiz_kolda_etkisiz`). Fark yalnız RPT'nin dağıtımından gelir.

Hücrenin RPT geldiğini politika, sipariş verildiği pazartesi `acik_siparisler`de
gördüğü kopyadan ve teslim gününün geçmesinden anlar (depo girişinin kendisi).
"""

import numpy as np
from perakende_veri.v3.politika import mevcut_dagitim
from perakende_veri.v3.tedarik import en_buyuk_kalan

from .anlik import Indeks, duzeltilmis

KURALLAR = ("mevcut", "b", "c", "d")
PENCERE_STOKLU_GUN = 28
HEDEF_GUN = 28
LANSMAN_HAFTA = 3
TUTMA_PAYI = 0.30


def gunluk_agirlik(egri_cx, dalga: int, gun_sayisi: int) -> np.ndarray:
    """Lansmandan itibaren gün başına göreli talep ağırlığı (çıkış eğrisi:
    indirimin talep artışı dahil). Eğrinin bittiği yerde 0."""
    pay = egri_cx._satir((dalga,))
    b = np.zeros(gun_sayisi)
    n = min(gun_sayisi, 7 * len(pay))
    b[:n] = np.repeat(pay / 7.0, 7)[:n]
    return b


def hiz_hedefi(S: np.ndarray, F: np.ndarray, beta_gecmis: np.ndarray, beta_ileri: float,
               pencere: int = PENCERE_STOKLU_GUN):
    """(b) kuralının çekirdeği, saf fonksiyon.

    S, F         [gün, hücre] satış ve stoklu bayrağı (lansmandan bugüne)
    beta_gecmis  [gün] eğri ağırlığı; beta_ileri önümüzdeki hedef ufkunun
                 ağırlık toplamı
    Döner: (hedef adet [hücre], bilgi var mı [hücre]).
    """
    if S.shape[0] == 0:
        return np.zeros(S.shape[1]), np.zeros(S.shape[1], dtype=bool)
    Fi = F.astype(np.int64)
    geri = np.cumsum(Fi[::-1], axis=0)[::-1]
    maske = (Fi == 1) & (geri <= pencere)
    s = (S * maske).sum(axis=0)
    agirlik = (maske * beta_gecmis[:, None]).sum(axis=0)
    var = maske.any(axis=0) & (agirlik > 0)
    seviye = np.divide(s, agirlik, out=np.zeros(S.shape[1]), where=var)
    return seviye * beta_ileri, var


class RPTDagitim:
    """`dagitim_politikasi`: bugünkü kural + RPT'si gelmiş option'lara kural."""

    def __init__(self, dunya, egriler_cx: dict, kural: str = "b", oyun_sezonlari=("AW24", "SS25"),
                 tutma: float | None = None, idx: Indeks | None = None):
        if kural not in KURALLAR:
            raise ValueError(kural)
        self.kural = kural
        self.tutma = (TUTMA_PAYI if kural == "d" else 0.0) if tutma is None else tutma
        self.idx = idx or Indeks.kur(dunya)
        opt = dunya.optionlar
        self.oyun = set(np.flatnonzero(
            (opt["line"] == "Collection").to_numpy() & opt["sezon_kodu"].isin(oyun_sezonlari).to_numpy()))
        self.lansman = opt["lansman_gun"].to_numpy()
        self.cikis = opt["cikis_gun"].to_numpy()
        self.beta = {}
        for o in self.oyun:
            e = egriler_cx[opt.at[o, "sezon_kodu"]]
            self.beta[o] = gunluk_agirlik(e, int(opt.at[o, "dalga"]),
                                          int(self.cikis[o] - self.lansman[o]) + HEDEF_GUN)
        self.bekleyen = {}       # (option, sipariş günü, sıra) → sipariş kopyası
        self.gelen = set()       # RPT'si gelmiş option'lar
        self.gunluk = []         # (gün, option, olay) — rapor için

    def _b(self, g, o, istek):
        c = self.idx.hucre[o]
        lan = int(self.lansman[o])
        S = g.satis_gecmisi[lan:g.gun, c].astype(float)
        F = g.stoklu_gecmisi[lan:g.gun, c]
        b = self.beta[o]
        n = g.gun - lan
        hedef, var = hiz_hedefi(S, F, b[:n], b[n:n + HEDEF_GUN].sum())
        yeni = np.maximum(np.rint(hedef).astype(np.int64) - g.magaza_stok[c], 0)
        istek[c] = np.where(var, yeni, istek[c])

    def _lansman(self, g, o, siparis, istek):
        w = g.dunya
        c = self.idx.hucre[o]
        lan = int(self.lansman[o])
        _, _, hiz = duzeltilmis(g, o, self.idx, lan, min(lan + 7 * LANSMAN_HAFTA, g.gun))
        pay = np.where(hiz > 0, hiz, 0.0)
        sku_c = w.hucre_sku[c]
        for s, adet in zip(siparis["skular"], siparis["adetler"]):
            gelen = int(round(adet * (1 - self.tutma)))
            m = sku_c == s
            if not m.any() or gelen <= 0:
                continue
            p = pay[m] if pay[m].sum() > 0 else self.idx.agirlik[c][m]
            stok = g.magaza_stok[c][m]
            hedef = en_buyuk_kalan(int(stok.sum()) + gelen, p)
            istek[c[m]] = np.maximum(hedef - stok, 0)

    def __call__(self, g):
        istek = np.asarray(mevcut_dagitim(g), dtype=np.int64).copy()
        if self.kural == "mevcut":
            return istek
        for s in g.acik_siparisler:
            if s["tip"] == "rpt" and s["option"] in self.oyun:
                self.bekleyen[(s["option"], s["siparis_gun"], s["planlanan_gun"])] = s
        yeni_gelen = []
        for k, s in list(self.bekleyen.items()):
            if s["gerceklesen_gun"] <= g.gun:
                del self.bekleyen[k]
                self.gelen.add(s["option"])
                yeni_gelen.append(s)
        for o in self.gelen:
            if g.gun < self.cikis[o]:
                self._b(g, o, istek)
        if self.kural in ("c", "d"):
            for s in yeni_gelen:
                if g.gun < self.cikis[s["option"]]:
                    self._lansman(g, s["option"], s, istek)
                    self.gunluk.append((g.gun, s["option"], "lansman"))
        return istek
