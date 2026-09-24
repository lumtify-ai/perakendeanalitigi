"""Haftalık oyun döngüsü: depo, motor, ihtiyaç, dağıtım ve ölçütleri birleştirir.

Karar günleri `ayar.bas`'tan başlayarak her pazartesi (Task tanımında 17
karar). Her karar gününde: çift sıradaki kararlarda NOS/Basic depo tedarik
edilir (`depo.tedarik_et`, ilgisiz line'ları kendi içinde eler), politika
hedef/öngörü üretir, `ihtiyac.bedene_bol` bedene böler, `dagitim.dagit`
sevk kurar. Sevkiyat ertesi gün sabahı (`motor.gunu_isle`'nin `gelen`
argümanı) stoka girer — satıştan önce.

`gozlenen` sızıntı kalkanı: politikaya geçirilmeden önce karar gününden
sonraki günler sıfırlanmış bir kopya üzerinde çalışılır, böylece hiçbir
politika henüz gerçekleşmemiş talebi göremez.
"""

from dataclasses import dataclass

import numpy as np

from . import sabitler
from .dagitim import KoliKurali, dagit
from .depo import depo_kur, depo_toplami, tedarik_et
from .dunya import Dunya
from .ihtiyac import bedene_bol
from .motor import Durum, gunu_isle
from .olcutler import hesapla
from .politika import Politika


@dataclass
class OyunAyari:
    alim_orani: float
    kural: KoliKurali
    acik_kapasite: int
    oncelik: str = "cover"
    bas: str = sabitler.OYUN_BAS
    bit: str = sabitler.OYUN_BIT


@dataclass
class Sonuc:
    olcutler: dict[str, float]
    haftalik: list[dict]  # karar başına koli, açık, depo kalan


def oyna(
    dunya: Dunya,
    talep: np.ndarray,
    gecmis_satis: np.ndarray,
    baslangic: Durum,
    politika: Politika,
    ayar: OyunAyari,
    paylar: np.ndarray,
    iade_tohumu: int = sabitler.IADE_TOHUM,
) -> Sonuc:
    depo = depo_kur(dunya, ayar.alim_orani, ayar.bas, ayar.bit)
    gozlenen = gecmis_satis.copy()

    bas_gunu = dunya.gun(ayar.bas)
    bit_gunu = dunya.gun(ayar.bit)
    karar_gunleri = [bas_gunu + 7 * k for k in range(sabitler.KARAR_SAYISI)]
    karar_sirasi = {gun: k for k, gun in enumerate(karar_gunleri)}

    baslangic_stok = float(baslangic.stok.sum())

    durum = baslangic
    rng = np.random.default_rng(iade_tohumu)

    bekleyen_sevk: np.ndarray | None = None
    haftalik: list[dict] = []

    for g in range(bas_gunu, bit_gunu + 1):
        gelen = bekleyen_sevk
        bekleyen_sevk = None

        satis, _kayip = gunu_isle(durum, g, talep[g], gelen, None, rng)
        gozlenen[g] = satis

        k = karar_sirasi.get(g)
        if k is not None:
            if k % 2 == 0:
                tedarik_et(depo, dunya, g)

            gorulen = gozlenen.copy()
            gorulen[g + 1 :] = 0

            hedef, ongoru = politika.hedef(gorulen, dunya, g, durum.stok, durum.stoklu_gunluk)
            n = bedene_bol(hedef, paylar, durum.stok, dunya)
            sevk = dagit(
                n, ongoru, durum.stok, depo, dunya, ayar.kural, ayar.acik_kapasite, ayar.oncelik
            )
            bekleyen_sevk = sevk.gelen

            haftalik.append(
                {
                    "gun": g,
                    "koli_sayisi": sevk.koli_sayisi,
                    "acik_adet": sevk.acik_adet,
                    "depo_kalan": depo_toplami(depo),
                }
            )

    # `hesapla` beden_sapmasi için mağaza beden payını `gozlenen[:bas_gunu]`'nden
    # kendisi yeniden hesaplar (bkz. olcutler.py docstring'i); bu yalnız
    # `gozlenen[:bas_gunu]` yukarıdaki `gecmis_satis.copy()` satırından beri
    # değişmediği için `paylar`'la (bu fonksiyona ayrı geçirilen, oyun başında
    # sabitlenen mağaza beden payı) aynı sonucu verir — `gecmis_satis` bu
    # çağrıdan sonra çağıran tarafından değiştirilirse artık aynı olmaz.
    olcutler = hesapla(durum, dunya, depo, haftalik, talep, gozlenen, baslangic_stok, ayar)
    return Sonuc(olcutler=olcutler, haftalik=haftalik)
