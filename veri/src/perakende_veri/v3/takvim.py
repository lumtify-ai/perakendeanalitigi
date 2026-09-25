"""v3 takvimi ve sezon tablosu.

İki takvim vardır: simülasyonun yürüdüğü tam takvim (ısınma dahil) ve
dışa aktarılan pencere. Gün indisi her yerde TAM takvimin indisidir
(0 = 2023-07-03); vakalar da aynı indisle çalışır.
"""

import numpy as np
import pandas as pd

from ..takvim import ILKBAHAR_YAZ_AYLARI
from . import sabitler


def sezon_tablosu() -> pd.DataFrame:
    """`sezon` tablosu: sezon × dalga başına bir satır (15 satır)."""
    satirlar = []
    for kod, s in sabitler.SEZONLAR.items():
        for dalga, lansman in enumerate(s["dalgalar"], start=1):
            satirlar.append(
                {
                    "sezon_kodu": kod,
                    "dalga": dalga,
                    "lansman_tarihi": pd.Timestamp(lansman),
                    "indirim_baslangic": pd.Timestamp(s["indirim"]),
                    "cikis_tarihi": pd.Timestamp(s["cikis"]),
                }
            )
    return pd.DataFrame(satirlar)


def _ticari_sezon(tarihler: pd.DatetimeIndex) -> list[str]:
    """Tarihin ticari sezon kodu: son ilk dalgası başlamış sezon.

    SS24, 2024-02-12'de ilk dalgası mağazaya girdiği gün başlar ve AW24'ün
    ilk dalgasına kadar sürer. İndirimdeki eski sezonun ürünü rafta dursa
    da ticari takvim yeni sezondadır.
    """
    baslangiclar = sorted(
        (pd.Timestamp(s["dalgalar"][0]), kod) for kod, s in sabitler.SEZONLAR.items()
    )
    kodlar = []
    for t in tarihler:
        uygun = [kod for bas, kod in baslangiclar if bas <= t]
        kodlar.append(uygun[-1] if uygun else "AW23")
    return kodlar


def _indirim_donemi(tarihler: pd.DatetimeIndex) -> np.ndarray:
    """Herhangi bir sezonun planlı indirimindeyse True (indirim ≤ t < çıkış)."""
    sonuc = np.zeros(len(tarihler), dtype=bool)
    for s in sabitler.SEZONLAR.values():
        sonuc |= (tarihler >= pd.Timestamp(s["indirim"])) & (
            tarihler < pd.Timestamp(s["cikis"])
        )
    return sonuc


def takvim_uret(baslangic=None, bitis=None) -> pd.DataFrame:
    """Tarih boyutu. Varsayılan: dışa aktarılan pencere (731 gün)."""
    tarihler = pd.date_range(
        baslangic or sabitler.BASLANGIC, bitis or sabitler.BITIS, freq="D"
    )
    return pd.DataFrame(
        {
            "tarih": tarihler,
            "hafta": tarihler.isocalendar().week.astype(int).to_numpy(),
            "ay": tarihler.month,
            "yil": tarihler.year,
            "sezon": [
                "İlkbahar/Yaz" if ay in ILKBAHAR_YAZ_AYLARI else "Sonbahar/Kış"
                for ay in tarihler.month
            ],
            "sezon_kodu": _ticari_sezon(tarihler),
            "tatil_mi": [t.strftime("%Y-%m-%d") in sabitler.TATILLER for t in tarihler],
            "indirim_donemi_mi": _indirim_donemi(tarihler),
        }
    )


def simulasyon_takvimi() -> pd.DataFrame:
    """Isınma dahil tam takvim; satır indisi = gün indisi."""
    return takvim_uret(sabitler.ISINMA_BASLANGIC, sabitler.BITIS)


def gun_indisi(tarih) -> int:
    """Tarihin tam takvimdeki indisi (0 = ISINMA_BASLANGIC). Pencere dışı olabilir."""
    return int((pd.Timestamp(tarih) - pd.Timestamp(sabitler.ISINMA_BASLANGIC)).days)
