"""Kâhin kolu: koşunun talebini bilen RPT kararı ("bilgi tam olsaydı").

`Kahin(gercek_talep, temel, ogrenilen)` bir `politika.KolRPT`'dir (oyun option'ları
kendi kararı, ötekiler Lumoda). Gerçek talep argümandır: bir motor koşusunun gizli
gerçeği (`rpt.motor.Kosu.gercek`: tarih, urun_id, talep; hücre-gün). İlk karar
pazartesisinde (h = 2) option'ın bütün h' ∈ 2…6 seçeneklerini o talep ve gerçek
teslim gecikmesiyle (dünyanın gizli `sapma_rpt`'si) değerlendirir, en kârlısını
planlar; aynı tedarik süresi ve MOQ. Stok akışı zincir düzeyinde; mağazalar arası
sıkışmayı bilmez — üst sınır değil, "bilgi tam olsaydı" kolu. v4'te talep fiyata
(markdown içseldir) bağlı olduğundan kâhinin bildiği, verilen koşunun talebidir.

SIZINTI. Bu modül gizli gerçeği görür; bu yüzden `politika`'nın dışındadır
(`politika` bunu içe aktarmaz; sızıntı taraması geçişlidir, `tests/test_sizinti.py`).
"""

import hashlib

import numpy as np
import pandas as pd

from . import anlik, miktar
from .politika import HAFTALAR, OYUN_SEZONLARI, KolRPT, Ogrenilen


def talep_ozeti(gercek_talep: pd.DataFrame) -> str:
    """Gerçek talep tablosunun özeti (koşu önbelleği anahtarı için)."""
    d = gercek_talep[["tarih", "urun_id", "talep"]]
    h = pd.util.hash_pandas_object(d, index=False).to_numpy()
    return hashlib.sha256(h.tobytes()).hexdigest()[:20]


class Kahin(KolRPT):
    """Gerçek talebi ve gerçek teslim gecikmesini bilen kol."""

    ad = "kahin"

    def __init__(self, gercek_talep: pd.DataFrame, temel, ogrenilen: Ogrenilen, haftalar=HAFTALAR,
                 oyun_sezonlari=OYUN_SEZONLARI, talep_kimligi: str | None = None):
        super().__init__(temel, oyun_sezonlari)
        self.gercek_talep = gercek_talep
        self.ogrenilen = ogrenilen
        self.haftalar = tuple(int(h) for h in haftalar)
        self.talep_kimligi = talep_kimligi or talep_ozeti(gercek_talep)
        self.plan: dict = {}          # option → (gün, adet)
        self.kum = None

    def _sifirla(self) -> None:
        super()._sifirla()
        self.plan = {}
        self.kum = None

    def parametreler(self) -> dict:
        return {**super().parametreler(), "haftalar": list(self.haftalar), "talep": self.talep_kimligi,
                "p_ind": self.ogrenilen.parametreler()["p_ind"]}

    def _kur(self, g) -> None:
        """Option × gün gerçek talep, birikimli ([gün + 1, O]; yalnız oyun option'ları)."""
        w = g.dunya
        self.idx = anlik.Indeks.kur(w)
        gun0 = pd.Timestamp(g.tarih).normalize() - pd.Timedelta(days=int(g.gun))
        urun_opt = pd.Series(np.asarray(w.sku_option), index=w.urunler["urun_id"].astype(str))
        d = self.gercek_talep
        o = urun_opt.reindex(d["urun_id"].astype(str)).to_numpy()
        gun = (pd.to_datetime(d["tarih"]) - gun0).dt.days.to_numpy()
        sec = self.oyun[o] & (gun >= 0)
        O = len(w.optionlar)
        D = int(gun[sec].max()) + 1 if sec.any() else 1
        T = np.zeros((D, O))
        np.add.at(T, (gun[sec], o[sec]), d["talep"].to_numpy(float)[sec])
        self.kum = np.vstack([np.zeros((1, O)), np.cumsum(T, axis=0)])

    def _pencere(self, o, bas, son) -> float:
        D = self.kum.shape[0] - 1
        bas, son = min(max(bas, 0), D), min(max(son, 0), D)
        return float(self.kum[son, o] - self.kum[bas, o]) if son > bas else 0.0

    def _planla(self, g, o: int) -> None:
        w = g.dunya
        opt = w.optionlar
        lan, ind, cik = int(self.lansman[o]), int(self.indirim[o]), int(opt.at[o, "cikis_gun"])
        L = int(self.L[o])
        p, c = float(opt.at[o, "liste_fiyati"]), float(opt.at[o, "alis_fiyati"])
        pi = float(self.ogrenilen.p_ind[self.option_id[o]])
        moq = int(self.moq[o])
        hc = self.idx.hucre[o]
        ip = (np.asarray(g.depo)[self.idx.sku[o]].sum() + np.asarray(g.magaza_stok)[hc].sum()
              + np.asarray(g.yolda)[hc].sum()
              + sum(int(np.sum(s["adetler"])) for s in g.acik_siparisler if s["option"] == o))
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
            Q = miktar.moq_yuvarla(Q, moq)
            tf = min(Q, F)
            kar = p * tf + pi * min(Q - tf, M) - c * Q
            if kar > en_iyi[0]:
                en_iyi = (kar, gun, Q)
        if en_iyi[1] is not None:
            self.plan[o] = (en_iyi[1], en_iyi[2])

    def karar(self, g, adaylar):
        if self.kum is None:
            self._kur(g)
        sonuc = {}
        for o in adaylar:
            o = int(o)
            h = (g.gun - self.lansman[o]) // 7
            if o not in self.plan and h == self.haftalar[0]:
                self._planla(g, o)
            if o in self.plan and self.plan[o][0] == g.gun:
                sonuc[o] = int(self.plan[o][1])
                self._kaydet(g, o, int(self.plan[o][1]))
        return sonuc
