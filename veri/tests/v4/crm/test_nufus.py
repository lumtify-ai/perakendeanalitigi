"""Görev 2: müşteri nüfusu, arketipler, katılış."""

import numpy as np
import pytest

from perakende_veri.v4.crm.sabitler import CRM_TOHUM


@pytest.fixture(scope="module")
def kucuk_nufus(kucuk_girdi):
    from perakende_veri.v4.crm.nufus import nufus_baslat

    return nufus_baslat(np.random.default_rng(CRM_TOHUM), kucuk_girdi)


@pytest.fixture(scope="module")
def n():
    """Mağaza bağlamı olmadan, her arketipten eşit sayıda müşteri."""
    from perakende_veri.v4.crm import nufus as N

    return N.arketip_ornegi(np.random.default_rng(CRM_TOHUM), 4000)


def test_arketip_dagilimi_segmentle_iliskili():
    from perakende_veri.v4 import sabitler as a_sabitler
    from perakende_veri.v4.crm.sabitler import ARKETIPLER, SEGMENT_ARKETIP_KARISIM

    assert set(SEGMENT_ARKETIP_KARISIM) == set(a_sabitler.SEGMENTLER) | {"online"}
    en_olasi = set()
    for seg, p in SEGMENT_ARKETIP_KARISIM.items():
        assert p.shape == (len(ARKETIPLER),)
        assert abs(p.sum() - 1) < 1e-9 and (p > 0).all(), seg
        assert p.max() <= 0.60, seg
        en_olasi.add(int(p.argmax()))
    assert len(en_olasi) > 1


def test_arketip_parametreleri_tam():
    from perakende_veri.v4 import sabitler as a_sabitler
    from perakende_veri.v4.crm.sabitler import ALT_KATEGORILER, ARKETIP_PARAMETRE, ARKETIPLER

    assert ALT_KATEGORILER == [a for alts in a_sabitler.KATEGORILER.values() for a in alts]
    assert list(ARKETIP_PARAMETRE) == ARKETIPLER
    for ad, p in ARKETIP_PARAMETRE.items():
        assert len(p["kategori"]) == 17 and min(p["kategori"]) > 0, ad
        assert len(p["kalip"]) == 4 and len(p["desen"]) == 5 and len(p["fiyat_segment"]) == 3, ad
        assert abs(sum(p["yas"]) - 1) < 1e-9, ad


def test_nufus_ekle_buyur_ve_gorunumler(kucuk_girdi):
    from perakende_veri.v4.crm.nufus import nufus_baslat

    nuf = nufus_baslat(np.random.default_rng(1), kucuk_girdi)
    K0 = nuf.K
    ref = nuf.hayatta
    yeni = nuf.ekle(np.random.default_rng(2), 3 * K0 + 5, ev_magaza=0, kayit_gun=10)
    assert nuf.K == 4 * K0 + 5 and yeni.tolist() == list(range(K0, nuf.K))
    for ad in nuf.SUTUNLAR:
        assert len(getattr(nuf, ad)) == nuf.K, ad
    assert nuf.tercih_kat.shape == (nuf.K, 17)
    assert (nuf.ev_magaza[yeni] == 0).all() and (nuf.kayit_gun[yeni] == 10).all()
    assert nuf.hayatta[yeni].all() and (nuf.terk_gun[yeni] == -1).all()
    assert not nuf.gorunur_mu[yeni].any() and (nuf.gorunur_gun[yeni] == -1).all()
    # görünüm yazılabilir ve tampona yazar
    nuf.hayatta[0] = False
    assert not nuf.hayatta[0]
    del ref


def test_beden_ust_alt_gecerli(n):
    from perakende_veri.v4.crm.sabitler import ARKETIPLER

    for ad in ("beden_ust", "beden_alt"):
        b = getattr(n, ad)
        assert b.min() >= 1 and b.max() <= 5, ad
    aile = n.arketip == ARKETIPLER.index("aile_alisverisci")
    assert aile.any() and (~aile).any()
    assert n.beden_dagin[aile].mean() > n.beden_dagin[~aile].mean()


def test_tercihler_olasilik_vektoru(n):
    for ad in ("tercih_kat", "tercih_kalip", "tercih_desen", "fiyat_segment_egilim"):
        t = getattr(n, ad)
        assert np.allclose(t.sum(axis=1), 1, atol=1e-4) and (t >= 0).all(), ad
    for ad in ("kart_olasiligi", "online_payi", "terk_p", "indirim_duyarlilik"):
        v = getattr(n, ad)
        assert (v >= 0).all() and (v <= 1).all(), ad
    assert (n.ziyaret_hizi > 0).all() and (n.sepet_ort >= 1).all()


def test_karisim_hedefleri():
    """Nüfus karışımında yıllık ziyaret ~3, mağaza sepeti ~2,2 (ziyaret
    ağırlıklı), kart payı mağaza ziyaretinde %50–60 (spec §2, §8)."""
    from perakende_veri.v4.crm import nufus as N

    o = N.karisim_ozeti()
    assert 2.5 <= o["ziyaret"] <= 3.8
    assert 2.0 <= o["sepet_magaza"] <= 2.5
    assert 1.6 <= o["sepet_online"] <= 2.2
    assert 0.50 <= o["kart_magaza"] <= 0.60


