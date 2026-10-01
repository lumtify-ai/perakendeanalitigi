"""v4 CRM (B) çok tohumlu kalibrasyon ve öğrenilebilirlik kontrolü (spec §8
"Çok tohum").

A bir kez kurulur (`sabitler.TOHUM` = 2026) ve bütün B tohumları aynı
girdiyle koşar (`tablolari_uret_crm(girdi=...)`). Her tohumdan sonra
tablolar, ham sonuç ve gizli gerçek bırakılır (tek tohum tepe ~20 GB).
Dosyaya yazılmaz: ölçütler bellekteki tablolardan
`tests/v4/crm/test_crm_kalibrasyon.py` (bantlar, `BANTLAR`) ve
`tests/v4/crm/test_crm_ogrenilebilirlik.py` (öğrenilebilirlik,
`OGRENILEBILIRLIK`) yardımcılarıyla birebir hesaplanır.

Kabul (mekanik, tablonun sonunda "kabul: evet/hayır"): bütün tohumlar
({4242, 1, 2, 3, 4}) ölçülmüş, her bant ve her öğrenilebilirlik ölçütü
≥ 4/5 tohumda, yayımlanan tohum (CRM_TOHUM = 4242) hepsinde. Kabul yoksa
çıkış kodu 1.

Kod imzası: her tohum sonucu B'yi etkileyen kaynakların (src/perakende_veri/
v4 altındaki .py ve kütüphane .jsonl dosyaları, iki ölçüt modülü) sha256
özetini ve commit SHA'sını taşır. JSON'da başka imzalı sonuç varsa uyarılır
ve yeni koşu baştan başlar (eski dosya `.eski.json` olarak saklanır);
`--tablo` imza uyuşmazlığını yalnız uyarır.

Kullanım (`veri/` dizininden):

    python araclar/v4_crm_cok_tohum.py                    # 5 tohum, TAM
    python araclar/v4_crm_cok_tohum.py --tohum 4242       # yalnız bir tohum
    python araclar/v4_crm_cok_tohum.py --kucuk            # duman (A KUCUK)
    python araclar/v4_crm_cok_tohum.py --tablo            # JSON'dan tabloyu bas
    python araclar/v4_crm_cok_tohum.py --etiket tur2      # çıktı adlarına ek
    python araclar/v4_crm_cok_tohum.py --ogrenme-yok      # yalnız bantlar

Sonuç `cikti/v4_crm_cok_tohum[_etiket].json` (tohum başına, her tohumdan
sonra yazılır), tablo `cikti/v4_crm_cok_tohum[_etiket].md`.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

VERI = Path(__file__).resolve().parents[1]
for p in (VERI, VERI / "src", VERI / "araclar"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

TOHUMLAR = [4242, 1, 2, 3, 4]
YAYIMLANAN = 4242
EN_AZ_GECEN = 4
CIKTI = VERI / "cikti"


def _yollar(etiket: str | None, kucuk: bool) -> tuple[Path, Path]:
    ad = "v4_crm_cok_tohum" + ("_kucuk" if kucuk else "") + (f"_{etiket}" if etiket else "")
    return CIKTI / f"{ad}.json", CIKTI / f"{ad}.md"


def _oku(yol: Path) -> dict:
    return json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}


def kod_imzasi() -> dict:
    """B'yi ve ölçütleri etkileyen kaynakların özeti + commit SHA."""
    dosyalar = sorted((VERI / "src" / "perakende_veri" / "v4").rglob("*.py"))
    dosyalar += sorted((VERI / "src" / "perakende_veri" / "v4").rglob("*.jsonl"))
    dosyalar += [VERI / "tests" / "v4" / "crm" / "test_crm_kalibrasyon.py",
                 VERI / "tests" / "v4" / "crm" / "test_crm_ogrenilebilirlik.py"]
    h = hashlib.sha256()
    for d in dosyalar:
        h.update(str(d.relative_to(VERI)).replace("\\", "/").encode())
        h.update(d.read_bytes().replace(b"\r\n", b"\n"))
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=VERI, capture_output=True,
                             text=True, check=True).stdout.strip()
        kirli = bool(subprocess.run(["git", "status", "--porcelain", "--", "src", "tests/v4/crm"], cwd=VERI,
                                    capture_output=True, text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        sha, kirli = "?", True
    return {"kaynak_sha256": h.hexdigest()[:16], "commit": sha + ("+kirli" if kirli else "")}


def _imza_uyusmayan(sonuc: dict, imza: dict) -> list[str]:
    return [t for t, o in sonuc.items() if o.get("imza", {}).get("kaynak_sha256") != imza["kaynak_sha256"]]


def kos(tohumlar: list[int], kucuk: bool, json_yolu: Path, ogrenme: bool = True) -> None:
    from v4_crm_hiz import bellek_gb

    from perakende_veri.v4.crm.girdi import girdi_kur
    from perakende_veri.v4.crm.uret import tablolari_uret_crm
    from perakende_veri.v4.magaza import Olcek
    from tests.v4.crm import test_crm_kalibrasyon as tk
    from tests.v4.crm import test_crm_ogrenilebilirlik as to

    imza = kod_imzasi()
    eski = _oku(json_yolu)
    uyusmayan = _imza_uyusmayan(eski, imza)
    if uyusmayan:
        yedek = json_yolu.with_suffix(".eski.json")
        print(f"UYARI: {json_yolu.name} başka kod imzalı sonuç taşıyor (tohum {', '.join(uyusmayan)}); "
              f"baştan başlanıyor, eski dosya {yedek.name}", flush=True)
        json_yolu.replace(yedek)
    print(f"kod imzası {imza}", flush=True)

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
        o["imza"] = imza
        o["b_sure_sn"] = b_sure
        o["olcum_sn"] = time.perf_counter() - t1
        o["adim_sn"] = {k: round(v, 1) for k, v in ham.sure.items()}
        o["crm_adim_sn"] = {k.strip(): round(v, 1) for k, v in ham.crm.sure.items()}
        gizli = ham.gizli_gercek() if ogrenme else None
        del ham
        gc.collect()
        if ogrenme:
            t1 = time.perf_counter()
            o.update(to.ogrenilebilirlik_olcutleri(tablolar, gizli, girdi.dunya.urunler))
            o["ogrenme_toplam_sn"] = time.perf_counter() - t1
        del tablolar, gizli
        gc.collect()
        simdi, tepe = bellek_gb()
        o["bellek_sonra_gb"] = simdi
        o["tepe_gb"] = tepe
        sonuc = _oku(json_yolu)
        sonuc[str(tohum)] = o
        json_yolu.write_text(json.dumps(sonuc, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"tohum {tohum}: B {b_sure:.0f} sn, ölçüm {o['olcum_sn']:.0f} sn"
              + (f", öğrenme {o['ogrenme_toplam_sn']:.0f} sn" if ogrenme else "")
              + f", bellek {simdi:.1f} GB (tepe {tepe:.1f})", flush=True)
        satirlar = tk.BANTLAR + (to.OGRENILEBILIRLIK if ogrenme else [])
        print("  " + ", ".join(f"{k}={o[k]:.4g}" for k, *_ in satirlar), flush=True)


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


def _tohumlar(sonuc: dict) -> list[int]:
    return [t for t in TOHUMLAR if str(t) in sonuc] + sorted(int(t) for t in sonuc if int(t) not in TOHUMLAR)


def kabul(sonuc: dict) -> tuple[bool, list[str]]:
    """(kabul mü, gerekçe satırları): bütün tohumlar, her ölçüt ≥ 4/5, 4242 hepsinde."""
    from tests.v4.crm import test_crm_kalibrasyon as tk
    from tests.v4.crm import test_crm_ogrenilebilirlik as to

    neden = []
    eksik = [t for t in TOHUMLAR if str(t) not in sonuc]
    if eksik:
        neden.append(f"eksik tohum: {eksik}")
    for anahtar, ad, bant, gecer in tk.BANTLAR + to.OGRENILEBILIRLIK:
        degerler = {t: sonuc[str(t)].get(anahtar) for t in TOHUMLAR if str(t) in sonuc}
        if any(v is None for v in degerler.values()):
            neden.append(f"{ad}: ölçülmemiş tohum")
            continue
        gecen = sum(bool(gecer(v)) for v in degerler.values())
        # eksik tohumda: kalan sayısı izin verilen (5 − 4) kaybı aşarsa
        if len(degerler) - gecen > len(TOHUMLAR) - EN_AZ_GECEN:
            neden.append(f"{ad}: {gecen}/{len(degerler)} (bant {bant})")
        if YAYIMLANAN in degerler and not gecer(degerler[YAYIMLANAN]):
            neden.append(f"{ad}: {YAYIMLANAN} kalır ({_bicim(degerler[YAYIMLANAN])}, bant {bant})")
    return not neden, neden


def tablo(sonuc: dict) -> str:
    from tests.v4.crm import test_crm_kalibrasyon as tk
    from tests.v4.crm import test_crm_ogrenilebilirlik as to

    tohumlar = _tohumlar(sonuc)
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
                if t == YAYIMLANAN:
                    t4242 = "geçer" if ok else "KALIR"
                hucre.append(f"{_bicim(v)} {'✓' if ok else '✗'}")
            say = "—" if gecer is None else f"{gecen}/{n}"
            out.append("| " + " | ".join([ad, bant, *hucre, say, t4242]) + " |")
        return out

    md = ["## Bantlar (spec §8)", ""] + satirlar(tk.BANTLAR)
    md += ["", "## Öğrenilebilirlik (spec §8)", ""] + satirlar(to.OGRENILEBILIRLIK)
    md += ["", "## Öğrenilebilirlik: ikincil satırlar", ""] + satirlar(to.OGRENILEBILIRLIK_IZLEME)
    md += ["", "## İzleme satırları", ""] + satirlar(tk.IZLEME)
    sure = [("b_sure_sn", "B süresi (sn, A ve yazma hariç)", "< 1200", lambda x: x < 1200),
            ("ogrenme_toplam_sn", "Öğrenilebilirlik ölçümü (sn)", "(bilgi)", None),
            ("tepe_gb", "Süreç tepe belleği (GB, birikimli)", "(bilgi)", None)]
    md += ["", "## Süre, bellek", ""] + satirlar(sure)
    imzalar = sorted({json.dumps(sonuc[str(t)].get("imza"), sort_keys=True) for t in tohumlar})
    md += ["", f"Kod imzası: {', '.join(imzalar)}" + ("  **UYARI: tohumlar farklı imzalı**" if len(imzalar) > 1 else "")]
    ok, neden = kabul(sonuc)
    md += ["", f"**kabul: {'evet' if ok else 'hayır'}**"] + [f"- {n}" for n in neden]
    return "\n".join(md) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tohum", type=int, action="append")
    ap.add_argument("--kucuk", action="store_true")
    ap.add_argument("--tablo", action="store_true", help="koşmadan JSON'dan tabloyu bas")
    ap.add_argument("--etiket", default=None)
    ap.add_argument("--ogrenme-yok", action="store_true", help="öğrenilebilirlik ölçütlerini atla")
    a = ap.parse_args()
    CIKTI.mkdir(exist_ok=True)
    json_yolu, md_yolu = _yollar(a.etiket, a.kucuk)
    if a.tablo:
        uy = _imza_uyusmayan(_oku(json_yolu), kod_imzasi())
        if uy:
            print(f"UYARI: tohum {', '.join(uy)} şimdiki koddan farklı imzalı", flush=True)
    else:
        kos(a.tohum or TOHUMLAR, a.kucuk, json_yolu, ogrenme=not a.ogrenme_yok)
    sonuc = _oku(json_yolu)
    md = f"# v4 CRM çok tohumlu kalibrasyon{' (KUCUK)' if a.kucuk else ''}\n\n" + tablo(sonuc)
    md_yolu.write_text(md, encoding="utf-8")
    print(md)
    return 0 if kabul(sonuc)[0] else 1


if __name__ == "__main__":
    sys.exit(main())
