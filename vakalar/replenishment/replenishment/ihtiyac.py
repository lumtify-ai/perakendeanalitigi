"""Kural tabanlı ihtiyaç hesabı (v4): haftalık satış, özel gün katsayısı,
güvenlik stoku aileleri, kural öngörüsü, mağazanın beden dağılımı, bedene bölme.

Girdi her yerde `[gun, C]` günlük matris (C = dünyanın hücre sayısı, ONL
hücreleri dahil): `satis` brüt satış, `stoklu` bool "o gün satış öncesi stok
> 0". `Gorunum.satis_gecmisi` / `stoklu_gecmisi` ya da çevrimdışı
`kaynak.gunluk_satis_matrisi` / `gunluk_stoklu_matrisi` ile aynı anlamdadır.
Mağaza–option (OC) toplamları `kaynak.Harita`dan (`harita.oc`: hücrenin OC
indisi) `bincount` ile alınır; option başına beden sayısı sabit varsayılmaz
(tek bedenli STD option'lar, aksesuar).

**Zaman.** Karar günü `karar_gunu` (pazartesi sabahı) satır indisidir ve o gün
dahil sonrasındaki satırlar HİÇ okunmaz: "son 7 gün" = `[karar−7, karar−1]`.
`takvim` (dünyanın `takvim` tablosu: `tarih`, `tatil_mi`, `black_friday_mi`) satırı matrisin
satırıyla aynı güne denk gelmelidir (çevrimdışı matris `bas` gününden
başlıyorsa takvim de o günden kesilir). Takvim geleceği bilir (tatiller
önceden ilan edilir): `hafta_katsayisi` `karar+7`'ye kadar bakar.

**Maliyet.** Karar fonksiyonları her pazartesi çağrılır; yalnız son
7 / 28 / 56 günlük pencereyi okurlar. Tam geçmiş geçen iki fonksiyon
(`ozel_gun_katsayilari`, `magaza_beden_paylari`) oyundan önce bir kez koşar.

**Sansür düzeltmesi (`stoklu`).** Stoksuz günde satış gözlenemez; hız
`satış / stoklu gün` olur. OC'nin "stoklu günü": hücrelerinden en az biri o gün
stoklu olan gün. Çevrimdışı matrisin iki kusuru bu tanımla kapanır: satış
olan gün stoklu sayılır (satış stoksuz olmaz; ortak tablo ~4,9 bin hücre-günü
"uygun" saymaz) ve verinin son üç günü (matriste kalıcı olarak `False`) zaten
karar penceresine girmez. Pencerede stoklu gün 0 ise satış da 0'dır ve hız
0 alınır: o pencere talep hakkında hiçbir şey söylemez (sıfıra bölme yok);
tamamen stoksuz bir OC'ye talebi başka bir bilgi (ör. kategori ortalaması)
vermelidir, bu modül uydurmaz.

Bu modül `perakende_veri`'yi, `replenishment.motor`'u ve hakemi içe aktarmaz.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .kaynak import Harita

_Z = 1.65   # istatistik ailesi: %95 hizmet düzeyi z değeri
BF_SONEKI = "|black_friday"   # Black Friday katsayısının anahtarı: "<üst kategori>|black_friday"


# ---------------------------------------------------------------------------
# Takvim
# ---------------------------------------------------------------------------


def _ozel_gunler(takvim: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(resmî tatil, Black Friday) bool dizileri. v4 takviminde BF cuması da
    `tatil_mi`dir ama trafiği tatilin tersidir (ortak `carpanlar`); ölçüm de
    ayırır (tatil katsayısı ≈ 0,6, BF günü ≈ 3,5 kat). BF ayrı bir özel gündür,
    tatil katsayısına karışmaz. `black_friday_mi` sütunu yoksa (v2 biçimi)
    BF boştur."""
    tatil = takvim["tatil_mi"].to_numpy(dtype=bool)
    bf = takvim["black_friday_mi"].to_numpy(dtype=bool) if "black_friday_mi" in takvim else np.zeros_like(tatil)
    return tatil & ~bf, bf


def _haftanin_gunu(takvim: pd.DataFrame) -> np.ndarray:
    """Pazartesi 0 … pazar 6 (`takvim.tarih`'ten; satır 0'ın hangi gün olduğu önemsiz)."""
    return pd.DatetimeIndex(takvim["tarih"]).weekday.to_numpy()


# ---------------------------------------------------------------------------
# Hücre → OC toplamaları (yalnız istenen pencere)
# ---------------------------------------------------------------------------


def _oc_say(harita: Harita) -> int:
    return len(harita.oc_magaza)


