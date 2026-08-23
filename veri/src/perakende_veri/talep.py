"""Talep çarpanları.

Bu modül kasten saf fonksiyonlardan oluşur: durum tutmaz, rastgelelik
içermez. Simülasyonun test edilebilirliği bu ayrıma dayanır.
"""

# Bedenler normal dağılıma yakın; uçlarda talep düşük. Transfer probleminin
# kaynağı büyük ölçüde bu asimetridir.
BEDEN_PAYLARI = {"XS": 0.10, "S": 0.22, "M": 0.32, "L": 0.24, "XL": 0.12}

SEZON_CARPANLARI = {
    "Dış Giyim": {"Sonbahar/Kış": 1.9, "İlkbahar/Yaz": 0.3},
    "Üst Giyim": {"Sonbahar/Kış": 1.0, "İlkbahar/Yaz": 1.1},
    "Alt Giyim": {"Sonbahar/Kış": 0.95, "İlkbahar/Yaz": 1.05},
}

MAGAZA_TIPI_CARPANLARI = {"AVM": 1.0, "Cadde": 0.72, "Outlet": 1.45}

TABAN_TALEP = {"Üst Giyim": 0.14, "Alt Giyim": 0.10, "Dış Giyim": 0.06}


def beden_dagilimi() -> dict[str, float]:
    return dict(BEDEN_PAYLARI)


def sezon_carpani(kategori: str, sezon: str) -> float:
    return SEZON_CARPANLARI[kategori][sezon]


def magaza_tipi_carpani(tip: str) -> float:
    return MAGAZA_TIPI_CARPANLARI[tip]


def gun_carpani(hafta_gunu: int, tatil_mi: bool) -> float:
    """hafta_gunu: 0=Pazartesi … 6=Pazar"""
    hafta_ici_disi = 1.55 if hafta_gunu >= 5 else 1.0
    return hafta_ici_disi * (1.35 if tatil_mi else 1.0)


def taban_talep(kategori: str) -> float:
    return TABAN_TALEP[kategori]
