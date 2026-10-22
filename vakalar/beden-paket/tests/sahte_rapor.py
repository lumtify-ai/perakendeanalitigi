"""Rapor ve demo testleri için sahte girdiler: `oyun.json`, `analiz.json`, `hikaye.json`, `kumeler.json`
(gerçek veri ve koşu yok). Dört mağaza (M1, M2 büyük; M3 orta; M4 küçük), iki beş bedenli option ve bir
aksesuar; ızgaranın 23 kaydı (`oyun.izgara_listesi`), pm_12 → p3_12 ve p2_ham → p2 bağlı. Bütün korunum
denetimleri tutar; testler tek bir alanı bozar.

`yaz(tmp_path, ...)` girdileri diske yazar (koşuların önbellek `meta.json`'ları ve demo dosyası dahil) ve
`rapor.hazirla`'nın anahtar sözcüklerini döndürür.
"""

import copy
import json
from pathlib import Path

import senaryolar
from beden_paket import oyun

OLCUM = "o" * 64
ANALIZ = "a" * 64
HIKAYE = "h" * 64
MAGAZALAR = ("M1", "M2", "M3", "M4")
PROFIL = {"M1": "buyuk", "M2": "buyuk", "M3": "orta", "M4": "kucuk"}
DESEN = {"p1": ["1-1-2-2-1"], "p2": ["1-1-2-2-1", "1-2-2-1-1"], "p1_12": ["1-3-4-3-1"],
         "p3_12": ["1-2-3-4-2", "1-3-4-3-1", "2-3-4-2-1"], "pm_12": ["1-2-3-4-2", "1-3-4-3-1", "2-3-4-2-1"],
         "p2_ham": ["1-1-2-2-1", "1-2-2-1-1"]}
ATAMA = {"p1": dict.fromkeys(MAGAZALAR, "1-1-2-2-1"),
         "p2": {"M1": "1-1-2-2-1", "M2": "1-1-2-2-1", "M3": "1-1-2-2-1", "M4": "1-2-2-1-1"},
         "p1_12": dict.fromkeys(MAGAZALAR, "1-3-4-3-1"),
         "p3_12": {"M1": "1-2-3-4-2", "M2": "1-2-3-4-2", "M3": "1-3-4-3-1", "M4": "2-3-4-2-1"}}
ATAMA["pm_12"] = ATAMA["p3_12"]
ATAMA["p2_ham"] = ATAMA["p2"]
K_DEGERI = {"p1": 1, "p2": 2, "p1_12": 1, "p3_12": 3, "pm_12": "magaza", "p2_ham": 2}
# kol → (ilk 4 hafta bulunabilirlik, beden kaybı, kırık set, brüt kâr) farkı Lumoda'ya
ETKI = {"dogrulama": (0, 0, 0, 0), "p1": (0.31, -1.2, -2.0, 50_000), "p2": (0.42, -1.5, -2.2, 70_000),
        "p1_12": (0.2, -4.0, -3.0, 300_000), "p3_12": (0.5, -6.0, -3.5, 350_000)}


def olcutler(kol: str, yol: int) -> dict:
    d4, bk, kr, bt = ETKI[kol]
    o = {"bulunabilirlik": 69.0 + 0.1 * yol + d4 / 3, "bulunabilirlik_ilk4": 80.0 + 0.1 * yol + d4,
         "beden_kayip_payi": 40.04 + 0.2 * yol + bk, "kirik_cift_pay_yuzde": 30.0 + kr, "sezon_sonu_kalan_yuzde": 20.0 - bk / 10,
         "tam_fiyat_str": 50.0 - bk / 10, "kayip_orani": 30.0, "brut_kar_tl": 100_000_000.0 + 1_000 * yol + bt,
         "markdown_tl": 1_000.0, "ilk_dagitim_adet": 7_000.0 if kol in ("dogrulama", "p1", "p2") else 7_012.0,
         "replenishment_adet": 500.0, "tukenen_hucre_yuzde": 70.0, "talep_adet": 10_000.0 + yol,
         "kirpilan_adet": 100.0 if kol == "dogrulama" else 0.0, "kirpilan_option": 2.0 if kol == "dogrulama" else 0.0}
    o |= {f"ilk_tukenen_beden_{b}": (10.0, 15.0, 5.0, 30.0, 40.0)[b - 1] for b in range(1, 6)}
    return o


