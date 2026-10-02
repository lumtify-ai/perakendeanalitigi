"""Görev 13: yayımlanan tablolar, gizli gerçek, üretici (KUCUK)."""

import hashlib

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4.crm.tablolar import GIZLI_TABLOLAR, TABLOLAR

BAS = pd.Timestamp("2023-01-01")
SON = pd.Timestamp("2025-12-31")


@pytest.fixture(scope="module")
def uretim(kucuk_girdi, kucuk_crm):
    from perakende_veri.v4.crm.uret import uret_girdiden

    return uret_girdiden(kucuk_girdi, crm=kucuk_crm)


@pytest.fixture(scope="module")
def tablolar(uretim):
    return uretim[0]


@pytest.fixture(scope="module")
def gizli(uretim):
    return uretim[1].gizli_gercek()


@pytest.fixture(scope="module")
def a_satis(kucuk_girdi):
    from perakende_veri.v4.uret import yayimla

    return yayimla(kucuk_girdi.dunya, kucuk_girdi.ham, kirli=False)["satis"]


def _ozet(tablolar: dict) -> str:
    h = hashlib.sha256()
    for ad in sorted(tablolar):
        df = tablolar[ad]
        h.update(f"{ad}:{list(df.columns)}:{[str(t) for t in df.dtypes]}".encode())
        h.update(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes())
    return h.hexdigest()


def _kume(s: pd.Series) -> set:
    return set(s.dropna().astype(str))


# ---------------------------------------------------------------------------
# Şema
# ---------------------------------------------------------------------------


def test_tablo_kumesi(tablolar, gizli):
    assert tuple(tablolar) == TABLOLAR
    assert tuple(gizli) == GIZLI_TABLOLAR
    for ad, df in tablolar.items():
        assert len(df) > 0, ad


SUTUNLAR = {
    "musteri": ["musteri_id", "kayit_tarihi", "kayit_kanali", "ev_magaza_id", "il", "yas_grubu", "cinsiyet"],
    "fis": ["fis_id", "tarih", "saat", "magaza_id", "musteri_id", "kanal", "fis_tipi", "adet", "tutar",
            "teslim_tarihi"],
    "fis_satir": ["fis_satir_id", "fis_id", "satir_no", "urun_id", "adet", "birim_fiyat", "tutar",
                  "indirim_tutari", "kampanya_id", "orijinal_fis_satir_id"],
    "online_liste_gunluk": ["tarih", "liste", "sira", "option_id", "gosterim", "tiklama", "sepete_ekleme",
                            "satin_alma"],
    "online_olay": ["oturum_id", "musteri_id", "zaman", "olay_tipi", "liste", "sira", "option_id", "fis_id"],
    "yorum": ["yorum_id", "fis_satir_id", "musteri_id", "urun_id", "tarih", "puan", "metin"],
}

TIPLER = {
    "musteri": {"musteri_id": "string", "kayit_tarihi": "datetime64[ns]", "kayit_kanali": "category",
                "ev_magaza_id": "category", "il": "category", "yas_grubu": "category", "cinsiyet": "category"},
    "fis": {"fis_id": "string", "tarih": "datetime64[ns]", "saat": "category", "magaza_id": "category",
            "musteri_id": "string", "kanal": "category", "fis_tipi": "category", "adet": "int32",
            "tutar": "float64", "teslim_tarihi": "datetime64[ns]"},
    "fis_satir": {"fis_satir_id": "string", "fis_id": "string", "satir_no": "int16", "urun_id": "category",
                  "adet": "int32", "birim_fiyat": "float64", "tutar": "float64", "indirim_tutari": "float64",
                  "kampanya_id": "category", "orijinal_fis_satir_id": "string"},
    "online_liste_gunluk": {"tarih": "datetime64[ns]", "liste": "category", "sira": "int16",
                            "option_id": "category", "gosterim": "int32", "tiklama": "int32",
                            "sepete_ekleme": "int32", "satin_alma": "int32"},
    "online_olay": {"oturum_id": "int64", "musteri_id": "string", "zaman": "datetime64[ns]",
                    "olay_tipi": "category", "liste": "category", "sira": "Int16", "option_id": "category",
                    "fis_id": "string"},
    "yorum": {"yorum_id": "string", "fis_satir_id": "string", "musteri_id": "string", "urun_id": "category",
              "tarih": "datetime64[ns]", "puan": "int8", "metin": "string"},
}


