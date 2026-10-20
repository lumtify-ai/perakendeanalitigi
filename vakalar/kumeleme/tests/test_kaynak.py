"""`kumeleme.kaynak`: bağlantı, tablo okuma, kapsam, şehir → iklim tablosu.

Oyuncak testleri `conftest`in 12 mağazalı fikstürünü kullanır; `veri` işaretli testler
yayımlanan v4 verisini (`veri/cikti/v4/perakende.duckdb`) ister.
"""

import pandas as pd
import pytest
from conftest import KARAR, LANSMAN, doldur, oyuncak_baglan

from kumeleme import kaynak, sabitler

SUTUNLAR = ["magaza_id", "ad", "sehir", "bolge", "tip", "metrekare", "enlem", "istanbul",
            "metropol", "gecmis_hafta", "kumelenir", "yeni"]


def _kapsam(t, **kw):
    return kaynak.kapsam(t["magaza"], t["magaza_olay"], t["satis"], KARAR, **kw)


def _ekle_magaza(t, magaza_id, acilis, kapanis=None, tip="AVM"):
    """Fikstüre bir mağaza ekler (satışsız)."""
    yeni = doldur("magaza", [(magaza_id, magaza_id, "Bursa", "Marmara", 40.0, 29.0, tip, 500, 1,
                              5000, acilis, kapanis)])
    t["magaza"] = pd.concat([t["magaza"], yeni], ignore_index=True)


def _olay(t, magaza_id, olay, karar, tarih):
    t["magaza_olay"] = pd.concat(
        [t["magaza_olay"], doldur("magaza_olay", [(magaza_id, olay, karar, tarih, None)])],
        ignore_index=True)


# ------------------------------------------------------------------ kapsam


def test_kapsam_karar_gununde_acik(tablolar):
    k = _kapsam(tablolar)
    assert list(k.columns) == SUTUNLAR
    assert list(k["magaza_id"]) == [f"M0{i}" for i in range(1, 10)]     # M10 kapalı, M11/ONL dışarıda
    s = k.set_index("magaza_id")
    assert s.loc["M01", "istanbul"] and s.loc["M02", "istanbul"] and not s.loc["M03", "istanbul"]
    assert list(s.index[s["metropol"]]) == ["M01", "M02", "M03", "M04"]
    assert s.loc["M08", ["sehir", "bolge", "tip"]].tolist() == ["Bodrum", "Ege", "AVM"]
    assert s["metrekare"].dtype.kind == "i" and s["enlem"].dtype.kind == "f"
    assert s["kumelenir"].dtype == bool and s["yeni"].dtype == bool
    assert set(s["bolge"]) == {"Marmara", "İç Anadolu", "Ege"}


def test_kapsam_acilacak_ve_kapanacak(tablolar):
    """Karar gününde kapalı ama lansmana dek açılan aday; kapanış kararı verilmiş ya da
    lansmana dek kapanan aday değil (İlk Sevkiyat `aday_maskesi`)."""
    t = tablolar
    _ekle_magaza(t, "A_LANSMAN", LANSMAN)                          # lansman günü açılıyor: aday
    _ekle_magaza(t, "A_SONRA", LANSMAN + pd.Timedelta(days=1))     # lansmandan sonra: değil
    _ekle_magaza(t, "K_KARAR", "2016-01-04", "2025-06-30")         # kapanış kararı verilmiş: değil
    _olay(t, "K_KARAR", "kapanis", "2025-01-15", "2025-06-30")
    _ekle_magaza(t, "K_SONRA", "2016-01-04", "2025-06-30")         # karar karar gününden sonra: aday
    _olay(t, "K_SONRA", "kapanis", "2025-03-01", "2025-06-30")
    _ekle_magaza(t, "K_LANSMAN", "2016-01-04", "2025-02-09")       # lansmandan önce kapanıyor: değil
    _ekle_magaza(t, "K_LANSMAN2", "2016-01-04", "2025-02-10")      # lansman günü kapanıyor: değil
    _ekle_magaza(t, "K_ILERI", "2016-01-04", "2025-02-11")         # lansmandan sonra kapanıyor: aday
    k = _kapsam(t).set_index("magaza_id")
    assert {"A_LANSMAN", "K_SONRA", "K_ILERI"} <= set(k.index)
    assert not {"A_SONRA", "K_KARAR", "K_LANSMAN", "K_LANSMAN2"} & set(k.index)
    assert k.loc["A_LANSMAN", "gecmis_hafta"] == 0 and k.loc["A_LANSMAN", "yeni"]


