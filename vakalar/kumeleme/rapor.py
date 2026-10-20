"""Mağaza Kümeleme dizisinin (6 yazı, `/magaza-kumeleme/magaza-gruplama/`) yayımlanacak BÜTÜN sayıları
buradan basılır (v4).

    cd vakalar/kumeleme
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m kumeleme.oyun          # cikti/sonuc.json, kumeler.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py             # demo JSON
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py --taslak         # eski koşuyla biçim denetimi

Kalıcı kural: yazıya yeni bir sayı girmeden önce buraya eklenir; ortak sayı denetimi (`cd
vakalar/kumeleme && .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi
../../site/src/content/yazi/magaza-kumeleme/magaza-gruplama --rapor cikti/rapor.txt`) yazılardaki her
sayının bu çıktıda geçtiğini denetler. Sayılar Türkçe basılır (binlik nokta, ondalık virgül, `%12,3`,
`−0,32`). Uydurma sayı yasaktır; elle konmuş anlatı değerleri yalnız ANLATI VARSAYIMLARI'ndadır.
Raporda takvim tarihi geçer (izlenebilirlik); yazılar tarih ve yıl basmaz.

Bölümler (`BOLUMLER`, bu sırayla; spec §5). Başlık sorularının (spec §5) her biri ilgili bölümde tek
bir `SORU n · …` satırıdır (cevap basılan değerlerden):

    VERİ                  kapsam (aday, kümelenen, yeni), dışarıda kalanlar, pencereler
    KURAL                 K1-K4 grupları, ciro eşikleri, bölge × sınıf tablosu
    ÖZELLİKLER            aileler, sütunlar, ağırlık, doldurma; "kaç yol var" matematiği
    ML                    aday tablosu, k ve öneri kuralı, boş siluet, kararlılık-önce açıklaması (R9),
                          yorum, İlk Sevkiyat'a giden kümeler (SORU 7)
    HAKEM                 ARI/AMI/saflık, metropol ayrımı, çapraz tablolar, segment saflığı (SORU 1, 2)
    KARARLILIK            yıllar arası, önyükleme, alt örneklem, K2/K3 yıllar arası (SORU 5)
    YENİ MAĞAZA           bırakbir 5-NN ve merkez (R10), statik kurallar, iki gerçek yeni mağaza (SORU 6)
    ABLASYON              S1-S5, S1 + ölçek, S1 stoklu, sütun orantılı ağırlık (R7) (SORU 3, 4)
    HİKÂYE                sahne, ders kalemleri, hakem doğrulaması, alternatif
    DEMO                  15 bileşim
    ANLATI VARSAYIMLARI
    KORUNUM

Rapor önce tampona yazılır; korunum tutmazsa ya da bir girdi eksik ya da eskiyse (`sonuc.json` yok;
bugünkü paket kodu ya da v4 dosyasıyla yazılmamış; `kumeler.json` ya da demo dosyası `sonuc.json`'dan
üretilenle aynı değil) stdout'a tek satır gitmez, mesaj stderr'e, çıkış kodu 1. `--taslak` eski ya da
eksik girdiyle basar (`sonuc.json` yine gerekir), eksikleri sonda listeler (çıkış kodu 2; bu çıktı
yazılara kaynak olamaz). Basılan her fark ve oran basılan işlenenlerden hesaplanır (`yuv`, `fark`,
`bolum`); tek ondalıklı her fark iki ondalıklı farkın bir kez yuvarlanmışıdır (`fark1`): aynı büyüklüğe
tek değer. Ölçülen süre basılmaz: aynı girdiyle iki koşu bayt bayt aynıdır. Bu dosya veriyi okumaz,
kümelemeyi koşmaz.

Okuma notları: hakemli ölçütler (ARI, AMI, saflık, segment isabeti) hiçbir seçime girmez, sonradan
ölçer. ARI 1 kusursuz eşleşme, 0 rastgele düzeyidir. Önerinin kümeleri gizli segmentle birebir
örtüşürse "kendi satış kümesine isabet" ile "segment isabeti" aynı sayıdır.
"""

import argparse
import contextlib
import io
import json
import math
import sys
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import senaryolar
from kumeleme import oyun

KOK = Path(__file__).resolve().parent
SONUC = oyun.SONUC
KUMELER = oyun.KUMELER

ANLATI_VARSAYIMLARI = {
    "ciro_siniflari": "ciro sınıfı payları: A ilk %20, B sonraki %30, C kalan %50 (Lumoda'nın bugünkü kuralı olarak "
                      "konmuş anlatı varsayımı; spec §4.1)",
    "kadro": "İstanbul mağazaları Ali'nin, Anadolu mağazaları Veli'nin (allocator); Pelin planner; Pars veriyi açan "
             "analist (dizinin kadrosu)",
    "en_kucuk_kume": "en küçük küme en az 3 mağaza: üç mağazadan küçük bir plan grubu kurulmaz (iş kısıtı olarak "
                     "konmuş varsayım)",
    "gecmis_esigi": "26 satışlı haftadan az geçmişi olan mağaza yeni sayılır (yürütücü eşiği)",
}
SEGMENT_ADLARI = ("anadolu_aile", "metropol_genc", "metropol_premium", "sicak_sahil", "soguk_iklim")


# ---------------------------------------------------------------------------
# Biçim
# ---------------------------------------------------------------------------

