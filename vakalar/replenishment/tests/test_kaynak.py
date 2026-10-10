"""`replenishment.kaynak`: yayımlanan v4'ten okuma, hücre haritası.

Oyuncak testleri `conftest.oyuncak_tablolar`ın (elle izlenebilir) bellek içi
DuckDB'sini kullanır; `veri` işaretli testler gerçek v4 dosyasını."""

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from conftest import gun, oyuncak_baglan, oyuncak_tablolar
from perakende_analitik import stok

from replenishment import kaynak, sabitler

BAS, BIT = gun(0), gun(13)
# Oyuncak "dünya"sı: hücre sırası (mağaza, ürün) = anahtar sırası
HUCRELER = [("M1", "A-S"), ("M1", "A-M"), ("M2", "A-S"), ("M2", "A-M"), ("ONL", "A-S"), ("ONL", "A-M")]


def _dunya():
    magazalar = pd.DataFrame({"magaza_id": ["M1", "M2", "M3", "ONL"]})
    urunler = pd.DataFrame({"urun_id": ["A-S", "A-M"]})
    return SimpleNamespace(
        magazalar=magazalar, urunler=urunler,
        hucre_magaza=np.array([magazalar["magaza_id"].tolist().index(m) for m, _ in HUCRELER]),
        hucre_sku=np.array([urunler["urun_id"].tolist().index(u) for _, u in HUCRELER]))


def _sutun(matris, m, u):
    return matris[:, HUCRELER.index((m, u))]


# ---------------------------------------------------------------- mağazalar


def test_fiziksel_magazalar_online_haric(oyuncak_con):
    df = kaynak.fiziksel_magazalar(oyuncak_con)
    assert list(df.columns) == ["magaza_id", "ad", "sehir", "bolge", "istanbul"]
    assert df["magaza_id"].tolist() == ["M1", "M2", "M3"]
    assert "ONL" not in set(df["magaza_id"])


def test_istanbul_ali_digerleri_veli(oyuncak_con):
    df = kaynak.fiziksel_magazalar(oyuncak_con).set_index("magaza_id")
    assert df["istanbul"].dtype == bool
    assert bool(df.loc["M1", "istanbul"]) is True      # İstanbul: Ali
    assert bool(df.loc["M2", "istanbul"]) is False     # Ankara: Veli
    # Bursa Marmara bölgesinde ama İstanbul değil: ayrım şehirden, bölgeden değil
    assert df.loc["M3", "bolge"] == "Marmara" and bool(df.loc["M3", "istanbul"]) is False


# ------------------------------------------------------------ replenishment


def test_haftalik_replenishment_yalniz_fiziksel(oyuncak_con):
    h = kaynak.haftalik_replenishment(oyuncak_con, BAS, BIT)
    assert list(h.columns) == ["hafta", "adet"]
    # g0: M1 A-M 7; g7: M1 A-S 12. ilk_dagitim, outlet_akisi ve pencere dışı (g14) sayılmaz
    assert h["hafta"].tolist() == [gun(0), gun(7)]
    assert h["adet"].tolist() == [7, 12]


def test_haftalik_replenishment_depo_ve_online_hedefi_sayilmaz():
    t = oyuncak_tablolar()
    ek = t["sevkiyat"].iloc[[0, 0]].copy()
    ek["tip"], ek["tarih"], ek["varis_tarihi"] = "replenishment", gun(7), gun(8)
    ek["kaynak"], ek["hedef"], ek["adet"] = ["DEPO", "M1"], ["ONL", "DEPO"], [500, 400]
    t["sevkiyat"] = pd.concat([t["sevkiyat"], ek], ignore_index=True)
    con = oyuncak_baglan(t)
    try:
        assert kaynak.haftalik_replenishment(con, BAS, BIT)["adet"].tolist() == [7, 12]
    finally:
        con.close()


def test_etkin_optionlar_pencereyle_kesisenler(oyuncak_con):
    assert kaynak.etkin_optionlar(oyuncak_con, BAS, BIT).to_dict("records") == [
        {"option_id": "OPT-A", "line": "Collection"}]
    # çıkıştan (g28) sonra başlayan pencerede option etkin değil
    assert kaynak.etkin_optionlar(oyuncak_con, gun(28), gun(40)).empty


def test_line_haritasi(oyuncak_con):
    assert kaynak.line_haritasi(oyuncak_con) == {"OPT-A": "Collection"}


# ----------------------------------------------------------------- matrisler


def test_hucre_anahtari_dunyanin_hucre_sirasinda():
    a = kaynak.hucre_anahtari(_dunya())
    assert a.tolist() == [f"{m}|{u}" for m, u in HUCRELER]


