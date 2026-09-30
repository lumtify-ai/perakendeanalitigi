"""Müşteri × ürün tercih puanı ve gizli tamamlayıcılık matrisi (spec §1, §3).

`Nufus` (ya da aynı sütunları taşıyan herhangi bir nesne: `arketip_ornegi`
gibi) ile A'nın `dunya.urunler` tablosundaki ürün öznitelikleri arasında
log-uzayda toplanabilir bir eşleştirme puanı üretir. Ölçek 5'in (Görev 5)
günlük eşleştirme algoritması iki aşamalıdır: önce **tip** düzeyinde (alt
kategori × fiyat segmenti × beden sırası; aksesuar tek beden STD) kesin
eşleştirme, sonra tip içinde SKU (kalıp, desen, indirim oranı) düzeyinde
ayrıştırma. Bu modül iki düzeyi ayrı fonksiyonlarla verir (`tip_puani`,
`sku_ek_puani`) ki eşleştirici binlerce (müşteri, tip) çiftini tip
düzeyinde ucuza puanlayıp yalnız kazanan tipler için SKU düzeyine insin;
`urun_puani` ikisinin toplamı olarak SKU düzeyinde tek adımda da
kullanılabilir (küçük ölçek, test, doğrulama).

Müşteri × ürün cinsiyeti (Görev 5b): `cinsiyet_terimi` aynı cinsiyet ve
Unisex için 0, çapraz için `CAPRAZ_CINSIYET_CEZA` (aksesuarda yarısı).
Tip kodu cinsiyetsiz kalır; eşleştirici terimi aşama 1'in grup anahtarına
(mağaza, tip, ürün cinsiyeti) katar. `urun_puani` üç terimin toplamıdır.

Gizli tamamlayıcılık matrisi (`tamamlayici_matris`) hiçbir yayımlanan
tabloya ya da `Nufus` sütununa girmez; yalnız günlük ayrıştırmanın (Görev
5) sepet-içi eşleştirme puanında kullanılır.
"""

import numpy as np
import pandas as pd

from .. import sabitler as a_sabitler
from . import sabitler as S

# ---------------------------------------------------------------------------
# Tip kodlaması: (alt kategori, fiyat segmenti, beden sırası; aksesuar STD)
# ---------------------------------------------------------------------------

A_ALT = len(S.ALT_KATEGORILER)
A_SEG = len(S.FIYAT_SEGMENTLERI)
BEDEN_KADEME = a_sabitler.BEDEN_KADEME_SAYISI      # 5
STD_BEDEN = BEDEN_KADEME                            # aksesuar tipinin beden indisi (5)
TIP_BEDEN = BEDEN_KADEME + 1                        # 0..4 gerçek beden + STD
N_TIP = A_ALT * A_SEG * TIP_BEDEN

_ALT_IDX = {a: i for i, a in enumerate(S.ALT_KATEGORILER)}
_SEG_IDX = {f: i for i, f in enumerate(S.FIYAT_SEGMENTLERI)}
_KALIP_IDX = {k: i for i, k in enumerate(S.KALIPLAR)}
_DESEN_IDX = {d: i for i, d in enumerate(S.DESENLER)}

# Alt kategorinin beden uyumunda hangi müşteri bedenine bakılacağı:
#   0 = beden_ust (Üst Giyim, Dış Giyim, Elbise & Tulum)
#   1 = beden_alt (Alt Giyim)
#  -1 = yok (Aksesuar, ceza 0)
_UST_KATEGORI: dict[str, str] = {
    a: u for u, altlar in a_sabitler.KATEGORILER.items() for a in altlar
}
_BEDEN_YONU = np.array(
    [
        1 if _UST_KATEGORI[a] == "Alt Giyim" else (-1 if _UST_KATEGORI[a] == "Aksesuar" else 0)
        for a in S.ALT_KATEGORILER
    ],
    dtype=np.int8,
)
BEDEN_YONU = _BEDEN_YONU  # [17] alt kategori → 0 üst beden, 1 alt beden, −1 aksesuar