def test_kapsam_lansman_varsayilani_ilk_pazartesi(tablolar):
    assert kaynak.lansman_gunu(KARAR) == LANSMAN
    assert kaynak.lansman_gunu(pd.Timestamp("2025-02-10")) == pd.Timestamp("2025-02-17")
    t = tablolar
    _ekle_magaza(t, "A_GEC", pd.Timestamp("2025-02-12"))
    assert "A_GEC" not in set(_kapsam(t)["magaza_id"])
    assert "A_GEC" in set(_kapsam(t, lansman=pd.Timestamp("2025-02-14"))["magaza_id"])


def test_outlet_ve_online_disarida(tablolar):
    k = _kapsam(tablolar)
    assert not {"M11", "ONL"} & set(k["magaza_id"])
    assert set(k["tip"]) == {"AVM", "Cadde"}
    # ikisinin de satışı var: kapsam dışı olmaları satışsızlıktan değil, tipten
    satis = tablolar["satis"]
    assert {"M11", "ONL"} <= set(satis["magaza_id"].astype(str))


def test_yeni_magaza_esik(tablolar):
    k = _kapsam(tablolar).set_index("magaza_id")
    assert k.loc["M09", "gecmis_hafta"] == 10                       # 2024-11-25 … 2025-01-27 haftaları
    assert k.loc["M09", "yeni"] and not k.loc["M09", "kumelenir"]
    eski = k.drop("M09")
    assert (eski["gecmis_hafta"] >= sabitler.GECMIS_HAFTA_ESIGI).all()
    assert eski["kumelenir"].all() and not eski["yeni"].any()
    assert (k["yeni"] == ~k["kumelenir"]).all()


def test_gecmis_hafta_tanimi(tablolar):
    """Karar gününe dek tamamlanmış (pazartesi-pazar) ve brüt satışlı hafta sayısı."""
    t = tablolar
    for ad, n in (("E25", 25), ("E26", 26), ("E27", 27)):
        _ekle_magaza(t, ad, "2024-01-01")
        bas = pd.Timestamp("2025-01-27") - pd.Timedelta(weeks=n - 1)   # son tam hafta: 01-27
        t["satis"] = pd.concat([t["satis"], doldur("satis", [
            (d, ad, "SKU-AW24", 1, 100.0, 0.0, None) for d in pd.date_range(bas, periods=n, freq="7D")])],
            ignore_index=True)
    # aynı haftada birden çok gün tek hafta; iade ve karar günü sonrası sayılmaz; kesintili hafta atlanır
    _ekle_magaza(t, "OZEL", "2024-01-01")
    t["satis"] = pd.concat([t["satis"], doldur("satis", [
        ("2025-01-27", "OZEL", "SKU-AW24", 1, 100.0, 0.0, None),
        ("2025-01-29", "OZEL", "SKU-AW24", 2, 200.0, 0.0, None),    # aynı hafta
        ("2025-01-20", "OZEL", "SKU-AW24", -1, -100.0, 0.0, None),  # yalnız iade: hafta sayılmaz
        ("2025-01-06", "OZEL", "SKU-AW24", 1, 100.0, 0.0, None),    # 01-13 haftası boş
        ("2025-02-04", "OZEL", "SKU-AW24", 1, 100.0, 0.0, None),    # karar haftası: tamamlanmadı
        ("2025-02-10", "OZEL", "SKU-AW24", 1, 100.0, 0.0, None),    # karar sonrası
    ])], ignore_index=True)
    k = _kapsam(t).set_index("magaza_id")
    assert [k.loc[a, "gecmis_hafta"] for a in ("E25", "E26", "E27")] == [25, 26, 27]
    assert [k.loc[a, "kumelenir"] for a in ("E25", "E26", "E27")] == [False, True, True]
    assert k.loc["OZEL", "gecmis_hafta"] == 2


def test_kapsam_karar_sonrasini_gormez(tablolar):
    """Karar gününden sonraki satışı bozmak kapsamı değiştirmez."""
    t = tablolar
    temel = _kapsam(t)
    bozuk = dict(t)
    s = t["satis"].copy()
    s.loc[s["tarih"] >= KARAR, "adet"] = 1000
    bozuk["satis"] = pd.concat([s, doldur("satis", [
        ("2025-03-03", "M09", "SKU-AW24", 5, 500.0, 0.0, None)])], ignore_index=True)
    pd.testing.assert_frame_equal(_kapsam(bozuk), temel)


