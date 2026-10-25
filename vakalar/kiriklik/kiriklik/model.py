"""Optimizasyon modeli: `opt`, `opt_set` ve `kahin` kollarının transfer planı (tasarım §0, K8, K10, K19, K21).
Karar modülü: girdisi karar günü girdisi ve hücre talebi (`tahmin.ufuk_talebi` ya da kahin girdisi, aynı şema).

**Marjinal değer (K10).** Hücrenin ufuk talebi D1 ~ Poisson(mu_tam) (tam fiyat evresi) ve D2 ~ Poisson(mu_ind)
(indirim evresi), bağımsız. Hücredeki k'ıncı adet önce tam fiyatta, sonra indirimde satılır, satılmazsa
kalıntı değerindedir:

    v(k) = fiyat_tam · P(D1 ≥ k) + fiyat_ind · [P(D1 + D2 ≥ k) − P(D1 ≥ k)] + kalinti_tl · [1 − P(D1 + D2 ≥ k)]

`fiyat_tam ≥ fiyat_ind ≥ kalinti_tl` iken v azalandır; program bunu ister (artan v'de `ValueError`).

**Program (K19: sezon başına tek program).** Rota tekil (verici, alıcı) mağaza çiftidir ve bütün option'lar
üzerinden bir kez kargo öder; bu yüzden bütün option'lar tek tamsayılı programdadır.

- Alıcı hücre: uygun aday çiftin (`uygunluk.adaylar(g).uygun`) `ihtiyac_tablosu` bedenleri (K18 süzgeci orada),
  ihtiyaç n = asorti − stok. Stoğu s0 olan alıcı hücreye gelen j'inci adedin kazancı v(s0 + j), j = 1…n: son stok
  asortiyi aşmaz.
- Verici hücre: `opt`'ta option'ın `uygun` mağazalardaki her stoklu hücresi (tam setler ve alıcı olmayan adaylar
  dahil), bedeni o option'da bir alıcının ihtiyacında geçiyorsa; `verici_yalniz_kirik`'te yalnız kırık çiftlerin
  hücreleri. Stoğu s0 olan vericiden j'inci çıkışın kaybı v(s0 − j + 1), j = 1…s0.
- v azalan olduğundan alıcının kazancı içbükey, vericinin kaybı dışbükeydir: adet adet [0, 1] sürekli artım
  değişkenleri program tarafından sırayla doldurulur, ikili gerekmez.
- x[v, a, o, s] ≥ 0 tamsayı (yay); y[v, a] ikili rota, x ≤ üst_sınır(yay) · y (yay başına: toplam bağdan
  sıkı). Bir mağaza bir option'da hem alıcı hem verici olamaz: iki yönde yayı olan (option, mağaza) için ikili
  rol (giriş ≤ ihtiyaç · rol, çıkış ≤ stok · (1 − rol)). `set_kosulu`: alıcı başına ikili z, her kırık bedene
  giriş ≥ z, toplam giriş ≤ ihtiyaç · z (tamamla ya da hiç alma); z alıcının rolü de olur.
- Amaç: Σ kazanç − Σ kayıp − (toplama + yıpranma × alış) × Σ x − kargo × Σ y (TL; boş plan 0).

**Küçültme (yalnız güvenli olanlar).** (i) v(s0 + j) ≤ adet başı maliyet olan alıcı adedi düşer (o adet hiçbir
planda amacı artırmaz). `set_kosulu`'nda kırık bedenin ilk adedi düşmez (tamamlama onu zorlayabilir).
(ii) Yayın (d → r) üst sınırı, k'ıncı adedin en iyi durumunun kârlı olduğu en büyük k'dır: kazanç_r(k) −
kayıp_d(k) − maliyet > 0 (yay k adet taşıyorsa alıcıya en az k, vericiden en az k adet geçer; son adedin kazancı
kazanç_r(k)'yı aşamaz, kaybı kayıp_d(k)'nın altına inemez, o adedi geri almak amacı düşürmez). Sınırı 0 olan yay
düşer. `set_kosulu`'nda kırık bedene giden yayın sınırı en az 1'dir.
`set_kosulu`'nda bir kırık bedenine hiç yay kalmayan alıcı tamamlanamaz, programa girmez.

**Çözücü (Ruling R16).** Gerçek programda (≈ 4.000 aday rota) CBC tam programı makul sürede kapatamaz (Görev 7
raporu). İki evre: (1) bütün programın LP gevşetmesi; amacı geçerli üst sınırdır (`lp_siniri`). (2) Daraltılmış
tamsayılı program: yalnız LP'de açık rotalar (y_LP > 1e-6) ve set koşulunda yalnız LP'de açık alıcılar
(z_LP > 1e-6); kalan mağazaların rol değişkenleri yerinde. CBC seri (PuLP 3.3.2'nin CBC 2.10.3'ü; `threads`
verilmez, Blok Transfer dersi), `CBC_SECENEKLERI`, `gapRel = GAP_REL`, düğüm sınırı `DUGUM_SINIRI`, süre sınırı
yok (aynı girdi aynı plan). Daraltma optimumu kaçırabilir; kaybı `gap_lp = (lp_siniri − amaç) ÷ |lp_siniri|`
sınırlar. Durum "optimal" (daraltılmış programda gapRel içinde), "dugum_siniri" (düğüm sınırında en iyi çözüm),
"cozumsuz" (tamsayı çözüm yok: boş plan).
"""

