"""Depo: option başına kapalı koli ve açık (beden bazlı) stok.

İlk alım (`depo_kur`) line'a göre iki farklı kurala göre büyüklük belirler:
Collection/Outlet ("tek alım line'ı") sezon boyunca bir kez, plan talebinin
`bas..bit` günleri toplamı × alım oranı kadar alınır. NOS/Basic ise sezon
boyunca sürekli tedarik edilen line'lardır; ilk kurulumda ve her
`tedarik_et` çağrısında hedef, zincir plan talebinin `TEDARIK_HEDEF_HAFTA`
haftalık toplamıdır (hedefin sezonu, ilgili günün sezonudur).

Bir option'ın alımı her zaman "kapalı koli" ve "açık adet" olarak ikiye
ayrılır: açık payı kadarı (`sabitler.ACIK_PAYI`, line'a göre) açık adet
olarak zincir beden dağılımına (`dunya.zincir_beden_payi`) göre bedenlere
paylaştırılır, kalanı 8'li kolilere yuvarlanır (aşağı).
"""

from dataclasses import dataclass

import numpy as np

from . import sabitler
from .dunya import Dunya


@dataclass
class Depo:
    koli: np.ndarray  # int64[O]     kapalı koli sayısı
    acik: np.ndarray  # int64[O, 5]  açık adet, beden_sira 1..5


def _line_per_option(dunya: Dunya) -> np.ndarray:
    """str[O]: her option'ın line'ı (option'ın bütün mağazalarında aynıdır)."""
    _, ilk_idx = np.unique(dunya.oc_opt, return_index=True)
    return dunya.oc_line[ilk_idx]


def _option_toplami(dunya: Dunya, hucre_deger: np.ndarray) -> np.ndarray:
    """float[O]: hücre değerinin option başına (bütün mağaza, bütün beden) toplamı."""
    O = len(dunya.optionlar)
    oc_toplam = hucre_deger[dunya.oc_hucre].sum(axis=1)  # float[OC], 5 bedenin toplamı
    sonuc = np.zeros(O, dtype=float)
    np.add.at(sonuc, dunya.oc_opt, oc_toplam)
    return sonuc


def _donem_hucre_toplami(dunya: Dunya, bas_gun: int, bit_gun: int) -> np.ndarray:
    """float[H]: bas_gun..bit_gun (dahil) günlerinin plan talebi toplamı, hücre başına."""
    H = len(dunya.hucre_magaza)
    toplam = np.zeros(H, dtype=float)
    sezonlar, sayilar = np.unique(dunya.sezon[bas_gun : bit_gun + 1], return_counts=True)
    for sezon, sayi in zip(sezonlar, sayilar):
        toplam += sayi * dunya.plan[sezon]
    return toplam


def _tek_alim_maskesi(line_per_option: np.ndarray) -> np.ndarray:
    return np.isin(line_per_option, sabitler.TEK_ALIM_LINE)


def _koli_ve_acik(
    dunya: Dunya, alim: np.ndarray, line_per_option: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    acik_payi = np.array([sabitler.ACIK_PAYI[line] for line in line_per_option])
    koli = np.floor(alim * (1 - acik_payi) / sabitler.KOLI_ADET).astype(np.int64)
    acik = np.round(
        alim[:, None] * acik_payi[:, None] * dunya.zincir_beden_payi[None, :]
    ).astype(np.int64)
    return koli, acik


def _nos_alim(dunya: Dunya, sezon: str) -> np.ndarray:
    """float[O]: NOS/Basic hedefi — zincir plan talebinin TEDARIK_HEDEF_HAFTA haftası."""
    gunluk = dunya.plan[sezon]
    return sabitler.TEDARIK_HEDEF_HAFTA * 7 * _option_toplami(dunya, gunluk)


def depo_kur(dunya: Dunya, alim_orani: float, bas: str, bit: str) -> Depo:
    line_per_option = _line_per_option(dunya)
    tek_alim = _tek_alim_maskesi(line_per_option)

    bas_gun = dunya.gun(bas)
    bit_gun = dunya.gun(bit)

    donem_toplami = _donem_hucre_toplami(dunya, bas_gun, bit_gun)
    tek_alim_hedefi = alim_orani * _option_toplami(dunya, donem_toplami)

    nos_hedefi = _nos_alim(dunya, dunya.sezon[bas_gun])

    alim = np.where(tek_alim, tek_alim_hedefi, nos_hedefi)
    koli, acik = _koli_ve_acik(dunya, alim, line_per_option)
    return Depo(koli=koli, acik=acik)


def tedarik_et(depo: Depo, dunya: Dunya, gun: int) -> None:
    line_per_option = _line_per_option(dunya)
    nos_maskesi = ~_tek_alim_maskesi(line_per_option)

    nos_hedefi = _nos_alim(dunya, dunya.sezon[gun])
    koli_hedef, acik_hedef = _koli_ve_acik(dunya, nos_hedefi, line_per_option)

    depo.koli[nos_maskesi] = np.maximum(depo.koli[nos_maskesi], koli_hedef[nos_maskesi])
    depo.acik[nos_maskesi] = np.maximum(depo.acik[nos_maskesi], acik_hedef[nos_maskesi])


def depo_toplami(depo: Depo) -> int:
    return int(depo.koli.sum() * sabitler.KOLI_ADET + depo.acik.sum())
