"""İndirim Takvimi dizisinin (6 yazı, `/indirim/indirim-takvimi/`) yayımlanacak BÜTÜN sayıları buradan basılır (v4).

    cd vakalar/markdown
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m markdown.oyun kalibrasyon      # cikti/kalibrasyon.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m markdown.oyun izgara           # cikti/oyun.json (koşular, ölçüm)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m markdown.oyun izgara --blok ablasyon   # kuralın ayrışımı (R24)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python analiz.py                         # cikti/analiz.json (koşusuz)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m markdown.hikaye                # cikti/hikaye.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py                     # demo JSON
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py --taslak                # eksik girdiyle biçim denetimi
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py --kucuk                 # cikti/kucuk/ (geliştirme)

Kalıcı kural: yazıya yeni bir sayı girmeden önce buraya eklenir; ortak sayı denetimi (`cd vakalar/markdown &&
.venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi ../../site/src/content/yazi/indirim/indirim-takvimi
--rapor cikti/rapor.txt`) yazılardaki her sayının bu çıktıda geçtiğini denetler. Sayılar Türkçe basılır (binlik
nokta, ondalık virgül, `%12,34`, `−0,32`). Uydurma sayı yasaktır; elle konmuş anlatı değerleri yalnız ANLATI
VARSAYIMLARI'ndadır. Rapor takvim tarihi ve yıl basmaz (yazıya girecek satırlarda sezon kodu dışında yıl yok;
günler indirim haftasına ya da lansmana göre hafta olarak basılır).

Bölümler (`BOLUMLER`, bu sırayla; spec §5). Başlık sorularının (spec §4.6) her biri ilgili bölümde tek bir
`SORU n · …` satırıdır (cevap basılan değerlerden; yön sözcükleri hesaplanan değerden):

    VERİ                 sezon sonu hunisi, Lumoda'nın kademe dağılımı, indirim başı STR'si ve çeyrekleri,
                         haftalık satış, geç RPT; beş sezonun aralıkları
    ESNEKLİK             öğrenilen ε̂ (saf, markdown, kampanya) ve gerçek ε; tek-option hesabı (SORU 4)
    KALİBRASYON          kural α ve tekdüze oran ızgarası (iki kalibrasyon sezonu), Lumoda'ya göre
    YOL 0                bütün kollar, bütün ölçütler, iki sezon ve toplam; Lumoda'ya farklar (SORU 1, 3, 6)
    AYRIŞIM              kime / ne zaman / etkileşim / ne kadar (SORU 5); kapsama kuralının kaynağı: Lumoda →
                         kural_takvim → kural, kural_deposuz → kural (Ruling R24; SORU 2)
    ÇEYREK               Lumoda'nın indirim başı STR çeyreklerine göre kazanç (SORU 7)
    YOLLAR               5 talep yolu: Lumoda'ya katkı farkı, min / medyan / max, k/n önde
    TAHMİN İSABETİ       kolların pazartesi kaydının tahmini satışı ↔ gerçekleşen (WAPE)
    YAN ETKİ             test dışı option'ların ciro farkı, ikame, elle transfer
    HİKÂYE               iki tulum (haftalık seri, stok, kollar), Oduncu Gömlek, pazartesi listesi (SORU 8)
    DEMO                 18 bileşim, site dosyası
    ANLATI VARSAYIMLARI
    KORUNUM              koşuların sözleşmeleri, aynı mal, yol 0 = yayımlanan, karar anı doğrulaması, tazelik

Rapor önce tampona yazılır; korunum tutmazsa ya da bir girdi eksik ya da eskiyse (ızgaranın bir koşusu yok ya da
bugünkü ölçüm koduyla ölçülmemiş, koşunun önbellek dizini yok; `analiz.json`, `hikaye.json` bugünkü kodla
yazılmamış; `kalibrasyon.json` bugünkü ölçüm koduyla değil; demo dosyası `senaryolar.uret()` ile aynı değil) stdout'a
tek satır gitmez, mesaj stderr'e, çıkış kodu 1 (`Eksik`). `--taslak` eksik girdiye dayanan bölümleri "[eksik: …]"
diye geçer ve sonda listeler (çıkış kodu 2; bu çıktı yazılara kaynak olamaz); `--kucuk` KÜÇÜK ölçeğin çıktılarını
okur (her zaman taslak). Basılan her fark ve oran basılan işlenenlerden hesaplanır (`yuv`, `fark`, `bolum`); tek
ondalıklı her fark iki ondalıklı farkın bir kez yuvarlanmışıdır (`fark1`): aynı büyüklüğe tek değer. Ölçülen
süre basılmaz. Bu dosya veriyi okumaz, simülasyon koşmaz.

Para milyon TL'dir (iki ondalık; farkın yanında parantezde bir kez yuvarlanmış bir ondalık), yüzdeler iki
ondalık, adetler tam sayı. Tanımlar `markdown/olcutler.py`'nin (YOL 0 ve sonrası) ve `analiz.py`'nin (VERİ)
notlarındadır.
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
from markdown import hikaye, oyun, sabitler, simulasyon

KOK = Path(__file__).resolve().parent
SEZONLAR = ("SS25", "AW24")             # yazının ana sahnesi önce
TOPLAM = "toplam"
SEZON_ADLARI = {"SS25": "SS25 (yaz)", "AW24": "AW24 (kış)", TOPLAM: "iki sezon"}
LUMODA = oyun.LUMODA
KORUNUM_ALANLARI = ("rpt_birebir", "ilk_dagitim_birebir", "arz_birebir", "merdiven", "siglasmaz", "pencere",
                    "takvim_tabani")

ANLATI_VARSAYIMLARI = {
    "kadro": "İstanbul mağazaları Ali'nin, Anadolu (İstanbul dışı) mağazaları Veli'nin (allocator); Pelin planner ve "
             "markdown listesinin sahibi (Lumoda'nın kuralı onun tablosu); Pars veriyi açan analist",
    "istanbul": "İstanbul = mağazanın şehri \"İstanbul\" (outlet ve online hariç fiziksel mağazalar); Anadolu = öteki "
                "fiziksel mağazalar",
    "mayista": "\"opt tulumu Mayısta indiriyor\" = opt'un ilk oranlı haftası Lumoda'nın kuralının başlayabileceği "
               "günden (indirim − 28) önce (HİKÂYE `ders`); takvim adı yazıya girmez",
    "karar_gunu": "\"karar günü\" = option'ın serbest karar penceresinin ilk pazartesisi, max(indirim − 56, lansman + 42) "
                  "(Ruling R9); \"indirim günü\" = indirim haftasının pazartesisi",
    "hafta": "haftalar pazartesi başlar; \"hafta k\" indirim haftasına göre (0 indirim haftası, −8 indirimden 8 hafta "
             "önce); \"lansman haftası k\" lansmandan k hafta sonra",
    "markdown_tl": "markdown TL ve outlet indirimi her bölümde olcutler tanımıdır (pozitif satış, kampanyasız, normal ve "
                   "online hat, oran > 0, lansman → çıkış; iadeden önce; outlet hattı çıkış → + 84); VERİ'nin \"keşif "
                   "tanımları\" satırı spec §0'ın iade düşülmüş indirim dönemi değeridir ve yazıda kullanılmaz (Ruling R21)",
    "kucuk": "KÜÇÜK ölçekte sahnenin option'ları yoktur; hikâye kuralla seçilmiş yedek option'ları basar (yalnız "
             "geliştirme)",
}

# ölçüt → (etiket, tür): t para (milyon TL), y yüzde, a adet, h hafta (bir ondalık)
OLCUTLER = (
    ("katki", "sezon katkısı", "t"), ("ciro_toplam", "toplam ciro", "t"), ("ciro_sezon", "sezon cirosu", "t"),
    ("ciro_outlet", "outlet cirosu", "t"), ("brut_kar", "brüt kâr", "t"), ("markdown_tl", "markdown TL", "t"),
    ("markdown_tl_online", "  online markdown TL", "t"), ("kampanya_tl", "kampanya TL", "t"),
    ("islem_tl", "işlem indirimi TL", "t"), ("outlet_indirim_tl", "outlet indirimi TL", "t"),
    ("tam_fiyat_str", "tam fiyat STR", "y"), ("son_str", "son STR", "y"), ("arz_adet", "arz (adet)", "a"),
    ("cikis_kalan_adet", "çıkışta kalan", "a"), ("cikis_kalan_magaza_adet", "  mağazada", "a"),
    ("cikis_kalan_depo_adet", "  depoda", "a"), ("cikis_kalan_liste", "çıkışta kalan liste değeri", "t"),
    ("cikis_kalan_alis", "çıkışta kalan alış değeri", "t"), ("olu_stok_adet", "ölü stok", "a"),
    ("olu_stok_alis", "ölü stok alış değeri", "t"), ("indirilen_option", "indirilen option", "a"),
    ("ilk_indirim_hafta_medyan", "ilk indirim haftası (medyan)", "h"), ("ort_en_derin", "ortalama en derin oran", "y"),
    ("muaf_str_ind", "muafların indirim başı STR'si", "y"), ("bulunabilirlik", "bulunabilirlik", "y"),
    ("kayip_orani", "kayıp oranı", "y"))
FARK_OLCUTLERI = ("katki", "ciro_toplam", "brut_kar", "markdown_tl", "outlet_indirim_tl", "tam_fiyat_str", "son_str",
                  "cikis_kalan_adet", "olu_stok_adet", "olu_stok_alis", "indirilen_option", "bulunabilirlik")
ONDALIK = {"t": 2, "y": 2, "a": 0, "h": 1}
KOL_ADLARI = {LUMODA: "Lumoda", "tekduze": "tekdüze", "kural": "kural", "opt_tuzak": "opt_tuzak", "opt": "opt",
              "opt_takvim": "opt_takvim", "opt_erken_yok": "opt_erken_yok", "opt_taban": "opt_taban", "kahin": "kahin"}
YOL0 = (LUMODA, *oyun.YOL0_KOLLARI)


class Eksik(Exception):
    """Raporun dayandığı bir girdi yok ya da eski (stderr, çıkış 1; taslakta bölüm atlanır)."""

    def __init__(self, *neler: str):
        super().__init__("; ".join(neler))
        self.neler = list(neler)


# ---------------------------------------------------------------------------
# Biçim (Beden ve Koli raporunun kuralları)
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


def bolum(a, b, ondalik_a: int = 0, ondalik_b: int = 0) -> float | None:
    payda = yuv(b, ondalik_b)
    return yuv(a, ondalik_a) / payda if payda else None


def mtl(x) -> float:
    return float(x) / 1e6


def deger(ad_tur: str, x) -> str:
    """Ölçütün kendi biçimiyle (tür `OLCUTLER`)."""
    if _yok(x):
        return "—"
    if ad_tur == "t":
        return s(mtl(x), 2)
    if ad_tur == "y":
        return yd(x, 2)
    if ad_tur == "h":
        return s(x, 1)
    return s(x, 0)


def farki(tur: str, a, c) -> str:
    """c − a ölçütün biçiminde (para M TL ve yüzde: iki ondalık + bir kez yuvarlanmış bir ondalık)."""
    if _yok(a) or _yok(c):
        return "—"
    if tur == "t":
        return f"{isaretli(fark(mtl(a), mtl(c), 2), 2)} M TL ({isaretli(fark1(mtl(a), mtl(c)), 1)})"
    if tur == "y":
        return f"{isaretli(fark(a, c, 2), 2)} puan ({isaretli(fark1(a, c), 1)})"
    if tur == "h":
        return f"{isaretli(fark(a, c, 1), 1)} hafta"
    return isaretli(fark(a, c, 0), 0)


def yon(x, arti: str, eksi: str, esit: str = "aynı") -> str:
    return arti if x > 0 else eksi if x < 0 else esit


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
        print("Eksik: " + "\n  ".join(e.neler), file=sys.stderr)
        return 1, ""
    return 0, tampon.getvalue()


YIL = re.compile(r"(?<![0-9A-Za-z])(?:19|20)\d{2}(?![0-9A-Za-z])")


def yillar(metin: str) -> list[str]:
    """Metinde geçen yıllar (dört haneli 19xx / 20xx, harf ya da rakama bitişik olmayan; sezon kodu ve özet
    dizgesi yakalanmaz). Rapor yıl basmaz: yazılar tarih ve yıl basmaz, raporun yazıya girecek satırları da."""
    return YIL.findall(metin)


def korunum(denetimler: list[tuple[str, bool]]) -> int:
    """Denetimlerin hepsi tutmalı; tutmayanlar adlarıyla AssertionError. Döner: denetim sayısı."""
    if not denetimler:
        raise AssertionError("korunum: hiç denetim yok")
    hatalar = [ad for ad, ok in denetimler if not bool(ok)]
    if hatalar:
        raise AssertionError("korunum bozuldu:\n  " + "\n  ".join(hatalar))
    return len(denetimler)


def gun_metni(g) -> str:
    """İndirim gününe göre gün: −79 → "indirimden 79 gün önce", 2 → "indirim gününden 2 gün sonra (indirimin 3. günü)"."""
    g = int(g)
    return (f"indirimden {s(-g)} gün önce" if g < 0 else "indirim günü (indirimin 1. günü)" if g == 0
            else f"indirim gününden {s(g)} gün sonra (indirimin {s(g + 1)}. günü)")


def hk(h) -> str:
    """İndirim haftasına göre hafta numarası: 0, −8, +3."""
    return "0" if int(h) == 0 else isaretli(int(h))


def hafta_metni(h) -> str:
    """İndirim haftasına göre hafta: 0 → "indirim haftası", −8 → "indirimden 8 hafta önce"."""
    if h is None:
        return "—"
    h = int(h)
    return "indirim haftası" if h == 0 else f"indirimden {s(-h)} hafta önce" if h < 0 else f"indirimden {s(h)} hafta sonra"


# ---------------------------------------------------------------------------
# Girdiler
# ---------------------------------------------------------------------------


@dataclass
class Veri:
    oyun: dict
    analiz: dict | None
    hikaye: dict | None
    kalibrasyon: dict | None
    demo_dosya: dict | None
    olcek: str = "tam"
    taslak: bool = False
    demo_bayt: int | None = None
    gecerli: set = field(default_factory=set)
    eksik: list = field(default_factory=list)
    olcum_kodu: str = ""


def _json(yol: Path) -> dict | None:
    yol = Path(yol)
    return json.loads(yol.read_text(encoding="utf-8")) if yol.is_file() else None


def izgara() -> list:
    """Raporun beklediği bütün koşular: kalibrasyon (18) + yol 0 (17) + yollar (52) + ablasyon (4; Ruling R24)."""
    return oyun.izgara_listesi("kalibrasyon") + oyun.izgara_listesi("hepsi") + oyun.izgara_listesi("ablasyon")


def gecerli_kosular(oyun_kaydi: dict, olcum_kodu: str, onbellek: Path) -> tuple[set, list]:
    """Izgaranın ölçülmüş ve önbellekte duran kayıtları; ve eksikler."""
    kosular = oyun_kaydi.get("kosular", {})
    ok, eksik = set(), []
    for k in izgara():
        e = kosular.get(k.ad)
        if e is None or "olcutler" not in e:
            eksik.append(f"oyun.json: {k.ad} yok (python -m markdown.oyun izgara / kalibrasyon)")
        elif e.get("olcum_kodu") != olcum_kodu:
            eksik.append(f"oyun.json: {k.ad} bugünkü ölçüm koduyla ölçülmemiş (python -m markdown.oyun olc)")
        else:
            m = Path(onbellek) / f"{k.ad}_{e['anahtar'][:20]}" / "meta.json"
            if not m.is_file() or json.loads(m.read_text(encoding="utf-8")).get("anahtar") != e["anahtar"]:
                eksik.append(f"önbellek: {k.ad} koşusu {m.parent.name} yok ya da anahtarı farklı")
            else:
                ok.add(k.ad)
    return ok, eksik


def hazirla(*, kucuk: bool = False, taslak: bool = False, cikti: Path | None = None, demo_yol: Path | None = None,
            olcum_kodu: str | None = None, analiz_kodu: str | None = None, hikaye_kodu: str | None = None,
            onbellek: Path | None = None) -> Veri:
    """Girdileri okur ve tazeliklerini denetler. Kesin kipte eksik ya da eski girdi `Eksik`; taslakta
    `Veri.eksik`'e yazılır. `oyun.json` her iki kipte de gerekir."""
    olcek = "kucuk" if kucuk else "tam"
    cikti = Path(cikti) if cikti is not None else (oyun.CIKTI / "kucuk" if kucuk else oyun.CIKTI)
    demo_yol = (senaryolar.KUCUK_HEDEF if kucuk else senaryolar.HEDEF) if demo_yol is None else Path(demo_yol)
    onbellek = simulasyon.KOSU_DIZINI if onbellek is None else Path(onbellek)
    kod = oyun.olcum_kodu() if olcum_kodu is None else olcum_kodu
    o = _json(cikti / "oyun.json")
    if o is None:
        raise Eksik(f"{cikti / 'oyun.json'} yok: önce python -m markdown.oyun izgara")
    sorun = []
    if o.get("olcek") != olcek:
        sorun.append(f"oyun.json {o.get('olcek')} ölçeğinde (beklenen {olcek})")
    gec, ek = gecerli_kosular(o, kod, onbellek)
    sorun += ek
    a = _json(cikti / "analiz.json")
    if a is None:
        sorun.append("analiz.json yok (python analiz.py)")
    else:
        if a.get("kod") != (analiz.kod_ozeti() if analiz_kodu is None else analiz_kodu):
            sorun.append("analiz.json bugünkü kodla yazılmamış (python analiz.py)")
        if a.get("olcek") != olcek:
            sorun.append(f"analiz.json {a.get('olcek')} ölçeğinde")
    h = _json(cikti / "hikaye.json")
    if h is None:
        sorun.append("hikaye.json yok (python -m markdown.hikaye)")
    else:
        if h.get("kod") != (hikaye.kod_ozeti() if hikaye_kodu is None else hikaye_kodu):
            sorun.append("hikaye.json bugünkü kodla yazılmamış (python -m markdown.hikaye)")
        if h.get("olcek") != olcek:
            sorun.append(f"hikaye.json {h.get('olcek')} ölçeğinde")
    k = _json(cikti / "kalibrasyon.json")
    if k is None:
        sorun.append("kalibrasyon.json yok (python -m markdown.oyun kalibrasyon)")
    elif k.get("olcum_kodu") != kod or k.get("olcek") != olcek:
        sorun.append("kalibrasyon.json bugünkü ölçüm koduyla ya da bu ölçekte değil (python -m markdown.oyun kalibrasyon)")
    demo = _json(demo_yol)
    if demo is None:
        sorun.append(f"{demo_yol.name} yok (python senaryolar.py)")
    if kucuk:
        sorun.append("KÜÇÜK ölçek: geliştirme çıktısı")
    if sorun and not (taslak or kucuk):
        raise Eksik(*sorun)
    return Veri(oyun=o, analiz=a, hikaye=h, kalibrasyon=k, demo_dosya=demo, olcek=olcek, taslak=taslak or kucuk,
                demo_bayt=demo_yol.stat().st_size if demo is not None else None, gecerli=gec, eksik=sorun,
                olcum_kodu=kod)


