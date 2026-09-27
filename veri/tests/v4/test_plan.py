"""Testler: Görev 10 Lumoda planı, ilk alım, ilk siparişler, plan tabloları.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §4.3 (+ §3.2, §4.1)
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-10-brief.md

`dw` yerel fixture'dır: bileşenleri `Olcek.KUCUK` ile doğrudan kurar
(Görev 11 ortak `kucuk_dunya` fixture'ını ekleyince ona döner).
"""

import dataclasses

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler
from perakende_veri.v4.cesit import cesit_ata, hucreleri_kur
from perakende_veri.v4.magaza import Olcek, alt_kume, magazalari_uret, olaylari_uret
from perakende_veri.v4.plan import (
    LambdaOzeti,
    ilk_alim,
    ilk_siparisler,
    indirim_inanci,
    lambda_ozeti,
    plan_lambda,
    plan_oznitelik_etkisi,
    plan_tablolari,
    talep_tahmini,
)
from perakende_veri.v4.rastgele import dunya_akisi
from perakende_veri.v4.takvim import gun_indisi
from perakende_veri.v4.talep import SEZON_KODLARI, lambda_kur, magaza_gun_carpani
from perakende_veri.v4.tedarik import lumoda_tedarikci_secimi, tedarikcileri_uret
from perakende_veri.v4.urun import urunleri_uret


def _dunya(olcek: Olcek) -> dict:
    rng = dunya_akisi()
    magazalar, gizli = magazalari_uret(rng)
    olaylar = olaylari_uret(rng, magazalar, gizli)
    tedarikciler, gizli_ted = tedarikcileri_uret(rng)
    maske = alt_kume(magazalar, gizli, olaylar, olcek)
    magazalar = magazalar[maske].reset_index(drop=True)
    gizli = gizli[maske].reset_index(drop=True)
    olaylar = olaylar[olaylar.magaza_id.isin(magazalar.magaza_id)].reset_index(drop=True)
    urunler, optionlar = urunleri_uret(rng, olcek)
    cesit_opt = cesit_ata(rng, magazalar, gizli, optionlar)
    hucre = hucreleri_kur(cesit_opt, urunler)
    lam, gt = lambda_kur(rng, magazalar, gizli, olaylar, optionlar, urunler, hucre)

    plan = plan_lambda(magazalar, gizli, olaylar, optionlar, urunler, hucre, gt)
    ozet = lambda_ozeti(plan, magazalar, optionlar)
    tahmin = talep_tahmini(ozet, optionlar)
    ted_idx = lumoda_tedarikci_secimi(rng, optionlar, tedarikciler, gizli_ted, tahmin)
    alim, teshis = ilk_alim(ozet, optionlar, ted_idx, gizli_ted, teshis=True)
    siparisler = ilk_siparisler(
        np.random.default_rng(5), optionlar, urunler, alim, ted_idx, tedarikciler, gizli_ted
    )
    tablolar = plan_tablolari(np.random.default_rng(6), ozet, lam, magazalar, optionlar, alim)
    return {
        "magazalar": magazalar, "gizli": gizli, "olaylar": olaylar, "urunler": urunler,
        "optionlar": optionlar, "hucre": hucre, "lam": lam, "gt": gt, "plan": plan,
        "ozet": ozet, "tahmin": tahmin, "tedarikciler": tedarikciler, "gizli_ted": gizli_ted,
        "ted_idx": ted_idx, "alim": alim, "teshis": teshis, "siparisler": siparisler,
        "tablolar": tablolar,
    }


@pytest.fixture(scope="module")
def dw():
    return _dunya(Olcek.KUCUK)


@pytest.fixture(scope="module")
def t(dw):
    return dw["tablolar"]


@pytest.fixture(scope="module")
def optionlar(dw):
    return dw["optionlar"]


def _sezonluk(optionlar) -> np.ndarray:
    return (optionlar["sezon_kodu"] != sabitler.DEVAMLI).to_numpy()


# ---------------------------------------------------------------------------
# Plan λ: ne bilir, ne bilmez
# ---------------------------------------------------------------------------


def test_plan_surprizi_bilmez(dw):
    """Sürpriz ve sürüklenme dizilerini değiştirmek plan λ'yı değiştirmez."""
    gt2 = dict(dw["gt"])
    gt2["surpriz"] = dw["gt"]["surpriz"] * 3.0
    gt2["suruklenme"] = dw["gt"]["suruklenme"] * 1.7
    gt2["cekicilik"] = dw["gt"]["cekicilik"] * 2.0
    plan2 = plan_lambda(
        dw["magazalar"], dw["gizli"], dw["olaylar"], dw["optionlar"], dw["urunler"], dw["hucre"], gt2
    )
    for d in (100, 400, 700, 1000):
        assert np.array_equal(dw["plan"].gun(d), plan2.gun(d))
    # ama gerçek λ'dan farklıdır (bilmediği bir şey var)
    assert not np.allclose(dw["plan"].gun(400), dw["lam"].gun(400))


