"""Görev 6: işlem indirimi, iade bağlama, boş ziyaret."""

import copy

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler as a_sabitler
from perakende_veri.v4.crm.sabitler import CRM_TOHUM

GUN_SAYISI = 32
IADE_ILK = max(a_sabitler.IADE_GECIKME_MAGAZA, a_sabitler.IADE_GECIKME_ONLINE)


def _kopya(taban):
    n = copy.copy(taban)
    n._tampon = {ad: a.copy() for ad, a in taban._tampon.items()}
    n._goster()
    return n


def _kapanan_magaza(girdi):
    """KUCUK'ta 2023 içinde kapanan ilk fiziksel mağaza ve kapanış günü."""
    from perakende_veri.v4.crm.nufus import magaza_bilgisi

    mb = magaza_bilgisi(girdi)
    kap = mb.kapanis_gun.copy()
    kap[kap < 400] = 10**6
    m = int(np.argmin(kap))
    assert kap[m] < 10**5
    return m, int(kap[m])


@pytest.fixture(scope="module")
def kosu(kucuk_girdi):
    """Kapanış etrafında tam günlük akış (katılış → ayrıştırma → işlem →
    iade → boş ziyaret): (bas, nufus, tetik, kayit, kapanan mağaza, gün)."""
    from perakende_veri.v4.crm.ayristir import Kayit, gun_ayristir
    from perakende_veri.v4.crm.iade import bos_ziyaret, iade_bagla, islem_indirimi_yerlestir
    from perakende_veri.v4.crm.nufus import katilis_sayisi, nufus_baslat
    from perakende_veri.v4.crm.rastgele import crm_uretici
    from perakende_veri.v4.crm.yasam import Tetik

    m, kg = _kapanan_magaza(kucuk_girdi)
    bas = kg - IADE_ILK - 2
    nuf = _kopya(nufus_baslat(np.random.default_rng(CRM_TOHUM), kucuk_girdi))
    tetik = Tetik.bos(nuf.K)
    kayit = Kayit()
    for d in range(bas, bas + GUN_SAYISI):
        rng = crm_uretici(d, "katilis")
        n = katilis_sayisi(rng, kucuk_girdi, nuf, d)
        if n.sum():
            nuf.ekle(rng, int(n.sum()), np.repeat(np.arange(len(n)), n), kayit_gun=d)
        gun_ayristir(d, kucuk_girdi, nuf, tetik, kayit)
        islem_indirimi_yerlestir(d, kucuk_girdi, nuf, kayit)
        if d >= bas + IADE_ILK:
            iade_bagla(d, kucuk_girdi, nuf, tetik, kayit)
        bos_ziyaret(d, kucuk_girdi, nuf, tetik, kayit)
    return bas, nuf, tetik, kayit, m, kg


def _satirlar(kayit):
    fis = kayit.tablo("fis")
    sat = kayit.tablo("fis_satir")
    return fis, sat.merge(fis[["fis_id", "gun", "magaza", "musteri", "tip"]], on="fis_id", how="left")


def _a(girdi, gunler, kaynak):
    from perakende_veri.v4.crm.girdi import ADET, H, INDIRIM, TUTAR

    w = girdi.dunya
    parca = []
    for d in gunler:
        s = getattr(girdi, kaynak)[d]
        c = s[:, H].astype(np.int64)
        parca.append(pd.DataFrame({
            "gun": d, "magaza": np.asarray(w.hucre_magaza)[c], "sku": np.asarray(w.hucre_sku)[c],
            "adet": s[:, ADET].astype(np.int64), "tutar": s[:, TUTAR], "indirim_tutari": s[:, INDIRIM],
        }))
    return pd.concat(parca, ignore_index=True)


# ---------------------------------------------------------------------------


def test_tutar_kurusu_kurusuna(kucuk_girdi, kosu):
    """Satış ve iade: (gün, mağaza, SKU, işaret) adet, tutar, indirim A ile
    kuruşu kuruşuna."""
    bas, _, _, kayit, _, _ = kosu
    _, sat = _satirlar(kayit)
    sat["iade"] = sat["adet"] < 0
    gunler = range(bas, bas + GUN_SAYISI)
    a = pd.concat([_a(kucuk_girdi, gunler, "satis_gun"),
                   _a(kucuk_girdi, range(bas + IADE_ILK, bas + GUN_SAYISI), "iade_gun")])
    a["iade"] = a["adet"] < 0
    anahtar = ["gun", "magaza", "sku", "iade"]
    b = sat.groupby(anahtar)[["adet", "tutar", "indirim_tutari"]].sum().sort_index()
    a = a.set_index(anahtar).sort_index()
    assert a.index.equals(b.index)
    assert (b["adet"].to_numpy() == a["adet"].to_numpy()).all()
    assert np.abs(b["tutar"].to_numpy() - a["tutar"].to_numpy()).max() < 0.005
    assert np.abs(b["indirim_tutari"].to_numpy() - a["indirim_tutari"].to_numpy()).max() < 0.005


