"""Görev 7: günlük döngü (katılış → terk → mağaza olayı → ayrıştırma →
işlem → iade → boş ziyaret → kart okutma) ve kart okutma."""

import dataclasses

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler as a_sabitler
from perakende_veri.v4.crm.sabitler import CRM_TOHUM

ONEK_PAY = 40   # önek: ilk kapanış günü + bu kadar gün


def _kapanis_gunleri(girdi) -> dict:
    """{mağaza indisi: kapanış günü}, koşulan günlerdeki kapanışlar."""
    from perakende_veri.v4.takvim import gun_indisi

    w = girdi.dunya
    idx = {mid: i for i, mid in enumerate(w.magazalar["magaza_id"])}
    return {idx[r.magaza_id]: gun_indisi(r.olay_tarihi) for r in w.magaza_olay.itertuples()
            if r.olay == "kapanis" and 0 < gun_indisi(r.olay_tarihi) < girdi.D}


def _onek_gun(girdi) -> int:
    """İlk kapanış + ONEK_PAY (KUCUK: 441 + 40 = 481): önek bir mağaza
    olayını (ev_kapanisi) ve birkaç ay başı terkini içerir."""
    return min(_kapanis_gunleri(girdi).values()) + ONEK_PAY


@pytest.fixture(scope="module")
def onek(kucuk_girdi):
    """İlk N gün (`_onek_gun`), iki bağımsız koşu (determinizm ve önek)."""
    from perakende_veri.v4.crm.dongu import crm_simule_et

    N = _onek_gun(kucuk_girdi)
    return crm_simule_et(kucuk_girdi, gun_sayisi=N), crm_simule_et(kucuk_girdi, gun_sayisi=N)


@pytest.fixture(scope="module")
def fis(kucuk_crm):
    return kucuk_crm.tablo("fis")


@pytest.fixture(scope="module")
def satir(kucuk_crm, fis):
    sat = kucuk_crm.tablo("fis_satir")
    return sat.merge(fis[["fis_id", "gun", "magaza", "musteri", "tip", "kart"]], on="fis_id", how="left")


def _acik(girdi):
    from perakende_veri.v4.motor.durum import magaza_takvimi

    acik, _ = magaza_takvimi(girdi.dunya, girdi.D)
    return acik


# ---------------------------------------------------------------------------


def test_fis_satir_toplami_a_temiz_satis(kucuk_girdi, satir):
    """Pencerede (mağaza × gün × SKU) adet, tutar, indirim_tutari A'nın
    temiz `satis`'iyle (iadeler dahil) kuruşu kuruşuna."""
    from perakende_veri.v4.tablolar import pencere
    from perakende_veri.v4.uret import yayimla

    w = kucuk_girdi.dunya
    a = yayimla(w, kucuk_girdi.ham, kirli=False)["satis"]
    bas, son = pencere()
    b = satir[(satir["gun"] >= bas) & (satir["gun"] <= son)]
    b = pd.DataFrame({
        "tarih": pd.Timestamp(a_sabitler.ISINMA_BASLANGIC) + pd.to_timedelta(b["gun"].to_numpy(np.int64), unit="D"),
        "magaza_id": w.magazalar["magaza_id"].to_numpy().astype(str)[b["magaza"].to_numpy(np.int64)],
        "urun_id": w.urunler["urun_id"].to_numpy().astype(str)[b["sku"].to_numpy(np.int64)],
        "adet": b["adet"].to_numpy(np.int64), "tutar": b["tutar"].to_numpy(), "indirim_tutari": b["indirim_tutari"].to_numpy(),
    })
    a = pd.DataFrame({"tarih": a["tarih"], "magaza_id": a["magaza_id"].astype(str), "urun_id": a["urun_id"].astype(str),
                      "adet": a["adet"].astype(np.int64), "tutar": a["tutar"], "indirim_tutari": a["indirim_tutari"]})
    anahtar = ["tarih", "magaza_id", "urun_id"]
    at = a.groupby(anahtar)[["adet", "tutar", "indirim_tutari"]].sum().sort_index()
    bt = b.groupby(anahtar)[["adet", "tutar", "indirim_tutari"]].sum().sort_index()
    assert at.index.equals(bt.index)
    assert (at["adet"].to_numpy() == bt["adet"].to_numpy()).all()
    assert np.abs(at["tutar"].to_numpy() - bt["tutar"].to_numpy()).max() < 0.005
    assert np.abs(at["indirim_tutari"].to_numpy() - bt["indirim_tutari"].to_numpy()).max() < 0.005


