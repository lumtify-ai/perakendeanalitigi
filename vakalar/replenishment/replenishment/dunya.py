"""Vakanın sabit dünyası.

`dunya_kur()`, Task 1'in `perakende_veri.simulasyon.dunya_yeniden_kur()`
fonksiyonunu çağırarak simülasyonun gördüğü çeşidi ve beklenen talebi
yeniden kurar — simülasyonu koşmadan. Hücre sırası simülasyonun `cesit`
sırasıdır ve **yeniden sıralanmaz**: ileride bir eşdeğerlik testi v2'yi
gün gün bu sırayla yeniden oynatacaktır.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from perakende_veri import simulasyon, talep


@dataclass(frozen=True)
class Dunya:
    tarihler: np.ndarray        # datetime64[D], 2025-01-01..2025-12-31 (365)
    tatil: np.ndarray           # bool[365]
    hucre_magaza: np.ndarray    # str[H]  (H = SKU×mağaza hücre sayısı, çeşit sırası)
    hucre_urun: np.ndarray      # str[H]
    oc_hucre: np.ndarray        # int[OC, 5] — option-mağaza başına beden_sira 1..5 hücre indeksleri
    oc_magaza: np.ndarray       # str[OC]
    oc_option: np.ndarray       # str[OC]
    oc_line: np.ndarray         # str[OC]
    oc_kategori: np.ndarray     # str[OC]  (ust_kategori)
    oc_magaza_tipi: np.ndarray  # str[OC]
    optionlar: np.ndarray       # str[O], sıralı
    oc_opt: np.ndarray          # int[OC] → optionlar indeksi
    magazalar: np.ndarray       # str[M], sıralı
    oc_mag: np.ndarray          # int[OC] → magazalar indeksi
    kapasite: np.ndarray        # int[M]
    plan: dict                  # sezon → float[H] günlük plan talebi
    beklenen: dict               # sezon → float[H] günlük beklenen gerçek talep
    sezon: np.ndarray           # str[365]
    zincir_beden_payi: np.ndarray    # float[5]

    def gun(self, tarih: str) -> int:
        """"2025-09-01" → 243 (yıl başından gün sayısı, 0 tabanlı)."""
        hedef = np.datetime64(tarih, "D")
        return int((hedef - self.tarihler[0]) / np.timedelta64(1, "D"))


def dunya_kur() -> Dunya:
    magazalar_df, _urunler_df, takvim_df, d = simulasyon.dunya_yeniden_kur()
    cesit = d["cesit"]
    cesit_urun = d["cesit_urun"]
    cesit_magaza = d["cesit_magaza"]

    hucre_magaza = cesit["magaza_id"].to_numpy().astype(str)
    hucre_urun = cesit["urun_id"].to_numpy().astype(str)

    oc_df = pd.DataFrame(
        {
            "hucre_index": np.arange(len(cesit)),
            "magaza_id": hucre_magaza,
            "urun_id": hucre_urun,
            "option_id": cesit_urun["option_id"].to_numpy().astype(str),
            "beden_sira": cesit_urun["beden_sira"].to_numpy(),
            "line": cesit_urun["line"].to_numpy().astype(str),
            "ust_kategori": cesit_urun["ust_kategori"].to_numpy().astype(str),
            "magaza_tipi": cesit_magaza["tip"].to_numpy().astype(str),
        }
    )

    siralanmis = oc_df.sort_values(["magaza_id", "option_id", "beden_sira"], kind="mergesort")
    grup = siralanmis.groupby(["magaza_id", "option_id"], sort=True)

    beden_sayilari = grup.size().to_numpy()
    if not (beden_sayilari == 5).all():
        raise ValueError("Her (mağaza, option) tam olarak 5 bedenli olmalı")

    oc_hucre = np.stack(grup["hucre_index"].apply(lambda s: s.to_numpy()).to_numpy())
    ilk = grup.first()
    oc_magaza = ilk.index.get_level_values("magaza_id").to_numpy().astype(str)
    oc_option = ilk.index.get_level_values("option_id").to_numpy().astype(str)
    oc_line = ilk["line"].to_numpy().astype(str)
    oc_kategori = ilk["ust_kategori"].to_numpy().astype(str)
    oc_magaza_tipi = ilk["magaza_tipi"].to_numpy().astype(str)

    optionlar = np.unique(oc_option)
    oc_opt = np.searchsorted(optionlar, oc_option).astype(np.int64)

    magazalar = np.sort(magazalar_df["magaza_id"].to_numpy().astype(str))
    oc_mag = np.searchsorted(magazalar, oc_magaza).astype(np.int64)
    kapasite = (
        magazalar_df.set_index("magaza_id")["kapasite"].reindex(magazalar).to_numpy()
    )

    tarihler = takvim_df["tarih"].to_numpy().astype("datetime64[D]")
    tatil = takvim_df["tatil_mi"].to_numpy(dtype=bool)
    sezon = takvim_df["sezon"].to_numpy().astype(str)

    zincir_payi = talep.beden_dagilimi()
    zincir_beden_payi = np.array([zincir_payi[k] for k in range(1, 6)], dtype=float)

    return Dunya(
        tarihler=tarihler,
        tatil=tatil,
        hucre_magaza=hucre_magaza,
        hucre_urun=hucre_urun,
        oc_hucre=oc_hucre,
        oc_magaza=oc_magaza,
        oc_option=oc_option,
        oc_line=oc_line,
        oc_kategori=oc_kategori,
        oc_magaza_tipi=oc_magaza_tipi,
        optionlar=optionlar,
        oc_opt=oc_opt,
        magazalar=magazalar,
        oc_mag=oc_mag,
        kapasite=kapasite,
        plan=d["plan"],
        beklenen=d["gercek"],
        sezon=sezon,
        zincir_beden_payi=zincir_beden_payi,
    )
