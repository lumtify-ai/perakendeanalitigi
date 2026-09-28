"""Görev 5: günlük satış ayrıştırması (fiş, çapa, tamamlayıcı, ziyaretçi)."""

import copy

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4.crm.sabitler import CRM_TOHUM
from perakende_veri.v4.takvim import gun_indisi

GUN = gun_indisi("2023-03-15")          # çarşamba, pencere içi
UZUN_BAS = gun_indisi("2023-04-01")
UZUN_GUN = 60


def _kopya(taban):
    n = copy.copy(taban)
    n._tampon = {ad: a.copy() for ad, a in taban._tampon.items()}
    n._goster()
    return n


def _katilis(d, girdi, nuf):
    from perakende_veri.v4.crm.nufus import katilis_sayisi
    from perakende_veri.v4.crm.rastgele import crm_uretici

    rng = crm_uretici(d, "katilis")
    n = katilis_sayisi(rng, girdi, nuf, d)
    if n.sum():
        nuf.ekle(rng, int(n.sum()), np.repeat(np.arange(len(n)), n), kayit_gun=d)


def _kos(girdi, nuf, gunler, kayit=None):
    from perakende_veri.v4.crm.ayristir import Kayit, gun_ayristir
    from perakende_veri.v4.crm.yasam import Tetik

    kayit = kayit or Kayit()
    tetik = Tetik.bos(nuf.K)
    for d in gunler:
        _katilis(d, girdi, nuf)
        gun_ayristir(d, girdi, nuf, tetik, kayit)
    return kayit


@pytest.fixture(scope="module")
def _taban(kucuk_girdi):
    from perakende_veri.v4.crm.nufus import nufus_baslat

    return nufus_baslat(np.random.default_rng(CRM_TOHUM), kucuk_girdi)


@pytest.fixture(scope="module")
def tek_gun(kucuk_girdi, _taban):
    """Tek gün (GUN), taze nüfus kopyası: (nufus, kayit)."""
    nuf = _kopya(_taban)
    return nuf, _kos(kucuk_girdi, nuf, [GUN])


@pytest.fixture(scope="module")
def kosu60(kucuk_girdi, _taban):
    """60 günlük KUCUK koşu (katılış var, terk/iade yok): (nufus, kayit)."""
    nuf = _kopya(_taban)
    return nuf, _kos(kucuk_girdi, nuf, range(UZUN_BAS, UZUN_BAS + UZUN_GUN))


def _satirlar(kayit):
    fis = kayit.tablo("fis")
    sat = kayit.tablo("fis_satir")
    return fis, sat.merge(fis[["fis_id", "gun", "magaza", "musteri"]], on="fis_id", how="left")


def _a_satis(girdi, gunler):
    from perakende_veri.v4.crm.girdi import ADET, INDIRIM, TUTAR, H

    w = girdi.dunya
    parca = []
    for d in gunler:
        s = girdi.satis_gun[d]
        c = s[:, H].astype(np.int64)
        parca.append(pd.DataFrame({
            "gun": d, "magaza": np.asarray(w.hucre_magaza)[c], "sku": np.asarray(w.hucre_sku)[c],
            "adet": s[:, ADET].astype(np.int64), "tutar": s[:, TUTAR], "indirim_tutari": s[:, INDIRIM],
        }))
    return pd.concat(parca, ignore_index=True)


# ---------------------------------------------------------------------------
# Brief testleri
# ---------------------------------------------------------------------------


def test_birim_korunumu(kucuk_girdi, tek_gun):
    _, kayit = tek_gun
    _, sat = _satirlar(kayit)
    b = (sat.groupby(["gun", "magaza", "sku"])[["adet", "tutar", "indirim_tutari"]].sum()
         .sort_index())
    a = _a_satis(kucuk_girdi, [GUN]).set_index(["gun", "magaza", "sku"]).sort_index()
    assert len(a) and a.index.equals(b.index)
    assert (b["adet"].to_numpy() == a["adet"].to_numpy()).all()
    assert np.abs(b["tutar"].to_numpy() - a["tutar"].to_numpy()).max() < 0.005
    assert np.abs(b["indirim_tutari"].to_numpy() - a["indirim_tutari"].to_numpy()).max() < 0.005


