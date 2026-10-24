"""Haftalık dinamik program (`markdown.model`) testleri: kaba kuvvetle eşdeğerlik ve sınır davranışları."""

import itertools
import time

import numpy as np
import pytest

from markdown.model import Cozum, _satis_egrileri, coz, haftalik_satis, merdiven_indisi
from markdown.sabitler import KADEMELER, STOK_KOVA

ORAN3 = np.array([0.0, 0.30, 0.50])


def _oyuncak(*, d=None, w=(0.6, 0.4), carpan=None, oran=ORAN3, T=3, X0=100.0, kalinti=0.2,
             iade=0.1, liste=100.0, k0=0, izinli=None):
    """Üç haftalık, iki hücreli, üç basamaklı oyuncak. Talep haftadan haftaya biraz düşer."""
    d = np.array([[30.0, 20.0], [26.0, 17.0], [22.0, 14.0]])[:T] if d is None else np.asarray(d, float)
    K = len(oran)
    if carpan is None:   # basamak başına ε = 2 civarı bir çarpan, her hafta aynı
        carpan = np.tile(1.0 + 2.0 * np.asarray(oran), (T, 1))
    etkin = np.tile(np.asarray(oran, float), (T, 1))
    izinli = np.ones((T, K), bool) if izinli is None else izinli
    return dict(d=d, w=np.asarray(w, float), X0=X0, liste=liste, carpan=np.asarray(carpan, float),
                etkin_oran=etkin, k0=k0, izinli=izinli, iade=iade, kalinti=kalinti)


def _kaba_kuvvet(p):
    """Her monoton yolu ızgarasız, aynı akışkan dinamikle oynat; (en iyi ciro, en iyi yol, ikinci en iyi ciro).

    Yol, izinli olmayan basamakta kalma kuralını DP ile aynı biçimde uygular: `k' >= k` izinli
    basamakları arasından seçilir, hiçbiri yoksa kalınır."""
    T, K = p["carpan"].shape
    sonuc = []
    for yol in itertools.product(range(K), repeat=T):
        k, gecerli = p["k0"], True
        for t, kp in enumerate(yol):
            aday = [j for j in range(k, K) if p["izinli"][t, j]] or [k]
            if kp not in aday:
                gecerli = False
                break
            k = kp
        if not gecerli:
            continue
        X, ciro = p["X0"], 0.0
        for t, kp in enumerate(yol):
            sigma = min(X, sum(min(X * w, dn * p["carpan"][t, kp]) for w, dn in zip(p["w"], p["d"][t])))
            ciro += sigma * p["liste"] * (1 - p["etkin_oran"][t, kp]) * (1 - p["iade"])
            X -= sigma
        sonuc.append((ciro + p["kalinti"] * p["liste"] * X, yol))
    sonuc.sort(key=lambda s: -s[0])
    return sonuc[0][0], np.array(sonuc[0][1]), (sonuc[1][0] if len(sonuc) > 1 else None)


# --- merdiven -------------------------------------------------------------------------------------

def test_merdiven_sigdirma():
    assert merdiven_indisi(0.0) == 0
    assert merdiven_indisi(0.05) == 1                 # üstündeki en yakın basamak
    assert merdiven_indisi(0.20) == 1                 # eşitse kendisi
    assert merdiven_indisi(0.2000000001) == 1         # kayan noktalı eşitlik
    assert merdiven_indisi(0.21) == 2
    assert merdiven_indisi(0.50) == 4
    assert merdiven_indisi(0.60) == 5
    assert merdiven_indisi(0.70) == 5
    assert merdiven_indisi(0.95) == len(KADEMELER) - 1   # %70'in üstü %70'e
    assert [merdiven_indisi(k) for k in KADEMELER] == list(range(len(KADEMELER)))


# --- haftalık satış -------------------------------------------------------------------------------

