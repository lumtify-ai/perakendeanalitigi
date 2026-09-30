"""Görev 10: yorum kütüphanesi — şema, parti tanımları, denetim (spec §6).

Kütüphane ~4.000 Türkçe yorumdan oluşur (`crm/yorum_kutuphanesi.jsonl`,
Görev 11'de 20 alt ajan tarafından 200'lük partiler halinde yazılır). Bu
modül üç şeyi verir:

1. Kayıt şeması (aşağıdaki alan adları) ve etiket sözlükleri (`KONULAR`,
   `DUYGULAR`, `USLUPLAR`, `KATEGORI_GRUPLARI` — A'nın 5 üst kategorisi,
   `v4.sabitler.KATEGORILER` anahtarları).
2. `parti_tanimlari()` / `parti_dosyasi_yaz()`: 20 × 200 = 4.000 "slot"
   (yazılacak yorumun etiket kombinasyonu; henüz metinsiz). Deterministik
   (`CRM_TOHUM`); `kutuphane_partileri.json` olarak diske yazılır.
3. `denetle()`: dolu (metinli) kütüphaneyi ya da bir alt ajanın kısmi
   partisini şema, tekrar, denge, uzunluk ve yer tutucu sözdizimi açısından
   denetler.

Kayıt şeması (JSONL satırı, Görev 11 çıktısı):
    {"id": "Y0001", "kategori_grubu": "Üst Giyim", "puan": 1..5,
     "duygu": "olumlu"|"olumsuz"|"karisik", "konular": [...],
     "metin": "...", "yer_tutucu": ["renk"|"beden", ...],
     "alt_kategori": null | "Çanta" | "Jean" | ... (A'nın alt kategorisi),
     "uslup": "kisa"|"uzun"|"yazim_hatali"|"ignelemeli"|"celiskili"|"duz"}

`duygu`, metnin gerçek duygusunu etiketler (yıldız puanını değil): puan
4–5 → "olumlu", puan 1–2 → "olumsuz", puan 3 → her zaman "karisik".
`uslup == "celiskili"` olan slotlarda metin puanla çelişir, bu yüzden
temel duygu tersine çevrilir (olumlu ⇄ olumsuz); "karisik" zaten
puanla uyumsuzluğu içerdiğinden çevrilmez.

Aksesuar (Çanta, Şal, Kemer) bedene bağlı olmadığından hiçbir Aksesuar
slotu/kaydı "beden_kalip" konusunu ya da "beden" yer tutucusunu içeremez.
"""

from __future__ import annotations

import functools
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

from .. import sabitler as _a_sabitler
from .sabitler import CRM_TOHUM

# ---------------------------------------------------------------------------
# Şema sözlükleri
# ---------------------------------------------------------------------------

KONULAR: list[str] = [
    "beden_kalip", "kumas_kalite", "renk", "kargo_teslimat",
    "fiyat_deger", "iade_sureci", "genel_begeni",
]
DUYGULAR: list[str] = ["olumlu", "olumsuz", "karisik"]
USLUPLAR: list[str] = [
    "kisa", "uzun", "yazim_hatali", "ignelemeli", "celiskili", "duz",
]
KATEGORI_GRUPLARI: list[str] = list(_a_sabitler.KATEGORILER.keys())
YER_TUTUCULAR: list[str] = ["renk", "beden"]

AKSESUAR_GRUBU = "Aksesuar"
AKSESUAR_YASAK_KONU = "beden_kalip"
AKSESUAR_YASAK_YER_TUTUCU = "beden"

REQUIRED_ALANLAR = {
    "id", "kategori_grubu", "puan", "duygu", "konular", "metin",
    "yer_tutucu", "uslup", "alt_kategori",
}

# ---------------------------------------------------------------------------
# Hedef dağılımlar (Görev 10 brief'i)
# ---------------------------------------------------------------------------

PUAN_ORANI: dict[int, float] = {5: 0.45, 4: 0.20, 3: 0.10, 2: 0.10, 1: 0.15}
USLUP_ORANI: dict[str, float] = {
    "kisa": 0.35, "uzun": 0.15, "yazim_hatali": 0.15,
    "ignelemeli": 0.05, "celiskili": 0.05, "duz": 0.25,
}
YER_TUTUCU_ORANI = 0.20
MIN_KATEGORI_KONU = 25          # her (kategori, konu) çifti için en az
DENGE_TOLERANSI = 0.20          # etiket dengesi ±%20
UZUNLUK_MEDYAN_ARALIGI = (8, 20)
YAKIN_TEKRAR_ESIGI = 0.8         # 5-gram Jaccard
YAKIN_TEKRAR_UST_ORAN = 0.02
TAM_TEKRAR_UST_ORAN = 0.01
TURKCE_KARAKTER_ALT_ORAN = 0.90  # yazim_hatali dışı metinlerde

KUTUPHANE_PARTILERI_YOLU = Path(__file__).resolve().parent / "kutuphane_partileri.json"

_TURKCE_DESEN = re.compile("[çğıöşüÇĞİÖŞÜ]")


# Gerçek renk adı yasağı (Görev 10b): renk yalnız `{renk}` yer tutucusuyla
# anılır ya da adı verilmez. Sözlük A'nın renklerini + yaygın renk adlarını
# içerir; eşleşme ASCII'ye katlanmış, kelime-başı (çekim ekleri yakalansın).
_YAYGIN_RENK_ADLARI: list[str] = [
    "siyah", "beyaz", "kırmızı", "mavi", "lacivert", "yeşil", "haki", "bej",
    "gri", "kahve", "kahverengi", "sarı", "pembe", "mor", "turuncu", "bordo",
    "taba", "ekru", "krem", "mint", "antrasit", "hardal", "pudra", "vizon",
    "somon", "lila", "turkuaz", "camel", "indigo", "füme", "altın", "gümüş",
    "fuşya", "zeytin", "petrol",
    "zümrüt", "mercan", "vişne", "kavuniçi", "kamel", "kapkara",
    "şarap", "nar",
    "taş", "ten",
]
_RENK_ADI_ATLA = {"melanj"}  # "Gri Melanj": renk "gri"; melanj kumaş terimi


def _ascii_katla(metin: str) -> str:
    """Türkçe büyük/küçük harf katlaması (İ→i, I→ı) + ASCII'ye indirgeme
    (ç→c, ğ→g, ı→i, ö→o, ş→s, ü→u): "Sarı", "SARI", "sari" aynı olur."""
    metin = metin.replace("İ", "i").replace("I", "ı").lower()
    return metin.translate(str.maketrans("çğıöşü", "cgiosu"))


def _renk_adlari_kur() -> frozenset[str]:
    adlar = list(_YAYGIN_RENK_ADLARI)
    for ad in list(_a_sabitler.RENKLER) + list(_a_sabitler.DEVAMLI_RENK_HAVUZU):
        adlar.extend(ad.split())
    return frozenset(
        _ascii_katla(a) for a in adlar if _ascii_katla(a) not in _RENK_ADI_ATLA
    )


