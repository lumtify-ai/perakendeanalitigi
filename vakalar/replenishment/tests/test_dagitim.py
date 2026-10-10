"""`replenishment.dagitim`: kısıtlı dağıtım (spec §3.4–3.5, §0 karar 10).

Oyuncak dünya: `n` fiziksel mağaza (M1…Mn) ve ONL (son mağaza); option'lar
beş bedenli, paket [1, 2, 2, 1, 1] (koli 7 adet). SKU `5o + b` option `o`'nun
`b`. bedeni (beden sırasıyla); hücre `m × S + s` (her mağazada her SKU).
Mağaza–option çifti (OC) sırası `harita_kur`'unki: (mağaza, option) artan.

Defter testte doğrudan kurulur (`kapali`, `acik` açık alanlar); `dagit`
düşümü kendisi yapar. KÜÇÜK dünya testi (`test_motor_maskesi_motorla_ayni`)
gerçek motorla koşar (testler `perakende_veri`'yi içe aktarabilir; modül
aktaramaz, `tests/test_sizinti.py`).
"""

from math import inf
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from replenishment import sabitler
from replenishment.dagitim import (
    KISITSIZ,
    KOLI_KURALLARI,
    KoliKurali,
    dagit,
    koli_uygun,
    motor_maskesi,
)
from replenishment.defter import GolgeDefter

PAKET = np.array([1, 2, 2, 1, 1])
B = 5


def _dunya(magaza=3, option=1):
    M, O = magaza + 1, option
    S = B * O
    paketler = pd.DataFrame({"paket_id": ["PKT01"] * B, "beden_seti": ["Harf"] * B,
                             "beden_sira": [1, 2, 3, 4, 5], "adet": PAKET})
    optionlar = pd.DataFrame({"line": ["Collection"] * O, "beden_seti": ["Harf"] * O,
                              "lansman_gun": [0] * O, "cikis_gun": [10**6] * O})
    urunler = pd.DataFrame({"beden_sira": [1, 2, 3, 4, 5] * O})
    magazalar = pd.DataFrame({"magaza_id": [f"M{i + 1}" for i in range(magaza)] + ["ONL"],
                              "tip": ["AVM"] * magaza + ["Online"]})
    hm = np.repeat(np.arange(M), S)
    hs = np.tile(np.arange(S), M)
    so = np.repeat(np.arange(O), B)
    return SimpleNamespace(
        paketler=paketler, optionlar=optionlar, urunler=urunler, magazalar=magazalar,
        sku_option=so, hucre_sku=hs, hucre_magaza=hm, hucre_option=so[hs],
        hucre_online=hm == magaza, hucre_outlet_akisi=np.zeros(M * S, dtype=bool),
    )


def _S(w):
    return len(w.sku_option)


def _OC(w):
    return len(w.magazalar) * len(w.optionlar)


def _hucre(w, m, s):
    return m * _S(w) + s


def _istek(w, ihtiyac: dict) -> np.ndarray:
    """{(mağaza, option): [5] beden ihtiyacı} → [C]."""
    x = np.zeros(len(w.hucre_sku), dtype=np.int64)
    for (m, o), v in ihtiyac.items():
        for b, a in enumerate(v):
            x[_hucre(w, m, B * o + b)] = a
    return x


def _defter(w, acik=None, kapali=None):
    d = GolgeDefter(w, sabitler.ACIK_PAYI)
    if acik is not None:
        d.acik = np.asarray(acik, dtype=np.int64).copy()
    if kapali is not None:
        d.kapali = np.asarray(kapali, dtype=np.int64).copy()
    return d


def _dagit(w, defter, istek, **kw):
    ayar = dict(kural=KOLI_KURALLARI["A"](), tavan=inf, oncelik="cover",
                ongoru_oc=np.ones(_OC(w)), eldeki_c=np.zeros(len(w.hucre_sku), dtype=np.int64),
                maske_c=~np.asarray(w.hucre_online))
    ayar.update(kw)
    return dagit(istek, defter, w, **ayar)


def _oc_toplam(w, sevk, o=0):
    """Fiziksel mağaza başına option `o`'ya giden adet."""
    n = len(w.magazalar) - 1
    return [int(sum(sevk.hucre_adet[_hucre(w, m, B * o + b)] for b in range(B))) for m in range(n)]


