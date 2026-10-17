"""`replenishment.kalibrasyon`: AW24 penceresinde parametre seçimi (spec §4.4,
Ruling R23).

Seçim mantığı sahte bir `kos_fn` ile sınanır (koşu yok): kalibrasyon koşuyu
enjekte edilen fonksiyona bırakır, motoru içe aktarmaz (`tests/test_sizinti.py`).
Referans tavan oyuncak dünyanın sevkiyatından.
"""

import json
import math
from datetime import date

import pandas as pd
import pytest
from conftest import gun

from replenishment import kalibrasyon
from replenishment.dagitim import KoliKurali
from replenishment.ihtiyac import GuvenlikStoku
from replenishment.kalibrasyon import Kalibrasyon, en_yakin, kalibre_et, maliyet_secimi, referans_tavan
from replenishment.politika import Ayar
from replenishment.sabitler import KAL_BAS, KAL_BIT, OYUN_BAS, OYUN_BIT

# ---------------------------------------------------------------- saf seçim


def test_en_yakin_esitlikte_kucuk_deger():
    assert en_yakin({2: 90.0, 3: 96.0, 4: 94.0}, hedef=95.0) == 3
    assert en_yakin({2: 94.0, 4: 96.0}, hedef=95.0) == 2


def test_maliyet_secimi_bulunabilirlik_esigini_korur():
    satirlar = [
        {"ad": "a", "bulunabilirlik": 95.0, "toplama_maliyeti_tl": 900},
        {"ad": "b", "bulunabilirlik": 94.5, "toplama_maliyeti_tl": 500},
        {"ad": "c", "bulunabilirlik": 93.0, "toplama_maliyeti_tl": 100},
    ]
    assert maliyet_secimi(satirlar)["ad"] == "b"


def test_maliyet_secimi_esik_tam_bir_puan():
    satirlar = [
        {"ad": "a", "bulunabilirlik": 95.0, "toplama_maliyeti_tl": 900},
        {"ad": "b", "bulunabilirlik": 94.0, "toplama_maliyeti_tl": 500},
    ]
    assert maliyet_secimi(satirlar)["ad"] == "b"


# ---------------------------------------------------------------- referans tavan


def test_referans_tavan(oyuncak_con):
    """Oyuncakta fiziksel mağazaya `replenishment` sevkleri: g0 7, g7 12, g14 9 adet
    (g7'deki `outlet_akisi` sayılmaz). Ortalama, penceredeki pazartesi sayısına
    bölünür (sevksiz hafta 0 sayılır)."""
    assert referans_tavan(oyuncak_con, gun(0).date(), gun(13).date(), oran=1.0) == 9     # 19 / 2
    assert referans_tavan(oyuncak_con, gun(7).date(), gun(13).date()) == 3               # ⌊0,25 × 12⌋
    assert referans_tavan(oyuncak_con, gun(0).date(), gun(20).date(), oran=1.0) == 9     # ⌊28 / 3⌋
    assert referans_tavan(oyuncak_con, gun(0).date(), gun(27).date(), oran=1.0) == 7     # 28 / 4 hafta


def test_referans_tavan_varsayilan_kalibrasyon_penceresi(oyuncak_con):
    # oyuncakta 2024 sonbaharında sevk yok: tavan 0 (pencere KAL_*)
    assert referans_tavan(oyuncak_con) == 0


# ---------------------------------------------------------------- kalibre_et (sahte kos_fn)


