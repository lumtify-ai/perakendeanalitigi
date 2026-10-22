"""`kumeleme.ogren`: k-means ve Ward kümeleri, kanonik etiket ve bölme kimliği, siluet, hakemsiz k
seçimi, kararlılık, yorum, önerilen ML kümesi.

Kümeleme testleri elle kurulan nokta bulutlarıyla (`_bulut`: ayrık Gauss kümeleri) çalışır; öneri
testleri `conftest`in 12 mağazalı fikstürünü kullanır (8 kümelenen mağaza: k aralığı ve en küçük
küme sınırı küçültülür). Gizli segment yalnız `gizli` fikstüründedir; `test_k_secimi_hakemsiz` onu
bozar ve seçimin değişmediğini gösterir. `veri` işaretli test yayımlanan v4 verisini ister.
"""

import inspect

import numpy as np
import pandas as pd
import pytest
from conftest import KARAR

from kumeleme import kaynak, ogren, sabitler


def _bulut(merkezler, sayilar, *, sapma=0.3, boyut=4, tohum=0, on="S"):
    """Ayrık Gauss kümeleri: `merkezler[i]` çevresinde `sayilar[i]` nokta; dizin `S00`, `S01` …
    karışık sırayla (küme sırası mağaza sırasından okunamaz)."""
    rng = np.random.default_rng(tohum)
    satir, gercek = [], []
    for i, (m, n) in enumerate(zip(merkezler, sayilar)):
        m = np.resize(np.asarray(m, dtype=float), boyut)
        satir.append(m + rng.normal(0, sapma, size=(n, boyut)))
        gercek += [i] * n
    X = np.vstack(satir)
    sira = rng.permutation(len(X))
    ids = [f"{on}{j:02d}" for j in range(len(X))]
    df = pd.DataFrame(X[sira], index=pd.Index(ids, name="magaza_id"),
                      columns=[f"oz{c}" for c in range(boyut)])
    return df, pd.Series(np.asarray(gercek)[sira], index=df.index)


def _uc_kume():
    return _bulut([(0, 0), (6, 0), (0, 6)], [8, 7, 6])


# ------------------------------------------------------------------ kume, kimlik


@pytest.mark.parametrize("yontem", ["kmeans", "ward"])
def test_kmeans_belirlenimci(yontem):
    """Aynı girdi aynı etiket; satır ve sütun sırası etiketleri değiştirmez; gerçek yapı bulunur."""
    X, gercek = _uc_kume()
    a = ogren.kume(X, yontem, 3)
    assert a.equals(ogren.kume(X, yontem, 3))
    assert a.index.name == "magaza_id" and list(a.index) == list(X.index) and a.dtype == "int64"
    karisik = X.sample(frac=1.0, random_state=1)[X.columns[::-1]]
    b = ogren.kume(karisik, yontem, 3)
    assert list(b.index) == list(karisik.index)
    assert b.reindex(a.index).equals(a)                                # aynı kanonik etiketler
    assert ogren.bolme_kimligi(a) == ogren.bolme_kimligi(pd.Series(gercek, index=X.index))
    if yontem == "kmeans":                                            # başka tohum, aynı bölme:
        assert ogren.kume(X, yontem, 3, tohum=7).equals(a)            # ayrık yapıda tek optimum


def test_kanonik_etiket_en_kucuk_kimlik():
    """Küme 0 en küçük mağaza kimliğini taşır; küme numaraları en küçük kimliklerin sırasıyla."""
    X, _ = _bulut([(0, 0), (6, 0), (0, 6), (6, 6)], [5, 4, 6, 3])
    for yontem in ("kmeans", "ward"):
        e = ogren.kume(X, yontem, 4)
        ilk = e.groupby(e).apply(lambda s: min(s.index))
        assert list(ilk.index) == [0, 1, 2, 3] and list(ilk) == sorted(ilk)
        assert e[min(X.index)] == 0


def test_kimlik_etiketten_bagimsiz():
    ids = pd.Index(["M01", "M02", "M03", "M04", "M05"], name="magaza_id")
    a = pd.Series([0, 0, 1, 1, 2], index=ids)
    perm = pd.Series([7, 7, 3, 3, 5], index=ids)                      # aynı bölme, başka adlar
    sira = a.iloc[::-1]                                                # aynı bölme, başka satır sırası
    adli = pd.Series(["x", "x", "y", "y", "z"], index=ids)
    k = ogren.bolme_kimligi(a)
    assert ogren.bolme_kimligi(perm) == ogren.bolme_kimligi(sira) == ogren.bolme_kimligi(adli) == k
    assert ogren.bolme_kimligi(pd.Series([0, 1, 1, 1, 2], index=ids)) != k   # başka bölme
    assert ogren.bolme_kimligi(a.rename(index={"M05": "M06"})) != k          # başka mağaza
    assert len(k) == 64
    assert ogren.kanonik(perm).equals(a)