# ---------------------------------------------------------------------------
# Kısayollar
# ---------------------------------------------------------------------------


def K(v, ad: str) -> dict:
    """Ölçülmüş ve önbellekte geçerli koşunun kaydı; değilse `Eksik`."""
    if ad not in v.gecerli:
        raise Eksik(f"koşu {ad}")
    return v.oyun["kosular"][ad]


def ad_(yol: int, kol: str, sezon: str | None = None) -> str:
    return oyun.kosu_adi(yol, LUMODA) if kol == LUMODA else oyun.kosu_adi(yol, kol, sezon)


def O(v, kol: str, sezon: str, yol: int = 0) -> dict:
    """(yol, kol, sezon) ölçütleri; sezon `toplam` ise `toplamlar[yol][kol]` (iki koşunun toplamı)."""
    if sezon == TOPLAM:
        if kol == LUMODA:
            K(v, ad_(yol, LUMODA))
        else:
            for z in SEZONLAR:
                K(v, ad_(yol, kol, z))
        t = ((v.oyun.get("toplamlar") or {}).get(str(yol)) or {}).get(kol)
        if t is None:
            raise Eksik(f"toplam yol {yol} {kol}")
        return t["olcutler"]
    if kol == LUMODA:
        return K(v, ad_(yol, LUMODA))["olcutler"][sezon]
    return K(v, ad_(yol, kol, sezon))["olcutler"]