class _Sahte:
    """Ayar'dan sentetik ölçüt üreten `kos_fn`; çağrıları kaydeder.

    Kısıtsız (güvenlik stoku) koşularında: istatistik 95,0; sabit d → 90 + 2d
    (hedefe en yakın 2 → 94, 3 → 96: eşitlikte küçük, 2); ros d → 88 + d (7 → 95).
    Mağaza stoğu: sabit 2 → 900, ros 7 → 800, istatistik 1000 → seçilen aile ros.
    Koli koşularında (tavan sonlu): A ve B tablolardan."""

    def __init__(self):
        self.cagrilar: list[tuple[str, Ayar]] = []

    def __call__(self, ad: str, ayar: Ayar) -> dict:
        self.cagrilar.append((ad, ayar))
        gs = ayar.gs
        if ayar.kisitsiz:
            b = {"istatistik": 95.0, "sabit": 90 + 2 * gs.deger, "ros": 88 + gs.deger}[gs.aile]
            stok = {"istatistik": 1000.0, "sabit": 2000.0 - 550 * gs.deger, "ros": 1500.0 - 100 * gs.deger}[gs.aile]
            return {"bulunabilirlik": b, "toplama_maliyeti_tl": 1e6, "magaza_stok_son": stok}
        k = ayar.kural()
        if k.ad == "A":
            b, maliyet = self.A[(k.alfa, k.beta)]
        else:
            b, maliyet = self.B[k.gamma]
        return {"bulunabilirlik": b, "toplama_maliyeti_tl": maliyet, "magaza_stok_son": 0.0}

    # (bulunabilirlik, maliyet): α küçük → daha çok koli, bulunabilirlik yüksek ve pahalı
    A = {(0.4, 2): (93.0, 1000), (0.4, 3): (93.5, 900), (0.6, 2): (92.0, 800), (0.6, 3): (92.5, 700),
         (0.4, 4): (93.0, 1100), (0.6, 4): (91.0, 1200)}
    B = {0.5: (93.0, 950), 0.75: (92.0, 850)}


def test_kalibrasyon_penceresi_oyunu_gormez():
    """Her kalibrasyon koşusunda kol yalnız KAL_BAS…KAL_BIT'te etkin; hiçbir çağrı oyun
    penceresine dokunmaz; bütçe ≤ 18 koşu; adlar benzersiz."""
    s = _Sahte()
    kalibre_et(s, tavan=1234)
    assert 0 < len(s.cagrilar) <= 18
    assert all(a.pencere == (KAL_BAS, KAL_BIT) for _, a in s.cagrilar)
    assert all(a.pencere[1] < OYUN_BAS for _, a in s.cagrilar)
    adlar = [ad for ad, _ in s.cagrilar]
    assert len(adlar) == len(set(adlar))
    assert all(ad.startswith("kal_") for ad in adlar)


def test_kalibre_et_secimleri():
    s = _Sahte()
    k = kalibre_et(s, tavan=1234)
    assert isinstance(k, Kalibrasyon)
    assert k.hedef_bulunabilirlik == 95.0
    assert k.gs == {"sabit": GuvenlikStoku("sabit", 2), "ros": GuvenlikStoku("ros", 7),
                    "istatistik": GuvenlikStoku("istatistik")}
    assert k.secilen_aile == "ros"                  # en düşük pencere sonu mağaza stoğu
    assert k.tavan == 1234
    # A: en iyi 93,5 (α 0,4, β 3); eşik 92,5: α 0,6 β 3 (92,5; maliyet 700) en ucuz
    assert k.koli["A"] == KoliKurali("A", alfa=0.6, beta=3)
    # B: en iyi 93,0 (γ 0,5); γ 0,75 → 92,0 eşikte, maliyet 850 < 950
    assert k.koli["B"] == KoliKurali("B", gamma=0.75)
    assert k.koli["C"] == KoliKurali("C", alfa=0.6, beta=3, gamma=0.75)
    # seçilen koli: A* (92,5; 700) ve B* (92,0; 850) arasından, eşik 91,5: A ucuz
    assert k.secilen_koli == "A"


def test_izgaralar_sabit():
    """Ruling R25: ros 6 ve β 4 ızgarada; bütçe 1 + 4 + 5 + 6 + 2 = 18 TAM koşu."""
    assert kalibrasyon.SABIT_IZGARA == (1, 2, 3, 4)
    assert kalibrasyon.ROS_IZGARA == (3, 5, 6, 7, 10)
    assert kalibrasyon.ALFA_IZGARA == (0.4, 0.6)
    assert kalibrasyon.BETA_IZGARA == (2, 3, 4)
    assert kalibrasyon.GAMA_IZGARA == (0.5, 0.75)
    s = _Sahte()
    kalibre_et(s, tavan=1234)
    assert len(s.cagrilar) == 18