def test_satis_matrisi_temiz_satistan(oyuncak_con):
    s = kaynak.gunluk_satis_matrisi(oyuncak_con, kaynak.hucre_anahtari(_dunya()), BAS, BIT)
    assert s.shape == (14, len(HUCRELER)) and s.dtype == np.int32
    ms = _sutun(s, "M1", "A-S")
    assert ms[3] == 2 and ms.sum() == 28            # mükerrer satış tek sayılır (ham: 30)
    assert _sutun(s, "M1", "A-M")[4] == 1           # iade brüt satıştan düşmez
    assert _sutun(s, "ONL", "A-M").tolist() == [0, 0, 0, 0, 0, 2] + [0] * 8   # ONL: depodan satış
    assert _sutun(s, "M2", "A-M").sum() == 0


def test_satis_matrisi_pencereye_ve_hucre_evrenine_bagli(oyuncak_con):
    a = kaynak.hucre_anahtari(_dunya())
    dar = kaynak.gunluk_satis_matrisi(oyuncak_con, a, gun(2), gun(4))
    assert dar.shape == (3, len(HUCRELER))
    assert _sutun(dar, "M1", "A-S").tolist() == [2, 2, 2]
    # anahtar evreninde olmayan hücrenin satışı sessizce düşer (ONL A-S, A-M yok)
    az = kaynak.gunluk_satis_matrisi(oyuncak_con, a[:4], BAS, BIT)
    assert az.shape == (14, 4) and az.sum() == 28 + 14 + 3


def test_stoklu_matrisi_ortak_tanimla(oyuncak_con):
    a = kaynak.hucre_anahtari(_dunya())
    st = kaynak.gunluk_stoklu_matrisi(oyuncak_con, a, BAS, BIT)
    assert st.shape == (14, len(HUCRELER)) and st.dtype == bool
    assert _sutun(st, "M1", "A-S").all() and _sutun(st, "M2", "A-M").all()
    # M2 A-S: 3 adet ilk üç günde biter (üçüncü gün satış öncesi 1 > 0 → stoklu), sonra boş
    assert _sutun(st, "M2", "A-S").tolist() == [True] * 3 + [False] * 11
    # ONL: satış öncesi = ertesi sabah depo stoğu + günün net satışı; A-M'nin depo stoğu g10'da biter
    assert _sutun(st, "ONL", "A-S").all()
    assert _sutun(st, "ONL", "A-M").tolist() == [True] * 9 + [False] * 5

    # ortak günlük tabloyla birebir: stoklu = durum != 'bos' (mağaza ve online)
    for tablo in (stok.gunluk_magaza(oyuncak_con, BAS, BIT), stok.gunluk_online(oyuncak_con, BAS, BIT)):
        tablo = tablo[tablo["tarih"] <= BIT]
        for r in tablo.itertuples():
            h = HUCRELER.index((str(r.magaza_id), str(r.urun_id))) if (str(r.magaza_id), str(r.urun_id)) in HUCRELER else None
            if h is not None:
                assert st[(r.tarih - BAS).days, h] == (r.durum != "bos")


def test_stoklu_matrisi_uygun_olmayan_hucre_gun_false(oyuncak_con):
    # M3'ün hiç stoğu/çeşidi yok → anahtar listesinde olsa bile False
    a = kaynak.hucre_anahtari(SimpleNamespace(
        magazalar=pd.DataFrame({"magaza_id": ["M3", "M1"]}), urunler=pd.DataFrame({"urun_id": ["A-S"]}),
        hucre_magaza=np.array([0, 1]), hucre_sku=np.array([0, 0])))
    st = kaynak.gunluk_stoklu_matrisi(oyuncak_con, a, BAS, BIT)
    assert not st[:, 0].any() and st[:, 1].all()


# --------------------------------------------------------------------- harita


@pytest.fixture(scope="module")
def kucuk():
    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek

    w = dunya_kur(Olcek.KUCUK)
    return w, kaynak.harita_kur(w)


def test_harita_hucre_dizileri_dunyanin_aynisi(kucuk):
    w, h = kucuk
    C, S, O = len(w.hucre_magaza), len(w.urunler), len(w.optionlar)
    for ad in ("hucre_magaza", "hucre_option", "hucre_sku", "hucre_online"):
        assert np.array_equal(getattr(h, ad), getattr(w, ad)), ad
    assert h.oc.shape == (C,) and h.sku_option.shape == (S,) and h.line.shape == (O,)
    assert np.array_equal(h.sku_option, w.sku_option)
    assert h.line.tolist() == w.optionlar["line"].astype(str).tolist()
    # beden bölmesi alanları (ihtiyac): option kategorisi / beden seti, SKU beden sırası ve zincir payı
    assert h.option_kategori.tolist() == w.optionlar["ust_kategori"].astype(str).tolist()
    assert h.option_beden_seti.tolist() == w.optionlar["beden_seti"].astype(str).tolist()
    assert np.array_equal(h.sku_beden, w.urunler["beden_sira"]) and h.sku_beden.min() == 1
    assert np.array_equal(h.sku_beden_payi, w.sku_beden_payi)
    assert np.allclose(np.bincount(h.sku_option, weights=h.sku_beden_payi), 1.0)