def _beden(w, sevk, m, o=0):
    return [int(sevk.hucre_adet[_hucre(w, m, B * o + b)]) for b in range(B)]


# ------------------------------------------------------------- koli kuralı


def test_koli_kurali_a():
    a = KOLI_KURALLARI["A"]()          # α = 0,6, β = 2
    assert not koli_uygun(np.array([0, 0, 5, 0, 0]), PAKET, a)   # tek beden
    assert koli_uygun(np.array([1, 2, 2, 1, 1]), PAKET, a)
    # Σn = 4 < 0,6 × 7 = 4,2
    assert not koli_uygun(np.array([1, 1, 1, 1, 0]), PAKET, a)
    # Σn yeter ama bir bedende açık (2 − 0) = 2, β'yı geçer
    assert not koli_uygun(np.array([3, 0, 2, 1, 1]), PAKET, a)
    # koli adedi içerikten: aksesuar kolisi (6 adet, tek beden)
    assert koli_uygun(np.array([5]), np.array([6]), a)          # 5 ≥ 3,6 ve 6 − 5 < 2
    assert not koli_uygun(np.array([4]), np.array([6]), a)      # 6 − 4 = 2, β'yı geçer
    assert not koli_uygun(np.array([3]), np.array([6]), a)      # 3 < 0,6 × 6


def test_koli_kurali_b_ve_c():
    b = KOLI_KURALLARI["B"](gamma=0.6)
    assert koli_uygun(np.array([1, 1, 1, 1, 1]), PAKET, b)      # 5/7
    assert not koli_uygun(np.array([0, 1, 1, 1, 0]), PAKET, b)  # 3/7
    assert not koli_uygun(np.array([0, 9, 9, 0, 0]), PAKET, b)  # min(içerik, n): 4/7
    n = np.array([1, 2, 2, 1, 0])                                # A geçer, 6/7 < 0,9
    assert koli_uygun(n, PAKET, KOLI_KURALLARI["A"]())
    assert not koli_uygun(n, PAKET, KOLI_KURALLARI["C"](gamma=0.9))
    assert koli_uygun(PAKET, PAKET, KOLI_KURALLARI["C"]())


def test_koli_kurali_yok_ve_dogrulama():
    assert not koli_uygun(PAKET * 9, PAKET, KOLI_KURALLARI["yok"]())
    assert set(KOLI_KURALLARI) == {"yok", "A", "B", "C"}
    with pytest.raises(ValueError):
        KoliKurali("A", None, 2, None)       # A α ister
    with pytest.raises(ValueError):
        KoliKurali("Z", None, None, None)


# ------------------------------------------------------- sıra: önce açık


def test_once_acik_sonra_koli():
    """İki koliye denk ihtiyaç; açıkta bir koli kadar adet, kapalıda bol koli.
    Önce açık gider (7 adet), kalan [1, 2, 2, 1, 1] A kuralını geçer: 1 koli.
    (v2 sırasında, önce koli, iki koli gider ve açık hiç kullanılmazdı.)"""
    w = _dunya(magaza=1)
    d = _defter(w, acik=PAKET, kapali=[5])
    sevk = _dagit(w, d, _istek(w, {(0, 0): 2 * PAKET}))
    assert sevk.acik_adet == 7 and sevk.koli_sayisi == 1 and sevk.koli_adet == 7
    assert _beden(w, sevk, 0) == (2 * PAKET).tolist()
    assert d.acik.sum() == 0 and d.kapali.tolist() == [4]


def test_koli_acilmaz():
    """Açık stok 0, kapalı koli var, tek bedende 3 adet ihtiyaç: kural geçmez,
    hiçbir şey gitmez; açık stok kapalıdan artmaz (hiçbir kuralda)."""
    w = _dunya(magaza=1)
    istek = _istek(w, {(0, 0): [0, 0, 3, 0, 0]})
    for ad in ("yok", "A", "B", "C"):
        d = _defter(w, acik=np.zeros(5), kapali=[5])
        sevk = _dagit(w, d, istek, kural=KOLI_KURALLARI[ad]())
        assert sevk.hucre_adet.sum() == 0 and sevk.koli_sayisi == 0
        assert d.acik.sum() == 0 and d.kapali.tolist() == [5]


