"""test_rapor'un sahte girdileri: `rapor_b.Veri`'nin eksiksiz, korunumu tutan bir örneği (gerçek veri
yok, koşu yok). Sayılar uydurmadır; yalnız raporun biçimini, bölümlerini ve denetimlerini sınar."""

import copy
import dataclasses

import numpy as np
import pandas as pd

import rapor_b
import senaryolar
from allocation import oyun, sabitler

U_ADET = 824_165
KIRPILAN = 14_357
TAVAN_KALAN = 100_000
ES_T = round(TAVAN_KALAN / U_ADET, 3)          # eşleşik tutma: tavanlının depoda bıraktığı pay
KAL = {
    "sezon": "SS24", "karar_gunu": "2024-02-09", "en_az": 80, "tavan": True, "gamma": 2.0, "tbar": 0.3,
    "belirsizlik_taban": "tahmin", "belirsizlik_olcusu": "benzer_tahmin_ayrisma", "belirsizlik_spearman": 0.1067,
    "kaynak": "tahmin", "izgara_ucunda": ["en_az"], "gamma_bulunabilirlik_araligi_puan": 0.0316,
    "gamma_kalan_araligi_puan": 0.1756, "gamma_esik_puan": 0.3,
    "hiyerarsi": [["alt_kategori", "fiyat_segmenti", "kalip"], ["alt_kategori"], []],
    "tahmin_parametreleri": {"num_leaves": 63, "learning_rate": 0.05, "n_estimators": 400, "min_child_samples": 100},
    "cevrimdisi": [
        {"asama": "taban", "aday": "lumoda", "wape": 0.2363, "n_option": 210, "secildi": False, "en_az": None,
         "num_leaves": None, "min_child_samples": None, "spearman": None},
        {"asama": "taban", "aday": "esit", "wape": 0.2924, "n_option": 210, "secildi": False, "en_az": None,
         "num_leaves": None, "min_child_samples": None, "spearman": None},
        {"asama": "benzer", "aday": "en_az=40", "wape": 0.2350, "n_option": 210, "secildi": False, "en_az": 40.0,
         "num_leaves": None, "min_child_samples": None, "spearman": None},
        {"asama": "benzer", "aday": "en_az=80", "wape": 0.2347, "n_option": 210, "secildi": True, "en_az": 80.0,
         "num_leaves": None, "min_child_samples": None, "spearman": None},
        {"asama": "tahmin", "aday": "63/100", "wape": 0.1968, "n_option": 210, "secildi": True, "en_az": None,
         "num_leaves": 63.0, "min_child_samples": 100.0, "spearman": None},
        {"asama": "tahmin", "aday": "31/100", "wape": 0.1973, "n_option": 210, "secildi": False, "en_az": None,
         "num_leaves": 31.0, "min_child_samples": 100.0, "spearman": None},
        {"asama": "belirsizlik", "aday": "benzer_dk", "wape": None, "n_option": 210, "secildi": False, "en_az": None,
         "num_leaves": None, "min_child_samples": None, "spearman": -0.03},
        {"asama": "belirsizlik", "aday": "benzer_duzey", "wape": None, "n_option": 210, "secildi": False,
         "en_az": None, "num_leaves": None, "min_child_samples": None, "spearman": None},
        {"asama": "belirsizlik", "aday": "benzer_tahmin_ayrisma", "wape": None, "n_option": 210, "secildi": True,
         "en_az": None, "num_leaves": None, "min_child_samples": None, "spearman": 0.1067},
    ],
    "simulasyon": [
        {"ad": "lumoda", "bulunabilirlik": 73.05, "sezon_sonu_kalan_yuzde": 24.17, "secildi": False, "t_en_az": None},
        {"ad": "kal_benzer_tavanli", "bulunabilirlik": 74.89, "sezon_sonu_kalan_yuzde": 23.18, "secildi": False,
         "t_en_az": None},
        {"ad": "kal_benzer_tavansiz", "bulunabilirlik": 73.18, "sezon_sonu_kalan_yuzde": 24.37, "secildi": False,
         "t_en_az": None},
        {"ad": "kal_tahmin_tavanli", "bulunabilirlik": 75.54, "sezon_sonu_kalan_yuzde": 24.55, "secildi": True,
         "t_en_az": None},
        {"ad": "kal_tahmin_tavansiz", "bulunabilirlik": 74.24, "sezon_sonu_kalan_yuzde": 23.76, "secildi": False,
         "t_en_az": None},
        {"ad": "kal_belirsizlik_g2", "bulunabilirlik": 75.73, "sezon_sonu_kalan_yuzde": 24.32, "secildi": True,
         "t_en_az": 0.04, "t_en_cok": 0.58},
    ],
}


