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
    {
        "ad": "verici_cover_esigi",
        "etiket": "Gönderen mağazada asgari cover (hafta)",
        "degerler": [6, 14, 18, 26],
    },
    {
        "ad": "alici_cover_tavani",
        "etiket": "Alıcı mağazada azami cover (hafta)",
        "degerler": [0, 3, 6, 14],
        # 0 = üçüncü kapı kapalı; alıcı yalnız kırık ya da stoksuz olabilir.
        # Yayımlanmış referans senaryo budur.
        "deger_etiketleri": {"0": "kapalı"},
    },
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
    for verici in PARAMETRELER[0]["degerler"]:
        for tavan in PARAMETRELER[1]["degerler"]:
            # min_satis kadrandan çıktı: sabit 1'de kalıyor, demo artık
            # verici eşiği (plan büyüklüğü) ile alıcı tavanı (plan isabeti)
            # arasındaki ayrımı gösteriyor.
            p = replace(
                Parametreler(),
                verici_cover_esigi=float(verici),
                alici_cover_tavani=float(tavan),
            )
            for yontem in PARAMETRELER[2]["degerler"]:
                plan, ozet = degerlendirme.boru_hatti(con, karar, p, yontem)
                # kayip_satis yalnız burada okunur: çözüm girdisi değil ölçüt.
                # Demo bu metrik olmadan gevşek bir alıcı tavanının planı
                # büyütürken isabetini düşürdüğünü gösteremez.
                ozet["kayip_yakalama_yuzde"] = round(
                    degerlendirme.kayip_satis_yakalama(plan, con, karar) * 100, 1
                )
                sonuclar[f"{verici}|{tavan}|{yontem}"] = {"ozet": ozet, "satirlar": []}
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
    print(f"yazildi: {HEDEF}")