def test_kapsam_kategorik_magaza_kimligi(tablolar):
    """Gerçek `satis` kimlikleri `category` gelir."""
    t = dict(tablolar)
    s = t["satis"].copy()
    s["magaza_id"] = s["magaza_id"].astype("category")
    t["satis"] = s
    pd.testing.assert_frame_equal(_kapsam(t), _kapsam(tablolar))


def test_kapsam_eksik_sutun(tablolar):
    with pytest.raises(KeyError):
        kaynak.kapsam(tablolar["magaza"], tablolar["magaza_olay"],
                      tablolar["satis"][["tarih", "magaza_id"]], KARAR)


# ------------------------------------------------------------------ şehir → iklim


SINIFLAR = {"soguk", "sicak_sahil", "ılıman", "karasal"}


def test_sehir_iklim_tablosu_bicimi():
    assert set(kaynak.SEHIR_IKLIM.values()) == SINIFLAR          # dört sınıf da kullanılıyor
    assert kaynak.TURISTIK <= set(kaynak.SEHIR_IKLIM)
    assert kaynak.METROPOL == {"İstanbul", "Ankara", "İzmir"}
    assert {kaynak.SEHIR_IKLIM[s] for s in ("Erzurum", "Kars", "Van", "Sivas")} == {"soguk"}
    assert all(kaynak.SEHIR_IKLIM[s] == "sicak_sahil" for s in kaynak.TURISTIK)


def test_sehir_iklim_oyuncak_sehirleri(tablolar):
    assert set(tablolar["magaza"]["sehir"].astype(str)) <= set(kaynak.SEHIR_IKLIM)


@pytest.mark.veri
def test_sehir_iklim_butun_sehirler():
    con = kaynak.baglan()
    try:
        sehirler = set(con.execute("select distinct sehir from magaza").df()["sehir"])
    finally:
        con.close()
    assert len(sehirler) == 26
    assert sehirler <= set(kaynak.SEHIR_IKLIM), sehirler - set(kaynak.SEHIR_IKLIM)


# ------------------------------------------------------------------ okuma


def test_yayimlanan_tablolar_ad_sirasi_ve_icerik(tablolar):
    con = oyuncak_baglan(tablolar)
    t = kaynak.yayimlanan_tablolar(con, ("urun", "magaza"))
    assert list(t) == ["urun", "magaza"]
    assert len(t["magaza"]) == 12 and len(t["urun"]) == 2
    con.close()


@pytest.mark.parametrize("ad", ["magaza; drop table x", "Magaza", "magaza-1", ""])
def test_yayimlanan_tablolar_gecersiz_ad(tablolar, ad):
    con = oyuncak_baglan(tablolar)
    with pytest.raises(ValueError):
        kaynak.yayimlanan_tablolar(con, (ad,))
    con.close()


def test_yayimlanan_tablolar_gizli_tabloyu_reddeder(tablolar):
    con = oyuncak_baglan(tablolar)
    con.execute("create table gizli_magaza as select 'M01' as magaza_id, 'x' as segment")
    for ad in ("gizli_magaza", "gizli_talep"):
        with pytest.raises(ValueError, match="gizli"):
            kaynak.yayimlanan_tablolar(con, ("magaza", ad))
    con.close()


def test_baglan_olmayan_dosya(tmp_path):
    with pytest.raises(FileNotFoundError):
        kaynak.baglan(tmp_path / "yok.duckdb")


# ------------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_kapsam_ss25():
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con, ("magaza", "magaza_olay"))
        # kapsam yalnız (tarih, magaza_id, adet) okur; 18 milyon satırı bellekte tutmamak için indirgenir
        satis = con.execute(
            "select distinct tarih::date::timestamp as tarih, magaza_id::varchar as magaza_id, "
            "1 as adet from satis where adet > 0 and tarih < ?", [sabitler.KARAR_GUNU]).df()
    finally:
        con.close()
    k = kaynak.kapsam(t["magaza"], t["magaza_olay"], satis, sabitler.KARAR_GUNU)
    assert len(k) == 69
    assert int(k["kumelenir"].sum()) == 67
    assert set(k.loc[k["yeni"], "magaza_id"]) == {"M027", "M041"}
    s = k.set_index("magaza_id")
    assert s.loc["M041", "gecmis_hafta"] == 19 and s.loc["M027", "gecmis_hafta"] == 0
    assert set(k["tip"]) <= {"AVM", "Cadde"}
    assert not {"M004", "M005", "M006", "M077", "M044"} & set(k["magaza_id"])    # kapanmış / sonradan açılan
    assert int(k["istanbul"].sum()) > 0 and int(k["metropol"].sum()) > int(k["istanbul"].sum())
