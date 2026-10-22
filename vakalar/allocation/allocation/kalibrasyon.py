"""Kalibrasyon (spec §0/12, §4.1): SS24'te, sızıntısız, kolların ayarlarını seçer; oyun sezonuna
(SS25) hiç bakmaz. Görev 8'in ızgarası seçimleri `cikti/kalibrasyon.json`'dan okur.

    c = kosusuz(tablolar, w)              # koşusuz: en_az, LightGBM parametreleri, belirsizlik ölçüsü
    s = simulasyon(kos_fn, c)             # 7 TAM koşu: kapsama tavanı açık/kapalı, eğri dikliği γ
    yaz(c, s, CIKTI / "kalibrasyon.json"); d = oku(...)

**Koşu enjekte edilir.** Bu modül bir karar modülüdür: motoru içe aktarmaz, gizli gerçeği
okumaz (`tests/test_sizinti.py`; DM Ruling R5 kalıbı). Koşuyu ve ölçümü `kos_fn(ad, tanim) ->
dict` yapar (`tanim`: `KalKol`); dönen sözlükte en az `bulunabilirlik` ve
`sezon_sonu_kalan_yuzde` vardır. Gerçek koşucu `oyun.kalibrasyon_kosucusu`
(`python -m allocation.oyun kalibrasyon`); kolu `kol_kur` ile kurar.

**Koşusuz** (`kosusuz`). Karar günü = SS24 Collection'ın en erken ilk dağıtım sevki
(`karar_gunu`; yayımlanan `sevkiyat`, 2024-02-09): o gün kapanmış tek Collection sezonu SS23'tür
(`ogrenme.kapanmis_sezonlar`). Öğrenme tablosu `ogrenme.ogrenme_tablosu(tablolar, w, karar)`
(yalnız SS23); gerçek pay `erken_gercek` ile SS24'ün yayımlanan verisinden (sansür düzeltmeli ilk
6 hafta talebi, `ogrenme.erken_talep`; matrisler erken kesimin ertesi gününe dek). Ölçü
`pay_wape` (aşağıda), option'lar ilk alımla ağırlıklı:

    benzer       `benzer.ogren(tablo, en_az, mevsim="SS")`, en_az ∈ `EN_AZ_IZGARASI`
    tahmin       `Tahminci.egit` num_leaves ∈ `NUM_LEAVES` × min_child_samples ∈
                 `MIN_CHILD_SAMPLES` (learning_rate, n_estimators `VARSAYILAN`'dan)
    kaynak       seçilmiş benzer ile seçilmiş tahminden WAPE'si küçük olan
    belirsizlik  `BELIRSIZLIK_OLCULERI`'nin her biri option başına; kaynağın option WAPE'siyle
                 Spearman sıra korelasyonu en yüksek olan

Her ızgarada eşitlikte ilk aday (ızgara sırası). Lumoda'nın gerçekleşen payı ve eşit pay
yalnız bağlam için tabloya girer (`asama = "taban"`). Tahmin ve ölçüler, kolun karar anında
göreceği aday kümesinin açık alanlardan yaklaşığıyla (`aday_yaklasik`) hesaplanır; WAPE gerçeği
gözlenen mağazalarda.

**Pay WAPE** (`pay_wape`, `option_wape`). Option başına, gerçeği gözlenen (talebi tanımlı)
mağazalarda: pay ve talep bu kümede 1'e normalleşir, WAPE = Σ|pay − gerçek pay| ÷ 2 (0 = aynı
paylar, 1 = ayrık). Payı olmayan mağaza 0 pay; kümede hiç pay yoksa pay eşit; toplam talebi 0
olan option dışarıda. `pay_wape` option'ların ağırlıklı ortalamasıdır (ağırlık yoksa eşit).

**Belirsizlik ölçüleri** (`BELIRSIZLIK_OLCULERI`; büyük = belirsiz):

    benzer_dk               `benzer.belirsizlik`: benzer option'ların mağaza göreli hızlarının
                            değişim katsayısı (mutlak öngörüyle ağırlıklı)
    benzer_duzey            endeksin seçtiği hiyerarşi düzeyi (genel düzey = az benzer)
    benzer_tahmin_ayrisma   benzer ile tahmin paylarının toplam değişim uzaklığı (iki modelin
                            anlaşmazlığı)

**Tutma eğrisi** (`tutma_egrisi`): `t_o = clip(t̄ · (u_o / ū)^γ, 0, 2t̄)`, sonra ağırlıklı ortalama
t̄'ye çarpımsal ölçeklenip yeniden kırpılır (yakınsayana dek). ū ağırlıklı ortalama, ağırlık
option'ın ilk alımı (gönderilebilir üst sınır U ilk alımın %70'iyle orantılıdır; U karar anında
depoya bağlı olduğundan önceden bilinmez); ölçüsü olmayan option ū alır (t = t̄).

**Simülasyon** (`simulasyon`; SS24 penceresi, yol 0, `Ayar.sezon = KAL_SEZONU`; kollar SS25'te
Lumoda). Önce `lumoda` (referans; yayımlanan dünya, önbellekli, seçime girmez), sonra:

    1. benzer ve tahmin, tavanlı ve tavansız, t = 0 (4 koşu)
    2. en iyisi (`secim`): tavan = onun tavanı, belirsizliğin tabanı = onun kolu
    3. belirsizlik (t̄ = `BELIRSIZLIK_TBAR`), γ ∈ `GAMMA_IZGARASI` (3 koşu); en iyisinin γ'sı

`secim`: sezon boyu bulunabilirliği en yüksek olanın `ESIK_PUAN` (0,3) puandan az gerisindekiler
arasında sezon sonu kalanı en düşük olan (eşitlikte ilk). Ölçütlerin tanımı `olcutler` modülünde
(`bulunabilirlik`, `sezon_sonu_kalan_yuzde`; oyunun ölçütleriyle aynı tanım).
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from allocation import benzer, kaynak, ogrenme, sabitler, tahmin
from allocation.paylastir import aday_maskesi
from allocation.politika import Ayar, BelirsizlikKol, BenzerKol, TahminKol

DOSYA = sabitler.CIKTI / "kalibrasyon.json"

# Ruling R24: ilk ızgaranın ({3, 5, 10}, {15, 31} × {20, 50}) seçimleri uçtaydı; genişletildi
# ({3..40}, {15, 31, 63} × {20..200}); en_az 40 ve num_leaves 63 yine uçta çıktı, o yönde bir
# kez daha uzatıldı (80, 127) ve orada durdu
EN_AZ_IZGARASI = (3, 5, 10, 20, 40, 80)
NUM_LEAVES = (15, 31, 63, 127)
MIN_CHILD_SAMPLES = (20, 50, 100, 200)
GAMMA_IZGARASI = (0.5, 1.0, 2.0)
BELIRSIZLIK_OLCULERI = ("benzer_dk", "benzer_duzey", "benzer_tahmin_ayrisma")
ESIK_PUAN = 0.3            # seçimde bulunabilirlik eşitliği (puan)
GEREKEN_OLCUTLER = ("bulunabilirlik", "sezon_sonu_kalan_yuzde")
_YAKINSAMA = 1e-12
_EN_COK_TUR = 200


# ---------------------------------------------------------------------------
# Pay WAPE ve sıra korelasyonu
# ---------------------------------------------------------------------------


def option_wape(pay: pd.DataFrame, gercek: pd.DataFrame) -> pd.Series:
    """option -> WAPE (modül notu). `pay`: `option, magaza, pay`; `gercek`: `option, magaza,
    talep` (NaN = gözlem yok). Satırı olmayan / toplam talebi 0 olan option dönüşte yok."""
    g = gercek.loc[gercek["talep"].notna().to_numpy(), ["option", "magaza", "talep"]]
    df = g.merge(pay[["option", "magaza", "pay"]], on=["option", "magaza"], how="left", validate="1:1")
    df["pay"] = df["pay"].fillna(0.0).astype(float)
    grup = df.groupby("option")
    df = df.assign(tt=grup["talep"].transform("sum"), tp=grup["pay"].transform("sum"),
                   n=grup["talep"].transform("size"))
    df = df[(df["tt"] > 0).to_numpy()]
    p = np.where(df["tp"] > 0, df["pay"] / df["tp"].where(df["tp"] > 0, 1.0), 1.0 / df["n"])
    fark = pd.Series(np.abs(p - df["talep"] / df["tt"]), index=df.index)
    return (fark.groupby(df["option"]).sum() / 2.0).rename("wape")


def pay_wape(pay: pd.DataFrame, gercek: pd.DataFrame, agirlik: Mapping | pd.Series | None = None) -> float:
    """Option WAPE'lerinin ağırlıklı ortalaması (`agirlik`: option -> ağırlık; yoksa eşit)."""
    w = option_wape(pay, gercek)
    if w.empty:
        return float("nan")
    a = np.ones(len(w)) if agirlik is None else pd.Series(agirlik).reindex(w.index).to_numpy(dtype=float)
    if not np.isfinite(a).all() or a.sum() <= 0:
        raise ValueError("pay_wape: ağırlık her option'da sonlu ve toplamı pozitif olmalı")
    return float((w.to_numpy() * a).sum() / a.sum())


