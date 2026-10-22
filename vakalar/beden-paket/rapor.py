"""Beden ve Paket dizisinin (6 yazı, `/assortment/beden-paket/`) yayımlanacak BÜTÜN sayıları buradan basılır (v4).

    cd vakalar/beden-paket
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m beden_paket.oyun izgara       # cikti/oyun.json (koşular, ölçüm)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python analiz.py                        # cikti/analiz.json (koşusuz)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m beden_paket.hikaye_kos        # cikti/hikaye.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py                    # demo JSON
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py --taslak               # eksik girdiyle biçim denetimi
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py --kucuk                # cikti/kucuk/ (geliştirme)

Kalıcı kural: yazıya yeni bir sayı girmeden önce buraya eklenir; ortak sayı denetimi (`cd
vakalar/beden-paket && .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi
../../site/src/content/yazi/assortment/beden-paket --rapor cikti/rapor.txt`) yazılardaki her sayının bu
çıktıda geçtiğini denetler. Sayılar Türkçe basılır (binlik nokta, ondalık virgül, `%12,3`, `−0,32`).
Uydurma sayı yasaktır; elle konmuş anlatı değerleri yalnız ANLATI VARSAYIMLARI'ndadır. Raporda takvim
tarihi geçer (izlenebilirlik); yazılar tarih ve yıl basmaz.

Bölümler (`BOLUMLER`, bu sırayla; spec §5). Başlık sorularının her biri ilgili bölümde tek bir
`SORU n · …` satırıdır (cevap basılan değerlerden; yön ve "aynı" sözcükleri hesaplanan değerden):

    VERİ                  kapsam, oyun option'ları, ns
    PAKET                 Lumoda paketi, zincir eğrisi, alım / depo / ilk dağıtım / replenishment beden payları,
                          paketi bölmenin yolları (SORU 1)
    EĞRİ                  ham / düzeltilmiş / daraltılmış, profil, zincir; hakemli ve hakemsiz; sansür; κ;
                          okunamayan mağaza; hat ayrımı (SORU 2)
    TASARIM               kol başına desenler, atama, profil × desen, uyumsuzluk; iki depo tanımı (R16)
    KOLLAR                yol 0: başlık (ilk haftalar) ve sezon ölçütleri; Lumoda'ya farklar
    YOLLAR                5 talep yolu: değerler, min / medyan / max, k/5 önde, bir ondalık
    K EĞRİSİ              koşusuz uyumsuzluk ve koşulan K'ların ölçütleri; mağazaya özel, kahin (SORU 4, 5)
    ABLASYON              12'li paket, sansür düzeltmesiz eğri (SORU 6)
    KÜMELEME ÇAPRAZI      beden profili × satış karışımı kümesi (SORU 3)
    HİKÂYE                sahne, gevşeyen, hakem, alternatif
    DEMO                  bileşimler, eksik bileşimler, site dosyası
    ANLATI VARSAYIMLARI
    KORUNUM               doğrulama = İlk Sevkiyat Lumoda; aynı mal; kırpma 0; İlk Sevkiyat anahtarları; girdiler

Rapor önce tampona yazılır; korunum tutmazsa ya da bir girdi eksik ya da eskiyse (ızgaranın bir koşusu
yok ya da bugünkü ölçüm koduyla ölçülmemiş, koşunun önbellek dizini yok; `analiz.json`, `hikaye.json`
bugünkü kodla yazılmamış; demo dosyası `senaryolar.uret()` ile aynı değil) stdout'a tek satır gitmez,
mesaj stderr'e, çıkış kodu 1 (`Eksik`). `--taslak` eksik girdiye dayanan bölümleri "[eksik: …]" diye
geçer ve sonda listeler (çıkış kodu 2; bu çıktı yazılara kaynak olamaz); `--kucuk` KÜÇÜK ölçeğin
çıktılarını okur (her zaman taslak). Basılan her fark ve oran basılan işlenenlerden hesaplanır (`yuv`,
`fark`, `bolum`); tek ondalıklı her fark iki ondalıklı farkın bir kez yuvarlanmışıdır (`fark1`): aynı
büyüklüğe tek değer. Ölçülen süre basılmaz. Bu dosya veriyi okumaz, simülasyon koşmaz.

Okuma notları: hakemli ölçütler (gerçek paya L1, ARI, kahin) hiçbir seçime girmez, sonradan ölçer.
Başlık ölçütleri ilk haftalardır (spec §0/12: Lumoda'nın replenishment'ı mağazanın bedenini bilir, açık
ilk haftalardadır; Ruling R19): ilk 4 hafta bulunabilirlik, beden kaybı payı ve kırık set (`*_ilk4`); sezon
boyu karşılıkları yanında basılır; ilk tükenen beden ilk dağıtımın varışından sonraki ilk bitendir. `brut_kar_tl` net satış − alış maliyetidir.
"""

import argparse
import contextlib
import io
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import analiz
import senaryolar
from beden_paket import hikaye_kos, oyun, sabitler

KOK = Path(__file__).resolve().parent

ANLATI_VARSAYIMLARI = {
    "kadro": "İstanbul mağazaları Ali'nin, Anadolu (İstanbul dışı) mağazaları Veli'nin (allocator); Pelin planner; "
             "Pars veriyi açan analist (dizinin kadrosu)",
    "depo": "tasarımın beden başına depo kısıtı karar anında bilinen ilk sipariş adedinden kurulur; kalite "
            "kontrolde hatalı çıkan adet (teslimde, çoğu karar gününden sonra) yalnız ön denetimde ve korunumda "
            "düşülür (Ruling R16, inceleme açık); iki tanımla tasarımların aynı olup olmadığı TASARIM'da",
    "ilk_haftalar": "başlık ölçütlerinin \"ilk haftaları\" İlk Sevkiyat'ın ilk 4 haftasıdır (ilk dağıtımın "
                    "varışından 28 gün)",
    "hikaye_penceresi": "hikâyede \"ilk haftalarda biter\": varıştan sonraki ilk tam haftalarda rafsız gün (sıkı 2 "
                        "hafta); \"rafta kalır\": 8 haftalık pencerede hiç rafsız gün yok ve sonunda mal var",
    "once_sarti": "hikâyede \"hedef bedenler öteki bedenlerden önce biter\" şartı ilk tasarımda yoktu; gerçek veride "
                  "zayıf bir sahne görüldükten sonra eklendi (sonuç görüldükten sonra konmuş bir seçim şartı; şartsız "
                  "seçilecek sahne HİKÂYE'de)",
    "bagimsizlik": "iki bölme \"bağımsız\" sayılır: ARI'nin mutlak değeri 0,05'ten küçük (anlatı eşiği; ARI basılır)",
    "kil_payi": "\"kıl payı\": iki ortalama L1'in farkı küçüğün %1'inden az (anlatı eşiği; iki değer basılır)",
}
BAGIMSIZ_ARI = 0.05
KIL_PAYI = 0.01

# ölçüt → (tür, ondalık): y yüzde (değer zaten yüzde), s sayı, t TL
BICIM = {"bulunabilirlik_ilk4": ("y", 2), "beden_kayip_payi_ilk4": ("y", 2), "kirik_cift_pay_yuzde_ilk4": ("y", 2),
         "beden_kayip_payi": ("y", 2), "kirik_cift_pay_yuzde": ("y", 2),
         "bulunabilirlik": ("y", 2), "sezon_sonu_kalan_yuzde": ("y", 2), "tam_fiyat_str": ("y", 2),
         "kayip_orani": ("y", 2), "brut_kar_tl": ("t", 0), "markdown_tl": ("t", 0), "ilk_dagitim_adet": ("s", 0),
         "replenishment_adet": ("s", 0), "tukenen_hucre_yuzde": ("y", 1), "kirpilan_adet": ("s", 0),
         **{f"{a}_{b}": ("y", 1) for a in ("ilk_tukenen_beden", "depoda_kalan_beden") for b in range(1, 6)}}
BASLIK = (("bulunabilirlik_ilk4", "ilk 4 hf bulun."), ("beden_kayip_payi_ilk4", "ilk 4 hf beden kaybı"),
          ("kirik_cift_pay_yuzde_ilk4", "ilk 4 hf kırık set"))
SEZON = (("bulunabilirlik", "sezon bulun."), ("beden_kayip_payi", "sezon beden kaybı"),
         ("kirik_cift_pay_yuzde", "sezon kırık set"), ("sezon_sonu_kalan_yuzde", "sezon sonu kalan"),
         ("tam_fiyat_str", "tam fiyat STR"), ("brut_kar_tl", "brüt kâr TL"))
OLCUTLER = BASLIK + SEZON
YUKSEK_IYI = {"bulunabilirlik_ilk4": True, "beden_kayip_payi": False, "kirik_cift_pay_yuzde": False,
              "beden_kayip_payi_ilk4": False, "kirik_cift_pay_yuzde_ilk4": False,
              "bulunabilirlik": True, "sezon_sonu_kalan_yuzde": False, "tam_fiyat_str": True, "brut_kar_tl": True,
              "kayip_orani": False}
KOL_ADLARI = {"dogrulama": "L0 Lumoda 1-2-2-1-1", "p1": "P1 tek 7'li", "p2": "P2 iki 7'li", "p1_12": "P1 tek 12'li",
              "p3_12": "P3 üç 12'li", "p2_12": "P2 iki 12'li", "p1_14": "P1 14'lü 2-2-4-4-2", "pm_12": "PM mağazaya özel 12'li", "p2_ham": "P2 ham eğri (ablasyon)"}
YOL_KIYASLARI = (("p1", "dogrulama"), ("p2", "dogrulama"), ("p3_12", "dogrulama"), ("p2", "p1"), ("p3_12", "p2"))


