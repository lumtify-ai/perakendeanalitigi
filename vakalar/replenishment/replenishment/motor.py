"""Oyun motoru: günlük stok defteri.

Her gün için sıra: 1) gelen mal stoka (FIFO'ya `gelis_gunu=gun` ile),
2) iade (FIFO dışı stoğa), 3) satış = min(stok, talep), kayıp = talep - satış,
4) FIFO tüketimi — önce FIFO dışı ("eski") stok, sonra gönderilen partiler
en eskiden. Bütün diziler `dunya.hucre_magaza` / `dunya.hucre_urun`
sırasındaki hücre eksenini taşır (H = hücre sayısı).

`gunu_isle` yüzlerce gün × birçok senaryo için çağrılacağından stok/satış
hesabı numpy ile vektörize edilir; FIFO defteri yalnızca o gün hem sevk
edilmiş parti taşıyan hem satış yapan hücreler için (`np.flatnonzero`)
döngüye girer.
"""

from collections import deque
from dataclasses import dataclass

import numpy as np

from . import sabitler


@dataclass
class Durum:
    stok: np.ndarray                 # int64[H]
    iade_kuyrugu: list                # son IADE_GECIKME günün satışları (en eski başta)
    fifo: list                        # hücre başına deque[[gelis_gunu, adet]]; yalnız GÖNDERİLEN mal
    gonderilen_satis_gunleri: list    # (hucre, gelis_gunu, satis_gunu, adet) kayıtları
    stoklu_talepli_gun: int = 0
    talepli_gun: int = 0


def baslangic_durumu(stok: np.ndarray, son_satislar: list) -> Durum:
    """`son_satislar` (en eski başta) iade kuyruğunu önceden doldurur."""
    stok_kopya = np.array(stok, dtype=np.int64, copy=True)
    H = stok_kopya.shape[0]
    return Durum(
        stok=stok_kopya,
        iade_kuyrugu=[np.array(s, dtype=np.int64, copy=True) for s in son_satislar],
        fifo=[deque() for _ in range(H)],
        gonderilen_satis_gunleri=[],
    )


def gunu_isle(
    durum: Durum,
    gun: int,
    talep: np.ndarray,
    gelen: np.ndarray | None,
    iade: np.ndarray | None,
    rng: np.random.Generator | None,
) -> tuple[np.ndarray, np.ndarray]:
    H = durum.stok.shape[0]
    talep = np.asarray(talep, dtype=np.int64)

    # 1) gelen mal stoka, FIFO'ya gelis_gunu=gun ile kaydedilir.
    if gelen is not None:
        gelen = np.asarray(gelen, dtype=np.int64)
        durum.stok += gelen
        for h in np.flatnonzero(gelen > 0):
            durum.fifo[h].append([gun, int(gelen[h])])

    # 2) iade: verilmişse o kullanılır, yoksa 7 gün önceki satıştan binom.
    if iade is not None:
        iade_miktari = np.asarray(iade, dtype=np.int64)
    elif len(durum.iade_kuyrugu) >= sabitler.IADE_GECIKME:
        iade_miktari = rng.binomial(durum.iade_kuyrugu[0], sabitler.IADE_ORANI).astype(np.int64)
    else:
        iade_miktari = np.zeros(H, dtype=np.int64)
    durum.stok += iade_miktari

    # Bulunabilirlik sayaçları: satıştan ÖNCEki stokla ölçülür.
    talepli = talep > 0
    durum.talepli_gun += int(talepli.sum())
    durum.stoklu_talepli_gun += int((talepli & (durum.stok > 0)).sum())

    # 3) satış / kayıp.
    satis = np.minimum(durum.stok, talep)
    kayip = talep - satis

    # 4) FIFO tüketimi: önce FIFO dışı ("eski") stok, sonra en eski partiden.
    dolu_hucreler = np.flatnonzero(satis > 0)
    for h in dolu_hucreler:
        kuyruk = durum.fifo[h]
        if not kuyruk:
            continue
        fifo_toplam = sum(adet for _gelis, adet in kuyruk)
        fifo_disi = int(durum.stok[h]) - fifo_toplam
        kalan = int(satis[h]) - max(fifo_disi, 0)
        while kalan > 0 and kuyruk:
            gelis_gunu, adet = kuyruk[0]
            alinan = min(adet, kalan)
            durum.gonderilen_satis_gunleri.append((int(h), int(gelis_gunu), int(gun), int(alinan)))
            kalan -= alinan
            kalan_adet = adet - alinan
            if kalan_adet == 0:
                kuyruk.popleft()
            else:
                kuyruk[0][1] = kalan_adet

    durum.stok -= satis

    # 5) iade kuyruğu: son IADE_GECIKME günün satışı, en eski başta.
    durum.iade_kuyrugu.append(satis.astype(np.int64).copy())
    if len(durum.iade_kuyrugu) > sabitler.IADE_GECIKME:
        durum.iade_kuyrugu.pop(0)

    return satis, kayip