def A(v) -> dict:
    if v.analiz is None:
        raise Eksik("analiz.json")
    return v.analiz


def H(v) -> dict:
    if v.hikaye is None:
        raise Eksik("hikaye.json")
    return v.hikaye


def kol_adi(kol: str) -> str:
    return KOL_ADLARI.get(kol, kol)


def katki_mtl(v, kol, sezon, yol=0) -> float:
    return yuv(mtl(O(v, kol, sezon, yol)["katki"]), 2)


def kfark(v, a: str, c: str, sezon: str, yol: int = 0) -> float:
    """c − a sezon katkısı, milyon TL, iki ondalık (basılan düzeylerden)."""
    return fark(mtl(O(v, a, sezon, yol)["katki"]), mtl(O(v, c, sezon, yol)["katki"]), 2)


def kfark_metni(x2: float) -> str:
    return f"{isaretli(x2, 2)} M TL ({isaretli(tek_ondalik(x2), 1)})"


# ---------------------------------------------------------------------------
# VERİ
# ---------------------------------------------------------------------------


KIRLI_STOK_PAYI = 450      # yayımlamanın hayalet stok kaydı: 150 satır × en çok 3 adet (v4 kirlet; VERİ ↔ YOL 0)


def _huni_satirlari(h: dict, ob: dict) -> None:
    o = ob["olcutler"]
    print(f"  arz {s(h['arz'])} adet = ilk {s(h['arz_ilk'])} + RPT {s(h['arz_rpt'])} ({s(h['rpt_option'])} option'a RPT); "
          f"alış değeri {s(mtl(h['arz_alis']), 2)} M TL")
    print(f"  Lumoda'nın indirim penceresinden önce (indirim − 28'e kadar) pozitif satış {s(h['satis_tam'])} adet; "
          f"erken indirim penceresinde (indirim − 28 → indirim) {s(h['satis_erken'])} adet; indirim başına kadar "
          f"{s(h['satis_once'])} adet")
    print(f"  indirim döneminde (indirim → çıkış) {s(h['satis_ind'])} adet, net ciro {s(mtl(h['ciro_ind']), 2)} M TL, "
          f"adet başı fiyat ÷ liste fiyatı {y(h['ind_fiyat_payi'])}")
    print(f"  outlet'e giden {s(h['outlet_akisi'])} adet; outlet mağazalarında 84 günde {s(h['outlet_satis'])} adet satış, "
          f"net ciro {s(mtl(h['outlet_ciro']), 2)} M TL, adet başı fiyat ÷ liste fiyatı {y(h['outlet_fiyat_payi'])}")
    print(f"  RPT'si indirim − 28'den sonra teslim edilen {s(h['rpt_gec_option'])} option, {s(h['rpt_gec_adet'])} adet")
    print("  olcutler tanımıyla (YOL 0'ın Lumoda'sı, aynı işlev; Ruling R21; yazıların tek tanımı):")
    print(f"    markdown TL {s(mtl(o['markdown_tl']), 2)} M TL (lansman → çıkış, oranı > 0 olan normal ve online hat "
          f"satırları, iadeden önce; online {s(mtl(o['markdown_tl_online']), 2)} M TL); outlet indirimi "
          f"{s(mtl(o['outlet_indirim_tl']), 2)} M TL (outlet hattı, çıkış → çıkış + 84)")
    print(f"    çıkıştan 7 gün önce kalan {s(o['cikis_kalan_adet'])} adet (mağazada {s(o['cikis_kalan_magaza_adet'])}, depoda "
          f"{s(o['cikis_kalan_depo_adet'])}); liste değeri {s(mtl(o['cikis_kalan_liste']), 2)} M TL, alış değeri "
          f"{s(mtl(o['cikis_kalan_alis']), 2)} M TL; çıkış + 120 günde depoda ölü stok {s(o['olu_stok_adet'])} adet, alış "
          f"değeri {s(mtl(o['olu_stok_alis']), 2)} M TL")
    print(f"  keşif tanımları (spec §0; yazıda kullanılmaz): indirim döneminde mağazalarda verilen indirim, iade düşülmüş "
          f"{s(mtl(h['md_ind_net']), 2)} M TL; outlet mağazalarında outlet indirimi, iade düşülmüş "
          f"{s(mtl(h['outlet_indirim_net']), 2)} M TL")


def _ob(a: dict, z: str) -> dict:
    ob = a["sezonlar"][z].get("olcutler")
    if ob is None:
        raise Eksik(f"analiz.json {z} olcutler bloğu (python analiz.py)")
    return ob


def veri_bolumu(v, ek) -> None:
    a = A(v)
    print(f"  kaynak: {'yayımlanan v4 DuckDB (analistin gördüğü veri)' if a['kaynak'] == 'yayimlanan' else a['kaynak']}; "
          "sezonun Collection option'ları; gizli gerçek yok. Markdown TL, outlet indirimi, kalan, ölü stok ve STR "
          "çeyrekleri olcutler tanımıyla yol 0 Lumoda koşusundan (yayımlanan v4'ün temiz hâli)")
    for z in SEZONLAR:
        d = a["sezonlar"].get(z)
        if d is None:
            raise Eksik(f"analiz.json {z}")
        h, ob = d["huni"], _ob(a, z)
        alt(f"{SEZON_ADLARI[z]}: sezon sonu hunisi ({s(h['option'])} option)")
        _huni_satirlari(h, ob)
        km = d["kademe"]
        print("  Lumoda'nın en derin oranı (option sayısı): " + " · ".join(
            f"{y(float(x), 0)} {s(n)}" for x, n in km["dagilim"].items())
              + f"; indirim gününden önce oranı olan {s(km['erken_indirilen'])} option, indirim − 28'den önce "
              f"{s(km['lumoda_oncesi_indirilen'])}")
        st = ob["str"]
        print(f"  indirim başı STR (100 × indirim başına kadar satış ÷ arz): p10 {yd(st['p10'])}, medyan {yd(st['p50'])}, "
              f"p90 {yd(st['p90'])}")
        _tablo(["çeyrek", "option", "STR aralığı", "çıkışta kalan", "kalanın payı", "markdown TL", "ölü stok"],
               [[str(c["ceyrek"]), s(c["option"]), f"{yd(c['str_alt'])}–{yd(c['str_ust'])}", s(c["kalan"]),
                 y(c["kalan_payi"]), f"{s(mtl(c['markdown_tl']), 2)} M TL", s(c["olu_stok"])] for c in ob["ceyrekler"]])
        print(f"  çıkışta kalanın indirim başı STR'sinin alt yarısındaki (1. ve 2. çeyrek) payı {y(ob['alt_yari_kalan_payi'])}")
        hf = d["haftalik"]
        print("  haftalık pozitif satış (indirimden 8 hafta önceden çıkışa): " + " · ".join(
            f"{hk(r['hafta'])}: {s(r['adet'])}" for r in hf))
        o = ob["olcutler"]
        ek += [(f"VERİ {z}: çeyrek option sayıları = option", sum(c["option"] for c in ob["ceyrekler"]) == h["option"]
                and o["option_sayisi"] == h["option"]),
               (f"VERİ {z}: kademe dağılımı = option", sum(km["dagilim"].values()) == h["option"]),
               (f"VERİ {z}: arz = ilk + RPT", abs(h["arz"] - h["arz_ilk"] - h["arz_rpt"]) < 1e-6),
               (f"VERİ {z}: yayımlanan arz = yol 0 Lumoda arzı", abs(h["arz"] - o["arz_adet"]) < 1e-6),
               (f"VERİ {z}: yayımlanan kalan ve ölü stok = yol 0 Lumoda'nınki (mağaza stoğunda kirli kayıt payı)",
                abs(h["kalan_magaza"] - o["cikis_kalan_magaza_adet"]) <= KIRLI_STOK_PAYI
                and abs(h["kalan_depo"] - o["cikis_kalan_depo_adet"]) < 1e-6
                and abs(h["olu_stok"] - o["olu_stok_adet"]) < 1e-6)]
    for z in a["analiz_sezonlari"]:
        lu = K(v, LUMODA)["olcutler"].get(z)
        if lu is None:
            continue
        ob = _ob(a, z)
        ek.append((f"VERİ {z} = YOL 0 Lumoda (olcutler: {', '.join(analiz.OLCUTLER_ALANLARI)})",
                   all(abs(ob["olcutler"][k] - lu[k]) < 1e-6 for k in analiz.OLCUTLER_ALANLARI)))
        lc = K(v, LUMODA)["ceyrek"][z]
        ek.append((f"VERİ {z} çeyrekleri = YOL 0 Lumoda çeyrekleri", len(lc) == len(ob["ceyrekler"]) and all(
            abs(c["katki"] - l["katki"]) < 1e-6 and abs(c["markdown_tl"] - l["markdown_tl"]) < 1e-6
            and abs(c["kalan"] - l["cikis_kalan_adet"]) < 1e-6 for c, l in zip(ob["ceyrekler"], lc))))
    alt(f"{s(len(a['analiz_sezonlari']))} sezonda aralık (" + ", ".join(a["analiz_sezonlari"]) + ")")
    otuz = [a["sezonlar"][z]["kademe"]["dagilim"].get("0.30", 0) for z in a["analiz_sezonlari"]]
    yetmis = [a["sezonlar"][z]["kademe"]["dagilim"].get("0.70", 0) for z in a["analiz_sezonlari"]]
    en_iyi = [yuv(mtl(_ob(a, z)["ceyrekler"][3]["markdown_tl"]), 2) for z in a["analiz_sezonlari"]]
    alt_yari = [yuv(100 * _ob(a, z)["alt_yari_kalan_payi"], 1) for z in a["analiz_sezonlari"]]
    print(f"  çıkışa kadar %30'da kalan option {s(min(otuz))}–{s(max(otuz))}; %70'e inen {s(min(yetmis))}–{s(max(yetmis))}")
    print(f"  en iyi çeyreğin markdown TL'si (olcutler) {s(min(en_iyi), 2)}–{s(max(en_iyi), 2)} M TL; kalanın alt yarıdaki "
          f"payı %{s(min(alt_yari), 1)}–%{s(max(alt_yari), 1)}")


