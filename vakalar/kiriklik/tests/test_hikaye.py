"""`kiriklik.hikaye`: sahnenin yeni ölçüleri (Ruling R38) oyuncak tablolarla: verici başına varış günü, Lumoda'da verilen
bedenin vericideki satışı, sahne bütçesi, rotaların kargosu; aday süzgeci ve seviye gevşetme. Uçtan uca sahne KÜÇÜK koşularla el ile
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


def _aday(alici, sehir, ist_disi, sehir_disi, depo_bos=True, lumoda_kirik=True, option="O1", alinan=5) -> dict:
    return {"alici": alici, "option_id": option, "alinan": alinan, "sehir": sehir, "verici": 3,
            "verici_istanbul_disi": ist_disi, "verici_sehir_disi": sehir_disi, "kirik_beden": 2, "depo_bos": depo_bos,
            "lumoda_kirik": lumoda_kirik}


def test_suz_kosullari():
    """Depoda yok ve Lumoda'da da kırık şart; `istanbul` süzgeci alıcı İstanbul + İstanbul dışı verici, `sehir` süzgeci
    alıcının şehri dışından verici sayar."""
    t = pd.DataFrame([_aday("A", "İstanbul", 3, 3), _aday("B", "İstanbul", 3, 3, depo_bos=False),
                      _aday("C", "İstanbul", 3, 3, lumoda_kirik=False), _aday("D", "İstanbul", 2, 3),
                      _aday("E", "Ankara", 3, 3), _aday("F", "Ankara", 1, 1)])
    assert list(hikaye.suz(t, ("tam", 3, "istanbul"))["alici"]) == ["A"]
    assert list(hikaye.suz(t, ("iki_verici", 2, "istanbul"))["alici"]) == ["A", "D"]
    assert list(hikaye.suz(t, ("sehir_disi", 2, "sehir"))["alici"]) == ["A", "D", "E"]
    assert hikaye.suz(t.iloc[:0], ("tam", 3, "istanbul")).empty


@pytest.mark.parametrize("satirlar, seviye, alici", [
    ([_aday("A", "İstanbul", 3, 3), _aday("B", "İstanbul", 2, 2)], "tam", ["A"]),
    ([_aday("B", "İstanbul", 2, 2), _aday("C", "Ankara", 2, 2)], "iki_verici", ["B"]),
    ([_aday("C", "Ankara", 2, 2), _aday("D", "İstanbul", 1, 1)], "sehir_disi", ["C"]),
])
def test_sec_ilk_bos_olmayan_seviye(satirlar, seviye, alici):
    """Seviye yalnız üstündekiler boşsa gevşer."""
    ad, a = hikaye.sec(pd.DataFrame(satirlar))
    assert ad == seviye and list(a["alici"]) == alici


def test_sec_aday_yoksa_eksik_kucuk_yedek_yalniz_kucukte():
    """TAM'da hiçbir seviye tutmazsa `Eksik` (sahne uydurulmaz); tek verici yedeği yalnız KÜÇÜK ölçekte."""
    t = pd.DataFrame([_aday("D", "Ankara", 1, 1)])
    with pytest.raises(hikaye.Eksik):
        hikaye.sec(t)
    ad, a = hikaye.sec(t, "kucuk")
    assert ad == "kucuk_yedek" and list(a["alici"]) == ["D"]
