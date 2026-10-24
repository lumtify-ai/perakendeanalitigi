"""Rapor ve demo testleri için sahte girdiler: `oyun.json`, `kalibrasyon.json`, `analiz.json`, `hikaye.json` (gerçek
veri ve koşu yok). Izgaranın 83 + 14 kaydı (`rapor.izgara()`), her test sezonunda 8 option; bütün korunum denetimleri
tutar; testler tek bir alanı bozar.

`yaz(tmp_path, ...)` girdileri diske yazar (koşuların önbellek `meta.json`'ları ve demo dosyası dahil) ve
`rapor.hazirla`'nın anahtar sözcüklerini döndürür.
"""

import copy
import json
from pathlib import Path

import rapor
import senaryolar
from markdown import oyun, sabitler

OLCUM = "o" * 64
ANALIZ = "a" * 64
HIKAYE = "h" * 64
OPTION = 8
SEZON_TABANI = {"SS25": 1.0, "AW24": 0.8, "AW23": 0.7, "SS24": 0.9}
# kol → (katkı, markdown TL, ölü stok, indirilen option) farkı Lumoda'ya (birim: TL, TL, adet, option)
ETKI = {"lumoda": (0, 0, 0, 0), "tekduze": (-110_000, 900_000, 40, 0), "kural": (330_000, 6_100_000, -2_600, -1),
        "opt_tuzak": (380_000, 150_000, 30, -3), "opt": (530_000, 4_600_000, -2_000, -1),
        "opt_takvim": (90_000, 1_300_000, -200, 0), "opt_erken_yok": (290_000, 560_000, -190, -1),
        "opt_taban": (370_000, 4_700_000, -2_040, 0), "kahin": (710_000, 3_500_000, -1_950, -1)}
PAYLAR = (0.125, 0.5, 0.25, 0.125)
TOPLANAN = ("ciro_sezon", "ciro_outlet", "ciro_toplam", "brut_kar", "katki", "markdown_tl", "markdown_tl_online", "kampanya_tl",
            "islem_tl", "outlet_indirim_tl", "arz_adet", "arz_alis", "cikis_kalan_adet", "cikis_kalan_magaza_adet",
            "cikis_kalan_depo_adet", "cikis_kalan_liste", "cikis_kalan_alis", "olu_stok_adet", "olu_stok_alis",
            "indirilen_option", "option_sayisi")


def olcutler(kol: str, sezon: str, yol: int = 0, kal: float = 0.0) -> dict:
    t = SEZON_TABANI[sezon]
    dk, dm, do, di = ETKI.get(kol, ETKI["kural"])
    katki = 20_000_000 * t + dk + 7_000 * yol + kal
    o = {"option_sayisi": float(OPTION), "ciro_sezon": 40_000_000 * t + dk, "ciro_outlet": 4_000_000 * t,
         "brut_kar": 22_000_000 * t + dk / 2, "markdown_tl": 3_300_000 * t + dm, "markdown_tl_online": 1_100_000 * t + dm / 3,
         "kampanya_tl": 6_000_000 * t, "islem_tl": 600_000 * t, "outlet_indirim_tl": 8_000_000 * t - dm / 3,
         "arz_adet": 60_000.0 * t, "arz_alis": 24_000_000 * t, "tam_fiyat_str": 46.5 - dm / 1e6, "son_str": 82.3 + dm / 1e6,
         "cikis_kalan_magaza_adet": 6_700.0 * t + do / 2, "cikis_kalan_depo_adet": 8_700.0 * t + do / 2,
         "cikis_kalan_liste": 15_700_000 * t, "cikis_kalan_alis": 5_700_000 * t, "olu_stok_adet": 4_250.0 * t + do,
         "olu_stok_alis": 1_340_000 * t, "indirilen_option": float(OPTION + di),
         "ilk_indirim_hafta_medyan": 0.0 if kol in ("lumoda", "tekduze", "opt_takvim", "opt_erken_yok") else -6.0,
         "ort_en_derin": 41.25, "muaf_str_ind": 108.57 if di else float("nan"), "bulunabilirlik": 56.91, "kayip_orani": 47.46}
    o["ciro_toplam"] = o["ciro_sezon"] + o["ciro_outlet"]
    o["katki"] = katki
    o["cikis_kalan_adet"] = o["cikis_kalan_magaza_adet"] + o["cikis_kalan_depo_adet"]
    return o


