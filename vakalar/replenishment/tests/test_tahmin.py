"""`replenishment.tahmin`: LightGBM özellikleri (iki yol, tek fonksiyon), eğitim seti,
içerik kimliği.

Oyuncak dünya (`_dunya`): iki fiziksel mağaza (M0 AVM, M1 Cadde) ve ONL; üç option
(o0 iki beden, o1 tek beden, o2 iki beden). Takvim dünyanın günü 0'dan
(2022-07-04, pazartesi) başlar; çevrimdışı matris `CEVRIMDISI_BAS`'tan
(2023-01-01, dünyanın 181. günü). İki yol aynı tarih için aynı özellik tablosunu
vermelidir.
"""

import pickle
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from replenishment import kaynak, tahmin
from replenishment.sabitler import EGITIM_BIT, OYUN_BAS
from replenishment.tahmin import CEVRIMDISI_BAS, OZELLIKLER, Tahminci

GUN0 = pd.Timestamp("2022-07-04")
N = 1000                     # 2022-07-04 .. 2025-03-30
TATIL = ("2024-03-06", "2024-03-07")
BF = ("2023-11-24",)


def _dunya():
    sku_option = np.array([0, 0, 1, 2, 2])
    hm, hs = [], []
    for m in (0, 1, 2):                                   # 2 = ONL
        for s in range(len(sku_option)):
            hm.append(m)
            hs.append(s)
    hm, hs = np.array(hm), np.array(hs)
    t = pd.DataFrame({"tarih": pd.date_range(GUN0, periods=N, freq="D")})
    gunler = t["tarih"].dt.strftime("%Y-%m-%d")
    t["tatil_mi"] = gunler.isin(TATIL + BF).to_numpy()
    t["black_friday_mi"] = gunler.isin(BF).to_numpy()
    return SimpleNamespace(
        hucre_magaza=hm, hucre_sku=hs, hucre_option=sku_option[hs], hucre_online=hm == 2,
        sku_option=sku_option, sku_beden_payi=np.array([0.5, 0.5, 1.0, 0.5, 0.5]),
        optionlar=pd.DataFrame({"line": ["Collection", "Basic", "NOS"],
                                "ust_kategori": ["Üst Giyim", "Aksesuar", "Alt Giyim"],
                                "beden_seti": ["Kadın Harf", "Standart", "Kadın Numara"]}),
        urunler=pd.DataFrame({"beden_sira": [1, 2, 1, 1, 2]}),
        magazalar=pd.DataFrame({"tip": ["AVM", "Cadde", "Online"]}),
        takvim=t,
    )


@pytest.fixture(scope="module")
def d():
    w = _dunya()
    h = kaynak.harita_kur(w)
    rng = np.random.default_rng(7)
    C = len(h.oc)
    satis = rng.poisson(0.8, (N, C)).astype(np.int32)
    stoklu = rng.random((N, C)) < 0.85
    satis[~stoklu & (rng.random((N, C)) < 0.7)] = 0
    return w, h, satis, stoklu


def _gorunum(satis, stoklu, tarih):
    k = int((pd.Timestamp(tarih) - GUN0).days)
    return SimpleNamespace(gun=k, tarih=pd.Timestamp(tarih), satis_gecmisi=satis[:k], stoklu_gecmisi=stoklu[:k])


# ------------------------------------------------------------------ iki yol


