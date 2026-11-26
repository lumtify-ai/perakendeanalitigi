"""`model`: marjinal değerler ve sezon programı (K10, K19, K21). Elle kurulmuş küçük `KararGirdisi`lerle sınanır;
`veri` işaretli test yayımlanan v4'te (yol 0) AW24 ve SS25 programlarını çözer.

Dünya: asorti 1-2-2-1-1, liste 100 TL (tam 100, indirim 70, kalıntı oranı 0,2 → 20 TL), alış 40 TL. Test paketi
toplama 5 TL, yıpranma %5 (adet başı 7 TL), kargo rota başı 40 TL. Talep (mu_tam, mu_ind) mağaza × option
başına verilir, hücreye beden çarpanıyla dağılır."""

import ast
import itertools
import math
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pulp
import pytest

from kiriklik import kaynak, model, plan, sabitler, tahmin, uygunluk
from kiriklik.sabitler import Paket

KARAR = date(2024, 12, 9)
LISTE, ALIS, FIYAT_TAM, FIYAT_IND, KALINTI = 100.0, 40.0, 100.0, 70.0, 0.2
PAKET = Paket(5.0, 40.0, 0.05)
BIRIM = PAKET.toplama_birim_tl + PAKET.yipranma_orani * ALIS          # 7 TL
BEDEN_CARPANI = (0.6, 1.0, 1.0, 0.8, 0.5)
ONBELLEK = Path(__file__).resolve().parents[1] / "cikti" / "ogrenme"


def _dunya(stoklar: dict, magazalar: dict | None = None) -> kaynak.KararGirdisi:
    """`stoklar`: {(mağaza, option): 5 bedenlik stok}; depo ve açık sipariş 0 (her beden doldurulamaz).
    `magazalar`: {mağaza: uygun} (verilmezse hepsi uygun)."""
    satir = [(m, o, i + 1, s, 0, 0) for (m, o), st in stoklar.items() for i, s in enumerate(st)]
    hucre = pd.DataFrame(satir, columns=["magaza_id", "option_id", "beden_sira", "stok", "depo", "acik_siparis"])
    hucre["urun_id"] = hucre.option_id + "-" + hucre.beden_sira.astype(str)
    hucre["liste_fiyati"], hucre["alis_fiyati"] = LISTE, ALIS
    if magazalar is None:
        magazalar = {m: True for m in hucre.magaza_id.unique()}
    magaza = pd.DataFrame({"magaza_id": list(magazalar), "ad": list(magazalar), "sehir": "X", "bolge": "Y",
                           "tip": "AVM", "uygun": list(magazalar.values())})
    opt = pd.DataFrame({"option_id": sorted(hucre.option_id.unique())})
    opt["lansman_tarihi"] = pd.Timestamp("2024-08-19")
    return kaynak.KararGirdisi(sezon="AW24", karar=KARAR, indirim=date(2025, 1, 2), cikis=date(2025, 2, 24),
                               hucre=hucre, satis=pd.DataFrame(), stoklu=pd.DataFrame(), magaza=magaza,
                               optionlar=opt, takvim=pd.DataFrame(), kampanya=pd.DataFrame())


def _talep(g, mu: dict) -> pd.DataFrame:
    """`mu`: {(mağaza, option) ya da (mağaza, option, beden_sira): (mu_tam, mu_ind)} (beden anahtarı önce);
    verilmeyen çift (0,2; 0,2). Beden çarpanı her hücreye uygulanır. Bütün hücreler."""
    h = g.hucre
    c = np.asarray(BEDEN_CARPANI)[h.beden_sira.to_numpy() - 1]
    m_ = [mu.get((m, o, s), mu.get((m, o), (0.2, 0.2)))
          for m, o, s in zip(h.magaza_id, h.option_id, h.beden_sira)]
    mt, mi = np.array([a for a, _ in m_]), np.array([b for _, b in m_])
    return pd.DataFrame({"magaza_id": h.magaza_id, "urun_id": h.urun_id, "mu_tam": mt * c, "mu_ind": mi * c,
                         "fiyat_tam": FIYAT_TAM, "fiyat_ind": FIYAT_IND})[tahmin.KOLONLAR]