# Beden sırası farkının log-ceza tabanı (`beden_dagin` ile bölünerek
# yumuşatılır); fark 0 → 0. KALİBRASYON (Görev 5): −1,2 / −3,0 ile KUCUK'ta
# 60 günlük koşuda (aksesuar hariç) müşterinin bedenindeki birim payı %70–71
# (brief alt sınırı %70), −1,8 / −3,5 ile %75–76 (5 B tohumu).
BEDEN_FARK_1 = -1.8
BEDEN_FARK_2 = -3.5


def tip_kodu(urunler) -> np.ndarray:
    """`urunler` (A'nın `dunya.urunler` tablosu ya da aynı sütunlara sahip
    bir alt küme) satırları için tip kodu, `[0, N_TIP)`."""
    alt = urunler["alt_kategori"].to_numpy()
    fs = urunler["fiyat_segmenti"].to_numpy()
    beden_sira = urunler["beden_sira"].to_numpy(dtype=np.int64)
    alt_idx = pd.Series(alt).map(_ALT_IDX).to_numpy(dtype=np.int64)
    seg_idx = pd.Series(fs).map(_SEG_IDX).to_numpy(dtype=np.int64)
    aksesuar = np.isin(alt, list(a_sabitler.AKSESUAR))
    beden_idx = np.where(aksesuar, STD_BEDEN, beden_sira - 1)
    return (alt_idx * A_SEG + seg_idx) * TIP_BEDEN + beden_idx


def tip_ozellik() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bütün `[0, N_TIP)` tip kodları için (alt kategori indisi, fiyat
    segmenti indisi, beden indisi [0..4 gerçek, `STD_BEDEN` aksesuar])."""
    tip = np.arange(N_TIP)
    beden_idx = tip % TIP_BEDEN
    kalan = tip // TIP_BEDEN
    seg_idx = kalan % A_SEG
    alt_idx = kalan // A_SEG
    return alt_idx, seg_idx, beden_idx


def tip_puani(nufus, k_idx, tip_idx) -> np.ndarray:
    """`[len(k_idx), len(tip_idx)]` log-puan: alt kategori tercihi + fiyat
    segmenti eğilimi + beden uyumu terimi (fark 0 → 0, 1 → −1,8, ≥2 → −3,5;
    `beden_dagin` ile yumuşar; aksesuar 0)."""
    k_idx = np.asarray(k_idx, dtype=np.int64)
    tip_idx = np.asarray(tip_idx, dtype=np.int64)
    alt_t, seg_t, beden_t = tip_ozellik()
    alt = alt_t[tip_idx]
    seg = seg_t[tip_idx]
    beden = beden_t[tip_idx]

    # log önce (müşteri × 17 / × 3), sonra tip sütunlarına dağıt: aynı değer, daha ucuz
    kat = np.log(np.asarray(nufus.tercih_kat)[k_idx])[:, alt]
    fiyat = np.log(np.asarray(nufus.fiyat_segment_egilim)[k_idx])[:, seg]

    yon = _BEDEN_YONU[alt]                                            # [T]
    musteri_ust = np.asarray(nufus.beden_ust)[k_idx].astype(np.float64)[:, None]
    musteri_alt = np.asarray(nufus.beden_alt)[k_idx].astype(np.float64)[:, None]
    musteri_beden = np.where(yon[None, :] == 1, musteri_alt, musteri_ust)   # [K, T]
    urun_beden = (beden.astype(np.float64) + 1.0)[None, :]                 # beden_sira 1..5
    fark = np.abs(musteri_beden - urun_beden)
    taban = np.select([fark < 0.5, fark < 1.5], [0.0, BEDEN_FARK_1], default=BEDEN_FARK_2)
    dagin = np.asarray(nufus.beden_dagin)[k_idx].astype(np.float64)[:, None]
    beden_terim = np.where((yon == -1)[None, :], 0.0, taban / dagin)

    return kat + fiyat + beden_terim


# ---------------------------------------------------------------------------
# Müşteri × ürün cinsiyeti (Görev 5b)
# ---------------------------------------------------------------------------

#: Ürün cinsiyet kodu: A'nın `CINSIYETLER` sırası (0 Kadın, 1 Erkek, 2 Unisex).
#: Müşteri `cinsiyet`i B'nin `CINSIYETLER` sırası (0 Kadın, 1 Erkek); iki
#: sıralama Kadın/Erkek'te aynı.
URUN_CINSIYET_SAYISI = len(a_sabitler.CINSIYETLER)
assert list(a_sabitler.CINSIYETLER[:2]) == list(S.CINSIYETLER)
_URUN_CINS_IDX = {c: i for i, c in enumerate(a_sabitler.CINSIYETLER)}


def urun_cinsiyet(urunler) -> np.ndarray:
    """SKU başına ürün cinsiyet kodu (0 Kadın, 1 Erkek, 2 Unisex)."""
    return pd.Series(urunler["cinsiyet"].to_numpy()).map(_URUN_CINS_IDX).to_numpy(dtype=np.int64)


def cinsiyet_ceza_tablosu() -> np.ndarray:
    """`[2 aksesuar mı, 2 müşteri cinsiyeti, 3 ürün cinsiyeti]` log-terim:
    aynı cinsiyet ve Unisex 0, çapraz `CAPRAZ_CINSIYET_CEZA` (aksesuarda ×
    `CAPRAZ_CINSIYET_AKSESUAR_KAT`: A'da aksesuarın cinsiyeti var ama beden
    yok; çanta/şal/kemer hediyesi giyimden olağan)."""
    t = np.zeros((2, 2, URUN_CINSIYET_SAYISI), dtype=np.float64)
    for mus in (0, 1):
        t[0, mus, 1 - mus] = S.CAPRAZ_CINSIYET_CEZA
        t[1, mus, 1 - mus] = S.CAPRAZ_CINSIYET_CEZA * S.CAPRAZ_CINSIYET_AKSESUAR_KAT
    return t


def cinsiyet_terimi(musteri_cins, urun_cins, aksesuar) -> np.ndarray:
    """Müşteri × ürün cinsiyet uyumu log-terimi (yayınlanan biçimlerle):
    `cinsiyet_ceza_tablosu()[aksesuar, musteri_cins, urun_cins]`."""
    t = cinsiyet_ceza_tablosu()
    return t[np.asarray(aksesuar, dtype=np.int64), np.asarray(musteri_cins, dtype=np.int64),
             np.asarray(urun_cins, dtype=np.int64)]


def sku_kodlari(urunler) -> tuple[np.ndarray, np.ndarray]:
    """SKU başına (kalıp indisi `KALIPLAR`, desen indisi `DESENLER`); günlük
    eşleştirici bir kez hesaplayıp `sku_ek_puani_cift`'e verir."""
    kalip_idx = pd.Series(urunler["kalip"].to_numpy()).map(_KALIP_IDX).to_numpy(dtype=np.int64)
    desen_idx = pd.Series(urunler["desen"].to_numpy()).map(_DESEN_IDX).to_numpy(dtype=np.int64)
    return kalip_idx, desen_idx