def test_sutunlar_ve_tipler(tablolar):
    for ad, df in tablolar.items():
        assert list(df.columns) == SUTUNLAR[ad], ad
        for c, t in TIPLER[ad].items():
            assert str(df[c].dtype) == t, (ad, c, str(df[c].dtype))


YASAK = ("arketip", "terk", "ltv", "hayatta", "ilgi", "neden", "konu", "duygu", "gecikme", "beden_uyumsuz",
         "islem", "a_satir", "kart", "kutuphane", "uslup", "gevseme", "bakilma", "tercih", "parametre")


def test_gizli_sutun_yok(tablolar):
    for ad, df in tablolar.items():
        for c in df.columns:
            assert not any(y in c for y in YASAK), (ad, c)


def test_kimlik_bicimleri(tablolar):
    desen = {("musteri", "musteri_id"): (r"K\d{7}", "K0000001"), ("fis", "fis_id"): (r"F\d{8}", "F00000001"),
             ("fis_satir", "fis_satir_id"): (r"FS\d{9}", "FS000000001"),
             ("yorum", "yorum_id"): (r"Y\d{7}", "Y0000001")}
    for (ad, c), (d, ilk) in desen.items():
        s = tablolar[ad][c]
        assert s.notna().all() and s.is_unique, (ad, c)
        assert s.str.fullmatch(d).all(), (ad, c)
        assert s.iloc[0] == ilk, (ad, c)


def test_pencere(tablolar):
    for ad, c in (("fis", "tarih"), ("online_liste_gunluk", "tarih"), ("yorum", "tarih")):
        t = tablolar[ad][c]
        assert t.min() >= BAS and t.max() <= SON, ad
    z = tablolar["online_olay"]["zaman"]
    assert z.min() >= pd.Timestamp("2025-09-01") and z.max() < pd.Timestamp("2025-12-01")
    t = tablolar["fis"]["teslim_tarihi"].dropna()
    assert t.max() <= SON


# ---------------------------------------------------------------------------
# Yabancı anahtarlar
# ---------------------------------------------------------------------------


def test_yabanci_anahtarlar(tablolar, kucuk_girdi):
    w = kucuk_girdi.dunya
    T = tablolar
    musteri = set(T["musteri"]["musteri_id"])
    fis = set(T["fis"]["fis_id"])
    satir = set(T["fis_satir"]["fis_satir_id"])
    assert _kume(T["fis"]["magaza_id"]) <= set(w.magazalar["magaza_id"].astype(str))
    assert _kume(T["musteri"]["ev_magaza_id"]) <= set(w.magazalar["magaza_id"].astype(str))
    assert _kume(T["fis"]["musteri_id"]) <= musteri
    assert set(T["fis_satir"]["fis_id"]) == fis              # her fişin en az bir satırı var
    assert _kume(T["fis_satir"]["urun_id"]) <= set(w.urunler["urun_id"].astype(str))
    assert _kume(T["fis_satir"]["kampanya_id"]) <= set(w.kampanya["kampanya_id"].astype(str))
    assert _kume(T["fis_satir"]["orijinal_fis_satir_id"]) <= satir
    assert set(T["yorum"]["fis_satir_id"]) <= satir
    assert set(T["yorum"]["musteri_id"]) <= musteri
    assert _kume(T["online_olay"]["musteri_id"]) <= musteri
    assert _kume(T["online_olay"]["fis_id"]) <= fis
    opt = set(w.optionlar["option_id"].astype(str))
    assert _kume(T["online_olay"]["option_id"]) <= opt
    assert _kume(T["online_liste_gunluk"]["option_id"]) <= opt
    # müşteri tablosunda fişi olmayan kimse ve görünmeyen kimse yok
    assert T["musteri"]["musteri_id"].is_unique


