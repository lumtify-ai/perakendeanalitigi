"""Oyun sonu ölçütleri.

`hesapla` bir `oyun.oyna` koşusunun sonunda çağrılır; bütün girdiler o
koşunun ürettiği nesnelerdir (`motor.Durum`, `depo.Depo`, haftalık karar
kayıtları, talep/gözlenen satış matrisleri). Döndürülen sözlüğün her
değeri `float`'tır (JSON'a gider); bölme sıfıra gitmeye çalıştığında
0.0 döner, NaN üretilmez.

Mağaza beden payı (`beden_sapmasi` için) `gecmis_satis` ayrı bir parametre
olarak alınmaz: `gozlenen[:bas_gunu]` oyunun başlangıcına kadarki geçmişle
bit bit aynıdır (`oyun.oyna` yalnız oyun günlerini üzerine yazar), bu
yüzden `ihtiyac.magaza_beden_paylari(gozlenen, dunya, bas_gunu)` `oyna`
başında hesaplanan `paylar` ile aynı sonucu verir.
"""

from typing import TYPE_CHECKING

import numpy as np

from . import sabitler
from .depo import Depo, depo_toplami
from .dunya import Dunya
from .ihtiyac import magaza_beden_paylari
from .motor import Durum

if TYPE_CHECKING:
    from .oyun import OyunAyari


def _oran_yuzde(pay: float, payda: float) -> float:
    return round(pay / payda * 100, 1) if payda > 0 else 0.0


def hesapla(
    durum: Durum,
    dunya: Dunya,
    depo: Depo,
    haftalik: list[dict],
    talep: np.ndarray,
    gozlenen: np.ndarray,
    baslangic_stok: float,
    ayar: "OyunAyari",
) -> dict[str, float]:
    bas_gunu = dunya.gun(ayar.bas)
    bit_gunu = dunya.gun(ayar.bit)

    talep_adet = float(talep[bas_gunu : bit_gunu + 1].sum())
    satis_adet = float(gozlenen[bas_gunu : bit_gunu + 1].sum())
    kayip_adet = talep_adet - satis_adet
    kayip_orani = _oran_yuzde(kayip_adet, talep_adet)

    bulunabilirlik = _oran_yuzde(durum.stoklu_talepli_gun, durum.talepli_gun)

    kayitlar = durum.gonderilen_satis_gunleri
    if kayitlar:
        agirlik = np.array([r[3] for r in kayitlar], dtype=float)
        sure = np.array([r[2] - r[1] for r in kayitlar], dtype=float)
        satisa_donme_gun = round(float((agirlik * sure).sum() / agirlik.sum()), 1)
        satilan_gonderilen = float(agirlik.sum())
    else:
        satisa_donme_gun = 0.0
        satilan_gonderilen = 0.0

    satilmayan_gonderilen = float(sum(adet for kuyruk in durum.fifo for _gelis, adet in kuyruk))
    gonderilen_adet = satilan_gonderilen + satilmayan_gonderilen

    koli_sayisi = float(sum(h["koli_sayisi"] for h in haftalik))
    acik_adet = float(sum(h["acik_adet"] for h in haftalik))
    toplama_maliyeti_tl = acik_adet * sabitler.ACIK_TL_ADET + koli_sayisi * sabitler.KOLI_TL

    if haftalik:
        ortalama_acik = acik_adet / len(haftalik)
        acik_doluluk = _oran_yuzde(ortalama_acik, ayar.acik_kapasite)
    else:
        acik_doluluk = 0.0

    magaza_stok_son = float(durum.stok.sum())
    depo_kalan = float(depo_toplami(depo))

    stok_oc = durum.stok[dunya.oc_hucre].astype(float)  # float[OC, 5]
    oc_toplam = stok_oc.sum(axis=1)
    stoklu = oc_toplam > 0

    kirik_cift = int(np.count_nonzero(stoklu & (stok_oc[:, [1, 2, 3]] == 0).any(axis=1)))
    stoklu_cift_sayisi = int(np.count_nonzero(stoklu))
    bos_cift_sayisi = int(stoklu.size - stoklu_cift_sayisi)
    kirik_cift_pay_yuzde = _oran_yuzde(kirik_cift, stoklu_cift_sayisi)

    if stoklu.any():
        paylar = magaza_beden_paylari(gozlenen, dunya, bas_gunu)
        dagilim = np.zeros_like(stok_oc)
        dagilim[stoklu] = stok_oc[stoklu] / oc_toplam[stoklu, None]
        tvd = 0.5 * np.abs(dagilim[stoklu] - paylar[stoklu]).sum(axis=1)
        beden_sapmasi = round(float(tvd.mean() * 100), 1)
    else:
        beden_sapmasi = 0.0

    str_orani = _oran_yuzde(satis_adet, baslangic_stok + gonderilen_adet)

    return {
        "talep_adet": talep_adet,
        "satis_adet": satis_adet,
        "kayip_adet": kayip_adet,
        "kayip_orani": kayip_orani,
        "bulunabilirlik": bulunabilirlik,
        "satisa_donme_gun": satisa_donme_gun,
        "satilmayan_gonderilen": satilmayan_gonderilen,
        "gonderilen_adet": gonderilen_adet,
        "koli_sayisi": koli_sayisi,
        "acik_adet": acik_adet,
        "toplama_maliyeti_tl": toplama_maliyeti_tl,
        "acik_doluluk": acik_doluluk,
        "magaza_stok_son": magaza_stok_son,
        "depo_kalan": depo_kalan,
        "kirik_cift": float(kirik_cift),
        "stoklu_cift_sayisi": float(stoklu_cift_sayisi),
        "bos_cift_sayisi": float(bos_cift_sayisi),
        "kirik_cift_pay_yuzde": kirik_cift_pay_yuzde,
        "beden_sapmasi": beden_sapmasi,
        "str": str_orani,
    }