def spearman(x, y) -> float:
    """Spearman sıra korelasyonu (eşit değerlere ortalama sıra); ikisi de sonlu olan çiftlerde.
    İki çiftten az ya da sabit dizide NaN."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    var = np.isfinite(x) & np.isfinite(y)
    if var.sum() < 2:
        return float("nan")
    rx = pd.Series(x[var]).rank().to_numpy()
    ry = pd.Series(y[var]).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


# ---------------------------------------------------------------------------
# Tutma eğrisi ve seçim
# ---------------------------------------------------------------------------


def tutma_egrisi(u: pd.Series, agirlik: pd.Series, gamma: float,
                 tbar: float = sabitler.BELIRSIZLIK_TBAR) -> pd.Series:
    """option -> t_o (modül notu; `u`'nun indeksiyle). `agirlik` `u`'nun her option'ını kapsar."""
    a = pd.Series(agirlik).reindex(u.index).to_numpy(dtype=float)
    if not np.isfinite(a).all() or (a < 0).any() or a.sum() <= 0:
        raise ValueError("tutma_egrisi: ağırlık her option'da sonlu, eksi olmayan, toplamı pozitif olmalı")
    if not 0.0 < tbar < 0.5:
        raise ValueError(f"tbar (0, 0,5) aralığında olmalı (2t̄ < 1): {tbar}")
    deger = u.to_numpy(dtype=float)
    var = np.isfinite(deger)
    if (deger[var] < 0).any():
        raise ValueError("tutma_egrisi: belirsizlik eksi olamaz")
    ort = float((deger[var] * a[var]).sum() / a[var].sum()) if var.any() and a[var].sum() > 0 else 0.0
    if float(gamma) == 0.0 or ort <= 0:
        return pd.Series(tbar, index=u.index, dtype=float)
    oran = np.where(var, deger / ort, 1.0)
    t = np.clip(tbar * oran ** float(gamma), 0.0, 2 * tbar)
    for _ in range(_EN_COK_TUR):
        m = float((t * a).sum() / a.sum())
        if abs(m - tbar) < _YAKINSAMA:
            break
        if m <= 0:
            raise ValueError("tutma_egrisi: bütün t sıfır, ortalama t̄'ye ölçeklenemez")
        t = np.clip(t * tbar / m, 0.0, 2 * tbar)
    else:
        raise RuntimeError("tutma_egrisi: ortalama t̄'ye yakınsamadı (2t̄ sınırı bağlıyor)")
    return pd.Series(t, index=u.index, dtype=float)


def secim(satirlar: list[dict], esik: float = ESIK_PUAN) -> dict:
    """Bulunabilirliği en iyisinin `esik` puandan az gerisinde olanlar arasında sezon sonu kalanı
    en düşük olan (eşitlikte ilk satır)."""
    if not satirlar:
        raise ValueError("secim: satır yok")
    en_iyi = max(float(s["bulunabilirlik"]) for s in satirlar)
    yakin = [s for s in satirlar if en_iyi - float(s["bulunabilirlik"]) < esik]
    return min(yakin, key=lambda s: float(s["sezon_sonu_kalan_yuzde"]))


# ---------------------------------------------------------------------------
# Koşusuz: SS23 ile öğren, SS24'te ölç
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Cevrimdisi:
    """Koşusuz seçimler (modül notu). `tablo`: her aday bir satır (`asama`, `aday`, `wape` ya da
    `spearman`, `secildi`, ...). `endeks`, `tahminci`: seçilen ayarlarla öğrenilmiş nesneler (SS23).
    `belirsizlik`, `agirlik`: SS24 Collection option_id -> seçilen ölçünün değeri / ilk alım."""

    en_az: int
    tahmin_parametreleri: dict
    belirsizlik_olcusu: str
    tablo: pd.DataFrame = field(repr=False)
    kaynak: str = "benzer"
    karar_gunu: pd.Timestamp | None = None
    endeks: object = field(default=None, repr=False)
    tahminci: object = field(default=None, repr=False)
    belirsizlik: pd.Series = field(default=None, repr=False)
    agirlik: pd.Series = field(default=None, repr=False)


def karar_gunu(tablolar: Mapping[str, pd.DataFrame], w, sezon: str = sabitler.KAL_SEZONU) -> pd.Timestamp:
    """Sezonun `LINE` option'larının en erken ilk dağıtım sevki (yayımlanan `sevkiyat`): motorun
    karar günü en uzak aday mağazanın sevk günüdür, en erkeni bu sezonun ilk kararıdır."""
    opt = kaynak.oyun_optionlari(w, sezon)
    skular = set(w.urunler["urun_id"].astype(str).to_numpy()[np.isin(np.asarray(w.sku_option), opt)])
    s = tablolar["sevkiyat"]
    secili = ((s["tip"] == "ilk_dagitim").fillna(False).to_numpy(dtype=bool)
              & s["urun_id"].astype(str).isin(skular).to_numpy())
    if not secili.any():
        raise ValueError(f"{sezon}: {sabitler.LINE} ilk dağıtımı yok")
    return pd.Timestamp(s.loc[secili, "tarih"].min()).normalize()


def erken_gercek(tablolar: Mapping[str, pd.DataFrame], w, sezon: str = sabitler.KAL_SEZONU) -> pd.DataFrame:
    """Sezonun `LINE` option'larının yayımlanan veriden erken talebi (`ogrenme.ERKEN_SUTUNLARI`):
    matrisler erken kesimin ertesi gününe dek (pencere kesimi dahil), varışlar bütün ilk dağıtım."""
    opt = kaynak.oyun_optionlari(w, sezon)
    dar = ogrenme.daralt(tablolar, w, opt)
    bit = kaynak.erken_kesim(w, sezon) + pd.Timedelta(days=1)
    satis, stoklu = kaynak.gunluk_matrisler(dar, w, bit)
    try:
        return ogrenme.erken_talep(satis, stoklu, kaynak.harita_kur(w), w, opt, ogrenme.ilk_varislar(dar, w))
    finally:
        del satis, stoklu


def aday_yaklasik(w, harita, o: int) -> np.ndarray:
    """[M] kolun aday kümesinin karar öncesi yaklaşığı: `paylastir.aday_maskesi`, kapanış kararı
    ve bugünkü açıklık bilinmeden (lansmana kadar açılan, lansmandan önce kapanmayan mağaza)."""
    M = len(w.magazalar)
    g = SimpleNamespace(dunya=w, kapanacak=np.zeros(M, dtype=bool), acik_magaza=np.zeros(M, dtype=bool))
    return aday_maskesi(g, int(o), harita)


def _uzun(optionlar, matris: np.ndarray, aday: np.ndarray) -> pd.DataFrame:
    """[n, M] pay matrisinden aday hücrelerin `option, magaza, pay` tablosu."""
    i, m = np.nonzero(aday)
    return pd.DataFrame({"option": np.asarray(optionlar, dtype=np.int64)[i], "magaza": m.astype(np.int64),
                         "pay": matris[i, m].astype(float)})


def _benzer_hesap(endeks, oz: pd.DataFrame, aday: np.ndarray):
    """(pay [n, M], düzey [n], dk [n])."""
    n, M = aday.shape
    pay, duzey, dk = np.zeros((n, M)), np.zeros(n), np.zeros(n)
    for i in range(n):
        satir = oz.iloc[i]
        e, d, _ = endeks.endeks(satir, aday[i])
        pay[i] = np.where(aday[i], e, 0.0)
        duzey[i] = d
        dk[i] = benzer.belirsizlik(endeks, satir, aday[i])
    return pay, duzey, dk


def _tahmin_pay(tc, w, oz: pd.DataFrame, aday: np.ndarray) -> np.ndarray:
    i, m = np.nonzero(aday)
    satirlar = oz.iloc[i].reset_index(drop=True)
    satirlar["magaza"] = m
    X = tahmin.ozellikler(satirlar, w.magazalar, tc.gecmis_karisim)
    pay = np.zeros(aday.shape)
    pay[i, m] = tc.tahmin(X)
    return pay


def _normal(pay: np.ndarray, aday: np.ndarray) -> np.ndarray:
    p = np.where(aday, pay, 0.0)
    t = p.sum(axis=1, keepdims=True)
    esit = aday / np.maximum(aday.sum(axis=1, keepdims=True), 1)
    return np.where(t > 0, p / np.where(t > 0, t, 1.0), esit)


def _adaylar(w, harita, opt: np.ndarray) -> np.ndarray:
    """[n, M] option'ların aday yaklaşığı (`aday_yaklasik`), `opt` sırasıyla."""
    if not len(opt):
        return np.zeros((0, len(w.magazalar)), bool)
    return np.stack([aday_yaklasik(w, harita, o) for o in opt])


def _olculer(benzer_pay: np.ndarray, duzey: np.ndarray, dk: np.ndarray, tahmin_pay: np.ndarray,
             aday: np.ndarray) -> dict[str, np.ndarray]:
    """`BELIRSIZLIK_OLCULERI`'nin option başına değerleri (modül notu)."""
    ayrisma = 0.5 * np.abs(_normal(benzer_pay, aday) - _normal(tahmin_pay, aday)).sum(axis=1)
    return {"benzer_dk": dk, "benzer_duzey": duzey, "benzer_tahmin_ayrisma": ayrisma}


def belirsizlik_olculeri(endeks, tahminci, w, harita, optionlar) -> dict[str, np.ndarray]:
    """`optionlar`ın (indis, bu sırayla) belirsizlik ölçüleri, öğrenilmiş `endeks` ve `tahminci` ile,
    kolun karar öncesi aday yaklaşığında (`kosusuz`'un hesabı; Görev 8 oyun sezonunun `t_o`'su için)."""
    opt = np.asarray(optionlar, dtype=np.int64)
    oz = ogrenme.option_oznitelikleri(w, opt)
    aday = _adaylar(w, harita, opt)
    benzer_pay, duzey, dk = _benzer_hesap(endeks, oz, aday)
    return _olculer(benzer_pay, duzey, dk, _tahmin_pay(tahminci, w, oz, aday), aday)


def _lumoda_payi(tablolar, w, optionlar) -> pd.DataFrame:
    """Yayımlanan `sevkiyat`'tan Lumoda'nın gerçekleşen ilk dağıtım adedi (bağlam)."""
    s = tablolar["sevkiyat"]
    s = s[(s["tip"] == "ilk_dagitim").fillna(False).to_numpy(dtype=bool)]
    sku = pd.Index(w.urunler["urun_id"].astype(str)).get_indexer(s["urun_id"].astype(str))
    m = pd.Index(w.magazalar["magaza_id"].astype(str)).get_indexer(s["hedef"].astype(str))
    var = (sku >= 0) & (m >= 0)
    df = pd.DataFrame({"option": np.asarray(w.sku_option)[sku[var]], "magaza": m[var],
                       "pay": s["adet"].to_numpy()[var].astype(float)})
    df = df[np.isin(df["option"], optionlar)]
    return df.groupby(["option", "magaza"], as_index=False)["pay"].sum()


def kosusuz(tablolar: Mapping[str, pd.DataFrame], w, *, sezon: str = sabitler.KAL_SEZONU,
            karar: pd.Timestamp | None = None, gercek: pd.DataFrame | None = None) -> Cevrimdisi:
    """Modül notundaki koşusuz seçim. `tablolar` yayımlanan tablolar (`kaynak.GUNLUK_TABLOLARI`;
    öğrenme karar gününden öncesini okur); `gercek` verilmezse `erken_gercek(tablolar, w, sezon)`.
    `karar` verilmezse `karar_gunu(tablolar, w, sezon)`."""
    karar = karar_gunu(tablolar, w, sezon) if karar is None else pd.Timestamp(karar).normalize()
    if gercek is None:
        gercek = erken_gercek(tablolar, w, sezon)
    ogr = ogrenme.ogrenme_tablosu(tablolar, w, karar)
    harita = kaynak.harita_kur(w)
    opt = kaynak.oyun_optionlari(w, sezon)
    oz = ogrenme.option_oznitelikleri(w, opt)
    aday = _adaylar(w, harita, opt)
    ilk_alim = pd.Series(np.asarray(w.ilk_alim, dtype=float)[opt], index=opt)
    satirlar: list[dict] = []

    def wape_satiri(asama: str, ad: str, pay: np.ndarray, **ek) -> dict:
        p = _uzun(opt, pay, aday)
        s = {"asama": asama, "aday": ad, "wape": pay_wape(p, gercek, ilk_alim),
             "n_option": int(len(option_wape(p, gercek))), **ek}
        satirlar.append(s)
        return s

    # bağlam: Lumoda'nın gerçekleşen payı ve eşit pay
    lum = _lumoda_payi(tablolar, w, opt)
    s = {"asama": "taban", "aday": "lumoda", "wape": pay_wape(lum, gercek, ilk_alim),
         "n_option": int(len(option_wape(lum, gercek)))}
    satirlar.append(s)
    wape_satiri("taban", "esit", aday.astype(float))

    # benzer: en_az ızgarası
    benzer_sonuc = {}
    for en_az in EN_AZ_IZGARASI:
        e = benzer.ogren(ogr, en_az, mevsim="SS").sabitle()
        hesap = _benzer_hesap(e, oz, aday)
        benzer_sonuc[en_az] = (e, hesap, wape_satiri("benzer", f"en_az={en_az}", hesap[0], en_az=en_az))
    en_az = min(EN_AZ_IZGARASI, key=lambda k: (benzer_sonuc[k][2]["wape"], EN_AZ_IZGARASI.index(k)))

    # tahmin: num_leaves × min_child_samples
    tahmin_sonuc = []
    for nl in NUM_LEAVES:
        for mcs in MIN_CHILD_SAMPLES:
            p = {**tahmin.VARSAYILAN, "num_leaves": nl, "min_child_samples": mcs}
            tc = tahmin.Tahminci.egit(ogr, w.magazalar, p).sabitle()
            pay = _tahmin_pay(tc, w, oz, aday)
            d = tc.dogrulama
            tahmin_sonuc.append((p, tc, pay, wape_satiri(
                "tahmin", f"num_leaves={nl},min_child_samples={mcs}", pay, num_leaves=nl, min_child_samples=mcs,
                sapma_pay_model=d.get("sapma_pay_model", np.nan), sapma_model=d.get("sapma_model", np.nan))))
    k = min(range(len(tahmin_sonuc)), key=lambda i: (tahmin_sonuc[i][3]["wape"], i))
    parametreler, tc, tahmin_pay_m, tahmin_satir = tahmin_sonuc[k]

    endeks, (benzer_pay_m, duzey, dk), benzer_satir = benzer_sonuc[en_az]
    benzer_satir["secildi"] = tahmin_satir["secildi"] = True
    kaynak_ad = "benzer" if benzer_satir["wape"] <= tahmin_satir["wape"] else "tahmin"
    kaynak_pay = benzer_pay_m if kaynak_ad == "benzer" else tahmin_pay_m

    # belirsizlik ölçüleri: kaynağın option WAPE'siyle Spearman
    olculer = _olculer(benzer_pay_m, duzey, dk, tahmin_pay_m, aday)
    ow = option_wape(_uzun(opt, kaynak_pay, aday), gercek).reindex(opt).to_numpy()
    rho = {}
    for ad in BELIRSIZLIK_OLCULERI:
        rho[ad] = spearman(olculer[ad], ow)
        satirlar.append({"asama": "belirsizlik", "aday": ad, "spearman": rho[ad],
                         "n_option": int((np.isfinite(olculer[ad]) & np.isfinite(ow)).sum()),
                         "kaynak": kaynak_ad})
    olcu = max(BELIRSIZLIK_OLCULERI, key=lambda a: (rho[a] if np.isfinite(rho[a]) else -np.inf,
                                                    -BELIRSIZLIK_OLCULERI.index(a)))
    for s in satirlar:
        if s["asama"] == "belirsizlik" and s["aday"] == olcu:
            s["secildi"] = True

    tablo = pd.DataFrame([{**s, "secildi": bool(s.get("secildi", False))} for s in satirlar])
    ids = w.optionlar["option_id"].astype(str).to_numpy()[opt]
    return Cevrimdisi(en_az=int(en_az), tahmin_parametreleri=dict(parametreler), belirsizlik_olcusu=olcu,
                      tablo=tablo, kaynak=kaynak_ad, karar_gunu=karar, endeks=endeks, tahminci=tc,
                      belirsizlik=pd.Series(np.asarray(olculer[olcu], dtype=float), index=ids, name=olcu),
                      agirlik=pd.Series(ilk_alim.to_numpy(), index=ids, name="ilk_alim"))


# ---------------------------------------------------------------------------
# Simülasyon (SS24, 7 TAM koşu)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class KalKol:
    """Bir kalibrasyon koşusunun tanımı (`kos_fn`'e gider; kolu `kol_kur` kurar).

    kol     "lumoda" (referans; Lumoda'nın kendisi) | "benzer" | "tahmin" | "belirsizlik"
    ayar    kolun `Ayar`'ı (`sezon = KAL_SEZONU`); belirsizlikte tabanın ayarı
    taban   belirsizliğin pay kaynağı ("benzer" | "tahmin")
    gamma   belirsizlik eğrisinin dikliği
    t_o     belirsizlikte option_id -> tutma oranı"""

    kol: str
    ayar: Ayar
    taban: str | None = None
    gamma: float | None = None
    t_o: Mapping[str, float] | None = field(default=None, repr=False)

    def parametreler(self) -> dict:
        """Koşu anahtarına giden `parametreler` (öğrenilmiş nesneler ve t_o kolun kendi
        `parametreler()`'inden girer)."""
        p = {"blok": "kalibrasyon", "kol": self.kol}
        if self.taban is not None:
            p["taban"] = self.taban
        if self.gamma is not None:
            p["gamma"] = float(self.gamma)
        return p


@dataclass(frozen=True, eq=False)
class Simulasyon:
    """Simülasyon seçimleri; `tablo` her koşu bir satır (`asama`, `ad`, `kol`, `tavan`, `gamma`,
    `kos_fn`'in ölçütleri, `secildi`)."""

    tavan: bool
    gamma: float
    belirsizlik_taban: str
    tablo: pd.DataFrame = field(repr=False)


def kol_kur(tanim: KalKol, cev: Cevrimdisi, temel, harita):
    """`tanim`ın ilk dağıtım kolu (her koşuya yeni nesne); `lumoda` için None (Lumoda'nın kendisi)."""
    if tanim.kol == "lumoda":
        return None
    if tanim.kol == "benzer":
        return BenzerKol(temel, harita, tanim.ayar, endeks=cev.endeks)
    if tanim.kol == "tahmin":
        return TahminKol(temel, harita, tanim.ayar, tahminci=cev.tahminci)
    if tanim.kol == "belirsizlik":
        if tanim.taban not in ("benzer", "tahmin") or tanim.t_o is None:
            raise ValueError("belirsizlik: taban (benzer | tahmin) ve t_o gerekir")
        return BelirsizlikKol(kol_kur(KalKol(tanim.taban, tanim.ayar), cev, temel, harita), tanim.t_o)
    raise ValueError(f"bilinmeyen kalibrasyon kolu: {tanim.kol!r}")


def _gamma_adi(g: float) -> str:
    return f"{float(g):g}"


def simulasyon(kos_fn, cev: Cevrimdisi) -> Simulasyon:
    """Modül notundaki simülasyon; `kos_fn(ad, tanim) -> dict` her koşu için bir kez."""
    satirlar: list[dict] = []

    def olc(asama: str, ad: str, tanim: KalKol) -> dict:
        olcut = dict(kos_fn(ad, tanim))
        eksik = [o for o in GEREKEN_OLCUTLER if o not in olcut]
        if eksik:
            raise KeyError(f"kos_fn ölçütü eksik ({ad}): {eksik}")
        s = {"asama": asama, "ad": ad, "kol": tanim.kol, "taban": tanim.taban, "tavan": bool(tanim.ayar.tavan),
             "gamma": tanim.gamma, **olcut, "secildi": False}
        satirlar.append(s)
        return s

    olc("referans", "lumoda", KalKol("lumoda", Ayar(sezon=sabitler.KAL_SEZONU, tavan=False)))

    tavan_satirlari = []
    for kol in ("benzer", "tahmin"):
        for tavan in (True, False):
            ad = f"kal_{kol}_{'tavanli' if tavan else 'tavansiz'}"
            tavan_satirlari.append(olc("tavan", ad, KalKol(kol, Ayar(sezon=sabitler.KAL_SEZONU, tutma=0.0,
                                                                         tavan=tavan))))
    en_iyi = secim(tavan_satirlari)
    en_iyi["secildi"] = True
    taban, tavan = en_iyi["kol"], bool(en_iyi["tavan"])

    gamma_satirlari = []
    for g in GAMMA_IZGARASI:
        t_o = tutma_egrisi(cev.belirsizlik, cev.agirlik, g)
        tanim = KalKol("belirsizlik", Ayar(sezon=sabitler.KAL_SEZONU, tavan=tavan), taban=taban, gamma=float(g),
                       t_o={str(o): float(v) for o, v in t_o.items()})
        s = olc("gamma", f"kal_belirsizlik_g{_gamma_adi(g)}", tanim)
        s.update(t_ortalama=float((t_o * cev.agirlik.reindex(t_o.index)).sum() / cev.agirlik.sum()),
                 t_en_az=float(t_o.min()), t_en_cok=float(t_o.max()))
        gamma_satirlari.append(s)
    en_iyi_g = secim(gamma_satirlari)
    en_iyi_g["secildi"] = True
    return Simulasyon(tavan=tavan, gamma=float(en_iyi_g["gamma"]), belirsizlik_taban=taban,
                      tablo=pd.DataFrame(satirlar))


# ---------------------------------------------------------------------------
# Dosya
# ---------------------------------------------------------------------------


def _json_degeri(x):
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):     # numpy skaleri
        x = x.item()
    if isinstance(x, float) and math.isnan(x):
        return None
    if isinstance(x, pd.Timestamp):
        return x.date().isoformat()
    return x