def test_iade_orijinali(tablolar):
    fs, f = tablolar["fis_satir"], tablolar["fis"]
    fs = fs.merge(f[["fis_id", "tarih", "magaza_id", "fis_tipi"]], on="fis_id")
    iade = fs[fs["fis_tipi"] == "iade"]
    satis = fs[fs["fis_tipi"] == "satis"]
    assert (iade["adet"] < 0).all() and (satis["adet"] > 0).all()
    assert satis["orijinal_fis_satir_id"].isna().all()
    bag = iade.dropna(subset=["orijinal_fis_satir_id"]).merge(
        satis, left_on="orijinal_fis_satir_id", right_on="fis_satir_id", suffixes=("", "_o"))
    assert len(bag) == iade["orijinal_fis_satir_id"].notna().sum()
    assert (bag["urun_id"].astype(str) == bag["urun_id_o"].astype(str)).all()
    assert (bag["magaza_id"].astype(str) == bag["magaza_id_o"].astype(str)).all()
    gecikme = (bag["tarih"] - bag["tarih_o"]).dt.days
    assert gecikme.isin([7, 10]).all()
    # boş orijinal yalnız pencerenin ilk günlerinde (orijinali ısınmada)
    bos = iade[iade["orijinal_fis_satir_id"].isna()]
    assert (bos["tarih"] < pd.Timestamp("2023-01-11")).all()


# ---------------------------------------------------------------------------
# Tutarlılık sözleşmesi
# ---------------------------------------------------------------------------


def _kurus(x) -> np.ndarray:
    return np.rint(np.asarray(x, dtype=float) * 100).astype(np.int64)


def test_tutarlilik_sozlesmesi(tablolar, a_satis):
    fs = tablolar["fis_satir"].merge(tablolar["fis"][["fis_id", "tarih", "magaza_id"]], on="fis_id")
    anahtar = ["tarih", "magaza_id", "urun_id"]

    def grupla(df):
        df = df.assign(magaza_id=df["magaza_id"].astype(str), urun_id=df["urun_id"].astype(str),
                       adet=df["adet"].astype(np.int64))
        return df.groupby(anahtar, observed=True)[["adet", "tutar", "indirim_tutari"]].sum()

    b, a = grupla(fs), grupla(a_satis)
    ortak = a.join(b, how="outer", lsuffix="_a", rsuffix="_b").fillna(0)
    assert len(ortak) == len(a) == len(b)
    assert (ortak["adet_a"] == ortak["adet_b"]).all()
    assert (_kurus(ortak["tutar_a"]) == _kurus(ortak["tutar_b"])).all()
    assert (_kurus(ortak["indirim_tutari_a"]) == _kurus(ortak["indirim_tutari_b"])).all()


def test_fis_toplamlari(tablolar):
    fs = tablolar["fis_satir"]
    top = fs.groupby("fis_id", observed=True).agg(adet=("adet", "sum"), tutar=("tutar", "sum"))
    f = tablolar["fis"].set_index("fis_id").loc[top.index]
    assert (f["adet"].to_numpy() == top["adet"].to_numpy()).all()
    assert (_kurus(f["tutar"]) == _kurus(top["tutar"])).all()
    assert (np.abs(fs["birim_fiyat"] * fs["adet"].abs() - fs["tutar"].abs()) <= 0.01 * fs["adet"].abs()).all()


def test_kimlik_ve_kart(tablolar, gizli):
    f = tablolar["fis"]
    onl = f["kanal"] == "online"
    assert f.loc[onl, "musteri_id"].notna().all()
    sat = (~onl) & (f["fis_tipi"] == "satis")
    pay = f.loc[sat, "musteri_id"].notna().mean()
    assert 0.50 <= pay <= 0.60, pay
    anonim = gizli["anonim_fis_sahibi"]
    assert set(anonim["fis_id"]) == set(f.loc[f["musteri_id"].isna(), "fis_id"])
    assert (anonim["musteri"] >= 0).all()
    # teslim tarihi yalnız online satış fişinde
    assert f.loc[~(onl & (f["fis_tipi"] == "satis")), "teslim_tarihi"].isna().all()
    t = f.loc[onl & (f["fis_tipi"] == "satis")]
    t = t.dropna(subset=["teslim_tarihi"])
    assert ((t["teslim_tarihi"] - t["tarih"]).dt.days >= 1).all()


def test_musteri_gorunur_ve_fisli(tablolar, uretim, gizli):
    """Yayımlanan her müşterinin en az bir kimlikli fişi (bütün kayıtta)
    var; hiç fişi olmayan yedek müşteriler yayımlanmaz."""
    ham = uretim[1]
    fis = ham.hazir.fis
    kimlikli = np.unique(fis["musteri"].to_numpy()[fis["kart"].to_numpy()])
    mg = gizli["musteri_gizli"]
    yay = mg["musteri_id"].notna().to_numpy()
    assert yay.sum() == len(tablolar["musteri"])
    assert np.isin(np.flatnonzero(yay), kimlikli).all()
    assert (mg["musteri_id"].dropna().to_numpy() == tablolar["musteri"]["musteri_id"].to_numpy()).all()


