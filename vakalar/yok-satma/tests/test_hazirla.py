"""`hazirla` duman testi: oyuncak v4 dünyasında bütün adımlar koşar, beş dosya çıkar.

Oyuncak dünya ortak paketin test fikstüründen (`vakalar/ortak/tests/conftest.py`)
kurulur ve geçici bir DuckDB dosyasına yazılır. Temel senaryo Ocak 2025'tedir;
çarpanlar ve ML 2023–2024'ten öğrendiği için buraya (yalnız ekleyerek, R2)
2024 sonunun stoklu online günlerine üç satış konur: ML gerçekten bir model
eğitir. Mağaza kanalının 2023–2024'te hiç satırı olmadığından `carpanlar`
hafta günü tablosunda boş satır ortalaması uyarısı verir (yalnız oyuncakta).
"""

import importlib.util
import json
import shutil
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from perakende_analitik import agac, stok
from yok_satma import hazirla

pytestmark = pytest.mark.filterwarnings("ignore:Mean of empty slice:RuntimeWarning")

_ORTAK_CONFTEST = Path(__file__).resolve().parents[2] / "ortak" / "tests" / "conftest.py"

GUNLUK_SUTUNLARI = ["tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi",
                    "brut_satis", "net_satis", "durum"]
KAYIP_SUTUNLARI = GUNLUK_SUTUNLARI + ["tahmini_talep", "kayip", "kayip_saf", "kaynak", "firsat"]
DOSYALAR = ["gunluk.parquet", "carpanlar.pkl", "kayip_naif.parquet", "kayip_basit.parquet",
            "kayip_ml.parquet"]


def _ortak_fikstur():
    spec = importlib.util.spec_from_file_location("ortak_conftest", _ORTAK_CONFTEST)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def oyuncak_db(tmp_path_factory) -> Path:
    """Oyuncak v4 tabloları gerçek tablolar olarak bir DuckDB dosyasında."""
    yol = tmp_path_factory.mktemp("veri") / "perakende.duckdb"
    fikstur = _ortak_fikstur()
    tablolar = fikstur.oyuncak_tablolar()
    # 2024 sonu: depo stoklu (depo_stok 2024-12-30'da başlar), online satışlar
    fikstur.ekle(tablolar, "satis", [
        ("2024-12-29", "ONL", "MDL0001-SYH-S", 1, 250.0, 0.0, None),
        ("2024-12-30", "ONL", "MDL0001-SYH-M", 2, 500.0, 0.0, None),
        ("2024-12-31", "ONL", "MDL0001-SYH-L", 1, 250.0, 0.0, None),
    ])
    con = duckdb.connect(str(yol))
    for ad, df in tablolar.items():
        con.register("_gecici", df)
        con.execute(f"create table {ad} as select * from _gecici")
        con.unregister("_gecici")
    con.close()
    return yol


@pytest.fixture(scope="module")
def cikti(oyuncak_db, tmp_path_factory) -> Path:
    dizin = tmp_path_factory.mktemp("cikti")
    hazirla.main(["--cikti", str(dizin), "--db", str(oyuncak_db)])
    return dizin


def test_bes_dosya_ve_sure(cikti):
    for ad in DOSYALAR:
        assert (cikti / ad).exists(), ad
    sure = json.loads((cikti / "sure.json").read_text(encoding="utf-8"))
    assert set(sure["adimlar"]) == set(hazirla.ADIMLAR)
    for adim in sure["adimlar"].values():
        assert adim["saniye"] >= 0 and adim["tepe_gb"] > 0


def test_gunluk_magaza_ve_online(cikti):
    g = pd.read_parquet(cikti / "gunluk.parquet")
    assert list(g.columns) == GUNLUK_SUTUNLARI
    assert {"M001", "M002", "ONL"} <= set(g["magaza_id"].astype(str))
    assert set(g["durum"].astype(str)) <= {"stoklu", "tukenen", "bos"}
    assert g["tarih"].min() >= pd.Timestamp("2023-01-01")
    assert g["tarih"].max() <= pd.Timestamp("2025-12-31")


def test_kayip_tablolari_yalniz_stoksuz_gunler(cikti):
    g = pd.read_parquet(cikti / "gunluk.parquet")
    stoksuz = int((g["durum"] != "stoklu").sum())
    assert stoksuz > 0
    for ad in ("naif", "basit", "ml"):
        k = pd.read_parquet(cikti / f"kayip_{ad}.parquet")
        assert set(KAYIP_SUTUNLARI) <= set(k.columns), ad
        assert len(k) == stoksuz, ad
        assert set(k["durum"].astype(str)) <= {"tukenen", "bos"}, ad
        assert (k["kayip"] >= 0).all() and k["kayip"].notna().all(), ad
        assert k["kaynak"].notna().all(), ad
        assert (k["tahmini_talep"] > 0).any(), ad   # ML'de: model eğitildi (sabit 0 değil)


