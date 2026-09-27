"""v4 talep bileşenleri: hücre × gün için liste fiyatında beklenen talep (λ).

    λ[d, c] = statik[c] · öznitelik_devamlı[sezon(d), c]
              · g_option[d, o(c)] · mevsim[d, iklim(m(c)), altkat(o(c))]
              · magaza_gun[d, m(c)] · kanib(d)[c]

    g_option   = yaşam eğrisi × sürüklenme × sürpriz              (option × gün)
    statik     = mağaza tabanı × üst kategori × line × cinsiyet payı × genç
                 eğilim × fiyat↔gelir × beden payı × kat × yerel gürültü
                 × öznitelik etkisi[kendi sezonu, segment(m), o]  (sezonluk)
    öznitelik_devamlı = DEVAMLI option'larda o günün sezonunun etkisi
                 (sezonluklarda 1; etki statikte katlı)
    magaza_gun = gün-of-hafta × tatil/Black Friday × yıl büyümesi × turistik
                 × açılış olgunlaşması × kapalılık (0) + olay kaymaları
    kanib      = cesit.kanibalizasyon_payi (hücre penceresi dışında 0),
                 yalnız n^β/n çeşit etkisi: çekicilik 1 verilir — option'ın
                 çekiciliği (sürpriz × öznitelik) zaten g_option ve statikte,
                 grup içi paylar ona zaten orantılı (fix: sürpriz eskiden
                 kanibalizasyon payında ikinci kez sayılıyordu, λ ∝ sürpriz²)

Fiyat etkisi burada YOK (motor uygular, Görev 9/11). Online (`ONL`)
hücrelerinin statiği fiziksel hücrelerin aynı SKU'daki statik toplamından
türetilir ve (üst kategori, line) başına bir kez, referans yılda (2024)
ONL'nin λ/statik oranı fizikselinkine eşitlenecek şekilde kalibre edilir
(bkz. `_onl_kalibrasyonu`). Olay kaymalarının oranı o günün mağaza λ⁰
toplamlarından alınır (bkz. `_gunluk_magaza_toplami`): kayan pay tam
%40 (tadilat) / %30 (kapanış) olur.

**Dünya akışından çekiliş sırası (sabit; Görev 11 aynı rng ile bu sırayla
çağırır, `lambda_kur` bu sırayı uygular):**

    1. oznitelik_etkisi   taban katsayı N(0,σ) [G, K], yürüyüş [S−1, G, K]
    2. surpriz            lognormal [O]
    3. suruklenme         AR(1) başlangıç [O], yenilikler [O, W−1]
    4. tau_oynama_cek     uniform, alt kategori başına (ALT_KATEGORILER sırası)
    5. statik_taban       yerel gürültü lognormal [M, A] (ONL satırı dahil, kullanılmaz)

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §2.3, §3.3, §5.1, §5.5
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-8-brief.md

v4 hiçbir v2/v3/kök modülünü içe aktarmaz (v3 formülleri kopyalanmıştır).
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from . import sabitler
from .cesit import OUTLET_AKISI_GUN, kanibalizasyon_payi
from .magaza import _haversine_km
from .takvim import D, gun_indisi, simulasyon_takvimi

IKLIMLER = ["ılıman", "sicak_sahil", "karasal", "soguk"]
ALT_KATEGORILER = [alt for altlar in sabitler.KATEGORILER.values() for alt in altlar]
SEZON_KODLARI = list(sabitler.SEZONLAR)
MEVSIM_LINELARI = list(sabitler.MEVSIM_LINE_USSU)
N_GUN = D + sabitler.UZATMA_GUN

_OZNITELIK_ALANLARI = ["kumas", "kalip", "desen", "detay", "fiyat_segmenti"]


def _anahtar_sozlugu() -> list[str]:
    """Öznitelik "alan:değer" anahtarları, sabit sırayla (veriden değil
    sözlükten: çekiliş sayısı option kümesine bağlı olmasın)."""
    anahtarlar = []
    for alan in _OZNITELIK_ALANLARI:
        if alan == "detay":
            degerler = sorted({v for _, vs in sabitler.DETAY.values() for v in vs})
        else:
            degerler = list(sabitler.OZNITELIKLER[alan])
        anahtarlar.extend(f"{alan}:{v}" for v in degerler)
    return anahtarlar


def sezon_gun() -> np.ndarray:
    """Gün → sezon indisi (SEZON_KODLARI): ilk dalgası başlamış son sezon;
    AW22'nin ilk dalgasından önce AW22 (0)."""
    baslangic = np.array(
        [gun_indisi(s["dalgalar"][0]) for s in sabitler.SEZONLAR.values()]
    )
    assert (np.diff(baslangic) > 0).all()
    idx = np.searchsorted(baslangic, np.arange(N_GUN), side="right") - 1
    return np.maximum(idx, 0)


def _option_sezon_idx(optionlar: pd.DataFrame) -> np.ndarray:
    """Sezonluk option'ın kendi sezonu; DEVAMLI için −1."""
    harita = {k: i for i, k in enumerate(SEZON_KODLARI)}
    return optionlar["sezon_kodu"].map(harita).fillna(-1).to_numpy(dtype=int)


# ---------------------------------------------------------------------------
# Öznitelik etkisi, sürpriz, sürüklenme, yaşam eğrisi
# ---------------------------------------------------------------------------


