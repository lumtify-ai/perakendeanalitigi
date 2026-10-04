"""ozellikler.ekle: hücre-gün anahtarlarına gözlemlenebilir özellikler."""

import numpy as np
import pandas as pd
import pytest
from conftest import ekle, oyuncak_baglan, oyuncak_tablolar

from perakende_analitik import ozellikler, stok

S = "MDL0001-SYH-S"     # temel senaryo, Basic / Üst Giyim / sezon_kodu AW24 dalga 1, liste 250
OUT = "MDL0010-SYH-M"    # Outlet hattı: cikis_tarihi 2025-01-12, Aksesuar
DEV = "MDL0011-SYH-M"    # devamlı (sezon_kodu DEVAMLI), lansman 2020-01-01
PANEL = 250.0


def _urun_ekle(t, urun_id: str, **ozel) -> None:
    yeni = t["urun"].iloc[[0]].copy()
    yeni["urun_id"] = urun_id
    yeni["option_id"] = urun_id.rsplit("-", 1)[0]
    for k, v in ozel.items():
        yeni[k] = pd.to_datetime(v) if k.endswith("tarihi") else v
    t["urun"] = pd.concat([t["urun"], yeni], ignore_index=True)


def _anahtar(satirlar: list[tuple[str, str, str]]) -> pd.DataFrame:
    """(tarih, magaza, urun) demetlerinden günlük tablo anahtarı (R9 türleri)."""
    df = pd.DataFrame(satirlar, columns=["tarih", "magaza_id", "urun_id"])
    df["tarih"] = pd.to_datetime(df["tarih"]).astype("datetime64[ns]")
    df["magaza_id"] = df["magaza_id"].astype("category")
    df["urun_id"] = df["urun_id"].astype("category")
    return df


@pytest.fixture
def oz_con():
    t = oyuncak_tablolar()
    ekle(t, "magaza", [("M003", "Ankara", "Ankara", "İç Anadolu", 39.9, 32.8, "Cadde", 300, 1,
                        4000, "2015-01-01", None)])
    _urun_ekle(t, OUT, line="Outlet", ust_kategori="Aksesuar", alt_kategori="Şapka",
               sezon_kodu="AW24", dalga=2, cikis_tarihi="2025-01-12", liste_fiyati=100.0,
               beden_sira=3)
    _urun_ekle(t, DEV, line="NOS", sezon_kodu="DEVAMLI", lansman_tarihi="2020-01-01")
    ekle(t, "sezon", [
        ("AW24", 1, "2024-08-19", "2025-01-02", "2025-02-24"),   # 01-02 .. 01-08
        ("AW24", 2, "2024-09-23", "2025-01-10", "2025-02-24"),   # 01-10 .. 01-16
        ("DEVAMLI", 1, "2020-01-01", "2025-01-02", "2025-02-24"),  # devamlıda yok sayılır
    ])
    ekle(t, "takvim", [("2025-01-01", 1, 1, 2025, "AW24", "AW24", True, False),
                       ("2025-01-08", 2, 1, 2025, "AW24", "AW24", False, True)])
    ekle(t, "kampanya", [
        # tüm ürünler, tüm bölgeler; 01-06 .. 01-10
        ("KAT_A", "kategori", "2025-01-06", "2025-01-10", "", "", "", 0.20),
        # Üst Giyim / Marmara,Ege; 01-13 .. 01-15
        ("KAT_B", "kategori", "2025-01-13", "2025-01-15", "Üst Giyim,Aksesuar", "", "Marmara,Ege", 0.40),
        # 01-13 .. 01-15, her yer; B'den küçük
        ("KAT_C", "kategori", "2025-01-13", "2025-01-15", "", "Basic,NOS", "", 0.25),
        # Black Friday: kapsamı yalnız Dış Giyim, ama gün işareti kapsamdan bağımsız
        ("BF", "black_friday", "2025-01-20", "2025-01-21", "Dış Giyim", "", "", 0.30),
    ])
    ekle(t, "fiyat", [
        ("2025-01-06", "MDL0001-SYH", "normal", 0.30),
        ("2025-01-13", "MDL0001-SYH", "normal", 0.10),
        ("2025-01-06", "MDL0010-SYH", "normal", 0.10),
        ("2025-01-06", "MDL0010-SYH", "outlet", 0.50),
        ("2025-01-06", "MDL0010-SYH", "online", 0.20),
    ])
    con = oyuncak_baglan(t)
    yield con
    con.close()


