"""`replenishment.olcutler` (asgari, Ruling R22): bulunabilirlik, toplama maliyeti,
pencere sonu mağaza stoğu. Elle kurulmuş tablolarla; koşuyla bağlantısı
`tests/test_oyun.py`'de."""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from replenishment import olcutler
from replenishment.sabitler import ACIK_TL_ADET, KOLI_TL

BAS, BIT = date(2024, 9, 2), date(2024, 9, 15)


def _gercek():
    return pd.DataFrame({
        "tarih": pd.to_datetime(["2024-09-01", "2024-09-02", "2024-09-02", "2024-09-03", "2024-09-10",
                                 "2024-09-15", "2024-09-15", "2024-09-16"]),
        "magaza_id": ["M1", "M1", "M2", "M1", "M2", "ONL", "M1", "M1"],
        "urun_id": ["A", "A", "A", "B", "B", "A", "A", "A"],
        "talep": [3, 2, 1, 4, 1, 5, 2, 1],
        "kendi_satis": [0, 2, 0, 1, 0, 0, 2, 0],
    })


def test_bulunabilirlik_fiziksel_pencere_talepli_gun():
    # pencerede fiziksel talepli hücre-gün: 09-02 M1, 09-02 M2, 09-03 M1, 09-10 M2, 09-15 M1 = 5;
    # kendi satışı olan: 09-02 M1, 09-03 M1, 09-15 M1 = 3 (ONL ve pencere dışı sayılmaz)
    assert olcutler.bulunabilirlik(_gercek(), BAS, BIT) == pytest.approx(60.0)


def test_bulunabilirlik_talep_sifir_satir_sayilmaz():
    g = _gercek()
    g.loc[1, "talep"] = 0           # gerçek tablo talepsiz satır içermez; içerse de payda dışı
    g.loc[1, "kendi_satis"] = 0
    assert olcutler.bulunabilirlik(g, BAS, BIT) == pytest.approx(50.0)


def test_bulunabilirlik_bos_pencere():
    assert olcutler.bulunabilirlik(_gercek(), date(2025, 1, 1), date(2025, 1, 7)) == 0.0


def test_toplama_maliyeti():
    hafta = pd.DataFrame({"gun": [1, 8], "acik_adet": [100.0, 50.0], "koli_sayisi": [3.0, 7.0]})
    assert olcutler.toplama_maliyeti(hafta) == 150 * ACIK_TL_ADET + 10 * KOLI_TL


def test_toplama_maliyeti_bos_hafta():
    assert olcutler.toplama_maliyeti(pd.DataFrame(columns=["gun", "tarih"])) == 0.0


def test_magaza_stok_son_son_fotograf_fiziksel():
    stok = pd.DataFrame({
        "tarih": pd.to_datetime(["2024-09-02", "2024-09-09", "2024-09-09", "2024-09-09", "2024-09-16"]),
        "magaza_id": ["M1", "M1", "M2", "ONL", "M1"],
        "adet": [10, 4, 6, 100, 99],
    })
    # BIT 09-15 (pazar): son fotoğraf 09-09; ONL sayılmaz; 09-16 pencereden sonra
    assert olcutler.magaza_stok_son(stok, BIT) == 10.0
    assert olcutler.magaza_stok_son(stok, date(2024, 9, 16)) == 99.0
    with pytest.raises(ValueError):
        olcutler.magaza_stok_son(stok, date(2024, 9, 1))


def test_temel_olcutler_kosudan_okur():
    tablolar = {
        "gercek": _gercek(),
        "stok": pd.DataFrame({"tarih": pd.to_datetime(["2024-09-09"]), "magaza_id": ["M1"],
                              "urun_id": ["A"], "adet": [7]}),
    }
    kayit = pd.DataFrame({
        "gun": [1, 1, 1, 1, 1], "tarih": pd.to_datetime(["2024-09-02"] * 5),
        "kalem": ["pazartesi", "acik_adet", "koli_sayisi", "gonderilen_adet", "koli_adet"],
        "hucre": [-1] * 5, "magaza_id": [""] * 5, "urun_id": [""] * 5, "deger": [1.0, 20.0, 2.0, 34.0, 14.0],
    })
    kosu = SimpleNamespace(tablo=lambda ad, sutunlar=None, urunler=None: tablolar[ad][list(sutunlar)],
                           kayitlar={"replenishment": kayit})
    o = olcutler.temel_olcutler(kosu, BAS, BIT)
    assert o == {
        "bulunabilirlik": pytest.approx(60.0),
        "toplama_maliyeti_tl": 20 * ACIK_TL_ADET + 2 * KOLI_TL,
        "magaza_stok_son": 7.0,
        "acik_adet": 20.0, "koli_sayisi": 2.0, "koli_adet": 14.0, "gonderilen_adet": 34.0,
    }
