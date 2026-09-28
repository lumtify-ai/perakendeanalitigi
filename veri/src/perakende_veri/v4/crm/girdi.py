"""B'nin A'dan okuduğu görünüm (spec §3).

`girdi_kur` A'yı `tablolari_uret(olcek, donus_ham=True)` ile kurar ve
ham motor çıktısını gün gün dilimler. A'nın hiçbir nesnesi değiştirilmez.

Gün dizileri 2B `float64`'tür; sütun indisleri aşağıdaki sabitlerdir
(`hucre`, `kampanya_id`, `islem_adet`, `satir` tam sayıdır, float64'te
kesin durur):

    H         hücre indisi (A: `dunya.hucre_*`)
    ADET      adet (iade satırında negatif)
    TUTAR     A'nın tutarı (iade: negatif)
    INDIRIM   A'nın indirim_tutari
    KAMPANYA  fiyatı belirleyen kampanyanın `kampanya` satır konumu, −1 yok
    ORAN      satış gününün oranı `max(markdown, kampanya)` (iade satırında
              iadenin doğduğu satış günününki); işlem indirimi hariç
    ISLEM     işlem indirimli birim sayısı `k` (adetle aynı işaretli)
    SATIR     `ham["satis"]` içindeki satır konumu

İşlem indirimi (A, `kampanya.gunun_fiyati`): oran 0 iken hücre-gün
çekilişiyle %30; A'da hücre-gün başına tek çekiliş olduğundan `k` ya 0 ya
`adet`tir. İade satırı satış gününün birim fiyatıyla (işlem indirimi
dahil) fiyatlanır (`motor/dongu.py` 16. adım), bu yüzden iadede de `k`
satış gününün oranıyla çıkarılır.
"""

from dataclasses import dataclass

import numpy as np

from .. import sabitler as a_sabitler
from ..magaza import Olcek
from ..motor.satis import hat_indisi

SUTUNLAR = ("hucre", "adet", "tutar", "indirim_tutari", "kampanya_id", "oran", "islem_adet", "satir")
H, ADET, TUTAR, INDIRIM, KAMPANYA, ORAN, ISLEM, SATIR = range(len(SUTUNLAR))

TUTAR_TOLERANSI = 0.01


@dataclass(frozen=True)
class Girdi:
    """dunya, ham: A'nın nesneleri (salt okunur). `satis_gun[d]` gün d'nin
    pozitif satış satırları, `iade_gun[d]` negatif satırları (sütunlar
    `SUTUNLAR`); `kayip_gun[d]` gün d'nin gizli kaybı [n, 2] int64
    (hucre, adet), ısınma dahil; `islem_adet` `ham["satis"]` satır
    sırasıyla işlem indirimli birim sayısı; `D` motorun gün sayısı."""

    dunya: object
    ham: dict
    satis_gun: list[np.ndarray]
    iade_gun: list[np.ndarray]
    kayip_gun: list[np.ndarray]
    islem_adet: np.ndarray
    D: int


