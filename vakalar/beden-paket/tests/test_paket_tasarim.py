"""Paket tasarımı (`paket_tasarim`): adaylar, uyumsuzluk, K desen, atama, depo kısıtı.

Oyuncak testleri `conftest`'in profil paylarını (`PAY`, `PROFIL`) doğrudan eğri olarak kullanır;
`veri` işaretli test SS25 karar anının gerçek eğrileriyle K = 1..4 ve mağaza desenlerini basar.
"""

from itertools import combinations, product

import numpy as np
import pandas as pd
import pytest
from conftest import PAY, PROFIL

from beden_paket import paket_tasarim as pt
from beden_paket import sabitler

S = list(pt.SUTUNLAR)
ZINCIR = np.array([0.1023, 0.2184, 0.3111, 0.2449, 0.1233])


def _egri(paylar: dict[str, tuple]) -> pd.DataFrame:
    df = pd.DataFrame([np.asarray(p, float) / np.sum(p) for p in paylar.values()],
                      index=pd.Index(list(paylar), name="magaza_id"), columns=S)
    return df


def _oyuncak() -> pd.DataFrame:
    return _egri({m: PAY[p] for m, p in PROFIL.items()})


def _agirlik(egri: pd.DataFrame, degerler=None) -> pd.Series:
    if degerler is None:
        degerler = np.arange(1, len(egri) + 1, dtype=float)
    return pd.Series(degerler, index=egri.index, dtype="float64")


def _maliyet(tasarim: pt.Tasarim, egri, agirlik) -> float:
    return sum(pt.uyumsuzluk(tasarim.desenler[i], egri.loc[m].to_numpy(), agirlik[m])
               for m, i in tasarim.atama.items())


def _yuk(tasarim: pt.Tasarim, agirlik) -> np.ndarray:
    """Beden başına giden adet (Σ ağırlık × desen)."""
    return sum(agirlik[m] * tasarim.desenler[i] for m, i in tasarim.atama.items())


# ---------------------------------------------------------------------------
# Adaylar ve uyumsuzluk
# ---------------------------------------------------------------------------


def test_adaylar_kisit():
    A = pt.adaylar()
    beklenen = sorted(p for p in product(range(8), repeat=5)
                      if sum(p) == 7 and all(p[b - 1] >= 1 for b in sabitler.CEKIRDEK_BEDENLER))
    assert A.shape == (70, 5) and A.dtype.kind == "i"
    assert [tuple(r) for r in A] == beklenen                     # tam küme, sözlük sırası
    assert tuple(sabitler.LUMODA_PAKET) in beklenen
    A12 = pt.adaylar(12)
    assert A12.shape == (715, 5) and (A12.sum(axis=1) == 12).all()
    assert (A12[:, 1:4] >= 1).all() and (A12 >= 0).all()


def test_uyumsuzluk_eksik_adet():
    e = np.array([1, 2, 2, 1.5, 0.5]) / 7
    # eksik adet: 4. bedende 0,5 eksik; 3 paket → 1,5 adet
    assert pt.uyumsuzluk((1, 2, 2, 1, 1), e, 3.0) == pytest.approx(1.5)
    assert pt.uyumsuzluk((1, 2, 2, 2, 0), e, 3.0) == pytest.approx(1.5)
    assert pt.uyumsuzluk((1, 2, 2, 1, 1), np.array([1, 2, 2, 1, 1]) / 7, 5.0) == 0.0
    # beklenen eksik adet = ağırlık × paket adedi × L1(paket payı, eğri) / 2
    p = np.array([1, 1, 2, 2, 1])
    assert pt.uyumsuzluk(p, ZINCIR, 2.0) == pytest.approx(2.0 * 7 * np.abs(p / 7 - ZINCIR).sum() / 2)


def test_en_yakin_desen_esitlikte_sozluk_sirasi():
    e = np.array([1, 2, 2, 1.5, 0.5]) / 7          # (1,2,2,1,1) ile (1,2,2,2,0) eşit
    assert tuple(pt.en_yakin_desen(e)) == (1, 2, 2, 1, 1)


# ---------------------------------------------------------------------------
# Tasarım
# ---------------------------------------------------------------------------


