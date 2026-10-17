"""Alternatif talep yolları: aynı dünya, farklı müşteri akışı (spec §4.5, Ruling R28).

    .venv/Scripts/python -m replenishment.yollar        # 5 yol, sıralı; cikti/yollar.json

Yol p'nin talep tohumu `oyun.talep_tohumu(p)` (yol 0 yayımlanan dünya, p > 0
`TALEP_TOHUM_TABANI + p`); dünya ve operasyon çekilişleri bütün yollarda aynıdır, yalnız
müşteri akışı değişir. Her yol kendi gerçekleşen tarihini Lumoda'yla üretir
(`lumoda_kisitsiz`, öğrenme geçmişi), LightGBM'i o tarihin yayımlanan biçiminden yeniden
eğitir (`oyun.hazirlik`: yolun DuckDB'si, `tahmin.cevrimdisi_egit`) ve dört kolu referans
noktada koşar: lumoda (kısıtlı), kural, tahmin_taban, tahmin (`oyun.yol_listesi`). Kalibrasyon
(güvenlik stoku, koli, tavan) yol 0'ınkidir: oyundan önceki bir karardır, yol başına yeniden
seçilmez. Yol 0'ın koşuları ızgaranınkilerle aynı anahtardadır (önbellekten; ölçümleri
`cikti/oyun.json`'dan).

Çıktı `cikti/yollar.json`: yol başına talep tohumu, tahmincinin özeti, kullanılan koşuların
anahtarları ve ölçütleri (`kosular`: kısa ad → anahtar, ölçütler), "ozet": kol başına ölçütlerin
yollar üstünde min / medyan / max'ı ve kol çiftlerinde "kaç yolda önde" sayıları
(`KARSILASTIRMALAR`; bulunabilirlikte yüksek, maliyet ve stokta düşük olan önde). Koşular
önbellekli olduğundan yarıda kalan iş kaldığı yerden sürer: her koşudan sonra yazılır; kaydı
başka bir kodla (`kod_ozeti`) yazılmış yol yeniden hesaplanır (koşular yine önbellekten).
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import kalibrasyon, motor, olcutler, oyun
from .sabitler import YOL_SAYISI

OZET_OLCUTLERI = ("bulunabilirlik", "kayip_orani", "kalici_kayip_orani", "ikame_payi", "toplama_maliyeti_tl",
                  "magaza_stok_son", "gonderilen_adet", "acik_adet", "koli_sayisi", "str", "satisa_donme_gun",
                  "kirik_cift_pay_yuzde", "beden_sapmasi", "kesilen_pay_yuzde", "depo_bos_kayip_pay_yuzde")
# (a, b): a'nın b'den kaç yolda önde olduğu
KARSILASTIRMALAR = (("tahmin_taban_ref", "kural_ref"), ("tahmin_ref", "kural_ref"),
                    ("tahmin_taban_ref", "tahmin_ref"), ("kural_ref", "lumoda_ref"),
                    ("tahmin_taban_ref", "lumoda_ref"), ("lumoda_kisitsiz", "lumoda_ref"))
YUKSEK_IYI = {"bulunabilirlik": True, "toplama_maliyeti_tl": False, "magaza_stok_son": False,
              "kayip_orani": False}


def kod_ozeti() -> str:
    """Bir yolun kaydını belirleyen kod ve veri: koşu kod özeti, v4 parmak izi, koşu
    özetinin dışında kalan `olcutler`, `oyun`, `yollar`."""
    disi = {Path(m.__file__).name: hashlib.sha256(Path(m.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for m in (olcutler, oyun, sys.modules[__name__])}
    icerik = {"kosu": motor.kod_ozeti(), "veri": motor.veri_parmak_izi(), "disi": disi}
    return hashlib.sha256(json.dumps(icerik, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def ozetle(yollar: dict) -> dict:
    """Kol başına ölçütlerin yollar üstünde min / medyan / max'ı; kol çiftlerinde kaç yolda önde."""
    kollar = sorted({k for y in yollar.values() for k in y.get("kosular", {})})
    oz = {"kollar": {}, "onde": {}}
    for kol in kollar:
        oz["kollar"][kol] = {}
        for olc in OZET_OLCUTLERI:
            v = np.array([y["kosular"][kol]["olcutler"][olc] for y in yollar.values()
                          if kol in y.get("kosular", {})], dtype=float)
            if len(v):
                oz["kollar"][kol][olc] = {"min": float(v.min()), "medyan": float(np.median(v)),
                                          "max": float(v.max()), "n": int(len(v))}
    for a, b in KARSILASTIRMALAR:
        ikili = [(y["kosular"][a]["olcutler"], y["kosular"][b]["olcutler"]) for y in yollar.values()
                 if a in y.get("kosular", {}) and b in y.get("kosular", {})]
        sayim = {"yol": len(ikili)}
        for olc, yuksek in YUKSEK_IYI.items():
            sayim[olc] = int(sum((x[olc] > z[olc]) if yuksek else (x[olc] < z[olc]) for x, z in ikili))
        oz["onde"][f"{a}|{b}"] = sayim
    return oz


