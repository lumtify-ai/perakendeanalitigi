"""Demo kadranının senaryoları (elle koşulur; build'in parçası değil).

    cd vakalar/beden-paket
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py   # site/src/data/senaryolar/beden-paket.json

Kadran iki eksenli (spec §8): paket tipi sayısı K {1, 2, 3, mağazaya özel} × paket büyüklüğü {7, 12}.
Bir bileşim yol 0'ın ölçülmüş koşusudur (`cikti/oyun.json`); koşulmamış bir bileşim, koşusuz K
eğrisinde (`cikti/analiz.json`, `k_egrisi`) aynı desen ve atamayı veren daha küçük K'nın koşusunu
alır (`esdeger_K`; ör. 7'li K = 3 ve mağazaya özel = P2, 12'li mağazaya özel = P3; Ruling R10). Ne
koşusu ne ikizi olan bileşim dosyaya girmez (`eksik`; ör. 12'li K = 2 koşulmadı, K eğrisinde K = 3'ten
ayrı).

**Yalnız çıktılardan.** Bu dosya simülasyonu koşmaz, veriyi okumaz; `oyun.json` ya da `analiz.json`
yoksa ya da bir bileşimin koşusu ölçülmemişse `RuntimeError`.

Sonuç kartları (`OZET_OLCUTLERI`, spec §0/12 ve §8): ilk 4 hafta bulunabilirlik, beden kaybı payı,
kırık set (stoklu çiftte çekirdek bedeni boş pay), brüt kâr. Yüzdeler bir ondalık: iki ondalıklı
değerin bir kez yarım yukarı yuvarlanmışı (rapor KOLLAR bölümü iki ondalık basar; tek yuvarlama
kuralı), brüt kâr tam TL. `satirlar`: bileşimin desenleri ve her desenin mağaza sayısı (çoktan aza),
koşunun adı (`kosu`) ve ikizse ikizin adı (`ayni`).

`surum` içeriğin özetidir (tarih ve commit yok): aynı girdiden iki üretim bayt bayt aynıdır.
"""

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
OYUN = CIKTI / "oyun.json"
ANALIZ = CIKTI / "analiz.json"
DIZI = "beden-paket"
HEDEF = KOK.parents[1] / "site" / "src" / "data" / "senaryolar" / f"{DIZI}.json"
BUTCE = 500 * 1024

PAKET_TIPLERI = (1, 2, 3, "magaza")
ADETLER = (7, 12)
# yol 0'ın tasarımlı ana kolları (oyun.KOLLAR; p2_ham ablasyondur, demoya girmez): (K, adet) → kol
KOLLAR = {(1, 7): "p1", (2, 7): "p2", (1, 12): "p1_12", (3, 12): "p3_12", ("magaza", 12): "pm_12"}

PARAMETRELER = [
    {"ad": "paket_tipi", "etiket": "Paket tipi sayısı", "degerler": list(PAKET_TIPLERI),
     "deger_etiketleri": {"1": "1 paket tipi", "2": "2 paket tipi", "3": "3 paket tipi",
                          "magaza": "mağazaya özel paket"}},
    {"ad": "adet", "etiket": "Paket büyüklüğü", "degerler": list(ADETLER),
     "deger_etiketleri": {str(a): f"{a} adet" for a in ADETLER}},
]

# kart → (oyun.json ölçütü, basamak)
OZET_OLCUTLERI = {"bulunabilirlik_ilk4": ("bulunabilirlik_ilk4", 1), "beden_kayip_payi": ("beden_kayip_payi", 1),
                  "kirik_cift_pay_yuzde": ("kirik_cift_pay_yuzde", 1), "brut_kar_tl": ("brut_kar_tl", 0)}


def anahtar(K, adet: int) -> str:
    return f"{K}|{adet}"


