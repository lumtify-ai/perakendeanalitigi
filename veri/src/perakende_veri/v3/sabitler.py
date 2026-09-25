"""v3 sabitleri.

v3, v2'nin mağazasını, beden setlerini, kategori ağacını ve talep
çarpanlarını **içe aktarır**; burada yalnız v3'e özgü olanlar durur:
iki yıllık pencere, sezon/dalga takvimi, tedarik, yaşam eğrisi, ürün
sürprizi, planlı indirim ve sonlu depo. Spec:
docs/superpowers/specs/2026-09-26-veri-v3-ve-rpt-design.md, bölüm 2.
"""

from datetime import date
from pathlib import Path

# Mağazalar v2'nin üreticisinden, v2'nin tohumuyla gelir: aynı 25 mağaza.
TOHUM = 42
VERI_SURUMU = "v3"

# --- Pencere ------------------------------------------------------------
# Dışa aktarılan pencere iki tam yıldır. Simülasyon altı ay önce başlar:
# AW23'ün ürünleri pencere açıldığında rafta ve yaşam eğrisinin kuyruğunda
# olsun, depo ve devamlı ürün stoğu "ilk gün" yapaylığından arınsın diye.
ISINMA_BASLANGIC = date(2023, 7, 3)
BASLANGIC = date(2024, 1, 1)
BITIS = date(2025, 12, 31)

# 2025 talebi 2024'ün %6 üstü. Isınma dönemi (2023) aynı eğilimin bir yıl
# gerisinde durur; tek çarpan, yıl içinde sıçrama yok.
YIL_BUYUME = {2023: 1 / 1.06, 2024: 1.0, 2025: 1.06}

# Resmî tatiller + Black Friday. 2025 listesi v2'ninkiyle aynıdır.
# 2023'ün yalnız ikinci yarısı gerekir (ısınma 3 Temmuz'da başlar).
TATILLER = {
    # 2023 (ısınma)
    "2023-07-15", "2023-08-30", "2023-10-29", "2023-11-24",
    # 2024
    "2024-01-01", "2024-04-09", "2024-04-10", "2024-04-11", "2024-04-12",
    "2024-04-23", "2024-05-01", "2024-05-19", "2024-06-15", "2024-06-16",
    "2024-06-17", "2024-06-18", "2024-06-19", "2024-07-15", "2024-08-30",
    "2024-10-29", "2024-11-29",
    # 2025 (v2)
    "2025-01-01", "2025-03-30", "2025-03-31", "2025-04-01", "2025-04-23",
    "2025-05-01", "2025-05-19", "2025-06-06", "2025-06-07", "2025-06-08",
    "2025-06-09", "2025-07-15", "2025-08-30", "2025-10-29", "2025-11-28",
}

