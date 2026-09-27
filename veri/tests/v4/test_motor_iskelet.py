"""Testler: Görev 12 motor iskeleti — tedarik, ilk dağıtım, yolda süre,
replenishment, sürekli tedarik, satış (mağaza rafı + online depo), iade.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §6
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-12-brief.md
"""

import dataclasses

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4.dunya import yolda_gun
from perakende_veri.v4.takvim import gun_indisi
from perakende_veri.v4.motor import Gorunum, simule_et
from perakende_veri.v4.politika import (
    Politikalar,
    Transferler,
    lumoda_politikalari,
    paket_tablosu,
)

POLITIKA_ADLARI = [
    "ilk_dagitim", "paket_secimi", "replenishment", "rpt", "markdown",
    "acilis", "kapanis", "elle_transfer", "outlet_akisi",
]


def _topla(indis, deger, n) -> np.ndarray:
    return np.bincount(np.asarray(indis, dtype=np.int64), np.asarray(deger, dtype=float),
                       minlength=n).astype(np.int64)


# ---------------------------------------------------------------------------
# Stok korunumu (omurga)
# ---------------------------------------------------------------------------


def _defter_dogrula(w, k, akis_var: bool = True) -> None:
    """Hücre, depo ve yolda defterini son duruma karşı doğrular (bkz.
    `test_stok_korunumu`)."""
    D = k["gun_sayisi"]
    C, S = len(w.cesit), len(w.urunler)
    son = k["son_durum"]
    sev, sat = k["sevkiyat"], k["satis"]
    onl = w.hucre_online

    varan = sev[sev.varis_gun < D]
    yolda = sev[sev.varis_gun >= D]

    # --- Hücre defteri ---------------------------------------------------
    h_giris = _topla(varan.hedef_hucre[varan.hedef_hucre >= 0], varan.adet[varan.hedef_hucre >= 0], C)
    h_cikis = _topla(sev.kaynak_hucre[sev.kaynak_hucre >= 0], sev.adet[sev.kaynak_hucre >= 0], C)
    fiz_sat = sat[~onl[sat.hucre.to_numpy()]]
    h_satis = _topla(fiz_sat.hucre[fiz_sat.adet > 0], fiz_sat.adet[fiz_sat.adet > 0], C)
    h_iade = _topla(fiz_sat.hucre[fiz_sat.adet < 0], -fiz_sat.adet[fiz_sat.adet < 0], C)
    if akis_var:
        assert h_satis.sum() > 0 and h_iade.sum() > 0 and h_giris.sum() > 0
    np.testing.assert_array_equal(h_giris - h_cikis - h_satis + h_iade, son["magaza_stok"])
    assert son["magaza_stok"][onl].sum() == 0, "ONL hücresinde raf stoğu olmaz"

    # --- Depo defteri ----------------------------------------------------
    teslim = np.zeros(S, dtype=np.int64)
    for s in k["siparis"]:
        if s["gerceklesen_gun"] < D:
            np.add.at(teslim, s["skular"], np.asarray(s["adetler"]) - np.asarray(s["hatali"]))
    depodan = sev[sev.kaynak == -1]
    d_giden = _topla(depodan.sku, depodan.adet, S)
    depoya = varan[varan.hedef == -1]
    d_gelen = _topla(depoya.sku, depoya.adet, S)
    onl_sat = sat[onl[sat.hucre.to_numpy()]]
    hs = w.hucre_sku
    d_onl_satis = _topla(hs[onl_sat.hucre[onl_sat.adet > 0]], onl_sat.adet[onl_sat.adet > 0], S)
    d_onl_iade = _topla(hs[onl_sat.hucre[onl_sat.adet < 0]], -onl_sat.adet[onl_sat.adet < 0], S)
    if akis_var:
        assert d_onl_satis.sum() > 0 and d_onl_iade.sum() > 0 and d_gelen.sum() > 0
    np.testing.assert_array_equal(
        teslim - d_giden + d_gelen - d_onl_satis + d_onl_iade, son["depo"]
    )

    # --- Yolda -----------------------------------------------------------
    y_h = yolda[yolda.hedef_hucre >= 0]
    np.testing.assert_array_equal(_topla(y_h.hedef_hucre, y_h.adet, C), son["yolda_hucre"])
    y_d = yolda[yolda.hedef == -1]
    np.testing.assert_array_equal(_topla(y_d.sku, y_d.adet, S), son["yolda_depo"])