def oyun_kaydi() -> dict:
    kosular = {}
    for yol, kol in oyun.izgara_listesi("hepsi"):
        ad = oyun.kosu_adi(yol, kol)
        taban = {"pm_12": "p3_12", "p2_ham": "p2"}.get(kol, kol)
        k = oyun.KOLLAR[kol]
        e = {"ad": ad, "yol": yol, "kol": kol, "paket_adet": k.adet, "K": None if kol == "dogrulama" else K_DEGERI[kol],
             "desenler": ["1-2-2-1-1"] if kol == "dogrulama" else list(DESEN[kol]),
             "atama": None if kol == "dogrulama" else dict(ATAMA[kol]), "anahtar": f"{ad:_<20}" + "k" * 44,
             "olcum_kodu": OLCUM, "talep_tohumu": None if yol == 0 else 20261019 + yol,
             "olcutler": olcutler(taban, yol), "korunum": {"hucre": 8, "fark_hucre": 0, "fark_adet": 0, "net_fark_adet": 0},
             "ayni_mal": None if kol == "dogrulama" else True,
             "on_denetim": {"option": 0, "option_beden": 0, "asim_adet": 0, "kontrol_option": 2}}
        if k.adet == 12:
            e["donusum"] = {"lumoda_adet": 7_000, "kol_adet": 7_012, "fark_adet": 12, "hucre": 8, "sifir_hucre": 0, "option": 2,
                          "option_en_buyuk_fark": 6, "option_fark_siniri": 6}
        if kol == "dogrulama":
            e["ilk_sevkiyat"] = {"birebir": 51, "olcut": 51, "farkli": []}
        if taban != kol:
            e["ayni"] = oyun.kosu_adi(yol, taban)
            e["anahtar"] = f"{oyun.kosu_adi(yol, taban):_<20}" + "k" * 44
        kosular[ad] = e
    yollar = {str(p): {"egri": {"kappa": 12800.0, "profil": {"buyuk": 2, "kucuk": 1, "orta": 1}}, "ns": {"paket": 1_000}}
              for p in range(5)}
    return {"olcek": "tam", "kosular": kosular, "yollar": yollar, "kosulmayan": oyun.KOSULMAYAN}


def _k(adet, K, desen, pb, ayni=None, en_iyi=True):
    return {"adet": adet, "K": K, "desenler": desen, "toplam_uyumsuzluk": pb * 1000, "paket_basina": pb,
            "en_iyi_mi": None if K == "lumoda" else en_iyi, "yontem": None if K == "lumoda" else "tam",
            "depo_uygun": None if K == "lumoda" else True, "ayni": ayni}


