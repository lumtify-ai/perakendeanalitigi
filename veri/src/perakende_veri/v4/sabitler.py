"""v4 sabitleri (Görev 3: pencere ve takvim). Sonraki görevler mağaza,
ürün, tedarik, talep, plan sabitlerini bu dosyaya ekler; tek yer burasıdır.

v4 hiçbir v2/v3/kök modülünü içe aktarmaz. Spec:
.superpowers/sdd/2026-09-27-veri-v4-cekirdek/{global,task-3-brief}.md
"""

from datetime import date
from pathlib import Path

TOHUM = 2026

# --- Pencere --------------------------------------------------------------
# Isınma, dışa aktarılan pencereden altı ay önce, 2022-07-04 (pazartesi)
# başlar: AW22'nin dalgaları pencere açıldığında rafta ve depoda otursun,
# "ilk gün" yapaylığı yaşanmasın diye (v3'ün ısınma mantığının bir yıl
# geriye uzatılmış hâli).
ISINMA_BASLANGIC = date(2022, 7, 4)
BASLANGIC = date(2023, 1, 1)
BITIS = date(2025, 12, 31)
UZATMA_GUN = 180  # pencere sonrası uzatma: iade/kirlenme kuyruğu bitişte kesilmesin

# Enflasyon yok; yalnız yıl büyümesi. 2025 talebi 2024'ün %6 üstü; 2023 bir
# yıl, 2022 iki yıl gerisinde aynı eğilimin.
YIL_BUYUME = {2022: 1 / 1.06 ** 2, 2023: 1 / 1.06, 2024: 1.0, 2025: 1.06}

# --- Tatiller ve Black Friday ----------------------------------------------
BLACK_FRIDAY = (
    date(2022, 11, 25),
    date(2023, 11, 24),
    date(2024, 11, 29),
    date(2025, 11, 28),
)

TATILLER = {
    # 2022 (ısınma, yalnız ikinci yarı: ısınma 2022-07-04'te başlar; arife
    # yarım günü (07-08) dahil değil, yalnız tam günler)
    "2022-07-09", "2022-07-10", "2022-07-11", "2022-07-12",
    "2022-07-15", "2022-08-30", "2022-10-29", "2022-11-25",
    # 2023
    "2023-01-01", "2023-04-21", "2023-04-22", "2023-04-23", "2023-05-01",
    "2023-05-19", "2023-06-28", "2023-06-29", "2023-06-30", "2023-07-01",
    "2023-07-15", "2023-08-30", "2023-10-29", "2023-11-24",
    # 2024
    "2024-01-01", "2024-04-09", "2024-04-10", "2024-04-11", "2024-04-12",
    "2024-04-23", "2024-05-01", "2024-05-19", "2024-06-15", "2024-06-16",
    "2024-06-17", "2024-06-18", "2024-06-19", "2024-07-15", "2024-08-30",
    "2024-10-29", "2024-11-29",
    # 2025
    "2025-01-01", "2025-03-30", "2025-03-31", "2025-04-01", "2025-04-23",
    "2025-05-01", "2025-05-19", "2025-06-06", "2025-06-07", "2025-06-08",
    "2025-06-09", "2025-07-15", "2025-08-30", "2025-10-29", "2025-11-28",
}

# --- Sezon ve dalga takvimi -------------------------------------------------
# Moda zincirinin ticari takvimi ay değil sezon kodu ile yürür. Dalga
# tarihi = ilk dağıtımın mağazaya girdiği gün (pazartesi). v3'ün örüntüsü
# (AW: ağustos/eylül/ekim dalgaları, indirim 2 Ocak, çıkış son şubat
# pazartesi; SS: şubat/mart/nisan dalgaları, indirim ~1 Temmuz, çıkış son
# ağustos pazartesi) bir yıl geriye uzatılır.
#
# AW22 yalnız ısınmanın referans sezonu ve sezon_kodu hesaplaması içindir;
# ilk dalgası ısınma başlangıcından sonradır ve dışa aktarılan sezon
# tablosuna girmez (bkz. takvim.sezon_tablosu).
SEZONLAR = {
    "AW22": {
        "dalgalar": [date(2022, 8, 22), date(2022, 9, 26), date(2022, 10, 31)],
        "indirim": date(2023, 1, 2), "cikis": date(2023, 2, 27),
    },
    "SS23": {
        "dalgalar": [date(2023, 2, 13), date(2023, 3, 20), date(2023, 4, 24)],
        "indirim": date(2023, 7, 3), "cikis": date(2023, 8, 28),
    },
    "AW23": {
        "dalgalar": [date(2023, 8, 21), date(2023, 9, 25), date(2023, 10, 30)],
        "indirim": date(2024, 1, 2), "cikis": date(2024, 2, 26),
    },
    "SS24": {
        "dalgalar": [date(2024, 2, 12), date(2024, 3, 18), date(2024, 4, 22)],
        "indirim": date(2024, 7, 1), "cikis": date(2024, 8, 26),
    },
    "AW24": {
        "dalgalar": [date(2024, 8, 19), date(2024, 9, 23), date(2024, 10, 28)],
        "indirim": date(2025, 1, 2), "cikis": date(2025, 2, 24),
    },
    "SS25": {
        "dalgalar": [date(2025, 2, 10), date(2025, 3, 17), date(2025, 4, 21)],
        "indirim": date(2025, 6, 30), "cikis": date(2025, 8, 25),
    },
    "AW25": {
        "dalgalar": [date(2025, 8, 18), date(2025, 9, 22), date(2025, 10, 27)],
        "indirim": date(2026, 1, 2), "cikis": date(2026, 2, 23),
    },
}