def ceyrek(o: dict) -> list[dict]:
    satir = []
    for c, p in enumerate(PAYLAR, start=1):
        r = {k: (v * p if isinstance(v, float) and k in TOPLANAN else v) for k, v in o.items()}
        r.update(ceyrek=c, str_alt=20.0 * c, str_ust=20.0 * c + 15.0, option_sayisi=2.0,
                 indirilen_option=2.0 if c < 4 or o["indirilen_option"] == OPTION else 1.0)
        satir.append(r)
    return satir


def toplam(oo: list[dict]) -> dict:
    t = {k: sum(o[k] for o in oo) for k in TOPLANAN}
    for k in ("tam_fiyat_str", "son_str", "ilk_indirim_hafta_medyan", "ort_en_derin", "muaf_str_ind", "bulunabilirlik",
              "kayip_orani"):
        t[k] = sum(o[k] for o in oo) / len(oo)
    return t


YAN = {"ciro_farki_test_disi": 547_000.0, "ciro_test_disi_lumoda": 237_000_000.0, "ciro_farki_basic": 163_000.0,
       "ciro_farki_collection": -13_000.0, "ciro_farki_nos": 363_000.0, "ciro_farki_outlet": 33_000.0, "ikame_alinan": 6110.0,
       "ikame_alinan_lumoda": 6294.0, "ikame_alinan_farki": -184.0, "ikame_giden": 10043.0, "ikame_giden_lumoda": 9270.0,
       "ikame_giden_farki": 773.0, "elle_transfer_farki": -6.0, "elle_transfer_farki_test": 32.0}
KAL = {"kural": 1.25, "tekduze": 0.40}


