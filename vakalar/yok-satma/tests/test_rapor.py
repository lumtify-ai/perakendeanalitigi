"""`rapor.py` testleri: oyuncak v4 dünyasında `hazirla` çıktıları + sahte hakem.

Oyuncak dünya ortak paketin fikstüründendir (`vakalar/ortak/tests/conftest.py`,
`test_hazirla.py` ile aynı kurulum). Sahte hakem, Basit kayıp tablosunun 2025
satırlarından ikisine, kayıp tablosunda olmayan bir uygun güne (stoklu) ve
uygun olmayan bir hücre-güne karşılanmayan talep yazar.
"""

import importlib.util
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

import rapor
from perakende_analitik import degerlendir
from yok_satma import hazirla

pytestmark = pytest.mark.filterwarnings("ignore:Mean of empty slice:RuntimeWarning")

_ORTAK_CONFTEST = Path(__file__).resolve().parents[2] / "ortak" / "tests" / "conftest.py"
BASLIKLAR = ["=== VERİ ===", "=== HİKÂYE ===", "=== ÇARPANLAR ===", "=== KESTİRİM ===",
             "=== AYRIŞIM ===", "=== LUMODA ===", "=== AĞAÇ ==="]


def _ortak_fikstur():
    spec = importlib.util.spec_from_file_location("ortak_conftest", _ORTAK_CONFTEST)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def oyuncak_db(tmp_path_factory) -> Path:
    yol = tmp_path_factory.mktemp("veri") / "perakende.duckdb"
    fikstur = _ortak_fikstur()
    tablolar = fikstur.oyuncak_tablolar()
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


@pytest.fixture(scope="module")
def sahte_hakem(cikti, tmp_path_factory) -> Path:
    dizin = tmp_path_factory.mktemp("hakem")
    k = pd.read_parquet(cikti / "kayip_basit.parquet")
    k = k[k["tarih"].dt.year == 2025].head(2)
    assert len(k) == 2
    g = pd.read_parquet(cikti / "gunluk.parquet", filters=[("durum", "in", ["stoklu"])])
    stoklu = g[g["tarih"].dt.year == 2025].head(1)
    satirlar = [(r.tarih, str(r.magaza_id), str(r.urun_id), 3, 0, 3, 1, 2)
                for r in k.itertuples()]
    satirlar += [(r.tarih, str(r.magaza_id), str(r.urun_id), 2, 1, 1, 0, 1)
                 for r in stoklu.itertuples()]
    satirlar.append((pd.Timestamp("2025-01-08"), "M002", "MDL0001-SYH-L", 1, 0, 1, 1, 0))
    kars = pd.DataFrame(satirlar, columns=["tarih", "magaza_id", "urun_id", "talep",
                                           "kendi_satis", "karsilanmayan", "ikameye_giden",
                                           "kalici_kayip"])
    kars.to_parquet(dizin / "karsilanmayan.parquet", index=False)
    pd.DataFrame({"tarih": pd.Series(dtype="datetime64[ns]"), "magaza_id": pd.Series(dtype=str),
                  "urun_id": pd.Series(dtype=str), "adet": pd.Series(dtype="int32")}
                 ).to_parquet(dizin / "ikame_alinan.parquet", index=False)
    (dizin / "meta.json").write_text(json.dumps({"tohum": 0}), encoding="utf-8")
    return dizin


@pytest.fixture(autouse=True)
def oyuncak_hikaye(monkeypatch):
    """Kullanıcının seçimi gerçek veridedir; oyuncakta varsayılan seçim oyuncak bir hücre-gün
    (M001 × MDL0001-SYH-M 2025-01-09'da bos, temel senaryo)."""
    monkeypatch.setattr(rapor, "HIKAYE_SECIMI", ("MDL0001-SYH", "M001", "2025-01-09"))


def _argv(cikti, db, hakem_dizini):
    return ["--cikti", str(cikti), "--db", str(db), "--hakem", str(hakem_dizini)]


def test_turkce_sayi_bicimi():
    assert rapor.s(1234567) == "1.234.567"
    assert rapor.s(0.555, 2) == "0,56"
    assert rapor.s(-3.2, 1) == "−3,2"
    assert rapor.y(0.1234) == "%12,3"
    assert rapor.yi(-0.032) == "−%3,2"
    assert rapor.yi(0.027) == "+%2,7"
    assert rapor.s(float("nan")) == "—"