def test_harita_oc_magaza_option_cifti(kucuk):
    w, h = kucuk
    O = len(w.optionlar)
    # oc: hücrenin (mağaza, option) çiftinin indisi; tekil, sıralı ve geri çevrilebilir
    assert np.array_equal(h.oc_magaza[h.oc], h.hucre_magaza)
    assert np.array_equal(h.oc_option[h.oc], h.hucre_option)
    anahtar = h.oc_magaza.astype(np.int64) * O + h.oc_option
    assert (np.diff(anahtar) > 0).all() and len(anahtar) == len(np.unique(h.oc))
    assert np.array_equal(np.unique(h.oc), np.arange(len(h.oc_magaza)))
    # online çiftler yalnız online mağazanın hücreleri
    assert np.array_equal(h.oc_online[h.oc], h.hucre_online)


def test_harita_salt_okunur(kucuk):
    _, h = kucuk
    with pytest.raises(ValueError):
        h.oc[0] = 0
    with pytest.raises(AttributeError):
        h.oc = h.oc


def test_kaynak_gizli_gercegi_ice_aktarmaz():
    """kaynak.py perakende_veri ve motoru içe aktarmaz (harita dünyayı argüman alır)."""
    ag = ast.parse(Path(kaynak.__file__).read_text(encoding="utf-8"))
    ice = []
    for d in ast.walk(ag):
        if isinstance(d, ast.Import):
            ice += [a.name for a in d.names]
        elif isinstance(d, ast.ImportFrom):
            ice.append(("." * d.level) + (d.module or "") + "|" + ",".join(a.name for a in d.names))
    kotu = [i for i in ice if "perakende_veri" in i or "motor" in i or "hakem" in i]
    assert not kotu, kotu


def test_sabitler_spec_degerleri():
    assert (sabitler.OYUN_BAS, sabitler.OYUN_BIT) == (pd.Timestamp("2025-09-01").date(), pd.Timestamp("2025-12-31").date())
    assert (sabitler.KAL_BAS, sabitler.KAL_BIT) == (pd.Timestamp("2024-09-02").date(), pd.Timestamp("2024-12-31").date())
    assert sabitler.EGITIM_BIT == pd.Timestamp("2025-08-17").date()
    assert sabitler.ACIK_PAYI == {"Collection": .20, "Outlet": .20, "NOS": .40, "Basic": .40}
    assert (sabitler.ACIK_TL_ADET, sabitler.KOLI_TL, sabitler.TAVAN_ORANI) == (10, 20, 0.25)
    assert sabitler.ALIM_DUZEYLERI == (0.4, 0.7, 1.0)
    assert sabitler.TAVAN_KATLARI == (0.4, 0.6, 1.0, 1.6, float("inf"))
    assert sabitler.DEMO_TAVANLARI == {"kisitsiz": float("inf"), "gevsek": 1.6, "siki": 0.6}
    assert (sabitler.YOL_SAYISI, sabitler.TALEP_TOHUM_TABANI) == (5, 20261010)


# ------------------------------------------------------------------ gerçek v4


@pytest.mark.veri
def test_oyun_penceresi_olcegi():
    if not kaynak.VERITABANI.exists():
        pytest.skip("v4 verisi yok (cd veri && python -m perakende_veri.v4.uret)")
    con = kaynak.baglan()
    try:
        h = kaynak.haftalik_replenishment(con, sabitler.OYUN_BAS, sabitler.OYUN_BIT)
        assert len(h) == 18 and (pd.to_datetime(h["hafta"]).dt.dayofweek == 0).all()
        assert 2_000_000 < h["adet"].sum() < 2_200_000
        etkin = kaynak.etkin_optionlar(con, sabitler.OYUN_BAS, sabitler.OYUN_BIT)
        assert etkin.groupby("line").size().to_dict() == {"Collection": 210, "Basic": 80, "NOS": 40, "Outlet": 40}
        m = kaynak.fiziksel_magazalar(con)
        assert len(m) == 84 and "ONL" not in set(m["magaza_id"])
        assert m["istanbul"].sum() == 18
    finally:
        con.close()
