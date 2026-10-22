"""Raporun ve demonun testleri için küçük, kendi içinde tutarlı sahte `sonuc.json` içeriği.

8 kümelenen mağaza (M01-M08) ve 1 yeni mağaza (M09). Etiketler elle; çapraz tablolar, ARI'ler ve bölme
kimlikleri paketin kendi işlevleriyle hesaplanır (korunum denetimleri tutsun diye). Sayılar gerçek
veri değildir.
"""

import copy

import pandas as pd

from kumeleme import ogren, olcutler, oyun

KUM = [f"M0{i}" for i in range(1, 9)]
YENI = "M09"
TUM = KUM + [YENI]

_MAGAZA = {   # ad, şehir, bölge, tip, m², metropol, istanbul
    "M01": ("İstanbul 1", "İstanbul", "Marmara", "AVM", 700, True, True),
    "M02": ("İstanbul 2", "İstanbul", "Marmara", "Cadde", 350, True, True),
    "M03": ("Ankara 1", "Ankara", "İç Anadolu", "AVM", 650, True, False),
    "M04": ("Bursa 1", "Bursa", "Marmara", "AVM", 600, False, False),
    "M05": ("Konya 1", "Konya", "İç Anadolu", "Cadde", 320, False, False),
    "M06": ("Antalya 1", "Antalya", "Akdeniz", "AVM", 540, False, False),
    "M07": ("Erzurum 1", "Erzurum", "Doğu Anadolu", "Cadde", 300, False, False),
    "M08": ("Eskişehir 1", "Eskişehir", "İç Anadolu", "Cadde", 280, False, False),
    "M09": ("Kocaeli 1", "Kocaeli", "Marmara", "AVM", 900, False, False),
}
GIZLI = {"M01": "metropol_genc", "M02": "anadolu_aile", "M03": "metropol_genc", "M04": "anadolu_aile",
         "M05": "anadolu_aile", "M06": "sicak_sahil", "M07": "soguk_iklim", "M08": "anadolu_aile", "M09": "anadolu_aile"}
K1 = {m: _MAGAZA[m][2] for m in TUM}
K2 = {"M01": "A", "M02": "C", "M03": "A", "M04": "B", "M05": "C", "M06": "B", "M07": "C", "M08": "C", "M09": "C"}
K3 = {m: f"{K1[m]}×{'ABC' if K1[m] != 'Marmara' else ('AB' if K2[m] != 'C' else 'C')}" for m in TUM}
K4 = {"M01": "metropol", "M02": "metropol", "M03": "metropol", "M04": "ılıman", "M05": "karasal",
      "M06": "sicak_sahil", "M07": "soguk", "M08": "karasal", "M09": "ılıman"}
ML = {"M01": 1, "M02": 0, "M03": 1, "M04": 0, "M05": 0, "M06": 2, "M07": 2, "M08": 0}
CIRO = {"M01": 9e7, "M02": 2e7, "M03": 8e7, "M04": 5e7, "M05": 1.5e7, "M06": 4e7, "M07": 1e7, "M08": 1.2e7,
        "M09": 0.0}


def _s(d: dict, ids=KUM) -> pd.Series:
    return pd.Series({m: d[m] for m in ids})


def _capraz(e: pd.Series, g: pd.Series) -> dict:
    t = olcutler.capraz(e, g)
    return {"satirlar": [oyun._j(x) for x in t.index], "sutunlar": [str(c) for c in t.columns],
            "degerler": t.to_numpy().tolist()}


def _grup(etiket: dict) -> dict:
    e, g = _s(etiket), _s(GIZLI)
    ari, ami = olcutler.ari_ami(e, g)
    met = [m for m in KUM if _MAGAZA[m][5]]
    dis = [m for m in KUM if not _MAGAZA[m][5]]
    bolum = {}
    for ad, ids in (("metropol", met), ("metropol_disi", dis)):
        a2, m2 = olcutler.ari_ami(_s(etiket, ids), _s(GIZLI, ids))
        bolum[ad] = {"n": len(ids), "ari": a2, "ami": m2, "grup": len({etiket[m] for m in ids}),
                     "segment": len({GIZLI[m] for m in ids})}
    sf = olcutler.saflik(e, g)
    return {"ari": ari, "ami": ami, "toplam_saflik": olcutler.toplam_saflik(e, g), "grup": int(e.nunique()),
            "capraz": _capraz(e, g), "bolum": bolum,
            "saflik": {s: {"n": int(sf.at[s, "n"]), "kume": oyun._j(sf.at[s, "kume"]), "pay": float(sf.at[s, "pay"]),
                           "kume_payi": float(sf.at[s, "kume_payi"])} for s in sf.index}}