def oyun_kaydi() -> dict:
    kosular = {}
    for k in rapor.izgara():
        e = {"ad": k.ad, "yol": k.yol, "kol": k.kol, "sezon": k.sezon, "deger": k.deger, "kalibrasyon": k.deger is not None,
             "anahtar": f"{k.ad:_<20}"[:20] + "k" * 44, "lumoda_anahtar": "lumoda______________" + "k" * 44,
             "olcum_kodu": OLCUM, "talep_tohumu": None if k.yol == 0 else sabitler.TALEP_TOHUM_TABANI + k.yol}
        if k.kol == oyun.LUMODA:
            sz = oyun.lumoda_sezonlari(k.yol)
            e["olcutler"] = {z: olcutler("lumoda", z, k.yol) for z in sz}
            e["ceyrek"] = {z: ceyrek(e["olcutler"][z]) for z in sz}
            e["option_tablosu"] = {z: f"olcum/{k.ad}_{z}.parquet" for z in sz}
            e["parametreler"], e["gecerli"] = {}, True
        else:
            fark = 0.0 if k.deger is None else 1_000.0 * k.deger
            e["olcutler"] = olcutler(k.kol, k.sezon, k.yol, fark)
            e["ceyrek"] = ceyrek(e["olcutler"])
            e["isabet"] = ({"wape": float("nan"), "yanlilik": float("nan"), "wape_ilk": float("nan"), "satir": 0.0}
                           if k.kol == "tekduze" else {"wape": 32.6, "yanlilik": -15.3, "wape_ilk": 38.4, "satir": 472.0})
            e["korunum"] = dict.fromkeys(rapor.KORUNUM_ALANLARI, True)
            e["yan_etki"] = dict(YAN)
            e["option_tablosu"] = f"olcum/{k.ad}.parquet"
            e["gecerli"] = True
            d = k.deger if k.deger is not None else KAL.get(k.kol)
            e["parametreler"] = ({"kol": "kural", "alfa": d} if k.kol == "kural" else
                                 {"kol": "tekduze", "oran": d, "taban": d} if k.kol == "tekduze" else {"kol": k.kol})
        kosular[k.ad] = e
    toplamlar = {}
    for p in (0, *oyun.YOLLAR):
        for kol in (oyun.LUMODA, *(oyun.YOL0_KOLLARI if p == 0 else oyun.YOL_KOLLARI)):
            if kol == oyun.LUMODA:
                lu = kosular[oyun.kosu_adi(p, kol)]
                oo, ad = [lu["olcutler"][z] for z in sabitler.TEST_SEZONLARI], [lu["ad"]]
                yan = None
            else:
                rr = [kosular[oyun.kosu_adi(p, kol, z)] for z in sabitler.TEST_SEZONLARI]
                oo, ad = [r["olcutler"] for r in rr], [r["ad"] for r in rr]
                yan = {a: sum(r["yan_etki"][a] for r in rr) for a in YAN}
            toplamlar.setdefault(str(p), {})[kol] = {"olcutler": toplam(oo), **({"yan_etki": yan} if yan else {}),
                                                     "gecerli": True, "kosular": ad}
    ogr = {z: {"eps_saf": 0.164, "eps_markdown": {"*": 1.28, "Elbise & Tulum": 1.47, "Üst Giyim": 1.30},
               "eps_kampanya": {"*": 1.75, "Elbise & Tulum": 1.88, "Üst Giyim": 1.77},
               "gercek_eps": {"*": 1.85, "Elbise & Tulum": 1.92, "Üst Giyim": 1.87}, "kalinti": 0.13,
               "iade": {"magaza": 0.065, "online": 0.29}} for z in sabitler.TEST_SEZONLARI}
    yollar = {str(p): {"yol": p, "kaynak": "yayimlanan" if p == 0 else f"vaka:y{p}_lumoda", "ogrenme": copy.deepcopy(ogr)}
              for p in (0, *oyun.YOLLAR)}
    return {"olcek": "tam", "kosular": kosular, "toplamlar": toplamlar, "yollar": yollar}


def kalibrasyon_kaydi(o: dict) -> dict:
    out = {"olcek": "tam", "olcum_kodu": OLCUM}
    for kol, ad in (("kural", "alfa"), ("tekduze", "oran")):
        tablo = []
        for d in oyun.KAL_DEGERLERI[kol]:
            adlar = [oyun.kosu_adi(0, kol, z, d) for z in sabitler.KAL_SEZONLARI]
            satir = {"deger": d, **{z: o["kosular"][a]["olcutler"]["katki"] for z, a in zip(sabitler.KAL_SEZONLARI, adlar)},
                     "gecerli": True, "kosular": adlar}
            satir["toplam"] = sum(satir[z] for z in sabitler.KAL_SEZONLARI)
            tablo.append(satir)
        out[kol] = {ad: KAL[kol], "tablo": tablo, "izgara_ucunda": False}
    return out


def _huni(o: dict) -> dict:
    h = {"arz": o["arz_adet"], "arz_ilk": o["arz_adet"] * 0.75, "arz_rpt": o["arz_adet"] * 0.25, "arz_alis": o["arz_alis"],
         "satis_tam": 41_255.0, "satis_erken": 3_936.0, "satis_once": 45_191.0, "satis_ind": 5_851.0, "ciro_ind": 4_994_511.0,
         "md_ind": 3_207_377.0, "md_ind_net": 2_730_000.0, "kampanya_ind": 0.0, "brut_ind": 6_120_693.0,
         "liste_ind": 9_331_331.0, "kalan_magaza": 6_746.0, "kalan_depo": 8_727.0, "kalan": 15_473.0,
         "kalan_liste": 15_698_025.0, "kalan_alis": 5_703_327.0, "outlet_akisi": 15_232.0, "outlet_satis": 11_779.0,
         "outlet_ciro": 4_358_495.0, "outlet_brut": 4_644_244.0, "outlet_liste": 12_890_092.0, "outlet_indirim": 8_243_661.0,
         "outlet_indirim_net": 7_750_000.0, "olu_stok": 4_252.0, "olu_stok_alis": 1_338_293.0, "rpt_gec_adet": 6_020.0,
         "ind_fiyat_payi": 0.6559, "outlet_fiyat_payi": 0.3603, "option": OPTION, "rpt_gec_option": 5, "rpt_option": 3}
    return h


