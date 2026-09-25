import pandas as pd

from perakende_veri.v3 import sabitler
from perakende_veri.v3.takvim import gun_indisi, sezon_tablosu, simulasyon_takvimi, takvim_uret


def test_pencere_iki_tam_yil():
    t = takvim_uret()
    assert len(t) == 731
    assert t["tarih"].min() == pd.Timestamp("2024-01-01")
    assert t["tarih"].max() == pd.Timestamp("2025-12-31")
    assert (t["tarih"].dt.dayofweek == 0).sum() == 105


def test_takvim_kolonlari():
    assert list(takvim_uret().columns) == [
        "tarih", "hafta", "ay", "yil", "sezon", "sezon_kodu", "tatil_mi", "indirim_donemi_mi",
    ]


def test_simulasyon_isinmayla_baslar():
    t = simulasyon_takvimi()
    assert t["tarih"].iloc[0] == pd.Timestamp("2023-07-03")
    assert t["tarih"].iloc[0].dayofweek == 0
    assert gun_indisi(sabitler.BASLANGIC) == 182
    assert t["tarih"].iloc[182] == pd.Timestamp(sabitler.BASLANGIC)


def test_sezon_tablosu():
    s = sezon_tablosu()
    assert len(s) == 15
    assert list(s.columns) == ["sezon_kodu", "dalga", "lansman_tarihi", "indirim_baslangic", "cikis_tarihi"]
    # Dalga ve çıkış günleri pazartesi; indirim lansmandan sonra, çıkıştan önce
    assert (s["lansman_tarihi"].dt.dayofweek == 0).all()
    assert (s["cikis_tarihi"].dt.dayofweek == 0).all()
    assert (s["lansman_tarihi"] < s["indirim_baslangic"]).all()
    assert (s["indirim_baslangic"] < s["cikis_tarihi"]).all()
    assert s.loc[(s.sezon_kodu == "SS24") & (s.dalga == 2), "lansman_tarihi"].item() == pd.Timestamp("2024-03-18")


def test_ticari_sezon_ve_indirim_donemi():
    t = takvim_uret().set_index("tarih")
    assert t.at[pd.Timestamp("2024-02-11"), "sezon_kodu"] == "AW23"
    assert t.at[pd.Timestamp("2024-02-12"), "sezon_kodu"] == "SS24"
    assert t.at[pd.Timestamp("2025-12-31"), "sezon_kodu"] == "AW25"
    assert t.at[pd.Timestamp("2024-01-02"), "indirim_donemi_mi"]
    assert not t.at[pd.Timestamp("2024-01-01"), "indirim_donemi_mi"]
    assert not t.at[pd.Timestamp("2024-02-26"), "indirim_donemi_mi"]   # çıkış günü
    assert t.at[pd.Timestamp("2025-06-30"), "indirim_donemi_mi"]
    assert not t.at[pd.Timestamp("2025-12-31"), "indirim_donemi_mi"]   # AW25 indirimi 2026'da


def test_tatiller():
    t = takvim_uret().set_index("tarih")["tatil_mi"]
    for gun in ("2024-04-10", "2024-06-16", "2024-11-29", "2025-11-28", "2025-03-31"):
        assert t[pd.Timestamp(gun)], gun
    assert not t[pd.Timestamp("2024-04-15")]
