"""Koşu ölçütleri (asgari; Ruling R22, Görev 10 genişletir).

Her ölçüt bir koşunun (`motor.Kosu` ya da tembel `KosuKaydi`) gizli gerçeğinden
ve tablolarından, bir pencerede (`[bas, bit]`, iki ucu dahil), fiziksel mağazalarda
(online `ONL` hariç) hesaplanır. Bu modül motoru içe aktarmaz; koşu nesnesini
çağıran verir (`tablo(ad, sutunlar)` ve `kayitlar`).

    bulunabilirlik     |talep > 0 ∧ kendi_satis > 0| / |talep > 0|, hücre-gün, yüzde.
                       v2'nin "satış öncesi stoklu talepli gün / talepli gün"üne
                       eşdeğer: raf stoğu ≥ 1 ve talep ≥ 1 ise hücre kendi talebinden
                       en az birini satar; stoksuzsa kendi satışı 0'dır (gizli gerçek
                       `kendi_satis`, ikame satışı hariç). Günlük stok yeniden kurulmaz.
    toplama_maliyeti   Σ açık adet × `ACIK_TL_ADET` + Σ koli × `KOLI_TL`, kolun hafta
                       tablosundan (`politika.hafta_tablosu`; pencere = kolun pencere
                       pazartesileri). Anlatı varsayımı.
    magaza_stok_son    pencerenin son pazartesi fotoğrafındaki (`stok`, `tarih ≤ bit`)
                       fiziksel mağaza stoğu. Fotoğraf o sabah, hareketlerden önce
                       çekilir (önceki gün sonu stoğu): son pazartesinin sevki girmez.
                       Oyun penceresinin sonundan sonra fotoğraf yoktur; ölçü iki
                       pencerede aynı tanımla alınsın diye son fotoğraf.
"""

from datetime import date

import numpy as np
import pandas as pd

from .kaynak import ONLINE
from .politika import hafta_tablosu
from .sabitler import ACIK_TL_ADET, KOLI_TL


def _pencerede(df: pd.DataFrame, bas: date, bit: date) -> np.ndarray:
    t = pd.to_datetime(df["tarih"]).dt.normalize()
    return ((t >= pd.Timestamp(bas)) & (t <= pd.Timestamp(bit))).to_numpy()


def _fiziksel(df: pd.DataFrame) -> np.ndarray:
    return (df["magaza_id"].astype(str) != ONLINE).to_numpy()


def bulunabilirlik(gercek: pd.DataFrame, bas: date, bit: date) -> float:
    """Yüzde (modül notu); pencerede talepli fiziksel hücre-gün yoksa 0."""
    s = _pencerede(gercek, bas, bit) & _fiziksel(gercek) & (gercek["talep"].to_numpy() > 0)
    payda = int(s.sum())
    if payda == 0:
        return 0.0
    return 100.0 * int((s & (gercek["kendi_satis"].to_numpy() > 0)).sum()) / payda


def toplama_maliyeti(hafta: pd.DataFrame) -> float:
    """TL; `hafta` = `politika.hafta_tablosu(kosu)` (boşsa 0)."""
    acik = float(hafta["acik_adet"].sum()) if "acik_adet" in hafta else 0.0
    koli = float(hafta["koli_sayisi"].sum()) if "koli_sayisi" in hafta else 0.0
    return acik * ACIK_TL_ADET + koli * KOLI_TL


def magaza_stok_son(stok: pd.DataFrame, bit: date) -> float:
    """Adet (modül notu); `bit`'e kadar fotoğraf yoksa `ValueError`."""
    t = pd.to_datetime(stok["tarih"]).dt.normalize()
    once = (t <= pd.Timestamp(bit)).to_numpy()
    if not once.any():
        raise ValueError(f"{bit} ya da öncesinde stok fotoğrafı yok")
    son = t[once].max()
    s = (t == son).to_numpy() & _fiziksel(stok)
    return float(stok["adet"].to_numpy()[s].sum(dtype=np.int64))


def temel_olcutler(kosu, bas: date, bit: date) -> dict[str, float]:
    """Kalibrasyonun ölçütleri: `bulunabilirlik`, `toplama_maliyeti_tl`,
    `magaza_stok_son` ve haftalık toplamlar (`acik_adet`, `koli_sayisi`, `koli_adet`,
    `gonderilen_adet`; kolun pencere pazartesileri)."""
    hafta = hafta_tablosu(kosu)
    toplam = {a: float(hafta[a].sum()) if a in hafta else 0.0
              for a in ("acik_adet", "koli_sayisi", "koli_adet", "gonderilen_adet")}
    return {
        "bulunabilirlik": bulunabilirlik(kosu.tablo("gercek", ["tarih", "magaza_id", "talep", "kendi_satis"]),
                                         bas, bit),
        "toplama_maliyeti_tl": toplama_maliyeti(hafta),
        "magaza_stok_son": magaza_stok_son(kosu.tablo("stok", ["tarih", "magaza_id", "adet"]), bit),
        **toplam,
    }
