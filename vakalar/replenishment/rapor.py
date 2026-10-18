"""Depodan Mağazaya dizisinin (6 yazı, `/replenishment/depodan-magazaya/`) yayımlanacak BÜTÜN
sayıları buradan basılır (v4).

    cd vakalar/replenishment
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt

Kalıcı kural: yazıya yeni bir sayı girmeden önce buraya eklenir; ortak sayı denetimi
(`cd vakalar/ortak && .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi
../../site/src/content/yazi/replenishment/depodan-magazaya --rapor ../replenishment/cikti/rapor.txt`)
yazılardaki her sayının bu çıktıda geçtiğini denetler. Sayılar Türkçe basılır (binlik nokta,
ondalık virgül, `%12,3`, `−0,32`). Uydurma sayı yasaktır; elle konmuş anlatı sayıları yalnız
ANLATI VARSAYIMLARI'ndadır ve orada etiketlidir. Raporda takvim tarihi geçer (izlenebilirlik);
yazılar tarih ve yıl basmaz, mevsime göreli söyler.

Bölümler (`BOLUMLER`, bu sırayla; spec §5 + Ruling R33):

    VERİ                  mağazalar, option ve çift sayıları, karar sayısı, varış günleri, ilk haftanın satışı
    DEPO                  alım düzeyleri (gerçekleşen ilk alım, planın yüzdesi), defterin koli / açık
                          bölünmesi, pencere sonu depo, NOS / Basic havuzu, uzlaştırma kalemleri
    KALİBRASYON           hedef bulunabilirlik, aileler, koli kuralları, referans tavan, özel gün katsayıları
    YOL 0                 her koşunun bütün ölçütleri
    LUMODA VE KURAL       R33: bulunabilirlik–mağaza stoğu sınırı, eşit stokta fark, farkın teşhisi
    YOLLAR                5 talep yolu, ayrışım (öngörü / politika etkisi), "kaç yolda önde", LightGBM
    LINE KIRILIMI         alım düzeyi, demo, kollar
    KOLİ VE TAVAN         koli kuralları, koli yok, tavan taraması, kısıtın bağlamadığı tavan
    ÖNCELİK               cover / ihtiyaç / eşit, iki alım düzeyinde; kıtlık kararı
    KURAL HEDEFİ          hedef / gerçek talep, tabanın bağladığı çiftler, toplam ile max; ilk pazartesi
    SANSÜR                düzeltmenin hedefe etkisi (sonuç etkisi ölçülmedi), hikâyenin boş raf örneği
    BASİT                 karar anı Basit'i öngörüsüyle kural
    HİKÂYE                sahne, mağaza bazlı denetim, o sabahın depo stoğu
    DEMO                  27 bileşim
    ANLATI VARSAYIMLARI
    KORUNUM

Rapor önce tampona yazılır; korunum tutmazsa ya da bir girdi eksikse (önbellekte olmayan koşu,
bugünkü kodla yazılmamış kayıt) stdout'a tek satır gitmez, mesaj stderr'e, çıkış kodu 1. Basılan her
fark, oran ve ara değer basılan işlenenlerden hesaplanır (`yuv`, `fark`, `bolum`, `ara_deger`).
Ölçülen süre basılmaz: aynı girdiyle iki koşu bayt bayt aynıdır. Girdiler ve hesaplar `rapor_b.py`'de
(motoru koşmaz; önbellekten).
"""

import argparse
import contextlib
import io
import math
import statistics
import sys
import warnings

import numpy as np
import pandas as pd

import rapor_b
from replenishment import sabitler

warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*force_all_finite.*", category=FutureWarning)

CIKTI = sabitler.CIKTI

# Hikâyedeki elle sayılar (1. yazı): veriden gelmez. Değer değişirse kayıt defterine yazılır.
#   veli_giris_saati   Veli'nin isteği kaydettiği saat ("sabah sekizde")
#   ali_giris_saati    Ali'nin aynı satıra ulaştığı saat
ANLATI_VARSAYIMLARI = {"veli_giris_saati": "08:00", "ali_giris_saati": "08:40"}


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
    return metin if metin.startswith("−") or _sifir_mi(metin) else "+" + metin


def tl(x, ondalik: int = 0) -> str:
    return "—" if _yok(x) else f"{s(x, ondalik)} TL"


def yuv(x, ondalik: int = 0) -> float:
    """`s(x, ondalik)`'ın bastığı değer."""
    return float(f"{float(x):.{ondalik}f}")


def fark(a, b, ondalik: int = 0) -> float:
    """b − a, ikisi de `ondalik` hanede basıldığı gibi."""
    return yuv(yuv(b, ondalik) - yuv(a, ondalik), ondalik)


def bolum(a, b, ondalik_a: int = 0, ondalik_b: int = 0) -> float | None:
    """a / b, ikisi de basıldığı gibi."""
    payda = yuv(b, ondalik_b)
    return yuv(a, ondalik_a) / payda if payda else None


def ara_deger(x, x1, y1, x2, y2, ondalik_x: int = 0, ondalik_y: int = 2) -> float:
    """(x1, y1)–(x2, y2) doğrusunda x'in y'si; hepsi basıldığı gibi. x aralık dışındaysa ValueError
    (dış değer kestirilmez)."""
    x, x1, x2 = (yuv(v, ondalik_x) for v in (x, x1, x2))
    y1, y2 = yuv(y1, ondalik_y), yuv(y2, ondalik_y)
    if not min(x1, x2) <= x <= max(x1, x2) or x1 == x2:
        raise ValueError(f"{x} aralığın ({x1}, {x2}) dışında")
    return y1 + (y2 - y1) * (x - x1) / (x2 - x1)


def kisitin_baglamadigi_tavan(noktalar, kisitsiz_bul: float, esik: float = 1.0, ondalik: int = 2):
    """Spec §3.5: bulunabilirliği kısıtsızın `esik` puan yakınına gelen en küçük tarama noktası
    (tavan katı; ∞ = sonsuz tavan, kısıtlı). Değerler basıldığı gibi; yoksa None."""
    for kat, bul in sorted(noktalar, key=lambda n: n[0]):
        if abs(yuv(bul, ondalik) - yuv(kisitsiz_bul, ondalik)) <= esik:
            return kat
    return None


def yol_farklari(a: list, b: list, ondalik: int) -> dict:
    """Yol başına a − b (basılan değerlerden), medyanı ve yön sayıları."""
    f = [fark(bb, aa, ondalik) for aa, bb in zip(a, b)]
    return {"farklar": f, "medyan": yuv(statistics.median(f), ondalik), "pozitif": sum(v > 0 for v in f),
            "negatif": sum(v < 0 for v in f), "n": len(f)}


def baslik(metin: str) -> None:
    print(f"\n=== {metin} ===")


def alt(metin: str) -> None:
    print(f"\n--- {metin} ---")


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


def hedef_denetimleri(h: rapor_b.HedefSonucu, tolerans: float = rapor_b.HEDEF_TOLERANSI) -> list[tuple[str, bool]]:
    """Yeniden kurulan fiziksel hedef, kolun kaydettiği hedefin `tolerans` göreli yakınında (her pazartesi)."""
    oran = np.abs(h.yeni_hedef / h.kayit_hedef - 1)
    return [(f"{h.ad}: yeniden kurulan hedef = kayıt (%{100 * tolerans:g} içinde, {len(oran)} pazartesi)",
             bool(len(oran) > 0 and (oran <= tolerans).all()))]


# ---------------------------------------------------------------------------
# Kısayollar
# ---------------------------------------------------------------------------

def K(v, ad: str) -> dict:
    return v.oyun["kosular"][ad]


def O(v, ad: str) -> dict:
    return K(v, ad)["olcutler"]


def L(v, ad: str) -> dict:
    return {r["line"]: r for r in K(v, ad)["line"]}


LINELAR = ("Collection", "NOS", "Basic", "Outlet")
KOL_ADI = {"lumoda_kisitsiz": "Lumoda kısıtsız (yayımlanan dünya)", "lumoda_ref": "Lumoda kısıtlı",
           "kural_ref": "kural (sabit 4 adet taban)", "kural_ufuk_14": "kural, ros 14 gün taban",
           "kural_ufuk_21": "kural, ros 21 gün taban", "kural_ufuk_28": "kural, ros 28 gün taban",
           "tahmin_taban_ref": "LightGBM + taban", "tahmin_ref": "yalnız LightGBM",
           "kural_basit_ref": "kural, öngörü karar anı Basit'i", "kural_gs_ros": "kural, ros 6 gün taban",
           "kural_gs_istatistik": "kural, istatistik taban"}

BICIM = {  # ölçüt → (tür, ondalık): y yüzde, s sayı, t TL
    "bulunabilirlik": ("y", 2), "talep_adet": ("s", 0), "satis_adet": ("s", 0), "kayip_orani": ("y", 2),
    "ikame_payi": ("y", 1), "kalici_kayip_orani": ("y", 2), "gonderilen_adet": ("s", 0), "acik_adet": ("s", 0),
    "koli_sayisi": ("s", 0), "koli_adet": ("s", 0), "toplama_maliyeti_tl": ("t", 0), "acik_doluluk_ort": ("y", 1),
    "acik_doluluk_tepe": ("y", 1), "tavan_bagli_hafta_yuzde": ("y", 1), "hafta_sayisi": ("s", 0),
    "kesilen_pay_yuzde": ("y", 1), "depo_bos_kayip_pay_yuzde": ("y", 1), "magaza_stok_son": ("s", 0),
    "stoklu_cift": ("s", 0), "bos_cift": ("s", 0), "kirik_cift": ("s", 0), "kirik_cift_pay_yuzde": ("y", 1),
    "beden_sapmasi": ("s", 1), "satisa_donme_gun": ("s", 1), "satilan_gonderilen": ("s", 0),
    "satilmayan_gonderilen": ("s", 0), "fifo_negatif_adet": ("s", 0), "satis_fiziksel_adet": ("s", 0),
    "str": ("y", 1),
}


def b(ad: str, x) -> str:
    tur, n = BICIM.get(ad, ("s", 2))
    return yd(x, n) if tur == "y" else tl(x, n) if tur == "t" else s(x, n)


