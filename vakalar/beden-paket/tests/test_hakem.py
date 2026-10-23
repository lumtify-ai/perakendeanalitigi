"""Hakem (gizli `beden_kayma` ve gerçek beden payı) ve eğri ölçütleri (`olcutler_egri`)."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from perakende_veri.v4 import sabitler as v4_sabitler

from beden_paket import hakem, olcutler_egri

S = ["b1", "b2", "b3", "b4", "b5"]


def _dunya(kayma: dict) -> SimpleNamespace:
    return SimpleNamespace(gizli_magaza=pd.DataFrame({"magaza_id": list(kayma), "segment": "x",
                                                      "beden_kayma": list(kayma.values())}))


def test_kayma_ve_gercek_pay():
    w = _dunya({"M002": 1, "M001": 0, "M003": -1, "M004": 2})
    k = hakem.kayma(w)
    assert list(k.index) == ["M001", "M002", "M003", "M004"]
    assert k.to_dict() == {"M001": 0, "M002": 1, "M003": -1, "M004": 1}       # +2 talepte +1'e kırpılır
    assert hakem.kayma(w, kirp=False)["M004"] == 2
    g = hakem.gercek_pay(w)
    assert list(g.columns) == S and list(g.index) == ["M001", "M002", "M003", "M004"]
    np.testing.assert_allclose(g.loc["M004"], g.loc["M002"])
    np.testing.assert_allclose(g.sum(axis=1), 1.0)
    np.testing.assert_allclose(g.loc["M001"], v4_sabitler.BEDEN_PAYLARI_ZINCIR, atol=1e-12)   # kayma 0 = zincir
    ort = g.to_numpy()[:3] @ np.arange(1, 6)
    assert ort[2] < ort[0] < ort[1]                                       # küçük < orta < büyük


def test_gercek_pay_tablo_kabul_eder():
    t = pd.DataFrame({"magaza_id": ["A", "B"], "beden_kayma": [1, 1]})
    g = hakem.gercek_pay(t)
    np.testing.assert_allclose(g.loc["A"], g.loc["B"])
    with pytest.raises(KeyError):
        hakem.kayma(pd.DataFrame({"magaza_id": ["A"]}))


def test_uzaklik_l1():
    idx = pd.Index(["A", "B"], name="magaza_id")
    t = pd.DataFrame([[0.2] * 5, [0.1, 0.2, 0.4, 0.2, 0.1]], index=idx, columns=S)
    g = pd.DataFrame([[0.1, 0.2, 0.4, 0.2, 0.1]] * 3, index=["A", "B", "C"], columns=S)
    u = olcutler_egri.uzaklik(t, g)
    assert list(u.index) == ["A", "B"]
    assert u["A"] == pytest.approx(0.1 + 0 + 0.2 + 0 + 0.1) and u["B"] == pytest.approx(0)
    with pytest.raises(KeyError):
        olcutler_egri.uzaklik(g, t)                                  # C'nin gerçeği yok


def test_kararlilik_ortak_magazalar():
    a = pd.DataFrame([[0.2] * 5, [0.2] * 5], index=["A", "B"], columns=S)
    b = pd.DataFrame([[0.2] * 5, [0.1, 0.2, 0.4, 0.2, 0.1]], index=["C", "B"], columns=S)
    k = olcutler_egri.kararlilik(a, b)
    assert list(k.index) == ["B"] and k["B"] == pytest.approx(0.4)


def test_ari():
    p = pd.Series(["kucuk", "kucuk", "buyuk", "orta"], index=["A", "B", "C", "D"])
    k = pd.Series([-1, -1, 1, 0, 0], index=["A", "B", "C", "D", "E"])
    assert olcutler_egri.ari(p, k) == pytest.approx(1.0)
    assert olcutler_egri.ari(p, pd.Series([0, 1, 0, 1], index=["A", "B", "C", "D"])) < 0.5