def test_koli_acilmaz_rastgele():
    """Kısıtlı her çağrıda: açık stok yalnız azalır, kapalı yalnız tam koli
    azalır; mağazaya giden = açıktan düşen + koli × içerik (SKU başına)."""
    rng = np.random.default_rng(7)
    w = _dunya(magaza=4, option=2)
    for _ in range(40):
        acik = rng.integers(0, 6, _S(w))
        kapali = rng.integers(0, 4, 2)
        d = _defter(w, acik, kapali)
        istek = rng.integers(0, 4, len(w.hucre_sku))
        ad = rng.choice(["yok", "A", "B", "C"])
        sevk = _dagit(w, d, istek, kural=KOLI_KURALLARI[ad](), tavan=float(rng.integers(0, 30)),
                      oncelik=rng.choice(["cover", "ihtiyac", "esit", "orantili"]))
        assert (d.acik <= acik).all() and (d.kapali <= kapali).all()
        giden = np.bincount(w.hucre_sku, sevk.hucre_adet, minlength=_S(w))
        koli = kapali - d.kapali
        assert np.array_equal(giden, (acik - d.acik) + koli[w.sku_option] * np.tile(PAKET, 2))
        assert sevk.koli_sayisi == koli.sum() and sevk.koli_adet == 7 * koli.sum()
        assert sevk.acik_adet == (acik - d.acik).sum()


def test_kural_gecmezse_koli_gitmez():
    """M + L ihtiyacına (S, XS, XL'yi şişirecek) koli gitmez, A kuralıyla;
    açıkta M varsa o gider, kalan için yine koli yok."""
    w = _dunya(magaza=1)
    istek = _istek(w, {(0, 0): [0, 0, 2, 1, 0]})
    d = _defter(w, acik=np.zeros(5), kapali=[9])
    sevk = _dagit(w, d, istek)
    assert sevk.hucre_adet.sum() == 0 and d.kapali.tolist() == [9]
    d = _defter(w, acik=[0, 0, 1, 0, 0], kapali=[9])
    sevk = _dagit(w, d, istek)
    assert _beden(w, sevk, 0) == [0, 0, 1, 0, 0] and sevk.koli_sayisi == 0


def test_koli_her_koliden_sonra_yeniden_degerlendirilir():
    """Kalan ihtiyaç 1,5 koli: ilk koliden sonra kalan [1, 1, 1, 0, 0] A'yı
    geçmez, ikinci koli gitmez."""
    w = _dunya(magaza=1)
    d = _defter(w, acik=np.zeros(5), kapali=[9])
    sevk = _dagit(w, d, _istek(w, {(0, 0): [2, 3, 3, 1, 1]}))
    assert sevk.koli_sayisi == 1 and _beden(w, sevk, 0) == PAKET.tolist()


# ------------------------------------------------------------------- tavan


def test_tavan_asilmaz():
    w = _dunya(magaza=3)
    istek = _istek(w, {(m, 0): [2, 2, 2, 2, 2] for m in range(3)})
    d = _defter(w, acik=np.full(5, 100), kapali=[0])
    sevk = _dagit(w, d, istek, tavan=7.5, kural=KOLI_KURALLARI["yok"]())
    assert sevk.acik_adet == 7 and sevk.hucre_adet.sum() == 7
    assert sevk.tavan_dolulugu == 1.0                  # bağlayan kesirli tavan: ⌊7,5⌋ = 7 dolu
    # Koli tavana sayılmaz: tavan 0'da da tam koli gider
    d = _defter(w, acik=np.full(5, 100), kapali=[5])
    sevk = _dagit(w, d, _istek(w, {(0, 0): PAKET}), tavan=0.0)
    assert sevk.acik_adet == 0 and sevk.koli_sayisi == 1 and sevk.tavan_dolulugu == 0.0
    # orantılı öncelikte de
    d = _defter(w, acik=np.full(5, 100), kapali=[0])
    sevk = _dagit(w, d, istek, tavan=7.5, oncelik="orantili")
    assert sevk.acik_adet == 7