def _coz(g, talep, set_kosulu=False, verici_yalniz_kirik=False, paket=PAKET):
    return model.coz(g, talep, KALINTI, paket, set_kosulu=set_kosulu, verici_yalniz_kirik=verici_yalniz_kirik,
                     kol="opt_set" if set_kosulu else "opt")


# ---------------------------------------------------------------- bağımsız değerleme

def _toplam_deger(t, f: int) -> float:
    """Hücrenin f adetlik stoğunun beklenen değeri Σ_{k ≤ f} v(k)."""
    if f <= 0:
        return 0.0
    return float(model.marjinal_degerler(t.mu_tam, t.mu_ind, t.fiyat_tam, t.fiyat_ind, KALINTI * LISTE, f).sum())


class _Degerleyici:
    """Planın amacını hareket listesinden, programdan bağımsız hesaplar: Σ hücre [V(son) − V(ilk)]
    − adet başı maliyet × adet − kargo × tekil rota."""

    def __init__(self, g, talep, paket=PAKET):
        self.stok = {(m, o, s): int(a) for m, o, s, a in
                     g.hucre[["magaza_id", "option_id", "beden_sira", "stok"]].itertuples(index=False)}
        self.urun = dict(zip(zip(g.hucre.option_id, g.hucre.beden_sira), g.hucre.urun_id))
        self.t = talep.set_index(["magaza_id", "urun_id"])
        self.paket = paket
        self._v = {}

    def V(self, m, o, s, f):
        k = (m, o, s, f)
        if k not in self._v:
            self._v[k] = _toplam_deger(self.t.loc[(m, self.urun[(o, s)])], f)
        return self._v[k]

    def hucre_degisimi(self, degisim: dict) -> float:
        return sum(self.V(m, o, s, self.stok[(m, o, s)] + d) - self.V(m, o, s, self.stok[(m, o, s)])
                   for (m, o, s), d in degisim.items() if d)

    def amac(self, hareketler) -> float:
        degisim = {}
        for o, s, v, a, n in hareketler[["option_id", "beden_sira", "verici", "alici", "adet"]].itertuples(
                index=False):
            degisim[(a, o, s)] = degisim.get((a, o, s), 0) + n
            degisim[(v, o, s)] = degisim.get((v, o, s), 0) - n
        birim = self.paket.toplama_birim_tl + self.paket.yipranma_orani * ALIS
        rota = len(set(zip(hareketler.verici, hareketler.alici)))
        return self.hucre_degisimi(degisim) - birim * hareketler.adet.sum() - self.paket.kargo_rota_tl * rota