# ---------------------------------------------------------------------------
# ESNEKLİK
# ---------------------------------------------------------------------------


def _ogrenme(v, yol: int, sezon: str) -> dict:
    g = ((v.oyun.get("yollar") or {}).get(str(yol)) or {}).get("ogrenme", {}).get(sezon)
    if g is None:
        raise Eksik(f"oyun.json yollar[{yol}] öğrenme {sezon}")
    return g


def esneklik_bolumu(v, ek) -> None:
    alt("öğrenilen ε̂ (yol 0, test sezonunun en erken karar gününden önceki satırlarla) ve gerçek ε (gizli; Lumoda "
        "koşusunun indirim dönemi satışıyla ağırlıklı hücre ε'si)")
    for z in SEZONLAR:
        g = _ogrenme(v, 0, z)
        print(f"  {SEZON_ADLARI[z]}: saf regresyon {s(g['eps_saf'], 3)} · markdown {s(g['eps_markdown']['*'], 3)} · "
              f"kampanya {s(g['eps_kampanya']['*'], 3)} · gerçek {s(g['gercek_eps']['*'], 3)} (havuz \"*\"); kalıntı "
              f"değeri {s(g['kalinti'], 3)} × liste; iade mağaza {y(g['iade']['magaza'])}, online {y(g['iade']['online'])}")
        ust = sorted(k for k in g["eps_kampanya"] if k != "*")
        _tablo(["üst kategori", "markdown", "kampanya", "gerçek"],
               [[u, s(g["eps_markdown"].get(u), 3), s(g["eps_kampanya"].get(u), 3), s(g["gercek_eps"].get(u), 3)] for u in ust])
    h = H(v)
    e = h["esneklik"]
    t = h["tulumlar"]["cok"]
    alt(f"tek-option hesabı: {e['option_id']} ({t['model_adi']}, {t['renk']}), karar günü ({hafta_metni(e['indirime_hafta'])}), "
        "yol 0")
    print(f"  satılabilir stok {s(e['satilabilir'])} adet; çıkışa kadar tam fiyatta tahmini talep {s(e['talep'])} adet "
          f"(talep ÷ stok {s(bolum(e['talep'], e['satilabilir']), 3)}); liste {s(e['liste'], 2)} TL; kalıntı {s(e['kalinti'], 3)}")
    _tablo(["ε kaynağı", "ε", "temizleme indirimi (1 − r = (talep ÷ stok)^(1/ε))", "merdivende", "DP ilk hafta",
            "DP en derin", "DP beklenen kalan", "DP beklenen ciro"],
           [[r["ad"], s(r["eps"], 3), y(r["temizleme_ham"]), y(r["temizleme_kademe"], 0), y(r["dp_oran"], 0),
             y(max(r["dp_yol"]) if r["dp_yol"] else None, 0), s(r["dp_kalan"]), f"{s(mtl(r['dp_ciro']), 2)} M TL"]
            for r in e["epsler"]])
    for r in e["epsler"]:
        print(f"  {r['ad']}: DP'nin haftalık yolu " + " ".join(y(x, 0) for x in r["dp_yol"]))
    print("  aynı gün kolların kararı (kayıt): " + " · ".join(f"{kol_adi(k)} {y(x, 0)}" for k, x in e["kol_kararlari"].items()
                                                         if x is not None))
    r = {x["ad"]: x for x in e["epsler"]}
    if r["saf"]["dp_oran"] == 0 and r["saf"]["eps"] < 1:
        print(f"  saf ε ({s(r['saf']['eps'], 3)}) 1'in altında: indirim beklenen ciroyu düşürür, DP indirmez")
    for kol, d in e["dogrulama"].items():
        print(f"  karar anı doğrulaması ({kol_adi(kol)} kaydı): satılabilir stok {s(d['satilabilir_esit'])}/"
              f"{s(d['satilabilir_option'])} option'da aynı; sahne option'ında oran, tahmini satış, beklenen kalan "
              f"{'aynı' if d['esit'] else 'FARKLI'}")
        ek.append((f"ESNEKLİK: karar anı {kol} kaydını üretir", d["esit"]))
    to, op = O(v, "opt_tuzak", TOPLAM), O(v, "opt", TOPLAM)
    dk = kfark(v, "opt", "opt_tuzak", TOPLAM)
    dm = fark(mtl(op["markdown_tl"]), mtl(to["markdown_tl"]), 2)
    di = fark(op["indirilen_option"], to["indirilen_option"])
    em, ec = _ogrenme(v, 0, "SS25")["eps_markdown"]["*"], _ogrenme(v, 0, "SS25")["eps_kampanya"]["*"]
    soru(4, f"Yanlış esneklik (markdown'dan) kararı ne kadar bozar, hangi yöne? İki sezonda opt_tuzak − opt katkı "
            f"{kfark_metni(dk)}; markdown TL {isaretli(dm, 2)} M TL ({isaretli(tek_ondalik(dm), 1)}), indirilen option "
            f"{isaretli(di)}: {yon(-dm, 'daha az indirim', 'daha çok indirim', 'aynı indirim')}"
            + (" (iki işaret ters: markdown TL ve indirilen option ayrı yönde)" if dm * di < 0 else "") + " "
            f"(SS25 ε̂ markdown {s(em, 3)} {'<' if yuv(em, 3) < yuv(ec, 3) else '>' if yuv(em, 3) > yuv(ec, 3) else '='} "
            f"kampanya {s(ec, 3)}); tek option'da markdown ε'si DP'ye ilk hafta "
            f"{y(r['markdown']['dp_oran'], 0)}, kampanya ε'si {y(r['kampanya']['dp_oran'], 0)} önerdirir")


# ---------------------------------------------------------------------------
# KALİBRASYON
# ---------------------------------------------------------------------------


def kalibrasyon_bolumu(v, ek) -> None:
    k = v.kalibrasyon
    if k is None:
        raise Eksik("kalibrasyon.json")
    kal = sabitler.KAL_SEZONLARI
    lu = {z: O(v, LUMODA, z) for z in kal}
    lu_top = sum(yuv(mtl(lu[z]["katki"]), 2) for z in kal)
    print(f"  ölçüt: iki kalibrasyon sezonunun ({', '.join(kal)}) sezon katkısı toplamı; yol 0, yol 0 Lumoda'sının RPT "
          f"takvimiyle; Lumoda'nın katkısı " + " · ".join(f"{z} {s(mtl(lu[z]['katki']), 2)}" for z in kal)
          + f" · toplam {s(lu_top, 2)} M TL")
    for kol, ad, et in (("kural", "alfa", "α"), ("tekduze", "oran", "oran")):
        alt(f"{kol_adi(kol)} ({et}); M TL")
        r = k[kol]
        satir = []
        for t in r["tablo"]:
            top = sum(yuv(mtl(t[z]), 2) for z in kal)
            satir.append([s(t["deger"], 2) if kol == "kural" else y(t["deger"], 0)] + [s(mtl(t[z]), 2) for z in kal]
                         + [s(top, 2), isaretli(yuv(top - lu_top, 2), 2), "evet" if t["gecerli"] else "hayır"])
            for z in kal:
                ek.append((f"KALİBRASYON: {t['kosular'][kal.index(z)]} = oyun.json", abs(
                    K(v, t["kosular"][kal.index(z)])["olcutler"]["katki"] - t[z]) < 1e-6))
        _tablo([et] + list(kal) + ["toplam", "− Lumoda", "geçerli"], satir)
        secilen = r[ad]
        print(f"  seçilen {et} {s(secilen, 2) if kol == 'kural' else y(secilen, 0)}"
              + ("; ızgaranın ucunda" if r["izgara_ucunda"] else ""))
        kul = [K(v, ad_(0, k, z))["parametreler"].get(ad) for z in SEZONLAR
               for k in ((kol, *oyun.ABLASYON_KOLLARI) if kol == "kural" else (kol,))]
        ek.append((f"KALİBRASYON: test kolu {kol} (kuralda ayrıştırma kolları da) seçilen {et} ile koştu", all(
            x is not None and abs(float(x) - float(secilen)) < 1e-9 for x in kul)))


# ---------------------------------------------------------------------------
# YOL 0
# ---------------------------------------------------------------------------


def _olcut_tablosu(v, sezon: str) -> None:
    kollar = list(YOL0)
    oo = {k: O(v, k, sezon) for k in kollar}
    _tablo(["ölçüt (M TL, %, adet)"] + [kol_adi(k) for k in kollar],
           [[et] + [deger(tur, oo[k].get(ad)) for k in kollar] for ad, et, tur in OLCUTLER])


