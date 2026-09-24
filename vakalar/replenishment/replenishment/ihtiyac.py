"""Kural tabanlı ihtiyaç hesabı: haftalık satış, özel gün katsayısı, safety
stock aileleri, kural öngörüsü, mağazanın beden dağılımı ve bedene bölme.

Bütün fonksiyonlar `dunya.oc_hucre[OC, 5]` (option-mağaza başına beden_sira
1..5 hücre indeksleri) üzerinden option-mağaza (OC) eksenine indirger. `satis`
her zaman hücre eksenli (365, H) bir dizi (bkz. `kaynak.py`); `stok` hücre
eksenli (H,) bir dizi.

`haftalik` bloğu salı..pazartesi'dir: karar günü pazartesi, teslim ertesi gün
salı sabahı olduğundan "son 7 gün" karar_gunu dahil geriye doğru 7 gündür.
Veri başlangıcından (gün 0) önceye taşan bloklar bütünüyle 0 sayılır —
kısmi toplam alınmaz.
"""

from dataclasses import dataclass

import numpy as np

from .dunya import Dunya


def _oc_gunluk_satis(satis: np.ndarray, dunya: Dunya) -> np.ndarray:
    """float[365, OC]: hücre eksenindeki satışın option-mağaza (5 beden) toplamı."""
    return satis[:, dunya.oc_hucre].sum(axis=2).astype(float)


def haftalik(satis: np.ndarray, dunya: Dunya, karar_gunu: int, hafta: int) -> np.ndarray:
    """float[hafta, OC] — karar_gunu dahil geriye doğru `hafta` tane 7 günlük
    (salı..pazartesi) blokta option-mağaza satış toplamı; en yeni son satırda.
    Veri başlangıcından önceye taşan bloklar 0."""
    oc_gunluk = _oc_gunluk_satis(satis, dunya)
    OC = oc_gunluk.shape[1]
    sonuc = np.zeros((hafta, OC), dtype=float)
    for i in range(hafta):
        geri = hafta - 1 - i
        bit = karar_gunu - 7 * geri
        bas = bit - 6
        if bas < 0:
            continue
        sonuc[i] = oc_gunluk[bas : bit + 1].sum(axis=0)
    return sonuc


def _kategori_gunluk(satis: np.ndarray, dunya: Dunya) -> tuple[np.ndarray, np.ndarray]:
    """(kategoriler[K], float[365, K]): ust_kategori başına günlük satış toplamı."""
    oc_gunluk = _oc_gunluk_satis(satis, dunya)
    kategoriler = np.unique(dunya.oc_kategori)
    kat_gunluk = np.zeros((oc_gunluk.shape[0], len(kategoriler)), dtype=float)
    for i, kat in enumerate(kategoriler):
        kat_gunluk[:, i] = oc_gunluk[:, dunya.oc_kategori == kat].sum(axis=1)
    return kategoriler, kat_gunluk


def ozel_gun_katsayilari(satis: np.ndarray, dunya: Dunya, bit_gunu: int) -> dict[str, float]:
    """ust_kategori → katsayı. Geçmişteki (gün < bit_gunu) her tatil günü h için:
    kategori satışı(h) / aynı haftanın gününe denk gelen, h'nin ±14 günü
    içindeki tatil olmayan günlerin ortalama kategori satışı. Katsayı bu
    oranların ortalaması."""
    kategoriler, kat_gunluk = _kategori_gunluk(satis, dunya)
    gun_sayisi = kat_gunluk.shape[0]
    haftanin_gunu = np.arange(gun_sayisi) % 7

    oranlar: dict[str, list] = {kat: [] for kat in kategoriler}
    for h in np.flatnonzero(dunya.tatil[:bit_gunu]):
        pencere = np.arange(max(h - 14, 0), min(h + 14, gun_sayisi - 1) + 1)
        aday = pencere[(haftanin_gunu[pencere] == haftanin_gunu[h]) & ~dunya.tatil[pencere]]
        if aday.size == 0:
            continue
        for i, kat in enumerate(kategoriler):
            payda = kat_gunluk[aday, i].mean()
            if payda <= 0:
                continue
            oranlar[kat].append(kat_gunluk[h, i] / payda)

    return {kat: float(np.mean(degerler)) for kat, degerler in oranlar.items() if degerler}


def hafta_katsayisi(dunya: Dunya, karar_gunu: int, gun_katsayisi: float) -> float:
    """(Σ_{karar+1..karar+7} f) / (Σ_{karar−6..karar} f); tatil günü f = gun_katsayisi, diğerleri 1."""

    def _toplam(bas: int, bit: int) -> float:
        gunler = np.arange(bas, bit + 1)
        f = np.where(dunya.tatil[gunler], gun_katsayisi, 1.0)
        return float(f.sum())

    pay = _toplam(karar_gunu + 1, karar_gunu + 7)
    payda = _toplam(karar_gunu - 6, karar_gunu)
    return pay / payda


