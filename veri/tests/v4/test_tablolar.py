"""Görev 15: yayımlanan tablolar, gizli gerçek, kirli kayıtlar, determinizm.

`t` KÜÇÜK dünyanın (conftest `kucuk_dunya`, `kucuk_kosu`) kirli yayımı,
`temiz` aynı koşunun kirletilmemiş hâli. Determinizm testi
`tablolari_uret(Olcek.KUCUK)` ile bağımsız ikinci bir koşu üretir.
"""

import hashlib

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler
from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.tablolar import YAYIMLANAN_SEVK_TIPLERI, gizli_gercek, hareket_tablolari
from perakende_veri.v4.takvim import gun_indisi
from perakende_veri.v4.uret import tablolari_uret, yayimla

TABLOLAR = {
    "magaza", "magaza_olay", "urun", "paket", "tedarikci", "sezon", "takvim", "kampanya",
    "mfp_plan", "range_plan", "magaza_plan", "siparis", "kalite_kontrol", "satis", "fiyat",
    "stok", "depo_stok", "sevkiyat",
}
BAS = pd.Timestamp(sabitler.BASLANGIC)
SON = pd.Timestamp(sabitler.BITIS)
SON_GUN = gun_indisi(sabitler.BITIS)


@pytest.fixture(scope="module")
def temiz(kucuk_dunya, kucuk_kosu):
    return hareket_tablolari(kucuk_dunya, kucuk_kosu)


@pytest.fixture(scope="module")
def t(kucuk_dunya, kucuk_kosu):
    return yayimla(kucuk_dunya, kucuk_kosu)


@pytest.fixture(scope="module")
def gizli(kucuk_dunya, kucuk_kosu):
    return gizli_gercek(kucuk_dunya, kucuk_kosu)


def _ozet(df: pd.DataFrame) -> str:
    kanonik = df.astype(str)
    kanonik = kanonik.sort_values(list(kanonik.columns)).reset_index(drop=True)
    metin = kanonik.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Küme, gizlilik
# ---------------------------------------------------------------------------


def test_tablo_kumesi(t, temiz):
    assert set(t) == TABLOLAR
    assert set(temiz) == TABLOLAR


YASAK_SUTUNLAR = {
    "segment", "gelir", "iklim", "esneklik", "hatali_orani", "kayip", "kayip_adet",
    "kadin_payi", "genc_egilim", "beden_kayma", "turistik", "yerel_gurultu", "surpriz",
    "maliyet_carpani", "kapasite_sezon_adet", "gecikme_parametre_t", "gecikme_beklenen_gun",
    "ikame", "ikame_adet",
}


def test_gizli_sutun_yok(t):
    for ad, df in t.items():
        sutunlar = set(df.columns)
        assert not (sutunlar & YASAK_SUTUNLAR), (ad, sutunlar & YASAK_SUTUNLAR)
        assert not any("kayip" in s for s in sutunlar), ad
    assert "kayip_satis" not in t and "ikame_satis" not in t


def test_magaza_ve_tedarikci_yalniz_yayimlanan(t, kucuk_dunya):
    assert list(t["magaza"].columns) == list(kucuk_dunya.magazalar.columns)
    assert "ONL" in set(t["magaza"]["magaza_id"])
    assert "kapasite_sezon_adet" not in t["tedarikci"].columns


# ---------------------------------------------------------------------------
# Yabancı anahtarlar
# ---------------------------------------------------------------------------


def _alt(a, b) -> bool:
    return set(pd.Series(a).dropna().astype(str)) <= set(pd.Series(b).astype(str))


def test_yabanci_anahtarlar(t):
    magaza = t["magaza"]["magaza_id"]
    urun = t["urun"]["urun_id"]
    option = t["urun"]["option_id"]
    for ad in ("satis", "stok"):
        assert _alt(t[ad]["magaza_id"], magaza), ad
        assert _alt(t[ad]["urun_id"], urun), ad
    assert _alt(t["depo_stok"]["urun_id"], urun)
    assert _alt(t["satis"]["kampanya_id"], t["kampanya"]["kampanya_id"])
    sv = t["sevkiyat"]
    assert _alt(sv["kaynak"], list(magaza) + ["DEPO"])
    assert _alt(sv["hedef"], list(magaza) + ["DEPO"])
    assert _alt(sv["urun_id"], urun)
    assert _alt(sv["paket_id"], t["paket"]["paket_id"])
    assert sv["paket_id"].notna().any()
    sp = t["siparis"]
    assert _alt(sp["urun_id"], urun) and _alt(sp["option_id"], option)
    assert _alt(sp["tedarikci_id"], t["tedarikci"]["tedarikci_id"])
    assert _alt(t["kalite_kontrol"]["siparis_id"], sp["siparis_id"])
    assert _alt(t["fiyat"]["option_id"], option)
    assert _alt(t["urun"]["tedarikci_id"], t["tedarikci"]["tedarikci_id"])
    assert _alt(t["urun"]["sezon_kodu"], list(t["sezon"]["sezon_kodu"]) + ["DEVAMLI"])
    assert _alt(t["magaza_olay"]["magaza_id"], magaza)
    assert _alt(t["magaza_plan"]["magaza_id"], magaza)
    # siparis: urun → option tutarlı
    u = t["urun"].set_index("urun_id")["option_id"]
    assert (u.loc[sp["urun_id"].astype(str)].to_numpy() == sp["option_id"].astype(str).to_numpy()).all()


