"""Vakanın sabitleri (spec 2026-10-19-ilk-sevkiyat-design, Global Constraints).

Değerler ölçüme göre değişebilir; değişiklik kayıt defterine Ruling olarak yazılır.
`LUMODA_ILK_PAYI`, v4 üretecinin `ILK_DAGITIM_PAYI`'yla aynı olmak zorundadır (testte
sınanır; vaka kodu `perakende_veri`'yi içe aktarmaz).
"""

from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
CIKTI = KOK / "cikti"

OYUN_SEZONU = "SS25"     # ilk sevkiyatı yeniden dağıttığımız sezon
KAL_SEZONU = "SS24"      # kalibrasyon sezonu (kapanmış, yayımlanan veriden)
LINE = "Collection"      # oyun yalnız bu line'ın option'larını dağıtır

LUMODA_ILK_PAYI = 0.70   # Lumoda ilk alımın bu payını mağazalara dağıtır, kalanı depoda kalır

ERKEN_GUN = 42           # erken talep penceresi: lansmandan itibaren 6 hafta
ERKEN_KESIM_GUN = 29     # erken pencere kesimi = sezonun indirim_baslangic'ı - 29 gün

TUTMA_DUZEYLERI = (0.0, 0.15, 0.30, 0.45)   # depoda tutulan pay (ızgara)
DEMO_TUTMA = (0.0, 0.15, 0.30)              # demo kadranında gösterilen düzeyler

BELIRSIZLIK_TBAR = 0.30  # belirsizlik eğrisinin dönüm noktası
TAVAN_KAPSAMA = 1.0      # tavan: öngörülen erken talebin katı

HIZ_GECMIS_GUN = 14      # son 14 günün stoklu gün hızı
HIZ_HEDEF_GUN = 28       # x 28 gün

YOL_SAYISI = 5           # talep tohumu yolları (yol 0 = yayımlanan tohum, `None`)
TALEP_TOHUM_TABANI = 20261019
