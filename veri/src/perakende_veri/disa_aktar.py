"""Tabloları üç formatta yayına hazırlar.

Üç format üç okuyucu içindir: CSV herkes için, Parquet ciddi kullanıcı
için, tek dosya DuckDB ise indiren kişinin hiçbir kurulum yapmadan
saniyeler içinde SQL çalıştırabilmesi için.
"""

from pathlib import Path

import duckdb
import pandas as pd


def yaz(tablolar: dict[str, pd.DataFrame], hedef: Path) -> None:
    """Tabloları CSV, Parquet ve tek dosya DuckDB olarak yazar."""
    hedef = Path(hedef)
    (hedef / "csv").mkdir(parents=True, exist_ok=True)
    (hedef / "parquet").mkdir(parents=True, exist_ok=True)

    for ad, df in tablolar.items():
        df.to_csv(hedef / "csv" / f"{ad}.csv", index=False, encoding="utf-8")
        df.to_parquet(hedef / "parquet" / f"{ad}.parquet", index=False)

    db_yolu = hedef / "perakende.duckdb"
    db_yolu.unlink(missing_ok=True)

    con = duckdb.connect(str(db_yolu))
    try:
        for ad, df in tablolar.items():
            con.register("gecici", df)
            con.execute(f"CREATE TABLE {ad} AS SELECT * FROM gecici")
            con.unregister("gecici")
    finally:
        con.close()
