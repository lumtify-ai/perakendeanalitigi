"""Demo kadranının senaryolarını üretir (elle koşulur; build'in parçası
DEĞİL — site spec §7). `cikti/yol0/` zaten kalibre edilmiş, koşulmuş
JSON'ları içerir; bu script yalnız onları okur, yeniden oynatmaz.

    .venv/Scripts/python senaryolar.py

Kadran üç eksenli: alım oranı (60/80/100) × yöntem (kural / tahmin_taban /
tahmin) × koli kuralı (A/B/C) = 27 kombinasyon. `kural` ve `tahmin_taban`
sütunları kalibrasyonun ROS güvenlik stoku ailesiyle koşulur (bkz.
`kos._TABAN_AILESI` ve `kalibrasyon.Kalibrasyon.varsayilan_ss` — burada
ROS sabitlenmiş, çünkü `tahmin_taban` yalnız ROS ile koşuldu; `kural`
sütunu bu yüzden aynı aileyle eşlenip adil kalıyor).

`kirik_cift` tek başına yanıltıcıdır (stoksuz bir çift "kırık" sayılmaz,
ama hiç raf yoksa yanlışlıkla iyi görünür) — kadran onun yerine
`kirik_cift_pay_yuzde`'yi gösterir (stoklu çiftler içindeki kırık payı,
bkz. `replenishment.olcutler.hesapla`).
"""
import json
import subprocess
from dataclasses import replace
from datetime import date
from pathlib import Path

from replenishment import sabitler
from replenishment.kos import _TABAN_AILESI, _dosya_adi, senaryo_anahtari

KOLI_SECENEKLERI = ("A", "B", "C")
YONTEM_SECENEKLERI = ("kural", "tahmin_taban", "tahmin")
# kos._TABAN_AILESI'den DOĞRUDAN import edilir (yeniden bildirilmez) —
# tahmin_taban zaten yalnız bu aileyle koşuldu; kural sütunu adil kıyas
# için aynı aileyle eşlenir, ikisi drift edemez.

PARAMETRELER = [
    {"ad": "alim", "etiket": "Depo alımı (planın yüzdesi)", "degerler": [60, 80, 100]},
    {
        "ad": "yontem", "etiket": "İhtiyaç hesabı", "degerler": list(YONTEM_SECENEKLERI),
        "deger_etiketleri": {
            "kural": "kural tabanlı",
            "tahmin_taban": "LightGBM + taban kural",
            "tahmin": "yalnız LightGBM",
        },
    },
    {
        "ad": "koli", "etiket": "Koli kuralı", "degerler": list(KOLI_SECENEKLERI),
        "deger_etiketleri": {"A": "eşik + şişme", "B": "karşılama oranı", "C": "ikisi birlikte"},
    },
]

_OZET_OLCUTLERI = (
    "bulunabilirlik", "kayip_orani", "satisa_donme_gun",
    "magaza_stok_son", "toplama_maliyeti_tl", "kirik_cift_pay_yuzde",
)

HEDEF = Path(__file__).resolve().parents[2] / "site" / "src" / "data" / "senaryolar" / "depodan-magazaya.json"


def _surum() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        sha = "yerel"
    return f"{sha} {date.today().isoformat()}"


def _senaryo_dict(alim: int, yontem: str, koli: str) -> dict:
    ss = _TABAN_AILESI if yontem in ("kural", "tahmin_taban") else None
    d = {"yontem": yontem, "alim": alim / 100, "koli": koli}
    if ss is not None:
        d["ss"] = ss
    return d


def uret(cikti: Path) -> dict:
    """`cikti/yol0/*.json`'dan 27 kombinasyonu okuyup demo kadranının
    `sonuclar` sözlüğünü kurar; anahtar sırası `{alim}|{yontem}|{koli}`
    (PARAMETRELER sırasıyla aynı, Demo.astro'nun `:has()` zincirini
    kurduğu sıra)."""
    sonuclar: dict[str, dict] = {}
    for alim in PARAMETRELER[0]["degerler"]:
        for yontem in YONTEM_SECENEKLERI:
            for koli in KOLI_SECENEKLERI:
                senaryo = _senaryo_dict(alim, yontem, koli)
                dosya = cikti / "yol0" / f"{_dosya_adi(senaryo_anahtari(senaryo))}.json"
                olcut = json.loads(dosya.read_text(encoding="utf-8"))
                anahtar = f"{alim}|{yontem}|{koli}"
                sonuclar[anahtar] = {
                    "ozet": {ad: olcut[ad] for ad in _OZET_OLCUTLERI},
                    "satirlar": [],
                }
    return sonuclar


def yaz(icerik: dict, yol: Path) -> None:
    metin = json.dumps(icerik, ensure_ascii=False, indent=1)
    boyut = len(metin.encode("utf-8"))
    if boyut >= 500 * 1024:
        raise ValueError(f"Senaryo dosyası bütçeyi aşıyor: {boyut} bayt ≥ 500 KB (site spec §7)")
    yol.write_text(metin, encoding="utf-8")


if __name__ == "__main__":
    icerik = {"surum": _surum(), "parametreler": PARAMETRELER, "sonuclar": uret(sabitler.CIKTI)}
    yaz(icerik, HEDEF)
    print(f"yazildi: {HEDEF}")
