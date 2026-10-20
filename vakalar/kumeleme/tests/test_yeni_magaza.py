"""`kumeleme.yeni_magaza`: statik özelliklerle atama ve bırakbir ölçümü.

`conftest`in 12 mağazalı fikstürü: 8 kümelenen mağaza (Marmara M01, M02, M05; İç Anadolu M03,
M04, M06; Ege M07, M08) ve yeni M09 (Kocaeli, Marmara). Kümeler testte elle verilir (bölgeye göre)
ya da bölgeye göre ayrık noktalardan kurulur (`_Z`).
"""

import inspect
from functools import partial

import numpy as np
import pandas as pd
import pytest
from conftest import KARAR

from kumeleme import kaynak, ogren, yeni_magaza


def _kapsam(tablolar):
    return kaynak.kapsam(tablolar["magaza"], tablolar["magaza_olay"], tablolar["satis"], KARAR)


_MERKEZ = {"Marmara": (0.0, 0.0), "İç Anadolu": (6.0, 0.0), "Ege": (0.0, 6.0)}


def _Z(kum, tohum=0):
    """Bölgeye göre üç ayrık nokta bulutu (satış özelliği yerine)."""
    rng = np.random.default_rng(tohum)
    X = np.array([_MERKEZ[b] for b in kum["bolge"]]) + rng.normal(0, 0.2, (len(kum), 2))
    return pd.DataFrame(X, index=pd.Index(kum["magaza_id"].to_numpy(), name="magaza_id"), columns=["a", "b"])


def _bolge_etiketi(kum):
    sira = {"Marmara": 0, "İç Anadolu": 1, "Ege": 2}
    return pd.Series([sira[b] for b in kum["bolge"]], index=pd.Index(kum["magaza_id"], name="magaza_id"))


def test_statik_tablo(tablolar):
    k = _kapsam(tablolar)
    S = yeni_magaza.statik_tablo(k)
    assert list(S.columns) == list(yeni_magaza.STATIKLER) and list(S.index) == list(k["magaza_id"])
    assert S.loc["M01", "iklim"] == "ılıman" and S.loc["M03", "iklim"] == "karasal"
    assert S.loc["M08", "iklim"] == "sicak_sahil" and bool(S.loc["M01", "metropol"])
    assert S.loc["M02", "log_m2"] == pytest.approx(np.log(350))
    with pytest.raises(KeyError):
        yeni_magaza.statik_tablo(k.assign(sehir="Atlantis"))


@pytest.mark.parametrize("yontem", yeni_magaza.YONTEMLER)
def test_atama_statikten(tablolar, yontem):
    """Atama yalnız statiklerden: satış ve diğer sütunlar sonucu değiştirmez; statik değişince
    atama değişir; arayüzde satış girdisi yok."""
    k = _kapsam(tablolar)
    kum, yeni = k[k["kumelenir"]], k[k["yeni"]]
    e = _bolge_etiketi(kum)
    a = yeni_magaza.ata(yeni, kum, e, yontem=yontem, komsu=3)
    assert a.to_dict() == {"M09": 0}                                   # Kocaeli → Marmara kümesi
    gurultu = yeni.assign(gecmis_hafta=500, ad="X", istanbul=True, net_ciro=1e12)
    kum_gurultu = kum.assign(gecmis_hafta=0, ad="Y", net_ciro=np.arange(len(kum)))
    assert yeni_magaza.ata(gurultu, kum_gurultu, e, yontem=yontem, komsu=3).equals(a)
    ege = yeni.assign(sehir="Bodrum", bolge="Ege", enlem=37.0, metrekare=540)
    assert yeni_magaza.ata(ege, kum, e, yontem=yontem, komsu=3).to_dict() == {"M09": 2}
    iki = pd.concat([yeni, ege.assign(magaza_id="M99")])               # satırlar birbirinden bağımsız
    assert yeni_magaza.ata(iki, kum, e, yontem=yontem, komsu=3).to_dict() == {"M09": 0, "M99": 2}
    assert set(inspect.signature(yeni_magaza.ata).parameters) == {
        "statik_yeni", "statik_kumelenmis", "etiket", "yontem", "komsu"}


def test_atama_hatalari(tablolar):
    k = _kapsam(tablolar)
    kum, yeni = k[k["kumelenir"]], k[k["yeni"]]
    e = _bolge_etiketi(kum)
    with pytest.raises(ValueError):
        yeni_magaza.ata(kum.iloc[:1], kum, e)                          # zaten kümelenmiş
    with pytest.raises(ValueError):
        yeni_magaza.ata(yeni, kum, e.iloc[1:])                         # etiketi eksik
    with pytest.raises(ValueError):
        yeni_magaza.ata(yeni, kum, e, yontem="rastgele")


