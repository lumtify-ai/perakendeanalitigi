"""Demo kadranının senaryoları (elle koşulur; build'in parçası değil).

    cd vakalar/markdown
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py            # site/src/data/senaryolar/indirim-takvimi.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py --kucuk    # cikti/kucuk/indirim-takvimi.json (geliştirme)

Kadran iki eksenli (spec §8): `kol` (yol 0'da koşulmuş altı kol: lumoda, tekduze, kural, opt_tuzak,
opt_takvim, opt) × `sezon` (yaz, kış, iki sezon) = 18 bileşim; anahtar `"<kol>|<sezon>"`. Sezon değerleri
sezon kodu değil (`yaz`, `kis`, `toplam`): değer sayfanın HTML'inde radyo düğmesinin değeri olarak durur ve
sayfada sezon kodu geçmez (spec §0); etiketler mevsime göreli. Bir bileşim yol 0'ın ölçülmüş koşusudur
(`cikti/oyun.json`): sezonda `<kol>_<sezon kodu>` (Lumoda'da `lumoda` kaydının o sezonu), iki sezonda
`toplamlar["0"][kol]` (iki koşunun option tablolarının birleşimi). İkiz yok (`ikizler` boş).

**Yalnız çıktılardan.** Simülasyon koşmaz, veriyi okumaz; `oyun.json` yoksa ya da bir bileşimin koşusu
ölçülmemişse `RuntimeError`.

Kartlar (`KARTLAR`, spec §8): `katki_farki_mtl` Lumoda'ya göre sezon katkısı farkı (milyon TL; iki ondalıklı
düzeylerin farkının bir kez yuvarlanmışı: `rapor.fark1`), `olu_stok_bin` ölü stok (bin adet), `markdown_mtl`
markdown TL (milyon TL), `tf_str` (tam fiyat STR; demo anahtarı İlk Sevkiyat'ın tam sayı basan `tam_fiyat_str` kartından ayrıdır) ve `son_str` (yüzde). Bütün kartlar bir ondalık: para ve
yüzde iki ondalıklı değerin bir kez yarım yukarı yuvarlanmışı (rapor iki ondalık basar; tek yuvarlama kuralı); ölü
stok tam adetten bir kez (rapor adet basar).

`surum` içeriğin özetidir (tarih ve commit yok): aynı girdiden iki üretim bayt bayt aynıdır.
"""

import argparse
import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
DIZI = "indirim-takvimi"
HEDEF = KOK.parents[1] / "site" / "src" / "data" / "senaryolar" / f"{DIZI}.json"
KUCUK_HEDEF = CIKTI / "kucuk" / f"{DIZI}.json"
BUTCE = 500 * 1024

KOLLAR = ("lumoda", "tekduze", "kural", "opt_tuzak", "opt_takvim", "opt")
SEZONLAR = {"yaz": "SS25", "kis": "AW24", "toplam": None}
LUMODA = "lumoda"

PARAMETRELER = [
    {"ad": "kol", "etiket": "Karar kuralı", "degerler": list(KOLLAR),
     "deger_etiketleri": {"lumoda": "Lumoda'nın kuralı", "tekduze": "herkese aynı indirim", "kural": "kapsama kuralı",
                          "opt_tuzak": "optimizasyon, yanlış esneklik", "opt_takvim": "optimizasyon, takvime bağlı",
                          "opt": "optimizasyon, serbest"}},
    {"ad": "sezon", "etiket": "Sezon", "degerler": list(SEZONLAR),
     "deger_etiketleri": {"yaz": "yaz sezonu", "kis": "kış sezonu", "toplam": "iki sezon"}},
]

# kart → (oyun.json ölçütü, bölen)
KARTLAR = {"katki_farki_mtl": ("katki", 1e6), "olu_stok_bin": ("olu_stok_adet", 1e3),
           "markdown_mtl": ("markdown_tl", 1e6), "tf_str": ("tam_fiyat_str", 1.0), "son_str": ("son_str", 1.0)}


def anahtar(kol: str, sezon: str) -> str:
    return f"{kol}|{sezon}"


def _yuv(x: float, ondalik: int) -> Decimal:
    return Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-ondalik), rounding=ROUND_HALF_UP)


