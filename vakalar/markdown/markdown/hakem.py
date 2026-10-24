"""Hakem: kahinin gerçek girdileri ve gerçek esneklik (yalnız ölçüm; spec §0/12, §4.1–4.2).

Bu modül ölçüm tarafındadır (`tests/test_sizinti.py` `OLCUM_MODULLERI`): vakada dünyanın gizli
alanlarına (`w.lam`, `w.esneklik_hucre`) yalnız bu modül ve `simulasyon` dokunur (AST kilidi:
öteki ölçüm modülleri de okumaz). Karar modülleri bunu içe aktarmaz; kahin girdileri politikaya
yapıcı argümanı olarak, dizi hâlinde verilir (`politika.KahinGirdisi`).

**Kahin girdisi** (`kahin_girdisi(w, test_idx, ufuk)`). Hücreler: test option'larının hücreleri, outlet
akışı hariç (`Tahminci.hucreler`'in kümesi; ONL dahil), artan dünya hücre indisiyle. Günler: `ufuk`
(verilmezse test option'larının en erken serbest karar penceresinden en geç çıkışın önceki gününe,
`[min pencere, max çıkış)`). `taban[u, j] = w.lam.gun(gun_u)[hucre_j]`: motorun talep çekilişindeki
λ, liste fiyatında, fiyat çarpanından önce (motor/dongu.py adım 13: talep = Poisson(λ · (1 −
max(md, kampanya))^(−ε))); float32'ye yuvarlanır. `eps = w.esneklik_hucre[hucre]` (motorun hücre
ε'si). Girdi yola göre değişmez (yollar yalnız müşteri akışını değiştirir; spec §4.4).

**Gerçek esneklik** (`gercek_eps(w, satis, sezon)`). Test option'larının (sezon verilmezse iki test
sezonunun) Collection option'larının, indirim döneminde (`indirim_gun ≤ gün < cikis_gun`) pozitif
satış satırlarının adediyle ağırlıklı hücre ε'si: `Σ adet · ε_hücre ÷ Σ adet`, üst kategori başına ve
`"*"` (hepsi). Satış satırı (mağaza, ürün) hücresine eşlenir; dünyada hücresi olmayan satır hata.
Satışı olmayan üst kategori sözlükte yer almaz.
"""

import numpy as np
import pandas as pd

from markdown import kaynak, sabitler
from markdown.politika import KahinGirdisi

_GUN_SIFIRI = pd.Timestamp(sabitler.GUN_SIFIRI)


def kahin_hucreleri(w, test_idx) -> np.ndarray:
    """Test option'larının outlet akışı dışı hücreleri (artan dünya hücre indisi)."""
    ho = np.asarray(w.hucre_option, dtype=np.int64)
    outlet = np.asarray(w.hucre_outlet_akisi, dtype=bool)
    return np.flatnonzero(np.isin(ho, np.asarray(test_idx, dtype=np.int64)) & ~outlet)


def varsayilan_ufuk(w, test_idx) -> np.ndarray:
    """`[min serbest karar penceresi, max çıkış)` gün indisleri."""
    idx = np.asarray(test_idx, dtype=np.int64)
    pencere = kaynak.karar_penceresi(w.optionlar, idx, "serbest")
    cikis = w.optionlar["cikis_gun"].to_numpy(dtype=np.int64)[idx]
    return np.arange(int(pencere.min()), int(cikis.max()), dtype=np.int64)


def kahin_girdisi(w, test_idx, ufuk=None) -> KahinGirdisi:
    """Kahinin gerçek girdisi (modül notu): hücre-gün λ (float32) ve hücre ε'si."""
    idx = np.unique(np.asarray(test_idx, dtype=np.int64))
    hucre = kahin_hucreleri(w, idx)
    gunler = varsayilan_ufuk(w, idx) if ufuk is None else np.asarray(ufuk, dtype=np.int64)
    if len(gunler) and (gunler.min() < 0 or gunler.max() >= w.lam.gun_sayisi):
        raise ValueError(f"ufuk dünyanın gün aralığı dışında: [{gunler.min()}, {gunler.max()}]")
    taban = np.empty((len(gunler), len(hucre)), dtype=np.float32)
    for u, d in enumerate(gunler):
        taban[u] = w.lam.gun(int(d))[hucre]
    eps = np.asarray(w.esneklik_hucre, dtype=float)[hucre]
    return KahinGirdisi(hucre=hucre, gunler=gunler, taban=taban, eps=eps)


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


def gercek_eps(w, satis: pd.DataFrame, sezon: str | None = None) -> dict[str, float]:
    """Satış ağırlıklı gerçek hücre ε'si, üst kategori ve `"*"` (modül notu). `satis`: en az `tarih,
    magaza_id, urun_id, adet`."""
    sezonlar = sabitler.TEST_SEZONLARI if sezon is None else (sezon,)
    opt = w.optionlar
    test = kaynak.test_optionlari(opt, sezonlar)
    secili = np.zeros(len(opt), dtype=bool)
    secili[test] = True
    sku_o = np.asarray(w.sku_option, dtype=np.int64)
    s = pd.Index(w.urunler["urun_id"].astype(str)).get_indexer(satis["urun_id"].astype(str))
    o = np.where(s >= 0, sku_o[np.maximum(s, 0)], -1)
    gun = ((pd.to_datetime(satis["tarih"]) - _GUN_SIFIRI).dt.days).to_numpy(dtype=np.int64)
    adet = satis["adet"].to_numpy(dtype=np.int64)
    oo = np.maximum(o, 0)
    indirim = opt["indirim_gun"].to_numpy(dtype=np.int64)[oo]
    cikis = opt["cikis_gun"].to_numpy(dtype=np.int64)[oo]
    m = (o >= 0) & secili[oo] & (adet > 0) & (gun >= indirim) & (gun < cikis)
    if not m.any():
        return {}
    sec = satis[m]
    hucre = _hucre_bul(w, sec["magaza_id"], sec["urun_id"])
    if (hucre < 0).any():
        raise ValueError(f"gercek_eps: dünyada hücresi olmayan {int((hucre < 0).sum())} satış satırı")
    a = adet[m].astype(float)
    eps = np.asarray(w.esneklik_hucre, dtype=float)[hucre]
    ust = opt["ust_kategori"].astype(str).to_numpy()[o[m]]
    t = pd.DataFrame({"ust": ust, "ae": a * eps, "a": a}).groupby("ust", sort=True)[["ae", "a"]].sum()
    sonuc = {str(k): float(r.ae / r.a) for k, r in t.iterrows()}
    sonuc["*"] = float((a * eps).sum() / a.sum())
    return sonuc
