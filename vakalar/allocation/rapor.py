"""İlk Sevkiyat dizisinin (6 yazı, `/allocation/ilk-sevkiyat/`) yayımlanacak BÜTÜN sayıları buradan
basılır (v4).

    cd vakalar/allocation
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py --taslak   # ızgara bitmeden biçim denetimi

Kalıcı kural: yazıya yeni bir sayı girmeden önce buraya eklenir; ortak sayı denetimi (`cd
vakalar/allocation && .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi
../../site/src/content/yazi/allocation/ilk-sevkiyat --rapor cikti/rapor.txt`) yazılardaki her sayının
bu çıktıda geçtiğini denetler. Sayılar Türkçe basılır (binlik nokta, ondalık virgül, `%12,3`,
`−0,32`). Uydurma sayı yasaktır; elle konmuş anlatı değerleri yalnız ANLATI VARSAYIMLARI'ndadır.
Raporda takvim tarihi geçer (izlenebilirlik); yazılar tarih ve yıl basmaz, mevsime göreli söyler.

Bölümler (`BOLUMLER`, bu sırayla; spec §5). Başlık sorularının (spec §4.6) her biri ilgili
bölümde tek bir `SORU n · …` satırıdır (cevap basılan değerlerden; yön sözcükleri işaretten):

    VERİ                  ölçek (dalgalar, option, mağaza), ilk alım, paket, aday kümesi, U
    KURAL                 Lumoda'nın plan payı, uç hücreler (oturan / hızlı biten), motorun kırpması
    KALİBRASYON           SS24: koşusuz WAPE seçimleri, belirsizlik ölçüsü, tavan ve γ simülasyonu
    YOL 0                 her koşunun bütün ölçütleri; pay bloğu kıyası (SORU 1, SORU 2)
    YOLLAR                5 talep yolu: min / medyan / max, "kaç yolda önde"
    TAVAN                 kapsama tavanı açık / kapalı (SORU 3)
    SABİT TAKVİM          dağıtımın doğrudan etkisi ↔ RPT ve markdown tepkisi (SORU 8)
    TUTMA                 tutma × pay kaynağı × replenishment, online (SORU 4)
    STRATEJİ              belirsizliğe göre tutma ↔ sabit t = %30 (SORU 5)
    İSABET                pay WAPE'si, oturan / hızlı biten hücreler, tavanın bağladığı
    BEDEN                 beden uyumsuzluğu (SORU 6), beden beden depoda kalan (SORU 7)
    HİKÂYE                sahne, plan, kolun kararı, alternatif, merdiven
    DEMO                  12 bileşim
    KÜME                  küme payı kolları (Mağaza Kümeleme SORU 7): koşusuz kalibrasyon, kümeler, yol 0, yollar;
                          `KÜME SORU 7 · …` satırı (İlk Sevkiyat'ın SORU 1–8'inden ayrı)
    ANLATI VARSAYIMLARI
    KORUNUM

Rapor önce tampona yazılır; korunum tutmazsa ya da bir girdi eksikse (önbellekte olmayan koşu,
bugünkü kodla yazılmamış kayıt, ölçülmemiş ızgara noktası) stdout'a tek satır gitmez, mesaj stderr'e,
çıkış kodu 1. `--taslak` eksik girdiye dayanan satırları "[eksik: …]" diye geçer ve sonda listeler
(çıkış kodu 2; bu çıktı yazılara kaynak olamaz). Basılan her fark, oran ve ara değer basılan
işlenenlerden hesaplanır (`yuv`, `fark`, `bolum`); bir ondalıklı fark iki ondalıklı farkın bir kez
yuvarlanmışıdır (`fark1`, Ruling R50 ve R53: aynı büyüklüğe tek değer). Ölçülen süre basılmaz: aynı girdiyle iki koşu bayt
bayt aynıdır. Girdiler `rapor_b.py`'de (motoru koşmaz; önbellekten).

Okuma notları (Ruling R43): "en iyi" kol pay bloğunun tavansız benzer ve tahmin kollarından seçilir (aynı
mal); tutma ekseni, belirsizliğin tabanı ve demo bu tavansız kolla kurulur. En iyinin seçimi, tutma ve
strateji SS25'te ölçülür, yani örneklem içidir: rapor onları ölçüm olarak basar, örneklem dışı karar diye
değil. Tavanın etkisi eşleşik tutma koşularıyla ayrıştırılır (tavanlı ↔ eşleşik = tavanın dağıtım
biçimi, eşleşik ↔ t 0 = depoda tutma). Belirsizliğin γ'sı kalibrasyon sezonunda tavanlı tabanla seçildi (STRATEJİ'de not).
`markdown_tl` brüt indirim tutarıdır, `brut_kar_tl` net satış − alış maliyetidir: ikisi toplanmaz.
"""

import argparse
import contextlib
import io
import statistics
import sys
import warnings
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd

import rapor_b
from allocation import oyun, sabitler
from rapor_b import Eksik

warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*force_all_finite.*", category=FutureWarning)

# Hikâyedeki elle değerler (1. yazı): veriden gelmez. Değer değişirse kayıt defterine yazılır.
ANLATI_VARSAYIMLARI = {
    "arama_gunu": "iki mağazanın Veli'yi aradığı gün: varıştan sonraki dördüncü pazartesi (taşanın 28 günlük "
                  "penceresinin bittiği gün)",
}


# ---------------------------------------------------------------------------
# Biçim
# ---------------------------------------------------------------------------

def _yok(x) -> bool:
    if x is None or x is pd.NaT:
        return True
    try:
        return bool(isinstance(x, (float, np.floating)) and np.isnan(x))
    except TypeError:
        return False


def _sifir_mi(metin: str) -> bool:
    return metin.lstrip("-").replace(".", "").replace(",", "").strip("0") == ""


def s(x, ondalik: int = 0) -> str:
    """Türkçe sayı: 1.234.567 · 0,55 · −3,2 (yuvarlanınca sıfır olan negatif işaretsiz)."""
    if _yok(x):
        return "—"
    metin = f"{float(x):,.{ondalik}f}".replace(",", "_").replace(".", ",").replace("_", ".")
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


def tl(x, ondalik: int = 0) -> str:
    return "—" if _yok(x) else f"{s(x, ondalik)} TL"


def yuv(x, ondalik: int = 0) -> float:
    """`s(x, ondalik)`'ın bastığı değer."""
    return float(f"{float(x):.{ondalik}f}")


def fark(a, b, ondalik: int = 0) -> float:
    """b − a, ikisi de `ondalik` hanede basıldığı gibi."""
    return yuv(yuv(b, ondalik) - yuv(a, ondalik), ondalik)


