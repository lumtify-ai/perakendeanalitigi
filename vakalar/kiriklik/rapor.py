"""Kırıklık Transferi (6 yazı, `/transfer/kiriklik-transferi/`) ve Kırıklık ve Atıl Stok (2 yazı,
`/is-zekasi/kiriklik-atil-stok/`) dizilerinin yayımlanacak BÜTÜN sayıları buradan basılır (v4).

    cd vakalar/kiriklik
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m kiriklik.oyun izgara --blok hepsi    # 47 TAM koşu ve planlar
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m kiriklik.oyun olc                    # cikti/oyun.json (ölçüm, tahmin)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python analiz.py                               # cikti/analiz.json (koşusuz)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m kiriklik.hikaye                      # cikti/hikaye.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py                           # demo JSON
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py --taslak                      # eksik girdiyle biçim denetimi
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py --kucuk                       # cikti/kucuk/ (geliştirme)

Kalıcı kural: yazıya yeni bir sayı girmeden önce buraya eklenir; ortak sayı denetimi (`python -m
perakende_analitik.sayi_denetimi --yazi <dizi dizini> --rapor cikti/rapor.txt`) yazılardaki her sayının bu çıktıda
geçtiğini denetler. Sayılar Türkçe basılır (binlik nokta, ondalık virgül, `%12,34`, `−0,32`). Uydurma sayı yasaktır.
Rapor takvim tarihi ve yıl basmaz (günler karar gününe ya da indirime göre gün ve hafta olarak basılır).

Bölümler (`BOLUMLER`, bu sırayla). Başlık sorularının (tasarım K13) her biri ilgili bölümde tek bir `SORU n · …`
satırıdır (cevap basılan değerlerden; yön sözcükleri hesaplanan değerden). Nedensel beklentiler (K13) bulundukları
bölümde `beklenti (K13) …: TUTUYOR | TUTMUYOR` satırıdır.

    VERİ            yayımlanan v4, karar sabahları: option, mağaza, SKU, depo, stoklu çift, satış (keşif olguları)
    KIRIKLIK        İş Zekası: haftalık kırık beden ve kırık çift, net ve brüt, dar tanım; referans pazartesisinde
                    mağaza tipi ve beden sırası; dört sezon (AW23, SS24 önceki aynı tip sezonlar)
    ATIL            haftalık satmayan ve atıl stok (option × mağaza x ∈ {1, 2, 3}; SKU x = 1); kırık çiftlerin atıl payı
    UYGUNLUK        karar anının hunisi: stoklu → kırık → depoda yok → açık sipariş yok → mağaza uygun
    PLAN            yol 0, kol × sezon: hareket, adet, rota, alıcı, verici, tamamlanan set; kural: tamamlanan ve atlanan
                    alıcı; opt ailesi: çözücü durumu, kaynağı, gap
    YOL 0           kol × sezon: kırık beden farkı (kesit × kapsam), satışa dönüş, ciro farkı (pencere), net (paket),
                    brüt kâr, stok; iki sezon özeti (demonun sayıları)
    YOLLAR          5 talep yolu: net (orta) ve kırık beden farkı, k/5 yolda önde, medyan
    AYRIŞIM         S3 opt − opt_set, S4 kural − kural_28, S7 kahin − opt (net orta, kırık beden farkı)
    SATIŞA DÖNÜŞ    saha ölçüsü ile gerçek etki, pencereler, vericide kayıp (S1, S5, S6)
    PARA            ciro farkı, brüt kâr, maliyet ve net üç paketle (S2)
    TAHMİN          tahminin kahinin gerçek talebine göre isabeti (Ruling R27): Σ talep, WAPE, yanlılık
    YAN ETKİ        replenishment, elle transfer, gizli kayıp, test dışı ciro, sürekli sipariş
    HİKÂYE          sahne (S8)
    DEMO            27 bileşim, site dosyası
    KORUNUM         raporun iç tutarlılığı

Rapor önce tampona yazılır; bir iç denetim tutmazsa ya da bir girdi eksik ya da eskiyse stdout'a tek satır gitmez,
mesaj stderr'e, çıkış kodu 1 (`Eksik`). Eski ya da eksik: ızgaranın bir koşusu (47) `oyun.json`'da yok, geçersiz
(korunum tutmadı ya da atlandı), bugünkü ölçüm koduyla ya da yolunun bugünkü Lumoda koşusuyla ölçülmemiş; koşunun
önbellek dizini yok ya da `meta.json`'u bugünkü vaka ve İlk Sevkiyat kodu, veri, kütüphane sürümleriyle değil; planı
plan önbelleğinde kimliğiyle yok ya da bugünkü karar koduyla kurulmamış; tahmin isabeti kaydı (yol × sezon) eski;
`analiz.json` bugünkü kodla ya da bugünkü v4 dosyasından değil; `hikaye.json` bugünkü kodla ya da bu `oyun.json`'un
koşularından değil; demo dosyası yok ya da `senaryolar.uret()` ile aynı değil. `--taslak` eksik girdiye dayanan
bölümleri "[eksik: …]" diye geçer ve sonda listeler (çıkış 2; bu çıktı yazılara kaynak olamaz); `--kucuk` KÜÇÜK
ölçeğin çıktılarını okur (her zaman taslak).

**Fark kuralı.** Para milyon TL'dir: iki ondalık ve yanında parantezde onun bir kez yarım yukarı yuvarlanmış bir
ondalığı (`para`); iki kol arasındaki fark basılan iki ondalıklı düzeylerin farkıdır (`fark_para`); iki sezon toplamı
ham toplamın iki ondalığıdır. Yüzdeler iki ondalık ve parantezde bir ondalık (`yuzde`), adetler tam sayı. Tek
ondalıklı her sayı iki ondalıklı sayının bir kez yuvarlanmışıdır: aynı büyüklüğe tek değer. "k/5 yolda önde" yol
başına işarettir. Tanımlar `kiriklik/olcutler.py`'nin (YOL 0 ve sonrası), `analiz.py`'nin (VERİ, KIRIKLIK, ATIL,
UYGUNLUK) ve `kiriklik/hikaye.py`'nin notlarındadır. Bu dosya veriyi okumaz, simülasyon koşmaz.
"""

import argparse
import contextlib
import io
import json
import math
import re
import statistics
import sys
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import analiz
import senaryolar
from allocation import motor
from kiriklik import hikaye, olcutler, oyun, sabitler, simulasyon

SEZONLAR = sabitler.TEST_SEZONLARI                  # AW24 ana sahne önce
TOPLAM = "toplam"
SEZON_ADLARI = {"AW24": "AW24 (kış)", "SS25": "SS25 (yaz)", "AW23": "AW23 (önceki kış)", "SS24": "SS24 (önceki yaz)",
                TOPLAM: "iki sezon"}
LUMODA = oyun.LUMODA
YOL0_KOLLARI = ("kural", "kural_28", "opt", "opt_set", "kahin")
KORUNUM_KOSULLARI = olcutler.KORUNUM_KOSULLARI
PAKETLER = tuple(sabitler.MALIYET_PAKETLERI)
PAKET_ADLARI = {"dusuk": "düşük", "orta": "orta", "yuksek": "yüksek"}
KESIT_ADLARI = {"karar": "karar sabahı", "varis_sonrasi": "varıştan sonraki ilk pazartesi",
                "indirim_oncesi": "indirimden önceki son pazartesi", "cikis_oncesi": "çıkıştan önceki pazartesi (− 7)"}
KAPSAM_ADLARI = {"transfer_edilen_alici": "alıcı çiftler", "transfer_edilen_verici": "verici çiftler",
                 "transfer_edilen": "transfer edilen çiftler", "butun": "bütün stok"}
PENCERE_ADLARI = {"tam": "tam fiyat (karar → indirim)", "indirim": "indirim (indirim → çıkış)",
                  "outlet": "outlet (çıkış → + 84 gün)", "toplam": "toplam"}
KIMLIK_ALANLARI = {"vaka": "vaka kod özeti", "kod": "İlk Sevkiyat kod özeti", "veri": "v4 veri parmak izi",
                   "surumler": "kütüphane sürümleri"}
HUNI_ADLARI = {"stoklu": "stoklu çift", "kirik": "kırık", "depoda_yok": "eksik bedenler depoda yok",
               "acik_siparis_yok": "açık siparişi de yok", "magaza_uygun": "mağaza uygun"}
AYRISIMLAR = ((3, "opt", "opt_set", "set koşulunun bedeli"), (4, "kural", "kural_28", "STD'nin son 28 güne göre değeri"),
              (7, "kahin", "opt", "talebi ve fiyat yolunu bilmenin değeri"))


class Eksik(Exception):
    """Raporun dayandığı bir girdi yok ya da eski (stderr, çıkış 1; taslakta bölüm atlanır)."""

    def __init__(self, *neler: str):
        super().__init__("; ".join(neler))
        self.neler = list(neler)


# ---------------------------------------------------------------------------
# Biçim (İndirim Takvimi raporunun kuralları)
# ---------------------------------------------------------------------------