def test_butun_gunler_satis_ve_iade_adedi(kucuk_girdi, satir):
    """Isınma dahil bütün günlerde (gün, mağaza, SKU, işaret) adet A ile aynı."""
    from perakende_veri.v4.crm.girdi import ADET, H

    w = kucuk_girdi.dunya
    hm, hs = np.asarray(w.hucre_magaza), np.asarray(w.hucre_sku)
    parca = []
    for kaynak in (kucuk_girdi.satis_gun, kucuk_girdi.iade_gun):
        for d, s in enumerate(kaynak):
            if len(s):
                c = s[:, H].astype(np.int64)
                parca.append(pd.DataFrame({"gun": d, "magaza": hm[c], "sku": hs[c], "adet": s[:, ADET].astype(np.int64)}))
    a = pd.concat(parca, ignore_index=True)
    a["iade"] = a["adet"] < 0
    b = satir[["gun", "magaza", "sku", "adet"]].astype(np.int64)
    b["iade"] = b["adet"] < 0
    anahtar = ["gun", "magaza", "sku", "iade"]
    at = a.groupby(anahtar)["adet"].sum().sort_index()
    bt = b.groupby(anahtar)["adet"].sum().sort_index()
    assert at.index.equals(bt.index)
    assert (at.to_numpy() == bt.to_numpy()).all()


def test_kapali_magazada_satis_fisi_yok(kucuk_girdi, fis):
    """Açılış öncesi, kapanış sonrası ve tadilatta satış fişi yok; kapalı
    mağaza-günündeki iade fişi yalnız A'nın o mağaza-günde iade satırı
    varsa (A iadeyi satışın hücresine yazar; Review Focus 2 ve 4)."""
    from perakende_veri.v4.crm.girdi import H

    acik = _acik(kucuk_girdi)
    g, m, tip = (fis[c].to_numpy(np.int64) for c in ("gun", "magaza", "tip"))
    kapali = ~acik[g, m]
    assert not (kapali & (tip == 0)).any()
    # testin anlamı: KUCUK'ta kapanan ve tadilata giren mağaza var
    olay = kucuk_girdi.dunya.magaza_olay
    assert {"kapanis", "tadilat"} <= set(olay["olay"])
    assert (~acik).any()
    hm = np.asarray(kucuk_girdi.dunya.hucre_magaza)
    a_iade = {(d, int(x)) for d, r in enumerate(kucuk_girdi.iade_gun) for x in np.unique(hm[r[:, H].astype(np.int64)])}
    b_iade = set(zip(g[kapali & (tip == 1)].tolist(), m[kapali & (tip == 1)].tolist()))
    assert b_iade <= a_iade


def test_terk_sonrasi_fis_yok(kucuk_crm, fis, satir):
    """Terk günü ve sonrasında satış fişi yok; terk sonrası iade fişi yalnız
    terkten önceki bir satışın iadesi."""
    tg = kucuk_crm.nufus.terk_gun
    assert (tg >= 0).sum() > 1000
    k = fis["musteri"].to_numpy(np.int64)
    g = fis["gun"].to_numpy(np.int64)
    olu = tg[k] >= 0
    sonra = olu & (g >= tg[k])
    assert not (sonra & (fis["tip"].to_numpy() == 0)).any()
    ia = satir[satir["adet"] < 0]
    ia = ia[(tg[ia["musteri"].to_numpy(np.int64)] >= 0)
            & (ia["gun"].to_numpy() >= tg[ia["musteri"].to_numpy(np.int64)])]
    orj = satir.set_index("satir_id").loc[ia["orijinal_satir"].to_numpy(), "gun"].to_numpy()
    assert (orj < tg[ia["musteri"].to_numpy(np.int64)]).all()
    # ölüler boş ziyarete de gelmez
    bz = kucuk_crm.tablo("bos_ziyaret")
    kb = bz["musteri"].to_numpy(np.int64)
    assert not ((tg[kb] >= 0) & (bz["gun"].to_numpy() >= tg[kb])).any()