def test_rapor_basliklari(cikti, oyuncak_db, sahte_hakem, capsys):
    assert rapor.main(_argv(cikti, oyuncak_db, sahte_hakem)) == 0
    metin = capsys.readouterr().out
    yerler = [metin.find(b) for b in BASLIKLAR]
    assert all(y >= 0 for y in yerler), dict(zip(BASLIKLAR, yerler))
    assert yerler == sorted(yerler)
    # sahte hakemin 2025 karşılanmayanı: 3 + 3 (kayıp tablosunda) + 1 (stoklu) + 1 (dışı)
    assert "hakemin 2025 karşılanmayanı: 8 adet" in metin
    assert "kayıp tablosundaki hücre-günlerde (yukarıdaki Σ karşılanmayan): 6 adet" in metin
    assert "bu veride yok" in metin
    assert "kullanıcının seçimi, kurgu kapısı (R25); sıkı arama: tutmayan ölçütler:" in metin
    assert "merkez depo, Ali MDL0001-SYH-M:" in metin and "operasyonel" in metin


def test_hikaye_arama(cikti, oyuncak_db, sahte_hakem, capsys):
    assert rapor.main(_argv(cikti, oyuncak_db, sahte_hakem) + ["--hikaye", "arama"]) == 0
    assert "hikâye adayı yok" in capsys.readouterr().out


def test_korunum_denetimi():
    rapor.korunum("esit", 10.0, 10.0 + 1e-12)
    with pytest.raises(rapor.KorunumHatasi, match="esit degil"):
        rapor.korunum("esit degil", 10.0, 9.0)


def test_korunum_bozulursa_rapor_durur(cikti, oyuncak_db, sahte_hakem, monkeypatch):
    asil = degerlendir.kirilimlar

    def bozuk(eslesik, con, tahmin="kayip"):
        df = asil(eslesik, con, tahmin)
        return df.iloc[1:].reset_index(drop=True) if len(df) > 1 else df.iloc[0:0]

    monkeypatch.setattr(degerlendir, "kirilimlar", bozuk)
    with pytest.raises(rapor.KorunumHatasi):
        rapor.main(_argv(cikti, oyuncak_db, sahte_hakem))


def test_eksik_cikti_komutu_soyler(cikti, oyuncak_db, sahte_hakem, tmp_path, capsys):
    bos = tmp_path / "bos"
    bos.mkdir()
    assert rapor.main(_argv(bos, oyuncak_db, sahte_hakem)) != 0
    assert "python -m yok_satma.hazirla" in capsys.readouterr().err
    assert rapor.main(_argv(cikti, oyuncak_db, tmp_path / "hakem_yok")) != 0
    assert "python -m perakende_analitik.hakem" in capsys.readouterr().err


def test_bulunma_eki():
    assert [rapor.bulunma(n) for n in (1, 2, 3, 6, 9, 10, 20, 24, 40, 60, 90, 100, 1000)] == [
        "1'inde", "2'sinde", "3'ünde", "6'sında", "9'unda", "10'unda", "20'sinde", "24'ünde",
        "40'ında", "60'ında", "90'ında", "100'ünde", "1.000'inde"]


def test_elle_hikaye(cikti, oyuncak_db, sahte_hakem, capsys):
    # M001 × MDL0001-SYH-M 2025-01-09'da bos (oyuncak dünyanın temel senaryosu)
    argv = _argv(cikti, oyuncak_db, sahte_hakem)
    assert rapor.main(argv + ["--hikaye", "MDL0001-SYH,M001,2025-01-09"]) == 0
    metin = capsys.readouterr().out
    assert "elle seçildi (--hikaye); sıkı arama: tutmayan ölçütler:" in metin
    assert "kayıp tablosu dışında kalan" in metin
    # o gün o mağazada bos bedeni yok: açık hata
    assert rapor.main(argv + ["--hikaye", "MDL0001-SYH,M002,2025-01-20"]) == 2
    assert "bos bedeni yok" in capsys.readouterr().err


def test_son_tukenis_hic_stoklanmamis_hucre_dahil():
    # A: son stoklu açılış 01-05 -> 01-04 operasyonel, 01-06 son; B: hiç stoklu açılmadı -> son (R26)
    df = pd.DataFrame({"tarih": pd.to_datetime(["2025-01-04", "2025-01-06", "2025-01-03"]),
                       "magaza_id": pd.Categorical(["M1", "M1", "M1"]),
                       "urun_id": pd.Categorical(["A", "A", "B"])})
    son = pd.DataFrame({"m": ["M1", "M1"], "u": ["A", "B"],
                        "son": pd.to_datetime(["2025-01-05", None])})
    son_mu, hic = rapor._son_tukenis_mi(df, son)
    assert son_mu.tolist() == [False, True, True] and hic.tolist() == [False, False, True]