def test_haftalik_satis_bicim_ve_deger():
    X = np.array([0.0, 10.0, 100.0])
    s = haftalik_satis(X, np.array([30.0, 20.0]), np.array([0.6, 0.4]), 1.0)
    assert s.shape == (3,)
    assert s[0] == 0.0
    assert s[1] == pytest.approx(10.0)          # stok sınırlı: 6 + 4
    assert s[2] == pytest.approx(50.0)          # talep sınırlı: min(60,30) + min(40,20)
    s2 = haftalik_satis(X, np.array([30.0, 20.0]), np.array([0.6, 0.4]), 1.5)
    assert s2[2] == pytest.approx(75.0)         # m talebi büyütür: min(60, 45) + min(40, 30)


def test_hizli_satis_egrisi_referansla_ayni():
    """DP'nin kullandığı sıralı-birikimli hesap, tanım olan `haftalik_satis` ile aynı (sıfır payı ve
    sıfır talepli hücreler dahil)."""
    rng = np.random.default_rng(3)
    d = rng.uniform(0, 5, 40)
    d[:4] = 0.0
    w = rng.dirichlet(np.ones(40))
    w[4:9] = 0.0
    X = np.linspace(0, 300, 61)
    m = np.array([1.0, 1.4, 2.2, 3.5])
    hizli = _satis_egrileri(X, d, w, m)
    for j, mj in enumerate(m):
        ref = np.minimum(haftalik_satis(X, d, w, mj), X)
        np.testing.assert_allclose(hizli[j], ref, rtol=1e-12, atol=1e-12)


# --- DP: kaba kuvvet ------------------------------------------------------------------------------

def _rastgele_oyuncak(tohum):
    """Çeşitli ama hep ucuz kaba kuvvetli oyuncak: stok talebe göre bol, esneklik 2..7, ε hafta başına."""
    rng = np.random.default_rng(tohum)
    oran = np.array([0.0, 0.20, 0.50])
    eps = rng.uniform(2.0, 7.0, size=(3, 1))
    carpan = 1.0 + eps * oran[None] * rng.uniform(0.8, 1.2, size=(3, 3))
    carpan[:, 0] = 1.0
    return _oyuncak(d=rng.uniform(2.0, 14.0, size=(3, 2)), carpan=carpan, oran=oran,
                    kalinti=float(rng.uniform(0.0, 0.3)), iade=float(rng.uniform(0.0, 0.2)),
                    X0=float(rng.uniform(60.0, 140.0)))


@pytest.mark.parametrize("tohum", range(12))
def test_dp_kaba_kuvvet(tohum):
    """DP'nin yolu, bütün monoton yolların ızgarasız en iyisine eşittir.

    DP yolu başlı başına uygulanabilir bir yol olduğundan kaba kuvvetin en iyisinden büyük olamaz;
    yolun kendisi ızgarasız oynatıldığı için ince ızgarada (kova=2001) fark yalnız karar eşiğindeki
    enterpolasyon hatasıdır. Ölçülen en kötü fark ~3e-12 TL (hatta kova=48'de de); bütçe brief'teki
    mutlak 1e-6 TL."""
    p = _rastgele_oyuncak(tohum)
    en_iyi, yol, ikinci = _kaba_kuvvet(p)
    c = coz(**p, kova=2001)
    assert isinstance(c, Cozum)
    assert c.beklenen_ciro <= en_iyi + 1e-9
    assert c.beklenen_ciro == pytest.approx(en_iyi, abs=1e-6)
    if ikinci is not None and en_iyi - ikinci > 1.0:      # kazanan açık farkla tekse yol da aynıdır
        np.testing.assert_array_equal(c.kademe, yol)


def test_dp_kaba_kuvvet_cesitli():
    """Kaba kuvvet testi anlamlı: tohumlar farklı yollar (sıfırdan farklı, derinleşen) üretiyor."""
    yollar = {tuple(_kaba_kuvvet(_rastgele_oyuncak(s))[1]) for s in range(12)}
    assert len(yollar) >= 3
    assert any(max(y) > 0 for y in yollar)