def test_stok_korunumu(kucuk_dunya, kucuk_kosu):
    """Her hücre ve her SKU için hareket defteri son stoğu birebir verir.

    Hücre: Σ varış (hedef hücre, varış günü < D) − Σ çıkış (kaynak hücre)
    − Σ satış + Σ iade = son mağaza stoğu. Kapalı mağazaya varan mal ve
    kapalı mağazanın iadesi, aynı gün hücreden depoya bir `sevkiyat`
    satırıyla (kaynak hücre = o hücre) geçer; defter bunu çıkış olarak sayar.

    Depo (SKU): Σ teslim (adet − hatalı; gerçekleşen gün < D) − Σ depodan
    giden + Σ depoya varan − online satış + online iade = son depo.

    Yolda: varış günü ≥ D olan satırlar son durumun yolda dizilerine eşit.
    """
    _defter_dogrula(kucuk_dunya, kucuk_kosu)


def test_stok_hic_eksi_degil(kucuk_kosu):
    k = kucuk_kosu
    assert (k["son_durum"]["magaza_stok"] >= 0).all()
    assert (k["son_durum"]["depo"] >= 0).all()
    assert (k["stok"].adet >= 0).all()
    assert (k["depo_stok"].adet >= 0).all()
    assert (k["sevkiyat"].adet > 0).all()
    assert (k["gizli_kayip"].adet > 0).all()


# ---------------------------------------------------------------------------
# Yolda süre, paket
# ---------------------------------------------------------------------------


def test_yolda_sure_uygulanir(kucuk_dunya, kucuk_kosu):
    w = kucuk_dunya
    sev = kucuk_kosu["sevkiyat"]
    depodan = sev[sev.tip.isin(["ilk_dagitim", "replenishment"])]
    assert len(depodan) > 0
    assert (depodan.kaynak == -1).all() and (depodan.hedef >= 0).all()
    beklenen = yolda_gun(w.depo_mesafe_km[depodan.hedef.to_numpy()], depo=True)
    np.testing.assert_array_equal(depodan.varis_gun - depodan.gun, beklenen)
    # Her iki tipte de en az bir uzak (>1 gün) mağaza var: süre gerçekten işliyor.
    assert (depodan.varis_gun - depodan.gun).max() >= 2


def test_ilk_dagitim_paket_katlari(kucuk_dunya, kucuk_kosu):
    w = kucuk_dunya
    sev = kucuk_kosu["sevkiyat"]
    ilk = sev[sev.tip == "ilk_dagitim"].copy()
    assert len(ilk) > 0 and (ilk.paket_id >= 0).all()
    _, _, icerik = paket_tablosu(w.paketler)
    sira = w.urunler["beden_sira"].to_numpy()
    ilk["icerik"] = icerik[ilk.paket_id.to_numpy(), sira[ilk.sku.to_numpy()]]
    assert (ilk.icerik > 0).all()
    assert (ilk.adet % ilk.icerik == 0).all(), "adet paket içeriğinin tam katı değil"
    ilk["paket"] = ilk.adet // ilk.icerik
    ilk["option"] = w.sku_option[ilk.sku.to_numpy()]
    grup = ilk.groupby(["gun", "hedef", "option"])
    assert (grup["paket"].nunique() == 1).all(), "bir mağazaya giden bedenler aynı paket sayısını taşımalı"
    # Paket, option'ın bütün bedenlerini taşır.
    beden_sayisi = pd.Series(w.sku_option).value_counts()
    n = grup["sku"].nunique()
    opt = n.index.get_level_values("option")
    np.testing.assert_array_equal(n.to_numpy(), beden_sayisi.loc[opt].to_numpy())
    # ONL ve outlet akışı hücreleri ilk dağıtım almaz.
    assert not w.hucre_online[ilk.hedef_hucre.to_numpy()].any()
    assert not w.hucre_outlet_akisi[ilk.hedef_hucre.to_numpy()].any()


def test_ilk_dagitim_lansmana_yetisir(kucuk_dunya, kucuk_kosu):
    """Teslim zamanında olan option'da mal lansman gününe kadar mağazada."""
    w = kucuk_dunya
    sev = kucuk_kosu["sevkiyat"]
    ilk = sev[sev.tip == "ilk_dagitim"]
    o = w.sku_option[ilk.sku.to_numpy()]
    lansman = w.optionlar["lansman_gun"].to_numpy()[o]
    teslim = {s["option"]: s["gerceklesen_gun"] for s in kucuk_kosu["siparis"] if s["tip"] == "ilk"}
    zamaninda = np.array([teslim[x] + 3 <= lansman[i] for i, x in enumerate(o)])
    assert zamaninda.any()
    assert (ilk.varis_gun.to_numpy()[zamaninda] <= lansman[zamaninda]).all()


