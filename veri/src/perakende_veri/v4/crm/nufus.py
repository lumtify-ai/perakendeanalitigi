"""Müşteri nüfusu (spec §2, §4 katılış): arketipler, gizli parametreler,
başlangıç tabanı ve günlük katılış.

`Nufus` sütunsal numpy dizileri tutar: her sütun, kapasitesi ikiye
katlanarak büyüyen bir tamponun `[:K]` görünümüdür (`K` = canlı satır
sayısı; `k` müşteri indisi = satır sırası, hiç değişmez). Görünümler
yazılabilir (ör. `nufus.hayatta[k] = False` tampona yazar), ancak `ekle`
tamponu yeniden ayırabileceğinden sütun referansı `ekle`'den sonra
yeniden okunmalıdır.

Bütün çekilişler argüman olarak verilen `rng` ile yapılır; modülde durum
yok (Görev 7'nin gün döngüsü sayaç üreteçleri geçirir).

Başlangıç tabanı boyutu (`nufus_baslat`)::

    T_m   = Σ_{d<28} U_{m,d} / sepet_hedef_m        (fiş talebi; 2,2 / ONL 1,8)
    e_m   = E_seg(m)[hız × (1 − online_payi)] × 28/365   (müşteri başına mağaza ziyareti)
    N_m   = ⌈1,2 · T_m / e_m⌉                         (fiziksel mağaza m'nin ev müşterisi)
    ONL:  S = Σ_k hız_k × online_payi_k × 28/365 (bütün tabanın online ziyareti);
          eksik 1,2 · T_ONL − S kadar ONL üyesi, e_ONL = E_online[hız × online_payi] × 28/365

Çekilen gerçek parametrelerle hesaplanan ziyaret 1,2 × talebin altında
kalırsa eksik kadar müşteri daha eklenir (döngü), böylece eşitsizlik
beklentide değil çekilen nüfusta sağlanır.
"""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import ClassVar

import numpy as np
import pandas as pd

from .. import sabitler as a_sabitler
from ..takvim import gun_indisi
from . import sabitler as S
from .girdi import ADET, H, Girdi

A = len(S.ARKETIPLER)
SEGMENT_ADLARI: list[str] = list(S.SEGMENT_ARKETIP_KARISIM)
BASLAT_GUN = S.BASLAT_GUN
YIL_GUN = 365.0
AY_GUN = 30.4


# ---------------------------------------------------------------------------
# Arketip tabloları (sabitlerden türetilir; durum değil)
# ---------------------------------------------------------------------------


def _tablo(anahtar: str) -> np.ndarray:
    return np.array([S.ARKETIP_PARAMETRE[a][anahtar] for a in S.ARKETIPLER], dtype=float)


def _normalize(x: np.ndarray) -> np.ndarray:
    return x / x.sum(axis=-1, keepdims=True)


_ZIYARET = _tablo("ziyaret_gamma")           # [A, 2]
_SEPET = _tablo("sepet_ort")                 # [A]
_KART = _tablo("kart_beta")
_ONLINE = _tablo("online_beta")
_TERK = _tablo("terk_beta")
_INDIRIM = _tablo("indirim_beta")
_FIYAT = _normalize(_tablo("fiyat_segment"))  # [A, 3]
_KAT = _normalize(_tablo("kategori"))         # [A, 17]
_KALIP = _normalize(_tablo("kalip"))          # [A, 4]
_DESEN = _normalize(_tablo("desen"))          # [A, 5]
_DAGIN = _tablo("beden_dagin")               # [A]
_YAS = _normalize(_tablo("yas"))              # [A, 5]
_YALNIZ_KADIN = np.array([a in a_sabitler.YALNIZ_KADIN for a in S.ALT_KATEGORILER])
_KARISIM = np.stack([S.SEGMENT_ARKETIP_KARISIM[s] for s in SEGMENT_ADLARI])  # [7 seg, A]


def _beta_ort(t: np.ndarray) -> np.ndarray:
    return t[:, 0] / t.sum(axis=1)


def _kategorik(rng, p: np.ndarray) -> np.ndarray:
    """Satır başına olasılık vektöründen (p [n, k]) bir indis."""
    u = rng.random(len(p))
    return np.minimum((u[:, None] > np.cumsum(p, axis=1)).sum(axis=1), p.shape[1] - 1)