def test_katilistan_once_fis_yok(kucuk_crm, fis):
    kg = kucuk_crm.nufus.kayit_gun
    assert (fis["gun"].to_numpy() >= kg[fis["musteri"].to_numpy(np.int64)]).all()
    bz = kucuk_crm.tablo("bos_ziyaret")
    assert (bz["gun"].to_numpy() >= kg[bz["musteri"].to_numpy(np.int64)]).all()


def test_kart_okutma(kucuk_crm, fis, satir):
    """ONL hep kimlikli; iade fişi orijinal satış fişinin kart durumunu
    alır; mağazada kart payı makul; `gorunur_mu`/`gorunur_gun` ilk kimlikli
    olay."""
    nuf = kucuk_crm.nufus
    onl = nuf.magaza.onl
    kart = fis["kart"].to_numpy()
    m = fis["magaza"].to_numpy()
    assert kart[m == onl].all()
    fiz_satis = (m != onl) & (fis["tip"].to_numpy() == 0)
    pay = kart[fiz_satis].mean()
    assert 0.35 < pay < 0.75, pay
    # kart olasılığı yüksek müşterilerde kart payı yüksek
    p = nuf.kart_olasiligi[fis["musteri"].to_numpy(np.int64)[fiz_satis]]
    assert kart[fiz_satis][p > 0.7].mean() > kart[fiz_satis][p < 0.3].mean() + 0.3
    # iade fişi ↔ orijinal
    ia = satir[satir["adet"] < 0]
    orj_fis = satir.set_index("satir_id").loc[ia["orijinal_satir"].to_numpy(), "fis_id"].to_numpy()
    kart_fis = kucuk_crm.kart
    beklenen = pd.Series(kart_fis[orj_fis]).groupby(ia["fis_id"].to_numpy()).max()
    assert (kart_fis[beklenen.index.to_numpy()] == beklenen.to_numpy()).all()
    # görünürlük
    ilk = fis[fis["kart"]].groupby("musteri")["gun"].min()
    gor = np.zeros(nuf.K, dtype=bool)
    gor[ilk.index.to_numpy()] = True
    assert (nuf.gorunur_mu == gor).all()
    gg = np.full(nuf.K, -1)
    gg[ilk.index.to_numpy()] = ilk.to_numpy()
    assert (nuf.gorunur_gun == gg).all()