# --- Mağazalar (Görev 4) -----------------------------------------------
# ~25 şehir, 7 coğrafi bölge: (şehir, bölge, enlem, boylam, iklim). Gerçek
# şehir merkezi koordinatları; turistik ilçeler (Bodrum, Fethiye, Alanya,
# Kemer) ayrı satır, iklim sıcak sahil.
SEHIRLER: list[tuple[str, str, float, float, str]] = [
    ("İstanbul", "Marmara", 41.0082, 28.9784, "ilıman"),
    ("Ankara", "İç Anadolu", 39.9334, 32.8597, "karasal"),
    ("İzmir", "Ege", 38.4237, 27.1428, "ilıman"),
    ("Bursa", "Marmara", 40.1826, 29.0665, "ilıman"),
    ("Antalya", "Akdeniz", 36.8969, 30.7133, "sicak_sahil"),
    ("Kocaeli", "Marmara", 40.8533, 29.8815, "ilıman"),
    ("Adana", "Akdeniz", 37.0000, 35.3213, "sicak_sahil"),
    ("Konya", "İç Anadolu", 37.8746, 32.4932, "karasal"),
    ("Mersin", "Akdeniz", 36.8121, 34.6415, "sicak_sahil"),
    ("Eskişehir", "İç Anadolu", 39.7767, 30.5206, "karasal"),
    ("Samsun", "Karadeniz", 41.2867, 36.3300, "ilıman"),
    ("Trabzon", "Karadeniz", 41.0027, 39.7168, "ilıman"),
    ("Kayseri", "İç Anadolu", 38.7312, 35.4787, "karasal"),
    ("Gaziantep", "Güneydoğu Anadolu", 37.0662, 37.3833, "karasal"),
    ("Diyarbakır", "Güneydoğu Anadolu", 37.9144, 40.2306, "karasal"),
    ("Erzurum", "Doğu Anadolu", 39.9000, 41.2700, "soguk"),
    ("Malatya", "Doğu Anadolu", 38.3552, 38.3095, "karasal"),
    ("Van", "Doğu Anadolu", 38.4891, 43.4089, "soguk"),
    ("Sivas", "İç Anadolu", 39.7477, 37.0179, "soguk"),
    ("Kars", "Doğu Anadolu", 40.6013, 43.0975, "soguk"),
    ("Denizli", "Ege", 37.7765, 29.0864, "ilıman"),
    ("Bodrum", "Ege", 37.0344, 27.4305, "sicak_sahil"),
    ("Fethiye", "Ege", 36.6217, 29.1164, "sicak_sahil"),
    ("Alanya", "Akdeniz", 36.5438, 31.9998, "sicak_sahil"),
    ("Kemer", "Akdeniz", 36.6019, 30.5608, "sicak_sahil"),
]

# Turistik ilçeler: konum ekseninde turistik bayrağı taşır (yaz sıçraması).
TURISTIK_SEHIRLER = {"Bodrum", "Fethiye", "Alanya", "Kemer"}

# İstanbul 18, Ankara 7, İzmir 6, ...; toplam 84. Soğuk iklim (Erzurum,
# Van, Sivas, Kars: 8 mağaza) ve sıcak sahil/turistik (Antalya, Adana,
# Mersin, Bodrum, Fethiye, Alanya, Kemer: 15 mağaza) havuzları her segmentte
# ≥ 6 fiziksel mağaza kuralını tohumdan bağımsız, tasarımla sağlar.
SEHIR_MAGAZA_SAYISI: dict[str, int] = {
    "İstanbul": 18, "Ankara": 7, "İzmir": 6, "Bursa": 5, "Antalya": 4,
    "Kocaeli": 3, "Adana": 3, "Konya": 4, "Mersin": 3, "Eskişehir": 2,
    "Samsun": 2, "Trabzon": 2, "Kayseri": 3, "Gaziantep": 3,
    "Diyarbakır": 2, "Erzurum": 3, "Malatya": 2, "Van": 2, "Sivas": 2,
    "Kars": 1, "Denizli": 2, "Bodrum": 2, "Fethiye": 1, "Alanya": 1,
    "Kemer": 1,
}
assert sum(SEHIR_MAGAZA_SAYISI.values()) == 84

# Outlet mağazaların şehir başına sayısı (toplam 10, yalnız büyük metro ve
# karasal iç şehirlerde); soğuk ve sıcak sahil/turistik havuzları hiç
# outlet almaz, böylece bu iki segmentin ≥6 fiziksel mağaza sayımı outlet
# düşmesinden etkilenmez.
OUTLET_SEHIRLERI: dict[str, int] = {
    "İstanbul": 3, "Ankara": 2, "İzmir": 1, "Bursa": 1, "Konya": 1,
    "Kayseri": 1, "Gaziantep": 1,
}
assert sum(OUTLET_SEHIRLERI.values()) == 10

METROPOL_SEHIRLERI = {"İstanbul", "Ankara", "İzmir"}

SEGMENTLER = [
    "metropol_premium", "metropol_genc", "anadolu_aile",
    "sicak_sahil", "soguk_iklim", "outlet",
]

# Merkez depo (Gebze); ONL'nin koordinatları budur.
GEBZE_DEPO = (40.80, 29.43)

# Tip başına raf yoğunluğu: kapasite = m² × yoğunluk × (1 − 0,08·(kat−1)).
TIP_YOGUNLUK = {"AVM": 9.0, "Cadde": 8.0, "Outlet": 12.5}

# --- Ürün (Görev 5) ---------------------------------------------------------
# marka (Lumoda) > cinsiyet > üst kategori > alt kategori > line > model >
# option > SKU. v2'nin ağacı korunur, Elbise & Tulum ve Aksesuar eklenir
# (spec §3.1 tablosu birebir); Çocuk yok.
MARKA = "Lumoda"

KATEGORILER: dict[str, list[str]] = {
    "Üst Giyim": ["Tişört", "Gömlek", "Bluz", "Kazak", "Sweatshirt"],
    "Alt Giyim": ["Pantolon", "Jean", "Etek", "Şort"],
    "Elbise & Tulum": ["Elbise", "Tulum"],
    "Dış Giyim": ["Mont", "Ceket", "Trençkot"],
    "Aksesuar": ["Çanta", "Şal", "Kemer"],
}

# Bluz, Elbise, Tulum, Etek yalnız Kadın.
YALNIZ_KADIN = {"Bluz", "Elbise", "Tulum", "Etek"}
AKSESUAR = {"Çanta", "Şal", "Kemer"}

CINSIYETLER = ["Kadın", "Erkek", "Unisex"]
CINSIYET_PAYLARI = [0.52, 0.38, 0.10]

# Beden setleri v2 mantığında (içe aktarılmaz, burada yeniden tanımlanır),
# beş kademe; Elbise & Tulum kadın harf setini kullanır, Aksesuar tek
# beden (STD).
BEDEN_SETLERI: dict[tuple[str, str], tuple[str, list[str]]] = {
    ("Kadın", "Üst Giyim"): ("Kadın Harf", ["XS", "S", "M", "L", "XL"]),
    ("Kadın", "Dış Giyim"): ("Kadın Harf", ["XS", "S", "M", "L", "XL"]),
    ("Kadın", "Elbise & Tulum"): ("Kadın Harf", ["XS", "S", "M", "L", "XL"]),
    ("Kadın", "Alt Giyim"): ("Kadın Numara", ["34", "36", "38", "40", "42"]),
    ("Erkek", "Üst Giyim"): ("Erkek Harf", ["S", "M", "L", "XL", "XXL"]),
    ("Erkek", "Dış Giyim"): ("Erkek Harf", ["S", "M", "L", "XL", "XXL"]),
    ("Erkek", "Alt Giyim"): ("Erkek Numara", ["30", "32", "34", "36", "38"]),
    ("Unisex", "Üst Giyim"): ("Unisex Harf", ["S", "M", "L", "XL", "XXL"]),
    ("Unisex", "Dış Giyim"): ("Unisex Harf", ["S", "M", "L", "XL", "XXL"]),
    ("Unisex", "Alt Giyim"): ("Unisex Numara", ["30", "32", "34", "36", "38"]),
}
# Aksesuar cinsiyetten bağımsız tek beden (lookup cinsiyeti yok sayar,
# bkz. urun._beden_seti).
AKSESUAR_BEDEN_SETI = ("Standart", ["STD"])

