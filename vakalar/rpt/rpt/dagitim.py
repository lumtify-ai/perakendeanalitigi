"""RPT geldiğinde depodan mağazalara dağıtım kuralları (v4 replenishment kancası).

Dört kural (`KURALLAR`), hepsi v4 motorunun `replenishment(g) -> [C] istek`
kancası; her koşuya yeni bir nesne kurulur (`KURALLAR[k](temel, egriler_cx)`):

    a   mevcut       Lumoda'nın bugünkü replenishment'ı (`temel`, v4
                     `lumoda_replenishment`): 28 günlük plan hedefi + ölü stok
                     kapısı. Stoksuz kalan hücre satamaz, satamayınca son 28
                     günlük hızı sıfır görünür, hızı sıfır olan hücreye mal gitmez.
    b   stoklu gün hızı: hücrenin son (en fazla) 28 STOKLU gününün satışı,
                     yaşam eğrisiyle bugüne taşınır (seviye a_c = satış ÷ Σ eğri
                     ağırlığı, hedef = a_c × önümüzdeki 28 günün eğri ağırlığı);
                     istek = hedef − mağaza stoğu − yolda. Hiç stoklu günü olmayan
                     hücre bugünkü kurala düşer; stokluyken satmamış hücre
                     (gerçekten ölü) mal almaz.
    c   yeniden lansman: RPT'nin geldiği görülen ilk pazartesi, gelen adet ilk
                     dağıtım gibi dağıtılır — SKU'nun mağaza payı, option'ın ilk üç
                     haftasının stoklu gün düzeltmeli hızından (stoksuz hücreye
                     planın payıyla). "Paya kadar doldur": mağazadaki stok + yolda +
                     gelen paylara bölünür, istek = pay − stok − yolda. Sonraki
                     pazartesiler (b).
    d   (c) + depoda tutma: gelenin %30'u depoda kalır, ertesi pazartesi (b) ile
                     çıkar.

ATFEDİLEBİLİRLİK. Kurallar yalnız oyun sezonlarının RPT'si GELMİŞ Collection
option'larına uygulanır; öteki bütün hücreler bugünkü kuralla dağıtılır. RPT'siz bir
kolda (b), (c), (d) bugünkü kuralla birebir aynı sonucu verir
(`test_rpt_yokken_kurallar_etkisiz`). Fark yalnız RPT'nin dağıtımından gelir.

RPT'NİN VARIŞI. v4 görünümü gerçekleşen teslim gününü taşımaz. Kural her pazartesi
açık RPT siparişlerini (`acik_siparisler`, tip `rpt`) izler: listeden düşen sipariş
teslim edilmiştir (mal o gün depoya girmiştir). Gelen adet SKU başına
min(sipariş adedi, depodaki stok): kalite kontrolde reddedilen adet depoya girmez,
teslimden sonraki online satış depodan düşer.

SIZINTI. Yalnız `Gorunum` ve dünyanın kamuya açık alanları (çeşit yapısı, plan,
option alanları) okunur; üreteci içe aktarmaz: Lumoda'nın kuralı argümandır
(`rpt.motor.lumoda("replenishment")`).
"""

import functools

import numpy as np
import pandas as pd

from . import anlik
from .politika import ozet_hash

OYUN_SEZONLARI = ("AW24", "SS25")
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


def en_buyuk_kalan(toplam: int, paylar: np.ndarray) -> np.ndarray:
    """`toplam` adedi paylara göre tam sayılara böler (en büyük kalan; eşitlikte
    önce gelen indis; v4 `plan.en_buyuk_kalan`'ın kopyası, testle kilitli)."""
    paylar = np.asarray(paylar, dtype=float)
    if toplam <= 0 or paylar.sum() <= 0:
        return np.zeros(len(paylar), dtype=np.int64)
    hedef = toplam * paylar / paylar.sum()
    tam = np.floor(hedef).astype(np.int64)
    kalan = int(toplam - tam.sum())
    if kalan > 0:
        sira = np.lexsort((np.arange(len(paylar)), -(hedef - tam)))
        tam[sira[:kalan]] += 1
    return tam