# ---------------------------------------------------------------------------
# Kalite
# ---------------------------------------------------------------------------


def test_hatali_mal_depoya_girmez(kucuk_dunya, kucuk_kosu):
    k = kucuk_kosu
    D = k["gun_sayisi"]
    kal = k["kalite"]
    assert set(kal.tip) >= {"ilk", "surekli"}
    assert (kal.hatali >= 0).all() and (kal.hatali <= kal.adet).all()
    assert (kal.numune <= kal.adet).all()
    assert kal.hatali.sum() > 0
    teslim_edilen = [s for s in k["siparis"] if s["gerceklesen_gun"] < D and s["tip"] != "baslangic"]
    assert len(kal) == len(teslim_edilen)
    assert kal.hatali.sum() == sum(int(np.sum(s["hatali"])) for s in teslim_edilen)
    assert kal.adet.sum() == sum(int(np.sum(s["adetler"])) for s in teslim_edilen)
    # Kalite çekilişi sipariş sayısından bağımsız: aynı (gün, option) aynı sonucu verir.
    from perakende_veri.v4.rastgele import sayac_uretici_option

    a = sayac_uretici_option(100, "kalite", 5).random(3)
    b = sayac_uretici_option(100, "kalite", 5).random(3)
    c = sayac_uretici_option(100, "kalite", 6).random(3)
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)


# ---------------------------------------------------------------------------
# Online depo paylaşımı (Review Focus 3)
# ---------------------------------------------------------------------------


def _hepsini_iste(g):
    return np.full(len(g.magaza_stok), 10**6, dtype=np.int64)


def test_online_depo_paylasimi(kucuk_dunya, kucuk_kosu):
    """Aynı gün replenishment depoyu 0'a çekince online o SKU'dan satamaz."""
    w = kucuk_dunya
    D = 150
    k = simule_et(w, Politikalar(replenishment=_hepsini_iste), gun_sayisi=D)
    assert (k["son_durum"]["depo"] >= 0).all()
    assert (k["depo_stok"].adet >= 0).all()

    sev, sat = k["sevkiyat"], k["satis"]
    onl_sat = sat[w.hucre_online[sat.hucre.to_numpy()] & (sat.adet > 0)]
    onl_sat = onl_sat.assign(sku=w.hucre_sku[onl_sat.hucre.to_numpy()])
    repl = sev[sev.tip == "replenishment"]
    assert len(repl) > 0
    cakisan = onl_sat.merge(repl[["gun", "sku"]].drop_duplicates(), on=["gun", "sku"])
    assert len(cakisan) == 0, "depoyu boşaltan günde online satış olmamalı"

    # Kontrol: varsayılan politikada aynı günlerde online satış var.
    v = kucuk_kosu["satis"]
    v = v[(v.gun < D) & w.hucre_online[v.hucre.to_numpy()] & (v.adet > 0)]
    v = v.assign(sku=w.hucre_sku[v.hucre.to_numpy()])
    assert len(v.merge(repl[["gun", "sku"]].drop_duplicates(), on=["gun", "sku"])) > 0


# ---------------------------------------------------------------------------
# Önek, determinizm
# ---------------------------------------------------------------------------


def test_gun_sayisi_oneki(kucuk_dunya, kucuk_kosu):
    n = 200
    kisa = simule_et(kucuk_dunya, gun_sayisi=n)
    assert kisa["gun_sayisi"] == n
    for ad in ("satis", "gizli_kayip", "sevkiyat", "stok", "depo_stok", "kalite"):
        tam = kucuk_kosu[ad]
        pd.testing.assert_frame_equal(
            kisa[ad].reset_index(drop=True),
            tam[tam.gun < n].reset_index(drop=True),
            obj=ad,
        )
    tam_sip = [s for s in kucuk_kosu["siparis"] if s["siparis_gun"] < n]
    kisa_sip = [s for s in kisa["siparis"] if s["siparis_gun"] < n]
    assert [(s["tip"], s["option"], s["gerceklesen_gun"]) for s in kisa_sip] == [
        (s["tip"], s["option"], s["gerceklesen_gun"]) for s in tam_sip
    ]


def _onek_esit(kisa, tam, n, adlar=("satis", "sevkiyat", "depo_stok")) -> None:
    for ad in adlar:
        t = tam[ad]
        pd.testing.assert_frame_equal(
            kisa[ad].reset_index(drop=True), t[t.gun < n].reset_index(drop=True),
            obj=f"{ad} (n={n})",
        )


