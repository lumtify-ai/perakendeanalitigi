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

MARKA = "Vesta"

# sabitler.py -> perakende_veri -> src -> veri  (parents[2] = veri/)
CIKTI_DIZINI = Path(__file__).resolve().parents[2] / "cikti" / VERI_SURUMU
