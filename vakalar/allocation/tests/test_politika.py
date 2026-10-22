"""`allocation.politika`: ilk dağıtım kolları, `hiz` replenishment'ı, sabit takvim.

Oyuncak dünya (`conftest`): option 2 (OPT-A, SS25 Collection, 5 beden, ilk alım 2100),
3 (OPT-B, SS25 Collection), 5 (OPT-X, SS25 Collection aksesuar, paket 6); 0 (SS23), 1 (SS24),
4 (SS25 Outlet) oyun dışı. Mağazalar M1..M4 (fiziksel, aday), MO (Outlet), ONL.

Motor testleri KÜÇÜK dünyada kısa koşu yapar (`GUN` gün; pencere 181. günde başlar): oyun
sezonu SS23'e çekilir (`Ayar(sezon="SS23")`; üç dalganın kararı pencerede), kollar gerçek
`Gorunum`'le karar verir.
"""

import copy
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from allocation import benzer, paylastir, politika, sabitler
from allocation.kaynak import harita_kur
from allocation.paylastir import TAVANSIZ
from allocation.politika import (Ayar, BelirsizlikKol, BenzerKol, EsitKol, HizReplenishment, KahinKol,
                                 LumodaTutKol, TahminKol, TakvimMarkdown, TakvimRPT)

M = 6
A, B, X = 2, 3, 5          # oyun option'ları (oyuncak)


def _gorunum(w, depo=None, gun=7, kapanacak=(), kapali=()):
    S, Mm = len(w.urunler), len(w.magazalar)
    k = np.zeros(Mm, dtype=bool)
    k[list(kapanacak)] = True
    a = np.ones(Mm, dtype=bool)
    a[list(kapali)] = False
    return SimpleNamespace(dunya=w, gun=gun, depo=np.full(S, 10**6) if depo is None else depo,
                           kapanacak=k, acik_magaza=a)


