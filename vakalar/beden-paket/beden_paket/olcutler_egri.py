"""Beden eğrisi ölçütleri (ölçüm modülü; kararlara girmez).

    uzaklik     tahmin edilen eğrinin gerçeğe (hakem) mağaza başına L1 uzaklığı Σ_b |p̂_b − p_b|
                (0..2); tahminin her mağazasının gerçeği olmalı
    kararlilik  iki eğri tablosunun (örn. iki sezonun karar anında okunan eğriler) ortak
                mağazalardaki L1 uzaklığı (hakemsiz)
    ari         profil atamasının gizli beden kaymasına ARI'si (ortak mağazalarda)
"""

import pandas as pd
from sklearn.metrics import adjusted_rand_score

SUTUNLAR = ["b1", "b2", "b3", "b4", "b5"]


def _l1(a: pd.DataFrame, b: pd.DataFrame, ids) -> pd.Series:
    A = a.loc[ids, SUTUNLAR].to_numpy(dtype="float64")
    B = b.loc[ids, SUTUNLAR].to_numpy(dtype="float64")
    return pd.Series(abs(A - B).sum(axis=1), index=pd.Index(list(ids), name="magaza_id"), name="l1")


def uzaklik(tahmin: pd.DataFrame, gercek: pd.DataFrame) -> pd.Series:
    """Mağaza → L1 (tahmin satır sırasıyla)."""
    eksik = [m for m in tahmin.index if m not in gercek.index]
    if eksik:
        raise KeyError(f"gerçeği olmayan mağaza: {eksik}")
    return _l1(tahmin, gercek, list(tahmin.index))


def kararlilik(egri_a: pd.DataFrame, egri_b: pd.DataFrame) -> pd.Series:
    """Ortak mağazalarda (egri_a sırasıyla) iki eğrinin L1 uzaklığı."""
    ortak = [m for m in egri_a.index if m in egri_b.index]
    return _l1(egri_a, egri_b, ortak)


def ari(profil: pd.Series, kayma: pd.Series) -> float:
    """Profil etiketlerinin gizli kaymaya ARI'si (ortak mağazalarda)."""
    ortak = [m for m in profil.index if m in kayma.index]
    return float(adjusted_rand_score(kayma.loc[ortak].to_numpy(), profil.loc[ortak].astype(str).to_numpy()))