class Eksik(Exception):
    """Raporun dayandığı bir girdi yok ya da eski (stderr, çıkış 1; taslakta bölüm atlanır)."""

    def __init__(self, *neler: str):
        super().__init__("; ".join(neler))
        self.neler = list(neler)


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
        metin = f"{x:,}"
    else:
        metin = f"{yuv(x, ondalik):,.{ondalik}f}"
    metin = metin.replace(",", "_").replace(".", ",").replace("_", ".")
    if _sifir_mi(metin):
        metin = metin.lstrip("-")
    return metin.replace("-", "−")


def y(x, ondalik: int = 1) -> str:
    """Yüzde, x oran: 0,123 → %12,3; negatif → −%3,2."""
    return "—" if _yok(x) else yd(100 * float(x), ondalik)


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
    return f"{n}/{d} ({y(n / d)})" if d else f"{n}/{d}"


def baslik(metin: str) -> None:
    print(f"\n=== {metin} ===")


def alt(metin: str) -> None:
    print(f"\n--- {metin} ---")


def soru(n: int, metin: str) -> None:
    print(f"SORU {n} · {metin}")


def b(ad: str, x) -> str:
    """Ölçütün kendi biçimiyle (`BICIM`)."""
    tur, n = BICIM.get(ad, ("s", 2))
    return yd(x, n) if tur == "y" else (s(x, n) + " TL") if tur == "t" else s(x, n)


def fb(ad: str, a, c) -> str:
    """c − a, ölçütün biçiminde (yüzdede puan, iki ondalık ve bir kez yuvarlanmış bir ondalık)."""
    tur, n = BICIM.get(ad, ("s", 2))
    if tur == "y":
        return f"{isaretli(fark(a, c, n), n)} puan ({isaretli(fark1(a, c), 1)})" if n == 2 else \
            f"{isaretli(fark(a, c, n), n)} puan"
    return isaretli(fark(a, c, n), n) + (" TL" if tur == "t" else "")


def desenler_metni(d: list[str]) -> str:
    return " + ".join(d)


def pay_metni(p, ondalik: int = 1) -> str:
    return " / ".join(y(x, ondalik) for x in p)


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


def korunum(denetimler: list[tuple[str, bool]]) -> int:
    """Denetimlerin hepsi tutmalı; tutmayanlar adlarıyla AssertionError. Döner: denetim sayısı."""
    if not denetimler:
        raise AssertionError("korunum: hiç denetim yok")
    hatalar = [ad for ad, ok in denetimler if not bool(ok)]
    if hatalar:
        raise AssertionError("korunum bozuldu:\n  " + "\n  ".join(hatalar))
    return len(denetimler)


def _tablo(basliklar: list[str], satirlar: list[list[str]]) -> None:
    gen = [max(len(bas), *(len(r[i]) for r in satirlar)) if satirlar else len(bas) for i, bas in enumerate(basliklar)]
    print("  " + "  ".join(bas.ljust(g) for bas, g in zip(basliklar, gen)))
    for r in satirlar:
        print("  " + "  ".join(c.ljust(g) for c, g in zip(r, gen)))


def _capraz(c: dict, ad: str) -> None:
    _tablo([ad] + [str(x) for x in c["sutunlar"]] + ["toplam"],
           [[str(sat)] + [str(x) for x in r] + [str(sum(r))] for sat, r in zip(c["satirlar"], c["degerler"])])


def ari(a: list, c: list) -> float:
    """Düzeltilmiş Rand indeksi (iki etiket dizisi; sklearn'le aynı formül, bağımlılık yok)."""
    n = len(a)
    tablo: dict = {}
    for x, z in zip(a, c):
        tablo[(x, z)] = tablo.get((x, z), 0) + 1
    sa: dict = {}
    sc: dict = {}
    for (x, z), k in tablo.items():
        sa[x] = sa.get(x, 0) + k
        sc[z] = sc.get(z, 0) + k
    toplam = sum(math.comb(k, 2) for k in tablo.values())
    ta, tc = sum(math.comb(k, 2) for k in sa.values()), sum(math.comb(k, 2) for k in sc.values())
    beklenen = ta * tc / math.comb(n, 2) if n > 1 else 0.0
    en_cok = (ta + tc) / 2
    return 1.0 if en_cok == beklenen else (toplam - beklenen) / (en_cok - beklenen)


# ---------------------------------------------------------------------------
# Girdiler
# ---------------------------------------------------------------------------


@dataclass
class Veri:
    oyun: dict
    analiz: dict | None
    hikaye: dict | None
    kumeler: dict | None
    demo_dosya: dict | None
    olcek: str = "tam"
    taslak: bool = False
    demo_bayt: int | None = None
    gecerli: set = field(default_factory=set)
    eksik: list = field(default_factory=list)


def _json(yol: Path) -> dict | None:
    yol = Path(yol)
    return json.loads(yol.read_text(encoding="utf-8")) if yol.is_file() else None


def kosu_dizini(onbellek: Path, e: dict) -> Path:
    """Kaydın simülasyon dizini (`simulasyon.kos`: `<ad>_<anahtar[:20]>`); bağlı kayıtta tabanınki."""
    return Path(onbellek) / f"{e.get('ayni') or e['ad']}_{e['anahtar'][:20]}"


def gecerli_kosular(oyun_kaydi: dict, olcum_kodu: str, onbellek: Path) -> tuple[set, list]:
    """Izgaranın (`oyun.izgara_listesi("hepsi")`) ölçülmüş ve önbellekte duran kayıtları; ve eksikler."""
    kosular = oyun_kaydi.get("kosular", {})
    ok, eksik = set(), []
    for yol, kol in oyun.izgara_listesi("hepsi"):
        ad = oyun.kosu_adi(yol, kol)
        e = kosular.get(ad)
        if e is None or "olcutler" not in e:
            eksik.append(f"oyun.json: {ad} yok (python -m beden_paket.oyun izgara)")
        elif e.get("olcum_kodu") != olcum_kodu:
            eksik.append(f"oyun.json: {ad} bugünkü ölçüm koduyla ölçülmemiş (izgara yeniden: önbellekten ölçer)")
        else:
            m = kosu_dizini(onbellek, e) / "meta.json"
            if not m.is_file() or json.loads(m.read_text(encoding="utf-8")).get("anahtar") != e["anahtar"]:
                eksik.append(f"önbellek: {ad} koşusu {m.parent.name} yok ya da anahtarı farklı")
            else:
                ok.add(ad)
    return ok, eksik


def _kumeler():
    try:
        from kumeleme import oyun as kumeleme_oyun
        return kumeleme_oyun.kumeler_oku(olcum=False), None
    except (FileNotFoundError, ValueError) as e:
        return None, f"kumeler.json okunamadı: {e}"


def hazirla(*, kucuk: bool = False, taslak: bool = False, cikti: Path | None = None, demo_yol: Path | None = None,
            olcum_kodu: str | None = None, analiz_kodu: str | None = None, hikaye_kodu: str | None = None,
            onbellek: Path | None = None, kumeler=None) -> Veri:
    """Girdileri okur ve tazeliklerini denetler. Kesin kipte eksik ya da eski girdi `Eksik`; taslakta
    `Veri.eksik`'e yazılır. `oyun.json` her iki kipte de gerekir."""
    olcek = "kucuk" if kucuk else "tam"
    cikti = Path(cikti) if cikti is not None else (sabitler.CIKTI / "kucuk" if kucuk else sabitler.CIKTI)
    demo_yol = senaryolar.HEDEF if demo_yol is None else Path(demo_yol)
    onbellek = sabitler.CIKTI / "kosular" if onbellek is None else Path(onbellek)
    o = _json(cikti / "oyun.json")
    if o is None:
        raise Eksik(f"{cikti / 'oyun.json'} yok: önce python -m beden_paket.oyun izgara")
    sorun = []
    if o.get("olcek") != olcek:
        sorun.append(f"oyun.json {o.get('olcek')} ölçeğinde (beklenen {olcek})")
    gec, ek = gecerli_kosular(o, oyun.olcum_kodu() if olcum_kodu is None else olcum_kodu, onbellek)
    sorun += ek
    a = _json(cikti / "analiz.json")
    if a is None:
        sorun.append("analiz.json yok (python analiz.py)")
    else:
        if a.get("kod") != (analiz.kod_ozeti() if analiz_kodu is None else analiz_kodu):
            sorun.append("analiz.json bugünkü kodla yazılmamış (python analiz.py)")
        if a.get("olcek") != olcek:
            sorun.append(f"analiz.json {a.get('olcek')} ölçeğinde")
    h = None if kucuk else _json(cikti / "hikaye.json")
    if kucuk:
        sorun.append("hikaye.json yalnız TAM (yayımlanan veri)")
    elif h is None:
        sorun.append("hikaye.json yok (python -m beden_paket.hikaye_kos)")
    elif h.get("kod") != (hikaye_kos.kod_ozeti() if hikaye_kodu is None else hikaye_kodu):
        sorun.append("hikaye.json bugünkü kodla yazılmamış (python -m beden_paket.hikaye_kos)")
    if kumeler is None:
        kumeler, hata = _kumeler()
        if hata:
            sorun.append(hata)
    demo = _json(demo_yol)
    if demo is None:
        sorun.append(f"{demo_yol.name} yok (python senaryolar.py)")
    if kucuk:
        sorun.append("KÜÇÜK ölçek: geliştirme çıktısı")
    if sorun and not (taslak or kucuk):
        raise Eksik(*sorun)
    return Veri(oyun=o, analiz=a, hikaye=h, kumeler=kumeler, demo_dosya=demo, olcek=olcek, taslak=taslak or kucuk,
                demo_bayt=demo_yol.stat().st_size if demo is not None else None, gecerli=gec, eksik=sorun)


