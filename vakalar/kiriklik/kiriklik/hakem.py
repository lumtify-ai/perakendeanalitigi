"""Hakem: kahin girdisi (tasarım §0 K8 `kahin`, K22). Ölçüm modülü: gizli gerçeğe dokunan tek modül.

    kahin_girdisi(w, lumoda_kosusu, g, hucreler, iade_magaza) -> DataFrame
        [magaza_id, urun_id, mu_tam, mu_ind, fiyat_tam, fiyat_ind]     (`tahmin.KOLONLAR`)

Çıktının şeması ve anlamı `tahmin.ufuk_talebi(g, og)` ile aynıdır, böylece optimizasyon (`model`) ikisini de
alabilir; fark girdinin kaynağıdır: tahmin açık bilgiden kurulur, kahin dünyanın **gerçek talebini ve gerçekleşen
fiyat yolunu** bilir (K22). `opt` ile `kahin` arasındaki fark "talebi ve fiyat yolunu bilmenin değeri"dir.
Karar modülleri bu modülü içe aktarmaz (`test_karar_modulleri_hakemi_ice_aktarmaz`; Görev 8 AST kilidi).

**Hücreler.** `hucreler` [magaza_id, urun_id], `tahmin.ufuk_talebi(g, og)`'nin aynı `g` için ürettiği hücre
kümesidir; çağıran verir, burada yeniden türetilmez: iki girdi aynı hücreleri kapsar ve satır sırası `hucreler`'in
sırasıdır. Hücreler fiziksel (AVM / Cadde) ve outlet akışı dışında olmalıdır, çünkü fiyat olarak yalnız normal hat
okunur; dünyada karşılığı olmayan ya da fiziksel olmayan hücre `ValueError`.

**Ufuk.** Evre 1 `[karar + VARIS_GUN, indirim)`, evre 2 `[indirim, çıkış)` (tahminle aynı). Gün indisi
`perakende_veri.v4.takvim.gun_indisi`.

**Talep.** Motorun talep çekilişinin beklentisi (motor/dongu.py adım 12-13): hücre-gün

    λ_gün = w.lam.gun(d)[hücre] · (1 − oran)^(−ε_hücre),        oran = max(markdown, kampanya)

`oran_talep`in motordaki tanımıdır; `markdown` kaydedilmiş normal hat durumu, `kampanya` dünyanın kampanya
takvimi (`w.kampanya_takvimi(d)[mağaza, option]`; tahminin yok saydığı kategori ve bölge kampanyaları da dahil,
çünkü gerçek fiyat yolu onları içerir). `mu_tam`, `mu_ind` evrelerin Σ λ_gün'üdür: Poisson ortalaması, stoktan
bağımsız (tahminle aynı sözleşme).

**Fiyat yolu.** Markdown yuvası her çağrıda bütün durumu `[O, 3]` döndürür ve motor bunu bir sonraki çağrıya kadar
korur (`z.fiyat_orani`); çağrı günleri her pazartesi ve sezonluk option'ların indirim günleridir. Günün durumu bu
yüzden o gün dahil son çağrı gününün `Takvim.markdown_gunu` kaydıdır (kayıtsız çağrı günü = sıfır durum, yani
yeniden oynatımın uyguladığı karar). Hat 0 (normal) okunur.

**Fiyatlar.** Evrenin günlük birim fiyatı `liste · (1 − oran)`; evre fiyatı bunun o günün beklenen talebiyle
ağırlıklı ortalamasıdır (talep fiyat düşünce artar, indirimli günler daha çok ağırlık alır); evrede toplam talep
sıfırsa ağırlıksız gün ortalaması, evre boşsa liste fiyatı. Sonra tahminle aynı iade payıyla net fiyat:
`× (1 − iade_magaza)` (çağıran `Ogrenilen.iade["magaza"]`'yı verir). **İşlem indirimi yoktur**: motorun rastgele
işlem indirimi (tam fiyatlı günde %30'a kadar) kahinde modellenmez, tahminin `fiyat_tam`ındaki `(1 − işlem)`
çarpanı burada bulunmaz; bu yüzden `fiyat_tam` kahinde tahminden biraz yüksektir.

`lumoda_kosusu` yolun Lumoda koşusudur (`allocation.motor.Kosu` / `KosuKaydi`; `motor.takvim(kosu, w)` ile
kayıtlı markdown kararlarından `Takvim` kurulur); doğrudan bir `motor.Takvim` de verilebilir.
"""

import numpy as np
import pandas as pd
from allocation import motor
from perakende_veri.v4.takvim import gun_indisi

from kiriklik import sabitler, tahmin
from kiriklik.kaynak import KararGirdisi

HAT_NORMAL = 0          # fiziksel hücrelerin fiyat hattı (motor/satis.py `hat_indisi`)


def _hucre_bul(w, magaza_id: pd.Series, urun_id: pd.Series) -> np.ndarray:
    """(magaza_id, urun_id) → dünya hücre indisi (yoksa −1)."""
    S = len(w.urunler)
    m = pd.Index(w.magazalar["magaza_id"].astype(str)).get_indexer(magaza_id.astype(str))
    s = pd.Index(w.urunler["urun_id"].astype(str)).get_indexer(urun_id.astype(str))
    anahtar = np.asarray(w.hucre_magaza, dtype=np.int64) * S + np.asarray(w.hucre_sku, dtype=np.int64)
    sira = np.argsort(anahtar, kind="stable")
    sirali = anahtar[sira]
    k = np.where((m >= 0) & (s >= 0), m.astype(np.int64) * S + s, -1)
    i = np.minimum(np.searchsorted(sirali, k), len(sirali) - 1)
    return np.where((k >= 0) & (sirali[i] == k), sira[i], -1)