def test_tavan_dolulugu_kesirli_tavanda():
    """Doluluk ⌊tavan⌋'a bölünür: bağlayan kesirli tavan 1,0; bağlamayan
    kesir; ⌊tavan⌋ = 0 iken 0; koli tavana sayılmaz (sonlu tavanda da)."""
    w = _dunya(magaza=2)
    for oncelik in ("cover", "orantili"):
        d = _defter(w, acik=np.full(5, 100), kapali=[0])
        sevk = _dagit(w, d, _istek(w, {(0, 0): [9] * 5, (1, 0): [9] * 5}), tavan=12.9,
                      oncelik=oncelik, kural=KOLI_KURALLARI["yok"]())
        assert sevk.acik_adet == 12 and sevk.tavan_dolulugu == 1.0
    d = _defter(w, acik=np.full(5, 100), kapali=[0])
    sevk = _dagit(w, d, _istek(w, {(0, 0): [1, 1, 1, 0, 0]}), tavan=12.9)
    assert sevk.tavan_dolulugu == pytest.approx(3 / 12)
    d = _defter(w, acik=np.full(5, 100), kapali=[3])
    sevk = _dagit(w, d, _istek(w, {(0, 0): PAKET}), tavan=0.7)
    assert sevk.acik_adet == 0 and sevk.koli_sayisi == 1 and sevk.tavan_dolulugu == 0.0
    # Koli tavana sayılmaz: tavan 2, açık 2 adet + 1 koli (7 adet) gider, doluluk 1,0
    d = _defter(w, acik=[0, 0, 2, 0, 0], kapali=[3])
    sevk = _dagit(w, d, _istek(w, {(0, 0): PAKET + np.array([0, 0, 2, 0, 0])}), tavan=2.0)
    assert sevk.acik_adet == 2 and sevk.koli_sayisi == 1 and sevk.tavan_dolulugu == 1.0


def test_tavan_sonsuzken_doluluk_sifir():
    w = _dunya(magaza=1)
    d = _defter(w, acik=np.full(5, 100), kapali=[0])
    sevk = _dagit(w, d, _istek(w, {(0, 0): [1, 1, 1, 1, 1]}))
    assert sevk.acik_adet == 5 and sevk.tavan_dolulugu == 0.0


# --------------------------------------------------------------- öncelik


def _uc_magaza(oncelik):
    """Tek SKU'da (M bedeni) 6 açık adet; ihtiyaç M1 6, M2 3, M3 2; öngörü
    M1 1, M2 5, M3 3; mağaza stoğu yok."""
    w = _dunya(magaza=3)
    istek = _istek(w, {(0, 0): [0, 0, 6, 0, 0], (1, 0): [0, 0, 3, 0, 0], (2, 0): [0, 0, 2, 0, 0]})
    d = _defter(w, acik=[0, 0, 6, 0, 0], kapali=[0])
    ongoru = np.array([1.0, 5.0, 3.0, 1.0])            # OC: M1, M2, M3, ONL
    sevk = _dagit(w, d, istek, oncelik=oncelik, ongoru_oc=ongoru, kural=KOLI_KURALLARI["yok"]())
    return _oc_toplam(w, sevk)


def test_oncelik_cover_ihtiyac_esit_orantili():
    # cover: (stok + giden + 1) / öngörü artan: M2 .2, M3 .33, M2 .4, M2 .6, M3 .67, M1 1
    assert _uc_magaza("cover") == [1, 3, 2]
    # ihtiyaç: en büyük kalan ihtiyaç önce; eşitlikte (mağaza, option) sırası
    assert _uc_magaza("ihtiyac") == [5, 1, 0]
    # eşit: giden adet sırayla; eşitlikte cover
    assert _uc_magaza("esit") == [2, 2, 2]
    # orantılı: 6 × (6, 3, 2) / 11 = 3,27 / 1,64 / 1,09 → 3, 1, 1 + en büyük kalan M2
    assert _uc_magaza("orantili") == [3, 2, 1]