def test_k1_zincire_en_yakin():
    # bütün mağazalar zincir eğrisindeyse tek desen zincire en yakın 7'li pakettir
    E = _egri({f"M{i}": ZINCIR for i in range(5)})
    t = pt.tasarla(E, _agirlik(E), 1)
    assert t.desenler.shape == (1, 5)
    assert tuple(t.desenler[0]) == tuple(pt.en_yakin_desen(ZINCIR))
    bf = min(pt.adaylar(), key=lambda p: (pt.uyumsuzluk(p, ZINCIR, 1.0), tuple(p)))
    assert tuple(t.desenler[0]) == tuple(bf)
    # karışık mağazalarda K = 1 en iyi tek paket: ağırlıklı toplam uyumsuzluğun kaba kuvvet en küçüğü
    E, w = _oyuncak(), _agirlik(_oyuncak())
    t = pt.tasarla(E, w, 1)
    kaba = min(pt.adaylar(), key=lambda p: (round(sum(pt.uyumsuzluk(p, E.loc[m].to_numpy(), w[m])
                                                       for m in E.index), 9), tuple(p)))
    assert tuple(t.desenler[0]) == tuple(kaba) and t.en_iyi_mi
    assert t.toplam_uyumsuzluk == pytest.approx(_maliyet(t, E, w))


def test_tasarim_belirlenimci():
    E, w = _oyuncak(), _agirlik(_oyuncak())
    for K in (1, 2, 3, "magaza"):
        a, b = pt.tasarla(E, w, K), pt.tasarla(E, w, K)
        np.testing.assert_array_equal(a.desenler, b.desenler)
        pd.testing.assert_series_equal(a.atama, b.atama)
        # satır sırası sonucu değiştirmez
        ters = pt.tasarla(E.iloc[::-1], w.iloc[::-1], K)
        np.testing.assert_array_equal(a.desenler, ters.desenler)
        pd.testing.assert_series_equal(a.atama, ters.atama.loc[a.atama.index])
    # eşitlikte sözlük sırasında ilk desen
    E1 = _egri({"M1": (1, 2, 2, 1.5, 0.5)})
    assert tuple(pt.tasarla(E1, _agirlik(E1), 1).desenler[0]) == (1, 2, 2, 1, 1)


def test_k_arttikca_uyumsuzluk_azalir():
    E, w = _oyuncak(), _agirlik(_oyuncak())
    t = {K: pt.tasarla(E, w, K) for K in (1, 2, 3, 4, "magaza")}
    u = [t[K].toplam_uyumsuzluk for K in (1, 2, 3, 4, "magaza")]
    assert all(x >= y - 1e-12 for x, y in zip(u, u[1:]))
    assert u[0] > u[1] > u[2]
    # üç profil, üç desen: her mağaza kendi en iyi desenini alır
    assert u[2] == pytest.approx(u[-1])
    assert all(t[K].en_iyi_mi for K in t)
    # K = 2 tam arama: kaba kuvvetle aynı
    D = {m: [pt.uyumsuzluk(p, E.loc[m].to_numpy(), w[m]) for p in pt.adaylar()] for m in E.index}
    kaba = min(sum(min(D[m][i], D[m][j]) for m in E.index) for i, j in combinations(range(70), 2))
    assert u[1] == pytest.approx(kaba)


def test_her_aday_desen_alir():
    E, w = _oyuncak(), _agirlik(_oyuncak())
    for K in (1, 2, 3, 4, "magaza"):
        t = pt.tasarla(E, w, K)
        assert list(t.atama.index) == list(E.index) and t.atama.index.name == "magaza_id"
        assert t.atama.between(0, len(t.desenler) - 1).all()
        assert set(t.atama) == set(range(len(t.desenler)))        # her desen en az bir mağazada
        assert [tuple(r) for r in t.desenler] == sorted(tuple(r) for r in t.desenler)
        assert (t.desenler.sum(axis=1) == 7).all() and (t.desenler[:, 1:4] >= 1).all()
        if K != "magaza":
            assert len(t.desenler) <= K
    # üç ayrı eğri: K = 4'te en çok üç desen kullanılır
    assert len(pt.tasarla(E, w, 4).desenler) == 3
    # sıfır ağırlıklı mağaza da (maliyete girmeden) kendi eğrisine en yakın desenini alır
    w0 = w.copy()
    w0["S06"] = 0.0
    t = pt.tasarla(E, w0, 3)
    i = t.atama["S06"]
    assert all(pt.uyumsuzluk(t.desenler[i], E.loc["S06"].to_numpy(), 1.0)
               <= pt.uyumsuzluk(d, E.loc["S06"].to_numpy(), 1.0) for d in t.desenler)


def test_magaza_deseni_tam():
    E, w = _oyuncak(), _agirlik(_oyuncak())
    t = pt.tasarla(E, w, "magaza")
    for m in E.index:
        assert tuple(t.desenler[t.atama[m]]) == tuple(pt.en_yakin_desen(E.loc[m].to_numpy()))
    assert t.toplam_uyumsuzluk == pytest.approx(
        sum(min(pt.uyumsuzluk(p, E.loc[m].to_numpy(), w[m]) for p in pt.adaylar()) for m in E.index))
    assert t.en_iyi_mi and t.depo_uygun is None