def test_kalibre_et_ayarlari():
    """Güvenlik stoku aileleri kısıtsız (tavan ∞, koli zorunluluğu yok); koli ızgarası
    seçilen ailenin güvenlik stokuyla referans tavanda, kısıtlı."""
    s = _Sahte()
    kalibre_et(s, tavan=1234)
    gs_cagrilari = [a for _, a in s.cagrilar if a.kisitsiz]
    koli_cagrilari = [a for _, a in s.cagrilar if not a.kisitsiz]
    assert len(gs_cagrilari) == 1 + len(kalibrasyon.SABIT_IZGARA) + len(kalibrasyon.ROS_IZGARA)
    assert all(math.isinf(a.tavan) for a in gs_cagrilari)
    assert len(koli_cagrilari) == len(kalibrasyon.ALFA_IZGARA) * len(kalibrasyon.BETA_IZGARA) + len(
        kalibrasyon.GAMA_IZGARA)
    assert all(a.tavan == 1234 and a.gs == GuvenlikStoku("ros", 7) for a in koli_cagrilari)
    assert {a.kural().ad for a in koli_cagrilari} == {"A", "B"}


def test_kalibre_et_tablosu():
    s = _Sahte()
    k = kalibre_et(s, tavan=1234)
    assert isinstance(k.tablo, pd.DataFrame)
    assert len(k.tablo) == len(s.cagrilar)
    assert list(k.tablo["ad"]) == [ad for ad, _ in s.cagrilar]
    assert {"asama", "ad", "aile", "deger", "koli", "bulunabilirlik", "toplama_maliyeti_tl",
            "magaza_stok_son"} <= set(k.tablo.columns)
    assert set(k.tablo["asama"]) == {"hedef", "sabit", "ros", "koli_A", "koli_B"}


def test_kalibrasyon_json_gidis_donus(tmp_path):
    k = kalibre_et(_Sahte(), tavan=1234)
    yol = tmp_path / "kalibrasyon.json"
    kalibrasyon.yaz(k, yol, sure_sn=12.5)
    d = json.loads(yol.read_text(encoding="utf-8"))
    assert d["pencere"] == [KAL_BAS.isoformat(), KAL_BIT.isoformat()]
    assert d["sure_sn"] == 12.5
    geri = kalibrasyon.oku(yol)
    assert (geri.gs, geri.koli, geri.secilen_aile, geri.secilen_koli, geri.tavan, geri.hedef_bulunabilirlik) == (
        k.gs, k.koli, k.secilen_aile, k.secilen_koli, k.tavan, k.hedef_bulunabilirlik)
    pd.testing.assert_frame_equal(geri.tablo, k.tablo, check_dtype=False)


def test_referans_ayar():
    k = kalibre_et(_Sahte(), tavan=1234)
    a = k.referans_ayar()
    assert a == Ayar(koli=KoliKurali("A", alfa=0.6, beta=3), tavan=1234, gs=GuvenlikStoku("ros", 7),
                     pencere=(OYUN_BAS, OYUN_BIT))
    assert k.referans_ayar(oncelik="esit", tavan=math.inf).tavan == math.inf


def test_eksik_olcut_hata():
    with pytest.raises(KeyError):
        kalibre_et(lambda ad, ayar: {"bulunabilirlik": 1.0}, tavan=10)


def test_kalibrasyon_motoru_ice_aktarmaz():
    from test_sizinti import PAKET, ihlaller

    assert "kalibrasyon" not in ihlaller(PAKET)


def test_kal_penceresi_pazartesi():
    assert KAL_BAS.weekday() == 0 and KAL_BAS == date(2024, 9, 2)
