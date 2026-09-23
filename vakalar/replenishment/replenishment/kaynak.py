"""v2 DuckDB'sinden dünyanın hücre sırasına pivotlanmış diziler.

Her fonksiyon `dunya.hucre_magaza` / `dunya.hucre_urun` sırasını hücre
ekseni olarak kullanır: satırlar günü, sütunlar hücreyi taşır. Eşleme
`(magaza_id, urun_id) → hücre indeksi` sözlüğü yerine vektörize bir
pandas/numpy `map` ile yapılır — 365 × H (H ≈ 12k) boyutundaki matrisler
Python satır döngüsüyle kurulmaz.
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import sabitler
from .dunya import Dunya


def baglan(yol: Path | None = None) -> duckdb.DuckDBPyConnection:
    hedef = Path(yol) if yol is not None else sabitler.V2_DB
    if not hedef.exists():
        raise FileNotFoundError(
            f"Veri dosyası yok: {hedef}. Önce üretin: "
            "cd veri && .venv/Scripts/python -m perakende_veri.uret"
        )
    return duckdb.connect(str(hedef), read_only=True)


def _hucre_anahtari(dunya: Dunya) -> pd.Series:
    """(mağaza|ürün) anahtarından hücre indeksine eşleme."""
    anahtar = pd.Index(dunya.hucre_magaza) + "|" + pd.Index(dunya.hucre_urun)
    return pd.Series(np.arange(len(dunya.hucre_magaza)), index=anahtar)


def _pivot(df: pd.DataFrame, deger_kolonu: str, dunya: Dunya) -> np.ndarray:
    """`(tarih, magaza_id, urun_id, deger_kolonu)` tablosunu (gün, hücre)'ye pivotlar.

    Dünyanın çeşidi dışında kalan (hayalet) satırlar sessizce atılır.
    Aynı (gün, hücre) için birden çok satır varsa toplanır.
    """
    H = len(dunya.hucre_magaza)
    hucre_anahtari = _hucre_anahtari(dunya)

    anahtar = df["magaza_id"].astype(str) + "|" + df["urun_id"].astype(str)
    hucre = anahtar.map(hucre_anahtari)
    gecerli = hucre.notna()

    hucre_idx = hucre[gecerli].to_numpy(dtype=np.int64)
    gun_idx = (
        (pd.to_datetime(df.loc[gecerli, "tarih"]).to_numpy().astype("datetime64[D]")
         - dunya.tarihler[0])
        / np.timedelta64(1, "D")
    ).astype(np.int64)
    deger = df.loc[gecerli, deger_kolonu].to_numpy(dtype=np.int64)

    mat = np.zeros((365, H), dtype=np.int32)
    np.add.at(mat, (gun_idx, hucre_idx), deger)
    return mat


def gozlenen_satis(con: duckdb.DuckDBPyConnection, dunya: Dunya) -> np.ndarray:
    """int32[365, H]; mükerrer ayıklanmış POZİTİF satış."""
    df = con.execute(
        "select tarih, magaza_id, urun_id, adet from satis where adet > 0"
    ).fetchdf()
    df = df.drop_duplicates(subset=["tarih", "magaza_id", "urun_id"], keep="first")
    return _pivot(df, "adet", dunya)


def iade(con: duckdb.DuckDBPyConnection, dunya: Dunya) -> np.ndarray:
    """int32[365, H]; negatif satırların mutlak değeri."""
    df = con.execute(
        "select tarih, magaza_id, urun_id, -adet as adet from satis where adet < 0"
    ).fetchdf()
    return _pivot(df, "adet", dunya)


def kayip(con: duckdb.DuckDBPyConnection, dunya: Dunya) -> np.ndarray:
    """int32[365, H]."""
    df = con.execute(
        "select tarih, magaza_id, urun_id, kayip_adet from kayip_satis"
    ).fetchdf()
    return _pivot(df, "kayip_adet", dunya)


def kahin_talep(con: duckdb.DuckDBPyConnection, dunya: Dunya) -> np.ndarray:
    """gozlenen_satis + kayip (yol 0)."""
    return gozlenen_satis(con, dunya) + kayip(con, dunya)


def stok_fotografi(con: duckdb.DuckDBPyConnection, dunya: Dunya, tarih: str) -> np.ndarray:
    """int64[H]; çeşit dışı (hayalet) satırlar atılır."""
    df = con.execute(
        "select magaza_id, urun_id, adet from stok where tarih = ?", [tarih]
    ).fetchdf()

    H = len(dunya.hucre_magaza)
    hucre_anahtari = _hucre_anahtari(dunya)
    anahtar = df["magaza_id"].astype(str) + "|" + df["urun_id"].astype(str)
    hucre = anahtar.map(hucre_anahtari)
    gecerli = hucre.notna()

    sonuc = np.zeros(H, dtype=np.int64)
    sonuc[hucre[gecerli].to_numpy(dtype=np.int64)] = df.loc[gecerli, "adet"].to_numpy(
        dtype=np.int64
    )
    return sonuc


def sevkiyat(con: duckdb.DuckDBPyConnection, dunya: Dunya) -> np.ndarray:
    """int32[365, H]."""
    df = con.execute(
        "select tarih, magaza_id, urun_id, adet from sevkiyat"
    ).fetchdf()
    return _pivot(df, "adet", dunya)


def haftalik_sevkiyat_ortalamasi(
    con: duckdb.DuckDBPyConnection, bas: str, bit: str, hafta: int
) -> float:
    (toplam,) = con.execute(
        "select coalesce(sum(adet), 0) from sevkiyat where tarih between ? and ?",
        [bas, bit],
    ).fetchone()
    return float(toplam) / hafta
