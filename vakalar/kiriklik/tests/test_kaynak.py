"""`kaynak`: karar girdisi (hücre, satış, stoklu gün, mağaza uygunluğu, option'lar) ve karar anı kesimi.

Oyuncak testleri `conftest`in 8 mağazalı (4 'uygun'suz) AW24 fikstürünü kullanır; `veri` işaretli testler
yayımlanan v4'ü ister.
"""

import ast
import re
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from conftest import ACIK_SIPARIS_TOPLAMI, CIKIS, INDIRIM, KARAR, urun_id

from kiriklik import kaynak, sabitler

KAYNAK_DOSYASI = Path(kaynak.__file__)


def _hucre(g, magaza, sira, sutun="stok"):
    s = g.hucre[(g.hucre.magaza_id == magaza) & (g.hucre.urun_id == urun_id("AW24-a", sira))]
    assert len(s) == 1, (magaza, sira)
    return s.iloc[0][sutun]


# ------------------------------------------------------------------ sezon ve tarihler


def test_baska_sezon_reddedilir(con):
    with pytest.raises(ValueError, match="AW25"):
        kaynak.karar_girdisi(con, "AW25")


def test_karar_tarihleri_sabitlerden(con):
    g = kaynak.karar_girdisi(con, "AW24")
    assert (g.sezon, g.karar, g.indirim, g.cikis) == (
        "AW24", date(2024, 12, 9), date(2025, 1, 2), date(2025, 2, 24))
    assert kaynak.sezon_dates(con, "AW24") == (date(2025, 1, 2), date(2025, 2, 24))
    assert sabitler.KARAR["AW24"] == KARAR.date() and sabitler.KARAR["SS25"] == date(2025, 6, 2)
    assert INDIRIM.date() == g.indirim and CIKIS.date() == g.cikis


def test_yayimlanmamis_sezon_dates_hata(con):
    with pytest.raises(ValueError):
        kaynak.sezon_dates(con, "AW25")


# ------------------------------------------------------------------ hücre


def test_hucre_kapsami_fiziksel_collection_standart_disi(con):
    g = kaynak.karar_girdisi(con, "AW24")
    assert list(g.hucre.columns) == ["magaza_id", "urun_id", "option_id", "beden_sira", "stok", "depo",
                                     "acik_siparis", "liste_fiyati", "alis_fiyati"]
    assert set(g.hucre.option_id) == {"AW24-a"}                       # Standart, Outlet line, SS25 dışarıda
    assert set(g.hucre.magaza_id) == {"S1", "S2", "S4", "S5", "S6", "S7", "S8"}   # Outlet ve Online dışarıda
    assert len(g.hucre) == 7 * 5                                      # eksik satır da hücre
    assert sorted(g.hucre.beden_sira.unique()) == [1, 2, 3, 4, 5]
    assert (g.hucre.liste_fiyati == 500.0).all() and (g.hucre.alis_fiyati == 200.0).all()


def test_hucre_karar_gunu_fotografi_eksik_satir_sifir(con):
    g = kaynak.karar_girdisi(con, "AW24")
    assert [_hucre(g, "S1", i) for i in range(1, 6)] == [1, 0, 2, 1, 1]       # 2024-12-16 (9) görünmez
    assert [_hucre(g, "S2", i) for i in range(1, 6)] == [1, 2, 2, 1, 1]
    assert [_hucre(g, "S5", i) for i in range(1, 6)] == [3, 0, 0, 0, 0]
    assert [_hucre(g, "S7", i) for i in range(1, 6)] == [0] * 5               # stok satırı yok -> 0
    assert g.hucre.stok.dtype.kind == "i"


def test_hucre_depo_karar_gunu(con):
    g = kaynak.karar_girdisi(con, "AW24")
    assert [_hucre(g, "S2", i, "depo") for i in range(1, 6)] == [0, 6, 0, 0, 0]


def test_acik_siparis_tanimi(con):
    """A: açık ve planı indirimden önce (10). B: planı indirimden sonra (sayılmaz). C: karardan önce teslim
    edilmiş (sayılmaz). D: karardan sonra verilmiş (sayılmaz). E: karar günü teslim (7, `>= karar`).
    F: karardan sonra teslim, planı indirimden önce (3). G: öteki sezon (hücrede yok)."""
    g = kaynak.karar_girdisi(con, "AW24")
    assert [_hucre(g, "S1", i, "acik_siparis") for i in range(1, 6)] == [0, ACIK_SIPARIS_TOPLAMI, 0, 0, 0]
    assert ACIK_SIPARIS_TOPLAMI == 10 + 7 + 3