def test_ltv_2026(kucuk_crm):
    ltv = kucuk_crm.ltv
    nuf = kucuk_crm.nufus
    assert len(ltv) == nuf.K
    assert np.isfinite(kucuk_crm.fiyat_ort).all() and (kucuk_crm.fiyat_ort > 0).all()
    assert (ltv["hayatta_olasiligi"].to_numpy() == nuf.hayatta).all()
    assert not ltv["geri_gelecek_2026"].to_numpy()[~nuf.hayatta].any()
    assert ltv["gerceklesen_harcama_2026"].sum() > 0
    # makulluk: beklenen 2026 harcaması (hayattakiler) aşırı çarpık değil
    h = np.sort(ltv["beklenen_harcama_2026"].to_numpy()[nuf.hayatta])
    ust = h[-max(1, len(h) // 100):].sum() / h.sum()
    assert ust < 0.15, ust
    assert np.percentile(h, 99) / np.median(h) < 20, np.percentile(h, 99) / np.median(h)


def test_determinizm(onek):
    from perakende_veri.v4.crm.dongu import crm_ozeti

    a, b = onek
    assert crm_ozeti(a) == crm_ozeti(b)
    assert crm_ozeti(a) != ""


def test_gun_sayisi_onek(kucuk_girdi, kucuk_crm, onek):
    """İlk N günlük koşu (N = ilk kapanış + 40) tam koşunun ilk N gününe
    birebir eşit; önekte bir kapanış ve terk var."""
    kisa, _ = onek
    N = kisa.D
    kap = _kapanis_gunleri(kucuk_girdi)
    assert min(kap.values()) < N
    assert (kisa.nufus.terk_gun >= 0).sum() > 1000
    assert kisa.tetik.ev_kapandi.any() or kisa.tetik.ev_gecti.any()
    for ad in ("fis", "fis_satir", "bos_ziyaret"):
        k = kisa.tablo(ad)
        t = kucuk_crm.tablo(ad)
        if ad == "fis_satir":
            t = t[t["fis_id"] < len(kisa.kart)]
        else:
            t = t[t["gun"] < N]
        pd.testing.assert_frame_equal(k.reset_index(drop=True), t.reset_index(drop=True))
    assert len(kisa.kart) > 0
    K = kisa.nufus.K
    for ad in ("arketip", "kayit_gun", "il", "yas_grubu", "cinsiyet", "kart_olasiligi", "ziyaret_hizi", "terk_p"):
        assert np.array_equal(getattr(kisa.nufus, ad), getattr(kucuk_crm.nufus, ad)[:K]), ad
    tg = kucuk_crm.nufus.terk_gun[:K]
    assert np.array_equal(kisa.nufus.terk_gun, np.where(tg < N, tg, -1))
    gg = kucuk_crm.nufus.gorunur_gun[:K]
    assert np.array_equal(kisa.nufus.gorunur_gun, np.where(gg < N, gg, -1))
    # kapanış tetikleri: N'den sonra kapanan mağazanın (N'deki) ev
    # müşterileri tam koşuda sonradan değişebilir, onlar hariç
    sonra = [m for m, g in kap.items() if g >= N]
    sabit = ~np.isin(kisa.nufus.ev_magaza, sonra)
    assert sabit.mean() > 0.6   # KUCUK: 0,80 (3 kapanış N'den sonra)
    assert (kisa.tetik.ev_kapandi | kisa.tetik.ev_gecti)[sabit].any()
    for ad in ("ev_kapandi", "ev_gecti"):
        a, b = getattr(kisa.tetik, ad), getattr(kucuk_crm.tetik, ad)[:K]
        assert np.array_equal(a[sabit], b[sabit]), ad
    assert np.array_equal(kisa.nufus.ev_magaza[sabit], kucuk_crm.nufus.ev_magaza[:K][sabit])


def test_satissiz_gunde_aday_yapisi_guncellenir(kucuk_girdi):
    """Satışsız günde `gun_ayristir` erken dönse de aday yapısı yeni
    müşterileri alır (boş ziyaret güncel adaylardan seçer)."""
    from perakende_veri.v4.crm.ayristir import Kayit, gun_ayristir
    from perakende_veri.v4.crm.nufus import nufus_baslat
    from perakende_veri.v4.crm.yasam import Tetik

    d0 = 100
    nuf = nufus_baslat(np.random.default_rng(CRM_TOHUM), kucuk_girdi)
    tetik = Tetik.bos(nuf.K)
    kayit = Kayit()
    gun_ayristir(d0, kucuk_girdi, nuf, tetik, kayit)
    nuf.ekle(np.random.default_rng(1), 50, ev_magaza=0, kayit_gun=d0 + 1)
    satis = list(kucuk_girdi.satis_gun)
    satis[d0 + 1] = satis[d0 + 1][:0]
    bos = dataclasses.replace(kucuk_girdi, satis_gun=satis)
    gun_ayristir(d0 + 1, bos, nuf, tetik, kayit)
    assert kayit.durum.adaylar.K == nuf.K
