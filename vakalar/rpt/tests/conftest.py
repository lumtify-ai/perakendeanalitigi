"""Ortak fikstürler. Gerçek v3 verisi gerektirenler `veri` işaretlidir ve
oturum başına bir kez yüklenir."""

import warnings

import pandas as pd
import pytest

from rpt import kaynak

# numpy 2.5 + pandas 2.3: Timedelta içinde "generic unit" uyarısı (bizim değil)
warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)


@pytest.fixture(scope="session")
def veri():
    if not kaynak.VERITABANI.exists():
        pytest.skip("v3 verisi yok (cd veri && python -m perakende_veri.v3.uret)")
    from perakende_veri.v3.dunya import dunya_kur

    t = kaynak.veri_yukle()
    dunya = dunya_kur()
    opt = kaynak.plan_ekle(kaynak.optionlar(t), dunya)
    hh = kaynak.hucre_hafta(t, opt)
    return {"t": t, "opt": opt, "hh": hh, "dunya": dunya}


def oyuncak_tablolar():
    """Tek option (OPT-A), iki beden, iki mağaza; elle izlenebilir.

    Lansman 2025-02-10 (pzt), indirim 2025-02-27 (perşembe; 17 gün), çıkış
    2025-03-10 (pzt, 4 hafta). M1 her gün stoklu ve her gün satar (S 2, M 1);
    M2'nin S bedeni ilk 3 gün 1'er satar, sonra stoksuzdur (günde 1 kayıp);
    M2'nin M bedeni stoklu ama hiç satmaz.
    """
    lansman = pd.Timestamp("2025-02-10")
    urun = pd.DataFrame({
        "urun_id": ["A-S", "A-M"], "option_id": ["OPT-A", "OPT-A"], "model_kodu": "MDLX",
        "model_adi": "Oyuncak", "renk": "Siyah", "cinsiyet": "Kadın", "ust_kategori": "Üst",
        "alt_kategori": "Tişört", "line": "Collection", "sezon_kodu": "SS25", "dalga": 1,
        "lansman_tarihi": lansman, "cikis_tarihi": pd.Timestamp("2025-03-10"),
        "tedarikci_id": "T01", "alis_fiyati": 100.0, "liste_fiyati": 250.0,
    })
    sezon = pd.DataFrame({"sezon_kodu": ["SS25"], "dalga": [1], "lansman_tarihi": [lansman],
                          "indirim_baslangic": [pd.Timestamp("2025-02-27")],
                          "cikis_tarihi": [pd.Timestamp("2025-03-10")]})
    tedarikci = pd.DataFrame({"tedarikci_id": ["T01"], "ad": ["Ege"], "ulke": ["Türkiye"],
                              "mense": ["Yerli"], "ilk_siparis_hafta": [12], "rpt_hafta": [4],
                              "moq_option": [300]})
    gunler = pd.date_range(lansman, periods=28, freq="D")
    satis, kayip = [], []
    for i, g in enumerate(gunler):
        satis.append((g, "M1", "A-S", 2))
        satis.append((g, "M1", "A-M", 1))
        if i < 3:
            satis.append((g, "M2", "A-S", 1))
        else:
            kayip.append((g, "M2", "A-S", 1))
    satis = pd.DataFrame(satis, columns=["tarih", "magaza_id", "urun_id", "adet"])
    satis["tutar"], satis["indirim_tutari"] = 100.0, 0.0
    kayip = pd.DataFrame(kayip, columns=["tarih", "magaza_id", "urun_id", "kayip_adet"])
    stok = []
    for h in range(5):
        pzt = lansman + pd.Timedelta(days=7 * h)
        for m, u in (("M1", "A-S"), ("M1", "A-M"), ("M2", "A-S"), ("M2", "A-M")):
            m2s = m == "M2" and u == "A-S"
            sg = 0 if h == 0 else (3 if (m2s and h == 1) else (0 if m2s else 7))
            stok.append((pzt, m, u, 0 if (m2s and h > 0) else 5, sg))
    stok = pd.DataFrame(stok, columns=["tarih", "magaza_id", "urun_id", "adet", "stoklu_gun"])
    sevkiyat = pd.DataFrame({
        "tarih": [lansman] * 4, "magaza_id": ["M1", "M1", "M2", "M2"],
        "urun_id": ["A-S", "A-M", "A-S", "A-M"], "adet": [60, 30, 3, 10], "tip": "ilk_dagitim"})
    depo = pd.DataFrame({"tarih": [lansman, lansman], "urun_id": ["A-S", "A-M"], "adet": [100, 50]})
    siparis = pd.DataFrame({"siparis_id": ["SP1", "SP1"], "tip": "ilk", "option_id": "OPT-A",
                            "urun_id": ["A-S", "A-M"], "tedarikci_id": "T01",
                            "siparis_tarihi": pd.Timestamp("2024-11-18"),
                            "planlanan_teslim": pd.Timestamp("2025-02-03"),
                            "gerceklesen_teslim": pd.Timestamp("2025-02-03"), "adet": [163, 90]})
    magaza = pd.DataFrame({"magaza_id": ["M1", "M2"], "ad": ["Bir", "İki"], "tip": ["AVM", "Cadde"]})
    return {"urun": urun, "sezon": sezon, "tedarikci": tedarikci, "satis": satis,
            "kayip_satis": kayip, "stok": stok, "sevkiyat": sevkiyat, "depo_stok": depo,
            "siparis": siparis, "magaza": magaza, "takvim": pd.DataFrame()}


@pytest.fixture
def oyuncak():
    t = oyuncak_tablolar()
    opt = kaynak.optionlar(t)
    opt["plan_sezon"] = 50.0
    return t, opt