def test_plan_trend_gecikmesi(dw):
    """SS25 planındaki öznitelik etkisi = SS24'ün gerçek etkisi (oversize
    dahil bütün anahtarlar); AW23 AW22'ninkini kullanır; ilk sezonlar
    yürüyüşsüz başlangıç katsayılarını."""
    gercek = dw["gt"]["oznitelik_etkisi"]
    plan_e = plan_oznitelik_etkisi(dw["gt"], dw["optionlar"])
    s = {k: i for i, k in enumerate(SEZON_KODLARI)}
    assert np.allclose(plan_e[s["SS25"]], gercek[s["SS24"]])
    assert np.allclose(plan_e[s["AW25"]], gercek[s["AW24"]])
    assert np.allclose(plan_e[s["AW23"]], gercek[s["AW22"]])
    assert np.allclose(plan_e[s["AW22"]], gercek[s["AW22"]])  # AW22 = başlangıç katsayısı
    assert not np.allclose(plan_e[s["SS23"]], gercek[s["SS23"]])  # yürüyüş bilinmez

    # oversize: SS25 planında SS24 kadar, gerçekte SS25 kadar (trend yükselir)
    opt = dw["optionlar"]
    over = (opt["kalip"] == "oversize").to_numpy()
    if over.any() and (~over).any():
        lg = np.log
        plan_fark = lg(plan_e[s["SS25"]][:, over]).mean() - lg(plan_e[s["SS25"]][:, ~over]).mean()
        gercek_fark = lg(gercek[s["SS25"]][:, over]).mean() - lg(gercek[s["SS25"]][:, ~over]).mean()
        assert plan_fark < gercek_fark


def test_plan_iklim_zincir_ortalamasi(dw):
    """Plan bütün mağazalarda zincir ortalaması mevsim eğrisini kullanır."""
    assert (dw["plan"].magaza_iklim == 4).all()
    assert (dw["lam"].magaza_iklim[:-1] < 4).all()


def test_plan_kapalilik_bilir_kayma_bilmez(dw):
    beklenen = magaza_gun_carpani(dw["magazalar"], dw["gizli"], dw["olaylar"], magaza_toplam=None)
    assert np.array_equal(dw["plan"].magaza_gun, beklenen)
    # kapalı günler 0 (açılış öncesi)
    acilis = dw["olaylar"][dw["olaylar"].olay == "acilis"]
    if len(acilis):
        r = acilis.iloc[0]
        m = int(np.flatnonzero(dw["magazalar"].magaza_id == r.magaza_id)[0])
        assert dw["plan"].magaza_gun[gun_indisi(r.olay_tarihi) - 1, m] == 0.0


def test_plan_indirim_inanci(dw):
    """İndirimin ilk 28 gününde 0,7^−1,7, sonra 0,5^−1,7, öncesinde 1."""
    opt = dw["optionlar"]
    carpan, oran = indirim_inanci(opt)
    o = int(np.flatnonzero(_sezonluk(opt))[0])
    ind, cik = int(opt.at[o, "indirim_gun"]), int(opt.at[o, "cikis_gun"])
    assert carpan[ind - 1, o] == 1.0 and oran[ind - 1, o] == 0.0
    assert carpan[ind + 5, o] == pytest.approx(0.7 ** -1.7)
    assert carpan[ind + 40, o] == pytest.approx(0.5 ** -1.7)
    assert oran[ind + 40, o] == pytest.approx(0.5)
    assert carpan[cik, o] == 1.0
    dev = int(np.flatnonzero(~_sezonluk(opt))[0])
    assert (carpan[:, dev] == 1.0).all()


def test_plan_toplam_makul(dw):
    """Naif ama saçma değil: 2024 plan λ toplamı gerçek λ toplamının ±%25'i
    (ikisi de planlanan indirim yolunda)."""
    gercek_ozet = lambda_ozeti(dw["lam"], dw["magazalar"], dw["optionlar"], indirimli=True)
    bas, bit = gun_indisi("2024-01-01"), gun_indisi("2025-01-01")
    p = dw["ozet"].gunluk[bas:bit].sum()
    g = gercek_ozet.gunluk[bas:bit].sum()
    assert 0.75 < p / g < 1.25, p / g


# ---------------------------------------------------------------------------
# İlk alım
# ---------------------------------------------------------------------------


def _moq(dw) -> np.ndarray:
    mense = dw["gizli_ted"]["mense"].to_numpy()[dw["ted_idx"]]
    return np.array([sabitler.MENSE_V4[m]["moq"] for m in mense])


