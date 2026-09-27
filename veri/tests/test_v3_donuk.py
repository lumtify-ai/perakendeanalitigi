"""v3 kilidi: v3 veri seti dondurulmuştur.

`vakalar/rpt` ve yayımlanmış altı RPT yazısı v3'ü okur ve
sayıları v3'den gelir. v4 işi v3'ün modüllerine,
tohum sırasına ya da sabitlerine dokunursa bu test düşer.

Özet, her tablonun metne çevrilip BÜTÜN kolonlara göre sıralanmış CSV
serileştirmesinin sha256'sıdır: satır sırasından bağımsız, içerikten
bağımlı. Değerler v4 işine başlanmadan önce (2026-09-27) kaydedildi.
"""

import hashlib

import pandas as pd
import pytest

from perakende_veri.v3.uret import tablolari_uret

BEKLENEN = {
    "depo_stok": (108785, "a414303d84f001e3d2345936522cbd314ba0f285440cf4ca80de5b403add84d8"),
    "kayip_satis": (119296, "235e34f886754b695402e13df4d431be2fa4ad86c3d7c8115921a512b2db6af4"),
    "magaza": (25, "5b515d8b50ba18171c9bdfa322f0008dcaf45dd5756d0b5b1ba514589742ed5f"),
    "satis": (978004, "9f06ddabff785a631c33845c52764ce272039b1e319926ca24dd76336933b6e6"),
    "sevkiyat": (318684, "233d317620dd553883fa6c80344ac185cda505f2cc2b234e9e65c6299359d3a7"),
    "sezon": (15, "4cb9f101346c3bcea929edc5119d883fc2402cfb58e8114591d84e53bcc6376e"),
    "siparis": (14605, "f3d87e69cc606dce113e6e4f6006a0bddfd9d9c06765e586284f1e8d31f26ec7"),
    "stok": (1049815, "b9016a01479b9a9e08f07d5921e6fc4398d2c336dd1211f1739308564ff12997"),
    "takvim": (731, "47f16d8a23555fa393baaa2bd3e490a9fc7317b6abdea0a43868c732428f3c99"),
    "tedarikci": (8, "47cefa5b666600fb6f4c53a178782f69bbe0429edd9ffe908b0bcb9ec1bf1f32"),
    "urun": (3600, "33bd643e9eb605dc42296ebb8da3df65f8ed8345c293119b6c325f517b0303bc"),
}


def _ozet(df: pd.DataFrame) -> str:
    kanonik = df.astype(str)
    kanonik = kanonik.sort_values(list(kanonik.columns)).reset_index(drop=True)
    metin = kanonik.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def tablolar():
    return tablolari_uret()


def test_v3_tablo_kumesi_degismedi(tablolar):
    assert set(tablolar) == set(BEKLENEN)


@pytest.mark.parametrize("ad", list(BEKLENEN))
def test_v3_tablo_bayt_bayt_ayni(tablolar, ad):
    satir, ozet = BEKLENEN[ad]
    assert len(tablolar[ad]) == satir
    assert _ozet(tablolar[ad]) == ozet, f"v3 '{ad}' tablosu değişti"