def test_islem_adet(kucuk_girdi, kosu):
    """Satır işlem durumunu A satırından alır: islem_adet ∈ {0, adet},
    A satırı başına toplam A'nın k'sı (iade negatif)."""
    _, _, _, kayit, _, _ = kosu
    sat = kayit.tablo("fis_satir")
    ia, ad = sat["islem_adet"].to_numpy(), sat["adet"].to_numpy()
    assert ((ia == 0) | (ia == ad)).all()
    top = sat.groupby("a_satir")["islem_adet"].sum()
    assert (top.to_numpy() == kucuk_girdi.islem_adet[top.index.to_numpy()]).all()
    assert (ia != 0).any() and (ia < 0).any()


def test_iade_orijinale_baglanir(kosu):
    """Her iade satırı daha erken tarihli (7 / ONL 10 gün), aynı SKU, aynı
    mağaza, aynı müşterinin satış satırına bağlı; satır başına iade ≤ adet."""
    _, nuf, _, kayit, _, _ = kosu
    _, sat = _satirlar(kayit)
    iade = sat[sat["adet"] < 0]
    assert len(iade)
    orj = sat.set_index("satir_id").loc[iade["orijinal_satir"].to_numpy()]
    assert (orj["adet"].to_numpy() > 0).all()
    assert (orj["sku"].to_numpy() == iade["sku"].to_numpy()).all()
    assert (orj["magaza"].to_numpy() == iade["magaza"].to_numpy()).all()
    assert (orj["musteri"].to_numpy() == iade["musteri"].to_numpy()).all()
    gec = np.where(iade["magaza"].to_numpy() == nuf.magaza.onl,
                   a_sabitler.IADE_GECIKME_ONLINE, a_sabitler.IADE_GECIKME_MAGAZA)
    assert (orj["gun"].to_numpy() == iade["gun"].to_numpy() - gec).all()
    geri = iade.groupby("orijinal_satir")["adet"].sum()
    assert (-geri.to_numpy() <= sat.set_index("satir_id").loc[geri.index, "adet"].to_numpy()).all()
    assert (sat.loc[sat["adet"] > 0, "orijinal_satir"] == -1).all()


def test_fis_isaretleri(kosu):
    """İade fişi yalnız negatif, satış fişi yalnız pozitif satır; boş fiş
    yok; iade fişi (müşteri, mağaza, gün) başına bir (Review Focus 5)."""
    _, _, _, kayit, _, _ = kosu
    fis, sat = _satirlar(kayit)
    assert (sat.loc[sat["tip"] == 1, "adet"] < 0).all()
    assert (sat.loc[sat["tip"] == 0, "adet"] > 0).all()
    assert set(sat["fis_id"]) == set(fis["fis_id"])
    iade_fis = fis[fis["tip"] == 1]
    assert len(iade_fis) and not iade_fis.duplicated(["musteri", "magaza", "gun"]).any()
    assert (sat.groupby("fis_id")["satir_no"].max() == sat.groupby("fis_id").size()).all()
    assert fis["fis_id"].is_unique and sat["satir_id"].is_unique


def test_kapanmis_magaza_iadesi(kosu):
    """Kapanıştan sonraki günlerde gelen iade, kapanan mağazanın orijinal
    satırına bağlanır (Review Focus 2)."""
    _, _, _, kayit, m, kg = kosu
    _, sat = _satirlar(kayit)
    iade = sat[(sat["adet"] < 0) & (sat["magaza"] == m) & (sat["gun"] >= kg)]
    assert len(iade) > 0
    assert (sat.loc[(sat["adet"] > 0) & (sat["magaza"] == m), "gun"] < kg).all()


def test_beden_uyumsuz_iade_orani(kosu):
    """Beden uyumsuz satırların iade oranı ≥ 2 × uyumlu satırlarınki, B'nin
    seçim yaptığı hücre-günlerde (iki tür satır da var, iade < satış).

    Havuzlanmış oran bu sınırı taşıyamaz: A iade adedini hücre-gün başına
    bedenden bağımsız belirler; tek satırlı hücre-günlerde seçim yok ve
    iade oranı yüksek ONL'de beden uyumsuz payı düşük (Simpson). KUCUK'ta
    havuzlanmış ~1,4, kanal içinde ~1,6 (mağaza) / ~1,9 (ONL); sonsuz
    ağırlıkla bile ~1,9 (rapor)."""
    bas, nuf, _, kayit, _, _ = kosu
    _, sat = _satirlar(kayit)
    geri = -sat[sat["adet"] < 0].groupby("orijinal_satir")["adet"].sum()
    s = sat[sat["adet"] > 0].copy()
    gec = np.where(s["magaza"] == nuf.magaza.onl,
                   a_sabitler.IADE_GECIKME_ONLINE, a_sabitler.IADE_GECIKME_MAGAZA)
    s = s[(s["gun"] + gec >= bas + IADE_ILK) & (s["gun"] + gec < bas + GUN_SAYISI)]
    s["geri"] = s["satir_id"].map(geri).fillna(0)
    s["uy"] = s["beden_uyumsuz_adet"] > 0
    h = s.groupby("a_satir").agg(uy=("uy", "mean"), geri=("geri", "sum"), adet=("adet", "sum"))
    secimli = h.index[(h["uy"] > 0) & (h["uy"] < 1) & (h["geri"] > 0) & (h["geri"] < h["adet"])]
    s = s[s["a_satir"].isin(secimli)]
    assert len(secimli) > 50
    uy = s["uy"]
    oran_uy = s.loc[uy, "geri"].sum() / s.loc[uy, "adet"].sum()
    oran_iyi = s.loc[~uy, "geri"].sum() / s.loc[~uy, "adet"].sum()
    assert oran_uy >= 2 * oran_iyi, (oran_uy, oran_iyi)