def test_gun_sayisi_oneki_acilis_sinirlari(kucuk_dunya, kucuk_kosu):
    """Açılış sınırında kesilen koşu da tam koşunun öneki: mağaza takvimi
    kısaltılmış D'ye göre değil dünya ufkuna göre kurulur (varışı D'yi aşan
    ilk dağıtım, açılacak mağazayı kapalı saymaz)."""
    w = kucuk_dunya
    acilanlar = w.magaza_olay[w.magaza_olay.olay == "acilis"]
    assert len(acilanlar) > 0
    for r in acilanlar.itertuples():
        a = gun_indisi(r.olay_tarihi)
        for n in (a - 1, a):
            if 0 < n <= w.gun_sayisi:
                _onek_esit(simule_et(w, gun_sayisi=n), kucuk_kosu, n)


def test_gun_sayisi_oneki_bildirilen_hata(kucuk_dunya, kucuk_kosu):
    """İnceleme bulgusu: n=412 koşusu 411. günün M021 ilk dağıtımını atlıyordu."""
    for n in (412, 413, 951, 952):
        _onek_esit(simule_et(kucuk_dunya, gun_sayisi=n), kucuk_kosu, n)


# ---------------------------------------------------------------------------
# Transfer korunumu (elle transfer, geri yönlendirme, yolda depo)
# ---------------------------------------------------------------------------


def test_transfer_korunumu(kucuk_dunya):
    """Enjekte edilen elle transfer: M009 → M007 (M007'nin tadilatı boyunca:
    varışlar `geri_yonlendirme` ile depoya döner) ve M008 → depo. Koşu son
    transfer yoldayken kesilir; defter (hücre, depo, yolda) tutar."""
    w = kucuk_dunya
    mid = w.magazalar["magaza_id"].to_numpy()
    kaynak, hedef, depoya = (int(np.flatnonzero(mid == x)[0]) for x in ("M009", "M007", "M008"))
    t = w.magaza_olay[(w.magaza_olay.magaza_id == "M007") & (w.magaza_olay.olay == "tadilat")].iloc[0]
    bas, bit = gun_indisi(t.olay_tarihi), gun_indisi(t.bitis_tarihi)
    hedef_skulari = set(w.hucre_sku[w.hucre_magaza == hedef])
    k_hucre = np.flatnonzero(w.hucre_magaza == kaynak)
    d_hucre = np.flatnonzero(w.hucre_magaza == depoya)

    def elle(g):
        if not (bas - 14 <= g.gun <= bit):
            return Transferler.bos()
        k = [c for c in k_hucre if g.magaza_stok[c] > 0 and w.hucre_sku[c] in hedef_skulari][:30]
        dp = [c for c in d_hucre if g.magaza_stok[c] > 0][:15]
        n1, n2 = len(k), len(dp)
        return Transferler(
            kaynak=np.array([kaynak] * n1 + [depoya] * n2, dtype=np.int64),
            hedef=np.array([hedef] * n1 + [-1] * n2, dtype=np.int64),
            sku=w.hucre_sku[np.array(k + dp, dtype=np.int64)],
            adet=np.full(n1 + n2, 2, dtype=np.int64),
        )

    son_pazartesi = max(d for d in range(bas - 14, bit + 1) if d % 7 == 0)
    k = simule_et(w, Politikalar(elle_transfer=elle), gun_sayisi=son_pazartesi + 1)
    sev = k["sevkiyat"]
    el = sev[sev.tip == "elle_transfer"]
    assert ((el.kaynak == kaynak) & (el.hedef == hedef)).sum() > 0
    assert ((el.kaynak == depoya) & (el.hedef == -1)).sum() > 0
    ss = el[el.hedef == hedef]
    beklenen = yolda_gun(w.mesafe_km[kaynak, hedef], depo=False)
    assert (ss.varis_gun - ss.gun == beklenen).all()
    geri = sev[sev.tip == "geri_yonlendirme"]
    assert len(geri) > 0 and (geri.kaynak == hedef).all() and (geri.hedef == -1).all()
    assert k["son_durum"]["yolda_depo"].sum() > 0
    assert (k["son_durum"]["magaza_stok"] >= 0).all() and (k["son_durum"]["depo"] >= 0).all()
    _defter_dogrula(w, k)


# ---------------------------------------------------------------------------
# Kampanya kimliği
# ---------------------------------------------------------------------------