BEDEN_KADEME_SAYISI = 5

# Beden başına standart paket (Lumoda'da her beden setine tek paket);
# Aksesuar koli adediyle (STD × 6).
PAKET_ADETLERI = [1, 2, 2, 1, 1]
AKSESUAR_KOLI_ADEDI = 6

# --- Öznitelikler ------------------------------------------------------
OZNITELIKLER: dict[str, list[str]] = {
    "kumas": ["pamuk", "keten", "denim", "yün", "viskon", "karışım"],
    "kalip": ["slim", "regular", "relaxed", "oversize"],
    "desen": ["düz", "çizgili", "kareli", "baskılı", "çiçekli"],
    "fiyat_segmenti": ["giris", "orta", "premium"],
}
FIYAT_SEGMENTI_PAYLARI = [0.35, 0.45, 0.20]

# Alt kategori → (detay alanı, izinli değerler). Aksesuar hiç girmez
# (detay None kalır) — tek alanlık `detay` sütunu böylece kategoriye göre
# ya boy ya yaka taşır, `detay_alani` hangisi olduğunu söyler.
DETAY: dict[str, tuple[str, list[str]]] = {
    "Tişört": ("yaka", ["bisiklet yaka", "V yaka", "polo yaka", "balıkçı yaka", "hakim yaka"]),
    "Gömlek": ("yaka", ["klasik yaka", "hakim yaka", "polo yaka", "yuvarlak yaka"]),
    "Bluz": ("yaka", ["V yaka", "yuvarlak yaka", "hakim yaka", "yakasız"]),
    "Kazak": ("yaka", ["balıkçı yaka", "bisiklet yaka", "V yaka", "hırka yaka"]),
    "Sweatshirt": ("yaka", ["bisiklet yaka", "kapüşonlu", "polo yaka"]),
    "Pantolon": ("boy", ["crop", "normal", "uzun"]),
    "Jean": ("boy", ["crop", "normal", "uzun"]),
    "Etek": ("boy", ["crop", "normal", "uzun"]),
    "Şort": ("boy", ["crop", "normal", "uzun"]),
    "Elbise": ("boy", ["crop", "normal", "uzun"]),
    "Tulum": ("boy", ["crop", "normal", "uzun"]),
    "Mont": ("boy", ["crop", "normal", "uzun"]),
    "Ceket": ("boy", ["crop", "normal", "uzun"]),
    "Trençkot": ("boy", ["crop", "normal", "uzun"]),
}

# Alt kategori → izinli kumaşlar (denim yalnız Jean/Etek/Şort'ta, yün
# yalnız kışlık üst giyim/dış giyimde vb.).
GECERLI_KUMAS: dict[str, list[str]] = {
    "Tişört": ["pamuk", "viskon", "karışım"],
    "Gömlek": ["pamuk", "keten", "viskon", "karışım"],
    "Bluz": ["pamuk", "keten", "viskon", "karışım"],
    "Kazak": ["yün", "karışım", "pamuk"],
    "Sweatshirt": ["pamuk", "karışım"],
    "Pantolon": ["pamuk", "keten", "viskon", "karışım"],
    "Jean": ["denim"],
    "Etek": ["pamuk", "keten", "denim", "viskon", "karışım"],
    "Şort": ["pamuk", "keten", "denim", "karışım"],
    "Elbise": ["pamuk", "keten", "viskon", "karışım"],
    "Tulum": ["pamuk", "keten", "viskon", "karışım"],
    "Mont": ["karışım", "pamuk"],
    "Ceket": ["denim", "karışım", "yün"],
    "Trençkot": ["pamuk", "karışım"],
    "Çanta": ["karışım", "viskon"],
    "Şal": ["yün", "viskon", "keten"],
    "Kemer": ["karışım", "viskon"],
}

# Alt kategori başına kesim/model adı havuzu (v2/v3'ün deseninin devamı,
# yeni alt kategoriler için genişletilmiş).
KESIMLER: dict[str, list[str]] = {
    "Tişört": ["Bisiklet Yaka", "V Yaka", "Oversize", "Slim Fit", "Polo Yaka"],
    "Gömlek": ["Slim Fit", "Regular Fit", "Oduncu", "Keten", "Oxford"],
    "Bluz": ["Fırfırlı", "Saten", "Yakasız", "Bağlamalı", "Basic"],
    "Kazak": ["Balıkçı Yaka", "Bisiklet Yaka", "Hırka", "Örgü Desenli"],
    "Sweatshirt": ["Kapüşonlu", "Bisiklet Yaka", "Oversize", "Fermuarlı"],
    "Pantolon": ["Chino", "Kumaş", "Jogger", "Yüksek Bel", "Wide Leg"],
    "Jean": ["Slim Fit", "Mom Fit", "Straight", "Skinny", "Baggy"],
    "Etek": ["Midi", "Mini", "Pileli", "Kalem"],
    "Şort": ["Bermuda", "Klasik", "Paperbag"],
    "Elbise": ["Midi", "Maxi", "Gömlek", "Askılı", "Bodycon"],
    "Tulum": ["Salopet", "Geniş Paça", "Dar Paça"],
    "Mont": ["Şişme", "Parka", "Puffer", "Bomber"],
    "Ceket": ["Blazer", "Deri", "Kot", "Süet"],
    "Trençkot": ["Klasik", "Uzun", "Kemerli"],
    "Çanta": ["Omuz Çantası", "El Çantası", "Sırt Çantası", "Crossbody"],
    "Şal": ["Yün Şal", "İpek Şal", "Fularlı Şal", "Kareli Şal"],
    "Kemer": ["İnce Kemer", "Geniş Kemer", "Örgü Kemer"],
}