def test_bos_fis_yok(tek_gun):
    _, kayit = tek_gun
    fis, sat = _satirlar(kayit)
    boyut = sat.groupby("fis_id")["adet"].sum()
    assert set(boyut.index) == set(fis["fis_id"])
    assert boyut.min() >= 1 and boyut.max() <= 8
    assert (sat["adet"] > 0).all()
    assert sat.groupby("fis_id")["sku"].nunique().eq(sat.groupby("fis_id").size()).all()
    # satir_no fiş içinde 1..n
    assert (sat.groupby("fis_id")["satir_no"].max() == sat.groupby("fis_id").size()).all()


def test_musterisiz_magaza_gunu(kucuk_girdi):
    """Uygun nüfus sıfır: yeni müşteriler (ev mağazası = fişin mağazası)
    eklenir, satış eksiksiz dağıtılır (Review Focus 1)."""
    from perakende_veri.v4.crm.nufus import Nufus, magaza_bilgisi

    nuf = Nufus.bos(magaza_bilgisi(kucuk_girdi))
    assert nuf.K == 0
    from perakende_veri.v4.crm.ayristir import Kayit, gun_ayristir
    from perakende_veri.v4.crm.yasam import Tetik

    kayit = Kayit()
    gun_ayristir(GUN, kucuk_girdi, nuf, Tetik.bos(0), kayit)
    fis, sat = _satirlar(kayit)
    assert nuf.K == len(fis) == kayit.sayac["yeni"] > 0
    assert (nuf.ev_magaza[fis["musteri"].to_numpy()] == fis["magaza"].to_numpy()).all()
    assert (nuf.kayit_gun == GUN).all()
    assert sat["adet"].sum() == _a_satis(kucuk_girdi, [GUN])["adet"].sum()


def _birlikte(sat, alt_birim, a, b, rng=None):
    """Birim düzeyinde (fiş, alt kategori) → a ve b'yi birlikte içeren fiş
    payı. `rng` verilirse alt kategoriler (gün, mağaza) içinde karıştırılır:
    fiş boyutları ve günün satışı sabitken bağımsız atamanın beklentisi."""
    adet = sat["adet"].to_numpy()
    fis = np.repeat(sat["fis_id"].to_numpy(), adet)
    alt = np.repeat(alt_birim, adet)
    if rng is not None:
        grup = np.repeat(sat["gun"].to_numpy() * 1000 + sat["magaza"].to_numpy(), adet)
        o = np.lexsort((rng.random(len(grup)), grup))
        g = np.argsort(grup, kind="stable")
        alt = alt.copy()
        alt[g] = alt[o]
    f = pd.DataFrame({"fis": fis, "a": alt == a, "b": alt == b}).groupby("fis").any()
    return (f["a"] & f["b"]).mean()


def test_tamamlayici_birlikte_gorunur(kosu60):
    """(Elbise, Çanta) birlikte görünme / bağımsız beklenti > 1,5. Bağımsız
    beklenti: fiş boyutları ve (gün, mağaza) satışı sabit, birimler fişlere
    rastgele (küçük fişlerde p_a × p_b beklentinin altında kalır: 1 birimlik
    fişte birlikte görünme olanaksız)."""
    from perakende_veri.v4.crm.sabitler import ALT_KATEGORILER

    _, kayit = kosu60
    _, sat = _satirlar(kayit)
    alt = kayit.durum.sku_alt[sat["sku"].to_numpy()]
    e, c = ALT_KATEGORILER.index("Elbise"), ALT_KATEGORILER.index("Çanta")
    gercek = _birlikte(sat, alt, e, c)
    rng = np.random.default_rng(0)
    bagimsiz = np.mean([_birlikte(sat, alt, e, c, rng) for _ in range(5)])
    assert gercek > 0 and gercek / bagimsiz > 1.5, (gercek, bagimsiz)