def test_ozellikler_iki_yol_ayni(d):
    """Aynı takvim günü: çevrimdışı matris (satır 0 = 2023-01-01, gelecek satırlar da
    içinde) ve oyuncak Görünüm (satır 0 = dünyanın günü 0, yalnız bugünden önce) →
    birebir aynı tablo. Pencere hem tatili hem gecikme bloklarını kapsar."""
    w, h, satis, stoklu = d
    off = int((pd.Timestamp(CEVRIMDISI_BAS) - GUN0).days)
    assert off == 181
    oz_cev = tahmin.oznitelik_kur(w, h, CEVRIMDISI_BAS)
    oz_gor = tahmin.gorunum_oznitelik(w, h)
    for tarih in ("2024-03-04", "2023-11-20", "2023-03-06"):
        k_cev = oz_cev.satir(tarih)
        assert oz_gor.satir(tarih) == k_cev + off
        cev = tahmin.ozellik_tablosu(satis[off:], stoklu[off:], h, oz_cev, k_cev)
        gor = tahmin.gorunum_ozellikleri(_gorunum(satis, stoklu, tarih), h, oz_gor)
        pd.testing.assert_frame_equal(cev, gor)
        assert list(cev.columns) == OZELLIKLER and len(cev) == len(h.oc_magaza)
    x = tahmin.ozellik_tablosu(satis[off:], stoklu[off:], h, oz_cev, oz_cev.satir("2024-03-04"))
    assert (x["tatil_gunu"] == 2).all() and (x["bf_gunu"] == 0).all()
    x = tahmin.ozellik_tablosu(satis[off:], stoklu[off:], h, oz_cev, oz_cev.satir("2023-11-20"))
    assert (x["tatil_gunu"] == 0).all() and (x["bf_gunu"] == 1).all()   # BF tatile karışmaz


def test_gorunum_hizasi_denetlenir(d):
    w, h, satis, stoklu = d
    yanlis = tahmin.oznitelik_kur(w, h, CEVRIMDISI_BAS)
    with pytest.raises(ValueError, match="hizalı değil"):
        tahmin.gorunum_ozellikleri(_gorunum(satis, stoklu, "2024-03-04"), h, yanlis)


def test_oznitelik_takvim_kapsamazsa_hata(d):
    w, h, _, _ = d
    with pytest.raises(ValueError, match="kapsamıyor"):
        tahmin.oznitelik_kur(w, h, "2021-01-01")


def test_ozellik_degerleri(d):
    """lag/ortalama blokları `[k−7, k−1]`'den geriye; stoklu gün; zincir yalnız fiziksel;
    kategoriler dünyanın sabit listesi."""
    w, h, satis, stoklu = d
    oz = tahmin.gorunum_oznitelik(w, h)
    k = oz.satir("2024-03-04")
    x = tahmin.ozellik_tablosu(satis, stoklu, h, oz, k)
    hafta = [np.bincount(h.oc, weights=satis[k - 7 * (i + 1):k - 7 * i].sum(0), minlength=len(h.oc_magaza))
             for i in range(8)]
    for i in range(4):
        assert np.allclose(x[f"lag{i + 1}"], hafta[i])
    assert np.allclose(x["ort4"], np.mean(hafta[:4], axis=0))
    assert np.allclose(x["ort8"], np.mean(hafta, axis=0))
    assert np.allclose(x["zincir_lag1"], hafta[0][~h.oc_online].sum())
    gorulen = np.zeros((7, len(h.oc_magaza)), bool)
    for j, gun in enumerate(range(k - 7, k)):
        gorulen[j, h.oc[stoklu[gun] | (satis[gun] > 0)]] = True
    assert np.allclose(x["stoklu_gun"], gorulen.sum(0))
    assert list(x["magaza_tipi"].cat.categories) == ["AVM", "Cadde", "Online"]
    assert list(x["line"].cat.categories) == ["Basic", "Collection", "NOS"]


def test_ozellik_karar_gunu_ve_sonrasi_okunmaz(d):
    w, h, satis, stoklu = d
    oz = tahmin.gorunum_oznitelik(w, h)
    k = oz.satir("2024-03-04")
    s2, f2 = satis.copy(), stoklu.copy()
    s2[k:] = 999
    f2[k:] = ~f2[k:]
    pd.testing.assert_frame_equal(tahmin.ozellik_tablosu(satis, stoklu, h, oz, k),
                                  tahmin.ozellik_tablosu(s2, f2, h, oz, k))


