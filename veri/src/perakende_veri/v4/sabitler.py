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