# ---------------------------------------------------------------------------
# Kısayollar
# ---------------------------------------------------------------------------


def K(v, ad: str) -> dict:
    """Ölçülmüş ve önbellekte geçerli koşunun kaydı; değilse `Eksik`."""
    if ad not in v.gecerli:
        raise Eksik(f"koşu {ad}")
    return v.oyun["kosular"][ad]


def O(v, ad: str) -> dict:
    return K(v, ad)["olcutler"]


def A(v) -> dict:
    if v.analiz is None:
        raise Eksik("analiz.json")
    return v.analiz


def kol_adi(kol: str) -> str:
    return KOL_ADLARI.get(kol, kol)


def yollar(v) -> list[int]:
    return [0, *oyun.YOLLAR]


def ad_(yol: int, kol: str) -> str:
    return oyun.kosu_adi(yol, kol)


def en_sik_ilk_tukenen(o: dict) -> int:
    return max(range(1, 6), key=lambda i: (yuv(o[f"ilk_tukenen_beden_{i}"], 1), -i))


def k_satiri(v, adet: int, K_) -> dict | None:
    return next((r for r in A(v)["k_egrisi"] if r["adet"] == adet and r["K"] == K_), None)


def k_kosusu(v, adet: int, K_) -> tuple[str | None, object]:
    """(Koşu adı, koşunun K'sı): (adet, K) tasarımıyla aynı desen ve atamayı veren en küçük K'nın
    (`senaryolar.esdeger_K`) koşusu; koşulmadıysa (None, None)."""
    k = senaryolar.esdeger_K(A(v)["k_egrisi"], K_, adet)
    kol = senaryolar.KOLLAR.get((k, adet))
    return (kol, k) if kol is not None else (None, None)


def _kiyas_tablosu(v, kollar: list[str], olcutler=OLCUTLER) -> None:
    _tablo(["kol"] + [bas for _, bas in olcutler],
           [[kol_adi(k)] + [b(m, O(v, k)[m]) for m, _ in olcutler] for k in kollar])


def _fark_satiri(v, a: str, c: str, olcutler=OLCUTLER) -> str:
    oa, oc = O(v, a), O(v, c)
    return " · ".join(f"{bas} {fb(m, oa[m], oc[m])}" for m, bas in olcutler)


# ---------------------------------------------------------------------------
# Bölümler
# ---------------------------------------------------------------------------


def veri_bolumu(v, ek) -> None:
    d = A(v)["veri"]
    kap = d["kapsam"]
    ist = sum(r["istanbul"] for r in kap)
    yeni = [r for r in kap if r["yeni"]]
    print(f"  karar günü {d['karar_gunu']} (SS25'in ilk Collection karar günü; İlk Sevkiyat ve Mağaza Kümeleme ile aynı)")
    print(f"  kapsam: {s(len(kap))} fiziksel, outlet olmayan mağaza (Mağaza Kümeleme'nin kapsamı): İstanbul {s(ist)} "
          f"(Ali'nin), Anadolu {s(len(kap) - ist)} (Veli'nin)")
    for r in yeni:
        print(f"  yeni mağaza (Kümeleme eşiği): {r['magaza_id']} {r['ad']} ({r['sehir']}, {r['tip']}), "
              f"{r['gecmis_hafta']} satışlı hafta")
    print(f"  oyun: SS25 Collection ilk dağıtımı, {s(d['oyun_option'])} option = beş bedenli {s(d['bes_bedenli_option'])} "
          f"+ tek bedenli (aksesuar, standart pakette kalır) {s(d['oyun_option'] - d['bes_bedenli_option'])}")
    print("  beden setleri (oyun option'ı): " + " · ".join(f"{a} {s(n)}" for a, n in d["beden_setleri"].items()))
    ns = d["ns"]
    print(f"  ns (Lumoda'nın motor sonrası giden paketi, mağaza × option; spec §0/11): {s(ns['hucre'])} hücre, "
          f"{s(ns['paket'])} paket, {s(ns['magaza'])} mağaza")
    ek += [("VERİ: oyun option = beş bedenli + aksesuar", sum(d["beden_setleri"].values()) == d["oyun_option"]),
           ("VERİ: paket alan mağaza kapsamda", ns["magaza"] <= len(kap)),
           ("VERİ: kimlikler tekil", len({r["magaza_id"] for r in kap}) == len(kap))]


def paket_bolumu(v, ek) -> None:
    p = A(v)["paket"]
    L = p["lumoda"]
    a = p["adet"]
    pt = p["paket_tablosu"]
    tek = pt["set_basina_paket_tipi"] == [1] and pt["desenler"] == ["-".join(map(str, L))]
    print(f"  yayımlanan paket tablosu: {s(pt['bes_bedenli_set'])} beş bedenli set, set başına paket tipi "
          f"{'/'.join(s(x) for x in pt['set_basina_paket_tipi'])}, içerik {', '.join(pt['desenler'])}; tek bedenli "
          f"{s(pt['tek_bedenli_set'])} set ({'/'.join(s(x) for x in pt['tek_bedenli_adet'])} adet)")
    print(f"  Lumoda'nın paketi{' her beş bedenli sette tek' if tek else ''}: {'-'.join(map(str, L))} ({s(a)} adet; "
          f"beden payı {pay_metni([x / a for x in L])})")
    print(f"  zincir satış eğrisi (karar öncesi, fiziksel mağazalar): {pay_metni(p['zincir'])}")
    yol_hepsi, yol_cekirdek = math.comb(a + 4, 4), math.comb(a - 3 + 4, 4)
    print(f"  {s(a)} adetlik paketi beş bedene bölmenin yolu {s(yol_hepsi)}; temel bedenler (2–4) en az birer adetle "
          f"{s(yol_cekirdek)} (tasarımın aday sayısı {s(p['aday_7'])}); 12'li pakette {s(math.comb(16, 4))} ve "
          f"{s(math.comb(13, 4))} (aday {s(p['aday_12'])})")
    alt("beş bedenli oyun option'larının beden adetleri ve payları (beden 1 → 5)")
    satir = []
    for et, k in (("ilk sipariş (alım)", "ilk_siparis"), ("depo (hatalı düşülmüş)", "depo"),
                  ("Lumoda ilk dağıtım", "ilk_dagitim"), ("Lumoda replenishment", "replenishment")):
        x = p[k]
        satir.append([et, " / ".join(s(int(n)) for n in x), pay_metni([n / sum(x) for n in x])])
    _tablo(["", "adet", "pay"], satir)
    ilk = p["ilk_dagitim"]
    oranli = all(ilk[i] * L[0] == L[i] * ilk[0] for i in range(5))
    if oranli:
        print("  ilk dağıtım birebir paket oranında (her beden paketin içeriği × paket sayısı)")
    kalan1 = fark(ilk[0], p["depo"][0], 0)
    print(f"  1. beden: depo {s(p['depo'][0])}, ilk dağıtım {s(ilk[0])} (depoda kalan {s(kalan1)})"
          + ("; 1. beden ilk dağıtımda tükeniyor (paket 1. bedeni depo kadar istiyor)" if kalan1 == 0 else ""))
    k1 = k_satiri(v, a, 1)
    lu = k_satiri(v, a, "lumoda")
    mz = p["magaza_l1"]
    farkli = k1 is not None and k1["desenler"] != ["-".join(map(str, L))]
    print(f"  Lumoda paketinin L1 uzaklığı (beden payı, 0–2): zincire {s(p['zincir_l1'], 3)}; mağaza eğrilerine "
          f"(hakemsiz, {s(mz['magaza'])} okunabilen mağaza) ortalama {s(mz['ortalama'], 3)}, en az {s(mz['en_az'], 3)}, en "
          f"çok {s(mz['en_cok'], 3)} ({mz['en_cok_magaza']}); gerçek talep payına (hakemli, {s(p['gercek_l1']['magaza'])} mağaza) "
          f"ortalama {s(p['gercek_l1']['ortalama'], 3)}")
    if lu and k1:
        print(f"  beklenen eksik adet (paket başına, mağaza eğrisine göre, Lumoda'nın giden paketiyle ağırlıklı): Lumoda "
              f"{s(lu['paket_basina'], 3)} · en iyi tek {s(a)}'li paket {desenler_metni(k1['desenler'])} "
              f"{s(k1['paket_basina'], 3)}" + ("; en iyi tek paket Lumoda'nınki değil" if farkli else ""))
    soru(1, f"Lumoda'nın paketi zincirin ve mağazaların beden eğrisinden ne kadar uzak? Paketin beden payı "
            f"{pay_metni([x / a for x in L])}, zincir {pay_metni(p['zincir'])}: L1 zincire {s(p['zincir_l1'], 3)}, mağaza "
            f"eğrilerine ortalama {s(mz['ortalama'], 3)} (en çok {s(mz['en_cok'], 3)}); paket başına beklenen eksik adet "
            + (f"{s(lu['paket_basina'], 3)} (en iyi tek paket {s(k1['paket_basina'], 3)})" if lu and k1 else "—"))
    ek += [("PAKET: aday sayısı = temel bedenli bölme yolu", p["aday_7"] == yol_cekirdek
            and p["aday_12"] == math.comb(13, 4)),
           ("PAKET: ilk dağıtım ≤ depo (beden beden)", all(x <= d for x, d in zip(ilk, p["depo"]))),
           ("PAKET: depo ≤ ilk sipariş", all(d <= s_ for d, s_ in zip(p["depo"], p["ilk_siparis"]))),
           ("PAKET: Lumoda ilk dağıtımı paket oranında", oranli)]


