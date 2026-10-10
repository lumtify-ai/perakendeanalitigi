"""Alternatif talep yolları: aynı dünya, farklı müşteri akışı (spec §4.5).

    .venv/Scripts/python -m rpt.yollar        # 5 yol, sıralı; cikti/yollar.json

Yol p'nin talep tohumu `oyun.talep_tohumu(p, taban)` (yol 0 yayımlanan dünya;
p > 0 `taban + p`); dünya ve operasyon çekilişleri bütün yollarda aynıdır. Her yol
kendi gerçekleşen tarihini (Lumoda'nın politikaları) üretir ve bütün öğrenmeyi
(eğri, belirsizlik, p_ind, aday modeli, karar anı çarpanları) o tarihten, yol
0'daki kodla yeniden yapar (`oyun.hazirlik`); sonra beş kolu koşar
(`oyun.yol_listesi`: rpt_yok, mevcut, frr3, oneri, kahin; mevcut ayrıca bugünkü
dağıtımla). Dağıtım kuralı yol 0'ın SS24 seçimidir (`cikti/oyun.json`; yol
başına yeniden seçilmez: seçim oyundan önceki bir karardır, spec §3.6 ızgarası).
Yol 0'ın koşuları ana ızgaranınkilerle aynı anahtardadır (önbellekten).

Çıktı: yol × sezon × (kol|kural) → ölçüt (`oyun.OLCUT_ALANLARI`) ve "ozet":
çift başına ölçütlerin min / medyan / max'ı, `oneri` kolunun kâr farkında
(rpt_yok'a göre) mevcut ve frr3'ten kaç yolda önde olduğu. Koşular önbellekli
olduğundan yarıda kalan iş kaldığı yerden sürer: JSON'da biten yol, kaydındaki
`kod` (`kod_ozeti`: koşu kod özeti, v4 parmak izi, bu modül, `olcutler`, `hazirla`
kodu) bugünküyle aynıysa atlanır, değilse yeniden hesaplanır (koşular yine
önbellekten gelir, anahtarları değişmediyse). Her yolun kaydı kullandığı koşuların
anahtarlarını da taşır (`anahtarlar`, `lumoda`); rapor yol 0'ınkileri oyun
koşularınınkilerle karşılaştırır.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import hazirla, motor, olcutler, oyun

CIKTI = oyun.CIKTI / "yollar.json"
YOL_SAYISI = 5
OZET_OLCUTLERI = ("d_kar", "kar", "kurtarilan", "kurtarilan_kalici", "kurtarilan_ikame", "rpt",
                  "rpt_option", "rpt_bosa", "yanlis_alarm", "kacirilan")


def kod_ozeti() -> str:
    """Bir yolun kaydını belirleyen kod ve veri: koşu kod özeti (`motor.kod_ozeti`;
    oyun dahil), v4 parmak izi, ölçüm ve bu modül (koşu özeti dışında kalan
    `olcutler`, `yollar`), günlük tablonun kodu (`hazirla.kod_ozeti`)."""
    disi = {y.name: hashlib.sha256(y.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for y in (Path(olcutler.__file__), Path(__file__))}
    icerik = {"kosu": motor.kod_ozeti(), "veri": motor.veri_parmak_izi(), "disi": disi,
              "hazirla": hazirla.kod_ozeti()}
    return hashlib.sha256(json.dumps(icerik, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def yol_kos(yol: int, en_iyi: str, taban: int = oyun.TALEP_TABANI) -> dict:
    """Bir yolun hazırlığı, beş kolu ve sezon özetleri."""
    t0 = time.perf_counter()
    H = oyun.hazirlik(yol, taban=taban)
    K = oyun.tum_kollar(H, ciftler=oyun.yol_listesi(en_iyi))
    ogr = H.ogrenilen
    sonuc = {
        "yol": int(yol), "talep_tohumu": H.talep_tohumu, "en_iyi": en_iyi,
        "ogrenme": {G: {"egitim_satir": int(ogr.modeller[G].n), "egitim_pozitif": int(ogr.modeller[G].pozitif),
                        "mu": {str(h): v for h, v in ogr.belirsizlik[G].mu.items()},
                        "sigma": {str(h): v for h, v in ogr.belirsizlik[G].sigma.items()}}
                    for G in oyun.OYUN},
        "sezon": {G: oyun.tablo_sozlugu(oyun.ozet_tablosu(K, G)) for G in oyun.OYUN},
        "lumoda": H.kosu.meta["anahtar"],
        "anahtarlar": {f"{kol}|{kural}": k.meta["anahtar"] for (kol, kural), k in K.items()},
    }
    sonuc["sure"] = round(time.perf_counter() - t0, 1)
    return sonuc


def ozetle(yollar: dict, en_iyi: str) -> dict:
    """Çift başına ölçütlerin yollar üstünde min / medyan / max'ı; `oneri`nin kâr
    farkında öteki kollardan kaç yolda önde olduğu."""
    oz = {}
    for G in oyun.OYUN:
        ciftler = sorted({c for y in yollar.values() for c in y["sezon"][G]})
        oz[G] = {}
        for c in ciftler:
            oz[G][c] = {}
            for olc in OZET_OLCUTLERI:
                v = [y["sezon"][G][c].get(olc) for y in yollar.values() if c in y["sezon"][G]]
                v = np.array([x for x in v if x is not None], dtype=float)
                if len(v):
                    oz[G][c][olc] = {"min": float(v.min()), "medyan": float(np.median(v)),
                                     "max": float(v.max()), "n": int(len(v))}
        oneri = f"oneri|{en_iyi}"
        for rakip in (f"mevcut|{en_iyi}", "mevcut|a", f"frr3|{en_iyi}"):
            ikili = [(y["sezon"][G][oneri]["d_kar"], y["sezon"][G][rakip]["d_kar"]) for y in yollar.values()
                     if oneri in y["sezon"][G] and rakip in y["sezon"][G]]
            oz[G][f"oneri_onde|{rakip}"] = {"yol": len(ikili), "onde": int(sum(a > b for a, b in ikili))}
    return oz


def kos(n: int = YOL_SAYISI, taban: int = oyun.TALEP_TABANI, en_iyi: str | None = None,
        cikti: Path = CIKTI) -> dict:
    """`n` yol (0 … n−1), sıralı; her yoldan sonra `cikti`ya yazar. `en_iyi`
    verilmezse `cikti/oyun.json`'daki yol 0 seçimi (yoksa seçim koşulur)."""
    if en_iyi is None:
        oj = oyun.CIKTI / "oyun.json"
        if oj.exists():
            en_iyi = json.loads(oj.read_text(encoding="utf-8"))["en_iyi"]
        else:
            en_iyi = oyun.dagitim_secimi(oyun.hazirlik(0, taban=taban))
    cikti = Path(cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    kayit = json.loads(cikti.read_text(encoding="utf-8")) if cikti.exists() else {}
    if kayit.get("taban") != taban or kayit.get("en_iyi") != en_iyi:
        kayit = {}
    kayit.update({"taban": int(taban), "n": int(n), "en_iyi": en_iyi})
    yollar = kayit.setdefault("yollar", {})
    kod = kod_ozeti()
    for anahtar in [k for k, v in yollar.items() if v.get("kod") != kod]:
        print(f"yol {anahtar}: kayıt başka bir kodla ya da v4 dosyasıyla; yeniden hesaplanacak", flush=True)
        del yollar[anahtar]
    for yol in range(n):
        if str(yol) in yollar:
            continue
        s = yol_kos(yol, en_iyi, taban)
        s["kod"] = kod
        yollar[str(yol)] = s
        kayit["ozet"] = ozetle(yollar, en_iyi)
        cikti.write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"yol {yol}: {s['sure']:.0f} sn", flush=True)
    kayit["ozet"] = ozetle({k: v for k, v in yollar.items() if int(k) < n}, en_iyi)
    cikti.write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
    return kayit


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    kos()


if __name__ == "__main__":
    main()
