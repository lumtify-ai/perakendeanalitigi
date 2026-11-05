"""`kiriklik.hikaye`: sahnenin yeni ölçüleri (Ruling R38) oyuncak tablolarla: verici başına varış günü, Lumoda'da verilen
bedenin vericideki satışı, sahne bütçesi, rotaların kargosu. Uçtan uca sahne KÜÇÜK koşularla el ile
(`python -m kiriklik.hikaye --olcek KUCUK`), TAM denetleyicide."""

from datetime import date

import pandas as pd
import pytest

from kiriklik import hikaye

KARAR = date(2024, 12, 9)
SATIR = ["magaza_id", "urun_id", "tarih", "adet", "tutar"]


def _satis(*satirlar) -> pd.DataFrame:
    df = pd.DataFrame(list(satirlar), columns=SATIR)
    df["tarih"] = pd.to_datetime(df["tarih"])
    return df


def test_varis_gunleri_verici_basina():
    """Her vericinin bu alıcıya, bu option'ın SKU'larındaki satırlarının en erken varışı (karardan gün); başka alıcıya ya
    da başka SKU'ya giden satır sayılmaz."""
    elle = pd.DataFrame([("V1", "A", "U-L", "2024-12-10"), ("V1", "A", "U-M", "2024-12-11"), ("V2", "A", "U-L", "2024-12-13"),
                         ("V2", "B", "U-L", "2024-12-10"), ("V3", "A", "X-L", "2024-12-10")],
                        columns=["kaynak", "hedef", "urun_id", "varis_tarihi"])
    elle["varis_tarihi"] = pd.to_datetime(elle["varis_tarihi"])
    assert hikaye.varis_gunleri(elle, "A", ["U-L", "U-M"], KARAR) == {"V1": 1, "V2": 4}


def test_lumoda_ilk_satis():
    """Vericinin verdiği bedeni Lumoda'da: pozitif satış adedi, ilk satışın karardan günü ve birim fiyatı (o günün
    pozitif satırlarından). İade adede girmez; satış yoksa adet 0, gün ve fiyat None."""
    t = _satis(("V1", "U-L", "2024-12-20", 1, 900.0), ("V1", "U-L", "2024-12-12", 2, 3259.98),
               ("V1", "U-L", "2024-12-15", -1, -1629.99), ("V1", "U-M", "2024-12-10", 5, 5000.0),
               ("V2", "U-L", "2024-12-10", 7, 7000.0))
    assert hikaye.lumoda_ilk_satis(t, "V1", "U-L", KARAR) == {"adet": 3, "ilk_gun": 3, "ilk_fiyat": pytest.approx(1629.99)}
    assert hikaye.lumoda_ilk_satis(t, "V3", "U-L", KARAR) == {"adet": 0, "ilk_gun": None, "ilk_fiyat": None}


def test_sahne_butcesi_ayni_hucreler():
    """Kol − Lumoda, net adet ve TL (iade dahil), yalnız verilen hücreler: alıcı +5 / +8.150, vericiler −5 / −6.683, net
    0 / +1.467; hücre dışı satırlar girmez."""
    kol = _satis(("A", "U-L", "2024-12-10", 3, 4890.0), ("A", "U-XL", "2024-12-11", 2, 3260.0),
                 ("A", "U-S", "2024-12-11", 9, 9000.0), ("V1", "U-M", "2024-12-11", 9, 9000.0))
    lum = _satis(("V1", "U-L", "2024-12-12", 3, 3683.0), ("V2", "U-XL", "2024-12-13", 2, 3000.0),
                 ("A", "U-S", "2024-12-11", 1, 1000.0))
    alici = pd.DataFrame([("A", "U-L"), ("A", "U-XL")], columns=["magaza_id", "urun_id"])
    verici = pd.DataFrame([("V1", "U-L"), ("V2", "U-XL")], columns=["magaza_id", "urun_id"])
    assert hikaye.sahne_butcesi(kol, lum, alici, verici) == {
        "alici": {"adet": 5, "tl": 8150.0}, "vericiler": {"adet": -5, "tl": -6683.0}, "net": {"adet": 0, "tl": 1467.0}}


def test_rotalarin_kargosu():
    """Rota sayısı × rota başı kargo: düşük ve orta maliyet (`sabitler.MALIYET_PAKETLERI`)."""
    assert hikaye.rota_kargosu(5) == {"dusuk": 1500.0, "orta": 2500.0}