def _dirichlet(rng, alfa: np.ndarray) -> np.ndarray:
    """Satır başına farklı yoğunluklu Dirichlet (gamma normalize), float32."""
    g = rng.standard_gamma(alfa) + 1e-12
    return (g / g.sum(axis=1, keepdims=True)).astype(np.float32)


def _beden_egrisi(kayma: float) -> np.ndarray:
    """A'nın zincir beden eğrisi, mağaza `beden_kayma` × adım kaydırılmış
    (A `talep._beden_tablosu` ile aynı ara değer)."""
    zincir = np.asarray(a_sabitler.BEDEN_PAYLARI_ZINCIR)
    k = len(zincir)
    konum = np.arange(k + 2, dtype=float)
    genis = np.concatenate([[a_sabitler.BEDEN_KENAR], zincir, [a_sabitler.BEDEN_KENAR]])
    p = np.interp(np.arange(1, k + 1) - kayma * a_sabitler.BEDEN_KAYMA_ADIM, konum, genis)
    return p / p.sum()


def _parametre_cek(rng, arketip: np.ndarray, kadin_payi: np.ndarray, beden_kayma: np.ndarray) -> dict:
    """Arketipe göre bireysel gizli parametreler (vektörel)."""
    n = len(arketip)
    a = arketip
    kadin = rng.random(n) < kadin_payi
    cinsiyet = np.where(kadin, 0, 1).astype(np.int8)

    kat_alfa = S.KATEGORI_YOGUNLUK * _KAT[a]
    kat_alfa[~kadin] *= np.where(_YALNIZ_KADIN, S.ERKEK_KADIN_KAT_CARPANI, 1.0)

    egriler = {float(k): np.cumsum(_beden_egrisi(float(k))) for k in np.unique(beden_kayma)}
    u = rng.random(n)
    beden_ust = np.empty(n, dtype=np.int8)
    for k, c in egriler.items():
        s = beden_kayma == k
        beden_ust[s] = 1 + np.minimum(np.searchsorted(c, u[s], side="right"), 4)
    kayma = rng.choice(np.array([-1, 0, 1]), size=n, p=S.ALT_BEDEN_KAYMA)
    beden_alt = np.clip(beden_ust + kayma, 1, 5).astype(np.int8)

    return {
        "yas_grubu": _kategorik(rng, _YAS[a]).astype(np.int8),
        "cinsiyet": cinsiyet,
        "ziyaret_hizi": rng.gamma(_ZIYARET[a, 0], _ZIYARET[a, 1]),
        "sepet_ort": 1.0 + rng.gamma(S.SEPET_SEKIL, (_SEPET[a] - 1.0) / S.SEPET_SEKIL),
        "kart_olasiligi": rng.beta(_KART[a, 0], _KART[a, 1]),
        "online_payi": rng.beta(_ONLINE[a, 0], _ONLINE[a, 1]),
        "terk_p": rng.beta(_TERK[a, 0], _TERK[a, 1]),
        "indirim_duyarlilik": rng.beta(_INDIRIM[a, 0], _INDIRIM[a, 1]),
        "tercih_kat": _dirichlet(rng, kat_alfa),
        "tercih_kalip": _dirichlet(rng, S.OZNITELIK_YOGUNLUK * _KALIP[a]),
        "tercih_desen": _dirichlet(rng, S.OZNITELIK_YOGUNLUK * _DESEN[a]),
        "fiyat_segment_egilim": _dirichlet(rng, S.FIYAT_YOGUNLUK * _FIYAT[a]),
        "beden_ust": beden_ust,
        "beden_alt": beden_alt,
        "beden_dagin": _DAGIN[a] * rng.lognormal(0.0, S.BEDEN_DAGIN_SIGMA, n),
    }


def arketip_ornegi(rng, n_her: int) -> SimpleNamespace:
    """Mağaza bağlamı olmadan her arketipten `n_her` müşterinin
    parametreleri (inceleme ve test için; kadın payı 0,55, beden kayması 0)."""
    arketip = np.repeat(np.arange(A), n_her).astype(np.int8)
    n = len(arketip)
    p = _parametre_cek(rng, arketip, np.full(n, 0.55), np.zeros(n))
    return SimpleNamespace(arketip=arketip, **p)