def test_musteri_kayit_ilk_kimlikli_olay(tablolar, uretim, gizli):
    """Son inceleme (Önemli 3): simülasyonda katılan müşterinin yayımlanan
    `kayit_tarihi` ilk kimlikli fişinin günü (`gorunur_gun`), `kayit_kanali`
    o fişin kanalı; başlangıç tabanı (katılış günü < 0) eski anlamını korur.
    Gizli gerçekte katılış günü ve kanalı değişmez."""
    ham = uretim[1]
    n = ham.crm.nufus
    fis = ham.hazir.fis
    kart = fis["kart"].to_numpy()
    mus = fis["musteri"].to_numpy()[kart]
    gun = fis["gun"].to_numpy()[kart]
    mag = fis["magaza"].to_numpy()[kart]
    o = np.lexsort((fis["fis_id"].to_numpy()[kart], fis["saat"].to_numpy()[kart], gun, mus))
    ilk = o[np.r_[True, np.diff(mus[o]) > 0]]
    ilk_gun = dict(zip(mus[ilk], gun[ilk]))
    ilk_onl = dict(zip(mus[ilk], mag[ilk] == n.magaza.onl))

    mg = gizli["musteri_gizli"]
    k = np.flatnonzero(mg["musteri_id"].notna().to_numpy())
    m = tablolar["musteri"]
    assert len(m) == len(k)
    taban = n.kayit_gun[k] < 0
    assert taban.any() and (~taban).any()
    beklenen_gun = np.where(taban, n.kayit_gun[k], [ilk_gun[i] for i in k])
    assert (beklenen_gun[~taban] == n.gorunur_gun[k][~taban]).all()
    from perakende_veri.v4.tablolar import _gun_tarihi

    assert (m["kayit_tarihi"].to_numpy() == _gun_tarihi(beklenen_gun)).all()
    onl = np.array([ilk_onl[i] for i in k])
    beklenen_kanal = np.where(taban, np.array(["magaza", "online"])[n.kayit_kanali[k]],
                              np.where(onl, "online", "magaza"))
    assert (m["kayit_kanali"].astype(str).to_numpy() == beklenen_kanal).all()
    # simülasyonda katılan: kayıt tarihi pencere içi ya da ısınmada, ilk fişten önce değil
    yeni = ~taban
    assert (m["kayit_tarihi"].to_numpy()[yeni] <= SON.to_datetime64()).all()
    # gizli gerçek katılış gününü taşır (yayımlanandan önce ya da aynı gün)
    gk = mg["kayit_tarihi"].to_numpy()[k]
    assert (gk == _gun_tarihi(n.kayit_gun[k])).all()
    assert (gk[yeni] <= m["kayit_tarihi"].to_numpy()[yeni]).all()
    assert (gk[yeni] < m["kayit_tarihi"].to_numpy()[yeni]).any()


def test_yorum_tutarli(tablolar):
    y = tablolar["yorum"].merge(tablolar["fis_satir"][["fis_satir_id", "fis_id", "urun_id"]],
                                on="fis_satir_id", suffixes=("", "_s"))
    y = y.merge(tablolar["fis"][["fis_id", "musteri_id", "kanal", "fis_tipi", "tarih"]], on="fis_id",
                suffixes=("", "_f"))
    assert len(y) == len(tablolar["yorum"])
    assert (y["urun_id"].astype(str) == y["urun_id_s"].astype(str)).all()
    assert (y["musteri_id"] == y["musteri_id_f"]).all()
    assert (y["kanal"] == "online").all() and (y["fis_tipi"] == "satis").all()
    assert (y["tarih"] > y["tarih_f"]).all()


# ---------------------------------------------------------------------------
# Online
# ---------------------------------------------------------------------------


def test_liste_satin_alma_onl_fis_satirlari(tablolar, kucuk_girdi):
    fs = tablolar["fis_satir"].merge(tablolar["fis"][["fis_id", "tarih", "kanal", "fis_tipi"]], on="fis_id")
    fs = fs[(fs["kanal"] == "online") & (fs["fis_tipi"] == "satis")]
    u = kucuk_girdi.dunya.urunler
    opt = dict(zip(u["urun_id"].astype(str), u["option_id"].astype(str)))
    fs = fs.assign(option_id=fs["urun_id"].astype(str).map(opt))
    b = fs.groupby(["tarih", "option_id"])["adet"].sum()
    g = tablolar["online_liste_gunluk"].assign(option_id=lambda d: d["option_id"].astype(str))
    a = g.groupby(["tarih", "option_id"])["satin_alma"].sum()
    a = a[a > 0]
    assert int(a.sum()) == int(fs["adet"].sum())
    pd.testing.assert_series_equal(a.sort_index(), b.sort_index(), check_names=False, check_dtype=False)
    assert g["sira"].between(1, 48).all()