def yol_kos(yol: int, kal: kalibrasyon.Kalibrasyon, ortam: oyun.Ortam, kayit: dict, yaz) -> dict:
    """Bir yolun hazırlığı ve beş koşusu; her koşudan sonra `yaz()` (kayıt `kayit`'te büyür)."""
    t0 = time.perf_counter()
    H = oyun.hazirlik(yol, ortam)
    oyun_kayitlari = oyun._json_oku(Path(ortam.cikti) / "oyun.json").get("kosular", {}) if yol == 0 else {}
    kayit.update({"yol": int(yol), "talep_tohumu": H.talep_tohumu, "lumoda": H.lumoda.meta["anahtar"],
                  "tahmin": {a: H.tahmin_ozet.get(a) for a in ("kimlik", "satir", "dogrulama_sapma",
                                                                 "dogrulama_sapma_lag1", "dogrulama_sapma_ort4")}})
    kosular = kayit.setdefault("kosular", {})
    for kisa, s in oyun.yol_listesi(yol):
        onceki = kosular.get(kisa) or oyun_kayitlari.get(s.ad)
        _, e = oyun.kos_bir(s, H, kal, ortam, onceki)
        kosular[kisa] = {k: e[k] for k in ("anahtar", "olcum_kodu", "kol", "alim", "ayar", "olcutler", "line",
                                            "motor_sn", "tepe_bellek_gb", "sevkiyat_farki", "kosum")}
        yaz()
    kayit["sure"] = round(time.perf_counter() - t0, 1)
    return kayit


def kos(n: int = YOL_SAYISI, ortam: oyun.Ortam | None = None, kal: kalibrasyon.Kalibrasyon | None = None) -> dict:
    """`n` yol (0 … n−1), sıralı; `cikti/yollar.json`'a her koşudan sonra yazar."""
    ortam = ortam or oyun.Ortam()
    kal = kal or kalibrasyon.oku()
    yol_dosyasi = Path(ortam.cikti) / "yollar.json"
    kayit = oyun._json_oku(yol_dosyasi)
    kayit.update({"n": int(n), "taban": oyun.TALEP_TOHUM_TABANI, "kollar": list(oyun.YOL_KOLLARI)})
    yollar = kayit.setdefault("yollar", {})
    kod = kod_ozeti()
    for anahtar in [k for k, v in yollar.items() if v.get("kod") != kod]:
        print(f"yol {anahtar}: kayıt başka bir kodla ya da v4 dosyasıyla; yeniden hesaplanacak", flush=True)
        del yollar[anahtar]

    def yaz():
        kayit["ozet"] = ozetle({k: v for k, v in yollar.items() if int(k) < n})
        oyun._json_yaz(yol_dosyasi, kayit)

    for yol in range(n):
        y = yollar.get(str(yol))
        if y is not None and y.get("tamam"):
            continue
        y = yollar.setdefault(str(yol), {"kod": kod})
        yol_kos(yol, kal, ortam, y, yaz)
        y["tamam"] = True
        yaz()
        print(f"yol {yol}: {y['sure']:.0f} sn", flush=True)
    motor.dunya.cache_clear()
    yaz()
    return kayit


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    oyun.uyanik_tut()
    kos()


if __name__ == "__main__":
    main()