def karisim_ozeti(agirlik: np.ndarray | None = None) -> dict:
    """Arketip karışımının beklenen ortalamaları (varsayılan ağırlık: fiziksel
    segment karışımlarının eşit ortalaması): yıllık ziyaret, ziyaret ağırlıklı
    mağaza/online sepet ve mağaza kart okutma olasılığı."""
    if agirlik is None:
        agirlik = _KARISIM[[SEGMENT_ADLARI.index(s) for s in a_sabitler.SEGMENTLER]].mean(axis=0)
    w = np.asarray(agirlik, dtype=float)
    hiz = _ZIYARET.prod(axis=1)
    onl = _beta_ort(_ONLINE)
    mag = w * hiz * (1 - onl)
    on = w * hiz * onl
    return {
        "ziyaret": float((w * hiz).sum()),
        "sepet_magaza": float((mag * _SEPET).sum() / mag.sum()),
        "sepet_online": float(S.ONLINE_SEPET_CARPANI * (on * _SEPET).sum() / on.sum()),
        "kart_magaza": float((mag * _beta_ort(_KART)).sum() / mag.sum()),
        "terk_aylik": float((w * _beta_ort(_TERK)).sum()),
    }


# ---------------------------------------------------------------------------
# Mağaza bilgisi (A'dan salt okunur türetilir)
# ---------------------------------------------------------------------------


def magaza_gunluk_adet(girdi: Girdi) -> np.ndarray:
    """[D, M] gün × mağaza pozitif satış adedi (iadeler hariç)."""
    w = girdi.dunya
    M = len(w.magazalar)
    hm = np.asarray(w.hucre_magaza, dtype=np.int64)
    out = np.zeros((girdi.D, M), dtype=np.float64)
    for d, s in enumerate(girdi.satis_gun):
        if len(s):
            out[d] = np.bincount(hm[s[:, H].astype(np.int64)], weights=s[:, ADET], minlength=M)
    return out


def magaza_kadin_payi(girdi: Girdi) -> np.ndarray:
    """[M] mağazanın kadın müşteri payı (Görev 5b): A'nın o mağazadaki bütün
    pozitif satışında Kadın / (Kadın + Erkek) birim payı (Unisex hariç) +
    `KADIN_HEDIYE_DUZELTME`, [0, 1]'e kırpılmış. Eşleştirme çapraz cinsiyete
    ceza verdiğinden (`tercih.cinsiyet_terimi`) müşteri karışımı satılan
    ürün karışımına uymalı; yoksa ceza kaçınılmaz çapraz atamaya döner.
    Hiç satışı olmayan mağazada A'nın gizli `kadin_payi` değeri."""
    w = girdi.dunya
    M = len(w.magazalar)
    hm = np.asarray(w.hucre_magaza, dtype=np.int64)
    hs = np.asarray(w.hucre_sku, dtype=np.int64)
    cins = w.urunler["cinsiyet"].to_numpy()
    kadin_s = (cins == "Kadın").astype(np.float64)
    erkek_s = (cins == "Erkek").astype(np.float64)
    kad = np.zeros(M)
    erk = np.zeros(M)
    for s in girdi.satis_gun:
        if len(s):
            c = s[:, H].astype(np.int64)
            m, sku, adet = hm[c], hs[c], s[:, ADET]
            kad += np.bincount(m, weights=adet * kadin_s[sku], minlength=M)
            erk += np.bincount(m, weights=adet * erkek_s[sku], minlength=M)
    gm = w.gizli_magaza.set_index("magaza_id").loc[w.magazalar["magaza_id"]]
    pay = gm["kadin_payi"].to_numpy(dtype=float).copy()
    satan = kad + erk > 0
    pay[satan] = kad[satan] / (kad[satan] + erk[satan]) + S.KADIN_HEDIYE_DUZELTME
    return np.clip(pay, 0.0, 1.0)


def _gun(tarih, bos: int) -> int:
    return bos if pd.isna(tarih) else gun_indisi(tarih)