def test_dp_kaba_kuvvet_indirim_kazandirir():
    """Oyuncakta indirim gerçekten seçiliyor: kaba kuvvetin en iyi yolu sıfır olmayan basamak içerir.

    (Testin anlamlı olması için: hepsi 0 olsaydı DP ile kaba kuvvet trivial olarak eşleşirdi.)"""
    p = _oyuncak(d=[[8.0, 5.0], [8.0, 5.0], [8.0, 5.0]], kalinti=0.1)
    en_iyi, yol, _ = _kaba_kuvvet(p)
    assert yol.max() > 0
    c = coz(**p, kova=2001)
    assert c.beklenen_ciro == pytest.approx(en_iyi, abs=1e-6)
    np.testing.assert_array_equal(c.kademe, yol)
    assert np.all(np.diff(c.kademe) >= 0)


def test_dp_kaba_kuvvet_izinli_ve_k0():
    """İzinli maskesi ve başlangıç basamağı da kaba kuvvette aynı."""
    izinli = np.array([[True, False, True], [False, False, False], [True, True, False]])
    p = _oyuncak(d=[[10.0, 6.0], [9.0, 6.0], [8.0, 5.0]], kalinti=0.1, izinli=izinli, k0=1)
    en_iyi, yol, _ = _kaba_kuvvet(p)
    c = coz(**p, kova=2001)
    assert c.beklenen_ciro == pytest.approx(en_iyi, abs=1e-6)


# --- sınır davranışları ---------------------------------------------------------------------------

def test_dp_stok_sifir():
    p = _oyuncak(X0=0.0)
    c = coz(**p)
    np.testing.assert_array_equal(c.kademe, np.zeros(3, int))
    assert c.beklenen_ciro == 0.0
    assert c.beklenen_kalan == 0.0
    np.testing.assert_array_equal(c.beklenen_satis, np.zeros(3))


def test_dp_bol_talep():
    """Talep stoku fersah fersah aşarsa indirim gereksiz: ilk hafta satış zaten stok kadar."""
    p = _oyuncak(d=np.full((3, 2), 500.0))
    c = coz(**p)
    np.testing.assert_array_equal(c.kademe, np.zeros(3, int))
    assert c.beklenen_kalan == pytest.approx(0.0)


def test_dp_esneklik_sifira_yakin():
    """ε → 0: çarpan ≈ 1, indirim satışı artırmaz, yalnız fiyatı düşürür."""
    p = _oyuncak(carpan=np.ones((3, 3)) + np.array([0.0, 1e-6, 2e-6]), d=[[8.0, 5.0]] * 3)
    c = coz(**p)
    np.testing.assert_array_equal(c.kademe, np.zeros(3, int))


def test_dp_esneklik_sonsuza_giderken():
    """ε → ∞ (spec §3.3): her pozitif basamak talebi sınırsız büyütür, en sığ indirim bile stoğu o hafta eritir.
    Kalıntı en sığ basamağın net fiyatının altındaysa DP tam fiyatta satar, son hafta en sığ basamağa iner, kalan 0;
    derin basamak hiç seçilmez (aynı stok daha ucuza satılırdı). Kaba kuvvetle aynı; ε büyüdükçe kalan azalır."""
    d = [[8.0, 5.0]] * 3                                            # tam fiyatta haftada 13 adet, stok 100
    kalan = []
    for eps in (0.5, 2.0, 8.0, 60.0):
        p = _oyuncak(d=d, carpan=np.tile((1.0 - ORAN3) ** -eps, (3, 1)), kalinti=0.2)
        c = coz(**p, kova=2001)
        en_iyi, _, _ = _kaba_kuvvet(p)
        assert c.beklenen_ciro == pytest.approx(en_iyi, rel=1e-6), eps
        kalan.append(c.beklenen_kalan)
    np.testing.assert_array_equal(c.kademe, [0, 0, 1])
    assert c.beklenen_kalan == pytest.approx(0.0, abs=1e-6)
    assert c.beklenen_ciro == pytest.approx(26 * 90.0 + 74 * 63.0, rel=1e-9)     # 2 hafta tam fiyat, kalan %30'da
    assert all(a >= b - 1e-9 for a, b in zip(kalan, kalan[1:])) and kalan[0] > 0