def test_ilk_alim_moq_ve_kapasite(dw):
    alim, opt = dw["alim"], dw["optionlar"]
    sez = _sezonluk(opt)
    moq = _moq(dw)
    assert (alim[sez] >= moq[sez]).all()
    assert (alim % 10 == 0).all()
    teshis = dw["teshis"]
    kap = dw["gizli_ted"]["kapasite_sezon_adet"].to_numpy()
    df = pd.DataFrame({"t": dw["ted_idx"], "s": opt["sezon_kodu"], "a": alim,
                       "asim": teshis["kapasite_asimi"].to_numpy(), "moq": moq})
    for (ti, s), g in df[sez].groupby(["t", "s"]):
        izin = kap[ti] + g.loc[g.asim, "moq"].sum()
        assert g.a.sum() <= izin, (ti, s)


def test_ilk_alim_talep_tahminiyle_tutarli(dw):
    """Kapasiteye takılmayan option'da ilk alım = max(MOQ, ⌈tahmin/10⌉·10)."""
    alim, tahmin, opt = dw["alim"], dw["tahmin"], dw["optionlar"]
    serbest = _sezonluk(opt) & ~dw["teshis"]["kapasite_kirpildi"].to_numpy()
    beklenen = np.maximum(_moq(dw), np.ceil(tahmin / 10 - 1e-9) * 10)
    assert np.array_equal(alim[serbest], beklenen[serbest].astype(np.int64))
    # tahmin = sezon planı ÷ 0,80, sezon planı > 0
    assert (tahmin[_sezonluk(opt)] > 0).all()


def test_ilk_alim_kapasite_kirpar(dw):
    """Yapay dar kapasite: toplam kapasiteyi aşmaz; kalan MOQ'nun altına
    inince MOQ sipariş edilir ve `kapasite_asimi` işaretlenir."""
    gizli = dw["gizli_ted"].copy()
    gizli["kapasite_sezon_adet"] = 2_000
    alim, teshis = ilk_alim(dw["ozet"], dw["optionlar"], dw["ted_idx"], gizli, teshis=True)
    sez = _sezonluk(dw["optionlar"])
    moq = _moq(dw)
    assert teshis["kapasite_asimi"].any()
    assert (alim[sez] >= moq[sez]).all() and (alim % 10 == 0).all()
    df = pd.DataFrame({"t": dw["ted_idx"], "s": dw["optionlar"]["sezon_kodu"], "a": alim,
                       "asim": teshis["kapasite_asimi"].to_numpy()})[sez]
    for _, g in df.groupby(["t", "s"]):
        assert g.loc[~g.asim, "a"].sum() <= 2_000
    assert (alim[teshis["kapasite_asimi"].to_numpy()] == moq[teshis["kapasite_asimi"].to_numpy()]).all()


def test_devamli_ilk_alim_sifir(dw):
    dev = ~_sezonluk(dw["optionlar"])
    assert dev.any()
    assert (dw["alim"][dev] == 0).all()
    assert (dw["tahmin"][dev] == 0).all()
    assert not any(dw["optionlar"].at[s["option"], "sezon_kodu"] == sabitler.DEVAMLI
                   for s in dw["siparisler"])


# ---------------------------------------------------------------------------
# İlk siparişler
# ---------------------------------------------------------------------------


def test_planlanan_teslim_lansmandan_once(dw):
    opt, ted = dw["optionlar"], dw["tedarikciler"]
    siparisler = dw["siparisler"]
    assert len(siparisler) == int(_sezonluk(opt).sum())
    pay = np.asarray(sabitler.BEDEN_PAYLARI_ZINCIR)
    urunler = dw["urunler"]
    for s in siparisler:
        o = s["option"]
        assert s["tip"] == "ilk"
        assert s["tedarikci"] == dw["ted_idx"][o]
        lansman = int(opt.at[o, "lansman_gun"])
        assert s["planlanan_gun"] == lansman - 7
        assert s["siparis_gun"] == s["planlanan_gun"] - 7 * int(ted.at[s["tedarikci"], "ilk_siparis_hafta"])
        m = sabitler.MENSE_V4[ted.at[s["tedarikci"], "mense"]]
        assert m["sapma_min"] <= s["gerceklesen_gun"] - s["planlanan_gun"] <= m["sapma_maks"]
        assert int(np.sum(s["adetler"])) == dw["alim"][o]
        assert (urunler.option_id.to_numpy()[s["skular"]] == opt.at[o, "option_id"]).all()
        assert len(s["hatali"]) == len(s["skular"])
        assert (s["hatali"] >= 0).all() and (s["hatali"] <= s["adetler"]).all()
        assert 0 < s["numune"] <= s["adetler"].sum()
        if len(s["skular"]) == 5:  # zincir beden eğrisi, en büyük kalan
            hedef = dw["alim"][o] * pay
            assert np.abs(s["adetler"] - hedef).max() < 1.0
    # hatalı gerçekten çekiliyor
    assert sum(int(s["hatali"].sum()) for s in siparisler) > 0