def test_beden_uyumu_cogunlukta(kosu60):
    nuf, kayit = kosu60
    _, sat = _satirlar(kayit)
    du = kayit.durum
    sku = sat["sku"].to_numpy()
    aks = du.sku_yon[sku] < 0
    k = sat["musteri"].to_numpy()
    yon = du.sku_yon[sku]
    mb = np.where(yon == 1, nuf.beden_alt[k], nuf.beden_ust[k])
    uyum = (np.abs(du.sku_beden[sku] - mb) == 0) & ~aks
    adet = sat["adet"].to_numpy()
    pay = adet[uyum].sum() / adet[~aks].sum()
    assert pay >= 0.70, pay
    # kayıttaki beden_uyumsuz_adet aynı tanımdan
    assert (sat["beden_uyumsuz_adet"].to_numpy() == np.where(~uyum & ~aks, adet, 0)).all()


def test_olu_musteri_fis_almaz(kucuk_girdi, _taban):
    """Aday yapısı kurulduktan sonra ölenler (artımlı yapı, ret yolu) fiş almaz."""
    nuf = _kopya(_taban)
    kayit = _kos(kucuk_girdi, nuf, [GUN])
    kurulus = kayit.durum.adaylar.kurulus_sayisi
    rng = np.random.default_rng(5)
    olu = rng.random(nuf.K) < 0.5
    nuf.hayatta[olu] = False
    nuf.terk_gun[olu] = GUN
    _kos(kucuk_girdi, nuf, [GUN + 1, GUN + 2], kayit)
    assert kayit.durum.adaylar.kurulus_sayisi == kurulus   # yeniden kurulmadı
    fis = kayit.tablo("fis")
    sonra = fis[fis["gun"] > GUN]
    assert len(sonra) and nuf.hayatta[sonra["musteri"].to_numpy()].all()


# ---------------------------------------------------------------------------
# Denetleyici kararları 2–5
# ---------------------------------------------------------------------------


def test_ziyaretci_ev_il_agirligi(kucuk_girdi, _taban):
    """k = 1 çekilişinde ev müşterisi payı = Σ ev ağırlığı / Σ ağırlık
    (ev 1, il içi 0,15; fiziksel ağırlık hız × (1 − online_payi))."""
    from perakende_veri.v4.crm.sabitler import IL_ICI_AGIRLIK
    from perakende_veri.v4.crm.ziyaretci import Adaylar

    nuf = _kopya(_taban)
    mb = nuf.magaza
    fiz = np.arange(mb.M) != mb.onl
    il_sayi = np.bincount(mb.il[fiz])
    m = int(np.flatnonzero(fiz & (il_sayi[np.maximum(mb.il, 0)] >= 2))[0])
    ad = Adaylar(nuf, GUN)
    ilde = np.flatnonzero((nuf.il == mb.il[m]) & nuf.hayatta)
    w = nuf.ziyaret_hizi[ilde] * (1 - nuf.online_payi[ilde])
    ev = nuf.ev_magaza[ilde] == m
    beklenen = (w[ev].sum()) / (w[ev].sum() + IL_ICI_AGIRLIK * w[~ev].sum())
    rng = np.random.default_rng(0)
    sec = np.array([ad.sec(nuf, m, 1, rng)[0] for _ in range(6000)])
    assert (nuf.il[sec] == mb.il[m]).all()
    gozlenen = (nuf.ev_magaza[sec] == m).mean()
    assert abs(gozlenen - beklenen) < 0.03, (gozlenen, beklenen)
    # ONL: ağırlık hız × online_payi; seçilenlerin ortalama online payı nüfusunkinden yüksek
    sec_o = ad.sec(nuf, mb.onl, 2000, rng)
    assert len(np.unique(sec_o)) == 2000
    assert nuf.online_payi[sec_o].mean() > nuf.online_payi.mean() + 0.05