def _yok(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _sifir_mi(metin: str) -> bool:
    return metin.lstrip("-").replace(".", "").replace(",", "").strip("0") == ""


def s(x, ondalik: int = 0) -> str:
    """Türkçe sayı: 1.234.567 · 0,55 · −3,2 (yuvarlanınca sıfır olan negatif işaretsiz)."""
    if _yok(x):
        return "—"
    if isinstance(x, int) and not isinstance(x, bool) and ondalik == 0:
        metin = f"{x:,}"                                 # tam sayı tam basılır (büyük sayıda kayan nokta yok)
    else:
        metin = f"{yuv(x, ondalik):,.{ondalik}f}"         # yarım yukarı (`yuv`): basılan = `yuv`
    metin = metin.replace(",", "_").replace(".", ",").replace("_", ".")
    if _sifir_mi(metin):
        metin = metin.lstrip("-")
    return metin.replace("-", "−")


def y(x, ondalik: int = 1) -> str:
    """Yüzde, x oran: 0,123 → %12,3; negatif → −%3,2."""
    if _yok(x):
        return "—"
    return yd(100 * float(x), ondalik)


def yd(x, ondalik: int = 1) -> str:
    """Yüzde, x zaten yüzde: 65,102 → %65,1."""
    if _yok(x):
        return "—"
    govde = s(abs(float(x)), ondalik)
    return ("−%" if x < 0 and not _sifir_mi(govde) else "%") + govde


def isaretli(x, ondalik: int = 0) -> str:
    """İşaretli sayı: +1,23 · −0,32 · 0,00."""
    metin = s(x, ondalik)
    return metin if metin.startswith("−") or metin == "—" or _sifir_mi(metin) else "+" + metin


def tl(x) -> str:
    """Tam TL ve milyon TL: 116.405.702 TL (116,4 milyon TL)."""
    return "—" if _yok(x) else f"{s(x)} TL ({s(float(x) / 1e6, 1)} milyon TL)"


def yuv(x, ondalik: int = 0) -> float:
    """`s(x, ondalik)`'ın bastığı değer (yarım yukarı, ondalık aritmetikle)."""
    q = Decimal(1).scaleb(-ondalik)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def fark(a, b, ondalik: int = 0) -> float:
    """b − a, ikisi de `ondalik` hanede basıldığı gibi."""
    return yuv(yuv(b, ondalik) - yuv(a, ondalik), ondalik)


def tek_ondalik(x2) -> float:
    """İki ondalıklı değerin bir kez, yarımda sıfırdan uzağa yuvarlanmışı (ondalık aritmetikle)."""
    return float(Decimal(f"{float(x2):.2f}").quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fark1(a, b) -> float:
    """b − a, bir ondalık: iki ondalıklı farkın (`fark(a, b, 2)`) bir kez yuvarlanmışı. Aynı büyüklüğün iki
    ondalıklı ve bir ondalıklı biçimi raporda tek değerdir; bir ondalıklı düzeylerin farkı değildir."""
    return tek_ondalik(fark(a, b, 2))


def bolum(a, b, ondalik_a: int = 0, ondalik_b: int = 0) -> float | None:
    """a / b, ikisi de basıldığı gibi."""
    payda = yuv(b, ondalik_b)
    return yuv(a, ondalik_a) / payda if payda else None


def oran(n: int, d: int) -> str:
    """Sayım ve yüzdesi: 55/67 (%82,1)."""
    return f"{n}/{d} ({y(n / d)})" if d else f"{n}/{d}"


def pay(x) -> str:
    """Bir pay (0-1) bir ondalıklı yüzde olarak: 0,0371 → %3,7."""
    return y(x, 1)


def puan(a, b) -> str:
    """b − a yüzde puan, bir ondalık (iki ondalıklı yüzdelerin farkının bir kez yuvarlanmışı)."""
    return f"{isaretli(fark1(100 * float(a), 100 * float(b)), 1)} puan"


def baslik(metin: str) -> None:
    print(f"\n=== {metin} ===")


def alt(metin: str) -> None:
    print(f"\n--- {metin} ---")


def soru(n: int, metin: str) -> None:
    print(f"SORU {n} · {metin}")


def tamponla(govde) -> tuple[int, str]:
    """`govde()`yi stdout'u tamponlayarak koşar: (0, metin) ya da korunum bozulursa (1, "") ve mesaj stderr'e."""
    tampon = io.StringIO()
    try:
        with contextlib.redirect_stdout(tampon):
            govde()
    except AssertionError as e:
        print(e, file=sys.stderr)
        return 1, ""
    return 0, tampon.getvalue()


def korunum(denetimler: list[tuple[str, bool]]) -> int:
    """Denetimlerin hepsi tutmalı; tutmayanlar adlarıyla AssertionError. Döner: denetim sayısı."""
    if not denetimler:
        raise AssertionError("korunum: hiç denetim yok")
    hatalar = [ad for ad, ok in denetimler if not bool(ok)]
    if hatalar:
        raise AssertionError("korunum bozuldu:\n  " + "\n  ".join(hatalar))
    return len(denetimler)


def stirling2(n: int, k: int) -> int:
    """n öğeyi k boş olmayan gruba bölmenin yolu (ikinci tür Stirling sayısı)."""
    return sum((-1) ** i * math.comb(k, i) * (k - i) ** n for i in range(k + 1)) // math.factorial(k)


def bilimsel(n: int) -> str:
    """Büyük tam sayının yaklaşık değeri: 5,6 × 10⁴⁴ (üs üst simgeyle; sayı denetimine üs girmez)."""
    us = len(str(n)) - 1
    govde = s(n / 10 ** us, 1)
    ust = str(us).translate(str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹"))
    return f"{govde} × 10{ust}"


# ---------------------------------------------------------------------------
# Girdiler
# ---------------------------------------------------------------------------


@dataclass
class Veri:
    sonuc: dict
    kumeler: dict | None
    demo_dosya: dict | None
    taslak: bool = False
    eksik: list[str] = field(default_factory=list)


def _json(yol: Path) -> dict | None:
    yol = Path(yol)
    return json.loads(yol.read_text(encoding="utf-8")) if yol.is_file() else None


def hazirla(sonuc_yol: Path = SONUC, kumeler_yol: Path = KUMELER, demo_yol: Path = senaryolar.HEDEF,
            taslak: bool = False, kod: str | None = None, veri_izi: list | None = None) -> Veri:
    """Girdileri okur ve kimliklerini denetler. Kesin kipte eski/eksik girdi `RuntimeError`; taslakta
    `Veri.eksik`'e yazılır. `sonuc.json` her iki kipte de gerekir."""
    sonuc = _json(sonuc_yol)
    if sonuc is None:
        raise RuntimeError(f"{sonuc_yol} yok: önce `python -m kumeleme.oyun`")
    kod = oyun.kod_ozeti() if kod is None else kod
    veri_izi = oyun.veri_parmak_izi() if veri_izi is None else veri_izi
    sorun = []
    if sonuc.get("surum") != oyun.KAYIT_SURUMU:
        sorun.append(f"sonuc.json kayıt sürümü {sonuc.get('surum')} (beklenen {oyun.KAYIT_SURUMU})")
    if sonuc.get("kod") != kod:
        sorun.append("sonuc.json bugünkü paket koduyla yazılmamış (önce python -m kumeleme.oyun)")
    if sonuc.get("veri_izi") != veri_izi:
        sorun.append("sonuc.json bugünkü v4 dosyasıyla yazılmamış")
    kumeler = _json(kumeler_yol)
    if kumeler is None:
        sorun.append(f"{Path(kumeler_yol).name} yok")
    demo = _json(demo_yol)
    if demo is None:
        sorun.append(f"{Path(demo_yol).name} yok (önce senaryolar.py)")
    if sorun and not taslak:
        raise RuntimeError("girdi eksik ya da eski:\n  " + "\n  ".join(sorun))
    return Veri(sonuc=sonuc, kumeler=kumeler, demo_dosya=demo, taslak=taslak, eksik=sorun)


# ---------------------------------------------------------------------------
# Kısayollar
# ---------------------------------------------------------------------------


def kapsam(v) -> list[dict]:
    return v.sonuc["veri"]["kapsam"]


def kumelenen(v) -> list[str]:
    return [r["magaza_id"] for r in kapsam(v) if r["kumelenir"]]


def yeniler(v) -> list[dict]:
    return [r for r in kapsam(v) if r["yeni"]]


def magaza(v, m: str) -> dict:
    return next(r for r in kapsam(v) if r["magaza_id"] == m)


def oneri(v) -> dict:
    return v.sonuc["ml"]["oneri"]


def yontem_adi(y_: str) -> str:
    return {"kmeans": "k-means", "ward": "Ward"}.get(y_, y_)


def aile_adi(a: str) -> str:
    return {"S1": "S1 satış karışımı", "S2": "S2 karışım + beden + mevsim", "S4": "S4 çeşitten arındırılmış S2",
            "S5": "S5 S2 + ölçek", "S1+olcek": "S1 + ölçek", "S1_stoklu": "S1 stoklu (çeşitten arındırılmış karışım)"
            }.get(a, a)


def kisa_ad(a: str) -> str:
    return {"S1+olcek": "S1 + ölçek", "S1_stoklu": "S1 stoklu"}.get(a, a)


def oneri_adi(v) -> str:
    o = oneri(v)
    return f"{o['aile']} {yontem_adi(o['yontem'])} k = {o['k']}"


def boyutlar(b) -> str:
    return "/".join(str(int(x)) for x in b)


def sayim(etiket: dict, ids) -> dict:
    out: dict = {}
    for m in ids:
        out[etiket[m]] = out.get(etiket[m], 0) + 1
    return out


def sayim_metni(c: dict, sira=None) -> str:
    anahtarlar = sira if sira is not None else sorted(c, key=lambda a: (-c[a], str(a)))
    return " · ".join(f"{a} {c[a]}" for a in anahtarlar if a in c)


def aday_satiri(v, aile, yontem, k) -> dict:
    return next(r for r in v.sonuc["ml"]["aday_tablosu"]
                if r["aile"] == aile and r["yontem"] == yontem and r["k"] == k)


def _tablo(basliklar: list[str], satirlar: list[list[str]]) -> None:
    gen = [max(len(b), *(len(r[i]) for r in satirlar)) if satirlar else len(b) for i, b in enumerate(basliklar)]
    print("  " + "  ".join(b.ljust(g) for b, g in zip(basliklar, gen)))
    for r in satirlar:
        print("  " + "  ".join(c.ljust(g) for c, g in zip(r, gen)))


# ---------------------------------------------------------------------------
# Bölümler
# ---------------------------------------------------------------------------


def veri_bolumu(v, ek) -> None:
    d = v.sonuc["veri"]
    kum = kumelenen(v)
    yen = yeniler(v)
    print(f"  karar günü {d['karar_gunu']} (SS25'in ilk Collection karar günü; lansman pazartesisi {d['lansman']})")
    print("  mağaza tablosu: " + " · ".join(f"{t} {n}" for t, n in d["tip_sayilari"].items()))
    print(f"  fiziksel (AVM ve Cadde) mağaza: {d['fiziksel']}; outlet ayrı gruptur (kümelenmez), online kapsam dışı")
    for r in d["disarida"]:
        print(f"  kapsam dışı: {r['magaza_id']} {r['ad']} ({r['neden']}; açılış {r['acilis']}"
              + (f", kapanış {r['kapanis']})" if r["kapanis"] else ")"))
    print(f"  aday mağaza (kapsam): {len(kapsam(v))} = kümelenen {len(kum)} + yeni {len(yen)} "
          f"(yeni: {d['gecmis_hafta_esigi']} satışlı haftadan az geçmiş)")
    for r in yen:
        print(f"  yeni mağaza {r['magaza_id']} {r['ad']} ({r['sehir']}, {r['bolge']}, {r['tip']}, "
              f"{s(r['metrekare'])} m²): {r['gecmis_hafta']} satışlı hafta")
    met = [m for m in kum if magaza(v, m)["metropol"]]
    sehir = sayim({m: magaza(v, m)["sehir"] for m in met}, met)
    print(f"  kümelenen {len(kum)} mağaza: metropol {len(met)} ({sayim_metni(sehir)}) · metropol dışı "
          f"{len(kum) - len(met)}; İstanbul {sum(magaza(v, m)['istanbul'] for m in kum)}, Anadolu (İstanbul dışı) "
          f"{len(kum) - sum(magaza(v, m)['istanbul'] for m in kum)}")
    print(f"  kümelenen mağazalarda bölge {len({magaza(v, m)['bolge'] for m in kum})}, şehir "
          f"{len({magaza(v, m)['sehir'] for m in kum})}; tip: "
          + sayim_metni(sayim({m: magaza(v, m)["tip"] for m in kum}, kum)))
    bas, bit = d["ozellik_penceresi"]
    print(f"  özellik penceresi {bas} … {bit} (karar gününden önceki 104 tamamlanmış hafta; karar haftası okunmaz)")
    cb, cbit = d["ciro_penceresi"]
    print(f"  ciro penceresi {cb} … {cbit} (karar gününden önceki 12 ay)")
    ek += [("VERİ: kapsam = kümelenen + yeni", len(kapsam(v)) == len(kum) + len(yen)),
           ("VERİ: kimlikler tekil", len({r["magaza_id"] for r in kapsam(v)}) == len(kapsam(v))),
           ("VERİ: fiziksel = kapsam + dışarıda", d["fiziksel"] == len(kapsam(v)) + len(d["disarida"]))]


def kural_bolumu(v, ek) -> None:
    kr = v.sonuc["kural"]
    e = kr["etiketler"]
    kum = kumelenen(v)
    yen = [r["magaza_id"] for r in yeniler(v)]
    n = len(kum)
    k1 = sayim(e["k1"], kum)
    print(f"  K1 bölge (yayımlanan bölge): {len(k1)} grup: {sayim_metni(k1)} (kümelenen {n})")
    k2 = sayim(e["k2"], kum)
    print(f"  K2 ciro sınıfı (son 12 ayın net cirosu, sıralı): A ilk {y(kr['oranlar']['A'], 0)} → {k2.get('A', 0)}, "
          f"B sonraki {y(kr['oranlar']['B'], 0)} → {k2.get('B', 0)}, C kalan → {k2.get('C', 0)}")
    print(f"    eşikler: A ≥ {tl(kr['esikler']['A'])} · B ≥ {tl(kr['esikler']['B'])}")
    ciro = kr["net_ciro"]
    c = sorted(ciro[m] for m in kum)
    med = (c[(n - 1) // 2] + c[n // 2]) / 2
    print(f"    kümelenen mağazaların net cirosu: en düşük {tl(c[0])} · medyan {tl(med)} · en yüksek {tl(c[-1])}")
    for m in kr["yillik_kisa"]:
        r = magaza(v, m)
        print(f"    12 aydan kısa geçmiş yıllıklaştırıldı: {m} {r['ad']} ({r['gecmis_hafta']} satışlı hafta) → "
              f"{tl(ciro[m])}, sınıf {e['k2'][m]}")
    for m in yen:
        bilgi = f"yıllıklaştırılmış ciro yalnız bilgi: {tl(ciro[m])}" if ciro[m] else "karar gününe dek satışı yok"
        print(f"    yeni mağaza sıralamaya girmez, C alır: {m} ({bilgi})")
    bolgeler = sorted(k1, key=lambda b: (-k1[b], b))
    satir = []
    for b in bolgeler:
        ms = [m for m in kum if e["k1"][m] == b]
        sc = sayim(e["k2"], ms)
        satir.append([b, str(len(ms))] + [str(sc.get(x, 0)) for x in "ABC"])
    alt("bölge × ciro sınıfı (kümelenen mağazalar)")
    _tablo(["bölge", "mağaza", "A", "B", "C"], satir)
    ist = [m for m in kum if magaza(v, m)["istanbul"]]
    si = sayim(e["k2"], ist)
    print(f"  İstanbul {len(ist)} mağaza: A {si.get('A', 0)} · B {si.get('B', 0)} · C {si.get('C', 0)}")
    k3 = sayim(e["k3"], kum)
    print(f"  K3 bölge × ciro sınıfı (hücre {kr['k3_en_az']} mağazadan azsa komşu sınıfla birleşir): {len(k3)} grup: "
          f"{sayim_metni(k3)}")
    k4 = sayim(e["k4"], kum)
    print(f"  K4 konum (metropol ya da şehrin iklim sınıfı; turistik belde sıcak sahil): {len(k4)} grup: {sayim_metni(k4)}")
    for m in yen:
        print(f"  yeni mağaza {m}: K1 {e['k1'][m]} · K2 {e['k2'][m]} · K3 {e['k3'][m]} · K4 {e['k4'][m]}")
    na, nb = int(math.floor(kr["oranlar"]["A"] * n + 0.5)), int(math.floor(kr["oranlar"]["B"] * n + 0.5))
    ek += [("KURAL: K1-K4 kapsamın her mağazasında", all(set(e[x]) == {r["magaza_id"] for r in kapsam(v)}
                                                          for x in oyun.KURALLAR)),
           ("KURAL: K2 = yarım yukarı A/B, C kalan", (k2.get("A", 0), k2.get("B", 0)) == (na, nb)),
           ("KURAL: yeni mağaza C", all(e["k2"][m] == "C" for m in yen)),
           ("KURAL: A eşiği > B eşiği", kr["esikler"]["A"] > kr["esikler"]["B"]),
           ("KURAL: grupların toplamı kümelenen", all(sum(sayim(e[x], kum).values()) == n for x in oyun.KURALLAR))]


def ozellik_bolumu(v, ek) -> None:
    oz = v.sonuc["ozellik"]
    blok_adi = {"karisim": "karışım", "beden": "beden eğrisi", "mevsim": "mevsimsellik", "olcek": "ölçek",
                "karisim_stoklu": "karışım (stoklu)", "beden_stoklu": "beden (stoklu)", "mevsim_stoklu": "mevsim (stoklu)"}
    satir = []
    for ad, r in oz.items():
        satir.append([aile_adi(ad), f"{r['magaza']} × {r['sutun']}", str(r["standart_sutun"]),
                      " + ".join(f"{blok_adi.get(b, b)} {r['blok_sutun'][b]}" for b in r["bloklar"]),
                      str(sum(r["doldurulan"].values())), s(sum(r["dusen_satis"].values())), r["kimlik"][:12]])
    _tablo(["aile", "mağaza × özellik", "standartta", "bloklar (sütun)", "doldurulan hücre", "düşen adet", "kimlik"],
           satir)
    s1 = oz["S1"]
    print(f"  satış karışımı (S1): {s1['alt_blok']['karisim']} alt blok = iki line grubu (Collection, Basic+NOS) × "
          "alt kategori, fiyat segmenti, kalıp; her nitelikte paylar bire toplanır")
    print("  ağırlık (Ruling R7): her blok toplam varyans 1, blok içinde her alt blok eşit (karışımda her biri 1/6); "
          "ablasyonda sütun orantılı")
    print("  beden eğrisi: beden sırası 1-5 payı, beden seti içinde, setler eşit ağırlıklı; mevsim: 12 ayın satışlı gün "
          "başına payı; ölçek: log günlük ciro, log m², log kapasite (karışımla aynı vektöre yalnız ablasyonda)")
    print("  çeşitten arındırma (S4): pay ham adet yerine stoklu gün başına satıştan; gözlenmeyen hücre nötr doldurulur")
    o = oneri(v)
    n = len(kumelenen(v))
    yol = stirling2(n, o["k"])
    print(f"  {n} mağaza × {s1['sutun']} özellik (S1); {n} mağazayı {o['k']} boş olmayan gruba bölmenin yolu: "
          f"{s(yol)} (yaklaşık {bilimsel(yol)}; {len(str(yol))} basamak)")
    ek += [("ÖZELLİKLER: aileler kümelenen mağazalarda", all(r["magaza"] == n for r in oz.values())),
           ("ÖZELLİKLER: blok sütunları toplamı", all(sum(r["blok_sutun"].values()) == r["sutun"] for r in oz.values())),
           ("ÖZELLİKLER: öneri ailesinin kimliği", oz[o["aile"]]["kimlik"] == o["ozellik_kimligi"])]


def ml_bolumu(v, ek) -> None:
    ml = v.sonuc["ml"]
    o = oneri(v)
    alt("aday tablosu: S1, S2 × k-means, Ward × k (hakem ARI sonradan ölçülür, seçime girmez)")
    satir = []
    for r in ml["aday_tablosu"]:
        satir.append([r["aile"], yontem_adi(r["yontem"]), str(r["k"]), s(r["siluet"], 3), s(r["w"], 1),
                      str(r["en_kucuk"]), boyutlar(r["boyutlar"]), "evet" if r["uygun"] else "hayır",
                      "aday" if r["secilen"] else "", s(r["kararlilik"], 3) if r["secilen"] else "",
                      ("öneri" if r["oneri"] else ("eşit" if r["esit"] else "")), s(r["ari"], 3)])
    _tablo(["aile", "yöntem", "k", "siluet", "dirsek w", "en küçük", "boyutlar", "uygun", "", "kararlılık", "", "ARI"],
           satir)
    print(f"  k kuralı (hakemsiz): en küçük küme ≥ {ml['en_kucuk_kume']} mağaza; kalanlarda siluet en "
          f"iyisinden {s(ml['silu_esitlik'], 2)} içindeki en küçük k; dirsek basılır, kurala girmez")
    print(f"  öneri kuralı (Ruling R9): adaylar arasında siluet birincil ({s(ml['silu_esitlik'], 2)} içinde eşit); "
          f"eşitlerde bölme kararlılığı ({s(ml['kararlilik_esitlik'], 2)} içinde eşit), sonra küçük k, S1, k-means")
    print(f"  kararlılık: mağazaların {y(ml['kararlilik_oran'], 0)}'i {ml['kararlilik_ornek']} kez iadesiz çekilip "
          "yeniden kümelenir, tam bölmeyle ortalama ARI")
    aday = [r for r in ml["aday_tablosu"] if r["secilen"]]
    for r in aday:
        print(f"  aday {r['aile']} {yontem_adi(r['yontem'])} k = {r['k']}: siluet {s(r['siluet'], 3)}, kararlılık "
              f"{s(r['kararlilik'], 3)} (bölme {s(r['bolme_kararlilik'], 3)}), boyutlar {boyutlar(r['boyutlar'])}"
              f"{', siluette eşit' if r['esit'] else ''}")
    satir_o = aday_satiri(v, o["aile"], o["yontem"], o["k"])
    ayni = [r for r in aday if r["kimlik"] == o["kimlik"] and r["yontem"] != o["yontem"]]
    print(f"ÖNERİ: {oneri_adi(v)}" + (f" ({', '.join(yontem_adi(r['yontem']) for r in ayni)} aynı bölme)" if ayni else "")
          + f"; boyutlar {boyutlar(o['boyutlar'])}, siluet {s(satir_o['siluet'], 3)}, kararlılık "
          f"{s(satir_o['kararlilik'], 3)}, kimlik {o['kimlik'][:12]}")
    alt(f"boş siluet (sütunlar bağımsız karıştırılmış, yapısız veri; {ml['bos_ornek']} karıştırma ortalaması)")
    for b in ml["bos_siluet"]:
        r = aday_satiri(v, b["aile"], b["yontem"], b["k"])
        print(f"  {b['aile']} {yontem_adi(b['yontem'])} k = {b['k']}: boş {s(b['bos_siluet'], 3)} · gerçek "
              f"{s(r['siluet'], 3)}")
    print("  S1 ve S2'de boş siluet aynı düzeyde: siluet aileler arasında karşılaştırılabilir (öneri kuralının gerekçesi)")
    kk = ml["kararlilik_once"]
    print(f"  açıklama (Ruling R9): kararlılığı birincil yapan kural (ilk taslak) {kk['aile']} "
          f"{yontem_adi(kk['yontem'])} k = {kk['k']}'ü seçerdi (kararlılık {s(kk['kararlilik'], 3)}, siluet "
          f"{s(kk['siluet'], 3)}); onun hakem ARI'si {s(kk['ari'], 3)}. Kural hakem sonucu görüldükten sonra "
          "denetleyicinin önceden yazdığı biçime döndü: seçimin hakemden tamamen bağımsız olduğu söylenemez")
    he = ml["hakemle_en_iyi"]
    print(f"  hakemle seçilseydi en iyi (uygun aday satırları): {he['aile']} {yontem_adi(he['yontem'])} k = {he['k']}, "
          f"ARI {s(he['ari'], 3)} (öneri ARI {s(satir_o['ari'], 3)})")
    alt(f"önerinin yorumu: her kümenin en ayırt edici {oyun.YORUM_N} özelliği (ortalama z; küme ortalaması / genel)")
    boy = sayim(o["etiket"], list(o["etiket"]))
    for c, liste in ml["yorum"].items():
        parca = [f"{senaryolar.ozellik_adi(f['ozellik'])} z {isaretli(f['z'], 2)} ({pay(f['kume_ort'])} / "
                 f"{pay(f['genel_ort'])})" for f in liste]
        print(f"  küme {c} ({boy[int(c)]} mağaza): " + "; ".join(parca))
    alt("İlk Sevkiyat'a giden kümeler (kumeler.json, git'te)")
    k = v.kumeler or {}
    print(f"  öneri {oneri_adi(v)} kimlik {o['kimlik'][:12]}; K1-K4 kapsamın {len(kapsam(v))} mağazasında; yeni "
          f"mağazalar {', '.join(f'{m} → küme {c}' for m, c in sorted(k.get('ml', {}).get('yeni_magaza', {}).get('atama', {}).items()))} "
          "(5-NN statik atama); gizli segment ayrı ve yalnız ölçüm için (kahin küme kolu)")
    soru(7, "Kümeye göre plan İlk Sevkiyat'ta mağazanın kendi geçmişinden ve LightGBM'den iyi mi; ciro sınıfına göre "
            "plan ne veriyor; gizli segment ne kadar ileride? Cevap İlk Sevkiyat raporunun KÜME bölümünde "
            "(vakalar/allocation/cikti/rapor.txt); bu rapor yalnız girdisini (kumeler.json) verir")
    ek += [("ML: tek öneri satırı", sum(r["oneri"] for r in ml["aday_tablosu"]) == 1),
           ("ML: öneri bir aday", satir_o["secilen"] and satir_o["kimlik"] == o["kimlik"]),
           ("ML: öneri boyutları kümelenen", sum(o["boyutlar"]) == len(kumelenen(v))),
           ("ML: öneri etiketi kümelenen mağazalarda", sorted(o["etiket"]) == sorted(kumelenen(v))),
           ("ML: boyut satırları toplamı", all(sum(r["boyutlar"]) == len(kumelenen(v)) for r in ml["aday_tablosu"])),
           ("ML: en küçük = boyutların en küçüğü", all(r["en_kucuk"] == min(r["boyutlar"]) for r in ml["aday_tablosu"])),
           ("ML: ARI aralıkta", all(-1 <= r["ari"] <= 1 for r in ml["aday_tablosu"]))]


def _capraz_bas(c: dict, ad: str) -> None:
    _tablo([ad] + [str(x) for x in c["sutunlar"]] + ["toplam"],
           [[str(sat)] + [str(x) for x in r] + [str(sum(r))] for sat, r in zip(c["satirlar"], c["degerler"])])


def hakem_bolumu(v, ek) -> None:
    h = v.sonuc["hakem"]
    g = h["gruplar"]
    n = len(kumelenen(v))
    print(f"  gizli segment (yalnız ölçüm; {n} kümelenen mağaza): " + " · ".join(f"{a} {b}" for a, b in
                                                                          h["segment_sayilari"].items()))
    adlar = {"k1": "K1 bölge", "k2": "K2 ciro sınıfı", "k3": "K3 bölge × ciro", "k4": "K4 konum",
             "ml": f"öneri ({oneri_adi(v)})"}
    _tablo(["gruplama", "grup", "ARI", "AMI", "saflık"],
           [[adlar[a], str(r["grup"]), s(r["ari"], 3), s(r["ami"], 3), y(r["toplam_saflik"])] for a, r in g.items()])
    print("  saflık: her grubun çoğunluk segmentindeki mağazaların toplam payı")
    soru(1, f"Bölge ve ciro sınıfı gizli segmente ne kadar oturuyor? K1 bölge ARI {s(g['k1']['ari'], 3)} (AMI "
            f"{s(g['k1']['ami'], 3)}) · K2 ciro sınıfı ARI {s(g['k2']['ari'], 3)} (AMI {s(g['k2']['ami'], 3)}) · K3 "
            f"bölge × ciro ARI {s(g['k3']['ari'], 3)} (AMI {s(g['k3']['ami'], 3)}); 1 kusursuz, 0 rastgele düzeyi")
    m4, mm = g["k4"]["bolum"], g["ml"]["bolum"]
    soru(2, f"Satış karışımından bulunan kümeler ne kadar oturuyor; konum kuralı ne kadarını zaten biliyor? öneri "
            f"ARI {s(g['ml']['ari'], 3)} · K4 konum ARI {s(g['k4']['ari'], 3)} (AMI {s(g['k4']['ami'], 3)}); "
            f"metropol dışında ({m4['metropol_disi']['n']} mağaza) K4 ARI {s(m4['metropol_disi']['ari'], 3)}, "
            f"metropolde ({m4['metropol']['n']} mağaza, {m4['metropol']['segment']} segment) K4 tek grup, öneri ARI "
            f"{s(mm['metropol']['ari'], 3)}")
    alt("metropol / metropol dışı (her grupta ayrı ARI)")
    _tablo(["gruplama", "metropol grup", "metropol ARI", "dışı grup", "dışı ARI"],
           [[adlar[a], str(r["bolum"]["metropol"]["grup"]), s(r["bolum"]["metropol"]["ari"], 3),
             str(r["bolum"]["metropol_disi"]["grup"]), s(r["bolum"]["metropol_disi"]["ari"], 3)] for a, r in g.items()])
    print(f"  metropol {m4['metropol']['n']} mağazada {m4['metropol']['segment']} segment, metropol dışı "
          f"{m4['metropol_disi']['n']} mağazada {m4['metropol_disi']['segment']} segment")
    km = h["k4_ml"]
    print(f"  K4 ↔ öneri (hakemsiz, iki bölmenin uyumu): ARI {s(km['ari'], 3)}")
    _capraz_bas(km["capraz"], "K4 \\ öneri kümesi")
    for a in ("k1", "k2", "k4", "ml"):
        alt(f"çapraz tablo: {adlar[a]} × gizli segment")
        _capraz_bas(g[a]["capraz"], adlar[a])
    alt("segment saflığı: segmentin en çok düştüğü grup, segmentin oradaki payı, grubun o segmentten payı")
    for a in ("ml", "k4", "k1"):
        for seg, r in g[a]["saflik"].items():
            print(f"  {adlar[a]} · {seg} ({r['n']}): en çok {r['kume']} ({oran(round(r['pay'] * r['n']), r['n'])}); "
                  f"grubun bu segmentten payı {y(r['kume_payi'])}")
    seg_k1 = g["k1"]["capraz"]
    if "anadolu_aile" in seg_k1["sutunlar"]:
        j = seg_k1["sutunlar"].index("anadolu_aile")
        top = sum(r[j] for r in seg_k1["degerler"])
        mar = {sat: r[j] for sat, r in zip(seg_k1["satirlar"], seg_k1["degerler"])}
        ist = sum(1 for m in kumelenen(v) if magaza(v, m)["istanbul"] and v.sonuc["gizli_kapsam"][m] == "anadolu_aile")
        print(f"  anadolu_aile segmentinin {top} mağazası: Marmara'da {mar.get('Marmara', 0)}, İstanbul'da {ist}")
    si = h["sehir_iklim"]
    print(f"  vakanın şehir → iklim tablosu (K4 ve yeni mağaza statikleri) simülatörün gizli iklim ekseniyle "
          f"şehir başına örtüşüyor: {si['ortusen']}/{si['sehir']} şehir; farklı: "
          + (", ".join(f"{f['sehir']} (vaka {f['vaka']}, simülatör {'/'.join(f['simulator'])})" for f in si["farkli"])
             or "yok")
          + ". Sentetik zincir gerçek coğrafya üstüne kurulu: konum kuralının başarısı kısmen verinin kurgusu (R5)")
    ek += [(f"HAKEM: {a} çapraz toplamı = kümelenen", sum(map(sum, r["capraz"]["degerler"])) == n) for a, r in g.items()]
    ek += [("HAKEM: şehir iklim sayımı", si["ortusen"] + len(si["farkli"]) == si["sehir"])]
    ek += [("HAKEM: segment sayıları toplamı", sum(h["segment_sayilari"].values()) == n),
           ("HAKEM: outlet/online ölçülmedi", not ({"outlet", "online"} & set(h["segment_sayilari"]))),
           ("HAKEM: metropol + dışı = kümelenen", all(r["bolum"]["metropol"]["n"] + r["bolum"]["metropol_disi"]["n"] == n
                                                      for r in g.values())),
           ("HAKEM: öneri ARI = aday tablosu", g["ml"]["ari"] == aday_satiri(v, oneri(v)["aile"], oneri(v)["yontem"],
                                                                            oneri(v)["k"])["ari"])]


def kararlilik_bolumu(v, ek) -> None:
    kr = v.sonuc["kararlilik"]
    n = len(kumelenen(v))
    d = kr["donem"]
    print(f"  yıllar arası: aynı yöntemle ({oneri_adi(v)}) her dönemin yalnız kendi 52 haftasıyla kurulan bölmeler")
    for r in d:
        print(f"    dönem {r['donem']}: {r['bas']} … {r['bit']} ({r['hafta']} hafta), {r['magaza']} mağaza, boyutlar "
              f"{boyutlar(kr['donem_boyutlar'][r['donem']])}, hakem ARI {s(kr['donem_hakem_ari'][r['donem']], 3)}")
    for m in kr["disarida"]:
        sh = kr["satisli_hafta_disarida"][m]
        print(f"    dışarıda {m} {magaza(v, m)['ad']}: satışlı hafta " + " · ".join(f"{a} {b}" for a, b in sh.items())
              + f" (eşik {v.sonuc['veri']['gecmis_hafta_esigi']})")
    ari = next(iter(kr["ari"].values()))
    print(f"  öneri yıllar arası ARI {s(ari, 3)} ({d[0]['magaza']} mağaza)")
    ka = kr["kural_ari"]
    print(f"  K2 ciro sınıfı yıllar arası ARI {s(ka['k2'], 3)} (aynı {kr['kural_magaza']} mağaza, dönem sonundan önceki "
          f"12 ayla; sınıfı değişen {oran(kr['k2_degisen'], kr['kural_magaza'])}) · K3 {s(ka['k3'], 3)} · K1 ve K4 "
          "statik (tanım gereği 1)")
    deg = kr["degisme"]
    hic = sum(1 for x in deg.values() if x == 0)
    oynak = sorted(deg, key=lambda m: (-deg[m], m))[:6]
    print(f"  önyükleme ({kr['ornek']} iadeli çekiliş, Macar eşlemesi): ARI {s(kr['onyukleme_ari'], 3)}; mağaza başına "
          f"ortalama küme değişme sıklığı {y(kr['degisme_ort'])}; hiç değişmeyen {oran(hic, n)}")
    print("  en oynak mağazalar: " + " · ".join(f"{m} {magaza(v, m)['ad']} {y(deg[m], 0)}" for m in oynak))
    print(f"  alt örneklem kararlılığı (%80 × 50, ML bölümü) {s(kr['alt_orneklem'], 3)}")
    soru(5, f"Kümeler sezondan sezona sabit mi? öneri yıllar arası ARI {s(ari, 3)} ({d[0]['magaza']} mağaza), "
            f"önyüklemede ARI {s(kr['onyukleme_ari'], 3)} ve mağaza başına değişme {y(kr['degisme_ort'])}; K2 ciro "
            f"sınıfı yıllar arası ARI {s(ka['k2'], 3)}")
    ek += [("KARARLILIK: ortak + dışarıda = kümelenen", d[0]["magaza"] + len(kr["disarida"]) == n),
           ("KARARLILIK: değişme her kümelenen mağazada", sorted(deg) == sorted(kumelenen(v))),
           ("KARARLILIK: değişme 0-1", all(0 <= x <= 1 for x in deg.values())),
           ("KARARLILIK: dönem boyutları ortak mağazalar", all(sum(b) == d[0]["magaza"] for b in kr["donem_boyutlar"].values())),
           ("KARARLILIK: alt örneklem = aday tablosu", kr["alt_orneklem"] == aday_satiri(
               v, oneri(v)["aile"], oneri(v)["yontem"], oneri(v)["k"])["kararlilik"])]


def _ozet_satirlari(oz: dict) -> list[list[str]]:
    adlar = {"hepsi": "hepsi", "metropol": "metropol", "metropol_disi": "metropol dışı"}
    return [[adlar[g], oran(r["dogru_kume"], r["n"]), oran(r["dogru_segment"], r["n"]),
             oran(r["kume_dogru_segment"], r["n"]), oran(r["taban_kume"], r["n"]), oran(r["taban_segment"], r["n"])]
            for g, r in oz.items()]


def yeni_magaza_bolumu(v, ek) -> None:
    ym = v.sonuc["yeni_magaza"]
    n = len(kumelenen(v))
    print("  bırakbir: kümelenen her mağaza yeniymiş gibi; kümeler o mağaza olmadan kurulur, mağaza yalnız statikleriyle "
          "(bölge, metropol, iklim, tip, log m², enlem) atanır")
    adlar = {"knn": f"en yakın {ym['komsu']} komşu (5-NN, varsayılan)", "merkez": "en yakın küme merkezi"}
    for y_, r in ym["yontemler"].items():
        alt(f"{adlar[y_]}: bırakbir bölmesi tam bölmeyle aynı {oran(r['ayni_bolme'], n)}")
        _tablo(["grup", "küme isabeti", "segment isabeti", "kendi satış kümesinin segmenti", "taban: en büyük küme",
                "taban: en sık segment"], _ozet_satirlari(r["ozet"]))
    k, mz = ym["yontemler"]["knn"]["ozet"], ym["yontemler"]["merkez"]["ozet"]
    grup_adi = {"hepsi": "hepsi", "metropol": "metropol", "metropol_disi": "metropol dışı"}
    print("  5-NN − merkez küme isabeti: " + " · ".join(
        f"{grup_adi[g]} {puan(mz[g]['dogru_kume'] / mz[g]['n'], k[g]['dogru_kume'] / k[g]['n'])}" for g in k))
    print("  Ruling R10: varsayılan 5-NN sonuçlar görüldükten sonra seçildi (ölçüt hakemsiz: kendi satış kümesine "
          "isabet); komşu sayısı 5 önceden yazılmıştı; iki yöntem de basılır")
    alt("statik kurallar: yeni mağaza grubunu satış görmeden alır (segment isabeti: grubun kendisi hariç çoğunluğu)")
    for a, oz in ym["statik_kural"].items():
        ad = {"k1": "K1 bölge", "k4": "K4 konum"}[a]
        print(f"  {ad}: " + " · ".join(f"{g} {oran(r['dogru_segment'], r['n'])}" for g, r in
                                       zip(("hepsi", "metropol", "metropol dışı"), oz.values())))
    alt("iki gerçek yeni mağaza (satış görmeden, statiklerle; kumeler.json 5-NN atamasını taşır)")
    cs = ym["kume_cogunluk_segment"]
    for m, r in ym["gercek"].items():
        dogru = r["knn_segment"] == r["gizli"]
        print(f"  {m} {r['ad']} ({r['sehir']}, {r['bolge']}, {r['tip']}, {s(r['metrekare'])} m², "
              f"{'metropol' if r['metropol'] else 'metropol dışı'}, {r['gecmis_hafta']} satışlı hafta): 5-NN → küme "
              f"{r['knn']} (çoğunluğu {r['knn_segment']}), merkez → küme {r['merkez']}; gizli segment {r['gizli']}: "
              f"{'isabet' if dogru else 'ıska'}; K4 {r['k4']}, K2 {r['k2']}")
    print("  önerinin kümelerinin çoğunluk segmenti: " + " · ".join(f"küme {c} {sg}" for c, sg in cs.items()))
    kh, km = k["hepsi"], k["metropol"]
    kd = k["metropol_disi"]
    isabet = [m for m, r in ym["gercek"].items() if r["knn_segment"] == r["gizli"]]
    soru(6, f"Yeni mağaza satış görmeden doğru kümeye konabiliyor mu? bırakbirde 5-NN {oran(kh['dogru_kume'], kh['n'])}; "
            f"metropolde {oran(km['dogru_kume'], km['n'])}, metropol dışında {oran(kd['dogru_kume'], kd['n'])}; en büyük "
            f"küme tabanı {oran(kh['taban_kume'], kh['n'])}; iki gerçek yeni mağazanın "
            f"{len(isabet)}'i doğru ({', '.join(isabet) or 'yok'})")
    for y_, r in ym["yontemler"].items():
        oz = r["ozet"]
        ek += [(f"YENİ: {y_} hepsi = metropol + dışı", all(oz["hepsi"][c] == oz["metropol"][c] + oz["metropol_disi"][c]
                                                          for c in oz["hepsi"])),
               (f"YENİ: {y_} bırakbir n = kümelenen", oz["hepsi"]["n"] == n and len(r["magazalar"]) == n)]
    ek += [("YENİ: gerçek yeni mağazalar = kapsamın yenileri", sorted(ym["gercek"]) == sorted(
        r["magaza_id"] for r in yeniler(v)))]


def _izgara_satiri(r: dict) -> list[str]:
    return [yontem_adi(r["yontem"]), str(r["k"]), s(r["siluet"], 3), boyutlar(r["boyutlar"]), s(r["ari"], 3),
            s(r["ami"], 3), s(r["ari_k2"], 3)]


def ablasyon_bolumu(v, ek) -> None:
    ab = v.sonuc["ablasyon"]
    k, yo = ab["sabit_k"], ab["sabit_yontem"]
    print(f"  her aile: hakemsiz k (aynı kural) ve önerinin yöntemi ve k'sıyla ({yontem_adi(yo)} k = {k}); ARI ve AMI "
          "gizli segmente, ARI K2 ciro sınıfına (hakemsiz: bölme ciroya ne kadar benziyor)")
    satir, sabit = [], {}
    for agirlik, tablo in (("alt blok", ab["alt_blok"]), ("sütun", ab["sutun"])):
        for aile, rows in tablo.items():
            for r in rows:
                if r["secilen"]:
                    satir.append([aile_adi(aile), agirlik, "hakemsiz k"] + _izgara_satiri(r))
            sb = next(r for r in rows if r["yontem"] == yo and r["k"] == k)
            sabit[(aile, agirlik)] = sb
            satir.append([aile_adi(aile), agirlik, f"k = {k}"] + _izgara_satiri(sb))
    _tablo(["aile", "ağırlık", "seçim", "yöntem", "k", "siluet", "boyutlar", "ARI", "AMI", "ARI (K2)"], satir)
    u = ab["uyum"]
    print(f"  iki ailenin bölmeleri arasında uyum ({yontem_adi(yo)} k = {k}, hakemsiz ARI): "
          + " · ".join(f"{kisa_ad(a.split('|')[0])} ↔ {kisa_ad(a.split('|')[1])} {s(x, 3)}" for a, x in u.items()))
    print(f"  K2 ciro sınıfı ↔ öneri ARI {s(ab['k2_ml_ari'], 3)}")
    s1, s1o = sabit[("S1", "alt blok")], sabit[("S1+olcek", "alt blok")]
    s2, s5 = sabit[("S2", "alt blok")], sabit[("S5", "alt blok")]

    def hakemsiz(aile: str) -> str:
        return "; ".join(f"{yontem_adi(r['yontem'])} k = {r['k']} siluet {s(r['siluet'], 3)} ARI {s(r['ari'], 3)} "
                         f"(K2 ile {s(r['ari_k2'], 3)})" for r in ab["alt_blok"][aile] if r["secilen"])

    print(f"  hakemsiz k ile S1 + ölçek: {hakemsiz('S1+olcek')}")
    eniyi_s1o = max(r["siluet"] for r in ab["alt_blok"]["S1+olcek"] if r["secilen"])
    oneri_siluet = aday_satiri(v, oneri(v)["aile"], oneri(v)["yontem"], oneri(v)["k"])["siluet"]
    if yuv(eniyi_s1o, 3) > yuv(oneri_siluet, 3):
        print(f"  S1 + ölçek'in hakemsiz silueti {s(eniyi_s1o, 3)}, önerininki {s(oneri_siluet, 3)}: ölçek aday "
              "ailelerine konsaydı siluet kuralı ciroya benzeyen bölmeyi seçerdi (ölçek karışımla aynı vektöre girmez)")
    soru(3, f"Ölçeği karışıma katmak neyi bozuyor? k = {k}'te S1 ARI {s(s1['ari'], 3)} → S1 + ölçek "
            f"{s(s1o['ari'], 3)}; S2 {s(s2['ari'], 3)} → S5 {s(s5['ari'], 3)}; K2 ciro sınıfıyla uyum S1 "
            f"{s(s1['ari_k2'], 3)} → S1 + ölçek {s(s1o['ari_k2'], 3)}")
    s1s, s4 = sabit[("S1_stoklu", "alt blok")], sabit[("S4", "alt blok")]
    print(f"  hakemsiz k ile S1 stoklu: {hakemsiz('S1_stoklu')}")
    soru(4, f"Çeşit yanlılığı ne kadar? hakemsiz k ile çeşitten arındırılmış karışım (S1 stoklu) "
            + "; ".join(f"{yontem_adi(r['yontem'])} k = {r['k']} ARI {s(r['ari'], 3)}"
                        for r in ab["alt_blok"]["S1_stoklu"] if r["secilen"])
            + f", ham karışım (S1) ARI {s(s1['ari'], 3)}; k = {k}'te {yontem_adi(yo)} S1 stoklu {s(s1s['ari'], 3)} "
            f"(ham bölmeyle uyumu {s(u['S1|S1_stoklu'], 3)}); S2 {s(s2['ari'], 3)}, S4 {s(s4['ari'], 3)} "
            f"(uyum {s(u['S2|S4'], 3)})")
    s1c, s2c = sabit[("S1", "sütun")], sabit[("S2", "sütun")]
    print(f"  Ruling R7 ablasyonu (sütun orantılı ağırlık, k = {k}): S1 ARI {s(s1['ari'], 3)} → {s(s1c['ari'], 3)}, "
          f"S2 {s(s2['ari'], 3)} → {s(s2c['ari'], 3)}")
    tum = [(aile, agirlik, r) for agirlik, t in (("alt blok", ab["alt_blok"]), ("sütun", ab["sutun"]))
           for aile, rows in t.items() for r in rows if r["uygun"]]
    en = max(tum, key=lambda x: (x[2]["ari"], -x[2]["k"]))
    print(f"  bütün ablasyon ızgarasında hakemle en iyi (uygun satırlar): {aile_adi(en[0])}, {en[1]}, "
          f"{yontem_adi(en[2]['yontem'])} k = {en[2]['k']}, ARI {s(en[2]['ari'], 3)}")
    ml = aday_satiri(v, "S1", yo, k)
    ek += [("ABLASYON: S1 alt blok = aday tablosu", s1["kimlik"] == ml["kimlik"] and s1["siluet"] == ml["siluet"]),
           ("ABLASYON: her ailede iki yöntemin hakemsiz seçimi en çok bir", all(
               sum(r["secilen"] and r["yontem"] == y_ for r in rows) <= 1 for t in (ab["alt_blok"], ab["sutun"])
               for rows in t.values() for y_ in ("kmeans", "ward"))),
           ("ABLASYON: boyutlar kümelenen", all(sum(r["boyutlar"]) == len(kumelenen(v)) for t in
                                                (ab["alt_blok"], ab["sutun"]) for rows in t.values() for r in rows))]


def _kalem_adi(f: str) -> str:
    return senaryolar.ozellik_adi(f) + " payı"


def _kunye(v, m: str, h: dict) -> str:
    r = h["magazalar"][m]
    return (f"{m} {r['ad']} ({r['sehir']}, {r['bolge']}, {r['tip']}, {s(r['metrekare'])} m²; K2 {r['k2']}, K3 {r['k3']}, "
            f"K4 {r['k4']}; öneri kümesi {r['ml_kume']}; net ciro {tl(r['net_ciro'])})")


def _sahne(v, h: dict, ad: str) -> None:
    a, b = h["cift1"]
    c, d = h["cift2"]
    print(f"  {ad} 1. çift (aynı grupta, farklı satan): {a} – {b}; karışım uzaklığı {s(h['mesafe'][0], 3)} (üst "
          f"{y(1 - h['kuyruk'][0], 0)} eşiği {s(h['esikler']['ust'], 3)}, fark {isaretli(fark(h['esikler']['ust'], h['mesafe'][0], 3), 3)})")
    print(f"  {ad} 2. çift (farklı grupta, aynı satan): {c} – {d}; karışım uzaklığı {s(h['mesafe'][1], 3)} (alt "
          f"{y(h['kuyruk'][1], 0)} eşiği {s(h['esikler']['alt'], 3)})")
    for m in dict.fromkeys((a, b, c, d)):
        print(f"    {_kunye(v, m, h)}")
    for k1, k2 in zip(h["kalemler"], h["kalemler2"]):
        print(f"    {_kalem_adi(k1['ozellik'])}: {a} {pay(k1['a'])} · {b} {pay(k1['b'])} (fark {puan(k1['a'], k1['b'])}); "
              f"{c} {pay(k2['c'])} · {d} {pay(k2['d'])} (fark {puan(k2['c'], k2['d'])})")
    dg = h["dogrulama"] or {}
    print(f"    hakem (yalnız doğrulama): " + " · ".join(f"{m} {sg}" for m, sg in dg.get("segmentler", {}).items())
          + f"; 1. çift farklı {'evet' if dg.get('cift1_farkli') else 'hayır'}, 2. çift aynı "
          f"{'evet' if dg.get('cift2_ayni') else 'hayır'}")
    print(f"    gevşeyen: {'; '.join(h['gevseyen']) or 'yok'}; doğrulamada elenen sahne {h['elenen']}")


def hikaye_bolumu(v, ek) -> None:
    h = v.sonuc["hikaye"]
    print("  merdiven (spec §6): 1. çift aynı bölge ve ciro sınıfında iki metropol mağazası (biri İstanbul), karışım "
          "uzaklığı üst çeyrekte, öneri kümeleri farklı; 2. çift farklı bölgede biri İstanbul biri Anadolu (metropol "
          "dışı), uzaklık alt çeyrekte, aynı öneri kümesi; uzaklık S1 standart uzayında öklid")
    _sahne(v, h, "SAHNE")
    ortak = set(h["cift1"]) & set(h["cift2"])
    if ortak:
        m = sorted(ortak)[0]
        print(f"  ortak mağaza {m} {h['magazalar'][m]['ad']}: komşusundan ayrılıyor, bir Anadolu mağazası gibi satıyor "
              f"(İstanbul mağazası Ali'nin, Anadolu mağazası Veli'nin)")
    print(f"  hakemsiz seçim aynı sahneyi veriyor: {'evet' if h['hakemsiz_ayni'] else 'hayır'}")
    if h.get("alternatif"):
        _sahne(v, h["alternatif"], "ALTERNATİF")
    kum = set(kumelenen(v))
    ek += [("HİKÂYE: sahnenin mağazaları kümelenen", set(h["cift1"]) | set(h["cift2"]) <= kum),
           ("HİKÂYE: 1. çift üst eşiğin üstünde", h["mesafe"][0] >= h["esikler"]["ust"]),
           ("HİKÂYE: 2. çift alt eşiğin altında", h["mesafe"][1] <= h["esikler"]["alt"]),
           ("HİKÂYE: öneri kimliği aynı", h["ml"]["kimlik"] == oneri(v)["kimlik"]),
           ("HİKÂYE: ML kümeleri öneriyle aynı", all(r["ml_kume"] == oneri(v)["etiket"][m]
                                                    for m, r in h["magazalar"].items()))]


def demo_bolumu(v, ek) -> None:
    son = senaryolar.sonuclar(v.sonuc)
    print(f"  {len(son)} bileşim: özellik seti {{{', '.join(senaryolar.AILELER)}}} × k "
          f"{{{', '.join(str(k) for k in senaryolar.KLER)}}}, k-means; kartlar hakem ARI, kararlılık, en küçük küme, siluet")
    _tablo(["bileşim", "ARI", "kararlılık", "en küçük", "siluet", "kümeler"],
           [[a, s(r["ozet"]["hakem_ari"], 3), s(r["ozet"]["kararlilik"], 3), str(r["ozet"]["en_kucuk_kume"]),
             s(r["ozet"]["siluet"], 3), boyutlar(x["magaza"] for x in r["satirlar"])] for a, r in son.items()])
    o = oneri(v)
    dosya = v.demo_dosya
    if dosya is None or dosya != senaryolar.uret(v.sonuc):
        if not v.taslak:
            raise AssertionError("DEMO: site dosyası senaryolar.uret() ile aynı değil")
        print("  [eksik: demo dosyası güncel değil]")
    else:
        print(f"  site dosyası {senaryolar.HEDEF.name}: sürüm {dosya['surum']} (içeriğin özeti)")
    d5 = v.sonuc["demo"].get(senaryolar.anahtar(o["aile"], o["k"]))
    ek += [("DEMO: 15 bileşim", len(son) == len(senaryolar.AILELER) * len(senaryolar.KLER)),
           ("DEMO: dosya bütçe içinde", len(senaryolar.metin(senaryolar.uret(v.sonuc)).encode("utf-8"))
            < senaryolar.BUTCE),
           ("DEMO: kümeler toplamı kümelenen", all(sum(x["magaza"] for x in r["satirlar"]) == len(kumelenen(v))
                                                  for r in son.values()))]
    if o["yontem"] == "kmeans" and d5 is not None:
        r = aday_satiri(v, o["aile"], "kmeans", o["k"])
        ek.append(("DEMO: önerinin bileşimi = aday tablosu",
                   d5["ari"] == r["ari"] and d5["siluet"] == r["siluet"] and d5["kararlilik"] == r["kararlilik"]))


def anlati_bolumu(v, ek) -> None:
    print("Veriden gelmeyen, anlatı için konmuş değerler (varsayım; yazıda kesin sayı gibi sunulmaz):")
    for anahtar, deger in ANLATI_VARSAYIMLARI.items():
        print(f"  {anahtar}: {deger}")


def korunum_bolumu(v, ek) -> None:
    beklenen = oyun.kumeler_kaydi(v.sonuc)
    if v.kumeler != beklenen:
        if not v.taslak:
            ek.append(("kumeler.json = sonuc.json'dan üretilen", False))
        else:
            print("  [eksik: kumeler.json güncel değil]")
    else:
        ek.append(("kumeler.json = sonuc.json'dan üretilen", True))
    n = korunum(ek)
    print(f"  {s(n)} denetim tuttu: kapsam, kural sınıfları, özellik boyutları, öneri ve aday tablosu, çapraz tablolar,")
    print("  kararlılık ve bırakbir sayımları, hikâye eşikleri, demo bileşimleri ve site dosyası, kumeler.json.")
    print(f"  sonuc.json bugünkü paket koduyla ({v.sonuc['kod'][:12]}) ve v4 dosyasıyla yazılmış.")


BOLUMLER = [
    ("VERİ", veri_bolumu), ("KURAL", kural_bolumu), ("ÖZELLİKLER", ozellik_bolumu), ("ML", ml_bolumu),
    ("HAKEM", hakem_bolumu), ("KARARLILIK", kararlilik_bolumu), ("YENİ MAĞAZA", yeni_magaza_bolumu),
    ("ABLASYON", ablasyon_bolumu), ("HİKÂYE", hikaye_bolumu), ("DEMO", demo_bolumu),
    ("ANLATI VARSAYIMLARI", anlati_bolumu), ("KORUNUM", korunum_bolumu),
]


def govde(v) -> None:
    """Bütün bölümler sırasıyla; korunum en sonda (tutmazsa AssertionError)."""
    print("Mağaza Kümeleme — v4 raporu. Kaynak: cikti/sonuc.json (python -m kumeleme.oyun), kumeler.json, "
          f"site/src/data/senaryolar/{senaryolar.HEDEF.name}.")
    ek: list = []
    for ad, f in BOLUMLER:
        baslik(ad)
        f(v, ek)
    if v.taslak:
        print(f"\nTASLAK: {s(len(v.eksik))} eksik ya da eski girdi (bu çıktı yazılara kaynak olamaz):")
        for e in v.eksik:
            print(f"  {e}")
    korunum(ek)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rapor.py", description=__doc__.split("\n")[0])
    p.add_argument("--taslak", action="store_true", help="eski ya da eksik girdiyle biçim denetimi (çıkış 2)")
    a = p.parse_args(argv)
    try:
        v = hazirla(taslak=a.taslak)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    kod, metin = tamponla(lambda: govde(v))
    if kod:
        return kod
    sys.stdout.write(metin)
    return 2 if v.taslak else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