def test_cover_magaza_stogunu_sayar():
    w = _dunya(magaza=2)
    istek = _istek(w, {(0, 0): [0, 0, 3, 0, 0], (1, 0): [0, 0, 3, 0, 0]})
    eldeki = np.zeros(len(w.hucre_sku), dtype=np.int64)
    eldeki[_hucre(w, 0, 2)] = 10                       # M1'in rafında 10 adet
    d = _defter(w, acik=[0, 0, 3, 0, 0], kapali=[0])
    sevk = _dagit(w, d, istek, eldeki_c=eldeki, kural=KOLI_KURALLARI["yok"]())
    assert _oc_toplam(w, sevk) == [0, 3]


@pytest.mark.parametrize("ihtiyac, ongoru, kapali, oncelik, beklenen", [
    # M1'in ihtiyacı ve öngörüsü büyük: cover ona yığar, eşit herkese birer koli
    ((3, 1, 1), (9, 1, 1.5), 3, "cover", [21, 0, 0]),
    ((3, 1, 1), (9, 1, 1.5), 3, "esit", [7, 7, 7]),
    # M2'nin ihtiyacı büyük, M3'ün öngörüsü: cover M3 sonra M2; ihtiyaç ve
    # orantılı (D'Hondt) iki koliyi M2'ye
    ((1, 3, 1), (1, 2, 9), 2, "cover", [0, 7, 7]),
    ((1, 3, 1), (1, 2, 9), 2, "ihtiyac", [0, 14, 0]),
    ((1, 3, 1), (1, 2, 9), 2, "orantili", [0, 14, 0]),
])
def test_oncelik_koli_asamasinda(ihtiyac, ongoru, kapali, oncelik, beklenen):
    """Açık stok yok; mağazaların ihtiyacı koli katı (`ihtiyac` × paket)."""
    w = _dunya(magaza=3)
    istek = _istek(w, {(m, 0): k * PAKET for m, k in enumerate(ihtiyac)})
    d = _defter(w, acik=np.zeros(5), kapali=[kapali])
    sevk = _dagit(w, d, istek, oncelik=oncelik, ongoru_oc=np.array([*ongoru, 1.0]))
    assert _oc_toplam(w, sevk) == beklenen
    assert sevk.koli_sayisi == kapali and d.kapali.tolist() == [0]


def test_acik_asamada_bedenler_dengeli():
    """OC içinde adet bedene isteğe orantılı sırayla gider (ilk bedeni
    tüketip sonrakini aç bırakmaz)."""
    w = _dunya(magaza=1)
    d = _defter(w, acik=np.full(5, 100), kapali=[0])
    sevk = _dagit(w, d, _istek(w, {(0, 0): [4, 4, 4, 4, 4]}), tavan=10.0)
    assert _beden(w, sevk, 0) == [2, 2, 2, 2, 2]


# ------------------------------------------------------ stok ve maske


def test_golge_stok_asilmaz():
    """Rastgele: SKU başına giden ≤ açık + kapalı adet; açık aşama açık stoğu,
    koli aşaması kapalı koliyi aşmaz; defter negatif olmaz; giden ≤ istek."""
    rng = np.random.default_rng(11)
    w = _dunya(magaza=5, option=2)
    for _ in range(40):
        acik = rng.integers(0, 4, _S(w))
        kapali = rng.integers(0, 3, 2)
        d = _defter(w, acik, kapali)
        istek = rng.integers(0, 9, len(w.hucre_sku))
        kural = KISITSIZ if rng.random() < 0.25 else KOLI_KURALLARI[rng.choice(["yok", "A", "B", "C"])]()
        sevk = _dagit(w, d, istek, kural=kural,
                      oncelik=rng.choice(["cover", "ihtiyac", "esit", "orantili"]),
                      ongoru_oc=rng.random(_OC(w)) * 5)
        giden = np.bincount(w.hucre_sku, sevk.hucre_adet, minlength=_S(w))
        assert (giden <= acik + kapali[w.sku_option] * np.tile(PAKET, 2)).all()
        assert (d.acik >= 0).all() and (d.kapali >= 0).all()
        assert np.array_equal(d.kapali_adet() + d.acik + giden,
                              kapali[w.sku_option] * np.tile(PAKET, 2) + acik)
        if kural.ad in ("yok", "kisitsiz"):          # koli yoksa giden ≤ istek
            assert (sevk.hucre_adet <= np.where(w.hucre_online, 0, istek)).all()