def sku_ek_puani_cift(nufus, k_idx, sku_idx, oran, kodlar) -> np.ndarray:
    """`sku_ek_puani`'nın çift (eleman eleman) biçimi: `[n]` log-puan eki,
    i. eleman müşteri `k_idx[i]` × SKU `sku_idx[i]` (`oran` [n] ya da
    skaler); `kodlar` = `sku_kodlari(urunler)`. Yoğun matrisin köşegeniyle
    aynı değer (test_tercih)."""
    k_idx = np.asarray(k_idx, dtype=np.int64)
    sku_idx = np.asarray(sku_idx, dtype=np.int64)
    kalip_idx, desen_idx = kodlar
    kalip_p = np.log(np.asarray(nufus.tercih_kalip)[k_idx, kalip_idx[sku_idx]])
    desen_p = np.log(np.asarray(nufus.tercih_desen)[k_idx, desen_idx[sku_idx]])
    indirim = np.asarray(nufus.indirim_duyarlilik)[k_idx].astype(np.float64) * np.asarray(oran, dtype=np.float64)
    return kalip_p + desen_p + indirim


def sku_ek_puani(nufus, k_idx, sku_idx, oran, urunler) -> np.ndarray:
    """`[len(k_idx), len(sku_idx)]` log-puan eki: kalıp + desen eğilimi +
    indirim duyarlılığı × `oran` (SKU başına ya da skaler)."""
    k_idx = np.asarray(k_idx, dtype=np.int64)
    sku_idx = np.asarray(sku_idx, dtype=np.int64)
    kalip, desen = sku_kodlari(urunler)
    kalip_idx, desen_idx = kalip[sku_idx], desen[sku_idx]

    kalip_p = np.log(np.asarray(nufus.tercih_kalip)[k_idx][:, kalip_idx])
    desen_p = np.log(np.asarray(nufus.tercih_desen)[k_idx][:, desen_idx])
    oran_arr = np.broadcast_to(np.asarray(oran, dtype=np.float64), (len(sku_idx),))
    indirim = np.asarray(nufus.indirim_duyarlilik)[k_idx].astype(np.float64)[:, None] * oran_arr[None, :]

    return kalip_p + desen_p + indirim