def oznitelik_etkisi(
    rng: np.random.Generator, optionlar: pd.DataFrame, segmentler: list[str]
) -> tuple[np.ndarray, pd.DataFrame]:
    """(`etki[sezon, segment, O]`, `trend_tablosu`) — ikisi de gizli.

    log-etki = Σ_alan katsayı[sezon, segment, "alan:değer"]. Katsayılar
    AW22'de N(0, OZNITELIK_TABAN_SIGMA)'dan başlar, her sezon TREND
    hikâyesi + N(0, OZNITELIK_YURUYUS_SIGMA) rastgele yürüyüşle kayar.
    Her (sezon, segment) diliminde option'lar üzerinden ortalanır (log
    ortalama 0): trend göreli tercihi kaydırır, toplam hacmi değil.
    """
    anahtarlar = _anahtar_sozlugu()
    k_idx = {a: i for i, a in enumerate(anahtarlar)}
    S, G, K = len(SEZON_KODLARI), len(segmentler), len(anahtarlar)

    taban = rng.normal(0.0, sabitler.OZNITELIK_TABAN_SIGMA, size=(G, K))
    yuruyus = rng.normal(0.0, sabitler.OZNITELIK_YURUYUS_SIGMA, size=(S - 1, G, K))

    ss_mi = np.array([k.startswith("SS") for k in SEZON_KODLARI])
    birikimli = np.empty((S, G, K))
    birikimli[0] = taban
    for s in range(1, S):
        adim = np.zeros(K)
        for anahtar, tanim in sabitler.TREND.items():
            tur, x = tanim[0], tanim[1]
            if tur == "birikimli" or (tur == "birikimli_SS" and ss_mi[s]):
                adim[k_idx[anahtar]] += x
        birikimli[s] = birikimli[s - 1] + adim[None, :] + yuruyus[s - 1]

    katsayi = birikimli + oznitelik_duzeyi(segmentler)
    etki = etki_katsayidan(katsayi, optionlar)

    ss, gg, kk = np.meshgrid(np.arange(S), np.arange(G), np.arange(K), indexing="ij")
    trend_tablosu = pd.DataFrame(
        {
            "sezon_kodu": np.array(SEZON_KODLARI)[ss.ravel()],
            "segment": np.array(segmentler)[gg.ravel()],
            "anahtar": np.array(anahtarlar)[kk.ravel()],
            "katsayi": katsayi.ravel(),
        }
    )
    return etki, trend_tablosu


def oznitelik_duzeyi(segmentler: list[str]) -> np.ndarray:
    """`[S, G, K]` birikmeyen (düzey) trend katsayıları: "duzey_SS_AW"
    (SS'de +x, AW'de −x) ve "sabit_segment". Rastgelelik yok (Görev 10'un
    plan katsayısı da bunu kullanır)."""
    anahtarlar = _anahtar_sozlugu()
    k_idx = {a: i for i, a in enumerate(anahtarlar)}
    S, G, K = len(SEZON_KODLARI), len(segmentler), len(anahtarlar)
    ss_mi = np.array([k.startswith("SS") for k in SEZON_KODLARI])
    duzey = np.zeros((S, G, K))
    for anahtar, tanim in sabitler.TREND.items():
        tur, x = tanim[0], tanim[1]
        if tur == "duzey_SS_AW":
            duzey[:, :, k_idx[anahtar]] += np.where(ss_mi, x, -x)[:, None]
        elif tur == "sabit_segment" and tanim[2] in segmentler:
            duzey[:, segmentler.index(tanim[2]), k_idx[anahtar]] += x
    return duzey


def etki_katsayidan(katsayi: np.ndarray, optionlar: pd.DataFrame) -> np.ndarray:
    """`[S, G, K]` log katsayı → `[S, G, O]` etki: option'ın öznitelik
    anahtarlarının katsayı toplamı, her (sezon, segment) diliminde
    option'lar üzerinden log ortalaması 0'a çekilip üslenir."""
    anahtarlar = _anahtar_sozlugu()
    k_idx = {a: i for i, a in enumerate(anahtarlar)}
    X = np.zeros((len(optionlar), len(anahtarlar)))
    for alan in _OZNITELIK_ALANLARI:
        degerler = optionlar[alan].to_numpy()
        for i, v in enumerate(degerler):
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                X[i, k_idx[f"{alan}:{v}"]] = 1.0
    log_etki = katsayi @ X.T  # [S, G, O]
    log_etki -= log_etki.mean(axis=2, keepdims=True)
    return np.exp(log_etki)


def katsayi_tablodan(trend_tablosu: pd.DataFrame, segmentler: list[str]) -> np.ndarray:
    """`oznitelik_etkisi`'nin `trend_tablosu`'ndan `[S, G, K]` katsayı dizisi
    (tablo (sezon, segment, anahtar) ij sırasıyla yazılır)."""
    S, G, K = len(SEZON_KODLARI), len(segmentler), len(_anahtar_sozlugu())
    return trend_tablosu["katsayi"].to_numpy(dtype=float).reshape(S, G, K)


def surpriz(rng: np.random.Generator, optionlar: pd.DataFrame) -> np.ndarray:
    """Option sürprizi: lognormal(0, σ_line), medyan 1."""
    sigma = optionlar["line"].map(sabitler.SURPRIZ_SIGMA).to_numpy(dtype=float)
    return rng.lognormal(0.0, sigma)


