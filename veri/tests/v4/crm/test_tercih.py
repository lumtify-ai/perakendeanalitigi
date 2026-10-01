"""Görev 3: tercih puanı ve gizli tamamlayıcılık."""

import numpy as np
import pytest

from perakende_veri.v4.crm.sabitler import ALT_KATEGORILER, ARKETIPLER, CRM_TOHUM


@pytest.fixture(scope="module")
def n():
    """Mağaza bağlamı olmadan, her arketipten eşit sayıda müşteri."""
    from perakende_veri.v4.crm import nufus as N

    return N.arketip_ornegi(np.random.default_rng(CRM_TOHUM), 500)


def test_tamamlayici_matris_simetrik_ve_sekli():
    from perakende_veri.v4.crm.tercih import tamamlayici_matris

    m = tamamlayici_matris()
    n = len(ALT_KATEGORILER)
    assert m.shape == (n, n)
    assert np.allclose(m, m.T)


def test_tamamlayici_elbise_canta_yuksek_ayni_alt_dusuk():
    from perakende_veri.v4.crm.tercih import tamamlayici_matris

    idx = {a: i for i, a in enumerate(ALT_KATEGORILER)}
    m = np.exp(tamamlayici_matris())
    assert m[idx["Elbise"], idx["Çanta"]] > 1.0
    assert m[idx["Çanta"], idx["Elbise"]] > 1.0
    for a in ALT_KATEGORILER:
        assert m[idx[a], idx[a]] < 1.0


def test_tamamlayici_diger_ciftler_notr():
    from perakende_veri.v4.crm.tercih import TAMAMLAYICI, tamamlayici_matris

    idx = {a: i for i, a in enumerate(ALT_KATEGORILER)}
    m = np.exp(tamamlayici_matris())
    eslesen = {frozenset(k) for k in TAMAMLAYICI}
    for a in ALT_KATEGORILER:
        for b in ALT_KATEGORILER:
            if a == b or frozenset((a, b)) in eslesen:
                continue
            assert m[idx[a], idx[b]] == pytest.approx(1.0)


def test_tamamlayicilik_sepet_toplami():
    from perakende_veri.v4.crm.tercih import tamamlayici_matris, tamamlayicilik

    idx = {a: i for i, a in enumerate(ALT_KATEGORILER)}
    m = tamamlayici_matris()
    sepet = np.array([idx["Elbise"]])
    aday = np.array([idx["Çanta"], idx["Kemer"]])
    beklenen = m[sepet][:, aday].sum(axis=0)
    assert np.allclose(tamamlayicilik(sepet, aday), beklenen)
    # boş sepet: sıfır
    assert np.allclose(tamamlayicilik(np.array([], dtype=np.int64), aday), 0.0)


def test_tip_kodu_ve_ozellik_tutarli(kucuk_girdi):
    from perakende_veri.v4.crm.tercih import N_TIP, tip_kodu, tip_ozellik

    urunler = kucuk_girdi.dunya.urunler
    tip = tip_kodu(urunler)
    assert tip.shape == (len(urunler),)
    assert tip.min() >= 0 and tip.max() < N_TIP

    alt_t, seg_t, beden_t = tip_ozellik()
    assert alt_t.shape == seg_t.shape == beden_t.shape == (N_TIP,)
    # aynı tipe düşen SKU'lar aynı (alt, segment) taşımalı (aksesuarda beden hep STD)
    from perakende_veri.v4 import sabitler as a_sabitler

    alt_idx = {a: i for i, a in enumerate(ALT_KATEGORILER)}
    fs_idx = {f: i for i, f in enumerate(["giris", "orta", "premium"])}
    alt_gercek = urunler["alt_kategori"].map(alt_idx).to_numpy()
    seg_gercek = urunler["fiyat_segmenti"].map(fs_idx).to_numpy()
    assert (alt_t[tip] == alt_gercek).all()
    assert (seg_t[tip] == seg_gercek).all()

    aksesuar = urunler["alt_kategori"].isin(a_sabitler.AKSESUAR).to_numpy()
    assert (beden_t[tip[aksesuar]] != urunler["beden_sira"].to_numpy()[aksesuar] - 1).all() or aksesuar.sum() == 0


def test_tip_puani_sekli(n):
    from perakende_veri.v4.crm.tercih import N_TIP, tip_puani

    k_idx = np.arange(len(n.arketip))
    tip_idx = np.arange(N_TIP)
    p = tip_puani(n, k_idx, tip_idx)
    assert p.shape == (len(k_idx), len(tip_idx))
    assert np.isfinite(p).all()