def _kaba_kuvvet(g, talep, set_kosulu, verici_yalniz_kirik) -> float:
    """Bütün tamsayı planlarını sayarak en iyi amaç (K21'in sınırları, programdan bağımsız yazılmış).

    Option başına olurlu hareket vektörleri ayrı sayılır (option'lar yalnız rota kargosuyla bağlıdır), sonra
    bütün bileşimler kargo tekil rota üzerinden ödenerek birleştirilir."""
    d = _Degerleyici(g, talep)
    ad = uygunluk.adaylar(g)
    alici = set(map(tuple, ad.loc[ad.uygun, ["magaza_id", "option_id"]].to_numpy()))
    kirik = set(map(tuple, ad.loc[ad.neden != "magaza", ["magaza_id", "option_id"]].to_numpy()))
    uygun_m = set(g.magaza.magaza_id[g.magaza.uygun])
    ih = uygunluk.ihtiyac_tablosu(g)
    ihtiyac = {(m, o, s): n for m, o, s, n in ih.itertuples(index=False) if (m, o) in alici}
    secenekler = []
    for o in sorted(g.hucre.option_id.unique()):
        yaylar = [(v, a, s, min(st, n)) for (a, o2, s), n in sorted(ihtiyac.items()) if o2 == o
                  for (v, o3, s3), st in sorted(d.stok.items())
                  if o3 == o and s3 == s and st > 0 and v != a and v in uygun_m
                  and (not verici_yalniz_kirik or (v, o) in kirik)]
        olurlu = []
        for x in itertools.product(*[range(ub + 1) for *_, ub in yaylar]):
            gelen, giden = {}, {}
            for (v, a, s, _), n in zip(yaylar, x):
                gelen[(a, s)] = gelen.get((a, s), 0) + n
                giden[(v, s)] = giden.get((v, s), 0) + n
            if any(n > ihtiyac[(a, o, s)] for (a, s), n in gelen.items()):
                continue
            if any(n > d.stok[(v, o, s)] for (v, s), n in giden.items()):
                continue
            alanlar = {a for (a, s), n in gelen.items() if n}
            if alanlar & {v for (v, s), n in giden.items() if n}:
                continue
            if set_kosulu and any(gelen.get((a, s), 0) == 0 for a in alanlar for s in range(1, 6)
                                  if d.stok[(a, o, s)] == 0):
                continue
            degisim = {(a, o, s): n for (a, s), n in gelen.items()}
            for (v, s), n in giden.items():
                degisim[(v, o, s)] = degisim.get((v, o, s), 0) - n
            deger = d.hucre_degisimi(degisim) - BIRIM * sum(x)
            rotalar = frozenset((v, a) for (v, a, *_), n in zip(yaylar, x) if n)
            olurlu.append((deger, rotalar))
        secenekler.append(olurlu)
    en_iyi = -math.inf
    for bilesim in itertools.product(*secenekler):
        rotalar = frozenset().union(*(r for _, r in bilesim))
        en_iyi = max(en_iyi, sum(v for v, _ in bilesim) - PAKET.kargo_rota_tl * len(rotalar))
    return en_iyi


# ---------------------------------------------------------------- marjinal değer

def test_marjinal_poisson_elle():
    v = model.marjinal_degerler(1.0, 0.0, 100.0, 70.0, 0.0, 3)
    assert v.shape == (3,)
    assert v[0] == pytest.approx(100.0 * (1 - math.exp(-1)))
    assert v[1] == pytest.approx(100.0 * (1 - 2 * math.exp(-1)))
    # ikinci evre ve kalıntı: D1 ~ P(1), D2 ~ P(0,5); v(1) = 100·P(D1≥1) + 70·[P(D≥1) − P(D1≥1)] + 20·P(D=0)
    w = model.marjinal_degerler(1.0, 0.5, 100.0, 70.0, 20.0, 1)
    p1, p12 = 1 - math.exp(-1), 1 - math.exp(-1.5)
    assert w[0] == pytest.approx(100 * p1 + 70 * (p12 - p1) + 20 * (1 - p12))
    assert model.marjinal_degerler(0.0, 0.0, 100.0, 70.0, 20.0, 2).tolist() == [20.0, 20.0]
    assert model.marjinal_degerler(1.0, 1.0, 100.0, 70.0, 20.0, 0).shape == (0,)


def test_marjinal_azalan():
    rng = np.random.default_rng(7)
    for _ in range(50):
        mt, mi = rng.uniform(0, 30, 2)
        ft = rng.uniform(50, 1500)
        fi = ft * rng.uniform(0.3, 1.0)
        kt = fi * rng.uniform(0.0, 1.0)
        v = model.marjinal_degerler(mt, mi, ft, fi, kt, 120)
        assert (np.diff(v) <= 0).all()
        assert v[0] <= ft + 1e-9 and v[-1] >= kt - 1e-9
        assert v[-1] == pytest.approx(kt, abs=1e-6)                  # talebin çok ötesinde yalnız kalıntı
    with pytest.raises(ValueError):
        model.marjinal_degerler(-1.0, 0.0, 100.0, 70.0, 20.0, 3)


# ---------------------------------------------------------------- program

# İki option, üç mağaza, hücre başına en çok 2 adet. O1: A (kırık 1, 4) ve C (kırık 2) alıcı adayı, B tam set.
# O2: B (kırık 2, 3) ve C (kırık 1) alıcı adayı, A tam set.
_KABA = {("A", "O1"): (0, 2, 2, 0, 1), ("B", "O1"): (1, 1, 2, 1, 1), ("C", "O1"): (2, 0, 1, 2, 1),
         ("A", "O2"): (1, 2, 1, 1, 1), ("B", "O2"): (1, 0, 0, 1, 1), ("C", "O2"): (0, 1, 2, 1, 1)}