def test_olay_siparisleri_onl_fisleri(tablolar):
    o = tablolar["online_olay"]
    sip = o[o["olay_tipi"] == "siparis"]
    assert sip["fis_id"].notna().all() and sip["fis_id"].is_unique
    assert o.loc[o["olay_tipi"] != "siparis", "fis_id"].isna().all()
    assert sip["liste"].isna().all() and sip["sira"].isna().all() and sip["option_id"].isna().all()
    f = tablolar["fis"]
    pen = f[(f["tarih"] >= "2025-09-01") & (f["tarih"] <= "2025-11-30") & (f["kanal"] == "online")
            & (f["fis_tipi"] == "satis")]
    assert set(sip["fis_id"]) == set(pen["fis_id"])
    m = sip.merge(f[["fis_id", "musteri_id", "tarih"]], on="fis_id")
    assert (m["musteri_id_x"] == m["musteri_id_y"]).all()
    assert (m["zaman"].dt.normalize() == m["tarih"]).all()


# ---------------------------------------------------------------------------
# Gizli gerçek
# ---------------------------------------------------------------------------


def test_gizli_gercek(gizli, uretim, tablolar):
    ham = uretim[1]
    K = ham.crm.nufus.K
    mg = gizli["musteri_gizli"]
    assert len(mg) == K and mg["arketip"].notna().all()
    assert len(gizli["ltv_2026"]) == K
    assert (gizli["terk"]["terk_tarihi"].notna()).all()
    assert len(gizli["terk"]) == (~mg["hayatta"]).sum()
    assert set(gizli["yorum_etiket"]["yorum_id"]) == set(tablolar["yorum"]["yorum_id"])
    kg = gizli["kargo_gecikme"]
    f = tablolar["fis"]
    assert set(kg["fis_id"]) == set(f.loc[(f["kanal"] == "online") & (f["fis_tipi"] == "satis"), "fis_id"])
    assert 0 < kg["gecikme"].mean() < 0.3
    tm = gizli["tiklama_modeli"]
    assert {"bakilma", "ilgi", "tiklama_sabiti"} <= set(tm)
    assert "option_id" in tm["ilgi"].columns
    bz = gizli["bos_ziyaret"]
    assert len(bz) and bz["tarih"].between(BAS, SON).all()
    assert set(gizli["fis_satir_gizli"]["fis_satir_id"]) <= set(tablolar["fis_satir"]["fis_satir_id"])


# ---------------------------------------------------------------------------
# Üretici
# ---------------------------------------------------------------------------


def test_determinizm(kucuk_girdi, tablolar):
    from perakende_veri.v4.crm.uret import tablolari_uret_crm

    ikinci = tablolari_uret_crm(girdi=kucuk_girdi)
    assert _ozet(ikinci) == _ozet(tablolar)


def test_yaz(tablolar, tmp_path):
    import duckdb

    from perakende_veri.v4.crm.uret import DUCKDB_ADI, yaz

    kucuk = {ad: df.head(500) for ad, df in tablolar.items()}
    yaz(kucuk, tmp_path)
    assert not (tmp_path / "csv" / "online_olay.csv").exists()
    for ad in TABLOLAR:
        assert (tmp_path / "parquet" / f"{ad}.parquet").exists()
        if ad != "online_olay":
            assert (tmp_path / "csv" / f"{ad}.csv").exists()
    con = duckdb.connect(str(tmp_path / DUCKDB_ADI), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM fis").fetchone()[0] == 500
        tip = dict(con.execute("SELECT column_name, data_type FROM information_schema.columns "
                               "WHERE table_name = 'fis'").fetchall())
        assert tip["tarih"] == "DATE" and tip["fis_id"] == "VARCHAR"
    finally:
        con.close()
    bas = (tmp_path / "csv" / "fis.csv").read_text(encoding="utf-8").splitlines()
    assert bas[0].split(",") == SUTUNLAR["fis"]