def suruklenme(rng: np.random.Generator, O: int, n_gun: int = N_GUN) -> np.ndarray:
    """Option düzeyinde haftalık log AR(1) (durağan başlangıç), günlüğe
    açılmış: `[n_gun, O]`."""
    hafta_sayisi = n_gun // 7 + 1
    rho, s = sabitler.SURUKLENME_RHO, sabitler.SURUKLENME_SIGMA
    x = np.empty((O, hafta_sayisi))
    x[:, 0] = rng.normal(0.0, s / np.sqrt(1 - rho**2), size=O)
    eps = rng.normal(0.0, s, size=(O, hafta_sayisi - 1))
    for w in range(1, hafta_sayisi):
        x[:, w] = rho * x[:, w - 1] + eps[:, w - 1]
    return np.ascontiguousarray(np.exp(x)[:, np.arange(n_gun) // 7].T)


def tau_oynama_cek(rng: np.random.Generator) -> dict[str, float]:
    """Alt kategori başına τ çarpanı U(1 − oynama, 1 + oynama), bir kez."""
    o = sabitler.YASAM_TAU_OYNAMA
    return {alt: float(rng.uniform(1 - o, 1 + o)) for alt in ALT_KATEGORILER}


def yasam_egrisi(
    optionlar: pd.DataFrame, tau_oynama: dict[str, float], n_gun: int = N_GUN
) -> np.ndarray:
    """`[n_gun, O]`: sezonluk option'da (h+1)^a·exp(−h/τ) (tepe 1'e ölçekli,
    h = lansmandan beri hafta, lansmandan önce 0); DEVAMLI'da 1.

    Outlet akışı (fix round 1, controller kararı): Collection option'ın
    çıkışından sonraki OUTLET_AKISI_GUN günde (yalnız outlet mağazalarının
    outlet akışı hücreleri açıktır; normal ve ONL hücrelerinin penceresi
    çıkışta kapanır) eğri sönmeye devam etmez, outlet eğrisiyle yeniden
    başlar: OUTLET_AKISI_TALEP × (1 − OUTLET_AKISI_DUSUS · t/84), t =
    çıkıştan beri gün (tepe = 1'e göre). Böylece option düzeyinde kalır.
    """
    a = sabitler.YASAM_A
    tau = (
        sabitler.YASAM_TAU_HAFTA
        * optionlar["alt_kategori"].map(tau_oynama).to_numpy(dtype=float)
    )
    lansman = optionlar["lansman_gun"].to_numpy(dtype=float)
    sezonluk = (optionlar["sezon_kodu"] != sabitler.DEVAMLI).to_numpy()
    h = (np.arange(n_gun, dtype=float)[:, None] - lansman[None, :]) / 7.0
    tepe_h = np.maximum(a * tau - 1.0, 0.0)
    tepe = (tepe_h + 1.0) ** a * np.exp(-tepe_h / tau)
    hp = np.maximum(h, 0.0)
    deger = (hp + 1.0) ** a * np.exp(-hp / tau[None, :]) / tepe[None, :]
    deger = np.where(h < 0, 0.0, deger)
    if "line" in optionlar and "cikis_gun" in optionlar:
        collection = (optionlar["line"] == "Collection").to_numpy()
        cikis = optionlar["cikis_gun"].to_numpy(dtype=float)
        t = np.arange(n_gun, dtype=float)[:, None] - cikis[None, :]
        pencere = collection[None, :] & (t >= 0) & (t < OUTLET_AKISI_GUN)
        outlet = sabitler.OUTLET_AKISI_TALEP * (
            1.0 - sabitler.OUTLET_AKISI_DUSUS * t / OUTLET_AKISI_GUN
        )
        deger = np.where(pencere, outlet, deger)
    return np.where(sezonluk[None, :], deger, 1.0)


# ---------------------------------------------------------------------------
# Mevsim
# ---------------------------------------------------------------------------


def _mevsim_egrisi(ay: np.ndarray, tepe: float, genlik: float, genislik: float) -> np.ndarray:
    """exp(A·cos(2π·Δ/12)), Δ = tepeye dairesel uzaklık (ay) − genişlik/2
    (≥ 0; tepe çevresinde düz bölge = sezon her düzeyde `genişlik` ay
    uzar). Bir yıllık ince ızgarada ortalamaya bölünür (ortalama 1)."""

    def ham(t):
        delta = np.abs(((np.asarray(t) - tepe + 6.0) % 12.0) - 6.0)
        delta = np.maximum(delta - genislik / 2.0, 0.0)
        return np.exp(genlik * np.cos(2 * np.pi * delta / 12.0))

    izgara = 1.0 + np.arange(12_000) / 1000.0
    return ham(ay) / ham(izgara).mean()


def mevsim_tablosu_kur(ussu: float = 1.0) -> np.ndarray:
    """`[N_GUN, 4 iklim, A]` mevsim çarpanı (IKLIMLER × ALT_KATEGORILER),
    `ussu` üssüyle yumuşatılmış (line başına, MEVSIM_LINE_USSU) ve yıllık
    ortalaması 1'e yeniden normalize.

    Yaz ürünü (tepe ayı YAZ_TEPE_ARALIGI içinde) ve kış ürünü iklim
    kaymalarını ayrı alır (sabitler.IKLIM_KAYMA)."""
    tarih = pd.DatetimeIndex(simulasyon_takvimi()["tarih"])
    ay = (tarih.month + (tarih.day - 1) / tarih.days_in_month).to_numpy(dtype=float)
    tablo = np.empty((len(ay), len(IKLIMLER), len(ALT_KATEGORILER)))
    lo, hi = sabitler.YAZ_TEPE_ARALIGI
    for i, iklim in enumerate(IKLIMLER):
        k = sabitler.IKLIM_KAYMA[iklim]
        for j, alt in enumerate(ALT_KATEGORILER):
            tepe, genlik = sabitler.MEVSIM[alt]
            if lo <= tepe <= hi:
                tepe += k.get("yaz_tepe", 0.0)
                genlik *= k.get("yaz_genlik", 1.0)
                genislik = k.get("yaz_genislik", 0.0)
            else:
                tepe += k.get("kis_tepe", 0.0)
                genlik *= k.get("kis_genlik", 1.0)
                genislik = 0.0
            # mevsim^ussu = exp(ussu·A·cos)/…: genliği ölçeklemek, üs almak +
            # yıllık ortalamaya yeniden bölmekle aynıdır.
            tablo[:, i, j] = _mevsim_egrisi(ay, tepe, genlik * ussu, genislik)
    return tablo


# ---------------------------------------------------------------------------
# Mağaza-gün çarpanı ve olay kaymaları
# ---------------------------------------------------------------------------


def _magaza_gunleri(magazalar: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Mağaza başına açılış/kapanış günü (kapanış yoksa N_GUN)."""
    acilis = np.array([gun_indisi(t) for t in magazalar["acilis_tarihi"]])
    kapanis = np.array(
        [N_GUN if pd.isna(t) else gun_indisi(t) for t in magazalar["kapanis_tarihi"]]
    )
    return acilis, kapanis


def kayma_alicilari(magazalar: pd.DataFrame, olaylar: pd.DataFrame) -> dict[str, list[int]]:
    """Tadilat/kapanış mağazası → [en yakın 2 fiziksel açık mağaza, ONL]
    (magazalar satır indisleri). Açık = olay tarihinde açılmış ve
    kapanmamış; uzaklık haversine."""
    magazalar = magazalar.reset_index(drop=True)
    fiziksel = (magazalar["tip"] != "Online").to_numpy()
    onl = int(np.flatnonzero(~fiziksel)[0])
    acilis, kapanis = _magaza_gunleri(magazalar)
    lat, lon = magazalar["enlem"].to_numpy(), magazalar["boylam"].to_numpy()
    sonuc = {}
    for _, r in olaylar[olaylar["olay"].isin(["tadilat", "kapanis"])].iterrows():
        c = int(np.flatnonzero(magazalar["magaza_id"].to_numpy() == r.magaza_id)[0])
        o = gun_indisi(r.olay_tarihi)
        uygun = fiziksel & (acilis <= o) & (kapanis > o)
        uygun[c] = False
        uzaklik = np.where(uygun, _haversine_km(lat[c], lon[c], lat, lon), np.inf)
        yakin = np.argsort(uzaklik, kind="stable")[: sabitler.KAYMA_YAKIN_SAYISI]
        sonuc[r.magaza_id] = [int(y) for y in yakin] + [onl]
    return sonuc


def magaza_gun_carpani(
    magazalar: pd.DataFrame,
    gizli: pd.DataFrame,
    olaylar: pd.DataFrame,
    magaza_toplam: np.ndarray | None = None,
    kapalilik: bool = True,
) -> np.ndarray:
    """`[N_GUN, M]` mağaza-gün çarpanı.

    Fiziksel: gün-of-hafta (v3) × (Black Friday 1,8 | resmî tatil 0,6) ×
    yıl büyümesi × turistik (Haz–Eyl 1,6, diğer 0,85) × açılış olgunlaşması
    (1 − 0,5·exp(−hafta/4), yalnız simülasyonda açılanlar). ONL: gün-of-
    hafta düz (fiziksel haftalık ortalama), Black Friday 1,8, tatil 1,
    yıl büyümesi; turistik ve olgunlaşma yok.

    `kapalilik=False`: karşı-olgusal (kimse kapanmamış, kayma yok).
    `kapalilik=True`: `magaza_toplam` verilmişse olay kaymaları eklenir
    — alıcının çarpanına `pay × T_kapanan / T_alıcı × kapananın karşı-
    olgusal çarpanı` eklenir (tadilat: yakın 2 × %15 + ONL %10, tadilat
    süresince; kapanış: aynı dağılımla toplam %30, kalıcı) — sonra kapalı
    günler (açılış öncesi, kapanış sonrası, tadilat arası) 0'lanır.

    `magaza_toplam`, mağaza-gün çarpanı HARİÇ mağaza talep toplamıdır:
    `[M]` (statik taban toplamı; gün boyunca sabit oran, yaklaşık) ya da
    `[N_GUN, M]` (o günün λ⁰ toplamı; kayma tam %40/%30 — `lambda_kur` bunu
    verir, bkz. `_gunluk_magaza_toplami`).
    """
    magazalar = magazalar.reset_index(drop=True)
    takvim = simulasyon_takvimi()
    tarih = pd.DatetimeIndex(takvim["tarih"])
    M = len(magazalar)
    gunler = np.arange(N_GUN)

    hafta_gunu = np.asarray(sabitler.HAFTA_GUNU_CARPANI)[tarih.weekday]
    bf = takvim["black_friday_mi"].to_numpy(dtype=bool)
    tatil = takvim["tatil_mi"].to_numpy(dtype=bool)
    buyume = np.array(
        [sabitler.YIL_BUYUME.get(y, sabitler.YIL_BUYUME[max(sabitler.YIL_BUYUME)]) for y in tarih.year]
    )
    trafik_fiz = np.where(bf, sabitler.BLACK_FRIDAY_CARPANI, np.where(tatil, sabitler.TATIL_CARPANI, 1.0))
    gun_fiz = hafta_gunu * trafik_fiz * buyume
    gun_onl = (
        float(np.mean(sabitler.HAFTA_GUNU_CARPANI))
        * np.where(bf, sabitler.BLACK_FRIDAY_CARPANI, 1.0)
        * buyume
    )
    turistik_gun = np.where(
        np.isin(tarih.month, list(sabitler.TURISTIK_YAZ_AYLARI)),
        sabitler.TURISTIK_YAZ_CARPANI,
        sabitler.TURISTIK_KIS_CARPANI,
    )

    turistik = (
        gizli.set_index("magaza_id").loc[magazalar["magaza_id"], "turistik"].to_numpy(dtype=bool)
    )
    fiziksel = (magazalar["tip"] != "Online").to_numpy()
    acilis, kapanis = _magaza_gunleri(magazalar)

    karsi = np.empty((N_GUN, M))
    for m in range(M):
        if not fiziksel[m]:
            karsi[:, m] = gun_onl
            continue
        col = gun_fiz * (turistik_gun if turistik[m] else 1.0)
        if acilis[m] > 0:
            hafta = np.maximum(gunler - acilis[m], 0) / 7.0
            col = col * (
                1.0 - sabitler.OLGUNLASMA_DERINLIK * np.exp(-hafta / sabitler.OLGUNLASMA_HAFTA)
            )
        karsi[:, m] = col
    if not kapalilik:
        return karsi

    sonuc = karsi.copy()
    mid = magazalar["magaza_id"].to_numpy()
    tadilat_araliklari = []
    for _, r in olaylar[olaylar["olay"] == "tadilat"].iterrows():
        c = int(np.flatnonzero(mid == r.magaza_id)[0])
        tadilat_araliklari.append((c, gun_indisi(r.olay_tarihi), gun_indisi(r.bitis_tarihi)))

    if magaza_toplam is not None:
        toplam = np.asarray(magaza_toplam, dtype=float)
        if toplam.ndim == 1:
            toplam = np.broadcast_to(toplam[None, :], (N_GUN, M))
        alicilar = kayma_alicilari(magazalar, olaylar)
        for _, r in olaylar[olaylar["olay"].isin(["tadilat", "kapanis"])].iterrows():
            c = int(np.flatnonzero(mid == r.magaza_id)[0])
            bas = gun_indisi(r.olay_tarihi)
            if r.olay == "tadilat":
                bit, paylar = gun_indisi(r.bitis_tarihi), sabitler.TADILAT_KAYMA
            else:
                bit, paylar = N_GUN, sabitler.KAPANIS_KAYMA
            bas, bit = max(bas, 0), min(bit, N_GUN)
            if bas >= bit:
                continue
            for a in alicilar[r.magaza_id]:
                pay = paylar["onl"] if not fiziksel[a] else paylar["yakin"]
                t_c, t_a = toplam[bas:bit, c], toplam[bas:bit, a]
                oran = np.divide(t_c, t_a, out=np.zeros(bit - bas), where=t_a > 0)
                sonuc[bas:bit, a] += pay * oran * karsi[bas:bit, c]

    for m in range(M):
        if fiziksel[m]:
            sonuc[: max(acilis[m], 0), m] = 0.0
            sonuc[min(kapanis[m], N_GUN) :, m] = 0.0
    for c, bas, bit in tadilat_araliklari:
        sonuc[max(bas, 0) : min(bit, N_GUN), c] = 0.0
    return sonuc


# ---------------------------------------------------------------------------
# Statik taban
# ---------------------------------------------------------------------------


def _beden_tablosu() -> np.ndarray:
    """`[3, 5]` beden payı × 5 (ortalama 1): satır = beden_kayma + 1."""
    zincir = np.asarray(sabitler.BEDEN_PAYLARI_ZINCIR)
    k = len(zincir)
    konum = np.arange(k + 2, dtype=float)  # 0 ve k+1 kenar
    genis = np.concatenate([[sabitler.BEDEN_KENAR], zincir, [sabitler.BEDEN_KENAR]])
    tablo = np.empty((3, k))
    for i, kayma in enumerate((-1, 0, 1)):
        x = np.arange(1, k + 1) - kayma * sabitler.BEDEN_KAYMA_ADIM
        p = np.interp(x, konum, genis)
        tablo[i] = p / p.sum() * k
    return tablo


def _segment_idx(gizli_hizali: pd.DataFrame, segmentler: list[str]) -> np.ndarray:
    """Mağaza segment indisi; listede olmayan (ONL "online") = len(segmentler)."""
    harita = {s: i for i, s in enumerate(segmentler)}
    return gizli_hizali["segment"].map(harita).fillna(len(segmentler)).to_numpy(dtype=int)


def statik_taban(
    rng: np.random.Generator,
    cesit: pd.DataFrame,
    magazalar: pd.DataFrame,
    gizli: pd.DataFrame,
    urunler: pd.DataFrame,
    optionlar: pd.DataFrame,
    etki: np.ndarray,
    yerel: np.ndarray | None = None,
) -> np.ndarray:
    """`[C]` hücre başına statik taban (ONL dahil, ONL kalibrasyonu hariç).

    Fiziksel: mağaza tabanı × üst kategori × line × cinsiyet payı × genç
    eğilim × fiyat↔gelir × beden payı × kat × yerel gürültü (mağaza × alt
    kategori lognormal σ 0,15) × öznitelik etkisi (sezonluk option'da kendi
    sezonu ve mağazanın segmenti; DEVAMLI'da 1 — o günün sezonu Lambda'da
    uygulanır). ONL: ONLINE_PAY/(1 − ONLINE_PAY) × aynı SKU'nun fiziksel
    statik toplamı × (Basic/NOS 1,25).

    Tek çekiliş: yerel gürültü `[M, A]` (çekiliş sırası 5). `yerel`
    verilirse çekiliş yapılmaz, verilen `[M, A]` kullanılır (Görev 10'un
    plan λ'sı: yerel gürültüyü bilmez, 1 verir; `rng` o zaman None olabilir).
    """
    magazalar = magazalar.reset_index(drop=True)
    urunler = urunler.reset_index(drop=True)
    optionlar = optionlar.reset_index(drop=True)
    M, A = len(magazalar), len(ALT_KATEGORILER)
    if yerel is None:
        yerel = rng.lognormal(0.0, sabitler.YEREL_GURULTU_SIGMA, size=(M, A))

    g = gizli.set_index("magaza_id").loc[magazalar["magaza_id"]].reset_index()
    m_c = cesit["magaza_idx"].to_numpy()
    s_c = cesit["sku_idx"].to_numpy()
    o_c = cesit["option_idx"].to_numpy()
    fiz_m = (magazalar["tip"] != "Online").to_numpy()
    fiz = fiz_m[m_c]

    # --- mağaza düzeyi -----------------------------------------------------
    tip = magazalar["tip"].to_numpy()
    kapasite = magazalar["kapasite"].to_numpy(dtype=float)
    magaza_taban = np.where(
        fiz_m,
        sabitler.TABAN_OLCEK
        * (kapasite / sabitler.KAPASITE_REFERANS) ** sabitler.KAPASITE_USSU
        * np.array([sabitler.TIP_TALEP_CARPANI.get(t, 0.0) for t in tip])
        * np.exp(sabitler.MAGAZA_GURULTU_SIGMA * g["yerel_gurultu"].to_numpy(dtype=float)),
        0.0,
    )
    kadin = g["kadin_payi"].to_numpy(dtype=float)
    genc = g["genc_egilim"].to_numpy(dtype=float)
    kayma = g["beden_kayma"].to_numpy(dtype=int)
    gelir = g["gelir"].to_numpy()
    cok_katli = magazalar["kat_sayisi"].to_numpy() > 1
    seg_m = _segment_idx(g, sabitler.SEGMENTLER)

    # --- SKU düzeyi --------------------------------------------------------
    cins = urunler["cinsiyet"].to_numpy()[s_c]
    ust = urunler["ust_kategori"].to_numpy()[s_c]
    line = urunler["line"].to_numpy()[s_c]
    fs = urunler["fiyat_segmenti"].to_numpy()[s_c]
    kalip = urunler["kalip"].to_numpy()[s_c]
    beden_sira = urunler["beden_sira"].to_numpy(dtype=int)[s_c]
    beden_sayisi = urunler.groupby("option_id")["beden_sira"].transform("size").to_numpy()[s_c]
    alt_idx = pd.Series(urunler["alt_kategori"].to_numpy()[s_c]).map(
        {a: i for i, a in enumerate(ALT_KATEGORILER)}
    ).to_numpy(dtype=int)

    k_c = kadin[m_c]
    cins_c = np.select([cins == "Kadın", cins == "Erkek"], [2 * k_c, 2 * (1 - k_c)], default=1.0)
    genc_c = np.exp(
        sabitler.GENC_ETKI_KATSAYISI
        * (genc[m_c] - 0.5)
        * pd.Series(kalip).map(sabitler.GENC_KALIP_SKORU).fillna(0.0).to_numpy()
    )
    fg_c = np.array(
        [sabitler.FIYAT_GELIR_TALEP[f][gl] for f, gl in zip(fs, gelir[m_c])], dtype=float
    )
    beden_c = np.where(
        beden_sayisi > 1,
        _beden_tablosu()[np.clip(kayma[m_c], -1, 1) + 1, np.clip(beden_sira, 1, 5) - 1],
        1.0,
    )
    kat_c = np.where(cok_katli[m_c] & (cins == "Erkek"), sabitler.KAT_ERKEK_CARPANI, 1.0)
    ust_c = pd.Series(ust).map(sabitler.UST_KATEGORI_TABAN).to_numpy(dtype=float)
    line_c = pd.Series(line).map(sabitler.LINE_TALEP_CARPANI).to_numpy(dtype=float)

    sezon_o = _option_sezon_idx(optionlar)[o_c]
    seg_c = seg_m[m_c]
    etki_c = np.ones(len(cesit))
    secim = fiz & (sezon_o >= 0)
    etki_c[secim] = etki[sezon_o[secim], seg_c[secim], o_c[secim]]

    statik = (
        magaza_taban[m_c] * ust_c * line_c * cins_c * genc_c * fg_c * beden_c * kat_c
        * yerel[m_c, alt_idx] * etki_c
    )
    statik = np.where(fiz, statik, 0.0)

    # --- ONL: ulusal toplamın kategoriye göre payı ---------------------------
    sku_toplam = np.bincount(s_c[fiz], weights=statik[fiz], minlength=len(urunler))
    p = pd.Series(ust).map(sabitler.ONLINE_PAY).to_numpy(dtype=float)
    basic = np.isin(line, ["Basic", "NOS"])
    onl_statik = p / (1 - p) * sku_toplam[s_c] * np.where(basic, sabitler.ONLINE_BASIC_CARPANI, 1.0)
    return np.where(fiz, statik, onl_statik)


# ---------------------------------------------------------------------------
# Montaj yardımcıları (Görev 10'un plan λ'sı da kullanır)
# ---------------------------------------------------------------------------


def _zincir_ortalama_etki(etki: np.ndarray, gizli: pd.DataFrame) -> np.ndarray:
    """`[S, O]`: segmentler üzerinden fiziksel mağaza sayısıyla ağırlıklı
    ortalama öznitelik etkisi (zincir ortalaması; ONL de bunu kullanır)."""
    seg = gizli.loc[gizli["segment"] != "online", "segment"]
    sayim = seg.value_counts()
    w = np.array([sayim.get(s, 0) for s in sabitler.SEGMENTLER], dtype=float)
    w = w / w.sum()
    return np.einsum("g,sgo->so", w, etki)


def mevsim_ve_iklim_slotu(
    magazalar: pd.DataFrame, gizli: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray]:
    """(`[N_GUN, 5, A·L]` mevsim tablosu, `[M]` iklim slotu). Slot 0–3
    IKLIMLER, 4 = fiziksel mağaza sayısıyla ağırlıklı zincir ortalaması
    (ONL'nin slotu; plan λ'sı bütün mağazalara bunu verir). Line üssü
    (MEVSIM_LINE_USSU) her slotta korunur."""
    magazalar = magazalar.reset_index(drop=True)
    g = gizli.set_index("magaza_id").loc[magazalar["magaza_id"]].reset_index()
    fiz_m = (magazalar["tip"] != "Online").to_numpy()
    iklim_sayim = g.loc[fiz_m, "iklim"].value_counts()
    w_iklim = np.array([iklim_sayim.get(i, 0) for i in IKLIMLER], dtype=float)
    # [N, 4, A, L] → ONL zincir ortalaması eklenir → [N, 5, A·L]
    mevsim4 = np.stack(
        [mevsim_tablosu_kur(sabitler.MEVSIM_LINE_USSU[ln]) for ln in MEVSIM_LINELARI], axis=-1
    )
    mevsim_onl = np.einsum("i,dial->dal", w_iklim / w_iklim.sum(), mevsim4)
    mevsim5 = np.ascontiguousarray(
        np.concatenate([mevsim4, mevsim_onl[:, None]], axis=1).reshape(N_GUN, 5, -1)
    )
    iklim_slot_m = np.where(
        fiz_m, g["iklim"].map({i: k for k, i in enumerate(IKLIMLER)}).fillna(0).to_numpy(), 4
    ).astype(np.intp)
    return mevsim5, iklim_slot_m


def option_mevsim_idx(optionlar: pd.DataFrame) -> np.ndarray:
    """`[O]` mevsim tablosunun son ekseninde option'ın sütunu: alt kategori · L + line."""
    alt_o = optionlar["alt_kategori"].map({a: i for i, a in enumerate(ALT_KATEGORILER)}).to_numpy(dtype=np.intp)
    line_o = optionlar["line"].map({ln: i for i, ln in enumerate(MEVSIM_LINELARI)}).to_numpy(dtype=np.intp)
    return (alt_o * len(MEVSIM_LINELARI) + line_o).astype(np.intp)


def devamli_etki_kur(
    etki: np.ndarray,
    magazalar: pd.DataFrame,
    gizli: pd.DataFrame,
    optionlar: pd.DataFrame,
    cesit_hucre: pd.DataFrame,
) -> np.ndarray:
    """`[S, C]`: DEVAMLI hücrelerde sezonun öznitelik etkisi (fiziksel:
    mağazanın segmenti; ONL: zincir ortalaması), diğer hücrelerde 1."""
    magazalar = magazalar.reset_index(drop=True)
    g = gizli.set_index("magaza_id").loc[magazalar["magaza_id"]].reset_index()
    m_c = cesit_hucre["magaza_idx"].to_numpy().astype(np.intp)
    o_c = cesit_hucre["option_idx"].to_numpy().astype(np.intp)
    etki_ort = _zincir_ortalama_etki(etki, gizli)
    etki_gen = np.concatenate([etki, etki_ort[:, None, :]], axis=1)  # [S, G+1, O]
    seg_c = _segment_idx(g, list(sabitler.SEGMENTLER))[m_c]
    devamli_c = (_option_sezon_idx(optionlar) < 0)[o_c]
    devamli_etki = np.ones((len(SEZON_KODLARI), len(m_c)))
    devamli_etki[:, devamli_c] = etki_gen[:, seg_c[devamli_c], o_c[devamli_c]]
    return devamli_etki


# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------


@dataclass
class Lambda:
    """Önceden hesaplanmış λ bileşenleri; `gun(d)` vektörel `[C]` float64.

    `gun(d)` önce küçük bir `[M, O]` tablo kurar (mağaza-gün × option-gün ×
    iklim-mevsim; ~160 bin eleman), sonra hücrelere tek bir toplama
    (`hucre_mo = m·O + o`) ile dağıtır — üç ayrı hücre düzeyi toplama
    yerine bir tane (tam ölçekte hız hedefi < 15 ms/gün)."""

    statik: np.ndarray          # [C] statik taban (ONL kalibre)
    statik_sezon: np.ndarray    # [S, C] statik × DEVAMLI hücrede sezonun öznitelik etkisi
    hucre_option: np.ndarray    # [C]
    hucre_magaza: np.ndarray    # [C]
    magaza_iklim: np.ndarray    # [M] mevsim slotu (0–3 IKLIMLER, 4 = ONL)
    option_mevsim: np.ndarray   # [O] alt kategori · L + line (MEVSIM_LINELARI)
    g_option: np.ndarray        # [N_GUN, O] yaşam × sürüklenme × sürpriz
    mevsim_tablosu: np.ndarray  # [N_GUN, 5, A] 4 iklim + ONL zincir ortalaması
    magaza_gun: np.ndarray      # [N_GUN, M]
    sezon_gun: np.ndarray       # [N_GUN] sezon indisi
    kanib: Callable[[int], np.ndarray]

    def __post_init__(self):
        O = self.g_option.shape[1]
        self.hucre_mo = (self.hucre_magaza.astype(np.intp) * O + self.hucre_option).astype(np.intp)

    @property
    def gun_sayisi(self) -> int:
        return self.g_option.shape[0]

    def gun(self, d: int) -> np.ndarray:
        """Gün d'de liste fiyatında beklenen talep `[C]` (fiyat etkisi yok)."""
        tablo = self.mevsim_tablosu[d].take(self.magaza_iklim, axis=0).take(self.option_mevsim, axis=1)
        tablo *= self.g_option[d][None, :]
        tablo *= self.magaza_gun[d][:, None]
        v = tablo.ravel().take(self.hucre_mo)
        v *= self.statik_sezon[self.sezon_gun[d]]
        v *= self.kanib(d)
        return v


def _onl_kalibrasyonu(
    lam: Lambda, onl_hucre: np.ndarray, grup_c: np.ndarray
) -> dict[tuple[str, str], float]:
    """(Üst kategori, line) başına ONL statik düzeltmesi: referans yılda
    (2024, 3 günde bir) ONL'nin λ/statik oranı fizikselinkine eşitlenir.
    Böylece ONL'nin λ payı statik payına (≈ ONLINE_PAY, Basic/NOS ×1,25)
    oturur; kanibalizasyonun ONL'de (çok option, küçük n^β/n), outlet
    akışı hücrelerinin (sönmüş yaşam eğrisi) ve gün çarpanlarının kanallar
    arasında farklı olmasının hacme etkisi nötrlenir. `grup_c` hücre
    başına (üst kategori, line) etiketidir."""
    bas, bit = gun_indisi("2024-01-01"), gun_indisi("2025-01-01")
    kod, gruplar = pd.factorize(pd.Series(list(map(tuple, grup_c))))
    anahtar = kod * 2 + onl_hucre.astype(int)
    n = 2 * len(gruplar)
    lam_top = np.zeros(n)
    for d in range(bas, bit, 3):
        lam_top += np.bincount(anahtar, weights=lam.gun(d), minlength=n)
    st_top = np.bincount(anahtar, weights=lam.statik, minlength=n)
    sonuc = {}
    for i, grup in enumerate(gruplar):
        fiz_oran = lam_top[2 * i] / st_top[2 * i] if st_top[2 * i] > 0 else 0.0
        onl_oran = lam_top[2 * i + 1] / st_top[2 * i + 1] if st_top[2 * i + 1] > 0 else 0.0
        sonuc[tuple(grup)] = float(fiz_oran / onl_oran) if fiz_oran > 0 and onl_oran > 0 else 1.0
    return sonuc


def _gunluk_magaza_toplami(
    lam: Lambda, magazalar: pd.DataFrame, olaylar: pd.DataFrame
) -> np.ndarray:
    """`[N_GUN, M]` olay kaymalarının oranı için mağaza başına günlük λ⁰
    toplamı (mağaza-gün çarpanı hariç: çarpan 1 alınır). Yalnız olay
    (tadilat/kapanış) mağazaları ve alıcıları, yalnız kayma günlerinde
    hesaplanır (hücre alt kümesiyle); diğer girdiler 0 kalır.

    Controller kararı statik toplam oranını söylüyordu; o oran günün
    mevsim/yaşam/çeşit karışımını bilmediği için kayan pay %40 yerine
    %36–56 çıkıyordu (Görev 8 raporu). Günlük λ⁰ oranı kaymayı tam yapar."""
    magazalar = magazalar.reset_index(drop=True)
    M = len(magazalar)
    sonuc = np.zeros((N_GUN, M))
    olay = olaylar[olaylar["olay"].isin(["tadilat", "kapanis"])]
    if olay.empty:
        return sonuc
    alicilar = kayma_alicilari(magazalar, olaylar)
    mid = magazalar["magaza_id"].to_numpy()
    ilgili: set[int] = set()
    gun_maske = np.zeros(N_GUN, dtype=bool)
    for _, r in olay.iterrows():
        ilgili.add(int(np.flatnonzero(mid == r.magaza_id)[0]))
        ilgili.update(alicilar[r.magaza_id])
        bas = max(gun_indisi(r.olay_tarihi), 0)
        bit = gun_indisi(r.bitis_tarihi) if r.olay == "tadilat" else N_GUN
        gun_maske[bas : min(bit, N_GUN)] = True
    idx = np.flatnonzero(np.isin(lam.hucre_magaza, sorted(ilgili)))
    tam_kanib = lam.kanib
    alt = Lambda(
        statik=lam.statik[idx],
        statik_sezon=np.ascontiguousarray(lam.statik_sezon[:, idx]),
        hucre_option=lam.hucre_option[idx],
        hucre_magaza=lam.hucre_magaza[idx],
        magaza_iklim=lam.magaza_iklim,
        option_mevsim=lam.option_mevsim,
        g_option=lam.g_option,
        mevsim_tablosu=lam.mevsim_tablosu,
        magaza_gun=np.ones((N_GUN, M)),
        sezon_gun=lam.sezon_gun,
        kanib=lambda d: tam_kanib(d).take(idx),
    )
    for d in np.flatnonzero(gun_maske):
        sonuc[d] = np.bincount(alt.hucre_magaza, weights=alt.gun(int(d)), minlength=M)
    return sonuc


def lambda_kur(
    rng: np.random.Generator,
    magazalar: pd.DataFrame,
    gizli: pd.DataFrame,
    olaylar: pd.DataFrame,
    optionlar: pd.DataFrame,
    urunler: pd.DataFrame,
    cesit_hucre: pd.DataFrame,
) -> tuple[Lambda, dict]:
    """λ'yı kurar; (Lambda, gizli gerçek sözlüğü). Çekiliş sırası modül
    başındaki listedir (1–5); geri kalanı deterministik."""
    magazalar = magazalar.reset_index(drop=True)
    optionlar = optionlar.reset_index(drop=True)
    urunler = urunler.reset_index(drop=True)
    segmentler = list(sabitler.SEGMENTLER)
    O = len(optionlar)

    # --- Çekilişler (sıra sabit) ------------------------------------------
    etki, trend_tablosu = oznitelik_etkisi(rng, optionlar, segmentler)   # 1
    surpriz_o = surpriz(rng, optionlar)                                    # 2
    surukl = suruklenme(rng, O)                                            # 3
    tau_oyn = tau_oynama_cek(rng)                                          # 4
    statik = statik_taban(rng, cesit_hucre, magazalar, gizli, urunler, optionlar, etki)  # 5

    # --- Deterministik parçalar -------------------------------------------
    g_option = yasam_egrisi(optionlar, tau_oyn) * surukl * surpriz_o[None, :]

    fiz_m = (magazalar["tip"] != "Online").to_numpy()
    m_c = cesit_hucre["magaza_idx"].to_numpy().astype(np.intp)
    o_c = cesit_hucre["option_idx"].to_numpy().astype(np.intp)
    fiz_c = fiz_m[m_c]
    mevsim5, iklim_slot_m = mevsim_ve_iklim_slotu(magazalar, gizli)
    mevsim_o = option_mevsim_idx(optionlar)

    kanib = kanibalizasyon_payi(cesit_hucre, optionlar, np.ones(O))
    devamli_etki = devamli_etki_kur(etki, magazalar, gizli, optionlar, cesit_hucre)

    sezon_g = sezon_gun()
    mg_kaymasiz = magaza_gun_carpani(magazalar, gizli, olaylar, magaza_toplam=None)

    def _kur(statik_v, mg):
        return Lambda(
            statik=statik_v,
            statik_sezon=statik_v[None, :] * devamli_etki,
            hucre_option=o_c,
            hucre_magaza=m_c,
            magaza_iklim=iklim_slot_m,
            option_mevsim=mevsim_o,
            g_option=g_option,
            mevsim_tablosu=mevsim5,
            magaza_gun=mg,
            sezon_gun=sezon_g,
            kanib=kanib,
        )

    # --- ONL kalibrasyonu (kaymasız), sonra kaymalı mağaza-gün ------------
    grup_o = list(zip(optionlar["ust_kategori"], optionlar["line"]))
    grup_c = np.array(grup_o, dtype=object)[o_c]
    kalib = _onl_kalibrasyonu(_kur(statik, mg_kaymasiz), ~fiz_c, grup_c)
    kalib_o = np.array([kalib.get(gr, 1.0) for gr in grup_o])
    duzeltme = np.where(fiz_c, 1.0, kalib_o[o_c])
    statik = statik * duzeltme

    statik_toplam = np.bincount(m_c, weights=statik, minlength=len(magazalar))
    gunluk_toplam = _gunluk_magaza_toplami(_kur(statik, mg_kaymasiz), magazalar, olaylar)
    mg = magaza_gun_carpani(magazalar, gizli, olaylar, magaza_toplam=gunluk_toplam)
    lam = _kur(statik, mg)

    gizli_talep = {
        "oznitelik_etkisi": etki,
        "trend_tablosu": trend_tablosu,
        "surpriz": surpriz_o,
        "suruklenme": surukl,
        "tau_oynama": tau_oyn,
        "onl_kalibrasyonu": kalib,
        "statik_toplam": statik_toplam,
        "gunluk_magaza_toplami": gunluk_toplam,
        "kayma_alicilari": kayma_alicilari(magazalar, olaylar),
    }
    return lam, gizli_talep
