"""`beden_paket.kaynak`: bağlantı, tablo okuma, kapsam (Kümeleme ile aynı), beş bedenli SKU'lar.

Oyuncak testleri `conftest`in 8 mağazalı fikstürünü kullanır; `veri` işaretli testler
yayımlanan v4 verisini (`veri/cikti/v4/perakende.duckdb`) ister.
"""

import pandas as pd
import pytest
from conftest import KARAR, LANSMAN, PROFIL, STANDART_PAKET, YENI, oyuncak_baglan
from kumeleme import kaynak as kumeleme_kaynak

from beden_paket import kaynak, sabitler

SUTUNLAR = ["magaza_id", "ad", "sehir", "bolge", "istanbul", "tip", "metrekare", "enlem",
            "gecmis_hafta", "yeni"]


def _kumeleme_kapsam(t, karar=KARAR):
    return kumeleme_kaynak.kapsam(t["magaza"], t["magaza_olay"], t["satis"], karar)


# ------------------------------------------------------------------ kapsam


def test_kapsam_oyuncak(tablolar):
    k = kaynak.kapsam(tablolar, KARAR)
    assert list(k.columns) == SUTUNLAR
    assert list(k["magaza_id"]) == list(PROFIL)                    # 8 aday, magaza sırası
    s = k.set_index("magaza_id")
    assert list(s.index[s["istanbul"]]) == ["S01", "S02"]
    assert list(s.index[s["yeni"]]) == [YENI]
    assert s.loc[YENI, "gecmis_hafta"] == 9                        # 2024-12-02 … 2025-01-27 haftaları
    assert (s.drop(YENI)["gecmis_hafta"] >= 26).all()
    assert s["yeni"].dtype == bool and s["istanbul"].dtype == bool
    assert s["metrekare"].dtype.kind == "i" and s["enlem"].dtype.kind == "f"
    assert s.loc["S06", ["sehir", "bolge", "tip"]].tolist() == ["Erzurum", "Doğu Anadolu", "AVM"]


def test_kapsam_kumeleme_ile_ayni_oyuncak(tablolar):
    """Sarmalayıcı yalnız sütun seçer ve yeniden adlandırmaz: değerler Kümeleme'ninkiyle aynı."""
    k = kaynak.kapsam(tablolar, KARAR)
    km = _kumeleme_kapsam(tablolar)
    pd.testing.assert_frame_equal(k, km[SUTUNLAR])
    assert (k["yeni"] == km["yeni"]).all() and (k["yeni"] == ~km["kumelenir"]).all()


def test_kapsam_karar_sonrasini_gormez(tablolar):
    """Karar gününden sonraki satışı bozmak kapsamı değiştirmez."""
    temel = kaynak.kapsam(tablolar, KARAR)
    bozuk = dict(tablolar)
    s = tablolar["satis"].copy()
    s.loc[s["tarih"] >= KARAR, "adet"] = 1000
    bozuk["satis"] = s
    pd.testing.assert_frame_equal(kaynak.kapsam(bozuk, KARAR), temel)
    assert (tablolar["satis"]["tarih"] >= LANSMAN).any()           # fikstür gerçekten karar sonrası taşıyor


def test_kapsam_eksik_tablo(tablolar):
    with pytest.raises(KeyError):
        kaynak.kapsam({"magaza": tablolar["magaza"]}, KARAR)


@pytest.mark.veri
def test_kapsam_kumeleme_ile_ayni():
    """Gerçek veride 69 aday; Kümeleme kapsamıyla aynı mağazalar, aynı sıra, aynı değerler."""
    con = kaynak.baglan()
    try:
        t = kaynak.kapsam_tablolari(con, sabitler.KARAR_GUNU)
    finally:
        con.close()
    k = kaynak.kapsam(t, sabitler.KARAR_GUNU)
    km = _kumeleme_kapsam(t, sabitler.KARAR_GUNU)
    assert len(k) == 69 and len(km) == 69
    assert list(k["magaza_id"]) == list(km["magaza_id"])
    pd.testing.assert_frame_equal(k, km[SUTUNLAR])
    assert set(k.loc[k["yeni"], "magaza_id"]) == {"M027", "M041"}
    assert int(k["istanbul"].sum()) > 0
    assert set(k["tip"]) <= {"AVM", "Cadde"}


# ------------------------------------------------------------------ beş bedenli


