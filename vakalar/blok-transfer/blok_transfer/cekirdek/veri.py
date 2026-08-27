from datetime import date
from pathlib import Path

import duckdb

# vakalar/blok-transfer/blok_transfer/cekirdek/veri.py → depo kökü 4 üst
VARSAYILAN_YOL = Path(__file__).resolve().parents[4] / "veri" / "cikti" / "v2" / "perakende.duckdb"


def baglan(yol: Path | None = None) -> duckdb.DuckDBPyConnection:
    hedef = Path(yol) if yol is not None else VARSAYILAN_YOL
    if not hedef.exists():
        raise FileNotFoundError(
            f"Veri dosyası yok: {hedef}. Önce üretin: "
            "cd veri && .venv/Scripts/python -m perakende_veri.uret"
        )
    return duckdb.connect(str(hedef), read_only=True)


def karar_tarihi(con: duckdb.DuckDBPyConnection) -> date:
    (t,) = con.execute("select max(tarih) from stok").fetchone()
    return t.date() if hasattr(t, "date") else t