def _kaba_kisitli(E, w, K, depo_payi):
    """Küçük örnekte kısıtlı tasarımın kaba kuvveti: her K desen kümesi × her atama."""
    A = pt.adaylar()
    ms = list(E.index)
    D = np.array([[pt.uyumsuzluk(p, E.loc[m].to_numpy(), w[m]) for p in A] for m in ms])
    cap = np.asarray(depo_payi) * 7 * w.sum()
    W = w.loc[ms].to_numpy()
    en_iyi = np.inf
    atamalar = np.array(list(product(range(K), repeat=len(ms))))       # [T, M]
    for kume in combinations(range(len(A)), K):
        kume = np.array(kume)
        secim = kume[atamalar]                                          # [T, M]
        yuk = np.einsum("m,tmb->tb", W, A[secim])
        uygun = (yuk <= cap + 1e-9).all(axis=1)
        if uygun.any():
            mal = D[np.arange(len(ms)), secim][uygun].sum(axis=1).min()
            en_iyi = min(en_iyi, mal)
    return en_iyi


def test_depo_kisiti():
    E = _egri({m: PAY[PROFIL[m]] for m in ("S01", "S04", "S06", "S07", "S05")})
    w = _agirlik(E, [3.0, 1.0, 2.0, 2.0, 1.0])
    serbest = pt.tasarla(E, w, 2)
    yuk = _yuk(serbest, w) / (7 * w.sum())
    # gevşek kısıt: sonuç değişmez
    gevsek = pt.tasarla(E, w, 2, depo_payi=np.full(5, 1.0))
    np.testing.assert_array_equal(gevsek.desenler, serbest.desenler)
    assert gevsek.depo_uygun and not gevsek.depo_asimi.any() and gevsek.yontem == "tam"
    # bağlayan kısıt: 5. bedende serbest tasarımın payının altında
    depo = np.array([1.0, 1.0, 1.0, 1.0, yuk[4] - 0.05])
    t = pt.tasarla(E, w, 2, depo_payi=depo)
    assert t.depo_uygun and t.en_iyi_mi and not t.depo_asimi.any() and t.yontem == "mip"
    assert (_yuk(t, w) <= depo * 7 * w.sum() + 1e-9).all()
    assert t.toplam_uyumsuzluk > serbest.toplam_uyumsuzluk
    assert t.toplam_uyumsuzluk == pytest.approx(_maliyet(t, E, w))
    assert t.toplam_uyumsuzluk == pytest.approx(_kaba_kisitli(E, w, 2, depo))
    # mağazaya özel desen de kısıta uyar
    tm = pt.tasarla(E, w, "magaza", depo_payi=depo)
    assert tm.depo_uygun and (_yuk(tm, w) <= depo * 7 * w.sum() + 1e-9).all()
    assert tm.toplam_uyumsuzluk <= t.toplam_uyumsuzluk + 1e-9
    # mağazaya özel kısıtlı tasarım üç desen kullanıyor: K = 3'te alt sınırın kendisi sonuçtur
    assert len(tm.desenler) == 3
    t3 = pt.tasarla(E, w, 3, depo_payi=depo)
    assert t3.toplam_uyumsuzluk == pytest.approx(tm.toplam_uyumsuzluk) and t3.en_iyi_mi
    assert t3.toplam_uyumsuzluk == pytest.approx(_kaba_kisitli(E, w, 3, depo))
    # sağlanamayan kısıt (her pakette 3. bedenden en az 1 adet var): en küçük aşımlı tasarım, işaretli
    imkansiz = np.array([1.0, 1.0, 0.05, 1.0, 1.0])
    t = pt.tasarla(E, w, 2, depo_payi=imkansiz)
    assert t.depo_uygun is False
    np.testing.assert_allclose(t.depo_asimi, [0, 0, w.sum() * (1 - 7 * 0.05), 0, 0], atol=1e-6)
    assert (t.desenler[:, 2] == 1).all()