def _olcutler(i: int) -> dict:
    """Bütün ölçüt alanları; i koşudan koşuya küçük farklar verir."""
    o = {"bulunabilirlik": 68.97698 + 0.137 * i, "bulunabilirlik_ilk4": 96.4695 + 0.01 * i, "talep_adet": 1_602_767.0,
         "satis_adet": 1_040_137.0 + 1000 * i, "kayip_orani": 35.1037 - 0.1 * i, "ikame_payi": 26.84,
         "kalici_kayip_orani": 25.68, "toplam_mal": 1_515_866.0, "rpt_adet": 343_680.0 + 500 * i,
         "kalan_magaza_adet": 147_142.0, "kalan_depo_adet": 152_556.0, "kalan_depo_ek_adet": 489.0,
         "sezon_sonu_kalan_yuzde": 19.7707 - 0.11 * i, "ilk_dagitim_adet": float(U_ADET),
         "replenishment_adet": 370_692.0 + 100 * i, "elle_transfer_adet": 3551.0, "tam_fiyat_str": 52.6934 + 0.07 * i,
         "markdown_tl_fiziksel": 39_176_516.53, "markdown_tl_online": 9_956_615.02, "markdown_tl": 49_133_131.55 - 1000 * i,
         "brut_kar_tl_fiziksel": 462_538_117.09, "brut_kar_tl_online": 71_894_987.97,
         "brut_kar_tl": 534_433_105.06 + 10_000 * i, "online_satis": 237_708.0 + 10 * i, "pay_wape": 0.2347 - 0.003 * i,
         "ilk_hucre": 5351.0, "oturan_hucre": 1065.0, "hizli_biten_hucre": 230.0, "kirpilan_adet": 0.0,
         "tavan_baglayan": 0.0, "tavan_kalan_adet": 0.0, "adaysiz_option": 0.0, "stoklu_cift_gun": 665_135.0,
         "kirik_cift_pay_yuzde": 25.27, "beden_kayip_payi": 42.31 - 0.2 * i, "tukenen_hucre_yuzde": 80.92}
    for b, (d, a, t) in enumerate(((0.0, 1.76, 25.7), (9.08, 10.7, 8.4), (37.49, 38.6, 9.7), (58.33, 59.07, 31.1),
                                   (16.64, 18.12, 25.06)), start=1):
        o.update({f"depoda_kalan_beden_{b}": d, f"alimdan_kalan_beden_{b}": a, f"ilk_tukenen_beden_{b}": t})
    return o


def _secim() -> dict:
    return {"kol": "tahmin", "tavan": False, "ad": "pay_tahmin_tavansiz", "esik_puan": 0.3, "kural": "kural metni",
            "adaylar": [{"ad": "pay_benzer_tavansiz", "kol": "benzer", "bulunabilirlik": 69.51, "sezon_sonu_kalan_yuzde": 19.65},
                        {"ad": "pay_tahmin_tavansiz", "kol": "tahmin", "bulunabilirlik": 70.41,
                         "sezon_sonu_kalan_yuzde": 17.74}]}     # Ruling R43: tavansız en iyi