import math
import os
import re
import tempfile
import time
from collections import defaultdict

import numpy as np
import pandas as pd
import pulp

from kiriklik import plan, sabitler, uygunluk
from kiriklik.kaynak import KararGirdisi
from kiriklik.sabitler import Paket

_TALEP_KOLONLARI = ["magaza_id", "urun_id", "mu_tam", "mu_ind", "fiyat_tam", "fiyat_ind"]
_SIRALAR = (1, 2, 3, 4, 5)

# PuLP'nin çözüm durumu: düğüm sınırında olurlu çözümle duran CBC'de de `solve()` dönüşü Optimal'dir; kanıtı
# `sol_status` taşır (Blok Transfer `cozuculer.mip`).
_DURUMLAR = {pulp.LpSolutionOptimal: "optimal", pulp.LpSolutionIntegerFeasible: "dugum_siniri"}
_LP_ESIGI = 1e-6           # LP gevşetmesinde açık sayılan rota / alıcı (R16)
# PuLP'nin taşıdığı CBC 2.10.3 (`PULP_CBC_CMD`'nin ikilisi); `PULP_CBC_CMD` PuLP 4.0 uyarısı verdiği için aynı
# ikili `COIN_CMD` ile çağrılır.
_CBC = pulp.PULP_CBC_CMD.pulp_cbc_path


def _kuyruk(mu: float, n: int) -> np.ndarray:
    """P(D ≥ k), k = 1…n, D ~ Poisson(mu) (log-uzayda olasılık, kümülatif toplam: k'da artmaz)."""
    if mu == 0.0:
        return np.zeros(n)
    i = np.arange(n)
    log_fakt = np.concatenate([[0.0], np.cumsum(np.log(np.arange(1, n)))]) if n > 0 else np.zeros(0)
    olas = np.exp(-mu + i * math.log(mu) - log_fakt)
    return np.clip(1.0 - np.cumsum(olas), 0.0, 1.0)


