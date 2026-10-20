"""Vakanın sabitleri (spec 2026-10-20-magaza-kumeleme-design, Global Constraints).

Değerler ölçüme göre değişebilir; değişiklik kayıt defterine Ruling olarak yazılır.
Bu modül tarafsızdır: `perakende_veri`'yi ve gizli gerçeği bilmez.
"""

from pathlib import Path

import pandas as pd

KOK = Path(__file__).resolve().parents[1]
CIKTI = KOK / "cikti"

# Karar günleri: bir sezonun ilk Collection dalgasının lansmanından önceki cuma. Kümeler
# yalnız bu güne kadarki yayımlanan veriyle kurulur.
KARAR_GUNU = pd.Timestamp("2025-02-07")       # SS25 (oyun sezonu; İlk Sevkiyat ile aynı gün)
KAL_KARAR_GUNU = pd.Timestamp("2024-02-09")   # SS24 (kalibrasyon sezonu)

GECMIS_HAFTA_ESIGI = 26   # karar gününden önce bu kadar satışlı hafta yoksa mağaza "yeni"

CIRO_A = 0.20             # ciro sınıfı: ilk %20 A, sonraki %30 B, kalan C (anlatı varsayımı)
CIRO_B = 0.30
K3_EN_AZ = 3              # bölge × ciro sınıfı hücresi bundan küçükse komşu sınıfa birleşir

K_ARALIK = range(3, 11)   # makine öğrenmesi kümelerinde denenen küme sayıları
EN_KUCUK_KUME = 3         # k seçiminde en küçük kümenin alt sınırı
KMEANS_N_INIT = 50

TOHUM = 20261020
YOL_SAYISI = 5            # İlk Sevkiyat ile aynı: talep tohumu yolları
