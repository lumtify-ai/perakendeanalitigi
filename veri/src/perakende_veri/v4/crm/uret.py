"""v4 CRM (B) veri setini üretir: python -m perakende_veri.v4.crm.uret

    girdi_kur (A, sabitler.TOHUM ile bellekte) → crm_simule_et → online_uret
    → kargo_tablosu → yorumlar → crm_tablolari → cikti/v4_crm/

Çıktı (`CIKTI_DIZINI`): `parquet/` (altı tablo), `csv/` (`online_olay`
hariç), `lumoda-v4-crm.duckdb` (altı tablo; Parquet'ten okunur, tarih
sütunları DATE). Gizli gerçek (`crm_gizli_gercek`) yazılmaz; Görev 14 ve
vakalar `tablolari_uret_crm(donus_ham=True)` ile ham sonucu alıp çağırır.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

from .. import sabitler as a_sabitler
from ..magaza import Olcek
from ..tablolar import pencere
from .dongu import CrmHam, crm_simule_et
from .girdi import Girdi, girdi_kur
from .kargo import kargo_tablosu
from .online import OnlineCikti, online_uret
from .rastgele import crm_uretici
from .sabitler import CRM_TOHUM
from .tablolar import TABLOLAR, CrmHazir, crm_gizli_gercek, crm_tablolari, hazirla
from .yorum import YorumSonucu, aday_satirlari, kutuphane_yukle, yorumlari_ata

CIKTI_DIZINI = a_sabitler.CIKTI_DIZINI.parent / "v4_crm"
DUCKDB_ADI = "lumoda-v4-crm.duckdb"
YALNIZ_PARQUET = ("online_olay",)


@dataclass(eq=False)
class CrmUretim:
    """Bir B koşusunun bütün ara sonuçları (`tablolari_uret_crm(donus_ham=True)`)."""

    girdi: Girdi
    crm: CrmHam
    online: OnlineCikti
    yorum: YorumSonucu
    kargo: pd.DataFrame
    hazir: CrmHazir
    tohum: int
    sure: dict = field(default_factory=dict)

    @property
    def yorumlar(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        return self.yorum.yorum, self.yorum.gizli

    def gizli_gercek(self) -> dict:
        return crm_gizli_gercek(self.girdi, self.crm, self.online, self.yorumlar, hazir=self.hazir)


def uret_girdiden(girdi: Girdi, tohum: int = CRM_TOHUM, crm: CrmHam | None = None) -> tuple[dict, CrmUretim]:
    """Hazır A görünümünden B'nin bütün koşusu; `crm` verilirse (aynı tohumla
    koşulmuş `crm_simule_et`) simülasyon yeniden yapılmaz. (tablolar, ham)."""
    sure: dict = {}
    t = time.perf_counter()

    def olc(ad):
        nonlocal t
        simdi = time.perf_counter()
        sure[ad] = simdi - t
        t = simdi

    if crm is None:
        crm = crm_simule_et(girdi, tohum)
    else:
        assert crm.tohum == tohum, "crm_ham başka tohumla koşulmuş"
    olc("crm_simule_et")
    online = online_uret(girdi, crm, tohum)
    olc("online_uret")
    kargo = kargo_tablosu(crm, girdi)
    a = aday_satirlari(crm, girdi, kargo=kargo)
    son_gun = min(pencere()[1], crm.D - 1)
    yorum = yorumlari_ata(crm_uretici(crm.D, "yorum", tohum), a, girdi.dunya.urunler, kutuphane_yukle(),
                          son_gun)
    olc("kargo+yorum")
    hazir = hazirla(girdi, crm, kargo)
    tablolar = crm_tablolari(girdi, crm, online, (yorum.yorum, yorum.gizli), hazir=hazir)
    olc("tablolar")
    return tablolar, CrmUretim(girdi=girdi, crm=crm, online=online, yorum=yorum, kargo=kargo,
                               hazir=hazir, tohum=tohum, sure=sure)


def tablolari_uret_crm(olcek: Olcek = Olcek.TAM, tohum: int = CRM_TOHUM, donus_ham: bool = False,
                       girdi: Girdi | None = None):
    """A (`sabitler.TOHUM`) → B (`tohum`) → yayımlanan altı tablo. `girdi`
    verilirse A yeniden kurulmaz (`olcek` yok sayılır). `donus_ham` ise
    `(tablolar, CrmUretim)`; gizli gerçek `CrmUretim.gizli_gercek()`."""
    sure_a = 0.0
    if girdi is None:
        t = time.perf_counter()
        girdi = girdi_kur(olcek)
        sure_a = time.perf_counter() - t
    tablolar, ham = uret_girdiden(girdi, tohum)
    ham.sure = {"a_kurulum": sure_a, **ham.sure}
    if donus_ham:
        return tablolar, ham
    return tablolar


# ---------------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------------


def _tarih_sutunlari(df: pd.DataFrame) -> list[str]:
    """Saat bileşeni olmayan datetime sütunları (DuckDB'de DATE)."""
    out = []
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            s = df[c].dropna()
            if not len(s) or (s == s.dt.normalize()).all():
                out.append(c)
    return out


def yaz(tablolar: dict[str, pd.DataFrame], hedef: Path = CIKTI_DIZINI) -> dict[str, float]:
    """Parquet (hepsi), DuckDB (hepsi, Parquet'ten), CSV (`online_olay`
    hariç, DuckDB `COPY`). Adım süreleri (sn)."""
    hedef = Path(hedef)
    (hedef / "parquet").mkdir(parents=True, exist_ok=True)
    (hedef / "csv").mkdir(parents=True, exist_ok=True)
    sure = {}
    t = time.perf_counter()
    tarihler = {}
    for ad, df in tablolar.items():
        df.to_parquet(hedef / "parquet" / f"{ad}.parquet", index=False)
        tarihler[ad] = _tarih_sutunlari(df)
    sure["parquet"] = time.perf_counter() - t

    t = time.perf_counter()
    db = hedef / DUCKDB_ADI
    db.unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    try:
        for ad in tablolar:
            yol = (hedef / "parquet" / f"{ad}.parquet").as_posix()
            degis = ", ".join(f"CAST({c} AS DATE) AS {c}" for c in tarihler[ad])
            secim = f"* REPLACE ({degis})" if degis else "*"
            con.execute(f"CREATE TABLE {ad} AS SELECT {secim} FROM read_parquet('{yol}')")
        sure["duckdb"] = time.perf_counter() - t
        t = time.perf_counter()
        for ad in tablolar:
            if ad in YALNIZ_PARQUET:
                continue
            yol = (hedef / "csv" / f"{ad}.csv").as_posix()
            con.execute(f"COPY {ad} TO '{yol}' (HEADER, DELIMITER ',')")
        sure["csv"] = time.perf_counter() - t
    finally:
        con.close()
    return sure


def _boyut_mb(yol: Path) -> float:
    return yol.stat().st_size / 2**20 if yol.exists() else float("nan")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.perf_counter()
    girdi = girdi_kur(Olcek.TAM)
    t1 = time.perf_counter()
    tablolar, ham = uret_girdiden(girdi, CRM_TOHUM)
    sure = ham.sure
    del ham, girdi
    t2 = time.perf_counter()
    yazma = yaz(tablolar, CIKTI_DIZINI)
    t3 = time.perf_counter()

    print(f"{'tablo':22s} {'satır':>12s} {'parquet MB':>11s} {'csv MB':>9s}")
    for ad in TABLOLAR:
        pq = _boyut_mb(CIKTI_DIZINI / "parquet" / f"{ad}.parquet")
        cs = _boyut_mb(CIKTI_DIZINI / "csv" / f"{ad}.csv")
        print(f"{ad:22s} {len(tablolar[ad]):>12,} {pq:>11.1f} {cs:>9.1f}")
    print(f"duckdb {_boyut_mb(CIKTI_DIZINI / DUCKDB_ADI):.1f} MB")
    print(f"\nA kurulumu {t1 - t0:.1f} sn (B'ye sayılmaz)")
    for ad, v in sure.items():
        print(f"  {ad:16s} {v:7.1f} sn")
    for ad, v in yazma.items():
        print(f"  yazma {ad:10s} {v:7.1f} sn")
    print(f"B toplam (yazma dahil) {t3 - t1:.1f} sn = {(t3 - t1) / 60:.1f} dk; yazma hariç {t2 - t1:.1f} sn")
    print(f"Çıktı: {CIKTI_DIZINI}")


if __name__ == "__main__":
    main()