def marjinal_degerler(mu_tam: float, mu_ind: float, fiyat_tam: float, fiyat_ind: float, kalinti_tl: float,
                      n_max: int) -> np.ndarray:
    """k = 1…n_max için hücredeki k'ıncı adedin beklenen değeri v(k) (modül belgesi; dizin k − 1)."""
    if not (np.isfinite(mu_tam) and np.isfinite(mu_ind) and mu_tam >= 0 and mu_ind >= 0):
        raise ValueError(f"talep negatif olmayan sonlu sayı olmalı: mu_tam {mu_tam}, mu_ind {mu_ind}")
    if n_max < 0:
        raise ValueError(f"n_max negatif: {n_max}")
    s1 = _kuyruk(float(mu_tam), int(n_max))
    s12 = _kuyruk(float(mu_tam) + float(mu_ind), int(n_max))
    # v = ft·S1 + fi·(S12 − S1) + kt·(1 − S12), azalanlık kayan noktada da korunsun diye bu sırayla
    return kalinti_tl + (fiyat_tam - fiyat_ind) * s1 + (fiyat_ind - kalinti_tl) * s12


def son_sinir(log: str) -> float | None:
    """CBC 2.10.3 logundan en iyi sınır (en büyükleme, TL): boşluk kaldıysa `Upper bound:` satırı, kanıtlı
    optimumda amacın kendisi (Blok Transfer `cozuculer.mip.son_sinir`'in kopyası; o vaka salt okunur)."""
    ust = re.search(r"^Upper bound:\s+(\S+)", log, re.MULTILINE)
    if ust:
        return float(ust.group(1))
    if re.search(r"^Result - Optimal solution found\s*$", log, re.MULTILINE):
        amac = re.search(r"^Objective value:\s+(\S+)", log, re.MULTILINE)
        if amac:
            return float(amac.group(1))
    return None


class _Degerler:
    """Hücre (mağaza, option, beden) başına marjinal değerler; talep ve fiyatı bir kez okur."""

    def __init__(self, g: KararGirdisi, talep: pd.DataFrame, kalinti_orani: float):
        if not set(_TALEP_KOLONLARI) <= set(talep.columns):
            raise ValueError(f"talep sütunları {_TALEP_KOLONLARI} olmalı: {list(talep.columns)}")
        if talep.duplicated(["magaza_id", "urun_id"]).any():
            raise ValueError("talep (magaza_id, urun_id) başına tek satır olmalı")
        self.talep = {(m, u): (a, b, c, d) for m, u, a, b, c, d in talep[_TALEP_KOLONLARI].itertuples(index=False)}
        sku = g.hucre.drop_duplicates(["option_id", "beden_sira"]).set_index(["option_id", "beden_sira"])
        self.urun = sku.urun_id.to_dict()
        self.liste = sku.liste_fiyati.astype(float).to_dict()
        self.alis = sku.alis_fiyati.astype(float).to_dict()
        self.kalinti_orani = float(kalinti_orani)
        self._v: dict = {}

    def __call__(self, m: str, o: str, s: int, n: int) -> np.ndarray:
        """v(1…n) (en az n uzunlukta; önbellekli)."""
        k = (m, o, s)
        v = self._v.get(k)
        if v is None or len(v) < n:
            satir = self.talep.get((m, self.urun[(o, s)]))
            if satir is None:
                raise ValueError(f"talep eksik: mağaza {m}, ürün {self.urun[(o, s)]}")
            mt, mi, ft, fi = satir
            v = marjinal_degerler(mt, mi, ft, fi, self.kalinti_orani * self.liste[(o, s)], max(n, 1))
            if (np.diff(v) > 1e-9 * max(1.0, abs(ft))).any():
                raise ValueError(f"marjinal değer artıyor ({m}, {o}, {s}): fiyat_tam ≥ fiyat_ind ≥ kalıntı gerekir")
            self._v[k] = v
        return v[:n]