def yol0_bolumu(v, ek) -> None:
    print("Yol 0 = yayımlanan dünya (aynı müşteri akışı). Kollar aynı malla yarışır (RPT Lumoda'nın takvimi, ilk dağıtım "
          "aynı; KORUNUM). Bir koşu tek test sezonudur; iki sezon iki koşunun toplamıdır.")
    tur = {ad: t for ad, _, t in OLCUTLER}
    for z in (*SEZONLAR, TOPLAM):
        alt(f"{SEZON_ADLARI[z]}: bütün ölçütler")
        _olcut_tablosu(v, z)
        alt(f"{SEZON_ADLARI[z]}: Lumoda'ya göre fark (kol − Lumoda)")
        lu = O(v, LUMODA, z)
        for kol in oyun.YOL0_KOLLARI:
            o = O(v, kol, z)
            print(f"  {kol_adi(kol)}: " + " · ".join(
                f"{et.strip()} {farki(tur[ad], lu[ad], o[ad])}" for ad, et, _ in OLCUTLER if ad in FARK_OLCUTLERI))
    ih = H(v).get("indirim_haftalari") or {}
    for z in SEZONLAR:
        alt(f"{SEZON_ADLARI[z]}: ilk indirim haftasının dağılımı (option sayısı; hafta indirim haftasına göre; hikaye.json)")
        haftalar = sorted({int(h) for k in YOL0 for h in (ih.get(k, {}).get(z) or {}).get("hafta", {})})
        satir = []
        for k in YOL0:
            d = (ih.get(k) or {}).get(z)
            if d is None:
                raise Eksik(f"hikaye.json indirim haftaları {k} {z}")
            satir.append([kol_adi(k)] + [s(d["hafta"].get(str(h), 0)) for h in haftalar] + [s(d["yok"])])
            ek.append((f"YOL 0 {z} {k}: ilk indirim haftası dağılımı = option sayısı",
                       sum(d["hafta"].values()) + d["yok"] == O(v, k, z)["option_sayisi"]
                       and d["option"] - d["yok"] == O(v, k, z)["indirilen_option"]))
        _tablo(["kol"] + [hk(h) for h in haftalar] + ["indirilmedi"], satir)
    alt("kollar arası katkı farkları (iki sezon; M TL)")
    for a_, c_ in (("tekduze", LUMODA), ("kural", LUMODA), ("opt", "kural"), ("opt", LUMODA), ("kahin", "opt"),
                   ("kahin", LUMODA), ("opt_tuzak", "opt"), ("opt", "opt_takvim")):
        print(f"  {kol_adi(a_)} − {kol_adi(c_)}: " + " · ".join(
            f"{SEZON_ADLARI[z]} {kfark_metni(kfark(v, c_, a_, z))}" for z in (*SEZONLAR, TOPLAM)))
    # Başlık soruları
    d1 = {z: kfark(v, "tekduze", LUMODA, z) for z in (*SEZONLAR, TOPLAM)}
    soru(1, f"Lumoda'nın kuralı düz indirimden (en iyi tekdüze oran, "
            f"{y(K(v, ad_(0, 'tekduze', 'SS25'))['parametreler']['oran'], 0)}) iyi mi? Lumoda − tekdüze katkı: "
            + " · ".join(f"{SEZON_ADLARI[z]} {kfark_metni(d1[z])}" for z in (*SEZONLAR, TOPLAM))
            + f": iki sezonda {yon(d1[TOPLAM], 'iyi', 'kötü')}")
    d3 = kfark(v, "kural", "opt", TOPLAM)
    ko = kfark(v, LUMODA, "opt", TOPLAM)
    kk = kfark(v, LUMODA, "kahin", TOPLAM)
    pay = ko / kk if kk > 0 else None
    soru(3, f"Optimizasyon kuralı ne kadar geçer, kahinle aradaki farkın ne kadarını kapatır? Opt − kural {kfark_metni(d3)}; "
            f"opt − Lumoda {kfark_metni(ko)}, kahin − Lumoda {kfark_metni(kk)}"
            + (f": opt'un Lumoda ile kahin arasındaki farkı kapattığı pay {y(pay)}" if pay is not None else "")
            + ("; kahin opt'un altında" if kk < ko else ""))
    op = O(v, "opt", TOPLAM)
    dm = fark(mtl(lu["markdown_tl"]), mtl(op["markdown_tl"]), 2)
    dc = fark(mtl(lu["ciro_toplam"]), mtl(op["ciro_toplam"]), 2)
    soru(6, f"Doğru politika markdown TL'sini artırırken ciroyu da artırıyor mu? Opt − Lumoda (iki sezon): markdown TL "
            f"{isaretli(dm, 2)} M TL ({isaretli(tek_ondalik(dm), 1)}), toplam ciro {isaretli(dc, 2)} M TL "
            f"({isaretli(tek_ondalik(dc), 1)}): markdown TL {yon(dm, 'artıyor', 'azalıyor')}, ciro {yon(dc, 'artıyor', 'azalıyor')}"
            + ("; ikisi birlikte artıyor" if dm > 0 and dc > 0 else ""))
    for z in (*SEZONLAR, TOPLAM):
        arz = O(v, LUMODA, z)["arz_adet"]
        ek.append((f"YOL 0 {z}: arz bütün kollarda Lumoda'nınki", all(
            O(v, k, z)["arz_adet"] == arz for k in oyun.YOL0_KOLLARI)))


# ---------------------------------------------------------------------------
# AYRIŞIM
# ---------------------------------------------------------------------------


def ayrisim_bolumu(v, ek) -> None:
    print("Ayrışım (spec §3.4): opt_takvim'den (takvim: indirim gününden önce yok, sonra herkes ≥ %30) iki serbestliğin "
          "değeri. Kime = opt_erken_yok − opt_takvim (iyi satanı indirimden muaf tutmak: taban yok); ne zaman = opt_taban − "
          "opt_takvim (8 hafta erken başlamak: taban var); ikisi = opt − opt_takvim; etkileşim = ikisi − kime − ne zaman; "
          "ne kadar = opt_takvim − tekdüze (aynı takvim, option'a göre derinlik). Sezon katkısı, M TL.")
    sonuc = {}
    for z in (*SEZONLAR, TOPLAM):
        kime = kfark(v, "opt_takvim", "opt_erken_yok", z)
        ne_zaman = kfark(v, "opt_takvim", "opt_taban", z)
        ikisi = kfark(v, "opt_takvim", "opt", z)
        etk = yuv(ikisi - kime - ne_zaman, 2)
        ne_kadar = kfark(v, "tekduze", "opt_takvim", z)
        yol_a = kfark(v, "opt_erken_yok", "opt", z)
        yol_b = kfark(v, "opt_taban", "opt", z)
        sonuc[z] = (kime, ne_zaman, ikisi, etk, ne_kadar)
        alt(SEZON_ADLARI[z])
        print(f"  kime {kfark_metni(kime)} · ne zaman {kfark_metni(ne_zaman)} · ikisi {kfark_metni(ikisi)} · etkileşim "
              f"{kfark_metni(etk)} · ne kadar {kfark_metni(ne_kadar)}")
        print(f"  yol A (önce kime): takvim → erken_yok {kfark_metni(kime)}, erken_yok → opt {kfark_metni(yol_a)}; yol B (önce "
              f"ne zaman): takvim → taban {kfark_metni(ne_zaman)}, taban → opt {kfark_metni(yol_b)}")
        for ad, et in (("markdown_tl", "markdown TL"), ("olu_stok_adet", "ölü stok")):
            tur = "t" if ad == "markdown_tl" else "a"
            t_ = O(v, "opt_takvim", z)
            print(f"  {et}: kime {farki(tur, t_[ad], O(v, 'opt_erken_yok', z)[ad])} · ne zaman "
                  f"{farki(tur, t_[ad], O(v, 'opt_taban', z)[ad])} · ikisi {farki(tur, t_[ad], O(v, 'opt', z)[ad])}")
        ek.append((f"AYRIŞIM {z}: yol A toplamı = ikisi", abs(yuv(kime + yol_a, 2) - ikisi) <= 0.011))
        ek.append((f"AYRIŞIM {z}: yol B toplamı = ikisi", abs(yuv(ne_zaman + yol_b, 2) - ikisi) <= 0.011))
    kural_ayrisimi(v, ek)
    kime, ne_zaman, ikisi, etk, ne_kadar = sonuc[TOPLAM]
    soru(5, f"Takvime bağlı kalmanın bedeli ne; kime / ne zaman / ne kadar ne diyor? İki sezonda opt − opt_takvim "
            f"{kfark_metni(ikisi)} (takvimin bedeli); kime {kfark_metni(kime)}, ne zaman {kfark_metni(ne_zaman)}, etkileşim "
            f"{kfark_metni(etk)}; ne kadar (opt_takvim − tekdüze) {kfark_metni(ne_kadar)}; serbestliklerden büyüğü "
            + ("kime" if kime > ne_zaman else "ne zaman" if ne_zaman > kime else "ikisi eşit"))


def kural_ayrisimi(v, ek) -> None:
    """Kapsama kuralının kazancının kaynağı (Ruling R24; yol 0, iki ayrıştırma kolu): Lumoda → kural_takvim (kuralın
    takvimdeki değeri: aynı pencere, kapsama ölçüsü) → kural (ne zaman: erken başlamak); kural_deposuz → kural (depo:
    depoyu ve açık siparişi görmek)."""
    alt("kapsama kuralı (Ruling R24): Lumoda → kural_takvim → kural ve kural_deposuz → kural; sezon katkısı, M TL")
    print("  kural_takvim = kural, karar penceresi indirim günü (erken başlamaz); kural_deposuz = kural, stok yalnız raf + "
          "yolda (depo ve açık sipariş yok: Lumoda'nın STR'yi mağazaya gidenle ölçmesinin yaklaşığı)")
    sonuc = {}
    for z in (*SEZONLAR, TOPLAM):
        takvim_degeri = kfark(v, LUMODA, "kural_takvim", z)
        ne_zaman = kfark(v, "kural_takvim", "kural", z)
        depo = kfark(v, "kural_deposuz", "kural", z)
        toplam_ = kfark(v, LUMODA, "kural", z)
        sonuc[z] = (takvim_degeri, ne_zaman, depo, toplam_)
        print(f"  {SEZON_ADLARI[z]}: kural − Lumoda {kfark_metni(toplam_)} = Lumoda → kural_takvim {kfark_metni(takvim_degeri)}"
              f" + kural_takvim → kural (ne zaman) {kfark_metni(ne_zaman)}; depo (kural − kural_deposuz) {kfark_metni(depo)}")
        ku, kt, kd = (O(v, k, z) for k in ("kural", "kural_takvim", "kural_deposuz"))
        print(f"    markdown TL: kural {s(mtl(ku['markdown_tl']), 2)}, kural_takvim {s(mtl(kt['markdown_tl']), 2)}, kural_deposuz "
              f"{s(mtl(kd['markdown_tl']), 2)} M TL · ölü stok {s(ku['olu_stok_adet'])} / {s(kt['olu_stok_adet'])} / "
              f"{s(kd['olu_stok_adet'])} · indirilen option {s(ku['indirilen_option'])} / {s(kt['indirilen_option'])} / "
              f"{s(kd['indirilen_option'])} · ilk indirim haftası medyanı {s(ku['ilk_indirim_hafta_medyan'], 1)} / "
              f"{s(kt['ilk_indirim_hafta_medyan'], 1)} / {s(kd['ilk_indirim_hafta_medyan'], 1)}")
        ek.append((f"AYRIŞIM {z}: Lumoda → kural_takvim → kural toplamı = kural − Lumoda",
                   abs(yuv(takvim_degeri + ne_zaman, 2) - toplam_) <= 0.011))
        arz = O(v, LUMODA, z)["arz_adet"]
        ek.append((f"AYRIŞIM {z}: kural ayrıştırma kollarında arz Lumoda'nınki",
                   O(v, "kural_takvim", z)["arz_adet"] == arz and O(v, "kural_deposuz", z)["arz_adet"] == arz))
    takvim_degeri, ne_zaman, depo, toplam_ = sonuc[TOPLAM]
    lu, ku = O(v, LUMODA, TOPLAM), O(v, "kural", TOPLAM)
    dd = fark(lu["cikis_kalan_depo_adet"], ku["cikis_kalan_depo_adet"])
    dmg = fark(lu["cikis_kalan_magaza_adet"], ku["cikis_kalan_magaza_adet"])
    buyuk = ("erken başlamak" if ne_zaman > depo else "depoyu görmek" if depo > ne_zaman else "ikisi eşit")
    soru(2, f"Kapsama kuralı Lumoda'yı ne kadar geçer, kazancı nereden? Kural − Lumoda katkı {kfark_metni(toplam_)} (iki sezon; "
            f"{yon(toplam_, 'geçer', 'geçemez')}); erken başlamanın değeri (kural − kural_takvim) {kfark_metni(ne_zaman)}, "
            f"depoyu görmenin değeri (kural − kural_deposuz) {kfark_metni(depo)}, takvimde kapsama ölçüsünün değeri "
            f"(kural_takvim − Lumoda) {kfark_metni(takvim_degeri)}; ikisinden büyüğü {buyuk}; ilk indirim haftası medyanı "
            f"kural {s(ku['ilk_indirim_hafta_medyan'], 1)}, Lumoda {s(lu['ilk_indirim_hafta_medyan'], 1)}; çıkışta depoda "
            f"kalan {isaretli(dd)} adet, mağazada {isaretli(dmg)} adet")


