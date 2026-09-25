"""Yeniden oynatma kilidi.

Dışa aktarılan v3, motorun varsayılan politikalarla ve önceden hesaplanmış
talep matrisiyle koşulmasının çıktısıdır. RPT vakası aynı motoru başka
politikalarla çağırır; bu test, "varsayılan politikalar + verilen talep =
yayımlanan tablolar" eşitliğini kilitler. Üretilmiş veri yoksa atlanır.
"""

import duckdb
import pandas as pd
import pytest

from perakende_veri.v3 import sabitler
from perakende_veri.v3.dunya import dunya_kur, talep_matrisi
from perakende_veri.v3.politika import LumodaRPT, mevcut_dagitim
from perakende_veri.v3.simulasyon import simule_et
from perakende_veri.v3.uret import hareket_tablolari

DB = sabitler.CIKTI_DIZINI / "perakende.duckdb"
ANAHTAR = ["tarih", "magaza_id", "urun_id"]


@pytest.fixture(scope="module")
def db():
    if not DB.exists():
        pytest.skip("v3 üretilmemiş: python -m perakende_veri.v3.uret")
    con = duckdb.connect(str(DB), read_only=True)
    yield lambda ad: _normal(con.sql(f"SELECT * FROM {ad}").df())
    con.close()


@pytest.fixture(scope="module")
def yeniden():
    """Vakanın yapacağı gibi: dünya, talep matrisi, açık politikalar."""
    dunya = dunya_kur()
    talep = talep_matrisi(dunya)
    ham = simule_et(dunya, talep, rpt_politikasi=LumodaRPT(), dagitim_politikasi=mevcut_dagitim)
    return {ad: _normal(df) for ad, df in hareket_tablolari(dunya, ham).items()}


def _normal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for kolon in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[kolon]):
            df[kolon] = df[kolon].astype("datetime64[ns]")
    return df


def _sirala(df, kolonlar):
    return df.sort_values(kolonlar, kind="stable").reset_index(drop=True)


def test_kayip_satis_birebir(db, yeniden):
    pd.testing.assert_frame_equal(_sirala(db("kayip_satis"), ANAHTAR),
                                  _sirala(yeniden["kayip_satis"], ANAHTAR), check_dtype=False)


def test_satis_birebir_kirli_kayitlar_haric(db, yeniden):
    # Mükerrer satırlar birebir kopyadır; (tarih, mağaza, ürün, adet) temiz
    # tabloda tekildir (aynı gün satış ve iade ayrı işaretli satırlar).
    kayitli = db("satis").drop_duplicates(ANAHTAR + ["adet"])
    k = ANAHTAR + ["adet"]
    pd.testing.assert_frame_equal(_sirala(kayitli[k], k), _sirala(yeniden["satis"][k], k),
                                  check_dtype=False)


def test_sevkiyat_depo_siparis_birebir(db, yeniden):
    pd.testing.assert_frame_equal(_sirala(db("sevkiyat"), ANAHTAR + ["tip"]),
                                  _sirala(yeniden["sevkiyat"], ANAHTAR + ["tip"]), check_dtype=False)
    pd.testing.assert_frame_equal(_sirala(db("depo_stok"), ["tarih", "urun_id"]),
                                  _sirala(yeniden["depo_stok"], ["tarih", "urun_id"]), check_dtype=False)
    pd.testing.assert_frame_equal(_sirala(db("siparis"), ["siparis_id", "urun_id"]),
                                  _sirala(yeniden["siparis"], ["siparis_id", "urun_id"]),
                                  check_dtype=False)


def test_stok_birebir_hayalet_haric(db, yeniden):
    kayitli = db("stok")
    temiz = yeniden["stok"]
    ic = kayitli.merge(temiz[ANAHTAR], on=ANAHTAR, how="inner")
    assert len(kayitli) - len(ic) == sabitler.HAYALET_STOK_KAYDI
    pd.testing.assert_frame_equal(_sirala(ic, ANAHTAR), _sirala(temiz, ANAHTAR), check_dtype=False)