def _kosular(secim: dict) -> dict:
    kosular = {}
    for i, (blok, kosumlar) in enumerate(oyun.IZGARA.items()):
        for j, k in enumerate(kosumlar):
            if k.tutma_kaynagi is not None:                  # eşleşik tutma: kos_hepsi'nin çözdüğü t
                k = dataclasses.replace(k, tutma=ES_T)
            c = oyun.cozumle(k, KAL, secim)
            o = _olcutler(len(kosular))
            if c["kol"] == "lumoda":
                o["kirpilan_adet"] = float(KIRPILAN)
            elif c["tavan"]:
                o["tavan_kalan_adet"], o["ilk_dagitim_adet"] = float(TAVAN_KALAN), float(U_ADET - TAVAN_KALAN)
                o["tavan_baglayan"] = 4000.0
            if c["tutma"]:
                o["ilk_dagitim_adet"] = float(round(U_ADET * (1 - c["tutma"])))
                o["tavan_kalan_adet"] = 0.0
            if c["kol"] == "belirsizlik":
                o["ilk_dagitim_adet"] = float(round(U_ADET * 0.7))
            if c["takvim"]:
                o["rpt_adet"], o["toplam_mal"] = 343_680.0, 1_515_866.0
            kosular[k.ad] = {"grup": blok, "kosum": {"ad": k.ad}, "cozum": c, "imza": oyun.imza(c),
                             "anahtar": f"{len(kosular):04d}" + "a" * 60, "olcum_kodu": "olcum", "olcutler": o}
    kosular["lumoda_takvimli"]["olcutler"] = copy.deepcopy(kosular["lumoda"]["olcutler"])
    for ad, taban in (("tut_eniyi_t00", "pay_tahmin_tavansiz"), ("demo_tahmin_t15", "tut_eniyi_t15"),
                      ("demo_tahmin_t30", "tut_eniyi_t30")):
        kosular[ad] = {**kosular[taban], "grup": kosular[ad]["grup"], "ayni": taban}
    return kosular


def _hucreler() -> pd.DataFrame:
    """Lumoda'nın ilk dağıtımının sahte hücreleri: sahne option'ı (taşan, biten) + dolgu (toplam 5.351)."""
    sahne = pd.DataFrame({
        "option_id": ["MDL0553-IND"] * 3, "ad": ["Bodycon Elbise İndigo"] * 3, "ust_kategori": ["Elbise & Tulum"] * 3,
        "magaza_id": ["M029", "M069", "M001"], "adet": [448, 112, 3808],
        "varis": pd.to_datetime(["2025-03-17"] * 3), "magaza": ["İzmir 4", "Erzurum 2", "İstanbul 1"],
        "veli": [True, True, False], "satis_28": [33, 228, 1000], "satis_14": [16, 102, 3000],
        "plan_sirasi": [1, 24, 2]})
    n = 5351 - 3
    rng = np.random.default_rng(0)
    adet = rng.integers(50, 300, n)
    dolgu = pd.DataFrame({
        "option_id": [f"O{i % 207:03d}" for i in range(n)], "ad": "Ürün", "ust_kategori": "Üst Giyim",
        "magaza_id": [f"M{i // 207:03d}" for i in range(n)], "adet": adet, "varis": pd.Timestamp("2025-02-10"),
        "magaza": "Mağaza", "veli": True, "satis_28": (adet * 0.5).astype(int), "satis_14": (adet * 0.3).astype(int),
        "plan_sirasi": 5})
    otur = 1065 - 1                                                     # sahnede taşan oturan
    dolgu.loc[: otur - 1, "satis_28"] = 0
    hizli = 230 - 1                                                     # sahnede biten hızlı
    sec = slice(otur, otur + hizli - 1)
    dolgu.loc[sec, "satis_14"] = dolgu.loc[sec, "adet"]
    dolgu.loc[sec, "satis_28"] = dolgu.loc[sec, "adet"]
    h = pd.concat([sahne, dolgu], ignore_index=True)
    g = h.groupby("option_id")["adet"]
    h["toplam"], h["magaza_sayisi"] = g.transform("sum"), g.transform("size")
    h["pay_sirasi"] = g.rank(method="min", ascending=False).astype(np.int64)
    h["kol_adet"] = 0
    return h