# ---------------------------------------------------------------------------
# ÇEYREK
# ---------------------------------------------------------------------------


def _ceyrekler(v, kol: str, sezon: str, yol: int = 0) -> list[dict]:
    if kol == LUMODA:
        return K(v, ad_(yol, LUMODA))["ceyrek"][sezon]
    return K(v, ad_(yol, kol, sezon))["ceyrek"]


def ceyrek_bolumu(v, ek) -> None:
    print("Çeyrekler Lumoda'nın (yol 0) indirim başı STR'sine göre (1 en düşük, 4 en yüksek); her kol aynı option "
          "kümelerinde ölçülür. Kazanç = kolun çeyrekteki sezon katkısı − Lumoda'nın (M TL).")
    kollar = list(oyun.YOL0_KOLLARI)
    toplam = {k: [0.0] * 4 for k in kollar}
    for z in SEZONLAR:
        lu = _ceyrekler(v, LUMODA, z)
        alt(f"{SEZON_ADLARI[z]}: STR aralıkları " + " · ".join(
            f"{c['ceyrek']}. {yd(c['str_alt'])}–{yd(c['str_ust'])} ({s(c['option_sayisi'])} option)" for c in lu))
        satir = []
        for k in kollar:
            kc = _ceyrekler(v, k, z)
            f = [fark(mtl(lu[i]["katki"]), mtl(kc[i]["katki"]), 2) for i in range(4)]
            toplam[k] = [yuv(t + x, 2) for t, x in zip(toplam[k], f)]
            satir.append([kol_adi(k)] + [isaretli(x, 2) for x in f] + [isaretli(kfark(v, LUMODA, k, z), 2)])
            ek.append((f"ÇEYREK {z} {k}: çeyrek katkıları toplamı = kolun katkısı",
                       abs(sum(c["katki"] for c in kc) - O(v, k, z)["katki"]) < 1.0))
        _tablo(["kol", "1. çeyrek", "2.", "3.", "4.", "kolun katkı farkı (YOL 0)"], satir)
        o = _ceyrekler(v, "opt", z)
        print("  opt − Lumoda markdown TL: " + " · ".join(
            f"{i + 1}. {farki('t', lu[i]['markdown_tl'], o[i]['markdown_tl'])}" for i in range(4)))
        print("  opt − Lumoda ölü stok: " + " · ".join(
            f"{i + 1}. {farki('a', lu[i]['olu_stok_adet'], o[i]['olu_stok_adet'])}" for i in range(4)))
        print("  opt'un indirmediği option: " + " · ".join(
            f"{i + 1}. {s(o[i]['option_sayisi'] - o[i]['indirilen_option'])}" for i in range(4)))
    alt("iki sezon (çeyrekte iki sezon farkının toplamı)")
    _tablo(["kol", "1. çeyrek", "2.", "3.", "4.", "kolun katkı farkı (YOL 0)"],
           [[kol_adi(k)] + [isaretli(x, 2) for x in toplam[k]] + [isaretli(kfark(v, LUMODA, k, TOPLAM), 2)] for k in kollar])
    t = toplam["opt"]
    en = max(range(4), key=lambda i: (t[i], -i))
    butun = kfark(v, LUMODA, "opt", TOPLAM)
    pay = t[en] / butun if butun > 0 else None
    op = O(v, "opt", TOPLAM)
    muaf = int(op["option_sayisi"] - op["indirilen_option"])
    kime = kfark(v, "opt_takvim", "opt_erken_yok", TOPLAM)
    soru(7, f"Kazanç hangi STR çeyreğinden geliyor; iyi satanı indirimden muaf tutmak ne kazandırıyor? Opt − Lumoda iki sezonda "
            "çeyrek çeyrek " + " · ".join(f"{i + 1}. {isaretli(x, 2)}" for i, x in enumerate(t))
            + f" M TL; en büyük kazanç {en + 1}. çeyrekte" + (f" (opt − Lumoda farkına oranı {y(pay)})" if pay is not None else "")
            + f"; opt {s(muaf)} option'ı hiç indirmiyor (indirim başı STR'leri {yd(op['muaf_str_ind'])}); muafiyetin değeri "
            f"(kime: opt_erken_yok − opt_takvim) {kfark_metni(kime)}")


# ---------------------------------------------------------------------------
# YOLLAR
# ---------------------------------------------------------------------------


def mevcut_yollar(v) -> list[int]:
    """Bütün koşuları geçerli olan yollar (0 her zaman ilk)."""
    out = []
    for p in (0, *oyun.YOLLAR):
        adlar = [ad_(p, LUMODA)] + [ad_(p, k, z) for k in oyun.YOL_KOLLARI for z in SEZONLAR]
        if all(a in v.gecerli for a in adlar):
            out.append(p)
    return out


def yollar_bolumu(v, ek) -> None:
    ps = mevcut_yollar(v)
    if 0 not in ps:
        raise Eksik("yol 0 koşuları")
    hepsi = (0, *oyun.YOLLAR)
    print(f"{s(len(hepsi))} talep yolu (İlk Sevkiyat kalıbı): yol 0 yayımlanan dünya, yol p > 0 aynı dünyada başka bir müşteri "
          "akışı; öğrenme o yolun Lumoda koşusundan, kahin aynı dünyanın gerçeğinden. Fark = kol − o yolun Lumoda'sı, sezon "
          "katkısı, M TL (basılan iki ondalıklı düzeylerden).")
    if len(ps) < len(hepsi):
        print(f"  [eksik yollar: {', '.join(str(p) for p in hepsi if p not in ps)}]")
    yl = v.oyun.get("yollar", {})
    for p in ps:
        g = yl.get(str(p), {})
        tohum = K(v, ad_(p, LUMODA)).get("talep_tohumu")
        og = g.get("ogrenme", {})
        print(f"  yol {p}: talep tohumu {tohum if tohum is not None else 'yayımlanan'} · ε̂ kampanya "
              + " · ".join(f"{z} {s(og.get(z, {}).get('eps_kampanya', {}).get('*'), 3)}" for z in SEZONLAR)
              + " · ε̂ markdown " + " · ".join(f"{z} {s(og.get(z, {}).get('eps_markdown', {}).get('*'), 3)}" for z in SEZONLAR))
    for z in (*SEZONLAR, TOPLAM):
        alt(f"{SEZON_ADLARI[z]} (yol {' · '.join(map(str, ps))}; min / medyan / max; k/n önde = fark > 0)")
        for k in oyun.YOL_KOLLARI:
            f = [kfark(v, LUMODA, k, z, p) for p in ps]
            print(f"  {kol_adi(k):<11}" + " · ".join(isaretli(x, 2) for x in f)
                  + f"  | min {isaretli(min(f), 2)} · medyan {isaretli(yuv(statistics.median(f), 2), 2)} · max "
                    f"{isaretli(max(f), 2)} · {sum(x > 0 for x in f)}/{len(f)} önde")
    alt("kol çiftleri (iki sezon; a − b; k/n a önde)")
    for a_, c_ in (("opt", "kural"), ("opt", "opt_tuzak"), ("opt", "opt_takvim"), ("kahin", "opt"), ("kural", "tekduze")):
        f = [kfark(v, c_, a_, TOPLAM, p) for p in ps]
        print(f"  {kol_adi(a_)} − {kol_adi(c_)}: " + " · ".join(isaretli(x, 2) for x in f)
              + f"  | medyan {isaretli(yuv(statistics.median(f), 2), 2)} · {sum(x > 0 for x in f)}/{len(f)} önde")
    tohumlar = [K(v, ad_(p, LUMODA)).get("talep_tohumu") for p in ps]
    ek.append(("YOLLAR: talep tohumları farklı", len(set(map(str, tohumlar))) == len(ps)))


# ---------------------------------------------------------------------------
# TAHMİN İSABETİ
# ---------------------------------------------------------------------------


def isabet_bolumu(v, ek) -> None:
    print("Kolun pazartesi kaydındaki tahmini satış (o pazartesiden çıkışa) ile kolun kendi koşusunda gerçekleşen pozitif "
          "satış (normal ve online hat). WAPE = 100 × Σ|t − g| ÷ Σ g; yanlılık = 100 × (Σ t − Σ g) ÷ Σ g; ilk = her option'ın "
          "ilk kayıt satırı. Tekdüze tahmin yazmaz.")
    satir = []
    for k in oyun.YOL0_KOLLARI:
        for z in SEZONLAR:
            i = K(v, ad_(0, k, z))["isabet"]
            satir.append([kol_adi(k), z, yd(i["wape"]), yd(i["yanlilik"]), yd(i["wape_ilk"]), s(i["satir"])])
    _tablo(["kol", "sezon", "WAPE", "yanlılık", "WAPE (ilk)", "satır"], satir)