def test_dp_kalinti_yuksek():
    """Kalıntı değeri ≥ 1: kalan stok satıştan değerli, indirim yok."""
    for kalinti in (1.0, 1.5):
        p = _oyuncak(d=[[8.0, 5.0]] * 3, kalinti=kalinti)
        c = coz(**p)
        np.testing.assert_array_equal(c.kademe, np.zeros(3, int))


def test_sigilasmaz():
    """Başlangıç basamağı k0 = 3 ise hiçbir hafta 3'ün altında kalmaz; yol monotondur."""
    oran = np.array(KADEMELER)
    K = len(oran)
    T = 6
    rng = np.random.default_rng(7)
    for _ in range(5):
        d = rng.uniform(3, 20, size=(T, 4))
        carpan = np.tile(1.0 + rng.uniform(0.5, 2.5) * oran, (T, 1))
        p = _oyuncak(d=d, w=np.full(4, 0.25), carpan=carpan, oran=oran, T=T, X0=200.0,
                     kalinti=float(rng.uniform(0, 0.5)), k0=3)
        c = coz(**p)
        assert c.kademe.min() >= 3
        assert np.all(np.diff(c.kademe) >= 0)
    # k0 = 3 iken satış yolu k0 = 0'dan daha dar bir kümede aranır; kaba kuvvet de aynı: ciro k0=3 <= k0=0
    p0 = dict(p, k0=0)
    assert coz(**p0).beklenen_ciro >= c.beklenen_ciro - 1e-9


def test_izinli_maskesi():
    """İzinli olmayan basamak seçilmez; hiçbir izinli k' >= k yoksa kalınır."""
    oran = np.array(KADEMELER)
    K, T = len(oran), 5
    d = np.full((T, 3), 5.0)
    carpan = np.tile(1.0 + 2.0 * oran, (T, 1))
    # yalnız %0 ve %50 izinli: DP başka bir şey seçemez
    izinli = np.zeros((T, K), bool)
    izinli[:, [0, 4]] = True
    p = _oyuncak(d=d, w=np.full(3, 1 / 3), carpan=carpan, oran=oran, T=T, X0=100.0, kalinti=0.0,
                 izinli=izinli)
    c = coz(**p)
    assert set(c.kademe.tolist()) <= {0, 4}
    # hiçbir hafta izinli değil: k0'da kalınır
    p2 = dict(p, izinli=np.zeros((T, K), bool), k0=2)
    c2 = coz(**p2)
    np.testing.assert_array_equal(c2.kademe, np.full(T, 2))
    # k0 = 5 iken yalnız %0 ve %50 izinli: ikisi de k0'ın altında; 5'te kalınır
    p3 = dict(p, k0=5)
    np.testing.assert_array_equal(coz(**p3).kademe, np.full(T, 5))
    # 3. haftadan sonra hiçbir şey izinli değilse o haftalar kalınır
    izn = izinli.copy()
    izn[2:] = False
    c4 = coz(**dict(p, izinli=izn))
    assert np.all(c4.kademe[2:] == c4.kademe[1])


def test_belirlenimci_ve_esitlikte_siglik():
    """Aynı girdi aynı çıktı; iki basamak eşit değerliyse sığ olan seçilir."""
    # iki basamak birebir aynı çarpan ve oran: eşit değer
    oran = np.array([0.0, 0.3, 0.3])
    carpan = np.array([[1.0, 1.5, 1.5]] * 3)
    p = _oyuncak(d=[[8.0, 5.0]] * 3, oran=oran, carpan=carpan, kalinti=0.0)
    a, b = coz(**p), coz(**p)
    np.testing.assert_array_equal(a.kademe, b.kademe)
    assert a.beklenen_ciro == b.beklenen_ciro
    assert a.kademe.tolist() == [1, 1, 1]       # indirim kazandırıyor; eşit iki basamaktan sığ olanı