def taban_metni(gs: dict) -> str:
    """Güvenlik stoku ailesinin metni: sabit 4 adet, ros 6 gün, istatistik Z = 1,65 (değeri kullanılmaz)."""
    if gs["aile"] == "istatistik":
        return "taban istatistik Z = 1,65"
    return f"taban {gs['aile']} {s(gs['deger'])} {'adet' if gs['aile'] == 'sabit' else 'gün'}"


def _ayar_metni(k: dict) -> str:
    a = k.get("ayar")
    if a is None:
        return "Lumoda kuralı, kısıt yok (motorun orantılı kesimi)"
    koli = a["koli"]
    koli_m = "koli zorunluluğu yok" if a["kisitsiz"] else (
        "koli yok" if koli["ad"] == "yok" else f"koli {koli['ad']}")
    tavan = "tavan yok" if a["tavan"] == "inf" else f"tavan {s(a['tavan'])}"
    parca = [f"alım %{s(100 * k['alim'])}", koli_m, tavan]
    if k["kol"] in ("kural", "kural_basit", "tahmin_taban"):
        parca.append(taban_metni(a["gs"]))
    elif k["kol"] == "tahmin":
        parca.append("taban yok")
    parca.append("öncelik orantılı (Lumoda'nın isteği)" if k["kol"] == "lumoda" else f"öncelik {a['oncelik']}")
    return " · ".join(parca)


# ---------------------------------------------------------------------------
# Bölümler
# ---------------------------------------------------------------------------

def veri_bolumu(v, ek) -> None:
    yy = v.yayimlanan
    m = yy.magazalar
    ist = int(m["istanbul"].sum())
    print("Kaynak: yayımlanan v4 tabloları (Lumoda'nın dünyası, kısıt yok) ve dünyanın açık alanları.")
    print(f"mağaza: {s(len(m))} fiziksel + 1 online; İstanbul (Ali) {s(ist)}, Anadolu (Veli) {s(len(m) - ist)}")
    pz = rapor_b.pazartesiler()
    gun = (sabitler.OYUN_BIT - sabitler.OYUN_BAS).days + 1
    print(f"oyun penceresi: {s(gun)} gün (sonbahar-kış sezonunun ilk dört ayı), {s(len(pz))} karar pazartesisi")
    alt("pencerede etkin option (line)")
    toplam = 0
    for _, r in yy.etkin_option.iterrows():
        print(f"  {r['line']:<11}{s(r['option']):>6}")
        toplam += int(r["option"])
    print(f"  {'toplam':<11}{s(toplam):>6}")
    alt("satıştaki fiziksel mağaza–option çifti (option satışta, mağaza açık; pazartesi başına)")
    c = list(v.satistaki.values())
    print(f"  ortalama {s(np.mean(c))} · en az {s(min(c))} · en çok {s(max(c))} · {s(len(c))} pazartesinin "
          f"toplamı {s(sum(c))} karar")
    print(f"  ilk pazartesi {s(c[0])} · son pazartesi {s(c[-1])}")
    alt("pencerede depodan fiziksel mağazaya replenishment (yayımlanan, Lumoda)")
    print(f"  {'line':<11}{'adet':>12}{'çift':>8}{'sevk satırı':>13}")
    for _, r in yy.repl.iterrows():
        print(f"  {r['line']:<11}{s(r['adet']):>12}{s(r['cift']):>8}{s(r['satir']):>13}")
    print(f"  {'toplam':<11}{s(yy.repl['adet'].sum()):>12}{s(yy.repl['cift'].sum()):>8}{s(yy.repl['satir'].sum()):>13}")
    alt("varış süresi (replenishment, çıkıştan mağazaya)")
    va = yy.varis
    vt = int(va["adet"].sum())
    for _, r in va.iterrows():
        print(f"  {s(r['gun'])} gün: {s(r['adet'])} adet ({y(int(r['adet']) / vt)})")
    print(f"  pencerede ilk dağıtım (yeni dalgalar, paketle): {s(yy.ilk_dagitim)} adet")
    alt("ilk karar pazartesisinden önceki 7 gün (karar günü hariç), fiziksel mağaza satışı")
    print(f"  satış yapan mağaza–option çifti {s(yy.son7['cift'])} · satış {s(yy.son7['adet'])} adet "
          f"(temiz satış, iade düşülmez; yazıdaki SQL bloğunun sonucu)")
    ek += [("varış toplamı ≤ replenishment toplamı", vt <= int(yy.repl["adet"].sum())),
           ("satıştaki çift > 0 her pazartesi", min(c) > 0)]


def depo_bolumu(v, ek) -> None:
    alt("alım düzeyleri: AW25 sezonluk option'larının gerçekleşen ilk alımı")
    print("  (alım düzeyi talep tahminine uygulanır; MOQ tabanı ve 10'un katına yuvarlama sonra işler)")
    tam = int(v.ilk_alim[1.0]["adet"].sum())
    pl = v.plan.set_index("line")
    plan_top = float(pl["plan"].sum())
    print(f"  sezon planı (lansmandan indirime; dünyanın plan özeti): {s(plan_top)} adet (" + " · ".join(
        f"{ln} {s(r['option'])} option {s(r['plan'])} adet" for ln, r in pl.iterrows()) + ")")
    for alim in (0.4, 0.7, 1.0):
        t = v.ilk_alim[alim]
        top = int(t["adet"].sum())
        satir = " · ".join(f"{r['line']} {s(r['option'])} option {s(r['adet'])} adet "
                           f"(planın {yd(100 * bolum(r['adet'], pl.loc[r['line'], 'plan']), 1)})" for _, r in t.iterrows())
        print(f"  alım %{s(100 * alim)}: {s(top)} adet = planın {yd(100 * bolum(top, plan_top), 1)}; %100 düzeyine oranı "
              f"{yd(100 * bolum(top, tam), 1)} ({satir})")
    alt("gölge defter, oyunun ilk pazartesisi (koli / açık bölünmesi, açık payı line başına)")
    for alim in (0.4, 0.7, 1.0):
        d = v.defter_bas[alim]
        top = d["uzl_kapali_adet"] + d["uzl_acik_adet"]
        print(f"  alım %{s(100 * alim)}: depo {s(top)} adet = kapalı {s(d['uzl_kapali_koli'])} koli "
              f"({s(d['uzl_kapali_adet'])} adet) + açık {s(d['uzl_acik_adet'])} adet (açık {yd(100 * bolum(d['uzl_acik_adet'], top))})")
    alt("pencerenin son günü depo stoğu (line)")
    for ad in ("kural_ref", "kural_a040_oncelik_cover", "lumoda_ref"):
        t = v.depo_son[ad]
        satir = " · ".join(f"{r['line']} {s(r['adet'])} (stoğu 0 SKU {s(r['bos'])}/{s(r['sku'])})" for _, r in t.iterrows())
        print(f"  {ad}: {satir}")
    alt("NOS + Basic depo havuzu (yayımlanan, pencere pazartesileri)")
    nb = v.yayimlanan.nb_depo
    print(f"  ortalama {s(nb['adet'].mean())} adet · en az {s(nb['adet'].min())} · en çok {s(nb['adet'].max())} · "
          f"stoğu 0 SKU payı ortalama {y(nb['bos_pay'].mean())}")
    alt("gölge defterin uzlaştırma kalemleri (kural_ref, ilk pazartesiden sonraki 17 uzlaştırmanın toplamı)")
    u = v.uzl.iloc[1:]
    kalemler = (
        ("teslim_adet", "tedarikçi teslimi (açık siparişlerin düşmesinden; kolide gelir, açık payı açığa)"),
        ("teslim_kapali_koli", "  bunun kapalı koliye giden kısmı (koli)"),
        ("teslim_acik_adet", "  bunun açığa giden kısmı (adet)"),
        ("kendi_sevk_adet", "kolun kendi gönderimi (bir önceki pazartesi)"),
        ("online_adet", "online satış (depodan; önce açıktan, tavana sayılmaz)"),
        ("ilk_dagitim_kapali_adet", "ilk dağıtım (yeni dalgalar; kapalı koliden)"),
        ("ilk_dagitim_acik_adet", "ilk dağıtımın kapalı koli kalmadığı için açıktan düşen kısmı"),
        ("outlet_adet", "outlet akışı (önce açıktan)"),
        ("aciklanamayan_arti_adet", "açıklanamayan artı (iade, kapanış dönüşü, sezon sonu stok devri; açığa)"),
        ("aciklanamayan_eksi_adet", "açıklanamayan eksi (kalite reddi, açılış transferi; önce açıktan)"),
        ("acilan_koli", "politika dışı çıkışlar için defterde açılan koli"),
    )
    for a, aciklama in kalemler:
        print(f"  {s(u['uzl_' + a].sum()):>12}  {aciklama}")
    son = v.uzl.iloc[-1]
    print(f"  pencere sonu defter: kapalı {s(son['uzl_kapali_koli'])} koli ({s(son['uzl_kapali_adet'])} adet), "
          f"açık {s(son['uzl_acik_adet'])} adet (gönderimden önce)")
    i = int(np.argmax(u["uzl_aciklanamayan_arti_adet"].to_numpy()))
    r = u.iloc[i]
    onceki, pzt = pd.Timestamp(r["tarih"]) - pd.Timedelta(days=7), pd.Timestamp(r["tarih"])
    devir = v.stok_devri[(onceki, pzt)]
    print(f"  en büyük açıklanamayan artı: {rapor_b._ts(pzt).date()} pazartesisi {s(r['uzl_aciklanamayan_arti_adet'])} adet; "
          f"aynı hafta depoya varan sezon sonu stok devri {s(devir)} adet (biten sezonun Collection artığı "
          f"mağazalardan depoya döner; kaydedicisi olmadığı için defter açıklanamayan artıya yazar)")
    print("  not: aynı hafta aynı SKU'da artı ve eksi akışlar uzlaştırmada netleşir; kalemler brüt akışın alt sınırıdır.")
    ek += [("en büyük açıklanamayan artıyı sezon sonu stok devri açıklıyor (devir ≤ artı, devir ≥ artının yarısı)",
            0.5 * r["uzl_aciklanamayan_arti_adet"] <= devir <= r["uzl_aciklanamayan_arti_adet"])]
    for alim in (0.4, 0.7):
        ek.append((f"alım %{s(100 * alim)} ilk alımı %100 düzeyinden küçük",
                   int(v.ilk_alim[alim]["adet"].sum()) < tam))