def yuvarla(deger: float, basamak: int):
    """Yüzde (basamak 1): iki ondalığa, sonra bir kez bir ondalığa yarım yukarı (`rapor.tek_ondalik(rapor.yuv(x,
    2))`, raporun KOLLAR / DEMO bölümleriyle aynı değer); tam sayı: yarım yukarı."""
    d = Decimal(repr(float(deger)))
    if basamak == 0:
        return int(d.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    iki = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(iki.quantize(Decimal(1).scaleb(-basamak), rounding=ROUND_HALF_UP))


def _oku(yol: Path, komut: str) -> dict:
    yol = Path(yol)
    if not yol.is_file():
        raise RuntimeError(f"{yol} yok: önce `{komut}`")
    return json.loads(yol.read_text(encoding="utf-8"))


def esdeger_K(k_egrisi: list[dict], K, adet: int):
    """(adet, K) tasarımıyla aynı desen ve atamayı veren en küçük K: K eğrisinin `ayni` zinciri (her satır
    aynı tasarımlı ilk daha küçük K'yı gösterir); satırı ya da ikizi yoksa K'nın kendisi."""
    k = K
    while True:
        r = next((r for r in k_egrisi if r["adet"] == adet and r["K"] == k), None)
        if r is None or r.get("ayni") is None:
            return k
        k = r["ayni"]


def kol_haritasi(k_egrisi: list[dict]) -> dict[str, tuple[str, str | None]]:
    """Bileşim anahtarı → (koşu adı, ikizse ikizin K'sı): bileşimin en küçük eşdeğer K'sının koşusu
    (`esdeger_K`, `KOLLAR`); koşusu olmayan bileşim haritada yok."""
    out = {}
    for K in PAKET_TIPLERI:
        for a in ADETLER:
            k = esdeger_K(k_egrisi, K, a)
            if (k, a) in KOLLAR:
                out[anahtar(K, a)] = (KOLLAR[(k, a)], None if k == K else str(k))
    return out


def eksik(k_egrisi: list[dict]) -> list[str]:
    h = kol_haritasi(k_egrisi)
    return [anahtar(K, a) for K in PAKET_TIPLERI for a in ADETLER if anahtar(K, a) not in h]


def sonuclar(oyun_kaydi: dict, analiz: dict) -> dict:
    """`{"<K>|<adet>": {"ozet": {...}, "satirlar": [...]}}`, `PARAMETRELER` sırasıyla."""
    kosular = oyun_kaydi.get("kosular") or {}
    out = {}
    for ad, (kol, ikiz_K) in kol_haritasi(analiz["k_egrisi"]).items():
        e = kosular.get(kol)
        if e is None or "olcutler" not in e:
            raise RuntimeError(f"{ad}: oyun.json'da ölçülmüş {kol} koşusu yok (önce python -m beden_paket.oyun izgara)")
        say = {}
        for d in (e.get("atama") or {}).values():
            say[d] = say.get(d, 0) + 1
        satirlar = [{"desen": d, "magaza": n} for d, n in sorted(say.items(), key=lambda x: (-x[1], x[0]))]
        out[ad] = {"ozet": {kart: yuvarla(e["olcutler"][alan], b) for kart, (alan, b) in OZET_OLCUTLERI.items()},
                   "satirlar": [{**r, "kosu": kol, "ayni": None if ikiz_K is None else f"K = {ikiz_K}"}
                                for r in satirlar]}
    return out


def _surum(govde: dict) -> str:
    m = json.dumps(govde, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(m.encode("utf-8")).hexdigest()[:12]


def uret(oyun_kaydi: dict | None = None, analiz: dict | None = None) -> dict:
    """Demo dosyasının içeriği: `{surum, parametreler, sonuclar}`."""
    oyun_kaydi = _oku(OYUN, "python -m beden_paket.oyun izgara") if oyun_kaydi is None else oyun_kaydi
    analiz = _oku(ANALIZ, "python analiz.py") if analiz is None else analiz
    govde = {"parametreler": PARAMETRELER, "sonuclar": sonuclar(oyun_kaydi, analiz)}
    return {"surum": _surum(govde), **govde}


def metin(icerik: dict) -> str:
    """JSON metni; bütçeyi (`BUTCE`) aşarsa `ValueError` (spec §8)."""
    m = json.dumps(icerik, ensure_ascii=False, indent=1)
    if len(m.encode("utf-8")) >= BUTCE:
        raise ValueError(f"senaryo dosyası bütçeyi aşıyor: {len(m.encode('utf-8'))} bayt ≥ {BUTCE}")
    return m


def yaz(icerik: dict, yol: Path = HEDEF) -> Path:
    yol = Path(yol)
    yol.write_text(metin(icerik) + "\n", encoding="utf-8", newline="\n")
    return yol


if __name__ == "__main__":
    print(f"yazıldı: {yaz(uret())}")
