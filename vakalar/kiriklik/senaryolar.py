"""Demo kadranının senaryoları (elle koşulur; build'in parçası değil; Transfer dizisinin 5. yazısı).

    cd vakalar/kiriklik
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py            # site/src/data/senaryolar/kiriklik-transferi.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py --kucuk    # cikti/kucuk/kiriklik-transferi.json (geliştirme)

Kadran üç eksenli (tasarım §0/16): `kol` (yol 0'ın üç kolu: kural, opt_set, opt) × `paket` (maliyet paketi: düşük,
orta, yüksek) × `sezon` (kış, yaz, iki sezon) = 27 bileşim; anahtar `"<kol>|<paket>|<sezon>"` (parametre sırası).
Sezon değerleri sezon kodu değil (`kis` AW24, `yaz` SS25, `toplam`): sayfada sezon kodu geçmez. Bir bileşim yol 0'ın
ölçülmüş koşularıdır (`cikti/oyun.json` `kosular["<kol>_<sezon kodu>"]["olcum"]`, Lumoda'ya göre farklar); iki sezonda
iki koşunun toplamı. İkiz yok.

**Yalnız çıktılardan.** Simülasyon koşmaz, veriyi okumaz; `oyun.json` yoksa ya da bir bileşimin koşusu geçerli
ölçülmemişse `RuntimeError`.

Kartlar (`KARTLAR`; bütün sayılar `rapor.py`'nin YOL 0'ında):
- `net_fark_mtl` net sonuç (milyon TL): ciro farkı (sezon kapsamı, karar → çıkış + 84) − transfer maliyeti (paketle);
  iki ondalıklı değerin (iki sezonda toplamın iki ondalığı) bir kez yarım yukarı yuvarlanmışı, bir ondalık.
- `kirik_beden_farki` indirim gününden önceki son pazartesi, sezonun bütün Collection stoğunda kırık beden sayısı
  farkı (kol − Lumoda; adet, pakete bağlı değil).
- `saha_donus_yuzde` saha ölçüsüyle satışa dönüş, çıkışa kadar: Σ min(alıcı hücrenin varıştan çıkışa satışı, alınan) ÷
  Σ alınan (yüzde, bir ondalık: iki ondalıklının bir kez yuvarlanmışı).
- `etki_donus_yuzde` gerçek etki: transfer edilen option'ların bütün mağaza ve kanallarında net satış farkı (karar →
  çıkış + 84) ÷ taşınan adet (yüzde, bir ondalık).

`surum` içeriğin özetidir (tarih ve commit yok): aynı girdiden iki üretim bayt bayt aynıdır.
"""

import argparse
import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
DIZI = "kiriklik-transferi"
HEDEF = KOK.parents[1] / "site" / "src" / "data" / "senaryolar" / f"{DIZI}.json"
KUCUK_HEDEF = CIKTI / "kucuk" / f"{DIZI}.json"
BUTCE = 500 * 1024

KOLLAR = ("kural", "opt_set", "opt")
PAKETLER = ("dusuk", "orta", "yuksek")
SEZONLAR = {"kis": "AW24", "yaz": "SS25", "toplam": None}
KARTLAR = ("net_fark_mtl", "kirik_beden_farki", "saha_donus_yuzde", "etki_donus_yuzde")

PARAMETRELER = [
    {"ad": "kol", "etiket": "Karar kuralı", "degerler": list(KOLLAR),
     "deger_etiketleri": {"kural": "uzmanın kuralı", "opt_set": "optimizasyon, set tamamlanır",
                          "opt": "optimizasyon, serbest"}},
    {"ad": "paket", "etiket": "Transfer maliyeti", "degerler": list(PAKETLER),
     "deger_etiketleri": {"dusuk": "düşük maliyet", "orta": "orta maliyet", "yuksek": "yüksek maliyet"}},
    {"ad": "sezon", "etiket": "Sezon", "degerler": list(SEZONLAR),
     "deger_etiketleri": {"kis": "kış sezonu", "yaz": "yaz sezonu", "toplam": "iki sezon"}},
]


def anahtar(kol: str, paket: str, sezon: str) -> str:
    return f"{kol}|{paket}|{sezon}"


def _yuv(x: float, ondalik: int) -> Decimal:
    return Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-ondalik), rounding=ROUND_HALF_UP)