def analiz_kaydi(oyun_k: dict) -> dict:
    kap = [{"magaza_id": m, "ad": f"Mağaza {m}", "sehir": "İstanbul" if m == "M4" else "Konya", "bolge": "Marmara",
            "istanbul": m == "M4", "tip": "AVM", "gecmis_hafta": 100, "yeni": False} for m in MAGAZALAR]
    tasarim = {"lumoda": {"paket_adet": 7, "desenler": ["1-2-2-1-1"], "giden_gercek_l1": 0.30, "giden_egri_l1": 0.31}}
    for kol in ("p1", "p2", "p1_12", "p3_12", "pm_12", "p2_ham"):
        say = {}
        for d in ATAMA[kol].values():
            say[d] = say.get(d, 0) + 1
        tasarim[kol] = {"paket_adet": oyun.KOLLAR[kol].adet, "K": K_DEGERI[kol], "egri": oyun.KOLLAR[kol].egri,
                        "desenler": list(DESEN[kol]), "atama": dict(ATAMA[kol]), "desen_magaza": {d: say.get(d, 0) for d in DESEN[kol]},
                        "desen_agirlik": {d: say.get(d, 0) / 4 for d in DESEN[kol]},
                        "profil_desen": {"satirlar": ["buyuk", "kucuk", "orta"], "sutunlar": DESEN[kol],
                                         "degerler": [[sum(1 for m in MAGAZALAR if PROFIL[m] == p and ATAMA[kol][m] == d)
                                                       for d in DESEN[kol]] for p in ("buyuk", "kucuk", "orta")]},
                        "toplam_uyumsuzluk": 100.0, "paket_basina": 0.5, "en_iyi_mi": True, "yontem": "tam",
                        "depo_uygun": True, "ayni": {"pm_12": "p3_12", "p2_ham": "p2"}.get(kol),
                        "giden_gercek_l1": 0.2, "giden_egri_l1": 0.18}
    k_egrisi = [_k(7, "lumoda", ["1-2-2-1-1"], 0.95), _k(7, 1, DESEN["p1"], 0.85), _k(7, 2, DESEN["p2"], 0.58),
                _k(7, 3, DESEN["p2"], 0.58, 2), _k(7, 4, DESEN["p2"], 0.58, 2), _k(7, "magaza", DESEN["p2"], 0.58, 2),
                _k(12, 1, DESEN["p1_12"], 1.31), _k(12, 2, ["1-2-4-3-2", "2-3-4-2-1"], 0.68),
                _k(12, 3, DESEN["p3_12"], 0.55), _k(12, 4, DESEN["p3_12"], 0.55, 3),
                _k(12, "magaza", DESEN["p3_12"], 0.55, 3)]
    egri = {
        "kappa": 12800.0, "kappa_izgara": [0.0, 1600.0, 12800.0],
        "kappa_tablosu": [{"kappa": 0.0, "l1": 0.027899, "magaza": 4}, {"kappa": 1600.0, "l1": 0.027853, "magaza": 4},
                          {"kappa": 12800.0, "l1": 0.027646, "magaza": 4}],
        "magaza": 4, "okunabilir": 4, "okunamaz": [], "en_az_adet": 500, "n_medyan": 120_000.0, "n_en_az": 46_000.0,
        "agirlik_medyan": 0.9, "agirlik_en_az": 0.78, "az_ornekli": {"M3": {"n": 46_000.0, "w": 0.78, "l1": 0.03, "kayma": 0}},
        "profil": {"buyuk": 2, "kucuk": 1, "orta": 1}, "profil_okunur": {"buyuk": 2, "kucuk": 1, "orta": 1},
        "profil_magaza": dict(PROFIL), "profil_egrisi": {"kucuk": [0.16, 0.28, 0.3, 0.18, 0.08],
                                                       "orta": [0.1, 0.22, 0.32, 0.24, 0.12],
                                                       "buyuk": [0.07, 0.16, 0.28, 0.31, 0.18]},
        "zincir": [0.1023, 0.2184, 0.3111, 0.2449, 0.1233],
        "yeni_secim": {"secim": "profil", "l1_profil": 0.17421, "l1_zincir": 0.17511, "isabet": 0.515, "magaza": 4},
        "yeni": {}, "sansur_tanisi": {"hucre": 10, "adet": 1000.0, "stoksuz_satisli_hucre": 1, "stoksuz_satisli_adet": 3.0,
                                      "az_gunlu_hucre": 2, "seyrek_hucre": 1, "seyrek_talep_payi": 0.0009,
                                      "en_buyuk_carpan": 242.7},
        "l1": {"ham": 0.0530, "duzeltilmis": 0.0337, "daraltilmis": 0.0333, "profil": 0.0328, "zincir": 0.1655},
        "l1_magaza": 4, "sansur_en_buyuk": 0.0201, "sansur_ortalama": 0.0053,
        "hat": {"havuz": {"hakemli_ham": 0.0530, "hakemli_duzeltilmis": 0.0337, "magaza": 4, "sansur_en_buyuk": 0.0201,
                          "sansur_ortalama": 0.0053, "hakemsiz_duzeltilmis": 0.0279, "hakemsiz_secilen": 0.0276,
                          "kappa": 12800.0, "hakemsiz_magaza": 4},
                "Collection": {"hakemli_ham": 0.083, "hakemli_duzeltilmis": 0.0289, "magaza": 4, "sansur_en_buyuk": 0.0489,
                               "sansur_ortalama": 0.0128, "hakemsiz_duzeltilmis": 0.0302, "hakemsiz_secilen": 0.0300,
                               "kappa": 12800.0, "hakemsiz_magaza": 4},
                "Basic+NOS": {"hakemli_ham": 0.05, "hakemli_duzeltilmis": 0.0359, "magaza": 4, "sansur_en_buyuk": 0.0202,
                              "sansur_ortalama": 0.0047, "hakemsiz_duzeltilmis": 0.0290, "hakemsiz_secilen": 0.0288,
                              "kappa": 12800.0, "hakemsiz_magaza": 4}},
        "kararlilik": {"l1": 0.0061, "magaza": 4, "kal_karar_gunu": "2024-02-09"}, "ari": 1.0, "ari_magaza": 4,
        "kayma_ham_2": 1,
        "profil_kayma": {"satirlar": ["buyuk", "kucuk", "orta"], "sutunlar": [-1, 0, 1], "degerler": [[0, 0, 2], [1, 0, 0], [0, 1, 0]]},
        "ham_duz_l1": {"ortalama": 0.026, "en_cok": 0.061},
    }
    return {
        "surum": 1, "olcek": "tam", "kod": ANALIZ, "oyun_olcum_kodu": OLCUM, "lumoda": "dogrulama_x",
        "lumoda_anahtar": oyun_k["kosular"]["dogrulama"]["anahtar"],
        "veri": {"karar_gunu": "2025-02-07", "kapsam": kap, "oyun_option": 3, "bes_bedenli_option": 2,
                 "beden_setleri": {"Kadın Harf": 2, "Standart": 1}, "ns": {"hucre": 12, "paket": 1_000, "magaza": 4},
                 "kaynak": "yayimlanan"},
        "paket": {"lumoda": [1, 2, 2, 1, 1], "adet": 7, "zincir": egri["zincir"], "zincir_l1": 0.1617,
                  "magaza_l1": {"ortalama": 0.25, "en_az": 0.1, "en_cok": 0.4, "en_cok_magaza": "M1", "magaza": 4},
                  "gercek_l1": {"ortalama": 0.26, "en_cok": 0.41, "magaza": 4},
                  "ilk_siparis": [1100, 2200, 3200, 2400, 1200], "depo": [1000, 2150, 3150, 2350, 1150],
                  "ilk_dagitim": [1000, 2000, 2000, 1000, 1000], "replenishment": [10, 50, 150, 200, 40],
                  "aday_7": 70, "aday_12": 715},
        "egri": egri, "tasarim": tasarim, "k_egrisi": k_egrisi,
        "kahin": {"ayni_atama": False, "farkli_magaza": ["M3"], "magaza": 4, "ari": 1.0, "ari_magaza": 4,
                  "uyumsuzluk_gercek_tasarim": 66.4, "uyumsuzluk_gercek_kahin": 64.8, "farkli_agirlik_payi": 0.021,
                  "farkli": {"M3": {"tasarim": "1-1-2-2-1", "kahin": "1-2-2-1-1", "kaynak": "profil", "paket": 21.0}},
                  "giden_gercek_l1_kahin": 0.19},
        "depo": {"ilk_siparis": [1100, 2200, 3200, 2400, 1200], "hatali_dusulmus": [1000, 2150, 3150, 2350, 1150],
                 "pay": {"7": {"siparis": [0.157, 0.314, 0.457, 0.343, 0.171], "hatali_dusulmus": [1 / 7, 0.31, 0.45, 0.34, 0.16],
                               "oyun": [0.157, 0.314, 0.457, 0.343, 0.171]},
                         "12": {"siparis": [0.157, 0.314, 0.457, 0.343, 0.171], "hatali_dusulmus": [0.143, 0.31, 0.45, 0.34, 0.16],
                                "oyun": [0.157, 0.314, 0.457, 0.343, 0.171]}},
                 "tasarim_ayni": {k: {"iki_tanim": True, "oyun_siparis": True}
                                  for k in ("p1", "p2", "p1_12", "p3_12", "pm_12", "p2_ham")}},
        "ilk_sevkiyat": {str(p): {"anahtar_ayni": True, "onbellekte": True} for p in range(5)},
    }


