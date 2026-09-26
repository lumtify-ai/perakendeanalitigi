"""Alternatif talep yolları: aynı beklenen talep, farklı Poisson tohumu.

    .venv/Scripts/python -m rpt.yollar        # 10 yol, paralel; cikti/yollar.json

Her yol kendi "gerçekleşen tarihini" (Banu'nun kuralı + bugünkü dağıtım)
üretir ve bütün öğrenmeyi (eğri, belirsizlik, aday modeli, dağıtım kuralı
seçimi) o tarihten, yol 0'daki kurallarla yapar; sonra kolları koşar.
Raporun aralıkları buradan (min / medyan / max ve kaç yolda aynı yön).
"""

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

CIKTI = Path(__file__).resolve().parents[1] / "cikti" / "yollar.json"
YOL_SAYISI = 10
TOHUM_TABANI = 20260926
OLCUTLER = ["delta_kar", "kurtarilan_kayip", "kurtarilan_kayip_tl", "rpt", "rpt_option", "rpt_magazaya",
            "rpt_depoda_kalan", "yanlis_alarm", "kar", "magazaya", "rpt_ek_tf", "rpt_ek_ind"]


def yol_talebi(dunya, yol: int):
    from perakende_veri.v3.dunya import talep_matrisi

    if yol == 0:
        return talep_matrisi(dunya)
    return talep_matrisi(dunya, np.random.default_rng([TOHUM_TABANI, yol]))


def yol_kos(yol: int) -> dict:
    import warnings

    warnings.filterwarnings("ignore")
    from perakende_veri.v3.dunya import dunya_kur

    from . import oyun

    t0 = time.time()
    w = dunya_kur()
    H = oyun.hazirlik(w, yol_talebi(w, yol))
    K = oyun.tum_kollar(H, lambda e: [("mevcut", e), ("frr3", "mevcut"), ("frr3", e), ("oneri", e),
                                      ("kahin", e)])
    en_iyi = K["en_iyi"]
    sonuc = {"yol": yol, "en_iyi": en_iyi, "sure": 0.0, "sezon": {}}
    for sezon in H["baglam"].oyun_sezonlari:
        tab = oyun.ozet_tablosu(w, K["ham"], sezon, ("kahin", en_iyi))
        sonuc["sezon"][sezon] = {
            f"{r.kol}|{'en_iyi' if (r.kural == en_iyi and r.kol != 'rpt_yok') else r.kural}":
                {k: float(getattr(r, k)) for k in OLCUTLER}
            for r in tab.itertuples(index=False)
        }
    sonuc["sure"] = time.time() - t0
    return sonuc


def main(yollar=None, isci: int = 4) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    yollar = list(yollar or range(1, YOL_SAYISI + 1))
    CIKTI.parent.mkdir(exist_ok=True)
    mevcut = json.loads(CIKTI.read_text(encoding="utf-8")) if CIKTI.exists() else {}
    eksik = [y for y in yollar if str(y) not in mevcut]
    with ProcessPoolExecutor(isci) as ex:
        for s in ex.map(yol_kos, eksik):
            mevcut[str(s["yol"])] = s
            CIKTI.write_text(json.dumps(mevcut, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"yol {s['yol']}: {s['sure']:.0f} sn, en iyi kural {s['en_iyi']}", flush=True)


if __name__ == "__main__":
    main()
