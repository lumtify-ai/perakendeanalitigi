"""Görev 9: online liste, Lumoda sıralaması, tıklama modeli, olay kaydı."""

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4.crm import sabitler as S
from perakende_veri.v4.crm.online import (
    lumoda_siralama,
    online_uret,
    tiklama_olasiligi,
)
from perakende_veri.v4.takvim import gun_indisi

OLAY_BAS, OLAY_SON = gun_indisi("2025-09-01"), gun_indisi("2025-11-30")
DILIM = (gun_indisi("2025-11-10"), gun_indisi("2025-12-05"))   # BF ve olay penceresi sonu dahil


@pytest.fixture(scope="module")
def kucuk_online(kucuk_girdi, kucuk_crm):
    return online_uret(kucuk_girdi, kucuk_crm)


@pytest.fixture(scope="module")
def onl_satirlari(kucuk_girdi, kucuk_crm):
    """ONL satış fiş satırları: gun, fis_id, musteri, option, adet."""
    fis = kucuk_crm.tablo("fis")
    onl = kucuk_crm.nufus.magaza.onl
    fis = fis[(fis["magaza"] == onl) & (fis["tip"] == 0)]
    sat = kucuk_crm.tablo("fis_satir")
    sat = sat[sat["fis_id"].isin(fis["fis_id"]) & (sat["adet"] > 0)]
    w = kucuk_girdi.dunya
    sku_opt = pd.Index(w.optionlar["option_id"]).get_indexer(w.urunler["option_id"])
    df = sat.merge(fis[["fis_id", "gun", "musteri", "saat"]], on="fis_id")
    df["option"] = sku_opt[df["sku"].to_numpy()]
    return df


@pytest.fixture(scope="module")
def stoklu(kucuk_girdi):
    w, ham = kucuk_girdi.dunya, kucuk_girdi.ham
    sku_opt = pd.Index(w.optionlar["option_id"]).get_indexer(w.urunler["option_id"])
    ds = ham["depo_stok"]
    ds = ds[ds["adet"] > 0]
    return set(zip(ds["gun"].to_numpy().tolist(), sku_opt[ds["sku"].to_numpy()].tolist()))


def _pencere(g):
    from perakende_veri.v4.tablolar import pencere

    b, s = pencere()
    return b, min(s, g.D - 1)


def test_satin_alma_toplami_onl_fis_satirlarina_esit(kucuk_online, onl_satirlari, kucuk_crm):
    b, s = _pencere(kucuk_crm)
    gl = kucuk_online.gunluk
    a = gl.groupby(["gun", "option"])["satin_alma"].sum()
    a = a[a > 0].sort_index()
    o = onl_satirlari[(onl_satirlari["gun"] >= b) & (onl_satirlari["gun"] <= s)]
    e = o.groupby(["gun", "option"])["adet"].sum().sort_index()
    assert len(e) > 1000
    assert a.index.equals(e.index)
    assert (a.to_numpy() == e.to_numpy()).all()


def test_gunluk_sinirlar(kucuk_online):
    gl = kucuk_online.gunluk
    assert gl["sira"].between(1, S.LISTE_UZUNLUGU).all()
    assert (gl["gosterim"] >= gl["tiklama"]).all()
    assert (gl["tiklama"] >= gl["sepete_ekleme"]).all()
    assert (gl["sepete_ekleme"] >= gl["satin_alma"]).all()
    n = gl.groupby(["gun", "liste"], observed=True).size()
    assert n.max() <= S.LISTE_UZUNLUGU + 20       # 48 + enjekte arama hücreleri
    assert not gl.duplicated(["gun", "liste", "sira", "option"]).any()


def test_stoksuz_option_listede_yok(kucuk_online, stoklu):
    gl = kucuk_online.gunluk
    st = np.array([(g, o) in stoklu for g, o in zip(gl["gun"].tolist(), gl["option"].tolist())])
    assert st.mean() > 0.9
    stoksuz = gl[~st]
    # stoksuz görünen option yalnız satın alındığı gün arama listesinin 1. sırasında
    assert stoksuz["liste"].astype(str).str.startswith("arama:").all()
    assert (stoksuz["sira"] == 1).all()
    assert (stoksuz["satin_alma"] > 0).all()