_KABA_MU = {("A", "O1"): (1.6, 0.9), ("B", "O1"): (0.3, 0.3), ("C", "O1"): (0.9, 0.5),
            ("A", "O2"): (0.3, 0.2), ("B", "O2"): (1.4, 0.8), ("C", "O2"): (0.8, 0.4)}


@pytest.mark.parametrize("set_kosulu,verici_yalniz_kirik", [(False, False), (True, True), (False, True)])
def test_kaba_kuvvetle_ayni(set_kosulu, verici_yalniz_kirik):
    g = _dunya(_KABA)
    t = _talep(g, _KABA_MU)
    p = _coz(g, t, set_kosulu, verici_yalniz_kirik)
    en_iyi = _kaba_kuvvet(g, t, set_kosulu, verici_yalniz_kirik)
    deger = _Degerleyici(g, t).amac(p.hareketler)
    assert en_iyi > 0 and not p.hareketler.empty                       # dünya önemsiz değil
    assert deger == pytest.approx(p.bilgi["amac"], abs=1e-6)
    assert en_iyi * (1 - sabitler.GAP_REL) - 1e-6 <= deger <= en_iyi + 1e-6
    assert p.bilgi["durum"] == "optimal"
    assert p.bilgi["sinir"] >= p.bilgi["amac"] - 1e-6
    # R16: LP gevşetmesi geçerli üst sınır; daraltmanın kaybını gap_lp sınırlar
    b = p.bilgi
    assert b["lp_siniri"] >= en_iyi - 1e-6
    assert b["gap_lp"] == pytest.approx((b["lp_siniri"] - b["amac"]) / b["lp_siniri"], abs=1e-9)
    assert en_iyi - deger <= b["gap_lp"] * b["lp_siniri"] + 1e-6
    # R18: set koşulunda kesmeli kök sınırı da; sinir = min(lp, kök), set koşulsuz sinir = lp
    if set_kosulu:
        assert b["kok_siniri"] is not None and b["sinir"] == min(b["lp_siniri"], b["kok_siniri"])
    else:
        assert b["kok_siniri"] is None and b["sinir"] == b["lp_siniri"] and b["gap"] == b["gap_lp"]
    assert b["sinir"] >= en_iyi - 1e-6
    assert b["gap"] == pytest.approx(max(0.0, b["sinir"] - b["amac"]) / b["sinir"], abs=1e-9)
    assert b["rota_daraltilmis"] <= b["rota_aday"]


def test_kaba_kuvvet_kosullari_bagliyor():
    # set koşulu ve verici süzgeci bu dünyada en iyi amacı gerçekten değiştirir (kıyas boş geçmesin)
    g = _dunya(_KABA)
    t = _talep(g, _KABA_MU)
    serbest = _kaba_kuvvet(g, t, False, False)
    assert _kaba_kuvvet(g, t, True, True) < serbest
    assert _kaba_kuvvet(g, t, False, True) < serbest


def _tek_birim_dunyasi(optionlar):
    """A her option'da yalnız 4. bedende kırık (ihtiyaç 1), B tam set ve zayıf: adedin net kazancı kargodan
    küçük, iki adedinki büyük."""
    stok = {}
    for o in optionlar:
        stok[("A", o)] = (1, 2, 2, 0, 1)
        stok[("B", o)] = (1, 2, 2, 1, 1)
    mu = {("A", o): (2.0, 1.0) for o in optionlar} | {("B", o): (0.05, 0.05) for o in optionlar}
    return _dunya(stok), mu