def urun_puani(nufus, k_idx, sku_idx, girdi, oran=None) -> np.ndarray:
    """`[len(k_idx), len(sku_idx)]` log-puan = `tip_puani` (SKU'nun tipi
    için) + `sku_ek_puani` + `cinsiyet_terimi` (müşteri × ürün cinsiyeti).
    `oran` verilmezse 0 (indirimsiz). Eşleştirici (Görev 5) cinsiyet
    terimini aşama 1'de uygular: grup = (mağaza, tip, ürün cinsiyeti)."""
    urunler = girdi.dunya.urunler
    k_idx = np.asarray(k_idx, dtype=np.int64)
    sku_idx = np.asarray(sku_idx, dtype=np.int64)
    if oran is None:
        oran = np.zeros(len(sku_idx))
    tip = tip_kodu(urunler)[sku_idx]
    aks = np.isin(urunler["alt_kategori"].to_numpy()[sku_idx], list(a_sabitler.AKSESUAR))
    cins = cinsiyet_terimi(np.asarray(nufus.cinsiyet)[k_idx][:, None],
                           urun_cinsiyet(urunler)[sku_idx][None, :], aks[None, :])
    return tip_puani(nufus, k_idx, tip) + sku_ek_puani(nufus, k_idx, sku_idx, oran, urunler) + cins


# ---------------------------------------------------------------------------
# Gizli tamamlayıcılık matrisi (yayımlanmaz)
# ---------------------------------------------------------------------------

#: Alt kategori çiftlerinin (simetrik) çarpanı; diğer bütün çiftler 1,0,
#: aynı alt kategori 0,6 (`tamamlayici_matris` içinde uygulanır).
TAMAMLAYICI: dict[tuple[str, str], float] = {
    ("Elbise", "Çanta"): 2.5,
    ("Elbise", "Kemer"): 1.8,
    ("Jean", "Tişört"): 2.2,
    ("Jean", "Gömlek"): 1.8,
    ("Mont", "Şal"): 2.0,
    ("Mont", "Kazak"): 1.6,
    ("Pantolon", "Gömlek"): 1.8,
    ("Etek", "Bluz"): 2.0,
    ("Şort", "Tişört"): 1.6,
    ("Tulum", "Çanta"): 1.6,
    ("Ceket", "Pantolon"): 1.5,
    ("Sweatshirt", "Jean"): 1.4,
}

AYNI_ALT_CARPANI = 0.6

#: Açık çiftlerin etkin çarpanı `TAMAMLAYICI[çift] ** TAMAMLAYICI_GUC`
#: (log-uzayda ×GUC; köşegen ve nötr çiftler değişmez). KALİBRASYON (Görev
#: 5): müşteri kategori tercihleri sivri (Dirichlet yoğunluğu 10) olduğundan
#: fişler kategoriye göre ayrışır; tamamlayıcılıksız (Elbise, Çanta) birlikte
#: görünmesi bağımsız beklentinin ~0,7'si, GUC 1'de ~1,0 (yalnız ayrışmayı
#: dengeler), GUC 3'te 1,5–1,8, GUC 4'te 1,76–2,09 (KUCUK, 60 gün, 5 B
#: tohumu; bağımsız beklenti fiş boyutları sabit permütasyon; test_ayristir).
TAMAMLAYICI_GUC = 4.0