def _hikaye(kosular: dict) -> dict:
    a = {"option_id": "MDL0553-IND", "ad": "Bodycon Elbise İndigo", "ust_kategori": "Elbise & Tulum",
         "tasan_magaza_id": "M029", "tasan_magaza": "İzmir 4", "biten_magaza_id": "M069", "biten_magaza": "Erzurum 2",
         "tasan_ilk_adet": 448, "tasan_satis_28": 33, "biten_ilk_adet": 112, "biten_satis_14": 102,
         "tasan_plan_sirasi": 1, "kol_tasan_adet": 70, "kol_biten_adet": 364, "oturan": 415, "biten_oran": 102 / 112,
         "tasan_pay": 448 / 4368, "biten_pay": 112 / 4368, "toplam": 4368, "magaza_sayisi": 3}
    return {"kol": {"kol": "tahmin", "ad": "pay_tahmin_tavansiz"}, "basamak": 0,
            "kaynak": {a: {"ad": ad, "dizin": f"{ad}_{kosular[ad]['anahtar'][:20]}", "anahtar": kosular[ad]["anahtar"],
                           "anahtar_kaynagi": "cikti/oyun.json", "ayni": None}
                       for a, ad in (("lumoda", "lumoda"), ("kol", "pay_tahmin_tavansiz"))},
            "sahne": {"gevseyen": []}, "ayrinti": a, "aday_sayilari": [1, 4, 6, 7, 9],
            "alternatif_sahne": {"option_id": "MDL0564-KRM", "ad": "Regular Fit Gömlek Kiremit", "basamak": 1,
                                 "gevseyen": ["1: 28 günde satış ≤ %20"], "tasan_magaza": "Antalya 3",
                                 "tasan_ilk_adet": 539, "tasan_satis_28": 63, "tasan_plan_sirasi": 2,
                                 "kol_tasan_adet": 189, "biten_magaza": "Van 2", "biten_ilk_adet": 140,
                                 "biten_satis_14": 162, "kol_biten_adet": 322}}


def _yollar(kosular: dict) -> dict:
    yollar = {}
    for p in range(sabitler.YOL_SAYISI):
        k = {}
        for kisa, s_ in oyun.yol_listesi(p, KAL):
            if p == 0:
                e = kosular[s_.ad]
                k[kisa] = {"ad": s_.ad, "anahtar": e["anahtar"], "olcum_kodu": "olcum", "olcutler": e["olcutler"]}
            else:
                o = _olcutler(p + len(k))
                k[kisa] = {"ad": s_.ad, "anahtar": f"y{p}{kisa}" + "b" * 50, "olcum_kodu": "olcum", "olcutler": o}
        yollar[str(p)] = {"kod": "yolkod", "tamam": True, "talep_tohumu": oyun.talep_tohumu(p), "kosular": k,
                          "girdi": {"ogrenme_satir": 15859, "karar_gunu": "2025-02-07"}}
    return {"n": sabitler.YOL_SAYISI, "taban": sabitler.TALEP_TOHUM_TABANI, "kollar": list(oyun.YOL_KOLLARI),
            "yollar": yollar}


def _demo(kosular: dict) -> dict:
    harita = oyun.demo_haritasi(kosular, KAL)
    son = {}
    for p in senaryolar.PAYLAR:
        for t in senaryolar.TUTMALAR:
            o = kosular[harita[p][senaryolar.harita_anahtari(t)]]["olcutler"]
            son[senaryolar.anahtar(p, t)] = {"ozet": {m: senaryolar.yuvarla(o[m], b) for m, b in
                                                      senaryolar.OZET_OLCUTLERI.items()}, "satirlar": []}
    return {"surum": "rapor", "parametreler": senaryolar.PARAMETRELER, "sonuclar": son}