def _oc_topla(x_c: np.ndarray, harita: Harita) -> np.ndarray:
    """float[OC]: `[C]` vektörün OC toplamı."""
    return np.bincount(harita.oc, weights=x_c, minlength=_oc_say(harita))


def _pencere(satis: np.ndarray, harita: Harita, bas: int, bit: int) -> np.ndarray:
    """float[OC]: `[bas, bit)` satırlarının OC satış toplamı. `bas < 0` ise 0:
    veri başından önceye taşan pencere bütünüyle 0 sayılır, kısmi toplam alınmaz."""
    if bas < 0:
        return np.zeros(_oc_say(harita))
    return _oc_topla(satis[bas:bit].sum(axis=0, dtype=np.int64), harita)


def stoklu_gun(
    stoklu: np.ndarray, satis: np.ndarray, harita: Harita, karar_gunu: int, gun: int
) -> np.ndarray:
    """float[OC]: `[karar−gun, karar−1]` içinde OC'nin stoklu gün sayısı —
    hücrelerinden en az biri stoklu ya da satış yapmış gün (satış stoksuz
    olmaz). Veri başından önceye taşan kısım sayılmaz."""
    bas = max(karar_gunu - gun, 0)
    sonuc = np.zeros(_oc_say(harita))
    for d in range(bas, karar_gunu):
        var = stoklu[d] | (satis[d] > 0)
        gorulen = np.zeros(_oc_say(harita), dtype=bool)
        gorulen[harita.oc[var]] = True
        sonuc += gorulen
    return sonuc


def _hiz(toplam: np.ndarray, gunler: np.ndarray) -> np.ndarray:
    """toplam / gün; gün 0 ise 0 (modül belgesi: sansürlü tam pencere)."""
    hiz = np.zeros_like(toplam)
    np.divide(toplam, gunler, out=hiz, where=gunler > 0)
    return hiz


def haftalik(satis: np.ndarray, harita: Harita, karar_gunu: int, hafta: int) -> np.ndarray:
    """float[hafta, OC]: karar gününden önceki `hafta` tane 7 günlük blokta OC
    satış toplamı; en yeni blok son satırda (`[karar−7, karar−1]`). Veri
    başlangıcından önceye taşan blok 0."""
    sonuc = np.zeros((hafta, _oc_say(harita)))
    for i in range(hafta):
        bit = karar_gunu - 7 * (hafta - 1 - i)   # blok [bit−7, bit)
        sonuc[i] = _pencere(satis, harita, bit - 7, bit)
    return sonuc


# ---------------------------------------------------------------------------
# Özel gün katsayıları
# ---------------------------------------------------------------------------


def _kategori_gunluk(
    satis: np.ndarray, harita: Harita, n: int
) -> tuple[np.ndarray, np.ndarray]:
    """(kategoriler[K], float[n, K]): fiziksel hücrelerin üst kategori başına
    günlük satışı, ilk `n` satır. Online hücreler dışarıda: online trafik
    tatil günü fiziksel mağaza gibi davranmaz."""
    kategoriler, kat_o = np.unique(harita.option_kategori, return_inverse=True)
    K = len(kategoriler)
    kat_c = np.where(harita.hucre_online, K, kat_o.reshape(-1)[harita.hucre_option])  # K: çöp kutusu
    sonuc = np.zeros((n, K))
    adim = 64
    for bas in range(0, n, adim):
        blok = satis[bas : min(bas + adim, n)]
        b = blok.shape[0]
        anahtar = (kat_c[None, :] + (K + 1) * np.arange(b)[:, None]).ravel()
        toplam = np.bincount(anahtar, weights=blok.ravel(), minlength=b * (K + 1))
        sonuc[bas : bas + b] = toplam.reshape(b, K + 1)[:, :K]
    return kategoriler, sonuc