def _cagri_gunu(w) -> np.ndarray:
    """Her dünya günü için o gün dahil markdown yuvasının son çağrı günü (çağrı günleri: pazartesiler ve sezonluk
    option'ların indirim günleri; motor/dongu.py adım 9 ve `indirim_gunleri`). İlk çağrıdan önceki gün −1."""
    haftanin_gunu = pd.DatetimeIndex(w.takvim["tarih"]).dayofweek.to_numpy()
    gunler = np.arange(len(haftanin_gunu))
    pazartesi = gunler - haftanin_gunu
    opt = w.optionlar
    indirim = np.unique(opt["indirim_gun"].to_numpy(dtype=np.int64)[opt["sezonluk"].to_numpy(dtype=bool)])
    k = np.searchsorted(indirim, gunler, side="right") - 1
    son_indirim = np.where(k >= 0, indirim[np.maximum(k, 0)], -1)
    return np.maximum(pazartesi, son_indirim)


def _bos() -> pd.DataFrame:
    return pd.DataFrame({"magaza_id": pd.Series(dtype=object), "urun_id": pd.Series(dtype=object),
                         "mu_tam": pd.Series(dtype=float), "mu_ind": pd.Series(dtype=float),
                         "fiyat_tam": pd.Series(dtype=float), "fiyat_ind": pd.Series(dtype=float)})[tahmin.KOLONLAR]


def kahin_girdisi(w, lumoda_kosusu, g: KararGirdisi, hucreler: pd.DataFrame, iade_magaza: float) -> pd.DataFrame:
    """Kahinin ufuk talebi ve net fiyatları (modül notu). `hucreler`: `tahmin.ufuk_talebi(g, og)`'nin hücreleri
    [magaza_id, urun_id]; çıktı bu sırada."""
    if hucreler.empty:
        return _bos()
    hucre = _hucre_bul(w, hucreler["magaza_id"], hucreler["urun_id"])
    if (hucre < 0).any():
        raise ValueError(f"kahin_girdisi: dünyada hücresi olmayan {int((hucre < 0).sum())} hücre")
    tip = w.magazalar["tip"].astype(str).to_numpy()[np.asarray(w.hucre_magaza)[hucre]]
    if (~np.isin(tip, sabitler.FIZIKSEL_TIPLER) | np.asarray(w.hucre_outlet_akisi, dtype=bool)[hucre]).any():
        raise ValueError("kahin_girdisi: hücreler fiziksel (AVM / Cadde) ve outlet akışı dışı olmalı")

    tk = lumoda_kosusu if isinstance(lumoda_kosusu, motor.Takvim) else motor.takvim(lumoda_kosusu, w)
    evre1 = np.arange(gun_indisi(g.karar) + sabitler.VARIS_GUN, gun_indisi(g.indirim))
    evre2 = np.arange(gun_indisi(g.indirim), gun_indisi(g.cikis))
    gunler = np.concatenate([evre1, evre2])
    if len(gunler) and (gunler.min() < 0 or gunler.max() >= min(w.lam.gun_sayisi, len(w.takvim))):
        raise ValueError(f"kahin_girdisi: ufuk dünyanın gün aralığı dışında: [{gunler.min()}, {gunler.max()}]")

    ho = np.asarray(w.hucre_option, dtype=np.int64)[hucre]
    hm = np.asarray(w.hucre_magaza, dtype=np.int64)[hucre]
    eps = np.asarray(w.esneklik_hucre, dtype=float)[hucre]
    liste = w.urunler["liste_fiyati"].to_numpy(dtype=float)[np.asarray(w.hucre_sku, dtype=np.int64)[hucre]]
    cagri = _cagri_gunu(w)
    durumlar: dict[int, np.ndarray] = {}

    def oran(d: int) -> np.ndarray:
        c = int(cagri[d])
        if c not in durumlar:
            durumlar[c] = tk.markdown_gunu(c) if c >= 0 else np.zeros((tk.option_sayisi, 3))
        return np.maximum(durumlar[c][ho, HAT_NORMAL], w.kampanya_takvimi(d)[hm, ho])

    def evre(gun_listesi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(Σ talep, talep ağırlıklı ortalama birim fiyat) hücre başına; iade payı düşülmemiş."""
        n = len(hucre)
        if len(gun_listesi) == 0:
            return np.zeros(n), liste.copy()
        talep, tutar, fiyat_toplam = np.zeros(n), np.zeros(n), np.zeros(n)
        for d in gun_listesi:
            o = oran(int(d))
            fiyat = liste * (1.0 - o)
            t = w.lam.gun(int(d))[hucre] * np.power(1.0 - o, -eps)
            talep += t
            tutar += t * fiyat
            fiyat_toplam += fiyat
        ortalama = np.where(talep > 0, tutar / np.where(talep > 0, talep, 1.0), fiyat_toplam / len(gun_listesi))
        return talep, ortalama

    mu_tam, fiyat_tam = evre(evre1)
    mu_ind, fiyat_ind = evre(evre2)
    net = 1.0 - float(iade_magaza)
    return pd.DataFrame({"magaza_id": hucreler["magaza_id"].to_numpy(), "urun_id": hucreler["urun_id"].to_numpy(),
                         "mu_tam": mu_tam, "mu_ind": mu_ind,
                         "fiyat_tam": fiyat_tam * net, "fiyat_ind": fiyat_ind * net})[tahmin.KOLONLAR]
