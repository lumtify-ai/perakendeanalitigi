"""`allocation.tahmin`: LightGBM (Poisson) mağaza x option erken talep tahmincisi.

Birim testler elle kurulmuş sentetik öğrenme tablosuyla (`ogrenme.ogrenme_tablosu`nun
sütunları; mağazalar 0..5) çalışır; karar anı sızıntı testi uzun oyuncak dünyayla (test_ogrenme).
`veri` işaretli test yayımlanan v4 dosyasını okur."""

import pickle
import time

import numpy as np
import pandas as pd
import pytest

from allocation import ogrenme, sabitler, tahmin

M = 6
MAGAZALAR = pd.DataFrame({
    "tip": ["AVM", "AVM", "Cadde", "Cadde", "AVM", "Cadde"],
    "bolge": ["Marmara", "Marmara", "Ege", "İç Anadolu", "Ege", "Marmara"],
    "sehir": ["İstanbul", "Bursa", "İzmir", "Ankara", "İzmir", "İstanbul"],
    "metrekare": [600, 450, 300, 520, 410, 380],
    "kapasite": [6000, 4500, 3000, 5200, 4100, 3800],
})
HIZLI = {"num_leaves": 8, "learning_rate": 0.1, "n_estimators": 60, "min_child_samples": 5}
ALT = ["Elbise", "Bluz", "Pantolon"]
KALIP = ["regular", "slim", "oversize"]
SEG = ["dusuk", "orta", "yuksek"]
MAG_CARPAN = np.array([2.0, 1.0, 0.5, 1.5, 1.0, 0.8])
ALT_CARPAN = {"Elbise": 3.0, "Bluz": 1.0, "Pantolon": 0.4}
# mağazanın kategori eğilimi: 0-1 Elbise'yi, 2-3 Pantolon'u sever (karışım özelliğinin taşıdığı sinyal)
EGILIM = {0: {"Elbise": 1.8, "Pantolon": 0.5}, 1: {"Elbise": 1.8, "Pantolon": 0.5},
          2: {"Elbise": 0.5, "Pantolon": 1.8}, 3: {"Elbise": 0.5, "Pantolon": 1.8}}