def test_hiza_gercek_dunya():
    """Gerçek (KÜÇÜK) v4 dünyasında takvim 2022-07-04'te başlar: çevrimdışı satır
    0 = 2023-01-01 = dünyanın 181. günü (`w.takvim.iloc[181:]`)."""
    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek

    w = dunya_kur(Olcek.KUCUK)
    h = kaynak.harita_kur(w)
    assert pd.Timestamp(w.takvim["tarih"].iloc[181]) == pd.Timestamp(CEVRIMDISI_BAS)
    cev, gor = tahmin.oznitelik_kur(w, h, CEVRIMDISI_BAS), tahmin.gorunum_oznitelik(w, h)
    assert cev.satir(CEVRIMDISI_BAS) == 0 and gor.satir(CEVRIMDISI_BAS) == 181
    assert gor.satir(OYUN_BAS) == cev.satir(OYUN_BAS) + 181
    assert np.array_equal(gor.tatil[181:], cev.tatil) and np.array_equal(gor.bf[181:], cev.bf)
    assert len(cev.line) == len(h.oc_magaza)


# ------------------------------------------------------------------ eğitim


def test_egitim_bit_gunu_sonrasini_gormez(d):
    """`bit_gunu` ve sonrasının satırları bozulunca (X, y) aynı; her hedef haftası
    `bit_gunu`'nden önce biter."""
    w, h, satis, stoklu = d
    oz = tahmin.oznitelik_kur(w, h, CEVRIMDISI_BAS)
    s, f = satis[181:], stoklu[181:]
    bit = oz.satir("2024-06-17")
    X, y = tahmin.egitim_seti(s, f, h, oz, bit)
    s2, f2 = s.copy(), f.copy()
    s2[bit:] = 999
    f2[bit:] = ~f2[bit:]
    X2, y2 = tahmin.egitim_seti(s2, f2, h, oz, bit)
    pd.testing.assert_frame_equal(X, X2)
    assert np.array_equal(y, y2) and len(y) > 0
    pzt = tahmin.egitim_pazartesileri(oz, bit)
    assert max(pzt) + 7 < bit and min(pzt) >= 56
    assert all(pd.Timestamp(CEVRIMDISI_BAS + pd.Timedelta(days=k)).dayofweek == 0 for k in pzt)


def test_egitim_satirlari_fiziksel_ve_gozlenebilir(d):
    """Satırlar yalnız fiziksel OC'ler ve hedef haftasında stoklu günü olanlar; hedef
    `[k+1, k+7]` satışı."""
    w, h, satis, stoklu = d
    oz = tahmin.oznitelik_kur(w, h, CEVRIMDISI_BAS)
    s, f = satis[181:].copy(), stoklu[181:].copy()
    pzt = tahmin.egitim_pazartesileri(oz, oz.satir("2023-05-01"))
    k = pzt[0]
    oc0 = int(np.flatnonzero(~h.oc_online)[0])
    c0 = np.flatnonzero(h.oc == oc0)
    s[k + 1:k + 8, c0] = 0
    f[k + 1:k + 8, c0] = False                    # oc0 hedef haftasında hiç stoklu değil
    X, y = tahmin.egitim_seti(s, f, h, oz, pzt[0] + 8)  # tek pazartesi
    fiz = np.flatnonzero(~h.oc_online)
    beklenen = [o for o in fiz if o != oc0]
    assert len(y) == len(beklenen)
    hedef = np.bincount(h.oc, weights=s[k + 1:k + 8].sum(0), minlength=len(h.oc_magaza))
    assert np.allclose(y, hedef[beklenen])
    assert np.allclose(X["lag1"], np.bincount(h.oc, weights=s[k - 7:k].sum(0), minlength=len(h.oc_magaza))[beklenen])


def _kucuk_model(d, parametreler=None):
    w, h, satis, stoklu = d
    oz = tahmin.oznitelik_kur(w, h, CEVRIMDISI_BAS)
    X, y = tahmin.egitim_seti(satis[181:], stoklu[181:], h, oz, oz.satir("2024-06-17"))
    p = parametreler or {"num_leaves": 7, "n_estimators": 20, "learning_rate": 0.1, "min_child_samples": 5}
    return Tahminci.egit(X, y, p), X