def _markdown_orani(dunya, fiyat, gun: np.ndarray, hucre: np.ndarray) -> np.ndarray:
    """Motorun 12. adımındaki `md = fiyat_orani[ho, hat]`, `ham["fiyat"]`
    değişim kaydından: (option, hat) anahtarında gün ≤ d olan son kayıt
    (aynı günde sonraki kayıt geçerli; ekleme sırası korunur), yoksa 0."""
    hat_c = hat_indisi(np.asarray(dunya.hucre_online), np.asarray(dunya.hucre_outlet_akisi))
    ho = np.asarray(dunya.hucre_option, dtype=np.int64)
    fg = fiyat["gun"].to_numpy(dtype=np.int64)
    fa = fiyat["option"].to_numpy(dtype=np.int64) * 3 + fiyat["hat"].to_numpy(dtype=np.int64)
    fo = fiyat["oran"].to_numpy(dtype=float)
    G = int(max(fg.max(initial=0), gun.max(initial=0))) + 1
    fk = fa * G + fg
    sira = np.argsort(fk, kind="stable")
    fk, fo = fk[sira], fo[sira]
    anahtar = ho[hucre] * 3 + hat_c[hucre]
    q = anahtar * G + gun
    i = np.searchsorted(fk, q, side="right") - 1
    gecerli = (i >= 0) & (fk[np.maximum(i, 0)] // G == anahtar)
    return np.where(gecerli, fo[np.maximum(i, 0)], 0.0)


def _kampanya_orani(dunya, gun: np.ndarray, hucre: np.ndarray) -> np.ndarray:
    hm = np.asarray(dunya.hucre_magaza, dtype=np.int64)
    ho = np.asarray(dunya.hucre_option, dtype=np.int64)
    sonuc = np.zeros(len(gun), dtype=float)
    sira = np.argsort(gun, kind="stable")
    gs = gun[sira]
    sinir = np.flatnonzero(np.diff(gs)) + 1
    for parca in np.split(sira, sinir):
        if len(parca):
            c = hucre[parca]
            sonuc[parca] = dunya.kampanya_takvimi(int(gun[parca[0]]))[hm[c], ho[c]]
    return sonuc


def satis_gunu_orani(dunya, ham: dict) -> np.ndarray:
    """`ham["satis"]` satır başına satış gününün `max(md, kampanya)` oranı
    (iade satırı: iadenin geldiği satış günü = gün − 7, ONL − 10)."""
    s = ham["satis"]
    gun = s["gun"].to_numpy(dtype=np.int64)
    hucre = s["hucre"].to_numpy(dtype=np.int64)
    iade = s["adet"].to_numpy() < 0
    gecikme = np.where(
        np.asarray(dunya.hucre_online)[hucre],
        a_sabitler.IADE_GECIKME_ONLINE, a_sabitler.IADE_GECIKME_MAGAZA,
    )
    satis_gunu = np.where(iade, gun - gecikme, gun)
    md = _markdown_orani(dunya, ham["fiyat"], satis_gunu, hucre)
    kamp = _kampanya_orani(dunya, satis_gunu, hucre)
    return np.maximum(md, kamp)


def islem_adedi(dunya, ham: dict, oran: np.ndarray) -> np.ndarray:
    """k = oran 0 satırlarda round((liste·adet − tutar) / (0,30·liste)),
    oran > 0 satırlarda 0. Birim fiyatlardan geri kurulan tutarın A
    tutarına ±0,01 eşit olduğunu doğrular."""
    s = ham["satis"]
    hucre = s["hucre"].to_numpy(dtype=np.int64)
    liste = dunya.urunler["liste_fiyati"].to_numpy(dtype=float)[np.asarray(dunya.hucre_sku)[hucre]]
    adet = s["adet"].to_numpy(dtype=np.int64)
    tutar = s["tutar"].to_numpy(dtype=float)
    r = a_sabitler.ISLEM_INDIRIM_ORANI
    k = np.where(oran == 0, np.rint((liste * adet - tutar) / (r * liste)), 0).astype(np.int64)
    kurulan = liste * (adet - r * k) * (1.0 - oran)
    hata = np.abs(kurulan - tutar)
    kotu = np.flatnonzero(hata > TUTAR_TOLERANSI)
    assert not len(kotu), (
        f"{len(kotu)} satırda tutar kurulamadı; ilk satırlar {kotu[:5].tolist()}, "
        f"hata {hata[kotu[:5]].tolist()}"
    )
    return k


def _gunlere_bol(dizi: np.ndarray, gun: np.ndarray, D: int) -> list[np.ndarray]:
    """`gun`e göre sıralı `dizi`yi D güne böler (görünüm, kopya değil)."""
    assert (np.diff(gun) >= 0).all(), "ham gün sırasında olmalı"
    sinir = np.searchsorted(gun, np.arange(1, D))
    return np.split(dizi, sinir)


def girdi_kur(olcek: Olcek = Olcek.TAM) -> Girdi:
    """A'yı `sabitler.TOHUM` ile kurar ve B'nin görünümünü hazırlar."""
    from ..uret import tablolari_uret

    tablolar, dunya, ham = tablolari_uret(olcek, donus_ham=True, tohum=a_sabitler.TOHUM)
    del tablolar
    return girdi_hamdan(dunya, ham)


def girdi_hamdan(dunya, ham: dict) -> Girdi:
    """Hazır (dunya, ham) çiftinden görünüm (A yeniden kurulmaz)."""
    D = int(ham["gun_sayisi"])
    s = ham["satis"]
    oran = satis_gunu_orani(dunya, ham)
    k = islem_adedi(dunya, ham, oran)

    gun = s["gun"].to_numpy(dtype=np.int64)
    tablo = np.empty((len(s), len(SUTUNLAR)), dtype=np.float64)
    tablo[:, H] = s["hucre"].to_numpy()
    tablo[:, ADET] = s["adet"].to_numpy()
    tablo[:, TUTAR] = s["tutar"].to_numpy()
    tablo[:, INDIRIM] = s["indirim_tutari"].to_numpy()
    tablo[:, KAMPANYA] = s["kampanya_id"].to_numpy()
    tablo[:, ORAN] = oran
    tablo[:, ISLEM] = k
    tablo[:, SATIR] = np.arange(len(s))

    poz = tablo[:, ADET] > 0
    satis_gun = _gunlere_bol(tablo[poz], gun[poz], D)
    iade_gun = _gunlere_bol(tablo[~poz], gun[~poz], D)
    del tablo

    kay = ham["gizli_kayip"]
    kg = kay["gun"].to_numpy(dtype=np.int64)
    kayip = np.column_stack([kay["hucre"].to_numpy(dtype=np.int64), kay["adet"].to_numpy(dtype=np.int64)])
    kayip_gun = _gunlere_bol(kayip, kg, D)

    k.setflags(write=False)
    return Girdi(dunya=dunya, ham=ham, satis_gun=satis_gun, iade_gun=iade_gun,
                 kayip_gun=kayip_gun, islem_adet=k, D=D)