def _kayitlar(df: pd.DataFrame) -> list[dict]:
    return [{s: _json_degeri(v) for s, v in r.items()} for r in df.to_dict("records")]


def izgara_ucundakiler(c: Cevrimdisi) -> list[str]:
    """Izgaranın ucunda seçilen parametreler (Ruling R24: uçta seçim ızgaranın yanlış yerde olduğunu
    gösterir; son ızgarada da uçta kalan buraya yazılır)."""
    uc = []
    for ad, deger, izgara in (("en_az", c.en_az, EN_AZ_IZGARASI),
                              ("num_leaves", c.tahmin_parametreleri.get("num_leaves"), NUM_LEAVES),
                              ("min_child_samples", c.tahmin_parametreleri.get("min_child_samples"),
                               MIN_CHILD_SAMPLES)):
        if deger in (min(izgara), max(izgara)):
            uc.append(ad)
    return uc


def _secilen_spearman(tablo: pd.DataFrame) -> float | None:
    if tablo.empty or "asama" not in tablo:
        return None
    r = tablo[(tablo["asama"] == "belirsizlik").to_numpy() & tablo["secildi"].to_numpy(dtype=bool)]
    return float(r["spearman"].iloc[0]) if len(r) else None


def _gamma_araligi(tablo: pd.DataFrame, sutun: str) -> float | None:
    if tablo.empty or "asama" not in tablo:
        return None
    g = tablo.loc[(tablo["asama"] == "gamma").to_numpy(), sutun]
    return float(g.max() - g.min()) if len(g) else None