RENK_ADLARI: frozenset[str] = _renk_adlari_kur()

# Kelime-başı eşleşmesinin yakaladığı bilinen yanlış pozitifler (ASCII katlı
# kelime başı): grip, moral/morarmak, hakikat/hakim/hakiki, sarılmak/sarih,
# taban/tabak, mintan, zeytinyağı, kremi (cilt kremi).
_RENK_ISTISNA = re.compile(
    r"^(?:grip|mor(?:al|ar|g|ta|fi|us|it)|haki[km]|taba[nkl]"
    r"|mintan|zeytiny|kremi)"
)
# Renk dışı anlamı yaygın adlar: yalnız TAM kelime ("altın rengi" evet,
# "altına/altında" hayır) ya da yalnız ardından renk/ton sözcüğü gelince
# ("kahve tonu" evet, "kahve içerken" hayır; "petrol rengi" evet, "petrolle" hayır).
_RENK_TAM_KELIME = {"altin", "tas", "ten"}
# "sarı" sarmak fiiliyle çakışır (sarıyor, sarıp, sarıcı, sarılmak, sarih):
# kelime-başı değil, yalnız isim çekimi (ASCII katlı) kabul edilir.
_SARI_ISIM_CEKIMI = re.compile(
    r"^sari(?:si|sini|sina|sinda|sindan|nin|ni|na|nda|ndan|dan|da|ya|yi"
    r"|yla|ydi|ymis|dir|li|lar\w*|msi\w*|mtirak\w*|sin)?$"
)
_RENK_RENK_SOZCUGU = ("renk", "reng", "ton")
_RENK_ARDINDAN_GEREKIR: dict[str, tuple[str, ...]] = {
    "kahve": _RENK_RENK_SOZCUGU,
    "petrol": _RENK_RENK_SOZCUGU,
    "sarap": _RENK_RENK_SOZCUGU,      # "şarap rengi" evet, "şarap lekesi" hayır
    "nar": ("cice",),                # "nar çiçeği" evet, "nar gibi" hayır
    "tas": _RENK_RENK_SOZCUGU,       # "taş rengi" evet, "taş gibi" hayır
}
# "ten rengi" ürünün rengi olarak (ten rengi, ten rengini, ten renkli, ten
# tonunda) yasaktır; ama "ten rengime/rengimle uydu" gibi kişi iyelikli biçim
# müşterinin cilt tonudur ve serbesttir ("tenime" zaten ayrı kelimedir).
# Bu yüzden "ten" yalnız ardından iyeliksiz renk/ton biçimi gelince sayılır.
_TEN_RENK_BICIMLERI = {
    "renk", "renkli", "renkte", "renkteki", "rengi", "rengini", "renginde",
    "renginden", "rengiyle", "rengine", "tonu", "tonunu", "tonunda", "tonlu",
}
# "kahve" ayrıca: koyu/açık gibi ton sıfatından sonra ("koyu kahve") ya da
# 3. tekil iyelik biçiminde ("kemerin kahvesi") renktir; "kahve içerken",
# "kahve molası", "kahvemi" içecektir ve geçer ("koyu kahve içiyorum" gibi
# nadir içecek kullanımı bilerek yakalanır — kütüphanede içecek anlatımı yok).
_KAHVE_TON_SIFATI = {"koyu", "acik", "orta", "sicak", "toprak"}
_KAHVE_IYELIK = re.compile(r"^kahvesi(?:ni|nin|nde|ndan|ne)?$")
# Pekiştirmeli biçimler: sapsarı, masmavi, yemyeşil, bembeyaz, kıpkırmızı,
# mosmor, pespembe, simsiyah (kapkara sözlükte ayrı ad).
_PEKISTIRME = {
    "sap": "sari", "mas": "mavi", "yem": "yesil", "bem": "beyaz",
    "kip": "kirmizi", "mos": "mor", "pes": "pembe", "sim": "siyah",
}


def renk_adlari_bul(metin: str) -> list[str]:
    """Metindeki (`{renk}`/`{beden}` yer tutucuları dışında) gerçek renk
    adlarını (ASCII katlı sözlük biçimiyle) döner."""
    metin = re.sub(r"\{(?:renk|beden)\}", " ", metin)
    kelimeler = re.findall(r"\w+|[^\w\s]+", _ascii_katla(metin))
    bulunan: list[str] = []
    for i, kelime in enumerate(kelimeler):
        for onek, kok in _PEKISTIRME.items():
            if kelime.startswith(onek + kok):
                kelime = kelime[len(onek):]
                break
        if _RENK_ISTISNA.match(kelime):
            continue
        for ad in RENK_ADLARI:
            if not kelime.startswith(ad):
                continue
            if ad == "sari" and not _SARI_ISIM_CEKIMI.match(kelime):
                continue
            if ad in _RENK_TAM_KELIME and kelime != ad:
                continue
            if ad == "ten":
                sonraki = kelimeler[i + 1] if i + 1 < len(kelimeler) else ""
                if sonraki not in _TEN_RENK_BICIMLERI:
                    continue
            if ad in _RENK_ARDINDAN_GEREKIR:
                if kelime.startswith("kahvere"):
                    continue
                sonraki = kelimeler[i + 1] if i + 1 < len(kelimeler) else ""
                onceki = kelimeler[i - 1] if i > 0 else ""
                kahve_renk = ad == "kahve" and (
                    onceki in _KAHVE_TON_SIFATI or _KAHVE_IYELIK.match(kelime)
                )
                if not (sonraki.startswith(_RENK_ARDINDAN_GEREKIR[ad]) or kahve_renk):
                    continue
            bulunan.append(ad)
            break
    return bulunan


# Gerçek beden etiketi yasağı (Görev 10b, tur 3): metin sonradan beden'i
# farklı olabilen bir SKU'ya atanır; beden yalnız `{beden}` ya da adsız
# ("bir beden büyük", "normal bedenim") anılır.
_HARF_BEDENLER_KESIN = {
    "xs", "xl", "xxl", "xxxl", "2xl", "3xl", "4xl", "small", "medium", "large",
}
_TEK_HARF_BEDENLER = {"s", "m", "l"}
_BEDEN_BAGLAM_FIILLERI = {
    "aldim", "aldik", "aldi", "geldi", "giydim", "denedim", "istedim", "siparis",
    "giyerim", "giyiyorum", "giyerdim", "giyiyordum", "alirim",
}
_BUYUK_HARF_BEDEN = re.compile(r"(?<![\w{])(?:XXXL|XXL|XL|XS|S|M|L)(?![\w}])")
# Sayının hemen ardından gelince beden bağlamı kuran sözcükler (ASCII katlı):
# "38 büyük geldi", "36 ile değiştirdim", "36'sı tam oldu", "38'i iade ettim".
# "40 derece", "38 TL", "3 hafta", "10 gün", "2 tane" bunları taşımaz.
_BEDEN_BAGLAM_SONRAKI = {"buyuk", "kucuk", "iade", "tam", "ile"}
_BEDEN_BAGLAM_SONRAKI_ONEK = ("degis",)  # değiştir-, değişim, değiştirmek
# Jean ölçüsü: "30 bel 32 boy", "28 bel" (bel/boy ardından: aralık dışı da sayılır).
_BEL_BOY = re.compile(r"(?<!\d)(\d{2})\s*(?:bel|boy)(?!\w)")