# Renk paleti (ad → üç harfli kod). Devamlı ürünler çekirdek altkümede
# döner: temel ürün sezon rengi taşımaz.
RENKLER: dict[str, str] = {
    "Siyah": "SYH", "Beyaz": "BYZ", "Bej": "BEJ", "Lacivert": "LCV",
    "Haki": "HAK", "Bordo": "BRD", "Ekru": "EKR", "İndigo": "IND",
    "Gri Melanj": "GRM", "Kiremit": "KRM", "Pudra": "PDR", "Yeşil": "YSL",
}
DEVAMLI_RENK_HAVUZU = ["Siyah", "Beyaz", "Lacivert", "Gri Melanj", "Bej", "İndigo"]

# --- Hacim (Görev 5) ----------------------------------------------------
# Sezon başına Collection ~210 + Outlet ~40 option; devamlı Basic 80 + NOS
# 40. `option_carpani` (bkz. Olcek) her ikisini de ölçekler.
SEZON_COLLECTION_OPTION = 210
SEZON_OUTLET_OPTION = 40
DEVAMLI_BASIC_OPTION = 80
DEVAMLI_NOS_OPTION = 40

RENK_SAYISI_ARALIGI = {"Collection": (2, 4), "Outlet": (2, 4), "Basic": (3, 3), "NOS": (2, 2)}

DEVAMLI = "DEVAMLI"

# Alt kategori ağırlıkları, sezon/line tipine göre (v3 tablosunun
# genişletilmiş hâli: Bluz, Elbise, Tulum, Çanta, Şal, Kemer eklendi).
# AW'de Şort hiç yok, SS'de Mont hiç yok (Collection'da 0 ağırlık ⇒ hiç
# üretilmez, bkz. urun.test_mont_yaz_yok/test_sort_kis_yok).
ALT_KATEGORI_AGIRLIK: dict[str, dict[str, float]] = {
    "AW": {
        "Tişört": 0.5, "Gömlek": 1.0, "Bluz": 0.8, "Kazak": 1.5, "Sweatshirt": 1.2,
        "Pantolon": 1.0, "Jean": 1.2, "Etek": 0.4, "Şort": 0.0,
        "Elbise": 0.5, "Tulum": 0.2,
        "Mont": 1.4, "Ceket": 1.0, "Trençkot": 0.6,
        "Çanta": 0.5, "Şal": 1.0, "Kemer": 0.3,
    },
    "SS": {
        "Tişört": 1.6, "Gömlek": 1.3, "Bluz": 1.0, "Kazak": 0.2, "Sweatshirt": 0.5,
        "Pantolon": 1.0, "Jean": 1.1, "Etek": 1.0, "Şort": 1.2,
        "Elbise": 1.3, "Tulum": 0.8,
        "Mont": 0.0, "Ceket": 0.6, "Trençkot": 0.4,
        "Çanta": 0.6, "Şal": 0.1, "Kemer": 0.4,
    },
    "Basic": {
        "Tişört": 3.0, "Gömlek": 1.0, "Bluz": 0.8, "Kazak": 0.6, "Sweatshirt": 1.5,
        "Pantolon": 1.5, "Jean": 2.0, "Etek": 0.2, "Şort": 0.4,
        "Elbise": 0.3, "Tulum": 0.0,
        "Mont": 0.3, "Ceket": 0.0, "Trençkot": 0.0,
        "Çanta": 0.4, "Şal": 0.2, "Kemer": 0.3,
    },
    "NOS": {
        "Tişört": 3.0, "Gömlek": 1.0, "Bluz": 0.0, "Kazak": 0.0, "Sweatshirt": 1.0,
        "Pantolon": 1.0, "Jean": 2.0, "Etek": 0.0, "Şort": 0.0,
        "Elbise": 0.0, "Tulum": 0.0,
        "Mont": 0.0, "Ceket": 0.0, "Trençkot": 0.0,
        "Çanta": 0.3, "Şal": 0.0, "Kemer": 0.2,
    },
}

# --- Fiyat (Görev 5) -----------------------------------------------------
# Alt kategori başına taban alış fiyatı (TL); tedarikçi çarpanı Görev 6'da
# uygulanır (burada yok).
TABAN_FIYAT: dict[str, float] = {
    "Tişört": 120, "Gömlek": 260, "Bluz": 240, "Kazak": 340, "Sweatshirt": 300,
    "Pantolon": 380, "Jean": 420, "Etek": 290, "Şort": 190,
    "Elbise": 420, "Tulum": 460,
    "Mont": 900, "Ceket": 720, "Trençkot": 850,
    "Çanta": 380, "Şal": 150, "Kemer": 180,
}

KUMAS_CARPANI = {
    "yün": 1.5, "keten": 1.3, "denim": 1.2, "viskon": 1.0, "pamuk": 0.9, "karışım": 0.85,
}

# Alış fiyatı segment çarpanı (kumaş sonrası, tedarikçi öncesi).
SEGMENT_ALIS_CARPANI = {"giris": 0.75, "orta": 1.0, "premium": 1.45}
ALIS_FIYATI_SIGMA = 0.08  # lognormal(0, sigma) gürültü

# Liste fiyatı (Lumoda kuralı): alış × segment çarpanı, ",99"a yuvarlanır.
LISTE_FIYATI_CARPANI = {"giris": 2.2, "orta": 2.6, "premium": 3.1}

# --- Tedarik (Görev 6) ---------------------------------------------------
# 18 tedarikçi: (ad, ülke, menşe, uzmanlık). Sıra tedarikci_id'yi belirler
# (T01…T18); v3'ün yerli adlarının devamı + kurgusal Mısır/Uzak Doğu adları.
# Uzmanlık: her alan ≥ 2 tedarikçi (örgü 4, denim 3, dış giyim 4, dokuma 5,
# aksesuar 2); aksesuarda en az bir yerli (Malatya Konfeksiyon).
TEDARIKCI_TANIMLARI: list[tuple[str, str, str, str]] = [
    ("Ege Tekstil", "Türkiye", "Yerli", "dokuma"),
    ("Marmara Konfeksiyon", "Türkiye", "Yerli", "örgü"),
    ("Denizli Örme", "Türkiye", "Yerli", "örgü"),
    ("Bursa Dokuma", "Türkiye", "Yerli", "dokuma"),
    ("Çorlu Giyim", "Türkiye", "Yerli", "dış giyim"),
    ("Kayseri İplik", "Türkiye", "Yerli", "örgü"),
    ("Gaziantep Tekstil", "Türkiye", "Yerli", "denim"),
    ("Adana Pamuklu", "Türkiye", "Yerli", "dokuma"),
    ("Malatya Konfeksiyon", "Türkiye", "Yerli", "aksesuar"),
    ("Kahramanmaraş Örme", "Türkiye", "Yerli", "dış giyim"),
    ("Kahire Nil Tekstil", "Mısır", "Yakın", "dokuma"),
    ("İskenderiye Delta Giyim", "Mısır", "Yakın", "denim"),
    ("Ningbo Hengtai Garment", "Çin", "Uzak Doğu", "dış giyim"),
    ("Guangzhou Feng Apparel", "Çin", "Uzak Doğu", "denim"),
    ("Dhaka Meghna Apparels", "Bangladeş", "Uzak Doğu", "örgü"),
    ("Chittagong Padma Garments", "Bangladeş", "Uzak Doğu", "dokuma"),
    ("Saigon Lotus Garment", "Vietnam", "Uzak Doğu", "dış giyim"),
    ("Tiruppur Ganga Textiles", "Hindistan", "Uzak Doğu", "aksesuar"),
]
assert len(TEDARIKCI_TANIMLARI) == 18

