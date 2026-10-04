"""Sentetik hücre-gün çerçeveleri: `ozellikler.ekle` çıktısının biçimi, DuckDB'siz.

`cerceve(...)` günlük tablonun sütunlarını (tarih, magaza_id, urun_id,
option_id, satis_oncesi, brut_satis, net_satis, durum) ve bütün
`ozellikler.OZELLIKLER` sütunlarını aynı türlerle kurar. Verilmeyen özellik
nötrdür: tatil yok, kampanya yok, markdown yok, devamlı ürün (yas_gun −1).
Skaler değerler bütün satırlara yayılır.
"""

import numpy as np
import pandas as pd

from perakende_analitik import stok

_KATEGORIK = ("magaza_id", "urun_id", "option_id", "kampanya_id", "line", "ust_kategori",
              "alt_kategori", "fiyat_segmenti", "magaza_tipi", "sehir", "kanal")


def _yay(deger, n: int) -> np.ndarray:
    a = np.asarray(deger)
    return np.broadcast_to(a, (n,)).copy() if a.ndim == 0 else a


def cerceve(tarih, magaza_id, urun_id, brut_satis, *, option_id=None, durum="stoklu",
            **ozellik) -> pd.DataFrame:
    tarih = pd.to_datetime(pd.Series(np.asarray(tarih))).astype("datetime64[ns]").to_numpy()
    n = len(tarih)
    magaza = _yay(np.asarray(magaza_id, dtype=object), n)
    urun = _yay(np.asarray(urun_id, dtype=object), n)
    if option_id is None:
        option_id = np.array([u.rsplit("-", 1)[0] for u in urun], dtype=object)
    satis = _yay(np.asarray(brut_satis), n).astype("int32")
    gun = tarih.astype("datetime64[D]").astype(np.int64)
    onl = magaza == "ONL"

    v = {
        "tarih": tarih,
        "magaza_id": magaza,
        "urun_id": urun,
        "option_id": _yay(np.asarray(option_id, dtype=object), n),
        "satis_oncesi": np.where(_yay(np.asarray(durum, dtype=object), n) == "bos", 0, satis + 5),
        "brut_satis": satis,
        "net_satis": satis,
        "durum": _yay(np.asarray(durum, dtype=object), n),
        "hafta_gunu": ((gun + 3) % 7).astype(np.int8),
        "tatil": False, "black_friday": False, "indirim_baslangici": False,
        "markdown_orani": 0.0, "kampanya_orani": 0.0, "kampanya_id": None,
        "yas_gun": -1, "line": "Basic", "ust_kategori": "Üst Giyim", "alt_kategori": "Gömlek",
        "fiyat_segmenti": "Orta", "beden_sira": 3, "magaza_tipi": np.where(onl, "Online", "AVM"),
        "sehir": "İstanbul", "metrekare": 1000, "kanal": np.where(onl, "online", "magaza"),
        "liste_fiyati": 500.0, "alis_fiyati": 200.0,
    }
    v.update(ozellik)
    v = {k: _yay(np.asarray(x, dtype=object) if x is None else x, n) for k, x in v.items()}
    if "oran" not in ozellik:
        v["oran"] = np.maximum(v["markdown_orani"].astype(float), v["kampanya_orani"].astype(float))

    df = pd.DataFrame({
        "tarih": v["tarih"],
        "magaza_id": v["magaza_id"], "urun_id": v["urun_id"], "option_id": v["option_id"],
        "satis_oncesi": v["satis_oncesi"].astype("int32"),
        "brut_satis": v["brut_satis"], "net_satis": v["net_satis"].astype("int32"),
        "durum": pd.Categorical(v["durum"], categories=stok.DURUMLAR),
        "hafta_gunu": v["hafta_gunu"].astype(np.int8),
        "tatil": v["tatil"].astype(bool), "black_friday": v["black_friday"].astype(bool),
        "indirim_baslangici": v["indirim_baslangici"].astype(bool),
        "markdown_orani": v["markdown_orani"].astype(np.float32),
        "kampanya_orani": v["kampanya_orani"].astype(np.float32),
        "kampanya_id": v["kampanya_id"],
        "oran": v["oran"].astype(np.float32),
        "yas_gun": v["yas_gun"].astype(np.int16),
        "line": v["line"], "ust_kategori": v["ust_kategori"], "alt_kategori": v["alt_kategori"],
        "fiyat_segmenti": v["fiyat_segmenti"], "beden_sira": v["beden_sira"].astype(np.int16),
        "magaza_tipi": v["magaza_tipi"], "sehir": v["sehir"],
        "metrekare": v["metrekare"].astype(np.int32), "kanal": v["kanal"],
        "liste_fiyati": v["liste_fiyati"].astype(np.float32),
        "alis_fiyati": v["alis_fiyati"].astype(np.float32),
    })
    for k in _KATEGORIK:
        df[k] = df[k].astype("category")
    return df


def birlestir(*parcalar: pd.DataFrame) -> pd.DataFrame:
    """Parçaları alt alta koyar; kategorik sütunlar birleşik kategoriyle kalır."""
    df = pd.concat(parcalar, ignore_index=True)
    for k in _KATEGORIK + ("durum",):
        if df[k].dtype != "category":
            df[k] = df[k].astype("category")
    df["durum"] = df["durum"].cat.set_categories(stok.DURUMLAR)
    return df