def test_siluet():
    X, gercek = _uc_kume()
    e = ogren.kume(X, "kmeans", 3)
    s = ogren.siluet(X, e)
    assert 0.8 < s <= 1.0                                              # ayrık kümeler
    assert ogren.siluet(X, e.iloc[::-1]) == pytest.approx(s)          # etiket sırası hizalanır
    karisik = pd.Series(np.arange(len(X)) % 3, index=X.index)
    assert ogren.siluet(X, karisik) < 0.2


# ------------------------------------------------------------------ k seçimi


def test_k_kurali_esitlikte_kucuk_k():
    """Siluet 0,01 içinde olan uygun k'lardan en küçüğü; en küçük kümesi sınırın altındaki k elenir."""
    t = pd.DataFrame({"k": [3, 4, 5, 6], "siluet": [0.400, 0.405, 0.50, 0.38],
                      "en_kucuk": [5, 4, 2, 3]})
    assert ogren.k_kurali(t, en_kucuk=3) == 3                          # 5 elendi; 3, 4'e 0,005 yakın
    t.loc[0, "siluet"] = 0.390                                         # artık 0,015 uzak
    assert ogren.k_kurali(t, en_kucuk=3) == 4
    assert ogren.k_kurali(t, en_kucuk=2) == 5
    assert ogren.k_kurali(t, en_kucuk=6) is None                       # uygun k yok
    assert ogren.SILUET_ESITLIK == 0.01


@pytest.mark.parametrize("yontem", ["kmeans", "ward"])
def test_k_secimi_en_kucuk_kume(yontem):
    """Dört ayrık bulut, biri 2 noktalı: siluet k = 4'te en yüksek ama en küçük küme 2 < 3, elenir."""
    X, _ = _bulut([(0, 0), (8, 0), (0, 8), (4, 4)], [9, 9, 9, 2], sapma=0.3)
    k, tablo = ogren.k_sec(X, yontem)
    assert list(tablo["k"]) == list(sabitler.K_ARALIK)
    t = tablo.set_index("k")
    assert t["siluet"].idxmax() == 4 and t.loc[4, "en_kucuk"] == 2 and not t.loc[4, "uygun"]
    assert k == 3 and t.loc[3, "uygun"] and t.loc[3, "secilen"]
    assert int(t["secilen"].sum()) == 1
    assert (t["en_kucuk"] >= 1).all() and (t["uygun"] == (t["en_kucuk"] >= sabitler.EN_KUCUK_KUME)).all()
    assert t["boyutlar"].map(sum).eq(len(X)).all()
    assert t["w"].is_monotonic_decreasing                             # dirsek sütunu: küme içi kareler
    k2, tablo2 = ogren.k_sec(X, yontem)
    assert k2 == k and tablo2.equals(tablo)


def test_k_sec_buyuk_k_atlanir():
    """n − 1'den büyük k denenmez (siluet tanımsız); hiç uygun k yoksa None."""
    X, _ = _bulut([(0, 0), (6, 0)], [3, 3])
    k, tablo = ogren.k_sec(X, "kmeans", k_aralik=range(2, 9), en_kucuk=3)
    assert list(tablo["k"]) == [2, 3, 4, 5] and k == 2
    k, _ = ogren.k_sec(X, "kmeans", k_aralik=range(3, 6), en_kucuk=3)
    assert k is None


def test_kararlilik():
    """Ayrık yapı alt örneklemede bozulmaz (ARI 1); yapısız bulutta düşüktür."""
    X, _ = _uc_kume()
    assert ogren.kararlilik(X, "kmeans", 3, ornek=10) == pytest.approx(1.0)
    rng = np.random.default_rng(3)
    Y = pd.DataFrame(rng.normal(size=(30, 4)), index=pd.Index([f"R{i:02d}" for i in range(30)],
                                                              name="magaza_id"))
    d = ogren.kararlilik(Y, "kmeans", 5, ornek=10)
    assert d < 0.9
    assert ogren.kararlilik(Y, "kmeans", 5, ornek=10) == d             # belirlenimci