def _katilis_carpani(w, D: int, acilis: np.ndarray) -> np.ndarray:
    """[D, M] kampanya (bölgesi kapsanan; BF ×3, diğer ×1,5, en büyüğü) ×
    açılış dalgası (ilk 12 hafta ×3)."""
    M = len(w.magazalar)
    bolge = w.magazalar["bolge"].to_numpy()
    online = (w.magazalar["tip"] == "Online").to_numpy()
    kamp = np.ones((D, M))
    for k in w.kampanya.itertuples():
        b = max(gun_indisi(k.baslangic), 0)
        s = min(gun_indisi(k.bitis) + 1, D)
        if b >= s:
            continue
        if k.kapsam_bolge:
            m = np.isin(bolge, k.kapsam_bolge.split(",")) & ~online
        else:
            m = np.ones(M, dtype=bool)
        c = S.KATILIS_BF_CARPANI if k.tip == "black_friday" else S.KATILIS_KAMPANYA_CARPANI
        kamp[b:s, m] = np.maximum(kamp[b:s, m], c)
    dalga = S.KATILIS_ACILIS_HAFTA * 7
    for m in np.flatnonzero(~online):
        b, s = max(acilis[m], 0), min(acilis[m] + dalga, D)
        if b < s:
            kamp[b:s, m] *= S.KATILIS_ACILIS_CARPANI
    return kamp


@dataclass(frozen=True, eq=False)
class MagazaBilgi:
    """Mağaza başına sabit bilgi. `il` fiziksel mağazanın `il_adlari`
    indisi (ONL −1); `onl_il_p` ONL üyesinin il dağılımı (ilin fiziksel
    mağaza sayısıyla orantılı, nüfus vekili); `gunluk_adet` [D, M];
    `gunluk_kumulatif` [D+1, M]; `katilis_carpani` [D, M]."""

    M: int
    onl: int
    segment: np.ndarray        # [M] SEGMENT_ADLARI indisi
    il: np.ndarray             # [M]
    il_adlari: tuple
    onl_il_p: np.ndarray
    kadin_payi: np.ndarray     # [M]
    beden_kayma: np.ndarray    # [M]
    acilis_gun: np.ndarray     # [M]
    kapanis_gun: np.ndarray    # [M] (açıksa büyük sayı)
    gunluk_adet: np.ndarray
    gunluk_kumulatif: np.ndarray
    katilis_carpani: np.ndarray


def magaza_bilgisi(girdi: Girdi) -> MagazaBilgi:
    w = girdi.dunya
    mag = w.magazalar
    M = len(mag)
    online = (mag["tip"] == "Online").to_numpy()
    assert online[-1] and online.sum() == 1, "ONL son satır olmalı"
    gm = w.gizli_magaza.set_index("magaza_id").loc[mag["magaza_id"]]
    segment = np.array([SEGMENT_ADLARI.index(s) for s in gm["segment"]], dtype=np.int64)
    sehir = mag["sehir"].to_numpy()
    il_adlari = tuple(sorted(set(sehir[~online])))
    il = np.array([il_adlari.index(s) if not o else -1 for s, o in zip(sehir, online)], dtype=np.int64)
    sayi = np.bincount(il[~online], minlength=len(il_adlari)).astype(float)
    kadin = magaza_kadin_payi(girdi)
    acilis = np.array([_gun(t, -10**6) for t in mag["acilis_tarihi"]], dtype=np.int64)
    kapanis = np.array([_gun(t, 10**6) for t in mag["kapanis_tarihi"]], dtype=np.int64)
    adet = magaza_gunluk_adet(girdi)
    kum = np.vstack([np.zeros((1, M)), np.cumsum(adet, axis=0)])
    return MagazaBilgi(
        M=M, onl=M - 1, segment=segment, il=il, il_adlari=il_adlari, onl_il_p=sayi / sayi.sum(),
        kadin_payi=kadin, beden_kayma=gm["beden_kayma"].to_numpy(dtype=float),
        acilis_gun=acilis, kapanis_gun=kapanis, gunluk_adet=adet, gunluk_kumulatif=kum,
        katilis_carpani=_katilis_carpani(w, girdi.D, acilis),
    )