def test_ortak_rota_bir_kez():
    g1, mu1 = _tek_birim_dunyasi(["O1"])
    t1 = _talep(g1, mu1)
    d = _Degerleyici(g1, t1)
    net = d.hucre_degisimi({("A", "O1", 4): 1, ("B", "O1", 4): -1}) - BIRIM
    paket = Paket(PAKET.toplama_birim_tl, 1.5 * net, PAKET.yipranma_orani)     # net < kargo < 2·net
    assert _coz(g1, t1, paket=paket).hareketler.empty                           # tek option kargoyu taşımaz
    g2, mu2 = _tek_birim_dunyasi(["O1", "O2"])
    p = _coz(g2, _talep(g2, mu2), paket=paket)
    h = p.hareketler
    assert sorted(h.option_id) == ["O1", "O2"] and set(zip(h.verici, h.alici)) == {("B", "A")}
    assert h.adet.tolist() == [1, 1] and p.bilgi["rota_sayisi"] == 1
    assert p.bilgi["amac"] == pytest.approx(2 * net - paket.kargo_rota_tl)    # kargo bir kez


def test_set_kosulu_tamamla_ya_da_hic():
    # A kırık 2 ve 3; D kırık 3 (2. bedeni var), 3. bedeni olan kırık verici yok → opt_set A'ya dokunmaz,
    # opt D'nin 2. bedenini taşır.
    stok = {("A", "O1"): (1, 0, 0, 1, 1), ("D", "O1"): (1, 2, 0, 1, 1)}
    mu = {("A", "O1"): (3.0, 1.0), ("D", "O1"): (0.1, 0.1)}
    g = _dunya(stok)
    t = _talep(g, mu)
    assert _coz(g, t, True, True).hareketler.empty
    p = _coz(g, t)
    assert set(zip(p.hareketler.alici, p.hareketler.beden_sira)) == {("A", 2)}
    # E kırık 1, 3. bedeni var → opt_set A'yı tamamlar: her kırık beden ≥ 1, bütün bedenler ≥ 1
    stok[("E", "O1")] = (0, 1, 2, 1, 1)
    mu[("E", "O1")] = (0.1, 0.1)
    g = _dunya(stok)
    q = _coz(g, _talep(g, mu), True, True)
    gelen = q.hareketler[q.hareketler.alici == "A"].groupby("beden_sira").adet.sum()
    assert gelen.get(2, 0) >= 1 and gelen.get(3, 0) >= 1
    assert q.bilgi["tamamlanan_alicilar"] == [["O1", "A"]]
    for (o, a), alt in q.hareketler.groupby(["option_id", "alici"]):           # her alıcı tamamlanır
        son = [stok[(a, o)][s - 1] + alt.adet[alt.beden_sira == s].sum() for s in range(1, 6)]
        assert min(son) >= 1
    # A 3. bedende zayıf: o adet tek başına kârsız (ayrı rota, düşük değer). opt yalnız 2. bedeni alır; opt_set
    # 2. bedenin kazancıyla 3. bedeni de taşır (tamamlamak zorunda), yoksa hiç almaz.
    mu[("A", "O1", 3)] = (0.05, 0.05)
    g = _dunya(stok)
    t = _talep(g, mu)
    serbest = _coz(g, t, False, True).hareketler
    assert set(zip(serbest.alici, serbest.beden_sira)) == {("A", 2)}
    q = _coz(g, t, True, True).hareketler
    assert {2, 3} <= set(q.beden_sira[q.alici == "A"])
    assert _Degerleyici(g, t).amac(q) == pytest.approx(_kaba_kuvvet(g, t, True, True), rel=sabitler.GAP_REL)


def test_alici_asorti_ustu_almaz():
    # A: 2. bedende 1 (asorti 2), 3. beden kırık; çok güçlü alıcı, bol stoklu zayıf verici: son stok asortiyi aşmaz
    stok = {("A", "O1"): (1, 1, 0, 1, 1), ("B", "O1"): (5, 9, 9, 5, 5)}
    g = _dunya(stok)
    p = _coz(g, _talep(g, {("A", "O1"): (40.0, 20.0), ("B", "O1"): (0.1, 0.1)}))
    gelen = p.hareketler.groupby("beden_sira").adet.sum().to_dict()
    assert gelen == {2: 1, 3: 2}
    assert set(p.hareketler.alici) == {"A"}