def _hucre_line(dunya: Dunya) -> np.ndarray:
    """str[H]: her hücrenin line'ı, option-mağaza eşlemesinden türetilir."""
    hucre_line = np.empty(len(dunya.hucre_urun), dtype=object)
    for oc in range(len(dunya.oc_hucre)):
        hucre_line[dunya.oc_hucre[oc]] = dunya.oc_line[oc]
    return hucre_line


def line_kirilimi(
    durum: Durum,
    dunya: Dunya,
    talep: np.ndarray,
    gozlenen: np.ndarray,
    bas_gunu: int,
    bit_gunu: int,
) -> dict[str, dict[str, float]]:
    """line → {talep_adet, satis_adet, kayip_orani, bulunabilirlik, magaza_stok_son}.

    Toplam rakam NOS ile Collection'ı birbirine karıştırır: NOS'un stoğu
    tanımı gereği bitmemeli, Collection ise sezonla gelip gider. Aynı
    replenishment kuralının ikisine ne yaptığı ancak burada görülür.

    Bulunabilirlik, talebin olduğu (hücre, gün) çiftlerinin kaçında rafta
    mal bulunduğudur; `durum.stoklu_gunluk` satıştan ÖNCE yazıldığı için
    ölçüm anı motorun kendi sayaçlarıyla aynıdır.
    """
    hucre_line = _hucre_line(dunya)
    pencere = slice(bas_gunu, bit_gunu + 1)
    talep_p = talep[pencere]
    satis_p = gozlenen[pencere]
    stoklu_p = durum.stoklu_gunluk[pencere]
    talepli = talep_p > 0

    sonuc: dict[str, dict[str, float]] = {}
    for line in sorted({str(x) for x in hucre_line}):
        sutun = hucre_line == line
        t_adet = float(talep_p[:, sutun].sum())
        # Satış gerçekleşen satış matrisinden gelir. "Stoklu gündeki talep"
        # diye yaklaşık hesaplamak kısmi karşılamayı yanlış sayardı: stok 3
        # iken talep 5 ise o gün 3 satılır, 5 değil.
        karsilanan = float(satis_p[:, sutun].sum())
        talepli_gun = int(talepli[:, sutun].sum())
        stoklu_talepli = int((talepli[:, sutun] & stoklu_p[:, sutun]).sum())
        sonuc[line] = {
            "talep_adet": t_adet,
            "satis_adet": karsilanan,
            "kayip_orani": _oran_yuzde(t_adet - karsilanan, t_adet),
            "bulunabilirlik": _oran_yuzde(stoklu_talepli, talepli_gun),
            "magaza_stok_son": float(durum.stok[sutun].sum()),
        }
    return sonuc
