"""Transfer planı: kolların ürettiği hareket listesi ve kimliği (tasarım §0, K7). Karar modülü: saf pandas.

Plan karar gününde üretilir, `elle_transfer` yuvasına enjekte edilir (simülasyon kapısı), ölçülür ve ızgara
koşu anahtarına kimliğiyle girer. Kol (kural, model) yalnız bu yapıyı üretir; plan motoru, hakemi ya da gizli
gerçeği tanımaz.
"""

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

KOLONLAR = ["option_id", "urun_id", "beden_sira", "verici", "alici", "adet"]
_SIRA = ["option_id", "alici", "verici", "beden_sira"]


def _bos_hareket() -> pd.DataFrame:
    return pd.DataFrame({"option_id": pd.Series(dtype=object), "urun_id": pd.Series(dtype=object),
                         "beden_sira": pd.Series(dtype="int64"), "verici": pd.Series(dtype=object),
                         "alici": pd.Series(dtype=object), "adet": pd.Series(dtype="int64")})


@dataclass(frozen=True, eq=False)
class Plan:
    """Bir kolun bir sezondaki transfer planı.

    `hareketler` [option_id, urun_id, beden_sira, verici, alici, adet]: magaza_id'lerle, satırlar
    (option_id, alici, verici, beden_sira) sırasında, adet > 0 ve tamsayı değerli (sıra zorlanmaz: `kimlik`
    sıradan bağımsızdır); (option_id, alici, verici, beden_sira) anahtarı tekildir.
    `bilgi` kola özel kayıttır (puanlar, çözüm durumu, gap, girdi kaynağı); kimliğe girmez.
    """
    kol: str
    sezon: str
    hareketler: pd.DataFrame
    bilgi: dict = field(default_factory=dict)
    _kimlik: str = field(init=False, repr=False)

    def __post_init__(self):
        h = self.hareketler
        if list(h.columns) != KOLONLAR:
            raise ValueError(f"hareketler sütunları {KOLONLAR} olmalı: {list(h.columns)}")
        if (h.adet <= 0).any():
            raise ValueError("hareket adedi pozitif olmalı")
        if (h.adet.to_numpy(dtype=float) != np.round(h.adet.to_numpy(dtype=float))).any():
            raise ValueError("hareket adedi tamsayı değerli olmalı")
        if h.duplicated(_SIRA).any():
            raise ValueError(f"hareket anahtarı {_SIRA} tekil olmalı")
        h = h[KOLONLAR].astype({"beden_sira": "int64", "adet": "int64"})      # savunma kopyası
        object.__setattr__(self, "hareketler", h)
        csv = h.sort_values(_SIRA, kind="mergesort").to_csv(index=False, lineterminator="\n")
        object.__setattr__(self, "_kimlik",
                           hashlib.sha256(f"{self.kol}\n{self.sezon}\n{csv}".encode()).hexdigest())

    @property
    def kimlik(self) -> str:
        """sha256: kol + sezon + `hareketler`'in kanonik CSV'si (satırlar (option_id, alici, verici,
        beden_sira) sıralı, sabit sütun sırası, tamsayı adet). Girdi satır sırasından bağımsızdır. Kurulurken
        bir kez hesaplanır (plan değişmez kabul edilir)."""
        return self._kimlik


def bos(kol: str, sezon: str, bilgi: dict) -> Plan:
    """Hareketsiz plan (kimliği yalnız kol ve sezondan)."""
    return Plan(kol=kol, sezon=sezon, hareketler=_bos_hareket(), bilgi=dict(bilgi))


def rotalar(hareketler: pd.DataFrame) -> pd.DataFrame:
    """Tekil (verici, alıcı) mağaza çifti, bütün option'lar üzerinden: [verici, alici, adet, option_sayisi].
    Kargo çift başına bir kez ödenir (K19)."""
    if hareketler.empty:
        return pd.DataFrame({"verici": pd.Series(dtype=object), "alici": pd.Series(dtype=object),
                             "adet": pd.Series(dtype="int64"), "option_sayisi": pd.Series(dtype="int64")})
    r = (hareketler.groupby(["verici", "alici"], sort=True)
         .agg(adet=("adet", "sum"), option_sayisi=("option_id", "nunique")).reset_index())
    return r.astype({"adet": "int64", "option_sayisi": "int64"})