def _yok(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _sifir_mi(metin: str) -> bool:
    return metin.lstrip("-").replace(".", "").replace(",", "").strip("0") == ""


def yuv(x, ondalik: int = 0) -> float:
    """`s(x, ondalik)`'ın bastığı değer (yarım yukarı, ondalık aritmetikle)."""
    q = Decimal(1).scaleb(-ondalik)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def s(x, ondalik: int = 0) -> str:
    """Türkçe sayı: 1.234.567 · 0,55 · −3,2 (yuvarlanınca sıfır olan negatif işaretsiz)."""
    if _yok(x):
        return "—"
    if isinstance(x, int) and not isinstance(x, bool) and ondalik == 0:
        metin = f"{x:,}"
    else:
        metin = f"{yuv(x, ondalik):,.{ondalik}f}"
    metin = metin.replace(",", "_").replace(".", ",").replace("_", ".")
    if _sifir_mi(metin):
        metin = metin.lstrip("-")
    return metin.replace("-", "−")


def yd(x, ondalik: int = 2) -> str:
    """Yüzde, x zaten yüzde: 65,102 → %65,10; negatif → −%3,20."""
    if _yok(x):
        return "—"
    govde = s(abs(float(x)), ondalik)
    return ("−%" if x < 0 and not _sifir_mi(govde) else "%") + govde


def y(x, ondalik: int = 1) -> str:
    """Yüzde, x oran: 0,123 → %12,3."""
    return "—" if _yok(x) else yd(100 * float(x), ondalik)


def isaretli(x, ondalik: int = 0) -> str:
    metin = s(x, ondalik)
    return metin if metin.startswith("−") or metin == "—" or _sifir_mi(metin) else "+" + metin


def fark(a, b, ondalik: int = 0) -> float:
    """b − a, ikisi de `ondalik` hanede basıldığı gibi."""
    return yuv(yuv(b, ondalik) - yuv(a, ondalik), ondalik)


def tek_ondalik(x2) -> float:
    """İki ondalıklı değerin bir kez yarım yukarı yuvarlanmışı (ondalık aritmetikle)."""
    return float(Decimal(f"{float(x2):.2f}").quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fark1(a, b) -> float:
    """b − a, bir ondalık: iki ondalıklı farkın (`fark(a, b, 2)`) bir kez yuvarlanmışı."""
    return tek_ondalik(fark(a, b, 2))


def mtl(x) -> float:
    return float(x) / 1e6


def _m2(x2: float) -> str:
    return f"{isaretli(x2, 2)} M TL ({isaretli(tek_ondalik(x2), 1)})"


def para(x) -> str:
    """TL farkı (kendisi bir fark ya da net) milyon TL: iki ondalık (bir kez yuvarlanmış bir ondalık)."""
    return "—" if _yok(x) else _m2(yuv(mtl(x), 2))


def fark_para(a, b) -> str:
    """b − a milyon TL: basılan iki ondalıklı düzeylerin farkı (ve onun bir kez yuvarlanmışı)."""
    return "—" if _yok(a) or _yok(b) else _m2(fark(mtl(a), mtl(b), 2))


def yuzde(x) -> str:
    """Oran (0–1) yüzde: iki ondalık (bir kez yuvarlanmış bir ondalık)."""
    if _yok(x):
        return "—"
    x2 = yuv(100 * float(x), 2)
    return f"{yd(x2, 2)} ({yd(tek_ondalik(x2), 1)})"


def puan_farki(a, b) -> str:
    """b − a yüzde puanı (a, b oran 0–1): basılan iki ondalıklı yüzdelerin farkı ve onun bir kez yuvarlanmışı."""
    if _yok(a) or _yok(b):
        return "—"
    x2 = fark(100 * float(a), 100 * float(b), 2)
    return f"{isaretli(x2, 2)} puan ({isaretli(tek_ondalik(x2), 1)})"


def bin_tl(x) -> str:
    return "—" if _yok(x) else f"{s(float(x) / 1e3, 0)} bin TL"


def hk(h) -> str:
    """İndirim haftasına göre hafta numarası: 0, −3, +2."""
    return "0" if int(h) == 0 else isaretli(int(h))


def yon(x, arti: str, eksi: str, esit: str = "aynı") -> str:
    return arti if x > 0 else eksi if x < 0 else esit


def tutuyor(x: bool) -> str:
    return "TUTUYOR" if x else "TUTMUYOR"


def baslik(metin: str) -> None:
    print(f"\n=== {metin} ===")


def alt(metin: str) -> None:
    print(f"\n--- {metin} ---")


def soru(n: int, metin: str) -> None:
    print(f"SORU {n} · {metin}")


def _tablo(basliklar: list[str], satirlar: list[list[str]]) -> None:
    gen = [max(len(b), *(len(r[i]) for r in satirlar)) if satirlar else len(b) for i, b in enumerate(basliklar)]
    print("  " + "  ".join(b.ljust(g) for b, g in zip(basliklar, gen)))
    for r in satirlar:
        print("  " + "  ".join(c.ljust(g) for c, g in zip(r, gen)))


def tamponla(govde) -> tuple[int, str]:
    """`govde()`yi stdout'u tamponlayarak koşar: (0, metin) ya da korunum bozulursa (1, "") ve mesaj stderr'e."""
    tampon = io.StringIO()
    try:
        with contextlib.redirect_stdout(tampon):
            govde()
    except AssertionError as e:
        print(e, file=sys.stderr)
        return 1, ""
    except Eksik as e:
        print("Eksik:\n  " + "\n  ".join(e.neler), file=sys.stderr)
        return 1, ""
    return 0, tampon.getvalue()


YIL = re.compile(r"(?<![0-9A-Za-z])(?:19|20)\d{2}(?![0-9A-Za-z])")


def yillar(metin: str) -> list[str]:
    """Metinde geçen yıllar (dört haneli 19xx / 20xx, harf ya da rakama bitişik olmayan; sezon kodu yakalanmaz)."""
    return YIL.findall(metin)


def korunum(denetimler: list[tuple[str, bool]]) -> int:
    """Denetimlerin hepsi tutmalı; tutmayanlar adlarıyla AssertionError. Döner: denetim sayısı."""
    if not denetimler:
        raise AssertionError("korunum: hiç denetim yok")
    hatalar = [ad for ad, ok in denetimler if not bool(ok)]
    if hatalar:
        raise AssertionError("korunum bozuldu:\n  " + "\n  ".join(hatalar))
    return len(denetimler)


# ---------------------------------------------------------------------------
# Girdiler
# ---------------------------------------------------------------------------


@dataclass
class Veri:
    oyun: dict
    analiz: dict | None
    hikaye: dict | None
    demo_dosya: dict | None
    olcek: str = "tam"
    taslak: bool = False
    demo_bayt: int | None = None
    gecerli: set = field(default_factory=set)            # geçerli kol koşularının adları
    lumoda: set = field(default_factory=set)             # geçerli Lumoda koşularının yolları
    planlar: dict = field(default_factory=dict)          # koşu adı → plan JSON'u
    tahmin: set = field(default_factory=set)             # geçerli (yol, sezon) tahmin isabeti kayıtları
    eksik: list = field(default_factory=list)
    olcum_kodu: str = ""


def _json(yol: Path) -> dict | None:
    yol = Path(yol)
    return json.loads(yol.read_text(encoding="utf-8")) if yol.is_file() else None


def kosu_kimligi() -> dict:
    """Bugünkü kodun ve verinin, koşu `meta.json`'unda kayıtlı kimliği (`simulasyon.hazirla`: vaka, kod, veri,
    sürümler)."""
    return json.loads(json.dumps({"vaka": simulasyon.vaka_kod_ozeti(), "kod": motor.kod_ozeti(),
                                  "veri": motor.veri_parmak_izi(),
                                  "surumler": {p: motor._surum(p) for p in motor.SURUM_PAKETLERI}}))


def _meta_sorunu(onbellek: Path, ad: str, anahtar: str, kimlik: dict) -> str | None:
    m = Path(onbellek) / f"{ad}_{anahtar[:20]}" / "meta.json"
    meta = json.loads(m.read_text(encoding="utf-8")) if m.is_file() else {}
    if meta.get("anahtar") != anahtar:
        return f"önbellek: {ad} koşusu {m.parent.name} yok ya da anahtarı farklı"
    farkli = [et for a, et in KIMLIK_ALANLARI.items() if meta.get(a) != kimlik[a]]
    if farkli:
        return (f"önbellek: {ad} koşusu bugünkü koda ya da veriye göre eski ({', '.join(farkli)} farklı; "
                "python -m kiriklik.oyun izgara)")
    return None


def _plan_bul(planlar: Path, r: dict) -> dict | None:
    for yol in sorted(Path(planlar).glob(f"{r['kol']}_{r['sezon']}_y{r['yol']}_*.json")):
        d = json.loads(yol.read_text(encoding="utf-8"))
        if d.get("kimlik") == r.get("plan_kimligi"):
            return d
    return None


def _plan_sorunu(pj: dict | None, r: dict, karar_kodu: str, olcek: str) -> str | None:
    ad = r["ad"]
    if pj is None:
        return f"plan önbelleği: {ad} planı (kimlik {str(r.get('plan_kimligi'))[:12]}) yok"
    ic = pj.get("icerik") or {}
    if pj.get("anahtar") != oyun.plan_anahtari(ic):
        return f"plan önbelleği: {ad} planının anahtarı içeriğiyle tutmuyor"
    if ic.get("kod") != karar_kodu:
        return f"plan önbelleği: {ad} planı bugünkü karar koduyla kurulmamış (python -m kiriklik.oyun izgara)"
    beklenen = {"kol": r["kol"], "sezon": r["sezon"], "yol": r["yol"], "olcek": olcek,
                "lumoda_anahtari": r["lumoda_anahtari"], "pulp": oyun._surum("pulp")}
    if any(ic.get(a) != v for a, v in beklenen.items()):
        return f"plan önbelleği: {ad} planının girdisi (kol, sezon, yol, ölçek, Lumoda, PuLP) kayıttan farklı"
    return None


def kosular_denetimi(o: dict, olcek: str, kod: str, onbellek: Path, planlar: Path, karar: dict, kimlik: dict
                     ) -> tuple[set, set, dict, list]:
    """Izgaranın 47 koşusu (modül notu): geçerli kol koşuları, geçerli Lumoda yolları, plan JSON'ları, sorunlar."""
    lumoda, kosular = o.get("lumoda") or {}, o.get("kosular") or {}
    gec, lum_ok, pjs, sorun = set(), set(), {}, []
    for i in oyun.izgara_listesi(olcek):
        if i.kol == LUMODA:
            e = lumoda.get(str(i.yol)) or {}
            if not e.get("anahtar") or e.get("gecerli") is False:
                sorun.append(f"oyun.json: {i.ad} Lumoda koşusu yok ({e.get('atlandi', 'kayıt yok')}; "
                             "python -m kiriklik.oyun izgara / olc)")
            elif m := _meta_sorunu(onbellek, i.ad, e["anahtar"], kimlik):
                sorun.append(m)
            else:
                lum_ok.add(i.yol)
            continue
        r = kosular.get(i.ad)
        lum = (lumoda.get(str(i.yol)) or {}).get("anahtar")
        if r is None:
            sorun.append(f"oyun.json: {i.ad} yok (python -m kiriklik.oyun izgara / olc)")
        elif r.get("gecerli") is not True or r.get("olcum") is None:
            neden = r.get("atlandi") or ", ".join(a for a, v in (r.get("korunum") or {}).items() if v is not True)
            sorun.append(f"oyun.json: {i.ad} geçersiz ({neden or 'ölçüm yok'})")
        elif r.get("olcum_ozeti") != kod:
            sorun.append(f"oyun.json: {i.ad} bugünkü ölçüm koduyla ölçülmemiş (python -m kiriklik.oyun olc)")
        elif lum is None or r.get("lumoda_anahtari") != lum:
            sorun.append(f"oyun.json: {i.ad} yolunun Lumoda koşusuyla ölçülmemiş (python -m kiriklik.oyun olc)")
        elif m := _meta_sorunu(onbellek, i.ad, r.get("anahtar") or "", kimlik):
            sorun.append(m)
        else:
            pj = _plan_bul(planlar, r)
            if m := _plan_sorunu(pj, r, karar[i.kol], olcek):
                sorun.append(m)
            else:
                gec.add(i.ad)
                pjs[i.ad] = pj
    return gec, lum_ok, pjs, sorun


def tahmin_denetimi(o: dict, kod: str, karar_kahin: str) -> tuple[set, list]:
    """Tahmin isabeti kayıtları (yol × sezon): geçerli, bugünkü ölçüm ve kahin karar koduyla, yolun Lumoda'sı ve
    `opt` koşusunun planıyla."""
    ok, sorun = set(), []
    for p in oyun.YOLLAR:
        for z in SEZONLAR:
            t = ((o.get("tahmin") or {}).get(str(p)) or {}).get(z)
            opt = (o.get("kosular") or {}).get(oyun.kosu_adi("opt", z, p)) or {}
            lum = ((o.get("lumoda") or {}).get(str(p)) or {}).get("anahtar")
            beklenen = {"olcum_ozeti": kod, "karar_kodu": karar_kahin, "lumoda_anahtari": lum,
                        "plan_kimligi": opt.get("plan_kimligi")}
            if not t or t.get("gecerli") is not True or t.get("isabet") is None:
                sorun.append(f"oyun.json: tahmin isabeti yol {p} {z} yok (python -m kiriklik.oyun olc)")
            elif any(t.get(a) != v for a, v in beklenen.items()):
                sorun.append(f"oyun.json: tahmin isabeti yol {p} {z} eski (ölçüm kodu, kahin karar kodu, Lumoda ya da "
                             "opt planı farklı; python -m kiriklik.oyun olc)")
            else:
                ok.add((p, z))
    return ok, sorun


def hazirla(*, kucuk: bool = False, taslak: bool = False, cikti: Path | None = None, demo_yol: Path | None = None,
            onbellek: Path | None = None, planlar: Path | None = None, olcum_kodu: str | None = None,
            analiz_kodu: str | None = None, hikaye_kodu: str | None = None, karar_kodlari: dict | None = None,
            kimlik: dict | None = None) -> Veri:
    """Girdileri okur ve tazeliklerini denetler (modül notu). Kesin kipte eksik ya da eski girdi `Eksik`; taslakta
    `Veri.eksik`'e yazılır. `oyun.json` her iki kipte de gerekir. Kod özetleri ve kimlik testlerde verilir."""
    olcek = "kucuk" if kucuk else "tam"
    o_ = oyun.varsayilan_ortam(olcek)
    cikti = Path(cikti) if cikti is not None else o_.cikti
    onbellek = Path(onbellek) if onbellek is not None else o_.onbellek
    planlar = Path(planlar) if planlar is not None else o_.planlar
    demo_yol = (senaryolar.KUCUK_HEDEF if kucuk else senaryolar.HEDEF) if demo_yol is None else Path(demo_yol)
    kod = oyun.olcum_kodu() if olcum_kodu is None else olcum_kodu
    karar = {k: oyun.karar_kod_ozeti(k) for k in oyun.KOLLAR} if karar_kodlari is None else karar_kodlari
    kimlik = kosu_kimligi() if kimlik is None else kimlik
    o = _json(cikti / "oyun.json")
    if o is None:
        raise Eksik(f"{cikti / 'oyun.json'} yok: önce python -m kiriklik.oyun izgara ve olc")
    sorun = []
    if o.get("olcek") != olcek:
        sorun.append(f"oyun.json {o.get('olcek')} ölçeğinde (beklenen {olcek})")
    gec, lum_ok, pjs, ek = kosular_denetimi(o, olcek, kod, onbellek, planlar, karar, kimlik)
    sorun += ek
    tah, ek = tahmin_denetimi(o, kod, karar["kahin"])
    sorun += ek
    a = _json(cikti / "analiz.json")
    if a is None:
        sorun.append("analiz.json yok (python analiz.py)")
    else:
        if a.get("kod") != (analiz.kod_ozeti() if analiz_kodu is None else analiz_kodu):
            sorun.append("analiz.json bugünkü kodla yazılmamış (python analiz.py)")
        if a.get("veri") != kimlik["veri"]:
            sorun.append("analiz.json bugünkü v4 dosyasından değil (python analiz.py)")
    h = _json(cikti / "hikaye.json")
    if h is None:
        sorun.append("hikaye.json yok (python -m kiriklik.hikaye)")
    else:
        r = (o.get("kosular") or {}).get(oyun.kosu_adi(hikaye.KOL, hikaye.SEZON, hikaye.YOL)) or {}
        lum0 = ((o.get("lumoda") or {}).get(str(hikaye.YOL)) or {}).get("anahtar")
        if h.get("kod") != (hikaye.kod_ozeti() if hikaye_kodu is None else hikaye_kodu):
            sorun.append("hikaye.json bugünkü kodla yazılmamış (python -m kiriklik.hikaye)")
        if (h.get("olcek"), (h.get("kosu") or {}).get("anahtar"), h.get("lumoda_anahtari"), h.get("plan_kimligi"),
                h.get("olcum_ozeti")) != (olcek, r.get("anahtar"), lum0, r.get("plan_kimligi"), kod):
            sorun.append("hikaye.json bu oyun.json'un kural AW24 ve Lumoda koşularından değil (python -m kiriklik.hikaye)")
    demo = _json(demo_yol)
    if demo is None:
        sorun.append(f"{demo_yol.name} yok (python senaryolar.py)")
    if kucuk:
        sorun.append("KÜÇÜK ölçek: geliştirme çıktısı")
    if sorun and not (taslak or kucuk):
        raise Eksik(*sorun)
    return Veri(oyun=o, analiz=a, hikaye=h, demo_dosya=demo, olcek=olcek, taslak=taslak or kucuk,
                demo_bayt=demo_yol.stat().st_size if demo is not None else None, gecerli=gec, lumoda=lum_ok,
                planlar=pjs, tahmin=tah, eksik=sorun, olcum_kodu=kod)


# ---------------------------------------------------------------------------
# Kısayollar
# ---------------------------------------------------------------------------


def K(v, kol: str, sezon: str, yol: int = 0) -> dict:
    """Geçerli kol koşusunun kaydı; değilse `Eksik`."""
    ad = oyun.kosu_adi(kol, sezon, yol)
    if ad not in v.gecerli:
        raise Eksik(f"koşu {ad}")
    return v.oyun["kosular"][ad]


def O(v, kol: str, sezon: str, yol: int = 0) -> dict:
    return K(v, kol, sezon, yol)["olcum"]


def OO(v, kol: str, sezon: str, yol: int = 0) -> list[dict]:
    """Sezonun ya da iki sezonun (`toplam`) ölçümleri."""
    return [O(v, kol, z, yol) for z in (SEZONLAR if sezon == TOPLAM else (sezon,))]


def A(v) -> dict:
    if v.analiz is None:
        raise Eksik("analiz.json")
    return v.analiz


def H(v) -> dict:
    if v.hikaye is None:
        raise Eksik("hikaye.json")
    return v.hikaye


def T(v, yol: int, sezon: str) -> dict:
    if (yol, sezon) not in v.tahmin:
        raise Eksik(f"tahmin isabeti yol {yol} {sezon}")
    return v.oyun["tahmin"][str(yol)][sezon]["isabet"]


def P(v, kol: str, sezon: str, yol: int = 0) -> dict:
    K(v, kol, sezon, yol)
    return v.planlar[oyun.kosu_adi(kol, sezon, yol)]["bilgi"]


def kirik_farki(o: dict, kesit: str = "indirim_oncesi", kapsam: str = "butun", olcu: str = "kirik_beden") -> int:
    return int(o["kiriklik"][kesit]["kapsamlar"][kapsam]["fark"][olcu])


def net(oo: list[dict], paket: str = sabitler.KARAR_PAKETI) -> float:
    return sum(o["para"]["net"][paket] for o in oo)


def topla(oo: list[dict], f) -> float | None:
    x = [f(o) for o in oo]
    return None if any(_yok(a) for a in x) else sum(x)


def oran(pay, payda):
    return None if _yok(pay) or not payda else pay / payda


# ---------------------------------------------------------------------------
# VERİ, KIRIKLIK, ATIL, UYGUNLUK (analiz.json)
# ---------------------------------------------------------------------------


def veri_bolumu(v, ek) -> None:
    a = A(v)
    print("Kaynak: yayımlanan v4 (analistin gördüğü veri), Collection SKU'ları (Standart beden seti hariç), fiziksel "
          "mağazalar (AVM + Cadde); asorti 1-2-2-1-1.")
    for z in SEZONLAR:
        h = a["huni"][z]
        k, oz = h["kesif"], h["ozet"]
        alt(f"{SEZON_ADLARI[z]}: karar sabahı (indirime {s(h['indirime_gun'])} gün)")
        print(f"  {s(k['option'])} option; stoklu mağaza {s(k['magaza'])} (fiziksel mağaza {s(k['magaza_fiziksel'])}, "
              f"açık ve kapanış kararsız {s(k['magaza_uygun'])}); stoklu (mağaza, option) çifti {s(oz['stoklu_cift'])}")
        print(f"  depo: SKU {s(k['sku'])}, depoda stoğu olan SKU {s(k['sku_depolu'])}; depo stoğu tamamen sıfır option "
              f"{s(k['option_deposuz'])}")
        print(f"  option başına medyan {s(k['option_basina_stoklu_medyan'], 0)} stoklu, "
              f"{s(k['option_basina_kirik_medyan'], 0)} kırık çift; son 28 günde {s(k['son28_esik'])}+ adet satan çift "
              f"{s(k['son28_esik_ustu'])} ({yuzde(oran(k['son28_esik_ustu'], oz['stoklu_cift']))})")


def _kirik_satiri(oz: dict) -> list[str]:
    return [s(oz["stoklu_cift"]), s(oz["kirik_cift"]), yuzde(oz["kirik_cift_oran"]), s(oz["kirik_beden"]),
            yuzde(oz["net_oran"]), s(oz["eksik_adet"]), yuzde(oz["brut_oran"]), s(oz["dar_kirik_cift"])]


KIRIK_BASLIK = ["stoklu çift", "kırık çift", "pay", "kırık beden", "net", "eksik adet", "brüt", "dar tanımla kırık"]


def kiriklik_bolumu(v, ek) -> None:
    a = A(v)
    print("Kırık beden = asortide olan ama stoğu sıfır beden; net kırıklık = kırık beden ÷ beden; brüt = eksik adet ÷ "
          "asorti (eksik = Σ max(0, asorti − stok)); kırık çift = en az bir kırık bedeni olan stoklu (mağaza, option) "
          "çifti. Dar tanım (Blok Transfer): ara bedenlerden (2–4) biri sıfır. Pazartesi sabah fotoğrafları, hafta "
          "indirim haftasına göre.")
    for z in a["sezonlar"]:
        b = a["sezon"][z]
        r = b["referans"]
        alt(f"{SEZON_ADLARI[z]}: referans pazartesisi (indirime {s(b['indirime_gun'])} gün, hafta {hk(r['hafta'])})")
        oz = r["butun"]
        print(f"  {s(oz['kirik_cift'])} / {s(oz['stoklu_cift'])} çift kırık ({yuzde(oz['kirik_cift_oran'])}); "
              f"{s(oz['kirik_beden'])} kırık beden, net {yuzde(oz['net_oran'])}, brüt {yuzde(oz['brut_oran'])} "
              f"({s(oz['eksik_adet'])} eksik adet); dar tanımla {s(oz['dar_kirik_cift'])} çift "
              f"(dar ÷ net {yuzde(oran(oz['dar_kirik_cift'], oz['kirik_cift']))}, fark "
              f"{s(oz['kirik_cift'] - oz['dar_kirik_cift'])} çift)")
        for t in sabitler.FIZIKSEL_TIPLER:
            x = r["tip"][t]
            print(f"  {t}: {s(x['kirik_cift'])} / {s(x['stoklu_cift'])} çift kırık ({yuzde(x['kirik_cift_oran'])}), net "
                  f"{yuzde(x['net_oran'])}, brüt {yuzde(x['brut_oran'])}")
        print("  beden sırasına göre (sıra · asorti · sıfır stoklu çift · stoklu çiftlerde payı · eksik adet): " + "; ".join(
            f"{x['beden_sira']} · {x['asorti']} · {s(x['kirik_cift'])} · {yuzde(x['pay'])} · {s(x['eksik_adet'])}"
            for x in r["beden_sirasi"]))
        _tablo(["hafta", *KIRIK_BASLIK, "AVM net", "Cadde net"],
               [[hk(w["hafta"]), *_kirik_satiri(w["butun"]), yuzde(w["tip"]["AVM"]["net_oran"]),
                 yuzde(w["tip"]["Cadde"]["net_oran"])] for w in b["haftalik"]])
        en = max(b["haftalik"], key=lambda w: (w["butun"]["kirik_beden"], -w["hafta"]))
        print(f"  en çok kırık beden hafta {hk(en['hafta'])}: {s(en['butun']['kirik_beden'])} (net "
              f"{yuzde(en['butun']['net_oran'])})")
    for z, onceki in a["onceki"].items():
        r, q = a["sezon"][z]["referans"]["butun"], a["sezon"][onceki]["referans"]["butun"]
        print(f"  {z} − {onceki} referans pazartesisinde: kırık çift {isaretli(r['kirik_cift'] - q['kirik_cift'])}, net "
              f"{yuzde(r['net_oran'])} − {yuzde(q['net_oran'])} = {puan_farki(q['net_oran'], r['net_oran'])}")


def _atil_hucre(x: dict) -> str:
    return f"{s(x['n'])} / {s(x['adet'])} / {bin_tl(x['alis'])}"


def atil_bolumu(v, ek) -> None:
    a = A(v)
    x0 = sabitler.ATIL_ESIK_OPTION
    print(f"Pencere {s(sabitler.ATIL_PENCERE_GUN)} gün, rafta en az {s(sabitler.ATIL_PENCERE_GUN)} gün; satmayan = "
          f"pencerede satış 0, atıl = 1 ile x arası (option × mağaza x = {x0}, SKU x = {sabitler.ATIL_ESIK_SKU}). "
          "Hücre: çift sayısı / mağaza stoğu (adet) / alış değeri.")
    for z in a["sezonlar"]:
        b = a["sezon"][z]
        alt(f"{SEZON_ADLARI[z]}")
        _tablo(["hafta", "satmayan", *(f"atıl x={x}" for x in sabitler.ATIL_DUYARLILIK), "yeni", "SKU satmayan (adet)",
                "SKU atıl (adet)", "kırık çiftte atıl+satmayan", "tam çiftte atıl+satmayan"],
               [[hk(w["hafta"]), _atil_hucre(w["atil"]["cift"][f"x{x0}"]["satmayan"]),
                 *(_atil_hucre(w["atil"]["cift"][f"x{x}"]["atil"]) for x in sabitler.ATIL_DUYARLILIK),
                 s(w["atil"]["cift"][f"x{x0}"]["yeni"]["n"]), s(w["atil"]["sku"]["satmayan"]["adet"]),
                 s(w["atil"]["sku"]["atil"]["adet"]), yuzde(_atil_payi(w["atil"]["kirik_atil"]["kirik"])),
                 yuzde(_atil_payi(w["atil"]["kirik_atil"]["tam"]))] for w in b["haftalik"]])
        r = next(w for w in b["haftalik"] if w["hafta"] == b["referans"]["hafta"])
        ka = r["atil"]["kirik_atil"]
        print(f"  referans pazartesisi (hafta {hk(r['hafta'])}): atıl ya da satmayan payı kırık çiftlerde "
              f"{yuzde(_atil_payi(ka['kirik']))} ({s(ka['kirik']['atil']['n'] + ka['kirik']['satmayan']['n'])} çift, "
              f"{s(ka['kirik']['atil']['adet'] + ka['kirik']['satmayan']['adet'])} adet), tam çiftlerde "
              f"{yuzde(_atil_payi(ka['tam']))}")


def _atil_payi(k: dict) -> float | None:
    n = sum(x["n"] for x in k.values()) - k["yeni"]["n"]
    return oran(k["atil"]["n"] + k["satmayan"]["n"], n)


def uygunluk_bolumu(v, ek) -> None:
    a = A(v)
    print("Uygun alıcı adayı (K4, K18): kırık çift, bütün kırık bedenlerinin karar anında depo stoğu ve indirimden önce "
          "teslim planlı açık siparişi sıfır, mağaza açık ve kapanış kararsız.")
    for z in SEZONLAR:
        h = a["huni"][z]
        b = h["basamaklar"]
        alt(f"{SEZON_ADLARI[z]}: karar sabahı")
        _tablo(["basamak", "çift", "önceki basamağın payı", "option"],
               [[HUNI_ADLARI[x["ad"]], s(x["cift"]), "—" if i == 0 else yuzde(oran(x["cift"], b[i - 1]["cift"])),
                 s(x["option"])] for i, x in enumerate(b)])
        n = h["neden"]
        print(f"  eleme nedenleri (öncelik: mağaza, depo, açık sipariş): depoda var {s(n['depoda_var'])}, açık sipariş "
              f"{s(n['acik_siparis'])}, mağaza {s(n['magaza'])}; uygun {s(n['uygun'])}")
        ek.append((f"UYGUNLUK {z}: huni basamakları azalır", all(b[i]["cift"] >= b[i + 1]["cift"] for i in range(len(b) - 1))))
        ek.append((f"UYGUNLUK {z}: huni = referans fotoğrafı (stoklu, kırık)",
                   (b[0]["cift"], b[1]["cift"]) == (a["sezon"][z]["referans"]["butun"]["stoklu_cift"],
                                                    a["sezon"][z]["referans"]["butun"]["kirik_cift"])))
        ek.append((f"UYGUNLUK {z}: son basamak = uygun etiketi", b[-1]["cift"] == n["uygun"]))


# ---------------------------------------------------------------------------
# PLAN
# ---------------------------------------------------------------------------


def _cozucu(bilgi: dict) -> str:
    return (f"durum {bilgi.get('durum', '—')}, kaynak {bilgi.get('kaynak', '—')}, gap {yuzde(bilgi.get('gap'))} (optimuma "
            "en çok bu kadar uzak; gap yoksa —)")


def plan_bolumu(v, ek) -> None:
    print("Yol 0, karar sabahı planları. Rota = tekil (verici, alıcı) mağaza çifti, bütün option'lar üzerinden.")
    satirlar = []
    for kol in YOL0_KOLLARI:
        for z in SEZONLAR:
            p = O(v, kol, z)["plan"]
            satirlar.append([kol, z, s(p["hareket"]), s(p["adet"]), s(p["rota"]), s(p["option"]), s(p["alici_cift"]),
                             s(p["alici_magaza"]), s(p["verici_cift"]), s(p["verici_magaza"]), s(p["tamamlanan_set"]),
                             s(p["alici_basina_verici_medyan"], 1), s(p["rota_basina_adet_medyan"], 1)])
    _tablo(["kol", "sezon", "hareket", "adet", "rota", "option", "alıcı çift", "alıcı mağaza", "verici çift",
            "verici mağaza", "tamamlanan set", "alıcı başına verici (medyan)", "rota başına adet (medyan)"], satirlar)
    for kol in YOL0_KOLLARI:
        for z in SEZONLAR:
            b, p = P(v, kol, z), O(v, kol, z)["plan"]
            if kol.startswith("kural"):
                t, at = len(b.get("tamamlanan_alicilar") or []), len(b.get("atlanan_alicilar") or [])
                print(f"  {kol} {z}: {s(t)} alıcı tamamlandı, {s(at)} alıcı atlandı (tamamlanamaz: dokunulmadı); "
                      f"denenen {s(t + at)}")
                ek.append((f"PLAN {kol} {z}: tamamlanan alıcı = ölçülen alıcı çifti", t == p["alici_cift"]))
            else:
                print(f"  {kol} {z}: {_cozucu(b)}")
    parca = []
    for kol in ("opt", "opt_set", "kahin"):
        gg = [P(v, kol, z, p).get("gap") for z in SEZONLAR for p in oyun.YOLLAR]
        yok = sum(_yok(g) for g in gg)
        parca.append(f"{kol} {yuzde(max(g for g in gg if not _yok(g)))}" if not yok
                     else f"{kol} — (gap yok: {s(yok)} koşu)")
    print("  çözücü, bütün yollar ve iki sezon: en büyük gap " + ", ".join(parca))
    k, o_ = (topla(OO(v, kol, TOPLAM), lambda o: o["plan"]["rota"]) for kol in ("kural", "opt"))
    ka, oa = (topla(OO(v, kol, TOPLAM), lambda o: o["plan"]["adet"]) for kol in ("kural", "opt"))
    print(f"  beklenti (K13) opt daha az ama daha dolu rota kurar: {tutuyor(o_ < k and oa / o_ > ka / k)} (iki sezon: "
          f"rota kural {s(k)}, opt {s(o_)}; rota başına adet kural {s(ka / k, 2)}, opt {s(oa / o_, 2)})")


# ---------------------------------------------------------------------------
# YOL 0
# ---------------------------------------------------------------------------


def _kesit_tablosu(o: dict) -> None:
    satirlar = []
    for kes, ad in KESIT_ADLARI.items():
        k = o["kiriklik"][kes]["kapsamlar"]
        if k is None:
            satirlar.append([ad, *("—" for _ in KAPSAM_ADLARI)])
            continue
        satirlar.append([ad, *(f"{isaretli(k[kap]['fark']['kirik_beden'])} / {isaretli(k[kap]['fark']['kirik_cift'])}"
                               for kap in KAPSAM_ADLARI)])
    _tablo(["kesit (kırık beden / kırık çift farkı)", *KAPSAM_ADLARI.values()], satirlar)
    lum = o["kiriklik"]["indirim_oncesi"]["kapsamlar"]["butun"]["lumoda"]
    print(f"  Lumoda indirimden önceki son pazartesi, bütün stok: {s(lum['kirik_beden'])} kırık beden, "
          f"{s(lum['kirik_cift'])} kırık çift (net {yuzde(lum['net_oran'])})")


def _yol0_ozet(v, kol: str, sezon: str) -> None:
    oo = OO(v, kol, sezon)
    h = {p: senaryolar.ham(oo, p) for p in PAKETLER}
    print(f"  {kol} · {SEZON_ADLARI[sezon]}: net " + ", ".join(f"{PAKET_ADLARI[p]} {para(h[p]['net_tl'])}" for p in PAKETLER)
          + f"; kırık beden farkı (indirim öncesi, bütün stok) {isaretli(h['orta']['kirik_beden_farki'])}; satışa dönüş "
          f"saha (çıkışa) {yuzde(h['orta']['saha_donus'])}, etki {yuzde(h['orta']['etki_donus'])}")


def yol0_bolumu(v, ek) -> None:
    print("Kollar yolun Lumoda koşusuna göre (kol − Lumoda). Aynı mal: RPT ve fiyat kayıtları Lumoda'nınkiyle birebir "
          "(korunum).")
    for kol in YOL0_KOLLARI:
        for z in SEZONLAR:
            o = O(v, kol, z)
            alt(f"{kol} · {SEZON_ADLARI[z]}")
            _kesit_tablosu(o)
            sd, pa = o["satisa_donus"], o["para"]
            print(f"  satışa dönüş: alınan {s(sd['alinan_adet'])}; indirime kadar {s(sd['indirime_satilan'])}, "
                  f"{yuzde(sd['saha_indirime'])}; çıkışa kadar {s(sd['cikisa_satilan'])}, {yuzde(sd['saha_cikisa'])}; "
                  f"etki {isaretli(sd['etki_adet']['toplam'])} adet, taşınanın {yuzde(sd['etki_oran'])}")
            print("  ciro farkı (sezon kapsamı): " + ", ".join(
                f"{PENCERE_ADLARI[p]} {para(pa['ciro']['sezon']['fark'][p])}" for p in PENCERE_ADLARI))
            print(f"  brüt kâr farkı {para(pa['brut_kar_farki']['sezon'])}; net " + ", ".join(
                f"{PAKET_ADLARI[p]} {para(pa['net'][p])}" for p in PAKETLER))
            st = o["stok"]["sezon"]
            print(f"  stok farkı: çıkışta kalan {isaretli(st['cikista_kalan']['fark']['adet'])} adet, outlet'e giden "
                  f"{isaretli(st['outlete_giden']['fark']['adet'])}, ölü stok {isaretli(st['olu_stok']['fark']['adet'])}")
    alt("iki sezon (demonun sayıları)")
    for kol in YOL0_KOLLARI:
        _yol0_ozet(v, kol, TOPLAM)


# ---------------------------------------------------------------------------
# YOLLAR
# ---------------------------------------------------------------------------


def yollar_bolumu(v, ek) -> None:
    print("5 talep yolu (yol 0 yayımlanan dünya). Net (orta paket) M TL ve kırık beden farkı (indirimden önceki son "
          "pazartesi, bütün stok); önde = net > 0, azalır = kırık beden farkı < 0.")
    for kol in oyun.ANA_KOLLAR:
        for z in (*SEZONLAR, TOPLAM):
            n2 = [yuv(mtl(net(OO(v, kol, z, p))), 2) for p in oyun.YOLLAR]
            kb = [sum(kirik_farki(o) for o in OO(v, kol, z, p)) for p in oyun.YOLLAR]
            md = yuv(statistics.median(n2), 2)
            print(f"  {kol} · {SEZON_ADLARI[z]}: net yol 0–4 {', '.join(isaretli(x, 2) for x in n2)}; "
                  f"{sum(x > 0 for x in n2)}/5 yolda önde, medyan {_m2(md)}; kırık beden farkı "
                  f"{', '.join(isaretli(x) for x in kb)}; {sum(x < 0 for x in kb)}/5 yolda azalıyor, medyan "
                  f"{isaretli(statistics.median(kb), 1)}")


# ---------------------------------------------------------------------------
# AYRIŞIM
# ---------------------------------------------------------------------------


def _ayrisim(v, a: str, b: str, z: str, yol: int = 0) -> tuple[float, int, float, float]:
    """(net orta farkı iki ondalık M TL, kırık beden farkı a − b, a ve b'nin net iki ondalığı)."""
    na, nb = net(OO(v, a, z, yol)), net(OO(v, b, z, yol))
    kb = sum(kirik_farki(o) for o in OO(v, a, z, yol)) - sum(kirik_farki(o) for o in OO(v, b, z, yol))
    return fark(mtl(nb), mtl(na), 2), kb, na, nb


def ayrisim_bolumu(v, ek) -> None:
    print("İki kol arasındaki fark (a − b): net (orta paket) basılan iki ondalıklı düzeylerin farkı; kırık beden "
          "farkı a'nın kırık beden farkı − b'ninki (indirimden önceki son pazartesi, bütün stok; eksi = a daha çok "
          "azaltıyor).")
    cevap = {}
    for n, a, b, ad in AYRISIMLAR:
        alt(f"S{n} {a} − {b} ({ad})")
        for z in (*SEZONLAR, TOPLAM):
            d2, kb, na, nb = _ayrisim(v, a, b, z)
            print(f"  {SEZON_ADLARI[z]} {a} − {b}: net (orta) {fark_para(nb, na)}, kırık beden {isaretli(kb)} "
                  f"({a} {para(na)}, {b} {para(nb)})")
            cevap[(n, z)] = (d2, kb)
        if a != "kural" or b != "kural_28":
            yollar = [_ayrisim(v, a, b, z, p) for z in SEZONLAR for p in oyun.YOLLAR]
            print(f"  bütün yollar ve iki sezon (10 koşu çifti): net {a} önde {sum(x[0] > 0 for x in yollar)}/10, "
                  f"medyan {_m2(yuv(statistics.median(x[0] for x in yollar), 2))}; kırık beden {a} daha çok azaltıyor "
                  f"{sum(x[1] < 0 for x in yollar)}/10")
    d3, kb3 = cevap[(3, TOPLAM)]
    print(f"  beklenti (K13) set koşulu kazancı azaltır, kırık bedeni daha çok azaltır: {tutuyor(d3 > 0 and kb3 > 0)} "
          f"(opt − opt_set iki sezon: net {_m2(d3)}, kırık beden {isaretli(kb3)})")
    soru(3, f"optimizasyon kuralın neresinde, set tamamlamak doğru hedef mi: opt − opt_set iki sezonda net (orta) "
            f"{_m2(d3)}, kırık beden {isaretli(kb3)} (opt_set kırık bedeni {yon(kb3, 'daha çok', 'daha az', 'aynı')} "
            f"azaltıyor, set koşulu kazancı {yon(d3, 'azaltıyor', 'artırıyor', 'değiştirmiyor')})")
    d4, kb4 = cevap[(4, TOPLAM)]
    soru(4, f"STD mi son 28 gün mü: kural − kural_28 iki sezonda net (orta) {_m2(d4)}, kırık beden {isaretli(kb4)} "
            f"({yon(d4, "STD'li puan önde", 'son 28 gün önde', 'ikisi aynı')})")
    d7, kb7 = cevap[(7, TOPLAM)]
    soru(7, f"tahmin hatasının payı: kahin − opt iki sezonda net (orta) {_m2(d7)}, kırık beden {isaretli(kb7)} "
            "(talebi ve fiyat yolunu bilmenin değeri)")


# ---------------------------------------------------------------------------
# SATIŞA DÖNÜŞ
# ---------------------------------------------------------------------------


def _sd_toplam(oo: list[dict]) -> dict:
    sd = [o["satisa_donus"] for o in oo]
    out = {a: topla(sd, lambda x, a=a: x[a]) for a in ("alinan_adet", "indirime_satilan", "cikisa_satilan",
                                                       "vericide_kayip_adet", "alicida_kazanc_adet")}
    out["etki_adet"] = {p: topla(sd, lambda x, p=p: x["etki_adet"][p]) for p in PENCERE_ADLARI}
    out["etki_adet_fiziksel"] = {p: topla(sd, lambda x, p=p: x["etki_adet_fiziksel"][p]) for p in PENCERE_ADLARI}
    out["tasinan"] = sum(o["plan"]["adet"] for o in oo)
    out["saha_indirime"] = oran(out["indirime_satilan"], out["alinan_adet"])
    out["saha_cikisa"] = oran(out["cikisa_satilan"], out["alinan_adet"])
    out["etki_oran"] = oran(out["etki_adet"]["toplam"], out["tasinan"])
    return out


def satisa_donus_bolumu(v, ek) -> None:
    print("Saha ölçüsü: alıcı hücrenin varıştan sonraki satışı (alınanla sınırlı) ÷ alınan. Gerçek etki (yalnız "
          "simülasyonda): transfer edilen option'ların bütün mağaza ve kanallarında net satış farkı ÷ taşınan adet.")
    for kol in YOL0_KOLLARI:
        for z in (*SEZONLAR, TOPLAM):
            t = _sd_toplam(OO(v, kol, z))
            e, f = t["etki_adet"], t["etki_adet_fiziksel"]
            print(f"  {kol} · {SEZON_ADLARI[z]}: alınan {s(t['alinan_adet'])}; saha indirime {yuzde(t['saha_indirime'])}, "
                  f"çıkışa {yuzde(t['saha_cikisa'])}; etki " + ", ".join(
                      f"{p} {isaretli(e[p])}" for p in PENCERE_ADLARI) + f" adet, taşınanın {yuzde(t['etki_oran'])}; "
                  f"fiziksel mağazalarda {isaretli(f['toplam'])}; vericide {isaretli(t['vericide_kayip_adet'])}, "
                  f"alıcıda {isaretli(t['alicida_kazanc_adet'])} adet")
    o = {z: O(v, "kural", z) for z in SEZONLAR}
    kb = {z: (kirik_farki(o[z], kapsam="transfer_edilen"), kirik_farki(o[z])) for z in SEZONLAR}
    sd = {z: o[z]["satisa_donus"] for z in SEZONLAR}
    soru(1, "kural kırık bedeni indirimden önceki son pazartesi " + "; ".join(
        f"{z} transfer edilen çiftlerde {isaretli(kb[z][0])}, bütün stokta {isaretli(kb[z][1])}" for z in SEZONLAR)
        + "; alınan malın satışa dönüşü (saha) " + "; ".join(
        f"{z} indirime kadar {yuzde(sd[z]['saha_indirime'])}, çıkışa kadar {yuzde(sd[z]['saha_cikisa'])}"
        for z in SEZONLAR))
    t = _sd_toplam(OO(v, "kural", TOPLAM))
    e = t["etki_adet"]
    pay = {p: oran(e[p], e["toplam"]) for p in ("tam", "indirim", "outlet")}
    cf = {p: topla(OO(v, "kural", TOPLAM), lambda x, p=p: x["para"]["ciro"]["sezon"]["fark"][p]) for p in PENCERE_ADLARI}
    soru(5, "kurtarılan satış (kural, iki sezon, bütün kanallar): " + ", ".join(
        f"{p} {isaretli(e[p])} adet, payı {yuzde(pay[p])}" for p in ("tam", "indirim", "outlet"))
        + f" = {isaretli(e['toplam'])} adet; ciro farkı tam fiyat {para(cf['tam'])}, indirim {para(cf['indirim'])}, "
        f"outlet {para(cf['outlet'])}")
    soru(6, f"sahanın görmediği (kural, iki sezon): saha alıcıda çıkışa kadar {s(t['cikisa_satilan'])} adet satış "
            f"görüyor, gerçek etki {isaretli(e['toplam'])} adet; vericide kaybedilen satış "
            f"{isaretli(t['vericide_kayip_adet'])} adet, alıcıda kazanç {isaretli(t['alicida_kazanc_adet'])} adet")


# ---------------------------------------------------------------------------
# PARA
# ---------------------------------------------------------------------------


def para_bolumu(v, ek) -> None:
    print("Ciro farkı satis.tutar (net TL, iade dahil), bütün mağaza ve kanallar, karar → çıkış + 84; arz kollarda aynı "
          "olduğu için katkı farkıdır. Maliyet = toplama × adet + kargo × rota + yıpranma × alış değeri; net = ciro farkı "
          "− maliyet. Paketler (adet başı TL, rota başı TL, yıpranma oranı 0–1): " + "; ".join(
              f"{PAKET_ADLARI[p]} {s(k.toplama_birim_tl, 1)} / {s(k.kargo_rota_tl, 1)} / {s(k.yipranma_orani, 2)}"
              for p, k in sabitler.MALIYET_PAKETLERI.items()))
    for kol in YOL0_KOLLARI:
        for z in (*SEZONLAR, TOPLAM):
            oo = OO(v, kol, z)
            cf = topla(oo, lambda o: o["para"]["ciro"]["sezon"]["fark"]["toplam"])
            ct = topla(oo, lambda o: o["para"]["ciro"]["transfer_edilen"]["fark"]["toplam"])
            bk = topla(oo, lambda o: o["para"]["brut_kar_farki"]["sezon"])
            mal = {p: topla(oo, lambda o, p=p: o["para"]["maliyet"][p]["toplam"]) for p in PAKETLER}
            print(f"  {kol} · {SEZON_ADLARI[z]}: ciro farkı {para(cf)} (transfer edilen option'larda {para(ct)}), brüt kâr "
                  f"farkı {para(bk)}; maliyet " + ", ".join(f"{PAKET_ADLARI[p]} {para(mal[p])}" for p in PAKETLER)
                  + "; net " + ", ".join(f"{PAKET_ADLARI[p]} {para(net(oo, p))}" for p in PAKETLER))
            if z == "AW24":
                m = oo[0]["para"]["maliyet"]["orta"]
                print(f"    orta paket maliyetin bileşenleri: toplama {para(m['toplama'])}, kargo {para(m['kargo'])}, "
                      f"yıpranma {para(m['yipranma'])}")
    yk = yuv(mtl(net(OO(v, "kural", TOPLAM), "yuksek")), 2)
    print(f"  beklenti (K13) maliyete bakmayan kural yüksek pakette net eksiye düşer: {tutuyor(yk < 0)} (kural iki sezon "
          f"yüksek paket net {_m2(yk)})")
    soru(2, "transfer maliyetine değiyor mu (iki sezon, net = ciro farkı − maliyet): " + "; ".join(
        f"{kol} " + ", ".join(f"{PAKET_ADLARI[p]} {_m2(yuv(mtl(net(OO(v, kol, TOPLAM), p)), 2))}" for p in PAKETLER)
        + f" ({_deger_sozu([yuv(mtl(net(OO(v, kol, TOPLAM), p)), 2) for p in PAKETLER])})"
        for kol in ("kural", "opt_set", "opt")))


def _deger_sozu(nn: list[float]) -> str:
    n = sum(x > 0 for x in nn)
    return "üç pakette değiyor" if n == 3 else "hiçbir pakette değmiyor" if n == 0 else f"{n} pakette değiyor"


# ---------------------------------------------------------------------------
# TAHMİN
# ---------------------------------------------------------------------------


def tahmin_bolumu(v, ek) -> None:
    print("Kolların gördüğü tahmin (tahmin.ufuk_talebi) ile kahinin gerçek talebi (hakem.kahin_girdisi), aynı hücreler: "
          "Σ beklenen talep, WAPE = Σ |tahmin − kahin| ÷ Σ kahin, yanlılık = Σ tahmin ÷ Σ kahin − 1. Bütün hücreler ve "
          "opt planının alıcı hücreleri.")
    for z in SEZONLAR:
        t = T(v, 0, z)
        alt(f"yol 0 · {SEZON_ADLARI[z]}")
        for kap, ad in (("butun", "bütün hücreler"), ("alici", "opt'un alıcı hücreleri")):
            x = t[kap]
            print(f"  {ad} ({s(x['hucre'])} hücre): " + "; ".join(
                f"{e} tahmin {s(x[e]['tahmin'], 0)}, kahin {s(x[e]['kahin'], 0)}, WAPE {yuzde(x[e]['wape'])}, yanlılık "
                f"{yuzde(x[e]['yanlilik'])}" for e in ("mu_tam", "mu_ind", "toplam")))
        ek.append((f"TAHMİN {z}: alıcı hücreleri bütün hücrelerin alt kümesi", t["alici"]["hucre"] <= t["butun"]["hucre"]))
    alt("bütün yollar (toplam talep, bütün hücreler)")
    for z in SEZONLAR:
        print(f"  {SEZON_ADLARI[z]}: " + "; ".join(
            f"yol {p} WAPE {yuzde(T(v, p, z)['butun']['toplam']['wape'])}, yanlılık "
            f"{yuzde(T(v, p, z)['butun']['toplam']['yanlilik'])}" for p in oyun.YOLLAR))


# ---------------------------------------------------------------------------
# YAN ETKİ
# ---------------------------------------------------------------------------


def yan_etki_bolumu(v, ek) -> None:
    print("Kol − Lumoda, karar → çıkış + 84. Replenishment ve Lumoda'nın elle transferi tepkilidir (malın toplamını "
          "değiştirmez); sürekli tedarik Basic/NOS'ta zincir satışına tepki verir (Ruling R25).")
    for kol in YOL0_KOLLARI:
        for z in SEZONLAR:
            e = O(v, kol, z)["yan_etki"]
            print(f"  {kol} · {z}: replenishment {isaretli(e['replenishment_adet_farki']['sezon'])} adet (bütün SKU'lar "
                  f"{isaretli(e['replenishment_adet_farki']['tum'])}), elle transfer "
                  f"{isaretli(e['elle_transfer_adet_farki']['sezon'])} (bütün {isaretli(e['elle_transfer_adet_farki']['tum'])}), "
                  f"gizli kayıp {isaretli(e['gizli_kayip_farki'])} (Lumoda {s(e['gizli_kayip_lumoda'])}), test dışı ciro "
                  f"{para(e['test_disi_ciro_farki'])}, sürekli sipariş {isaretli(e['surekli_siparis_adet_farki'])} adet")


# ---------------------------------------------------------------------------
# HİKÂYE
# ---------------------------------------------------------------------------


def hikaye_bolumu(v, ek) -> None:
    h = H(v)
    sa = h["sahne"]
    print(f"Yol 0, {h['sezon']}, {h['kol']} kolu, {s(h['alici_cift'])} alıcı çifti. Seviye {h['seviye']} (süzgeç "
          "gevşetme sırası: tam, iki_verici, sehir_disi); seviyelerin aday sayısı " + ", ".join(
              f"{a} {s(n)}" for a, n in h["seviyeler"].items()))
    o, al = sa["option"], sa["alici"]
    print(f"  option: {o['model_adi']} ({o['renk']}, {o['alt_kategori']}), liste fiyatı {s(o['liste_fiyati'], 2)} TL")
    print(f"  alıcı: {al['ad']} ({al['sehir']}); karar sabahı bedenler " + ", ".join(
        f"{b} {s(a)}" for b, a in sa["karar"]["bedenler"].items()) + f" (asorti " + ", ".join(
        f"{b} {s(a)}" for b, a in sa["karar"]["asorti"].items()) + "); kırık bedenler "
        + ", ".join(sa["karar"]["kirik_bedenler"]) + " (depo stoğu " + ", ".join(
        f"{b} {s(a)}" for b, a in sa["karar"]["kirik_depo"].items()) + ")")
    for x in sa["vericiler"]:
        print(f"  verici {x['ad']} ({x['sehir']}): {s(x['adet'])} adet (" + ", ".join(
            f"{b} {s(a)}" for b, a in x["bedenler"].items()) + ")")
    ist_disi = sum(x["sehir"] != hikaye.ISTANBUL for x in sa["vericiler"])
    print(f"  verici {s(len(sa['vericiler']))} (İstanbul dışında {s(ist_disi)}); alınan {s(sa['alinan'])} adet (" + ", ".join(
        f"{b} {s(a)}" for b, a in sa["alinan_bedenler"].items()) + f"); varış karardan {s(sa['varis_gun'])} gün sonra; "
        f"indirime {s(sa['indirime_gun'])} gün")
    si = sa["satis_indirime"]
    print(f"  indirim gününe kadar alıcının satışı (pozitif adet): kural kolunda alınan bedenlerde "
          f"{s(si['kural']['alinan_sku'])}, option'da {s(si['kural']['option'])}; Lumoda'da aynı hücrelerde "
          f"{s(si['lumoda']['alinan_sku'])} ve {s(si['lumoda']['option'])}; saha ölçüsüyle {s(sa['saha_indirime'])} / "
          f"{s(sa['alinan'])}")
    io_ = sa["indirim_oncesi"]
    for kol, ad in (("kural", "kural kolunda"), ("lumoda", "Lumoda'da")):
        x = io_[kol]
        print(f"  indirimden önceki son pazartesi {ad}: " + ", ".join(f"{b} {s(a)}" for b, a in x["bedenler"].items())
              + f" ({'kırık: ' + ', '.join(x['kirik_bedenler']) if x['kirik'] else 'tam set'})")
    a0 = h["adaylar"][0]
    ek.append(("HİKÂYE: sahne ilk aday", (a0["alici"], a0["option_id"], a0["alinan"])
               == (al["magaza_id"], o["option_id"], sa["alinan"])))
    ek.append(("HİKÂYE: verici adetleri = alınan = beden adetleri",
               sum(x["adet"] for x in sa["vericiler"]) == sa["alinan"] == sum(sa["alinan_bedenler"].values())))
    ek.append(("HİKÂYE: kırık bedenlerin depo stoğu sıfır", all(a == 0 for a in sa["karar"]["kirik_depo"].values())))
    ek.append(("HİKÂYE: Lumoda'da indirime kırık giriyor", io_["lumoda"]["kirik"] is True))
    soru(8, f"hikâye sahnesi: {al['ad']} ({al['sehir']}), {o['model_adi']}: kırık bedenler "
            f"{', '.join(sa['karar']['kirik_bedenler'])} (depoda yok) {s(len(sa['vericiler']))} vericiden "
            f"{s(sa['alinan'])} adetle tamamlanıyor; indirime "
            f"kadar kural kolunda alınan bedenlerden {s(si['kural']['alinan_sku'])} satış, Lumoda'da aynı hücrelerde "
            f"{s(si['lumoda']['alinan_sku'])}; Lumoda'da çift indirime "
            f"{'kırık' if io_['lumoda']['kirik'] else 'tam'} giriyor")


# ---------------------------------------------------------------------------
# DEMO, KORUNUM
# ---------------------------------------------------------------------------


def demo_bolumu(v, ek) -> None:
    son = senaryolar.sonuclar(v.oyun)
    print(f"  {len(son)} bileşim: kol {{{', '.join(senaryolar.KOLLAR)}}} × paket {{{', '.join(senaryolar.PAKETLER)}}} × "
          f"sezon {{{', '.join(senaryolar.SEZONLAR)}}}; kartlar net (M TL), kırık beden farkı, saha ve etki satışa dönüş "
          "(yüzde; para ve yüzde iki ondalıklının bir kez yuvarlanmışı)")
    et = {p["ad"]: p["deger_etiketleri"] for p in senaryolar.PARAMETRELER}
    satirlar = []
    for a, r in son.items():
        kol, paket, sz = a.split("|")
        z = senaryolar.SEZONLAR[sz] or TOPLAM
        oo, oz = OO(v, kol, z), r["ozet"]
        satirlar.append([f"{et['kol'][kol]} · {et['paket'][paket]} · {et['sezon'][sz]}", isaretli(oz["net_fark_mtl"], 1),
                         isaretli(oz["kirik_beden_farki"]), yd(oz["saha_donus_yuzde"], 1), yd(oz["etki_donus_yuzde"], 1)])
        t = _sd_toplam(oo)
        ek.append((f"DEMO {a}: kartlar = rapor", (
            oz["net_fark_mtl"], oz["kirik_beden_farki"], oz["saha_donus_yuzde"], oz["etki_donus_yuzde"]) == (
            tek_ondalik(yuv(mtl(net(oo, paket)), 2)), sum(kirik_farki(o) for o in oo),
            tek_ondalik(yuv(100 * t["saha_cikisa"], 2)), tek_ondalik(yuv(100 * t["etki_oran"], 2)))))
    _tablo(["bileşim", "net (M TL)", "kırık beden farkı", "saha dönüş", "etki dönüş"], satirlar)
    ek.append(("DEMO: 27 bileşim", len(son) == len(senaryolar.KOLLAR) * len(senaryolar.PAKETLER) * len(senaryolar.SEZONLAR)))
    dosya = v.demo_dosya
    if dosya is None or dosya != senaryolar.uret(v.oyun):
        if not v.taslak:
            raise AssertionError("DEMO: site dosyası senaryolar.uret() ile aynı değil")
        print("  [eksik: demo dosyası güncel değil]")
    else:
        print(f"  site dosyası {senaryolar.HEDEF.name}: sürüm {dosya['surum']} (içeriğin özeti)")
    if v.demo_bayt is not None or not v.taslak:
        ek.append(("DEMO: sitedeki dosya bütçe içinde", v.demo_bayt is not None and v.demo_bayt < senaryolar.BUTCE))


def _ayni(a, b, tol: float = 1e-9) -> bool:
    return (_yok(a) and _yok(b)) or (not _yok(a) and not _yok(b) and abs(float(a) - float(b)) <= tol)


def korunum_bolumu(v, ek) -> None:
    for i in oyun.izgara_listesi(v.olcek):
        if i.kol == LUMODA or i.ad not in v.gecerli:
            continue
        r = v.oyun["kosular"][i.ad]
        ek.append((f"{i.ad}: korunum ({', '.join(KORUNUM_KOSULLARI)})",
                   all((r.get("korunum") or {}).get(a) is True for a in KORUNUM_KOSULLARI)))
        ek.append((f"{i.ad}: ölçümün sezonu", r["olcum"].get("sezon") == i.sezon))
        ek.append((f"{i.ad}: planın girdisi yolun Lumoda'sı", (v.planlar[i.ad]["bilgi"] or {}).get("girdi")
                   == {"yol": i.yol, "lumoda_anahtari": r["lumoda_anahtari"]}))
        o = r["olcum"]
        sd, t, h = o["satisa_donus"], _sd_toplam([o]), senaryolar.ham([o], sabitler.KARAR_PAKETI)
        ek.append((f"{i.ad}: yeniden türetilen satışa dönüş oranları = olcutler'in ölçtüğü (rapor ve demo)",
                   all(_ayni(a, b) for a, b in ((t["saha_indirime"], sd["saha_indirime"]),
                                                (t["saha_cikisa"], sd["saha_cikisa"]), (t["etki_oran"], sd["etki_oran"]),
                                                (h["saha_donus"], sd["saha_cikisa"]), (h["etki_donus"], sd["etki_oran"])))))
    ek.append(("ızgaranın bütün koşuları geçerli ve ölçülmüş",
               v.taslak or len(v.gecerli) + len(v.lumoda) == len(oyun.izgara_listesi(v.olcek))))
    if v.analiz is not None and v.olcek == "tam":
        ek.append(("VERİ yayımlanan DuckDB'den", v.analiz.get("kaynak") == "yayimlanan"))
        for z in SEZONLAR:                 # yol 0 Lumoda = yayımlanan v4: karar sabahının kırıklığı iki kaynakta aynı
            if oyun.kosu_adi("kural", z, 0) in v.gecerli:
                lum = O(v, "kural", z)["kiriklik"]["karar"]["kapsamlar"]["butun"]["lumoda"]
                hu = v.analiz["huni"][z]["ozet"]
                ek.append((f"UYGUNLUK {z}: analiz.json karar sabahı = yol 0 Lumoda koşusunun karar fotoğrafı",
                           all(hu[a] == lum[a] for a in ("stoklu_cift", "kirik_cift", "dar_kirik_cift", "kirik_beden",
                                                         "eksik_adet"))))
    n = korunum(ek)
    print(f"  {s(n)} denetim tuttu: {s(len(v.gecerli))} koşunun korunumu ({', '.join(KORUNUM_KOSULLARI)}), ölçümün "
          "sezonu, planın girdisi, yeniden türetilen satışa dönüş oranları; plan önbelleği bugünkü karar koduyla; uygunluk "
          "hunisi; hikâye sahnesi; demo kartları.")
    print(f"  oyun.json kayıtları bugünkü ölçüm koduyla ({v.olcum_kodu[:12]}); analiz.json "
          f"{(v.analiz or {}).get('kod', '—')[:12]}; hikaye.json {(v.hikaye or {}).get('kod', '—')[:12]}.")


BOLUMLER = [
    ("VERİ", veri_bolumu), ("KIRIKLIK", kiriklik_bolumu), ("ATIL", atil_bolumu), ("UYGUNLUK", uygunluk_bolumu),
    ("PLAN", plan_bolumu), ("YOL 0", yol0_bolumu), ("YOLLAR", yollar_bolumu), ("AYRIŞIM", ayrisim_bolumu),
    ("SATIŞA DÖNÜŞ", satisa_donus_bolumu), ("PARA", para_bolumu), ("TAHMİN", tahmin_bolumu),
    ("YAN ETKİ", yan_etki_bolumu), ("HİKÂYE", hikaye_bolumu), ("DEMO", demo_bolumu), ("KORUNUM", korunum_bolumu),
]


def govde(v) -> None:
    """Bütün bölümler sırasıyla; korunum en sonda (tutmazsa AssertionError). Taslakta `Eksik` veren bölüm atlanır."""
    print("Kırıklık Transferi ve Kırıklık ve Atıl Stok — v4 raporu. Kaynak: cikti/oyun.json (python -m kiriklik.oyun), "
          f"cikti/analiz.json, cikti/hikaye.json, plan önbelleği, site/src/data/senaryolar/{senaryolar.HEDEF.name}.")
    ek: list = []
    atlanan = []
    for ad, f in BOLUMLER:
        baslik(ad)
        try:
            f(v, ek)
        except Eksik as e:
            if not v.taslak:
                raise
            print(f"  [eksik: {'; '.join(e.neler)}]")
            atlanan.append(ad)
    if v.taslak:
        print(f"\nTASLAK: {s(len(v.eksik))} eksik ya da eski girdi, {s(len(atlanan))} bölüm atlandı (bu çıktı yazılara "
              "kaynak olamaz):")
        for e in v.eksik:
            print(f"  {e}")
        if "KORUNUM" in atlanan:
            return
    korunum(ek)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rapor.py", description=__doc__.split("\n")[0])
    p.add_argument("--taslak", action="store_true", help="eski ya da eksik girdiyle biçim denetimi (çıkış 2)")
    p.add_argument("--kucuk", action="store_true", help="KÜÇÜK ölçeğin çıktıları (cikti/kucuk/; çıkış 2)")
    a = p.parse_args(argv)
    try:
        v = hazirla(kucuk=a.kucuk, taslak=a.taslak)
    except Eksik as e:
        print("Eksik:\n  " + "\n  ".join(e.neler), file=sys.stderr)
        return 1
    kod, metin = tamponla(lambda: govde(v))
    if kod:
        return kod
    if yillar(metin):
        print(f"korunum bozuldu: rapor yıl basıyor ({', '.join(sorted(set(yillar(metin))))})", file=sys.stderr)
        return 1
    sys.stdout.write(metin)
    return 2 if v.taslak else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
