"""Kırıklık ve atıl stok ölçüleri (tasarım §0, K1 ve K2). Saf pandas/numpy; karar ve ölçüm ikisi de bunu içe aktarır.

**Kırık beden:** asortide olan ama mağazada stoğu sıfır olan beden. **Net kırıklık** = kırık beden ÷ beden
sayısı; sıfırdan büyük (mağaza, option) çifti **kırık çifttir**. **Brüt kırıklık** = Σ max(0, asorti − stok)
÷ Σ asorti (eksik adet; asortinin altındaki ama sıfır olmayan beden brüte girer, neti etkilemez). **Dar
kırık** Blok Transfer'in tanımıdır: ara bedenlerden (sıra 2–4) biri sıfır.

Toplu oranlar stoklu çiftler üzerinden toplu hesaplanır (Σ pay ÷ Σ payda, çift oranlarının ortalaması değil);
stoğu sıfır çift hiçbir paydaya girmez.

**Atıl stok:** pencere (28 gün) satışına göre `satmayan` (0), `atil` (1 ile eşik arası), `satan`; rafta
pencereden kısa süredir duran `yeni` sayılır ve ne atıl ne satmayandır.
"""

import numpy as np
import pandas as pd

from kiriklik import sabitler

_BEDEN_SIRALARI = (1, 2, 3, 4, 5)
_ARA_SIRALAR = (2, 3, 4)   # Blok Transfer'in dar tanımı


def cift_tablosu(hucre: pd.DataFrame, asorti: tuple[int, ...] = sabitler.ASORTI) -> pd.DataFrame:
    """Stoklu (mağaza, option) çifti başına kırıklık ölçüleri.

    `hucre` [magaza_id, option_id, beden_sira, stok] (fazla sütunlar yok sayılır); bedenler 1–5, eksik beden
    satırı 0 stoktur. Çıktı [magaza_id, option_id, stok, beden, kirik_beden, eksik_adet, asorti_top, net,
    brut, kirik, dar_kirik]; `stok` çiftin toplam adedidir, stoğu 0 çift çıkmaz.
    """
    if len(asorti) != len(_BEDEN_SIRALARI):
        raise ValueError(f"asorti {len(_BEDEN_SIRALARI)} bedenlidir: {asorti}")
    if len(hucre) and not hucre.beden_sira.isin(_BEDEN_SIRALARI).all():
        raise ValueError("beden_sira yalnız 1–5 olabilir")
    genis = (hucre.pivot_table(index=["magaza_id", "option_id"], columns="beden_sira", values="stok",
                               aggfunc="sum", fill_value=0)
             .reindex(columns=list(_BEDEN_SIRALARI), fill_value=0))
    st = genis.to_numpy(dtype=np.int64)
    a = np.asarray(asorti, dtype=np.int64)
    ara = np.isin(_BEDEN_SIRALARI, _ARA_SIRALAR)
    toplam = st.sum(axis=1)
    kirik_beden = (st == 0).sum(axis=1)
    eksik = np.maximum(0, a - st).sum(axis=1)
    cift = genis.index.to_frame(index=False)
    cift["stok"] = toplam
    cift["beden"] = len(_BEDEN_SIRALARI)
    cift["kirik_beden"] = kirik_beden
    cift["eksik_adet"] = eksik
    cift["asorti_top"] = int(a.sum())
    cift["net"] = kirik_beden / len(_BEDEN_SIRALARI)
    cift["brut"] = eksik / int(a.sum())
    cift["kirik"] = kirik_beden > 0
    cift["dar_kirik"] = (st[:, ara] == 0).any(axis=1)
    return cift[toplam > 0].reset_index(drop=True)


def ozet(cift: pd.DataFrame) -> dict:
    """`cift_tablosu` çıktısının toplu ölçüleri (oranlar 0–1; payda sıfırsa 0.0).

    Mutlak sayılar (`kirik_cift`, `kirik_beden`, `eksik_adet`) oranların yanında kalır: vericiyi boşaltmak
    çifti paydadan çıkarıp oranı yapay iyileştirebilir.
    """
    n = len(cift)
    beden, asorti = int(cift.beden.sum()), int(cift.asorti_top.sum())
    kirik_beden, eksik = int(cift.kirik_beden.sum()), int(cift.eksik_adet.sum())
    kirik_cift = int(cift.kirik.sum())
    return {
        "stoklu_cift": n, "kirik_cift": kirik_cift, "dar_kirik_cift": int(cift.dar_kirik.sum()),
        "kirik_beden": kirik_beden, "beden": beden, "eksik_adet": eksik, "asorti": asorti,
        "net_oran": kirik_beden / beden if beden else 0.0,
        "brut_oran": eksik / asorti if asorti else 0.0,
        "kirik_cift_oran": kirik_cift / n if n else 0.0,
    }


def atil_sinifi(satis_28: np.ndarray, rafta_28: np.ndarray, esik: int) -> np.ndarray:
    """Pencere satışına göre sınıf: `satmayan` (satış 0), `atil` (1 ≤ satış ≤ `esik`), `satan` (> esik);
    rafta `ATIL_PENCERE_GUN`'den az gündür duran `yeni` (satışına bakılmadan)."""
    satis = np.asarray(satis_28)
    sinif = np.where(satis <= 0, "satmayan", np.where(satis <= esik, "atil", "satan"))
    return np.where(np.asarray(rafta_28) < sabitler.ATIL_PENCERE_GUN, "yeni", sinif)