def test_esitlik_payi():
    """Kayan nokta gürültüsü kadar (göreli ~1e-14) üstün derin basamak, eşit sayılır; sığ olan seçilir."""
    oran = np.array([0.0, 0.3, 0.3])
    carpan = np.array([[1.0, 1.5, 1.5 * (1 + 1e-14)]] * 3)
    p = _oyuncak(d=[[8.0, 5.0]] * 3, oran=oran, carpan=carpan, kalinti=0.0)
    assert coz(**p).kademe.tolist() == [1, 1, 1]
    carpan[:, 2] = 1.5 * (1 + 1e-6)     # gerçekten daha iyi: derin seçilir
    assert 2 in coz(**dict(p, carpan=carpan)).kademe.tolist()


def test_yol_tutarliligi():
    """Rapor edilen yol kendi içinde tutarlı: ciro, satış ve kalan aynı akışkan dinamikten çıkar."""
    p = _oyuncak(d=[[10.0, 6.0], [9.0, 6.0], [8.0, 5.0]], kalinti=0.15)
    c = coz(**p)
    X, ciro = p["X0"], 0.0
    for t in range(3):
        k = c.kademe[t]
        s = min(X, sum(min(X * w, dn * p["carpan"][t, k]) for w, dn in zip(p["w"], p["d"][t])))
        assert c.beklenen_satis[t] == pytest.approx(s)
        ciro += s * p["liste"] * (1 - p["etkin_oran"][t, k]) * (1 - p["iade"])
        X -= s
    assert c.beklenen_kalan == pytest.approx(X)
    assert c.beklenen_ciro == pytest.approx(ciro + p["kalinti"] * p["liste"] * X)


def test_hiz_gercek_olcek():
    """T=17, 600 hücre, 6 basamak, 48 kova: tek çözüm 50 ms'nin çok altında (ölçülen ~ onda biri)."""
    T, N, K = 17, 600, len(KADEMELER)
    rng = np.random.default_rng(1)
    d = rng.uniform(0.0, 1.0, size=(T, N))
    w = rng.dirichlet(np.ones(N))
    oran = np.array(KADEMELER)
    carpan = np.tile(1.0 + 1.8 * oran, (T, 1))
    etkin = np.tile(oran, (T, 1))
    kw = dict(d=d, w=w, X0=500.0, liste=900.0, carpan=carpan, etkin_oran=etkin, k0=0,
              izinli=np.ones((T, K), bool), iade=0.08, kalinti=0.3, kova=STOK_KOVA)
    coz(**kw)          # ısınma
    en_az = min(_sure(lambda: coz(**kw)) for _ in range(5))
    assert en_az < 0.050, f"coz {en_az * 1000:.1f} ms"


def _sure(f):
    t0 = time.perf_counter()
    f()
    return time.perf_counter() - t0


def test_hizlandirma_yardimcilari_birebir():
    """Toplu satış eğrileri, satır satır enterpolasyon ve tek satır seçim; özgün hesaplarla bit düzeyinde
    aynı (hızlandırma davranışı değiştirmez)."""
    from markdown.model import _interp_satirlar, _satis_egrileri_hepsi, _sec, _sec_tek
    rng = np.random.default_rng(7)
    T, N, K, B = 5, 9, 6, 11
    X = np.linspace(0.0, 37.0, B)
    d = rng.gamma(1.0, 2.0, (T, N))
    d[:, 2] = 0.0
    w = rng.dirichlet(np.ones(N))
    w[4] = 0.0
    m = rng.uniform(1.0, 4.0, (T, K))
    hepsi = _satis_egrileri_hepsi(X, d, w, m)
    for t in range(T):
        np.testing.assert_array_equal(hepsi[t], _satis_egrileri(X, d[t], w, m[t]))
    F = rng.normal(size=(K, B))
    for x in (0.0, X[3], 0.5 * (X[3] + X[4]), 36.99, X[-1], 40.0, 1e-300):
        np.testing.assert_array_equal(_interp_satirlar(x, X, F), [np.interp(x, X, F[k]) for k in range(K)])
    for _ in range(50):
        q = rng.normal(size=K)
        q[rng.integers(K)] = q.max()                       # eşitlik
        aday = rng.random(K) < 0.6
        aday[rng.integers(K)] = True
        assert _sec_tek(q, aday) == int(_sec(q[:, None], aday[None, :])[1][0, 0])
