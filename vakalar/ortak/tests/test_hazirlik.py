"""hazirlik: günlük tablo, çarpanlar ve kayıp tablosu yazımı (oyuncak dünya)."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from perakende_analitik import hazirlik

PENCERE = (date(2025, 1, 6), date(2025, 1, 26))


@pytest.fixture
def gunluk(oyuncak_con, tmp_path):
    yol = tmp_path / "gunluk.parquet"
    hazirlik.gunluk_yaz(oyuncak_con, yol, PENCERE)
    return yol


def test_gunluk_pencere_disina_cikmaz(gunluk):
    g = pd.read_parquet(gunluk)
    assert list(g.columns) == hazirlik.GUNLUK_SUTUNLARI
    assert g["tarih"].min() >= pd.Timestamp(PENCERE[0])
    assert g["tarih"].max() <= pd.Timestamp(PENCERE[1])
    assert {"bos", "tukenen", "stoklu"} <= set(g["durum"].astype(str))


def test_hedef_araligi_yalniz_aralik_satirlarini_yazar(oyuncak_con, gunluk, tmp_path):
    bas, bit = date(2025, 1, 9), date(2025, 1, 14)
    tam = tmp_path / "tam.parquet"
    aralikli = tmp_path / "aralikli.parquet"
    hazirlik.kayip_yaz(oyuncak_con, "naif", gunluk, tmp_path / "yok.pkl", tam)
    ozet = hazirlik.kayip_yaz(oyuncak_con, "naif", gunluk, tmp_path / "yok.pkl", aralikli,
                              hedef_araligi=(bas, bit))
    t = pd.read_parquet(tam)
    a = pd.read_parquet(aralikli)

    assert len(a) > 0
    assert a["tarih"].between(pd.Timestamp(bas), pd.Timestamp(bit), inclusive="left").all()
    beklenen = t[(t["tarih"] >= pd.Timestamp(bas)) & (t["tarih"] < pd.Timestamp(bit))]
    assert len(a) < len(t)
    assert len(a) == len(beklenen)
    anahtar = ["tarih", "magaza_id", "urun_id"]
    kes = lambda d: d.sort_values(anahtar).reset_index(drop=True)   # noqa: E731
    pd.testing.assert_frame_equal(kes(a), kes(beklenen))
    assert ozet["hedef_satir"] == len(a)
    assert ozet["toplam_kayip"] == pytest.approx(float(beklenen["kayip"].sum()))


def test_hedef_araligi_egitim_havuzunu_degistirmez(oyuncak_con, gunluk, tmp_path):
    tam = hazirlik.kayip_yaz(oyuncak_con, "naif", gunluk, tmp_path / "yok.pkl", tmp_path / "t.parquet")
    dar = hazirlik.kayip_yaz(oyuncak_con, "naif", gunluk, tmp_path / "yok.pkl", tmp_path / "d.parquet",
                             hedef_araligi=(date(2025, 1, 9), date(2025, 1, 14)))
    assert dar["havuz_satir"] == tam["havuz_satir"]


def test_agacsiz_kaynak_sutunu_yok(oyuncak_con, gunluk, tmp_path):
    agacli = tmp_path / "agacli.parquet"
    agacsiz = tmp_path / "agacsiz.parquet"
    hazirlik.kayip_yaz(oyuncak_con, "naif", gunluk, tmp_path / "yok.pkl", agacli)
    hazirlik.kayip_yaz(oyuncak_con, "naif", gunluk, tmp_path / "yok.pkl", agacsiz, agacli=False)
    assert "kaynak" in pd.read_parquet(agacli).columns
    s = pd.read_parquet(agacsiz)
    assert "kaynak" not in s.columns and "firsat" not in s.columns
    pd.testing.assert_frame_equal(s, pd.read_parquet(agacli)[list(s.columns)])


def test_atomik_yazim_ara_dosya_birakmaz(oyuncak_con, gunluk, tmp_path, monkeypatch):
    kayip = tmp_path / "kayip.parquet"
    hazirlik.kayip_yaz(oyuncak_con, "naif", gunluk, tmp_path / "yok.pkl", kayip)
    assert not list(tmp_path.glob("*.yaziliyor"))

    # yazım yarıda kesilirse: eski dosya olduğu gibi kalır, ara dosya silinir
    kayip.write_bytes(b"eski")

    def yarida_kes(self, yol, *a, **k):
        Path(yol).write_bytes(b"yarim")
        raise OSError("disk dolu")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", yarida_kes)
    with pytest.raises(OSError, match="disk dolu"):
        hazirlik.kayip_yaz(oyuncak_con, "naif", gunluk, tmp_path / "yok.pkl", kayip)
    assert kayip.read_bytes() == b"eski"
    assert not list(tmp_path.glob("*.yaziliyor"))


def test_kestirici_bilinmeyen_ad_hata(tmp_path):
    with pytest.raises(ValueError, match="bilinmeyen kestirici"):
        hazirlik.kestirici("yok", tmp_path / "c.pkl")


@pytest.mark.filterwarnings("ignore:Mean of empty slice:RuntimeWarning")
def test_carpanlar_ogrenme_bitisine_dek_ogrenir(oyuncak_con, gunluk, tmp_path):
    yol = tmp_path / "carpanlar.pkl"
    erken = hazirlik.carpanlar_yaz(oyuncak_con, gunluk, yol, date(2025, 1, 12))
    tum = hazirlik.carpanlar_yaz(oyuncak_con, gunluk, yol, PENCERE[1])
    assert 0 < erken < tum
    assert not list(tmp_path.glob("*.yaziliyor"))
    assert hazirlik.kestirici("basit", yol) is not None
