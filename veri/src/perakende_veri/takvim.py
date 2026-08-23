import pandas as pd

from . import sabitler

# 2025 resmî tatilleri ve perakende için yüksek hacimli günler
TATILLER = {
    "2025-01-01", "2025-03-30", "2025-03-31", "2025-04-01", "2025-04-23",
    "2025-05-01", "2025-05-19", "2025-06-06", "2025-06-07", "2025-06-08",
    "2025-06-09", "2025-07-15", "2025-08-30", "2025-10-29", "2025-11-28",
}

ILKBAHAR_YAZ_AYLARI = {3, 4, 5, 6, 7, 8}


def takvim_uret() -> pd.DataFrame:
    """Tarih boyutunu üretir. Sezon, koleksiyon takvimiyle hizalıdır."""
    tarihler = pd.date_range(sabitler.BASLANGIC, sabitler.BITIS, freq="D")
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
            "tatil_mi": [t.strftime("%Y-%m-%d") in TATILLER for t in tarihler],
        }
    )