def beden_etiketleri_bul(metin: str) -> list[str]:
    """Metindeki (`{renk}`/`{beden}` dışında) gerçek beden etiketlerini döner.

    Kararlar: büyük harfli tek başına XS/S/M/L/XL/XXL/XXXL her zaman;
    xs/xl/xxl/xxxl/2xl/3xl/4xl ve small/medium/large her harf durumunda;
    küçük harfli tek harf (s/m/l) yalnız beden/numara ya da "aldım/geldi..."
    fiiliyle bitişikken; 32-54 arası sayı yalnız beden/numara ya da aynı fiillerle
    bitişikken ("38 beden", "beden 40", "40 numara", "38'i aldım"); sayılar
    ayrıca ardından büyük/küçük/iade/tam/ile/değiştir- gelince ("38 büyük
    geldi", "36 ile değiştirdim", "36'sı tam oldu", "38'i iade ettim"); iki
    haneli sayı + bel/boy her zaman ("30 bel 32 boy"). "40 derece", "38 TL", "3 hafta",
    "10 gün", "bedenime", "bir beden büyük" geçer. Yazıyla sayılar ("otuz sekiz")
    kapsanmaz.
    """
    metin = re.sub(r"\{(?:renk|beden)\}", " ", metin)
    bulunan = set(_BUYUK_HARF_BEDEN.findall(metin))
    katli = re.sub(r"(?<=\w)['’]\w*", "", _ascii_katla(metin))
    bulunan.update(_BEL_BOY.findall(katli))
    t = re.findall(r"\w+|[^\w\s]+", katli)
    for i, kelime in enumerate(t):
        onceki = t[i - 1] if i > 0 else ""
        sonraki = t[i + 1] if i + 1 < len(t) else ""
        bagli = (
            onceki.startswith(("beden", "numara"))
            or sonraki.startswith(("beden", "numara"))
            or sonraki in _BEDEN_BAGLAM_FIILLERI
        )
        # Sayılara (yalnız) ek bağlam: büyük/küçük/iade/tam/ile/değiştir-.
        sayi_bagli = bagli or (
            sonraki in _BEDEN_BAGLAM_SONRAKI
            or sonraki.startswith(_BEDEN_BAGLAM_SONRAKI_ONEK)
        )
        if kelime in _HARF_BEDENLER_KESIN:
            bulunan.add(kelime.upper())
        elif kelime in _TEK_HARF_BEDENLER and bagli:
            bulunan.add(kelime.upper())
        elif len(kelime) == 2 and kelime.isdigit() and 32 <= int(kelime) <= 54 and sayi_bagli:
            bulunan.add(kelime)
    return sorted(bulunan)


# Özel gün / bayram adı yasağı (Görev 11, düzeltme turu 1): yorum tarihi
# atamada belirlenir; metin belirli bir güne bağlanırsa tarihle çelişir.
# ASCII katlı metinde kelime başından aranır ("Anneler Günü'nde", "bayramlık"
# da yakalanır). Ay adları burada yok ("nisan"=nişan, "ekim", "aralık" gibi
# yaygın çakışmalar); onlar yazım kuralıyla ve gözden geçirmeyle denetlenir.
_OZEL_GUN_DESENLERI: dict[str, str] = {
    "Öğretmenler Günü": r"ogretmenler gun",
    "Anneler Günü": r"anneler gun",
    "Babalar Günü": r"babalar gun",
    "Sevgililer Günü": r"sevgililer gun",
    "yılbaşı": r"yilbas",
    "yeni yıl": r"yeni yil(?!\w)",
    "bayram": r"bayram",
    "Ramazan": r"ramazan",
    "Kurban": r"kurban bayram",
    "23 Nisan": r"23 nisan",
    "29 Ekim": r"29 ekim",
    "19 Mayıs": r"19 mayis",
    "30 Ağustos": r"30 agustos",
    "Noel": r"noel",
    "kandil": r"kandil",
    "Hıdırellez": r"hidirellez",
    "karne günü": r"karne",
}
_OZEL_GUN_REGEX = {
    ad: re.compile(r"(?<!\w)" + desen) for ad, desen in _OZEL_GUN_DESENLERI.items()
}


def ozel_gun_adlari_bul(metin: str) -> list[str]:
    """Metindeki özel gün / bayram adlarını (sözlükteki okunur adlarıyla) döner."""
    katli = _ascii_katla(metin)
    return sorted(ad for ad, rx in _OZEL_GUN_REGEX.items() if rx.search(katli))


def _konu_uygulanabilir_mi(kategori: str, konu: str) -> bool:
    return not (kategori == AKSESUAR_GRUBU and konu == AKSESUAR_YASAK_KONU)


def _uygulanabilir_konular(kategori: str) -> list[str]:
    return [k for k in KONULAR if _konu_uygulanabilir_mi(kategori, k)]


def _puan_duygu(puan: int, uslup: str) -> str:
    """Metnin gerçek duygusu: puan 4-5 → olumlu, 1-2 → olumsuz, 3 → karisik;
    `celiskili` üslubunda (metin puanla çelişir) olumlu/olumsuz ters döner."""
    if puan >= 4:
        temel = "olumlu"
    elif puan <= 2:
        temel = "olumsuz"
    else:
        return "karisik"
    if uslup == "celiskili":
        return "olumsuz" if temel == "olumlu" else "olumlu"
    return temel


def _oranli_sayilar(oranlar: dict, toplam: int) -> dict:
    """En büyük kalan yöntemi: oranları `toplam`a tam bölünen tam sayılara
    çevirir (toplamları kesin `toplam` eder)."""
    ham = {k: oran * toplam for k, oran in oranlar.items()}
    taban = {k: int(v) for k, v in ham.items()}
    kalan = toplam - sum(taban.values())
    sira = sorted(oranlar.keys(), key=lambda k: ham[k] - taban[k], reverse=True)
    for k in sira[:kalan]:
        taban[k] += 1
    return taban


def _oranli_dizi(oranlar: dict, toplam: int, rng: np.random.Generator) -> list:
    sayilar = _oranli_sayilar(oranlar, toplam)
    dizi: list = []
    for k, c in sayilar.items():
        dizi.extend([k] * c)
    rng.shuffle(dizi)
    return dizi


# ---------------------------------------------------------------------------
# Parti tanımları
# ---------------------------------------------------------------------------