def _satir(sonuc: pd.DataFrame, tarih: str, magaza: str, urun: str) -> pd.Series:
    t = pd.Timestamp(tarih)
    s = sonuc[(sonuc["tarih"] == t) & (sonuc["magaza_id"] == magaza) & (sonuc["urun_id"] == urun)]
    assert len(s) == 1
    return s.iloc[0]


def test_oran_markdown_ve_kampanyanin_buyugu(oz_con):
    g = _anahtar([("2025-01-08", "M001", S),    # markdown .30 > kampanya .20
                  ("2025-01-14", "M001", S),    # markdown .10 < KAT_B .40 (KAT_C .25 de var)
                  ("2025-01-22", "M001", S)])   # panel satırı yok, kampanya yok
    s = ozellikler.ekle(oz_con, g)
    a, b, c = (s.iloc[i] for i in range(3))
    assert a["markdown_orani"] == pytest.approx(0.30)
    assert a["kampanya_orani"] == pytest.approx(0.20)
    assert a["oran"] == pytest.approx(0.30)
    assert a["kampanya_id"] == "KAT_A"
    assert b["markdown_orani"] == pytest.approx(0.10)
    assert b["kampanya_orani"] == pytest.approx(0.40)
    assert b["oran"] == pytest.approx(0.40)
    assert b["kampanya_id"] == "KAT_B"
    assert (c["markdown_orani"], c["kampanya_orani"], c["oran"]) == (0.0, 0.0, 0.0)
    assert pd.isna(c["kampanya_id"])
    assert ozellikler.etiket_fiyati(s).tolist() == pytest.approx(
        [PANEL * 0.70, PANEL * 0.60, PANEL])


def test_bolgeli_kampanya_online_kapsamaz(oz_con):
    # KAT_B Marmara,Ege (Üst Giyim): M001 Marmara kapsanır, M003 İç Anadolu kapsanmaz,
    # ONL (bolge Marmara, ama online) kapsanmaz; KAT_C bölgesizdir, üçünü de kapsar.
    g = _anahtar([("2025-01-14", "M001", S), ("2025-01-14", "M003", S), ("2025-01-14", "ONL", S)])
    s = ozellikler.ekle(oz_con, g)
    assert s["kampanya_orani"].tolist() == pytest.approx([0.40, 0.25, 0.25])
    assert s["kampanya_id"].tolist() == ["KAT_B", "KAT_C", "KAT_C"]


def test_outlet_hatti_cikistan_sonra(oz_con):
    # OUT: cikis_tarihi 01-12. Hafta pazartesisi 01-06: normal .10, outlet .50, online .20
    g = _anahtar([("2025-01-11", "M002", OUT),   # cikistan önce: normal
                  ("2025-01-12", "M002", OUT),   # cikis günü: outlet
                  ("2025-01-12", "M001", OUT),   # outlet mağazası değil: normal
                  ("2025-01-12", "ONL", OUT)])   # online hattı
    s = ozellikler.ekle(oz_con, g, ["markdown_orani"])
    assert s["markdown_orani"].tolist() == pytest.approx([0.10, 0.50, 0.10, 0.20])


