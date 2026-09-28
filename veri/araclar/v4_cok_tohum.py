"""v4 çok tohumlu sağlamlık kontrolü: kalibrasyon bantları (spec §8.2) ve
öğrenilebilirlik eşikleri (spec §8.3) farklı tohumlarda tutuyor mu?

YALNIZ ÖLÇÜM: hiçbir kalibrasyon düğmesini ya da test eşiğini değiştirmez.
Ölçütler `tests/v4/test_kalibrasyon.py`, `test_ogrenilebilirlik.py` ve
`test_talep.py`'deki yardımcılarla birebir hesaplanır; bantlar o testlerin
assert'lerinden kopyadır.

Kullanım (`veri/` dizininden):

    python araclar/v4_cok_tohum.py --tohum 2026   # bir tohumu koş, JSON'a ekle
    python araclar/v4_cok_tohum.py --tablo        # JSON'dan tabloyu bas + yaz
    python araclar/v4_cok_tohum.py                # bütün tohumlar sırayla + tablo

Her TAM koşusu ~5 dk; tohum başına ayrı süreç belleği tamamen bırakır.
Sonuçlar `cikti/v4_cok_tohum.json`, tablo `cikti/v4_cok_tohum.md`.
"""

import argparse
import gc
import json
import subprocess
import sys
import time
from pathlib import Path