# ---------------------------------------------------------------------------
# Pencere
# ---------------------------------------------------------------------------


def _pencerede(s: pd.Series) -> bool:
    s = pd.to_datetime(s)
    return bool(((s >= BAS) & (s <= SON)).all())


def test_pencere(t, kucuk_dunya, kucuk_kosu):
    for ad, sutun in [("satis", "tarih"), ("stok", "tarih"), ("depo_stok", "tarih"),
                      ("sevkiyat", "tarih"), ("fiyat", "hafta_baslangic"),
                      ("kalite_kontrol", "teslim_tarihi")]:
        assert len(t[ad]) > 0, ad
        assert _pencerede(t[ad][sutun]), (ad, sutun)
    sv = t["sevkiyat"]
    v = sv["varis_tarihi"].dropna()
    assert _pencerede(v)
    assert (v >= sv.loc[v.index, "tarih"]).all()

    sp = t["siparis"]
    assert (sp["siparis_tarihi"] <= SON).all()
    g = sp["gerceklesen_teslim"]
    assert _pencerede(g.dropna())
    # pencereden önce verilip pencerede teslim edilen siparişler tutulur
    assert ((sp["siparis_tarihi"] < BAS) & g.notna()).any()
    # teslimi pencere sonrası olan her SKU satırında gerceklesen_teslim boş
    opt = kucuk_dunya.optionlar
    gec = [s for s in kucuk_kosu["siparis"] if s["tip"] != "baslangic" and s["gerceklesen_gun"] > SON_GUN]
    gec_satir = sum(int((np.asarray(s["adetler"]) > 0).sum()) for s in gec)
    assert gec_satir > 0
    assert int(g.isna().sum()) == gec_satir
    # Review Focus 4: AW25 siparişi pencere sonrası teslimse boş
    sezon = t["urun"].drop_duplicates("option_id").set_index("option_id")["sezon_kodu"]
    aw25_gec = {opt.at[s["option"], "option_id"] for s in gec
                if opt.at[s["option"], "sezon_kodu"] == "AW25"}
    if aw25_gec:
        aw = sp[sp["option_id"].astype(str).isin(aw25_gec) & (sp["planlanan_teslim"] > SON)]
        assert aw["gerceklesen_teslim"].isna().any()
    assert set(sezon.loc[sp["option_id"].astype(str).unique()]) >= {"AW25"}
    assert set(sp["tip"]) == {"ilk", "rpt", "surekli"}


def test_sezon_tablosu_aw25_gorunur(t):
    sz = t["sezon"]
    assert len(sz) == 21 and "AW22" in set(sz["sezon_kodu"])
    aw25 = sz[sz["sezon_kodu"] == "AW25"]
    assert len(aw25) == 3
    assert aw25["indirim_baslangic"].notna().all() and aw25["cikis_tarihi"].notna().all()
    assert (aw25["cikis_tarihi"] > SON).all()
    assert (aw25["lansman_tarihi"] <= SON).all()
    assert "AW22" in set(t["urun"]["sezon_kodu"])


# ---------------------------------------------------------------------------
# Hareket tablolarının içeriği
# ---------------------------------------------------------------------------


def test_satis_ham_ile_tutarli(temiz, kucuk_kosu):
    bas = gun_indisi(sabitler.BASLANGIC)
    h = kucuk_kosu["satis"]
    h = h[(h["gun"] >= bas) & (h["gun"] <= SON_GUN)]
    s = temiz["satis"]
    assert len(s) == len(h)
    assert int(s["adet"].sum()) == int(h["adet"].sum())
    assert (s["adet"] < 0).any() and "ONL" in set(s["magaza_id"].astype(str))
    assert "DEPO" not in set(s["magaza_id"].cat.categories)
    assert abs(float(s["tutar"].sum()) - float(h["tutar"].sum())) < 1.0
    assert s["kampanya_id"].isna().any() and s["kampanya_id"].notna().any()
    assert s["tutar"].dtype == np.float64 and s["adet"].dtype == np.int32
    assert list(s.columns) == ["tarih", "magaza_id", "urun_id", "adet", "tutar",
                               "indirim_tutari", "kampanya_id"]


def test_sevkiyat_tipleri(temiz):
    sv = temiz["sevkiyat"]
    assert set(sv["tip"].astype(str)) <= set(YAYIMLANAN_SEVK_TIPLERI)
    assert "baslangic" not in set(sv["tip"].astype(str))
    assert {"ilk_dagitim", "replenishment", "elle_transfer"} <= set(sv["tip"].astype(str))
    depo = sv["kaynak"].astype(str) == "DEPO"
    assert depo.any() and (~depo).any()
    assert list(sv.columns) == ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet",
                                "tip", "paket_id"]
    ilk = sv["tip"].astype(str) == "ilk_dagitim"
    assert sv.loc[ilk, "paket_id"].notna().all()
    assert sv.loc[~ilk, "paket_id"].isna().all()


