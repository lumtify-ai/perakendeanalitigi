"""Ortak fikstürler. Gerçek v4 verisi gerektirenler `veri` işaretlidir ve
oturum başına bir kez yüklenir."""

import warnings

import pandas as pd
import pytest

from rpt import kaynak

# numpy 2.5 + pandas 2.3: Timedelta içinde "generic unit" uyarısı (bizim değil)
warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)


@pytest.fixture(scope="session")
def veri():
    """Gerçek v4: temiz tablolar, option'lar, hücre-hafta paneli (oturumda bir kez)."""
    if not kaynak.VERITABANI.exists():
        pytest.skip("v4 verisi yok (cd veri && python -m perakende_veri.v4.uret)")
    t = kaynak.veri_yukle()
    opt = kaynak.optionlar(t)
    hh = kaynak.hucre_hafta(t, opt)
    return {"t": t, "opt": opt, "hh": hh}


def oyuncak_tablolar():
    """v4 şemalı oyuncak: tek option (OPT-A), iki beden, iki mağaza + ONL; elle izlenebilir.

    Lansman 2025-02-10 (pzt), indirim 2025-02-27 (perşembe; 17 gün), çıkış
    2025-03-10 (pzt, 4 hafta). M1 her gün stoklu ve her gün satar (S 2, M 1);
    M2'nin S bedeni ilk 3 gün 1'er satar, sonra stoksuzdur; M2'nin M bedeni
    stoklu ama hiç satmaz. ONL (online, stok satırı yok) her gün S'den 1,
    5. gün M'den 2 satar. Depo günlük yazılır (S: 100 - gün, M: 50).
    İlk dağıtım lansmandan 2 gün önce çıkar, lansman sabahı varır; bir
    replenishment 6. gün çıkar 8. gün varır (1. hafta).
    """
    lansman = pd.Timestamp("2025-02-10")
    gun = lambda n: lansman + pd.Timedelta(days=n)  # noqa: E731
    urun = pd.DataFrame({
        "urun_id": ["A-S", "A-M"], "option_id": ["OPT-A", "OPT-A"], "model_kodu": "MDLX",
        "model_adi": "Oyuncak", "renk": "Siyah", "cinsiyet": "Kadın", "ust_kategori": "Üst",
        "alt_kategori": "Tişört", "line": "Collection", "sezon_kodu": "SS25", "dalga": 1,
        "lansman_tarihi": lansman, "cikis_tarihi": gun(28),
        "tedarikci_id": "T01", "alis_fiyati": 100.0, "liste_fiyati": 250.0,
    })
    sezon = pd.DataFrame({"sezon_kodu": ["SS25"], "dalga": [1], "lansman_tarihi": [lansman],
                          "indirim_baslangic": [pd.Timestamp("2025-02-27")],
                          "cikis_tarihi": [gun(28)]})
    tedarikci = pd.DataFrame({"tedarikci_id": ["T01"], "ad": ["Ege"], "ulke": ["Türkiye"],
                              "mense": ["Yerli"], "ilk_siparis_hafta": [12], "rpt_hafta": [4],
                              "moq_option": [300], "uzmanlik": ["dokuma"]})
    satis = []
    for i in range(28):
        g = gun(i)
        satis.append((g, "M1", "A-S", 2))
        satis.append((g, "M1", "A-M", 1))
        satis.append((g, "ONL", "A-S", 1))
        if i < 3:
            satis.append((g, "M2", "A-S", 1))
    satis.append((gun(5), "ONL", "A-M", 2))
    satis = pd.DataFrame(satis, columns=["tarih", "magaza_id", "urun_id", "adet"])
    satis["tutar"], satis["indirim_tutari"], satis["kampanya_id"] = 100.0, 0.0, None
    stok = []
    for h in range(5):
        pzt = gun(7 * h)
        for m, u in (("M1", "A-S"), ("M1", "A-M"), ("M2", "A-S"), ("M2", "A-M")):
            m2s = m == "M2" and u == "A-S"
            sg = 0 if h == 0 else (3 if (m2s and h == 1) else (0 if m2s else 7))
            # h = 0: pazartesi sabahı mağazalar henüz boş (varış o günün hareketi)
            stok.append((pzt, m, u, 0 if (h == 0 or (m2s and h > 0)) else 5, sg))
    stok = pd.DataFrame(stok, columns=["tarih", "magaza_id", "urun_id", "adet", "stoklu_gun"])
    sevkiyat = pd.DataFrame({
        "tarih": [gun(-2)] * 4 + [gun(6), gun(7), gun(7), gun(8), gun(9)],
        "varis_tarihi": [gun(0)] * 4 + [gun(8), gun(9), gun(9), pd.NaT, gun(10)],
        "kaynak": ["DEPO"] * 4 + ["DEPO", "DEPO", "M1", "DEPO", "M1"],
        "hedef": ["M1", "M1", "M2", "M2", "M1", "M2", "DEPO", "M1", "M2"],
        "urun_id": ["A-S", "A-M", "A-S", "A-M", "A-S", "A-S", "A-S", "A-M", "A-M"],
        "adet": [60, 30, 3, 10, 12, 5, 4, 7, 2],
        "tip": ["ilk_dagitim"] * 4 + ["replenishment", "outlet_akisi", "stok_devri",
                                      "replenishment", "elle_transfer"],
        "paket_id": None})
    depo = pd.DataFrame([(gun(i), u, v) for i in range(28)
                         for u, v in (("A-S", 100 - i), ("A-M", 50))],
                        columns=["tarih", "urun_id", "adet"])
    siparis = pd.DataFrame({"siparis_id": ["SP1", "SP1"], "tip": "ilk", "option_id": "OPT-A",
                            "urun_id": ["A-S", "A-M"], "tedarikci_id": "T01",
                            "siparis_tarihi": pd.Timestamp("2024-11-18"),
                            "planlanan_teslim": pd.Timestamp("2025-02-03"),
                            "gerceklesen_teslim": pd.Timestamp("2025-02-03"), "adet": [163, 90]})
    kalite = pd.DataFrame({"siparis_id": ["SP1"], "teslim_tarihi": [pd.Timestamp("2025-02-03")],
                           "numune": [20], "hatali": [1]})
    magaza = pd.DataFrame({"magaza_id": ["M1", "M2", "ONL"], "ad": ["Bir", "İki", "Online"],
                           "tip": ["AVM", "Cadde", "Online"]})
    return {"urun": urun, "sezon": sezon, "tedarikci": tedarikci, "satis": satis,
            "stok": stok, "sevkiyat": sevkiyat, "depo_stok": depo, "siparis": siparis,
            "kalite_kontrol": kalite, "magaza": magaza, "takvim": pd.DataFrame()}


@pytest.fixture
def oyuncak():
    t = oyuncak_tablolar()
    opt = kaynak.optionlar(t)
    opt["plan_sezon"] = 50.0
    return t, opt