def kalibrasyon_bolumu(v, ek) -> None:
    k = v.kal
    print("Pencere: oyundan bir yıl önceki aynı mevsim (oyun penceresiyle aynı uzunlukta, sızıntısız), yol 0, alım %100.")
    tab = pd.DataFrame(k["tablo"])
    hed = tab[tab["asama"] == "hedef"].iloc[0]
    print(f"hedef bulunabilirlik: {yd(k['hedef_bulunabilirlik'], 2)} (istatistik ailesinin kısıtsız koşusu; "
          f"mağaza stoğu {s(hed['magaza_stok_son'])})")
    print(f"referans tavan: {s(k['tavan'])} adet/hafta = ⌊{s(sabitler.TAVAN_ORANI, 2)} × kalibrasyon penceresinde "
          f"Lumoda'nın haftalık ortalama replenishment adedi {s(v.yayimlanan.kal_ort, 1)}⌋")
    alt("güvenlik stoku aileleri (kısıtsız: tavan yok, koli zorunluluğu yok)")
    for _, r in tab[tab["asama"].isin(["sabit", "ros"])].iterrows():
        print(f"  {r['aile']:<11}{s(r['deger']):>4}: bulunabilirlik {yd(r['bulunabilirlik'], 2)} · mağaza stoğu "
              f"{s(r['magaza_stok_son'])} · gönderilen {s(r['gonderilen_adet'])}")
    gs = k["gs"]
    print(f"  seçilen: sabit {s(gs['sabit']['deger'])} adet, ros {s(gs['ros']['deger'])} gün (hedefe en yakın); "
          f"istatistik Z = 1,65 (%95 hizmet düzeyi; parametresiz)")
    secim = {a: tab[(tab["aile"] == a) & (tab["deger"] == gs[a]["deger"]) & (tab["koli"] == "kisitsiz")].iloc[0]
             for a in ("sabit", "ros", "istatistik")}
    for a, r in secim.items():
        print(f"  {a}: bulunabilirlik {yd(r['bulunabilirlik'], 2)} · mağaza stoğu {s(r['magaza_stok_son'])}")
    print(f"  aile seçimi (aynı hedefte en az stok): {k['secilen_aile']}")
    alt("koli kuralları (referans tavan, seçilen aile; en iyinin 1 puan yakınında en ucuz)")
    for _, r in tab[tab["asama"].str.startswith("koli")].iterrows():
        par = f"α {s(r['alfa'], 1)} β {s(r['beta'])}" if r["koli"] == "A" else f"γ {s(r['gamma'], 2)}"
        print(f"  {r['koli']} ({par}, taban {r['aile']}): bulunabilirlik {yd(r['bulunabilirlik'], 2)} · toplama "
              f"{tl(r['toplama_maliyeti_tl'])} · koli {s(r['koli_sayisi'])} · açık {s(r['acik_adet'])}")
    ka = k["koli"]
    print(f"  seçilen: {k['secilen_koli']} (α {s(ka['A']['alfa'], 1)}, β {s(ka['A']['beta'])}); "
          f"B (γ {s(ka['B']['gamma'], 2)}); C = A ∧ B kalibre edilmedi (R27: C ⊆ B, B'nin bulunabilirliğini aşamaz), "
          f"oyunda ölçüldü; A'nın α'sı ızgaranın alt ucunda (R26)")
    alt("özel gün katsayıları (pencere başına dek koşunun geçmişi; üst kategori, fiziksel mağazalar)")
    kat = v.katsayilar
    for ad in sorted(a for a in kat if "|" not in a):
        print(f"  {ad:<16} resmî tatil günü {s(kat[ad], 2)} · Black Friday günü {s(kat.get(ad + '|black_friday'), 2)}")
    print("  (katsayı: o günün kategori satışı ÷ ±14 gün içinde haftanın aynı gününe denk gelen normal günlerin ortalaması)")
    ek.append(("referans tavan = ⌊oran × haftalık ortalama⌋",
               k["tavan"] == math.floor(sabitler.TAVAN_ORANI * v.yayimlanan.kal_ort)))


OLCUT_SIRASI = tuple(BICIM)


def yol0_bolumu(v, ek) -> None:
    print("Her koşunun bütün ölçütleri (yol 0 = yayımlanan dünya; pencere, fiziksel mağazalar). Kırık çift her zaman")
    print("stoklu ve boş çift sayısıyla birlikte; bulunabilirlik = talepli hücre-günlerin rafta mal bulunan payı.")
    grup = None
    for ad, k in v.oyun["kosular"].items():
        if k["grup"] != grup:
            grup = k["grup"]
            alt(f"grup: {grup}")
        o = k["olcutler"]
        print(f"  {ad}  [{k['kol']}; {_ayar_metni(k)}]")
        parca = [f"{a}={b(a, o[a])}" for a in OLCUT_SIRASI if a in o]
        for i in range(0, len(parca), 6):
            print("    " + " · ".join(parca[i:i + 6]))
        ek += [(f"{ad}: satış ≤ talep", o["satis_adet"] <= o["talep_adet"]),
               (f"{ad}: FIFO negatif süre yok", o["fifo_negatif_adet"] == 0),
               (f"{ad}: ölçüm bugünkü ölçüm koduyla", k["olcum_kodu"] == v.olcum_kodu)]
        if k["kol"] != "lumoda_kisitsiz":
            ek.append((f"{ad}: kolun kaydı = sevkiyat (motor kesmedi)", k["sevkiyat_farki"] == 0))


def _sinir_satiri(v, ad) -> dict:
    o = O(v, ad)
    return {"ad": ad, "bul": o["bulunabilirlik"], "stok": o["magaza_stok_son"], "ort": v.ort_stok[ad],
            "donme": o["satisa_donme_gun"], "tl": o["toplama_maliyeti_tl"], "kirik": o["kirik_cift_pay_yuzde"],
            "gon": o["gonderilen_adet"], "beden": o["beden_sapmasi"], "depo_bos": o["depo_bos_kayip_pay_yuzde"]}


def _esit_stok(lum: dict, kurallar: list[dict], anahtar: str) -> tuple[float | None, tuple | None]:
    """Kural sınırında (stoğa göre sıralı) Lumoda'nın stoğundaki bulunabilirlik (basılan değerlerden)."""
    sira = sorted(kurallar, key=lambda r: yuv(r[anahtar]))
    for a, c in zip(sira[:-1], sira[1:]):
        if yuv(a[anahtar]) <= yuv(lum[anahtar]) <= yuv(c[anahtar]):
            return ara_deger(lum[anahtar], a[anahtar], a["bul"], c[anahtar], c["bul"]), (a["ad"], c["ad"])
    return None, None


