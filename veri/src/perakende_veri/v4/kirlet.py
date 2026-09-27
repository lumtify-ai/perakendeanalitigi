"""Dört kirli kayıt türü (spec §6.4): v3'ün üçü, üç yıla ve ~80 mağazaya
ölçekli, artı tek taraflı transfer.

    mükerrer satış      MUKERRER_KAYIT gerçek (adet > 0) satış satırı iki kez
    bedelsiz satış      BEDELSIZ_KAYIT satış satırında tutar = indirim = 0
    hayalet stok        HAYALET_STOK_KAYDI stok satırı: mağazanın hiçbir
                        zaman taşımadığı SKU, pencere pazartesisi, adet 1–3,
                        stoklu_gun 7 (sistem stoğu gördüğü için dolu görünür)
    tek taraflı transfer  TEK_TARAFLI_TRANSFER `elle_transfer` satırında
                        varis_tarihi boş (çıkış var, varış yok)

Üreteç dünya akış tablosunun `kirli` çocuğudur (`dunya.akislar()["kirli"]`,
bkz. dunya.py); çekiliş sırası yukarıdaki sıradır. Yalnız `satis`, `stok`,
`sevkiyat` değişir; kategori tipleri korunur (kirli satırlar aynı
kategori kümesinden gelir).
"""

import numpy as np
import pandas as pd

from . import sabitler


def kirlet(rng: np.random.Generator, tablolar: dict, dunya) -> dict:
    """Kirletilmiş yeni sözlük döndürür (girdi değişmez)."""
    t = dict(tablolar)
    satis, stok, sevkiyat = t["satis"], t["stok"], t["sevkiyat"]

    # 1) Mükerrer satış: aynı satır ikinci kez (sıralamada hemen yanında).
    gercek = np.flatnonzero(satis["adet"].to_numpy() > 0)
    secim = np.sort(rng.choice(gercek, size=sabitler.MUKERRER_KAYIT, replace=False))
    satis = pd.concat([satis, satis.iloc[secim]], ignore_index=True)

    # 2) Bedelsiz satış: gerçek satış satırında tutar ve indirim 0.
    gercek = np.flatnonzero(satis["adet"].to_numpy() > 0)
    bedelsiz = np.sort(rng.choice(gercek, size=sabitler.BEDELSIZ_KAYIT, replace=False))
    satis = satis.copy()
    satis.loc[bedelsiz, ["tutar", "indirim_tutari"]] = 0.0
    satis = satis.sort_values(["tarih", "magaza_id", "urun_id"], kind="stable").reset_index(drop=True)

    # 3) Hayalet stok: fiziksel mağaza × hiç taşımadığı SKU (red örneklemesi).
    M = len(dunya.magazalar)
    S = len(dunya.urunler)
    fiziksel = np.flatnonzero((dunya.magazalar["tip"] != "Online").to_numpy())
    tasinan = set((np.asarray(dunya.hucre_magaza, dtype=np.int64) * S
                   + np.asarray(dunya.hucre_sku, dtype=np.int64)).tolist())
    pazartesiler = np.sort(stok["tarih"].unique())
    secilen: list[tuple[int, int]] = []
    goruldu: set[int] = set()
    while len(secilen) < sabitler.HAYALET_STOK_KAYDI:
        m = int(fiziksel[rng.integers(len(fiziksel))])
        s = int(rng.integers(S))
        anahtar = m * S + s
        if anahtar in tasinan or anahtar in goruldu:
            continue
        goruldu.add(anahtar)
        secilen.append((m, s))
    n = len(secilen)
    tarih = pazartesiler[rng.integers(len(pazartesiler), size=n)]
    adet = rng.integers(1, 4, size=n)
    m_idx = np.array([m for m, _ in secilen])
    s_idx = np.array([s for _, s in secilen])
    mag_id = dunya.magazalar["magaza_id"].to_numpy().astype(str)[m_idx]
    urun_id = dunya.urunler["urun_id"].to_numpy().astype(str)[s_idx]
    hayalet = pd.DataFrame(
        {
            "tarih": tarih,
            "magaza_id": pd.Categorical(mag_id, categories=stok["magaza_id"].cat.categories),
            "urun_id": pd.Categorical(urun_id, categories=stok["urun_id"].cat.categories),
            "adet": adet.astype(stok["adet"].dtype),
            "stoklu_gun": np.full(n, 7, dtype=stok["stoklu_gun"].dtype),
        }
    )
    assert M > 0 and hayalet["magaza_id"].notna().all() and hayalet["urun_id"].notna().all()
    stok = pd.concat([stok, hayalet], ignore_index=True)
    stok = stok.sort_values(["tarih", "magaza_id", "urun_id"], kind="stable").reset_index(drop=True)

    # 4) Tek taraflı transfer: elle_transfer satırında varış kaydı yok.
    aday = np.flatnonzero(
        ((sevkiyat["tip"] == "elle_transfer") & sevkiyat["varis_tarihi"].notna()).to_numpy()
    )
    tek = np.sort(rng.choice(aday, size=sabitler.TEK_TARAFLI_TRANSFER, replace=False))
    sevkiyat = sevkiyat.copy()
    sevkiyat.loc[tek, "varis_tarihi"] = pd.NaT

    t.update({"satis": satis, "stok": stok, "sevkiyat": sevkiyat})
    return t
