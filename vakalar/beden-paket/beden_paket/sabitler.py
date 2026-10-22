"""Vakanın sabitleri (spec 2026-10-22-beden-paket-design, Global Constraints).

Değerler ölçüme göre değişebilir; değişiklik kayıt defterine Ruling olarak yazılır.
Bu modül tarafsızdır: `perakende_veri`'yi ve gizli gerçeği bilmez.
"""

from pathlib import Path

import pandas as pd

KOK = Path(__file__).resolve().parents[1]
CIKTI = KOK / "cikti"

# Karar günleri: bir sezonun ilk Collection dalgasının lansmanından önceki cuma. Eğri ve
# paket yalnız bu güne kadarki yayımlanan veriyle kurulur.
KARAR_GUNU = pd.Timestamp("2025-02-07")       # SS25 (oyun sezonu; İlk Sevkiyat ve Kümeleme ile aynı gün)
KAL_KARAR_GUNU = pd.Timestamp("2024-02-09")   # SS24 (kalibrasyon sezonu)

BEDEN_SAYISI = 5                # beden sıralı set başına beden sayısı (beden_sira 1..5); tek bedenliler dışarıda
PAKET_ADET = 7                  # bir paketteki toplam adet
LUMODA_PAKET = (1, 2, 2, 1, 1)  # Lumoda'nın tek paket tipi (yayımlanan `paket` tablosu)
CEKIRDEK_BEDENLER = (2, 3, 4)   # beden_sira; her pakette en az 1
K_LISTESI = (1, 2, 3, 4)        # ortak paket deseni sayısı

EGRI_PENCERE_HAFTA = 8          # eğri: option lansmanından sonraki ilk haftalar
GECMIS_PENCERE_HAFTA = 104      # eğri: karar gününden önceki son tamamlanmış hafta sayısı

TOHUM = 20261022
YOL_SAYISI = 5                  # İlk Sevkiyat ile aynı: talep tohumu yolları