def test_bos_siluet():
    """Sütunları karıştırılmış bulutta yapı yok: siluet gerçek bölmeninkinden çok düşük."""
    X, _ = _uc_kume()
    X.columns = [f"karisim/G/n/{c}" for c in X.columns]
    Z = X / X.std(ddof=0)
    s = ogren.siluet(Z, ogren.kume(Z, "kmeans", 3))
    b = ogren.bos_siluet(X, "karisim", "kmeans", 3, ornek=4)
    assert 0 < b < 0.5 < s
    assert ogren.bos_siluet(X.iloc[::-1], "karisim", "kmeans", 3, ornek=4) == b    # satır sırası


# ------------------------------------------------------------------ yorum


def test_yorum_ayirt_edici():
    """Kümenin en ayırt edici özellikleri: |ortalama z| büyükten küçüğe, işaretiyle."""
    ids = pd.Index([f"M{i:02d}" for i in range(1, 9)], name="magaza_id")
    X = pd.DataFrame({
        "a": [10, 10, 10, 10, 0, 0, 0, 0],      # küme 0 yüksek: z +1
        "b": [0, 0, 1, 1, 0, 0, 1, 1],          # ayırt etmez: z 0
        "c": [0, 0, 0, 1, 5, 5, 5, 4],          # küme 1 yüksek
        "s": [3] * 8,                           # sabit: düşer
    }, index=ids, dtype=float)
    e = pd.Series([0, 0, 0, 0, 1, 1, 1, 1], index=ids)
    y = ogren.yorum(X, e, n=2)
    assert list(y) == [0, 1]
    assert [ad for ad, _ in y[0]] == ["a", "c"] and [ad for ad, _ in y[1]] == ["a", "c"]
    assert y[0][0][1] == pytest.approx(1.0) and y[1][0][1] == pytest.approx(-1.0)
    z_c = (np.array([0, 0, 0, 1]) - X["c"].mean()).mean() / X["c"].std(ddof=0)
    assert y[0][1][1] == pytest.approx(z_c) and y[0][1][1] < 0
    assert all(ad != "s" for v in y.values() for ad, _ in v)
    # ölçekten bağımsız: standartlanmış (ağırlıklı) tabloda aynı yorum
    Z = (X - X.mean()) / X.std(ddof=0).replace(0, 1) / 3.0
    yz = ogren.yorum(Z, e, n=2)
    assert list(yz) == list(y)
    for kume in y:
        for (a1, z1), (a2, z2) in zip(y[kume], yz[kume]):
            assert a1 == a2 and z1 == pytest.approx(z2)
    assert len(ogren.yorum(X, e)[0]) == 3


# ------------------------------------------------------------------ öneri


def test_oneri_kurali():
    """Siluet birincil; siluette eşitler (≤ 0,01) bölme kararlılığıyla ayrılır; kararlılıkta eşitler
    (≤ 0,02) küçük k, sonra aile ve yöntem sırası."""
    a = pd.DataFrame([("S1", "kmeans", 5, 0.300, 0.85, "a"), ("S1", "ward", 5, 0.300, 0.90, "b"),
                      ("S2", "kmeans", 3, 0.280, 0.99, "c"), ("S2", "ward", 5, 0.270, 0.97, "d")],
                     columns=["aile", "yontem", "k", "siluet", "kararlilik", "kimlik"])
    i, esit, bolme = ogren.oneri_kurali(a)
    assert i == 1 and list(esit) == [True, True, False, False]       # S2 kararlı ama siluette geride
    assert list(bolme) == list(a["kararlilik"])                       # dört ayrı bölme
    a.loc[2, "siluet"] = 0.295                                          # artık siluette eşit
    i, esit, _ = ogren.oneri_kurali(a)
    assert i == 2 and list(esit) == [True, True, True, False]
    a.loc[2, "kararlilik"] = 0.91                                       # S1 ward ile 0,01: küçük k
    assert ogren.oneri_kurali(a)[0] == 2
    a.loc[2, "k"] = 5                                                   # k da eşit: aile sırası
    assert ogren.oneri_kurali(a)[0] == 1
    a.loc[0, "kararlilik"] = 0.90                                       # aile de eşit: yöntem sırası
    assert ogren.oneri_kurali(a)[0] == 0
    assert (ogren.SILUET_ESITLIK, ogren.KARARLILIK_ESITLIK) == (0.01, 0.02)