def lumoda_bolumu(v, ek) -> None:
    print("R33: Lumoda'nın bugünkü kuralı (planın 4 haftası, ölü stok kapısı) taban çizgisidir. Kısıtlı Lumoda ile kural,")
    print("aynı depo kısıtında (koli A, referans tavan), bulunabilirlik–mağaza stoğu sınırında karşılaştırılır; kuralın")
    print("hedef ufku kod değişmeden güvenlik stokuyla (ros × gün) genişletildi (R30).")
    alt("sınır (yol 0)")
    satirlar = [_sinir_satiri(v, ad) for ad in ("lumoda_kisitsiz",) + rapor_b.SINIR_KOLLARI]
    print(f"  {'kol':<38}{'bulun.':>8}{'stok son':>10}{'ort. stok':>11}{'dönme':>7}{'toplama TL':>13}"
          f"{'kırık %':>9}{'beden sap.':>11}{'gönderilen':>12}")
    for r in sorted(satirlar, key=lambda r: r["stok"]):
        print(f"  {KOL_ADI[r['ad']]:<38}{yd(r['bul'], 2):>8}{s(r['stok']):>10}{s(r['ort']):>11}{s(r['donme'], 1):>7}"
              f"{s(r['tl']):>13}{yd(r['kirik'], 1):>9}{s(r['beden'], 1):>11}{s(r['gon']):>12}")
    lum = next(r for r in satirlar if r["ad"] == "lumoda_ref")
    ref = next(r for r in satirlar if r["ad"] == "kural_ref")
    kurallar = [r for r in satirlar if r["ad"].startswith("kural")]
    toplam = fark(ref["bul"], lum["bul"], 2)
    print(f"  Lumoda kısıtlı − kural referans: {isaretli(toplam, 2)} puan bulunabilirlik; stok son "
          f"{isaretli(fark(ref['stok'], lum['stok']))} adet ({yd(100 * (bolum(lum['stok'], ref['stok']) - 1), 1)}); "
          f"satışa dönme {s(lum['donme'], 1)} / {s(ref['donme'], 1)} gün; toplama {isaretli(fark(ref['tl'], lum['tl']))} TL")
    for anahtar, etiket in (("stok", "pencere sonu mağaza stoğu"), ("ort", "pencere ortalaması mağaza stoğu")):
        yb, ara = _esit_stok(lum, kurallar, anahtar)
        if yb is None:
            print(f"  eşit {etiket}: Lumoda'nın stoğu kural sınırının dışında (dış değer kestirilmez)")
            continue
        esit = yuv(yb, 2)
        print(f"  eşit {etiket} ({s(lum[anahtar])}): kural sınırı {ara[0]} ile {ara[1]} arasında doğrusal → "
              f"{yd(esit, 2)}; Lumoda {yd(lum['bul'], 2)}: eşit stokta fark {isaretli(fark(esit, lum['bul'], 2), 2)} puan; "
              f"toplam farkın {isaretli(fark(ref['bul'], esit, 2), 2)} puanı stok düzeyinden")
    alt("5 yolda Lumoda kısıtlı − kural referans (bulunabilirlik, puan)")
    yl = v.yollar["yollar"]
    f = yol_farklari([yl[p]["kosular"]["lumoda_ref"]["olcutler"]["bulunabilirlik"] for p in sorted(yl)],
                     [yl[p]["kosular"]["kural_ref"]["olcutler"]["bulunabilirlik"] for p in sorted(yl)], 2)
    print(f"  {' · '.join(isaretli(x, 2) for x in f['farklar'])}; medyan {isaretli(f['medyan'], 2)}; "
          f"Lumoda önde {f['pozitif']}/{f['n']}")

    alt("teşhis (R33): talepli hücre-gün payı, bulunabilirlik, kayıp ve kırık çift, gruplara göre")
    print("  İlk dağıtım (yeni dalgaların paketle ilk sevki) her kolda Lumoda'nındır; kollar yalnız replenishment'ı farklı")
    print("  yapar. Bulunabilirlik ve kayıp iki ondalık, katkı üç ondalık basılır; grup toplamları basılan katkılardan,")
    print("  toplam fark basılan bulunabilirliklerden (ikisi arasındaki fark yalnız yuvarlama).")
    kollar = ("lumoda_kisitsiz", "lumoda_ref", "kural_ref", "kural_ufuk_21", "kural_ufuk_28", "tahmin_taban_ref",
              "tahmin_ref", "kural_basit_ref")
    karsi = ("kural_ufuk_21", "kural_ufuk_28", "kural_ref")
    etiket = {"lansman": "lansman grubu (pencerede lanse = AW25 dalga 2–3, oyun içinde lanse edilenler; yaş satırın gününe göre)",
              "line_yari": "line × pencerenin yarısı (hafta 1–9 / 10–18)",
              "line_beden": "line × beden (çekirdek: beden sırası 2–4)",
              "hafta": "pencere haftası (hafta n: n. karar pazartesisinden başlayan 7 gün)"}
    pz = rapor_b.pazartesiler()
    katki_basili: dict = {}
    for kesit in ("lansman", "line_yari", "line_beden", "hafta"):
        print(f"\n  {etiket[kesit]}")
        tablar = {a: v.teshis[a][v.teshis[a]["kesit"] == kesit].set_index("grup") for a in kollar}
        ref_t = tablar["lumoda_ref"]
        ad = (lambda g: f"{g} ({str(pz[int(ref_t.loc[g, 'hafta'])].date())})") if kesit == "hafta" else (lambda g: g)
        olcuts = [("bulunabilirlik", lambda t, g: yd(100 * t.loc[g, "bulunan"] / t.loc[g, "talepli"], 2)
                   if g in t.index and t.loc[g, "talepli"] else "—"),
                  ("kayıp oranı (karşılanmayan / talep)", lambda t, g: yd(100 * t.loc[g, "karsilanmayan"] / t.loc[g, "talep"], 2)
                   if g in t.index and t.loc[g, "talep"] else "—")]
        for baslik_, fn in olcuts:
            print(f"    {baslik_}")
            print(f"    {'grup':<62}{'pay':>7}" + "".join(f"{a:>18}" for a in kollar))
            for g in ref_t.index:
                pay = ref_t.loc[g, "talepli"] / ref_t["talepli"].sum()
                print(f"    {ad(g):<62}{y(pay):>7}" + "".join(f"{fn(t, g):>18}" for t in tablar.values()))
        if kesit in ("lansman", "line_yari"):
            kt = {a: v.kirik[a][v.kirik[a]["kesit"] == kesit].set_index("grup") for a in kollar}
            foto = "son fotoğraf" if kesit == "lansman" else "hafta 9'un sonu ve son fotoğraf"
            print(f"    kırık çift payı (kırık / stoklu çift; {foto}; yaş fotoğraf gününe göre)")
            gruplar = sorted(set().union(*[set(t.index) for t in kt.values()]))
            for g in gruplar:
                print(f"    {g:<69}" + "".join(
                    f"{(yd(100 * t.loc[g, 'kirik'] / t.loc[g, 'stoklu'], 1) + ' (' + s(t.loc[g, 'stoklu']) + ')') if g in t.index and t.loc[g, 'stoklu'] else '—':>18}"
                    for t in kt.values()))
        for kural in karsi:
            kk = rapor_b.grup_katkisi(v.teshis["lumoda_ref"][v.teshis["lumoda_ref"]["kesit"] == kesit],
                                      v.teshis[kural][v.teshis[kural]["kesit"] == kesit])
            kk["katki_b"] = [yuv(x, 3) for x in kk["katki"]]
            katki_basili[(kesit, kural)] = kk
            basili_fark = fark(O(v, kural)["bulunabilirlik"], O(v, "lumoda_ref")["bulunabilirlik"], 2)
            print(f"    Lumoda kısıtlı − {kural}, katkı (puan): " + " · ".join(
                f"{ad(g)} {isaretli(x, 3)}" for g, x in zip(kk["grup"], kk["katki_b"])) +
                f" · Σ katkı {isaretli(sum(kk['katki_b']), 3)} (basılan bulunabilirlik farkı {isaretli(basili_fark, 2)})")
    alt("teşhisin özeti (Lumoda kısıtlı − kural; basılan katkılardan)")
    bf = v.bf_haftasi
    for kural in karsi:
        la = katki_basili[("lansman", kural)]
        ly = katki_basili[("line_yari", kural)]
        kh = katki_basili[("hafta", kural)]
        nb = yuv(la.loc[la["line"].isin(["NOS", "Basic"]), "katki_b"].sum(), 3)
        nb2 = yuv(ly.loc[ly["line"].isin(["NOS", "Basic"]) & (ly["yari"] == "ikinci"), "katki_b"].sum(), 3)
        pl = yuv(la.loc[la["pencerede"].astype(bool), "katki_b"].sum(), 3)
        kalan = yuv(la.loc[~la["line"].isin(["NOS", "Basic"]) & ~la["pencerede"].astype(bool), "katki_b"].sum(), 3)
        top = yuv(nb + pl + kalan, 3)
        bfk = yuv(kh.loc[kh["hafta"] == bf, "katki_b"].sum(), 3)
        print(f"  {kural}: Σ katkı {isaretli(top, 3)} puan (basılan fark "
              f"{isaretli(fark(O(v, kural)['bulunabilirlik'], O(v, 'lumoda_ref')['bulunabilirlik'], 2), 2)}) = NOS + Basic "
              f"{isaretli(nb, 3)} + pencerede lanse edilen option'ların replenishment'ı {isaretli(pl, 3)} + Collection'ın "
              f"geri kalanı ve Outlet {isaretli(kalan, 3)}; NOS + Basic'in pencerenin ikinci yarısındaki katkısı "
              f"{isaretli(nb2, 3)}; Black Friday haftası (hafta {s(bf + 1)}) katkısı {isaretli(bfk, 3)}")
        ek.append((f"teşhis özeti grupları lansman kesitinin bütün gruplarını kapsar ({kural})",
                   abs(top - yuv(la["katki_b"].sum(), 3)) < 1e-9))
    print("  okuma: yeni lansmanların replenishment'ı eşit stoktaki farkı açıklamıyor (ilk dağıtım ortak); fark NOS ve")
    print("  Basic'te, pencerenin ikinci yarısında. Nedeni bu rapordan çıkmaz (beden düzeyinde istek bir aday, ölçülmedi).")
    alt("NOS + Basic depo stoğu (pencerenin ikinci yarısının 9 pazartesisi): depo boş mu?")
    for ad_ in ("lumoda_ref", "kural_ref", "kural_ufuk_28"):
        d = v.nb_depo[ad_].iloc[9:]
        print(f"  {ad_}: ortalama {s(d['adet'].mean())} adet · stoğu 0 SKU payı ortalama {y(d['bos_pay'].mean(), 2)}")
    print("  depo-boş kayıp payı (bu başlığın kapsamı dışında: bütün pencere, bütün line'lar, fiziksel mağazalar; "
          "karşılanmayanın SKU'nun depo stoğu 0 iken olan payı): " + " · ".join(
        f"{a} {yd(O(v, a)['depo_bos_kayip_pay_yuzde'], 1)}" for a in ("lumoda_ref", "kural_ref", "kural_ufuk_21", "kural_ufuk_28")))
    alt("line kırılımı (sınır kolları)")
    for ad_ in ("lumoda_ref", "kural_ref", "kural_ufuk_21", "kural_ufuk_28"):
        li = L(v, ad_)
        print(f"  {ad_:<15}" + " · ".join(f"{ln} {yd(li[ln]['bulunabilirlik'], 1)} (stok {s(li[ln]['magaza_stok_son'])}, "
                                          f"gönderilen {s(li[ln]['gonderilen_adet'])})" for ln in LINELAR))
    for a in kollar:
        o = O(v, a)
        for kesit, t in v.teshis[a].groupby("kesit"):
            ek += [(f"teşhis {a} {kesit}: Σ talep = ölçüt", int(t["talep"].sum()) == int(o["talep_adet"])),
                   (f"teşhis {a} {kesit}: Σ bulunan / Σ talepli = bulunabilirlik",
                    abs(100 * t["bulunan"].sum() / t["talepli"].sum() - o["bulunabilirlik"]) < 1e-9)]
        for kesit in ("lansman", "line_yari"):
            t = v.kirik[a][v.kirik[a]["kesit"] == kesit]
            if kesit == "line_yari":
                t = t[t["grup"].str.endswith(rapor_b.YARILAR["ikinci"])]
            ek.append((f"kırık tablosu {a} {kesit}: son fotoğrafta Σ stoklu, Σ kırık = ölçüt",
                       int(t["stoklu"].sum()) == int(o["stoklu_cift"]) and int(t["kirik"].sum()) == int(o["kirik_cift"])))
    for (kesit, kural), kk in katki_basili.items():
        ek.append((f"katkılar toplamı = bulunabilirlik farkı ({kesit}, {kural})",
                   abs(kk["katki"].sum() - (O(v, "lumoda_ref")["bulunabilirlik"] - O(v, kural)["bulunabilirlik"])) < 1e-6))


YOL_OLCUTLERI = (("bulunabilirlik", 2), ("kayip_orani", 2), ("magaza_stok_son", 0), ("toplama_maliyeti_tl", 0),
                 ("satisa_donme_gun", 1), ("kirik_cift_pay_yuzde", 1))