def test_maske_disina_gitmez():
    w = _dunya(magaza=3)
    istek = _istek(w, {(m, 0): 2 * PAKET for m in range(3)})
    istek[np.asarray(w.hucre_online)] = 5                       # ONL hücrelerinde de istek
    maske = ~np.asarray(w.hucre_online) & (np.asarray(w.hucre_magaza) != 1)   # M2 maskeli
    for kural in (KOLI_KURALLARI["A"](), KISITSIZ):
        for oncelik in ("cover", "ihtiyac", "esit", "orantili"):
            d = _defter(w, acik=PAKET * 2, kapali=[6])
            sevk = _dagit(w, d, istek, kural=kural, oncelik=oncelik, maske_c=maske)
            assert sevk.hucre_adet[~maske].sum() == 0
            assert sevk.hucre_adet[maske].sum() > 0


def test_koli_maskeli_icerik_hucresine_gitmez():
    """Kolinin bir bedeninin hücresi maskeliyse o OC'ye koli gitmez."""
    w = _dunya(magaza=1)
    maske = ~np.asarray(w.hucre_online)
    maske[_hucre(w, 0, 4)] = False                               # XL hücresi maskeli
    d = _defter(w, acik=np.zeros(5), kapali=[3])
    sevk = _dagit(w, d, _istek(w, {(0, 0): PAKET}), maske_c=maske)
    assert sevk.hucre_adet.sum() == 0 and d.kapali.tolist() == [3]


# --------------------------------------------------------------- kısıtsız


def test_kisitsiz_butun_stok_acik_gibi():
    """Kısıtsız: kapalı koli de adet adet gider (defter koliyi kendi açar);
    koli kuralı yok, tavan yok."""
    w = _dunya(magaza=1)
    d = _defter(w, acik=np.zeros(5), kapali=[2])
    sevk = _dagit(w, d, _istek(w, {(0, 0): [0, 0, 3, 0, 0]}), kural=KISITSIZ)
    assert _beden(w, sevk, 0) == [0, 0, 3, 0, 0]
    assert sevk.koli_sayisi == 0 and sevk.acik_adet == 3 and sevk.tavan_dolulugu == 0.0
    # 2 koli açıldı (M bedeni 2'şer), içerik açığa geçti, 3 adet düştü
    assert d.kapali.tolist() == [0] and d.acik.tolist() == [2, 4, 1, 2, 2]
    with pytest.raises(ValueError):
        _dagit(w, d, _istek(w, {(0, 0): [0, 0, 1, 0, 0]}), kural=KISITSIZ, tavan=10.0)


def test_kisitsiz_defter_dizileri_yerinde_degisir():
    """Kısıtsızda koli açma defterin dizilerini yerinde değiştirir: önceden
    alınmış başvuru değişikliği görür."""
    w = _dunya(magaza=1)
    d = _defter(w, acik=np.zeros(5), kapali=[2])
    acik, kapali = d.acik, d.kapali
    _dagit(w, d, _istek(w, {(0, 0): [0, 0, 3, 0, 0]}), kural=KISITSIZ)
    assert d.acik is acik and d.kapali is kapali
    assert acik.tolist() == [2, 4, 1, 2, 2] and kapali.tolist() == [0]


def test_kisitsiz_orantili_motor_kesimiyle_ayni():
    """Kısıtsız + orantılı = motorun orantılı kesimi (defter toplamı = depo)."""
    from perakende_veri.v4.motor.durum import orantili_kes

    rng = np.random.default_rng(3)
    w = _dunya(magaza=6, option=2)
    for _ in range(20):
        acik = rng.integers(0, 6, _S(w))
        kapali = rng.integers(0, 3, 2)
        d = _defter(w, acik, kapali)
        depo = d.kapali_adet() + d.acik
        istek = rng.integers(0, 6, len(w.hucre_sku))
        maske = ~np.asarray(w.hucre_online)
        sevk = _dagit(w, d, istek, kural=KISITSIZ, oncelik="orantili", maske_c=maske)
        beklenen = orantili_kes(np.where(maske, istek, 0), np.asarray(w.hucre_sku), depo)
        assert np.array_equal(sevk.hucre_adet, beklenen)


