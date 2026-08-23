import duckdb
import pandas as pd
from perakende_veri.disa_aktar import yaz


def _ornek():
    return {
        "magaza": pd.DataFrame(
            {"magaza_id": ["M001", "M002"], "sehir": ["İzmir", "Bursa"]}
        )
    }


def test_uc_format_da_yazilir(tmp_path):
    yaz(_ornek(), tmp_path)
    assert (tmp_path / "csv" / "magaza.csv").exists()
    assert (tmp_path / "parquet" / "magaza.parquet").exists()
    assert (tmp_path / "perakende.duckdb").exists()


def test_duckdb_sorgulanabilir(tmp_path):
    yaz(_ornek(), tmp_path)
    con = duckdb.connect(str(tmp_path / "perakende.duckdb"), read_only=True)
    assert con.sql("SELECT count(*) FROM magaza").fetchone()[0] == 2
    con.close()


def test_csv_turkce_karakterleri_korur(tmp_path):
    yaz(_ornek(), tmp_path)
    icerik = (tmp_path / "csv" / "magaza.csv").read_text(encoding="utf-8")
    assert "İzmir" in icerik


def test_ustuste_yazilabilir(tmp_path):
    # Üretim iki kez koşarsa ikincisi hata vermemeli
    yaz(_ornek(), tmp_path)
    yaz(_ornek(), tmp_path)
    con = duckdb.connect(str(tmp_path / "perakende.duckdb"), read_only=True)
    assert con.sql("SELECT count(*) FROM magaza").fetchone()[0] == 2
    con.close()