def yollar_bolumu(v, ek) -> None:
    yl = v.yollar["yollar"]
    p_sira = sorted(yl, key=int)
    print(f"{s(len(p_sira))} talep yolu: yol 0 yayımlanan dünya, yol p > 0 aynı dünyada başka bir müşteri akışı "
          "(talep tohumu); her yolda LightGBM o yolun geçmişiyle yeniden eğitilir, kalibrasyon yol 0'ınki.")
    for p in p_sira:
        t = yl[p]["tahmin"]
        print(f"  yol {p}: LightGBM eğitim satırı {s(t['satir'])} · doğrulama Poisson sapması {s(t['dogrulama_sapma'], 3)} "
              f"(son hafta {s(t['dogrulama_sapma_lag1'], 3)}, 4 hafta ortalaması {s(t['dogrulama_sapma_ort4'], 3)})")
    kollar = v.yollar["kollar"]
    for olc, n in YOL_OLCUTLERI:
        alt(f"{olc} (yol 0 … {p_sira[-1]}; min / medyan / max basılan değerlerden)")
        for kol in kollar:
            d = [yl[p]["kosular"][kol]["olcutler"][olc] for p in p_sira]
            yv = [yuv(x, n) for x in d]
            print(f"  {kol:<17}" + " · ".join(s(x, n) for x in d) +
                  f"  | min {s(min(yv), n)} · medyan {s(statistics.median(yv), n)} · max {s(max(yv), n)}")
    alt("ayrışım (spec §4.6): öngörü etkisi = tahmin_taban − kural (aynı taban); politika etkisi = tahmin − tahmin_taban")
    med = {}
    for bilesen, (a, c) in {"öngörü": ("tahmin_taban_ref", "kural_ref"), "politika": ("tahmin_ref", "tahmin_taban_ref")}.items():
        for olc, n in (("bulunabilirlik", 2), ("kayip_orani", 2), ("magaza_stok_son", 0), ("toplama_maliyeti_tl", 0)):
            f = yol_farklari([yl[p]["kosular"][a]["olcutler"][olc] for p in p_sira],
                             [yl[p]["kosular"][c]["olcutler"][olc] for p in p_sira], n)
            med[(bilesen, olc)] = f["medyan"]
            print(f"  {bilesen} · {olc}: " + " · ".join(isaretli(x, n) for x in f["farklar"]) +
                  f" | medyan {isaretli(f['medyan'], n)} · artı {f['pozitif']}/{f['n']} · eksi {f['negatif']}/{f['n']}")
    for olc in ("bulunabilirlik", "kayip_orani"):
        o_, p_ = med[("öngörü", olc)], med[("politika", olc)]
        print(f"  politika / öngörü (medyanlar, {olc}): {s(p_ / o_, 2) if o_ else '—'}")
    alt("yol 0: tahmin kolları − kural (basılan değerlerden)")
    k0 = yl["0"]["kosular"]
    for a in ("tahmin_taban_ref", "tahmin_ref"):
        parca = []
        for olc, n in (("bulunabilirlik", 2), ("kayip_orani", 2), ("magaza_stok_son", 0), ("toplama_maliyeti_tl", 0),
                       ("gonderilen_adet", 0), ("satisa_donme_gun", 1)):
            parca.append(f"{olc} {isaretli(fark(k0['kural_ref']['olcutler'][olc], k0[a]['olcutler'][olc], n), n)}")
        print(f"  {a} − kural_ref: " + " · ".join(parca))
    alt("kaç yolda önde (bulunabilirlik yüksek, kayıp / maliyet / stok düşük olan önde; basılan değerlerden)")
    from replenishment.yollar import KARSILASTIRMALAR, YUKSEK_IYI

    ondalik = {"bulunabilirlik": 2, "kayip_orani": 2, "toplama_maliyeti_tl": 0, "magaza_stok_son": 0}
    for a, c in KARSILASTIRMALAR:
        parca = []
        for olc, yuksek in YUKSEK_IYI.items():
            n = ondalik[olc]
            say = sum((yuv(yl[p]["kosular"][a]["olcutler"][olc], n) > yuv(yl[p]["kosular"][c]["olcutler"][olc], n))
                      if yuksek else
                      (yuv(yl[p]["kosular"][a]["olcutler"][olc], n) < yuv(yl[p]["kosular"][c]["olcutler"][olc], n))
                      for p in p_sira)
            parca.append(f"{olc} {say}/{len(p_sira)}")
        print(f"  {a} > {c}: " + " · ".join(parca))
    alt("LightGBM (yol 0)")
    pr = v.tahmin_parametreleri
    print(f"  bir kez eğitilir (oyun sezonunun ilk lansmanından önceki gün dek, üç yıla yakın geçmiş); sezon içinde "
          f"yeniden eğitilmez. Parametreler: {s(pr['num_leaves'])} yaprak, {s(pr['n_estimators'])} ağaç, öğrenme oranı "
          f"{s(pr['learning_rate'], 2)}, yaprakta en az {s(pr['min_child_samples'])} örnek; amaç Poisson")
    to = v.tahmin_ozet
    print(f"  eğitim: {s(to['pazartesi'])} pazartesi, {s(to['satir'])} satır (fiziksel çift, hedef haftasında en az bir stoklu "
          f"gün); doğrulama son {s(to['dogrulama_pazartesi'])} pazartesi, {s(to['dogrulama_satir'])} satır: hedef haftası "
          f"satışı ortalaması {s(to['dogrulama_ortalama_y'], 2)} adet, tahmin ortalaması {s(to['dogrulama_ortalama_tahmin'], 2)}")
    es = v.esitlik
    fz = es["fiziksel"]
    print(f"  karar anı eşitliği: {s(es['fiziksel_oc'])} fiziksel çiftte "
          f"{s(sum(1 for x in fz.values() if x['esit_pay'] == 1.0))} / {s(len(fz))} özellik çevrimdışı ve Görünüm yolunda birebir; "
          f"tahminlerin ortalama mutlak farkı {s(es['tahmin']['ort_mutlak_fark'], 4)}")
    oyun_k = v.oyun["kosular"]
    for kol in kollar:
        ek.append((f"yollar.json yol 0 {kol} = oyun.json", yl["0"]["kosular"][kol]["anahtar"] == oyun_k[kol]["anahtar"]))
    guncel = all(yl[p].get("kod") == v.yollar_kodu for p in p_sira)
    print(f"  yollar.json'un kod özeti {'güncel' if guncel else 'eski (ölçüm dışı bir dosya, ör. oyun.py, sonradan değişti)'}; "
          f"{s(v.yol_kosulari)} yol koşusu önbellekte bugünkü kodla, ölçümleri bugünkü ölçüm koduyla")
    ek += [("yolların koşuları önbellekte (bugünkü kod, veri, sürüm)", v.yol_kosulari == len(p_sira) * len(kollar)),
           ("yolların hepsi tamam", all(yl[p].get("tamam") for p in p_sira)),
           ("yolların ölçümü bugünkü ölçüm koduyla",
            all(yl[p]["kosular"][k]["olcum_kodu"] == v.olcum_kodu for p in p_sira for k in kollar))]


def _line_tablosu(v, ad: str, ek) -> None:
    li = L(v, ad)
    print(f"  {ad} [{_ayar_metni(K(v, ad))}]")
    print(f"    {'line':<11}{'talep':>11}{'satış':>11}{'kayıp':>8}{'bulun.':>8}{'stok son':>10}{'gönderilen':>12}")
    for ln in LINELAR:
        r = li[ln]
        print(f"    {ln:<11}{s(r['talep_adet']):>11}{s(r['satis_adet']):>11}{yd(r['kayip_orani'], 1):>8}"
              f"{yd(r['bulunabilirlik'], 1):>8}{s(r['magaza_stok_son']):>10}{s(r['gonderilen_adet']):>12}")
    ek.append((f"line {ad}: Σ talep = ölçüt", abs(sum(r["talep_adet"] for r in li.values()) - O(v, ad)["talep_adet"]) < 0.5))


def line_bolumu(v, ek) -> None:
    alt("alım düzeyi (kural, referans nokta: aynı koli, tavan, taban; yalnız alım farklı)")
    _line_tablosu(v, "kural_a040_oncelik_cover", ek)
    _line_tablosu(v, "kural_ref", ek)
    a, c = L(v, "kural_a040_oncelik_cover"), L(v, "kural_ref")
    print("  alım %40 → %100, bulunabilirlik (puan): " + " · ".join(
        f"{ln} {isaretli(fark(a[ln]['bulunabilirlik'], c[ln]['bulunabilirlik'], 1), 1)}" for ln in LINELAR))
    alt("demo kural kolları: line bulunabilirliği (alım × tavan)")
    for tavan in ("kisitsiz", "gevsek", "siki"):
        for alim in ("a040", "a070", "a100"):
            ad = f"demo_kural_{alim}_{tavan}"
            li = L(v, ad)
            print(f"  {tavan:<9}{alim}: " + " · ".join(f"{ln} {yd(li[ln]['bulunabilirlik'], 1)}" for ln in LINELAR))
        a, c = L(v, f"demo_kural_a040_{tavan}"), L(v, f"demo_kural_a100_{tavan}")
        print(f"  {tavan:<9}%40 → %100: " + " · ".join(
            f"{ln} {isaretli(fark(a[ln]['bulunabilirlik'], c[ln]['bulunabilirlik'], 1), 1)}" for ln in LINELAR))
    alt("kollar (yol 0, referans nokta)")
    for ad in ("lumoda_kisitsiz", "lumoda_ref", "kural_ufuk_28", "tahmin_taban_ref", "tahmin_ref", "kural_basit_ref"):
        _line_tablosu(v, ad, ek)


TAVAN_NOKTALARI = (("×0,4", 0.4, "kural_tavan_x040"), ("×0,6 (sıkı)", 0.6, "demo_kural_a100_siki"),
                   ("×1,0 (referans)", 1.0, "kural_ref"), ("×1,6 (gevşek)", 1.6, "demo_kural_a100_gevsek"),
                   ("∞ (kısıtlı, tavan yok)", math.inf, "kural_tavan_inf"))