def tam_veri() -> rapor_b.Veri:
    secim = _secim()
    kosular = _kosular(secim)
    es = {f"es_{k}": {"kaynak": f"pay_{k}_tavanli", "anahtar": kosular[f"pay_{k}_tavanli"]["anahtar"], "tutma": ES_T,
                      "ham": TAVAN_KALAN / U_ADET, "U_adet": U_ADET, "giden_adet": U_ADET - TAVAN_KALAN}
          for k in ("benzer", "tahmin")}
    oyun_k = {"kosular": kosular, "belirsizlik_gamma": 2.0, "eslesik_tutma": es,
              "girdi": {"belirsizlik": {"olcu": "benzer_tahmin_ayrisma", "gamma": 2.0, "t_en_az": 0.04,
                                        "t_en_cok": 0.58, "t_ortalama": 0.3}}}
    yayimlanan = {
        "dalga": pd.DataFrame({"dalga": [1, 2, 3], "option": [66, 75, 69], "ilk_alim": [421290, 430550, 346450],
                               "teslim": [421290, 430550, 346450], "ilk_dagitim": [289439, 296319, 238407],
                               "en_cok_magaza": [39, 35, 30]}),
        "lansman": pd.DataFrame({"dalga": [1, 2, 3], "lansman_tarihi": pd.to_datetime(["2025-02-10", "2025-03-17", "2025-04-21"]),
                                 "indirim_baslangic": pd.to_datetime(["2025-06-30"] * 3),
                                 "cikis_tarihi": pd.to_datetime(["2025-08-25"] * 3)}),
        "magaza": pd.DataFrame({"magaza_id": [f"M{i:03d}" for i in range(69)], "istanbul": [i < 12 for i in range(69)]}),
        "beden": pd.DataFrame({"beden_sira": [1, 2, 3, 4, 5], "adet": [100, 220, 320, 240, 120]}),
        "paket": pd.DataFrame({"beden_seti": ["Kadın Harf"] * 5 + ["Standart"], "beden_sira": [1, 2, 3, 4, 5, 1],
                               "adet": [1, 2, 2, 1, 1, 6]}),
        "bes_bedenli_option": 193,
    }
    kural = {"option": 210, "ilk_alim": 1_198_290, "paket_adedi": [6, 7], "kural_paket": 120_054,
             "kural_adet": U_ADET + KIRPILAN, "U_paket": 118_003, "U_adet": U_ADET, "U_baglayan": 177, "U_kural_ustu": 0,
             "aday_hucre": 5354, "aday_sku_hucre": 25162, "aday_magaza_ort": 25.5, "aday_magaza_min": 16,
             "aday_magaza_max": 39, "kirpilan_option": 177, "kirpilan_hucre": 1791, "kirpilan_paket": 2051,
             "kirpilan_adet": KIRPILAN}
    plan = pd.DataFrame({"magaza_id": ["M029", "M069", "M001"], "ust_kategori": ["Elbise & Tulum"] * 3,
                         "sira": [1, 24, 2], "satis_hedefi": [18132.0, 4631.0, 15000.0]})
    gecerli = set(kosular)
    yol = _yollar(kosular)
    demo = _demo(kosular)
    bag = {"_taban": (358179, 697107)}
    bag.update({a: True for a, e in kosular.items() if e["grup"] in ("pay", "sabit_takvim") and a != "lumoda"})
    return rapor_b.Veri(
        oyun=oyun_k, kal=copy.deepcopy(KAL), secim=secim, hikaye=_hikaye(kosular), yollar=yol, demo=demo,
        demo_dosya=copy.deepcopy(demo), olcum_kodu="olcum", gecerli=gecerli,
        yol_gecerli={(p, k) for p, y in yol["yollar"].items() for k in y["kosular"]}, yayimlanan=yayimlanan,
        kural=kural, hucreler=_hucreler(), plan=plan, bagimsizlik=bag,
        yol_bagimsizlik={str(p): True for p in range(1, sabitler.YOL_SAYISI)}, yollar_kodu="yolkod",
        acilan={"lumoda", "pay_esit"})


def boz(v: rapor_b.Veri, bozma: str) -> None:
    """`tam_veri()`'nin bir korunum denetimini bozar."""
    k = v.oyun["kosular"]
    if bozma == "takvimli_farkli":
        k["lumoda_takvimli"]["olcutler"]["bulunabilirlik"] += 1e-6
    elif bozma == "sabit_rpt_farkli":
        k["sabit_esit"]["olcutler"]["rpt_adet"] += 7
    elif bozma == "demo_dosyasi_farkli":
        v.demo_dosya["sonuclar"]["esit|15"]["ozet"]["bulunabilirlik"] += 0.1
    elif bozma == "satis_talebi_asar":
        k["pay_esit"]["olcutler"]["satis_adet"] = k["pay_esit"]["olcutler"]["talep_adet"] + 1
    elif bozma == "yol0_anahtar_farkli":
        v.yollar["yollar"]["0"]["kosular"]["esit"]["anahtar"] = "x" * 64
    elif bozma == "eslesik_kaynagi_farkli":
        v.oyun["eslesik_tutma"]["es_tahmin"]["anahtar"] = "y" * 64
    elif bozma == "eslesik_mal_farkli":
        k["es_benzer"]["olcutler"]["ilk_dagitim_adet"] -= 10_000
    elif bozma == "hikaye_kaynagi_farkli":
        v.hikaye["kaynak"]["lumoda"]["anahtar"] = "baska"
    else:
        raise ValueError(bozma)


def bos_veri(taslak: bool = False, eksik: list | None = None) -> rapor_b.Veri:
    return rapor_b.Veri(oyun={"kosular": {}}, kal={}, taslak=taslak, eksik=list(eksik or []), acilan={"x"})