# --- Sezon ve dalga takvimi --------------------------------------------
# Moda zincirinin ticari takvimi ay değil sezon kodu ile yürür. Dalga
# tarihi = ilk dağıtımın mağazaya girdiği gün (pazartesi).
#
# AW25'in indirim ve çıkış tarihleri pencerenin dışındadır; zincirin
# ticari takvimi olarak önceden bilinir (planlama onlara göre yapılır),
# ama veri 2025-12-31'de kesilir: AW25 sağdan sansürlüdür.
SEZONLAR = {
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
DEVAMLI = "DEVAMLI"

# --- Ürün evreni --------------------------------------------------------
SEZON_COLLECTION_MODEL = 36
SEZON_OUTLET_MODEL = 6
BASIC_MODEL = 22
NOS_MODEL = 10
DALGA_SAYISI = 3

# Renk paleti genişler; kodlar v2'nin üç harfli biçimini korur
# (SYH, BEJ, LCV v2 ile aynı).
RENKLER = {
    "Siyah": "SYH", "Beyaz": "BYZ", "Bej": "BEJ", "Lacivert": "LCV",
    "Haki": "HAK", "Bordo": "BRD", "Ekru": "EKR", "İndigo": "IND",
    "Gri Melanj": "GRM", "Kiremit": "KRM", "Pudra": "PDR", "Yeşil": "YSL",
}
# Devamlı ürünler çekirdek renklerde döner: temel ürün sezon rengi taşımaz
DEVAMLI_RENK_HAVUZU = ["Siyah", "Beyaz", "Lacivert", "Gri Melanj", "Bej", "İndigo"]
SEZON_RENK_ARALIGI = (2, 4)   # Collection ve Outlet: 2–4 renk, uçlar dahil
BASIC_RENK = 3
NOS_RENK = 2

# Sezon tipine göre alt kategori ağırlıkları. Yaz koleksiyonunda mont,
# kış koleksiyonunda şort olmaz; kazak ve dış giyim kışın ağırlık kazanır.
ALT_KATEGORI_AGIRLIK = {
    "AW": {
        "Tişört": 0.5, "Gömlek": 1.0, "Kazak": 1.5, "Sweatshirt": 1.2,
        "Pantolon": 1.0, "Jean": 1.2, "Etek": 0.6, "Şort": 0.0,
        "Mont": 1.4, "Ceket": 1.0, "Trençkot": 0.6,
    },
    "SS": {
        "Tişört": 1.6, "Gömlek": 1.3, "Kazak": 0.2, "Sweatshirt": 0.5,
        "Pantolon": 1.0, "Jean": 1.1, "Etek": 1.0, "Şort": 1.2,
        "Mont": 0.1, "Ceket": 0.6, "Trençkot": 0.6,
    },
    "Basic": {
        "Tişört": 3.0, "Gömlek": 1.0, "Kazak": 0.6, "Sweatshirt": 1.5,
        "Pantolon": 1.5, "Jean": 2.0, "Etek": 0.3, "Şort": 0.4,
        "Mont": 0.3, "Ceket": 0.0, "Trençkot": 0.0,
    },
    "NOS": {
        "Tişört": 3.0, "Gömlek": 1.0, "Kazak": 0.0, "Sweatshirt": 1.0,
        "Pantolon": 1.0, "Jean": 2.0, "Etek": 0.0, "Şort": 0.0,
        "Mont": 0.0, "Ceket": 0.0, "Trençkot": 0.0,
    },
}

# --- Tedarik ------------------------------------------------------------
# Süreler aralık içinden tedarikçi başına BİR KEZ çekilir: tedarikçinin
# kendi sabit süresi vardır, gerçekleşen teslim onun etrafında sapar.
YERLI_TEDARIKCILER = [   # v2'nin üretici listesi
    "Ege Tekstil", "Marmara Konfeksiyon", "Denizli Örme",
    "Bursa Dokuma", "Çorlu Giyim",
]
UZAK_DOGU_TEDARIKCILER = [   # kurgusal
    ("Ningbo Hengtai Garment", "Çin"),
    ("Dhaka Meghna Apparels", "Bangladeş"),
    ("Saigon Lotus Garment", "Vietnam"),
]
MENSE = {
    "Yerli": {"ilk": (10, 12), "rpt": (4, 6), "moq": 300},
    "Uzak Doğu": {"ilk": (24, 30), "rpt": (12, 16), "moq": 600},
}
# Teslim sapması (gün, planlanana göre). Yerli: ±3 gün, simetrik.
# Uzak Doğu: 0…+21, sağa çarpık — gemi gecikir, erken gelmez.
YERLI_SAPMA_GUN = 3
UZAK_DOGU_SAPMA_GUN = 21
UZAK_DOGU_SAPMA_BETA = (1.3, 3.5)

# Uzak Doğu'dan gelme olasılığı (alt kategoriye göre). Dış giyim ve jean
# ağırlıklı Uzak Doğu (%60), tişört/gömlek/etek/şort ağırlıklı yerli (%80
# yerli). Kazak/sweatshirt/pantolon %25. Beklenen: AW ~%39, SS ~%31;
# bu tohumla Collection modellerinin %42'si Uzak Doğu (spec: ~%40).
UZAK_DOGU_OLASILIGI = {
    "Mont": 0.6, "Ceket": 0.6, "Trençkot": 0.6, "Jean": 0.6,
    "Tişört": 0.2, "Gömlek": 0.2, "Etek": 0.2, "Şort": 0.2,
    "Kazak": 0.25, "Sweatshirt": 0.25, "Pantolon": 0.25,
}

# --- Talep --------------------------------------------------------------
# Ürün sürprizi: plan bu çarpanı bilmez. RPT'nin varlık sebebi.
SURPRIZ_SIGMA = {"Collection": 0.55, "Outlet": 0.40, "Basic": 0.20, "NOS": 0.10}

# Yaşam eğrisi f(h) = (h+1)^a · exp(−h/τ), h = lansmandan beri hafta,
# tepesi 1'e ölçekli. SPEC SAPMASI: spec a=1,2 ve τ=5 diyor ama aynı
# cümlede "tepe 2.–4. haftada, 12. haftada tepenin ~%35'i" diyor; a=1,2,
# τ=5 tepeyi h=5'e (6. hafta) koyar ve 12. haftada tepenin %62'sini
# bırakır — kendi tarifiyle çelişir. a=1,0 ve τ=4 tarifi tutturur: tepe
# h=3 (4. hafta), h=11'de tepenin %41'i, h=12'de %34'ü.
YASAM_A = 1.0
YASAM_TAU_HAFTA = 4.0
YASAM_TAU_OYNAMA = 0.20   # alt kategori başına ±%20 (bir kez çekilir)

# Mevsimsellik: alt kategori başına (tepe ayı, genlik) — düzgün kosinüs,
# ortalaması 1. Line'ın sezon etkisiyle (v2 LINE_SEZON_ETKISI) üs olarak
# yumuşatılır.
MEVSIM = {
    "Mont": (12.5, 0.95), "Ceket": (11.0, 0.55), "Trençkot": (10.5, 0.35),
    "Kazak": (12.5, 0.70), "Sweatshirt": (12.0, 0.40),
    "Tişört": (6.5, 0.50), "Gömlek": (5.5, 0.20),
    "Pantolon": (10.0, 0.10), "Jean": (10.0, 0.15),
    "Etek": (6.0, 0.35), "Şort": (6.5, 1.00),
}

# Option düzeyinde haftalık çarpımsal AR(1) (log uzayında)
SURUKLENME_RHO = 0.7
SURUKLENME_SIGMA = 0.10

# Line hacmi. Sezonluk ürün yaşam eğrisiyle doğar ve söner; eğrinin
# ortalaması tepenin yarısı civarında olduğu için v2'nin Collection
# hacmiyle aynı ortalamaya ulaşmak tepenin daha yüksek olmasını ister.
# Basic/NOS için v2'nin line hacmi (talep.LINE_HACIM_CARPANLARI) aynen
# geçerli; bu sözlük onun ÜSTÜNE uygulanan v3 çarpanıdır.
SEZONLUK_TEPE_CARPANI = {"Collection": 1.7, "Outlet": 1.4, "Basic": 1.0, "NOS": 1.0}

# Planlı sezon sonu indirimi (Collection ve Outlet)
INDIRIM_ILK_HAFTA = 4
INDIRIM_ORANLARI = (0.30, 0.50)          # ilk 4 hafta, sonrası
INDIRIM_TALEP_CARPANI = (1.6, 2.2)       # fiyat esnekliği

# Kampanya gürültüsü: tam fiyatlı satışta rastgele işlem indirimi
ISLEM_INDIRIM_OLASILIGI = 0.08
ISLEM_INDIRIM_ORANI = 0.30

# --- Plan, ilk alım, ilk dağıtım ---------------------------------------
HEDEF_TAM_FIYAT_STR = 0.80     # ilk alım = plan / 0,80
ILK_DAGITIM_PAYI = 0.60        # ilk alımın %60'ı mağazalara, %40'ı depoda
PLANLANAN_TESLIM_ONCE_HAFTA = 1   # depoya lansmandan bir hafta önce
YUVARLAMA_ADET = 10            # sipariş miktarı 10'un katına yuvarlanır

# --- Depo ve replenishment ---------------------------------------------
REPL_HEDEF_GUN = 28            # hedef: önümüzdeki 4 haftanın plan talebi
OLU_STOK_PENCERESI_GUN = 28    # hız penceresi ve yeni hücre muafiyeti
OLU_STOK_HEDEF_HAFTA = 4       # hızla kaç haftalık stok "yeter" sayılır

# Sürekli tedarik (Basic, NOS): iki haftada bir gözden geçirme
SUREKLI_GOZDEN_GECIRME_HAFTA = 2
SUREKLI_EMNIYET_HAFTA = {"Basic": 2, "NOS": 3}
SUREKLI_DUZELTME_GUN = 56       # plan düzeltmesinin baktığı geçmiş
SUREKLI_DUZELTME_SINIR = (0.7, 1.6)
SUREKLI_SAPMA_SAYISI = 128     # option başına önceden çekilen teslim sapması

# --- Lumoda'nın RPT pratiği (spec 2.8) ---------------------------------
RPT_ILK_HAFTA = 3
RPT_SON_HAFTA = 6
RPT_STR_ESIGI = 0.55
RPT_MIKTAR_ORANI = 0.50

# --- İade ve kirli kayıtlar (v2'nin iki yıla ölçeklenmiş hâli) ----------
IADE_ORANI = 0.06
IADE_GECIKME_GUN = 7
MUKERRER_KAYIT = 80
BEDELSIZ_KAYIT = 50
HAYALET_STOK_KAYDI = 60

CIKTI_DIZINI = Path(__file__).resolve().parents[3] / "cikti" / VERI_SURUMU