def egri_bolumu(v, ek) -> None:
    e = A(v)["egri"]
    l1 = e["l1"]
    print(f"  {s(e['magaza'])} mağaza; eğrisi okunabilen (penceredeki beş bedenli satış ≥ {s(e['en_az_adet'])} adet, R7) "
          f"{s(e['okunabilir'])}, okunamayan {', '.join(e['okunamaz']) or 'yok'}")
    print(f"  örneklem (adet): okunabilenlerde medyan {s(e['n_medyan'])}, en az {s(e['n_en_az'])}; daraltma ağırlığı w = "
          f"n / (n + κ): medyan {s(e['agirlik_medyan'], 3)}, en az {s(e['agirlik_en_az'], 3)}")
    alt(f"gerçek talep payına ortalama L1 (hakemli; {s(e['l1_magaza'])} okunabilen mağaza; 0–2)")
    _tablo(["eğri", "L1"], [[a, s(l1[k], 4)] for a, k in (("ham satış payı", "ham"), ("sansür düzeltmeli", "duzeltilmis"),
                                                         ("daraltılmış (son eğri)", "daraltilmis"),
                                                         ("profil eğrisi", "profil"), ("zincir", "zincir"))])
    sans = fark(l1["ham"], l1["duzeltilmis"], 4)
    dar = fark(l1["duzeltilmis"], l1["daraltilmis"], 4)
    print(f"  sansür düzeltmesi L1'i {isaretli(sans, 4)} değiştiriyor; daraltma {isaretli(dar, 4)}"
          + (f" (bu veride daraltma sonucu değiştirmiyor, Ruling R6; w medyanı {s(e['agirlik_medyan'], 3)})"
             if abs(dar) < 0.001 else ""))
    print(f"  sansürün büyüklüğü (|düzeltilmiş − ham| beden payı, okunabilen mağaza × beden): ortalama "
          f"{s(100 * e['sansur_ortalama'], 2)} puan, en çok {s(100 * e['sansur_en_buyuk'], 2)} puan; ham ↔ düzeltilmiş eğri L1 "
          f"ortalama {s(e['ham_duz_l1']['ortalama'], 4)}, en çok {s(e['ham_duz_l1']['en_cok'], 4)}")
    t = e["sansur_tanisi"]
    print(f"  düzeltmenin bedeli (tanı): stoksuz ama satışlı hücre {s(t['stoksuz_satisli_hucre'])} ({s(t['stoksuz_satisli_adet'])} "
          f"adet, {s(t['adet'])} adette), 1–2 stoklu günlü hücre {s(t['az_gunlu_hucre'])}, seyrek hücre {s(t['seyrek_hucre'])} "
          f"(düzeltilmiş talepteki payı {y(t['seyrek_talep_payi'], 2)})")
    izgara = e["kappa_izgara"]
    tab = e.get("kappa_tablosu") or []
    ucta = e["kappa"] == max(izgara)
    print(f"  κ (hakemsiz; SS24 karar anında kurulan eğrinin SS24 Collection ilk 8 haftasının gerçekleşen payına L1'i): "
          f"seçilen {s(e['kappa'])}" + (" (ızgaranın üst ucu; ızgara sonuç görüldükten sonra genişletilmedi, Ruling R8)"
                                       if ucta else ""))
    if tab:
        print("    " + " · ".join(f"κ {s(r['kappa'])} {s(r['l1'], 6)}" for r in tab))
        lo, hi = min(r["l1"] for r in tab), max(r["l1"] for r in tab)
        print(f"    tablo aralığı {s(lo, 6)} … {s(hi, 6)} (fark {s(fark(lo, hi, 6), 6)})")
    alt("hat ayrımı (Ruling R5): eğri havuzdan (Collection + Basic/NOS) okunur; tanı satırları")
    hat = e["hat"]
    _tablo(["hat", "ham → gerçek", "düzeltilmiş → gerçek (hakemli)", "düzeltilmiş → SS24 gerçekleşen (hakemsiz)", "sansür ort.",
            "sansür en çok"],
           [[h, s(r["hakemli_ham"], 4), s(r["hakemli_duzeltilmis"], 4), s(r["hakemsiz_duzeltilmis"], 4),
             s(100 * r["sansur_ortalama"], 2) + " puan", s(100 * r["sansur_en_buyuk"], 2) + " puan"] for h, r in hat.items()])
    hakemsiz_en = min(hat, key=lambda h: (yuv(hat[h]["hakemsiz_duzeltilmis"], 4), h))
    hakemli_en = min(hat, key=lambda h: (yuv(hat[h]["hakemli_duzeltilmis"], 4), h))
    print(f"  hakemsiz ölçüt {hakemsiz_en} hattını seçer, hakemli ölçüt {hakemli_en} hattını"
          + ("; seçim hakemsizdir (Kümeleme R9 ilkesi)" if hakemsiz_en != hakemli_en else ""))
    kr = e["kararlilik"]
    print(f"  kararlılık (hakemsiz): kalibrasyon karar günü {kr['kal_karar_gunu']} ↔ oyun karar günü düzeltilmiş eğri, "
          f"{s(kr['magaza'])} ortak okunabilen mağazada ortalama L1 {s(kr['l1'], 4)}")
    alt("profiller (k-means, k = 3; ortalama beden sırasına göre adlı)")
    print("  profil (bütün mağazalar): " + " · ".join(f"{p} {s(n)}" for p, n in e["profil"].items())
          + "; okunabilenlerde: " + " · ".join(f"{p} {s(n)}" for p, n in e["profil_okunur"].items()))
    for p, r in e["profil_egrisi"].items():
        print(f"    {p}: {pay_metni(r)}")
    print(f"  profilin gizli kaymaya ARI'si (hakem: etkin, [−1, +1]'e kırpılmış kayma, Ruling R4; {s(e['ari_magaza'])} okunabilen "
          f"mağaza): {s(e['ari'], 3)}; ham çekilişte +2 olan mağaza {s(e.get('kayma_ham_2', 0))} (talepte +1 ile aynı)")
    _capraz(e["profil_kayma"], "profil \\ kayma")
    alt("okunamayan ve az örnekli mağazalar")
    ys = e["yeni_secim"]
    lp, lz = ys.get("l1_profil"), ys.get("l1_zincir")
    if lp is not None and lz is not None:
        kil = abs(lp - lz) < KIL_PAYI * min(lp, lz)
        print(f"  yedek eğri kuralı (bırakbir, hakemsiz, {s(ys['magaza'])} mağaza): statik profil L1 {s(lp, 5)}, zincir {s(lz, 5)} "
              f"→ {ys['secim']}" + (" (kıl payı, Ruling R9)" if kil else "") + f"; statik atama isabeti {y(ys['isabet'])}")
    for m, r in e["yeni"].items():
        obur_ad, obur = ("zincir", r["l1_zincir"]) if r["kaynak"] == "profil" else ("statik profil", r["l1_statik_profil"])
        iyi = "—" if obur is None else ("kötü" if r["l1_son"] > obur else "iyi" if r["l1_son"] < obur else "eşit")
        print(f"  {m}: n {s(r['n'])}, kaynak {r['kaynak']} (statik profil {r['statik_profil']}); gizli kayma "
              f"{isaretli(r['kayma'])}; gerçeğe L1 {s(r['l1_son'], 4)}, seçilmeyen {obur_ad} seçilseydi {s(obur, 4)} "
              f"(hakeme göre seçim {iyi})")
    for m, r in e["az_ornekli"].items():
        print(f"  {m}: n {s(r['n'])}, w {s(r['w'], 3)}, gerçeğe L1 {s(r['l1'], 4)}")
    soru(2, f"Satıştan okunan beden eğrisi gerçeğe ne kadar yakın; sansür düzeltmesi ve daraltma ne kazandırıyor? L1 ham "
            f"{s(l1['ham'], 4)} → düzeltilmiş {s(l1['duzeltilmis'], 4)} → daraltılmış {s(l1['daraltilmis'], 4)} (zincir "
            f"{s(l1['zincir'], 4)}, profil eğrisi {s(l1['profil'], 4)}); sansür ortalama {s(100 * e['sansur_ortalama'], 2)} puan, "
            f"en çok {s(100 * e['sansur_en_buyuk'], 2)} puan; κ {s(e['kappa'])}"
            + (" ızgara ucunda" if ucta else ""))
    ek += [("EĞRİ: okunabilen + okunamayan = kapsam", e["okunabilir"] + len(e["okunamaz"]) == e["magaza"]),
           ("EĞRİ: profil sayımı = kapsam", sum(e["profil"].values()) == e["magaza"]),
           ("EĞRİ: profil × kayma toplamı = okunabilen", sum(map(sum, e["profil_kayma"]["degerler"])) == e["okunabilir"]),
           ("EĞRİ: seçilen κ ızgarada", e["kappa"] in izgara),
           ("EĞRİ: κ tablosunun en küçüğü seçilen", not tab or min(tab, key=lambda r: (round(r["l1"], 12), r["kappa"]))["kappa"]
            == e["kappa"]),
           ("EĞRİ: havuz hat satırı = ana L1", abs(hat["havuz"]["hakemli_duzeltilmis"] - l1["duzeltilmis"]) < 1e-12)]