def _bilgi_bos(set_kosulu, verici_yalniz_kirik, paket, kalinti_orani, sure) -> dict:
    return {"cozum": "model", "durum": "optimal", "amac": 0.0, "lp_siniri": 0.0, "gap_lp": 0.0, "sinir": 0.0,
            "gap": 0.0, "degisken_sayisi": 0, "ikili_sayisi": 0, "kisit_sayisi": 0, "lp_degisken_sayisi": 0,
            "lp_kisit_sayisi": 0, "yay_sayisi": 0, "yay_daraltilmis": 0, "rota_aday": 0, "rota_daraltilmis": 0,
            "kurma_sn": sure, "lp_sn": 0.0, "mip_sn": 0.0, "sure_sn": sure,
            "rota_sayisi": 0, "alici_sayisi": 0, "tamamlanan_alicilar": [], "set_kosulu": set_kosulu,
            "verici_yalniz_kirik": verici_yalniz_kirik, "kalinti_orani": float(kalinti_orani),
            "paket": {"toplama_birim_tl": paket.toplama_birim_tl, "kargo_rota_tl": paket.kargo_rota_tl,
                      "yipranma_orani": paket.yipranma_orani}}


def coz(g: KararGirdisi, talep: pd.DataFrame, kalinti_orani: float, paket: Paket, *, set_kosulu: bool,
        verici_yalniz_kirik: bool, kol: str) -> plan.Plan:
    """Sezonun bütün option'ları üzerinden tek program (modül belgesi). `talep` [magaza_id, urun_id, mu_tam,
    mu_ind, fiyat_tam, fiyat_ind] alıcı ve verici hücrelerini kapsamalı (eksikse `ValueError`); kalıntı değeri
    hücrenin `kalinti_orani × liste_fiyati`'dır. `bilgi` (R16): durum ("optimal" | "dugum_siniri" | "cozumsuz"),
    amac (planın TL değeri, hareketlerden), lp_siniri, gap_lp, sinir ve gap (daraltılmış programın CBC sınırı ve
    boşluğu), değişken / ikili / kısıt sayısı (daraltılmış; lp_* bütün program), yay ve rota sayıları (rota_aday
    bütün, rota_daraltilmis), evre süreleri (kurma_sn, lp_sn, mip_sn, sure_sn), plandaki rota ve alıcı sayısı,
    tamamlanan alıcılar ([option_id, magaza_id])."""
    t0 = time.perf_counter()
    ad = uygunluk.adaylar(g)
    alici_cift = set(zip(ad.magaza_id[ad.uygun], ad.option_id[ad.uygun]))
    kirik_cift = set(zip(ad.magaza_id[ad.neden != "magaza"], ad.option_id[ad.neden != "magaza"]))
    uygun_m = set(g.magaza.magaza_id[g.magaza.uygun.astype(bool)])
    stok = g.hucre.groupby(["magaza_id", "option_id", "beden_sira"]).stok.sum()
    stok = {k: int(a) for k, a in stok.items()}
    deger = _Degerler(g, talep, kalinti_orani)

    def birim(o, s):
        return paket.toplama_birim_tl + paket.yipranma_orani * deger.alis[(o, s)]

    # alıcı hücreler: (a, o, s) → (s0, kazançlar) (küçültme i)
    alici = {}
    ih = uygunluk.ihtiyac_tablosu(g)
    for a, o, s, n in sorted(ih.itertuples(index=False, name=None)):
        if (a, o) not in alici_cift:
            continue
        s0 = stok.get((a, o, s), 0)
        kazanc = deger(a, o, s, s0 + n)[s0:s0 + n]
        adet = int((kazanc > birim(o, s)).sum())
        if set_kosulu and s0 == 0:
            adet = max(adet, 1)
        if adet > 0:
            alici[(a, o, s)] = (s0, kazanc[:adet])
    gerekli = {(o, s) for _, o, s in alici}

    # verici hücreler: (v, o, s) → (s0, kayıplar artan)
    verici = {}
    for (v, o, s), s0 in sorted(stok.items()):
        if s0 > 0 and v in uygun_m and (o, s) in gerekli and (not verici_yalniz_kirik or (v, o) in kirik_cift):
            verici[(v, o, s)] = (s0, deger(v, o, s, s0)[::-1])
    verici_os = defaultdict(list)
    for v, o, s in verici:
        verici_os[(o, s)].append(v)

    # yaylar (küçültme ii)
    yaylar = []                                                      # (v, a, o, s, üst sınır)
    for (a, o, s), (s0_r, kazanc) in alici.items():
        zorunlu = set_kosulu and s0_r == 0
        for v in verici_os[(o, s)]:
            if v == a:
                continue
            s0_d, kayip = verici[(v, o, s)]
            k = min(len(kazanc), s0_d)
            ust = int((kazanc[:k] - kayip[:k] - birim(o, s) > 0).sum())      # azalan fark: önek
            if zorunlu:
                ust = max(ust, 1)
            if ust > 0:
                yaylar.append((v, a, o, s, ust))
    if set_kosulu:
        yaylar = _tamamlanabilir(yaylar, alici, stok)
    rota_aday = len({(v, a) for v, a, *_ in yaylar})
    kurma_sn = time.perf_counter() - t0
    if not yaylar:
        return plan.bos(kol, g.sezon, _bilgi_bos(set_kosulu, verici_yalniz_kirik, paket, kalinti_orani,
                                                 time.perf_counter() - t0))

    # evre 1 (R16): bütün programın LP gevşetmesi; amacı geçerli üst sınırdır
    t1 = time.perf_counter()
    pr, _, y, z, _ = _kur(yaylar, alici, verici, stok, birim, paket, set_kosulu)
    pr.solve(pulp.COIN_CMD(path=_CBC, msg=False, mip=False))
    if pr.status != pulp.LpStatusOptimal:                            # boş plan LP'de de olurlu: olmamalı
        raise RuntimeError(f"LP gevşetmesi çözülemedi: {pulp.LpStatus[pr.status]}")
    lp_siniri = float(pulp.value(pr.objective))
    lp_degisken, lp_kisit = pr.numVariables(), pr.numConstraints()
    acik_rota = {r for r, yr in y.items() if (yr.value() or 0.0) > _LP_ESIGI}
    acik_alici = {k for k, zr in z.items() if (zr.value() or 0.0) > _LP_ESIGI}
    lp_sn = time.perf_counter() - t1

    # evre 2: daraltılmış program (LP'de açık rotalar; set koşulunda LP'de açık alıcılar)
    daralt = [yy for yy in yaylar
              if (yy[0], yy[1]) in acik_rota and (not set_kosulu or (yy[1], yy[2]) in acik_alici)]
    if set_kosulu:
        daralt = _tamamlanabilir(daralt, alici, stok)
    t2 = time.perf_counter()
    if daralt:
        pr, x, _, _, ikili = _kur(daralt, alici, verici, stok, birim, paket, set_kosulu)
        tanitici, log_yolu = tempfile.mkstemp(prefix="kiriklik_cbc_", suffix=".log")
        os.close(tanitici)
        try:
            pr.solve(pulp.COIN_CMD(path=_CBC, msg=False, gapRel=sabitler.GAP_REL, maxNodes=sabitler.DUGUM_SINIRI,
                                   options=list(sabitler.CBC_SECENEKLERI), logPath=log_yolu))
            with open(log_yolu, encoding="utf-8", errors="replace") as f:
                sinir = son_sinir(f.read())
        finally:
            os.remove(log_yolu)
        durum = _DURUMLAR.get(pr.sol_status, "cozumsuz")
        degisken, kisit = pr.numVariables(), pr.numConstraints()
    else:                                                            # LP hiçbir rotayı açmadı: boş plan en iyisi
        durum, x, ikili, degisken, kisit, sinir = "optimal", [], 0, 0, 0, 0.0
    mip_sn = time.perf_counter() - t2

    satirlar = []
    if durum != "cozumsuz":
        for i, (v, a, o, s, _) in enumerate(daralt):
            n = int(round(x[i].value() or 0.0))
            if n > 0:
                satirlar.append((o, deger.urun[(o, s)], s, v, a, n))
    if satirlar:
        h = (pd.DataFrame(satirlar, columns=plan.KOLONLAR).astype({"beden_sira": "int64", "adet": "int64"})
             .sort_values(["option_id", "alici", "verici", "beden_sira"], kind="mergesort").reset_index(drop=True))
    else:
        h = plan.bos(kol, g.sezon, {}).hareketler
    plan_amaci = _plan_amaci(h, stok, deger, birim, paket)
    gap = None
    if sinir is not None:
        gap = (sinir - plan_amaci) / max(abs(plan_amaci), 1e-9) if sinir - plan_amaci > 1e-6 else 0.0
    gap_lp = (lp_siniri - plan_amaci) / max(abs(lp_siniri), 1e-9) if lp_siniri - plan_amaci > 1e-6 else 0.0

    gelen = h.groupby(["alici", "option_id", "beden_sira"]).adet.sum().to_dict()
    tamamlanan = [[o, a] for o, a in sorted(set(zip(h.option_id, h.alici)))
                  if all(stok.get((a, o, s), 0) + gelen.get((a, o, s), 0) >= 1 for s in _SIRALAR)]
    bilgi = _bilgi_bos(set_kosulu, verici_yalniz_kirik, paket, kalinti_orani, 0.0)
    bilgi.update({
        "durum": durum, "amac": plan_amaci, "lp_siniri": lp_siniri, "gap_lp": gap_lp, "sinir": sinir, "gap": gap,
        "degisken_sayisi": degisken, "ikili_sayisi": ikili, "kisit_sayisi": kisit,
        "lp_degisken_sayisi": lp_degisken, "lp_kisit_sayisi": lp_kisit, "yay_sayisi": len(yaylar),
        "yay_daraltilmis": len(daralt), "rota_aday": rota_aday, "rota_daraltilmis": len(acik_rota),
        "rota_sayisi": len(set(zip(h.verici, h.alici))), "alici_sayisi": len(set(zip(h.option_id, h.alici))),
        "tamamlanan_alicilar": tamamlanan, "kurma_sn": kurma_sn, "lp_sn": lp_sn, "mip_sn": mip_sn,
        "sure_sn": time.perf_counter() - t0})
    return plan.Plan(kol=kol, sezon=g.sezon, hareketler=h, bilgi=bilgi)


