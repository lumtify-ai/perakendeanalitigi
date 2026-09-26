"""Kollar: v3 motoruna enjekte edilen RPT kararları.

Her kol bir `rpt_politikasi` (+ `dagitim.RPTDagitim`) çiftidir. Oyun
sezonlarının (AW24, SS25) Collection option'ları için kolun kuralı, öteki
bütün option'lar için Lumoda'nın bugünkü kuralı işler — geçmiş ve gelecek
sezonlar her kolda aynıdır.

    rpt_yok    oyun option'larına hiç RPT yok
    mevcut     Banu'nun kuralı (v3'ün kendisi)
    frr        Banu'nun tetiği (STR ≥ %55, yetişme) h. pazartesi; miktar FRR
    oneri      aday modeli (olasılık ≥ eşik) + newsvendor, h = 2…6, option
               başına en fazla bir RPT (ilk alarmda)
    kahin      gerçek talebi ve gerçek teslim gecikmesini bilir; option başına
               h = 2…6 arasından en kârlı haftayı ve miktarı seçer (aynı
               tedarik süresi ve MOQ). Stok akışı zincir düzeyinde; sıkışmayı
               bilmez — üst sınır değil, "bilgi tam olsaydı" kolu.

SIZINTI. Kâhin dışındaki kollar yalnız `Gorunum`u ve geçmiş sezonlardan
öğrenilmiş nesneleri (eğri, belirsizlik, aday modeli) kullanır.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from perakende_veri.v3.politika import LumodaRPT
from perakende_veri.v3.tedarik import moq_yuvarla

from . import anlik, miktar


@dataclass
class Baglam:
    """Bir talep yolu için kolların ortak girdileri (oyun.hazirlik kurar)."""

    dunya: object
    talep: np.ndarray
    idx: anlik.Indeks
    oyun_sezonlari: tuple
    egriler: dict            # sezon → {(yöntem, hedef): Egri}
    belirsizlik: dict        # sezon → miktar.Belirsizlik
    modeller: dict = field(default_factory=dict)   # sezon → aday.Modeller
    p_ind: np.ndarray | None = None
    esik: float = 0.5
    operasyon_tohumu: int = 42    # v3: iade / işlem indirimi (gün, hücre) başına, politikadan bağımsız

    def oyun_maskesi(self) -> np.ndarray:
        opt = self.dunya.optionlar
        return (opt["line"] == "Collection").to_numpy() & opt["sezon_kodu"].isin(self.oyun_sezonlari).to_numpy()


class KolRPT:
    """Oyun option'ları için `karar`, ötekiler için Lumoda."""

    def __init__(self, b: Baglam):
        self.b = b
        self.oyun = b.oyun_maskesi()
        self.lumoda = LumodaRPT()
        opt = b.dunya.optionlar
        self.lansman = opt["lansman_gun"].to_numpy()
        self.kayit = []   # (gün, option, adet, bilgi)

    def karar(self, g, adaylar: np.ndarray) -> dict:
        return {}

    def __call__(self, g):
        dis = {o: q for o, q in self.lumoda(g).items() if not self.oyun[o]}
        h_gun = g.gun - self.lansman
        aday = np.flatnonzero(self.oyun & (h_gun >= 0) & (g.rpt_sayisi == 0) & (h_gun % 7 == 0))
        ic = self.karar(g, aday) if aday.size else {}
        return {**dis, **ic}


class RPTYok(KolRPT):
    pass


class Mevcut(KolRPT):
    def karar(self, g, adaylar):
        return {o: q for o, q in self.lumoda(g).items() if self.oyun[o]}


class FRR(KolRPT):
    def __init__(self, b: Baglam, hafta: int = 3):
        super().__init__(b)
        self.hafta = hafta

    def karar(self, g, adaylar):
        w = self.b.dunya
        opt = w.optionlar
        sonuc = {}
        str_ = np.divide(g.satilan_option, g.gonderilen_option, out=np.zeros(len(opt)),
                         where=g.gonderilen_option > 0)
        for o in adaylar:
            h = (g.gun - self.lansman[o]) // 7
            if h != self.hafta:
                continue
            L = int(opt.at[o, "rpt_hafta"])
            yetisir = self.lansman[o] + 7 * 3 + 7 * L < opt.at[o, "indirim_gun"]
            if str_[o] < 0.55 or not yetisir:
                continue
            e = self.b.egriler[opt.at[o, "sezon_kodu"]][("ham", "indirim")]
            x = float(g.satilan_option[o])  # dünkü akşama kadar brüt satış (lansmandan)
            q = miktar.frr(x, e.k((int(opt.at[o, "dalga"]),), h), float(w.ilk_alim[o]),
                           int(opt.at[o, "moq_option"]))
            if q > 0:
                sonuc[int(o)] = q
                self.kayit.append((g.gun, int(o), q, {"x": x}))
        return sonuc