def test_tip_puani_beden_farki_cezasi(n):
    """Beden farkı 2 olan tipin puanı farkı 0 olandan ≥ 3 log düşük
    (aile_alisverisci hariç: yüksek beden_dagin cezayı yumuşatır)."""
    from perakende_veri.v4.crm.tercih import tip_kodu, tip_ozellik, tip_puani
    from perakende_veri.v4.crm import sabitler as S

    alt_t, seg_t, beden_t = tip_ozellik()
    alt_idx = ALT_KATEGORILER.index("Tişört")  # Üst Giyim -> beden_ust
    # tam eşit beden (customer beden_ust bilinmiyor burada tek tek deneriz)
    aday = np.flatnonzero((alt_t == alt_idx) & (seg_t == seg_t[alt_t == alt_idx][0]))
    beden_vals = sorted(set(beden_t[aday].tolist()) & {0, 1, 2, 3, 4})
    assert len(beden_vals) >= 3
    tip0 = aday[beden_t[aday] == beden_vals[0]][0]
    tip2 = aday[beden_t[aday] == beden_vals[0] + 2][0]

    k_idx = np.arange(len(n.arketip))
    p = tip_puani(n, k_idx, np.array([tip0, tip2]))
    fark = p[:, 0] - p[:, 1]
    aile = ARKETIPLER.index("aile_alisverisci")
    hariç = n.arketip != aile
    # yalnız müşterinin beden_ust'unun tip0'ın bedenine (beden_vals[0]+1) tam
    # uyduğu satırlarda karşılaştırma anlamlı
    tam_uyum = n.beden_ust == (beden_vals[0] + 1)
    maske = hariç & tam_uyum
    assert maske.any()
    assert (fark[maske] >= 3.0 - 1e-6).all()


def test_tip_puani_aksesuar_beden_cezasiz(n):
    from perakende_veri.v4.crm.tercih import tip_ozellik, tip_puani

    alt_idx = ALT_KATEGORILER.index("Çanta")
    alt_t, seg_t, beden_t = tip_ozellik()
    tip_idx = np.flatnonzero(alt_t == alt_idx)[:1]
    k_idx = np.arange(len(n.arketip))
    p = tip_puani(n, k_idx, tip_idx)
    beklenen = (np.log(n.tercih_kat[:, alt_idx]) + np.log(n.fiyat_segment_egilim[:, seg_t[tip_idx[0]]]))
    assert np.allclose(p[:, 0], beklenen)


def test_urun_puani_esittir_tip_artı_sku(kucuk_girdi, n):
    """urun_puani = tip + SKU eki + cinsiyet terimi (Görev 5b: cinsiyet
    terimi eklendi)."""
    from perakende_veri.v4 import sabitler as a_sabitler
    from perakende_veri.v4.crm.tercih import (
        cinsiyet_terimi, sku_ek_puani, tip_kodu, tip_puani, urun_cinsiyet, urun_puani,
    )

    urunler = kucuk_girdi.dunya.urunler
    sku_idx = np.arange(min(50, len(urunler)))
    k_idx = np.arange(min(20, len(n.arketip)))
    oran = np.linspace(0.0, 0.3, len(sku_idx))

    toplam = urun_puani(n, k_idx, sku_idx, kucuk_girdi, oran=oran)
    tip = tip_kodu(urunler)[sku_idx]
    aks = urunler["alt_kategori"].isin(a_sabitler.AKSESUAR).to_numpy()[sku_idx]
    cins = cinsiyet_terimi(np.asarray(n.cinsiyet)[k_idx][:, None], urun_cinsiyet(urunler)[sku_idx][None, :],
                           aks[None, :])
    beklenen = tip_puani(n, k_idx, tip) + sku_ek_puani(n, k_idx, sku_idx, oran, urunler) + cins
    assert np.allclose(toplam, beklenen)
    assert toplam.shape == (len(k_idx), len(sku_idx))


def test_urun_puani_oransiz_sifir_varsayilan(kucuk_girdi, n):
    from perakende_veri.v4.crm.tercih import urun_puani

    sku_idx = np.arange(5)
    k_idx = np.arange(5)
    a = urun_puani(n, k_idx, sku_idx, kucuk_girdi)
    b = urun_puani(n, k_idx, sku_idx, kucuk_girdi, oran=np.zeros(5))
    assert np.allclose(a, b)


def test_gizli_matris_yayimlanan_yapida_degil():
    from perakende_veri.v4.crm.nufus import Nufus

    assert not any("tamamlay" in ad.lower() for ad in Nufus.SUTUNLAR)
    assert not any("tamamlay" in ad.lower() for ad in Nufus.GOZLEMLENEBILIR)


def test_sku_ek_puani_cift_kosegenle_ayni(kucuk_girdi, n):
    from perakende_veri.v4.crm.tercih import sku_ek_puani, sku_ek_puani_cift, sku_kodlari

    u = kucuk_girdi.dunya.urunler
    rng = np.random.default_rng(3)
    k = rng.integers(0, len(n.arketip), 50)
    s = rng.integers(0, len(u), 50)
    oran = rng.choice([0.0, 0.3, 0.5], 50)
    yogun = sku_ek_puani(n, k, s, oran, u)
    cift = sku_ek_puani_cift(n, k, s, oran, sku_kodlari(u))
    assert np.allclose(cift, np.diag(yogun), atol=1e-6)