def test_aday_yapisi_artimli(kucuk_girdi, _taban):
    from perakende_veri.v4.crm.sabitler import ADAY_YENIDEN_KUR_GUN
    from perakende_veri.v4.crm.ziyaretci import Adaylar

    nuf = _kopya(_taban)
    mb = nuf.magaza
    ad = Adaylar(nuf, GUN)
    m = int(np.flatnonzero(np.arange(mb.M) != mb.onl)[0])
    n_ev = ad.ev_liste[m].n
    yeni = nuf.ekle(np.random.default_rng(1), 50, ev_magaza=m, kayit_gun=GUN + 1)
    ad.guncelle(nuf, GUN + 1)
    assert ad.kurulus_sayisi == 1 and ad.ev_liste[m].n == n_ev + 50
    assert set(yeni) <= set(ad.ev_liste[m].aday[: ad.ev_liste[m].n].tolist())
    # yeni müşteriler çekilebilir: bütün eskileri öldür
    nuf.hayatta[: yeni[0]] = False
    sec = ad.sec(nuf, m, 10, np.random.default_rng(2))
    assert len(sec) == 10 and (sec >= yeni[0]).all()
    # ev mağazası değişince baştan kurulur
    nuf.ev_magaza[yeni[0]] = (m + 1) % mb.onl
    ad.guncelle(nuf, GUN + 2)
    assert ad.kurulus_sayisi == 2
    # süre dolunca baştan kurulur (ölüler atılır)
    ad.guncelle(nuf, GUN + 2 + ADAY_YENIDEN_KUR_GUN)
    assert ad.kurulus_sayisi == 3 and ad.onl_liste.n == int(nuf.hayatta.sum())


def test_fis_sayisi_ve_boyutu():
    from perakende_veri.v4.crm.ayristir import fis_boyutlari, fis_sayisi

    U = np.array([0, 1, 3, 7, 50, 400, 900])
    onl = np.array([False] * 6 + [True])
    F = fis_sayisi(U, onl, bf=False)
    F_bf = fis_sayisi(U, onl, bf=True)
    assert F[0] == 0 and F[1] == 1 and (F[1:] >= 1).all() and (F <= U).all()
    assert (F_bf <= F).all() and F_bf[5] < F[5]
    assert F[5] == round(400 / 2.2) and F[6] == round(900 / 1.8)
    rng = np.random.default_rng(0)
    fis_m = np.repeat(np.arange(len(U)), F)
    sepet = 1 + rng.gamma(4.0, 0.3, len(fis_m))
    b = fis_boyutlari(rng, fis_m, U, sepet)
    assert b.min() >= 1 and b.max() <= 8
    assert (np.bincount(fis_m, b, minlength=len(U)) == U).all()
    # sıkışık durum: U = 8F
    b2 = fis_boyutlari(rng, np.zeros(5, dtype=np.int64), np.array([40]), np.full(5, 2.0))
    assert (b2 == 8).all()
    # çarpık: 1–2 birimlik fişler çoğunlukta, tek birimlik ≥ %25, uzun sağ kuyruk
    b3 = fis_boyutlari(rng, np.zeros(2000, dtype=np.int64), np.array([4400]), np.full(2000, 2.2))
    say = np.bincount(b3, minlength=9) / 2000
    assert say[1] >= 0.25 and say[1] + say[2] > 0.6 and say[5:].sum() > 0.02


def test_fis_boyutu_musteri_sepetine_bagli(kosu60):
    nuf, kayit = kosu60
    fis, sat = _satirlar(kayit)
    boyut = sat.groupby("fis_id")["adet"].sum().reindex(fis["fis_id"]).to_numpy()
    s = nuf.sepet_ort[fis["musteri"].to_numpy()]
    assert np.corrcoef(s, boyut)[0, 1] > 0.1
    fiz = fis["kanal"].to_numpy() == 0
    assert 1.8 < boyut[fiz].mean() < 2.6