# ---------------------------------------------------------------------------
# Nüfus
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class Nufus:
    """Sütun dizileri uzunluk K (tamponun görünümü). Kodlar: `arketip`
    `sabitler.ARKETIPLER`, `yas_grubu` `YAS_GRUPLARI`, `cinsiyet`
    `CINSIYETLER`, `kayit_kanali` `KAYIT_KANALLARI` (0 mağaza, 1 online),
    `il` `il_adlari` indisleri; `ev_magaza` A'nın mağaza indisi (ONL üyesi:
    ONL). `tercih_*` satırları olasılık vektörü (float32). `terk_gun` −1 =
    hayatta. `gorunur_mu`: kartlı ya da online üyeli — ilk kart okutulan ya
    da online sipariş anında True yapılır (Görev 5–7). `gorunur_gun`: o ilk
    kimlikli olayın günü (int32), −1 = henüz görünür değil; ısınma
    tabanında da simülasyonda gözlenene kadar −1 kalır; Görev 7 yazar.
    `GOZLEMLENEBILIR` yayımlanabilir sütunlardır (`musteri` tablosu); geri
    kalan her sütun gizlidir. Kişisel veri yok."""

    GOZLEMLENEBILIR: ClassVar[tuple[str, ...]] = (
        "ev_magaza", "il", "yas_grubu", "cinsiyet", "kayit_gun", "kayit_kanali", "gorunur_gun",
    )

    SUTUNLAR: ClassVar[dict[str, tuple[type, int]]] = {
        "arketip": (np.int8, 0),
        "ev_magaza": (np.int16, 0),
        "il": (np.int16, 0),
        "yas_grubu": (np.int8, 0),
        "cinsiyet": (np.int8, 0),
        "kayit_gun": (np.int32, 0),
        "kayit_kanali": (np.int8, 0),
        "kart_olasiligi": (np.float64, 0),
        "ziyaret_hizi": (np.float64, 0),
        "sepet_ort": (np.float64, 0),
        "online_payi": (np.float64, 0),
        "terk_p": (np.float64, 0),
        "tercih_kat": (np.float32, len(S.ALT_KATEGORILER)),
        "tercih_kalip": (np.float32, len(S.KALIPLAR)),
        "tercih_desen": (np.float32, len(S.DESENLER)),
        "fiyat_segment_egilim": (np.float32, len(S.FIYAT_SEGMENTLERI)),
        "indirim_duyarlilik": (np.float64, 0),
        "beden_ust": (np.int8, 0),
        "beden_alt": (np.int8, 0),
        "beden_dagin": (np.float64, 0),
        "hayatta": (np.bool_, 0),
        "terk_gun": (np.int32, 0),
        "gorunur_mu": (np.bool_, 0),
        "gorunur_gun": (np.int32, 0),
    }

    magaza: MagazaBilgi
    il_adlari: tuple
    K: int = 0
    arketip: np.ndarray = None
    ev_magaza: np.ndarray = None
    il: np.ndarray = None
    yas_grubu: np.ndarray = None
    cinsiyet: np.ndarray = None
    kayit_gun: np.ndarray = None
    kayit_kanali: np.ndarray = None
    kart_olasiligi: np.ndarray = None
    ziyaret_hizi: np.ndarray = None
    sepet_ort: np.ndarray = None
    online_payi: np.ndarray = None
    terk_p: np.ndarray = None
    tercih_kat: np.ndarray = None
    tercih_kalip: np.ndarray = None
    tercih_desen: np.ndarray = None
    fiyat_segment_egilim: np.ndarray = None
    indirim_duyarlilik: np.ndarray = None
    beden_ust: np.ndarray = None
    beden_alt: np.ndarray = None
    beden_dagin: np.ndarray = None
    hayatta: np.ndarray = None
    terk_gun: np.ndarray = None
    gorunur_mu: np.ndarray = None
    gorunur_gun: np.ndarray = None
    #: Var olan satırlarda `ev_magaza` ya da `online_payi` değiştiren her kod
    #: (`yasam.ev_kapanisi`) `ev_degisti()` çağırır; ziyaretçi aday yapısı
    #: (`ziyaretci.Adaylar`) bu sayaçla yeniden kurulur. `ekle` saymaz.
    degisim_sayaci: int = 0
    _tampon: dict = field(default_factory=dict, repr=False)

    def ev_degisti(self) -> None:
        self.degisim_sayaci += 1

    @classmethod
    def bos(cls, magaza: MagazaBilgi, kapasite: int = 1024) -> "Nufus":
        n = cls(magaza=magaza, il_adlari=magaza.il_adlari)
        n._ayir(max(int(kapasite), 1))
        return n

    @property
    def kapasite(self) -> int:
        return len(self._tampon["arketip"])

    def _ayir(self, kapasite: int) -> None:
        for ad, (tip, gen) in self.SUTUNLAR.items():
            sekil = (kapasite, gen) if gen else (kapasite,)
            yeni = np.zeros(sekil, dtype=tip)
            eski = self._tampon.get(ad)
            if eski is not None:
                yeni[: self.K] = eski[: self.K]
            self._tampon[ad] = yeni
        self._goster()

    def _goster(self) -> None:
        for ad in self.SUTUNLAR:
            setattr(self, ad, self._tampon[ad][: self.K])

    def ekle(self, rng, n: int, ev_magaza, kayit_gun, kayit_kanali=None) -> np.ndarray:
        """`n` yeni müşteri (vektörel); `ev_magaza`, `kayit_gun`,
        `kayit_kanali` skaler ya da uzunluk-n. Arketip ev mağazasının
        segment karışımından (ONL: "online"), parametreler arketipten; il
        fiziksel ev mağazasının şehri, ONL üyesinde il dağılımından.
        `kayit_kanali` verilmezse ev mağazası ONL ise 1. Yeni satırların
        indislerini döndürür."""
        n = int(n)
        K0 = self.K
        if n <= 0:
            return np.arange(K0, K0)
        mb = self.magaza
        ev = np.broadcast_to(np.asarray(ev_magaza, dtype=np.int64), (n,))
        onl = ev == mb.onl
        arketip = _kategorik(rng, _KARISIM[mb.segment[ev]]).astype(np.int8)
        il = mb.il[ev].copy()
        if onl.any():
            il[onl] = rng.choice(len(mb.il_adlari), size=int(onl.sum()), p=mb.onl_il_p)
        p = _parametre_cek(rng, arketip, mb.kadin_payi[ev], mb.beden_kayma[ev])
        if kayit_kanali is None:
            kayit_kanali = onl.astype(np.int8)

        if K0 + n > self.kapasite:
            kap = self.kapasite
            while kap < K0 + n:
                kap *= 2
            self._ayir(kap)
        s = slice(K0, K0 + n)
        t = self._tampon
        t["arketip"][s] = arketip
        t["ev_magaza"][s] = ev
        t["il"][s] = il
        t["kayit_gun"][s] = kayit_gun
        t["kayit_kanali"][s] = kayit_kanali
        for ad, deger in p.items():
            t[ad][s] = deger
        t["hayatta"][s] = True
        t["terk_gun"][s] = -1
        t["gorunur_mu"][s] = False
        t["gorunur_gun"][s] = -1
        self.K = K0 + n
        self._goster()
        return np.arange(K0, K0 + n)


