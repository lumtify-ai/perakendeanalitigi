import json

import pytest

from rpt import hazirla


def test_gunluk_yolu_yoksa_komut_soyler(tmp_path):
    with pytest.raises(RuntimeError, match="rpt.hazirla"):
        hazirla.gunluk_yolu(tmp_path)


def test_gunluk_yolu_bayat_pencere(tmp_path):
    (tmp_path / hazirla.GUNLUK).write_bytes(b"")
    (tmp_path / hazirla.KAYNAK).write_text(json.dumps({"pencere": ["2024-01-01", "2024-12-31"]}),
                                           encoding="utf-8")
    with pytest.raises(RuntimeError, match="pencere"):
        hazirla.gunluk_yolu(tmp_path)
    (tmp_path / hazirla.KAYNAK).write_text(json.dumps({"pencere": hazirla._iz_pencere()}),
                                           encoding="utf-8")
    assert hazirla.gunluk_yolu(tmp_path) == tmp_path / hazirla.GUNLUK


@pytest.mark.veri
def test_carpan_bulucu_kapanmis_sezon_yoksa_notr():
    import pandas as pd
    from perakende_analitik.carpanlar import Carpanlar

    from rpt import kaynak

    if not kaynak.VERITABANI.exists():
        pytest.skip("v4 verisi yok")
    con = kaynak.baglan()
    try:
        try:
            yol = hazirla.gunluk_yolu(con=con)
        except RuntimeError as e:
            pytest.skip(str(e))
        bul = hazirla.carpan_bulucu(con, yol)
        n = bul(pd.Timestamp("2023-03-13"))                           # SS23 1. dalga, h = 4
        bos = Carpanlar()
        assert (n.hafta_gunu, n.ozel_gun, n.esneklik_kampanya) == (bos.hafta_gunu, bos.ozel_gun, {})
        assert n.yasam.empty and n.beden_payi.empty
        t = pd.Timestamp("2024-09-02")                                # AW24 1. dalga, h = 2
        c = bul(t)
        assert c is bul(pd.Timestamp("2024-12-09"))                   # aynı küme: SS23, AW23, SS24
        assert c.hafta_gunu == hazirla.carpanlar(con, yol, t).hafta_gunu and c.hafta_gunu
    finally:
        con.close()