def test_alici_verici_ayni_option_olmaz():
    # A kırık 1, C kırık 2; birbirlerinin eksiğini ancak birbirleri tutar. A 1. bedende, C 2. bedende güçlü:
    # takas iki yönde de tek başına kârlı ama bir mağaza bir option'da hem alıcı hem verici olamaz.
    g = _dunya({("A", "O1"): (0, 2, 2, 1, 1), ("C", "O1"): (1, 0, 2, 1, 1)})
    t = _talep(g, {("A", "O1", 1): (3.0, 1.0), ("A", "O1"): (0.1, 0.1),
                   ("C", "O1", 2): (3.0, 1.0), ("C", "O1"): (0.1, 0.1)})
    d = _Degerleyici(g, t)
    for yon in ({("A", "O1", 1): 1, ("C", "O1", 1): -1}, {("C", "O1", 2): 2, ("A", "O1", 2): -2}):
        assert d.hucre_degisimi(yon) - BIRIM * abs(sum(v for v in yon.values() if v > 0)) > PAKET.kargo_rota_tl
    p = _coz(g, t)
    h = p.hareketler
    assert len(h) == 1
    assert not set(zip(h.alici, h.option_id)) & set(zip(h.verici, h.option_id))
    # kaba kuvvetle de en iyisi bu
    assert _Degerleyici(g, t).amac(h) == pytest.approx(_kaba_kuvvet(g, t, False, False), rel=sabitler.GAP_REL)
    # ayrı option'larda aynı mağaza alıcı ve verici olabilir: O1'de A alır C verir, O2'de C alır A verir
    stok = {("A", "O1"): (0, 2, 2, 1, 1), ("C", "O1"): (1, 2, 2, 1, 1), ("C", "O2"): (1, 0, 2, 1, 1),
            ("A", "O2"): (1, 2, 2, 1, 1)}
    mu = {("A", "O1"): (3.0, 1.0), ("C", "O1"): (0.1, 0.1), ("C", "O2"): (3.0, 1.0), ("A", "O2"): (0.1, 0.1)}
    g2 = _dunya(stok)
    q = _coz(g2, _talep(g2, mu)).hareketler
    assert set(zip(q.option_id, q.verici, q.alici)) == {("O1", "C", "A"), ("O2", "A", "C")}


def test_vericisiz_model_bos():
    # tek mağaza: alıcı adayı var, verici yok
    g = _dunya({("A", "O1"): (1, 0, 2, 1, 1)})
    p = _coz(g, _talep(g, {}))
    assert p.hareketler.empty and p.kol == "opt" and p.bilgi["durum"] == "optimal" and p.bilgi["amac"] == 0.0
    # öteki mağaza da aynı bedende kırık: o bedenin stoğu yok
    g = _dunya({("A", "O1"): (1, 0, 2, 1, 1), ("B", "O1"): (1, 0, 1, 1, 1)})
    assert _coz(g, _talep(g, {}), True, True).hareketler.empty
    # kırık çift yok
    g = _dunya({("A", "O1"): (1, 2, 2, 1, 1), ("B", "O1"): (1, 2, 2, 1, 1)})
    p = _coz(g, _talep(g, {}))
    assert p.hareketler.empty and p.bilgi["degisken_sayisi"] == 0
    # verici mağaza uygun değil
    g = _dunya({("A", "O1"): (1, 0, 2, 1, 1), ("B", "O1"): (1, 2, 2, 1, 1)}, {"A": True, "B": False})
    assert _coz(g, _talep(g, {("A", "O1"): (5.0, 2.0)})).hareketler.empty


def test_plan_ve_bilgi():
    g = _dunya(_KABA)
    p = _coz(g, _talep(g, _KABA_MU), True, True)
    assert isinstance(p, plan.Plan) and p.sezon == "AW24" and p.kol == "opt_set"
    assert list(p.hareketler.columns) == plan.KOLONLAR
    assert [t.kind for t in p.hareketler.dtypes] == ["O", "O", "i", "O", "O", "i"]
    assert (p.hareketler.urun_id == p.hareketler.option_id + "-" + p.hareketler.beden_sira.astype(str)).all()
    for k in ("durum", "amac", "lp_siniri", "gap_lp", "sinir", "gap", "degisken_sayisi", "kisit_sayisi",
              "rota_aday", "rota_daraltilmis", "kurma_sn", "lp_sn", "kok_sn", "mip_sn", "sure_sn",
              "kok_siniri", "cbc_sinir", "cbc_gap", "rota_sayisi",
              "tamamlanan_alicilar", "set_kosulu", "verici_yalniz_kirik"):
        assert k in p.bilgi, k
    assert p.bilgi["rota_sayisi"] == len(plan.rotalar(p.hareketler))
    assert p.bilgi["cbc_gap"] == pytest.approx(0.0, abs=sabitler.GAP_REL)