# ---------------------------------------------------------------------------
# Başlangıç tabanı
# ---------------------------------------------------------------------------


def _sepet_hedefi(M: int) -> np.ndarray:
    h = np.full(M, S.SEPET_HEDEF_MAGAZA)
    h[-1] = S.SEPET_HEDEF_ONLINE
    return h


def fis_talebi(girdi: Girdi, bas: int, son: int, adet: np.ndarray | None = None) -> np.ndarray:
    """[M] günler [bas, son) beklenen fiş sayısı: adet ÷ sepet hedefi."""
    if adet is None:
        adet = magaza_gunluk_adet(girdi)
    return adet[bas:son].sum(axis=0) / _sepet_hedefi(adet.shape[1])


def beklenen_ziyaret(nufus: Nufus, gun: int) -> np.ndarray:
    """[M] hayatta müşterilerin `gun` günde beklenen ziyareti: fiziksel
    mağaza = ev müşterilerinin mağaza ziyareti (hız × (1 − online_payi));
    ONL = bütün hayatta müşterilerin online ziyareti (hız × online_payi)."""
    mb = nufus.magaza
    h = nufus.hayatta
    f = gun / YIL_GUN
    ev = nufus.ev_magaza[h].astype(np.int64)
    hiz = nufus.ziyaret_hizi[h]
    onl = nufus.online_payi[h]
    fiz = ev != mb.onl
    out = np.bincount(ev[fiz], weights=hiz[fiz] * (1 - onl[fiz]), minlength=mb.M) * f
    out[mb.onl] = (hiz * onl).sum() * f
    return out