def test_yol_suresi_en_sik_deger():
    t = oyuncak_tablolar()
    ekle(t, "magaza", [("M003", "Ankara", "Ankara", "İç Anadolu", 39.9, 32.8, "Cadde", 300, 1,
                        4000, "2015-01-01", None)])
    # M001: temel senaryoda 4 satır 1 gün; 5 satır 2 gün -> 2
    ekle(t, "sevkiyat", [(f"2025-01-0{i}", f"2025-01-0{i + 2}", "DEPO", "M001", S, 1,
                          "replenishment", None) for i in range(1, 6)])
    # M003: 2 gün x2, 4 gün x2 (beraberlik: küçük olan), varışsız ve mağazadan çıkış sayılmaz
    ekle(t, "sevkiyat", [
        ("2025-01-01", "2025-01-03", "DEPO", "M003", S, 1, "replenishment", None),
        ("2025-01-02", "2025-01-04", "DEPO", "M003", S, 1, "replenishment", None),
        ("2025-01-01", "2025-01-05", "DEPO", "M003", S, 1, "replenishment", None),
        ("2025-01-02", "2025-01-06", "DEPO", "M003", S, 1, "replenishment", None),
        ("2025-01-03", None, "DEPO", "M003", S, 1, "replenishment", None),
        ("2025-01-03", "2025-01-13", "M001", "M003", S, 1, "elle_transfer", None),
    ])
    con = oyuncak_baglan(t)
    yol = ozellikler.yol_suresi(con)
    assert yol["M001"] == 2
    assert yol["M003"] == 2
    assert yol["M002"] == 1          # temel senaryo: ilk dağıtım ve replenishment 1 gün
    assert "ONL" not in yol and "DEPO" not in yol
    assert all(isinstance(v, int) for v in yol.values())
    con.close()


def test_devamli_yas_eksi_bir(oz_con):
    g = _anahtar([("2025-01-08", "M001", DEV), ("2025-01-08", "M001", S)])
    s = ozellikler.ekle(oz_con, g)
    assert s["yas_gun"].tolist() == [-1, 65]      # 2024-11-04 -> 2025-01-08
    # devamlıda sezon tablosunda satır olsa da indirim_baslangici hep False
    assert s["indirim_baslangici"].tolist() == [False, True]


def test_takvim_ve_sezon_bayraklari(oz_con):
    g = _anahtar([("2025-01-01", "M001", S),     # tatil; indirim penceresinden önce
                  ("2025-01-02", "M001", S),     # indirim_baslangic günü
                  ("2025-01-08", "M001", S),     # penceredeki son gün (+6)
                  ("2025-01-09", "M001", S),     # pencere bitti (+7)
                  ("2025-01-12", "M001", OUT),   # AW24 dalga 2: 01-10 .. 01-16
                  ("2025-01-20", "M001", S)])    # Black Friday kapsamı Dış Giyim; Üst Giyim da işaretli
    s = ozellikler.ekle(oz_con, g)
    assert s["tatil"].tolist() == [True, False, False, False, False, False]
    assert s["indirim_baslangici"].tolist() == [False, True, True, False, True, False]
    assert s["black_friday"].tolist() == [False, False, False, False, False, True]
    assert s["hafta_gunu"].tolist() == [2, 3, 2, 3, 6, 0]   # 0 = pazartesi


def test_urun_ve_magaza_ozellikleri(oz_con):
    g = _anahtar([("2025-01-08", "M002", S), ("2025-01-08", "ONL", S), ("2025-01-08", "M001", OUT)])
    s = ozellikler.ekle(oz_con, g)
    assert s["magaza_tipi"].tolist() == ["Outlet", "Online", "AVM"]
    assert s["sehir"].tolist() == ["İzmir", "İstanbul", "İstanbul"]
    assert s["metrekare"].tolist() == [600, 0, 400]
    assert s["kanal"].tolist() == ["magaza", "online", "magaza"]
    assert s["line"].tolist() == ["Basic", "Basic", "Outlet"]
    assert s["ust_kategori"].tolist() == ["Üst Giyim", "Üst Giyim", "Aksesuar"]
    assert s["alt_kategori"].tolist() == ["Gömlek", "Gömlek", "Şapka"]
    assert s["fiyat_segmenti"].tolist() == ["orta"] * 3
    assert s["beden_sira"].tolist() == [2, 2, 3]
    assert s["liste_fiyati"].tolist() == pytest.approx([250.0, 250.0, 100.0])
    assert s["alis_fiyati"].tolist() == pytest.approx([100.0, 100.0, 100.0])