def test_artan_marjinal_deger_hata():
    # R17: kalıntı (20 TL) indirim fiyatının üstündeyse v artar, artım değişkenleri sırayla dolmaz → ValueError
    g = _dunya({("A", "O1"): (1, 0, 2, 1, 1), ("B", "O1"): (1, 2, 2, 1, 1)})
    t = _talep(g, {("A", "O1"): (0.5, 0.5)}).assign(fiyat_tam=10.0, fiyat_ind=5.0)
    with pytest.raises(ValueError, match="artıyor"):
        _coz(g, t)


@pytest.mark.parametrize("set_kosulu", [False, True])
def test_cozumsuz_bos_plan(monkeypatch, set_kosulu):
    # CBC tamsayı çözüm bulamazsa (kök de bulamazsa) boş plan, durum "cozumsuz"; sınır LP'ye düşer
    monkeypatch.setattr(model, "_cbc", lambda pr, dugum, secenekler, gap_rel: (pulp.LpSolutionNoSolutionFound, None))
    g = _dunya(_KABA)
    p = _coz(g, _talep(g, _KABA_MU), set_kosulu, set_kosulu)
    b = p.bilgi
    assert p.hareketler.empty and b["durum"] == "cozumsuz" and b["amac"] == 0.0
    assert b["sinir"] == b["lp_siniri"] and b["kok_siniri_yok"] is set_kosulu


def test_kok_cozumu_daha_iyiyse_plan_odur(monkeypatch):
    # daraltılmış program çözümsüz kalırsa kökün bütün programdaki çözümü plan olur (R19)
    gercek = model._cbc

    def sahte(pr, dugum, secenekler, gap_rel):
        return gercek(pr, dugum, secenekler, gap_rel) if dugum == 0 else (pulp.LpSolutionNoSolutionFound, None)

    monkeypatch.setattr(model, "_cbc", sahte)
    g = _dunya(_KABA)
    t = _talep(g, _KABA_MU)
    p = _coz(g, t, True, True)
    b = p.bilgi
    assert b["kaynak"] == "kok" and b["durum"] == "dugum_siniri" and b["daraltilmis_durum"] == "cozumsuz"
    assert not p.hareketler.empty and b["amac"] == pytest.approx(_Degerleyici(g, t).amac(p.hareketler), abs=1e-6)
    assert b["amac"] == b["kok_amaci"] <= _kaba_kuvvet(g, t, True, True) + 1e-6
    assert _coz(g, t, True, True).bilgi["kaynak"] in ("kok", "daraltilmis")


@pytest.mark.parametrize("set_kosulu", [False, True])
def test_ayni_girdi_ayni_plan(set_kosulu):
    g = _dunya(_KABA)
    t = _talep(g, _KABA_MU)
    p, q = _coz(g, t, set_kosulu, set_kosulu), _coz(g, t, set_kosulu, set_kosulu)
    assert p.kimlik == q.kimlik and not p.hareketler.empty
    assert p.bilgi["amac"] == q.bilgi["amac"]


def test_talep_eksik_hucre_hata():
    g = _dunya({("A", "O1"): (1, 0, 2, 1, 1), ("B", "O1"): (1, 2, 2, 1, 1)})
    t = _talep(g, {})
    with pytest.raises(ValueError, match="talep"):
        _coz(g, t[t.magaza_id != "B"])


def test_model_ice_aktarma_kilidi():
    yasak = ("perakende_veri", "allocation", "kiriklik.hakem", "kiriklik.simulasyon", "kiriklik.olcutler",
             "kiriklik.oyun", "markdown")
    agac = ast.parse(Path(model.__file__).read_text(encoding="utf-8"))
    alinan = set()
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            alinan |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            alinan.add(n.module or "")
    assert not [a for a in alinan if any(a == y or a.startswith(y + ".") for y in yasak)]