def koli_bolumu(v, ek) -> None:
    alt("koli tanımı (yayımlanan `paket` tablosu; ilk dağıtımla aynı)")
    for _, r in v.yayimlanan.paket.iterrows():
        print(f"  {r['paket_id']} {r['beden_seti']}: {s(r['adet'])} adet (beden sırasıyla {r['dagilim']})")
    print("  açık payı (depoya gelen partinin tam koli kurulabilen kısmından açık kalan): " + " · ".join(
        f"{ln} {y(sabitler.ACIK_PAYI[ln], 0)}" for ln in LINELAR))
    alt("koli kuralı (kural kolu, referans tavan; gönderim önce açık adet, kalan ihtiyaç için kural izin verirse tam koli)")
    print(f"  {'kural':<9}{'gönderilen':>12}{'koli':>9}{'koli adet':>11}{'açık':>9}{'bulun.':>8}{'kayıp':>8}"
          f"{'toplama TL':>12}{'TL/adet':>9}{'beden sap.':>11}{'stok son':>10}{'kırık %':>9}{'dönme':>7}")
    for etiket, ad in (("A", "kural_ref"), ("B", "kural_koli_B"), ("C", "kural_koli_C"), ("koli yok", "kural_koli_yok")):
        o = O(v, ad)
        birim = bolum(o["toplama_maliyeti_tl"], o["gonderilen_adet"])
        print(f"  {etiket:<9}{s(o['gonderilen_adet']):>12}{s(o['koli_sayisi']):>9}{s(o['koli_adet']):>11}{s(o['acik_adet']):>9}"
              f"{yd(o['bulunabilirlik'], 1):>8}{yd(o['kayip_orani'], 1):>8}{s(o['toplama_maliyeti_tl']):>12}{s(birim, 2):>9}"
              f"{s(o['beden_sapmasi'], 1):>11}{s(o['magaza_stok_son']):>10}{yd(o['kirik_cift_pay_yuzde'], 1):>9}"
              f"{s(o['satisa_donme_gun'], 1):>7}")
    a, yk = O(v, "kural_ref"), O(v, "kural_koli_yok")
    tavan = v.kal["tavan"]
    nh = int(a["hafta_sayisi"])
    print(f"  koli yok − A: bulunabilirlik {isaretli(fark(a['bulunabilirlik'], yk['bulunabilirlik'], 1), 1)} puan; "
          f"gönderilen {isaretli(fark(a['gonderilen_adet'], yk['gonderilen_adet']))} adet")
    print(f"  açık toplama tavanı {s(tavan)} adet/hafta × {s(nh)} hafta = {s(tavan * nh)} adet; koli yokken taşınan "
          f"{s(yk['gonderilen_adet'])} adet")
    print(f"  B − C bulunabilirlik farkı {isaretli(fark(O(v, 'kural_koli_C')['bulunabilirlik'], O(v, 'kural_koli_B')['bulunabilirlik'], 2), 2)} puan; "
          f"A − B {isaretli(fark(O(v, 'kural_koli_B')['bulunabilirlik'], a['bulunabilirlik'], 2), 2)} puan")
    alt("tavan taraması (kural kolu; referans tavanın katları)")
    print(f"  {'tavan':<24}{'adet/hafta':>11}{'bulun.':>8}{'kayıp':>8}{'açık':>10}{'koli':>9}{'dol. ort':>9}{'dol. tepe':>10}"
          f"{'tavanda hafta':>14}{'toplama TL':>12}{'stok son':>10}")
    noktalar = []
    for etiket, kat, ad in TAVAN_NOKTALARI:
        o = O(v, ad)
        t = "—" if math.isinf(kat) else s(math.floor(tavan * kat))
        bagli = round(o["tavan_bagli_hafta_yuzde"] * o["hafta_sayisi"] / 100)
        print(f"  {etiket:<24}{t:>11}{yd(o['bulunabilirlik'], 2):>8}{yd(o['kayip_orani'], 1):>8}{s(o['acik_adet']):>10}"
              f"{s(o['koli_sayisi']):>9}{yd(o['acik_doluluk_ort'], 1):>9}{yd(o['acik_doluluk_tepe'], 1):>10}"
              f"{(s(bagli) + '/' + s(o['hafta_sayisi'])) if not math.isinf(kat) else '—':>14}{s(o['toplama_maliyeti_tl']):>12}"
              f"{s(o['magaza_stok_son']):>10}")
        noktalar.append((kat, o["bulunabilirlik"]))
        ref_ayar = dict(K(v, "kural_ref")["ayar"])
        ayar = dict(K(v, ad)["ayar"])
        ek.append((f"tavan taraması {ad}: referans noktadan yalnız tavanla ayrılır",
                   {**ayar, "tavan": None} == {**ref_ayar, "tavan": None}))
    kz = O(v, "demo_kural_a100_kisitsiz")
    print(f"  kısıtsız (tavan yok, koli zorunluluğu yok): bulunabilirlik {yd(kz['bulunabilirlik'], 2)} · açık "
          f"{s(kz['acik_adet'])} · toplama {tl(kz['toplama_maliyeti_tl'])} · doluluk ort. (referans tavana) "
          f"{yd(kz['acik_doluluk_ort'], 1)} · stok son {s(kz['magaza_stok_son'])}")
    kat = kisitin_baglamadigi_tavan(noktalar, kz["bulunabilirlik"])
    print("  kısıtın bağlamadığı tavan (tanım, spec §3.5): bulunabilirliği kısıtsızın 1 puan yakınına gelen en küçük "
          "tarama noktası (basılan değerlerden)")
    sonuc = "yok" if kat is None else ("∞" if math.isinf(kat) else f"×{s(kat, 1)} ({s(math.floor(tavan * kat))} adet/hafta)")
    print(f"  sonuç: {sonuc}")
    for etiket, kat_, ad in TAVAN_NOKTALARI:
        print(f"    {etiket}: kısıtsızdan {isaretli(fark(kz['bulunabilirlik'], O(v, ad)['bulunabilirlik'], 2), 2)} puan")


def oncelik_bolumu(v, ek) -> None:
    print("Paylaştırma önceliği her iki aşamada (açık ve koli) sırayı belirler: cover (gönderimden sonra elindeki malı en")
    print("kısa süre yetecek mağaza önce), ihtiyaç (en büyük ihtiyaç önce), eşit (o hafta en az almış olan önce).")
    gruplar = {"%100": {"cover": "kural_ref", "ihtiyac": "kural_oncelik_ihtiyac", "esit": "kural_oncelik_esit"},
               "%40": {o: f"kural_a040_oncelik_{o}" for o in ("cover", "ihtiyac", "esit")}}
    for alim, kollar in gruplar.items():
        alt(f"alım {alim}")
        print(f"  {'öncelik':<9}{'bulun.':>8}{'kayıp':>8}{'beden sap.':>11}{'stok son':>10}{'kırık %':>9}{'depo-boş kayıp':>16}{'dönme':>7}")
        bl = []
        for o_, ad in kollar.items():
            o = O(v, ad)
            bl.append(o["bulunabilirlik"])
            print(f"  {o_:<9}{yd(o['bulunabilirlik'], 2):>8}{yd(o['kayip_orani'], 2):>8}{s(o['beden_sapmasi'], 1):>11}"
                  f"{s(o['magaza_stok_son']):>10}{yd(o['kirik_cift_pay_yuzde'], 1):>9}{yd(o['depo_bos_kayip_pay_yuzde'], 1):>16}"
                  f"{s(o['satisa_donme_gun'], 1):>7}")
        print(f"  aralık (en yüksek − en düşük bulunabilirlik): {s(fark(min(bl), max(bl), 2), 2)} puan")
    kt = v.oyun["kitlik"]
    alt("kıtlık kararı")
    for a in ("a100", "a040"):
        d = kt[a]
        print(f"  alım %{s(int(a[1:]))}: kısıtsız kolda depo stoğundan kesilen istek payı {yd(d['kisitsiz_kesilen_pay_yuzde'], 1)}; "
              f"kısıtsız kolda depo-boş kayıp payı {yd(d['kisitsiz_depo_bos_kayip_pay_yuzde'], 1)}")
    print(f"  bağlayıcı (alım %40'ta öncelikler arası aralık ≥ {s(kt['esik_puan'], 1)} puan): "
          f"{'evet' if kt['baglayici'] else 'hayır'}; daha kıt alım (%20) {'koşulmadı' if kt['baglayici'] else 'koşuldu'}")
    o = O(v, "kural_ref")
    bagli = round(o["tavan_bagli_hafta_yuzde"] * o["hafta_sayisi"] / 100)
    print(f"  referans noktada açık toplama tavanının dolduğu hafta: {s(bagli)} / {s(o['hafta_sayisi'])}; doluluk "
          f"ortalaması {yd(o['acik_doluluk_ort'], 1)}")
    ek.append(("kıtlık kararı oyun.json'daki ölçümle aynı", abs(kt["a040"]["aralik"] - (max(
        O(v, f"kural_a040_oncelik_{x}")["bulunabilirlik"] for x in ("cover", "ihtiyac", "esit")) - min(
        O(v, f"kural_a040_oncelik_{x}")["bulunabilirlik"] for x in ("cover", "ihtiyac", "esit")))) < 1e-9))


def _hedef_ozeti(h: rapor_b.HedefSonucu) -> dict:
    n = len(h.pazartesi) - 1          # son pazartesinin hedef haftası pencereden taşar
    sl = slice(0, n)
    return {"n": n, **{a: float(getattr(h, a)[sl].sum()) for a in
                       ("ongoru", "ongoru_ham", "gs_top", "hedef", "hedef_ham", "toplam", "talep")},
            "baglayan": float(h.baglayan[sl].mean()), "baglayan_sifir": float(h.baglayan_sifir[sl].mean()),
            "satistaki": float(h.satistaki[sl].mean())}