def test_kodlama_kumelenmislerden():
    """İstatistikler kümelenmiş mağazalardan; görülmemiş kategori 0 kodlanır; bloklar eşit varyans."""
    ref = pd.DataFrame({"bolge": ["A", "A", "B", "B"], "metropol": [True, False, True, False],
                        "iklim": ["x", "x", "x", "y"], "tip": ["AVM"] * 4,
                        "log_m2": [1.0, 2.0, 3.0, 4.0], "enlem": [36.0, 38.0, 40.0, 42.0]})
    yeni = ref.iloc[:1].assign(bolge="C", log_m2=10.0)
    A, B = yeni_magaza._kodla(ref, yeni)
    assert A.shape[1] == 2 + 2 + 2 + 1 + 1                             # tip sabit: düşer
    blok = [slice(0, 2), slice(2, 4), slice(4, 6), slice(6, 7), slice(7, 8)]
    assert [A[:, b].var(axis=0).sum() for b in blok] == pytest.approx([1.0] * 5)
    assert B[0, :2] == pytest.approx([-0.5 / np.sqrt(0.5)] * 2)          # C: iki sütunda 0, merkezlenmiş
    assert B[0, 6] == pytest.approx((10.0 - 2.5) / np.std([1.0, 2.0, 3.0, 4.0]))


def test_knn_cogunluk_ve_esitlik():
    ref = pd.DataFrame({"magaza_id": ["A", "B", "C", "D"], "sehir": ["Konya"] * 4, "bolge": ["İç Anadolu"] * 4,
                        "tip": ["AVM"] * 4, "metrekare": [100, 110, 1000, 1100], "enlem": [37.0] * 4,
                        "metropol": [False] * 4})
    e = pd.Series({"A": 0, "B": 1, "C": 1, "D": 1})
    yeni = ref.iloc[:1].assign(magaza_id="N", metrekare=101)
    assert yeni_magaza.ata(yeni, ref, e, yontem="knn", komsu=1).iloc[0] == 0
    assert yeni_magaza.ata(yeni, ref, e, yontem="knn", komsu=2).iloc[0] == 0   # 1-1 eşit: en yakın
    assert yeni_magaza.ata(yeni, ref, e, yontem="knn", komsu=3).iloc[0] == 1
    assert yeni_magaza.ata(yeni, ref, e, yontem="merkez").iloc[0] == 0


def test_birakbir_kendisini_gormez(tablolar):
    """Her mağazanın ataması onun satırı olmadan kurulan kümelerle yapılır: kümeleme işlevi
    mağaza hariç çağrılır; mağazanın kendi özellik satırı değişince gerçek kümesi değişir, atandığı
    kümenin (diğer) üyeleri değişmez."""
    k = _kapsam(tablolar)
    kum = k[k["kumelenir"]]
    Z = _Z(kum)
    cagri = []

    def fn(X):
        cagri.append(sorted(X.index))
        return ogren.kume(X, "ward", 3)

    b = yeni_magaza.birakbir(kum, Z, fn)
    ids = sorted(kum["magaza_id"])
    assert list(b["magaza_id"]) == ids and list(b.columns) == [
        "magaza_id", "gercek_kume", "atanan", "metropol", "ayni_bolme"]
    assert cagri[0] == ids and len(cagri) == 1 + len(ids)
    assert [sorted(set(ids) - set(c)) for c in cagri[1:]] == [[m] for m in ids]
    assert b["ayni_bolme"].all()
    assert b["atanan"].isin(b["gercek_kume"]).all()                    # tam bölmenin etiket uzayında
    assert b.set_index("magaza_id")["metropol"].to_dict() == kum.set_index("magaza_id")["metropol"].to_dict()

    def diger_uyeler(t, m):
        tam = t.set_index("magaza_id")["gercek_kume"]
        a = t.set_index("magaza_id").at[m, "atanan"]
        return sorted(i for i in tam.index if tam[i] == a and i != m)

    Z2 = Z.copy()
    Z2.loc["M01"] = _MERKEZ["Ege"]                                     # M01 satışıyla Ege'ye benzer
    b2 = yeni_magaza.birakbir(kum, Z2, partial(ogren.kume, yontem="ward", k=3))
    tam2 = b2.set_index("magaza_id")["gercek_kume"]
    assert sorted(i for i in tam2.index if tam2[i] == tam2["M01"]) == ["M01", "M07", "M08"]
    assert diger_uyeler(b2, "M01") == diger_uyeler(b, "M01") == ["M02", "M05"]


def test_birakbir_girdi_denetimi(tablolar):
    k = _kapsam(tablolar)
    kum = k[k["kumelenir"]]
    with pytest.raises(ValueError):
        yeni_magaza.birakbir(kum.iloc[1:], _Z(kum), partial(ogren.kume, yontem="ward", k=3))
