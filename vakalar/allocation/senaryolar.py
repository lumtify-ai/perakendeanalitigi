"""Demo kadranının senaryoları (elle koşulur; build'in parçası değil).

    .venv/Scripts/python senaryolar.py      # site/src/data/senaryolar/ilk-sevkiyat.json

Kadran iki eksenli: ilk dağıtımın pay kaynağı (Lumoda'nın plan payı / eşit / benzer ürün / LightGBM)
× depoda tutulan pay (gönderilebilir üst sınır U'ya göre %0 / %15 / %30; spec §0/9) = 12 bileşim.
Koşular oyun ızgarasındandır (spec §4.5 demo bloğu): yol 0, replenishment, RPT ve markdown
Lumoda'nın tepkili kararı, benzer ve tahmin tavansız (aynı mal; Ruling R43). Hangi bileşimin hangi
koşu olduğu `cikti/oyun.json`'un `demo` alanındadır (`oyun.demo_haritasi`: Lumoda %0 =
`lumoda`, Lumoda %15 / %30 = `tut_lumoda_t15` / `_t30`, öteki %0'lar pay bloğu, %15 / %30 demo
bloğu ya da tutma ekseninin aynı koşusu; tahmin %15 / %30 = `tut_eniyi_t15` / `_t30`).

**Yalnız önbellekten.** Değerler `cikti/oyun.json`'daki ölçülmüş kayıtlardan okunur; her kaydın
koşusu `cikti/kosular/<ad>_<anahtar[:20]>/meta.json`'da aynı anahtarla durmalıdır (takma adda
`ayni` tabanın dizini; yoksa `RuntimeError`: önce ızgara). Bu dosya motoru içe aktarmaz, koşmaz.

Sonuç kartları (`OZET_OLCUTLERI`, spec §8): sezon boyu bulunabilirlik, tam fiyat STR, sezon sonu
kalan (ilk alım + RPT'nin yüzdesi), kayıp oranı, düzeltme yükü (oyun option'larının replenishment
adedi). Yüzdeler bir ondalık, adet tam sayı (rapor DEMO bölümü aynı yuvarlamayla basar).
"""

import json
import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
ONBELLEK = CIKTI / "kosular"
HEDEF = KOK.parents[1] / "site" / "src" / "data" / "senaryolar" / "ilk-sevkiyat.json"
BUTCE = 500 * 1024

PAYLAR = ("lumoda", "esit", "benzer", "tahmin")
TUTMALAR = (0, 15, 30)

PARAMETRELER = [
    {"ad": "pay", "etiket": "İlk dağıtımın pay kaynağı", "degerler": list(PAYLAR),
     "deger_etiketleri": {"lumoda": "plan payı (Lumoda)", "esit": "herkese eşit", "benzer": "benzer ürün",
                          "tahmin": "LightGBM tahmini"}},
    {"ad": "tutma", "etiket": "Depoda tutulan pay", "degerler": list(TUTMALAR),
     "deger_etiketleri": {str(t): f"%{t}" for t in TUTMALAR}},
]

# ölçüt → basamak (yuvarlama)
OZET_OLCUTLERI = {"bulunabilirlik": 1, "tam_fiyat_str": 1, "sezon_sonu_kalan_yuzde": 1, "kayip_orani": 1,
                  "replenishment_adet": 0}


def anahtar(pay: str, tutma: int) -> str:
    return f"{pay}|{tutma}"


def harita_anahtari(tutma: int) -> str:
    """`oyun.demo_haritasi`'nın tutma anahtarı (`f"{t:g}"`, t oran): 0 → "0", 15 → "0.15"."""
    return f"{tutma / 100:g}"


def yuvarla(deger: float, basamak: int):
    return round(float(deger), basamak) if basamak else int(round(float(deger)))


def _onbellekte(ad: str, kosu_anahtari: str, onbellek: Path) -> bool:
    meta = Path(onbellek) / f"{ad}_{kosu_anahtari[:20]}" / "meta.json"
    return meta.is_file() and json.loads(meta.read_text(encoding="utf-8")).get("anahtar") == kosu_anahtari


def kosu_adi(oyun: dict, pay: str, tutma: int) -> str:
    """Bileşimin koşu adı (`oyun.json`'un `demo` haritasından); yoksa `RuntimeError`."""
    ad = (oyun.get("demo") or {}).get(pay, {}).get(harita_anahtari(tutma))
    if not ad:
        raise RuntimeError(f"{anahtar(pay, tutma)}: oyun.json'un demo haritasında koşu yok "
                           "(önce ızgara: python -m allocation.oyun)")
    return ad


def sonuclar(oyun: dict, onbellek: Path = ONBELLEK) -> dict:
    """`{"<pay>|<tutma>": {"ozet": {...}, "satirlar": []}}`, `PARAMETRELER` sırasıyla."""
    kosular = oyun["kosular"]
    sonuc = {}
    for p in PAYLAR:
        for t in TUTMALAR:
            ad = kosu_adi(oyun, p, t)
            e = kosular.get(ad)
            if e is None:
                raise RuntimeError(f"{ad} oyun.json'da yok: önce `python -m allocation.oyun`")
            dizin_adi = e.get("ayni", ad)
            if not _onbellekte(dizin_adi, e["anahtar"], onbellek):
                raise RuntimeError(f"{ad}: koşu önbellekte yok ya da anahtarı farklı ({onbellek}); önce ızgara")
            o = e["olcutler"]
            sonuc[anahtar(p, t)] = {"ozet": {m: yuvarla(o[m], b) for m, b in OZET_OLCUTLERI.items()},
                                    "satirlar": []}
    return sonuc


def _surum() -> str:
    """Kodun sürümü: HEAD'in kısa özeti (tarih yok: aynı commit'te iki üretim bayt bayt aynı)."""
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=KOK).stdout.strip()
    except Exception:  # noqa: BLE001 — git yoksa yerel
        return "yerel"


def uret(oyun: dict | None = None, onbellek: Path = ONBELLEK, surum: str | None = None) -> dict:
    """Demo dosyasının içeriği: `{surum, parametreler, sonuclar}` (yalnız önbellekten)."""
    if oyun is None:
        oyun = json.loads((CIKTI / "oyun.json").read_text(encoding="utf-8"))
    return {"surum": surum if surum is not None else _surum(), "parametreler": PARAMETRELER,
            "sonuclar": sonuclar(oyun, onbellek)}


def metin(icerik: dict) -> str:
    """JSON metni; bütçeyi (`BUTCE`) aşarsa `ValueError` (spec §8)."""
    m = json.dumps(icerik, ensure_ascii=False, indent=1)
    if len(m.encode("utf-8")) >= BUTCE:
        raise ValueError(f"senaryo dosyası bütçeyi aşıyor: {len(m.encode('utf-8'))} bayt ≥ {BUTCE}")
    return m


def yaz(icerik: dict, yol: Path = HEDEF) -> Path:
    yol = Path(yol)
    yol.write_text(metin(icerik) + "\n", encoding="utf-8")
    return yol


if __name__ == "__main__":
    print(f"yazıldı: {yaz(uret())}")