def test_listede_olmayan_satin_alma_arama_listesinde(kucuk_online, kucuk_girdi, stoklu, onl_satirlari,
                                                     kucuk_crm):
    b, s = _pencere(kucuk_crm)
    alt = kucuk_girdi.dunya.optionlar["alt_kategori"].to_numpy()
    o = onl_satirlari[(onl_satirlari["gun"] >= b) & (onl_satirlari["gun"] <= s)]
    e = o.groupby(["gun", "option"])["adet"].sum()
    listede_degil = [(g, op) for g, op in e.index if (g, op) not in stoklu]
    assert listede_degil, "KUCUK'ta stoksuz görünürken satılan option beklenirdi"
    gl = kucuk_online.gunluk.set_index(["gun", "option"])
    for g, op in listede_degil[:200]:
        r = gl.loc[[(g, op)]]
        assert len(r) == 1
        assert r["liste"].iloc[0] == f"arama:{alt[op]}"
        assert r["sira"].iloc[0] == 1
        assert r["satin_alma"].iloc[0] == e[(g, op)]


def test_ayni_ilgide_sira1_tiklamasi_sira20den_buyuk(kucuk_online):
    for ilgi in (0.3, 1.0, 3.0):
        assert tiklama_olasiligi(1, ilgi) > tiklama_olasiligi(20, ilgi)
    gl = kucuk_online.gunluk
    gl = gl[~gl["liste"].astype(str).str.startswith("arama:") | (gl["gosterim"] > 0)]
    oran = gl.groupby("sira")[["tiklama", "gosterim"]].sum()
    ctr = oran["tiklama"] / oran["gosterim"]
    assert ctr.loc[1] > ctr.loc[20]


def test_her_online_fis_icin_tek_siparis_ayni_musteri(kucuk_online, onl_satirlari):
    ol = kucuk_online.olay
    sip = ol[ol["olay_tipi"] == "siparis"]
    fis = onl_satirlari[(onl_satirlari["gun"] >= OLAY_BAS) & (onl_satirlari["gun"] <= OLAY_SON)]
    fis = fis.drop_duplicates("fis_id").set_index("fis_id")
    assert len(fis) > 100
    assert sip["fis_id"].is_unique
    assert set(sip["fis_id"]) == set(fis.index)
    assert (sip.set_index("fis_id")["musteri"].loc[fis.index].to_numpy() == fis["musteri"].to_numpy()).all()
    # sipariş anı fişin saat dakikası
    z = sip.set_index("fis_id")["zaman"].loc[fis.index]
    dk = z.dt.hour * 60 + z.dt.minute
    assert (dk.to_numpy() == fis["saat"].to_numpy()).all()
    assert (ol.loc[ol["olay_tipi"] != "siparis", "fis_id"] == -1).all()


def test_giris_payi(kucuk_online):
    ol = kucuk_online.olay
    ot = ol.groupby("oturum_id")["musteri"].first()
    pay = (ot >= 0).mean()
    assert 0.45 <= pay <= 0.75, pay
    # sipariş oturumları hep giriş yapmış
    sip_ot = ol.loc[ol["olay_tipi"] == "siparis", "oturum_id"]
    assert (ot.loc[sip_ot] >= 0).all()
    assert (ol.groupby("oturum_id")["musteri"].nunique() == 1).all()


def test_olay_penceresi_ve_oturum_yapisi(kucuk_online):
    ol = kucuk_online.olay
    assert ol["zaman"].min() >= pd.Timestamp("2025-09-01")
    assert ol["zaman"].max() < pd.Timestamp("2025-12-01")
    assert (ol.groupby("oturum_id")["zaman"].apply(lambda z: z.is_monotonic_increasing)).all()
    gor = ol[ol["olay_tipi"] == "liste_goruntuleme"].groupby("oturum_id").size()
    sip = set(ol.loc[ol["olay_tipi"] == "siparis", "oturum_id"])
    tarama = gor[~gor.index.isin(sip)]
    assert tarama.between(1, S.OTURUM_EN_COK).all()
    # günlük oturum ≈ görüntüleme / 3
    gun = ol["zaman"].dt.normalize()
    n_ot = ol.groupby(gun)["oturum_id"].nunique()
    n_gor = ol[ol["olay_tipi"] == "liste_goruntuleme"].groupby(gun[ol["olay_tipi"] == "liste_goruntuleme"]).size()
    r = (n_gor / n_ot).mean()
    assert 2.5 <= r <= 3.5, r


