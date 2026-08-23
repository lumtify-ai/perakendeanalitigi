"""Talep çarpanları.

Bu modül kasten saf fonksiyonlardan oluşur: durum tutmaz, rastgelelik
içermez. Simülasyonun test edilebilirliği bu ayrıma dayanır.
"""

# Beden talebi etikete değil, setteki SIRAYA bağlıdır. Tişört S/M/L
# gider, pantolon 32/34 gider — ama ikisinde de orta kademeler satar,
# uçlar durur. Eğri bu yüzden 1..5 konumu üzerinden tanımlanır.
# Transfer probleminin kaynağı büyük ölçüde bu asimetridir.
BEDEN_PAYLARI = {1: 0.10, 2: 0.22, 3: 0.32, 4: 0.24, 5: 0.12}

SEZON_CARPANLARI = {
    "Dış Giyim": {"Sonbahar/Kış": 1.9, "İlkbahar/Yaz": 0.3},
    "Üst Giyim": {"Sonbahar/Kış": 1.0, "İlkbahar/Yaz": 1.1},
    "Alt Giyim": {"Sonbahar/Kış": 0.95, "İlkbahar/Yaz": 1.05},
}

MAGAZA_TIPI_CARPANLARI = {"AVM": 1.0, "Cadde": 0.72, "Outlet": 1.45}

TABAN_TALEP = {"Üst Giyim": 0.14, "Alt Giyim": 0.10, "Dış Giyim": 0.06}

CINSIYET_CARPANLARI = {"Kadın": 1.15, "Erkek": 0.85, "Unisex": 0.95}

# --- Line: ürünün ticari rolü -------------------------------------------
# Sezonluk / devamlı ayrımı ayrı bir eksen değildir; line onu taşır.
#
# Sezon etkisi: 1.0 = kategorinin sezon dalgalanmasını olduğu gibi alır,
# 0.0 = sezondan hiç etkilenmez. NOS ürünün stoğu asla bitmemeli, bu
# yüzden talebi de yıl boyu düzdür. Collection sezonuyla gelir gider.
LINE_SEZON_ETKISI = {"Basic": 0.35, "Collection": 1.00, "NOS": 0.15, "Outlet": 0.60}

# Hacim: NOS ve Basic çok satar; Outlet geçmiş sezondur, talebi düşüktür.
LINE_HACIM_CARPANLARI = {"Basic": 1.15, "Collection": 1.00, "NOS": 1.30, "Outlet": 0.55}

# Moda riski: Collection'ın bir mağazada tutup diğerinde tutmama ihtimali
# yüksektir; NOS'ta neredeyse yoktur. Simülasyon yerel sapmayı bununla ölçekler.
LINE_MODA_RISKI = {"Basic": 0.75, "Collection": 1.35, "NOS": 0.45, "Outlet": 1.10}


def beden_dagilimi() -> dict[int, float]:
    """Beden setindeki sıraya göre talep payları. Toplamı 1.0'dır."""
    return dict(BEDEN_PAYLARI)


def sezon_carpani(ust_kategori: str, sezon: str) -> float:
    return SEZON_CARPANLARI[ust_kategori][sezon]


def magaza_tipi_carpani(tip: str) -> float:
    return MAGAZA_TIPI_CARPANLARI[tip]


def cinsiyet_carpani(cinsiyet: str) -> float:
    return CINSIYET_CARPANLARI[cinsiyet]


def taban_talep(ust_kategori: str) -> float:
    return TABAN_TALEP[ust_kategori]


def line_hacim_carpani(line: str) -> float:
    return LINE_HACIM_CARPANLARI[line]


def line_moda_riski(line: str) -> float:
    return LINE_MODA_RISKI[line]


def line_sezon_carpani(line: str, ust_kategori: str, sezon: str) -> float:
    """Kategorinin sezon çarpanını ürünün line'ına göre yumuşatır."""
    ham = sezon_carpani(ust_kategori, sezon)
    return 1.0 + (ham - 1.0) * LINE_SEZON_ETKISI[line]


def gun_carpani(hafta_gunu: int, tatil_mi: bool) -> float:
    """hafta_gunu: 0=Pazartesi … 6=Pazar"""
    hafta_ici_disi = 1.55 if hafta_gunu >= 5 else 1.0
    return hafta_ici_disi * (1.35 if tatil_mi else 1.0)