def test_buyuk_paket_donusumlu():
    """12'li paket (715 aday): K = 3'te kombinasyon sayısı tam arama sınırını aşar, dönüşümlü arama."""
    E, w = _oyuncak(), _agirlik(_oyuncak())
    t1 = pt.tasarla(E, w, 1, adet=12)
    t3 = pt.tasarla(E, w, 3, adet=12)
    assert t1.yontem == "tam" and t1.en_iyi_mi and t3.yontem == "donusumlu"
    assert (t3.desenler.sum(axis=1) == 12).all()
    assert t3.toplam_uyumsuzluk < t1.toplam_uyumsuzluk
    np.testing.assert_array_equal(t3.desenler, pt.tasarla(E, w, 3, adet=12).desenler)
    # üç profil: dönüşümlü arama mağazaya özel alt sınıra erişir, en iyiliği kanıtlanır
    assert t3.en_iyi_mi
    assert t3.toplam_uyumsuzluk == pytest.approx(pt.tasarla(E, w, "magaza", adet=12).toplam_uyumsuzluk)
    # on ayrı eğri: alt sınıra erişilmezse en iyilik iddia edilmez
    rng = np.random.default_rng(7)
    E10 = _egri({f"M{i:02d}": tuple(rng.dirichlet(np.full(5, 3.0))) for i in range(10)})
    t = pt.tasarla(E10, _agirlik(E10), 3, adet=12)
    alt = pt.tasarla(E10, _agirlik(E10), "magaza", adet=12).toplam_uyumsuzluk
    assert t.yontem == "donusumlu" and t.toplam_uyumsuzluk > alt and not t.en_iyi_mi


def test_desen_profil_capraz():
    E, w = _oyuncak(), _agirlik(_oyuncak())
    t = pt.tasarla(E, w, 3)
    profil = pd.Series(PROFIL).rename_axis("magaza_id")
    c = pt.desen_profil_capraz(t, profil)
    assert list(c.columns) == [pt.desen_adi(d) for d in t.desenler]
    assert c.to_numpy().sum() == len(E)
    assert sorted(c.index) == ["buyuk", "kucuk", "orta"]
    assert ((c > 0).sum(axis=1) == 1).all()                       # her profil tek desende


def test_girdi_denetimi():
    E, w = _oyuncak(), _agirlik(_oyuncak())
    with pytest.raises(ValueError):
        pt.tasarla(E, w.drop("S01"), 2)
    with pytest.raises(ValueError):
        pt.tasarla(E, w * -1, 2)
    with pytest.raises(ValueError):
        pt.tasarla(E, w, 0)
    with pytest.raises(ValueError):
        pt.tasarla(E, w, 2, depo_payi=np.ones(4))


# ---------------------------------------------------------------------------
# Gerçek veri
# ---------------------------------------------------------------------------


@pytest.mark.veri
def test_tasarim_ss25():
    """SS25 karar anının eğrileri, eşit ağırlık: K = 1..4 ve mağaza desenleri, profil çapraz tablosu."""
    from beden_paket import egri, kaynak

    con = kaynak.baglan()
    k = kaynak.kapsam(kaynak.kapsam_tablolari(con, sabitler.KARAR_GUNU), sabitler.KARAR_GUNU)
    e = egri.magaza_egrisi(egri.egri_tablolari(con, sabitler.KARAR_GUNU), k, sabitler.KARAR_GUNU)
    w = pd.Series(1.0, index=e.magaza.index)
    lumoda = sum(pt.uyumsuzluk(sabitler.LUMODA_PAKET, r.to_numpy(), 1.0) for _, r in e.magaza.iterrows())
    print(f"\nzincir: {np.round(e.zincir, 4).tolist()}; zincire en yakın: "
          f"{pt.desen_adi(pt.en_yakin_desen(e.zincir))}; Lumoda {pt.desen_adi(sabitler.LUMODA_PAKET)} "
          f"uyumsuzluk {lumoda:.3f} (paket başına {lumoda / len(w):.4f})")
    onceki = lumoda
    for K in (1, 2, 3, 4, "magaza"):
        t = pt.tasarla(e.magaza, w, K)
        c = pt.desen_profil_capraz(t, e.profil)
        print(f"K={K}: {[pt.desen_adi(d) for d in t.desenler]} uyumsuzluk {t.toplam_uyumsuzluk:.3f} "
              f"(paket başına {t.toplam_uyumsuzluk / len(w):.4f}) en_iyi_mi={t.en_iyi_mi} yontem={t.yontem}")
        print(c.to_string() if K != "magaza" else c.loc[:, c.sum() > 0].to_string())
        assert t.toplam_uyumsuzluk <= onceki + 1e-9 and t.en_iyi_mi
        assert t.atama.index.equals(e.magaza.index)
        assert K == "magaza" or len(t.desenler) <= K
        onceki = t.toplam_uyumsuzluk
    # tanı (yalnız ölçüm): gerçek beden payıyla tasarlansaydı
    from beden_paket import hakem

    g = hakem.gercek_pay().reindex(e.magaza.index)
    for K in (1, 2, 3, "magaza"):
        t = pt.tasarla(g, w, K)
        print(f"gerçek pay K={K}: {[pt.desen_adi(d) for d in t.desenler]} "
              f"uyumsuzluk {t.toplam_uyumsuzluk:.3f}")