def test_fiyat_paneli(temiz):
    f = temiz["fiyat"]
    assert set(f["hat"].astype(str)) == {"normal", "outlet", "online"}
    assert (pd.to_datetime(f["hafta_baslangic"]).dt.dayofweek == 0).all()
    assert not f.duplicated(["hafta_baslangic", "option_id", "hat"]).any()
    assert f["indirim_orani"].between(0, 1).all()
    assert (f["indirim_orani"] > 0).any()


def test_stok_haftalik(temiz):
    s = temiz["stok"]
    assert (pd.to_datetime(s["tarih"]).dt.dayofweek == 0).all()
    assert s["stoklu_gun"].between(0, 7).all()
    assert "ONL" not in set(s["magaza_id"].astype(str))


# ---------------------------------------------------------------------------
# Kirli kayıtlar
# ---------------------------------------------------------------------------


def test_kirli_sayilar(t, temiz, kucuk_dunya):
    # mükerrer satış
    assert len(t["satis"]) - len(temiz["satis"]) == sabitler.MUKERRER_KAYIT
    # bedelsiz satış (temizde yok)
    bedelsiz = lambda s: int(((s["adet"] > 0) & (s["tutar"] == 0) & (s["indirim_tutari"] == 0)).sum())  # noqa: E731
    assert bedelsiz(temiz["satis"]) == 0
    assert bedelsiz(t["satis"]) == sabitler.BEDELSIZ_KAYIT
    # hayalet stok: mağaza o SKU'yu hiç taşımıyor, pazartesi, stoklu_gun 7
    assert len(t["stok"]) - len(temiz["stok"]) == sabitler.HAYALET_STOK_KAYDI
    w = kucuk_dunya
    tasinan = set(zip(w.magazalar["magaza_id"].to_numpy()[w.hucre_magaza],
                      w.urunler["urun_id"].to_numpy()[w.hucre_sku]))
    st = t["stok"]
    anahtar = list(zip(st["magaza_id"].astype(str), st["urun_id"].astype(str)))
    hayalet = st[[k not in tasinan for k in anahtar]]
    assert len(hayalet) == sabitler.HAYALET_STOK_KAYDI
    assert (hayalet["stoklu_gun"] == 7).all()
    assert (pd.to_datetime(hayalet["tarih"]).dt.dayofweek == 0).all()
    # tek taraflı transfer: elle_transfer satırlarında varış boş
    bos = lambda s: int(((s["tip"].astype(str) == "elle_transfer") & s["varis_tarihi"].isna()).sum())  # noqa: E731
    assert bos(t["sevkiyat"]) - bos(temiz["sevkiyat"]) == sabitler.TEK_TARAFLI_TRANSFER
    assert len(t["sevkiyat"]) == len(temiz["sevkiyat"])
    # diğer tablolar kirlenmez
    for ad in TABLOLAR - {"satis", "stok", "sevkiyat"}:
        assert _ozet(t[ad]) == _ozet(temiz[ad]), ad


def test_kirli_dtype_korunur(t, temiz):
    for ad in ("satis", "stok", "sevkiyat"):
        assert dict(t[ad].dtypes) == dict(temiz[ad].dtypes), ad


# ---------------------------------------------------------------------------
# Gizli gerçek
# ---------------------------------------------------------------------------


def test_gizli_gercek(gizli, kucuk_dunya, kucuk_kosu):
    assert {"kayip_satis", "ikame_satis", "segment", "esneklik", "oznitelik_etkisi",
            "trend_tablosu", "tedarikci_profili"} <= set(gizli)
    k = gizli["kayip_satis"]
    assert list(k.columns) == ["tarih", "magaza_id", "urun_id", "kayip_adet"]
    bas = gun_indisi(sabitler.BASLANGIC)
    h = kucuk_kosu["gizli_kayip"]
    h = h[(h["gun"] >= bas) & (h["gun"] <= SON_GUN)]
    assert int(k["kayip_adet"].sum()) == int(h["adet"].sum())
    assert _pencerede(k["tarih"]) and _pencerede(gizli["ikame_satis"]["tarih"])
    assert {"segment", "iklim", "gelir"} <= set(gizli["segment"].columns)
    e = gizli["esneklik"]
    w = kucuk_dunya
    ciftler = set(zip(w.hucre_magaza.tolist(), w.hucre_option.tolist()))
    assert len(e) == len(ciftler)
    assert list(e.columns) == ["magaza_id", "option_id", "esneklik"]
    assert "kapasite_sezon_adet" in gizli["tedarikci_profili"].columns


# ---------------------------------------------------------------------------
# Determinizm
# ---------------------------------------------------------------------------


def test_determinizm_kucuk(t):
    ikinci = tablolari_uret(Olcek.KUCUK)
    assert set(ikinci) == set(t)
    for ad in t:
        assert len(ikinci[ad]) == len(t[ad]), ad
        assert _ozet(ikinci[ad]) == _ozet(t[ad]), ad
