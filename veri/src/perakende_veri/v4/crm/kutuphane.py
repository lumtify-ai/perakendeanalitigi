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
    "yer_tutucu", "uslup",
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
        puan_sayim = Counter(k.get("puan") for k in kayitlar)
        for puan, oran in PUAN_ORANI.items():
            beklenen = oran * n
            gercek = puan_sayim.get(puan, 0)
            if beklenen > 0 and abs(gercek - beklenen) / beklenen > DENGE_TOLERANSI:
                hatalar.append(
                    f"puan {puan} dagilimi hedeften sapiyor: {gercek} (beklenen ~{beklenen:.0f})"
                )
        uslup_sayim = Counter(k.get("uslup") for k in kayitlar)
        for uslup, oran in USLUP_ORANI.items():
            beklenen = oran * n
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
                if sayi < MIN_KATEGORI_KONU:
                    hatalar.append(
                        f"({kategori}, {konu}) cifti icin yalniz {sayi} yorum"
                        f" (< {MIN_KATEGORI_KONU})"
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
9. Format: yalnız `metin` alanının içeriğini üret; şemanın diğer alanları
   (id, kategori_grubu, puan, duygu, konular, uslup, yer_tutucu) sana
   slotta verilmiştir, değiştirme.
"""