def parti_tanimlari(n_parti: int = 20, parti_boyu: int = 200) -> list[dict]:
    """20 × 200 = 4.000 slot: her slot bir yazım görevidir (henüz metinsiz).

    Deterministik (`CRM_TOHUM`'dan türetilen bağımsız akışlar); aynı
    parametrelerle her çağrıda birebir aynı sonucu verir. Hedef dağılımlar
    (puan, üslup, yer tutucu payı) `_oranli_sayilar` ile tam sağlanır; her
    (kategori, konu) çifti kategori başına eşit bölüşülmüş round-robin
    birincil konu atamasıyla `MIN_KATEGORI_KONU`'nun çok üstünde garanti
    edilir.
    """
    toplam = n_parti * parti_boyu
    ana_ss = np.random.SeedSequence(CRM_TOHUM, spawn_key=(90,))
    (puan_ss, uslup_ss, kat_ss, konu_sira_ss, konu_ek_ss, yer_ss) = ana_ss.spawn(6)
    rng_puan = np.random.default_rng(puan_ss)
    rng_uslup = np.random.default_rng(uslup_ss)
    rng_kat = np.random.default_rng(kat_ss)
    rng_konu_sira = np.random.default_rng(konu_sira_ss)
    rng_konu_ek = np.random.default_rng(konu_ek_ss)
    rng_yer = np.random.default_rng(yer_ss)

    puanlar = _oranli_dizi(PUAN_ORANI, toplam, rng_puan)
    usluplar = _oranli_dizi(USLUP_ORANI, toplam, rng_uslup)
    kategori_orani = {kat: 1.0 / len(KATEGORI_GRUPLARI) for kat in KATEGORI_GRUPLARI}
    kategoriler = _oranli_dizi(kategori_orani, toplam, rng_kat)

    uygulanabilir = {kat: _uygulanabilir_konular(kat) for kat in KATEGORI_GRUPLARI}
    konu_sirasi = {
        kat: rng_konu_sira.permutation(uygulanabilir[kat]).tolist()
        for kat in KATEGORI_GRUPLARI
    }
    kategori_sayaci = {kat: 0 for kat in KATEGORI_GRUPLARI}

    yer_tutucu_adet = round(YER_TUTUCU_ORANI * toplam)
    yer_tutucu_idx = set(
        rng_yer.choice(toplam, size=yer_tutucu_adet, replace=False).tolist()
    )

    slotlar = []
    for i in range(toplam):
        kat = str(kategoriler[i])
        puan = int(puanlar[i])
        uslup = str(usluplar[i])
        duygu = _puan_duygu(puan, uslup)

        sira = konu_sirasi[kat]
        birincil = sira[kategori_sayaci[kat] % len(sira)]
        kategori_sayaci[kat] += 1
        konular = [birincil]
        aday_diger = [k for k in uygulanabilir[kat] if k != birincil]
        zar = rng_konu_ek.random()
        if zar < 0.10 and len(aday_diger) >= 2:
            konular += list(rng_konu_ek.choice(aday_diger, size=2, replace=False))
        elif zar < 0.45 and aday_diger:
            konular.append(str(rng_konu_ek.choice(aday_diger)))

        if i in yer_tutucu_idx:
            if kat == AKSESUAR_GRUBU:
                yer_tutucu = ["renk"]
            else:
                secim = int(rng_yer.integers(0, 3))
                yer_tutucu = [["renk"], ["beden"], ["renk", "beden"]][secim]
        else:
            yer_tutucu = []

        slotlar.append({
            "id": f"Y{i + 1:04d}",
            "kategori_grubu": kat,
            "puan": puan,
            "duygu": duygu,
            "konular": konular,
            "uslup": uslup,
            "yer_tutucu": yer_tutucu,
        })

    return [
        {"parti_no": p + 1, "slotlar": slotlar[p * parti_boyu:(p + 1) * parti_boyu]}
        for p in range(n_parti)
    ]


def parti_dosyasi_yaz(
    partiler: list[dict] | None = None, yol: str | Path | None = None,
) -> Path:
    """`parti_tanimlari()` sonucunu (verilmezse yeniden üretir) JSON olarak
    yazar; varsayılan hedef `kutuphane_partileri.json`."""
    if partiler is None:
        partiler = parti_tanimlari()
    hedef = Path(yol) if yol is not None else KUTUPHANE_PARTILERI_YOLU
    hedef.write_text(json.dumps(partiler, ensure_ascii=False, indent=2), encoding="utf-8")
    return hedef


# ---------------------------------------------------------------------------
# Ek parti tanımları (Görev 11c): 4.000 -> 7.000
# ---------------------------------------------------------------------------
# Görev 12 TAM ölçümü (talep %62 Üst Giyim) ek talep önerisi çıkardı
# (`.superpowers/.../ek-kutuphane-talep.json`, git dışı). Önerinin hedef
# sayıları burada sabit olarak durur; tek karar farkı konu kümeleridir:
# yalnız ["genel_begeni"] en fazla 500 slot, kalan 698 slot genel_begeni +
# (kumas_kalite, renk, beden_kalip, kargo_teslimat) ikililerine dağıtılır.

EK_ILK_ID = 4001
EK_PARTI_SAYISI = 15
EK_ILK_PARTI_NO = 21
EK_KUTUPHANE_PARTILERI_YOLU = (
    Path(__file__).resolve().parent / "kutuphane_ek_partileri.json"
)