def _aday(aile, yontem, k, etiket, *, secilen=False, oneri=False, kararlilik=None, ari=0.1, siluet=0.2):
    boy = sorted(pd.Series(etiket).value_counts().tolist(), reverse=True)
    return {"aile": aile, "yontem": yontem, "k": k, "siluet": siluet, "w": 10.0 / k, "en_kucuk": min(boy),
            "boyutlar": boy, "uygun": min(boy) >= 2, "secilen": secilen, "kararlilik": kararlilik,
            "bolme_kararlilik": kararlilik, "esit": oneri, "oneri": oneri,
            "kimlik": ogren.bolme_kimligi(pd.Series(etiket)), "ari": ari, "ami": ari}


def _iki(etiket_k3: dict) -> dict:
    return {m: (0 if v == 0 else 1) for m, v in etiket_k3.items()}


def _izgara(ari3: float, k2ari: float = 0.05) -> list[dict]:
    rows = []
    for yontem in ("kmeans", "ward"):
        for k, e in ((2, _iki(ML)), (3, ML)):
            r = _aday("x", yontem, k, e, secilen=(k == 3), ari=ari3 if k == 3 else 0.2, siluet=0.31 if k == 3 else 0.2)
            rows.append({c: r[c] for c in ("yontem", "k", "siluet", "en_kucuk", "boyutlar", "uygun", "secilen", "ari",
                                           "ami", "kimlik")} | {"ari_k2": k2ari})
    return rows


def _demo() -> dict:
    out = {}
    for aile in ("S1", "S2", "S4"):
        for k in (4, 5, 6, 7, 8):
            boy = [8 - (k - 1)] + [1] * (k - 1)
            out[f"{aile}|{k}"] = {"ari": 0.5 + k / 100, "kararlilik": 0.9 - k / 100, "en_kucuk": min(boy),
                                  "siluet": 0.25 + k / 1000,
                                  "kumeler": [{"kume": i, "magaza": b, "ozellik": "karisim/Collection/kalip/regular",
                                               "z": 1.0} for i, b in enumerate(boy)]}
    return out


def _yeni_ozet(dogru: int, met: int) -> dict:
    return {"hepsi": {"n": 8, "dogru_kume": dogru, "dogru_segment": dogru, "kume_dogru_segment": 8, "taban_kume": 4,
                      "taban_segment": 4},
            "metropol": {"n": 3, "dogru_kume": met, "dogru_segment": met, "kume_dogru_segment": 3, "taban_kume": 1,
                         "taban_segment": 1},
            "metropol_disi": {"n": 5, "dogru_kume": dogru - met, "dogru_segment": dogru - met, "kume_dogru_segment": 5,
                              "taban_kume": 3, "taban_segment": 3}}