# ---------------------------------------------------------------------------
# Görev 5b: müşteri × ürün cinsiyeti
# ---------------------------------------------------------------------------


def test_cinsiyet_terimi_degerleri():
    """Aynı cinsiyet ve Unisex 0; çapraz `CAPRAZ_CINSIYET_CEZA`; aksesuarda
    ceza × `CAPRAZ_CINSIYET_AKSESUAR_KAT`."""
    from perakende_veri.v4.crm import sabitler as S
    from perakende_veri.v4.crm.tercih import cinsiyet_terimi

    c = S.CAPRAZ_CINSIYET_CEZA
    assert c < 0
    mus = np.array([0, 0, 0, 1, 1, 1, 0, 1])          # 0 kadın, 1 erkek
    urun = np.array([0, 1, 2, 0, 1, 2, 1, 0])         # 0 Kadın, 1 Erkek, 2 Unisex
    aks = np.array([0, 0, 0, 0, 0, 0, 1, 1], dtype=bool)
    beklenen = [0, c, 0, c, 0, 0, c * S.CAPRAZ_CINSIYET_AKSESUAR_KAT, c * S.CAPRAZ_CINSIYET_AKSESUAR_KAT]
    assert np.allclose(cinsiyet_terimi(mus, urun, aks), beklenen)


def test_urun_cinsiyet_kodu(kucuk_girdi):
    from perakende_veri.v4 import sabitler as a_sabitler
    from perakende_veri.v4.crm.tercih import urun_cinsiyet

    u = kucuk_girdi.dunya.urunler
    kod = urun_cinsiyet(u)
    assert (np.asarray(a_sabitler.CINSIYETLER)[kod] == u["cinsiyet"].to_numpy()).all()
    # yalnız-kadın alt kategoriler hep Kadın
    assert (kod[u["alt_kategori"].isin(a_sabitler.YALNIZ_KADIN).to_numpy()] == 0).all()


def test_urun_puani_cinsiyet_capraz_dusuk(kucuk_girdi, n):
    """Aynı müşteri için, tip ve SKU eki eşitken çapraz cinsiyet ürünü
    `CAPRAZ_CINSIYET_CEZA` kadar düşük puan alır."""
    from perakende_veri.v4.crm import sabitler as S
    from perakende_veri.v4.crm.tercih import sku_ek_puani, tip_kodu, tip_puani, urun_cinsiyet, urun_puani

    u = kucuk_girdi.dunya.urunler
    from perakende_veri.v4 import sabitler as a_sabitler

    giyim = ~u["alt_kategori"].isin(a_sabitler.AKSESUAR).to_numpy()
    kod = urun_cinsiyet(u)
    sku = np.r_[np.flatnonzero(giyim & (kod == 0))[:20], np.flatnonzero(giyim & (kod == 1))[:20]]
    k_idx = np.arange(40)
    fark = urun_puani(n, k_idx, sku, kucuk_girdi) - (
        tip_puani(n, k_idx, tip_kodu(u)[sku]) + sku_ek_puani(n, k_idx, sku, np.zeros(len(sku)), u))
    capraz = np.asarray(n.cinsiyet)[k_idx][:, None] != kod[sku][None, :]
    assert np.allclose(fark[capraz], S.CAPRAZ_CINSIYET_CEZA) and np.allclose(fark[~capraz], 0.0)
    assert capraz.any() and (~capraz).any()


# ---------------------------------------------------------------------------
# Görev 5c: indirim tercihi aşama 1'de
# ---------------------------------------------------------------------------


def test_indirim_terimi_degerleri():
    """`INDIRIM_AGIRLIGI × indirim_duyarlilik × indirimli`; indirimsiz 0."""
    from perakende_veri.v4.crm import sabitler as S
    from perakende_veri.v4.crm.tercih import indirim_terimi

    assert S.INDIRIM_AGIRLIGI > 0
    d = np.array([0.0, 0.2, 0.8, 1.0, 0.8])
    ind = np.array([1, 1, 1, 1, 0], dtype=bool)
    assert np.allclose(indirim_terimi(d, ind), S.INDIRIM_AGIRLIGI * d * ind)


def test_urun_puani_indirimli_satir_terimi(kucuk_girdi, n):
    """`urun_puani(..., indirimli=)` indirimli SKU-gün satırına müşterinin
    `indirim_terimi`'ni ekler; verilmezse 0 (indirimsiz)."""
    from perakende_veri.v4.crm import sabitler as S
    from perakende_veri.v4.crm.tercih import urun_puani

    sku = np.arange(10)
    k_idx = np.arange(30)
    ind = np.arange(10) % 2 == 0
    fark = urun_puani(n, k_idx, sku, kucuk_girdi, indirimli=ind) - urun_puani(n, k_idx, sku, kucuk_girdi)
    beklenen = S.INDIRIM_AGIRLIGI * np.asarray(n.indirim_duyarlilik)[k_idx][:, None] * ind[None, :]
    assert np.allclose(fark, beklenen)