# ---------------------------------------------------------------------------
# YAN ETKİ
# ---------------------------------------------------------------------------


def yan_etki_bolumu(v, ek) -> None:
    print("Test dışı option'lar (aynı koşu penceresi: öteki sezonlar, Outlet line, Basic, NOS) ve ikame: kol − Lumoda. "
          "Sezon satışlarının çıkıştan sonraki iadesi outlet penceresine düşer (Ruling R18; toplam ciro etkilenmez).")
    for z in (*SEZONLAR, TOPLAM):
        alt(SEZON_ADLARI[z])
        satir = []
        for k in oyun.YOL0_KOLLARI:
            if z == TOPLAM:
                O(v, k, TOPLAM)
                ye = v.oyun["toplamlar"]["0"][k]["yan_etki"]
            else:
                ye = K(v, ad_(0, k, z))["yan_etki"]
            satir.append([kol_adi(k), isaretli(yuv(mtl(ye["ciro_farki_test_disi"]), 2), 2)]
                         + [isaretli(yuv(mtl(ye.get(f"ciro_farki_{x}", 0.0)), 2), 2) for x in ("collection", "outlet", "basic", "nos")]
                         + [isaretli(ye["ikame_alinan_farki"]), isaretli(ye["ikame_giden_farki"]),
                            isaretli(ye["elle_transfer_farki"]), isaretli(ye["elle_transfer_farki_test"])])
        _tablo(["kol", "test dışı ciro (M TL)", "Collection", "Outlet", "Basic", "NOS", "ikame alınan (adet)",
                "ikameye giden", "elle transfer", "elle transfer (test)"], satir)
    lu = K(v, ad_(0, "opt", "SS25"))["yan_etki"]["ciro_test_disi_lumoda"]
    print(f"  ölçek: Lumoda'nın test dışı cirosu (SS25 koşu penceresi) {s(mtl(lu), 2)} M TL")


# ---------------------------------------------------------------------------
# HİKÂYE
# ---------------------------------------------------------------------------


def _seri_tablosu(t: dict) -> None:
    _tablo(["hafta", "lansman haftası", "satış", "oran", "outlet oranı", "mağaza", "outlet mağazası", "depo"],
           [[hk(r['hafta']), str(r["hafta_lansman"]), s(r["satis"]), y(r["oran"], 0) if r["oran"] is not None else "—",
             y(r["outlet_oran"], 0) if r["outlet_oran"] is not None else "—", s(r["magaza_stok"]), s(r["outlet_stok"]),
             s(r["depo"])] for r in t["haftalik"]])


def _dagilim(et: str, d: dict) -> None:
    print(f"  {et}: mağazada {s(d['magaza'])} adet ({s(d['magaza_sayisi'])} mağaza), depoda {s(d['depo'])}, toplam "
          f"{s(d['magaza'] + d['depo'])}; İstanbul {s(d['istanbul'])} (Ali), Anadolu {s(d['anadolu'])} (Veli)")
    print("    en büyük stoklu mağazalar: " + " · ".join(
        f"{m['ad']} ({m['sehir']}) {s(m['adet'])}" for m in d["en_buyuk"]))


def _tulum_bolumu(h: dict, rol: str) -> None:
    t = h["tulumlar"][rol]
    karar = next((r for r in t["haftalik"] if r["hafta_bas"] == t["karar_gunu"]), None)
    alt(f"{t['option_id']} {t['model_adi']} ({t['renk']}), {s(t['dalga'])}. dalga, liste {s(t['liste'], 2)} TL, alış "
        f"{s(t['alis'], 2)} TL")
    rpt = ", ".join(f"{s(r['adet'])} adet (teslim {gun_metni(r['teslim_indirime_gun'])})" for r in t["rpt"]) or "yok"
    print(f"  arz {s(t['arz'])} adet (ilk {s(t['arz_ilk'])}, RPT {s(t['arz_rpt'])}: {rpt}); indirim başına kadar satış "
          f"{s(t['satis_once'])} adet, indirim başı STR {yd(t['str_ind'])}")
    if karar is not None:
        once = [r["satis"] for r in t["haftalik"] if karar["hafta"] - 4 <= r["hafta"] < karar["hafta"]]
        print(f"  karar günü (lansmanın {s(karar['hafta_lansman'])}. haftası, {hafta_metni(karar['hafta'])}): elde "
              f"{s(karar['magaza_stok'] + karar['depo'])} adet (mağaza {s(karar['magaza_stok'])}, depo {s(karar['depo'])}); "
              f"karar gününden önceki hafta satış {s(once[-1]) if once else '—'}, önceki {s(len(once))} haftanın ortalaması "
              f"{s(sum(once) / len(once)) if once else '—'}; karar haftasında satış {s(karar['satis'])}")
    _dagilim("karar günü stoğu", t["karar"])
    _dagilim("indirim günü stoğu", t["indirim_gunu"])
    print(f"  çıkıştan 7 gün önce kalan {s(t['cikis_kalan']['magaza'] + t['cikis_kalan']['depo'])} adet (mağaza "
          f"{s(t['cikis_kalan']['magaza'])}, depo {s(t['cikis_kalan']['depo'])}); çıkış + 120'de ölü stok {s(t['olu_stok'])} adet "
          f"({y(t['olu_stok'] / t['arz'] if t['arz'] else None)} arzın)")
    lu = t["lumoda"]
    dort = [r for r in t["haftalik"] if -4 <= r["hafta"] <= 0]
    print(f"  Lumoda: ilk oranlı hafta {hafta_metni(lu['ilk_indirim_hafta'])}, en derin {y(lu['en_derin'], 0)}; indirimden 4 "
          "hafta önceden indirim haftasına oran " + " · ".join(f"{hk(r['hafta'])}: {y(r['oran'] or 0, 0)}" for r in dort))
    print("  haftalık seri (hafta indirim haftasına göre; mağaza, outlet mağazası ve depo pazartesi fotoğrafı):")
    _seri_tablosu(t)


def _yol_metni(yol: list[dict]) -> str:
    """Oranın değiştiği haftalar: "−8: %30 · −4: %40" (hiç indirilmediyse "indirim yok")."""
    out, son = [], 0.0
    for r in yol:
        if r["oran"] != son:
            out.append(f"{hk(r['hafta'])}: {y(r['oran'], 0)}")
            son = r["oran"]
    return " · ".join(out) or "indirim yok"