def test_acik_siparis_indirim_gunu_sayilmaz(con):
    """Planlanan teslim tam indirim günü: `planlanan_teslim < indirim` sağlanmaz."""
    con.execute("update siparis set planlanan_teslim = '2025-01-02' where siparis_id = 'A'")
    g = kaynak.karar_girdisi(con, "AW24")
    assert _hucre(g, "S1", 2, "acik_siparis") == 10        # E (7) + F (3)


def test_gizli_tablo_okunmaz(con):
    """`gizli_*` tabloları (varsa) sonucu değiştirmez; kaynak onları adıyla da anmaz."""
    onceki = kaynak.karar_girdisi(con, "AW24")
    con.execute("create table gizli_talep as select 1 as x")
    con.execute("create table gizli_kayip as select 'AW24-a-1' as urun_id, 99 as adet")
    sonraki = kaynak.karar_girdisi(con, "AW24")
    pd.testing.assert_frame_equal(onceki.hucre, sonraki.hucre)
    pd.testing.assert_frame_equal(onceki.satis, sonraki.satis)
    agac = ast.parse(KAYNAK_DOSYASI.read_text(encoding="utf-8"))
    for dugum in ast.walk(agac):               # belge dizileri hariç, her metin sabiti (SQL dahil)
        if isinstance(dugum, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(dugum):
            dugum.body = dugum.body[1:]
    metinler = [d.value for d in ast.walk(agac) if isinstance(d, ast.Constant) and isinstance(d.value, str)]
    assert not [m for m in metinler if re.search(r"gizli_", m)]


# ------------------------------------------------------------------ mağaza


def test_magaza_uygunluk(con):
    g = kaynak.karar_girdisi(con, "AW24")
    assert list(g.magaza.columns) == ["magaza_id", "ad", "sehir", "bolge", "tip", "uygun"]
    assert set(g.magaza.tip) == {"AVM", "Cadde"}
    uygun = dict(zip(g.magaza.magaza_id, g.magaza.uygun, strict=True))
    assert uygun == {"S1": True, "S2": True,
                     "S4": False,    # karar günü kapalı (kapanis_tarihi geçmiş)
                     "S5": False,    # kapanış kararı karar günü öncesi alınmış (olay gelecekte)
                     "S6": True,     # kapanış kararı karardan sonra: karar anında bilinmez
                     "S7": False,    # tadilatta
                     "S8": False}    # açılışı karar gününden sonra


def test_magaza_tadilat_bitince_uygun(con):
    con.execute("update magaza_olay set bitis_tarihi = '2024-12-09' where magaza_id = 'S7'")
    g = kaynak.karar_girdisi(con, "AW24")
    assert g.magaza.set_index("magaza_id").uygun["S7"]     # bitiş günü tadilat sona ermiştir


# ------------------------------------------------------------------ satış, stoklu gün, option


def test_karar_sonrasi_satir_yok(con):
    g = kaynak.karar_girdisi(con, "AW24")
    assert g.satis.tarih.max() < pd.Timestamp(g.karar)
    assert g.stoklu.tarih.max() == pd.Timestamp(g.karar)
    assert g.stoklu.tarih.min() == pd.Timestamp("2024-11-25")


def test_satis_mukerrer_duser_iade_kalir(con):
    g = kaynak.karar_girdisi(con, "AW24")
    assert list(g.satis.columns) == ["magaza_id", "urun_id", "tarih", "adet", "tutar"]
    s = g.satis.sort_values("tarih")
    assert list(zip(s.magaza_id, s.tarih.dt.strftime("%Y-%m-%d"), s.adet, s.tutar, strict=True)) == [
        ("S1", "2024-12-07", 2, 800.0), ("S1", "2024-12-08", -1, -400.0)]    # S3 (Outlet) dışarıda


def test_stoklu_hucre_anahtarlari(con):
    g = kaynak.karar_girdisi(con, "AW24")
    assert list(g.stoklu.columns) == ["magaza_id", "urun_id", "tarih", "stoklu_gun"]
    assert set(g.stoklu.magaza_id) <= {"S1", "S2", "S4", "S5", "S6", "S7", "S8"}
    assert set(g.stoklu.urun_id) <= set(g.hucre.urun_id)
    assert len(g.stoklu) == 3 * (5 + 5 + 1)       # 3 pazartesi: S1 (5) + S2 (5) + S5 (1)


def test_optionlar(con):
    g = kaynak.karar_girdisi(con, "AW24")
    assert list(g.optionlar.columns) == ["option_id", "alt_kategori", "ust_kategori", "dalga",
                                         "lansman_tarihi", "liste_fiyati", "alis_fiyati"]
    assert list(g.optionlar.option_id) == ["AW24-a"]
    assert g.optionlar.lansman_tarihi.iloc[0] == pd.Timestamp("2024-08-19")


def test_girdi_degistirilemez(con):
    g = kaynak.karar_girdisi(con, "AW24")
    with pytest.raises(AttributeError):
        g.karar = date(2024, 12, 16)


# ------------------------------------------------------------------ bağlantı ve karar-modülü kilidi


def test_baglan_salt_okunur(tmp_path):
    yol = tmp_path / "x.duckdb"
    c = duckdb.connect(str(yol))
    c.execute("create table t as select 1 as x")
    c.close()
    ro = kaynak.baglan(yol)
    assert ro.execute("select x from t").fetchone() == (1,)
    with pytest.raises(duckdb.Error):
        ro.execute("insert into t values (2)")
    ro.close()


def test_baglan_dosya_yoksa_hata(tmp_path):
    with pytest.raises(FileNotFoundError):
        kaynak.baglan(tmp_path / "yok.duckdb")


@pytest.mark.parametrize("modul", ["kaynak", "sabitler"])
def test_karar_modulu_yasak_ice_aktarma_yok(modul):
    yol = KAYNAK_DOSYASI.with_name(f"{modul}.py")
    adlar = []
    for d in ast.walk(ast.parse(yol.read_text(encoding="utf-8"))):
        if isinstance(d, ast.Import):
            adlar += [a.name for a in d.names]
        elif isinstance(d, ast.ImportFrom):
            adlar.append(d.module or "")
            adlar += [f"{d.module}.{a.name}" for a in d.names]
    yasak = ("perakende_veri", "allocation.motor", "kiriklik.hakem", "kiriklik.simulasyon",
             "kiriklik.olcutler", "kiriklik.oyun")
    assert not [a for a in adlar if a.startswith(yasak)]


# ------------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_kesif_sayilari_aw24(veri_con):
    g = kaynak.karar_girdisi(veri_con, "AW24")
    stoklu = g.hucre.groupby(["magaza_id", "option_id"]).stok.sum()
    assert int((stoklu > 0).sum()) == 4051
    assert g.hucre[g.hucre.stok > 0].option_id.nunique() == 181


@pytest.mark.veri
def test_kesif_sayilari_ss25(veri_con):
    g = kaynak.karar_girdisi(veri_con, "SS25")
    stoklu = g.hucre.groupby(["magaza_id", "option_id"]).stok.sum()
    assert int((stoklu > 0).sum()) == 4258
    assert g.hucre[g.hucre.stok > 0].option_id.nunique() == 193


@pytest.mark.veri
@pytest.mark.parametrize("sezon", sabitler.TEST_SEZONLARI)
def test_karar_sonrasi_satir_yok_veri(veri_con, sezon):
    g = kaynak.karar_girdisi(veri_con, sezon)
    assert g.satis.tarih.max() < pd.Timestamp(g.karar)
    assert g.stoklu.tarih.max() == pd.Timestamp(g.karar)
    assert g.magaza.uygun.any() and g.hucre.acik_siparis.ge(0).all()
    assert set(g.magaza.tip) == set(sabitler.FIZIKSEL_TIPLER)
    assert g.indirim > g.karar and g.cikis > g.indirim


@pytest.mark.veri
def test_depo_ve_acik_siparis_dolu_aw24(veri_con):
    sku = kaynak.karar_girdisi(veri_con, "AW24").hucre.drop_duplicates("urun_id")   # SKU düzeyi: mağazaya tekrarlanır
    assert int(sku.acik_siparis.sum()) > 0 and int(sku.depo.sum()) > 0
