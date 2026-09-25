"""v3 veri setini uçtan uca üretir: python -m perakende_veri.v3.uret"""

import sys
import time

import numpy as np
import pandas as pd

from ..disa_aktar import yaz
from . import sabitler
from .dunya import Dunya, akislar, dunya_kur, talep_matrisi
from .simulasyon import simule_et
from .takvim import gun_indisi, takvim_uret

SIRALAMA = ["tarih", "magaza_id", "urun_id"]
_TIP_SIRASI = {"ilk": 0, "surekli": 1, "rpt": 2}


def _pencere() -> tuple[int, int]:
    return gun_indisi(sabitler.BASLANGIC), gun_indisi(sabitler.BITIS)


def hucre_tablosu(dunya: Dunya, ham: pd.DataFrame, pencere=True) -> pd.DataFrame:
    """Ham (gun, hucre) tablosunu (tarih, magaza_id, urun_id) tablosuna çevirir."""
    bas, son = _pencere()
    if pencere:
        ham = ham[(ham["gun"] >= bas) & (ham["gun"] <= son)]
    tarihler = dunya.takvim["tarih"].to_numpy()
    magaza = dunya.cesit["magaza_id"].to_numpy()
    urun = dunya.cesit["urun_id"].to_numpy()
    h = ham["hucre"].to_numpy()
    df = pd.DataFrame(
        {"tarih": tarihler[ham["gun"].to_numpy()], "magaza_id": magaza[h], "urun_id": urun[h]}
    )
    for kolon in ham.columns.drop(["gun", "hucre"]):
        df[kolon] = ham[kolon].to_numpy()
    return df


def siparis_tablosu(dunya: Dunya, siparisler: list[dict], urun_filtre=None) -> pd.DataFrame:
    """SKU düzeyinde `siparis`. Kimlik, sipariş tarihine göre sıralı atanır.

    Pencereden sonra gerçekleşecek teslimlerin `gerceklesen_teslim`i boştur:
    veri 2025-12-31'de kesilir, zincir henüz gelmemiş malın ne zaman
    geleceğini bilmez (planlananı bilir).
    """
    _, son = _pencere()
    opt = dunya.optionlar
    urun_id = dunya.urunler["urun_id"].to_numpy()
    sirali = sorted(
        siparisler,
        key=lambda s: (s["siparis_gun"], _TIP_SIRASI[s["tip"]], opt.at[s["option"], "option_id"]),
    )
    satirlar = []
    for no, s in enumerate(sirali, start=1):
        for sku, adet in zip(s["skular"], s["adetler"]):
            if adet <= 0:
                continue
            satirlar.append(
                {
                    "siparis_id": f"SP{no:05d}",
                    "tip": s["tip"],
                    "option_id": opt.at[s["option"], "option_id"],
                    "urun_id": urun_id[sku],
                    "tedarikci_id": opt.at[s["option"], "tedarikci_id"],
                    "siparis_tarihi": int(s["siparis_gun"]),
                    "planlanan_teslim": int(s["planlanan_gun"]),
                    "gerceklesen_teslim": int(s["gerceklesen_gun"]),
                    "adet": int(adet),
                }
            )
    df = pd.DataFrame(satirlar)
    baslangic = np.datetime64(sabitler.ISINMA_BASLANGIC, "D")
    for kolon in ("siparis_tarihi", "planlanan_teslim", "gerceklesen_teslim"):
        gun = df[kolon].to_numpy()
        tarih = (baslangic + gun.astype("timedelta64[D]")).astype("datetime64[ns]")
        if kolon == "gerceklesen_teslim":
            tarih = np.where(gun <= son, tarih, np.datetime64("NaT", "ns"))
        df[kolon] = tarih
    if urun_filtre is not None:
        df = df[df["option_id"].isin(urun_filtre)]
    return df.reset_index(drop=True)