def kural_hedefi_bolumu(v, ek) -> None:
    print("Hedef = max(öngörü, güvenlik stoku); öngörü = son 7 günün satışı ÷ stoklu gün × 7 × hafta katsayısı.")
    print("Çift düzeyinde hedef kolun kaydında yok: koşunun kendi tablolarından yeniden kurulur (rapor_b notu);")
    print("satıştaki fiziksel çiftler (option satışta, mağaza açık). Gerçek talep: hedef haftası (ertesi gün + 7 gün),")
    print("fiziksel mağazalar; son pazartesinin hedef haftası pencereden taştığı için ilk 17 pazartesi.")
    for ad, h in v.hedef.items():
        z = _hedef_ozeti(h)
        alt(f"{ad} ({taban_metni(h.gs)})")
        print(f"  {s(z['n'])} pazartesi: Σ öngörü {s(z['ongoru'])} · Σ güvenlik stoku {s(z['gs_top'])} · Σ hedef {s(z['hedef'])} "
              f"· Σ gerçek talep {s(z['talep'])}")
        print(f"  hedef stok / hedef haftasının gerçek talebi {y(bolum(z['hedef'], z['talep']))} · öngörü / gerçek talep "
              f"{y(bolum(z['ongoru'], z['talep']))}")
        print(f"  tabanın bağladığı çift (güvenlik stoku > öngörü): pazartesi başına ortalama {s(z['baglayan'])} / "
              f"{s(z['satistaki'])} satıştaki çift ({y(bolum(z['baglayan'], z['satistaki']))}); bunların öngörüsü 0 olanı "
              f"{s(z['baglayan_sifir'])} ({y(bolum(z['baglayan_sifir'], z['baglayan']))})")
        print(f"  toplam ile max: Σ (öngörü + güvenlik stoku) {s(z['toplam'])}; max'a oranı {y(bolum(z['toplam'], z['hedef']))}, "
              f"yani toplam hedef max'tan {yd(100 * (bolum(z['toplam'], z['hedef']) - 1), 1)} fazla "
              f"({isaretli(fark(z['hedef'], z['toplam']))} adet; yalnız hedef, sonuç etkisi ölçülmedi)")
        esit = int(np.sum(np.isclose(h.yeni_hedef, h.kayit_hedef, rtol=1e-9, atol=1e-6)))
        oran = np.abs(h.yeni_hedef / h.kayit_hedef - 1)
        i = int(np.argmax(oran))
        print(f"  yeniden kurma denetimi: kayıtla birebir pazartesi {s(esit)} / {s(len(oran))}; en büyük fark "
              f"{rapor_b._ts(h.pazartesi[i]).date()} pazartesisi {yd(100 * oran[i], 2)}")
        ek += hedef_denetimleri(h)
    ref = v.hedef["kural_ref"]
    alt("kural_ref, pazartesi başına (satıştaki çiftler)")
    print(f"  {'#':>3} {'tarih':<11}{'satıştaki':>10}{'öngörü':>10}{'hedef':>10}{'talep':>10}{'bağlayan':>10}")
    for i, p in enumerate(ref.pazartesi):
        icinde = min(7, (pd.Timestamp(sabitler.OYUN_BIT) - rapor_b._ts(p)).days)
        not_ = "" if icinde >= 7 else f"  (kısmi: hedef haftasının {s(icinde)} günü pencerede; toplamlara girmez)"
        print(f"  {i + 1:>3} {str(rapor_b._ts(p).date()):<11}{s(ref.satistaki[i]):>10}{s(ref.ongoru[i]):>10}"
              f"{s(ref.hedef[i]):>10}{s(ref.talep[i]):>10}{s(ref.baglayan[i]):>10}{not_}")
    il = v.ilk
    alt("ilk pazartesi: kural ve LightGBM öngörüsü (bütün kolların geçmişi aynı; satıştaki çiftler)")
    print(f"  satıştaki çift {s(il.satistaki)} · gerçek talep (hedef haftası) {s(il.talep)}")
    oran = bolum(il.lgbm_ongoru, il.kural_ongoru)
    print(f"  öngörü: kural {s(il.kural_ongoru)} · LightGBM {s(il.lgbm_ongoru)} (LightGBM / kural {s(oran, 3)}: LightGBM "
          f"kuraldan {yd(100 * (oran - 1), 1)} yüksek)")
    print(f"  hedef: kural (max(öngörü, taban)) {s(il.kural_hedef)} · LightGBM + taban {s(il.taban_hedef)} · yalnız LightGBM "
          f"{s(il.lgbm_ongoru)}; kural / yalnız LightGBM {s(bolum(il.kural_hedef, il.lgbm_ongoru), 2)} kat")
    print(f"  öngörü / gerçek talep: kural {y(bolum(il.kural_ongoru, il.talep))} · LightGBM {y(bolum(il.lgbm_ongoru, il.talep))}")
    ek += [("ilk pazartesi LightGBM (fiziksel) = tahmin_ref kaydı", abs(il.lgbm_fiziksel / il.kayit_tahmin - 1) < 1e-6),
           ("ilk pazartesi max(LightGBM, taban) (fiziksel) = tahmin_taban_ref kaydı", abs(il.taban_fiziksel / il.kayit_taban - 1) < 1e-6)]


def sansur_bolumu(v, ek) -> None:
    print("Sansür düzeltmesi: hız = satış ÷ stoklu gün (takvim günü değil). Sonuç etkisi (düzeltmesiz kural koşusu)")
    print("ızgarada YOK: ölçülmedi; yazı v2'nin bulunabilirlik farkını kullanamaz. Hedef düzeyindeki etkisi aynı koşunun")
    print("geçmişiyle hesaplanır (kural_ref; satıştaki çiftler, ilk 17 pazartesi).")
    z = _hedef_ozeti(v.hedef["kural_ref"])
    print(f"  Σ öngörü: düzeltmesiz {s(z['ongoru_ham'])} → düzeltmeli {s(z['ongoru'])} "
          f"({yd(100 * (bolum(z['ongoru'], z['ongoru_ham']) - 1), 1)})")
    print(f"  Σ hedef:  düzeltmesiz {s(z['hedef_ham'])} → düzeltmeli {s(z['hedef'])} "
          f"({yd(100 * (bolum(z['hedef'], z['hedef_ham']) - 1), 1)})")
    alt("hikâyenin boş raf örneği (yayımlanan dünya, sahnenin SKU'su, pencere)")
    sa = v.hikaye["sansur"]
    print(f"  {sa['ad']} ({sa['sku']}): {s(sa['takvim_gun'])} takvim günü, {s(sa['stoklu_gun'])} stoklu gün, satış {s(sa['satis'])}")
    print(f"  hız: takvim gününe {s(sa['hiz_takvim'], 2)} · stoklu güne {s(sa['hiz_stoklu'], 2)} "
          f"({s(bolum(sa['hiz_stoklu'], sa['hiz_takvim'], 2, 2), 1)} kat)")
    ek.append(("boş raf örneği: satış = stoklu günlerdeki satış", sa["satis"] == sa["satis_stoklu"]))


def basit_bolumu(v, ek) -> None:
    print("kural_basit: kuralın öngörüsü yerine ortak paketin karar anı Basit'i (Satış Kaybı dizisinin kestiricisi;")
    print("ham 7 gün × hafta katsayısı); taban, koli, tavan aynı. Yalnız yol 0.")
    a, c = O(v, "kural_ref"), O(v, "kural_basit_ref")
    for olc, n in (("bulunabilirlik", 2), ("kayip_orani", 2), ("kalici_kayip_orani", 2), ("magaza_stok_son", 0),
                   ("toplama_maliyeti_tl", 0), ("satisa_donme_gun", 1), ("kirik_cift_pay_yuzde", 1), ("gonderilen_adet", 0)):
        print(f"  {olc:<22} kural {b(olc, a[olc]):>14} · Basit {b(olc, c[olc]):>14} · fark {isaretli(fark(a[olc], c[olc], n), n)}")


