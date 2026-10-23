"""Fikstürlerin kendisi: sahte `Gorunum` gerçek dataclass'ın alanlarını taşır, oyuncak tablolar
v4 şemasındadır.
"""

import dataclasses

import duckdb
import numpy as np
import pytest
from conftest import GUN_SIFIRI, AcikDunya, gorunum, oyuncak_optionlar
from perakende_veri.v4.motor.durum import Gorunum

OPTION_SUTUNLARI = ["option_id", "sezon_kodu", "line", "lansman_gun", "indirim_gun", "cikis_gun",
                    "sezonluk", "ust_kategori", "alt_kategori", "dalga", "liste_fiyati"]


def _ornek(gun=10, **kw):
    C, S, O = 4, 3, 2
    sg = np.arange(30 * C, dtype=np.int16).reshape(30, C) % 3
    return gorunum(gun, stok=[5, 0, 2, 9], depo=[1, 2, 3], satis_gecmisi=sg,
                   stoklu_gecmisi=sg > 0, fiyat_orani=np.zeros((O, 3)), **kw)


def test_gorunum_gercek_alanlari_tasir():
    g = _ornek(optionlar="x")
    assert isinstance(g, Gorunum)
    alanlar = {f.name for f in dataclasses.fields(Gorunum)}
    assert alanlar == {f.name for f in dataclasses.fields(g)}
    assert g.dunya.optionlar == "x" and g.tarih == GUN_SIFIRI + np.timedelta64(10, "D")
    assert g.satis_gecmisi.shape == (30, 4) and g.magaza_stok.tolist() == [5, 0, 2, 9]
    assert g.satis_oncesi_gecmisi is None and g.fiyat_gecmisi is None


def test_gorunum_bugunu_ve_sonrasini_gormez():
    g = _ornek(gun=10)
    assert g.satis_gecmisi[10:].sum() == 0 and not g.stoklu_gecmisi[10:].any()
    assert g.satis_gecmisi[:10].sum() > 0
    assert g.satis_28.tolist() == g.satis_gecmisi[:10].sum(axis=0).tolist()    # 28 günden kısa geçmiş


def test_gorunum_salt_okunur():
    g = _ornek()
    for ad in ("magaza_stok", "depo", "satis_gecmisi", "fiyat_orani", "gonderilen_option"):
        with pytest.raises(ValueError):
            getattr(g, ad)[...] = 1


def test_gorunum_dunyasi_gizli_alani_vermez():
    g = _ornek(optionlar="x")
    for ad in ("lam", "esneklik", "gizli_magaza", "ilk_siparisler", "gercek"):
        with pytest.raises(AttributeError):
            getattr(g.dunya, ad)
    assert isinstance(g.dunya, AcikDunya)


def test_gorunum_gecersiz_girdi():
    sg = np.zeros((5, 4), dtype=np.int16)
    with pytest.raises(ValueError, match="gun"):
        gorunum(10, [0] * 4, [0], sg, sg > 0, np.zeros((1, 3)))
    with pytest.raises(ValueError, match="biçim"):
        gorunum(2, [0] * 3, [0], sg, sg > 0, np.zeros((1, 3)))


def test_oyuncak_optionlar_biçimi(optionlar):
    assert set(optionlar.columns) == set(OPTION_SUTUNLARI)
    assert len(optionlar) == 13 and optionlar["sezonluk"].sum() == 12
    assert (optionlar["lansman_gun"] < optionlar["cikis_gun"]).all()
    assert optionlar.equals(oyuncak_optionlar())


def test_oyuncak_baglanti(con):
    adlar = {t for (t,) in con.execute("show tables").fetchall()}
    assert {"satis", "stok", "fiyat", "kampanya", "sezon", "takvim", "magaza", "urun"} <= adlar
    assert con.execute("select count(distinct magaza_id) from satis").fetchone()[0] == 7


def test_oyuncak_kampanya_kapsamli_ve_kapsamsiz_magaza(con):
    kapsamli, kapsamsiz = (con.execute(
        "select count(*) from satis where tarih = '2025-01-13' and kampanya_id is " + durum
    ).fetchone()[0] for durum in ("not null", "null"))
    assert kapsamli > 0 and kapsamsiz > 0
    marmara = {m for (m,) in con.execute(
        "select distinct magaza_id from satis where kampanya_id is not null").fetchall()}
    assert marmara == {"S1", "S2", "ONL"}


def test_oyuncak_erken_biten_ve_satmayan_option(con):
    sat = dict(con.execute("select o.option_id, coalesce(sum(s.adet), 0) from "
                           "(select distinct option_id from urun where line = 'Collection') o "
                           "left join urun u using (option_id) left join satis s using (urun_id) "
                           "group by 1").fetchall())
    assert sat["SS25-c"] == 0 and sat["AW24-c"] == 0
    son = con.execute("select max(tarih) from satis s join urun u using (urun_id) "
                      "where u.option_id = 'AW24-b'").fetchone()[0]
    assert str(son)[:10] == "2024-09-23"           # lansman 08-19 + 5 hafta; sonra satış yok
    assert isinstance(con, duckdb.DuckDBPyConnection)