def tamamlayici_matris() -> np.ndarray:
    """`[17, 17]` log-tamamlayıcılık matrisi (simetrik); köşegen `log(0,6)`,
    açık çiftler `GUC × log(TAMAMLAYICI[çift])`, diğerleri `log(1) = 0`.
    Gizli gerçek budur (eşleştiricinin kullandığı etkin matris)."""
    n = A_ALT
    m = np.ones((n, n), dtype=np.float64)
    np.fill_diagonal(m, AYNI_ALT_CARPANI)
    for (a, b), deger in TAMAMLAYICI.items():
        i, j = _ALT_IDX[a], _ALT_IDX[b]
        m[i, j] = deger ** TAMAMLAYICI_GUC
        m[j, i] = deger ** TAMAMLAYICI_GUC
    return np.log(m)


def tamamlayicilik(sepet_alt: np.ndarray, aday_alt: np.ndarray) -> np.ndarray:
    """`[len(aday_alt)]`: sepetteki alt kategorilerle her adayın toplam
    log-tamamlayıcılığı (boş sepet → 0)."""
    aday_alt = np.asarray(aday_alt, dtype=np.int64)
    sepet_alt = np.asarray(sepet_alt, dtype=np.int64)
    if len(sepet_alt) == 0:
        return np.zeros(len(aday_alt))
    m = tamamlayici_matris()
    return m[sepet_alt][:, aday_alt].sum(axis=0)


# ---------------------------------------------------------------------------
# Ölçüm: müşteri cinsiyeti × ürün cinsiyeti (Görev 5b)
# ---------------------------------------------------------------------------


def cinsiyet_ozeti(nufus, fis: pd.DataFrame, fis_satir: pd.DataFrame, urunler,
                   yalniz_kartli: bool = True) -> dict:
    """Satış satırlarında (adet > 0) müşteri × ürün cinsiyeti ölçüleri.
    `fis` en az fis_id, musteri (ve `yalniz_kartli` ise kart) sütunlarını
    taşır. Cinsiyeti belli ürün = Kadın ya da Erkek (Unisex hariç).
    Döner: `capraz` (cinsiyeti belli, aksesuar hariç birimlerde müşteri ≠
    ürün payı), `capraz_aksesuar` (yalnız aksesuar), `kadin_urun_kadin`
    / `kadin_urun_erkek` (kadın / erkek müşterinin cinsiyeti belli giyim
    birimlerinde kadın ürün payı), `urun_pay` (Kadın, Erkek, Unisex birim
    payı), `musteri_kadin` (birim ağırlıklı kadın müşteri payı)."""
    sat = fis_satir[fis_satir["adet"] > 0]
    fis_id = sat["fis_id"].to_numpy(np.int64)
    fis_ix = fis.set_index("fis_id")
    k = fis_ix["musteri"].to_numpy(np.int64)[np.searchsorted(fis_ix.index.to_numpy(), fis_id)]
    adet = sat["adet"].to_numpy(np.int64)
    if yalniz_kartli:
        kart = fis_ix["kart"].to_numpy(bool)[np.searchsorted(fis_ix.index.to_numpy(), fis_id)]
        k, adet, sku = k[kart], adet[kart], sat["sku"].to_numpy(np.int64)[kart]
    else:
        sku = sat["sku"].to_numpy(np.int64)
    ucins = urunler["cinsiyet"].to_numpy()[sku]
    aks = np.isin(urunler["alt_kategori"].to_numpy()[sku], list(a_sabitler.AKSESUAR))
    mk = np.asarray(nufus.cinsiyet)[k] == 0            # kadın müşteri
    uk, ue = ucins == "Kadın", ucins == "Erkek"
    belli = uk | ue
    capraz = (mk & ue) | (~mk & uk)

    def pay(maske, pay_maske):
        n = adet[maske].sum()
        return float(adet[maske & pay_maske].sum() / n) if n else float("nan")

    giyim = belli & ~aks
    toplam = adet.sum()
    return {
        "capraz": pay(giyim, capraz),
        "capraz_aksesuar": pay(belli & aks, capraz),
        "capraz_tumu": pay(belli, capraz),
        "kadin_urun_kadin": pay(giyim & mk, uk),
        "kadin_urun_erkek": pay(giyim & ~mk, uk),
        "urun_pay": {c: float(adet[ucins == c].sum() / toplam) for c in ("Kadın", "Erkek", "Unisex")},
        "musteri_kadin": float(adet[mk].sum() / toplam),
        "birim": int(toplam),
    }