def test_turler_sira_ve_girdi_korunur(oz_con):
    g = _anahtar([("2025-01-14", "M001", S), ("2025-01-08", "ONL", OUT), ("2025-01-08", "M002", S)])
    onceki = g.copy()
    s = ozellikler.ekle(oz_con, g)
    pd.testing.assert_frame_equal(g, onceki)               # girdi değişmez
    assert list(s.columns) == list(g.columns) + ozellikler.OZELLIKLER
    pd.testing.assert_frame_equal(s[list(g.columns)], g)   # sıra ve anahtarlar aynı
    assert s["tatil"].dtype == bool and s["black_friday"].dtype == bool
    assert s["indirim_baslangici"].dtype == bool
    assert s["oran"].dtype == np.float32 and s["markdown_orani"].dtype == np.float32
    assert s["kampanya_orani"].dtype == np.float32
    for kolon in ("line", "ust_kategori", "alt_kategori", "fiyat_segmenti", "magaza_tipi",
                  "sehir", "kanal", "kampanya_id"):
        assert isinstance(s[kolon].dtype, pd.CategoricalDtype), kolon
    assert s["hafta_gunu"].dtype == np.int8 and s["yas_gun"].dtype == np.int16


def test_duz_metin_anahtar_da_olur(oz_con):
    g = _anahtar([("2025-01-14", "M001", S)])
    g["magaza_id"] = g["magaza_id"].astype(str)
    g["urun_id"] = g["urun_id"].astype(str)
    s = ozellikler.ekle(oz_con, g)
    assert s["oran"].iloc[0] == pytest.approx(0.40)


def test_sutun_alt_kumesi(oz_con):
    g = _anahtar([("2025-01-14", "M001", S), ("2025-01-12", "M002", OUT)])
    tam = ozellikler.ekle(oz_con, g)
    # oran, markdown ve kampanyaya bağlıdır: yalnız o istenir, ama sonuç aynıdır
    alt = ozellikler.ekle(oz_con, g, ["oran", "hafta_gunu"])
    assert list(alt.columns) == list(g.columns) + ["hafta_gunu", "oran"]
    pd.testing.assert_series_equal(alt["oran"], tam["oran"])
    pd.testing.assert_series_equal(alt["hafta_gunu"], tam["hafta_gunu"])
    with pytest.raises(ValueError, match="bilinmeyen"):
        ozellikler.ekle(oz_con, g, ["yok_boyle_sutun"])


def test_bilinmeyen_anahtar_hata(oz_con):
    g = _anahtar([("2025-01-14", "M999", S)])
    with pytest.raises(ValueError, match="M999"):
        ozellikler.ekle(oz_con, g)


def test_bos_girdi(oz_con):
    g = _anahtar([("2025-01-14", "M001", S)]).iloc[:0]
    s = ozellikler.ekle(oz_con, g)
    assert len(s) == 0 and list(s.columns) == list(g.columns) + ozellikler.OZELLIKLER


# --------------------------------------------------------------- gerçek veri

@pytest.mark.veri
def test_gercek_v4_ozellikler_bir_ay(v4_con):
    from datetime import date
    g = stok.gunluk_magaza(v4_con, date(2025, 3, 1), date(2025, 3, 31))
    anahtar = g[["tarih", "magaza_id", "urun_id"]]
    s = ozellikler.ekle(v4_con, anahtar)
    assert len(s) == len(g)
    assert not s["oran"].isna().any() and not s["liste_fiyati"].isna().any()
    assert not s["magaza_tipi"].isna().any() and not s["line"].isna().any()
    assert 0.0 <= float(s["oran"].min()) and float(s["oran"].max()) <= 0.70 + 1e-6
    assert (s["oran"] > 0).mean() > 0.05
    assert (s["hafta_gunu"].between(0, 6)).all()
    yol = ozellikler.yol_suresi(v4_con)
    assert len(yol) >= 80 and min(yol.values()) >= 0
