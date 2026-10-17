"""Demo kadranının senaryoları (elle koşulur; build'in parçası değil).

    .venv/Scripts/python senaryolar.py      # site/src/data/senaryolar/depodan-magazaya.json

Kadran üç eksenli: depo alımı (planın %40 / %70 / %100'ü) × ihtiyaç hesabı (kural / LightGBM +
taban / yalnız LightGBM) × açık toplama tavanı (kısıtsız / gevşek ×1,6 / sıkı ×0,6) = 27 bileşim;
koşular oyun ızgarasının demo bloğu (`replenishment.oyun.IZGARA["demo"]`, Ruling R28): yol 0,
kalibrasyonun seçtiği güvenlik stoku ailesi ve koli kuralı.

**Yalnız önbellekten.** Değerler `cikti/oyun.json`'daki ölçülmüş kayıtlardan okunur; her kaydın
koşusu `cikti/kosular/<ad>_<anahtar[:20]>/meta.json`'da aynı anahtarla durmalıdır (yoksa
`RuntimeError`: önce ızgara). Bu dosya motoru içe aktarmaz, koşmaz.

Kırık çift tek başına yanıltıcıdır (boş raf kırık sayılmaz); kadran stoklu çiftlerdeki kırık
payını gösterir (`kirik_cift_pay_yuzde`). Değerler yuvarlanır: yüzde ve gün bir ondalık, adet ve
TL tam sayı (rapor DEMO bölümü aynı yuvarlamayla basar).
"""

import json
import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
ONBELLEK = CIKTI / "kosular"
HEDEF = KOK.parents[1] / "site" / "src" / "data" / "senaryolar" / "depodan-magazaya.json"
BUTCE = 500 * 1024

ALIMLAR = (40, 70, 100)
YONTEMLER = ("kural", "tahmin_taban", "tahmin")
TAVANLAR = ("kisitsiz", "gevsek", "siki")

PARAMETRELER = [
    {"ad": "alim", "etiket": "Depo alımı (planın yüzdesi)", "degerler": list(ALIMLAR),
     "deger_etiketleri": {str(a): f"%{a}" for a in ALIMLAR}},
    {"ad": "yontem", "etiket": "İhtiyaç hesabı", "degerler": list(YONTEMLER),
     "deger_etiketleri": {"kural": "kural tabanlı", "tahmin_taban": "LightGBM + taban kural",
                          "tahmin": "yalnız LightGBM"}},
    {"ad": "tavan", "etiket": "Açık toplama tavanı", "degerler": list(TAVANLAR),
     "deger_etiketleri": {"kisitsiz": "kısıtsız", "gevsek": "gevşek", "siki": "sıkı"}},
]

# ölçüt → basamak (yuvarlama)
OZET_OLCUTLERI = {"bulunabilirlik": 1, "kayip_orani": 1, "satisa_donme_gun": 1, "magaza_stok_son": 0,
                  "toplama_maliyeti_tl": 0, "kirik_cift_pay_yuzde": 1}


def kosu_adi(alim: int, yontem: str, tavan: str) -> str:
    """Demo bloğundaki koşunun adı (`oyun._demo`): `demo_<yöntem>_a<alım:03d>_<tavan>`."""
    return f"demo_{yontem}_a{alim:03d}_{tavan}"


def anahtar(alim: int, yontem: str, tavan: str) -> str:
    return f"{alim}|{yontem}|{tavan}"


def yuvarla(deger: float, basamak: int):
    return round(float(deger), basamak) if basamak else int(round(float(deger)))


def _onbellekte(ad: str, kosu_anahtari: str, onbellek: Path) -> bool:
    meta = Path(onbellek) / f"{ad}_{kosu_anahtari[:20]}" / "meta.json"
    return meta.is_file() and json.loads(meta.read_text(encoding="utf-8")).get("anahtar") == kosu_anahtari


def sonuclar(oyun: dict, onbellek: Path = ONBELLEK) -> dict:
    """`{"<alım>|<yöntem>|<tavan>": {"ozet": {...}, "satirlar": []}}`, `PARAMETRELER` sırasıyla."""
    kosular = oyun["kosular"]
    sonuc = {}
    for a in ALIMLAR:
        for y in YONTEMLER:
            for t in TAVANLAR:
                ad = kosu_adi(a, y, t)
                e = kosular.get(ad)
                if e is None:
                    raise RuntimeError(f"{ad} oyun.json'da yok: önce `python -m replenishment.oyun izgara --blok demo`")
                if not _onbellekte(ad, e["anahtar"], onbellek):
                    raise RuntimeError(f"{ad}: koşu önbellekte yok ya da anahtarı farklı ({onbellek}); önce ızgara")
                o = e["olcutler"]
                sonuc[anahtar(a, y, t)] = {"ozet": {m: yuvarla(o[m], b) for m, b in OZET_OLCUTLERI.items()},
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
    """JSON metni; bütçeyi (`BUTCE`) aşarsa `ValueError` (site spec §7)."""
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
