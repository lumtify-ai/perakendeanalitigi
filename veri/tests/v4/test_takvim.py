from datetime import date

import pandas as pd

from perakende_veri.v4 import sabitler, takvim


def test_gun_sayisi():
    assert takvim.D == 1277 and takvim.gun_indisi(date(2023, 1, 1)) == 181


def test_dalgalar_pazartesi():
    for s in sabitler.SEZONLAR.values():
        assert all(t.weekday() == 0 for t in s["dalgalar"]) and len(s["dalgalar"]) == 3


def test_sezon_sirasi():
    # dalga < indirim < çıkış, SS/AW dönüşümlü (ilk dalga tarihine göre kronolojik)
    sirali = sorted(sabitler.SEZONLAR.items(), key=lambda kv: kv[1]["dalgalar"][0])
    onceki_tip = None
    for kod, s in sirali:
        assert s["dalgalar"][-1] < s["indirim"] < s["cikis"]
        tip = kod[:2]
        assert tip in ("AW", "SS")
        if onceki_tip is not None:
            assert tip != onceki_tip
        onceki_tip = tip


def test_takvim_tablosu_pencere():
    t = takvim.takvim_tablosu()
    assert len(t) == 1096 and t.tarih.min() == pd.Timestamp("2023-01-01")


def test_black_friday_tatilde():
    assert all(str(b) in sabitler.TATILLER for b in sabitler.BLACK_FRIDAY)