@dataclass(frozen=True)
class GuvenlikStoku:
    aile: str            # "sabit" | "ros" | "istatistik"
    deger: float = 0.0   # sabit: adet; ros: gün; istatistik: kullanılmaz (Z=1.65)


def guvenlik_stoku(ss: GuvenlikStoku, satis: np.ndarray, dunya: Dunya, karar_gunu: int) -> np.ndarray:
    """sabit: deger. ros: son 28 gün satışı/28 × deger. istatistik:
    1.65 × std(son 8 haftalık toplam, ddof=1) × sqrt(1)."""
    OC = dunya.oc_hucre.shape[0]

    if ss.aile == "sabit":
        return np.full(OC, ss.deger, dtype=float)

    if ss.aile == "ros":
        bas = karar_gunu - 27
        if bas < 0:
            return np.zeros(OC, dtype=float)
        oc_gunluk = _oc_gunluk_satis(satis, dunya)
        toplam = oc_gunluk[bas : karar_gunu + 1].sum(axis=0)
        return toplam / 28.0 * ss.deger

    if ss.aile == "istatistik":
        haftalik_toplam = haftalik(satis, dunya, karar_gunu, 8)
        std = haftalik_toplam.std(axis=0, ddof=1)
        return 1.65 * std * np.sqrt(1.0)

    raise ValueError(f"Bilinmeyen güvenlik stoku ailesi: {ss.aile}")


def kural_ongorusu(
    satis: np.ndarray, dunya: Dunya, karar_gunu: int, katsayilar: dict[str, float]
) -> np.ndarray:
    """son 7 gün satışı × hafta_katsayisi(kategori katsayısıyla)."""
    oc_gunluk = _oc_gunluk_satis(satis, dunya)
    bas = karar_gunu - 6
    if bas < 0:
        son7 = np.zeros(oc_gunluk.shape[1], dtype=float)
    else:
        son7 = oc_gunluk[bas : karar_gunu + 1].sum(axis=0)

    kat_katsayi = {
        kat: hafta_katsayisi(dunya, karar_gunu, katsayilar.get(kat, 1.0))
        for kat in np.unique(dunya.oc_kategori)
    }
    carpan = np.array([kat_katsayi[kat] for kat in dunya.oc_kategori])
    return son7 * carpan


def magaza_beden_paylari(satis: np.ndarray, dunya: Dunya, bit_gunu: int) -> np.ndarray:
    """float[OC, 5]: Mağazanın ust_kategori'deki geçmiş satışının beden payı
    (bit_gunu'ne kadar, gün < bit_gunu). Kategoride hiç satış yoksa
    zincir_beden_payi."""
    hucre_toplam = satis[:bit_gunu].sum(axis=0).astype(float)
    oc_beden = hucre_toplam[dunya.oc_hucre]  # float[OC, 5]

    OC = oc_beden.shape[0]
    sonuc = np.empty((OC, 5), dtype=float)
    grup_anahtari = np.char.add(np.char.add(dunya.oc_magaza.astype(str), "|"), dunya.oc_kategori.astype(str))
    for anahtar in np.unique(grup_anahtari):
        idx = np.flatnonzero(grup_anahtari == anahtar)
        grup_toplam = oc_beden[idx].sum(axis=0)
        toplam = grup_toplam.sum()
        pay = grup_toplam / toplam if toplam > 0 else dunya.zincir_beden_payi
        sonuc[idx] = pay
    return sonuc


def bedene_bol(
    hedef_oc: np.ndarray,
    paylar: np.ndarray,
    stok: np.ndarray,
    dunya: Dunya,
    oc=None,
) -> np.ndarray:
    """int[OC, 5] ihtiyaç = max(round(hedef × pay) − beden stoku, 0).

    `oc` verilirse option-mağaza indekslerinin bir alt kümesidir; `hedef_oc`
    ve `paylar` bu alt küme üzerinden indekslenir. `oc` None ise bütün OC."""
    oc_hucre = dunya.oc_hucre if oc is None else dunya.oc_hucre[oc]
    beden_stok = stok[oc_hucre]  # int[n, 5]
    hedef = np.round(np.asarray(hedef_oc, dtype=float)[:, None] * paylar)
    ihtiyac = np.maximum(hedef - beden_stok, 0)
    return ihtiyac.astype(np.int64)
