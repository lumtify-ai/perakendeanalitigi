"""v4 CRM (B) çok tohumlu kalibrasyon kontrolü (spec §8 "Çok tohum").

A bir kez kurulur (`sabitler.TOHUM` = 2026) ve bütün B tohumları aynı
girdiyle koşar (`tablolari_uret_crm(girdi=...)`). Her tohumdan sonra
tablolar ve ham sonuç bırakılır (tek tohum tepe ~19 GB). Dosyaya yazılmaz:
ölçütler bellekteki tablolardan `tests/v4/crm/test_crm_kalibrasyon.py`'nin
yardımcılarıyla birebir hesaplanır; bantlar oradaki `BANTLAR`'dır.

Kabul: her bant ≥ 4/5 tohumda, yayımlanan tohum (CRM_TOHUM = 4242) bütün
bantlarda. Tablo tohumların gerçekten farklı sonuç verdiğini de gösterir
(fiş, kart payı, yorum sayısı satırları).

Kullanım (`veri/` dizininden):

    python araclar/v4_crm_cok_tohum.py                    # 5 tohum, TAM
    python araclar/v4_crm_cok_tohum.py --tohum 4242       # yalnız bir tohum
    python araclar/v4_crm_cok_tohum.py --kucuk            # duman (A KUCUK)
    python araclar/v4_crm_cok_tohum.py --tablo            # JSON'dan tabloyu bas
    python araclar/v4_crm_cok_tohum.py --etiket tur2      # çıktı adlarına ek

Sonuç `cikti/v4_crm_cok_tohum[_etiket].json` (tohum başına, her tohumdan
sonra yazılır), tablo `cikti/v4_crm_cok_tohum[_etiket].md`.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

VERI = Path(__file__).resolve().parents[1]
for p in (VERI, VERI / "src", VERI / "araclar"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

TOHUMLAR = [4242, 1, 2, 3, 4]
CIKTI = VERI / "cikti"


def _yollar(etiket: str | None, kucuk: bool) -> tuple[Path, Path]:
    ad = "v4_crm_cok_tohum" + ("_kucuk" if kucuk else "") + (f"_{etiket}" if etiket else "")
    return CIKTI / f"{ad}.json", CIKTI / f"{ad}.md"


def _oku(yol: Path) -> dict:
    return json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}


def kos(tohumlar: list[int], kucuk: bool, json_yolu: Path) -> None:
    from v4_crm_hiz import bellek_gb

    from perakende_veri.v4.crm.girdi import girdi_kur
    from perakende_veri.v4.crm.uret import tablolari_uret_crm
    from perakende_veri.v4.magaza import Olcek
    from tests.v4.crm import test_crm_kalibrasyon as tk

    t0 = time.perf_counter()
    girdi = girdi_kur(Olcek.KUCUK if kucuk else Olcek.TAM)
    a_sure = time.perf_counter() - t0
    t0 = time.perf_counter()
    a_ozet = tk.a_satis_ozeti(girdi)
    print(f"A kurulumu {a_sure:.1f} sn; A satış özeti {time.perf_counter() - t0:.1f} sn; "
          f"bellek {bellek_gb()[0]:.1f} GB", flush=True)

    for tohum in tohumlar:
        bas = time.perf_counter()
        tablolar, ham = tablolari_uret_crm(girdi=girdi, tohum=tohum, donus_ham=True)
        b_sure = time.perf_counter() - bas
        t1 = time.perf_counter()
        o = tk.kalibrasyon_olcutleri(tablolar, ham, a_ozet)
        o["tohum"] = tohum
        o["b_sure_sn"] = b_sure
        o["olcum_sn"] = time.perf_counter() - t1
        o["adim_sn"] = {k: round(v, 1) for k, v in ham.sure.items()}
        o["crm_adim_sn"] = {k.strip(): round(v, 1) for k, v in ham.crm.sure.items()}
        del tablolar, ham
        gc.collect()
        simdi, tepe = bellek_gb()
        o["bellek_sonra_gb"] = simdi
        o["tepe_gb"] = tepe
        sonuc = _oku(json_yolu)
        sonuc[str(tohum)] = o
        json_yolu.write_text(json.dumps(sonuc, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"tohum {tohum}: B {b_sure:.0f} sn, ölçüm {o['olcum_sn']:.0f} sn, bellek {simdi:.1f} GB "
              f"(tepe {tepe:.1f})", flush=True)
        print("  " + ", ".join(f"{k}={o[k]:.4g}" for k, *_ in tk.BANTLAR), flush=True)


def _bicim(x) -> str:
    if isinstance(x, bool):
        return str(int(x))
    if isinstance(x, int):
        return f"{x:,}"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    if abs(x) < 1:
        return f"{x:.4f}"
    return f"{x:.3f}"


def tablo(sonuc: dict) -> str:
    from tests.v4.crm import test_crm_kalibrasyon as tk

    tohumlar = [t for t in TOHUMLAR if str(t) in sonuc] + sorted(
        int(t) for t in sonuc if int(t) not in TOHUMLAR)
    bas = ["ölçüt", "bant / hedef"] + [f"t={t}" for t in tohumlar] + ["geçen", "4242"]

    def satirlar(liste):
        out = ["| " + " | ".join(bas) + " |", "|" + "---|" * len(bas)]
        for anahtar, ad, bant, gecer in liste:
            hucre, gecen, n, t4242 = [], 0, 0, "—"
            for t in tohumlar:
                v = sonuc[str(t)].get(anahtar)
                if v is None:
                    hucre.append("—")
                    continue
                if gecer is None:
                    hucre.append(_bicim(v))
                    continue
                ok = bool(gecer(v))
                gecen += ok
                n += 1
                if t == 4242:
                    t4242 = "geçer" if ok else "KALIR"
                hucre.append(f"{_bicim(v)} {'✓' if ok else '✗'}")
            say = "—" if gecer is None else f"{gecen}/{n}"
            out.append("| " + " | ".join([ad, bant, *hucre, say, t4242]) + " |")
        return out

    md = ["## Bantlar (spec §8)", ""] + satirlar(tk.BANTLAR)
    md += ["", "## İzleme satırları", ""] + satirlar(tk.IZLEME)
    sure = [("b_sure_sn", "B süresi (sn, A ve yazma hariç)", "< 1200", lambda x: x < 1200),
            ("tepe_gb", "Süreç tepe belleği (GB, birikimli)", "(bilgi)", None)]
    md += ["", "## Süre, bellek", ""] + satirlar(sure)
    return "\n".join(md) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tohum", type=int, action="append")
    ap.add_argument("--kucuk", action="store_true")
    ap.add_argument("--tablo", action="store_true", help="koşmadan JSON'dan tabloyu bas")
    ap.add_argument("--etiket", default=None)
    a = ap.parse_args()
    CIKTI.mkdir(exist_ok=True)
    json_yolu, md_yolu = _yollar(a.etiket, a.kucuk)
    if not a.tablo:
        kos(a.tohum or TOHUMLAR, a.kucuk, json_yolu)
    md = f"# v4 CRM çok tohumlu kalibrasyon{' (KUCUK)' if a.kucuk else ''}\n\n" + tablo(_oku(json_yolu))
    md_yolu.write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