# ---------------------------------------------------------------- gerçek veri

def _veri_cozumu(veri_con, sezon, set_kosulu):
    g = kaynak.karar_girdisi(veri_con, sezon)
    og = tahmin.ogrenilen(veri_con, sezon, onbellek=ONBELLEK)
    talep = tahmin.ufuk_talebi(g, og)
    t0 = time.perf_counter()
    p = model.coz(g, talep, og.kalinti, sabitler.MALIYET_PAKETLERI[sabitler.KARAR_PAKETI],
                  set_kosulu=set_kosulu, verici_yalniz_kirik=set_kosulu, kol="opt_set" if set_kosulu else "opt")
    sure = time.perf_counter() - t0
    h = p.hareketler
    b = p.bilgi
    print(f"\n{sezon} {p.kol}: durum {b['durum']}, kaynak {b['kaynak']}, LP {b['lp_siniri']:.1f}, "
          f"amaç {b['amac']:.1f}, "
          f"gap_lp {b['gap_lp']:.5f}, kök {b['kok_siniri']}, sınır {b['sinir']:.1f}, gap {b['gap']:.5f}, "
          f"CBC daraltılmış sınır {b['cbc_sinir']} gap {b['cbc_gap']}, rota {b['rota_aday']}/"
          f"{b['rota_daraltilmis']}, değişken {b['degisken_sayisi']}/{b['lp_degisken_sayisi']}, "
          f"süre {sure:.1f} sn (kurma {b['kurma_sn']:.1f}, LP {b['lp_sn']:.1f}, kök {b['kok_sn']:.1f}, "
          f"MIP {b['mip_sn']:.1f}); "
          f"hareket {len(h)}, adet {int(h.adet.sum())}, plan rotası {b['rota_sayisi']}, "
          f"alıcı {b['alici_sayisi']}, tamamlanan {len(b['tamamlanan_alicilar'])}")
    return g, p


def _tutarli(g, p, set_kosulu):
    stok = g.hucre.set_index(["magaza_id", "option_id", "beden_sira"]).stok
    h = p.hareketler
    for (m, o, b), adet in h.groupby(["verici", "option_id", "beden_sira"]).adet.sum().items():
        assert adet <= stok[(m, o, b)]
    gelen = h.groupby(["alici", "option_id", "beden_sira"]).adet.sum()
    ih = uygunluk.ihtiyac_tablosu(g).set_index(["magaza_id", "option_id", "beden_sira"]).ihtiyac
    for k, adet in gelen.items():
        assert adet <= ih[k]
    ad = uygunluk.adaylar(g)
    assert set(zip(h.alici, h.option_id)) <= set(zip(ad.magaza_id[ad.uygun], ad.option_id[ad.uygun]))
    assert not set(zip(h.alici, h.option_id)) & set(zip(h.verici, h.option_id))
    if set_kosulu:
        kirik = set(zip(ad.magaza_id[ad.neden != "magaza"], ad.option_id[ad.neden != "magaza"]))
        assert set(zip(h.verici, h.option_id)) <= kirik
        assert len(p.bilgi["tamamlanan_alicilar"]) == h[["option_id", "alici"]].drop_duplicates().shape[0]


@pytest.mark.veri
@pytest.mark.parametrize("set_kosulu", [False, True])
def test_opt_aw24_cozulur(veri_con, set_kosulu):
    g, p = _veri_cozumu(veri_con, "AW24", set_kosulu)
    assert p.bilgi["durum"] in ("optimal", "dugum_siniri")          # R16
    assert p.bilgi["gap"] <= 0.05                                  # R18
    _tutarli(g, p, set_kosulu)


@pytest.mark.veri
@pytest.mark.parametrize("set_kosulu", [False, True])
def test_opt_ss25_cozulur(veri_con, set_kosulu):
    g, p = _veri_cozumu(veri_con, "SS25", set_kosulu)
    assert p.bilgi["durum"] in ("optimal", "dugum_siniri")          # R16
    assert p.bilgi["gap"] <= 0.05                                  # R18
    _tutarli(g, p, set_kosulu)
