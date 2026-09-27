"""v4 sabitleri (Görev 3: pencere ve takvim). Sonraki görevler mağaza,
ürün, tedarik, talep, plan sabitlerini bu dosyaya ekler; tek yer burasıdır.

v4 hiçbir v2/v3/kök modülünü içe aktarmaz. Spec:
.superpowers/sdd/2026-09-27-veri-v4-cekirdek/{global,task-3-brief}.md
"""

from datetime import date

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

# Gizli gecikme profili (tedarikçi başına, menşe aralığından bir kez
# çekilir): ortalama ve standart sapma (gün); v3/spec yalnız menşe
# düzeyinde sınır verir (MENSE_V4 sapma_min/maks), tedarikçi düzeyinde
# farklılaşma (gizli gerçek — bir algoritmanın öğrenmesi gereken şey)
# burada tasarım kararıdır. `teslim_sapmasi` bu ortalama/sd ile Normal
# çeker, sonra menşenin sapma_min/maks'ına kırpar (yön/sınır garantisi).
GECIKME_PROFIL_ORT: dict[str, tuple[float, float]] = {
    "Yerli": (-1.0, 1.0), "Yakın": (3.0, 7.0), "Uzak Doğu": (7.0, 14.0),
}
GECIKME_PROFIL_SD: dict[str, tuple[float, float]] = {
    "Yerli": (1.0, 2.0), "Yakın": (1.5, 3.0), "Uzak Doğu": (3.0, 6.0),
}

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
# en küçük kapasiteli.
KAPASITE_SEZON_ARALIGI: dict[str, tuple[int, int]] = {
    "Yerli": (5_000, 15_000), "Yakın": (8_000, 20_000), "Uzak Doğu": (20_000, 60_000),
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

# Uzmanlıkta maliyet ×0,93, hatalı oran ×0,7 (spec §4.1). `uzmanlik_bonusu`
# (gizli tabloda) maliyet tarafını taşır; hatalı tarafı `hatali_adet`'in
# `uyum` parametresiyle doğrudan bu sabitten uygulanır.
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