VERI = Path(__file__).resolve().parents[1]
for p in (VERI, VERI / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

TOHUMLAR = [2026, 1, 2, 3, 4]
CIKTI = VERI / "cikti"
JSON_YOLU = CIKTI / "v4_cok_tohum.json"
MD_YOLU = CIKTI / "v4_cok_tohum.md"


def _aralik(a, b):
    return lambda x: a <= x <= b


# (anahtar, bant metni, geçer mi) — test assert'leriyle birebir.
OLCUTLER = [
    ("online_payi_2023", "0,15–0,20", _aralik(0.15, 0.20)),
    ("online_payi_2024", "0,15–0,20", _aralik(0.15, 0.20)),
    ("online_payi_2025", "0,15–0,20", _aralik(0.15, 0.20)),
    ("online_iade", "0,25–0,30", _aralik(0.25, 0.30)),
    ("collection_str", "0,55–0,70", _aralik(0.55, 0.70)),
    ("bulunabilirlik_basic_nos", "0,85–0,95", _aralik(0.85, 0.95)),
    ("bulunabilirlik_collection", "0,70–0,85", _aralik(0.70, 0.85)),
    ("ikame_payi", "0,20–0,40", _aralik(0.20, 0.40)),
    ("plan_option_mape", "0,40–0,55", _aralik(0.40, 0.55)),
    ("plan_kategori_ay_mape_SS24", "0,10–0,20", _aralik(0.10, 0.20)),
    ("plan_kategori_ay_mape_AW24", "0,10–0,20", _aralik(0.10, 0.20)),
    ("outlet_akisi_orani", "0,8–1,2", _aralik(0.8, 1.2)),
    ("sure_sn", "< 600", lambda x: x < 600),
    ("kumeleme_ari", "0,4–0,8", _aralik(0.4, 0.8)),
    ("esneklik_saf_goreli_hata", "> 0,4", lambda x: x > 0.4),
    ("esneklik_kampanya_goreli_hata", "≤ 0,2", lambda x: x <= 0.2),
    ("trend_ss25_p", "< 0,05", lambda x: x < 0.05),
    ("trend_ss25_fark", "(bilgi)", None),
    ("trend_ss23_fark", "(bilgi)", None),
    ("trend_kayma", "SS25 − SS23 fark > 0", lambda x: x > 0),
    ("acilis_orta_sayisi", "= 4", lambda x: x == 4),
    ("acilis_orta_kapsama_max", "< 0,60 (4'ün en büyüğü)", lambda x: x < 0.60),
    ("tedarikci_spearman", "≥ 0,5", lambda x: x >= 0.5),
]


def olc(tohum: int) -> dict:
    import pandas as pd

    from perakende_veri.v4.magaza import Olcek
    from perakende_veri.v4.tablolar import gizli_gercek
    from perakende_veri.v4.uret import tablolari_uret
    from tests.v4 import test_kalibrasyon as tk
    from tests.v4 import test_ogrenilebilirlik as to
    from tests.v4 import test_talep as tt

    bas = time.perf_counter()
    t, w, ham = tablolari_uret(Olcek.TAM, donus_ham=True, tohum=tohum)
    sure = time.perf_counter() - bas
    print(f"tohum {tohum}: tablolari_uret(TAM) {sure:.1f} sn", flush=True)
    gizli = gizli_gercek(w, ham)

    o: dict = {"tohum": tohum, "sure_sn": sure}
    for y, v in tk.online_payi(t).items():
        o[f"online_payi_{y}"] = v
    o["online_iade"] = tk.online_iade(t)
    o["collection_str"] = tk.collection_str(w, t)["str"]
    for k, v in tk.bulunabilirlik(w, ham).items():
        o[f"bulunabilirlik_{k}"] = v
    o["ikame_payi"] = tk.ikame_payi(gizli)
    for k, v in tk.plan_hatasi(w).items():
        o[f"plan_{k}"] = v
    talep, gelen = tt._outlet_orani(w, ham)
    o["outlet_akisi_orani"] = talep / gelen

    sz = t["sezon"]
    lansmanlar = set(pd.to_datetime(sz.loc[sz["dalga"] == 1, "lansman_tarihi"]))
    og = to.olcumler(t, gizli, to.plan28_hesapla(w), lansmanlar)
    o["kumeleme_ari"] = og["kumeleme"]["ari"]
    o["esneklik_saf_goreli_hata"] = og["saf"]["goreli_hata"]
    o["esneklik_saf_eps_hat"] = og["saf"]["eps_hat"]
    o["esneklik_saf_eps"] = og["saf"]["eps"]
    o["esneklik_kampanya_goreli_hata"] = og["kampanya"]["goreli_hata"]
    o["esneklik_kampanya_eps_hat"] = og["kampanya"]["eps_hat"]
    o["esneklik_kampanya_eps"] = og["kampanya"]["eps"]
    o["esneklik_kampanya_sayisi"] = og["kampanya"]["kampanya_sayisi"]
    o["trend_ss25_p"] = og["trend"]["p"]
    o["trend_ss25_fark"] = og["trend"]["fark"]
    o["trend_ss23_fark"] = og["trend_ss23"]["fark"]
    o["trend_kayma"] = og["trend"]["fark"] - og["trend_ss23"]["fark"]
    orta = {m: v["kapsama"] for m, v in og["acilis"].items() if v["sezon_ortasi"]}
    o["acilis_orta_sayisi"] = len(orta)
    o["acilis_orta_kapsama_max"] = max(orta.values()) if orta else float("nan")
    o["acilis_orta_kapsama"] = orta
    o["tedarikci_spearman"] = og["tedarikci"]["spearman"]

    del t, w, ham, gizli, og
    gc.collect()
    return o


def _oku() -> dict:
    if JSON_YOLU.exists():
        return json.loads(JSON_YOLU.read_text(encoding="utf-8"))
    return {}


def _bicim(x) -> str:
    if isinstance(x, int):
        return str(x)
    if abs(x) < 1e-3 and x != 0:
        return f"{x:.1e}"
    if abs(x) >= 100:
        return f"{x:.0f}"
    return f"{x:.3f}"


def tablo(sonuc: dict) -> str:
    tohumlar = [t for t in TOHUMLAR if str(t) in sonuc] + sorted(
        int(t) for t in sonuc if int(t) not in TOHUMLAR
    )
    bas = ["ölçüt", "bant / eşik"] + [f"t={t}" for t in tohumlar] + ["min", "max", "geçen"]
    satirlar = ["| " + " | ".join(bas) + " |", "|" + "---|" * len(bas)]
    for anahtar, bant, gecer in OLCUTLER:
        degerler = [sonuc[str(t)].get(anahtar) for t in tohumlar]
        hucre, gecen = [], 0
        for v in degerler:
            if v is None:
                hucre.append("—")
                continue
            if gecer is None:
                hucre.append(_bicim(v))
                continue
            ok = bool(gecer(v))
            gecen += ok
            hucre.append(f"{_bicim(v)} {'✓' if ok else '✗'}")
        var = [v for v in degerler if v is not None]
        mn = _bicim(min(var)) if var else "—"
        mx = _bicim(max(var)) if var else "—"
        say = "—" if gecer is None else f"{gecen}/{len(var)}"
        satirlar.append("| " + " | ".join([anahtar, bant, *hucre, mn, mx, say]) + " |")
    return "\n".join(satirlar) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tohum", type=int, action="append")
    ap.add_argument("--tablo", action="store_true")
    a = ap.parse_args()
    CIKTI.mkdir(exist_ok=True)

    if a.tohum:
        for t in a.tohum:
            o = olc(t)
            sonuc = _oku()
            sonuc[str(t)] = o
            JSON_YOLU.write_text(json.dumps(sonuc, indent=1, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(o, indent=1, ensure_ascii=False), flush=True)
    elif not a.tablo:
        for t in TOHUMLAR:  # her tohum ayrı süreçte: bellek tamamen bırakılır
            subprocess.run([sys.executable, __file__, "--tohum", str(t)], check=True)

    if a.tablo or not a.tohum:
        md = "# v4 çok tohumlu sağlamlık\n\n" + tablo(_oku())
        MD_YOLU.write_text(md, encoding="utf-8")
        print(md)


if __name__ == "__main__":
    main()