def sozluk(c: Cevrimdisi, s: Simulasyon) -> dict:
    """JSON'a giden biçim (Görev 8 bunu okur). Belirsizlik sinyalinin gücü açıkça yazılır:
    seçilen ölçünün Spearman'ı ve γ koşularının bulunabilirlik / sezon sonu kalan aralığı (puan;
    aralık `ESIK_PUAN`'dan küçükse γ seçimi eşitlik kuralıyla, sezon sonu kalandan verilmiştir)."""
    return {
        "sezon": sabitler.KAL_SEZONU,
        "karar_gunu": None if c.karar_gunu is None else pd.Timestamp(c.karar_gunu).date().isoformat(),
        "en_az": int(c.en_az),
        "hiyerarsi": [list(d) for d in benzer.HIYERARSI],
        "tahmin_parametreleri": {k: _json_degeri(v) for k, v in c.tahmin_parametreleri.items()},
        "kaynak": c.kaynak,
        "belirsizlik_olcusu": c.belirsizlik_olcusu,
        "tavan": bool(s.tavan),
        "gamma": float(s.gamma),
        "belirsizlik_taban": s.belirsizlik_taban,
        "tbar": sabitler.BELIRSIZLIK_TBAR,
        "izgara": {"en_az": list(EN_AZ_IZGARASI), "num_leaves": list(NUM_LEAVES),
                   "min_child_samples": list(MIN_CHILD_SAMPLES), "gamma": list(GAMMA_IZGARASI)},
        "izgara_ucunda": izgara_ucundakiler(c),
        "belirsizlik_spearman": _secilen_spearman(c.tablo),
        "gamma_bulunabilirlik_araligi_puan": _gamma_araligi(s.tablo, "bulunabilirlik"),
        "gamma_kalan_araligi_puan": _gamma_araligi(s.tablo, "sezon_sonu_kalan_yuzde"),
        "gamma_esik_puan": ESIK_PUAN,
        "cevrimdisi": _kayitlar(c.tablo),
        "simulasyon": _kayitlar(s.tablo),
    }


def yaz(c: Cevrimdisi, s: Simulasyon, yol=DOSYA, **ek) -> Path:
    """Seçimleri (ve `ek` alanlarını, ör. süre) JSON olarak yazar (önce geçici ad, sonra yerine)."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".yaziliyor")
    gecici.write_text(json.dumps({**sozluk(c, s), **{k: _json_degeri(v) for k, v in ek.items()}},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(yol)
    return yol


def oku(yol=DOSYA) -> dict:
    """`yaz`ın dosyası (sözlük)."""
    return json.loads(Path(yol).read_text(encoding="utf-8"))