def _kirlet(rng, satis, stok, dunya):
    """Kirli kayıtlar (v2 ile aynı üç tür, iki yıla ölçekli)."""
    gercek = satis.index[satis["adet"] > 0].to_numpy()
    mukerrer = satis.loc[rng.choice(gercek, size=sabitler.MUKERRER_KAYIT, replace=False)]
    satis = pd.concat([satis, mukerrer], ignore_index=True)

    bedelsiz = rng.choice(
        satis.index[satis["adet"] > 0].to_numpy(), size=sabitler.BEDELSIZ_KAYIT, replace=False
    )
    satis.loc[bedelsiz, ["tutar", "indirim_tutari"]] = 0.0

    # Hayalet stok: mağazanın hiçbir sezonda taşımadığı üründe stok. Sistem
    # stoğu gördüğü için stoklu_gun de dolu görünür (7).
    cesit = set(zip(dunya.cesit["magaza_id"], dunya.cesit["urun_id"]))
    magazalar = dunya.magazalar["magaza_id"].to_numpy()
    urunler = dunya.urunler["urun_id"].to_numpy()
    pazartesiler = stok["tarih"].unique()
    hayalet = []
    while len(hayalet) < sabitler.HAYALET_STOK_KAYDI:
        magaza = str(rng.choice(magazalar))
        urun = str(rng.choice(urunler))
        if (magaza, urun) in cesit:
            continue
        hayalet.append(
            {"tarih": pazartesiler[rng.integers(len(pazartesiler))], "magaza_id": magaza,
             "urun_id": urun, "adet": int(rng.integers(1, 4)), "stoklu_gun": 7}
        )
    stok = pd.concat([stok, pd.DataFrame(hayalet)], ignore_index=True)
    return satis, stok


def hareket_tablolari(dunya: Dunya, ham: dict) -> dict[str, pd.DataFrame]:
    """Motorun ham çıktısından pencereli, kimlikli, temiz hareket tabloları."""
    bas, son = _pencere()
    satis = hucre_tablosu(dunya, ham["satis"])
    kayip = hucre_tablosu(dunya, ham["kayip_satis"])
    sevkiyat = hucre_tablosu(dunya, ham["sevkiyat"])
    stok = hucre_tablosu(dunya, ham["stok"])

    d = ham["depo_stok"]
    d = d[(d["gun"] >= bas) & (d["gun"] <= son)]
    depo_stok = pd.DataFrame(
        {
            "tarih": dunya.takvim["tarih"].to_numpy()[d["gun"].to_numpy()],
            "urun_id": dunya.urunler["urun_id"].to_numpy()[d["sku"].to_numpy()],
            "adet": d["adet"].to_numpy(),
        }
    )
    satan_optionlar = set(
        dunya.urunler.set_index("urun_id").loc[satis["urun_id"].unique(), "option_id"]
    )
    siparis = siparis_tablosu(dunya, ham["siparis"], satan_optionlar)
    return {"siparis": siparis, "satis": satis, "stok": stok, "depo_stok": depo_stok,
            "sevkiyat": sevkiyat, "kayip_satis": kayip}


def tablolari_uret(donus_ham: bool = False):
    """On bir tabloyu tek tohumun dört akışından üretir."""
    rng = akislar()
    dunya = dunya_kur(rng["dunya"])
    talep = talep_matrisi(dunya, rng["talep"])
    ham = simule_et(dunya, talep, rng_operasyon=rng["operasyon"])
    h = hareket_tablolari(dunya, ham)
    satis, stok = _kirlet(rng["kirli"], h["satis"], h["stok"], dunya)

    urun = dunya.urunler.copy()
    tablolar = {
        "magaza": dunya.magazalar,
        "urun": urun,
        "takvim": takvim_uret(),
        "sezon": dunya.sezon,
        "tedarikci": dunya.tedarikciler,
        "siparis": h["siparis"],
        "satis": satis.sort_values(SIRALAMA, kind="stable").reset_index(drop=True),
        "stok": stok.sort_values(SIRALAMA, kind="stable").reset_index(drop=True),
        "depo_stok": h["depo_stok"].sort_values(["tarih", "urun_id"], kind="stable").reset_index(drop=True),
        "sevkiyat": h["sevkiyat"].sort_values(SIRALAMA, kind="stable").reset_index(drop=True),
        "kayip_satis": h["kayip_satis"].sort_values(SIRALAMA, kind="stable").reset_index(drop=True),
    }
    if donus_ham:
        return tablolar, dunya, talep, ham
    return tablolar


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.time()
    tablolar = tablolari_uret()
    t1 = time.time()
    yaz(tablolar, sabitler.CIKTI_DIZINI)
    for ad, df in tablolar.items():
        print(f"{ad:12s} {len(df):>10,} satır")
    print(f"\nÜretim {t1 - t0:.1f} sn, yazma {time.time() - t1:.1f} sn")
    print(f"Çıktı: {sabitler.CIKTI_DIZINI}")


if __name__ == "__main__":
    main()