def _musteri_basina(segment: np.ndarray, online: bool) -> np.ndarray:
    """Segment karışımına göre müşteri başına beklenen yıllık ziyaret
    (mağaza ya da online kanalı)."""
    hiz = _ZIYARET.prod(axis=1)
    onl = _beta_ort(_ONLINE)
    kanal = hiz * (onl if online else 1 - onl)
    return _KARISIM[segment] @ kanal


def nufus_baslat(rng, girdi: Girdi) -> Nufus:
    """Isınma başı (gün 0) mevcut taban; boyut modül docstring'indeki
    formülle. `kayit_gun` < 0: hayatta kalanların kıdemi aylık terk
    olasılığıyla üstel (ortalama 30,4 / terk_p gün), ev mağazasının açılışı
    ve 10 yılla sınırlı."""
    mb = magaza_bilgisi(girdi)
    T = fis_talebi(girdi, 0, BASLAT_GUN, mb.gunluk_adet)
    hedef = S.BASLAT_PAYI * T
    f = BASLAT_GUN / YIL_GUN
    fiz = np.arange(mb.M) != mb.onl
    e = _musteri_basina(mb.segment, online=False) * f
    ilk = np.where(fiz & (T > 0), np.ceil(hedef / e), 0).astype(np.int64)
    nufus = Nufus.bos(mb, kapasite=int(ilk.sum() * 1.3) + 1024)

    eksik = ilk
    for _ in range(20):
        if not eksik.any():
            break
        nufus.ekle(rng, int(eksik.sum()), np.repeat(np.arange(mb.M), eksik), kayit_gun=0)
        z = beklenen_ziyaret(nufus, BASLAT_GUN)
        eksik = np.where(fiz & (z < hedef), np.ceil((hedef - z) / e), 0).astype(np.int64)

    e_onl = float(_musteri_basina(mb.segment[[mb.onl]], online=True)[0]) * f
    for _ in range(20):
        z = beklenen_ziyaret(nufus, BASLAT_GUN)[mb.onl]
        if z >= hedef[mb.onl]:
            break
        nufus.ekle(rng, int(np.ceil((hedef[mb.onl] - z) / e_onl)), mb.onl, kayit_gun=0)

    ev = nufus.ev_magaza.astype(np.int64)
    ust = np.minimum(S.KAYIT_GECMISI_UST_GUN, np.maximum(-mb.acilis_gun[ev], 1))
    kidem = np.ceil(rng.exponential(AY_GUN / nufus.terk_p))
    nufus.kayit_gun[:] = -np.clip(kidem, 1, ust).astype(np.int32)
    return nufus


# ---------------------------------------------------------------------------
# Katılış
# ---------------------------------------------------------------------------


def hacim28(mb: MagazaBilgi, d: int) -> np.ndarray:
    """[M] son 28 günün (bugün dahil; açılıştan önceki günler sayılmaz)
    günlük ortalama adedi × 28."""
    bas = np.maximum(np.maximum(d - S.KATILIS_PENCERE + 1, mb.acilis_gun), 0)
    n = d + 1 - bas
    kum = mb.gunluk_kumulatif
    top = kum[d + 1] - kum[np.minimum(bas, d + 1), np.arange(mb.M)]
    return np.where(n > 0, top / np.maximum(n, 1) * S.KATILIS_PENCERE, 0.0)


def katilis_beklenen(girdi: Girdi, nufus: Nufus, d: int) -> np.ndarray:
    """[M] gün d'nin beklenen yeni müşterisi: taban × V28 × (kampanya/BF ×
    açılış dalgası); o gün satışı olmayan (kapalı, tadilatta) mağazada 0."""
    mb = nufus.magaza
    taban = np.full(mb.M, S.KATILIS_TABAN)
    taban[mb.onl] = S.KATILIS_TABAN_ONLINE
    lam = taban * hacim28(mb, d) * mb.katilis_carpani[d]
    return np.where(mb.gunluk_adet[d] > 0, lam, 0.0)


def katilis_sayisi(rng, girdi: Girdi, nufus: Nufus, d: int) -> np.ndarray:
    """[M] gün d'de mağaza başına yeni müşteri sayısı (Poisson); ONL
    satırı online üyelik akışıdır. Eklemek çağıranın işi (`nufus.ekle`)."""
    return rng.poisson(katilis_beklenen(girdi, nufus, d)).astype(np.int64)