def yuvarla(deger: float) -> float:
    """İki ondalığa, sonra bir kez bir ondalığa yarım yukarı (`rapor.tek_ondalik(rapor.yuv(x, 2))`)."""
    return float(_yuv(deger, 2).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _oku(yol: Path, komut: str) -> dict:
    yol = Path(yol)
    if not yol.is_file():
        raise RuntimeError(f"{yol} yok: önce `{komut}`")
    return json.loads(yol.read_text(encoding="utf-8"))


def kosu_adi(kol: str, sezon_kodu: str) -> str:
    return f"{kol}_{sezon_kodu}"


def olcumler(oyun_kaydi: dict, kol: str, sezon: str) -> list[tuple[str, dict]]:
    """Bileşimin (koşu adı, ölçüm) listesi: sezonda tek koşu, iki sezonda iki koşu (AW24, SS25 sırası)."""
    kodlar = [SEZONLAR[sezon]] if SEZONLAR[sezon] else [k for k in SEZONLAR.values() if k]
    out = []
    for z in kodlar:
        ad = kosu_adi(kol, z)
        e = (oyun_kaydi.get("kosular") or {}).get(ad)
        if e is None or e.get("gecerli") is not True or e.get("olcum") is None:
            raise RuntimeError(f"{kol}|{sezon}: oyun.json'da geçerli ölçülmüş {ad} koşusu yok "
                               "(önce python -m kiriklik.oyun izgara ve olc)")
        out.append((ad, e["olcum"]))
    return out


def ham(oo: list[dict], paket: str) -> dict:
    """Kartların yuvarlanmamış değerleri (modül notu): net TL, kırık beden farkı, iki dönüş oranı (0–1)."""
    alinan = sum(o["satisa_donus"]["alinan_adet"] for o in oo)
    tasinan = sum(o["plan"]["adet"] for o in oo)
    return {"net_tl": sum(o["para"]["net"][paket] for o in oo),
            "kirik_beden_farki": sum(o["kiriklik"]["indirim_oncesi"]["kapsamlar"]["butun"]["fark"]["kirik_beden"]
                                     for o in oo),
            "saha_donus": sum(o["satisa_donus"]["cikisa_satilan"] for o in oo) / alinan if alinan else None,
            "etki_donus": sum(o["satisa_donus"]["etki_adet"]["toplam"] for o in oo) / tasinan if tasinan else None}


def ozet(oo: list[dict], paket: str) -> dict:
    h = ham(oo, paket)
    return {"net_fark_mtl": yuvarla(h["net_tl"] / 1e6),
            "kirik_beden_farki": int(h["kirik_beden_farki"]),
            "saha_donus_yuzde": None if h["saha_donus"] is None else yuvarla(100 * h["saha_donus"]),
            "etki_donus_yuzde": None if h["etki_donus"] is None else yuvarla(100 * h["etki_donus"])}


def sonuclar(oyun_kaydi: dict) -> dict:
    """`{"<kol>|<paket>|<sezon>": {"ozet": {...}, "satirlar": [{"kosu": ...}]}}`, `PARAMETRELER` sırasıyla."""
    out = {}
    for kol in KOLLAR:
        for paket in PAKETLER:
            for sezon in SEZONLAR:
                kayit = olcumler(oyun_kaydi, kol, sezon)
                out[anahtar(kol, paket, sezon)] = {"ozet": ozet([o for _, o in kayit], paket),
                                                   "satirlar": [{"kosu": ad} for ad, _ in kayit]}
    return out


def _surum(govde: dict) -> str:
    m = json.dumps(govde, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(m.encode("utf-8")).hexdigest()[:12]


def uret(oyun_kaydi: dict | None = None) -> dict:
    """Demo dosyasının içeriği: `{surum, parametreler, ikizler, sonuclar}`."""
    oyun_kaydi = _oku(CIKTI / "oyun.json", "python -m kiriklik.oyun olc") if oyun_kaydi is None else oyun_kaydi
    govde = {"parametreler": PARAMETRELER, "ikizler": {}, "sonuclar": sonuclar(oyun_kaydi)}
    return {"surum": _surum(govde), **govde}


def metin(icerik: dict) -> str:
    """JSON metni; bütçeyi (`BUTCE`) aşarsa `ValueError`."""
    m = json.dumps(icerik, ensure_ascii=False, indent=1)
    if len(m.encode("utf-8")) >= BUTCE:
        raise ValueError(f"senaryo dosyası bütçeyi aşıyor: {len(m.encode('utf-8'))} bayt ≥ {BUTCE}")
    return m


def yaz(icerik: dict, yol: Path = HEDEF) -> Path:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(metin(icerik) + "\n", encoding="utf-8", newline="\n")
    return yol


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="senaryolar.py", description=__doc__.splitlines()[0])
    p.add_argument("--kucuk", action="store_true", help="KÜÇÜK ölçeğin oyun.json'u → cikti/kucuk/ (geliştirme)")
    a = p.parse_args(argv)
    if a.kucuk:
        o = _oku(CIKTI / "kucuk" / "oyun.json", "python -m kiriklik.oyun olc --olcek KUCUK")
        print(f"yazıldı: {yaz(uret(o), KUCUK_HEDEF)}")
    else:
        o = _oku(CIKTI / "oyun.json", "python -m kiriklik.oyun olc")
        if o.get("olcek") != "tam":
            raise RuntimeError(f"cikti/oyun.json {o.get('olcek')} ölçeğinde; site dosyası yalnız TAM'dan yazılır")
        print(f"yazıldı: {yaz(uret(o))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