def _tamamlanabilir(yaylar: list, alici: dict, stok: dict) -> list:
    """Set koşulu: bir kırık bedenine hiç yay kalmayan alıcının yayları çıkar (tamamlanamaz, z = 0 zorunlu)."""
    yayli = {(a, o, s) for _, a, o, s, _ in yaylar}
    tamamlanamaz = {(a, o) for a, o, _ in alici
                    if any(stok.get((a, o, s), 0) == 0 and (a, o, s) not in yayli for s in _SIRALAR)}
    return [yy for yy in yaylar if (yy[1], yy[2]) not in tamamlanamaz]


def _kur(yaylar: list, alici: dict, verici: dict, stok: dict, birim, paket: Paket, set_kosulu: bool):
    """Yaylar üzerinden program (modül belgesi): (problem, x listesi, y {rota: değişken}, z {(alıcı, option):
    değişken}, ikili sayısı)."""
    pr = pulp.LpProblem("kiriklik", pulp.LpMaximize)
    x = [pr.add_variable(f"x{i}", 0, ub, cat="Integer") for i, (*_, ub) in enumerate(yaylar)]
    giris, cikis = defaultdict(list), defaultdict(list)              # hücre → yay dizinleri
    for i, (v, a, o, s, _) in enumerate(yaylar):
        giris[(a, o, s)].append(i)
        cikis[(v, o, s)].append(i)
    ub = [yy[4] for yy in yaylar]
    amac = []
    u_say = w_say = 0
    pay_giris, pay_cikis = defaultdict(int), defaultdict(int)       # (mağaza, option) → en çok giriş / çıkış
    for k, idx in giris.items():
        _, kazanc = alici[k]
        n = min(len(kazanc), sum(ub[i] for i in idx))
        u = [pr.add_variable(f"u{u_say + j}", 0, 1) for j in range(n)]
        u_say += n
        amac += [(uj, float(kazanc[j])) for j, uj in enumerate(u)]
        pr += pulp.lpSum(x[i] for i in idx) == pulp.lpSum(u), f"ag{u_say}"
        pay_giris[(k[0], k[1])] += n
    for k, idx in cikis.items():
        s0, kayip = verici[k]
        n = min(s0, sum(ub[i] for i in idx))
        w = [pr.add_variable(f"w{w_say + j}", 0, 1) for j in range(n)]
        w_say += n
        amac += [(wj, -float(kayip[j])) for j, wj in enumerate(w)]
        pr += pulp.lpSum(x[i] for i in idx) == pulp.lpSum(w), f"vg{w_say}"
        pay_cikis[(k[0], k[1])] += n
    y = {r: pr.add_variable(f"y{j}", cat="Binary") for j, r in enumerate(sorted({(v, a) for v, a, *_ in yaylar}))}
    for i, (v, a, o, s, _) in enumerate(yaylar):
        amac.append((x[i], -birim(o, s)))
        pr += x[i] - ub[i] * y[(v, a)] <= 0, f"r{i}"
    amac += [(yr, -paket.kargo_rota_tl) for yr in y.values()]
    pr += pulp.LpAffineExpression(amac)

    giris_mo, cikis_mo = defaultdict(list), defaultdict(list)
    for (m, o, _), idx in giris.items():
        giris_mo[(m, o)] += idx
    for (m, o, _), idx in cikis.items():
        cikis_mo[(m, o)] += idx
    ikili = len(y)
    z = {}
    if set_kosulu:
        for j, (a, o) in enumerate(sorted(giris_mo)):
            z[(a, o)] = zr = pr.add_variable(f"z{j}", cat="Binary")
            for s in _SIRALAR:
                if stok.get((a, o, s), 0) == 0:
                    pr += pulp.lpSum(x[i] for i in giris[(a, o, s)]) - zr >= 0, f"zk{j}_{s}"
            pr += pulp.lpSum(x[i] for i in giris_mo[(a, o)]) - pay_giris[(a, o)] * zr <= 0, f"zt{j}"
        ikili += len(z)
    for j, mo in enumerate(sorted(set(giris_mo) & set(cikis_mo))):
        rol = z.get(mo)
        if rol is None:
            rol = pr.add_variable(f"rol{j}", cat="Binary")
            ikili += 1
            pr += pulp.lpSum(x[i] for i in giris_mo[mo]) - pay_giris[mo] * rol <= 0, f"rg{j}"
        pr += pulp.lpSum(x[i] for i in cikis_mo[mo]) + pay_cikis[mo] * rol <= pay_cikis[mo], f"rc{j}"
    return pr, x, y, z, ikili


def _plan_amaci(h: pd.DataFrame, stok: dict, deger: _Degerler, birim, paket: Paket) -> float:
    """Planın amaç değeri hareketlerden (programın artım değişkenlerinden bağımsız): Σ hücre [V(son) − V(ilk)]
    − adet başı maliyet × adet − kargo × tekil rota; V(f) = Σ_{k ≤ f} v(k)."""
    degisim = defaultdict(int)
    maliyet = 0.0
    for o, s, v, a, n in h[["option_id", "beden_sira", "verici", "alici", "adet"]].itertuples(index=False):
        degisim[(a, o, s)] += n
        degisim[(v, o, s)] -= n
        maliyet += birim(o, s) * n
    toplam = 0.0
    for (m, o, s), d in degisim.items():
        s0 = stok.get((m, o, s), 0)
        v = deger(m, o, s, max(s0, s0 + d))
        toplam += float(v[:s0 + d].sum() - v[:s0].sum())
    return toplam - maliyet - paket.kargo_rota_tl * len(set(zip(h.verici, h.alici)))