# Menşe tablosu (v3'ün genişlemesi): ilk sipariş / RPT süresi (hafta), MOQ,
# gerçekleşen teslimin planlanana göre sapma sınırları (gün).
MENSE_V4: dict[str, dict] = {
    "Yerli": {"ilk": (10, 12), "rpt": (4, 6), "moq": 300, "sapma_min": -3, "sapma_maks": 3},
    "Yakın": {"ilk": (14, 16), "rpt": (7, 9), "moq": 400, "sapma_min": 0, "sapma_maks": 10},
    "Uzak Doğu": {"ilk": (24, 30), "rpt": (12, 16), "moq": 600, "sapma_min": 0, "sapma_maks": 21},
}

# Gizli gecikme şekli (fix round 1 - controller kararı): brief'in beta
# biçimi korunur (v3'ün UZAK_DOGU_SAPMA_BETA'sıyla aynı şekil), tedarikçi
# düzeyinde farklılaşma yalnız bir ölçek/kayma parametresiyle eklenir —
# `teslim_sapmasi` mense'e göre:
#   Uzak Doğu: round(olcek_t × 21 × Beta(1.3, 3.5)), olcek_t ~ U(0.6, 1.4)
#   Yakın:     round(olcek_t × 10 × Beta(1.3, 3.5)), olcek_t ~ U(0.6, 1.4)
#   Yerli:     round(bias_t + tam sayı gürültü ±2), bias_t ~ U(-1, 1)
# sonra menşenin sapma_min/maks'ına (MENSE_V4) kırpılır. `olcek_t`/`bias_t`
# gizli_tedarikci'de `gecikme_parametre_t` sütununda saklanır (anlamı
# mense'e göre değişir); `gecikme_beklenen_gun` bunun analitik beklentisidir
# (Beta(a,b) ortalaması a/(a+b)).
SAPMA_BETA = (1.3, 3.5)
OLCEK_T_ARALIGI = (0.6, 1.4)
YERLI_BIAS_ARALIGI = (-1.0, 1.0)
YERLI_GURULTU_MAKS_GUN = 2

# Hatalı oran: tedarikçi başına beta(2,5) ile [0,5%–6%] aralığına
# ölçeklenir (sağa çarpık: çoğu tedarikçi iyi, birkaçı kötü).
HATALI_ORANI_ARALIGI = (0.005, 0.06)
HATALI_ORANI_BETA = (2.0, 5.0)

# Maliyet çarpanı: genel aralık 0,85–1,15; Uzak Doğu alt aralığı ortalaması
# tam 0,90 olacak şekilde daraltılır (spec: "Uzak Doğu ortalaması 0,9").
MALIYET_CARPANI_ARALIGI: dict[str, tuple[float, float]] = {
    "Yerli": (0.85, 1.15), "Yakın": (0.85, 1.15), "Uzak Doğu": (0.85, 0.95),
}

# Kapasite (sezon başına adet); tasarım kararı — spec kesin sayı vermez,
# yalnız "sezon başına adet" der. Uzak Doğu fabrikaları en büyük, yerli
# en küçük kapasiteli. KALİBRASYON DÜĞMESİ: fix round 1'de toplam ilk alım
# hacmiyle (Collection+Outlet, 80 mağaza+online, sezon başına ~1,0-1,3M
# adet) tutarlı olacak şekilde büyütüldü; kesin değerler Görev 17'de
# (uçtan uca hacim ayarı) yeniden ayarlanabilir.
KAPASITE_SEZON_ARALIGI: dict[str, tuple[int, int]] = {
    "Yerli": (40_000, 120_000), "Yakın": (60_000, 150_000), "Uzak Doğu": (120_000, 300_000),
}

# Uzmanlık alanı → alt kategoriler (herhangi bir tedarikçi herhangi bir alt
# kategoriyi üretebilir; bonus yalnız kendi alanında).
UZMANLIK_ALANLARI: dict[str, list[str]] = {
    "örgü": ["Tişört", "Sweatshirt", "Kazak"],
    "denim": ["Jean"],
    "dış giyim": ["Mont", "Ceket", "Trençkot"],
    "dokuma": ["Gömlek", "Bluz", "Pantolon", "Etek", "Şort", "Elbise", "Tulum"],
    "aksesuar": ["Çanta", "Şal", "Kemer"],
}
ALT_KATEGORI_ALAN: dict[str, str] = {
    alt: alan for alan, altlar in UZMANLIK_ALANLARI.items() for alt in altlar
}

# Uzmanlıkta maliyet ×0,93, hatalı oran ×0,7 (spec §4.1); her iki taraf da
# doğrudan bu sabitlerden uygulanır (`alis_fiyati_uygula`, `hatali_adet`'in
# `uyum` parametresi) — gizli_tedarikci'de ayrı bir "bonus" sütunu yok
# (fix round 1: inert `uzmanlik_bonusu` sütunu kaldırıldı, bkz. task-6-report).
UZMANLIK_MALIYET_CARPANI = 0.93
UZMANLIK_HATALI_CARPANI = 0.7

# Lumoda alışkanlığı: dış giyim ağırlıklı dört alt kategoride (mont, jean,
# ceket, trençkot) alışılmış birincil/ikincil tedarikçi %60 olasılıkla
# yalnız Uzak Doğu havuzundan seçilir (v3'ün UZAK_DOGU_OLASILIGI'nin
# alışkanlık düzeyindeki karşılığı).
LUMODA_UZAK_DOGU_ALT_KATEGORILERI = {"Mont", "Jean", "Ceket", "Trençkot"}
LUMODA_UZAK_DOGU_HAVUZ_OLASILIGI = 0.6
# Alışkanlık seçiminde kamuya açık uzmanlık alanı eşleşen tedarikçiye
# ağırlık çarpanı (gizli performansa değil, yalnız bu kamu bilgisine bakar).
LUMODA_UZMANLIK_AGIRLIGI = 3.0

