"""Demo kadranının senaryoları (elle koşulur; build'in parçası değil).

    cd vakalar/kumeleme
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py   # site/src/data/senaryolar/magaza-gruplama.json

Kadran iki eksenli (spec §8): özellik seti {S1 satış karışımı, S2 karışım + beden + mevsim, S4 çeşitten
arındırılmış S2} × küme sayısı k {4, 5, 6, 7, 8} = 15 bileşim; yöntem k-means (önerinin yöntemi).
Kadranda k kullanıcınındır: hakemsiz k kuralı burada uygulanmaz, demo "k'yı değiştirince ne olur"u
gösterir.

**Yalnız `cikti/sonuc.json`'dan.** Değerler `python -m kumeleme.oyun`'un `demo` bloğundan okunur; bu
dosya kümelemeyi koşmaz, veriyi okumaz. `sonuc.json` yoksa `RuntimeError`.

Sonuç kartları (`OZET_OLCUTLERI`, bu sırayla): hakem uyumu (gizli segmente karşı ARI), kararlılık
(mağazaların %80'iyle 50 kez yeniden kümeleme, tam bölmeyle ortalama ARI; `ogren.kararlilik`), en
küçük kümenin mağaza sayısı, siluet. Oranlar üç ondalık (rapor DEMO bölümü aynı yuvarlamayla basar).
`satirlar`: kümeler büyükten küçüğe, mağaza sayısı ve kümenin en ayırt edici özelliği (`ogren.yorum`).

`surum` içeriğin özetidir (tarih ve commit yok): aynı `sonuc.json`'dan iki üretim bayt bayt aynıdır.
"""

import hashlib
import json
from pathlib import Path

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
SONUC = CIKTI / "sonuc.json"
DIZI = "magaza-gruplama"
HEDEF = KOK.parents[1] / "site" / "src" / "data" / "senaryolar" / f"{DIZI}.json"
BUTCE = 500 * 1024

AILELER = ("S1", "S2", "S4")
KLER = (4, 5, 6, 7, 8)

PARAMETRELER = [
    {"ad": "aile", "etiket": "Özellik seti", "degerler": list(AILELER),
     "deger_etiketleri": {"S1": "satış karışımı", "S2": "karışım + beden + mevsim",
                          "S4": "çeşitten arındırılmış karışım + beden + mevsim"}},
    {"ad": "k", "etiket": "Küme sayısı", "degerler": list(KLER),
     "deger_etiketleri": {str(k): f"{k} küme" for k in KLER}},
]

# kart → (sonuc.json demo alanı, basamak)
OZET_OLCUTLERI = {"hakem_ari": ("ari", 3), "kararlilik": ("kararlilik", 3), "en_kucuk_kume": ("en_kucuk", 0),
                  "siluet": ("siluet", 3)}

_NITELIK = {"alt_kategori": "alt kategori", "fiyat_segmenti": "fiyat segmenti", "kalip": "kalıp"}
_AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım",
          "Aralık")
_FIYAT = {"giris": "giriş", "orta": "orta", "ust": "üst"}
_OLCEK = {"log_ciro": "günlük ciro", "log_m2": "m²", "log_kapasite": "kapasite"}


def ozellik_adi(sutun: str) -> str:
    """Özellik sütununun okunur adı: `karisim/Collection/kalip/regular` → "Collection · kalıp · regular"."""
    p = str(sutun).split("/")
    blok = p[0]
    stoklu = " (stoklu gün başına)" if blok.endswith("_stoklu") else ""
    if blok.startswith("karisim") and len(p) == 4:
        deger = _FIYAT.get(p[3], p[3]) if p[2] == "fiyat_segmenti" else p[3]
        return f"{p[1]} · {_NITELIK.get(p[2], p[2])} · {deger}{stoklu}"
    if blok.startswith("beden") and len(p) == 2:
        return f"beden sırası {p[1]}{stoklu}"
    if blok.startswith("mevsim") and len(p) == 2 and p[1].isdigit() and 1 <= int(p[1]) <= 12:
        return f"{_AYLAR[int(p[1]) - 1]} payı{stoklu}"
    if blok == "olcek" and len(p) == 2:
        return _OLCEK.get(p[1], p[1])
    return str(sutun)


def anahtar(aile: str, k: int) -> str:
    return f"{aile}|{k}"


def yuvarla(deger: float, basamak: int):
    return round(float(deger), basamak) if basamak else int(round(float(deger)))


def oku(yol: Path = SONUC) -> dict:
    yol = Path(yol)
    if not yol.is_file():
        raise RuntimeError(f"{yol} yok: önce `python -m kumeleme.oyun`")
    return json.loads(yol.read_text(encoding="utf-8"))


def sonuclar(sonuc: dict) -> dict:
    """`{"<aile>|<k>": {"ozet": {...}, "satirlar": [...]}}`, `PARAMETRELER` sırasıyla."""
    demo = sonuc.get("demo") or {}
    out = {}
    for a in AILELER:
        for k in KLER:
            d = demo.get(anahtar(a, k))
            if d is None:
                raise RuntimeError(f"{anahtar(a, k)}: sonuc.json'un demo bloğunda yok (önce python -m kumeleme.oyun)")
            out[anahtar(a, k)] = {
                "ozet": {kart: yuvarla(d[alan], b) for kart, (alan, b) in OZET_OLCUTLERI.items()},
                "satirlar": [{"kume": i + 1, "magaza": int(c["magaza"]), "ayirt_edici": ozellik_adi(c["ozellik"])}
                             for i, c in enumerate(d["kumeler"])]}
    return out


def _surum(govde: dict) -> str:
    m = json.dumps(govde, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(m.encode("utf-8")).hexdigest()[:12]


def uret(sonuc: dict | None = None) -> dict:
    """Demo dosyasının içeriği: `{surum, parametreler, sonuclar}`."""
    if sonuc is None:
        sonuc = oku()
    govde = {"parametreler": PARAMETRELER, "sonuclar": sonuclar(sonuc)}
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