def analiz_kaydi(o: dict) -> dict:
    sezonlar = {}
    for z in ("SS23", "AW23", "SS24", "AW24", "SS25"):
        lu = o["kosular"]["lumoda"]["olcutler"].get(z) or olcutler("lumoda", "SS24")
        sezonlar[z] = {
            "gunler": {"lansman_ilk": "2025-02-10", "indirim": "2025-06-30", "cikis": "2025-08-25"}, "huni": _huni(lu),
            "kademe": {"dagilim": {"0.30": 6, "0.70": 2}, "erken_indirilen": 2, "lumoda_oncesi_indirilen": 0},
            "str": {"p10": 41.55, "p50": 66.67, "p90": 97.38, "alt_yari_kalan_payi": 0.815,
                    "ceyrekler": [{"ceyrek": c, "option": 2, "str_alt": 20.0 * c, "str_ust": 20.0 * c + 15, "str_ort": 20.0 * c + 7,
                                   "kalan": 4_000.0 - 900 * c, "kalan_payi": 0.25, "md_ind": 600_000.0 * c,
                                   "md_ind_net": 550_000.0 * c, "olu_stok": 900.0, "arz": 15_000.0} for c in range(1, 5)],
                    "option_str": {}},
            "haftalik": [{"hafta": h, "adet": 5_000.0 - 300 * (h + 8)} for h in range(-8, 8)]}
    return {"surum": 1, "olcek": "tam", "kod": ANALIZ, "kaynak": "yayimlanan", "lumoda_anahtar": None,
            "veri": {"ilk_gun": "2023-01-01", "son_gun": "2025-12-31"},
            "analiz_sezonlari": ["SS23", "AW23", "SS24", "AW24", "SS25"], "sezonlar": sezonlar}


def _seri(bas_hafta: int, n: int) -> list[dict]:
    return [{"hafta_bas": f"2025-{1 + (i // 4):02d}-0{1 + i % 4}", "hafta": bas_hafta + i, "hafta_lansman": i,
             "satis": float(500 - 10 * i), "oran": 0.0 if bas_hafta + i < 0 else 0.3, "outlet_oran": None,
             "magaza_stok": float(6_000 - 100 * i), "outlet_stok": 0.0, "depo": 600.0} for i in range(n)]


def _dagilim(gun: str) -> dict:
    return {"gun": gun, "magaza": 3_500.0, "depo": 3_088.0, "istanbul": 425.0, "anadolu": 3_075.0, "magaza_sayisi": 60,
            "en_buyuk": [{"magaza_id": "M040", "ad": "İzmir 4", "sehir": "İzmir", "adet": 557.0, "istanbul": False},
                         {"magaza_id": "M060", "ad": "Malatya 1", "sehir": "Malatya", "adet": 419.0, "istanbul": False}]}