def test_bos_ziyaret(kucuk_girdi, kosu):
    """Boş ziyaret adetleri (gün, mağaza, SKU) gizli kayba eşit; yaklaşık
    yarısı o gün o mağazada fişi olan müşterilerde."""
    bas, _, _, kayit, _, _ = kosu
    w = kucuk_girdi.dunya
    bz = kayit.tablo("bos_ziyaret")
    parca = []
    for d in range(bas, bas + GUN_SAYISI):
        k = kucuk_girdi.kayip_gun[d]
        parca.append(pd.DataFrame({"gun": d, "magaza": np.asarray(w.hucre_magaza)[k[:, 0]],
                                   "sku": np.asarray(w.hucre_sku)[k[:, 0]], "adet": k[:, 1]}))
    a = pd.concat(parca).groupby(["gun", "magaza", "sku"])["adet"].sum()
    b = bz.groupby(["gun", "magaza", "sku"])["adet"].sum()
    assert a.sort_index().index.equals(b.sort_index().index)
    assert (a.sort_index().to_numpy() == b.sort_index().to_numpy()).all()
    fis = kayit.tablo("fis")
    fisli = fis[fis["tip"] == 0][["gun", "magaza", "musteri"]].drop_duplicates()
    m = bz.merge(fisli, on=["gun", "magaza", "musteri"], how="left", indicator=True)
    pay = m.loc[m["_merge"] == "both", "adet"].sum() / m["adet"].sum()
    assert 0.4 < pay < 0.6, pay
    assert (bz["adet"] > 0).all() and not bz.duplicated(["gun", "magaza", "musteri", "sku"]).any()


def test_tetikler(kosu):
    """Tetik: iade fişi başına bir iade olayı; iade edilen beden uyumsuz
    satır başına bir; boş ziyaretçinin stoksuzluk penceresi d + 60."""
    _, nuf, tetik, kayit, _, _ = kosu
    fis, sat = _satirlar(kayit)
    iade_fis = fis[fis["tip"] == 1]
    beklenen = np.bincount(iade_fis["musteri"], minlength=nuf.K)
    assert (tetik.iade_sayisi[: nuf.K] == beklenen).all()
    son = iade_fis.groupby("musteri")["gun"].max()
    assert (tetik.son_iade_gun[son.index.to_numpy()] == son.to_numpy()).all()
    iade = sat[sat["adet"] < 0]
    uy = iade[iade["beden_uyumsuz_adet"] != 0]
    assert len(uy) and (tetik.beden_uyumsuz_sayisi[: nuf.K] == np.bincount(uy["musteri"], minlength=nuf.K)).all()
    bz = kayit.tablo("bos_ziyaret")
    son_bz = bz.groupby("musteri")["gun"].max()
    assert (tetik.stoksuz_bitis_gun[son_bz.index.to_numpy()] == son_bz.to_numpy() + 60).all()
    assert (np.delete(tetik.stoksuz_bitis_gun[: nuf.K], son_bz.index.to_numpy()) == -1).all()


def test_rastgele_iade_gunu_bagimsiz(kucuk_girdi, kosu):
    """İade ve boş ziyaret çekilişleri gün d ve tohumdan belirlenir:
    aynı durumdan iki çağrı aynı sonucu verir."""
    from perakende_veri.v4.crm.iade import iade_bagla

    bas, nuf, _, kayit, _, _ = kosu
    from perakende_veri.v4.crm.yasam import Tetik

    d = bas + GUN_SAYISI - 1
    sonuc = []
    for _ in range(2):
        k2 = copy.copy(kayit)
        k2._parca = {a: list(v) for a, v in kayit._parca.items()}
        k2._gun = {a: {g: list(i) for g, i in v.items()} for a, v in kayit._gun.items()}
        # gün d'nin iade parçalarını çıkarıp yeniden bağla
        iade_mi = {"fis": lambda p: (p["tip"] == 1).all(), "fis_satir": lambda p: (p["adet"] < 0).all()}
        for ad, f in iade_mi.items():
            k2._gun[ad][d] = [i for i in k2._gun[ad][d] if not f(k2._parca[ad][i])]
        iade_bagla(d, kucuk_girdi, nuf, Tetik.bos(nuf.K), k2)
        sonuc.append(k2.gun_parcalari("fis_satir", d)[-1]["orijinal_satir"].copy())
    assert np.array_equal(sonuc[0], sonuc[1])