# Kalite kontrol numunesi: min(adet, NUMUNE_TABAN + adet // NUMUNE_BOLEN).
NUMUNE_TABAN = 32
NUMUNE_BOLEN = 50

# --- Talep (Görev 8) ------------------------------------------------------
# λ = liste fiyatında beklenen günlük talep (hücre = mağaza × SKU). Fiyat
# etkisi burada yok (motor uygular). "KALİBRASYON" yorumlu düğmeler
# Görev 17'de (uçtan uca hacim/pay ayarı) yeniden ayarlanabilir; buradaki
# değerler ilk tahmindir.

# Mağaza tabanı = TABAN_OLCEK × (kapasite / KAPASITE_REFERANS)^KAPASITE_USSU
#                 × TIP_TALEP_CARPANI[tip] × exp(MAGAZA_GURULTU_SIGMA × yerel_gurultu)
TABAN_OLCEK = 0.6               # KALİBRASYON: toplam hacim
KAPASITE_REFERANS = 5000.0      # ~550 m² tek katlı AVM
KAPASITE_USSU = 1.0             # KALİBRASYON: brief "kapasiteyle orantılı"
TIP_TALEP_CARPANI = {"AVM": 1.0, "Cadde": 0.85, "Outlet": 1.6}  # KALİBRASYON
MAGAZA_GURULTU_SIGMA = 0.10     # gizli_magaza.yerel_gurultu (N(0,1)) ölçeği

# Üst kategori ve line hacim çarpanları (v3'ün TABAN_TALEP ve
# LINE_HACIM × SEZONLUK_TEPE çarpanlarının devamı).
UST_KATEGORI_TABAN = {                                      # KALİBRASYON
    "Üst Giyim": 1.0, "Alt Giyim": 0.75, "Elbise & Tulum": 0.7,
    "Dış Giyim": 0.45, "Aksesuar": 0.6,
}
LINE_TALEP_CARPANI = {"Collection": 1.7, "Outlet": 0.8, "Basic": 1.15, "NOS": 1.3}  # KALİBRASYON

# Genç eğilim: kalıbın "genç" skoru × (genc_egilim − 0,5) × katsayı, log uzayında.
GENC_KALIP_SKORU = {"oversize": 1.0, "relaxed": 0.5, "regular": -0.5, "slim": -0.5}
GENC_ETKI_KATSAYISI = 0.6

# Fiyat segmenti ↔ gelir uyumu (talep çarpanı).
FIYAT_GELIR_TALEP = {
    "giris": {"dusuk": 1.25, "orta": 1.0, "yuksek": 0.8},
    "orta": {"dusuk": 1.0, "orta": 1.1, "yuksek": 1.0},
    "premium": {"dusuk": 0.6, "orta": 1.0, "yuksek": 1.35},
}

# Zincir beden eğrisi (beden sırası 1..5; v2/v3 değerleri) ve kaydırma:
# mağazanın `beden_kayma`'sı (−1/0/+1) × BEDEN_KAYMA_ADIM kadar sıra
# kayar (kenarlar BEDEN_KENAR ile uzatılır, doğrusal ara değer).
BEDEN_PAYLARI_ZINCIR = [0.10, 0.22, 0.32, 0.24, 0.12]
BEDEN_KENAR = 0.04
BEDEN_KAYMA_ADIM = 0.5

KAT_ERKEK_CARPANI = 0.9         # çok katlı mağazada erkek ürünleri üst katta
YEREL_GURULTU_SIGMA = 0.15      # mağaza × alt kategori lognormal

# Online payı (ulusal talebin kategoriye göre payı); Basic/NOS online'da güçlü.
ONLINE_PAY = {
    "Üst Giyim": 0.18, "Alt Giyim": 0.17, "Elbise & Tulum": 0.20,
    "Dış Giyim": 0.12, "Aksesuar": 0.21,
}
ONLINE_BASIC_CARPANI = 1.25

# Ürün sürprizi (lognormal medyan 1); v3'ten küçük (spec §3.3).
SURPRIZ_SIGMA = {"Collection": 0.40, "Outlet": 0.30, "Basic": 0.15, "NOS": 0.08}

# Yaşam eğrisi (v3 formülü): (h+1)^a · exp(−h/τ), tepe 1'e ölçekli.
YASAM_A = 1.0
YASAM_TAU_HAFTA = 4.0
YASAM_TAU_OYNAMA = 0.20         # alt kategori başına ±%20

# Sürüklenme: option düzeyinde haftalık log AR(1).
SURUKLENME_RHO = 0.7
SURUKLENME_SIGMA = 0.10

# Öznitelik etkisi: başlangıç katsayısı N(0, OZNITELIK_TABAN_SIGMA) (segment
# × "alan:değer"), sezondan sezona TREND + N(0, OZNITELIK_YURUYUS_SIGMA).
OZNITELIK_TABAN_SIGMA = 0.10    # KALİBRASYON: öğrenilebilirlik (spec §8.3)
OZNITELIK_YURUYUS_SIGMA = 0.03
# Önceden yazılmış trend hikâyesi (log katsayı):
#   "birikimli": her sezon eklenir; "birikimli_SS": yalnız SS sezonlarında
#   eklenir; "duzey_SS_AW": SS'de +x, AW'de −x (birikmez);
#   "sabit_segment": yalnız verilen segmentte sabit +x.
TREND = {
    "kalip:oversize": ("birikimli", 0.12),
    "kalip:slim": ("birikimli", -0.10),
    "kumas:keten": ("birikimli_SS", 0.08),
    "desen:çiçekli": ("duzey_SS_AW", 0.15),
    "fiyat_segmenti:premium": ("sabit_segment", 0.30, "metropol_premium"),
}

# Mevsim: alt kategori → (tepe ayı, genlik); 1.0 = 1 Ocak. v3 MEVSIM +
# yeni kategoriler (Bluz, Elbise, Tulum, Çanta, Şal, Kemer).
MEVSIM = {
    "Mont": (12.5, 0.95), "Ceket": (11.0, 0.55), "Trençkot": (10.5, 0.35),
    "Kazak": (12.5, 0.70), "Sweatshirt": (12.0, 0.40),
    "Tişört": (6.5, 0.50), "Gömlek": (5.5, 0.20), "Bluz": (6.0, 0.30),
    "Pantolon": (10.0, 0.10), "Jean": (10.0, 0.15),
    "Etek": (6.0, 0.35), "Şort": (6.5, 1.00),
    "Elbise": (6.5, 0.55), "Tulum": (6.5, 0.50),
    "Çanta": (8.0, 0.10), "Şal": (12.0, 0.80), "Kemer": (9.0, 0.05),
}
# Yaz ürünü: tepe ayı [3, 9]; diğerleri kış ürünü.
YAZ_TEPE_ARALIGI = (3.0, 9.0)
# İklim kaymaları (ay / çarpan). "genişlik": tepe çevresinde yaz sezonunun
# her düzeyde bu kadar ay uzaması (düz tepe), bkz. talep._mevsim_egrisi.
IKLIM_KAYMA = {
    "ılıman": {},
    "sicak_sahil": {"yaz_tepe": -0.7, "yaz_genislik": 0.5, "kis_genlik": 0.6},
    "karasal": {"yaz_genlik": 1.15, "kis_genlik": 1.15},
    "soguk": {"kis_tepe": 0.5, "kis_genlik": 1.3, "yaz_genlik": 0.7},
}