def tasarim_bolumu(v, ek) -> None:
    t = A(v)["tasarim"]
    alt("kol başına tasarım (yol 0; uyumsuzluk = beklenen eksik adet, mağaza eğrisine göre, ağırlık giden paket)")
    satir = []
    for kol in analiz.TASARIM_KOLLARI:
        r = t[kol]
        satir.append([kol_adi(kol), f"{r['paket_adet']}'li K {r['K']}",
                      " · ".join(f"{d} ({s(r['desen_magaza'][d])})" for d in r["desenler"]),
                      s(r["toplam_uyumsuzluk"], 1), s(r["paket_basina"], 4),
                      "aranmaz" if r["K"] == "sabit" else "kanıtlı" if r["en_iyi_mi"] else "kanıtsız",
                      r["yontem"], "uygun" if r["depo_uygun"] else "aşıyor", r["ayni"] or ""])
    _tablo(["kol", "", "desenler (mağaza)", "uyumsuzluk", "paket başına", "en iyi", "yöntem", "depo", "aynı kol"], satir)
    for kol in ("p2", "p3_12"):
        alt(f"{kol_adi(kol)}: profil × desen (mağaza sayısı)")
        _capraz(t[kol]["profil_desen"], "profil \\ desen")
        print("  desenin giden paket payı: " + " · ".join(f"{d} {y(x)}" for d, x in t[kol]["desen_agirlik"].items()))
    alt("mağazaya giden beden payının uzaklığı (koşusuz; giden paketle ağırlıklı ortalama L1)")
    _tablo(["kol", "gerçek paya (hakemli)", "tahmin edilen eğriye (hakemsiz)"],
           [[kol_adi("dogrulama" if k == "lumoda" else k), s(t[k]["giden_gercek_l1"], 4), s(t[k]["giden_egri_l1"], 4)]
            for k in ("lumoda", *analiz.TASARIM_KOLLARI)])
    d = A(v)["depo"]
    alt("depo kısıtı: iki tanım (Ruling R16; ANLATI VARSAYIMLARI)")
    print(f"  ilk sipariş adedi (karar anında bilinen) {' / '.join(s(x) for x in d['ilk_siparis'])}; hatalı düşülmüş "
          f"{' / '.join(s(x) for x in d['hatali_dusulmus'])}")
    for a, r in d["pay"].items():
        print(f"  {a}'li depo payı (depo ÷ kolun giden adedi): sipariş {' / '.join(s(x, 4) for x in r['siparis'])} · hatalı "
              f"düşülmüş {' / '.join(s(x, 4) for x in r['hatali_dusulmus'])}")
    sinir = d["pay"]["7"]["hatali_dusulmus"][0]
    if abs(sinir * 7 - 1) < 1e-3:
        b1 = min(int(d_.split("-")[0]) for k in analiz.TASARIM_KOLLARI if t[k]["paket_adet"] == 7 for d_ in t[k]["desenler"])
        print(f"  7'li pakette 1. beden hatalı düşülmüş depoda tam sınırda (pay {s(sinir, 4)} ≈ 1/7); 7'li tasarımların "
              f"desenlerinde 1. beden en az {s(b1)}" + (": yük depoya eşit" if b1 == 1 else ""))
    ayni = d["tasarim_ayni"]
    hepsi = all(r["iki_tanim"] for r in ayni.values())
    print("  tasarım iki tanımda aynı: " + " · ".join(f"{k} {'evet' if r['iki_tanim'] else 'hayır'}" for k, r in ayni.items())
          + ("; depo tanımı bu veride tasarımı değiştirmiyor" if hepsi else ""))
    print("  ön denetim (option başına, hatalı düşülmüş depo; koşudan önce): " + " · ".join(
        f"{k} {s(K(v, k)['on_denetim']['option'])}/{s(K(v, k)['on_denetim']['kontrol_option'])} option aşıyor"
        for k in analiz.TASARIM_KOLLARI))
    for kol in analiz.TASARIM_KOLLARI:
        e = K(v, kol)
        ek.append((f"TASARIM: oyun.json {kol} kaydı = bugünkü tasarım (desen, atama)",
                   e["desenler"] == t[kol]["desenler"] and e.get("atama") == t[kol]["atama"]))
        ek.append((f"TASARIM: {kol} ön denetimde aşan option yok", e["on_denetim"]["option"] == 0))
    ek += [("TASARIM: desen mağaza sayıları = kapsam", all(sum(t[k]["desen_magaza"].values()) == A(v)["egri"]["magaza"]
                                                          for k in analiz.TASARIM_KOLLARI)),
           ("TASARIM: tasarımlar depoya uygun", all(t[k]["depo_uygun"] for k in analiz.TASARIM_KOLLARI))]


def kollar_bolumu(v, ek) -> None:
    kollar = list(oyun.YOL0_KOLLARI)
    print("Kollar Lumoda'nın giden paket sayısını gönderir (spec §0/5, §0/11; 12'lide adet dönüşümü); yalnız paketin beden "
          "içeriği değişir. Aynı mal kol başına KORUNUM'da denetlenir. Başlık ölçütleri ilk haftalar (spec §0/12).")
    alt("yol 0: başlık ölçütleri (ilk 4 hafta: bulunabilirlik, beden kaybı payı, kırık set; Ruling R19) ve sezon boyu "
        "ölçütleri")
    _kiyas_tablosu(v, kollar)
    ref = K(v, "dogrulama").get("ilk_sevkiyat")
    if ref is not None:
        uretir = ref["birebir"] == ref["olcut"] and not ref["farkli"]
        print(f"  doğrulama kolu İlk Sevkiyat'ın Lumoda koşusunu {'üretir' if uretir else 'üretmiyor'}: ölçütler birebir "
              f"{s(ref['birebir'])}/{s(ref['olcut'])}"
              + (f" (farklı: {', '.join(ref['farkli'])})" if ref["farkli"] else ""))
    for kol in kollar:
        e = K(v, kol)
        if e.get("ayni"):
            print(f"  {kol_adi(kol)}: {kol_adi(e['ayni'])} ile aynı desen ve atama, aynı koşu ({e['ayni']})")
    alt("Lumoda'ya göre fark (kol − Lumoda; yüzdede puan, iki ondalık ve bir kez yuvarlanmış bir ondalık)")
    for kol in kollar[1:]:
        if K(v, kol).get("ayni"):
            continue
        print(f"  {kol_adi(kol)}: {_fark_satiri(v, 'dogrulama', kol)}")
    alt("ilk tükenen beden (bedeni biten hücrelerde, varıştan sonra rafı ilk biten bedenin dağılımı; beden 1 → 5)")
    for kol in kollar:
        if K(v, kol).get("ayni"):
            continue
        o = O(v, kol)
        en = en_sik_ilk_tukenen(o)
        print(f"  {kol_adi(kol)}: " + " / ".join(yd(o[f"ilk_tukenen_beden_{i}"], 1) for i in range(1, 6))
              + f" · en sık {en}. beden · en az bir bedeni biten hücre {yd(o['tukenen_hucre_yuzde'], 1)}")
    alt("depoda kalan (beş bedenli option'lar; ilk dağıtımdan sonra depoda fiilen kalan pay, beden 1 → 5)")
    for kol in kollar:
        if not K(v, kol).get("ayni"):
            o = O(v, kol)
            print(f"  {kol_adi(kol)}: " + " / ".join(yd(o.get(f"depoda_kalan_beden_{i}"), 1) for i in range(1, 6)))
    lu, p2 = O(v, "dogrulama"), O(v, "p2")
    d4 = fark(lu["bulunabilirlik_ilk4"], p2["bulunabilirlik_ilk4"], 2)
    ds = fark(lu["bulunabilirlik"], p2["bulunabilirlik"], 2)
    print(f"  P2 − Lumoda bulunabilirlik: ilk 4 hafta {isaretli(d4, 2)} puan, sezon boyu {isaretli(ds, 2)} puan"
          + ("; kazanç ilk haftalarda büyük, sezon boyunca daralıyor"
             if d4 > 0 and ds < d4 else ""))
    alt("mal ve kırpma")
    _tablo(["kol", "ilk dağıtım adet", "replenishment adet", "kırpılan adet", "kırpılan option", "aynı mal"],
           [[kol_adi(k), s(O(v, k)["ilk_dagitim_adet"]), s(O(v, k)["replenishment_adet"]), s(O(v, k)["kirpilan_adet"]),
             s(O(v, k).get("kirpilan_option", 0)), {True: "evet", False: "hayır", None: "—"}[K(v, k)["ayni_mal"]]]
            for k in kollar])


def _yol_degerleri(v, kol: str, olc: str) -> list[float]:
    return [O(v, ad_(p, kol))[olc] for p in yollar(v)]


def yol_farklari(a: list, c: list, ondalik: int) -> dict:
    """Yol başına a − c (basılan değerlerden), medyanı ve yön sayıları."""
    f = [fark(cc, aa, ondalik) for aa, cc in zip(a, c)]
    return {"farklar": f, "medyan": yuv(statistics.median(f), ondalik), "pozitif": sum(x > 0 for x in f),
            "negatif": sum(x < 0 for x in f), "n": len(f)}


