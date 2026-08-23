from datetime import date
from pathlib import Path

TOHUM = 42
VERI_SURUMU = "v1"

BASLANGIC = date(2025, 1, 1)
BITIS = date(2025, 12, 31)

MAGAZA_SAYISI = 25
MODEL_SAYISI = 80

BEDENLER = ["XS", "S", "M", "L", "XL"]
RENKLER = ["Siyah", "Bej", "Lacivert"]

MAGAZA_TIPLERI = ["AVM", "Cadde", "Outlet"]

SEHIRLER = [
    "İstanbul", "Ankara", "İzmir", "Bursa", "Antalya",
    "Adana", "Konya", "Gaziantep", "Kayseri", "Trabzon",
]

KATEGORILER = {
    "Üst Giyim": ["Tişört", "Gömlek", "Kazak", "Sweatshirt"],
    "Alt Giyim": ["Pantolon", "Jean", "Etek", "Şort"],
    "Dış Giyim": ["Mont", "Ceket", "Trençkot"],
}

# --- Ürün hiyerarşisi -------------------------------------------------
# Moda perakendesinde ürün hiyerarşisi kararın kendisidir: transfer,
# ikmal ve sevkiyat algoritmalarının tamamı kapsamını bu ağaç üzerinden
# tanımlar. Sıra: cinsiyet > ana kategori > alt kategori > line.

CINSIYETLER = ["Kadın", "Erkek", "Unisex"]
CINSIYET_PAYLARI = [0.52, 0.38, 0.10]

# Ürün çizgisi (line): aynı alt kategorinin tasarım/kullanım ailesi
LINELER = ["Basic", "Denim", "Casual", "Klasik", "Spor"]

# Mevsimsellik: sezonluk ürün sezonuyla gelir gider; devamlı (NOS) ürün
# yıl boyu satar ve stoğu hiç bitmemelidir. Transfer kararı ikisinde
# farklı işler, bu yüzden ayrı bir eksen olarak tutulur.
MEVSIMSELLIKLER = ["Sezonluk", "Devamlı"]

# Basic ve Denim çizgileri ağırlıklı olarak devamlı; diğerleri sezonluk
LINE_DEVAMLI_OLASILIGI = {
    "Basic": 0.80, "Denim": 0.55, "Casual": 0.20, "Klasik": 0.25, "Spor": 0.30,
}

SEZON_GRUPLARI = {"S1": "2025-İlkbahar/Yaz", "S2": "2025-Sonbahar/Kış"}

URETICILER = [
    "Ege Tekstil", "Marmara Konfeksiyon", "Denizli Örme",
    "Bursa Dokuma", "Çorlu Giyim",
]

MARKA = "Vesta"

# sabitler.py -> perakende_veri -> src -> veri  (parents[2] = veri/)
CIKTI_DIZINI = Path(__file__).resolve().parents[2] / "cikti" / VERI_SURUMU