# Line başına mevsim genliği üssü (mevsim^üs, yıllık ortalama 1'e yeniden
# normalize): Basic/NOS daha düz (stok bulunurluğu bandı için sigorta).
MEVSIM_LINE_USSU = {"Collection": 1.0, "Outlet": 1.0, "Basic": 0.6, "NOS": 0.4}  # KALİBRASYON

# Outlet akışı eğrisi (fix round 1): Collection option'ın çıkıştan sonraki
# 84 günlük outlet penceresinde yaşam çarpanı
# OUTLET_AKISI_TALEP × (1 − OUTLET_AKISI_DUSUS · t/84) (option tepesi = 1).
# Görev 13 fix: liste fiyatında değil, outlet hattının indirimli fiyatında
# (çıkışta %50, 28 günde bir kademe, en çok %70; outlet esnekliğiyle ~×10)
# kalibre, TAM ölçekte (yayımlanan veri): pencerelerdeki fiyat etkili outlet
# akışı talebi ≈ outlet_akisi ile gelen adet (0,069 → oran 0,99;
# test_talep.test_outlet_akisi_tam, yavas, 0,8–1,2; KÜÇÜK yalnız 0,5–3,0).
OUTLET_AKISI_TALEP = 0.069      # KALİBRASYON
OUTLET_AKISI_DUSUS = 0.6

# Mağaza-gün çarpanları.
HAFTA_GUNU_CARPANI = [1.0, 1.0, 1.0, 1.0, 1.0, 1.55, 1.55]  # v3 (Pzt..Paz)
TATIL_CARPANI = 0.6             # resmî tatil (fiziksel trafik)
BLACK_FRIDAY_CARPANI = 1.8      # trafik (fiziksel ve online)
TURISTIK_YAZ_AYLARI = {6, 7, 8, 9}
TURISTIK_YAZ_CARPANI = 1.6
TURISTIK_KIS_CARPANI = 0.85
OLGUNLASMA_DERINLIK = 0.5       # 1 − 0,5·exp(−hafta/4)
OLGUNLASMA_HAFTA = 4.0

# Olay kaymaları: kapanan mağazanın talebinin payı → en yakın 2 fiziksel
# açık mağaza (her biri) ve ONL.
TADILAT_KAYMA = {"yakin": 0.15, "onl": 0.10}      # toplam %40
KAPANIS_KAYMA = {"yakin": 0.1125, "onl": 0.075}   # toplam %30, aynı dağılım
KAYMA_YAKIN_SAYISI = 2

# --- Kampanya ve esneklik (Görev 9) ----------------------------------------
# Kampanya takvimi talepten bağımsız (dışsal) çekilir: ayrı bir alt rng
# kullanır (bkz. kampanya.kampanyalari_uret), böylece markdown (içsel,
# Lumoda kuralı) ile karışmayan temiz fiyat varyasyonu sağlar.
KAMPANYA_BF_ORANI = 0.30
KAMPANYA_BF_GUN = 4  # Cuma..Pazartesi dahil

KAMPANYA_KATEGORI_YIL = 10          # tam yılda kategori kampanyası sayısı
KAMPANYA_KATEGORI_GUN_ARALIGI = (7, 14)
KAMPANYA_KATEGORI_ORANLARI = [0.20, 0.30, 0.40]
KAMPANYA_KATEGORI_BOLGE_ARALIGI = (2, 4)

KAMPANYA_IKINCI_URUN_YIL = 4        # tam yılda "ikinci ürün" kampanyası sayısı
KAMPANYA_IKINCI_URUN_GUN = 10
# "İkinci ürüne %50" mekaniği kayıt tutulmaz; okuyucu tipe (ikinci_urun)
# bakıp etkin indirim oranını burada saklanan değerden okur.
KAMPANYA_IKINCI_URUN_ORAN_ETKIN = 0.25

# Gizli esneklik ε = ESNEKLIK_UST[ust_kategori] × ESNEKLIK_GELIR[gelir],
# outlet segmentinde ayrıca × ESNEKLIK_OUTLET_CARPANI (fiyata daha duyarlı).
ESNEKLIK_UST = {
    "Üst Giyim": 1.8, "Alt Giyim": 1.6, "Elbise & Tulum": 2.0,
    "Dış Giyim": 1.4, "Aksesuar": 2.2,
}
ESNEKLIK_GELIR = {"dusuk": 1.25, "orta": 1.0, "yuksek": 0.75}
ESNEKLIK_OUTLET_CARPANI = 1.2

# İşlem indirimi (v3'teki gibi): tam fiyatlı (markdown/kampanya yok) satışta
# rastgele uygulanan indirim.
ISLEM_INDIRIM_OLASILIGI = 0.08
ISLEM_INDIRIM_ORANI = 0.30

# --- Plan (Görev 10) ---------------------------------------------------------
# Lumoda'nın planı bilerek naiftir (spec §4.3): sürprizi, sürüklenmeyi,
# iklim kaymasını, mağaza × alt kategori gürültüsünü, olay kaymalarını ve
# bu sezonun öznitelik etkisini bilmez (bir önceki aynı tip sezonunkini
# kullanır), gerçek esnekliği bilmez (sabit PLAN_ESNEKLIK varsayar).
HEDEF_TAM_FIYAT_STR = 0.80      # ilk alım = sezon planı (lansman → indirim) ÷ hedef STR
YUVARLAMA_ADET = 10             # sipariş adedi 10'un katı (v3)
PLANLANAN_TESLIM_ONCE_GUN = 7   # ilk siparişin planlanan teslimi = lansman − 7 gün

# Planın indirim inancı: indirimin ilk 28 gününde %30, sonra çıkışa kadar
# %50; talep etkisi (1 − oran)^(−PLAN_ESNEKLIK).
PLAN_ESNEKLIK = 1.7
PLAN_INDIRIM_ILK_GUN = 28
PLAN_INDIRIM_ILK_ORAN = 0.30
PLAN_INDIRIM_SONRA_ORAN = 0.50

