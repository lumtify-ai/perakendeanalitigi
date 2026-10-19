"""Paylaştırma çekirdeği: paket içeriği, gönderilebilir üst sınır `U`, aday maskesi, paylaştırma.

Her politika kolu (`esit`, `benzer`, `tahmin`, `kahin`) mağaza paylarını bu işlevlerle paketlere
çevirir. Hepsi saf işlevdir (rastgelelik yok, girdiyi değiştirmez).

Kural: bu modül gizli gerçeğe (`perakende_veri`), motora (`allocation.motor`) ve hakeme dokunmaz;
yalnız `Gorunum`un (`depo`, `kapanacak`, `acik_magaza`, `dunya`) ve dünyanın açık alanlarını okur.

**Gönderilebilir üst sınır** (spec §0/9):

    U = min( ⌊ilk_alim × LUMODA_ILK_PAYI ÷ paket_adedi⌋ ,  min_b ⌊depo_b ÷ içerik_b⌋ )

İlk terim tam sayı (kesir) aritmetiğiyle hesaplanır. Lumoda'nın `lumoda_ilk_dagitim`'i aynı
terimi kayan noktayla hesaplar (`ilk_alim * 0.70 // paket_adedi`); `ilk_alim × 0,70` tam
bölünen durumlarda kayan nokta bir eksik verir (ör. 700 × 0,70 ÷ 7 -> 69). Bu modülün `U`'su
tam değeri verir; fark yalnız bu durumlarda ve en çok 1 pakettir.

**Aday kümesi** `lumoda_ilk_dagitim`'inkiyle aynıdır (kopyalanmış mantık; testte karşılaştırılır).

**Paylaştırma** (`paylastir`): en büyük kalan yöntemi, eşitlikte küçük mağaza indisi kazanır.
İki ortak kısıt (spec §3.3):

    tavan_paket       Mağaza başına en çok paket. Tavanı aşan mağaza tavanda sabitlenir, artan
                      paketler ötekilere payları oranında yeniden paylaştırılır (su dolumu:
                      yeni mağaza bağlanmayana dek tekrarlı). Herkes tavandaysa kalan
                      paketler dağıtılmaz. `None` = hiçbir mağazada tavan yok; dizide
                      `TAVANSIZ` (en büyük int64) o mağazanın tavansız olduğunu gösterir
                      (öngörüsü olmayan mağaza). Negatif tavan hatadır.
    en_az_gosterim    Payı 1 paketin altında kalan (hedefi < 1) pozitif paylı mağaza ya 1
                      paket alır ya hiç: en büyük kalan sırasında bu mağazalar, kesri ne
                      kadar küçük olursa olsun, tam paket kısmı olan mağazaların kesirlerinin
                      önüne geçer (kalan paketler önce onlara gider, kendi aralarında en
                      büyük hedefe göre). Hiçbir mağaza tam paket kısmından kaybetmez; toplam
                      aşılmaz. Kapalıyken düz en büyük kalan.

Pay toplamı 0 ise (aday ve pozitif paylı mağaza yoksa) hiçbir mağazaya paket gitmez: pay
vermeyen kol kendi geri düşüşünü seçer (eşit paylaştırma ya da boş).
"""

from fractions import Fraction

import numpy as np
import pandas as pd

from allocation import sabitler

TAVANSIZ = int(np.iinfo(np.int64).max)    # `tavan_paket` dizisinde: bu mağazada tavan yok

_KESIR_BASAMAK = 9    # kesir karşılaştırmasında kayan nokta gürültüsünü eleyen yuvarlama


# ---------------------------------------------------------------------------
# Paket içeriği ve üst sınır
# ---------------------------------------------------------------------------


def _paket_satirlari(w, o: int):
    """(beden_sira [B], adet [B]): option'ın beden setinin paketi (setin ilk görülen paketi;
    v4 `paket_tablosu` ile aynı seçim), beden sırasıyla; içeriği 0 olan beden düşer."""
    p = w.paketler
    bs = w.optionlar["beden_seti"].iloc[o]
    set_satir = p[p["beden_seti"] == bs]
    if set_satir.empty:
        raise KeyError(f"{bs!r} beden setinin paketi yok (option {o})")
    set_satir = set_satir[set_satir["paket_id"] == set_satir["paket_id"].iloc[0]]
    set_satir = set_satir.sort_values("beden_sira")
    adet = set_satir["adet"].to_numpy().astype(np.int64)
    sira = set_satir["beden_sira"].to_numpy().astype(np.int64)
    dolu = adet > 0
    return sira[dolu], adet[dolu]


def paket_icerigi(w, o: int) -> np.ndarray:
    """[B] option'ın beden seti paketinin beden sırasına göre içeriği (adet; dolu bedenler)."""
    return _paket_satirlari(w, o)[1]


def paket_adedi(w, o: int) -> int:
    """Paketteki toplam adet."""
    return int(paket_icerigi(w, o).sum())