def test_kimlik_icerikten(d, tmp_path):
    """Kimlik model metninden + parametrelerden: aynı model iki pickle gidiş-dönüşünde
    (sabitlenmeden) ve dosya gidiş-dönüşünde aynı kimliği verir; parametre değişince
    kimlik değişir."""
    t, X = _kucuk_model(d)
    k = t.kimlik
    assert len(k) == 64
    iki = pickle.loads(pickle.dumps(pickle.loads(pickle.dumps(t))))
    assert iki.kimlik == k and iki.sabitle().kimlik == k
    assert np.array_equal(iki.tahmin(X), t.tahmin(X))
    sabit = t.sabitle()
    assert sabit._kimlik == k and sabit.sabitle() is sabit
    yol = tmp_path / "model.json"
    t.kaydet(yol)
    geri = Tahminci.yukle(yol)
    assert geri.kimlik == k and np.array_equal(geri.tahmin(X), t.tahmin(X))
    t2, _ = _kucuk_model(d, {"num_leaves": 7, "n_estimators": 21, "learning_rate": 0.1, "min_child_samples": 5})
    assert t2.kimlik != k
    yeniden, _ = _kucuk_model(d)
    assert yeniden.kimlik == k                      # deterministik eğitim


def test_tahmin_negatif_ve_nan_degil(d):
    t, X = _kucuk_model(d)
    p = t.tahmin(X)
    assert p.shape == (len(X),) and (p >= 0).all() and np.isfinite(p).all()
    with pytest.raises(ValueError, match="OZELLIKLER"):
        t.tahmin(X[OZELLIKLER[::-1]])


def test_sifir_hedef_reddedilir(d):
    _, X = _kucuk_model(d)
    with pytest.raises(ValueError, match="sıfır"):
        Tahminci.egit(X, np.zeros(len(X)))


def test_poisson_sapma():
    assert tahmin.poisson_sapma(np.array([0.0, 2.0]), np.array([1e-9, 2.0])) == pytest.approx(2e-6 / 2, abs=1e-9)
    assert tahmin.poisson_sapma(np.array([3.0]), np.array([1.0])) == pytest.approx(2 * (3 * np.log(3) - 2))


# ------------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_egitim_suresi(tmp_path):
    """Yol 0 eğitimi (yayımlanan DuckDB, `[2023-01-01, EGITIM_BIT)`): süre ve
    doğrulama sapması basılır (rapor ve kayıt defteri için); model doğrulamada
    gecikme öngörülerinden iyi; kaydet/yükle gidiş-dönüşü kimliği korur. Oyunun
    kullandığı model bu testin yan etkisi değildir: `python -m replenishment.oyun
    hazirlik` (`oyun.tahminci_hazirla`) `cikti/tahmin/yol0.json`'u açıkça üretir."""
    import json

    from replenishment import motor   # test: dünyayı kurmak için (karar modülü değil)

    if not kaynak.VERITABANI.exists():
        pytest.skip("v4 verisi yok (cd veri && python -m perakende_veri.v4.uret)")
    w = motor.dunya("tam")
    h = kaynak.harita_kur(w)
    con = kaynak.baglan()
    try:
        t, ozet = tahmin.cevrimdisi_egit(con, w, h, EGITIM_BIT)
    finally:
        con.close()
    print(json.dumps(ozet, ensure_ascii=False, indent=1))
    assert ozet["bit"] == EGITIM_BIT.isoformat() == "2025-08-17"
    assert ozet["dogrulama_sapma"] < min(ozet["dogrulama_sapma_lag1"], ozet["dogrulama_sapma_ort4"])
    assert t.kimlik == ozet["kimlik"]
    t.kaydet(tmp_path / "yol0.json")
    assert Tahminci.yukle(tmp_path / "yol0.json").kimlik == t.kimlik