def yuvarla(deger: float) -> float:
    """İki ondalığa, sonra bir kez bir ondalığa yarım yukarı (`rapor.tek_ondalik(rapor.yuv(x, 2))`)."""
    return float(_yuv(deger, 2).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fark1(a: float, b: float) -> float:
    """b − a, bir ondalık: iki ondalıklı düzeylerin farkının bir kez yuvarlanmışı (`rapor.fark1`)."""
    iki = (_yuv(b, 2) - _yuv(a, 2)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(iki.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _oku(yol: Path, komut: str) -> dict:
    yol = Path(yol)
    if not yol.is_file():
        raise RuntimeError(f"{yol} yok: önce `{komut}`")
    return json.loads(yol.read_text(encoding="utf-8"))


def kosu_adi(kol: str, sezon_kodu: str) -> str:
    return LUMODA if kol == LUMODA else f"{kol}_{sezon_kodu}"


def olcutler(oyun_kaydi: dict, kol: str, sezon: str) -> tuple[dict, list[str]]:
    """(bileşimin ölçütleri, kaynak koşular): sezonda koşunun (Lumoda'da sezonun) ölçütleri, iki sezonda
    `toplamlar["0"][kol]`."""
    kosular = oyun_kaydi.get("kosular") or {}
    kod = SEZONLAR[sezon]
    if kod is None:
        t = ((oyun_kaydi.get("toplamlar") or {}).get("0") or {}).get(kol)
        if t is None or "olcutler" not in t:
            raise RuntimeError(f"{kol}|{sezon}: oyun.json'da yol 0 toplamı yok (önce python -m markdown.oyun izgara)")
        return t["olcutler"], list(t.get("kosular") or [])
    ad = kosu_adi(kol, kod)
    e = kosular.get(ad)
    if e is None or "olcutler" not in e:
        raise RuntimeError(f"{kol}|{sezon}: oyun.json'da ölçülmüş {ad} koşusu yok (önce python -m markdown.oyun izgara)")
    o = e["olcutler"][kod] if kol == LUMODA else e["olcutler"]
    return o, [ad]


def ozet(o: dict, lumoda: dict) -> dict:
    out = {}
    for kart, (alan, bolen) in KARTLAR.items():
        if kart == "katki_farki_mtl":
            out[kart] = fark1(lumoda[alan] / bolen, o[alan] / bolen)
        elif kart == "olu_stok_bin":
            out[kart] = float(_yuv(o[alan] / bolen, 1))          # rapor ölü stoğu tam adet basar: tek yuvarlama
        else:
            out[kart] = yuvarla(o[alan] / bolen)
    return out


def sonuclar(oyun_kaydi: dict) -> dict:
    """`{"<kol>|<sezon>": {"ozet": {...}, "satirlar": [{"kosu": ...}]}}`, `PARAMETRELER` sırasıyla."""
    out = {}
    for kol in KOLLAR:
        for sezon in SEZONLAR:
            o, kaynak = olcutler(oyun_kaydi, kol, sezon)
            lu, _ = olcutler(oyun_kaydi, LUMODA, sezon)
            out[anahtar(kol, sezon)] = {"ozet": ozet(o, lu), "satirlar": [{"kosu": k} for k in kaynak]}
    return out


def _surum(govde: dict) -> str:
    m = json.dumps(govde, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(m.encode("utf-8")).hexdigest()[:12]


def uret(oyun_kaydi: dict | None = None) -> dict:
    """Demo dosyasının içeriği: `{surum, parametreler, ikizler, sonuclar}`."""
    oyun_kaydi = _oku(CIKTI / "oyun.json", "python -m markdown.oyun izgara") if oyun_kaydi is None else oyun_kaydi
    govde = {"parametreler": PARAMETRELER, "ikizler": {}, "sonuclar": sonuclar(oyun_kaydi)}
    return {"surum": _surum(govde), **govde}


def metin(icerik: dict) -> str:
    """JSON metni; bütçeyi (`BUTCE`) aşarsa `ValueError` (spec §8)."""
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
        print(f"yazıldı: {yaz(uret(_oku(CIKTI / 'kucuk' / 'oyun.json', 'oyun izgara --olcek KUCUK')), KUCUK_HEDEF)}")
    else:
        o = _oku(CIKTI / "oyun.json", "python -m markdown.oyun izgara")
        if o.get("olcek") != "tam":
            raise RuntimeError(f"cikti/oyun.json {o.get('olcek')} ölçeğinde; site dosyası yalnız TAM'dan yazılır")
        print(f"yazıldı: {yaz(uret(o))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