# ------------------------------------------------------- motor maskesi


def test_motor_maskesi_oyuncak():
    w = _dunya(magaza=2, option=2)
    w.optionlar["cikis_gun"] = [10**6, 20]
    w.hucre_outlet_akisi = np.asarray(w.hucre_magaza) == 1
    g = SimpleNamespace(dunya=w, gun=20, ilk_dagitim_gun=np.array([5, 3]),
                        acik_magaza=np.array([True, True, True]))
    m = motor_maskesi(g)
    hm, ho = np.asarray(w.hucre_magaza), np.asarray(w.hucre_option)
    assert np.array_equal(m, (hm == 0) & (ho == 0))      # M2 outlet, ONL, o1 çıkmış
    g.ilk_dagitim_gun = np.array([20, 3])               # ilk dağıtım bugün: henüz değil
    assert not motor_maskesi(g).any()
    g.ilk_dagitim_gun = np.array([5, 3])
    g.acik_magaza = np.array([False, True, True])
    assert not motor_maskesi(g).any()


def test_motor_maskesi_motorla_ayni():
    """KÜÇÜK dünya, kısa koşu, sonda politikası: her pazartesi bütün hücrelere
    (ONL dahil) birer adet ister, SKU başına depo stoğunu aşmayacak kadar
    (motor kesmesin). Motor maskenin dışındaki isteği sıfırlar, içindekini
    olduğu gibi gönderir."""
    from perakende_veri.v4.motor import simule_et
    from perakende_veri.v4.politika import Politikalar

    from replenishment import motor

    w = motor.dunya("kucuk")
    hs = np.asarray(w.hucre_sku)
    C = len(hs)
    rng = np.random.default_rng(0)
    kayit = {}

    def sonda(g):
        sira = rng.permutation(C)
        hucre_sirali = sira[np.argsort(hs[sira], kind="stable")]       # SKU'ya göre, SKU içi rastgele
        bas = np.searchsorted(hs[hucre_sirali], hs[hucre_sirali], side="left")
        rutbe = np.arange(C) - bas
        istek = np.zeros(C, dtype=np.int64)
        istek[hucre_sirali[rutbe < np.asarray(g.depo)[hs[hucre_sirali]]]] = 1
        kayit[int(g.gun)] = (istek, motor_maskesi(g), np.array(g.ilk_dagitim_gun),
                             np.array(g.acik_magaza))
        return istek

    ham = simule_et(w, Politikalar(replenishment=sonda), gun_sayisi=260)
    sv = ham["sevkiyat"]
    sv = sv[sv["tip"] == "replenishment"]
    neden = dict.fromkeys(("online", "outlet", "ilk_dagitim_once", "cikmis", "kapali_magaza"), 0)
    ho, hm = np.asarray(w.hucre_option), np.asarray(w.hucre_magaza)
    cikis = w.optionlar["cikis_gun"].to_numpy()[ho]
    icerde = 0
    for gun, (istek, maske, ilk, acik) in kayit.items():
        giden = np.zeros(C, dtype=np.int64)
        s = sv[sv["gun"] == gun]
        np.add.at(giden, s["hedef_hucre"].to_numpy(), s["adet"].to_numpy())
        assert np.array_equal(giden, np.where(maske, istek, 0)), gun
        icerde += int(istek[maske].sum())
        istendi = istek > 0
        neden["online"] += int((istendi & np.asarray(w.hucre_online)).sum())
        neden["outlet"] += int((istendi & np.asarray(w.hucre_outlet_akisi)).sum())
        neden["ilk_dagitim_once"] += int((istendi & (ilk[ho] >= gun)).sum())
        neden["cikmis"] += int((istendi & (cikis <= gun)).sum())
        neden["kapali_magaza"] += int((istendi & ~acik[hm]).sum())
    assert icerde > 0
    # Maskenin her kolu sınandı (her nedenle istenip motorca sıfırlanan hücre var)
    assert all(v > 0 for v in neden.values()), neden