def hikaye_bolumu(v, ek) -> None:
    h = H(v)
    sh = h["sahne"]
    print(f"  sahne (spec §0/3): {h['sezon']}, iki lacivert tulum (cok {sh['cok']}, az {sh['az']}) ve Oduncu Gömlek "
          f"({sh['gomlek']}); yayımlanan veriden (yol 0 Lumoda)" + (" — KÜÇÜK yedek sahne" if h["sahne_yedek"] else ""))
    for rol in ("cok", "az"):
        _tulum_bolumu(h, rol)
    g = h["gomlek"]
    alt(f"{g['option_id']} {g['model_adi']} ({g['renk']}): Lumoda'nın kör noktası")
    rpt = g["rpt"][-1] if g["rpt"] else None
    print(f"  arz {s(g['arz'])} adet (ilk {s(g['arz_ilk'])}, RPT {s(g['arz_rpt'])}); indirim gününe kadar fiziksel mağaza "
          f"satışı {s(g['satis_once_fiziksel'])}, mağazalara giden {s(g['magazaya_giden'])}: Lumoda'nın STR'si "
          f"{s(g['str_lumoda'], 2)}; bütün satış {s(g['satis_once'])} ÷ arz: {s(g['str_arz'], 2)}")
    if rpt:
        print(f"  RPT {s(rpt['adet'])} adet: sipariş {gun_metni(rpt['siparis_indirime_gun'])}, depoya teslim "
              f"{gun_metni(rpt['teslim_indirime_gun'])}")
    print(f"  Lumoda: en derin {y(g['lumoda']['en_derin'], 0)}, ilk oranlı hafta {hafta_metni(g['lumoda']['ilk_indirim_hafta'])}; "
          f"çıkış + 120'de ölü stok {s(g['olu_stok'])} adet ({s(g['arz'])} adetten)")
    alt("her kolda üç option (yol 0, SS25): fiyat yolu ve sonuç")
    for rol in ("cok", "az", "gomlek"):
        oid = sh[rol]
        satir = []
        for kol in YOL0:
            if kol not in h["kollar"]:
                satir.append([kol_adi(kol), "eksik"] + ["—"] * 7)
                continue
            r = h["kollar"][kol]["optionlar"][rol]
            so = r["sonuc"]
            satir.append([kol_adi(kol), _yol_metni(r["fiyat_yolu"]), s(so["satis_cikis"]), s(so["cikis_kalan_adet"]),
                          s(so["olu_stok_adet"]), s(mtl(so["ciro_toplam"]), 2), s(mtl(so["markdown_tl"]), 2),
                          s(mtl(so["katki"]), 2), y(r["en_derin"], 0)])
        print(f"  {oid}:")
        _tablo(["kol", "oran yolu (hafta: oran)", "çıkışa kadar satış", "çıkışta kalan", "ölü stok", "toplam ciro (M TL)",
                "markdown TL", "katkı", "en derin"], satir)
    d = h["ders"]
    t = h["tulumlar"]["cok"]
    print(f"  ders (cok): opt ilk kez {hafta_metni(d['cok_opt_ilk_indirim_hafta'])} indiriyor; Lumoda'nın kuralı en erken "
          f"{hafta_metni(d['lumoda_baslangic_hafta'])} başlar: "
          + ("ders karar anında görülüyor (opt Lumoda'dan önce indiriyor)" if d["cok_lumoda_oncesi"]
             else "DERS KARAR ANINDA GÖRÜLMÜYOR: opt bu tulumu Lumoda'nın kuralından önce indirmiyor"))
    print(f"  ders (az): opt bu tulumu " + (f"{hafta_metni(d['az_opt_ilk_indirim_hafta'])} indiriyor" if d["az_opt_indirdi"]
                                             else "çıkışa kadar hiç indirmiyor"))
    pl = h["pazartesi_listesi"]
    for anahtar_, et in (("karar_gunu", "karar günü"), ("indirim_gunu", "indirim günü")):
        p = pl[anahtar_]
        alt(f"pazartesi listesi (opt kaydı, {et}): {s(p['option'])} option karar veriyor, oranı > 0 olan {s(p['indirimli'])} "
            "(" + " · ".join(f"{y(float(x), 0)} {s(n)}" for x, n in p["oranlar"].items()) + ")")
        _tablo(["option", "oran", "tahmini satış (çıkışa)", "satılabilir stok", "beklenen kalan"],
               [[r["option_id"], y(r["oran"], 0), s(r["tahmini_satis"]), s(r["satilabilir"]), s(r["beklenen_kalan"])]
                for r in p["satirlar"]])
    lu_c, op_c = h["kollar"][LUMODA]["optionlar"]["cok"]["sonuc"], h["kollar"]["opt"]["optionlar"]["cok"]["sonuc"]
    op_a = h["kollar"]["opt"]["optionlar"]["az"]
    soru(8, f"İki lacivert tulum her kolda ne yaşadı? {sh['cok']}: Lumoda'da ölü stok {s(lu_c['olu_stok_adet'])}, opt'ta "
            f"{s(op_c['olu_stok_adet'])} adet ({isaretli(fark(lu_c['olu_stok_adet'], op_c['olu_stok_adet']))}); opt ilk kez "
            f"{hafta_metni(d['cok_opt_ilk_indirim_hafta'])} indiriyor ("
            + ("Lumoda'dan önce: ders karar anında görülüyor" if d["cok_lumoda_oncesi"] else "ders karar anında görülmüyor")
            + f"); {sh['az']}: opt " + (f"{hafta_metni(op_a['ilk_indirim_hafta'])} indiriyor" if d["az_opt_indirdi"]
                                         else "hiç indirmiyor") + f", çıkışta kalan {s(op_a['sonuc']['cikis_kalan_adet'])} adet")
    ek += [("HİKÂYE: yol 0 Lumoda'sı oyun.json'unki", h["lumoda_anahtar"] == K(v, LUMODA)["anahtar"]),
           ("HİKÂYE: bütün yol 0 kolları okundu", not h["eksik_kollar"]),
           ("HİKÂYE: karar günü kaynak.karar_penceresi'yle aynı", h["karar_gunu_tutarli"]),
           ("HİKÂYE: ölçüm kodu bugünkü", h["olcum_kodu"] == v.olcum_kodu)]
    for kol, r in h["kollar"].items():
        ad = ad_(0, kol, h["sezon"])
        ek.append((f"HİKÂYE: {kol} koşusu oyun.json'unki", r["anahtar"] == K(v, ad)["anahtar"]))
    for rol in ("cok", "az"):
        tt, lk = h["tulumlar"][rol], h["kollar"][LUMODA]["optionlar"][rol]["sonuc"]
        ek.append((f"HİKÂYE {rol}: yayımlanan arz, kalan ve ölü stok = yol 0 Lumoda option tablosu (mağaza stoğunda kirli "
                   "kayıt payı)", tt["arz"] == lk["arz_adet"] and tt["olu_stok"] == lk["olu_stok_adet"]
                   and tt["cikis_kalan"]["depo"] == lk["cikis_kalan_depo_adet"]
                   and abs(tt["cikis_kalan"]["magaza"] - lk["cikis_kalan_magaza_adet"]) <= KIRLI_STOK_PAYI))


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------


def demo_bolumu(v, ek) -> None:
    son = senaryolar.sonuclar(v.oyun)
    print(f"  {len(son)} bileşim: kol {{{', '.join(senaryolar.KOLLAR)}}} × sezon {{{', '.join(senaryolar.SEZONLAR)}}}; kartlar "
          "Lumoda'ya göre katkı farkı (M TL), ölü stok (bin adet), markdown TL (M TL), tam fiyat STR, son STR (hepsi bir "
          "ondalık: iki ondalıklının bir kez yuvarlanmışı)")
    et = {p["ad"]: p["deger_etiketleri"] for p in senaryolar.PARAMETRELER}
    _tablo(["bileşim", "katkı farkı (M TL)", "ölü stok (bin)", "markdown (M TL)", "tam fiyat STR", "son STR", "koşu"],
           [[f"{et['kol'][a.split('|')[0]]} · {et['sezon'][a.split('|')[1]]}", isaretli(r["ozet"]["katki_farki_mtl"], 1),
             s(r["ozet"]["olu_stok_bin"], 1), s(r["ozet"]["markdown_mtl"], 1), yd(r["ozet"]["tam_fiyat_str"], 1),
             yd(r["ozet"]["son_str"], 1), ", ".join(x["kosu"] for x in r["satirlar"])] for a, r in son.items()])
    ek.append(("DEMO: 18 bileşim", len(son) == len(senaryolar.KOLLAR) * len(senaryolar.SEZONLAR)))
    for a, r in son.items():
        kol, sz = a.split("|")
        z = senaryolar.SEZONLAR[sz] or TOPLAM
        lu, o = O(v, LUMODA, z), O(v, kol, z)
        ek.append((f"DEMO {a}: katkı farkı = rapor", r["ozet"]["katki_farki_mtl"] == fark1(mtl(lu["katki"]), mtl(o["katki"]))))
    dosya = v.demo_dosya
    if dosya is None or dosya != senaryolar.uret(v.oyun):
        if not v.taslak:
            raise AssertionError("DEMO: site dosyası senaryolar.uret() ile aynı değil")
        print("  [eksik: demo dosyası güncel değil]")
    else:
        print(f"  site dosyası {senaryolar.HEDEF.name}: sürüm {dosya['surum']} (içeriğin özeti)")
    if v.demo_bayt is not None or not v.taslak:
        ek.append(("DEMO: sitedeki dosya bütçe içinde", v.demo_bayt is not None and v.demo_bayt < senaryolar.BUTCE))


def anlati_bolumu(v, ek) -> None:
    print("Veriden gelmeyen, anlatı için konmuş tanımlar (varsayım; yazıda kesin sayı gibi sunulmaz):")
    for anahtar_, d in ANLATI_VARSAYIMLARI.items():
        print(f"  {anahtar_}: {d}")


# ---------------------------------------------------------------------------
# KORUNUM
# ---------------------------------------------------------------------------


def korunum_bolumu(v, ek) -> None:
    sayi = 0
    for k in izgara():
        if k.kol == LUMODA or k.ad not in v.gecerli:
            continue
        e = K(v, k.ad)
        kr = e.get("korunum") or {}
        ek.append((f"{k.ad}: sözleşmeler ({', '.join(KORUNUM_ALANLARI)})", e.get("gecerli") is True
                   and all(kr.get(a) is True for a in KORUNUM_ALANLARI)))
        sayi += 1
    ek.append(("ızgaranın bütün koşuları geçerli ve ölçülmüş", v.taslak or len(v.gecerli) == len(izgara())))
    for p in mevcut_yollar(v):
        for kol in (LUMODA, *(oyun.YOL0_KOLLARI if p == 0 else oyun.YOL_KOLLARI)):
            t = ((v.oyun.get("toplamlar") or {}).get(str(p)) or {}).get(kol)
            ek.append((f"toplam yol {p} {kol}: var ve geçerli", t is not None and t.get("gecerli") is True))
    a = A(v)
    if v.olcek == "tam":
        ek.append(("yol 0 Lumoda = yayımlanan: öğrenme yayımlanan DuckDB'den",
                   v.oyun.get("yollar", {}).get("0", {}).get("kaynak") == "yayimlanan"))
        ek.append(("VERİ yayımlanan DuckDB'den", a.get("kaynak") == "yayimlanan"))
    else:
        ek.append(("analiz.json bu oyun.json'un yol 0 Lumoda'sından", a.get("lumoda_anahtar") == K(v, LUMODA)["anahtar"]))
    n = korunum(ek)
    print(f"  {s(n)} denetim tuttu: {s(sayi)} koşunun sözleşmeleri (RPT ve ilk dağıtım Lumoda'nınkiyle birebir, arz birebir, "
          "merdiven, sığlaşmaz, pencere, takvim tabanı), arz bütün kollarda aynı, yol toplamları, yol 0 Lumoda = yayımlanan,")
    print("  karar anı doğrulaması (opt ve opt_tuzak kaydı), kalibrasyonun seçtiği değerle koşan test kolları, hikâye ve demo "
          "kayıtları, veri sayımları.")
    print(f"  oyun.json kayıtları bugünkü ölçüm koduyla ({v.olcum_kodu[:12]}); analiz.json {a['kod'][:12]}; hikaye.json "
          f"{(v.hikaye or {}).get('kod', '—')[:12]}; kalibrasyon.json {(v.kalibrasyon or {}).get('olcum_kodu', '—')[:12]}.")


BOLUMLER = [
    ("VERİ", veri_bolumu), ("ESNEKLİK", esneklik_bolumu), ("KALİBRASYON", kalibrasyon_bolumu), ("YOL 0", yol0_bolumu),
    ("AYRIŞIM", ayrisim_bolumu), ("ÇEYREK", ceyrek_bolumu), ("YOLLAR", yollar_bolumu), ("TAHMİN İSABETİ", isabet_bolumu),
    ("YAN ETKİ", yan_etki_bolumu), ("HİKÂYE", hikaye_bolumu), ("DEMO", demo_bolumu),
    ("ANLATI VARSAYIMLARI", anlati_bolumu), ("KORUNUM", korunum_bolumu),
]


def govde(v) -> None:
    """Bütün bölümler sırasıyla; korunum en sonda (tutmazsa AssertionError). Taslakta `Eksik` veren bölüm atlanır."""
    print("İndirim Takvimi — v4 raporu. Kaynak: cikti/oyun.json (python -m markdown.oyun), cikti/kalibrasyon.json, "
          f"cikti/analiz.json, cikti/hikaye.json, site/src/data/senaryolar/{senaryolar.HEDEF.name}.")
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
