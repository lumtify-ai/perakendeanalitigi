"""Alternatif talep yolları: aynı dünya, farklı müşteri akışı (spec §0/13, §4.4).

    .venv/Scripts/python -m allocation.yollar        # 5 yol, sıralı; cikti/yollar.json

Yol p'nin talep tohumu `oyun.talep_tohumu(p)` (yol 0 yayımlanan dünya, p > 0 `TALEP_TOHUM_TABANI +
p`): talebin Poisson ve ikame çekilişleri değişir, ürün sürprizleri (λ), dünya ve operasyon
çekilişleri aynıdır. Her yol kendi gerçekleşen tarihini Lumoda'yla üretir (`y<p>_lumoda`), benzer
ürün endeksini ve LightGBM'i o tarihin yayımlanan biçiminden yeniden öğrenir, kahinin erken
birincil talebini o yolun `lumoda` gizli gerçeğinden alır (`oyun.Girdi`) ve dört kolu koşar: esit,
benzer, tahmin (ikisi tavansız: Lumoda'yla aynı mal, Ruling R44), kahin; t = 0 (`oyun.yol_listesi`). Sonra
üç küme kolu (`oyun.YOL_KUME_KOLLARI`: kume_ml, kume_gizli; Mağaza Kümeleme spec §4.4; kume_k3, Lumoda'nın
grupları, Ruling R23): kümeler (K3 ızgarası dahil) o yolun
`lumoda` tablolarından kümeleme paketinin işlevleriyle yeniden kurulur (`oyun.kumeleri_kur`), küme payı
o yolun öğrenme tablosundan. Kalibrasyon (küme payınınki dahil) yol 0'ınkidir
(oyundan önceki karar, yol başına yeniden seçilmez). Yol 0'ın koşuları ızgaranın pay bloğuyla aynı
anahtardadır (önbellekten; ölçümleri `cikti/oyun.json`'dan).

Çıktı `cikti/yollar.json`: yol başına talep tohumu, girdilerin özeti (karar günü, öğrenme satırı,
endeks / tahminci kimliği, küme kollarının kümeleme kimliği ve düzeyleri), koşuların anahtarı ve ölçütleri; "ozet": kol başına ölçütlerin yollar
üstünde min / medyan / max'ı ve kol çiftlerinde "kaç yolda önde" sayıları (`KARSILASTIRMALAR`;
`YUKSEK_IYI`'deki yönle). Yarıda kalan iş kaldığı yerden sürer (her koşudan sonra yazılır, koşular
önbellekli); kaydı başka bir kodla (`kod_ozeti`) yazılmış yol yeniden ölçülür.
"""

import gc
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

import kumeleme.oyun as kumeleme_oyun

from allocation import kalibrasyon, motor, olcutler, oyun, sabitler

OZET_OLCUTLERI = ("bulunabilirlik", "bulunabilirlik_ilk4", "kayip_orani", "sezon_sonu_kalan_yuzde",
                  "tam_fiyat_str", "markdown_tl", "brut_kar_tl", "pay_wape", "rpt_adet", "replenishment_adet",
                  "kirik_cift_pay_yuzde", "oturan_hucre", "hizli_biten_hucre")
# (a, b): a'nın b'den kaç yolda önde olduğu
KARSILASTIRMALAR = (("esit", "lumoda"), ("benzer", "lumoda"), ("tahmin", "lumoda"), ("tahmin", "benzer"),
                    ("kahin", "lumoda"), ("kahin", "tahmin"), ("kume_ml", "lumoda"), ("kume_ml", "benzer"),
                    ("kume_ml", "tahmin"), ("kume_gizli", "kume_ml"), ("kume_ml", "kume_k3"), ("kume_k3", "lumoda"))
YUKSEK_IYI = {"bulunabilirlik": True, "sezon_sonu_kalan_yuzde": False, "kayip_orani": False,
              "tam_fiyat_str": True, "brut_kar_tl": True, "pay_wape": False}


