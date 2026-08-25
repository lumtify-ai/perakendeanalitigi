"""Demo senaryolarını üretir (elle koşulur; build'in parçası DEĞİL — site spec §7).

    .venv/Scripts/python senaryolar.py
"""
import json
import subprocess
from dataclasses import replace
from datetime import date
from pathlib import Path

from blok_transfer import degerlendirme
from blok_transfer.cekirdek import veri
from blok_transfer.cekirdek.parametreler import Parametreler

PARAMETRELER = [
    {"ad": "cover_esigi", "etiket": "Gönderen mağazada cover eşiği (hafta)", "degerler": [4, 6, 8, 12]},
    {"ad": "min_satis", "etiket": "Alıcı mağazada asgari haftalık satış (adet)", "degerler": [0, 1, 2]},
    {"ad": "yontem", "etiket": "Çözüm yöntemi", "degerler": ["greedy", "mip"]},
]
HEDEF = Path(__file__).resolve().parents[2] / "site" / "src" / "data" / "senaryolar" / "blok-transfer.json"


def _surum() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        sha = "yerel"
    return f"{sha} {date.today().isoformat()}"


def uret(con, karar) -> dict:
    sonuclar = {}
    for cover in PARAMETRELER[0]["degerler"]:
        for min_satis in PARAMETRELER[1]["degerler"]:
            p = replace(Parametreler(), cover_esigi=float(cover), min_satis=float(min_satis))
            for yontem in PARAMETRELER[2]["degerler"]:
                _, ozet = degerlendirme.boru_hatti(con, karar, p, yontem)
                sonuclar[f"{cover}|{min_satis}|{yontem}"] = {"ozet": ozet, "satirlar": []}
    return {"surum": _surum(), "parametreler": PARAMETRELER, "sonuclar": sonuclar}


def yaz(icerik: dict, yol: Path) -> None:
    metin = json.dumps(icerik, ensure_ascii=False, indent=1)
    boyut = len(metin.encode("utf-8"))
    if boyut >= 500 * 1024:
        raise ValueError(f"Senaryo dosyası bütçeyi aşıyor: {boyut} bayt ≥ 500 KB (site spec §7)")
    yol.write_text(metin, encoding="utf-8")


if __name__ == "__main__":
    con = veri.baglan()
    yaz(uret(con, veri.karar_tarihi(con)), HEDEF)
    print(f"yazıldı: {HEDEF}")