class Oneri(KolRPT):
    """Aday modeli + newsvendor."""

    def __init__(self, b: Baglam, model: str = "lgbm", haftalar=(2, 3, 4, 5, 6)):
        super().__init__(b)
        self.model = model
        self.haftalar = set(haftalar)

    def karar(self, g, adaylar):
        from . import aday

        w = self.b.dunya
        opt = w.optionlar
        satirlar = [anlik.ozet(g, int(o), self.b.idx) for o in adaylar
                    if (g.gun - self.lansman[o]) // 7 in self.haftalar]
        if not satirlar:
            return {}
        sonuc = {}
        kayit = pd.DataFrame(satirlar)
        for sezon, parca in kayit.groupby(opt["sezon_kodu"].to_numpy()[kayit["option"]]):
            ozl = aday.ozellikler(parca, w, self.b.egriler[sezon], self.b.belirsizlik[sezon], self.b.p_ind)
            p = self.b.modeller[sezon].olasilik(ozl, self.model)
            for r, pr in zip(ozl.itertuples(index=False), p):
                if pr >= self.b.esik and r.q_nv > 0:
                    sonuc[int(r.option)] = int(r.q_nv)
                    self.kayit.append((g.gun, int(r.option), int(r.q_nv), {"p": float(pr), "h": r.h}))
        return sonuc


class Kahin(KolRPT):
    """Gerçek talebi bilen kol. İlk karar pazartesisinde (h = 2) bütün
    h' ∈ 2…6 seçeneklerini değerlendirir, en kârlısını planlar."""

    def __init__(self, b: Baglam, haftalar=(2, 3, 4, 5, 6)):
        super().__init__(b)
        w = b.dunya
        self.haftalar = tuple(haftalar)
        opt = w.optionlar
        O = len(opt)
        # Option × gün gerçek talep, birikimli
        T = np.zeros((b.talep.shape[0], O))
        for o in np.flatnonzero(self.oyun):
            T[:, o] = b.talep[:, b.idx.hucre[o]].sum(axis=1)
        self.kum = np.vstack([np.zeros((1, O)), np.cumsum(T, axis=0)])
        self.plan = {}   # option → (gün, adet)

    def _pencere(self, o, bas, son):
        D = self.kum.shape[0] - 1
        bas, son = min(max(bas, 0), D), min(max(son, 0), D)
        return self.kum[son, o] - self.kum[bas, o] if son > bas else 0.0

    def _planla(self, g, o):
        w = self.b.dunya
        opt = w.optionlar
        lan, ind, cik = self.lansman[o], int(opt.at[o, "indirim_gun"]), int(opt.at[o, "cikis_gun"])
        L = int(opt.at[o, "rpt_hafta"])
        p, c, pi = float(opt.at[o, "liste_fiyati"]), float(opt.at[o, "alis_fiyati"]), float(self.b.p_ind[o])
        moq = int(opt.at[o, "moq_option"])
        ip = g.depo[self.b.idx.sku[o]].sum() + g.magaza_stok[self.b.idx.hucre[o]].sum() + sum(
            int(np.sum(s["adetler"])) for s in g.acik_siparisler if s["option"] == o)
        en_iyi = (0.0, None, 0)
        for hh in self.haftalar:
            gun = lan + 7 * hh
            if gun < g.gun:
                continue
            gelis = gun + 7 * L + int(w.sapma_rpt[o, 0])
            B = self._pencere(o, g.gun, gelis)
            Xtf = self._pencere(o, gelis, ind)
            Xind = self._pencere(o, max(gelis, ind), cik)
            C0 = max(ip - B, 0.0)
            F = max(Xtf - C0, 0.0)
            M = max(Xind - max(C0 - Xtf, 0.0), 0.0)
            Q = F + (M if pi > c else 0.0)
            if Q <= 0:
                continue
            Q = moq_yuvarla(Q, moq)

            def kar(q):
                tf = min(q, F)
                return p * tf + pi * min(q - tf, M) - c * q

            if kar(Q) > en_iyi[0]:
                en_iyi = (kar(Q), gun, Q)
        if en_iyi[1] is not None:
            self.plan[o] = (en_iyi[1], en_iyi[2])

    def karar(self, g, adaylar):
        sonuc = {}
        for o in adaylar:
            h = (g.gun - self.lansman[o]) // 7
            if o not in self.plan and h == self.haftalar[0]:
                self._planla(g, o)
            if o in self.plan and self.plan[o][0] == g.gun:
                sonuc[int(o)] = int(self.plan[o][1])
                self.kayit.append((g.gun, int(o), int(self.plan[o][1]), {}))
        return sonuc