def ozel_gun_katsayilari(
    satis: np.ndarray, harita: Harita, takvim: pd.DataFrame, bit_gunu: int
) -> dict[str, float]:
    """üst kategori → katsayı (fiziksel mağazalar).

    `bit_gunu`'nden önceki (gün < bit_gunu) her resmî tatil günü h için:
    kategori satışı(h) / aynı haftanın gününe denk gelen, h'nin ±14 günü
    içindeki özel olmayan (tatil ya da BF olmayan) günlerin ortalama kategori
    satışı. Katsayı bu oranların ortalaması. Karşılaştırma penceresi de
    `bit_gunu`'nde kırpılır: h'ye yakın bir tatilin +14 penceresi `bit_gunu`'nü
    aşarsa gerçekleşmemiş günler paydaya sızmaz. Karşılaştırma günü olmayan ya
    da payda 0 olan gün o kategoride atlanır.

    Black Friday günleri aynı yöntemle ayrı ölçülür ve `"<kategori>|black_friday"`
    anahtarıyla döner (`BF_SONEKI`); tatil katsayısına karışmaz (bkz. `_ozel_gunler`)."""
    if bit_gunu > satis.shape[0] or bit_gunu > len(takvim):
        raise ValueError(f"bit_gunu {bit_gunu}: satış {satis.shape[0]}, takvim {len(takvim)} satır")
    kategoriler, kat_gunluk = _kategori_gunluk(satis, harita, bit_gunu)
    tatil, bf = _ozel_gunler(takvim)
    ozel, hg = tatil | bf, _haftanin_gunu(takvim)

    sonuc: dict[str, float] = {}
    for sonek, olay in (("", tatil), (BF_SONEKI, bf)):
        oranlar: dict[str, list] = {str(kat): [] for kat in kategoriler}
        for h in np.flatnonzero(olay[:bit_gunu]):
            pencere = np.arange(max(h - 14, 0), min(h + 14, bit_gunu - 1) + 1)
            aday = pencere[(hg[pencere] == hg[h]) & ~ozel[pencere]]
            if aday.size == 0:
                continue
            for i, kat in enumerate(kategoriler):
                payda = kat_gunluk[aday, i].mean()
                if payda > 0:
                    oranlar[str(kat)].append(kat_gunluk[h, i] / payda)
        sonuc |= {kat + sonek: float(np.mean(o)) for kat, o in oranlar.items() if o}
    return sonuc


def hafta_katsayisi(
    takvim: pd.DataFrame, karar_gunu: int, gun_katsayisi: float, bf_katsayisi: float = 1.0
) -> float:
    """(Σ_{karar+1..karar+7} f) / (Σ_{karar−7..karar−1} f); resmî tatil günü
    f = gun_katsayisi, Black Friday f = bf_katsayisi, diğerleri 1. Pay: teslimden
    (ertesi gün) bir sonraki teslime kadar örtülecek hafta; payda: öngörünün
    dayandığı gözlem haftası."""
    tatil, bf = _ozel_gunler(takvim)
    if karar_gunu + 7 >= len(tatil):
        raise ValueError(f"takvim karar_gunu+7 ({karar_gunu + 7}) gününü kapsamıyor ({len(tatil)} satır)")
    f = np.where(bf, bf_katsayisi, np.where(tatil, gun_katsayisi, 1.0))

    payda = f[max(karar_gunu - 7, 0) : max(karar_gunu, 0)].sum()
    return 1.0 if payda == 0 else float(f[karar_gunu + 1 : karar_gunu + 8].sum() / payda)


# ---------------------------------------------------------------------------
# Güvenlik stoku, öngörü
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuvenlikStoku:
    aile: Literal["sabit", "ros", "istatistik"]
    deger: float = 0.0   # sabit: adet; ros: gün; istatistik: kullanılmaz (z = 1,65)


def guvenlik_stoku(
    satis: np.ndarray,
    harita: Harita,
    karar_gunu: int,
    ayar: GuvenlikStoku,
    stoklu: np.ndarray | None = None,
) -> np.ndarray:
    """float[OC]. sabit: `deger`. ros: son 28 gün satışı / 28 × `deger`.
    istatistik: 1,65 × std(son 8 haftalık toplam, ddof=1) × √1.

    `stoklu` verilirse ros ailesinde 28 yerine son 28 günün stoklu gün sayısına
    bölünür (sansür düzeltmesi; stoklu gün 0 ise 0). İstatistik ailesi
    `stoklu`'yu kullanmaz: yayılım, düzeltilmemiş haftalık satıştan ölçülür."""
    OC = _oc_say(harita)
    if ayar.aile == "sabit":
        return np.full(OC, ayar.deger, dtype=float)
    if ayar.aile == "ros":
        toplam = _pencere(satis, harita, karar_gunu - 28, karar_gunu)
        if stoklu is None:
            return toplam / 28.0 * ayar.deger
        return _hiz(toplam, stoklu_gun(stoklu, satis, harita, karar_gunu, 28)) * ayar.deger
    if ayar.aile == "istatistik":
        return _Z * haftalik(satis, harita, karar_gunu, 8).std(axis=0, ddof=1)
    raise ValueError(f"Bilinmeyen güvenlik stoku ailesi: {ayar.aile}")


