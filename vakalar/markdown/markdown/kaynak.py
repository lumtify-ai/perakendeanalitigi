"""Yayımlanan v4 verisinden okuma, test option'ları ve karar penceresi.

Kural: bu modül gizli gerçeğe (`perakende_veri`, gizli tablolar) ve ölçüm tarafına (hakem,
simülasyon, ölçütler, `allocation.motor`) dokunmaz (AST kilidi, `tests/test_sizinti.py`). Veri
`veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`) üstünden ortak paketin bağlantısıyla
okunur.

**Gün ekseni.** Dünyanın gün indisi 0 = 2022-07-04 (ısınma başı; pazartesi), `sabitler.GUN_SIFIRI`.
Yayımlanan tablolar yalnız 2023-01-01'den başlar ama `optionlar`'ın `lansman_gun` / `indirim_gun` /
`cikis_gun` sütunları bu eksendedir. Gün 0 pazartesi olduğundan gün `d` pazartesidir <=> `d % 7 == 0`
(kod, haftanın gününü `GUN_SIFIRI`'ndan türetir; sabit 7'ye güvenmez).

**`bitis` kesimi.** Karar modülü ve öğrenme, test sezonunun en erken karar gününden önceki satırları
görür (spec §3.1). `yayimlanan_tablolar(..., bitis)` gözlenen olay tablolarını (`DONEM_SUTUNLARI`)
`bitis` gününden önce keser; kampanya, sezon, takvim, magaza, urun, paket gibi ileriye dönük açık
bilgi tablolarına dokunmaz. Bitişten önce verilmiş ama sonra teslim edilen siparişin
`gerceklesen_teslim`i karar anında bilinemez: boşaltılır (`planlanan_teslim` açık plandır, kalır).
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np
import pandas as pd
from perakende_analitik import kaynak as ortak

from markdown import sabitler

VERITABANI = ortak.VARSAYILAN_YOL

_AD = re.compile(r"^[a-z_]+$")
GIZLI_TABLO_ONEKI = "gizli_"       # gizli gerçeğin tabloları (yalnız hakem okur); kara liste

# Gözlenen olay tabloları -> kesimin uygulandığı tarih sütunu
DONEM_SUTUNLARI = {
    "satis": "tarih",
    "stok": "tarih",
    "depo_stok": "tarih",
    "sevkiyat": "tarih",
    "fiyat": "hafta_baslangic",
    "siparis": "siparis_tarihi",
    "kalite_kontrol": "teslim_tarihi",
}

KOL_TIPLERI = ("serbest", "takvim")


def baglan(yol: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """v4 DuckDB dosyasına salt okunur bağlanır (ortak `kaynak.baglan`)."""
    return ortak.baglan(yol)


def yayimlanan_tablolar(con, adlar: Sequence[str],
                        bitis: pd.Timestamp | str | None = None) -> dict[str, pd.DataFrame]:
    """`adlar` tablolarını DataFrame olarak okur (ad -> tablo, `adlar` sırasıyla).

    `gizli_` önekli tablo adı reddedilir (savunma katmanı; yayımlanan veride zaten yoktur). `bitis`
    verilirse `DONEM_SUTUNLARI`'ndaki tablolar o günden önceki satırlara kesilir (bitiş günü
    dahil değil); `siparis`'te bitişte henüz gerçekleşmemiş teslim tarihi boşaltılır. Büyük
    tablolarda kimlikler `category` gelir (DuckDB ENUM)."""
    for ad in adlar:
        if not _AD.match(ad):
            raise ValueError(f"geçersiz tablo adı: {ad!r}")
        if ad.startswith(GIZLI_TABLO_ONEKI):
            raise ValueError(f"gizli tablo okunamaz: {ad!r}")
    sonuc = {}
    for ad in adlar:
        if bitis is None or ad not in DONEM_SUTUNLARI:
            sonuc[ad] = con.execute(f"select * from {ad}").df()
            continue
        b = pd.Timestamp(bitis)
        sutun = DONEM_SUTUNLARI[ad]
        secim = "*"
        parametre = [b]
        if ad == "siparis":
            secim = ("* replace (case when gerceklesen_teslim < ? then gerceklesen_teslim end "
                     "as gerceklesen_teslim)")
            parametre = [b, b]
        sonuc[ad] = con.execute(f"select {secim} from {ad} where {sutun} < ?", parametre).df()
    return sonuc


# ---------------------------------------------------------------------------
# Test option'ları ve karar penceresi
# ---------------------------------------------------------------------------


def test_optionlari(optionlar: pd.DataFrame, sezonlar: Sequence[str] | str) -> np.ndarray:
    """`sezonlar`daki sezonların Collection option'ları: `optionlar`ın satır konumları (dünyada
    option indisi), artan sırayla. `optionlar` dünyanın `optionlar` biçimindedir (`option_id`,
    `sezon_kodu`, `line`, `lansman_gun`, `indirim_gun`, `cikis_gun`, `sezonluk`, ...)."""
    if isinstance(sezonlar, str):
        sezonlar = (sezonlar,)
    m = (optionlar["line"].astype(str) == sabitler.LINE) \
        & optionlar["sezon_kodu"].astype(str).isin(list(sezonlar))
    return np.flatnonzero(m.to_numpy())


def _pazartesiye_ileri(gun: np.ndarray) -> np.ndarray:
    """Günü ilk pazartesiye (kendisi dahil) ileri yuvarlar; haftanın günü `GUN_SIFIRI`'ndan."""
    haftanin_gunu_0 = pd.Timestamp(sabitler.GUN_SIFIRI).weekday()      # Pazartesi = 0
    return gun + (7 - (gun + haftanin_gunu_0) % 7) % 7


def karar_penceresi(optionlar: pd.DataFrame, idx: np.ndarray,
                    kol_tipi: Literal["serbest", "takvim"]) -> np.ndarray:
    """`idx` option'larının ilk indirim yapabileceği en erken gün (dünya gün indisi), `idx` sırasıyla.

    `serbest`: `max(indirim_gun - ERKEN_GUN, lansman_gun + RPT_SON_GUN)`, sonra **pazartesisi**:
    hesaplanan günden itibaren ilk pazartesi (hesaplanan gün pazartesiyse kendisi). İkinci terim
    option'ın kendi RPT penceresinin son günüdür (spec §0/7). Karar günleri pazartesi olduğundan
    pencere pazartesiye yuvarlanır; geriye değil ileri (daha erken karar vermeyiz).
    `takvim`: `indirim_gun` (yuvarlama yok; motor sezon indiriminde o günü de çağırır)."""
    if kol_tipi not in KOL_TIPLERI:
        raise ValueError(f"kol tipi {KOL_TIPLERI}'den biri olmalı: {kol_tipi!r}")
    idx = np.asarray(idx, dtype=np.int64)
    if idx.size and not optionlar["sezonluk"].to_numpy(dtype=bool)[idx].all():
        raise ValueError("karar penceresi yalnız sezonluk option'larda tanımlı")
    indirim = optionlar["indirim_gun"].to_numpy(dtype=np.int64)[idx]
    if kol_tipi == "takvim":
        return indirim
    lansman = optionlar["lansman_gun"].to_numpy(dtype=np.int64)[idx]
    return _pazartesiye_ileri(np.maximum(indirim - sabitler.ERKEN_GUN, lansman + sabitler.RPT_SON_GUN))