def yollar_bolumu(v, ek) -> None:
    ps = yollar(v)
    yl = v.oyun.get("yollar", {})
    print(f"{s(len(ps))} talep yolu (İlk Sevkiyat kalıbı): yol 0 yayımlanan dünya, yol p > 0 aynı dünyada başka bir müşteri "
          "akışı; her yolda eğri, profiller, κ ve tasarımlar o yolun yayımlanan tablolarından yeniden öğrenilir.")
    for p in ps:
        g = yl.get(str(p), {})
        eg = g.get("egri", {})
        lo = K(v, ad_(p, "dogrulama"))
        print(f"  yol {p}: talep tohumu {lo.get('talep_tohumu') if lo.get('talep_tohumu') is not None else 'yayımlanan'} · κ "
              f"{s(eg.get('kappa'))} · profil " + " · ".join(f"{a} {s(n)}" for a, n in (eg.get("profil") or {}).items())
              + f" · ns {s((g.get('ns') or {}).get('paket'))} paket · P2 desenleri {desenler_metni(K(v, ad_(p, 'p2'))['desenler'])}"
              + f" · P3 12'li {desenler_metni(K(v, ad_(p, 'p3_12'))['desenler'])}")
    kollar = list(oyun.YOL_KOLLARI)
    olcutler = OLCUTLER + (("kayip_orani", "kayıp"),)
    for olc, bas in olcutler:
        n = BICIM[olc][1]
        alt(f"{bas} (yol {' · '.join(map(str, ps))}; min / medyan / max basılan değerlerden)")
        for k in kollar:
            yv = [yuv(x, n) for x in _yol_degerleri(v, k, olc)]
            print(f"  {kol_adi(k):<22}" + " · ".join(s(x, n) for x in yv)
                  + f"  | min {s(min(yv), n)} · medyan {s(statistics.median(yv), n)} · max {s(max(yv), n)}")
    alt(f"kaç yolda önde (k/{s(len(ps))}; bulunabilirlik, STR, brüt kâr yüksek; beden kaybı, kırık set, kalan, kayıp düşük "
        "olan önde; medyan fark basılan değerlerden)")
    for a, c in YOL_KIYASLARI:
        parca = []
        for olc, bas in olcutler:
            n = BICIM[olc][1]
            f = yol_farklari(_yol_degerleri(v, a, olc), _yol_degerleri(v, c, olc), n)
            onde = f["pozitif"] if YUKSEK_IYI[olc] else f["negatif"]
            parca.append(f"{bas} {onde}/{f['n']} (medyan {isaretli(f['medyan'], n)})")
        print(f"  {kol_adi(a)} − {kol_adi(c)}: " + " · ".join(parca))
    alt("yüzde ölçütlerinde fark, bir ondalık (iki ondalıklı farkların ve medyanın bir kez yuvarlanmışı)")
    for a, c in YOL_KIYASLARI:
        for olc, bas in olcutler:
            if BICIM[olc][0] != "y":
                continue
            f = yol_farklari(_yol_degerleri(v, a, olc), _yol_degerleri(v, c, olc), 2)
            print(f"  {kol_adi(a)} − {kol_adi(c)} {bas}: " + " · ".join(isaretli(tek_ondalik(x), 1) for x in f["farklar"])
                  + f" | medyan {isaretli(tek_ondalik(f['medyan']), 1)}")
    for p in ps:
        dg = K(v, ad_(p, "dogrulama")).get("ilk_sevkiyat")
        ek.append((f"YOLLAR: yol {p} doğrulama kolu = İlk Sevkiyat Lumoda (ölçütler birebir)",
                   v.olcek != "tam" or (dg is not None and dg["birebir"] == dg["olcut"] and not dg["farkli"])))
    tohum = [K(v, ad_(p, "dogrulama")).get("talep_tohumu") for p in ps]
    ek += [("YOLLAR: talep tohumları farklı", len(set(map(str, tohum))) == len(ps)),
           ("YOLLAR: Lumoda'nın talebi yoldan yola farklı",
            len({O(v, ad_(p, "dogrulama"))["talep_adet"] for p in ps}) == len(ps))]


def k_egrisi_bolumu(v, ek) -> None:
    ke = A(v)["k_egrisi"]
    print("Koşusuz K eğrisi (tasarım uyumsuzluğu: paket başına beklenen eksik adet, mağaza eğrisine göre; `ayni`: aynı desen "
          "ve atamayı veren daha küçük K, ayrı koşu gerekmez). Paket tipi maliyeti verilmez: eğri okura bırakılır.")
    _tablo(["paket", "K", "desenler", "paket başına", "en iyi", "aynı"],
           [[f"{r['adet']}'li", str(r["K"]), desenler_metni(r["desenler"]), s(r["paket_basina"], 4),
             "" if r["en_iyi_mi"] is None else ("kanıtlı" if r["en_iyi_mi"] else "kanıtsız"),
             "" if r["ayni"] is None else f"K = {r['ayni']}"] for r in ke])
    olc = BASLIK + (("brut_kar_tl", "brüt kâr TL"),)
    for a in (7, 12):
        alt(f"{a}'li: K başına ölçütler (koşulan kol ya da aynı tasarımlı ikizi; Lumoda 7'li başlangıç)")
        satir = [] if a != 7 else [["Lumoda", "dogrulama"] + [b(m, O(v, "dogrulama")[m]) for m, _ in olc]]
        for K_ in (*sabitler.K_LISTESI, "magaza"):
            kol, k_ = k_kosusu(v, a, K_)
            if kol is None:
                satir.append([f"K = {K_}", "koşulmadı"] + ["—"] * len(olc))
            else:
                et = kol if k_ == K_ else f"{kol} (K = {k_} ile aynı)"
                satir.append([f"K = {K_}", et] + [b(m, O(v, kol)[m]) for m, _ in olc])
        _tablo(["K", "koşu"] + [bas for _, bas in olc], satir)
    k1, k2 = k_kosusu(v, 7, 1)[0], k_kosusu(v, 7, 2)[0]
    doy7 = all(k_kosusu(v, 7, K_)[1] == 2 for K_ in (3, 4, "magaza"))
    doy12 = all(k_kosusu(v, 12, K_)[1] == 3 for K_ in (4, "magaza"))
    lu = O(v, "dogrulama")
    print(f"  7'li artan kazanç: Lumoda → K = 1 {_fark_satiri(v, 'dogrulama', k1, olc)}")
    print(f"  7'li artan kazanç: K = 1 → K = 2 {_fark_satiri(v, k1, k2, olc)}")
    if doy7:
        print(f"  7'li pakette K = 3, 4 ve mağazaya özel K = 2 ile aynı desen ve atama: kazanç K = 2'de doyuyor (7 adette "
              f"temel bedenler ≥ 1 ile aday desen {s(A(v)['paket']['aday_7'])})")
    p1_12, p3_12 = k_kosusu(v, 12, 1)[0], k_kosusu(v, 12, 3)[0]
    if p1_12 and p3_12:
        print(f"  12'li: K = 1 → K = 3 {_fark_satiri(v, p1_12, p3_12, olc)}")
    if doy12:
        print("  12'li pakette K = 4 ve mağazaya özel K = 3 ile aynı desen ve atama")
    o2 = O(v, k2)
    soru(4, "Kaç paket tipi ne kazandırıyor; kazanç hangi ölçütte? 7'li K = 2 − Lumoda: " + " · ".join(
        f"{bas} {fb(m, lu[m], o2[m])}" for m, bas in olc)
        + ("; K ≥ 2 aynı tasarım (doyum K = 2)" if doy7 else "")
        + ("; 12'li K = 3 − Lumoda: " + " · ".join(f"{bas} {fb(m, lu[m], O(v, p3_12)[m])}" for m, bas in olc)
           if p3_12 else ""))
    kh = A(v)["kahin"]
    alt("mağazaya özel paket ve kahin (doğru okumak ne kadar ileride; Ruling R15: kahin koşulmaz)")
    pm7 = k_kosusu(v, 7, "magaza")
    pm12 = k_kosusu(v, 12, "magaza")
    for a, pm in ((7, pm7), (12, pm12)):
        print(f"  {a}'li mağazaya özel paket: " + (f"K = {pm[1]} ile aynı desen ve atama ({pm[0]})" if pm[1] != "magaza"
                                                   else f"ayrı tasarım ({pm[0] or 'koşulmadı'})"))
    print(f"  kahin (P2'nin desenleri gerçek beden payına göre atanırsa): profil ARI {s(kh['ari'], 3)} ({s(kh['ari_magaza'])} "
          f"okunabilen mağaza); atama {'aynı' if kh['ayni_atama'] else 'farklı'}"
          + ("" if kh["ayni_atama"] else f": {', '.join(kh['farkli_magaza'])} (giden paketteki payı {y(kh['farkli_agirlik_payi'])})"))
    for m, r in kh["farkli"].items():
        print(f"    {m}: tasarım {r['tasarim']} (eğri kaynağı {r['kaynak']}), kahin {r['kahin']}")
    ut, uk = kh["uyumsuzluk_gercek_tasarim"], kh["uyumsuzluk_gercek_kahin"]
    print(f"  gerçek paya göre uyumsuzluk (beklenen eksik adet): P2 ataması {s(ut, 1)}, kahin {s(uk, 1)} "
          f"({y(bolum(uk, ut, 1, 1) - 1 if bolum(uk, ut, 1, 1) is not None else None)}); giden payın gerçeğe L1'i P2 "
          f"{s(A(v)['tasarim']['p2']['giden_gercek_l1'], 4)}, kahin {s(kh['giden_gercek_l1_kahin'], 4)}")
    soru(5, "Mağazaya özel paket (üst sınır) ile 3 paket tipi arasında ne kalıyor; doğru okumak ne kadar ileride? "
            + ("7'li mağazaya özel = K = 2" if pm7[1] == 2 else f"7'li mağazaya özel {pm7[0]}")
            + ("; 12'li mağazaya özel = K = 3 (P3)" if pm12[1] == 3 else "")
            + (f"; kahin atamayı yalnız şu mağazada değiştirir: {', '.join(kh['farkli_magaza'])} (giden paketteki payı "
               f"{y(kh['farkli_agirlik_payi'])}), gerçek paya göre uyumsuzluk {s(ut, 1)} → {s(uk, 1)}"
               if not kh["ayni_atama"] else "; kahin atamayı değiştirmez"))
    ek += [("K EĞRİSİ: 7'li K artınca uyumsuzluk artmaz", all(
        k_satiri(v, 7, a)["toplam_uyumsuzluk"] >= k_satiri(v, 7, c)["toplam_uyumsuzluk"] - 1e-9
        for a, c in ((1, 2), (2, 3), (3, 4)))),
           ("K EĞRİSİ: K = 1 Lumoda'dan kötü değil", k_satiri(v, 7, 1)["toplam_uyumsuzluk"]
            <= k_satiri(v, 7, "lumoda")["toplam_uyumsuzluk"] + 1e-9),
           ("K EĞRİSİ: koşulan kolların deseni = K eğrisi satırı", all(
               K(v, kol)["desenler"] == k_satiri(v, a, k)["desenler"] for (k, a), kol in senaryolar.KOLLAR.items()))]