def _sahne_magazasi(m: str, rol: str) -> dict:
    gelen = [3 * k for k in (1, 2, 2, 1, 1)]
    biten = {"buyuk": (None, 5, 4, 1, 2), "kucuk": (1, 2, 5, 5, None)}[rol]
    return {"magaza": m, "istanbul": m == "M4", "profil": rol, "egri": [0.07, 0.16, 0.28, 0.31, 0.18],
            "option": "OPT-A", "sezon": "SS24", "beden_seti": "Kadın Harf", "varis": "2024-02-12", "bas": "2024-02-12",
            "desen": "1-2-2-1-1", "paket": 3, "satis": 30,
            "bedenler": [{"beden_sira": b + 1, "beden": ("XS", "S", "M", "L", "XL")[b], "gelen": gelen[b], "satis": 6,
                          "biten_hafta": biten[b], "bos_gun": 0 if biten[b] is None else 10, "kalan": 1 if biten[b] is None else 0}
                         for b in range(5)]}


def hikaye_kaydi() -> dict:
    return {"surum": 1, "kod": HIKAYE, "karar_gunu": "2025-02-07", "buyuk": _sahne_magazasi("M1", "buyuk"),
            "kucuk": _sahne_magazasi("M4", "kucuk"), "kademe": 2, "gevseyen": ["erken pencere: 3 hafta", "erken pencere: 4 hafta"],
            "roller": "kadro", "zincir": [0.1023, 0.2184, 0.3111, 0.2449, 0.1233], "elenen": 0,
            "dogrulama": {"kayma": {"M1": 1, "M4": -1}, "buyuk": True, "kucuk": True}, "pencere_hafta": 8,
            "alternatif": None, "magazalar": {"M1": {"ad": "Konya 1", "sehir": "Konya", "bolge": "İç Anadolu", "tip": "AVM",
                                                    "metrekare": 400, "istanbul": False},
                                             "M4": {"ad": "İstanbul 1", "sehir": "İstanbul", "bolge": "Marmara", "tip": "AVM",
                                                    "metrekare": 900, "istanbul": True}},
            "hakemsiz_ayni": True}