# Plan tabloları: "geçen yılın gerçekleşeni" = önceki yılın aynı sezonunun
# gizli gerçek beklenen talebi × PLAN_BULUNABILIRLIK (simülasyon çıktısı
# plana geri beslenmez); × büyüme hedefi × yönetim iyimserliği (üst
# kategori başına bir kez çekilir).
PLAN_BULUNABILIRLIK = 0.85
PLAN_BUYUME_HEDEFI = 1.06
PLAN_IYIMSERLIK_ARALIGI = (1.03, 1.12)
PLAN_RANGE_SIGMA = 0.05         # range_plan option sayısı = gerçekleşen × lognormal(0, σ)
MFP_STOK_KAPSAMA_AY = 1.0       # dönem sonu stok hedefi = sonraki ayın satış planı × kapsama

# --- Motor (Görev 12) --------------------------------------------------------
# İlk dağıtım: ilk alımın bu payı paketle mağazalara gider (magaza_plan
# payıyla), kalanı depoda (online + replenishment) kalır.
ILK_DAGITIM_PAYI = 0.60

# Replenishment (v3 kuralı, v3 değerleri kopyalanmıştır).
REPL_HEDEF_GUN = 28             # hedef: önümüzdeki 4 haftanın plan talebi
OLU_STOK_PENCERESI_GUN = 28     # hız penceresi ve yeni hücre muafiyeti
OLU_STOK_HEDEF_HAFTA = 4        # hızla kaç haftalık stok "yeter" sayılır

# Basic/NOS sürekli tedarik (v3 kuralı).
SUREKLI_GOZDEN_GECIRME_HAFTA = 2
SUREKLI_EMNIYET_HAFTA = {"Basic": 2, "NOS": 3}
SUREKLI_DUZELTME_GUN = 56       # plan düzeltmesinin baktığı geçmiş
SUREKLI_DUZELTME_SINIR = (0.7, 1.6)

# İade (spec §6.1 adım 7). Online gecikmesi sabit 10 gün (7–14 aralığının
# ortası). Kalite izi: p_iade × (1 + IADE_KALITE_CARPANI × tedarikçinin
# gizli hatalı oranı).
IADE_ORANI_MAGAZA = 0.06
IADE_GECIKME_MAGAZA = 7
IADE_ORANI_ONLINE = 0.27
IADE_GECIKME_ONLINE = 10
IADE_KALITE_CARPANI = 4.0

# --- Markdown, RPT, ikame, çıkış (Görev 13) ---------------------------------
# Lumoda markdown kuralı (spec §5.2, içsel): Collection ve Outlet line,
# pazartesi, indirim_gun − MARKDOWN_ONCE_GUN'den itibaren. Beklenen STR =
# MARKDOWN_BEKLENEN_STR × min(1, (d − lansman) ÷ (indirim − lansman));
# option STR'si (brüt satış ÷ mağazalara giden) beklenenin
# MARKDOWN_TETIK katının altındaysa bir kademe derinleşir (haftada en fazla
# bir); indirim gününden itibaren en az MARKDOWN_INDIRIM_TABANI; hiç
# sığlaşmaz. Normal ve online hattı aynı.
MARKDOWN_KADEMELERI = (0.20, 0.30, 0.40, 0.50, 0.70)
MARKDOWN_ONCE_GUN = 28
MARKDOWN_BEKLENEN_STR = 0.80
MARKDOWN_TETIK = 0.7
MARKDOWN_INDIRIM_TABANI = 0.30
# Outlet hattı: outlet akışıyla gelen Collection, çıkış gününde %50'den
# başlar, her OUTLET_MARKDOWN_ARALIK_GUN günde bir kademe (en çok %70).
OUTLET_MARKDOWN_BASLANGIC = 0.50
OUTLET_MARKDOWN_ARALIK_GUN = 28
# Outlet'te satış penceresi çıkıştan sonra 12 hafta (cesit.OUTLET_AKISI_GUN ile aynı).
OUTLET_OMRU_GUN = 84
# Outlet akışında depo stoğunun bölünmesi: son bu kadar günün outlet satışı payı.
OUTLET_SATIS_PENCERESI_GUN = 28

# Lumoda'nın RPT pratiği (v3 kuralı, v3 değerleri kopyalanmıştır).
RPT_ILK_HAFTA = 3
RPT_SON_HAFTA = 6
RPT_STR_ESIGI = 0.55
RPT_MIKTAR_ORANI = 0.50

# İkame (spec §5.4). Beden ikamesi: karşılanmamış talebin BEDEN_IKAME_ORANI'
# aynı option'ın komşu bedenine (önce büyük). Kategori ikamesi: kalanın
# IKAME_PAYI[alt kategori]'si aynı mağaza × alt kategori × fiyat segmentinde
# stoğu olan başka option'lara. Tek tur.
BEDEN_IKAME_ORANI = 0.05
IKAME_PAYI = {
    "Tişört": 0.40, "Sweatshirt": 0.40,
    "Gömlek": 0.30, "Bluz": 0.30, "Pantolon": 0.30, "Jean": 0.30, "Etek": 0.30, "Şort": 0.30,
    "Kazak": 0.25, "Elbise": 0.25, "Tulum": 0.25,
    "Mont": 0.20, "Ceket": 0.20, "Trençkot": 0.20,
    "Çanta": 0.25, "Şal": 0.25, "Kemer": 0.25,
}

# --- Mağaza olayları ve elle transfer (Görev 14) ------------------------------
# Bölge müdürünün pazartesi elle transferi: bölge başına 0..ELLE_TRANSFER_MAKS
# (eşit olasılıklı); kaynak = son ELLE_SATIS_PENCERESI_GUN günde satışı 0 ve
# option stoğu ≥ ELLE_STOK_ESIGI olan (mağaza, option).
ELLE_TRANSFER_MAKS = 3
ELLE_STOK_ESIGI = 3
ELLE_SATIS_PENCERESI_GUN = 28

# --- Yayım ve kirli kayıtlar (Görev 15, spec §6.4, §7) -----------------------
# Kirli kayıtlar üç yıla ve ~80 mağazaya ölçekli (v3: 80 / 50 / 60, iki yıl,
# 25 mağaza); `kirlet` dünya akış tablosunun `kirli` çocuk üretecini kullanır.
MUKERRER_KAYIT = 200
BEDELSIZ_KAYIT = 120
HAYALET_STOK_KAYDI = 150
TEK_TARAFLI_TRANSFER = 40  # elle_transfer satırında varis_tarihi boş

CIKTI_DIZINI = Path(__file__).resolve().parents[3] / "cikti" / "v4"