def test_kampanya_id(kucuk_dunya, kucuk_kosu):
    """Satışın kampanya_id'si fiyatı belirleyen kampanyadır: oranı günün
    (mağaza, option) kampanya oranına ve uygulanan indirime eşit."""
    w = kucuk_dunya
    sat = kucuk_kosu["satis"]
    s = sat[(sat.adet > 0) & (sat.kampanya_id >= 0)]
    assert len(s) > 0
    oran = w.kampanya["oran"].to_numpy()[s.kampanya_id.to_numpy()]
    liste = w.urunler["liste_fiyati"].to_numpy()[w.hucre_sku[s.hucre.to_numpy()]]
    np.testing.assert_allclose(s.indirim_tutari / (liste * s.adet), oran, atol=1e-3)
    gun_orani = np.array([
        w.kampanya_takvimi(d)[w.hucre_magaza[c], w.hucre_option[c]]
        for d, c in zip(s.gun.to_numpy()[:2000], s.hucre.to_numpy()[:2000])
    ])
    np.testing.assert_allclose(gun_orani, oran[:2000])
    # Kampanyasız satışta kampanya oranı yoktur (markdown yok: Görev 12).
    yok = sat[(sat.adet > 0) & (sat.kampanya_id < 0)].head(2000)
    gun_orani = np.array([
        w.kampanya_takvimi(d)[w.hucre_magaza[c], w.hucre_option[c]]
        for d, c in zip(yok.gun.to_numpy(), yok.hucre.to_numpy())
    ])
    assert (gun_orani == 0).all()
    # İade satırı satış gününün kampanyasını taşır.
    assert (sat[sat.adet < 0].kampanya_id >= 0).any()


# ---------------------------------------------------------------------------
# Talep, iade, politika arayüzü
# ---------------------------------------------------------------------------


def test_talep_kaydi_satis_arti_kayip(kucuk_dunya):
    k = simule_et(kucuk_dunya, gun_sayisi=120, kayit_talep=True)
    talep = k["talep"]
    assert talep.shape == (120, len(kucuk_dunya.cesit)) and talep.dtype == np.int16
    sat = k["satis"][k["satis"].adet > 0]
    kay = k["gizli_kayip"]
    toplam = np.zeros(talep.shape, dtype=np.int64)
    np.add.at(toplam, (sat.gun.to_numpy(), sat.hucre.to_numpy()), sat.adet.to_numpy())
    np.add.at(toplam, (kay.gun.to_numpy(), kay.hucre.to_numpy()), kay.adet.to_numpy())
    np.testing.assert_array_equal(toplam, talep)


def test_iade_oranlari(kucuk_dunya, kucuk_kosu):
    w, sat = kucuk_dunya, kucuk_kosu["satis"]
    onl = w.hucre_online[sat.hucre.to_numpy()]
    for maske, alt, ust in ((~onl, 0.06, 0.09), (onl, 0.27, 0.34)):
        s = sat[maske]
        oran = -s.adet[s.adet < 0].sum() / s.adet[s.adet > 0].sum()
        assert alt * 0.95 < oran < ust, oran


def test_satis_tutari(kucuk_dunya, kucuk_kosu):
    w, sat = kucuk_dunya, kucuk_kosu["satis"]
    s = sat[sat.adet > 0]
    liste = w.urunler["liste_fiyati"].to_numpy()[w.hucre_sku[s.hucre.to_numpy()]]
    np.testing.assert_allclose(s.tutar + s.indirim_tutari, liste * s.adet, atol=0.02)
    assert (s.indirim_tutari > 0).any() and (s.indirim_tutari >= -1e-9).all()


def test_politika_arayuzu(kucuk_dunya):
    pol = lumoda_politikalari()
    assert sorted(pol) == sorted(POLITIKA_ADLARI)
    varsayilan = Politikalar()
    assert [f.name for f in dataclasses.fields(Politikalar)] == POLITIKA_ADLARI
    for ad in POLITIKA_ADLARI:
        assert getattr(varsayilan, ad) is pol[ad]
    assert Transferler.bos().adet.size == 0

    goruldu = []

    def casus(g):
        assert isinstance(g, Gorunum)
        for ad in ("magaza_stok", "depo", "yolda", "satis_gecmisi", "stoklu_gecmisi",
                    "fiyat_orani", "acik_magaza", "kapanacak"):
            with pytest.raises(ValueError):
                getattr(g, ad)[...] = 0
        assert g.satis_gecmisi.shape[0] == g.gun
        goruldu.append(g.gun)
        return pol["replenishment"](g)

    simule_et(kucuk_dunya, Politikalar(replenishment=casus), gun_sayisi=15)
    assert goruldu == [0, 7, 14]
