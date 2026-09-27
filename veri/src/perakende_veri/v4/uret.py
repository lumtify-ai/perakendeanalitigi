"""v4 veri setini uçtan uca üretir: python -m perakende_veri.v4.uret

    dunya_kur(olcek) → simule_et (Lumoda) → hareket_tablolari (18 temiz
    tablo) → kirlet (`kirli` çocuk üreteci) → cikti/v4/ (CSV, Parquet,
    DuckDB; kök `disa_aktar.yaz`)

Gizli gerçek (`tablolar.gizli_gercek`) yazılmaz; vakalar `tablolari_uret(
donus_ham=True)` ile dünyayı ve ham çıktıyı alıp kendileri çağırır.
"""

import sys
import time

from ..disa_aktar import yaz
from . import sabitler
from .dunya import akislar, dunya_kur
from .kirlet import kirlet
from .magaza import Olcek
from .motor import simule_et
from .tablolar import hareket_tablolari


def yayimla(dunya, ham: dict, kirli: bool = True) -> dict:
    """Ham motor çıktısından yayımlanan 18 tablo (varsayılan: kirli)."""
    tablolar = hareket_tablolari(dunya, ham)
    if kirli:
        tablolar = kirlet(akislar(dunya.tohum)["kirli"], tablolar, dunya)
    return tablolar


def tablolari_uret(olcek: Olcek = Olcek.TAM, donus_ham: bool = False):
    """Dünya → motor → yayımlanan tablolar. `donus_ham` ise
    `(tablolar, dunya, ham)`."""
    dunya = dunya_kur(olcek)
    ham = simule_et(dunya)
    tablolar = yayimla(dunya, ham)
    if donus_ham:
        return tablolar, dunya, ham
    return tablolar


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.time()
    dunya = dunya_kur(Olcek.TAM)
    t1 = time.time()
    ham = simule_et(dunya)
    t2 = time.time()
    tablolar = yayimla(dunya, ham)
    del ham
    t3 = time.time()
    yaz(tablolar, sabitler.CIKTI_DIZINI)
    t4 = time.time()
    for ad, df in tablolar.items():
        print(f"{ad:15s} {len(df):>11,} satır")
    print(
        f"\nDünya {t1 - t0:.1f} sn, motor {t2 - t1:.1f} sn, tablolar {t3 - t2:.1f} sn, "
        f"yazma {t4 - t3:.1f} sn, toplam {t4 - t0:.1f} sn"
    )
    print(f"Çıktı: {sabitler.CIKTI_DIZINI}")


if __name__ == "__main__":
    main()