def _tulum(oid: str, dalga: int, arz: int) -> dict:
    seri = _seri(-20 if dalga == 1 else -10, 40 if dalga == 1 else 30)
    return {"option_id": oid, "model_adi": "Salopet Tulum", "renk": "Lacivert", "dalga": dalga, "liste": 869.99, "alis": 334.55,
            "ust_kategori": "Elbise & Tulum", "alt_kategori": "Tulum", "sezon": "SS25", "lansman": "2025-02-10",
            "indirim": "2025-06-30", "cikis": "2025-08-25", "karar_gunu": seri[12]["hafta_bas"], "indirim_pazartesi": "2025-06-30",
            "arz_ilk": arz, "arz_rpt": 0, "arz": arz, "rpt": [], "haftalik": seri, "satis_once": arz * 0.4,
            "str_ind": 40.0, "karar": _dagilim(seri[12]["hafta_bas"]), "indirim_gunu": _dagilim("2025-06-30"),
            "cikis_kalan": {"magaza": 1_500.0, "depo": 2_000.0}, "olu_stok": 2_944.0,
            "lumoda": {"en_derin": 0.7, "ilk_indirim_hafta": -4}}


def _kol_sonucu(kol: str, rol: str) -> dict:
    erken = kol in ("opt", "opt_taban", "kahin", "kural")
    yol = [{"hafta": h, "oran": (0.3 if (erken and h >= -8) or h >= 0 else 0.0) if rol != "az" or kol == "lumoda" else 0.0}
           for h in range(-20, 8)]
    olu = {"lumoda": 2_944.0}.get(kol, 1_200.0 if erken else 2_500.0)
    return {"fiyat_yolu": yol, "ilk_indirim_hafta": next((r["hafta"] for r in yol if r["oran"] > 0), None),
            "en_derin": max(r["oran"] for r in yol),
            "sonuc": {"arz_adet": 8_390.0, "satis_cikis": 6_000.0, "satis_indirim": 5_000.0, "cikis_kalan_magaza_adet": 900.0,
                      "cikis_kalan_depo_adet": 1_400.0, "cikis_kalan_adet": 2_300.0, "olu_stok_adet": olu, "ciro_sezon": 4_500_000.0,
                      "ciro_outlet": 300_000.0, "ciro_toplam": 4_800_000.0, "markdown_tl": 400_000.0, "arz_alis": 2_806_874.0,
                      "katki": 1_993_126.0},
            "karar_gunu_kaydi": None}