def test_parquet_turleri(cikti):
    g = pd.read_parquet(cikti / "gunluk.parquet")
    assert g["tarih"].dtype == "datetime64[ns]"
    for c in ("magaza_id", "urun_id", "option_id", "durum"):
        assert isinstance(g[c].dtype, pd.CategoricalDtype), c
    assert list(g["durum"].cat.categories) == stok.DURUMLAR
    for c in ("satis_oncesi", "brut_satis", "net_satis"):
        assert g[c].dtype == "int32", c
    # süzülmüş okumada da bütün kategori evreni kalır
    s = pd.read_parquet(cikti / "gunluk.parquet", columns=["magaza_id", "durum"],
                        filters=[("durum", "in", ["bos"])])
    assert list(s["durum"].cat.categories) == stok.DURUMLAR
    assert list(s["magaza_id"].cat.categories) == list(g["magaza_id"].cat.categories)
    for ad in ("naif", "basit", "ml"):
        k = pd.read_parquet(cikti / f"kayip_{ad}.parquet")
        assert k["tarih"].dtype == "datetime64[ns]" and k["firsat"].dtype == "datetime64[ns]"
        for c in ("magaza_id", "urun_id", "durum", "kaynak"):
            assert isinstance(k[c].dtype, pd.CategoricalDtype), (ad, c)
        assert list(k["durum"].cat.categories) == stok.DURUMLAR
        assert list(k["kaynak"].cat.categories) == list(agac.DALLAR)


def _zamanlar(dizin: Path) -> dict[str, int | None]:
    return {ad: (dizin / ad).stat().st_mtime_ns if (dizin / ad).exists() else None
            for ad in DOSYALAR}


@pytest.fixture
def ayri_cikti(oyuncak_db, tmp_path) -> Path:
    """Durum değiştiren testler için kendi çıktı dizini (modül çıktısı bozulmasın)."""
    dizin = tmp_path / "cikti"
    hazirla.main(["--cikti", str(dizin), "--db", str(oyuncak_db)])
    return dizin


def test_gunluk_yeniden_kurulunca_bagimlilar_gecersiz(ayri_cikti, oyuncak_db):
    once = _zamanlar(ayri_cikti)
    hazirla.main(["--cikti", str(ayri_cikti), "--db", str(oyuncak_db), "--adim", "gunluk"])
    sonra = _zamanlar(ayri_cikti)
    assert sonra["gunluk.parquet"] != once["gunluk.parquet"]
    for ad in DOSYALAR[1:]:
        assert sonra[ad] is None, ad                  # bağımlılar silindi
    sure = json.loads((ayri_cikti / "sure.json").read_text(encoding="utf-8"))
    assert set(sure["adimlar"]) == {"gunluk"}
    hazirla.main(["--cikti", str(ayri_cikti), "--db", str(oyuncak_db)])   # yeniden kurar
    son = _zamanlar(ayri_cikti)
    assert son["gunluk.parquet"] == sonra["gunluk.parquet"]
    assert all(son[ad] is not None for ad in DOSYALAR)


def test_silinen_gunluk_bagimlilari_yeniden_kosturur(ayri_cikti, oyuncak_db):
    once = _zamanlar(ayri_cikti)
    (ayri_cikti / "gunluk.parquet").unlink()
    hazirla.main(["--cikti", str(ayri_cikti), "--db", str(oyuncak_db)])
    sonra = _zamanlar(ayri_cikti)
    assert all(sonra[ad] is not None and sonra[ad] != once[ad] for ad in DOSYALAR)


def test_carpanlar_yalniz_basiti_gecersiz_kilar(ayri_cikti, oyuncak_db):
    once = _zamanlar(ayri_cikti)
    hazirla.main(["--cikti", str(ayri_cikti), "--db", str(oyuncak_db), "--adim", "carpanlar"])
    sonra = _zamanlar(ayri_cikti)
    assert sonra["carpanlar.pkl"] != once["carpanlar.pkl"]
    assert sonra["kayip_basit.parquet"] is None
    for ad in ("gunluk.parquet", "kayip_naif.parquet", "kayip_ml.parquet"):
        assert sonra[ad] == once[ad], ad
    (ayri_cikti / "carpanlar.pkl").unlink()
    with pytest.raises(FileNotFoundError, match="carpanlar"):   # basit'in girdisi yoksa açık hata
        hazirla.main(["--cikti", str(ayri_cikti), "--db", str(oyuncak_db), "--adim", "basit"])


def test_baska_db_hepsini_gecersiz_kilar(ayri_cikti, oyuncak_db, tmp_path):
    once = _zamanlar(ayri_cikti)
    kopya = tmp_path / "kopya.duckdb"
    shutil.copyfile(oyuncak_db, kopya)
    hazirla.main(["--cikti", str(ayri_cikti), "--db", str(kopya)])
    sonra = _zamanlar(ayri_cikti)
    assert all(sonra[ad] is not None and sonra[ad] != once[ad] for ad in DOSYALAR)
    iz = json.loads((ayri_cikti / "kaynak.json").read_text(encoding="utf-8"))
    assert iz["yol"] == str(kopya.resolve())


def test_var_olan_adim_atlanir_istenen_yeniden_kosar(cikti, oyuncak_db):
    def zaman(ad):
        return (cikti / ad).stat().st_mtime_ns

    once = {ad: zaman(ad) for ad in DOSYALAR}
    hazirla.main(["--cikti", str(cikti), "--db", str(oyuncak_db)])
    assert {ad: zaman(ad) for ad in DOSYALAR} == once
    hazirla.main(["--cikti", str(cikti), "--db", str(oyuncak_db), "--adim", "naif"])
    assert zaman("kayip_naif.parquet") != once["kayip_naif.parquet"]
    assert zaman("gunluk.parquet") == once["gunluk.parquet"]
    hazirla.main(["--cikti", str(cikti), "--db", str(oyuncak_db), "--yeniden"])
    assert all(zaman(ad) != once[ad] for ad in DOSYALAR)
