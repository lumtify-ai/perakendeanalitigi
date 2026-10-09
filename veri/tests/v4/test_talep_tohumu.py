"""Testler: `simule_et(..., talep_tohumu=...)` (RPT v4, Görev 1).

Spec: docs/superpowers/specs/2026-10-09-rpt-v4-design.md §3.2
Brief: .superpowers/sdd/2026-10-09-rpt-v4/task-1-brief.md

`talep_tohumu=None` (varsayılan) bugünkü davranıştır: talep, `beden_ikame`
ve `ikame` tekdüzeleri dünyanın tohumundan çekilir; yayımlanan v4 bu yolla
üretilmiştir. Bir değer verilirse yalnız bu üç tekdüze o tohumdan çekilir;
dünya (mağazalar, ürünler, beklenen talep, sürprizler) ve operasyon
çekilişleri (indirim, iade, kalite) aynı kalır.

Hızlı testler KUCUK dünyada kısa koşularla (`GUN_SAYISI`); tam
karşılaştırma (`yavas`, `veri`) TAM dünyayı yayımlanan yolla yeniden üretir
ve 18 tabloyu `cikti/v4/parquet` ile karşılaştırır (~5 dk, ~6 GB).
"""

import io

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.motor.satis import ikame, tekduzeler

GUN_SAYISI = 200  # satış, kayıp ve ikame oluşur; tam KUCUK koşusu gereksiz
BASKA_TOHUM = 7


def _esit(a, b, ad: str = "") -> None:
    """Ham motor çıktısının iki değeri birebir aynı (DataFrame, dizi, sözlük,
    liste ya da skaler; iç içe)."""
    if isinstance(a, pd.DataFrame):
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), obj=ad)
    elif isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b, err_msg=ad)
        assert a.dtype == b.dtype, ad
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), ad
        for k in a:
            _esit(a[k], b[k], f"{ad}.{k}")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), ad
        for i, (x, y) in enumerate(zip(a, b)):
            _esit(x, y, f"{ad}[{i}]")
    else:
        assert a == b, ad


@pytest.fixture(scope="module")
def varsayilan(kucuk_dunya):
    return simule_et(kucuk_dunya, gun_sayisi=GUN_SAYISI, kayit_talep=True)


@pytest.fixture(scope="module")
def baska(kucuk_dunya):
    return simule_et(kucuk_dunya, gun_sayisi=GUN_SAYISI, kayit_talep=True, talep_tohumu=BASKA_TOHUM)


# ---------------------------------------------------------------------------
# Varsayılan = bugünkü davranış
# ---------------------------------------------------------------------------


def test_varsayilan_tohum_ayni_tablolar(kucuk_dunya, varsayilan):
    """Parametresiz koşu, `talep_tohumu=None` ve `talep_tohumu=dunya.tohum`
    koşularının bütün çıktıları birebir aynı (Review Focus 2)."""
    w = kucuk_dunya
    none = simule_et(w, gun_sayisi=GUN_SAYISI, kayit_talep=True, talep_tohumu=None)
    acik = simule_et(w, gun_sayisi=GUN_SAYISI, kayit_talep=True, talep_tohumu=w.tohum)
    assert len(varsayilan["satis"]) > 0 and len(varsayilan["ikame_satis"]) > 0
    for ad in varsayilan:
        _esit(varsayilan[ad], none[ad], ad)
        _esit(varsayilan[ad], acik[ad], ad)


def test_tekduzeler_talep_tohumu():
    """`talep` tekdüzesi verilen talep tohumundan; indirim ve iade yalnız
    operasyon tohumundan (talep tohumu onları değiştirmez)."""
    C = 50
    a = tekduzeler(10, C, sabitler.TOHUM, sabitler.TOHUM)
    b = tekduzeler(10, C, BASKA_TOHUM, sabitler.TOHUM)
    assert not np.array_equal(a["talep"], b["talep"])
    np.testing.assert_array_equal(a["indirim"], b["indirim"])
    np.testing.assert_array_equal(a["iade"], b["iade"])


def test_ikame_tohumu(kucuk_dunya):
    """`ikame(..., tohum=None)` dünyanın tohumuyla aynı; başka tohum başka
    çekiliş (beden ve kategori ikamesi)."""
    w = kucuk_dunya
    d, C = 400, len(w.cesit)
    lam = w.lam.gun(d)
    kayip = np.where(lam > 0.2, 3, 0).astype(np.int64)
    stok = np.where(kayip > 0, 0, 2).astype(np.int64)
    s0, g0 = ikame(stok, kayip, w, d)
    s1, g1 = ikame(stok, kayip, w, d, tohum=w.tohum)
    s2, g2 = ikame(stok, kayip, w, d, tohum=BASKA_TOHUM)
    np.testing.assert_array_equal(s0, s1)
    np.testing.assert_array_equal(g0, g1)
    assert s0.sum() > 0
    assert not np.array_equal(s0, s2)
    assert s2.sum() + g2.sum() == kayip.sum()


# ---------------------------------------------------------------------------
# Farklı tohum: talep değişir, dünya değişmez
# ---------------------------------------------------------------------------


