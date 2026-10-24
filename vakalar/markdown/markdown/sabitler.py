"""Vaka sabitleri (spec §0, Global Constraints). Karar modülüdür: `perakende_veri`'yi içe aktarmaz.

Ölçüme göre bir Ruling'le değişebilir; değiştiren görev sabiti burada değiştirir ve kayıt defterine
Ruling yazar.
"""

# Test ve kalibrasyon sezonları (spec §0/5, §4.3): her koşu tek test sezonudur.
TEST_SEZONLARI = ("AW24", "SS25")
KAL_SEZONLARI = ("AW23", "SS24")
LINE = "Collection"

# Kademe merdiveni Lumoda'nınki (spec §0/8): oran geri alınmaz.
KADEMELER = (0.0, 0.20, 0.30, 0.40, 0.50, 0.70)

# Karar penceresi (spec §0/7): en erken gün max(indirim_gun - ERKEN_GUN, lansman_gun + RPT_SON_GUN).
ERKEN_GUN = 56       # indirimden önce en erken (8 hafta)
RPT_SON_GUN = 42     # lansman + 42 = option'ın RPT penceresinin son günü

TAKVIM_TABANI = 0.30     # takvime bağlı kol: indirim gününden itibaren en az bu oran

HIZ_GUN = 14            # satış hızı pencereleri (gün)
HIZ_GUN_UZUN = 28
YOL_SAYISI = 5          # oyun yolları (talep tohumu başına)
TALEP_TOHUM_TABANI = 20261019    # İlk Sevkiyat'ınki
STOK_KOVA = 48          # DP durumu: stok kovası sayısı

# Öğrenme, test sezonunun en erken karar pazartesisinden önceki satırlarla yapılır, bir kez
# (spec §3.1). Değerler `kaynak.karar_penceresi("serbest")`in en küçüğüne eşittir (testle sınanır).
OGRENME_BITIS = {"AW24": "2024-11-11", "SS25": "2025-05-05"}

# Dünyanın gün ekseni: gün 0 = ısınma başı (v4 `takvim.gun_indisi`; pazartesi). Yayımlanan
# tablolar 2023-01-01'den başlar ama gün indisi bu tarihten sayılır. Karar modülü dünyayı içe
# aktarmadığı için sabit burada tutulur; `test_kaynak.py` dünyanın `optionlar` günleriyle sınar.
GUN_SIFIRI = "2022-07-04"