# (kategori_grubu, puan) -> slot sayısı (toplam 3.000)
EK_GRUP_PUAN: dict[tuple[str, int], int] = {
    ("Alt Giyim", 1): 57, ("Alt Giyim", 2): 61, ("Alt Giyim", 3): 78,
    ("Alt Giyim", 4): 101, ("Alt Giyim", 5): 594,
    ("Dış Giyim", 2): 1, ("Dış Giyim", 3): 1,
    ("Elbise & Tulum", 4): 3, ("Elbise & Tulum", 5): 31,
    ("Üst Giyim", 1): 133, ("Üst Giyim", 2): 139, ("Üst Giyim", 3): 134,
    ("Üst Giyim", 4): 246, ("Üst Giyim", 5): 1421,
}
# konu kümesi -> slot sayısı; yalnız genel_begeni <= 500 (EK_GENEL_BEGENI_UST)
EK_GENEL_BEGENI_UST = 500
# Önerideki 1.198 yalnız-genel_begeni slotundan 698'i ikili kümelere dağıtılır
# (kumas_kalite en büyük pay); öneride zaten olan kümeler aynen kalır.
EK_GENEL_BEGENI_DAGITIMI: dict[str, int] = {
    "kumas_kalite": 278, "renk": 140, "beden_kalip": 140, "kargo_teslimat": 140,
}
EK_KONU_KUMELERI: list[tuple[tuple[str, ...], int]] = [
    (("genel_begeni",), EK_GENEL_BEGENI_UST),
    (("genel_begeni", "kumas_kalite"), EK_GENEL_BEGENI_DAGITIMI["kumas_kalite"]),
    (("genel_begeni", "renk"), 400 + EK_GENEL_BEGENI_DAGITIMI["renk"]),
    (("genel_begeni", "beden_kalip"), 399 + EK_GENEL_BEGENI_DAGITIMI["beden_kalip"]),
    (("genel_begeni", "kargo_teslimat"), EK_GENEL_BEGENI_DAGITIMI["kargo_teslimat"]),
    (("genel_begeni", "fiyat_deger"), 399),
    (("kumas_kalite",), 259),
    (("kumas_kalite", "genel_begeni"), 110),
    (("beden_kalip", "iade_sureci"), 90),
    (("kargo_teslimat",), 89),
    (("beden_kalip",), 56),
]
EK_USLUP_SAYILARI: dict[str, int] = {
    "kisa": 1050, "duz": 750, "uzun": 450, "yazim_hatali": 450,
    "ignelemeli": 150, "celiskili": 150,
}
EK_YER_TUTUCU_SAYILARI: dict[tuple[str, ...], int] = {
    (): 2400, ("renk",): 276, ("renk", "beden"): 162, ("beden",): 162,
}
# (kategori_grubu, alt kategori | None = genel) -> slot sayısı
EK_ALT_KATEGORI_HEDEFI: dict[tuple[str, str | None], int] = {
    ("Alt Giyim", None): 533, ("Alt Giyim", "Etek"): 12,
    ("Alt Giyim", "Jean"): 225, ("Alt Giyim", "Pantolon"): 77,
    ("Alt Giyim", "Şort"): 44,
    ("Dış Giyim", None): 2,
    ("Elbise & Tulum", None): 21, ("Elbise & Tulum", "Elbise"): 8,
    ("Elbise & Tulum", "Tulum"): 5,
    ("Üst Giyim", None): 1245, ("Üst Giyim", "Bluz"): 91,
    ("Üst Giyim", "Gömlek"): 247, ("Üst Giyim", "Kazak"): 56,
    ("Üst Giyim", "Sweatshirt"): 159, ("Üst Giyim", "Tişört"): 275,
}


def _sayilardan_dizi(sayilar: dict, rng: np.random.Generator) -> list:
    dizi: list = []
    for k, c in sayilar.items():
        dizi.extend([k] * c)
    rng.shuffle(dizi)
    return dizi


def ek_parti_tanimlari() -> list[dict]:
    """15 × 200 = 3.000 ek slot (id Y4001–Y7000, parti_no 21–35).

    Hedef sayılar modül sabitlerindedir (`EK_*`); her boyut (grup×puan,
    konu kümesi, üslup, yer tutucu) kendi bağımsız `CRM_TOHUM` akışıyla
    karıştırılır, yani sonuç deterministiktir. `duygu` `_puan_duygu`dan
    gelir. Her slotta yazara yol gösteren `alt_kategori_hedef` vardır
    (belirli alt kategori ya da None = genel); bu alan kütüphane kaydına
    girmez.
    """
    toplam = EK_PARTI_SAYISI * 200
    ana_ss = np.random.SeedSequence(CRM_TOHUM, spawn_key=(91,))
    (gp_ss, konu_ss, uslup_ss, yer_ss, alt_ss) = ana_ss.spawn(5)

    grup_puan = _sayilardan_dizi(EK_GRUP_PUAN, np.random.default_rng(gp_ss))
    konu_kumeleri = _sayilardan_dizi(
        {kume: c for kume, c in EK_KONU_KUMELERI}, np.random.default_rng(konu_ss),
    )
    usluplar = _sayilardan_dizi(EK_USLUP_SAYILARI, np.random.default_rng(uslup_ss))
    yer_tutucular = _sayilardan_dizi(
        EK_YER_TUTUCU_SAYILARI, np.random.default_rng(yer_ss),
    )
    rng_alt = np.random.default_rng(alt_ss)
    alt_hedefleri: dict[str, list] = {}
    for kat in KATEGORI_GRUPLARI:
        alt_hedefleri[kat] = _sayilardan_dizi(
            {alt: c for (g, alt), c in EK_ALT_KATEGORI_HEDEFI.items() if g == kat},
            rng_alt,
        )
    alt_sayac = {kat: 0 for kat in KATEGORI_GRUPLARI}

    slotlar = []
    for i in range(toplam):
        kat, puan = grup_puan[i]
        uslup = usluplar[i]
        konular = list(konu_kumeleri[i])
        yer_tutucu = list(yer_tutucular[i])
        if kat == AKSESUAR_GRUBU:
            konular = [k for k in konular if _konu_uygulanabilir_mi(kat, k)]
            yer_tutucu = [y for y in yer_tutucu if y != AKSESUAR_YASAK_YER_TUTUCU]
        alt = alt_hedefleri[kat][alt_sayac[kat]]
        alt_sayac[kat] += 1
        slotlar.append({
            "id": f"Y{EK_ILK_ID + i:04d}",
            "kategori_grubu": kat,
            "puan": int(puan),
            "duygu": _puan_duygu(int(puan), uslup),
            "konular": konular,
            "uslup": uslup,
            "yer_tutucu": yer_tutucu,
            "alt_kategori_hedef": alt,
        })

    return [
        {"parti_no": EK_ILK_PARTI_NO + p, "slotlar": slotlar[p * 200:(p + 1) * 200]}
        for p in range(EK_PARTI_SAYISI)
    ]


def ek_parti_dosyasi_yaz(
    partiler: list[dict] | None = None, yol: str | Path | None = None,
) -> Path:
    """`ek_parti_tanimlari()` sonucunu `kutuphane_ek_partileri.json` olarak yazar."""
    if partiler is None:
        partiler = ek_parti_tanimlari()
    hedef = Path(yol) if yol is not None else EK_KUTUPHANE_PARTILERI_YOLU
    hedef.write_text(json.dumps(partiler, ensure_ascii=False, indent=2), encoding="utf-8")
    return hedef


@functools.lru_cache(maxsize=1)
def _slot_haritasi() -> dict[str, dict]:
    """id -> slot (ana 4.000 + ek 3.000 slot dosyası)."""
    harita: dict[str, dict] = {}
    for kaynak in (parti_tanimlari(), ek_parti_tanimlari()):
        for parti in kaynak:
            for slot in parti["slotlar"]:
                harita[slot["id"]] = slot
    return harita


def _slot_dosyasi_boyutu(slot_id: str) -> tuple[str, int]:
    """Slot id'nin ait olduğu dosya (ana/ek) ve o dosyadaki slot sayısı."""
    numara = int(slot_id[1:])
    if numara >= EK_ILK_ID:
        return "ek", EK_PARTI_SAYISI * 200
    return "ana", 20 * 200


# ---------------------------------------------------------------------------
# Denetim
# ---------------------------------------------------------------------------