def sonuc() -> dict:
    """Sahte `sonuc.json` içeriği (korunum denetimleri tutar)."""
    kapsam = [{"magaza_id": m, "ad": a, "sehir": sh, "bolge": b, "tip": t, "metrekare": m2, "enlem": 39.0,
               "istanbul": ist, "metropol": met, "gecmis_hafta": 0 if m == YENI else (40 if m == "M06" else 104),
               "kumelenir": m != YENI, "yeni": m == YENI}
              for m, (a, sh, b, t, m2, met, ist) in _MAGAZA.items()]
    oz = {"bloklar": ["karisim"], "magaza": 8, "sutun": 6, "standart_sutun": 6, "blok_sutun": {"karisim": 6},
          "alt_blok": {"karisim": 6}, "doldurulan": {}, "dusen_satis": {}, "kimlik": "a" * 64}
    ml_kimlik = ogren.bolme_kimligi(pd.Series(ML))
    ml_ari = olcutler.ari_ami(_s(ML), _s(GIZLI))[0]
    aday = [_aday("S1", "kmeans", 2, _iki(ML), ari=0.4),
            _aday("S1", "kmeans", 3, ML, secilen=True, oneri=True, kararlilik=0.85, ari=ml_ari, siluet=0.31),
            _aday("S1", "ward", 3, ML, secilen=True, kararlilik=0.87, ari=ml_ari, siluet=0.31),
            _aday("S2", "kmeans", 2, _iki(ML), secilen=True, kararlilik=0.99, ari=0.05, siluet=0.27)]
    gruplar = {"k1": _grup(K1), "k2": _grup(K2), "k3": _grup(K3), "k4": _grup(K4), "ml": _grup(ML)}
    k4 = _s(K4)
    km = pd.crosstab(k4.to_numpy(), _s(ML).to_numpy())
    s = {
        "surum": oyun.KAYIT_SURUMU, "kod": "k" * 64, "veri_izi": ["perakende.duckdb", 1, 2],
        "veri": {"karar_gunu": "2025-02-07", "lansman": "2025-02-10",
                 "tip_sayilari": {"AVM": 5, "Cadde": 5, "Online": 1, "Outlet": 1}, "fiziksel": 10,
                 "disarida": [{"magaza_id": "M10", "ad": "İstanbul 3", "neden": "kapanmış ya da kapanış kararı verilmiş",
                               "acilis": "2016-05-02", "kapanis": "2024-09-18"}],
                 "kapsam": kapsam, "ozellik_penceresi": ["2023-02-06", "2025-02-02"],
                 "kal_ozellik_penceresi": {"karar_gunu": "2024-02-09", "bas": "2022-02-07", "bit": "2024-02-04",
                                           "hafta": 104, "ilk_satis": "2023-01-01", "veri_hafta": 57},
                 "ciro_penceresi": ["2024-02-07", "2025-02-06"], "gecmis_hafta_esigi": 26},
        "kural": {"etiketler": {"k1": K1, "k2": K2, "k3": K3, "k4": K4}, "net_ciro": CIRO,
                  "esikler": {"A": 8e7, "B": 4e7}, "yillik_kisa": ["M06"], "oranlar": {"A": 0.2, "B": 0.3},
                  "k3_en_az": 3},
        "ozellik": {a: {**oz, "kimlik": ("b" * 64 if a == "S1" else "c" * 64)}
                    for a in ("S1", "S2", "S4", "S5", "S1+olcek", "S1_stoklu")},
        "ml": {"aday_tablosu": aday,
               "bos_siluet": [{"aile": r["aile"], "yontem": r["yontem"], "k": r["k"], "bos_siluet": 0.05}
                              for r in aday if r["secilen"]],
               "kararlilik_once": {"aile": "S2", "yontem": "kmeans", "k": 2, "kararlilik": 0.99, "siluet": 0.27,
                                   "ari": 0.05},
               "hakemle_en_iyi": {"aile": "S1", "yontem": "kmeans", "k": 3, "ari": ml_ari},
               "oneri": {"aile": "S1", "yontem": "kmeans", "k": 3, "kimlik": ml_kimlik, "etiket": ML,
                         "boyutlar": [4, 2, 2], "ozellik_kimligi": "b" * 64},
               "yorum": {str(c): [{"ozellik": "karisim/Collection/kalip/regular", "z": 1.2, "kume_ort": 0.3,
                                   "genel_ort": 0.25}] for c in (0, 1, 2)},
               "en_kucuk_kume": 3, "silu_esitlik": 0.01, "kararlilik_esitlik": 0.02, "kararlilik_ornek": 50,
               "kararlilik_oran": 0.8, "bos_ornek": 10},
        "hakem": {"segment_sayilari": {k: int(v) for k, v in _s(GIZLI).value_counts().sort_index().items()},
                  "gruplar": gruplar,
                  "k4_ml": {"ari": 0.4, "capraz": {"satirlar": list(km.index), "sutunlar": [int(c) for c in km.columns],
                                                   "degerler": km.to_numpy().tolist()}},
                  "sehir_iklim": {"sehir": 9, "ortusen": 8, "farkli": [{"sehir": "İzmir", "vaka": "sicak_sahil",
                                                                         "simulator": ["ılıman"]}],
                                  "vaka_tablosu": 26}},
        "kararlilik": {"donem": [{"donem": "2023", "bas": "2023-01-02", "bit": "2023-12-31", "hafta": 52, "magaza": 7},
                                 {"donem": "2024", "bas": "2024-02-05", "bit": "2025-02-02", "hafta": 52, "magaza": 7}],
                       "disarida": ["M06"], "satisli_hafta_disarida": {"M06": {"2023": 0, "2024": 40}},
                       "ari": {"2023|2024": 0.64}, "donem_boyutlar": {"2023": [4, 2, 1], "2024": [3, 2, 2]},
                       "donem_hakem_ari": {"2023": 0.9, "2024": 0.7},
                       "degisme": {m: (0.0 if i % 2 else 0.25) for i, m in enumerate(KUM)},
                       "gorulme": {m: 30 for m in KUM}, "degisme_ort": 0.125, "onyukleme_ari": 0.8, "ornek": 50,
                       "alt_orneklem": 0.85, "kural_ari": {"k2": 0.83, "k3": 0.91}, "k2_degisen": 1, "kural_magaza": 7},
        "yeni_magaza": {"komsu": 5, "varsayilan": "knn",
                        "yontemler": {y_: {"ayni_bolme": 8, "ozet": _yeni_ozet(d, mt),
                                           "magazalar": [{"magaza_id": m, "gercek_kume": ML[m], "atanan": ML[m],
                                                          "metropol": _MAGAZA[m][5], "dogru_kume": True,
                                                          "dogru_segment": True} for m in KUM]}
                                      for y_, d, mt in (("knn", 7, 2), ("merkez", 6, 1))},
                        "statik_kural": {"k1": _yeni_ozet(5, 1), "k4": _yeni_ozet(5, 0)},
                        "gercek": {YENI: {"knn": 0, "merkez": 0, "ad": "Kocaeli 1", "sehir": "Kocaeli", "bolge": "Marmara",
                                          "tip": "AVM", "metrekare": 900, "metropol": False, "gecmis_hafta": 0,
                                          "k1": K1[YENI], "k2": "C", "k3": K3[YENI], "k4": K4[YENI],
                                          "gizli": "anadolu_aile", "knn_segment": "anadolu_aile",
                                          "merkez_segment": "anadolu_aile"}},
                        "kume_cogunluk_segment": {"0": "anadolu_aile", "1": "metropol_genc", "2": None}},
        "ablasyon": {"alt_blok": {a: _izgara(1.0 if a in ("S1", "S1_stoklu") else 0.1)
                                  for a in ("S1", "S2", "S4", "S5", "S1+olcek", "S1_stoklu")},
                     "sutun": {a: _izgara(0.9) for a in ("S1", "S2")}, "k2_ml_ari": 0.03,
                     "uyum": {"S1|S1_stoklu": 1.0, "S2|S4": 1.0, "S1|S1+olcek": 0.1, "S2|S5": 0.4},
                     "sabit_k": 3, "sabit_yontem": "kmeans"},
        "hikaye": {"cift1": ["M02", "M01"], "cift2": ["M02", "M05"],
                   "kalemler": [{"ozellik": "karisim/Collection/kalip/regular", "a": 0.30, "b": 0.13}],
                   "kalemler2": [{"ozellik": "karisim/Collection/kalip/regular", "c": 0.30, "d": 0.31}],
                   "mesafe": [1.8, 0.6], "esikler": {"ust": 1.6, "alt": 1.0}, "kuyruk": [0.75, 0.25], "gevseyen": [],
                   "elenen": 0, "dogrulama": {"cift1_farkli": True, "cift2_ayni": True,
                                              "segmentler": {m: GIZLI[m] for m in ("M02", "M01", "M05")}},
                   "alternatif": None,
                   "magazalar": {m: {"ad": _MAGAZA[m][0], "sehir": _MAGAZA[m][1], "bolge": _MAGAZA[m][2],
                                     "tip": _MAGAZA[m][3], "metrekare": _MAGAZA[m][4], "istanbul": _MAGAZA[m][6],
                                     "k2": K2[m], "k3": K3[m], "k4": K4[m], "ml_kume": ML[m], "net_ciro": CIRO[m],
                                     "gizli_segment": GIZLI[m]} for m in ("M02", "M01", "M05")},
                   "ml": {"aile": "S1", "yontem": "kmeans", "k": 3, "kimlik": ml_kimlik}, "hakemsiz_ayni": True},
        "demo": _demo(),
        "gizli_kapsam": GIZLI,
    }
    return copy.deepcopy(s)