def hikaye_bolumu(v, ek) -> None:
    hk = v.hikaye
    sa = hk["sahne"]
    print(f"Sahne (yayımlanan dünya, Lumoda'nın kısıtsız kuralı; seçim merdiveni R32): {sa['model_adi']} {sa['renk']} "
          f"{sa['beden']} ({sa['sku']}, {sa['line']}, {sa['beden_seti']})")
    print(f"  oyunun {s(sa['pazartesi_sirasi'])}. pazartesisi ({sa['pazartesi']}), lansmandan {s(sa['lansmandan_gun'])} gün sonra; "
          f"hız penceresi {s(sa['hiz_penceresi_gun'])} gün önce / sonra")
    print(f"  istek {s(sa['istek_toplam'])} adet ({s(sa['n_istek_magaza'])} mağaza: Ali {s(sa['n_ali_istek'])}, Veli "
          f"{s(sa['n_veli_istek'])}); giden {s(sa['giden_toplam'])} adet")
    d = v.yayimlanan.hikaye_depo
    print(f"  depo stoğu (yayımlanan `depo_stok`, sabah fotoğrafı): o pazartesi {sa['sku']} {s(d['pazartesi']['sku'])} adet "
          f"(option'ın bütün bedenleri {s(d['pazartesi']['option'])}); ertesi sabah {s(d['ertesi']['sku'])} adet")
    print(f"  o pazartesi depodan çıkan replenishment: " + ", ".join(f"{m} {s(a)} adet" for m, a in d["sevk"].items()))
    alt("mağazalar (istek, giden; stoklu gün hızı = satış ÷ stoklu gün, önce / sonra)")
    print(f"  {'mağaza':<14}{'kişi':<6}{'istek':>6}{'giden':>6}   {'önce gün / satış / hız':<26}{'sonra gün / satış / hız':<26}")
    for m in hk["sahne"]["magazalar"]:
        on, so = m["once"], m["sonra"]
        print(f"  {m['ad']:<14}{m['kisi']:<6}{s(m['istek']):>6}{s(m['giden']):>6}   "
              f"{s(on['stoklu_gun']) + ' / ' + s(on['satis']) + ' / ' + s(on['hiz'], 2):<26}"
              f"{s(so['stoklu_gun']) + ' / ' + s(so['satis']) + ' / ' + s(so['hiz'], 2):<26}")
    g = sa["gruplar"]
    for ad, et in (("ali_gitmeyen", "Ali'nin almayan mağazaları"), ("veli_giden", "Veli'nin alan mağazası")):
        x = g[ad]
        print(f"  {et} ({', '.join(x['magazalar'])}): önce {s(x['once']['hiz'], 2)} · sonra {s(x['hiz'], 2)} adet/stoklu gün")
    kn = sa["kanit"]
    print(f"  kanıt (grup hızı farkı, z): önce {s(kn['z_once'], 2)} · sonra {s(kn['z_sonra'], 2)}")
    alt("mağaza bazında denetim (her almayan Ali mağazası her alan Veli mağazasından hızlı mı)")
    mag = {m["magaza_id"]: m for m in sa["magazalar"]}
    ali = [mag[m] for m in g["ali_gitmeyen"]["magazalar"]]
    veli = [mag[m] for m in g["veli_giden"]["magazalar"]]
    for donem, anahtar in (("önce", "once"), ("sonra", "sonra")):
        en_yavas_ali = min(yuv(m[anahtar]["hiz"], 2) for m in ali)
        en_hizli_veli = max(yuv(m[anahtar]["hiz"], 2) for m in veli)
        print(f"  {donem}: en yavaş almayan Ali mağazası {s(en_yavas_ali, 2)} > en hızlı alan Veli mağazası "
              f"{s(en_hizli_veli, 2)}: {'tutuyor' if en_yavas_ali > en_hizli_veli else 'tutmuyor'}")
    ko = sa["kural_olcut"]
    print(f"  ürün geneli (rapor sütunu, merdivende değil; R32): bütün pencerede bu option'da kural kısıtsız "
          f"{yd(ko['bulunabilirlik_kural'], 2)}, Lumoda {yd(ko['bulunabilirlik_lumoda'], 2)} bulunabilirlik; kayıp "
          f"{yd(ko['kayip_orani_kural'], 2)} / {yd(ko['kayip_orani_lumoda'], 2)}")
    alt("seçim merdiveni")
    print("  " + " → ".join(f"{a} {s(n)}" for a, n in hk["merdiven"]["huni"]))
    print(f"  birebir aday {s(hk['merdiven']['rapor']['birebir'])}; bunlardan ürün genelinde kuralın iyi olduğu "
          f"{s(hk['merdiven']['rapor']['birebir_kural_iyi'])}")
    al = hk["alternatif"]
    print(f"  alternatif: {al['model_adi']} {al['renk']} {al['beden']} ({al['sku']}), oyunun {s(al['pazartesi_sirasi'])}. "
          f"pazartesisi; istek {s(al['istek_toplam'])}, giden {s(al['giden_toplam'])}")
    ek += [("hikâye: mağaza istekleri toplamı = sahnenin isteği", sum(m["istek"] for m in sa["magazalar"]) == sa["istek_toplam"]),
           ("hikâye: mağazaya gidenlerin toplamı = sahnenin gideni", sum(m["giden"] for m in sa["magazalar"]) == sa["giden_toplam"]),
           ("hikâye: yayımlanan sevkiyat = sahnenin gideni (mağaza başına)",
            d["sevk"] == {m["magaza_id"]: m["giden"] for m in sa["magazalar"] if m["giden"]}),
           ("hikâye koşuları oyun.json'daki ölçülmüş kayıtlar",
            all(v.oyun["kosular"][x["ad"]]["anahtar"] == x["anahtar"] for x in hk["kaynak"]["kosular"].values()))]


def demo_bolumu(v, ek) -> None:
    import senaryolar

    print("Kadran: depo alımı × ihtiyaç hesabı × açık toplama tavanı (27 bileşim; yol 0, demo bloğu, yalnız önbellekten).")
    print("Değerler sitedeki dosyayla aynı yuvarlamayla (yüzde ve gün bir ondalık, adet ve TL tam sayı).")
    son = v.demo["sonuclar"]
    olc = list(senaryolar.OZET_OLCUTLERI)
    print(f"  {'bileşim':<26}" + "".join(f"{o:>22}" for o in olc))
    for anahtar, g in son.items():
        print(f"  {anahtar:<26}" + "".join(
            f"{s(g['ozet'][o], senaryolar.OZET_OLCUTLERI[o]):>22}" for o in olc))
    alt("kadranın farkları (bulunabilirlik, puan; basılan bir ondalıklı değerlerden)")
    bul = {k: g["ozet"]["bulunabilirlik"] for k, g in son.items()}
    for alim in senaryolar.ALIMLAR:
        for yon in senaryolar.YONTEMLER:
            k = lambda t: bul[senaryolar.anahtar(alim, yon, t)]
            print(f"  %{s(alim)} {yon:<13} tavan: sıkı → gevşek {isaretli(fark(k('siki'), k('gevsek'), 1), 1)} · gevşek → "
                  f"kısıtsız {isaretli(fark(k('gevsek'), k('kisitsiz'), 1), 1)} · sıkı → kısıtsız "
                  f"{isaretli(fark(k('siki'), k('kisitsiz'), 1), 1)}")
    for alim in senaryolar.ALIMLAR:
        for tav in senaryolar.TAVANLAR:
            d = {yon: bul[senaryolar.anahtar(alim, yon, tav)] for yon in senaryolar.YONTEMLER}
            print(f"  %{s(alim)} {tav:<9} yöntem: kural − LightGBM + taban {isaretli(fark(d['tahmin_taban'], d['kural'], 1), 1)} · "
                  f"kural − yalnız LightGBM {isaretli(fark(d['tahmin'], d['kural'], 1), 1)} · aralık (en yüksek − en düşük) "
                  f"{s(fark(min(d.values()), max(d.values()), 1), 1)}")
    for yon in senaryolar.YONTEMLER:
        for tav in senaryolar.TAVANLAR:
            print(f"  {yon:<13} {tav:<9} alım %40 → %100: "
                  f"{isaretli(fark(bul[senaryolar.anahtar(40, yon, tav)], bul[senaryolar.anahtar(100, yon, tav)], 1), 1)}")
    import json as _json

    hedef = senaryolar.HEDEF
    dosya = _json.loads(hedef.read_text(encoding="utf-8")) if hedef.exists() else {}
    ek += [("demo: 27 bileşim", len(son) == 27),
           ("demo: sitedeki dosya = raporun bileşimleri", dosya.get("sonuclar") == son and
            dosya.get("parametreler") == v.demo["parametreler"])]


def anlati_bolumu(v, ek) -> None:
    print("Veriden gelmeyen, anlatı için konmuş değerler (varsayım; yazıda kesin sayı gibi sunulmaz):")
    print("  açık payı (depoya gelen partinin açık kalan kısmı): " + " · ".join(
        f"{ln} {y(p, 0)}" for ln, p in sabitler.ACIK_PAYI.items()))
    print(f"  toplama maliyeti: açık adet başına {s(sabitler.ACIK_TL_ADET)} TL, koli başına {s(sabitler.KOLI_TL)} TL")
    print(f"  tavan oranı: haftalık açık toplama tavanı = kalibrasyon penceresinde Lumoda'nın haftalık ortalama "
          f"replenishment adedi × {s(sabitler.TAVAN_ORANI, 2)}")
    for anahtar, deger in ANLATI_VARSAYIMLARI.items():
        print(f"  {anahtar}: {deger} (1. yazının sahnesi)")
    if v is not None:
        o = O(v, "kural_ref")
        alt("açık adet maliyetine duyarlılık (kural_ref; açık ve koli sayısı aynı, açık TL/adet değişken)")
        for t in (5, 10, 20):
            print(f"  açık {s(t)} TL/adet: toplama {tl(o['acik_adet'] * t + o['koli_sayisi'] * sabitler.KOLI_TL)}")
        ek.append(("toplama maliyeti = açık × 10 + koli × 20 (kural_ref)",
                   abs(o["acik_adet"] * sabitler.ACIK_TL_ADET + o["koli_sayisi"] * sabitler.KOLI_TL
                       - o["toplama_maliyeti_tl"]) < 0.5))


def korunum_bolumu(v, ek) -> None:
    ek.append(("koşular önbellekten açıldı (motor koşmadı)", len(v.acilan) > 0))
    n = korunum(ek)
    print(f"  {s(n)} denetim tuttu: satış ≤ talep, kolun kaydı = sevkiyat, FIFO, ölçüm kodu, yollar = oyun, teşhis toplamları,")
    print("  katkılar = fark, kırık tablosu = ölçüt, line toplamları, yeniden kurulan hedef = kayıt, ilk pazartesi LightGBM = kayıt,")
    print("  tavan taraması, referans tavan, stok devri, hikâye (istek, gönderim, koşu anahtarları), demo dosyası, toplama maliyeti.")
    print(f"  koşu önbelleği: {s(len(v.acilan))} koşu önbellekten açıldı (bugünkü kod, v4 dosyası ve sürümlerle; motor koşmadı)")


BOLUMLER = [
    ("VERİ", veri_bolumu), ("DEPO", depo_bolumu), ("KALİBRASYON", kalibrasyon_bolumu), ("YOL 0", yol0_bolumu),
    ("LUMODA VE KURAL", lumoda_bolumu), ("YOLLAR", yollar_bolumu), ("LINE KIRILIMI", line_bolumu),
    ("KOLİ VE TAVAN", koli_bolumu), ("ÖNCELİK", oncelik_bolumu), ("KURAL HEDEFİ", kural_hedefi_bolumu),
    ("SANSÜR", sansur_bolumu), ("BASİT", basit_bolumu), ("HİKÂYE", hikaye_bolumu), ("DEMO", demo_bolumu),
    ("ANLATI VARSAYIMLARI", anlati_bolumu), ("KORUNUM", korunum_bolumu),
]


def govde(v) -> None:
    """Bütün bölümler sırasıyla; korunum en sonda (tutmazsa AssertionError)."""
    print("Depodan Mağazaya (replenishment) — v4 raporu. Kaynak: oyun koşuları (cikti/kosular, cikti/oyun.json), "
          "yollar (cikti/yollar.json), kalibrasyon, hikâye, yayımlanan v4 tabloları.")
    ek: list = []
    for ad, f in BOLUMLER:
        baslik(ad)
        f(v, ek)
    korunum(ek)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="rapor.py", description=__doc__.split("\n")[0]).parse_args(argv)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            v = rapor_b.hazirla()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    kod, metin = tamponla(lambda: govde(v))
    if kod:
        return kod
    sys.stdout.write(metin)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