def _kayitlari_oku(yol_veya_liste, hatalar: list[str] | None = None) -> list[dict]:
    """JSONL yolu ya da kayıt listesi okur. Bozuk bir satır `hatalar`a
    (satır numarasıyla) eklenir ve atlanır; `hatalar` verilmemişse sessizce
    atlanır."""
    if isinstance(yol_veya_liste, (str, Path)):
        kayitlar = []
        with open(yol_veya_liste, encoding="utf-8") as f:
            for no, satir in enumerate(f, start=1):
                satir = satir.strip()
                if not satir:
                    continue
                try:
                    kayit = json.loads(satir)
                except json.JSONDecodeError as e:
                    if hatalar is not None:
                        hatalar.append(f"satir {no}: bozuk JSON ({e.msg})")
                    continue
                if not isinstance(kayit, dict):
                    if hatalar is not None:
                        hatalar.append(f"satir {no}: kayit bir nesne degil")
                    continue
                kayitlar.append(kayit)
        return kayitlar
    return list(yol_veya_liste)


def _normalize(metin: str) -> str:
    metin = metin.lower()
    metin = re.sub(r"[^\w\sçğıöşüÇĞİÖŞÜ]", "", metin)
    return re.sub(r"\s+", " ", metin).strip()


def _shingle_kumesi(metin: str, n: int = 5) -> set[str]:
    kelimeler = metin.split()
    if len(kelimeler) < n:
        return {" ".join(kelimeler)} if kelimeler else set()
    return {" ".join(kelimeler[i:i + n]) for i in range(len(kelimeler) - n + 1)}


YAYGIN_SHINGLE_SINIRI = 500


def _yakin_tekrar_orani(metinler: list[str]) -> tuple[float, int]:
    """(oran, atlanan_yaygin_shingle). Bir metnin başka bir metinle 5-gram
    Jaccard > eşik paylaşan çift olma oranı. Ters shingle indeksiyle aday
    çiftleri sınırlar (tam O(n^2) yerine); `YAYGIN_SHINGLE_SINIRI`'ndan fazla
    belgede geçen shingle aday üretmez ama sayılıp döndürülür — çağıran bunu
    hata sayar (yaygın şablon sessizce geçmesin)."""
    n = len(metinler)
    if n < 2:
        return 0.0, 0
    atlanan = 0
    kumeler = [_shingle_kumesi(m) for m in metinler]
    ters_indeks: dict[str, list[int]] = {}
    for i, kume in enumerate(kumeler):
        for sh in kume:
            ters_indeks.setdefault(sh, []).append(i)

    aday_ciftler: set[tuple[int, int]] = set()
    for idxs in ters_indeks.values():
        if len(idxs) > YAYGIN_SHINGLE_SINIRI:
            atlanan += 1
        elif len(idxs) > 1:
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    aday_ciftler.add((idxs[a], idxs[b]))

    etkilenen: set[int] = set()
    for i, j in aday_ciftler:
        a, b = kumeler[i], kumeler[j]
        if not a or not b:
            continue
        birlesim = len(a | b)
        if birlesim and len(a & b) / birlesim > YAKIN_TEKRAR_ESIGI:
            etkilenen.add(i)
            etkilenen.add(j)
    return len(etkilenen) / n, atlanan