def hikaye_kaydi(o: dict) -> dict:
    sahne = {"cok": "MDL0606-LCV", "az": "MDL0605-LCV", "gomlek": "MDL0563-YSL"}
    kollar = {}
    for kol in rapor.YOL0:
        ad = oyun.kosu_adi(0, kol) if kol == oyun.LUMODA else oyun.kosu_adi(0, kol, "SS25")
        kollar[kol] = {"kosu": ad, "anahtar": o["kosular"][ad]["anahtar"],
                       "optionlar": {rol: _kol_sonucu(kol, rol) for rol in sahne}}
    eps = [{"ad": a, "eps": e, "temizleme_ham": t, "temizleme_kademe": k, "dp_oran": d, "dp_yol": [d] * 8 + [0.4] * 8,
            "dp_kalan": 500.0, "dp_satis": 6_000.0, "dp_ciro": 4_000_000.0}
           for a, e, t, k, d in (("saf", 0.164, 0.99, 0.7, 0.0), ("markdown", 1.47, 0.42, 0.5, 0.0),
                                 ("kampanya", 1.88, 0.35, 0.4, 0.3), ("gercek", 1.92, 0.34, 0.4, 0.3))]
    gom = {"option_id": "MDL0563-YSL", "model_adi": "Oduncu Gömlek", "renk": "Yeşil", "dalga": 3, "liste": 479.99, "alis": 182.43,
           "arz": 13_050, "arz_ilk": 8_700, "arz_rpt": 4_350, "satis_once_fiziksel": 5_000.0, "magazaya_giden": 7_700.0,
           "satis_once": 5_500.0, "str_lumoda": 0.65, "str_arz": 0.42, "olu_stok": 5_447.0,
           "rpt": [{"siparis": "2025-06-02", "teslim": "2025-07-02", "adet": 4_350, "teslim_indirime_gun": 2,
                    "siparis_indirime_gun": -28}],
           "lumoda": {"en_derin": 0.3, "ilk_indirim_hafta": 0}, "haftalik": _seri(-10, 30)}
    liste = {"gun": "2025-05-05", "option": 70, "indirimli": 12, "oranlar": {"0.00": 58, "0.30": 12},
             "satirlar": [{"option_id": "MDL0606-LCV", "oran": 0.3, "tahmini_satis": 6_000.0, "satilabilir": 6_588.0,
                           "beklenen_kalan": 588.0}]}
    return {"surum": 1, "kod": HIKAYE, "olcek": "tam", "sezon": "SS25", "sahne": sahne, "sahne_yedek": False,
            "lumoda_anahtar": o["kosular"]["lumoda"]["anahtar"], "olcum_kodu": OLCUM,
            "tulumlar": {"cok": _tulum("MDL0606-LCV", 1, 8_390), "az": _tulum("MDL0605-LCV", 3, 4_470)}, "gomlek": gom,
            "kollar": kollar, "eksik_kollar": [],
            "esneklik": {"option_id": "MDL0606-LCV", "gun": "2025-05-05", "indirime_hafta": -8, "satilabilir": 6_588.0,
                         "talep": 3_100.0, "liste": 869.99, "kalinti": 0.13, "ust_kategori": "Elbise & Tulum", "epsler": eps,
                         "dogrulama": {k: {"kayit": {}, "hesap": {}, "satilabilir_option": 70, "satilabilir_esit": 70, "esit": True}
                                       for k in ("opt", "opt_tuzak")},
                         "kol_kararlari": {"opt": 0.3, "opt_tuzak": 0.0, "kahin": 0.3, "kural": 0.0}, "ogrenilen": "x"},
            "ders": {"cok_opt_ilk_indirim_hafta": -8, "lumoda_baslangic_hafta": -4, "cok_lumoda_oncesi": True,
                     "cok_indirim_oncesi": True, "az_opt_indirdi": False, "az_opt_ilk_indirim_hafta": None},
            "pazartesi_listesi": {"karar_gunu": liste, "indirim_gunu": {**liste, "gun": "2025-06-30"}},
            "karar_gunu_tutarli": True,
            "indirim_haftalari": {kol: {z: {"hafta": {"-6": 3, "0": OPTION + ETKI[kol][3] - 3}, "yok": -ETKI[kol][3],
                                            "option": OPTION} for z in sabitler.TEST_SEZONLARI} for kol in rapor.YOL0}}


def girdiler() -> dict:
    """Her çağrıda bağımsız bir kopya (testler bir alanı bozar)."""
    o = oyun_kaydi()
    return copy.deepcopy({"oyun": o, "kalibrasyon": kalibrasyon_kaydi(o), "analiz": analiz_kaydi(o), "hikaye": hikaye_kaydi(o)})


def yaz(tmp_path: Path, g: dict | None = None, *, demo: bool = True) -> dict:
    """Girdileri `tmp_path`'e yazar; `rapor.hazirla`'nın anahtar sözcükleri."""
    g = girdiler() if g is None else copy.deepcopy(g)
    cikti = Path(tmp_path) / "cikti"
    onbellek = cikti / "kosular"
    cikti.mkdir(parents=True, exist_ok=True)
    for ad in ("oyun", "kalibrasyon", "analiz", "hikaye"):
        if g.get(ad) is not None:
            (cikti / f"{ad}.json").write_text(json.dumps(g[ad], ensure_ascii=False), encoding="utf-8")
    for e in g["oyun"]["kosular"].values():
        d = onbellek / f"{e['ad']}_{e['anahtar'][:20]}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({"anahtar": e["anahtar"]}), encoding="utf-8")
    demo_yol = Path(tmp_path) / f"{senaryolar.DIZI}.json"
    if demo:
        senaryolar.yaz(senaryolar.uret(g["oyun"]), demo_yol)
    return {"cikti": cikti, "demo_yol": demo_yol, "olcum_kodu": OLCUM, "analiz_kodu": ANALIZ, "hikaye_kodu": HIKAYE,
            "onbellek": onbellek}