def ablasyon_bolumu(v, ek) -> None:
    alt("paket büyüklüğü: 12'li (aynı mal yaklaşık: mağaza × option'a giden adedin 12'liye dönüşümü)")
    kollar = ["dogrulama", "p1", "p2", "p1_14", "p1_12", "p2_12", "p3_12"]
    _kiyas_tablosu(v, kollar)
    d14 = A(v)["depo"]["pay"]["7"]["hatali_dusulmus"][0]
    if 2 / 12 > d14:
        print(f"  Lumoda paketinin (1-2-2-1-1) 12'li karşılığı kurulamaz: 1. bedende depo payı {s(d14, 4)}, 12'li "
              f"oranlı desen 1. bedene 2/12 = {s(2 / 12, 4)} ister ve depoyu aşar (Ruling R22); yerine P1'in iki katı "
              "14'lü 2-2-4-4-2 aynı beden paylarını büyük pakette sınar")
    p14 = K(v, "p1_14")
    d = p14.get("donusum")
    if d:
        print(f"  P1 14'lü dönüşüm (aşağı yuvarlama): Lumoda {s(d['lumoda_adet'])} adet → {s(d['kol_adet'])} adet (fark "
              f"{isaretli(d['fark_adet'])}); 0 pakete düşen hücre {s(d['sifir_hucre'])}/{s(d['hucre'])}")
    alt("ayrıştırma (Ruling R22): paket büyüklüğü ↔ içerik inceliği")
    for a, c, et in (("p1", "p1_14", "yalnız paket büyüklüğü (aynı içerik): P1 14'lü − P1"),
                     ("p1", "p1_12", "içerik inceliği + büyüklük: P1 12'li − P1"),
                     ("p1_12", "p3_12", "12'lide paket tipi: P3 12'li − P1 12'li")):
        print(f"  {et}: {_fark_satiri(v, a, c)}")
    dn = K(v, "p3_12")["donusum"]
    print(f"  dönüşüm: Lumoda {s(dn['lumoda_adet'])} adet → 12'li kol {s(dn['kol_adet'])} adet (fark {isaretli(dn['fark_adet'])}); "
          f"0 pakete düşen hücre {s(dn['sifir_hucre'])}/{s(dn['hucre'])}; {s(dn['option'])} option, option başına en büyük "
          f"fark {s(dn['option_en_buyuk_fark'])} adet (sınır {s(dn['option_fark_siniri'])}: option toplamı en yakın tam pakete)")
    print(f"  P1 12'li − P1 7'li: {_fark_satiri(v, 'p1', 'p1_12')}")
    print(f"  P3 12'li − P2 7'li: {_fark_satiri(v, 'p2', 'p3_12')}")
    t = A(v)["tasarim"]
    p3, p2 = O(v, "p3_12"), O(v, "p2")
    d4 = fark(p2["bulunabilirlik_ilk4"], p3["bulunabilirlik_ilk4"], 2)
    soru(6, f"Paket büyüklüğü (7 → 12) neyi değiştiriyor? 12'li pakette desen sayısı {len(t['p3_12']['desenler'])} "
            f"({desenler_metni(t['p3_12']['desenler'])}), 7'lide {len(t['p2']['desenler'])}; P3 12'li − P2 7'li: "
            + " · ".join(f"{bas} {fb(m, p2[m], p3[m])}" for m, bas in OLCUTLER)
            + f"; adet farkı {isaretli(dn['fark_adet'])} (aynı mal yaklaşık); yalnız büyüklük (P1 14'lü − P1): "
            + " · ".join(f"{bas} {fb(m, O(v, 'p1')[m], O(v, 'p1_14')[m])}" for m, bas in BASLIK)
            + "; içerik inceliği + büyüklük (P1 12'li − P1): "
            + " · ".join(f"{bas} {fb(m, O(v, 'p1')[m], O(v, 'p1_12')[m])}" for m, bas in BASLIK)
            + ("" if d4 else "; ilk 4 hafta bulunabilirlik aynı"))
    alt("sansür düzeltmesiz eğri (P2 ham)")
    h = K(v, "p2_ham")
    a = A(v)["egri"]["ham_duz_l1"]
    if h.get("ayni") == "p2" and t["p2_ham"]["ayni"] == "p2":
        print(f"  ham eğriyle tasarlanan P2 düzeltilmiş eğriyle tasarlananla aynı desen ve atama: sansür düzeltmesi 7'li "
              f"tasarımı değiştirmiyor (ham ↔ düzeltilmiş eğri L1 ortalama {s(a['ortalama'], 4)}, en çok {s(a['en_cok'], 4)})")
    else:
        print(f"  P2 ham: {desenler_metni(h['desenler'])}; P2 ham − P2: {_fark_satiri(v, 'p2', 'p2_ham')}")
    ek += [("ABLASYON: 12'li kolların dönüşümü aynı (aynı ns)",
            all(K(v, k)["donusum"] == dn for k in ("p1_12", "p2_12"))),
           ("ABLASYON: P1 14'lü P1'in iki katı (aynı beden payları)",
            K(v, "p1_14")["desenler"] == ["-".join(str(2 * int(x)) for x in K(v, "p1")["desenler"][0].split("-"))]),
           ("ABLASYON: 12'li dönüşümde option başına fark sınırda", dn["option_en_buyuk_fark"] <= dn["option_fark_siniri"])]


def kumeleme_bolumu(v, ek) -> None:
    km = v.kumeler
    if km is None:
        raise Eksik("kumeler.json")
    e = A(v)["egri"]
    t = A(v)["tasarim"]["p2"]
    profil = e["profil_magaza"]
    ml = dict(km["ml"]["etiket"])
    ml |= km["ml"].get("yeni_magaza", {}).get("atama", {})
    ortak = sorted(m for m in profil if m in ml)
    print(f"  Mağaza Kümeleme'nin satış karışımı kümeleri (kumeler.json, öneri {km['ml']['aile']} {km['ml']['yontem']} "
          f"k = {km['ml']['k']}; yeni mağazalar 5-NN ataması) ile beden profilleri, {s(len(ortak))} ortak mağaza")
    satirlar = sorted({profil[m] for m in ortak})
    sutunlar = sorted({ml[m] for m in ortak})
    deg = [[sum(1 for m in ortak if profil[m] == p and ml[m] == c) for c in sutunlar] for p in satirlar]
    _capraz({"satirlar": satirlar, "sutunlar": sutunlar, "degerler": deg}, "profil \\ satış kümesi")
    r = ari([profil[m] for m in ortak], [ml[m] for m in ortak])
    bag = abs(r) < BAGIMSIZ_ARI
    print(f"  ARI (beden profili ↔ satış kümesi) {s(r, 3)}" + (": iki eksen bağımsız (ANLATI VARSAYIMLARI eşiği)" if bag else ""))
    print("  P2 deseni profili izler: " + " · ".join(
        f"{p} → " + "/".join(c for c, n in zip(t["profil_desen"]["sutunlar"], row) if n)
        for p, row in zip(t["profil_desen"]["satirlar"], t["profil_desen"]["degerler"])))
    soru(3, f"Mağazalar kaç beden profiline ayrılıyor; bu profiller satış karışımı kümelerinden bağımsız mı? "
            f"{len(e['profil'])} profil (" + " · ".join(f"{p} {s(n)}" for p, n in e["profil"].items())
            + f"); satış kümeleriyle ARI {s(r, 3)}" + (" (bağımsız)" if bag else ""))
    ek.append(("KÜMELEME: kümeler kapsamın her mağazasını kapsar (kumeler.json ↔ analiz)", len(ortak) == e["magaza"]))


def _sahne(h: dict, ad: str) -> None:
    for rol, et in (("buyuk", "büyüğe kayık"), ("kucuk", "küçüğe kayık")):
        r = h[rol]
        kn = h.get("magazalar", {}).get(r["magaza"], {})
        kim = "Ali'nin" if r["istanbul"] else "Veli'nin"
        print(f"  {ad} {et}: {r['magaza']} {kn.get('ad', '')} ({kn.get('sehir', '')}, {kn.get('bolge', '')}, {kn.get('tip', '')}, "
              f"{s(kn.get('metrekare'))} m²; {kim}); profil {r['profil']}, eğri {pay_metni(r['egri'])}")
        print(f"    option {r['option']} ({r['sezon']}, {r['beden_seti']}): varış {r['varis']}, {s(r['paket'])} paket "
              f"{r['desen']} ({s(sum(x['gelen'] for x in r['bedenler']))} adet); ilk {s(h['pencere_hafta'])} haftada satış "
              f"{s(r['satis'])}")
        _tablo(["beden", "gelen", "satış", "biten hafta", "rafsız gün", "kalan"],
               [[f"{x['beden_sira']} ({x['beden']})", s(x["gelen"]), s(x["satis"]),
                 "—" if x["biten_hafta"] is None else s(x["biten_hafta"]), s(x["bos_gun"]), s(x["kalan"])]
                for x in r["bedenler"]])
    dg = h.get("dogrulama")
    if dg:
        print("    hakem (yalnız doğrulama; yazıda \"gerçekte\"): gizli kayma " + " · ".join(
            f"{m} {isaretli(k)}" for m, k in dg["kayma"].items())
              + f"; büyük +1 {'evet' if dg['buyuk'] else 'hayır'}, küçük −1 {'evet' if dg['kucuk'] else 'hayır'}")
    print(f"    kademe {h['kademe']}; roller {h['roller']}; gevşeyen: {'; '.join(h['gevseyen']) or 'yok'}; doğrulamada "
          f"elenen sahne {h['elenen']}")