def denetle(yol_veya_liste, tam_esik: int = 1000) -> dict:
    """Kütüphaneyi (JSONL yolu ya da kayıt listesi) denetler.

    Küçük (kısmi parti) girdilerde şema/tekrar/uzunluk/yer-tutucu denetimi
    yapılır; yalnız `len(kayitlar) >= tam_esik` olduğunda etiket dengesi ve
    (kategori, konu) kapsama eşiği denetlenir (bunlar bütün kütüphane
    ölçeğinde anlamlıdır).
    """
    hatalar: list[str] = []
    kayitlar = _kayitlari_oku(yol_veya_liste, hatalar)
    olcumler: dict = {}
    n = len(kayitlar)
    olcumler["kayit_sayisi"] = n
    if n == 0:
        hatalar.append("kütüphane boş")
        return {"gecerli": False, "hatalar": hatalar, "olcumler": olcumler}

    gorulen_idler: set = set()
    tekrar_idler: set = set()
    for i, k in enumerate(kayitlar):
        ad = k.get("id", f"?{i}")
        eksik = REQUIRED_ALANLAR - set(k.keys())
        if eksik:
            hatalar.append(f"kayit {ad}: eksik alan(lar) {sorted(eksik)}")
            continue

        if k["id"] in gorulen_idler:
            tekrar_idler.add(k["id"])
        gorulen_idler.add(k["id"])

        kategori = k["kategori_grubu"]
        if kategori not in KATEGORI_GRUPLARI:
            hatalar.append(f"kayit {ad}: bilinmeyen kategori_grubu {kategori!r}")

        puan = k["puan"]
        if not isinstance(puan, int) or isinstance(puan, bool) or not (1 <= puan <= 5):
            hatalar.append(f"kayit {ad}: gecersiz puan {puan!r}")

        if k["duygu"] not in DUYGULAR:
            hatalar.append(f"kayit {ad}: gecersiz duygu {k['duygu']!r}")

        if k["uslup"] not in USLUPLAR:
            hatalar.append(f"kayit {ad}: gecersiz uslup {k['uslup']!r}")

        if (
            isinstance(puan, int) and not isinstance(puan, bool) and 1 <= puan <= 5
            and k["uslup"] in USLUPLAR and k["duygu"] in DUYGULAR
        ):
            beklenen_duygu = _puan_duygu(puan, k["uslup"])
            if k["duygu"] != beklenen_duygu:
                hatalar.append(
                    f"kayit {ad}: duygu {k['duygu']!r} puan/uslup kuralina uymuyor"
                    f" (beklenen {beklenen_duygu!r})"
                )

        konular = k["konular"]
        if not isinstance(konular, list) or not konular or any(
            kn not in KONULAR for kn in konular
        ):
            hatalar.append(f"kayit {ad}: gecersiz konular {konular!r}")
        elif kategori == AKSESUAR_GRUBU and AKSESUAR_YASAK_KONU in konular:
            hatalar.append(
                f"kayit {ad}: Aksesuar icin yasak konu {AKSESUAR_YASAK_KONU!r}"
            )

        alt = k["alt_kategori"]
        if alt is not None and alt not in _a_sabitler.KATEGORILER.get(kategori, []):
            hatalar.append(
                f"kayit {ad}: alt_kategori {alt!r} kategori_grubu {kategori!r}"
                " icinde degil"
            )

        if isinstance(k.get("metin"), str):
            renkler = renk_adlari_bul(k["metin"])
            if renkler:
                hatalar.append(f"kayit {ad}: gercek renk adi {sorted(set(renkler))}")

        if isinstance(k.get("metin"), str):
            etiketler = beden_etiketleri_bul(k["metin"])
            if etiketler:
                hatalar.append(f"kayit {ad}: gercek beden etiketi {etiketler}")
            gunler = ozel_gun_adlari_bul(k["metin"])
            if gunler:
                hatalar.append(f"kayit {ad}: ozel gun adi {gunler}")

        yer_tutucu = k["yer_tutucu"]
        if not isinstance(yer_tutucu, list) or any(
            y not in YER_TUTUCULAR for y in yer_tutucu
        ):
            hatalar.append(f"kayit {ad}: gecersiz yer_tutucu {yer_tutucu!r}")
        else:
            if kategori == AKSESUAR_GRUBU and AKSESUAR_YASAK_YER_TUTUCU in yer_tutucu:
                hatalar.append(
                    f"kayit {ad}: Aksesuar icin yasak yer_tutucu {AKSESUAR_YASAK_YER_TUTUCU!r}"
                )
            metin_ham = k.get("metin", "")
            for yt in yer_tutucu:
                if "{%s}" % yt not in metin_ham:
                    hatalar.append(f"kayit {ad}: yer_tutucu {yt!r} metinde yok")
            for aday in YER_TUTUCULAR:
                if "{%s}" % aday in metin_ham and aday not in yer_tutucu:
                    hatalar.append(
                        f"kayit {ad}: metinde bildirilmemis yer_tutucu {{{aday}}}"
                    )

    if tekrar_idler:
        hatalar.append(f"tekrarlayan id: {sorted(tekrar_idler)}")

    metin_kayitlari = [
        k for k in kayitlar
        if isinstance(k.get("metin"), str) and k.get("metin", "").strip()
    ]
    metinler = [k["metin"] for k in metin_kayitlari]
    olcumler["metin_dolu_kayit"] = len(metinler)

    if metinler:
        norm_metinler = [_normalize(m) for m in metinler]
        sayac = Counter(norm_metinler)
        tam_tekrar_sayisi = sum(c for c in sayac.values() if c > 1)
        tam_tekrar_orani = tam_tekrar_sayisi / len(metinler)
        olcumler["tam_tekrar_orani"] = tam_tekrar_orani
        if tam_tekrar_orani > TAM_TEKRAR_UST_ORAN:
            hatalar.append(
                f"tam metin tekrar orani {tam_tekrar_orani:.3f} > {TAM_TEKRAR_UST_ORAN}"
            )

        yakin_orani, atlanan = _yakin_tekrar_orani(norm_metinler)
        olcumler["yakin_tekrar_orani"] = yakin_orani
        olcumler["atlanan_yaygin_shingle"] = atlanan
        if atlanan:
            hatalar.append(
                f"{atlanan} yaygin shingle {YAYGIN_SHINGLE_SINIRI}+ kayitta geciyor"
                " (ortak sablon; yakin tekrar taranamadi)"
            )
        if yakin_orani > YAKIN_TEKRAR_UST_ORAN:
            hatalar.append(
                f"yakin tekrar orani {yakin_orani:.3f} > {YAKIN_TEKRAR_UST_ORAN}"
            )

        kelime_sayilari = [len(m.split()) for m in metinler]
        medyan = float(np.median(kelime_sayilari))
        olcumler["kelime_medyani"] = medyan
        alt, ust = UZUNLUK_MEDYAN_ARALIGI
        if not (alt <= medyan <= ust):
            hatalar.append(
                f"kelime medyani {medyan} hedef araligi [{alt},{ust}] disinda"
            )

        normal_metinler = [
            k["metin"] for k in metin_kayitlari if k.get("uslup") != "yazim_hatali"
        ]
        if normal_metinler:
            turkce_var = sum(1 for m in normal_metinler if _TURKCE_DESEN.search(m))
            turkce_orani = turkce_var / len(normal_metinler)
            olcumler["turkce_karakter_orani"] = turkce_orani
            if turkce_orani < TURKCE_KARAKTER_ALT_ORAN:
                hatalar.append(
                    f"turkce karakter orani {turkce_orani:.3f} < {TURKCE_KARAKTER_ALT_ORAN}"
                    " (yazim_hatali disi metinlerde)"
                )

    if n >= tam_esik:
        # Beklenen dağılımlar: kayıtların hepsi bilinen bir slota (ana ya da ek
        # slot dosyası) ait ise hedefler o slotların gerçek dağılımından
        # türetilir (7.000'lik birleşik kütüphane ana 4.000 oranlarından
        # farklıdır); aksi halde (bilinmeyen id'li deneme girdisi) sabit oran
        # hedefleri kullanılır.
        harita = _slot_haritasi()
        slotlar = [
            harita.get(k["id"]) if isinstance(k.get("id"), str) else None
            for k in kayitlar
        ]
        slot_bilinir = all(sl is not None for sl in slotlar)
        bilinmeyen = [k.get("id") for k, sl in zip(kayitlar, slotlar) if sl is None]
        if bilinmeyen:
            hatalar.append(
                f"{len(bilinmeyen)} kayit bilinmeyen id"
                f" (ilk birkaci: {bilinmeyen[:5]!r}); dagilim hedefleri"
                " sabit oranlara dustu"
            )
        if slot_bilinir:
            # kayit-slot esitligi: etiketler kayitin kendi slotuyla ayni olmali
            for k, sl in zip(kayitlar, slotlar):
                for alan in ("kategori_grubu", "puan", "duygu", "konular",
                             "uslup", "yer_tutucu"):
                    if k.get(alan) != sl[alan]:
                        hatalar.append(
                            f"kayit {k.get('id')}: {alan} slotla ayni degil"
                            f" ({k.get(alan)!r} != {sl[alan]!r})"
                        )
            dosyalar = {_slot_dosyasi_boyutu(sl["id"]) for sl in slotlar}
            olcumler["slot_tamlik"] = {
                "kayit": len({sl["id"] for sl in slotlar}),
                "slot": sum(b for _, b in dosyalar),
            }
            puan_beklenen = Counter(sl["puan"] for sl in slotlar)
            uslup_beklenen = Counter(sl["uslup"] for sl in slotlar)
            slot_cift: Counter | None = Counter()
            for sl in slotlar:
                for konu in sl["konular"]:
                    slot_cift[(sl["kategori_grubu"], konu)] += 1
        else:
            puan_beklenen = {p: o * n for p, o in PUAN_ORANI.items()}
            uslup_beklenen = {u: o * n for u, o in USLUP_ORANI.items()}
            slot_cift = None
        olcumler["beklenen_kaynak"] = "slot" if slot_bilinir else "sabit_oran"

        puan_sayim = Counter(k.get("puan") for k in kayitlar)
        for puan in PUAN_ORANI:
            beklenen = puan_beklenen.get(puan, 0)
            gercek = puan_sayim.get(puan, 0)
            if beklenen > 0 and abs(gercek - beklenen) / beklenen > DENGE_TOLERANSI:
                hatalar.append(
                    f"puan {puan} dagilimi hedeften sapiyor: {gercek} (beklenen ~{beklenen:.0f})"
                )
        uslup_sayim = Counter(k.get("uslup") for k in kayitlar)
        for uslup in USLUP_ORANI:
            beklenen = uslup_beklenen.get(uslup, 0)
            gercek = uslup_sayim.get(uslup, 0)
            if beklenen > 0 and abs(gercek - beklenen) / beklenen > DENGE_TOLERANSI:
                hatalar.append(
                    f"uslup {uslup!r} dagilimi hedeften sapiyor: {gercek} (beklenen ~{beklenen:.0f})"
                )

        cift_sayim: Counter = Counter()
        for k in kayitlar:
            for konu in k.get("konular") or []:
                cift_sayim[(k.get("kategori_grubu"), konu)] += 1
        for kategori in KATEGORI_GRUPLARI:
            for konu in _uygulanabilir_konular(kategori):
                sayi = cift_sayim.get((kategori, konu), 0)
                asgari = MIN_KATEGORI_KONU
                if slot_cift is not None:
                    asgari = min(MIN_KATEGORI_KONU, slot_cift.get((kategori, konu), 0))
                if sayi < asgari:
                    hatalar.append(
                        f"({kategori}, {konu}) cifti icin yalniz {sayi} yorum"
                        f" (< {asgari})"
                    )

        olcumler["puan_dagilimi"] = dict(puan_sayim)
        olcumler["uslup_dagilimi"] = dict(uslup_sayim)

    return {"gecerli": len(hatalar) == 0, "hatalar": hatalar, "olcumler": olcumler}


