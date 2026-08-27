from datetime import date
from pathlib import Path

TOHUM = 42
VERI_SURUMU = "v2"

BASLANGIC = date(2025, 1, 1)
BITIS = date(2025, 12, 31)

MAGAZA_SAYISI = 25
MODEL_SAYISI = 80

MARKA = "Lumoda"

# --- Mağaza -------------------------------------------------------------

MAGAZA_TIPLERI = ["AVM", "Cadde", "Outlet"]

SEHIRLER = [
    "İstanbul", "Ankara", "İzmir", "Bursa", "Antalya",
    "Adana", "Konya", "Gaziantep", "Kayseri", "Trabzon",
]

# Türkiye moda perakendesinde mağaza dağılımı İstanbul ağırlıklıdır.
# Eşit dağıtmak transfer probleminin coğrafi gerçekliğini bozar.
SEHIR_AGIRLIKLARI = [0.30, 0.13, 0.11, 0.08, 0.08, 0.07, 0.06, 0.06, 0.06, 0.05]

# Mağaza adı zincirde konumu belirtir; şehir adı tek başına yetmez
# çünkü aynı şehirde birden çok mağaza olur.
SEMTLER = {
    "İstanbul": [
        "Kadıköy", "Nişantaşı", "Bağdat Caddesi", "Akmerkez", "Zorlu",
        "Marmara Forum", "Beylikdüzü", "Ataşehir", "Bakırköy", "Kanyon",
    ],
    "Ankara": ["Kızılay", "Panora", "Armada", "Bilkent", "Çayyolu"],
    "İzmir": ["Alsancak", "Bornova", "Karşıyaka", "Optimum"],
    "Bursa": ["Nilüfer", "Korupark", "Osmangazi"],
    "Antalya": ["Lara", "MarkAntalya", "Konyaaltı"],
    "Adana": ["Optimum", "Seyhan"],
    "Konya": ["Kule Site", "Selçuklu"],
    "Gaziantep": ["Şehitkamil", "Sanko Park"],
    "Kayseri": ["Kayseri Park", "Melikgazi"],
    "Trabzon": ["Forum", "Meydan"],
}

# --- Ürün hiyerarşisi ---------------------------------------------------
# Moda perakendesinde hiyerarşi bir sınıflandırma değil kararın kendisidir:
# transfer, ikmal ve sevkiyat algoritmalarının hepsi kapsamını bu ağaç
# üzerinden tanımlar.
#
#   cinsiyet > üst kategori > alt kategori > line > model > option > SKU
#
# model  = ürün kodu + ürün adı (tasarım; fiyat bu düzeyde belirlenir)
# option = model × renk        (planlamanın ve transfer kararının birimi)
# SKU    = option × beden      (en alt stok birimi)

CINSIYETLER = ["Kadın", "Erkek", "Unisex"]
CINSIYET_PAYLARI = [0.52, 0.38, 0.10]

KATEGORILER = {
    "Üst Giyim": ["Tişört", "Gömlek", "Kazak", "Sweatshirt"],
    "Alt Giyim": ["Pantolon", "Jean", "Etek", "Şort"],
    "Dış Giyim": ["Mont", "Ceket", "Trençkot"],
}

# Line, ürünün ticari rolünü ve yaşam döngüsünü söyler. Sezonluk /
# devamlı ayrımı ayrı bir eksen değildir; line onu zaten taşır.
#
#   Basic       Yıl boyu satılan temel ürün, düşük moda riski
#   Collection  Sezonluk koleksiyon; sezonuyla gelir gider, riski yüksek
#   NOS         Never Out of Stock — stoğu asla bitmemesi gereken çekirdek
#   Outlet      Geçmiş sezondan devreden, outlet kanalına yönelen ürün
LINELER = ["Basic", "Collection", "NOS", "Outlet"]
LINE_PAYLARI = [0.30, 0.45, 0.15, 0.10]

RENKLER = {"Siyah": "SYH", "Bej": "BEJ", "Lacivert": "LCV"}

URETICILER = [
    "Ege Tekstil", "Marmara Konfeksiyon", "Denizli Örme",
    "Bursa Dokuma", "Çorlu Giyim",
]

# --- Beden setleri ------------------------------------------------------
# Beden tek bir ölçek değildir. Üst giyim harfle, alt giyim numarayla
# gider; kadın ve erkek numaraları farklıdır. Kırıklık analizi beden
# etiketine değil, setteki SIRAYA bakar — bu yüzden her set beş kademedir
# ve talep eğrisi etiketten bağımsız, konumla tanımlanır.
BEDEN_SETLERI = {
    ("Kadın", "Üst Giyim"): ("Kadın Harf", ["XS", "S", "M", "L", "XL"]),
    ("Kadın", "Dış Giyim"): ("Kadın Harf", ["XS", "S", "M", "L", "XL"]),
    ("Kadın", "Alt Giyim"): ("Kadın Numara", ["34", "36", "38", "40", "42"]),
    ("Erkek", "Üst Giyim"): ("Erkek Harf", ["S", "M", "L", "XL", "XXL"]),
    ("Erkek", "Dış Giyim"): ("Erkek Harf", ["S", "M", "L", "XL", "XXL"]),
    ("Erkek", "Alt Giyim"): ("Erkek Numara", ["30", "32", "34", "36", "38"]),
    ("Unisex", "Üst Giyim"): ("Unisex Harf", ["S", "M", "L", "XL", "XXL"]),
    ("Unisex", "Dış Giyim"): ("Unisex Harf", ["S", "M", "L", "XL", "XXL"]),
    ("Unisex", "Alt Giyim"): ("Unisex Numara", ["30", "32", "34", "36", "38"]),
}

BEDEN_KADEME_SAYISI = 5

# Alt kategori başına kesim/model adı havuzu — ürün adı buradan kurulur
KESIMLER = {
    "Tişört": ["Bisiklet Yaka", "V Yaka", "Oversize", "Slim Fit", "Polo Yaka"],
    "Gömlek": ["Slim Fit", "Regular Fit", "Oduncu", "Keten", "Oxford"],
    "Kazak": ["Balıkçı Yaka", "Bisiklet Yaka", "Hırka", "Örgü Desenli"],
    "Sweatshirt": ["Kapüşonlu", "Bisiklet Yaka", "Oversize", "Fermuarlı"],
    "Pantolon": ["Chino", "Kumaş", "Jogger", "Yüksek Bel", "Wide Leg"],
    "Jean": ["Slim Fit", "Mom Fit", "Straight", "Skinny", "Baggy"],
    "Etek": ["Midi", "Mini", "Pileli", "Kalem"],
    "Şort": ["Bermuda", "Klasik", "Paperbag"],
    "Mont": ["Şişme", "Parka", "Puffer", "Bomber"],
    "Ceket": ["Blazer", "Deri", "Kot", "Süet"],
    "Trençkot": ["Klasik", "Uzun", "Kemerli"],
}

CIKTI_DIZINI = Path(__file__).resolve().parents[2] / "cikti" / VERI_SURUMU