def test_bes_bedenli(tablolar):
    u = tablolar["urun"]
    b = kaynak.bes_bedenli(u)
    assert len(u) == 26 and len(b) == 25
    assert "OPT-NOS-STD-STD" not in set(b["urun_id"])              # aksesuar / tek beden hariç
    assert set(b["beden_seti"]) == {"Kadın Harf", "Kadın Numara"}
    assert set(b["beden_sira"]) == {1, 2, 3, 4, 5} and b["beden_sira"].dtype == "int64"
    assert b.groupby("option_id")["beden_sira"].apply(lambda s: sorted(s) == [1, 2, 3, 4, 5]).all()
    assert list(b["urun_id"]) == [x for x in u["urun_id"] if x != "OPT-NOS-STD-STD"]    # sıra korunur
    assert list(b.columns) == list(u.columns)


def test_bes_bedenli_tek_bedenli_set_ve_aksesuar(tablolar):
    """Beş bedenli bir set bile aksesuar kategorisindeyse dışarıda; eksik sıralı set dışarıda."""
    u = tablolar["urun"].copy()
    u.loc[u["option_id"] == "OPT-BAS", "ust_kategori"] = "Aksesuar"
    assert "OPT-BAS" not in set(kaynak.bes_bedenli(u)["option_id"])
    u = tablolar["urun"].copy()
    u = u[~((u["beden_seti"] == "Kadın Numara") & (u["beden_sira"] == 5))]    # set 4 bedenli kaldı
    assert "Kadın Numara" not in set(kaynak.bes_bedenli(u)["beden_seti"])


def test_bes_bedenli_eksik_sutun(tablolar):
    with pytest.raises(KeyError):
        kaynak.bes_bedenli(tablolar["urun"].drop(columns=["beden_sira"]))


@pytest.mark.veri
def test_bes_bedenli_gercek_veri():
    con = kaynak.baglan()
    try:
        u = kaynak.yayimlanan_tablolar(con, ("urun",))["urun"]
    finally:
        con.close()
    b = kaynak.bes_bedenli(u)
    assert set(b["beden_sira"]) == {1, 2, 3, 4, 5}
    assert len(b) == len(u) - int((u["beden_seti"] == "Standart").sum())
    assert not (b["ust_kategori"] == "Aksesuar").any() and not (b["beden_seti"] == "Standart").any()
    assert set(b["line"]) == {"Collection", "Basic", "NOS", "Outlet"}     # NOS'un giyimi beş bedenli
    assert len(b) == len(u) - int((u["ust_kategori"] == "Aksesuar").sum())     # aksesuar = tek beden


# ------------------------------------------------------------------ okuma


def test_yayimlanan_tablolar_ad_sirasi_ve_icerik(tablolar):
    con = oyuncak_baglan(tablolar)
    t = kaynak.yayimlanan_tablolar(con, ("urun", "magaza", "paket"))
    assert list(t) == ["urun", "magaza", "paket"]
    assert len(t["magaza"]) == 8 and len(t["urun"]) == 26
    p = t["paket"][t["paket"]["beden_seti"] == "Kadın Harf"].sort_values("beden_sira")
    assert tuple(p["adet"]) == STANDART_PAKET == sabitler.LUMODA_PAKET
    assert int(p["adet"].sum()) == sabitler.PAKET_ADET
    con.close()


@pytest.mark.parametrize("ad", ["magaza; drop table x", "Magaza", "magaza-1", ""])
def test_yayimlanan_tablolar_gecersiz_ad(tablolar, ad):
    con = oyuncak_baglan(tablolar)
    with pytest.raises(ValueError):
        kaynak.yayimlanan_tablolar(con, (ad,))
    con.close()


def test_gizli_tablo_reddedilir(tablolar, gizli):
    con = oyuncak_baglan(tablolar)
    con.register("_g", gizli)
    con.execute("create table gizli_magaza as select * from _g")
    for ad in ("gizli_magaza", "gizli_talep"):
        with pytest.raises(ValueError, match="gizli"):
            kaynak.yayimlanan_tablolar(con, ("magaza", ad))
    con.close()


def test_baglan_olmayan_dosya(tmp_path):
    with pytest.raises(FileNotFoundError):
        kaynak.baglan(tmp_path / "yok.duckdb")


def test_fikstur_gizli_kaymayi_tabloda_tasimaz(tablolar, gizli):
    """Gizli kayma yalnız `gizli` fikstüründe; yayımlanan tablolarda kayma ya da profil sütunu yok."""
    assert list(gizli.columns) == ["magaza_id", "beden_kayma"]
    assert set(gizli["beden_kayma"]) == {-1.0, 0.0, 1.0}           # üç kayma profili
    for ad, df in tablolar.items():
        assert not [c for c in df.columns if "kayma" in c or "profil" in c or "gizli" in c], ad