def kumeler_kaydi() -> dict:
    return {"ml": {"aile": "S1", "yontem": "kmeans", "k": 2, "etiket": {"M1": 0, "M2": 1, "M3": 0, "M4": 1},
                   "yeni_magaza": {"atama": {}}}}


def girdiler() -> dict:
    """Her çağrıda bağımsız bir kopya (testler bir alanı bozar; modül sabitleri paylaşılmaz)."""
    o = oyun_kaydi()
    return copy.deepcopy({"oyun": o, "analiz": analiz_kaydi(o), "hikaye": hikaye_kaydi(), "kumeler": kumeler_kaydi()})


def yaz(tmp_path: Path, g: dict | None = None, *, demo: bool = True) -> dict:
    """Girdileri `tmp_path`'e yazar; `rapor.hazirla`'nın anahtar sözcükleri (kumeler dahil)."""
    g = girdiler() if g is None else copy.deepcopy(g)
    cikti = Path(tmp_path) / "cikti"
    onbellek = cikti / "kosular"
    cikti.mkdir(parents=True, exist_ok=True)
    for ad in ("oyun", "analiz", "hikaye"):
        if g.get(ad) is not None:
            (cikti / f"{ad}.json").write_text(json.dumps(g[ad], ensure_ascii=False), encoding="utf-8")
    for e in g["oyun"]["kosular"].values():
        d = onbellek / f"{e.get('ayni') or e['ad']}_{e['anahtar'][:20]}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({"anahtar": e["anahtar"]}), encoding="utf-8")
    demo_yol = Path(tmp_path) / "beden-paket.json"
    if demo:
        senaryolar.yaz(senaryolar.uret(g["oyun"], g["analiz"]), demo_yol)
    return {"cikti": cikti, "demo_yol": demo_yol, "olcum_kodu": OLCUM, "analiz_kodu": ANALIZ, "hikaye_kodu": HIKAYE,
            "onbellek": onbellek, "kumeler": g["kumeler"]}
