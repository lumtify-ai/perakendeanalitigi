import numpy as np
import pytest

from perakende_veri import sabitler as v2_sabitler
from perakende_veri.v3 import sabitler
from perakende_veri.v3.tedarik import (
    en_buyuk_kalan, moq_yuvarla, tedarikcileri_uret, teslim_sapmasi,
)
from perakende_veri.v3.urun import urunleri_uret


@pytest.fixture(scope="module")
def tedarikciler():
    return tedarikcileri_uret(np.random.default_rng(1))


@pytest.fixture(scope="module")
def urunler(tedarikciler):
    return urunleri_uret(np.random.default_rng(2), tedarikciler)


# --- Tedarikçi ----------------------------------------------------------

def test_sekiz_tedarikci(tedarikciler):
    assert len(tedarikciler) == 8
    assert list(tedarikciler.columns) == [
        "tedarikci_id", "ad", "ulke", "mense", "ilk_siparis_hafta", "rpt_hafta", "moq_option",
    ]
    yerli = tedarikciler[tedarikciler.mense == "Yerli"]
    uzak = tedarikciler[tedarikciler.mense == "Uzak Doğu"]
    assert list(yerli["ad"]) == v2_sabitler.URETICILER
    assert set(uzak["ulke"]) == {"Çin", "Bangladeş", "Vietnam"}


def test_tedarik_sureleri_araliklarda(tedarikciler):
    for mense, m in sabitler.MENSE.items():
        t = tedarikciler[tedarikciler.mense == mense]
        assert t["ilk_siparis_hafta"].between(*m["ilk"]).all()
        assert t["rpt_hafta"].between(*m["rpt"]).all()
        assert (t["moq_option"] == m["moq"]).all()


def test_teslim_sapmasi():
    rng = np.random.default_rng(0)
    y = teslim_sapmasi(rng, "Yerli", 5000)
    u = teslim_sapmasi(rng, "Uzak Doğu", 5000)
    assert y.min() == -3 and y.max() == 3
    assert u.min() >= 0 and u.max() <= 21
    assert np.median(u) < 10.5          # sağa çarpık: çoğu az gecikir


def test_moq_alt_sinirdir_kat_degil():
    assert moq_yuvarla(100, 300) == 300
    assert moq_yuvarla(700, 300) == 700
    assert moq_yuvarla(701, 300) == 710
    assert moq_yuvarla(650.0, 600) == 650


def test_en_buyuk_kalan():
    a = en_buyuk_kalan(10, np.array([0.1, 0.22, 0.32, 0.24, 0.12]))
    assert a.sum() == 10 and (a >= 0).all()
    assert list(a) == list(en_buyuk_kalan(10, np.array([0.1, 0.22, 0.32, 0.24, 0.12])))
    assert en_buyuk_kalan(0, np.ones(3)).sum() == 0
    assert list(en_buyuk_kalan(2, np.ones(3))) == [1, 1, 0]   # eşitlikte küçük indis


# --- Ürün ---------------------------------------------------------------

def test_urun_kolonlari(urunler):
    assert "uretici" not in urunler.columns
    for kolon in ("sezon_kodu", "dalga", "lansman_tarihi", "cikis_tarihi", "tedarikci_id"):
        assert kolon in urunler.columns


def test_242_model(urunler):
    modeller = urunler.drop_duplicates("model_kodu")
    assert len(modeller) == 242
    assert modeller["model_kodu"].iloc[0] == "MDL001"
    assert modeller["model_kodu"].iloc[-1] == "MDL242"
    sayim = modeller.groupby("line").size()
    assert sayim["Basic"] == 22 and sayim["NOS"] == 10
    assert sayim["Collection"] == 180 and sayim["Outlet"] == 30
    sezonluk = modeller[modeller.sezon_kodu != "DEVAMLI"]
    per_sezon = sezonluk.groupby(["sezon_kodu", "line"]).size().unstack()
    assert (per_sezon["Collection"] == 36).all() and (per_sezon["Outlet"] == 6).all()
    assert (sezonluk[sezonluk.line == "Collection"].groupby(["sezon_kodu", "dalga"]).size() == 12).all()


def test_renk_sayilari(urunler):
    renk = urunler.groupby(["model_kodu", "line"])["renk"].nunique().reset_index()
    assert (renk[renk.line == "Basic"]["renk"] == 3).all()
    assert (renk[renk.line == "NOS"]["renk"] == 2).all()
    sezonluk = renk[renk.line.isin(["Collection", "Outlet"])]["renk"]
    assert sezonluk.between(2, 4).all()
    assert set(urunler["renk_kodu"]) <= set(sabitler.RENKLER.values())


def test_kimlik_bicimi(urunler):
    r = urunler.iloc[0]
    assert r["urun_id"] == f"{r['option_id']}-{r['beden']}"
    assert r["option_id"] == f"{r['model_kodu']}-{r['renk_kodu']}"
    assert urunler["urun_id"].is_unique


def test_devamli_ve_sezonluk_tarihleri(urunler):
    devamli = urunler[urunler.sezon_kodu == "DEVAMLI"]
    assert devamli["line"].isin(["Basic", "NOS"]).all()
    assert devamli["dalga"].isna().all() and devamli["cikis_tarihi"].isna().all()
    sezonluk = urunler[urunler.sezon_kodu != "DEVAMLI"]
    for kod, s in sabitler.SEZONLAR.items():
        u = sezonluk[sezonluk.sezon_kodu == kod]
        for dalga, tarih in enumerate(s["dalgalar"], start=1):
            assert (u.loc[u.dalga == dalga, "lansman_tarihi"] == str(tarih)).all()
        assert (u["cikis_tarihi"] == str(s["cikis"])).all()


def test_mevsime_gore_kategori(urunler):
    m = urunler.drop_duplicates("model_kodu")
    aw = m[m.sezon_kodu.str.startswith("AW")]
    ss = m[m.sezon_kodu.str.startswith("SS")]
    assert (aw["alt_kategori"] == "Şort").sum() == 0
    assert (aw["ust_kategori"] == "Dış Giyim").mean() > (ss["ust_kategori"] == "Dış Giyim").mean()


def test_tedarikci_atamasi(urunler, tedarikciler):
    assert urunler["tedarikci_id"].isin(tedarikciler["tedarikci_id"]).all()
    m = urunler.drop_duplicates("model_kodu").merge(tedarikciler, on="tedarikci_id")
    coll = m[m.line == "Collection"]
    assert 0.25 < (coll["mense"] == "Uzak Doğu").mean() < 0.55
    # Tişört / gömlek / etek / şort ağırlıklı yerli
    hafif = coll[coll.alt_kategori.isin(["Tişört", "Gömlek", "Etek", "Şort"])]
    assert (hafif["mense"] == "Yerli").mean() > 0.6