def hikaye_bolumu(v, ek) -> None:
    h = v.hikaye
    if h is None:
        raise Eksik("hikaye.json")
    print("  merdiven (spec §6): büyük profilli Anadolu mağazasında (Veli) 4. ve 5. beden ilk haftalarda öteki bedenlerden "
          "önce biter, 1. beden rafta kalır; küçük profilli İstanbul mağazasında (Ali) tersi; ikisine de aynı 1-2-2-1-1 paketi "
          "(sevkiyat tablosundan); karar öncesi yayımlanan veri")
    print(f"  zincir eğrisi {pay_metni(h['zincir'])}")
    _sahne(h, "SAHNE")
    print(f"  hakemsiz seçim aynı sahneyi veriyor: {'evet' if h.get('hakemsiz_ayni') else 'hayır'}")
    os_ = h.get("once_sarti") or {}
    oz = os_.get("oncesiz")
    print("  \"hedef bedenler öteki bedenlerden önce biter\" şartı sonuç görüldükten sonra eklendi (ilk tasarımda yoktu; "
          f"seçilen sahne kademe {h['kademe']}); şart olmasaydı: "
          + ("sahne yok" if oz is None else
             f"büyük {oz['buyuk']} ({oz['option_buyuk']}), küçük {oz['kucuk']} ({oz['option_kucuk']}), kademe {oz['kademe']}"
             + (" (aynı sahne)" if os_.get("ayni") else " (başka sahne)")))
    if h.get("alternatif"):
        _sahne(h["alternatif"], "ALTERNATİF")
    lumoda = "-".join(map(str, sabitler.LUMODA_PAKET))
    pr = A(v)["egri"]["profil_magaza"]
    for rol in ("buyuk", "kucuk"):
        r = h[rol]
        ek += [(f"HİKÂYE: {rol} mağazaya Lumoda paketi", r["desen"] == lumoda),
               (f"HİKÂYE: {rol} gelen = paket × desen",
                [x["gelen"] for x in r["bedenler"]] == [r["paket"] * k for k in sabitler.LUMODA_PAKET]),
               (f"HİKÂYE: {rol} profili analizin eğrisiyle aynı", pr.get(r["magaza"]) == r["profil"] == rol)]
    ek.append(("HİKÂYE: karar günü aynı", h["karar_gunu"] == A(v)["veri"]["karar_gunu"]))
    if h.get("dogrulama") is not None:
        ek.append(("HİKÂYE: hakem doğruladı", h["dogrulama"]["buyuk"] and h["dogrulama"]["kucuk"]))


def demo_bolumu(v, ek) -> None:
    son = senaryolar.sonuclar(v.oyun, A(v))
    eks = senaryolar.eksik(A(v)["k_egrisi"])
    print(f"  {len(son)} bileşim: paket tipi sayısı {{{', '.join(str(k) for k in senaryolar.PAKET_TIPLERI)}}} × paket "
          f"büyüklüğü {{7, 12}}; kartlar ilk 4 hafta bulunabilirlik, beden kaybı payı, kırık set (bir ondalık: iki "
          "ondalıklının bir kez yuvarlanmışı), brüt kâr")
    _tablo(["bileşim", "ilk 4 hf bulun.", "ilk 4 hf beden kaybı", "ilk 4 hf kırık set", "brüt kâr TL", "koşu", "desenler"],
           [[a, yd(r["ozet"]["bulunabilirlik_ilk4"], 1), yd(r["ozet"]["beden_kayip_payi_ilk4"], 1),
             yd(r["ozet"]["kirik_cift_pay_yuzde_ilk4"], 1), s(r["ozet"]["brut_kar_tl"]),
             r["satirlar"][0]["kosu"] + (f" ({r['satirlar'][0]['ayni']} ile aynı)" if r["satirlar"][0]["ayni"] else ""),
             " · ".join(f"{x['desen']} ({x['magaza']})" for x in r["satirlar"])] for a, r in son.items()])
    if eks:
        print(f"  dosyada olmayan bileşim (koşusu ve aynı tasarımlı ikizi yok): {', '.join(eks)}")
    ek.append(("DEMO: arayüzün her bileşiminin sonucu var", not eks and len(son) == len(senaryolar.PAKET_TIPLERI)
               * len(senaryolar.ADETLER)))
    dosya = v.demo_dosya
    if dosya is None or dosya != senaryolar.uret(v.oyun, A(v)):
        if not v.taslak:
            raise AssertionError("DEMO: site dosyası senaryolar.uret() ile aynı değil")
        print("  [eksik: demo dosyası güncel değil]")
    else:
        print(f"  site dosyası {senaryolar.HEDEF.name}: sürüm {dosya['surum']} (içeriğin özeti)")
    if v.demo_bayt is not None or not v.taslak:
        ek.append(("DEMO: sitedeki dosya bütçe içinde", v.demo_bayt is not None and v.demo_bayt < senaryolar.BUTCE))


def anlati_bolumu(v, ek) -> None:
    print("Veriden gelmeyen, anlatı için konmuş değerler ve tanımlar (varsayım; yazıda kesin sayı gibi sunulmaz):")
    for anahtar, deger in ANLATI_VARSAYIMLARI.items():
        print(f"  {anahtar}: {deger}")


def korunum_bolumu(v, ek) -> None:
    dg = K(v, "dogrulama")
    ref = dg.get("ilk_sevkiyat")
    if v.olcek == "tam":
        ek.append(("doğrulama kolu = İlk Sevkiyat Lumoda (yol 0, bütün ölçütler birebir)",
                   ref is not None and ref["birebir"] == ref["olcut"] and not ref["farkli"]))
        isv = A(v).get("ilk_sevkiyat") or {}
        ek.append(("İlk Sevkiyat Lumoda koşularının anahtarları değişmedi ve önbellekte (5 yol)",
                   len(isv) == sabitler.YOL_SAYISI and all(r["anahtar_ayni"] and r["onbellekte"] for r in isv.values())))
    for p in yollar(v):
        for kol in oyun.YOL0_KOLLARI if p == 0 else oyun.YOL_KOLLARI:
            if kol == "dogrulama":
                continue
            ad = ad_(p, kol)
            e = K(v, ad)
            o = e["olcutler"]
            ek += [(f"{ad}: kırpma 0 (adet ve option)", o["kirpilan_adet"] == 0 and o.get("kirpilan_option", 0) == 0),
                   (f"{ad}: aynı mal", e["ayni_mal"] is True)]
            if e["paket_adet"] == sabitler.PAKET_ADET:
                lp = O(v, ad_(p, "dogrulama"))
                ek += [(f"{ad}: çift başına giden adet = Lumoda'nın", e["korunum"]["fark_adet"] == 0
                        and e["korunum"]["fark_hucre"] == 0),
                       (f"{ad}: ilk dağıtım adedi = Lumoda'nın", o["ilk_dagitim_adet"] == lp["ilk_dagitim_adet"])]
    ek.append(("analiz.json bu oyun.json'un Lumoda koşusundan", A(v)["lumoda_anahtar"] == dg["anahtar"]))
    n = korunum(ek)
    print(f"  {s(n)} denetim tuttu: doğrulama kolu (İlk Sevkiyat Lumoda), aynı mal ve kırpma (her kol, her yol), İlk "
          "Sevkiyat anahtarları,")
    print("  tasarım kayıtları, K eğrisi, hikâye, demo bileşimleri ve site dosyası, veri sayımları.")
    print(f"  oyun.json kayıtları bugünkü ölçüm koduyla ({oyun.olcum_kodu()[:12]}); analiz.json "
          f"{A(v)['kod'][:12]}; hikaye.json {(v.hikaye or {}).get('kod', '—')[:12]}.")


BOLUMLER = [
    ("VERİ", veri_bolumu), ("PAKET", paket_bolumu), ("EĞRİ", egri_bolumu), ("TASARIM", tasarim_bolumu),
    ("KOLLAR", kollar_bolumu), ("YOLLAR", yollar_bolumu), ("K EĞRİSİ", k_egrisi_bolumu), ("ABLASYON", ablasyon_bolumu),
    ("KÜMELEME ÇAPRAZI", kumeleme_bolumu), ("HİKÂYE", hikaye_bolumu), ("DEMO", demo_bolumu),
    ("ANLATI VARSAYIMLARI", anlati_bolumu), ("KORUNUM", korunum_bolumu),
]


def govde(v) -> None:
    """Bütün bölümler sırasıyla; korunum en sonda (tutmazsa AssertionError). Taslakta `Eksik` veren bölüm atlanır."""
    print("Beden ve Paket — v4 raporu. Kaynak: cikti/oyun.json (python -m beden_paket.oyun izgara), cikti/analiz.json, "
          f"cikti/hikaye.json, Mağaza Kümeleme kumeler.json, site/src/data/senaryolar/{senaryolar.HEDEF.name}.")
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
    sys.stdout.write(metin)
    return 2 if v.taslak else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