def test_olay_kaydi_gunluk_ozetle_tutarli(kucuk_online):
    ol = kucuk_online.olay
    gl = kucuk_online.gunluk
    gl = gl[(gl["gun"] >= OLAY_BAS) & (gl["gun"] <= OLAY_SON)]
    gun = (ol["zaman"].dt.normalize() - pd.Timestamp("2022-07-04")).dt.days
    ol = ol.assign(gun=gun.to_numpy())
    for tip, sut in (("tiklama", "tiklama"), ("sepete_ekleme", "sepete_ekleme")):
        a = ol[ol["olay_tipi"] == tip].groupby(["gun", "liste", "sira", "option"], observed=True).size()
        e = gl.set_index(["gun", "liste", "sira", "option"])[sut]
        e = e[e > 0]
        a = a.reindex(e.index, fill_value=0)
        assert (a.to_numpy() == e.to_numpy()).all(), tip
        assert len(ol[ol["olay_tipi"] == tip]) == int(e.sum())
    # liste görüntüleme = listelenmiş hücrelerin gösterimi (liste başına tek değer)
    v = ol[ol["olay_tipi"] == "liste_goruntuleme"].groupby(["gun", "liste"], observed=True).size()
    g2 = gl[gl["sira"] > 1].groupby(["gun", "liste"], observed=True)["gosterim"].agg(["min", "max"])
    assert (g2["min"] == g2["max"]).all()
    ortak = g2.index.intersection(v.index)
    assert len(ortak) > 0.9 * len(g2)
    assert (v.loc[ortak].to_numpy() == g2.loc[ortak, "min"].to_numpy()).all()


def test_ters_siralama_satin_almayi_degistirmez(kucuk_girdi, kucuk_crm):
    def ters(g):
        return {a: v[::-1] for a, v in lumoda_siralama(g).items()}

    lum = online_uret(kucuk_girdi, kucuk_crm, gun_bas=DILIM[0], gun_son=DILIM[1])
    tr = online_uret(kucuk_girdi, kucuk_crm, siralama=ters, gun_bas=DILIM[0], gun_son=DILIM[1])
    a = lum.gunluk.groupby(["gun", "option"])["satin_alma"].sum()
    b = tr.gunluk.groupby(["gun", "option"])["satin_alma"].sum()
    a, b = a[a > 0].sort_index(), b[b > 0].sort_index()
    assert a.index.equals(b.index) and (a.to_numpy() == b.to_numpy()).all()
    # sıralama gerçekten değişti
    k = ["gun", "liste", "sira"]
    x = lum.gunluk[lum.gunluk["sira"] == 1].drop_duplicates(k).set_index(k)["option"]
    y = tr.gunluk[tr.gunluk["sira"] == 1].drop_duplicates(k).set_index(k)["option"]
    ortak = x.index.intersection(y.index)
    assert (x.loc[ortak] != y.loc[ortak]).mean() > 0.3
    # sipariş olayları sıralamadan bağımsız
    sa = lum.olay.loc[lum.olay["olay_tipi"] == "siparis", "fis_id"]
    sb = tr.olay.loc[tr.olay["olay_tipi"] == "siparis", "fis_id"]
    assert set(sa) == set(sb) and len(sa) > 0


def test_lumoda_kategori_7_gun_satisina_gore(kucuk_online, kucuk_crm, onl_satirlari):
    gl = kucuk_online.gunluk
    d = gun_indisi("2024-10-15")
    satir = onl_satirlari[(onl_satirlari["gun"] >= d - 7) & (onl_satirlari["gun"] < d)]
    s7 = satir.groupby("option")["adet"].sum()
    g = gl[(gl["gun"] == d) & gl["liste"].astype(str).str.startswith("kategori:")]
    for _, l in g.groupby("liste", observed=True):
        l = l.sort_values("sira")
        v = s7.reindex(l["option"]).fillna(0).to_numpy()
        assert (np.diff(v) <= 0).all()


def test_determinizm(kucuk_girdi, kucuk_crm):
    a = online_uret(kucuk_girdi, kucuk_crm, gun_bas=OLAY_SON - 3, gun_son=OLAY_SON + 2)
    b = online_uret(kucuk_girdi, kucuk_crm, gun_bas=OLAY_SON - 3, gun_son=OLAY_SON + 2)
    pd.testing.assert_frame_equal(a.gunluk, b.gunluk)
    pd.testing.assert_frame_equal(a.olay, b.olay)
    assert len(a.olay) > 0


def test_gizli_ilgi_ve_bakilma(kucuk_online, kucuk_girdi):
    gz = kucuk_online.gizli
    bk = gz["bakilma"]
    assert len(bk) == S.LISTE_UZUNLUGU and (np.diff(bk["bakilma"].to_numpy()) < 0).all()
    il = gz["ilgi"]
    assert (il["ilgi"] > 0).all() and np.isfinite(il["ilgi"]).all()
    assert set(il["arketip"]) == set(S.ARKETIPLER)
    assert il["option"].nunique() == len(kucuk_girdi.dunya.optionlar)


def test_huni_oranlari(kucuk_online):
    s = kucuk_online.gunluk[["tiklama", "sepete_ekleme", "satin_alma"]].sum()
    assert 0.04 <= s["satin_alma"] / s["tiklama"] <= 0.14
    assert 0.2 <= s["satin_alma"] / s["sepete_ekleme"] <= 0.5
    assert 0.2 <= s["sepete_ekleme"] / s["tiklama"] <= 0.32
