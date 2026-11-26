"""Rapor ve demo testleri için sahte girdiler: `oyun.json` (47 koşu ve tahmin isabeti), plan önbelleğinin JSON'ları,
koşuların önbellek `meta.json`'ları, `analiz.json`, `hikaye.json`, demo dosyası (gerçek veri ve koşu yok). Ölçüm
sözlükleri `olcutler.olc`'un, analiz `analiz.kur`'un, hikâye `hikaye.kur`'un şemasındadır; bütün korunum denetimleri
tutar; testler tek bir alanı bozar.

`yaz(tmp_path, g)` girdileri diske yazar ve `rapor.hazirla`'nın anahtar sözcüklerini döndürür.
"""

import copy
import json
from pathlib import Path

import pandas as pd

import rapor
import senaryolar
from kiriklik import oyun, sabitler
from kiriklik.plan import Plan

OLCUM = "o" * 64
ANALIZ = "a" * 64
HIKAYE = "h" * 64
VERI = ["perakende.duckdb", 219164672, 1790588309530439400]
# koşuların meta.json kimliği (`rapor.kosu_kimligi()`'nin sahtesi)
KIMLIK = {"vaka": "v" * 64, "kod": "m" * 64, "veri": VERI, "surumler": {"numpy": "2.5.4", "pandas": "2.3.3"}}
KARAR_KODLARI = {k: (("k" if k == "kahin" else "p") * 64) for k in oyun.KOLLAR}
PULP = oyun._surum("pulp")
TARIH = {"AW24": {"karar": "2024-12-09", "indirim": "2025-01-02", "cikis": "2025-02-24", "outlet_sonu": "2025-05-19",
                  "son_gun": "2025-12-31"},
         "SS25": {"karar": "2025-06-02", "indirim": "2025-06-30", "cikis": "2025-08-25", "outlet_sonu": "2025-11-17",
                  "son_gun": "2025-12-31"}}
KESIT_TARIHI = {"AW24": ("2024-12-09", "2024-12-16", "2024-12-30", "2025-02-17"),
                "SS25": ("2025-06-02", "2025-06-09", "2025-06-23", "2025-08-18")}
# kol → (adet, rota, kırık beden azalışı, saha dönüşü, etki oranı, ciro farkı TL)
KOL = {"kural": (550, 310, 260, 0.62, 0.30, 90_000.0), "kural_28": (520, 300, 230, 0.58, 0.27, 70_000.0),
       "opt": (2_100, 270, 420, 0.70, 0.45, 600_000.0), "opt_set": (1_070, 320, 380, 0.66, 0.38, 330_000.0),
       "kahin": (2_000, 250, 450, 0.75, 0.52, 720_000.0)}
SEZON_CARPANI = {"AW24": 1.0, "SS25": 0.8}


def anahtar(ad: str) -> str:
    return f"{ad:_<20}"[:20] + "x" * 44


def kimlik(ad: str) -> str:
    return f"{ad:_<20}"[:20] + "i" * 44


def _ozet(stoklu: int, kirik_cift: int, kirik_beden: int, eksik: int) -> dict:
    beden, asorti = 5 * stoklu, 7 * stoklu
    return {"stoklu_cift": stoklu, "kirik_cift": kirik_cift, "dar_kirik_cift": int(kirik_cift * 0.75),
            "kirik_beden": kirik_beden, "beden": beden, "eksik_adet": eksik, "asorti": asorti,
            "net_oran": kirik_beden / beden, "brut_oran": eksik / asorti, "kirik_cift_oran": kirik_cift / stoklu}