def ust_sinir(g, o: int, harita) -> int:
    """Option `o` için gönderilebilir üst sınır `U` (paket); modül notuna bakın."""
    w = g.dunya
    sira, icerik = _paket_satirlari(w, o)
    pay = Fraction(repr(float(sabitler.LUMODA_ILK_PAYI)))    # 0.7 -> 7/10 (kayan nokta kaymasız)
    u = int(pay * int(w.ilk_alim[o]) // int(icerik.sum()))
    skular = np.flatnonzero(harita.sku_option == o)
    sku_beden = dict(zip(harita.sku_beden_sira[skular].tolist(), skular.tolist()))
    for b, c in zip(sira.tolist(), icerik.tolist()):
        if b not in sku_beden:
            raise ValueError(f"option {o}: paketteki beden {b} için SKU yok")
        u = min(u, int(g.depo[sku_beden[b]]) // c)
    return max(u, 0)


# ---------------------------------------------------------------------------
# Aday maskesi
# ---------------------------------------------------------------------------


def aday_maskesi(g, o: int, harita) -> np.ndarray:
    """[M] bool: `lumoda_ilk_dagitim`'in aday tanımı, yalnız açık alanlardan.

    Option'ın fiziksel (ONL olmayan), outlet akışı olmayan hücresi olan mağaza; kapanış kararı
    verilmemiş; bugün açık ya da lansmana kadar açılacak (`acilis_tarihi` <= lansman); lansmandan
    önce kapanmıyor (`kapanis_tarihi` yok ya da > lansman)."""
    w = g.dunya
    mag = w.magazalar
    lansman = w.optionlar["lansman_tarihi"].iloc[o]
    hucre = (harita.hucre_option == o) & ~harita.hucre_online & ~np.asarray(w.hucre_outlet_akisi)
    aday = np.zeros(len(mag), dtype=bool)
    aday[harita.hucre_magaza[hucre]] = True
    aday &= ~np.asarray(g.kapanacak)
    acilis = pd.to_datetime(mag["acilis_tarihi"])
    kapanis = pd.to_datetime(mag["kapanis_tarihi"])
    aday &= np.asarray(g.acik_magaza) | (acilis <= lansman).to_numpy()
    aday &= ~(kapanis.notna() & (kapanis <= lansman)).to_numpy()
    return aday


# ---------------------------------------------------------------------------
# Paylaştırma
# ---------------------------------------------------------------------------


def _su_dolumu(kalan: int, pay: np.ndarray, tavan: np.ndarray, uygun: np.ndarray):
    """Tavanda sabitlenen mağazalar ve onlar düşülünce paylaşılacak paket.

    `uygun` mağazalar arasında hedef = kalan × pay / Σpay; hedefi tavana ulaşan mağaza tavanda
    sabitlenir ve paketi düşülür; sabitlenen kalmayana dek tekrarlanır. Dönüş: (sabit [M] bool,
    serbest mağazaların paylaşacağı kalan paket)."""
    sabit = np.zeros(len(pay), dtype=bool)
    while True:
        serbest = uygun & ~sabit
        if kalan <= 0 or not serbest.any():
            return sabit, max(kalan, 0)
        hedef = kalan * pay[serbest] / pay[serbest].sum()
        bagli = hedef >= tavan[serbest]
        if not bagli.any():
            return sabit, kalan
        indis = np.flatnonzero(serbest)[bagli]
        sabit[indis] = True
        kalan -= int(tavan[indis].sum())


def paylastir(toplam: int, pay: np.ndarray, aday: np.ndarray, *,
              tavan_paket: np.ndarray | None = None, en_az_gosterim: bool = True) -> np.ndarray:
    """`toplam` paketi `pay` oranında aday mağazalara böler -> [M] int64 paket sayısı.

    Aday olmayan ve payı 0 olan mağaza 0 alır. Dönüş toplamı <= `toplam`; tavan yoksa (ya da
    bağlamıyorsa) ve pozitif paylı aday varsa = `toplam`. Kurallar için modül notuna bakın."""
    pay = np.asarray(pay, dtype=float)
    aday = np.asarray(aday, dtype=bool)
    M = len(pay)
    if pay.ndim != 1 or not np.isfinite(pay).all() or (pay < 0).any():
        raise ValueError("pay: sonlu ve eksi olmayan [M] dizi olmalı")
    if aday.shape != (M,):
        raise ValueError(f"aday: [{M}] bool dizi olmalı, şekli {aday.shape}")
    if tavan_paket is None:
        tavan = np.full(M, TAVANSIZ, dtype=np.int64)
    else:
        tavan = np.asarray(tavan_paket)
        if tavan.shape != (M,) or not np.issubdtype(tavan.dtype, np.integer) or (tavan < 0).any():
            raise ValueError(f"tavan_paket: [{M}] eksi olmayan int dizi olmalı (tavansız: TAVANSIZ)")
        tavan = tavan.astype(np.int64)

    sonuc = np.zeros(M, dtype=np.int64)
    toplam = int(toplam)
    uygun = aday & (pay > 0) & (tavan > 0)
    if toplam <= 0 or not uygun.any():
        return sonuc

    sabit, kalan = _su_dolumu(toplam, pay, tavan, uygun)
    sonuc[sabit] = tavan[sabit]
    serbest = uygun & ~sabit
    if not serbest.any() or kalan <= 0:
        return sonuc

    hedef = kalan * pay[serbest] / pay[serbest].sum()
    taban = np.floor(hedef).astype(np.int64)
    artan = min(max(kalan - int(taban.sum()), 0), len(hedef))
    kesir = np.round(hedef - taban, _KESIR_BASAMAK)
    kucuk = (hedef < 1) if en_az_gosterim else np.zeros(len(hedef), dtype=bool)
    # sıra: küçük (hedefi < 1) mağazalar önce, sonra kesre göre azalan; eşitlikte küçük indis
    sira = np.lexsort((np.arange(len(hedef)), -kesir, ~kucuk))
    taban[sira[:artan]] += 1
    sonuc[serbest] = taban
    return sonuc