def kod_ozeti() -> str:
    """Bir yolun kaydını belirleyen kod ve veri: koşu kod özeti, v4 parmak izi, koşu özetinin dışında
    kalan `olcutler`, `oyun`, `kalibrasyon`, `yollar` ve kümeleme paketi (küme kollarının kümeleri ve payı
    yolda onun işlevleriyle kurulur; `kumeleme.oyun.kod_ozeti`)."""
    disi = {Path(m.__file__).name: hashlib.sha256(Path(m.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for m in (olcutler, oyun, kalibrasyon, sys.modules[__name__])}
    icerik = {"kosu": motor.kod_ozeti(), "veri": motor.veri_parmak_izi(), "disi": disi,
              "kumeleme": kumeleme_oyun.kod_ozeti()}
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


def yol_kos(yol: int, kal: dict, ortam: oyun.Ortam, kayit: dict, yaz) -> dict:
    """Bir yolun girdileri ve sekiz koşusu (beş kol + üç küme kolu); her koşudan sonra `yaz()` (kayıt
    `kayit`'te büyür)."""
    t0 = time.perf_counter()
    G = oyun.Girdi(yol, ortam, kal)
    oyun_kayitlari = oyun.json_oku(ortam.oyun_yolu).get("kosular", {}) if int(yol) == 0 else {}
    kayit.update({"yol": int(yol), "talep_tohumu": oyun.talep_tohumu(yol)})
    kosular = kayit.setdefault("kosular", {})
    for kisa, s in oyun.yol_listesi(yol, kal):
        onceki = kosular.get(kisa) or oyun_kayitlari.get(s.ad)
        k, e = oyun.kos_bir(s, G, kal, None, onceki)
        del k
        kosular[kisa] = {a: e[a] for a in ("anahtar", "olcum_kodu", "kosum", "cozum", "imza", "talep_tohumu",
                                           "motor_sn", "tepe_bellek_gb", "olcutler") if a in e} | {"ad": s.ad}
        kayit["girdi"] = dict(G.bilgi)
        if "endeks" in G.__dict__:
            kayit["girdi"]["endeks"] = G.endeks.kimlik
        if "tahminci" in G.__dict__:
            kayit["girdi"]["tahminci"] = G.tahminci.kimlik
        if s.kol == "kume":
            kosular[kisa]["kume"] = {a: G.kume_bilgisi(s.kume)[a] for a in ("bas", "en_az", "duzey", "endeks", "pay",
                                                                           "cift", "sifir_pay", "kumeleme")}
        yaz()
    kayit["sure_sn"] = round(time.perf_counter() - t0, 1)
    del G
    gc.collect()
    return kayit


def kos(n: int = sabitler.YOL_SAYISI, ortam: oyun.Ortam | None = None, kal: dict | None = None) -> dict:
    """`n` yol (0 … n−1), sıralı; `cikti/yollar.json`'a her koşudan sonra yazar."""
    ortam = ortam or oyun.Ortam()
    kal = kal if kal is not None else kalibrasyon.oku()
    yol_dosyasi = Path(ortam.cikti) / "yollar.json"
    kayit = oyun.json_oku(yol_dosyasi)
    kayit.update({"n": int(n), "taban": sabitler.TALEP_TOHUM_TABANI, "kollar": list(oyun.YOL_KOLLARI),
                  "kume_kollari": list(oyun.YOL_KUME_KOLLARI)})
    yollar = kayit.setdefault("yollar", {})
    kod = kod_ozeti()
    for anahtar in [k for k, v in yollar.items() if v.get("kod") != kod]:
        print(f"yol {anahtar}: kayıt başka bir kodla ya da v4 dosyasıyla; yeniden ölçülecek", flush=True)
        del yollar[anahtar]

    def yaz():
        kayit["ozet"] = ozetle({k: v for k, v in yollar.items() if int(k) < n})
        oyun.json_yaz(yol_dosyasi, kayit)

    for yol in range(n):
        y = yollar.get(str(yol))
        if y is not None and y.get("tamam"):
            continue
        y = yollar.setdefault(str(yol), {"kod": kod})
        yol_kos(yol, kal, ortam, y, yaz)
        y["tamam"] = True
        yaz()
        print(f"yol {yol}: {y['sure_sn']:.0f} sn", flush=True)
    yaz()
    return kayit


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    oyun.uyanik_tut()
    t0 = time.perf_counter()
    kos()
    print(f"yollar bitti: {time.perf_counter() - t0:.0f} sn", flush=True)


if __name__ == "__main__":
    main()