class _Temel:
    """Lumoda yerine geçen sahte kural: çağrıları sayar; plan payı 4:3:2:1 (aday mağazalar),
    toplam Lumoda'nın ifadesi (⌊ilk alım × 0,70 ÷ paket adedi⌋), en büyük kalanla."""

    def __init__(self, h):
        self.h = h
        self.cagrilar = []

    def __call__(self, g, o):
        self.cagrilar.append(o)
        w = g.dunya
        toplam = int(w.ilk_alim[o] * sabitler.LUMODA_ILK_PAYI // paylastir.paket_adedi(w, o))
        aday = paylastir.aday_maskesi(g, o, self.h)
        return paylastir.paylastir(toplam, np.array([4., 3., 2., 1., 0., 0.]), aday, en_az_gosterim=False)


@pytest.fixture
def h(dunya):
    return harita_kur(dunya)


@pytest.fixture
def temel(h):
    return _Temel(h)


def _tablo_satiri(o, m, talep, alt="Tişört", seg="giriş", kalip="regular", ust="Üst Giyim", ia=2100.0,
                  sezon="SS24"):
    return {"option": o, "magaza": m, "stoklu_gun": 0 if np.isnan(talep) else 20, "talep": talep,
            "sezon_kodu": sezon, "alt_kategori": alt, "fiyat_segmenti": seg, "kalip": kalip,
            "ust_kategori": ust, "ilk_alim": ia}


def _endeks(satirlar, en_az=1):
    return benzer.ogren(pd.DataFrame(satirlar), en_az=en_az)


def _kahin_talebi():
    return {("OPT-A", "M1"): 60.0, ("OPT-A", "M2"): 30.0, ("OPT-A", "M3"): 10.0,
            ("OPT-A", "MO"): 999.0, ("OPT-B", "M4"): 5.0}


def _kollar(temel, h, ayar=None, endeks=None):
    endeks = endeks or _endeks([_tablo_satiri(0, m, t) for m, t in enumerate([40., 30., 20., 10.])])
    return {
        "lumoda_tut": LumodaTutKol(temel, h, ayar),
        "esit": EsitKol(temel, h, ayar),
        "benzer": BenzerKol(temel, h, ayar, endeks=endeks),
        "kahin": KahinKol(temel, h, ayar, erken_talep=_kahin_talebi()),
    }


# ---------------------------------------------------------------------------
# Sözleşme: devretme, toplam
# ---------------------------------------------------------------------------


def test_kollar_listesi():
    assert politika.KOLLAR == {"lumoda_tut", "esit", "benzer", "tahmin", "kahin", "belirsizlik"}
    adlar = {k.ad for k in (LumodaTutKol, EsitKol, BenzerKol, TahminKol, KahinKol, BelirsizlikKol)}
    assert adlar == politika.KOLLAR
    assert Ayar() == Ayar(sabitler.OYUN_SEZONU, 0.0, True, True)
    for t in (-0.1, 1.0, float("nan")):
        with pytest.raises(ValueError, match="tutma"):
            Ayar(tutma=t)


@pytest.mark.parametrize("ad", ["lumoda_tut", "esit", "benzer", "kahin"])
def test_baska_sezon_lumodaya_devreder(dunya, h, temel, ad):
    """Oyun sezonunun Collection'ı dışındaki option'da kol `temel(g, o)`'yu aynen döndürür
    (SS23, SS24, SS25 Outlet); oyun option'ında temel yalnız pay kaynağıysa çağrılır. Sezon
    `Ayar.sezon`dan: SS23'e çekilince SS23 option'ı kolun, SS25'inki Lumoda'nın."""
    g = _gorunum(dunya)
    kol = _kollar(temel, h)[ad]
    for o in (0, 1, 4):
        beklenen = _Temel(h)(g, o)
        np.testing.assert_array_equal(kol(g, o), beklenen)
    assert temel.cagrilar == [0, 1, 4]
    kol(g, A)
    assert temel.cagrilar == [0, 1, 4] + ([A] if ad == "lumoda_tut" else [])
    k = kol.kayit_tablosu()
    assert list(k.columns) == politika.KAYIT_SUTUNLARI
    assert set(k.loc[~k["kol"], "arg0"]) <= {0, 1, 4} and set(k.loc[k["kol"], "arg0"]) == {A}
    assert (k.loc[~k["kol"], "U"] == -1).all()

    temel.cagrilar.clear()
    kol23 = _kollar(temel, h, Ayar(sezon="SS23"))[ad]
    np.testing.assert_array_equal(kol23(g, A), _Temel(h)(g, A))
    assert kol23.kendi_mi(0) and not kol23.kendi_mi(A) and not kol23.kendi_mi(4)
    kol23(g, 0)
    assert kol23.kayit_tablosu().query("kol")["arg0"].unique().tolist() == [0]


@pytest.mark.parametrize("ad", ["lumoda_tut", "esit", "benzer", "kahin"])
@pytest.mark.parametrize("t", [0.0, 0.30])
def test_toplam_ust_sinirla(dunya, h, temel, ad, t):
    """Gönderilen toplam ⌊U × (1 − t)⌋ paket (t = 0: ⌊U⌋, t = 0,30: ⌊0,7·U⌋; tam sayı
    aritmetiğiyle), U `ust_sinir` (Lumoda payı ya da depoda en küçük beden bağlar). Kayıtta
    U ve toplam."""
    S = len(dunya.urunler)
    kucuk = np.full(S, 10**6)
    kucuk[10] = 101          # OPT-A'nın 1. bedeni (paket içeriği 1): U = 101
    kucuk[25] = 6 * 37 + 5   # OPT-X tek beden, paket 6: U = 37
    for depo in (None, kucuk):
        g = _gorunum(dunya, depo=depo)
        kol = _kollar(temel, h, Ayar(tavan=False, tutma=t))[ad]
        for o in (A, B, X):
            U = paylastir.ust_sinir(g, o, h)
            beklenen = U * round((1 - t) * 100) // 100
            assert kol(g, o).sum() == beklenen, (o, U)
        k = kol.kayit_tablosu().groupby("arg0").first()
        assert (k["toplam"] == [U_ * round((1 - t) * 100) // 100 for U_ in k["U"]]).all()
        if depo is not None:
            assert k.loc[A, "U"] == 101 and k.loc[X, "U"] == 37


def test_lumoda_tut_t0_lumodanin_ta_kendisi(dunya, h, temel):
    """t = 0 ve U ≥ Lumoda'nın toplamı: çıktı Lumoda'nınki mağaza mağaza (Ayar.en_az_gosterim
    ve tavan etkisiz). Depo bağlayınca (U küçük) Lumoda'nın paketleri U'ya ölçeklenir: hiçbir
    mağaza Lumoda'dan fazla almaz, toplam U."""
    g = _gorunum(dunya)
    kol = LumodaTutKol(temel, h, Ayar(tavan=True, en_az_gosterim=True))
    assert kol.parametreler()["ayar"] == {"sezon": "SS25", "tutma": 0.0, "tavan": False, "en_az_gosterim": False}
    for o in (A, B, X):
        np.testing.assert_array_equal(kol(g, o), _Temel(h)(g, o))
    depo = np.full(len(dunya.urunler), 10**6)
    depo[10] = 50
    g = _gorunum(dunya, depo=depo)
    lum = _Temel(h)(g, A)
    out = kol(g, A)
    assert out.sum() == 50 and (out <= lum).all()
    np.testing.assert_array_equal(out, paylastir.paylastir(50, lum.astype(float), lum > 0, en_az_gosterim=False))


def test_esit_tavansiz(dunya, h, temel):
    """`esit` aday mağazalara eşit pay verir; tavan yok (Ayar.tavan etkisiz, spec §0/14). Aday
    olmayan (outlet, online) almaz."""
    g = _gorunum(dunya)
    kol = EsitKol(temel, h, Ayar(tavan=True))
    assert kol.parametreler() == {"kol": "esit", "ayar": {"sezon": "SS25", "tutma": 0.0, "tavan": False,
                                                          "en_az_gosterim": True}}
    out = kol(g, A)
    U = paylastir.ust_sinir(g, A, h)
    assert out.sum() == U and out[4:].sum() == 0
    assert out[:4].max() - out[:4].min() <= 1
    k = kol.kayit_tablosu()
    assert (k["tavanda"] == 0).all() and (k["duzey"] == -1).all()
    assert sorted(k["indis"]) == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# benzer, tahmin, kahin, belirsizlik
# ---------------------------------------------------------------------------


def _benzer_endeksi(ilk_alim_kati=1.0):
    """İki geçmiş option, ikisi de OPT-A'nın öznitelikleri: P küçük (M2 güçlü), Q büyük (M2
    zayıf). M2'nin endeksi yüksek, mutlak öngörüsü düşük: tavanı bağlar."""
    ia = 2100.0 * ilk_alim_kati
    P = [_tablo_satiri(0, m, t, ia=ia) for m, t in enumerate([1., 10., 1., 1.])]
    Q = [_tablo_satiri(1, m, t, ia=ia) for m, t in enumerate([1000., 10., 1000., 1000.])]
    return _endeks(P + Q, en_az=2)


def test_benzer_tavan_baglar(dunya, h, temel):
    """Pay = endeks; tavan = ⌈mutlak öngörü × TAVAN_KAPSAMA ÷ paket adedi⌉ (en az 1). M2'nin
    tavanı bağlar, artan paketler ötekilere; tavan kapalıyken M2 daha çok alır. Herkes tavanda
    ise kalan dağıtılmaz (depoda). Hiçbir adayın geçmişi yoksa (mutlak öngörü NaN) tavan yok."""
    g = _gorunum(dunya)
    e = _benzer_endeksi()
    aday = paylastir.aday_maskesi(g, A, h)
    endeks, duzey, mutlak = e.endeks(politika._oznitelik(dunya, A).iloc[0], aday)
    assert duzey == 0 and endeks[1] > endeks[0]
    tavan = np.maximum(np.ceil(mutlak[:4] * sabitler.TAVAN_KAPSAMA / 7), 1).astype(int)
    assert tavan[1] == 2

    kol = BenzerKol(temel, h, endeks=e)
    out = kol(g, A)
    U = paylastir.ust_sinir(g, A, h)
    assert out[1] == tavan[1] and out.sum() == U and (out[:4] <= tavan).all()
    k = kol.kayit_tablosu()
    assert (k["tavanda"] == 1).all() and (k["duzey"] == 0).all()
    acik = BenzerKol(temel, h, Ayar(tavan=False), endeks=e)(g, A)
    assert acik[1] > 20 and acik.sum() == U
    np.testing.assert_array_equal(acik, paylastir.paylastir(U, np.where(aday, endeks, 0), aday))

    # herkes tavanda: geçmiş option'ların ilk alımı 100 kat → öngörü 100'de bir
    kucuk = BenzerKol(temel, h, endeks=_benzer_endeksi(100.0))
    out = kucuk(g, A)
    assert out.sum() < U and (out[:4] == 1).sum() >= 1
    k = kucuk.kayit_tablosu()
    assert (k["tavanda"] == 4).all() and (k["toplam"] == U).all()

    # öngörü yok: yalnız aday olmayan MO'nun geçmişi var
    yok = _endeks([_tablo_satiri(0, 4, 50.0)])
    kol = BenzerKol(temel, h, endeks=yok)
    np.testing.assert_array_equal(kol._pay(g, A, aday)[1][:4], [TAVANSIZ] * 4)
    out = kol(g, A)
    assert out.sum() == U and out[:4].max() - out[:4].min() <= 1
    assert kol.parametreler()["endeks"] == yok.kimlik != e.kimlik


class _SahteTahminci:
    """`Tahminci` arayüzü: tahmin = metrekare ÷ 10 (özellik satırlarının aday mağazalardan
    kurulduğunu gösterir)."""

    def __init__(self):
        self.gecmis_karisim = pd.DataFrame({"magaza": np.array([], np.int64), "ozellik": [], "deger": [],
                                            "pay": np.array([], float)})
        self.kimlik = "sahte"
        self.X = None

    def sabitle(self):
        return self

    def tahmin(self, X):
        self.X = X
        return X["metrekare"].to_numpy() / 10


def test_tahmin_kolu_tahminden(dunya, h, temel):
    """Pay = tahmin (aday mağazaların özellik satırlarından, `tahmin.ozellikler`); tavan aynı
    biçimde tahminden. Tahminci kimliği parametrelerde."""
    from allocation import tahmin

    w = copy.copy(dunya)
    w.magazalar = dunya.magazalar.assign(metrekare=[700, 300, 2000, 10, 500, 0], kapasite=[1] * 6)
    g = _gorunum(w)
    t = _SahteTahminci()
    kol = TahminKol(temel, h, tahminci=t)
    out = kol(g, A)
    assert list(t.X.columns) == tahmin.OZELLIKLER and len(t.X) == 4
    assert (t.X["liste_fiyati"] == 299.99).all() and t.X["magaza_sehir"].tolist() == ["İstanbul", "Ankara",
                                                                                     "Bursa", "İzmir"]
    tavan = np.maximum(np.ceil(np.array([70., 30., 200., 1.]) / 7), 1).astype(int)    # [10, 5, 29, 1]
    U = paylastir.ust_sinir(g, A, h)
    np.testing.assert_array_equal(out[:4], tavan)      # toplam > Σ tavan: herkes tavanda
    assert out.sum() < U
    assert kol.parametreler()["tahminci"] == "sahte"
    acik = TahminKol(temel, h, Ayar(tavan=False), tahminci=t)(g, A)
    assert acik.sum() == U and acik[2] > acik[0] > acik[1] > acik[3] >= 1


def test_kahin_olculen_paydan(dunya, h, temel):
    """Pay = ölçülmüş erken talep `(option_id, magaza_id)`; ölçümü olmayan mağaza 0, aday olmayan
    (MO) yok sayılır; tavan yok. Option'da hiç ölçüm yoksa eşit (geri düşüş, kayıtta). Kimlik
    sözlüğün içeriğinden (sıradan bağımsız)."""
    g = _gorunum(dunya)
    kol = KahinKol(temel, h, Ayar(tavan=True), erken_talep=_kahin_talebi())
    assert kol.parametreler()["ayar"]["tavan"] is False
    out = kol(g, A)
    U = paylastir.ust_sinir(g, A, h)
    aday = paylastir.aday_maskesi(g, A, h)
    np.testing.assert_array_equal(out, paylastir.paylastir(U, np.array([60., 30., 10., 0., 999., 0.]), aday))
    assert out[3] == 0 and out[4] == 0 and out.sum() == U
    x = kol(g, X)
    assert x.sum() == paylastir.ust_sinir(g, X, h) and x[:4].max() - x[:4].min() <= 1
    k = kol.kayit_tablosu().groupby("arg0")["geri_dusus"].first()
    assert not k[A] and k[X]

    ters = dict(reversed(list(_kahin_talebi().items())))
    assert KahinKol(temel, h, erken_talep=ters).parametreler() == KahinKol(
        temel, h, erken_talep=_kahin_talebi()).parametreler()
    assert KahinKol(temel, h, erken_talep={**_kahin_talebi(), ("OPT-A", "M4"): 1.0}).parametreler() != \
        kol.parametreler()
    with pytest.raises(ValueError, match="erken_talep"):
        KahinKol(temel, h, erken_talep={("OPT-A", "M1"): -1.0})


def test_belirsizlik_ortalama_tbar(dunya, h, temel):
    """t option başına `t_o`dan; t_o'nun adet ağırlıklı (U × paket adedi) ortalaması t̄ = %30
    ise gönderilen toplam adet sabit t = %30'unkiyle aynıdır (option başına en çok bir paket
    yuvarlama farkı). Pay ve tavan tabandan; t_o eksik option `KeyError`, aralık dışı
    `ValueError`."""
    g = _gorunum(dunya)
    oid = dunya.optionlar["option_id"]
    U = {o: paylastir.ust_sinir(g, o, h) for o in (A, B, X)}
    pk = {o: paylastir.paket_adedi(dunya, o) for o in (A, B, X)}
    a = {o: U[o] * pk[o] for o in U}
    tbar = sabitler.BELIRSIZLIK_TBAR
    t = {A: 0.45, X: 0.15}
    t[B] = (tbar * sum(a.values()) - sum(t[o] * a[o] for o in t)) / a[B]
    assert 0 <= t[B] <= 2 * tbar
    assert np.isclose(sum(t[o] * a[o] for o in a) / sum(a.values()), tbar)

    taban = EsitKol(temel, h, Ayar(en_az_gosterim=False))
    kol = BelirsizlikKol(taban, {oid[o]: t[o] for o in t})
    sabit = EsitKol(temel, h, Ayar(en_az_gosterim=False, tutma=tbar))
    adet = sabit_adet = 0
    for o in (A, B, X):
        out = kol(g, o)
        assert out.sum() == np.floor(round(U[o] * (1 - t[o]), 9))
        adet += out.sum() * pk[o]
        sabit_adet += sabit(g, o).sum() * pk[o]
    assert abs(adet - sabit_adet) <= sum(pk.values())
    k = kol.kayit_tablosu().groupby("arg0")["t"].first()
    np.testing.assert_allclose(k.loc[[A, B, X]].to_numpy(), [t[A], t[B], t[X]])
    p = kol.parametreler()
    assert p["kol"] == "belirsizlik" and p["taban"]["kol"] == "esit" and p["ayar"]["tutma"] is None
    assert len(p["t_o"]) == 3 and kol.temel is temel
    assert p["taban"]["ayar"]["tutma"] is None
    # tabanın tutma'sı t_o'yla geçersiz: aynı davranan iki kol aynı kimlik
    t_o = {oid[o]: t[o] for o in t}
    baska = BelirsizlikKol(EsitKol(temel, h, Ayar(en_az_gosterim=False, tutma=0.15)), t_o)
    assert baska.parametreler() == p
    assert BelirsizlikKol(EsitKol(temel, h, Ayar(en_az_gosterim=True)), t_o).parametreler() != p
    assert taban.kayit_tablosu().empty           # taban kararı belirsizliğin kaydında

    with pytest.raises(KeyError, match="OPT-B"):
        BelirsizlikKol(taban, {oid[A]: 0.3})(g, B)
    with pytest.raises(ValueError, match="t_o"):
        BelirsizlikKol(taban, {oid[A]: 1.2})
    # pay ve tavan tabandan: benzer tabanlı belirsizlik tavanı uygular
    bz = BelirsizlikKol(BenzerKol(temel, h, endeks=_benzer_endeksi()), {oid[A]: 0.0})
    assert bz(g, A)[1] == 2 and bz.parametreler()["ayar"]["tavan"] is True


def test_kayit_ve_yeniden_kullanim(dunya, h, temel):
    """Kayıt `motor.Kaydedici` biçiminde (kirpma tablosu okur); `baglan` kaydı sıfırlar; gün
    geri giderse (nesne ikinci koşuda) `RuntimeError`. Boş kayıt sütunlarıyla döner. Bütün
    kolların parametreleri motor anahtarına girer (kanonik JSON)."""
    from allocation import motor

    kol = EsitKol(temel, h)
    bos = kol.kayit_tablosu()
    assert bos.empty and list(bos.columns) == politika.KAYIT_SUTUNLARI
    kol(_gorunum(dunya, gun=10), A)
    k = kol.kayit_tablosu()
    assert k[["gun", "arg0", "indis", "deger"]].dtypes.tolist() == [np.int64] * 4
    with pytest.raises(RuntimeError, match="ikinci koşu"):
        kol(_gorunum(dunya, gun=9), A)
    kol.baglan({})
    assert kol.kayit_tablosu().empty
    kol(_gorunum(dunya, gun=9), A)

    # aday mağazası olmayan kendi kararı: tek nöbetçi satır (indis −1, paket 0, özet dolu)
    bos_kol = EsitKol(temel, h)
    out = bos_kol(_gorunum(dunya, kapanacak=range(M)), A)
    assert not out.any()
    k = bos_kol.kayit_tablosu()
    assert len(k) == 1 and k["indis"].iloc[0] == -1 and k["deger"].iloc[0] == 0 and k["kol"].iloc[0]
    assert k["U"].iloc[0] == paylastir.ust_sinir(_gorunum(dunya), A, h) == k["toplam"].iloc[0]

    oid = dunya.optionlar["option_id"]
    kollar = list(_kollar(temel, h).values())
    kollar += [TahminKol(temel, h, tahminci=_SahteTahminci()), BelirsizlikKol(kol, {oid[A]: 0.2})]
    for p in kollar:
        motor._kanonik(p.parametreler())
        assert motor.politika_kimligi(p)["temel"]["tur"].endswith("_Temel")
        assert p.sabitle() is p


# ---------------------------------------------------------------------------
# hiz replenishment'ı
# ---------------------------------------------------------------------------


def _hucre(w, magaza, urun):
    m = w.magazalar["magaza_id"].tolist().index(magaza)
    s = w.urunler["urun_id"].tolist().index(urun)
    return int(np.flatnonzero((w.hucre_magaza == m) & (w.hucre_sku == s))[0])


def test_hiz_replenishment_oyuncak(dunya, h):
    """İstek = max(⌈son 14 günün stoklu gün hızı × 28⌉ − stok − yolda, 0) oyun hücrelerinde
    (ilk dağıtımı bitmiş, fiziksel, açık); pencerede stoklu gün yoksa ilk dağıtımdan bu yana
    (R16); öteki hücreler `temel`'in isteği, oyun hücresinin ötekileri 0."""
    w = dunya
    C, O, d = len(w.hucre_magaza), len(w.optionlar), 20
    satis = np.zeros((d, C), dtype=np.int16)
    stoklu = np.zeros((d, C), dtype=bool)
    stok, yolda = np.zeros(C, dtype=np.int64), np.zeros(C, dtype=np.int64)
    c1, c2, c3 = _hucre(w, "M1", "OPT-A-1"), _hucre(w, "M2", "OPT-A-2"), _hucre(w, "M3", "OPT-A-3")
    c4, c5 = _hucre(w, "M4", "OPT-A-1"), _hucre(w, "ONL", "OPT-A-1")
    cb, cg = _hucre(w, "M1", "OPT-B-1"), _hucre(w, "M1", "OPT-GA-1")
    stoklu[6:20, c1] = True                  # 14 stoklu gün, 3 satış: hız 3/14, hedef ⌈6⌉ = 6
    satis[[7, 9, 12], c1] = 1
    stok[c1], yolda[c1] = 1, 2               # istek 6 − 3 = 3
    stoklu[2:6, c2] = True                   # pencerede stoksuz; ilk dağıtımdan beri 4 gün 8 satış
    satis[2:6, c2] = 2                       # hız 2, hedef 56
    stoklu[6:20, c4] = True
    satis[10, c4] = 9                        # M4 bugün kapalı: istek 0
    stoklu[:, c5] = True
    satis[:, c5] = 5                         # ONL: istek 0
    stoklu[6:20, cb] = True
    satis[10, cb] = 9                        # OPT-B'nin ilk dağıtımı bitmedi: 0
    ilk = np.full(O, 10**6)
    ilk[A] = 1
    g = SimpleNamespace(dunya=w, gun=d, satis_gecmisi=satis, stoklu_gecmisi=stoklu, magaza_stok=stok,
                        yolda=yolda, ilk_dagitim_gun=ilk, acik_magaza=np.array([1, 1, 1, 0, 1, 1], bool))

    def temel(g):
        return np.arange(C, dtype=np.int64) + 1000

    r = HizReplenishment(temel, h)
    assert r.parametreler() == {"sezon": "SS25", "gecmis_gun": 14, "hedef_gun": 28}
    istek = r(g)
    assert istek.dtype == np.int64 and istek.shape == (C,)
    assert istek[c1] == 3 and istek[c2] == 56 and istek[c3] == 0
    assert istek[c4] == 0 and istek[c5] == 0 and istek[cb] == 0
    oyun = np.isin(w.hucre_option, [A, B, X])
    assert (istek[~oyun] == np.arange(C)[~oyun] + 1000).all() and istek[cg] == cg + 1000
    assert set(np.flatnonzero(oyun & (istek > 0))) == {c1, c2}
    assert r.hucreler(g)[[c1, c2, c3]].all() and not r.hucreler(g)[[c4, c5, cb]].any()
    # sezon başka: hepsi temel
    np.testing.assert_array_equal(HizReplenishment(temel, h, sezon="SS23")(g)[oyun], np.arange(C)[oyun] + 1000)


# ---------------------------------------------------------------------------
# Sabit takvim
# ---------------------------------------------------------------------------


def test_takvim_rpt_markdown_oyuncak(dunya):
    """`optionlar`da günün kaydı (RPT: sıfır adet ve SKU dizisi korunur; kaydı olmayan gün RPT
    yok; markdown: günün kaydedilen oranı, kaydı olmayan çağrı günü 0), ötekilerde `temel`.
    Parametreler takvimin içerik kimliği ve option listesi."""
    from allocation import motor

    O = len(dunya.optionlar)
    md = np.zeros((O, 3))
    md[A] = [0.2, 0.0, 0.2]
    md[0] = [0.5, 0.5, 0.5]
    tk = motor.Takvim(rpt={7: {A: 50, 0: 30, B: np.array([1, 2, 0, 0, 0]), X: 0}},
                      markdown={7: md}, option_sayisi=O)

    def rpt(g):
        return {0: 99, 1: 11, A: 77}

    def markdown(g):
        return np.full((O, 3), 0.1)

    r = TakvimRPT(rpt, tk, [X, A, B])
    c = r(SimpleNamespace(gun=7))
    assert sorted(c) == [0, 1, A, B, X] and c[0] == 99 and c[1] == 11 and c[A] == 50 and c[X] == 0
    np.testing.assert_array_equal(c[B], [1, 2, 0, 0, 0])
    assert r(SimpleNamespace(gun=14)) == {0: 99, 1: 11}
    assert r.parametreler() == {"takvim": tk.kimlik, "optionlar": [A, B, X]}
    assert r.temel is rpt

    m = TakvimMarkdown(markdown, tk, [A, B, X])
    c = m(SimpleNamespace(gun=7))
    np.testing.assert_array_equal(c[A], [0.2, 0.0, 0.2])
    np.testing.assert_array_equal(c[[B, X]], np.zeros((2, 3)))
    np.testing.assert_array_equal(c[[0, 1, 4]], np.full((3, 3), 0.1))
    c = m(SimpleNamespace(gun=14))
    assert not c[[A, B, X]].any() and (c[[0, 1, 4]] == 0.1).all()
    assert m.parametreler()["takvim"] == tk.kimlik
    baska = motor.Takvim(rpt={7: {A: 51}}, markdown={}, option_sayisi=O)
    assert TakvimRPT(rpt, baska, [A]).parametreler()["takvim"] != r.parametreler()["takvim"]


# ---------------------------------------------------------------------------
# Motor içinde (KÜÇÜK dünya, kısa koşu)
# ---------------------------------------------------------------------------

GUN = 300
KUCUK = {"olcek": "kucuk", "gun_sayisi": GUN, "onbellek": None}
SEZON = "SS23"     # KÜÇÜK kısa koşuda kararı pencereye düşen sezon


@pytest.fixture(scope="module")
def kucuk():
    from allocation import kaynak, motor

    w = motor.dunya("kucuk")
    return SimpleNamespace(w=w, h=kaynak.harita_kur(w), oyun=kaynak.oyun_optionlari(w, SEZON),
                           lumoda=motor.lumoda("ilk_dagitim"))


class _Denetci:
    """Kolu sarar: her kararda gerçek `Gorunum`'le `aday_maskesi`'ni ve Lumoda'nın çıktısını
    saklar, kolun çıktısını döndürür (kayıt kolun)."""

    def __init__(self, kol, lumoda, h):
        self.kol, self.lumoda, self.h = kol, lumoda, h
        self.temel = kol.temel
        self.kararlar = []

    def __call__(self, g, o):
        if self.kol.kendi_mi(o):
            self.kararlar.append((o, paylastir.aday_maskesi(g, o, self.h), self.lumoda(g, o).copy(),
                                  np.asarray(g.kapanacak).copy()))
        return self.kol(g, o)

    def parametreler(self):
        return self.kol.parametreler()

    def kayit_tablosu(self):
        return self.kol.kayit_tablosu()


def _oyun_kirpmasi(k, kucuk):
    from allocation import motor

    t = motor.kirpma_tablosu(k, kucuk.w)
    oyun = set(kucuk.w.optionlar["option_id"].to_numpy()[kucuk.oyun])
    return t[t["option_id"].isin(oyun)]


def test_aday_maskesi_lumodayla_ayni(kucuk):
    """Gerçek karar anlarında (KÜÇÜK, SS23'ün üç dalgası) Lumoda'nın paket verdiği mağazalar
    `aday_maskesi`'nin içindedir; toplam aday sayısını aşınca kümeler aynıdır. Eşit kol her
    adaya paket gönderdiğinde motor hiçbir aday mağazayı sıfırlamaz: sevkiyattaki mağazalar
    kolun paket verdiği mağazalardır (kayıt ↔ `sevkiyat`)."""
    from allocation import motor

    kol = _Denetci(EsitKol(kucuk.lumoda, kucuk.h, Ayar(sezon=SEZON)), kucuk.lumoda, kucuk.h)
    k = motor.kos(kol, ad="esit_denetim", parametreler={}, **KUCUK)
    assert {o for o, *_ in kol.kararlar} == set(kucuk.oyun.tolist())
    esit = 0
    for o, aday, lum, _ in kol.kararlar:
        assert not (lum > 0)[~aday].any(), o
        if lum.sum() >= aday.sum():
            np.testing.assert_array_equal(lum > 0, aday)
            esit += 1
    assert esit >= len(kucuk.oyun) // 2
    assert _oyun_kirpmasi(k, kucuk).empty
    kayit = k.kayitlar["ilk_dagitim"]
    kendi = kayit[kayit["kol"]]
    gonderilen = kendi[kendi["deger"] > 0].groupby("arg0")["indis"].apply(set)
    adaylar = {o: set(np.flatnonzero(a)) for o, a, *_ in kol.kararlar}
    tam = [o for o in gonderilen.index if len(gonderilen[o]) == len(adaylar[o])]
    assert len(tam) > 0
    s = k.tablolar["sevkiyat"]
    s = s[s["tip"].astype(str) == "ilk_dagitim"]
    opt = kucuk.w.urunler.set_index("urun_id")["option_id"]
    mag = kucuk.w.magazalar["magaza_id"].tolist()
    for o in tam:
        oid = kucuk.w.optionlar["option_id"].iloc[o]
        giden = set(s.loc[s["urun_id"].astype(str).map(opt) == oid, "hedef"].astype(str).map(mag.index))
        assert giden == adaylar[o], oid


def _kucuk_endeks(kucuk):
    """KÜÇÜK dünyada sahte geçmiş: AW22 Collection option'larının fiziksel mağazalarda rastgele
    erken talebi (öznitelikler dünyadan); SS23 kararları hiyerarşiyle eşleşir."""
    from allocation import ogrenme

    w, rng = kucuk.w, np.random.default_rng(3)
    gecmis = np.flatnonzero((w.optionlar["sezon_kodu"] == "AW22").to_numpy()
                            & (w.optionlar["line"] == "Collection").to_numpy())
    oz = ogrenme.option_oznitelikleri(w, gecmis)
    fiz = np.flatnonzero(kucuk.h.magaza_fiziksel)
    satir = []
    for i, o in enumerate(gecmis):
        for m in fiz:
            satir.append({"option": int(o), "magaza": int(m), "stoklu_gun": 30,
                          "talep": float(rng.gamma(2.0, 15.0)), **oz.iloc[i].to_dict()})
    return benzer.ogren(pd.DataFrame(satir), en_az=2)


def _kucuk_kahin(kucuk):
    w, rng = kucuk.w, np.random.default_rng(4)
    mag = w.magazalar["magaza_id"].to_numpy()[kucuk.h.magaza_fiziksel]
    return {(oid, m): float(rng.poisson(20) if rng.random() < 0.8 else 0)
            for oid in w.optionlar["option_id"].to_numpy()[kucuk.oyun] for m in mag}


@pytest.mark.parametrize("ad,t", [("esit", 0.0), ("esit", 0.45), ("lumoda_tut", 0.0), ("lumoda_tut", 0.30),
                                  ("benzer", 0.0), ("kahin", 0.15), ("belirsizlik", None)])
def test_kol_motorca_kirpilmaz(kucuk, ad, t):
    """Kısa KÜÇÜK koşu, oyun sezonu SS23'e çekilmiş: kolun her SS23 Collection kararı U'ya
    sığar, motor tek paket kırpmaz (`kirpma_tablosu` oyun option'larında boş); aynı koşuda
    Lumoda'nın kararları kırpılır. Kayıt her kararı taşır, gönderilen toplam = ⌊U(1−t)⌋
    (tavan bağlamadıkça)."""
    from allocation import motor

    ayar = Ayar(sezon=SEZON, tutma=t or 0.0)
    oidler = kucuk.w.optionlar["option_id"].to_numpy()[kucuk.oyun]
    t_o = dict(zip(oidler, np.random.default_rng(5).uniform(0, 2 * sabitler.BELIRSIZLIK_TBAR, len(oidler))))
    kol = {"esit": lambda: EsitKol(kucuk.lumoda, kucuk.h, ayar),
           "belirsizlik": lambda: BelirsizlikKol(EsitKol(kucuk.lumoda, kucuk.h, ayar), t_o),
           "lumoda_tut": lambda: LumodaTutKol(kucuk.lumoda, kucuk.h, ayar),
           "benzer": lambda: BenzerKol(kucuk.lumoda, kucuk.h, ayar, endeks=_kucuk_endeks(kucuk)),
           "kahin": lambda: KahinKol(kucuk.lumoda, kucuk.h, ayar, erken_talep=_kucuk_kahin(kucuk))}[ad]()
    k = motor.kos(kol, ad=f"{ad}_kirpma", parametreler={}, **KUCUK)
    assert _oyun_kirpmasi(k, kucuk).empty
    kayit = k.kayitlar["ilk_dagitim"]
    kendi = kayit[kayit["kol"]]
    assert set(kendi["arg0"]) == set(kucuk.oyun.tolist())
    ozet = kendi.groupby("arg0").agg(U=("U", "first"), toplam=("toplam", "first"), giden=("deger", "sum"),
                                     baglayan=("tavanda", "first"))
    if t is None:      # belirsizlik: option başına t_o
        t = kendi.groupby("arg0")["t"].first().to_numpy()
        np.testing.assert_allclose(t, [t_o[oidler[list(kucuk.oyun).index(o)]] for o in ozet.index])
    assert (ozet["toplam"] == np.floor(np.round(ozet["U"] * (1 - t), 9))).all()
    assert (ozet["giden"] <= ozet["toplam"]).all()
    assert (ozet.loc[ozet["baglayan"] == 0, "giden"] == ozet.loc[ozet["baglayan"] == 0, "toplam"]).all()
    if ad == "benzer":
        assert (ozet["baglayan"] > 0).any()
    # Lumoda'ya devredilen (oyun dışı) kararlar kayıtta, motor onları kırpabilir
    assert (~kayit["kol"]).any()


def test_lumoda_kosusu_oyun_sezonunda_kirpilir(kucuk):
    """Karşıt: aynı kısa koşuda Lumoda'nın SS23 Collection kararlarını motor kırpar (kolların
    U'ya sığdığı testi boş geçmesin)."""
    from allocation import motor

    k = motor.kos(ad="lumoda", parametreler={}, **KUCUK)
    assert len(_oyun_kirpmasi(k, kucuk)) > 0


def test_hiz_replenishment_yalniz_oyun_hucreleri(kucuk):
    """KÜÇÜK kısa koşuda `hiz` (SS23): her pazartesi öteki hücrelerin isteği Lumoda'nın o
    `Gorunum`'deki isteğiyle aynı; oyun hücrelerinin isteği yalnız uygun hücrelerde (oyun,
    fiziksel, açık, ilk dağıtımı bitmiş) pozitif; koşu boyunca uygun hücre ve istek var."""
    from allocation import motor

    lumoda_r = motor.lumoda("replenishment")
    oyun_h = np.isin(kucuk.h.hucre_option, kucuk.oyun)
    ozet = []

    class _Karsilastir:
        def __init__(self):
            self.r = HizReplenishment(lumoda_r, kucuk.h, sezon=SEZON)
            self.temel = lumoda_r

        def __call__(self, g):
            a = self.r(g)
            b = np.asarray(lumoda_r(g), dtype=np.int64)
            np.testing.assert_array_equal(a[~oyun_h], b[~oyun_h])
            uygun = self.r.hucreler(g)
            assert not (a[oyun_h & ~uygun] != 0).any()
            ozet.append((int(uygun.sum()), int((a[uygun] > 0).sum())))
            return a

    motor.kos(EsitKol(kucuk.lumoda, kucuk.h, Ayar(sezon=SEZON)), replenishment=_Karsilastir(),
              ad="hiz", parametreler={}, **KUCUK)
    assert len(ozet) > 10
    assert max(u for u, _ in ozet) > 0 and sum(p for _, p in ozet) > 0