def _oznitelik(o: int, sezon: str = "SS24") -> dict:
    return {"ust_kategori": "Üst Giyim", "alt_kategori": ALT[o % 3], "fiyat_segmenti": SEG[(o // 3) % 3],
            "kalip": KALIP[(o // 9) % 3], "kumas": f"k{o % 4}", "renk": f"r{o % 5}", "desen": "düz",
            "cinsiyet": "Kadın" if o % 2 else "Erkek", "dalga": 1 + o % 3,
            "liste_fiyati": 300.0 + 10 * (o % 7), "sezon_kodu": sezon, "ilk_alim": 500 + 20 * (o % 11)}


def sentetik(n_option: int = 45, tohum: int = 7, ilk: int = 0, stoksuz=()) -> pd.DataFrame:
    """Talep = mağaza çarpanı x alt kategori çarpanı x mağazanın kategori eğilimi x gürültü;
    `stoksuz` (option, mağaza) çiftleri stoklu_gun 0 / talep NaN satırı olur."""
    rng = np.random.default_rng(tohum)
    satir = []
    for o in range(ilk, ilk + n_option):
        oz = _oznitelik(o)
        olcek = rng.uniform(0.7, 1.4)
        for m in range(M):
            t = 12.0 * MAG_CARPAN[m] * ALT_CARPAN[oz["alt_kategori"]]                 * EGILIM.get(m, {}).get(oz["alt_kategori"], 1.0) * olcek * rng.uniform(0.8, 1.25)
            if (o, m) in stoksuz:
                satir.append({"option": o, "magaza": m, "satis": 3, "stoklu_gun": 0, "talep": np.nan, **oz})
            else:
                satir.append({"option": o, "magaza": m, "satis": int(t), "stoklu_gun": 42, "talep": t, **oz})
    df = pd.DataFrame(satir)
    return df[[*ogrenme.ERKEN_SUTUNLARI, *ogrenme.OZNITELIKLER, "ilk_alim"]]


def _yeni_satirlar(o: int = 500) -> pd.DataFrame:
    """Yeni option için tahmin satırları: her mağaza, yalnız öznitelikler (talep yok)."""
    oz = _oznitelik(o, "SS25")
    df = pd.DataFrame([{"magaza": m, **oz} for m in range(M)])
    return df


# ---------------------------------------------------------------- karisim


def test_karisim_paylar_ve_eksik_anahtarlar():
    t = sentetik(n_option=12)
    k = tahmin.karisim(t)
    assert list(k.columns) == ["magaza", "ozellik", "deger", "pay"]
    assert set(k["ozellik"]) == {"alt_kategori", "kalip", "fiyat_segmenti"}
    # mağaza başına her özelliğin payları 1'e toplanır
    toplam = k.groupby(["magaza", "ozellik"])["pay"].sum()
    np.testing.assert_allclose(toplam.to_numpy(), 1.0)
    # elle: mağaza 2, alt kategori payları
    m2 = t[t["magaza"] == 2]
    beklenen = m2.groupby("alt_kategori")["talep"].sum() / m2["talep"].sum()
    got = k[(k["magaza"] == 2) & (k["ozellik"] == "alt_kategori")].set_index("deger")["pay"]
    pd.testing.assert_series_equal(got.sort_index(), beklenen.sort_index(), check_names=False)


def test_karisim_stoksuz_satir_girmez():
    t = sentetik(n_option=12)
    ek = sentetik(n_option=4, ilk=100, stoksuz={(o, m) for o in range(100, 104) for m in range(M)})
    ek["satis"] = 9999
    pd.testing.assert_frame_equal(tahmin.karisim(t), tahmin.karisim(pd.concat([t, ek], ignore_index=True)))


# ---------------------------------------------------------------- özellikler


def test_ozellikler_egitim_ve_tahmin_ayni_sutunlar():
    t = sentetik()
    k = tahmin.karisim(t)
    egitim = tahmin.ozellikler(t, MAGAZALAR, k)
    yeni = tahmin.ozellikler(_yeni_satirlar(), MAGAZALAR, k)
    assert list(egitim.columns) == list(yeni.columns) == tahmin.OZELLIKLER
    assert [d.name for d in egitim.dtypes] == [d.name for d in yeni.dtypes]    # kategori listeleri çağrıya göre
    for s in tahmin.KATEGORIK:
        assert isinstance(egitim[s].dtype, pd.CategoricalDtype), s
    assert len(egitim) == len(t) and len(yeni) == M
    assert egitim.index.equals(t.index)
    # mağaza özellikleri indisle eşlenir; sezon tipi sezon kodundan
    y = yeni.iloc[3]
    assert (y["magaza_tip"], y["magaza_bolge"], y["magaza_sehir"]) == ("Cadde", "İç Anadolu", "Ankara")
    assert (y["metrekare"], y["kapasite"]) == (520, 5200)
    assert yeni["sezon_tipi"].astype(str).unique().tolist() == ["SS"]
    aw = _yeni_satirlar().assign(sezon_kodu="AW25")
    assert tahmin.ozellikler(aw, MAGAZALAR, k)["sezon_tipi"].astype(str).unique().tolist() == ["AW"]
    # karışım: mağaza 3'ün Elbise payı
    pay = k[(k["magaza"] == 3) & (k["ozellik"] == "alt_kategori") & (k["deger"] == _yeni_satirlar()["alt_kategori"][0])]
    assert y["pay_alt_kategori"] == pytest.approx(pay["pay"].iloc[0])


def test_ozellikler_bilinmeyen_magaza_ve_deger():
    t = sentetik()
    k = tahmin.karisim(t[t["magaza"] != 5])          # mağaza 5'in geçmişi yok (yeni açılan)
    yeni = _yeni_satirlar().assign(kalip="kesim-yeni", fiyat_segmenti="orta")
    x = tahmin.ozellikler(yeni, MAGAZALAR, k)
    assert np.isnan(x.loc[5, "pay_alt_kategori"])     # mağaza bilinmiyor: eksik
    assert (x.loc[:4, "pay_kalip"] == 0.0).all()      # mağaza biliniyor, kalıp geçmişte yok: sıfır pay
    assert x.loc[:4, "pay_fiyat_segmenti"].between(0, 1).all()
    assert "kesim-yeni" in set(x["kalip"].astype(str))


def test_egitim_ozellikleri_kendi_optionini_gormez():
    """Eğitim satırının karışım özelliği, o option dışındaki option'lardan kurulur (option'a göre
    katlamalı): option'ın kendi talebi değişince kendi satırlarının özelliği değişmez."""
    t = sentetik()
    X, y = tahmin.egitim_ozellikleri(t, MAGAZALAR)
    assert list(X.columns) == tahmin.OZELLIKLER and len(X) == len(y) == len(t)
    bozuk = t.copy()
    o = 11
    bozuk.loc[bozuk["option"] == o, "talep"] *= 50.0
    X2, y2 = tahmin.egitim_ozellikleri(bozuk, MAGAZALAR)
    kendi = (t["option"] == o).to_numpy()
    pd.testing.assert_frame_equal(X[kendi], X2[kendi])
    assert (y2[kendi] > y[kendi]).all()
    # başkalarının özelliği (aynı katlarda) değişir: özellik gerçekten diğer option'lardan geliyor
    assert not X["pay_alt_kategori"].equals(X2["pay_alt_kategori"])


# ---------------------------------------------------------------- tahminci


def test_stoksuz_satirlar_egitim_disi():
    t = sentetik()
    ek = sentetik(n_option=6, ilk=200, stoksuz={(o, m) for o in range(200, 206) for m in range(M)})
    ek["satis"] = 5000
    t2 = pd.concat([t, ek], ignore_index=True)
    # kısmen stoksuz option: stoksuz hücre satırı yalnız o hücreyi düşürür
    a = tahmin.Tahminci.egit(t, MAGAZALAR, HIZLI)
    b = tahmin.Tahminci.egit(t2, MAGAZALAR, HIZLI)
    assert a.kimlik == b.kimlik
    np.testing.assert_array_equal(a.tahmin(tahmin.ozellikler(_yeni_satirlar(), MAGAZALAR, a.gecmis_karisim)),
                                  b.tahmin(tahmin.ozellikler(_yeni_satirlar(), MAGAZALAR, b.gecmis_karisim)))
    X, y = tahmin.egitim_ozellikleri(t2, MAGAZALAR)
    assert len(X) == len(y) == len(t) and np.isfinite(y).all()
    kismi = t.copy()
    kismi.loc[kismi.index[:3], ["stoklu_gun", "talep"]] = [0, np.nan]
    X, _ = tahmin.egitim_ozellikleri(kismi, MAGAZALAR)
    assert len(X) == len(t) - 3


def test_egitim_bos_ya_da_sifir_reddedilir():
    t = sentetik(n_option=10)
    with pytest.raises(ValueError, match="boş"):
        tahmin.Tahminci.egit(t.iloc[:0], MAGAZALAR, HIZLI)
    t["talep"] = 0.0
    with pytest.raises(ValueError, match="boş"):
        tahmin.Tahminci.egit(t, MAGAZALAR, HIZLI)


def test_kimlik_icerikten():
    t = sentetik()
    a = tahmin.Tahminci.egit(t, MAGAZALAR, HIZLI).sabitle()
    assert len(a.kimlik) == 64 and a.sabitle() is a
    # iki pickle gidiş-dönüşünde aynı (RPT'nin pickle kimliği dersi)
    b = pickle.loads(pickle.dumps(a))
    c = pickle.loads(pickle.dumps(b))
    assert a.kimlik == b.kimlik == c.kimlik
    # sabitlenmemiş de aynı içerik özeti
    d = tahmin.Tahminci.egit(t, MAGAZALAR, HIZLI)
    assert d.kimlik == a.kimlik
    # yeniden eğitim aynı model (tohum, tek iş parçacığı sayısı sabit)
    assert tahmin.Tahminci.egit(sentetik(), MAGAZALAR, HIZLI).kimlik == a.kimlik
    # içerik değişince kimlik değişir: parametre, veri
    assert tahmin.Tahminci.egit(t, MAGAZALAR, {**HIZLI, "n_estimators": 61}).kimlik != a.kimlik
    assert tahmin.Tahminci.egit(sentetik(tohum=8), MAGAZALAR, HIZLI).kimlik != a.kimlik
    # eğitilmiş model gidiş-dönüşte aynı tahmini verir
    x = tahmin.ozellikler(_yeni_satirlar(), MAGAZALAR, a.gecmis_karisim)
    np.testing.assert_array_equal(a.tahmin(x), c.tahmin(x))


def test_tahmin_sozlesmesi():
    t = sentetik()
    m = tahmin.Tahminci.egit(t, MAGAZALAR, HIZLI)
    x = tahmin.ozellikler(_yeni_satirlar(), MAGAZALAR, m.gecmis_karisim)
    p = m.tahmin(x)
    assert p.shape == (M,) and p.dtype == np.float64 and np.isfinite(p).all() and (p >= 0).all()
    with pytest.raises(ValueError, match="OZELLIKLER"):
        m.tahmin(x[["metrekare"]])
    with pytest.raises(ValueError, match="OZELLIKLER"):
        m.tahmin(x[list(reversed(tahmin.OZELLIKLER))])
    # bilinmeyen kategori düşmez (LightGBM eksik sayar)
    yeni = _yeni_satirlar().assign(renk="hic-gorulmedi", kumas="hic-gorulmedi")
    assert np.isfinite(m.tahmin(tahmin.ozellikler(yeni, MAGAZALAR, m.gecmis_karisim))).all()


def test_tahmin_sinyali_ogrenir():
    """Sentetik talep mağaza ve alt kategori çarpanlarının çarpımı: model hem mağaza sırasını hem
    alt kategori sırasını bulur; doğrulama sapması mağaza ortalaması tabanından düşüktür."""
    m = tahmin.Tahminci.egit(sentetik(n_option=60), MAGAZALAR, HIZLI)
    p = {}
    for alt in ALT:
        satirlar = _yeni_satirlar().assign(alt_kategori=alt)
        p[alt] = m.tahmin(tahmin.ozellikler(satirlar, MAGAZALAR, m.gecmis_karisim))
    assert p["Elbise"].sum() > p["Bluz"].sum() > p["Pantolon"].sum()
    assert np.argmax(p["Bluz"]) == 0 and np.argmin(p["Bluz"]) == 2       # mağaza çarpanı sırası
    d = m.dogrulama
    assert d["sapma_model"] < d["sapma_taban"]
    assert d["sapma_pay_model"] < d["sapma_pay_taban"]
    assert d["n_dogrulama_option"] == 12 and d["n_egitim_option"] == 48
    assert d["n_dogrulama"] == 12 * M and d["n_egitim"] == 48 * M


def test_dogrulama_option_bazinda_ayrilir():
    t = sentetik(n_option=30)
    # dışlanan option'lar eğitime hiç girmez: çıkarılmış tabloyla aynı eğitim kimliği olmaz ama
    # sayılar tutar; aynı çağrı iki kez aynı sonucu verir
    d1 = tahmin.dogrula(t, MAGAZALAR, HIZLI)
    d2 = tahmin.dogrula(t, MAGAZALAR, HIZLI)
    assert d1 == d2
    dis = np.arange(0, 6)
    d3 = tahmin.dogrula(t, MAGAZALAR, HIZLI, dislanan=dis)
    assert d3["n_dogrulama_option"] == 6 and d3["n_dogrulama"] == 6 * M and d3["n_egitim"] == 24 * M
    assert tahmin.dogrula(t[t["option"] < 3], MAGAZALAR, HIZLI) == {}       # çok az option: doğrulama yok


def test_poisson_sapma():
    assert tahmin.poisson_sapma(np.array([2.0, 0.0]), np.array([2.0, 0.0])) == pytest.approx(0.0, abs=1e-5)
    assert tahmin.poisson_sapma(np.array([0.0]), np.array([3.0])) == pytest.approx(6.0)
    assert tahmin.poisson_sapma(np.array([4.0]), np.array([2.0])) == pytest.approx(2 * (4 * np.log(2) - 2))


# ---------------------------------------------------------------- karar anı (uzun oyuncak dünya)


def test_egitim_karar_sonrasini_gormez():
    """Karar gününden sonraki satış, stok ve varışlar bozulunca öğrenme tablosu, eğitilen model ve
    kimliği değişmez; karar öncesi talep bozulunca değişir (test duyarlı)."""
    from test_ogrenme import gecmis_dunya, gecmis_tablolar

    w, t = gecmis_dunya(), gecmis_tablolar()
    karar = pd.Timestamp("2025-02-01")
    mag = w.magazalar.assign(metrekare=500, kapasite=5000)
    p = {"num_leaves": 4, "learning_rate": 0.1, "n_estimators": 20, "min_child_samples": 1}
    tablo = ogrenme.ogrenme_tablosu(t, w, karar)
    once = tahmin.Tahminci.egit(tablo, mag, p)

    bozuk = {ad: df.copy() for ad, df in t.items()}
    for ad in ("satis", "stok"):
        d = bozuk[ad]
        sonra = d["tarih"] >= karar
        assert sonra.any()
        d.loc[sonra, "adet"] = d.loc[sonra, "adet"] * 7 + 3
    sv = bozuk["sevkiyat"]
    sonra = sv["varis_tarihi"] >= karar
    sv.loc[sonra, "adet"] = sv.loc[sonra, "adet"] * 5 + 1
    tablo2 = ogrenme.ogrenme_tablosu(bozuk, w, karar)
    pd.testing.assert_frame_equal(tablo, tablo2)
    sonra_egitim = tahmin.Tahminci.egit(tablo2, mag, p)
    assert sonra_egitim.kimlik == once.kimlik

    oncesi = tablo.copy()
    oncesi["talep"] = oncesi["talep"] * 2.0
    assert tahmin.Tahminci.egit(oncesi, mag, p).kimlik != once.kimlik


# ---------------------------------------------------------------- gerçek veri


@pytest.mark.veri
def test_egitim_suresi():
    """Yayımlanan v4: SS25 karar gününden (2025-02-01) önceki kapanmış sezonlarla eğitim. Süre, satır
    sayısı ve doğrulama Poisson sapması kayıt defterine yazılır (`-s` ile görülür)."""
    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek

    from allocation import kaynak

    w = dunya_kur(Olcek.TAM)
    karar = pd.Timestamp("2025-02-01")
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con)
    finally:
        con.close()
    t0 = time.perf_counter()
    tablo = ogrenme.ogrenme_tablosu(t, w, karar)
    t1 = time.perf_counter()
    del t
    m = tahmin.Tahminci.egit(tablo, w.magazalar, tahmin.VARSAYILAN).sabitle()
    t2 = time.perf_counter()
    d = m.dogrulama
    print(f"\nogrenme tablosu {t1 - t0:.1f} sn, {len(tablo)} satir; egitim (dogrulama + son) {t2 - t1:.1f} sn")
    print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()})
    # SS24 dalga 3'ü tutarak (zaman yönünde) ikinci doğrulama
    dis = np.unique(tablo.loc[(tablo["sezon_kodu"] == sabitler.KAL_SEZONU) & (tablo["dalga"] == 3), "option"])
    d3 = tahmin.dogrula(tablo, w.magazalar, tahmin.VARSAYILAN, dislanan=dis)
    print("SS24 dalga 3:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d3.items()})
    print("kimlik", m.kimlik)

    assert d["sapma_model"] < d["sapma_taban"] and d["sapma_pay_model"] < d["sapma_pay_taban"]
    assert d3["sapma_model"] < d3["sapma_taban"]
    assert sorted(set(tablo["sezon_kodu"])) == ["AW23", "SS23", "SS24"]
    # aynı tablo aynı kimlik
    assert tahmin.Tahminci.egit(tablo, w.magazalar, tahmin.VARSAYILAN).kimlik == m.kimlik