def _kapsam(stoklu: int, kirik_beden: int, azalis: int) -> dict:
    lum = _ozet(stoklu, kirik_beden // 2, kirik_beden, int(kirik_beden * 1.4))
    kol = _ozet(stoklu, (kirik_beden - azalis) // 2, kirik_beden - azalis, int((kirik_beden - azalis) * 1.4))
    fark = {m: kol[m] - lum[m] for m in ("kirik_beden", "kirik_cift", "stoklu_cift", "eksik_adet")}
    biten, gelen = -(abs(azalis) // 3), 7 if azalis else 0        # üçlü farka eşit (olcutler.kiriklik_ayrisimi)
    return {"kol": kol, "lumoda": lum, "fark": fark,
            "ayrisim": {"ortak": fark["kirik_beden"] - biten - gelen, "kolda_biten": biten, "lumodada_biten": gelen,
                        "kolda_biten_cift": abs(biten) // 2, "lumodada_biten_cift": 3 if azalis else 0}}


def _pencereli(t: float, i: float, o: float) -> dict:
    return {"tam": t, "indirim": i, "outlet": o, "toplam": t + i + o}


def olcum(kol: str, sezon: str, yol: int = 0) -> dict:
    adet, rota, azalis, saha, etki, ciro = KOL[kol]
    c = SEZON_CARPANI[sezon] * (1 - 0.03 * yol)
    adet, azalis, ciro = int(adet * c), int(azalis * c), ciro * c
    kesitler = {}
    for i, (ad, gun) in enumerate(zip(("karar", "varis_sonrasi", "indirim_oncesi", "cikis_oncesi"), KESIT_TARIHI[sezon])):
        a = 0 if ad == "karar" else azalis - 20 * i
        kesitler[ad] = {"tarih": gun, "kapsamlar": {
            "transfer_edilen_alici": _kapsam(400, 900, a), "transfer_edilen_verici": _kapsam(500, 1_100, -a // 5),
            "transfer_edilen": _kapsam(900, 2_000, a - a // 5), "butun": _kapsam(4_000, 4_100 + 50 * i, a - a // 5)}}
    alinan = adet
    ind, cik = int(alinan * saha * 0.7), int(alinan * saha)
    e_toplam = int(adet * etki)
    etki_adet = _pencereli(int(e_toplam * 0.6), int(e_toplam * 0.3), e_toplam - int(e_toplam * 0.6) - int(e_toplam * 0.3))
    maliyet, net = {}, {}
    alis = 280.0 * adet
    for p, pk in sabitler.MALIYET_PAKETLERI.items():
        m = {"toplama": pk.toplama_birim_tl * adet, "kargo": pk.kargo_rota_tl * rota, "yipranma": pk.yipranma_orani * alis}
        m["toplam"] = m["toplama"] + m["kargo"] + m["yipranma"]
        maliyet[p] = m
        net[p] = ciro - m["toplam"]
    ciro_kol = _pencereli(20e6 + ciro * 0.7, 9e6 + ciro * 0.2, 3e6 + ciro * 0.1)
    ciro_lum = _pencereli(20e6, 9e6, 3e6)
    stok_alt = lambda a: {"magaza_adet": a, "depo_adet": 2 * a, "adet": 3 * a, "liste": 3 * a * 700.0, "alis": 3 * a * 280.0}
    return {
        "sezon": sezon, "tarihler": TARIH[sezon], "kiriklik": kesitler,
        "satisa_donus": {"alinan_adet": alinan, "indirime_satilan": ind, "cikisa_satilan": cik,
                         "saha_indirime": ind / alinan, "saha_cikisa": cik / alinan, "etki_adet": etki_adet,
                         "etki_adet_fiziksel": {p: int(x * 0.9) for p, x in etki_adet.items()},
                         "etki_oran": e_toplam / adet, "vericide_kayip_adet": -int(adet * 0.2),
                         "alicida_kazanc_adet": int(adet * 0.5)},
        "para": {"ciro": {k: {"kol": ciro_kol, "lumoda": ciro_lum,
                              "fark": {p: ciro_kol[p] - ciro_lum[p] for p in ciro_kol}}
                          for k in ("transfer_edilen", "sezon")},
                 "brut_kar_farki": {"transfer_edilen": ciro * 0.6, "sezon": ciro * 0.6}, "tasinan_alis": alis,
                 "maliyet": maliyet, "net": net},
        "stok": {k: {"cikista_kalan": {"kol": stok_alt(900), "lumoda": stok_alt(1_000),
                                       "fark": {a: stok_alt(900)[a] - stok_alt(1_000)[a] for a in stok_alt(1)}},
                     "outlete_giden": {"kol": {"adet": 1_500, "liste": 1e6, "alis": 4e5},
                                       "lumoda": {"adet": 1_600, "liste": 1.1e6, "alis": 4.4e5},
                                       "fark": {"adet": -100, "liste": -1e5, "alis": -4e4}},
                     "olu_stok": {"kol": {"adet": 300, "alis": 9e4}, "lumoda": {"adet": 320, "alis": 9.6e4},
                                  "fark": {"adet": -20, "alis": -6e3}}}
                 for k in ("transfer_edilen", "sezon")} | {"tarihler": {"cikis_fotografi": KESIT_TARIHI[sezon][3],
                                                                        "olu_stok": "2025-06-23"}},
        "yan_etki": {"replenishment_adet_farki": {"sezon": -40, "tum": -35},
                     "elle_transfer_adet_farki": {"sezon": -3, "tum": -2}, "gizli_kayip_farki": -int(adet * 0.3),
                     "gizli_kayip_lumoda": 50_000, "test_disi_ciro_farki": 12_000.0, "test_disi_ciro_lumoda": 3e8,
                     "surekli_siparis_adet_farki": 4},
        "plan": {"hareket": int(adet * 0.8), "adet": adet, "rota": rota, "option": 80, "alici_cift": 200,
                 "alici_magaza": 60, "verici_cift": 500, "verici_magaza": 66, "tamamlanan_set": 190,
                 "alici_basina_verici_medyan": 2.0, "rota_basina_adet_medyan": adet / rota,
                 "cozucu": {} if kol.startswith("kural") else {"durum": "optimal", "gap": 0.011, "kaynak": "daraltilmis"},
                 **plan_kaynagi(kol, adet, rota)},
    }


def plan_kaynagi(kol: str, adet: int, rota: int) -> dict:
    """`olcutler.plan_kaynagi` şeması: kural ailesi kırık setlerden, opt ailesi çoğunlukla tam setlerden alır."""
    tam = 0 if kol.startswith("kural") else int(adet * 0.9)
    return {"tam_setten_adet": tam, "tam_setten_pay": tam / adet, "tam_set_verici_cift": 0 if not tam else 350,
            "verici_hucre": 690, "sifirlanan_hucre": 300 if not tam else 4, "tam_set_verici_hucre": 0 if not tam else 600,
            "tam_sette_sifirlanan_hucre": 0 if not tam else 2, "rota_tek_adet": rota // 2}


HAREKET = ["option_id", "urun_id", "beden_sira", "verici", "alici", "adet"]
ORTUSME = {("opt", "AW24"): [("O", "O-1", 1, "V1", "A", 3), ("O", "O-2", 2, "V2", "A", 1)],
           ("kahin", "AW24"): [("O", "O-1", 1, "V2", "A", 2), ("O", "O-2", 2, "V2", "A", 1), ("O", "O-1", 1, "V1", "B", 2)],
           ("opt", "SS25"): [("P", "P-1", 1, "V1", "A", 2)], ("kahin", "SS25"): [("P", "P-1", 1, "V1", "A", 2)]}


def ortusme_plani(kol: str, sezon: str) -> Plan:
    return Plan(kol=kol, sezon=sezon, hareketler=pd.DataFrame(ORTUSME[(kol, sezon)], columns=HAREKET))


def plan_bilgisi(kol: str) -> dict:
    if kol.startswith("kural"):
        return {"pencereler": ["std", 7, 14, 28] if kol == "kural" else [28], "cozum": "kural",
                "tamamlanan_alicilar": [[f"O{i}", "M1"] for i in range(200)],
                "atlanan_alicilar": [[f"O{i}", "M2"] for i in range(330)], "puan_sayisi": 13_000}
    return {"cozum": "model", "durum": "optimal", "kaynak": "kok" if kol == "opt_set" else "daraltilmis",
            "gap": 0.017 if kol == "opt_set" else 0.011, "gap_lp": 0.09 if kol == "opt_set" else 0.011,
            "sinir": 1.0e6, "amac": 0.99e6, "rota_sayisi": KOL[kol][1], "alici_sayisi": 700}


def isabet(c: float) -> dict:
    def alan(t, k):
        return {"tahmin": t, "kahin": k, "wape": 0.42, "yanlilik": t / k - 1}
    b = {"hucre": 30_000, "mu_tam": alan(9_000 * c, 8_000.0), "mu_ind": alan(11_000 * c, 10_000.0),
         "toplam": alan(20_000 * c, 18_000.0)}
    a = {"hucre": 1_500, "mu_tam": alan(900 * c, 700.0), "mu_ind": alan(1_100 * c, 1_000.0),
         "toplam": alan(2_000 * c, 1_700.0)}
    return {"butun": b, "alici": a, "alici_hucre": 1_500}


def oyun_kaydi() -> dict:
    lumoda, kosular = {}, {}
    for i in oyun.izgara_listesi():
        if i.kol == oyun.LUMODA:
            lumoda[str(i.yol)] = {"ad": i.ad, "anahtar": anahtar(i.ad), "talep_tohumu": None if i.yol == 0 else 7 + i.yol}
            continue
        kosular[i.ad] = {"ad": i.ad, "kol": i.kol, "sezon": i.sezon, "yol": i.yol, "anahtar": anahtar(i.ad),
                         "lumoda_anahtari": anahtar(oyun.kosu_adi(oyun.LUMODA, None, i.yol)),
                         "plan_kimligi": ortusme_plani(i.kol, i.sezon).kimlik if (i.kol, i.sezon) in ORTUSME and i.yol == 0
                         else kimlik(i.ad), "olcum_ozeti": OLCUM,
                         "korunum": dict.fromkeys(rapor.KORUNUM_KOSULLARI, True), "gecerli": True,
                         "olcum": olcum(i.kol, i.sezon, i.yol)}
    tahmin = {str(p): {z: {"lumoda_anahtari": lumoda[str(p)]["anahtar"],
                           "plan_kimligi": kosular[oyun.kosu_adi("opt", z, p)]["plan_kimligi"],
                           "olcum_ozeti": OLCUM, "karar_kodu": KARAR_KODLARI["kahin"], "gecerli": True,
                           "isabet": isabet(1.1 + 0.05 * p if z == "AW24" else 1.25)}
                       for z in sabitler.TEST_SEZONLARI} for p in oyun.YOLLAR}
    return {"olcek": "tam", "lumoda": lumoda, "kosular": kosular, "tahmin": tahmin}


def _hafta(h: int, stoklu: int, kirik_beden: int) -> dict:
    oz = _ozet(stoklu, kirik_beden // 2, kirik_beden, int(kirik_beden * 1.45))
    atil = {s: {"n": n, "adet": 4 * n, "alis": 4 * n * 290.0} for s, n in
            (("satmayan", 200), ("atil", 500), ("satan", 3_000), ("yeni", 0))}
    return {"tarih": f"2024-12-{9 + h:02d}" if h >= 0 else "2024-11-25", "hafta": h, "hafta_lansman": 16 + h,
            "butun": oz, "tip": {"AVM": oz, "Cadde": oz},
            "atil": {"cift": {f"x{x}": copy.deepcopy(atil) for x in sabitler.ATIL_DUYARLILIK}, "sku": copy.deepcopy(atil),
                     "kirik_atil": {"kirik": copy.deepcopy(atil), "tam": copy.deepcopy(atil)},
                     "kirik_atil_kalan": {"kirik": copy.deepcopy(atil), "tam": copy.deepcopy(atil)}}}


def analiz_kaydi() -> dict:
    sezon, huni = {}, {}
    for z in ("AW23", "SS24", "AW24", "SS25"):
        hf = [_hafta(h, 4_000, 3_000 + 200 * (h + 4)) for h in range(-4, 2)]
        ref = hf[1]
        if z in sabitler.TEST_SEZONLARI:            # karar sabahı = yol 0 Lumoda'nın karar fotoğrafı (rapor denetler)
            ref["butun"] = olcum("kural", z)["kiriklik"]["karar"]["kapsamlar"]["butun"]["lumoda"]
        sezon[z] = {"gunler": {"lansman": "2024-08-19", "indirim": "2025-01-02", "cikis": "2025-02-24",
                               "referans": "2024-12-09"}, "indirime_gun": 24, "haftalik": hf,
                    "referans": {"tarih": ref["tarih"], "hafta": ref["hafta"], "butun": ref["butun"], "tip": ref["tip"],
                                 "beden_sirasi": [{"beden_sira": i, "asorti": a, "kirik_cift": 700 + 10 * i,
                                                   "pay": (700 + 10 * i) / 4_000, "eksik_adet": a * (700 + 10 * i)}
                                                  for i, a in enumerate(sabitler.ASORTI, start=1)]}}
    for z in sabitler.TEST_SEZONLARI:
        oz = sezon[z]["referans"]["butun"]
        huni[z] = {"karar": TARIH[z]["karar"], "indirime_gun": 24, "ozet": oz,
                   "basamaklar": [{"ad": a, "cift": n, "option": o} for a, n, o in
                                  (("stoklu", oz["stoklu_cift"], 181), ("kirik", oz["kirik_cift"], 181),
                                   ("depoda_yok", 1_126, 145), ("acik_siparis_yok", 819, 115), ("magaza_uygun", 819, 115))],
                   "neden": {"uygun": 819, "depoda_var": oz["kirik_cift"] - 1_126, "acik_siparis": 307, "magaza": 0},
                   "kesif": {"option": 181, "magaza": 69, "sku": 905, "sku_depolu": 392, "option_deposuz": 42,
                             "option_toplam": 181, "option_basina_stoklu_medyan": 23.0, "option_basina_kirik_medyan": 10.0,
                             "son28_esik": 6, "son28_esik_ustu": 3_510, "magaza_fiziksel": 74, "magaza_uygun": 69}}
    return {"surum": 1, "olcek": "tam", "kod": ANALIZ, "kaynak": "yayimlanan", "veri": VERI,
            "veri_gunleri": {"ilk": "2023-01-01", "son": "2025-12-31"}, "sezonlar": ["AW23", "SS24", "AW24", "SS25"],
            "onceki": {"AW24": "AW23", "SS25": "SS24"}, "sezon": sezon, "huni": huni}


def hikaye_kaydi(o: dict) -> dict:
    r = o["kosular"]["kural_AW24"]
    aday = {"alici": "M005", "option_id": "MDL0442-HAK", "alinan": 6, "sehir": "İstanbul", "verici": 4,
            "verici_istanbul_disi": 3, "verici_sehir_disi": 3, "kirik_beden": 2, "depo_bos": True, "lumoda_kirik": True}
    return {"surum": 1, "kod": HIKAYE, "olcek": "tam", "sezon": "AW24", "kol": "kural", "yol": 0,
            "kosu": {"ad": "kural_AW24", "anahtar": r["anahtar"]}, "lumoda_anahtari": o["lumoda"]["0"]["anahtar"],
            "plan_kimligi": r["plan_kimligi"], "olcum_ozeti": OLCUM, "alici_cift": 200, "seviye": "tam",
            "seviyeler": {"tam": 4, "iki_verici": 9, "sehir_disi": 30},
            "adaylar": [aday, {**aday, "alici": "M007", "alinan": 5}],
            "sahne": {"option": {"option_id": "MDL0442-HAK", "model_adi": "Kaşe Kaban", "renk": "Haki",
                                 "alt_kategori": "Kaban", "liste_fiyati": 2_499.99},
                      "alici": {"magaza_id": "M005", "ad": "İstanbul 5", "sehir": "İstanbul"},
                      "vericiler": [{"magaza_id": f"M04{i}", "ad": f"Konya {i}", "sehir": "Konya", "adet": 2 if i == 0 else 1,
                                     "bedenler": {0: {"M": 1, "L": 1}, 1: {"L": 1}}.get(i, {"M": 1}),
                                     "varis_gun": (1, 1, 2, 4, 4)[i],
                                     "lumoda": ({"L": {"adet": 1, "ilk_gun": 3, "ilk_fiyat": 1629.99},
                                                 "M": {"adet": 0, "ilk_gun": None, "ilk_fiyat": None}} if i == 0
                                                else {"M": {"adet": 2, "ilk_gun": 30, "ilk_fiyat": 1140.99}})}
                                    for i in range(5)],
                      "karar": {"bedenler": {"XS": 1, "S": 1, "M": 0, "L": 0, "XL": 1},
                                "asorti": {"XS": 1, "S": 2, "M": 2, "L": 1, "XL": 1}, "kirik_bedenler": ["M", "L"],
                                "kirik_depo": {"M": 0, "L": 0}},
                      "alinan": 6, "alinan_bedenler": {"M": 4, "L": 2}, "en_erken_varis_gun": 1, "en_gec_varis_gun": 4,
                      "butce": {"alici": {"adet": 5, "tl": 8150.2}, "vericiler": {"adet": -5, "tl": -6683.1},
                                "net": {"adet": 0, "tl": 1467.1}, },
                      "kargo": {"rota": 5, "dusuk": 1500.0, "orta": 2500.0},
                      "satis_indirime": {"kural": {"alinan_sku": 4, "option": 6}, "lumoda": {"alinan_sku": 0, "option": 2}},
                      "saha_indirime": 4,
                      "indirim_oncesi": {"kural": {"bedenler": {"XS": 1, "S": 1, "M": 1, "L": 0, "XL": 1}, "kirik": True,
                                                   "kirik_bedenler": ["L"], "stok": 4},
                                         "lumoda": {"bedenler": {"XS": 1, "S": 0, "M": 0, "L": 0, "XL": 1}, "kirik": True,
                                                    "kirik_bedenler": ["S", "M", "L"], "stok": 2}},
                      "tarihler": {"karar": "2024-12-09", "indirim": "2025-01-02", "indirim_oncesi": "2024-12-30"},
                      "indirime_gun": 24, "indirim_oncesi_gun": 21}}


def girdiler() -> dict:
    """Her çağrıda bağımsız bir kopya (testler bir alanı bozar)."""
    o = oyun_kaydi()
    return copy.deepcopy({"oyun": o, "analiz": analiz_kaydi(), "hikaye": hikaye_kaydi(o)})


def plan_json(r: dict, kod: str) -> dict:
    icerik = {"kol": r["kol"], "sezon": r["sezon"], "yol": r["yol"], "olcek": "tam",
              "lumoda_anahtari": r["lumoda_anahtari"], "kod": kod, "pulp": PULP}
    bilgi = plan_bilgisi(r["kol"]) | {"girdi": {"yol": r["yol"], "lumoda_anahtari": r["lumoda_anahtari"]}}
    return {"anahtar": oyun.plan_anahtari(icerik), "icerik": icerik, "kimlik": r["plan_kimligi"], "kol": r["kol"],
            "sezon": r["sezon"], "bilgi": bilgi}


def yaz(tmp_path: Path, g: dict | None = None, *, demo: bool = True, metalar: dict | None = None,
        planlar: dict | None = None) -> dict:
    """Girdileri `tmp_path`'e yazar; `rapor.hazirla`'nın anahtar sözcükleri. `metalar`: koşu adı → `meta.json`,
    `planlar`: koşu adı → plan JSON'u (verilmeyenler kurallı)."""
    g = girdiler() if g is None else copy.deepcopy(g)
    cikti = Path(tmp_path) / "cikti"
    onbellek, plan_dizini = cikti / "kosular", cikti / "planlar"
    for d in (cikti, onbellek, plan_dizini):
        d.mkdir(parents=True, exist_ok=True)
    for ad in ("oyun", "analiz", "hikaye"):
        if g.get(ad) is not None:
            (cikti / f"{ad}.json").write_text(json.dumps(g[ad], ensure_ascii=False), encoding="utf-8")
    o = g["oyun"]
    kayitlar = [e for e in list(o["kosular"].values()) + list(o["lumoda"].values()) if e.get("anahtar")]
    for e in kayitlar:
        d = onbellek / f"{e['ad']}_{e['anahtar'][:20]}"
        d.mkdir(parents=True, exist_ok=True)
        m = (metalar or {}).get(e["ad"]) or {"anahtar": e["anahtar"], **KIMLIK}
        (d / "meta.json").write_text(json.dumps(m), encoding="utf-8")
    for r in o["kosular"].values():
        pj = (planlar or {}).get(r["ad"]) or plan_json(r, KARAR_KODLARI[r["kol"]])
        kok = plan_dizini / f"{r['kol']}_{r['sezon']}_y{r['yol']}_{pj['anahtar'][:20]}"
        kok.with_suffix(".json").write_text(json.dumps(pj, ensure_ascii=False), encoding="utf-8")
        if r["yol"] == 0 and (r["kol"], r["sezon"]) in ORTUSME:
            ortusme_plani(r["kol"], r["sezon"]).hareketler.to_parquet(kok.with_suffix(".parquet"), index=False)
    demo_yol = Path(tmp_path) / f"{senaryolar.DIZI}.json"
    if demo:
        senaryolar.yaz(senaryolar.uret(o), demo_yol)
    return {"cikti": cikti, "demo_yol": demo_yol, "onbellek": onbellek, "planlar": plan_dizini, "olcum_kodu": OLCUM,
            "analiz_kodu": ANALIZ, "hikaye_kodu": HIKAYE, "karar_kodlari": KARAR_KODLARI, "kimlik": KIMLIK}