def test_ilk_siparisler_deterministik(dw):
    a = ilk_siparisler(np.random.default_rng(5), dw["optionlar"], dw["urunler"], dw["alim"],
                       dw["ted_idx"], dw["tedarikciler"], dw["gizli_ted"])
    for x, y in zip(a, dw["siparisler"]):
        assert x["gerceklesen_gun"] == y["gerceklesen_gun"]
        assert np.array_equal(x["hatali"], y["hatali"])


# ---------------------------------------------------------------------------
# Plan tabloları
# ---------------------------------------------------------------------------


def test_mfp_sutunlar(t):
    assert set(t["mfp_plan"].columns) >= {
        "sezon_kodu", "ay", "kanal", "ust_kategori", "satis_tutari", "adet",
        "brut_marj", "donem_sonu_stok", "otb",
    }


def test_mfp_otb_ozdesligi(t):
    """OTB = satış planı + dönem sonu stok − dönem başı stok; sezon sonunda stok 0."""
    mfp = t["mfp_plan"].sort_values(["sezon_kodu", "kanal", "ust_kategori", "ay"])
    for _, g in mfp.groupby(["sezon_kodu", "kanal", "ust_kategori"]):
        bas = np.concatenate([[0], g.donem_sonu_stok.to_numpy()[:-1]])
        assert np.array_equal(g.otb.to_numpy(), g.adet.to_numpy() + g.donem_sonu_stok.to_numpy() - bas)
        assert g.donem_sonu_stok.iloc[-1] == 0
    assert set(mfp.kanal) == {"Mağaza", "Online"}
    assert (mfp.satis_tutari > 0).any() and (mfp.brut_marj <= mfp.satis_tutari).all()


def test_mfp_gecen_yil_formulu(dw, t):
    """SS25 MFP adedi / (SS24 gerçek beklenen talep × 0,85 × 1,06) üst
    kategori başına iyimserlik aralığında (1,03–1,12)."""
    gercek = lambda_ozeti(dw["lam"], dw["magazalar"], dw["optionlar"], indirimli=True)
    opt = dw["optionlar"]
    mfp = t["mfp_plan"]
    ss24 = SEZON_KODLARI.index("SS24")
    sezon_o = opt["sezon_kodu"].map({k: i for i, k in enumerate(SEZON_KODLARI)}).fillna(-1).to_numpy()
    gun_s = gercek.gun_sezonu
    for ust in sorted(opt.ust_kategori.unique()):
        u = (opt.ust_kategori == ust).to_numpy()
        seas = gercek.gunluk[:, :, u & (sezon_o == ss24)].sum()
        dev = gercek.gunluk[gun_s == ss24][:, :, u & (sezon_o < 0)].sum()
        onceki = (seas + dev) * 0.85 * 1.06
        plan = mfp[(mfp.sezon_kodu == "SS25") & (mfp.ust_kategori == ust)].adet.sum()
        if onceki > 200:
            assert 1.03 - 0.02 <= plan / onceki <= 1.12 + 0.02, (ust, plan / onceki)


def test_range_plan_option_sayisi(t, optionlar):
    rp = t["range_plan"]
    assert set(rp.columns) >= {"sezon_kodu", "alt_kategori", "fiyat_segmenti", "line",
                               "option_sayisi", "ortalama_fiyat", "derinlik"}
    gercek = int(_sezonluk(optionlar).sum())
    assert abs(rp.option_sayisi.sum() - gercek) <= 0.10 * gercek
    assert (rp.option_sayisi >= 1).all()
    assert set(rp.line) <= {"Collection", "Outlet"}


def test_magaza_plan(dw, t):
    mp = t["magaza_plan"]
    assert set(mp.columns) >= {"sezon_kodu", "magaza_id", "ust_kategori", "satis_hedefi"}
    assert "ONL" in set(mp.magaza_id)
    assert (mp.satis_hedefi >= 0).all()
    # kapanan mağaza kapanıştan sonra lansmanı olan sezonlarda 0 hedef
    kap = dw["olaylar"][dw["olaylar"].olay == "kapanis"]
    for _, r in kap.iterrows():
        sonra = [k for k, s in sabitler.SEZONLAR.items()
                 if pd.Timestamp(s["dalgalar"][0]) > r.olay_tarihi]
        x = mp[(mp.magaza_id == r.magaza_id) & mp.sezon_kodu.isin(sonra)]
        assert x.satis_hedefi.sum() == 0


def test_plan_tablolari_gizli_sizdirmaz(t):
    yasak = {"surpriz", "segment", "esneklik", "oznitelik_etkisi", "hatali_orani", "kapasite_sezon_adet"}
    for df in t.values():
        assert not (set(df.columns) & yasak)