def test_oneri_kurali_ayni_bolme_esit():
    """Aynı bölmeyi veren iki yöntem kararlılıkta eşittir (ortalama): yöntem sırası belirler."""
    a = pd.DataFrame([("S1", "kmeans", 5, 0.3076, 0.851, "x"), ("S1", "ward", 5, 0.3076, 0.877, "x"),
                      ("S2", "kmeans", 3, 0.2784, 0.992, "y")],
                     columns=["aile", "yontem", "k", "siluet", "kararlilik", "kimlik"])
    i, esit, bolme = ogren.oneri_kurali(a)
    assert i == 0 and list(esit) == [True, True, False]
    assert bolme[0] == bolme[1] == pytest.approx(0.864) and bolme[2] == pytest.approx(0.992)
    a.loc[0, "kararlilik"] = 0.70                                       # ortalama değişir, yine eşit
    assert ogren.oneri_kurali(a)[0] == 0
    a.loc[1, "kimlik"] = "z"                                            # artık farklı bölme: ward
    assert ogren.oneri_kurali(a)[0] == 1


# 8 kümelenen mağazaya uygun: fikstürde M08 (turistik) tek başına kalır, en küçük küme 1
_KUCUK = dict(k_aralik=range(2, 4), en_kucuk=1, ornek=5)


def _kapsam(tablolar):
    return kaynak.kapsam(tablolar["magaza"], tablolar["magaza_olay"], tablolar["satis"], KARAR)


def test_oneri_fikstur(tablolar):
    k = _kapsam(tablolar)
    o = ogren.oneri(tablolar, k, tablolar["urun"], KARAR, **_KUCUK)
    assert o.aile in ("S1", "S2") and o.yontem in ("kmeans", "ward") and o.k in (2, 3)
    assert sorted(o.etiket.index) == sorted(k.loc[k["kumelenir"], "magaza_id"])   # yeni mağaza yok
    assert "M09" not in o.etiket.index
    assert o.kimlik == ogren.bolme_kimligi(o.etiket)
    t = o.tablo
    assert set(t["aile"]) == {"S1", "S2"} and set(t["yontem"]) == {"kmeans", "ward"}
    assert len(t) == 2 * 2 * 2
    sec = t[t["oneri"]]
    assert len(sec) == 1 and (sec.iloc[0]["aile"], sec.iloc[0]["yontem"], sec.iloc[0]["k"]) == (o.aile, o.yontem, o.k)
    # adaylar: her (aile, yöntem) için k_sec'in seçtiği k; kararlılık yalnız adaylarda
    assert t.groupby(["aile", "yontem"])["secilen"].sum().eq(1).all()
    assert t["kararlilik"].notna().equals(t["secilen"]) and not (t["esit"] & ~t["secilen"]).any()
    assert t["bolme_kararlilik"].notna().equals(t["secilen"])
    assert bool(sec.iloc[0]["secilen"]) and bool(sec.iloc[0]["esit"])
    aday = t[t["secilen"]]
    assert sec.iloc[0]["siluet"] >= aday["siluet"].max() - ogren.SILUET_ESITLIK


def test_k_secimi_hakemsiz(tablolar, gizli):
    """Gizli segment kapsamda ve tablolarda dursa da, karıştırılsa da öneri aynı; arayüzde hakem
    girdisi yok."""
    k = _kapsam(tablolar)
    gercek = k.merge(gizli, on="magaza_id", how="left")
    rng = np.random.default_rng(0)
    bozuk_seg = gizli.assign(segment=rng.permutation(gizli["segment"].to_numpy()))
    assert not bozuk_seg["segment"].equals(gizli["segment"])
    bozuk = k.merge(bozuk_seg, on="magaza_id", how="left")
    a = ogren.oneri({**tablolar, "gizli_magaza": gizli}, gercek, tablolar["urun"], KARAR, **_KUCUK)
    b = ogren.oneri({**tablolar, "gizli_magaza": bozuk_seg}, bozuk, tablolar["urun"], KARAR, **_KUCUK)
    c = ogren.oneri(tablolar, k, tablolar["urun"], KARAR, **_KUCUK)
    for o in (b, c):
        assert (o.aile, o.yontem, o.k, o.kimlik) == (a.aile, a.yontem, a.k, a.kimlik)
        assert o.etiket.equals(a.etiket)
        pd.testing.assert_frame_equal(o.tablo, a.tablo)
    for f in (ogren.oneri, ogren.k_sec, ogren.kume, ogren.kararlilik):
        assert not {"segment", "hakem", "gizli"} & set(inspect.signature(f).parameters)