def _dunya_izi(w) -> dict:
    """Dünyanın talep ve option yüzü (kopya): beklenen talep birkaç günde,
    option, ürün, mağaza, plan ve kampanya tabloları."""
    return {
        "lam": np.stack([np.array(w.lam.gun(d), copy=True) for d in (0, 50, GUN_SAYISI - 1, 400)]),
        "optionlar": w.optionlar.copy(),
        "urunler": w.urunler.copy(),
        "magazalar": w.magazalar.copy(),
        "kampanya": w.kampanya.copy(),
        "tohum": w.tohum,
    }


def test_farkli_tohum_talebi_degistirir_dunyayi_degistirmez(kucuk_dunya, varsayilan):
    w = kucuk_dunya
    once = _dunya_izi(w)
    b = simule_et(w, gun_sayisi=GUN_SAYISI, kayit_talep=True, talep_tohumu=BASKA_TOHUM)
    _esit(once, _dunya_izi(w), "dunya")

    a = varsayilan
    # Talep matrisi farklı, ama aynı beklenen talepten: toplam yakın.
    assert not np.array_equal(a["talep"], b["talep"])
    ta, tb = int(a["talep"].sum()), int(b["talep"].sum())
    assert abs(ta - tb) / ta < 0.02, (ta, tb)
    # Talebin olabileceği hücre-günler aynı: λ = 0 olan yerde iki koşuda da 0.
    lam = np.stack([w.lam.gun(d) for d in range(GUN_SAYISI)])
    assert (a["talep"][lam == 0] == 0).all() and (b["talep"][lam == 0] == 0).all()
    # Satış ve ikame de değişir.
    assert not a["satis"].equals(b["satis"])
    assert not a["ikame_satis"].equals(b["ikame_satis"])
    # Satıştan önce verilen kararlar (başlangıç siparişleri) dünyaya aittir.
    ilk_a = [s for s in a["siparis"] if s["tip"] == "baslangic"]
    ilk_b = [s for s in b["siparis"] if s["tip"] == "baslangic"]
    assert ilk_a
    _esit(ilk_a, ilk_b, "baslangic_siparis")


def test_ayni_tohum_deterministik(kucuk_dunya, baska):
    b2 = simule_et(kucuk_dunya, gun_sayisi=GUN_SAYISI, kayit_talep=True, talep_tohumu=BASKA_TOHUM)
    for ad in baska:
        _esit(baska[ad], b2[ad], ad)


# ---------------------------------------------------------------------------
# Tam karşılaştırma: varsayılan yol yayımlanan v4'ü yeniden üretir
# ---------------------------------------------------------------------------


def _parquet_turu(df: pd.DataFrame) -> pd.DataFrame:
    """Yayımlama yolundaki Parquet gidiş-dönüşü (`disa_aktar.yaz`:
    `to_parquet(index=False)`), bellekte."""
    tampon = io.BytesIO()
    df.to_parquet(tampon, index=False)
    tampon.seek(0)
    return pd.read_parquet(tampon)


@pytest.mark.yavas
@pytest.mark.veri
def test_tam_kosu_yayimlanan_v4_ile_ayni():
    """`uret.main` yolu (TAM dünya, `simule_et(dunya)`, `yayimla`) bugünkü
    kodla yayımlanan 18 tabloyu birebir verir: her tablo, Parquet gidiş-
    dönüşünden sonra `cikti/v4/parquet/<tablo>.parquet` ile aynı (değer,
    tür, sıra). Ayrıca yok-satma hakeminin DuckDB doğrulaması (satır,
    Σ adet, günlük satış) tutar."""
    import duckdb

    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek
    from perakende_veri.v4.uret import yayimla

    parquet = sabitler.CIKTI_DIZINI / "parquet"
    db_yolu = sabitler.CIKTI_DIZINI / "perakende.duckdb"
    if not parquet.exists() or not db_yolu.exists():
        pytest.skip("yayımlanan v4 yok (python -m perakende_veri.v4.uret)")

    dunya = dunya_kur(Olcek.TAM)
    ham = simule_et(dunya)
    tablolar = yayimla(dunya, ham)
    del ham

    yayimlanan = sorted(p.stem for p in parquet.glob("*.parquet"))
    assert sorted(tablolar) == yayimlanan
    for ad in yayimlanan:
        pd.testing.assert_frame_equal(
            _parquet_turu(tablolar[ad]), pd.read_parquet(parquet / f"{ad}.parquet"), obj=ad,
        )

    con = duckdb.connect(str(db_yolu), read_only=True)
    try:
        for ad in yayimlanan:
            n = con.execute(f"select count(*) from {ad}").fetchone()[0]
            assert len(tablolar[ad]) == int(n), ad
        adet = con.execute("select sum(adet) from satis").fetchone()[0]
        assert int(tablolar["satis"]["adet"].sum()) == int(adet)
        db = con.execute("select tarih, sum(adet) as adet from satis group by tarih order by tarih").df()
    finally:
        con.close()
    yeni = tablolar["satis"].groupby("tarih", observed=True)["adet"].sum().sort_index()
    np.testing.assert_array_equal(pd.to_datetime(db["tarih"]).to_numpy(), pd.to_datetime(yeni.index).to_numpy())
    np.testing.assert_array_equal(db["adet"].to_numpy(dtype=np.int64), yeni.to_numpy(dtype=np.int64))
