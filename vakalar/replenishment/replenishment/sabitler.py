"""Vakanın sabitleri (spec 2026-10-10-depodan-magazaya-v4, Global Constraints).

Düzey ve katlar (`ALIM_DUZEYLERI`, `TAVAN_KATLARI`) yürütmede ölçüme göre
değişebilir; değişiklik kayıt defterine Ruling olarak yazılır.
"""

from datetime import date
from math import inf
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
CIKTI = KOK / "cikti"

# Oyun penceresi: AW25'in 18 replenishment pazartesisi
OYUN_BAS, OYUN_BIT = date(2025, 9, 1), date(2025, 12, 31)
# Kalibrasyon penceresi: bir önceki sonbahar (oyundan bir yıl önce)
KAL_BAS, KAL_BIT = date(2024, 9, 2), date(2024, 12, 31)
# Öğrenmenin son günü: AW25 lansmanından önce; alım düzeyinden bağımsız
EGITIM_BIT = date(2025, 8, 17)

# Açık (koli açılarak) gönderimde line başına açık stok payı
ACIK_PAYI = {"Collection": 0.20, "Outlet": 0.20, "NOS": 0.40, "Basic": 0.40}
ACIK_TL_ADET = 10      # açık adet toplama maliyeti (TL / adet)
KOLI_TL = 20           # koli toplama maliyeti (TL / koli)
TAVAN_ORANI = 0.25     # haftalık açık toplama tavanı (haftalık satışın oranı)

# Kıtlık ekseni: ilk alım düzeyi (planın kesri) ve açık toplama tavanı katları
ALIM_DUZEYLERI = (0.4, 0.7, 1.0)
TAVAN_KATLARI = (0.4, 0.6, 1.0, 1.6, inf)
# Demo kadranının tavan konumları
DEMO_TAVANLARI = {"kisitsiz": inf, "gevsek": 1.6, "siki": 0.6}

# Talep yolları: yol p > 0 için tohum TALEP_TOHUM_TABANI + p; yol 0 yayımlanan
# dünyadır (talep tohumu None)
YOL_SAYISI = 5
TALEP_TOHUM_TABANI = 20261010