def test_nufus_baslat_boyutu(kucuk_girdi, kucuk_nufus):
    from perakende_veri.v4.crm import nufus as N

    nuf = kucuk_nufus
    talep = N.fis_talebi(kucuk_girdi, 0, N.BASLAT_GUN)       # [M] beklenen fiş
    ziyaret = N.beklenen_ziyaret(nuf, N.BASLAT_GUN)           # [M] hayatta müşterilerin
    assert nuf.hayatta.all() and (nuf.kayit_gun < 0).all()
    assert ziyaret.sum() >= talep.sum()
    fiz = talep > 0
    assert (ziyaret[fiz] >= talep[fiz]).all()
    assert (ziyaret[:-1][talep[:-1] == 0] == 0).all()


def test_nufus_il_ve_kanal(kucuk_girdi, kucuk_nufus):
    nuf = kucuk_nufus
    w = kucuk_girdi.dunya
    onl = len(w.magazalar) - 1
    sehir = w.magazalar["sehir"].to_numpy()
    fiz = nuf.ev_magaza != onl
    assert (np.asarray(nuf.il_adlari)[nuf.il[fiz]] == sehir[nuf.ev_magaza[fiz]]).all()
    assert (nuf.kayit_kanali == (~fiz).astype(np.int8)).all()
    # ONL üyesinin ili fiziksel mağazaların şehirlerinden
    assert set(np.asarray(nuf.il_adlari)[nuf.il[~fiz]]) <= set(sehir[:-1])


def test_katilis_acilis_dalgasi(kucuk_girdi, kucuk_nufus):
    from perakende_veri.v4.crm.nufus import katilis_sayisi
    from perakende_veri.v4.takvim import gun_indisi

    w = kucuk_girdi.dunya
    acilan = w.magaza_olay[w.magaza_olay.olay == "acilis"]
    rng = np.random.default_rng(CRM_TOHUM)
    ilk = sonra = 0
    for r in acilan.itertuples():
        m = int(np.flatnonzero(w.magazalar.magaza_id.to_numpy() == r.magaza_id)[0])
        a = gun_indisi(r.olay_tarihi)
        if a + 168 > kucuk_girdi.D:
            continue
        ilk += sum(int(katilis_sayisi(rng, kucuk_girdi, kucuk_nufus, d)[m]) for d in range(a, a + 84))
        sonra += sum(int(katilis_sayisi(rng, kucuk_girdi, kucuk_nufus, d)[m]) for d in range(a + 84, a + 168))
    assert sonra > 0
    assert ilk >= 2 * sonra


def test_katilis_black_friday_ve_onl(kucuk_girdi, kucuk_nufus):
    from perakende_veri.v4.crm.nufus import katilis_beklenen
    from perakende_veri.v4.takvim import gun_indisi

    bf = gun_indisi("2024-11-29")
    k = katilis_beklenen(kucuk_girdi, kucuk_nufus, bf)
    k_once = katilis_beklenen(kucuk_girdi, kucuk_nufus, bf - 14)
    assert k.shape == (len(kucuk_girdi.dunya.magazalar),)
    assert k[-1] > 0 and k.sum() > 2 * k_once.sum()
    assert kucuk_nufus.magaza.katilis_carpani[bf].min() == 3.0


def test_kisisel_veri_yok():
    from perakende_veri.v4.crm.nufus import Nufus

    assert not {"ad", "eposta", "telefon"} & set(Nufus.__dataclass_fields__)


def test_gozlemlenebilir_alanlar():
    from perakende_veri.v4.crm.nufus import Nufus

    gozlem = set(Nufus.GOZLEMLENEBILIR)
    assert gozlem <= set(Nufus.SUTUNLAR)
    assert Nufus.SUTUNLAR["gorunur_gun"][0] == np.int32
    gizli = {"arketip", "terk_p", "ziyaret_hizi", "kart_olasiligi", "hayatta", "terk_gun"}
    gizli |= {a for a in Nufus.SUTUNLAR if a.startswith(("tercih_", "beden_"))}
    assert {"tercih_kat", "beden_ust", "beden_dagin"} <= gizli
    assert not gizli & gozlem


def test_kadin_payi_a_satisindan(kucuk_girdi):
    """Görev 5b: mağazanın kadın müşteri payı = A'nın o mağazadaki satışında
    Kadın / (Kadın + Erkek) birim payı + `KADIN_HEDIYE_DUZELTME`."""
    from perakende_veri.v4.crm import sabitler as S
    from perakende_veri.v4.crm.girdi import ADET, H
    from perakende_veri.v4.crm.nufus import magaza_bilgisi

    w = kucuk_girdi.dunya
    mb = magaza_bilgisi(kucuk_girdi)
    cins = w.urunler["cinsiyet"].to_numpy()
    hm, hs = np.asarray(w.hucre_magaza), np.asarray(w.hucre_sku)
    kad = np.zeros(mb.M)
    erk = np.zeros(mb.M)
    for s in kucuk_girdi.satis_gun:
        c = s[:, H].astype(np.int64)
        np.add.at(kad, hm[c], s[:, ADET] * (cins[hs[c]] == "Kadın"))
        np.add.at(erk, hm[c], s[:, ADET] * (cins[hs[c]] == "Erkek"))
    satan = kad + erk > 0
    beklenen = np.clip(kad[satan] / (kad[satan] + erk[satan]) + S.KADIN_HEDIYE_DUZELTME, 0.0, 1.0)
    assert np.allclose(mb.kadin_payi[satan], beklenen)
    assert ((mb.kadin_payi >= 0) & (mb.kadin_payi <= 1)).all()