def test_tekrar_alim_tamponu(kucuk_girdi, tek_gun):
    nuf, kayit = tek_gun
    du = kayit.durum
    _, sat = _satirlar(kayit)
    k = sat["musteri"].to_numpy()
    o = du.sku_option[sat["sku"].to_numpy()]
    # her alım müşterinin tamponunda (günde ≤ 8 option'lı müşteriler)
    say = pd.Series(o).groupby(k).nunique()
    az = np.isin(k, say.index[say <= 8])
    assert (du.tekrar[k[az]] == o[az, None]).any(axis=1).all()
    # bonus: tamponda olan option +0,8 (Basic/NOS +1,2), olmayan 0
    from perakende_veri.v4.crm.sabitler import TEKRAR_BONUS, TEKRAR_BONUS_DEVAMLI

    devamli = np.flatnonzero(du.option_devamli)[0]
    koleksiyon = np.flatnonzero(~du.option_devamli)[0]
    du2 = copy.copy(du)
    du2.tekrar = np.full_like(du.tekrar, -1)
    du2.tekrar_ptr = np.zeros_like(du.tekrar_ptr)
    du2.tekrar_ekle(np.array([3, 3]), np.array([devamli, koleksiyon]))
    b = du2.tekrar_bonusu(np.array([3, 3, 3, 4]), np.array([devamli, koleksiyon, koleksiyon + 1, devamli]))
    assert b.tolist() == pytest.approx([TEKRAR_BONUS_DEVAMLI, TEKRAR_BONUS, 0.0, 0.0])
    # halka: 10 option'dan son 8'i kalır
    du2.tekrar_ekle(np.full(10, 7), np.arange(100, 110))
    assert sorted(du2.tekrar[7].tolist()) == list(range(102, 110))


def test_tekrar_alim_etkisi(kucuk_girdi, _taban):
    """Tekrar bonusu Basic/NOS option'larının aynı müşteriye yeniden
    satılma oranını bonussuz koşuya göre artırır."""
    from perakende_veri.v4.crm import sabitler as S

    def tekrar_orani(bonus):
        eski = S.TEKRAR_BONUS, S.TEKRAR_BONUS_DEVAMLI
        S.TEKRAR_BONUS = S.TEKRAR_BONUS_DEVAMLI = bonus
        try:
            nuf = _kopya(_taban)
            kayit = _kos(kucuk_girdi, nuf, range(UZUN_BAS, UZUN_BAS + 30))
        finally:
            S.TEKRAR_BONUS, S.TEKRAR_BONUS_DEVAMLI = eski
        _, sat = _satirlar(kayit)
        o = kayit.durum.sku_option[sat["sku"].to_numpy()]
        c = pd.DataFrame({"k": sat["musteri"], "o": o, "g": sat["gun"]}).drop_duplicates()
        n_gun = c.groupby(["k", "o"])["g"].nunique()
        return (n_gun > 1).sum() / len(n_gun)

    assert tekrar_orani(3.0) > tekrar_orani(0.0)


def test_kayit_alanlari_ve_saat(tek_gun):
    from perakende_veri.v4.crm.ayristir import Kayit

    _, kayit = tek_gun
    fis, sat = _satirlar(kayit)
    assert list(kayit.tablo("fis").columns) == list(Kayit.SEMA["fis"])
    assert list(kayit.tablo("fis_satir").columns) == list(Kayit.SEMA["fis_satir"])
    assert len(kayit.tablo("bos_ziyaret")) == 0
    assert (sat["orijinal_satir"] == -1).all() and (sat["islem_adet"] == 0).all()
    assert sat["satir_id"].tolist() == list(range(len(sat)))
    assert fis["fis_id"].is_unique and (fis["tip"] == 0).all()
    onl = fis["kanal"] == 1
    mag = fis.loc[~onl, "saat"]
    assert mag.min() >= 600 and mag.max() < 1320
    assert ((mag >= 18 * 60) & (mag < 21 * 60)).mean() > 0.35   # hafta içi akşam tepesi
    assert fis.loc[onl, "saat"].between(0, 1439).all() and (fis.loc[onl, "saat"] < 600).any()


def test_determinizm(kucuk_girdi, _taban, tek_gun):
    nuf = _kopya(_taban)
    kayit = _kos(kucuk_girdi, nuf, [GUN])
    a, b = kayit.tablo(), tek_gun[1].tablo()
    for ad in a:
        pd.testing.assert_frame_equal(a[ad], b[ad])