class RPTDagitim:
    """v4 `replenishment` kancası: `temel` (Lumoda) + RPT'si gelmiş oyun option'larına
    kuralın kendisi. `egriler_cx`: sezon → çıkış eğrisi (`Egri`, hedef "cikis")."""

    def __init__(self, temel, egriler_cx: dict, kural: str = "b", oyun_sezonlari=OYUN_SEZONLARI,
                 tutma: float | None = None):
        if kural not in KURAL_ADLARI:
            raise ValueError(f"kural {KURAL_ADLARI}'den biri olmalı: {kural!r}")
        self.temel = temel
        self.egriler_cx = dict(egriler_cx)
        self.kural = kural
        self.oyun_sezonlari = tuple(oyun_sezonlari)
        self.tutma = (TUTMA_PAYI if kural == "d" else 0.0) if tutma is None else float(tutma)
        self.bekleyen: dict = {}      # (option, sipariş günü) → açık RPT siparişinin kopyası
        self.gelen: set = set()       # RPT'si gelmiş option'lar
        self.olaylar: list = []       # (gün, option, olay, adet)
        self._w = None

    def parametreler(self) -> dict:
        """Koşu önbelleği anahtarına girecek tanım (`motor.kos(parametreler=…)`)."""
        return {"kural": self.kural, "tutma": self.tutma, "oyun_sezonlari": list(self.oyun_sezonlari),
                "egriler_cx": ozet_hash(self.egriler_cx)}

    def _hazirla(self, w) -> None:
        if self._w is w:
            return
        self._w = w
        opt = w.optionlar
        self.idx = anlik.Indeks.kur(w)
        oyun = ((opt["line"] == "Collection").to_numpy()
                & opt["sezon_kodu"].isin(self.oyun_sezonlari).to_numpy())
        self.oyun = set(int(o) for o in np.flatnonzero(oyun))
        self.lansman = opt["lansman_gun"].to_numpy()
        self.cikis = opt["cikis_gun"].to_numpy()
        dagitilir = ~np.asarray(w.hucre_online) & ~np.asarray(w.hucre_outlet_akisi)
        self.hucre = {o: self.idx.hucre[o][dagitilir[self.idx.hucre[o]]] for o in self.oyun}
        self.beta = {}
        for o in self.oyun:
            e = self.egriler_cx[opt.at[o, "sezon_kodu"]]
            self.beta[o] = gunluk_agirlik(e, int(opt.at[o, "dalga"]),
                                          int(self.cikis[o] - self.lansman[o]) + HEDEF_GUN)

    def _b(self, g, o: int, istek: np.ndarray) -> None:
        c = self.hucre[o]
        lan = int(self.lansman[o])
        if g.gun <= lan or not len(c):
            return
        S = np.asarray(g.satis_gecmisi)[lan:g.gun, c].astype(float)
        F = np.asarray(g.stoklu_gecmisi)[lan:g.gun, c]
        b = self.beta[o]
        n = g.gun - lan
        hedef, var = hiz_hedefi(S, F, b[:n], b[n:n + HEDEF_GUN].sum())
        elde = np.asarray(g.magaza_stok)[c] + np.asarray(g.yolda)[c]
        yeni = np.maximum(np.rint(hedef).astype(np.int64) - elde, 0)
        istek[c] = np.where(var, yeni, istek[c])

    def _lansman(self, g, o: int, siparis: dict, istek: np.ndarray) -> int:
        """Gelen adedi ilk dağıtım gibi böler; dağıtılan toplam isteği döndürür."""
        w = g.dunya
        c = self.hucre[o]
        lan = int(self.lansman[o])
        plan = np.asarray(w.ileri_plan(lan, 7 * LANSMAN_HAFTA))[c] + 1e-9
        _, _, hiz = anlik.duzeltilmis(g, c, plan, lan, min(lan + 7 * LANSMAN_HAFTA, g.gun))
        pay = np.where(hiz > 0, hiz, 0.0)
        sku_c = np.asarray(w.hucre_sku)[c]
        stok = np.asarray(g.magaza_stok)[c] + np.asarray(g.yolda)[c]
        depo = np.asarray(g.depo)
        toplam = 0
        for s, adet in zip(np.asarray(siparis["skular"]), np.asarray(siparis["adetler"])):
            gelen = int(round(min(int(adet), int(depo[s])) * (1 - self.tutma)))
            m = sku_c == s
            if not m.any() or gelen <= 0:
                continue
            p = pay[m] if pay[m].sum() > 0 else plan[m]
            hedef = en_buyuk_kalan(int(stok[m].sum()) + gelen, p)
            yeni = np.maximum(hedef - stok[m], 0)
            istek[c[m]] = yeni
            toplam += int(yeni.sum())
        return toplam

    def __call__(self, g) -> np.ndarray:
        istek = np.asarray(self.temel(g), dtype=np.int64).copy()
        if self.kural == "a":
            return istek
        self._hazirla(g.dunya)
        acik = {(int(s["option"]), int(s["siparis_gun"])): s for s in g.acik_siparisler
                if s["tip"] == "rpt" and int(s["option"]) in self.oyun}
        yeni_gelen = [s for k, s in self.bekleyen.items() if k not in acik]
        self.bekleyen = acik
        for s in yeni_gelen:
            self.gelen.add(int(s["option"]))
            self.olaylar.append((g.gun, int(s["option"]), "varis", int(np.sum(s["adetler"]))))
        for o in sorted(self.gelen):
            if g.gun < self.cikis[o]:
                self._b(g, o, istek)
        if self.kural in ("c", "d"):
            for s in yeni_gelen:
                o = int(s["option"])
                if g.gun < self.cikis[o]:
                    n = self._lansman(g, o, s, istek)
                    self.olaylar.append((g.gun, o, "lansman", n))
        return istek

    def kayit_tablosu(self) -> pd.DataFrame:
        """Olaylar (motor koşu kaydına alır): gün, option, olay (varis / lansman), adet."""
        return pd.DataFrame(self.olaylar, columns=["gun", "option", "olay", "adet"])


KURAL_ADLARI = ("a", "b", "c", "d")
KURALLAR = {k: functools.partial(RPTDagitim, kural=k) for k in KURAL_ADLARI}