def ornek_metin_yazdir(yol_veya_liste, n: int = 20, tohum: int = CRM_TOHUM) -> list[dict]:
    """Önizleme için `n` rastgele (tohumlu, deterministik) kayıt döner."""
    kayitlar = _kayitlari_oku(yol_veya_liste)
    n = min(n, len(kayitlar))
    if n == 0:
        return []
    rng = np.random.default_rng(tohum)
    secili = rng.choice(len(kayitlar), size=n, replace=False)
    return [kayitlar[i] for i in sorted(int(x) for x in secili)]


# ---------------------------------------------------------------------------
# Görev 11 alt ajanları için yazım yönergesi
# ---------------------------------------------------------------------------

YAZAR_YONERGESI = """\
Yorum kütüphanesi yazım yönergesi (Görev 11)

Sana verilen her "slot" bir etiket kombinasyonudur (kategori_grubu, puan,
duygu, konular, uslup, yer_tutucu). Görevin, bu etiketlere GERÇEKTEN uyan,
doğal bir Türkçe e-ticaret ürün yorumu yazmak — etiketleri metne "yapıştırma",
metin o etiketleri gerçekten taşısın.

Uymanız gereken kurallar:

1. Doğallık: Gerçek bir müşterinin yazdığı bir yorum gibi oku. Marka adı,
   mağaza adı, gerçek kişi adı veya başka kişisel bilgi KULLANMA. Küfür/argo
   yok.
2. Konular: `konular` listesindeki HER konu metinde açıkça (ima değil,
   fark edilir şekilde) geçmeli. Listede olmayan konulardan bahsetme.
3. Duygu ve puan: `duygu` metnin gerçek tonu olmalı. `uslup == "celiskili"`
   olan slotlarda metnin tonu YILDIZ PUANIYLA ÇELİŞİR (ör. puan 5 ama metin
   aslında hayal kırıklığını anlatıyor, ya da puan 1 ama metin övgü dolu) —
   bu kasıtlıdır, düzeltme.
4. Üslup:
   - `kisa`: 1-2 cümle, öz.
   - `uzun`: birkaç cümle, ayrıntılı.
   - `yazim_hatali`: gerçek yazım hataları ve/veya Türkçe karakter eksikliği
     içerir (örn. "begendim", "cok iyi", noktalama eksik) — bu slotlarda
     Türkçe karakter kullanmama serbesttir.
   - `ignelemeli`: iğneleyici/alaycı bir ton (ör. sahte övgüyle eleştiri).
   - `celiskili`: kural 3'teki gibi puanla çelişen ton.
   - `duz`: sade, tarafsız anlatım.
5. Uzunluk: kelime sayısı çoğunlukla 8-20 arasında olsun (kisa/uzun uçları
   dahil makul çeşitlilik).
6. Yer tutucu: `yer_tutucu` alanı doluysa metinde tam olarak `{renk}` ve/veya
   `{beden}` yer tutucusunu KELİMESİ KELİMESİNE kullan (ör. "{renk} rengi tam
   aradığım tondaydı"); listede olmayan yer tutucuyu metne koyma. Aksesuar
   (Çanta, Şal, Kemer) ürünlerinde asla `{beden}` kullanma.
7. Türkçe karakter: `yazim_hatali` dışındaki bütün üsluplarda doğru Türkçe
   karakterleri (ç, ğ, ı, ö, ş, ü, İ) kullan.
8. Çeşitlilik: Aynı parti içinde cümle kalıplarını, kelime seçimini ve açılış
   cümlelerini tekrarlama — kütüphane denetimi (`kutuphane.denetle`) hem tam
   metin tekrarını hem de 5 kelimelik dizilerin örtüştüğü yakın tekrarları
   yakalar; art arda benzer şablonlar reddedilir.
9. Format: yalnız `metin` ve `alt_kategori` alanlarını üret; şemanın diğer
   alanları (id, kategori_grubu, puan, duygu, konular, uslup, yer_tutucu)
   sana slotta verilmiştir, değiştirme.
10. Alt kategori: metin bir ürün türü anıyorsa (ör. "çantanın sapı", "etek
   hoş") `alt_kategori`'yi o ürünün A'daki adına ayarla; yalnız slotun
   `kategori_grubu`'ndaki alt kategorilerden birini anabilirsin (Üst Giyim:
   Tişört, Gömlek, Bluz, Kazak, Sweatshirt; Alt Giyim: Pantolon, Jean, Etek,
   Şort; Elbise & Tulum: Elbise, Tulum; Dış Giyim: Mont, Ceket, Trençkot;
   Aksesuar: Çanta, Şal, Kemer) — başka gruptan ürün adı anma. Eş anlamlılar
   A'nın adına eşlenir (kot→Jean, kaban→Mont); A'da karşılığı olmayan ürün
   adı (hırka, yelek, atkı...) kullanılmaz, gerekirse ürün adı verme. Genel metinde (ürün türü anılmıyorsa) `alt_kategori` null olsun.
11. Renk adı yok: gerçek renk adı verme (siyah, haki, bej, lacivert, sarı...).
   Renk ya `{renk}` yer tutucusuyla anılır ya da adı verilmeden ("rengi",
   "tonu") söylenir.
12. Fiyat/değer: `fiyat_deger` konulu slotlarda ürünün indirimle, kampanyayla
   ya da yarı fiyatına alındığını söyleme (indirim anlatan metin yalnız
   indirimli satırlara atanabildiği için kullanılmaz kalır). Fiyatı ödenen
   bedele göre değerlendir: "bu fiyata değer", "pahalı", "uygun" gibi.
13. Ek parti slotlarında (Y4001–Y7000) `alt_kategori_hedef` alanı yol
   göstericidir: belirli bir alt kategoriyse metin o ürün türünü anar ve
   `alt_kategori` buna göre doldurulur; null ise ürün türü anılmaz
   (`alt_kategori` null). Bu alan kütüphane kaydına yazılmaz.
"""