_SURECTE = """
import hashlib, sys
sys.path.insert(0, sys.argv[1])
from conftest import KARAR, oyuncak_tablolar
from kumeleme import kaynak, ogren
t = oyuncak_tablolar()
k = kaynak.kapsam(t["magaza"], t["magaza_olay"], t["satis"], KARAR)
o = ogren.oneri(t, k, t["urun"], KARAR, k_aralik=range(2, 4), en_kucuk=1, ornek=5)
print(o.aile, o.yontem, o.k, o.kimlik,
      hashlib.sha256(o.tablo.to_csv(float_format="%.12g").encode()).hexdigest())
"""


def test_oneri_surecler_arasi_belirlenimci():
    """İki ayrı Python sürecinde (farklı dizge karması tohumu) öneri ve aday tablosu aynı."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    cikti = []
    for karma in ("1", "2"):
        ortam = {**os.environ, "PYTHONHASHSEED": karma, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, "-c", _SURECTE, str(Path(__file__).parent)],
                           capture_output=True, text=True, encoding="utf-8", env=ortam, check=True)
        cikti.append(r.stdout.strip())
    assert cikti[0] == cikti[1] and len(cikti[0].split()) == 5


def test_oneri_hazir_ozellik(tablolar):
    """Hazır özellik tabloları verilirse yeniden kurulmaz; sonuç aynı."""
    from kumeleme import ozellikler as oz
    k = _kapsam(tablolar)
    ids = k.loc[k["kumelenir"], "magaza_id"]
    X = {a: oz.ozellik_tablosu(tablolar, ids, tablolar["urun"], KARAR, a) for a in ("S1", "S2")}
    a = ogren.oneri(tablolar, k, tablolar["urun"], KARAR, **_KUCUK)
    b = ogren.oneri(None, k, None, KARAR, ozellik=X, **_KUCUK)
    assert a.kimlik == b.kimlik
    pd.testing.assert_frame_equal(a.tablo, b.tablo)


# ------------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_oneri_ss25():
    """SS25 karar günü, 67 kümelenen mağaza: aday tablosu ve öneri kayda (-s ile basılır)."""
    from kumeleme import ozellikler as oz
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con, ("magaza", "magaza_olay", "urun"))
        satis = con.execute(
            "select distinct tarih::date::timestamp as tarih, magaza_id::varchar as magaza_id, "
            "1 as adet from satis where adet > 0 and tarih < ?", [sabitler.KARAR_GUNU]).df()
        k = kaynak.kapsam(t["magaza"], t["magaza_olay"], satis, sabitler.KARAR_GUNU)
        X_ham = {a: oz.ozellik_tablosu(con, k.loc[k["kumelenir"], "magaza_id"], t["urun"],
                                       sabitler.KARAR_GUNU, a) for a in ogren.ONERI_AILELERI}
        o = ogren.oneri(con, k, t["urun"], sabitler.KARAR_GUNU)
        o2 = ogren.oneri(None, k, None, sabitler.KARAR_GUNU, ozellik=X_ham)
        X = X_ham[o.aile]
    finally:
        con.close()
    assert len(o.etiket) == 67 and o.etiket.value_counts().min() >= sabitler.EN_KUCUK_KUME
    assert o.k in sabitler.K_ARALIK and len(o.tablo) == 2 * 2 * len(sabitler.K_ARALIK)
    assert o.kimlik == ogren.bolme_kimligi(o.etiket) == o2.kimlik
    y = ogren.yorum(X, o.etiket)
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.max_rows", 100):
        print("\n" + o.tablo.drop(columns=["kimlik"]).to_string(index=False))
    for _, r in o.tablo[o.tablo["secilen"]].iterrows():
        print(f"boş siluet {r['aile']} {r['yontem']} k={r['k']}: "
              f"{ogren.bos_siluet(X_ham[r['aile']], r['aile'], r['yontem'], r['k']):.3f}")
    print(f"öneri: {o.aile} {o.yontem} k={o.k} boyutlar {sorted(o.etiket.value_counts(), reverse=True)} "
          f"kimlik {o.kimlik[:12]}")
    for kume, ozl in y.items():
        print(kume, [(a, round(z, 2)) for a, z in ozl])