def tek_ondalik(x2) -> float:
    """İki ondalıklı değerin bir kez, yarımda sıfırdan uzağa yuvarlanmışı: +0,95 → +1,0, −0,35 → −0,4 (ondalık
    aritmetikle; ikili kayan noktanın 0,95 → 0,9 sapması olmadan)."""
    return float(Decimal(f"{float(x2):.2f}").quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fark1(a, b) -> float:
    """b − a, bir ondalık: iki ondalıklı farkın (`fark(a, b, 2)`) bir kez yuvarlanmışı (Ruling R50, R53). Aynı
    büyüklüğün iki ondalıklı ve bir ondalıklı biçimi raporda tek değerdir; bir ondalıklı düzeylerin farkı değildir."""
    return tek_ondalik(fark(a, b, 2))


def bolum(a, b, ondalik_a: int = 0, ondalik_b: int = 0) -> float | None:
    """a / b, ikisi de basıldığı gibi."""
    payda = yuv(b, ondalik_b)
    return yuv(a, ondalik_a) / payda if payda else None


def yon(a, b, yuksek_iyi: bool, ondalik: int) -> str:
    """a'nın b'ye göre yönü, basılan değerlerden: "önde" | "geride" | "eşit"."""
    d = fark(b, a, ondalik)
    if d == 0:
        return "eşit"
    return "önde" if (d > 0) == yuksek_iyi else "geride"


def kapanan_pay(kol, lumoda, kahin, ondalik: int) -> float | None:
    """Kahinle Lumoda arasındaki farkın kolun kapattığı payı: (kol − lumoda) ÷ (kahin − lumoda),
    `ondalik` hanede basılan değerlerden (bulunabilirlikte iki ondalık, R53); kapatılacak fark yoksa None."""
    payda = fark(lumoda, kahin, ondalik)
    return fark(lumoda, kol, ondalik) / payda if payda else None


def yol_farklari(a: list, b: list, ondalik: int) -> dict:
    """Yol başına a − b (basılan değerlerden), medyanı ve yön sayıları."""
    f = [fark(bb, aa, ondalik) for aa, bb in zip(a, b)]
    return {"farklar": f, "medyan": yuv(statistics.median(f), ondalik), "pozitif": sum(v > 0 for v in f),
            "negatif": sum(v < 0 for v in f), "n": len(f)}


def baslik(metin: str) -> None:
    print(f"\n=== {metin} ===")


def alt(metin: str) -> None:
    print(f"\n--- {metin} ---")


def soru(n: int, metin: str) -> None:
    print(f"SORU {n} · {metin}")


def tamponla(govde) -> tuple[int, str]:
    """`govde()`yi stdout'u tamponlayarak koşar: (0, metin) ya da korunum bozulursa (1, "") ve mesaj
    stderr'e."""
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


# ---------------------------------------------------------------------------
# Kısayollar
# ---------------------------------------------------------------------------

def K(v, ad: str) -> dict:
    """Ölçülmüş ve önbellekte geçerli koşunun kaydı; değilse `Eksik`."""
    if ad not in v.gecerli:
        raise Eksik(ad)
    return v.oyun["kosular"][ad]


def O(v, ad: str) -> dict:
    return K(v, ad)["olcutler"]


def pay_kollari(v) -> dict[str, str]:
    """Pay bloğunun aynı malı gönderen ana kolları (t = 0, tepkili RPT ve markdown; Ruling R43: benzer ve
    tahmin tavansız): kısa ad → koşu."""
    return {"lumoda": "lumoda", "esit": "pay_esit", "benzer": "pay_benzer_tavansiz", "tahmin": "pay_tahmin_tavansiz",
            "kahin": "pay_kahin"}


def pay_karsiligi(v, ad: str) -> str:
    """Koşunun (ör. sabit takvimli) tepkili pay bloğu karşılığı: aynı kol ve aynı tavan."""
    c = K(v, ad)["cozum"]
    if c["kol"] == "lumoda":
        return "lumoda"
    if c["kol"] in ("benzer", "tahmin"):
        return f"pay_{c['kol']}_{'tavanli' if c['tavan'] else 'tavansiz'}"
    return f"pay_{c['kol']}"


def kahin_olculur(v, ad: str = "pay_kahin") -> bool:
    """Kahinin bağımsızlık varsayımı (spec §0/11, §10) bu koşuda tuttu mu."""
    return bool((v.bagimsizlik or {}).get(ad))


PAY_SATIRLARI = (("lumoda", "lumoda"), ("esit", "pay_esit"), ("benzer tavanlı", "pay_benzer_tavanli"),
                 ("benzer tavansız", "pay_benzer_tavansiz"), ("tahmin tavanlı", "pay_tahmin_tavanli"),
                 ("tahmin tavansız", "pay_tahmin_tavansiz"), ("kahin", "pay_kahin"))


def pay_satirlari(v) -> list[tuple[str, str]]:
    """Pay bloğunun yedi koşusu (tavanlı ve tavansız); kahin ölçülemiyorsa düşer."""
    return [(et, ad) for et, ad in PAY_SATIRLARI if ad != "pay_kahin" or kahin_olculur(v)]


def secim_adi(v) -> str:
    if not v.secim:
        raise Eksik("secim.json")
    return v.secim["ad"]


BICIM = {  # ölçüt → (tür, ondalık): y yüzde, s sayı, t TL
    "bulunabilirlik": ("y", 2), "bulunabilirlik_ilk4": ("y", 2), "talep_adet": ("s", 0), "satis_adet": ("s", 0),
    "kayip_orani": ("y", 2), "ikame_payi": ("y", 1), "kalici_kayip_orani": ("y", 2),
    "toplam_mal": ("s", 0), "rpt_adet": ("s", 0), "ilk_dagitim_adet": ("s", 0), "replenishment_adet": ("s", 0),
    "elle_transfer_adet": ("s", 0), "kalan_magaza_adet": ("s", 0), "kalan_depo_adet": ("s", 0),
    "kalan_depo_ek_adet": ("s", 0), "sezon_sonu_kalan_yuzde": ("y", 2),
    "tam_fiyat_str": ("y", 2), "markdown_tl": ("t", 0), "markdown_tl_fiziksel": ("t", 0),
    "markdown_tl_online": ("t", 0), "brut_kar_tl": ("t", 0), "brut_kar_tl_fiziksel": ("t", 0),
    "brut_kar_tl_online": ("t", 0), "online_satis": ("s", 0),
    "pay_wape": ("s", 3), "ilk_hucre": ("s", 0), "oturan_hucre": ("s", 0), "hizli_biten_hucre": ("s", 0),
    "kirpilan_adet": ("s", 0), "tavan_baglayan": ("s", 0), "tavan_kalan_adet": ("s", 0), "adaysiz_option": ("s", 0),
    "stoklu_cift_gun": ("s", 0), "kirik_cift_pay_yuzde": ("y", 1), "beden_kayip_payi": ("y", 1),
    "tukenen_hucre_yuzde": ("y", 1),
    **{f"{a}_{b}": ("y", 1) for a in ("depoda_kalan_beden", "alimdan_kalan_beden", "ilk_tukenen_beden")
       for b in range(1, 6)},
}
OLCUT_SIRASI = tuple(BICIM)
ONDALIK = {a: n for a, (_, n) in BICIM.items()}
YUKSEK_IYI = {"bulunabilirlik": True, "bulunabilirlik_ilk4": True, "kayip_orani": False,
              "sezon_sonu_kalan_yuzde": False, "tam_fiyat_str": True, "markdown_tl": False, "brut_kar_tl": True,
              "pay_wape": False}
# Kıyas tablolarının sütunları (ölçüt, başlık, ondalık)
KIYAS = (("bulunabilirlik", "bulun.", 2), ("bulunabilirlik_ilk4", "ilk 4 hf", 2), ("kayip_orani", "kayıp", 2),
         ("tam_fiyat_str", "tam STR", 2), ("sezon_sonu_kalan_yuzde", "kalan", 2), ("markdown_tl", "markdown TL", 0),
         ("brut_kar_tl", "brüt kâr TL", 0), ("pay_wape", "WAPE", 3))
MAL = (("ilk_dagitim_adet", "ilk dağıtım"), ("rpt_adet", "RPT"), ("toplam_mal", "toplam mal"),
       ("replenishment_adet", "replenishment"), ("kalan_magaza_adet", "kalan mağaza"),
       ("kalan_depo_adet", "kalan depo"), ("online_satis", "online satış"))


def b(ad: str, x) -> str:
    tur, n = BICIM.get(ad, ("s", 2))
    return yd(x, n) if tur == "y" else tl(x, n) if tur == "t" else s(x, n)


def kol_metni(e: dict) -> str:
    """Koşunun çözülmüş tanımı (oyun.json `cozum`) okunur biçimde."""
    c = e.get("cozum", {})
    kol = c.get("kol", "?")
    parca = [kol + (f" (taban {c['taban']})" if c.get("taban") else "")]
    if kol in ("benzer", "tahmin") or c.get("taban") in ("benzer", "tahmin"):
        parca.append("tavanlı" if c.get("tavan") else "tavansız")
    parca.append("t option başına (t̄ %30)" if c.get("tutma") is None else f"t {yd(100 * c['tutma'], 0)}")
    parca.append("replenishment hiz" if c.get("repl") == "hiz" else "replenishment Lumoda")
    parca.append("sabit takvim" if c.get("takvim") else "tepkili RPT ve markdown")
    if c.get("yol"):
        parca.append(f"yol {c['yol']}")
    return " · ".join(parca)


def _kiyas_tablosu(v, satirlar: list[tuple[str, str]], olcutler=KIYAS) -> None:
    print(f"  {'kol':<26}" + "".join(f"{bas:>15}" for _, bas, _ in olcutler))
    for etiket, ad in satirlar:
        o = O(v, ad)
        print(f"  {etiket:<26}" + "".join(
            f"{(yd(o[m], n) if BICIM[m][0] == 'y' else s(o[m], n)):>15}" for m, _, n in olcutler))


def _mal_tablosu(v, satirlar: list[tuple[str, str]]) -> None:
    print(f"  {'kol':<26}" + "".join(f"{bas:>15}" for _, bas in MAL))
    for etiket, ad in satirlar:
        o = O(v, ad)
        print(f"  {etiket:<26}" + "".join(f"{s(o[m]):>15}" for m, _ in MAL))


def _fark_satiri(v, a: str, c: str, olcutler=KIYAS) -> str:
    """c − a, basılan değerlerden."""
    oa, oc = O(v, a), O(v, c)
    return " · ".join(f"{bas} {isaretli(fark(oa[m], oc[m], n), n)}" for m, bas, n in olcutler)


# ---------------------------------------------------------------------------
# Bölümler
# ---------------------------------------------------------------------------

def veri_bolumu(v, ek) -> None:
    yy = v.yayimlanan
    print(f"Kaynak: yayımlanan v4 tabloları (= `lumoda` koşusu, eşdeğerlik testi); oyun sezonu {sabitler.OYUN_SEZONU}, "
          f"line {sabitler.LINE}. İlk dağıtım yalnız fiziksel mağazalara (AVM, Cadde); online depodan satar.")
    alt("dalgalar")
    lan = yy["lansman"].set_index("dalga")
    d = yy["dalga"]
    for _, r in d.iterrows():
        ln = lan.loc[int(r["dalga"])]
        print(f"  dalga {s(r['dalga'])}: lansman {pd.Timestamp(ln['lansman_tarihi']).date()} · {s(r['option'])} option · "
              f"ilk alım (ilk sipariş) {s(r['ilk_alim'])} adet (teslim edilen {s(r['teslim'])}) · ilk dağıtım "
              f"{s(r['ilk_dagitim'])} adet (ilk alımın {y(bolum(r['ilk_dagitim'], r['ilk_alim']))})")
    top = {a: int(d[a].sum()) for a in ("option", "ilk_alim", "teslim", "ilk_dagitim")}
    print(f"  toplam: {s(top['option'])} option · ilk alım {s(top['ilk_alim'])} adet (teslim edilen {s(top['teslim'])}) · "
          f"ilk dağıtım {s(top['ilk_dagitim'])} adet (ilk alımın {y(bolum(top['ilk_dagitim'], top['ilk_alim']))}; "
          f"option başına ortalama {s(bolum(top['ilk_dagitim'], top['option']))} adet)")
    ilk = lan.iloc[0]
    print(f"  indirim başlangıcı {pd.Timestamp(ilk['indirim_baslangic']).date()}, çıkış (outlet akışı) "
          f"{pd.Timestamp(ilk['cikis_tarihi']).date()}; erken pencere lansmandan {s(sabitler.ERKEN_GUN)} gün, en geç "
          f"indirimden {s(sabitler.ERKEN_KESIM_GUN)} gün önce kesilir")
    alt("mağazalar")
    m = yy["magaza"]
    ist = int(m["istanbul"].sum())
    print(f"  ilk dağıtım alan fiziksel mağaza {s(len(m))}: İstanbul (Ali) {s(ist)}, Anadolu (Veli) {s(len(m) - ist)}; "
          f"en çok mağazaya giden option {s(d['en_cok_magaza'].max())} mağaza")
    alt("paket ve beden")
    icerik: dict[str, list[str]] = {}
    for seti, g in yy["paket"].groupby("beden_seti", sort=True):
        icerik.setdefault(f"{'-'.join(s(x) for x in g['adet'])} = {s(g['adet'].sum())} adet", []).append(str(seti))
    for ic, setler in icerik.items():
        print(f"  paket {ic}: {', '.join(setler)}")
    bd = yy["beden"]
    toplam_b = int(bd["adet"].sum())
    print(f"  ilk alımın beden payları (beş bedenli {s(yy['bes_bedenli_option'])} option, beden sırasıyla): "
          + " / ".join(y(bolum(a, toplam_b)) for a in bd["adet"]))
    print(f"  paketin en küçük bedene payı: 1 / 7 = {y(1 / 7)} (ilk alımda {y(bolum(int(bd['adet'].iloc[0]), toplam_b))})")
    alt("Lumoda'nın kuralı, gönderilebilir üst sınır U, aday kümesi")
    k = v.kural
    if k is None:
        raise Eksik("lumoda / pay_esit (kural)")
    print(f"  ilk alım (dünyanın açık alanı, kuralın girdisi): {s(k['ilk_alim'])} adet; paket adedi {', '.join(s(x) for x in k['paket_adedi'])}")
    print(f"  kural: toplam paket = ⌊ilk alım × {s(sabitler.LUMODA_ILK_PAYI, 2)} ÷ paket adedi⌋ → {s(k['kural_paket'])} paket "
          f"({s(k['kural_adet'])} adet; ilk alımın {y(bolum(k['kural_adet'], k['ilk_alim']))})")
    print(f"  U = min(kural, depodaki en dar bedenin paket sayısı): {s(k['U_paket'])} paket ({s(k['U_adet'])} adet); "
          f"U'nun kuraldan küçük olduğu option {s(k['U_baglayan'])} / {s(k['option'])} (kalite reddi depoyu azaltır)")
    print(f"  aday kümesi (Lumoda'nın aday maskesi; eşit kolun kaydı): {s(k['aday_hucre'])} (option, mağaza) hücresi; "
          f"option başına ortalama {s(k['aday_magaza_ort'], 1)} mağaza (en az {s(k['aday_magaza_min'])}, en çok "
          f"{s(k['aday_magaza_max'])})")
    print(f"  karar: {s(k['option'])} option × ortalama {s(k['aday_magaza_ort'], 1)} mağaza × beden = {s(k['aday_sku_hucre'])} "
          f"(mağaza, SKU) adedi; satış görülmeden, dalga başına tek karar")
    lo = O(v, "lumoda")
    ek += [("VERİ: yayımlanan ilk dağıtım (fiziksel) = lumoda koşusunun ilk dağıtımı",
            top["ilk_dagitim"] == int(lo["ilk_dagitim_adet"])),
           ("VERİ: dalgaların option toplamı = kuralın option sayısı", top["option"] == k["option"]),
           ("VERİ: Lumoda'nın gönderdiği = kural − motorun kırptığı", k["kural_adet"] - k["kirpilan_adet"]
            == int(lo["ilk_dagitim_adet"])),
           ("VERİ: U kuralı aşmaz", k["U_kural_ustu"] == 0),
           ("VERİ: Lumoda'nın gönderdiği = U (t = 0)", int(lo["ilk_dagitim_adet"]) == k["U_adet"])]


def kural_bolumu(v, ek) -> None:
    h, k = v.hucreler, v.kural
    if h is None or k is None:
        raise Eksik("lumoda (kural hücreleri)")
    lo = O(v, "lumoda")
    print("Lumoda'nın ilk dağıtımı: option'ın toplam paketi aday mağazalara, mağazanın planındaki (sezon × üst kategori)")
    print("satış hedefi payıyla, en büyük kalanla. Kapsama tavanı ve en az gösterim yok. Hücre = (option, fiziksel mağaza),")
    print("ilk adet mağazaya varan ilk dağıtım; satışlar varıştan itibaren pozitif satış satırları (hikâye seçimiyle aynı tanım).")
    n = len(h)
    otur = int((h["satis_28"] < 0.20 * h["adet"]).sum())
    hizli = int((h["satis_14"] >= 0.80 * h["adet"]).sum())
    print(f"  ilk dağıtım alan hücre {s(n)} · option başına ortalama {s(n / h['option_id'].nunique(), 1)} mağaza")
    print(f"  oturan (28 günde ilk adedin < %20'si): {s(otur)} ({y(bolum(otur, n))}) · hızlı biten (14 günde ≥ %80): "
          f"{s(hizli)} ({y(bolum(hizli, n))})")
    r = float(np.corrcoef(h["adet"], h["satis_28"])[0, 1])
    print(f"  ilk adet ile 28 günlük satışın korelasyonu (hücreler): {s(r, 2)}")
    en = h.groupby("option_id")["adet"].transform("max") == h["adet"]
    tepe = h[en].drop_duplicates("option_id")
    pay = tepe["adet"] / tepe["toplam"]
    print(f"  option'ın en büyük hücresinin payı: medyan {y(pay.median())}, en yüksek {y(pay.max())}; eşit pay (1 ÷ mağaza "
          f"sayısı) medyanı {y((1 / tepe['magaza_sayisi']).median())}")
    i = int(h["adet"].to_numpy().argmax())
    r0 = h.iloc[i]
    print(f"  en büyük hücre: {r0['option_id']} {r0['ad']} → {r0['magaza']} ({r0['magaza_id']}) {s(r0['adet'])} adet "
          f"(option'daki payı {y(r0['adet'] / r0['toplam'])}); 28 günde {s(r0['satis_28'])} satış ({y(bolum(r0['satis_28'], r0['adet']))})")
    tasan = tepe[tepe["satis_28"] <= 0.10 * tepe["adet"]]
    print(f"  en büyük payı alıp 28 günde ≤ %10 satan hücre: {s(len(tasan))} option'da (Veli'nin bölgesinde "
          f"{s(int(tasan['veli'].sum()))}); plan sırası 1–3 olanı {s(int(((tasan['plan_sirasi'] >= 1) & (tasan['plan_sirasi'] <= 3)).sum()))}")
    alt("motorun Lumoda'yı kırpması (paketler depodaki SKU'lara sığdırılır; kalite reddi)")
    print(f"  kırpılan option {s(k['kirpilan_option'])} / {s(k['option'])} · (option, mağaza) {s(k['kirpilan_hucre'])} · "
          f"{s(k['kirpilan_paket'])} paket · {s(k['kirpilan_adet'])} adet (gönderilenin {y(bolum(k['kirpilan_adet'], lo['ilk_dagitim_adet']))})")
    print("  kollar kendilerini U'ya sığdırır: motor kollarda kırpmaz (her kol koşusunda korunum)")
    ek += [("KURAL: hücre sayısı = lumoda ilk_hucre", n == int(lo["ilk_hucre"])),
           ("KURAL: oturan = lumoda oturan_hucre", otur == int(lo["oturan_hucre"])),
           ("KURAL: hızlı biten = lumoda hizli_biten_hucre", hizli == int(lo["hizli_biten_hucre"])),
           ("KURAL: kırpılan adet = lumoda kirpilan_adet", k["kirpilan_adet"] == int(lo["kirpilan_adet"]))]


def kalibrasyon_bolumu(v, ek) -> None:
    k = v.kal
    print(f"Sezon {k['sezon']} (kapanmış, sızıntısız): karar günü {k['karar_gunu']}; öğrenme yalnız o gün kapanmış "
          f"sezonlardan. Ölçü pay WAPE'si: option başına Σ|pay − gerçek pay| ÷ 2 (gerçek pay sansür düzeltmeli ilk 6 hafta")
    print("talebi), ilk alımla ağırlıklı; 0 = aynı paylar, 1 = ayrık.")
    t = pd.DataFrame(k["cevrimdisi"])
    alt("koşusuz seçim")
    for _, r in t[t["asama"] == "taban"].iterrows():
        print(f"  {r['aday']:<10} WAPE {s(r['wape'], 3)} ({s(r['n_option'])} option)")
    bz = t[t["asama"] == "benzer"]
    print("  benzer (en az örnek eşiği): " + " · ".join(f"{s(r['en_az'])} → {s(r['wape'], 3)}" for _, r in bz.iterrows()))
    print(f"  seçilen en_az {s(k['en_az'])}; ızgara ucunda: {', '.join(k.get('izgara_ucunda') or []) or 'yok'} "
          f"(kenarda kalan seçim; Ruling R25)")
    print("  benzer hiyerarşisi: " + " → ".join(" × ".join(d) if d else "genel" for d in k["hiyerarsi"]))
    tm = t[t["asama"] == "tahmin"].sort_values("wape", kind="stable")
    for _, r in tm.head(4).iterrows():
        print(f"  tahmin num_leaves {s(r['num_leaves'])} × min_child_samples {s(r['min_child_samples'])}: WAPE {s(r['wape'], 3)}"
              f"{' (seçilen)' if r['secildi'] else ''}")
    tp = k["tahmin_parametreleri"]
    print(f"  LightGBM (Poisson): {s(tp['num_leaves'])} yaprak, {s(tp['n_estimators'])} ağaç, öğrenme oranı "
          f"{s(tp['learning_rate'], 2)}, yaprakta en az {s(tp['min_child_samples'])} örnek; kaynak (WAPE'si küçük): {k['kaynak']}")
    bl = t[t["asama"] == "belirsizlik"]
    print("  belirsizlik ölçüsünün kaynak WAPE'siyle Spearman'ı: " + " · ".join(
        f"{r['aday']} {s(r['spearman'], 3) if not _yok(r['spearman']) else 'tanımsız'}" for _, r in bl.iterrows())
          + f"; seçilen {k['belirsizlik_olcusu']}")
    alt("simülasyon (kalibrasyon sezonu, yol 0; bulunabilirlik / sezon sonu kalan)")
    sm = pd.DataFrame(k["simulasyon"])
    for _, r in sm.iterrows():
        aralik = "" if _yok(r.get("t_en_az")) else f" · t {s(r['t_en_az'], 2)}–{s(r['t_en_cok'], 2)}"
        print(f"  {r['ad']:<24} {yd(r['bulunabilirlik'], 2)} / {yd(r['sezon_sonu_kalan_yuzde'], 2)}{aralik}"
              f"{' (seçilen)' if r['secildi'] else ''}")
    by = {r["ad"]: r for _, r in sm.iterrows()}
    for kol in ("benzer", "tahmin"):
        a, c = by.get(f"kal_{kol}_tavansiz"), by.get(f"kal_{kol}_tavanli")
        if a is not None and c is not None:
            print(f"  {kol}: tavanlı − tavansız bulunabilirlik {isaretli(fark(a['bulunabilirlik'], c['bulunabilirlik'], 2), 2)} puan, "
                  f"kalan {isaretli(fark(a['sezon_sonu_kalan_yuzde'], c['sezon_sonu_kalan_yuzde'], 2), 2)} puan")
    print(f"  seçim: tavan {'açık' if k['tavan'] else 'kapalı'}, belirsizliğin tabanı {k['belirsizlik_taban']}, γ "
          f"{s(k['gamma'], 1)} (γ'ların bulunabilirlik aralığı {s(k['gamma_bulunabilirlik_araligi_puan'], 2)} puan < eşik "
          f"{s(k['gamma_esik_puan'], 1)}; sezon sonu kalanla seçildi, kalan aralığı {s(k['gamma_kalan_araligi_puan'], 2)} puan)")
    print(f"  oyunda kullanılan γ {s(v.oyun.get('belirsizlik_gamma'), 1)} (ölçünün Spearman'ı ≤ 0 ise 0: sabit tutma)")


def yol0_bolumu(v, ek) -> None:
    print("Her koşunun bütün ölçütleri (yol 0 = yayımlanan dünyanın müşteri akışı; oyun sezonunun Collection option'ları,")
    print("fiziksel mağazalar, ilk dağıtım varışından çıkışa; para ve online ayrı). Aynı koşu iki adla ölçülmüşse ikinci ad")
    print("tabana gösterilir (Ruling R30).")
    grup = None
    for ad, e in v.oyun["kosular"].items():
        if e.get("grup") != grup:
            grup = e.get("grup")
            alt(f"grup: {grup}")
        if "ayni" in e:
            print(f"  {ad} = {e['ayni']} (aynı koşu)  [{kol_metni(e)}]")
            continue
        if ad not in v.gecerli:
            print(f"  {ad}  [eksik: önbellekte geçerli değil]")
            continue
        o = e["olcutler"]
        print(f"  {ad}  [{kol_metni(e)}]")
        parca = [f"{a}={b(a, o[a])}" for a in OLCUT_SIRASI if a in o] + [
            f"{a}={s(o[a], 2)}" for a in o if a not in BICIM]
        for i in range(0, len(parca), 6):
            print("    " + " · ".join(parca[i:i + 6]))
        ek.append((f"{ad}: satış ≤ talep", o["satis_adet"] <= o["talep_adet"]))
        if e.get("cozum", {}).get("kol") != "lumoda":
            ek.append((f"{ad}: motor kolu kırpmadı", o["kirpilan_adet"] == 0))
        if e.get("cozum", {}).get("kol") not in ("lumoda", "belirsizlik") and e.get("cozum", {}).get("tutma") == 0.0 \
                and v.kural is not None:
            ek.append((f"{ad}: t = 0'da ilk dağıtım + tavanın bıraktığı = U", int(o["ilk_dagitim_adet"] + o["tavan_kalan_adet"])
                       == v.kural["U_adet"]))
    pk = pay_kollari(v)
    alt("pay bloğu (t = 0: herkes Lumoda'nın gönderdiği kadar; tepkili RPT ve markdown)")
    kollar = pay_satirlari(v)
    if not kahin_olculur(v):
        print("  kahin: ölçülemedi (erken talebin bağımsızlığı tutmadı)")
    _kiyas_tablosu(v, kollar)
    print("  mal akışı (adet): ilk dağıtım, RPT, toplam mal (ilk alım + RPT − kalite reddi), oyun option'larının")
    print("  replenishment'ı, sezon sonu kalan (mağaza / depo), online satış")
    _mal_tablosu(v, kollar)
    print("  online (aynı depodan satar): " + " · ".join(
        f"{et} {s(O(v, ad)['online_satis'])} adet, brüt kâr {tl(O(v, ad)['brut_kar_tl_online'])}" for et, ad in kollar))
    for et, ad in kollar[1:]:
        print(f"  {et} − lumoda: {_fark_satiri(v, 'lumoda', ad)}")
    alt("pay bloğunun en iyisi (secim.json; Ruling R43: tavansız benzer ve tahmin arasından; SS25'te ölçülür, örneklem içi)")
    sc = v.secim or {}
    if sc:
        print(f"  kural: {sc.get('kural')} (eşik {s(sc.get('esik_puan'), 1)} puan)")
        for a in sc.get("adaylar", []):
            print(f"  aday {a['ad']}: bulunabilirlik {yd(a['bulunabilirlik'], 2)} · kalan {yd(a['sezon_sonu_kalan_yuzde'], 2)}")
        print(f"  en iyi: {sc.get('ad')} ({sc.get('kol')})")
    print("  not: markdown_tl brüt indirim tutarıdır, brüt kâr net satış − alış maliyetidir; ikisi toplanmaz")

    lu, es = O(v, "lumoda"), O(v, "pay_esit")
    soru(1, "Lumoda'nın plan payı eşit dağıtımdan iyi mi (aynı mal, t = 0)? Lumoda / eşit (plan payının yönü): bulunabilirlik "
         f"{yd(lu['bulunabilirlik'], 1)} / {yd(es['bulunabilirlik'], 1)} ({isaretli(fark1(es['bulunabilirlik'], lu['bulunabilirlik']), 1)} puan, "
         f"{yon(lu['bulunabilirlik'], es['bulunabilirlik'], True, 1)}) · sezon sonu kalan {yd(lu['sezon_sonu_kalan_yuzde'], 1)} / "
         f"{yd(es['sezon_sonu_kalan_yuzde'], 1)} ({yon(lu['sezon_sonu_kalan_yuzde'], es['sezon_sonu_kalan_yuzde'], False, 1)}) · tam fiyat STR "
         f"{yd(lu['tam_fiyat_str'], 1)} / {yd(es['tam_fiyat_str'], 1)} ({yon(lu['tam_fiyat_str'], es['tam_fiyat_str'], True, 1)}) · brüt kâr "
         f"{tl(lu['brut_kar_tl'])} / {tl(es['brut_kar_tl'])} ({yon(lu['brut_kar_tl'], es['brut_kar_tl'], True, 0)}) · pay WAPE "
         f"{s(lu['pay_wape'], 3)} / {s(es['pay_wape'], 3)} ({yon(lu['pay_wape'], es['pay_wape'], False, 3)})")
    soru2 = []
    kahin = kahin_olculur(v)
    for et, ad in (("benzer", pk["benzer"]), ("tahmin", pk["tahmin"])):
        o = O(v, ad)
        parca = (f"{et} {yd(o['bulunabilirlik'], 1)} ({isaretli(fark1(lu['bulunabilirlik'], o['bulunabilirlik']), 1)} puan), "
                 f"WAPE {s(o['pay_wape'], 3)}")
        if kahin:
            kh = O(v, "pay_kahin")
            kp = kapanan_pay(o["bulunabilirlik"], lu["bulunabilirlik"], kh["bulunabilirlik"], 2)
            kw = kapanan_pay(o["pay_wape"], lu["pay_wape"], kh["pay_wape"], 3)
            parca += (f", kahinle Lumoda arasındaki farktan kapanan: bulunabilirlik {y(kp, 0) if kp is not None else '—'}, "
                      f"WAPE {y(kw, 0) if kw is not None else '—'}")
        soru2.append(parca)
    if kahin:
        kh = O(v, "pay_kahin")
        kahin_m = (f"kahin {yd(kh['bulunabilirlik'], 1)} ({isaretli(fark1(lu['bulunabilirlik'], kh['bulunabilirlik']), 1)} puan), "
                   f"WAPE {s(kh['pay_wape'], 3)}")
    else:
        kahin_m = "kahin ölçülemedi (erken talebin bağımsızlığı tutmadı)"
    soru(2, f"Benzer ürün ve LightGBM plan payını ne kadar geçer, kahin farkının ne kadarını kapatır? Lumoda "
         f"{yd(lu['bulunabilirlik'], 1)}, WAPE {s(lu['pay_wape'], 3)} · " + " · ".join(soru2) + f" · {kahin_m}. Hepsi aynı malı "
         "gönderir (t = 0, tavansız); tavanlı kollar TAVAN'da")


def yollar_bolumu(v, ek) -> None:
    yl = v.yollar
    if not yl:
        raise Eksik("yollar.json")
    yollar = yl["yollar"]
    p_sira = sorted(yollar, key=int)
    kollar = yl.get("kollar", list(oyun.YOL_KOLLARI))
    eksik = [f"yol {p} {k}" for p in p_sira for k in kollar if (p, k) not in v.yol_gecerli]
    if eksik:
        raise Eksik(*eksik)
    print(f"{s(len(p_sira))} talep yolu: yol 0 yayımlanan dünya, yol p > 0 aynı dünyada başka bir müşteri akışı (talep tohumu "
          f"{yl['taban']} + p). Yalnız Poisson ve ikame çekilişleri değişir; ürün sürprizleri (λ) sabittir (spec §0/13):")
    print("dayanıklılık örnekleme gürültüsünedir, farklı ürün başarılarına değil. Her yolda benzer endeksi ve LightGBM o yolun")
    print("Lumoda geçmişinden yeniden öğrenilir, kahin o yolun Lumoda gizli gerçeğinden; kalibrasyon yol 0'ınki.")
    print("Kollar aynı malı gönderir (t = 0; benzer ve tahmin tavansız, Ruling R44).")
    for p in p_sira:
        g = yollar[p].get("girdi", {})
        lo = yollar[p]["kosular"]["lumoda"]["olcutler"]
        print(f"  yol {p}: talep tohumu {yollar[p]['talep_tohumu'] if yollar[p]['talep_tohumu'] is not None else 'yayımlanan'} · "
              f"Lumoda koşusunun talebi (oyun hücreleri) {s(lo['talep_adet'])} adet · öğrenme satırı {s(g.get('ogrenme_satir'))} · "
              f"karar günü {g.get('karar_gunu', '—')}")
    tohum = [yollar[p]["talep_tohumu"] for p in p_sira]
    ek += [("yollar: talep tohumları farklı", len(set(map(str, tohum))) == len(p_sira)),
           ("yollar: Lumoda koşularının talebi yoldan yola farklı",
            len({yollar[p]["kosular"]["lumoda"]["olcutler"]["talep_adet"] for p in p_sira}) == len(p_sira)),
           ("yollar: her yolun öğrenilmiş girdileri o yolun Lumoda koşusundan (yol 0 yayımlanan)",
            all(yollar[p].get("girdi", {}).get("kaynak") == ("yayimlanan" if int(p) == 0 else yollar[p]["kosular"]["lumoda"]["anahtar"])
                for p in p_sira)),
           ("yollar: benzer endeksi ve LightGBM yoldan yola farklı",
            len({yollar[p].get("girdi", {}).get("endeks") for p in p_sira}) == len(p_sira)
            and len({yollar[p].get("girdi", {}).get("tahminci") for p in p_sira}) == len(p_sira))]
    yb = v.yol_bagimsizlik or {}
    print("  kahinin bağımsızlığı (y<p>_kahin ↔ y<p>_lumoda erken birincil talep): " + " · ".join(
        f"yol {p} {'tutuyor' if yb.get(p) else 'tutmuyor'}" for p in p_sira if int(p) > 0))
    olcutler = (("bulunabilirlik", 2), ("sezon_sonu_kalan_yuzde", 2), ("kayip_orani", 2), ("tam_fiyat_str", 2),
                ("pay_wape", 3), ("brut_kar_tl", 0), ("markdown_tl", 0))
    deger = {(k, olc): [yollar[p]["kosular"][k]["olcutler"][olc] for p in p_sira] for k in kollar for olc, _ in olcutler}
    for olc, n in olcutler:
        alt(f"{olc} (yol {' · '.join(p_sira)}; min / medyan / max basılan değerlerden)")
        for k in kollar:
            if k == "kahin" and not all(yb.get(p) for p in p_sira if int(p) > 0):
                print(f"  {k:<8} ölçülemedi (bir yolda bağımsızlık tutmadı)")
                continue
            yv = [yuv(x, n) for x in deger[(k, olc)]]
            print(f"  {k:<8}" + " · ".join(s(x, n) for x in yv) +
                  f"  | min {s(min(yv), n)} · medyan {s(statistics.median(yv), n)} · max {s(max(yv), n)}")
    alt(f"kaç yolda önde (k/{s(len(p_sira))}: bulunabilirlik, STR, brüt kâr yüksek; kalan, kayıp, WAPE, markdown düşük olan "
        "önde; basılan değerlerden)")
    ciftler = [(a, c) for i, a in enumerate(kollar) for c in kollar[:i]]
    for a, c in ciftler:
        if "kahin" in (a, c) and not all(yb.get(p) for p in p_sira if int(p) > 0):
            continue
        parca = []
        for olc, n in olcutler:
            if olc not in YUKSEK_IYI:
                continue
            f = yol_farklari(deger[(a, olc)], deger[(c, olc)], n)
            onde = f["pozitif"] if YUKSEK_IYI[olc] else f["negatif"]
            parca.append(f"{olc} {onde}/{f['n']} yolda önde (medyan fark {isaretli(f['medyan'], n)})")
        print(f"  {a} − {c}: " + " · ".join(parca))
    alt("bulunabilirlik farkı, bir ondalık (iki ondalıklı farkların ve medyanın yuvarlaması: tek nicelik, tek değer)")
    for a, c in ciftler:
        if "kahin" in (a, c) and not all(yb.get(p) for p in p_sira if int(p) > 0):
            continue
        f = yol_farklari(deger[(a, "bulunabilirlik")], deger[(c, "bulunabilirlik")], 2)
        print(f"  {a} − {c}: " + " · ".join(isaretli(tek_ondalik(x), 1) for x in f["farklar"])
              + f" | medyan {isaretli(tek_ondalik(f['medyan']), 1)} · {a} önde {f['pozitif']}/{f['n']}, geride {f['negatif']}/{f['n']}")
    k0 = yollar["0"]["kosular"] if "0" in yollar else {}
    for kisa, e in k0.items():
        ek.append((f"yollar: yol 0 {kisa} = oyun.json ({e.get('ad')})",
                   e.get("ad") in v.oyun["kosular"] and e["anahtar"] == v.oyun["kosular"][e["ad"]]["anahtar"]))
    ek += [(f"yollar: yol {p} {k_} tavansız (R44)", yollar[p]["kosular"][k_].get("cozum", {}).get("tavan") is False)
           for p in p_sira for k_ in ("benzer", "tahmin")]
    ek += [("yollar: hepsi tamam", all(yollar[p].get("tamam") for p in p_sira)),
           ("yollar: 5 yol", len(p_sira) == sabitler.YOL_SAYISI),
           ("yollar: kayıt bugünkü kodla (yollar.kod_ozeti)", all(yollar[p].get("kod") == v.yollar_kodu for p in p_sira))]


TAVAN_OLCUTLER = (("ilk_dagitim_adet", "ilk dağıtım", 0), ("bulunabilirlik", "bulun.", 2),
                  ("bulunabilirlik_ilk4", "ilk 4 hf", 2), ("kayip_orani", "kayıp", 2), ("sezon_sonu_kalan_yuzde", "kalan", 2),
                  ("tam_fiyat_str", "tam STR", 2), ("markdown_tl", "markdown TL", 0), ("brut_kar_tl", "brüt kâr TL", 0),
                  ("pay_wape", "WAPE", 3), ("replenishment_adet", "repl.", 0))


def ayrisim(parca: list[tuple[str, float]], ek_metin: str = "") -> str:
    """"toplam +0,95 = biçim −0,18 + tutma +1,13 (bir ondalıkla +1,0 / −0,2 / +1,1)": iki ondalıklı ayrışım (toplanır)
    ve her parçanın bir ondalıklı biçimi, iki ondalıklının bir kez yuvarlanmışı (R53; bir ondalıkta toplam tutmayabilir)."""
    (et0, x0), *kalan = parca
    govde = f"{et0} {isaretli(x0, 2)} = " + " + ".join(f"{et} {isaretli(x, 2)}" for et, x in kalan)
    return govde + f" (bir ondalıkla {' / '.join(isaretli(tek_ondalik(x), 1) for _, x in parca)}{ek_metin})"


def _satir(etiket: str, o: dict, olcutler) -> str:
    return f"  {etiket:<28}" + "".join(f"{(yd(o[m], n) if BICIM[m][0] == 'y' else s(o[m], n)):>14}" for m, _, n in olcutler)


def tavan_bolumu(v, ek) -> None:
    print("Kapsama tavanı (yalnız benzer ve tahmin): mağazaya en çok öngörülen ilk 6 haftalık talep kadar (paket yukarı")
    print("yuvarlanır, en az 1); tavan bağlarsa artan paket öteki mağazalara, herkes tavandaysa kalan depoda kalır. Tavanlı kol")
    print("U'nun bir kısmını depoda bırakır, yani örtük bir tutma kolu olur. Ayrışım (Ruling R43): eşleşik koşu (es_<kol>) aynı")
    print("kolun tavansız hâlidir, t = tavanlı koşunun depoda bıraktığı pay; tavanlı − eşleşik = tavanın dağıtım biçimi (aynı")
    print("toplam mal; malı hangi mağazaya gönderdiği ve hangi option'da daha çok tuttuğu: eşleşik her option'da aynı t'yi")
    print("tutar), eşleşik − tavansız t 0 = depoda tutmanın etkisi. Farklar basılan değerlerden; bir ondalıklı biçim iki")
    print("ondalıklı farkın bir kez yuvarlanmışıdır (Ruling R53).")
    es_t = v.oyun.get("eslesik_tutma") or {}
    sat = []
    for kol in ("benzer", "tahmin"):
        a, e_, c = f"pay_{kol}_tavansiz", f"es_{kol}", f"pay_{kol}_tavanli"
        oa, oe, oc = O(v, a), O(v, e_), O(v, c)
        et = es_t.get(e_)
        if et is None:
            raise Eksik(f"oyun.json eslesik_tutma.{e_}")
        alt(f"{kol}: tavansız t 0 · eşleşik t {s(et['tutma'], 3)} · tavanlı")
        print(f"  eşleşik t = 1 − tavanlının gönderdiği ÷ U = 1 − {s(et['giden_adet'])} ÷ {s(et['U_adet'])} = {s(et['ham'], 4)} "
              f"(0,001'e yuvarlanır)")
        print(f"  {'koşu':<28}" + "".join(f"{bas:>14}" for _, bas, _ in TAVAN_OLCUTLER))
        for etk, o in (("tavansız t 0", oa), (f"eşleşik ({e_})", oe), ("tavanlı", oc)):
            print(_satir(etk, o, TAVAN_OLCUTLER))
        for etk, x, z in (("tavanlı − eşleşik (biçim)", e_, c), ("eşleşik − tavansız (tutma)", a, e_),
                          ("tavanlı − tavansız (toplam)", a, c)):
            print(f"  {etk}: " + " · ".join(f"{bas} {isaretli(fark(O(v, x)[m], O(v, z)[m], n), n)}"
                                           for m, bas, n in TAVAN_OLCUTLER))
        print(f"  tavanlı: tavanda mağaza {s(oc['tavan_baglayan'])} (option × mağaza), depoda bıraktığı {s(oc['tavan_kalan_adet'])} "
              f"adet; eşleşiğin ilk dağıtımı tavanlınınkinden {isaretli(fark(oc['ilk_dagitim_adet'], oe['ilk_dagitim_adet']))} adet "
              "(paket tabanı ve t'nin yuvarlaması)")
        ek += [(f"TAVAN: {e_} t'si kaynak tavanlı koşunun ({c}) kaydından",
                et.get("kaynak") == c and et.get("anahtar") == K(v, c)["anahtar"]
                and int(et["giden_adet"]) == int(oc["ilk_dagitim_adet"])),
               (f"TAVAN: {e_} ilk dağıtımı tavanlınınkinin U'ya göre %0,5 yakınında (aynı mal)",
                abs(oe["ilk_dagitim_adet"] - oc["ilk_dagitim_adet"]) <= 0.005 * et["U_adet"]),
               (f"TAVAN: {e_} U'su tavansız kolunki", int(et["U_adet"]) == int(oa["ilk_dagitim_adet"] + oa["tavan_kalan_adet"]))]
        sat.append(f"{kol} (depoda kalan U'ya oranı {y(et['tutma'], 1)}): " + "; ".join(
            f"{et_m} " + ayrisim([("toplam", fark(oa[m], oc[m], 2)), ("biçim", fark(oe[m], oc[m], 2)),
                                   ("tutma", fark(oa[m], oe[m], 2))])
            for m, et_m in (("bulunabilirlik", "bulunabilirlik"), ("sezon_sonu_kalan_yuzde", "kalan"))))
    sm = {r_["ad"]: r_ for r_ in v.kal.get("simulasyon", [])}
    kal = []
    for kol in ("benzer", "tahmin"):
        a, c = sm.get(f"kal_{kol}_tavansiz"), sm.get(f"kal_{kol}_tavanli")
        if a and c:
            kal.append(f"{kol} {isaretli(fark1(a['bulunabilirlik'], c['bulunabilirlik']), 1)}")
    soru(3, "Kapsama tavanı tek başına ne kazandırır? Tavanlı − tavansız, eşleşik tutmayla ayrışmış (SS25, yol 0; puan): "
         + " · ".join(sat) + (f"; kalibrasyon sezonunda tavanlı − tavansız bulunabilirlik {', '.join(kal)} puan (ayrışmamış)"
                              if kal else ""))

SABIT_KOLLAR = (("lumoda", "lumoda_takvimli"), ("esit", "sabit_esit"), ("benzer", "sabit_benzer"),
                ("tahmin", "sabit_tahmin"), ("kahin", "sabit_kahin"))
SABIT_OLCUTLER = (("bulunabilirlik", 2), ("sezon_sonu_kalan_yuzde", 2), ("tam_fiyat_str", 2), ("kayip_orani", 2),
                  ("markdown_tl", 0), ("brut_kar_tl", 0))


def sabit_takvim_bolumu(v, ek) -> None:
    print("Sabit takvim: lumoda koşusunun RPT siparişleri ve markdown oranları oyun option'larında aynen yeniden oynatılır;")
    print("öteki option'lar Lumoda. Kolların ilk dağıtımı aynı; RPT ve markdown dağıtıma tepki vermez, toplam mal aynıdır.")
    print("Ayrışım (basılan değerlerden): toplam fark = tepkili kol − lumoda; doğrudan = sabit kol − lumoda_takvimli;")
    print("tepki = toplam − doğrudan (RPT ve markdown'ın dağıtıma tepkisinin payı). Benzer ve tahmin tavansız (Ruling R46):")
    print("bütün kollar aynı malı gönderir; tepkili karşılık aynı kol ve aynı tavanla (`pay_karsiligi`).")
    lu, lt = O(v, "lumoda"), O(v, "lumoda_takvimli")
    ayni = all(abs(float(lu[a]) - float(lt[a])) < 1e-9 for a in lu)
    ek += [(f"SABİT TAKVİM: {a} tavansız (R46)", K(v, a)["cozum"].get("tavan") is False) for a in ("sabit_benzer", "sabit_tahmin")]
    print(f"  lumoda_takvimli = lumoda (bütün ölçütler, yeniden oynatma eşdeğerliği): {'evet' if ayni else 'hayır'}")
    ek.append(("SABİT TAKVİM: lumoda_takvimli bütün ölçütlerde lumoda", ayni and set(lu) == set(lt)))
    satirlar = []
    for kol, sabit in SABIT_KOLLAR:
        tepkili = pay_karsiligi(v, sabit)
        if kol == "kahin" and not (kahin_olculur(v, "pay_kahin") and kahin_olculur(v, "sabit_kahin")):
            print("  kahin: ölçülemedi (erken talebin bağımsızlığı tutmadı)")
            continue
        satirlar.append((kol, sabit, tepkili))
    _mal_tablosu(v, [(f"{sb}", sb) for _, sb, _ in satirlar])
    _kiyas_tablosu(v, [(f"{sb}", sb) for _, sb, _ in satirlar])
    oz = []
    for kol, sabit, tepkili in satirlar:
        os_, ot = O(v, sabit), O(v, tepkili)
        ek += [(f"SABİT TAKVİM: {sabit} RPT adedi = lumoda'nınki", int(os_["rpt_adet"]) == int(lu["rpt_adet"])),
               (f"SABİT TAKVİM: {sabit} toplam mal = lumoda'nınki", int(os_["toplam_mal"]) == int(lu["toplam_mal"]))]
        if kol == "lumoda":
            continue
        print(f"  {kol} ({tepkili} ↔ {sabit}):")
        for m, n in SABIT_OLCUTLER:
            top = fark(lu[m], ot[m], n)
            dog = fark(lt[m], os_[m], n)
            tep = yuv(top - dog, n)
            pay = bolum(dog, top, n, n)
            print(f"    {m:<24} toplam {isaretli(top, n)} = doğrudan {isaretli(dog, n)} + tepki {isaretli(tep, n)}"
                  f"{'' if pay is None else f' (doğrudan payı {y(pay, 0)})'}")
        top = fark(lu["bulunabilirlik"], ot["bulunabilirlik"], 2)
        dog = fark(lt["bulunabilirlik"], os_["bulunabilirlik"], 2)
        pay = bolum(dog, top, 2, 2)                     # tablodaki "doğrudan payı" ile aynı hesap
        oz.append(f"{kol}{' tavanlı' if tepkili.endswith('_tavanli') else ''} " + ayrisim(
            [("toplam", top), ("doğrudan", dog), ("tepki", yuv(top - dog, 2))],
            "" if pay is None else f"; doğrudan payı {y(pay, 0)}"))
    soru(8, "Kolların farkının ne kadarı dağıtımın kendisinden, ne kadarı RPT ve markdown'ın tepkisinden? Bulunabilirlik farkı "
         "(puan, kol − Lumoda): " + " · ".join(oz))


def _tut_adi(kaynak: str, t: float, repl: str) -> str:
    return f"tut_{kaynak}_t{round(t * 100):02d}{'_hiz' if repl == 'hiz' else ''}"


TUT_OLCUTLER = (("ilk_dagitim_adet", "ilk dağıtım", 0), ("bulunabilirlik", "bulun.", 2), ("bulunabilirlik_ilk4", "ilk 4 hf", 2),
                ("kayip_orani", "kayıp", 2), ("sezon_sonu_kalan_yuzde", "kalan", 2), ("tam_fiyat_str", "tam STR", 2),
                ("markdown_tl", "markdown TL", 0), ("replenishment_adet", "repl.", 0), ("online_satis", "online", 0),
                ("brut_kar_tl", "brüt kâr TL", 0))


def tutma_bolumu(v, ek) -> None:
    print("Tutma oranı t gönderilebilir üst sınır U'ya göre (spec §0/9): kol ⌊U × (1 − t)⌋ paket gönderir, kalanı depoda kalır;")
    print("t = 0 Lumoda'nın gönderdiği kadardır (Lumoda'nın %30'u ilk alıma göredir, Ruling R27). Pay kaynağı: Lumoda'nın planı")
    print(f"(lumoda_tut) ve pay bloğunun tavansız en iyisi ({secim_adi(v)}; R43, SS25'te seçildi: örneklem içi ölçüm).")
    print("Replenishment: Lumoda'nın kuralı (ölü stok kapısıyla) ya da hiz (son 14 günün stoklu gün hızı × 28 gün, kapısız; yalnız oyun hücreleri).")
    print("Online aynı depodan satar: tutma online satışını da değiştirir (sütun).")
    lu = O(v, "lumoda")
    sec = v.secim or {}
    for t in sabitler.TUTMA_DUZEYLERI:
        for repl in ("lumoda", "hiz"):
            c = K(v, _tut_adi("eniyi", t, repl))["cozum"]
            ek.append((f"TUTMA: {_tut_adi('eniyi', t, repl)} kolu ve tavanı secim.json'un en iyisi",
                       c.get("kol") == sec.get("kol") and c.get("tavan") == sec.get("tavan")))
    sonuc = {}
    for kaynak in ("lumoda", "eniyi"):
        for repl in ("lumoda", "hiz"):
            alt(f"pay {kaynak if kaynak == 'lumoda' else 'en iyi'} · replenishment {repl}")
            print(f"  {'t':<6}" + "".join(f"{bas:>14}" for _, bas, _ in TUT_OLCUTLER))
            for t in sabitler.TUTMA_DUZEYLERI:
                o = O(v, _tut_adi(kaynak, t, repl))
                sonuc[(kaynak, repl, t)] = o
                print(f"  {yd(100 * t, 0):<6}" + "".join(
                    f"{(yd(o[m], n) if BICIM[m][0] == 'y' else s(o[m], n)):>14}" for m, _, n in TUT_OLCUTLER))
            t0 = sonuc[(kaynak, repl, 0.0)]
            for t in sabitler.TUTMA_DUZEYLERI[1:]:
                o = sonuc[(kaynak, repl, t)]
                print(f"  t {yd(100 * t, 0)} − t %0: bulunabilirlik {isaretli(fark(t0['bulunabilirlik'], o['bulunabilirlik'], 2), 2)} · "
                      f"kalan {isaretli(fark(t0['sezon_sonu_kalan_yuzde'], o['sezon_sonu_kalan_yuzde'], 2), 2)} · tam STR "
                      f"{isaretli(fark(t0['tam_fiyat_str'], o['tam_fiyat_str'], 2), 2)} · online "
                      f"{isaretli(fark(t0['online_satis'], o['online_satis']))} adet · brüt kâr {isaretli(fark(t0['brut_kar_tl'], o['brut_kar_tl']))} TL")
            for t in sabitler.TUTMA_DUZEYLERI:
                ek.append((f"TUTMA: {_tut_adi(kaynak, t, repl)} U'yu aşmaz",
                           v.kural is None or sonuc[(kaynak, repl, t)]["ilk_dagitim_adet"] <= v.kural["U_adet"]))
    alt("replenishment'a bağlılık (hiz − Lumoda, aynı t ve pay; bulunabilirlik / kalan, puan)")
    for kaynak in ("lumoda", "eniyi"):
        print(f"  {kaynak}: " + " · ".join(
            f"t {yd(100 * t, 0)} {isaretli(fark(sonuc[(kaynak, 'lumoda', t)]['bulunabilirlik'], sonuc[(kaynak, 'hiz', t)]['bulunabilirlik'], 2), 2)} / "
            f"{isaretli(fark(sonuc[(kaynak, 'lumoda', t)]['sezon_sonu_kalan_yuzde'], sonuc[(kaynak, 'hiz', t)]['sezon_sonu_kalan_yuzde'], 2), 2)}"
            for t in sabitler.TUTMA_DUZEYLERI))
    l0 = sonuc[("lumoda", "lumoda", 0.0)]
    print(f"  tut_lumoda_t00 − lumoda (Lumoda'nın U'ya sığdırılmış hâli ↔ motorun kırpması; R28): bulunabilirlik "
          f"{isaretli(fark(lu['bulunabilirlik'], l0['bulunabilirlik'], 2), 2)} · kalan "
          f"{isaretli(fark(lu['sezon_sonu_kalan_yuzde'], l0['sezon_sonu_kalan_yuzde'], 2), 2)} · ilk dağıtım "
          f"{isaretli(fark(lu['ilk_dagitim_adet'], l0['ilk_dagitim_adet']))} adet")
    parca = []
    for kaynak in ("lumoda", "eniyi"):
        for repl in ("lumoda", "hiz"):
            dz = [(t, yuv(sonuc[(kaynak, repl, t)]["bulunabilirlik"], 1)) for t in sabitler.TUTMA_DUZEYLERI]
            en_iyi_t = max(dz, key=lambda x: (x[1], -x[0]))[0]
            t0, t30 = sonuc[(kaynak, repl, 0.0)], sonuc[(kaynak, repl, 0.30)]
            parca.append(f"{'Lumoda payı' if kaynak == 'lumoda' else 'en iyi pay'} × {repl}: t %0 → %30 "
                         f"{isaretli(fark1(t0['bulunabilirlik'], t30['bulunabilirlik']), 1)} puan bulunabilirlik, "
                         f"{isaretli(fark1(t0['sezon_sonu_kalan_yuzde'], t30['sezon_sonu_kalan_yuzde']), 1)} puan kalan; "
                         f"en yüksek bulunabilirlik t {yd(100 * en_iyi_t, 0)}")
    soru(4, "Depoda tutmanın değeri nedir ve replenishment'a bağlı mı (Lumoda ↔ hiz)? " + " · ".join(parca))


def strateji_bolumu(v, ek) -> None:
    a, c = "tut_eniyi_t30", "belirsizlik"
    bilgi = v.belirsizlik_t
    print(f"Belirsizliğe göre tutma (strateji-oneri): pay tavansız en iyi koldan ({secim_adi(v)}; R43); t option başına, belirsiz")
    print("option daha çok depoda. Karşılığı aynı kolla sabit t = %30 (tut_eniyi_t30). İkisi de SS25'te ölçülür: örneklem içi.")
    print(f"t_o = clip(t̄ · (u_o / ū)^γ, 0, 2t̄), ilk alımla ağırlıklı ortalaması t̄ = {yd(100 * v.kal.get('tbar', 0.3), 0)}; "
          f"ölçü {v.kal['belirsizlik_olcusu']} (kalibrasyonda Spearman {s(v.kal.get('belirsizlik_spearman'), 3)}).")
    if bilgi:
        print(f"  oyunda γ {s(v.oyun.get('belirsizlik_gamma'), 1)} · koşunun kararlarındaki t (belirsizlik kaydı, "
              f"{s(bilgi['option'])} option): {s(bilgi['t_en_az'], 2)}–{s(bilgi['t_en_cok'], 2)} · ilk alımla ağırlıklı ortalama "
              f"{s(bilgi['t_ortalama'], 3)}")
        ek.append(("STRATEJİ: kayıttaki t_o'ların ilk alımla ağırlıklı ortalaması t̄",
                   abs(bilgi["t_ortalama"] - v.kal.get("tbar", 0.3)) < 1e-6))
        eski = (v.oyun.get("girdi") or {}).get("belirsizlik")
        if eski:
            ek.append(("STRATEJİ: kayıttaki t aralığı oyun.json girdisiyle aynı",
                       abs(eski["t_en_az"] - bilgi["t_en_az"]) < 1e-9 and abs(eski["t_en_cok"] - bilgi["t_en_cok"]) < 1e-9))
        print(f"  not: γ kalibrasyon sezonunda {v.kal.get('belirsizlik_taban')} "
              f"{'tavanlı' if v.kal.get('tavan') else 'tavansız'} tabanla seçildi; oyunda taban tavansız (R43). γ'lar arasındaki "
              f"bulunabilirlik farkı orada {s(v.kal.get('gamma_bulunabilirlik_araligi_puan'), 2)} puandı: seçim bu tabana "
              "taşınabilir sayıldı, yeniden sınanmadı")
    else:
        raise Eksik("belirsizlik (karar kaydı)")
    _kiyas_tablosu(v, [("sabit t %30", a), ("belirsizlik", c)])
    _mal_tablosu(v, [("sabit t %30", a), ("belirsizlik", c)])
    oa, oc = O(v, a), O(v, c)
    print(f"  belirsizlik − sabit: {_fark_satiri(v, a, c)}")
    soru(5, f"Belirsizliğe göre tutmak sabit tutmayı aynı malla geçer mi? İlk dağıtım {s(oc['ilk_dagitim_adet'])} / "
         f"{s(oa['ilk_dagitim_adet'])} adet; bulunabilirlik {yd(oc['bulunabilirlik'], 2)} / {yd(oa['bulunabilirlik'], 2)} "
         f"({isaretli(fark(oa['bulunabilirlik'], oc['bulunabilirlik'], 2), 2)} puan, {yon(oc['bulunabilirlik'], oa['bulunabilirlik'], True, 2)}) · "
         f"kalan {yd(oc['sezon_sonu_kalan_yuzde'], 2)} / {yd(oa['sezon_sonu_kalan_yuzde'], 2)} "
         f"({yon(oc['sezon_sonu_kalan_yuzde'], oa['sezon_sonu_kalan_yuzde'], False, 2)}) · tam STR {yd(oc['tam_fiyat_str'], 2)} / "
         f"{yd(oa['tam_fiyat_str'], 2)} ({yon(oc['tam_fiyat_str'], oa['tam_fiyat_str'], True, 2)}); {sinyal_metni(v.kal)}")


def sinyal_metni(kal: dict) -> str:
    """Belirsizlik ölçüsünün sinyali, kalibrasyon.json'un kendi eşiğiyle: γ'ların bulunabilirlik aralığı
    `gamma_esik_puan`'ın altındaysa eğrinin dikliği sonucu değiştirmedi (zayıf); Spearman yanında basılır."""
    ara, esik, rho = kal.get("gamma_bulunabilirlik_araligi_puan"), kal.get("gamma_esik_puan"), kal.get("belirsizlik_spearman")
    if ara is None or esik is None:
        return f"Spearman {s(rho, 3)}"
    zayif = yuv(ara, 2) < yuv(esik, 1)
    return (f"kalibrasyonda γ'ların bulunabilirlik aralığı {s(ara, 2)} puan {'<' if zayif else '≥'} eşik {s(esik, 1)}: "
            f"{'ölçünün sinyali zayıf' if zayif else 'eğrinin dikliği sonucu değiştirdi'} (Spearman {s(rho, 3)})")


def depoda_tutar(e: dict) -> bool:
    """Koşu U'nun bir kısmını depoda bırakır mı (çözümden): t > 0, t option başına (belirsizlik) ya da tavanlı."""
    c = e.get("cozum", {})
    return c.get("tutma") is None or bool(c.get("tutma")) or bool(c.get("tavan"))


def isabet_bolumu(v, ek) -> None:
    pk = pay_kollari(v)
    print("Dağıtım isabeti: option başına mağaza payı (ilk dağıtım adedi) ile koşunun gerçek erken penceredeki birincil talep")
    print("payı arasındaki WAPE, ilk alımla ağırlıklı. Oturan: 28 günde ilk adedin < %20'si; hızlı biten: 14 günde ≥ %80.")
    b_ = v.bagimsizlik or {}
    taban = b_.get("_taban")
    if taban:
        print(f"  erken pencere (lumoda): {s(taban[0])} talepli hücre-gün, Σ birincil talep {s(taban[1])}; bağımsızlık: " + ", ".join(
            f"{a} {'tutuyor' if ok else 'tutmuyor' if ok is False else 'açılamadı'}" for a, ok in sorted(b_.items()) if a != "_taban"))
    kollar = pay_satirlari(v)
    if not kahin_olculur(v):
        print("  kahin: ölçülemedi (erken talebin bağımsızlığı tutmadı)")
    print(f"  {'kol':<18}{'WAPE':>8}{'ilk hücre':>11}{'oturan':>9}{'oturan %':>10}{'hızlı':>8}{'hızlı %':>9}{'tavanda':>9}")
    for et, ad in kollar:
        o = O(v, ad)
        print(f"  {et:<18}{s(o['pay_wape'], 3):>8}{s(o['ilk_hucre']):>11}{s(o['oturan_hucre']):>9}"
              f"{y(bolum(o['oturan_hucre'], o['ilk_hucre'])):>10}{s(o['hizli_biten_hucre']):>8}"
              f"{y(bolum(o['hizli_biten_hucre'], o['ilk_hucre'])):>9}{s(o['tavan_baglayan']):>9}")
    t = pd.DataFrame(v.kal["cevrimdisi"])
    sec = t[t["secildi"].astype(bool) & t["asama"].isin(["benzer", "tahmin"])].set_index("asama")["wape"]
    tb = t[t["asama"] == "taban"].set_index("aday")["wape"]
    print(f"  kalibrasyon sezonunda (koşusuz, aynı WAPE tanımı): lumoda {s(tb.get('lumoda'), 3)} · eşit {s(tb.get('esit'), 3)} · "
          f"benzer {s(sec.get('benzer'), 3)} · tahmin {s(sec.get('tahmin'), 3)}")
    lu = O(v, "lumoda")
    print("  oyun sezonunda WAPE − lumoda: " + " · ".join(
        f"{et} {isaretli(fark(lu['pay_wape'], O(v, ad)['pay_wape'], 3), 3)}" for et, ad in kollar[1:]))
    print(f"  aynı malı gönderen ana kollar (R43): {pk['benzer']}, {pk['tahmin']}; tavanlılar TAVAN'da ayrışır")
    bd = v.benzer_duzey
    if bd is None:
        raise Eksik("pay_benzer_tavansiz (düzey kaydı)")
    hy = v.kal["hiyerarsi"]
    toplam = sum(bd.values())
    print(f"  benzer kolunun option başına kullandığı hiyerarşi düzeyi (pay_benzer_tavansiz kaydı, en az örnek {s(v.kal['en_az'])}): "
          + " · ".join(f"{' × '.join(d) if d else 'genel (bütün Collection)'} {s(bd.get(i, 0))}" for i, d in enumerate(hy))
          + f" (toplam {s(toplam)} option)")
    ek.append(("İSABET: benzer düzey dağılımı bütün oyun option'larını kapsar", v.kural is None or toplam == v.kural["option"]))


def beden_bolumu(v, ek) -> None:
    print("Beden uyumsuzluğu (tek paket 1-2-2-1-1, spec §0/5): kırık çift = stoklu (mağaza, option, gün) çiftlerinde çekirdek")
    print("bedenlerden (2–4) biri boş; beden kaybı payı = karşılanmayan talebin, bedeni boşken aynı çiftin başka bedeni stoklu")
    print("olduğu günlerdeki kısmı. Beden kaynaklı kayıp oranı = kayıp oranı × beden kaybı payı (puan, talebe göre).")
    kollar = pay_satirlari(v)
    print(f"  {'kol':<18}{'kırık %':>9}{'beden kaybı payı':>18}{'kayıp':>8}{'beden kaynaklı':>16}{'tükenen hücre':>15}")
    bk = {}
    for et, ad in kollar:
        o = O(v, ad)
        bk[et] = yuv(o["kayip_orani"], 2) * yuv(o["beden_kayip_payi"], 1) / 100
        print(f"  {et:<18}{yd(o['kirik_cift_pay_yuzde'], 1):>9}{yd(o['beden_kayip_payi'], 1):>18}{yd(o['kayip_orani'], 2):>8}"
              f"{s(bk[et], 2):>16}{yd(o['tukenen_hucre_yuzde'], 1):>15}")
    havuz = [a for a, e in v.oyun["kosular"].items() if "ayni" not in e and e.get("grup") in ("esdegerlik", "pay", "eslesik",
                                                                                              "tutma", "strateji")]
    if any(a not in v.gecerli for a in havuz):
        raise Eksik(*[a for a in havuz if a not in v.gecerli])
    havuz = [a for a in havuz if a != "pay_kahin" or kahin_olculur(v)]
    deg = {a: O(v, a)["beden_kayip_payi"] for a in havuz}
    tutan = [a for a in havuz if depoda_tutar(K(v, a))]
    gonderen = [a for a in havuz if a not in tutan]
    alt("beden kaybı payı: her şeyi gönderen ↔ depoda tutan koşular (t > 0, t option başına ya da tavanlı; çözümden)")
    for et, grup in (("her şeyi gönderen", gonderen), ("depoda tutan", tutan)):
        print(f"  {et} ({s(len(grup))} koşu): " + " · ".join(f"{a} {yd(deg[a], 1)}" for a in grup))
    en_az = min(havuz, key=lambda a: (yuv(deg[a], 1), a))
    en_cok = max(havuz, key=lambda a: (yuv(deg[a], 1), a))
    etiket = lambda a: "depoda tutan" if a in tutan else "her şeyi gönderen"  # noqa: E731
    aralik = lambda g: f"{yd(min(deg[a] for a in g), 1)}–{yd(max(deg[a] for a in g), 1)}" if g else "—"  # noqa: E731
    soru(6, f"Beden uyumsuzluğu kaybın ne kadarı, hangi kol onu azaltamıyor? Beden kaybı payı Lumoda {yd(deg['lumoda'], 1)} "
         f"(beden kaynaklı kayıp {s(bk['lumoda'], 2)} puan); en düşük {en_az} {yd(deg[en_az], 1)} ({etiket(en_az)}), en yüksek "
         f"{en_cok} {yd(deg[en_cok], 1)} ({etiket(en_cok)}); her şeyi gönderen {s(len(gonderen))} koşu {aralik(gonderen)}, "
         f"depoda tutan {s(len(tutan))} koşu {aralik(tutan)}")
    alt("beden beden depoda kalan (beş bedenli option'lar; beden sırası 1 → 5)")
    for et, ad in kollar[:1] + [("en iyi, t %30 (tut_eniyi_t30)", "tut_eniyi_t30")]:
        o = O(v, ad)
        print(f"  {et}: ilk alıma göre gönderilmeyen " + " / ".join(yd(o[f"alimdan_kalan_beden_{i}"], 1) for i in range(1, 6))
              + " · depoda fiilen kalan " + " / ".join(yd(o[f"depoda_kalan_beden_{i}"], 1) for i in range(1, 6)))
        print(f"    ilk tükenen beden (bedeni biten hücreler arasında; en az bir bedeni biten hücre payı {yd(o['tukenen_hucre_yuzde'], 1)}): "
              + " / ".join(yd(o[f"ilk_tukenen_beden_{i}"], 1) for i in range(1, 6)))
    lu = O(v, "lumoda")
    toplam = (v.yayimlanan or {}).get("beden")
    alim = " / ".join(y(bolum(a, int(toplam["adet"].sum()))) for a in toplam["adet"]) if toplam is not None else "—"
    ilk_tuk = max(range(1, 6), key=lambda i: yuv(lu[f"ilk_tukenen_beden_{i}"], 1))
    soru(7, "\"%30 depoda\" beden beden ne demek? Lumoda'da ilk alıma göre gönderilmeyen (beden 1 → 5): "
         + " / ".join(yd(lu[f"alimdan_kalan_beden_{i}"], 1) for i in range(1, 6))
         + f" (ilk alımın beden payları {alim}; paket en küçük bedene {y(1 / 7)}); sezon içinde ilk tükenen beden en sık "
         f"{s(ilk_tuk)}. beden ({yd(lu[f'ilk_tukenen_beden_{ilk_tuk}'], 1)})")


def hikaye_bolumu(v, ek) -> None:
    hk = v.hikaye
    if not hk:
        raise Eksik("hikaye.json")
    if v.hucreler is None or v.plan is None:
        raise Eksik("lumoda (hücreler)")
    a = hk["ayrinti"]
    sa = hk["sahne"]
    print(f"Sahne (yayımlanan dünya, Lumoda'nın ilk dağıtımı; merdiven Ruling R36): {a['option_id']} {a['ad']} ({a['ust_kategori']}); "
          f"basamak {s(hk['basamak'])} ({', '.join(sa['gevseyen']) or 'gevşeme yok'}); kol {hk['kol']['ad']}")
    h = v.hucreler
    hs = h[h["option_id"] == a["option_id"]].set_index("magaza_id")
    t, bt = hs.loc[a["tasan_magaza_id"]], hs.loc[a["biten_magaza_id"]]
    p = v.plan
    pk = p[p["ust_kategori"] == a["ust_kategori"]]
    toplam_plan = float(pk["satis_hedefi"].sum())
    ph = pk.set_index("magaza_id")["satis_hedefi"]
    print(f"  option'ın Lumoda ilk dağıtımı {s(a['toplam'])} adet, {s(a['magaza_sayisi'])} fiziksel mağaza; varış "
          f"{pd.Timestamp(t['varis']).date()} (taşan) / {pd.Timestamp(bt['varis']).date()} (biten)")
    print(f"  taşan {a['tasan_magaza']} ({a['tasan_magaza_id']}): {s(a['tasan_ilk_adet'])} adet (option'daki payı {y(a['tasan_pay'])}, "
          f"en büyük pay) · 28 günde {s(a['tasan_satis_28'])} satış ({y(bolum(a['tasan_satis_28'], a['tasan_ilk_adet']))}) · 14 günde "
          f"{s(t['satis_14'])} · oturan {s(a['oturan'])} adet")
    print(f"    plan: {sabitler.OYUN_SEZONU} {a['ust_kategori']} satış hedefi {s(ph.get(a['tasan_magaza_id']))} adet, fiziksel mağazalarda "
          f"sıra {s(a['tasan_plan_sirasi'])} / {s(len(pk))}; kategorinin planındaki payı {y(bolum(ph.get(a['tasan_magaza_id']), toplam_plan))}")
    print(f"  biten {a['biten_magaza']} ({a['biten_magaza_id']}): {s(a['biten_ilk_adet'])} adet (option'daki payı {y(a['biten_pay'])}) · 14 günde "
          f"{s(a['biten_satis_14'])} satış ({y(a['biten_oran'])}) · 28 günde {s(bt['satis_28'])} (replenishment'la)")
    print(f"    plan: satış hedefi {s(ph.get(a['biten_magaza_id']))} adet, sıra {s(bt['plan_sirasi'])} / {s(len(pk))}; kategorinin planındaki payı "
          f"{y(bolum(ph.get(a['biten_magaza_id']), toplam_plan))}")
    print(f"  kol ({hk['kol']['ad']}, yalnız karar öncesi bilgiyle): taşana {s(a['kol_tasan_adet'])} adet (Lumoda'nın adedine "
          f"oranı {y(bolum(a['kol_tasan_adet'], a['tasan_ilk_adet']))}), bitene {s(a['kol_biten_adet'])} adet (Lumoda'nın "
          f"adedinin {s(bolum(a['kol_biten_adet'], a['biten_ilk_adet']), 1)} katı)")
    al = hk.get("alternatif_sahne")
    if al:
        print(f"  alternatif: {al['option_id']} {al['ad']} (basamak {s(al['basamak'])}; {', '.join(al['gevseyen']) or 'gevşeme yok'}): "
              f"taşan {al['tasan_magaza']} {s(al['tasan_ilk_adet'])} adet, 28 günde {s(al['tasan_satis_28'])} "
              f"({y(bolum(al['tasan_satis_28'], al['tasan_ilk_adet']))}), plan sırası {s(al['tasan_plan_sirasi'])}, kol "
              f"{s(al['kol_tasan_adet'])} · biten {al['biten_magaza']} {s(al['biten_ilk_adet'])} adet, 14 günde "
              f"{s(al['biten_satis_14'])}, kol {s(al['kol_biten_adet'])}")
    print("  merdivenin aday sayıları (basamak 0 → 4): " + " · ".join(s(x) for x in hk["aday_sayilari"]))
    lum = v.oyun["kosular"].get("lumoda", {})
    kol = v.oyun["kosular"].get(hk["kol"]["ad"], {})
    kl, kk = hk["kaynak"]["lumoda"], hk["kaynak"]["kol"]
    ek += [("HİKÂYE: kaynak lumoda koşusu oyun.json'daki", kl.get("anahtar") == lum.get("anahtar")
            and kl.get("dizin") == f"lumoda_{lum.get('anahtar', '')[:20]}"),
           ("HİKÂYE: kaynak kol koşusu oyun.json'daki", kk.get("ad") == hk["kol"]["ad"] and kk.get("anahtar") == kol.get("anahtar")
            and kk.get("dizin") == f"{kol.get('ayni') or hk['kol']['ad']}_{kol.get('anahtar', '')[:20]}"),
           ("HİKÂYE: kol secim.json'un en iyisi", (v.secim or {}).get("ad") == hk["kol"]["ad"]),
           ("HİKÂYE: taşanın adet ve satışı = hücre tablosu",
            int(t["adet"]) == a["tasan_ilk_adet"] and int(t["satis_28"]) == a["tasan_satis_28"]),
           ("HİKÂYE: bitenin adet ve satışı = hücre tablosu",
            int(bt["adet"]) == a["biten_ilk_adet"] and int(bt["satis_14"]) == a["biten_satis_14"]),
           ("HİKÂYE: option toplamı ve mağaza sayısı = hücre tablosu",
            int(hs["adet"].sum()) == a["toplam"] and len(hs) == a["magaza_sayisi"]),
           ("HİKÂYE: taşanın plan sırası = plan tablosu", int(t["plan_sirasi"]) == a["tasan_plan_sirasi"])]


def demo_bolumu(v, ek) -> None:
    import senaryolar

    if not v.demo:
        raise Eksik("demo (senaryolar.uret)")
    print("Kadran: pay kaynağı × depoda tutulan pay (U'ya göre) = 12 bileşim; yol 0, yalnız önbellekten. Değerler sitedeki")
    print("dosyayla aynı yuvarlamayla (yüzde bir ondalık, adet tam sayı).")
    son = v.demo["sonuclar"]
    olc = list(senaryolar.OZET_OLCUTLERI)
    print(f"  {'bileşim':<12}" + "".join(f"{o:>24}" for o in olc))
    for anahtar, g in son.items():
        print(f"  {anahtar:<12}" + "".join(f"{s(g['ozet'][o], senaryolar.OZET_OLCUTLERI[o]):>24}" for o in olc))
    alt("kadranın farkları (basılan değerlerden)")
    for pay in senaryolar.PAYLAR:
        k = lambda t, m: son[senaryolar.anahtar(pay, t)]["ozet"][m]  # noqa: E731
        print(f"  {pay:<7} tutma %0 → %15 → %30: bulunabilirlik {isaretli(fark(k(0, 'bulunabilirlik'), k(15, 'bulunabilirlik'), 1), 1)}"
              f" / {isaretli(fark(k(15, 'bulunabilirlik'), k(30, 'bulunabilirlik'), 1), 1)} · kalan "
              f"{isaretli(fark(k(0, 'sezon_sonu_kalan_yuzde'), k(15, 'sezon_sonu_kalan_yuzde'), 1), 1)} / "
              f"{isaretli(fark(k(15, 'sezon_sonu_kalan_yuzde'), k(30, 'sezon_sonu_kalan_yuzde'), 1), 1)}")
    for t in senaryolar.TUTMALAR:
        lu = son[senaryolar.anahtar("lumoda", t)]["ozet"]
        print(f"  tutma %{t}: kol − Lumoda bulunabilirlik " + " · ".join(
            f"{p} {isaretli(fark(lu['bulunabilirlik'], son[senaryolar.anahtar(p, t)]['ozet']['bulunabilirlik'], 1), 1)}"
            for p in senaryolar.PAYLAR[1:]))
    alt("kadranın koşularından kol − Lumoda bulunabilirlik, iki ondalık (kadran düzeyleri bir ondalıkla gösterir; "
        "yukarıdaki farklar o basılan düzeylerin farkıdır)")
    bul = lambda p, t: O(v, v.oyun["kosular"][(ad := senaryolar.kosu_adi(v.oyun, p, t))].get("ayni", ad))["bulunabilirlik"]  # noqa: E731
    for t in senaryolar.TUTMALAR:
        print(f"  tutma %{t}: " + " · ".join(f"{p} {isaretli(fark(bul('lumoda', t), bul(p, t), 2), 2)}"
                                             for p in senaryolar.PAYLAR[1:]))
    dosya = v.demo_dosya or {}
    ek += [("DEMO: 12 bileşim", len(son) == 12),
           ("DEMO: sitedeki dosya = raporun bileşimleri",
            dosya.get("sonuclar") == son and dosya.get("parametreler") == v.demo["parametreler"])]


KUME_KOLLARI = (("küme: ciro sınıfı (K2)", "kume_k2"), ("küme: bölge (K1)", "kume_k1"),
                ("küme: ML önerisi", "kume_ml"), ("küme: gizli segment", "kume_gizli"))
KUME_KARSILASTIRMA = (("lumoda", "lumoda"), ("esit", "pay_esit"), ("benzer (mağaza geçmişi)", "pay_benzer_tavansiz"),
                      ("tahmin (LightGBM)", "pay_tahmin_tavansiz"), ("kahin", "pay_kahin"))
KUME_YOL_KOLLARI = ("lumoda", "benzer", "tahmin", "kume_ml", "kume_gizli")
KUME_YOL_CIFTLERI = (("kume_ml", "lumoda"), ("kume_ml", "benzer"), ("kume_ml", "tahmin"), ("kume_gizli", "kume_ml"))


def yon1(a, b, yuksek_iyi: bool = True) -> str:
    """a'nın b'ye göre yönü, basılan bir ondalıklı farktan (`fark1(b, a)`): "önde" | "geride" | "eşit"."""
    d = fark1(b, a)
    if d == 0:
        return "eşit"
    return "önde" if (d > 0) == yuksek_iyi else "geride"


def etkin_duzey(duzey_tam: dict) -> int | None:
    """Seçimin bütün option'ları tek düzeydeyse o düzey (HIYERARSI indisi): pay, hiyerarşisi o düzeyden başlayan
    seçimle aynıdır (eşitlik bozma "ince düzey önce" ilk düzeyi daha ince gösterebilir); değilse None."""
    d = [int(i) for i, n in duzey_tam.items() if n]
    return d[0] if len(d) == 1 else None


def _duzey_metni(duzey_tam: dict, hiyerarsi) -> str:
    """`duzey_tam` (HIYERARSI indisi → option sayısı) okunur biçimde."""
    return " · ".join(f"{' × '.join(hiyerarsi[int(i)]) or 'genel'} {s(n)}"
                      for i, n in sorted(duzey_tam.items(), key=lambda x: int(x[0])) if n)


def kume_bolumu(v, ek) -> None:
    """Mağaza Kümeleme vakasının SORU 7'si (spec 2026-10-20 §4.4): küme payı kolları, kalibrasyon, yol 0, yollar."""
    print("Mağaza Kümeleme vakasının sorusu: kümeye göre plan İlk Sevkiyat'ta ne verir? Küme payı (kumeleme.kume_payi) benzer")
    print("ürün endeksinin küme düzeyindeki hâlidir: bir geçmiş option'da kümenin göreli hızı, üye mağazaların göreli")
    print("hızlarının ortalaması; pay = kümenin, yeni option'ın benzerlik düzeyindeki göreli hızı × mağazanın ölçeği (geçmiş")
    print("Collection talebinin küme ortalamasına oranı; geçmişi olmayan mağaza kümesinin medyan ölçeğini alır). Kollar")
    print("KahinKol'la koşulur (kayıtta kol adı kahin, Ruling R2); t = 0, tavansız: Lumoda'yla aynı mal (⌊U⌋). Gizli segment")
    print("kolu yalnız ölçümdür (gerçek hayatta yok): kümelemenin ulaşabileceği en iyi yapı. Yeni mağaza ML kolunda statik")
    print("özelliklerle 5-NN'le atanır, gizli kolda gerçek segmentini taşır.")
    kk = v.kume_kal
    if not kk:
        raise Eksik(f"cikti/{oyun.KUME_KAL_DOSYASI}")
    hy = kk["hiyerarsi"]
    alt(f"kalibrasyon ({kk['sezon']}, koşusuz; karar günü {kk['karar_gunu']}, öğrenme {', '.join(kk.get('kapanmis_sezonlar', []))}; "
        "kümeler o gün yeniden kuruldu)")
    print(f"  ızgara: hiyerarşinin ilk düzeyi × en az örnek eşiği {', '.join(s(e) for e in kk['izgara']['en_az'])}; ölçü pay WAPE'si "
          "(KALİBRASYON'daki tanım, ilk alımla ağırlıklı); kural: " + kk["kural"])
    print("  ilk düzey (hiyerarşi o düzeyden genele iner): " + " · ".join(
        f"{b} {' × '.join(hy[b]) or 'yalnız genel'}" for b in kk["izgara"]["bas"]))
    for yapi, b in kk["kumeler"].items():
        if yapi.startswith("_"):
            continue
        print(f"  {yapi:<6} {s(b['grup'])} grup, boyutlar {' / '.join(s(n) for n in b['boyutlar'])} ({s(b['magaza'])} mağaza)"
              + (f"; {b['aile']} {b['yontem']} k = {s(b['k'])}" if yapi == "ml" else ""))
    t = pd.DataFrame(kk["tablo"])
    for yapi, sec in kk["secim"].items():
        ty = t[t["yapi"] == yapi]
        print(f"  {yapi}: WAPE (satır ilk düzey, sütun en az örnek {' / '.join(s(e) for e in kk['izgara']['en_az'])})")
        for bas in kk["izgara"]["bas"]:
            r = ty[ty["bas"] == bas].set_index("en_az")["wape"]
            print(f"    {bas}  " + "  ".join(f"{s(r.get(e), 3):>6}" for e in kk["izgara"]["en_az"]))
        dt = ty[(ty["bas"] == sec["bas"]) & (ty["en_az"] == sec["en_az"])]["duzey_tam"].iloc[0]
        es = etkin_duzey(dt)
        esdeger = (f"; ızgarada ilk düzey {sec['bas']}, en az örnek {s(sec['en_az'])} satırı (pay ilk düzey {es} ile aynı)"
                   if es is not None and es != int(sec["bas"]) else
                   f"; ızgarada ilk düzey {sec['bas']}, en az örnek {s(sec['en_az'])} satırı")
        print(f"    seçilen (etkin düzey): {_duzey_metni(dt, hy)}; WAPE {s(sec['wape'], 3)}{esdeger}; "
              f"ızgara ucunda: {'evet' if sec['izgara_ucunda'] else 'hayır'}")
    tk = pd.DataFrame(v.kal["cevrimdisi"])
    secilen = tk[tk["secildi"].astype(bool) & tk["asama"].isin(["benzer", "tahmin"])].set_index("asama")["wape"]
    taban = tk[tk["asama"] == "taban"].set_index("aday")["wape"]
    print(f"  aynı sezonda öteki paylar (KALİBRASYON): lumoda {s(taban.get('lumoda'), 3)} · eşit {s(taban.get('esit'), 3)} · "
          f"benzer {s(secilen.get('benzer'), 3)} · tahmin {s(secilen.get('tahmin'), 3)}")

    alt("kümeler (oyun sezonu karar günü; yol 0)")
    ku = v.kume_uyum
    if ku:
        print(f"  gizli segmentle uyum (yalnız ölçüm; {s(ku['aday'])} aday, {s(ku['kumelenen'])} kümelenen): " + " · ".join(
            f"{y_} ARI {s(r['ari'], 3)} (kümelenenlerde {s(r['ari_kumelenen'], 3)})" for y_, r in ku["yapi"].items() if y_ != "gizli"))
        print("  ML kümesinin çoğunluk segmentinden ayrışan mağaza: " + (", ".join(
            f"{a['magaza_id']}{' (yeni)' if a['yeni'] else ''} ML küme {a['ml']} ({a['ml_cogunluk']}), gerçeği {a['gizli']}"
            for a in ku["ayrisan"]) or "yok"))
    gk = v.oyun.get("girdi", {}).get("kume", {})
    eksik = [ad for _, ad in KUME_KOLLARI if ad.removeprefix("kume_") not in gk]
    if eksik:
        raise Eksik(*(f"oyun.json girdi.kume ({ad})" for ad in eksik))
    for et, ad in KUME_KOLLARI:
        b = gk[ad.removeprefix("kume_")]
        km = b["kumeleme"]
        print(f"  {ad:<11} {km['kaynak']}, {s(km['grup'])} grup ({' / '.join(s(n) for n in km['boyutlar'])}), kimlik {km['kimlik'][:12]}"
              + (f"; {km['aile']} {km['yontem']} k = {s(km['k'])}, öneri kimliği {km['oneri_kimligi'][:12]}, yeni mağaza ataması "
                 + ", ".join(f"{m} → küme {c}" for m, c in sorted(km["yeni_atama"].items())) if ad == "kume_ml" else ""))
        print(f"    düzeyler (oyun option'ları): {_duzey_metni(b['duzey_tam'], hy)} · medyan ölçek alan: "
              + (", ".join(f"{m} {s(x, 3)}" for m, x in sorted(b["medyan_olcekli"].items())) or "yok")
              + f" · kümesi olmayan aday (yaklaşık aday kümesinde): {', '.join(b['etiketsiz_aday']) or 'yok'}")

    alt("yol 0 (oyun sezonu; aynı mal, t = 0, tepkili RPT ve markdown)")
    kars = [(et, ad) for et, ad in KUME_KARSILASTIRMA if ad != "pay_kahin" or kahin_olculur(v)]
    satirlar = kars + list(KUME_KOLLARI)
    _kiyas_tablosu(v, satirlar)
    _mal_tablosu(v, satirlar)
    kd = v.kume_denetim or {}
    for _, ad in KUME_KOLLARI:
        d = kd.get(ad)
        if d is not None:
            print(f"  {ad}: kararlarda {s(d['aday'])} aday (option, mağaza; {s(d['aday_magaza'])} mağaza), sözlükte "
                  f"{s(d['aday_sozlukte'])}, payı > 0 {s(d['aday_pozitif'])}; sözlük {s(d['sozluk_cift'])} çift")
    for et, ad in KUME_KOLLARI:
        print(f"  {ad} − benzer: {_fark_satiri(v, 'pay_benzer_tavansiz', ad)}")
        print(f"  {ad} − tahmin: {_fark_satiri(v, 'pay_tahmin_tavansiz', ad)}")
    print(f"  kume_gizli − kume_ml: {_fark_satiri(v, 'kume_ml', 'kume_gizli')}")
    print(f"  kume_k2 − lumoda (ciro sınıfına göre plan ↔ Lumoda'nın mağaza planı): {_fark_satiri(v, 'lumoda', 'kume_k2')}")
    print("  bulunabilirlik farkı, bir ondalık (iki ondalıklı farkın bir kez yuvarlanmışı): " + " · ".join(
        f"{a} − {c} {isaretli(fark1(O(v, c)['bulunabilirlik'], O(v, a)['bulunabilirlik']), 1)}"
        for a, c in (("kume_ml", "pay_benzer_tavansiz"), ("kume_ml", "pay_tahmin_tavansiz"), ("kume_k2", "lumoda"),
                     ("kume_k1", "lumoda"), ("kume_ml", "lumoda"), ("kume_gizli", "kume_ml"))))

    yl = (v.yollar or {}).get("yollar", {})
    p_sira = sorted(yl, key=int)
    alt(f"yollar ({s(len(p_sira))} talep yolu; yol p > 0'da kümeler ve öğrenme o yolun Lumoda tablolarından yeniden kurulur)")
    eksik = [f"yol {p} {k}" for p in p_sira for k in KUME_YOL_KOLLARI if (p, k) not in v.yol_gecerli]
    if eksik or not p_sira:
        raise Eksik(*(eksik or ["yollar.json"]))
    for p in p_sira:
        km = yl[p]["kosular"]["kume_ml"]["kume"]["kumeleme"]
        print(f"  yol {p}: ML {km['kaynak']}, {km.get('aile')} {km.get('yontem')} k = {s(km.get('k'))} "
              f"({' / '.join(s(n) for n in km['boyutlar'])}), yeni mağaza ataması "
              + (", ".join(f"{m} → {c}" for m, c in sorted((km.get("yeni_atama") or {}).items())) or "yok"))
    deger = {(k, o): [yl[p]["kosular"][k]["olcutler"][o] for p in p_sira] for k in KUME_YOL_KOLLARI
             for o in ("bulunabilirlik", "sezon_sonu_kalan_yuzde", "pay_wape")}
    for o, n in (("bulunabilirlik", 2), ("sezon_sonu_kalan_yuzde", 2), ("pay_wape", 3)):
        print(f"  {o}:")
        for k in KUME_YOL_KOLLARI:
            yv = [yuv(x, n) for x in deger[(k, o)]]
            print(f"    {k:<11}" + " · ".join(s(x, n) for x in yv)
                  + f"  | min {s(min(yv), n)} · medyan {s(statistics.median(yv), n)} · max {s(max(yv), n)}")
    onde = {}
    for a, c in KUME_YOL_CIFTLERI:
        parca = []
        for o, n in (("bulunabilirlik", 2), ("sezon_sonu_kalan_yuzde", 2), ("pay_wape", 3)):
            f = yol_farklari(deger[(a, o)], deger[(c, o)], n)
            k_ = f["pozitif"] if YUKSEK_IYI[o] else f["negatif"]
            onde[(a, c, o)] = (k_, f)
            parca.append(f"{o} {k_}/{f['n']} yolda önde (medyan fark {isaretli(f['medyan'], n)})")
        f = onde[(a, c, "bulunabilirlik")][1]
        print(f"  {a} − {c}: " + " · ".join(parca))
        print(f"    bulunabilirlik farkı bir ondalık: " + " · ".join(isaretli(tek_ondalik(x), 1) for x in f["farklar"])
              + f" | medyan {isaretli(tek_ondalik(f['medyan']), 1)}")

    ml, bz, tm, lu = (O(v, a) for a in ("kume_ml", "pay_benzer_tavansiz", "pay_tahmin_tavansiz", "lumoda"))
    k2, gz = O(v, "kume_k2"), O(v, "kume_gizli")
    yb = lambda a, c: onde[(a, c, "bulunabilirlik")]  # noqa: E731
    print(f"KÜME SORU 7 · Kümeye göre plan İlk Sevkiyat'ta mağazanın kendi geçmişinden ve LightGBM'den iyi mi; ciro sınıfına "
          f"göre plan ne veriyor; gizli segment ne kadar ileride? Yol 0 bulunabilirlik: ML kümesi {yd(ml['bulunabilirlik'], 1)} "
          f"(benzer {yd(bz['bulunabilirlik'], 1)}, {isaretli(fark1(bz['bulunabilirlik'], ml['bulunabilirlik']), 1)} puan, "
          f"{yon1(ml['bulunabilirlik'], bz['bulunabilirlik'])}; tahmin {yd(tm['bulunabilirlik'], 1)}, "
          f"{isaretli(fark1(tm['bulunabilirlik'], ml['bulunabilirlik']), 1)} puan, {yon1(ml['bulunabilirlik'], tm['bulunabilirlik'])})"
          f" · pay WAPE ML {s(ml['pay_wape'], 3)} / benzer {s(bz['pay_wape'], 3)} / tahmin {s(tm['pay_wape'], 3)} · ciro sınıfı "
          f"{yd(k2['bulunabilirlik'], 1)} (Lumoda {yd(lu['bulunabilirlik'], 1)}, {isaretli(fark1(lu['bulunabilirlik'], k2['bulunabilirlik']), 1)} puan)"
          f" · gizli segment {yd(gz['bulunabilirlik'], 1)} (ML'den {isaretli(fark1(ml['bulunabilirlik'], gz['bulunabilirlik']), 1)} puan)"
          f" · yollarda ML bulunabilirlikte benzerden {yb('kume_ml', 'benzer')[0]}/{yb('kume_ml', 'benzer')[1]['n']}, tahminden "
          f"{yb('kume_ml', 'tahmin')[0]}/{yb('kume_ml', 'tahmin')[1]['n']}, Lumoda'dan {yb('kume_ml', 'lumoda')[0]}/"
          f"{yb('kume_ml', 'lumoda')[1]['n']} yolda önde; gizli segment ML'den {yb('kume_gizli', 'kume_ml')[0]}/"
          f"{yb('kume_gizli', 'kume_ml')[1]['n']} yolda önde (medyan fark {isaretli(tek_ondalik(yb('kume_gizli', 'kume_ml')[1]['medyan']), 1)} puan)")

    # korunum
    U = v.kural["U_adet"] if v.kural else None
    for _, ad in KUME_KOLLARI:
        e, o = K(v, ad), O(v, ad)
        c = e.get("cozum", {})
        b = gk[ad.removeprefix("kume_")]
        sec = kk["secim"][ad.removeprefix("kume_")]
        ek += [(f"KÜME: {ad} t = 0, tavansız, Lumoda replenishment, tepkili takvim",
                c.get("kol") == "kume" and c.get("tutma") == 0.0 and c.get("tavan") is False and c.get("repl") == "lumoda"
                and not c.get("takvim") and c.get("yol") == 0),
               (f"KÜME: {ad} motor kırpmadı", o["kirpilan_adet"] == 0),
               (f"KÜME: {ad} ⌊U⌋ gönderdi (ilk dağıtım = U, tavanın bıraktığı 0)",
                U is not None and int(o["ilk_dagitim_adet"]) == U and o["tavan_kalan_adet"] == 0),
               (f"KÜME: {ad} kalibrasyonun seçimiyle (ilk düzey, en az örnek)", (b["bas"], b["en_az"]) == (sec["bas"], sec["en_az"])),
               (f"KÜME: {ad} kümeleri kumeler.json'dan (yol 0)", b["kumeleme"]["kaynak"] == "kumeler.json"),
               (f"KÜME: {ad} koşunun kümeleri bugünkü kumeler.json'unkiler (bölme kimliği)",
                bool(ku) and b["kumeleme"]["kimlik"] == ku.get("kimlik", {}).get(ad.removeprefix("kume_"))
                and (ad != "kume_ml" or b["kumeleme"].get("oneri_kimligi") == ku.get("oneri_kimligi")))]
        ek += _kume_denetimleri(kd.get(ad), ad, b.get("pay"))
    for ad, anahtar in oyun.MEVCUT_ANAHTARLAR.items():
        ek.append((f"KÜME: mevcut koşu {ad}'nın anahtarı değişmedi", K(v, ad)["anahtar"] == anahtar))
    ek += kume_kalibrasyon_tazeligi(v)
    for p in p_sira:
        if int(p) == 0:
            continue
        es = yl[p]["kosular"]["esit"]["olcutler"]
        for kisa in oyun.YOL_KUME_KOLLARI:
            e = yl[p]["kosular"][kisa]
            ek += [(f"KÜME: yol {p} {kisa} motor kırpmadı, ⌊U⌋ (eşit kolla aynı ilk dağıtım)",
                    e["olcutler"]["kirpilan_adet"] == 0 and e["olcutler"]["tavan_kalan_adet"] == 0
                    and e["olcutler"]["ilk_dagitim_adet"] == es["ilk_dagitim_adet"]),
                   (f"KÜME: yol {p} {kisa} kümeleri yolun tablolarından yeniden kuruldu",
                    e["kume"]["kumeleme"]["kaynak"].startswith("yeniden kuruldu"))]
            ek += _kume_denetimleri(kd.get(e["ad"]), f"yol {p} {kisa}", e["kume"].get("pay"))


def kume_kalibrasyon_tazeligi(v) -> list[tuple[str, bool]]:
    """`cikti/kume_kalibrasyon.json`'un tazeliği (dosyanın anahtarı yok; kayıtlı alanlardan): ızgara koşusunun
    kullandığı seçim (oyun.json `kume_kalibrasyon`) dosyanınkiyle aynı; kalibrasyon sezonu ve karar günü
    kalibrasyon.json'unkiyle ve kümeleme vakasının `KAL_KARAR_GUNU`'yle aynı; ızgara ve hiyerarşi bugünkü
    sabitler; tablo eksiksiz ve her yapının seçimi tablosunun en küçük WAPE'si (bugünkü biçim: `duzey_tam`)."""
    from kumeleme import sabitler as kumeleme_sabitler

    kk, kal = v.kume_kal or {}, v.kal or {}
    t = pd.DataFrame(kk.get("tablo", []))
    izgara = {"bas": list(oyun.KUME_BAS_IZGARASI), "en_az": list(oyun.KUME_EN_AZ_IZGARASI)}
    n = len(oyun.KUME_YAPILARI) * len(izgara["bas"]) * len(izgara["en_az"])
    tablo_tamam = len(t) == n and "duzey_tam" in t and set(t["yapi"]) == set(oyun.KUME_YAPILARI)
    secim_tutar = tablo_tamam and all(
        kk["secim"][y_]["wape"] == t.loc[t["yapi"] == y_, "wape"].min() for y_ in oyun.KUME_YAPILARI)
    return [("KÜME: ızgaranın kullandığı küme kalibrasyonu bugünkü kume_kalibrasyon.json",
             (v.oyun.get("kume_kalibrasyon") or {}).get("secim") == kk.get("secim")),
            ("KÜME: küme kalibrasyonu kalibrasyon sezonunda ve karar gününde (kalibrasyon.json, KAL_KARAR_GUNU)",
             kk.get("sezon") == kal.get("sezon") and kk.get("karar_gunu") == kal.get("karar_gunu")
             == kumeleme_sabitler.KAL_KARAR_GUNU.date().isoformat()),
            ("KÜME: küme kalibrasyonunun ızgarası ve hiyerarşisi bugünkü sabitler",
             kk.get("izgara") == izgara and kk.get("hiyerarsi") == [list(d) for d in rapor_b.kume_payi.HIYERARSI]),
            ("KÜME: küme kalibrasyonunun tablosu eksiksiz, seçimler tablonun en küçüğü", bool(secim_tutar))]


def _kume_denetimleri(d: dict | None, ad: str, girdi_kimligi: str | None) -> list[tuple[str, bool]]:
    """Bir küme koşusunun kaydından (`rapor_b.kume_denetimi`) korunum satırları."""
    if d is None:
        return [(f"KÜME: {ad} koşu kaydı denetlendi", False)]
    return [(f"KÜME: {ad} kolu KahinKol (kayıtta kahin)", d["tur"] == "allocation.politika.KahinKol" and d["kol"] == "kahin"),
            (f"KÜME: {ad} koşunun payı kume_paylari.json'daki sözlük (kimlik içerikten) ve girdi kaydındaki",
             d["kimlik_kosu"] is not None and d["kimlik_kosu"] == d["kimlik_sozluk"] == d["kimlik_kayit"] == girdi_kimligi),
            (f"KÜME: {ad} kararındaki her aday sözlükte, payı > 0 (spec §0/12)",
             d["aday"] > 0 and d["aday_sozlukte"] == d["aday"] == d["aday_pozitif"]),
            (f"KÜME: {ad} düzey −1, geri düşüş yok", d["duzey"] == [-1] and d["geri_dusus"] == 0)]


def anlati_bolumu(v, ek) -> None:
    print("Veriden gelmeyen, anlatı için konmuş değerler (varsayım; yazıda kesin sayı gibi sunulmaz):")
    for anahtar, deger in ANLATI_VARSAYIMLARI.items():
        print(f"  {anahtar}: {deger} (1. yazının sahnesi)")


def korunum_bolumu(v, ek) -> None:
    ek.append(("koşular önbellekten açıldı (motor koşmadı)", len(v.acilan) > 0))
    n = korunum(ek)
    print(f"  {s(n)} denetim tuttu: satış ≤ talep, motor kolları kırpmadı, t = 0'da ilk dağıtım + tavanın bıraktığı = U,")
    print("  yayımlanan ilk dağıtım = lumoda, kural − kırpma = Lumoda'nın gönderdiği, uç hücreler = ölçütler, sabit takvimde")
    print("  aynı mal, tutma U'yu aşmaz, t̄, yollar = oyun, hikâye (kaynak koşular, hücreler, plan), demo dosyası; küme")
    print("  kollarında ⌊U⌋ ve kırpma 0, payın sözlüğü kararların her adayını kapsar, mevcut koşuların anahtarı değişmedi.")
    print(f"  koşu önbelleği: {s(len(v.gecerli))} ölçülmüş koşunun ve {s(len(v.yol_gecerli))} yol koşusunun kaydı doğrulandı, "
          f"{s(len(v.acilan))} koşu önbellekten açıldı (bugünkü kod, v4 dosyası ve sürümlerle; motor koşmadı)")


BOLUMLER = [
    ("VERİ", veri_bolumu), ("KURAL", kural_bolumu), ("KALİBRASYON", kalibrasyon_bolumu), ("YOL 0", yol0_bolumu),
    ("YOLLAR", yollar_bolumu), ("TAVAN", tavan_bolumu), ("SABİT TAKVİM", sabit_takvim_bolumu), ("TUTMA", tutma_bolumu),
    ("STRATEJİ", strateji_bolumu), ("İSABET", isabet_bolumu), ("BEDEN", beden_bolumu), ("HİKÂYE", hikaye_bolumu),
    ("DEMO", demo_bolumu), ("KÜME", kume_bolumu), ("ANLATI VARSAYIMLARI", anlati_bolumu), ("KORUNUM", korunum_bolumu),
]


def govde(v) -> None:
    """Bütün bölümler sırasıyla; korunum en sonda (tutmazsa AssertionError). Kesin kipte eksik girdi
    korunum gibi işlenir (stdout boş); taslakta bölüm "[eksik: …]" satırıyla kesilir."""
    print("İlk Sevkiyat (allocation) — v4 raporu. Kaynak: oyun koşuları (cikti/kosular, cikti/oyun.json), yollar "
          "(cikti/yollar.json), kalibrasyon, hikâye, yayımlanan v4 tabloları.")
    ek: list = []
    for ad, f in BOLUMLER:
        baslik(ad)
        try:
            f(v, ek)
        except Eksik as e:
            if not v.taslak:
                raise AssertionError(f"{ad}: {e}") from e
            print(f"  [eksik: {', '.join(e.adlar)}] bölümün kalanı basılmadı")
    if v.taslak:
        print(f"\nTASLAK: {s(len(v.eksik))} eksik girdi (bu çıktı yazılara kaynak olamaz):")
        for e in v.eksik:
            print(f"  {e}")
    korunum(ek)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rapor.py", description=__doc__.split("\n")[0])
    p.add_argument("--taslak", action="store_true", help="eksik girdiyle biçim denetimi (çıkış 2)")
    a = p.parse_args(argv)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            v = rapor_b.hazirla(taslak=a.taslak)
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
