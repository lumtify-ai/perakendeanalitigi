"""Oyun: kolları aynı müşteri akışında v4 motorunda koşturur (asgari: yalnız
kalibrasyon alt komutu, Ruling R24; Görev 10 genişletir).

    .venv/Scripts/python -m replenishment.oyun kalibrasyon    # cikti/kalibrasyon.json

KALİBRASYON. `kalibrasyon.kalibre_et` koşuyu enjekte edilen `kos_fn(ad, ayar)`'a
bırakır (karar modülü motoru içe aktarmaz, Ruling R5). Buradaki koşucu
(`kalibrasyon_kosucusu`) `kural` kolunu (`politika.KuralKol`, Lumoda'yı sarar) verilen
`Ayar`'la yol 0'da (yayımlanan dünya), alım 1,0'da, kaydedicilerle koşar ve kolun
penceresinde ölçer (`olcutler.temel_olcutler`). Kolun kimliği (`parametreler()`: kol
adı ve bütün `Ayar`) koşu anahtarına kendiliğinden girer. Koşudan sonra kolun kaydı
`sevkiyat` ile karşılaştırılır; fark varsa (motor isteği kesmiş, defter kaymış) koşu
geçersizdir (`RuntimeError`).

KOŞULAR. `motor.kos(..., tembel=True)` (önbellek `cikti/kosular/`, sıralı); biten her
koşu `cikti/ilerleme.jsonl`'a (ad, saniye, önbellekten mi, motor saniyesi, tepe bellek)
yazılır, yarıda kalan kalibrasyon yeniden başlatılınca önbellekten devam eder. Uzun
koşuda makine uyku moduna girmez (Windows `SetThreadExecutionState`).
"""

import argparse
import json
import sys
import time
from pathlib import Path

from . import kalibrasyon, kaynak, motor, olcutler, politika
from .sabitler import CIKTI

ILERLEME = CIKTI / "ilerleme.jsonl"


def _ilerleme(ad: str, sn: float, onbellekten: bool, dosya: Path | None = ILERLEME, **ek) -> None:
    satir = {"ad": ad, "sn": round(float(sn), 1), "onbellekten": bool(onbellekten),
             "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"), **ek}
    print(json.dumps(satir, ensure_ascii=False), flush=True)
    if dosya is not None:
        Path(dosya).parent.mkdir(parents=True, exist_ok=True)
        with open(dosya, "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False) + "\n")


def uyanik_tut() -> None:
    """Windows'ta süreç sürdükçe sistem uykusunu engeller (başka yerde etkisiz)."""
    if sys.platform == "win32":
        import ctypes

        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def kalibrasyon_kosucusu(*, olcek: str = "tam", onbellek: Path | None = motor.KOSU_DIZINI,
                         gun_sayisi: int | None = None, ilerleme: Path | None = ILERLEME):
    """`kalibre_et`'in `kos_fn(ad, ayar) -> dict`'i (modül notu). `olcek`, `onbellek`,
    `gun_sayisi` testler içindir."""

    def kos_fn(ad: str, ayar: politika.Ayar) -> dict:
        t0 = time.perf_counter()
        kol = politika.KuralKol(motor.lumoda("replenishment"), ayar)
        k = motor.kos(kol, ad=ad, parametreler={}, onbellek=onbellek, olcek=olcek, gun_sayisi=gun_sayisi,
                      tembel=onbellek is not None, kaydedici=True)
        fark = politika.sevkiyatla_karsilastir(k)
        if not fark.empty:
            raise RuntimeError(f"{ad}: kolun kaydı sevkiyattan {len(fark)} satırda farklı (koşu geçersiz)")
        bas, bit = ayar.pencere
        olcut = olcutler.temel_olcutler(k, bas, bit)
        _ilerleme(ad, time.perf_counter() - t0, k.onbellekten, ilerleme,
                  motor_sn=k.meta.get("motor_sn"), tepe_gb=k.meta.get("tepe_bellek_gb"),
                  bulunabilirlik=round(olcut["bulunabilirlik"], 3))
        return olcut

    return kos_fn


def kalibrasyon_kos(yol: Path = kalibrasyon.DOSYA) -> kalibrasyon.Kalibrasyon:
    """Gerçek kalibrasyon: referans tavan (yayımlanan veri) → `kalibre_et` → `yol`."""
    t0 = time.perf_counter()
    con = kaynak.baglan()
    try:
        tavan = kalibrasyon.referans_tavan(con)
    finally:
        con.close()
    print(f"referans tavan: {tavan}", flush=True)
    k = kalibrasyon.kalibre_et(kalibrasyon_kosucusu(), tavan)
    kalibrasyon.yaz(k, yol, sure_sn=round(time.perf_counter() - t0, 1))
    return k


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m replenishment.oyun")
    alt = ap.add_subparsers(dest="komut", required=True)
    alt.add_parser("kalibrasyon", help="AW24 penceresinde kalibrasyon (cikti/kalibrasyon.json)")
    secim = ap.parse_args(argv)
    if secim.komut == "kalibrasyon":
        uyanik_tut()
        k = kalibrasyon_kos()
        sutunlar = ["asama", "ad", "bulunabilirlik", "toplama_maliyeti_tl", "magaza_stok_son"]
        print(k.tablo[sutunlar].to_string(), flush=True)
        print(f"hedef {k.hedef_bulunabilirlik:.3f}  gs {k.gs}  aile {k.secilen_aile}  koli {k.koli}  "
              f"seçilen koli {k.secilen_koli}  tavan {k.tavan}", flush=True)


if __name__ == "__main__":
    main()