def kural_ongorusu(
    satis: np.ndarray,
    harita: Harita,
    karar_gunu: int,
    katsayilar: dict[str, float],
    stoklu: np.ndarray | None = None,
    *,
    takvim: pd.DataFrame,
) -> np.ndarray:
    """float[OC]: son 7 gün satışı × hafta katsayısı. Hafta katsayısı option'ın üst
    kategorisinin tatil katsayısıyla (`katsayilar[kategori]`) ve Black Friday
    katsayısıyla (`katsayilar[kategori + BF_SONEKI]`) hesaplanır; anahtarı
    olmayan katsayı 1.

    `stoklu` verilirse (son 7 gün satışı / son 7 günün stoklu günü) × 7 × hafta
    katsayısı: sansürlü talep düzeltmesi; stoklu gün 0 ise 0. Verilmezse
    takvim gününe bölme korunur.

    `takvim` (anahtar sözcük): hafta katsayısı geleceğin tatillerini ondan
    okur (`hafta_katsayisi`)."""
    son7 = _pencere(satis, harita, karar_gunu - 7, karar_gunu)
    if stoklu is not None:
        son7 = _hiz(son7, stoklu_gun(stoklu, satis, harita, karar_gunu, 7)) * 7.0
    kategoriler, kat_o = np.unique(harita.option_kategori, return_inverse=True)
    carpan = np.array([
        hafta_katsayisi(takvim, karar_gunu, katsayilar.get(str(k), 1.0), katsayilar.get(str(k) + BF_SONEKI, 1.0))
        for k in kategoriler])
    return son7 * carpan[kat_o.reshape(-1)[harita.oc_option]]


# ---------------------------------------------------------------------------
# Beden bölmesi
# ---------------------------------------------------------------------------


def magaza_beden_paylari(satis: np.ndarray, harita: Harita, bit_gunu: int) -> np.ndarray:
    """float[C]: hücrenin, OC'sinin hedefinden aldığı pay (OC içinde toplam 1).

    Mağazanın aynı üst kategori ve beden setindeki option'larının geçmiş satışı
    (gün < `bit_gunu`) beden sırasına göre havuzlanır; havuzdaki payı o beden
    sırasındaki bütün hücreler alır (yeni option'ın kendi geçmişi yoktur).
    Mağaza–kategori–set grubunda hiç satış yoksa zincirin beden eğrisi
    (`sku_beden_payi`). Sonuç OC içinde yeniden ölçeklenir: çeşit dışı bedenler
    (OC'nin hücresi olmayan bedenler) payını taşımaz."""
    if bit_gunu > satis.shape[0]:
        raise ValueError(f"bit_gunu {bit_gunu}: satış {satis.shape[0]} satır")
    satis_c = satis[:bit_gunu].sum(axis=0, dtype=np.int64).astype(float)

    _, grup_o = np.unique(
        np.char.add(np.char.add(harita.option_kategori, "|"), harita.option_beden_seti), return_inverse=True)
    G = int(grup_o.max()) + 1 if len(grup_o) else 0
    sku_o, sku_b = harita.sku_option, harita.sku_beden
    B = int(sku_b.max()) + 1 if len(sku_b) else 0
    magaza_say = int(harita.hucre_magaza.max()) + 1
    grup_c = grup_o.reshape(-1)[harita.hucre_option]
    beden_c = sku_b[harita.hucre_sku]
    mg = harita.hucre_magaza.astype(np.int64) * G + grup_c        # mağaza–grup
    mgb = mg * B + beden_c                                         # mağaza–grup–beden
    havuz = np.bincount(mgb, weights=satis_c, minlength=magaza_say * G * B)
    toplam = np.bincount(mg, weights=satis_c, minlength=magaza_say * G)[mg]
    pay = np.where(toplam > 0, havuz[mgb] / np.where(toplam > 0, toplam, 1.0), harita.sku_beden_payi[harita.hucre_sku])
    oc_toplam = _oc_topla(pay, harita)[harita.oc]
    return _oranla(pay, oc_toplam)


def _oranla(pay: np.ndarray, payda: np.ndarray) -> np.ndarray:
    sonuc = np.zeros_like(pay)
    np.divide(pay, payda, out=sonuc, where=payda > 0)
    return sonuc


def bedene_bol(
    hedef_oc: np.ndarray,
    paylar: np.ndarray,
    stok_c: np.ndarray,
    yolda_c: np.ndarray,
    harita: Harita,
) -> np.ndarray:
    """int64[C] ihtiyaç = max(round(hedef × pay) − stok − yolda, 0).

    v4 farkı: yoldaki mal sayılır (v2'de yalnız raf stoğu). `hedef_oc` [OC]
    harita sırasında, `paylar` / `stok_c` / `yolda_c` [C]."""
    hedef = np.round(np.asarray(hedef_oc, dtype=float)[harita.oc] * paylar)
    return np.maximum(hedef - stok_c - yolda_c, 0).astype(np.int64)
