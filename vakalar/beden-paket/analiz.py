"""Koşusuz analiz: raporun eğri, paket, tasarım, K eğrisi, kahin ve depo girdileri (`cikti/analiz.json`).

    cd vakalar/beden-paket
    PYTHONIOENCODING=utf-8 .venv/Scripts/python analiz.py                  # TAM yol 0 → cikti/analiz.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python analiz.py --olcek KUCUK    # cikti/kucuk/analiz.json

Ölçüm tarafıdır (paket dışında, vaka kökünde; `rapor.py` gibi): hakemi okur (gerçek beden payı ve etkin
kayma; yalnız ölçü), simülasyon koşmaz. Yol 0'ın kararları oyunun kendi girdisinden kurulur
(`oyun.YolGirdisi(0)`: eğri, ns, ağırlık, depo, tasarımlar), böylece rapordaki tasarım oyun.json'daki
koşuların tasarımıyla aynıdır (rapor bunu denetler). Yolun Lumoda koşusu (doğrulama kolu) önbellekte
olmalıdır (`python -m beden_paket.kosucu dogrulama`); yoksa koşulur.

Bloklar (`analiz.json`):

    veri      kapsam, oyun option'ları, ns özeti
    paket     Lumoda paketi, zincir, alım / depo / ilk dağıtım / replenishment beden adetleri, Lumoda
              paketinin zincire, mağaza eğrilerine (hakemsiz) ve gerçek paya (hakemli) uzaklığı
    egri      κ ve tablosu, örneklem, ağırlık, profiller, yedek kural, sansür tanısı; gerçeğe L1 (ham,
              düzeltilmiş, daraltılmış, profil, zincir); sansürün büyüklüğü; hat ayrımı (havuz,
              Collection, Basic+NOS: hakemli ve hakemsiz, Ruling R5); kararlılık (SS24 ↔ SS25 karar
              anı, hakemsiz); profilin kaymaya ARI'si ve çapraz tablosu; okunamayan / az örnekli mağaza
    tasarim   yol 0'ın her tasarımlı kolu: desenler, atama, profil × desen, uyumsuzluk, aynı kol;
              mağazaya giden beden payının gerçek paya (hakemli) ve eğriye (hakemsiz) ağırlıklı L1'i
    k_egrisi  `oyun.k_egrisi` (7 ve 12'li, K = 1..4 ve mağaza; Lumoda)
    kahin     `oyun.kahin_ayni_mi` (P2) ve ayrılan mağazaların ağırlık payı (Ruling R15)
    depo      iki depo tanımı (Ruling R16): ilk sipariş adedi ↔ hatalı düşülmüş; depo payları ve
              tasarımların iki tanımda aynı olup olmadığı
    ilk_sevkiyat  İlk Sevkiyat'ın Lumoda koşularının anahtarları değişmedi mi (TAM)

`kod`: analizi belirleyen kodun özeti (paketin bütün modülleri ve bu dosya; `hikaye_*` hariç); rapor
eski analizi reddeder.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from allocation import motor
from allocation import oyun as al_oyun

from beden_paket import egri as egri_modulu
from beden_paket import hakem, kaynak, kosucu, olcutler_egri, oyun, paket_tasarim, sabitler

KOK = Path(__file__).resolve().parent
SURUM = 1
SUTUNLAR = list(paket_tasarim.SUTUNLAR)
HATLAR = {"havuz": egri_modulu.HATLAR, "Collection": ("Collection",), "Basic+NOS": ("Basic", "NOS")}
TASARIM_KOLLARI = ("p1", "p2", "p1_12", "p3_12", "pm_12", "p2_ham")


def hedef(olcek: str = "tam") -> Path:
    return (sabitler.CIKTI if olcek == "tam" else sabitler.CIKTI / "kucuk") / "analiz.json"


def kod_ozeti() -> str:
    """Analizi belirleyen kodun özeti: paketin modülleri (`hikaye_*` hariç) ve bu dosya (LF)."""
    paket = KOK / "beden_paket"
    dosyalar = sorted(y for y in paket.glob("*.py") if not y.stem.startswith("hikaye_")) + [Path(__file__).resolve()]
    h = hashlib.sha256()
    for y in dosyalar:
        h.update(y.name.encode() + b"\0" + y.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def _f(x) -> float | None:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def _satir(a) -> list[float]:
    return [float(x) for x in np.asarray(a, dtype="float64")]


def _l1(A: pd.DataFrame, B: pd.DataFrame, ids) -> pd.Series:
    return olcutler_egri._l1(A, B, list(ids))


# ---------------------------------------------------------------------------
# Bloklar
# ---------------------------------------------------------------------------


def veri_blogu(G: oyun.YolGirdisi) -> dict:
    k = G._kararlar["kapsam"]
    sutun = ["magaza_id", "ad", "sehir", "bolge", "istanbul", "tip", "gecmis_hafta", "yeni"]
    kap = [{s: (bool(r[s]) if s in ("istanbul", "yeni") else int(r[s]) if s == "gecmis_hafta" else str(r[s]))
            for s in sutun} for _, r in k.iterrows()]
    o = G.w.optionlar.set_index(G.w.optionlar["option_id"].astype(str))
    setler = o.loc[G.oyun_ids, "beden_seti"].astype(str).value_counts().sort_index()
    return {"karar_gunu": sabitler.KARAR_GUNU.date().isoformat(), "kapsam": kap,
            "oyun_option": len(G.oyun_ids), "bes_bedenli_option": len(G.bes_optionlar),
            "beden_setleri": {a: int(n) for a, n in setler.items()}, "ns": G.bilgi()["ns"],
            "kaynak": G.kaynak_adi}


def _replenishment_beden(G: oyun.YolGirdisi) -> list[int]:
    """Lumoda koşusunda (doğrulama kolu) beş bedenli oyun option'larına giden replenishment, beden sırası
    başına adet."""
    u = G.w.urunler
    u = u[u["option_id"].astype(str).isin(set(G.bes_optionlar))]
    sira = dict(zip(u["urun_id"].astype(str), u["beden_sira"].astype(int)))
    sv = G.lumoda.tablo("sevkiyat", sutunlar=["urun_id", "adet", "tip"], urunler=list(sira))
    sv = sv[sv["tip"].astype(str) == "replenishment"]
    b = sv["urun_id"].astype(str).map(sira)
    t = sv.groupby(b)["adet"].sum().reindex(range(1, 6), fill_value=0)
    return [int(x) for x in t]


def paket_blogu(G: oyun.YolGirdisi, gercek: pd.DataFrame, ok: list[str]) -> dict:
    e = G.egri
    L = np.asarray(sabitler.LUMODA_PAKET, dtype="float64")
    p = L / L.sum()
    Lp = pd.DataFrame([p] * len(e.magaza), index=e.magaza.index, columns=SUTUNLAR)
    hakemsiz = _l1(Lp, e.magaza, ok)
    hakemli = _l1(Lp, gercek, list(e.magaza.index))
    d = G.bilgi()["depo"]
    return {"lumoda": [int(x) for x in sabitler.LUMODA_PAKET], "adet": int(L.sum()),
            "zincir": _satir(e.zincir), "zincir_l1": float(np.abs(p - e.zincir).sum()),
            "magaza_l1": {"ortalama": float(hakemsiz.mean()), "en_az": float(hakemsiz.min()),
                          "en_cok": float(hakemsiz.max()), "en_cok_magaza": str(hakemsiz.idxmax()),
                          "magaza": len(ok)},
            "gercek_l1": {"ortalama": float(hakemli.mean()), "en_cok": float(hakemli.max()), "magaza": len(hakemli)},
            "ilk_siparis": d["ilk_siparis"], "depo": d["depo"], "ilk_dagitim": d["lumoda_giden"],
            "replenishment": _replenishment_beden(G),
            "aday_7": int(len(paket_tasarim.adaylar(7))), "aday_12": int(len(paket_tasarim.adaylar(12)))}


def _hat_satiri(et, kapsam, ok, gercek, hatlar) -> dict:
    duz = egri_modulu.duzeltilmis(et, kapsam, sabitler.KARAR_GUNU, hatlar=hatlar)
    ham = egri_modulu.ham(et, kapsam, sabitler.KARAR_GUNU, hatlar=hatlar)
    ids = [m for m in ok if not duz.loc[m].isna().any() and not ham.loc[m].isna().any()]
    fark = (duz.loc[ids, SUTUNLAR] - ham.loc[ids, SUTUNLAR]).abs().to_numpy()
    kappa, tablo = egri_modulu.kappa_sec(et, sabitler.KARAR_GUNU, hatlar=hatlar)
    k0 = tablo.loc[tablo["kappa"] == 0, "l1"]
    return {"hakemli_ham": float(_l1(ham, gercek, ids).mean()), "hakemli_duzeltilmis": float(_l1(duz, gercek, ids).mean()),
            "magaza": len(ids), "sansur_en_buyuk": float(fark.max()), "sansur_ortalama": float(fark.mean()),
            "hakemsiz_duzeltilmis": float(k0.iloc[0]) if len(k0) else None,
            "hakemsiz_secilen": float(tablo.loc[tablo["kappa"] == kappa, "l1"].iloc[0]), "kappa": float(kappa),
            "hakemsiz_magaza": int(tablo["magaza"].iloc[0])}


def egri_blogu(G: oyun.YolGirdisi, et: dict, gercek: pd.DataFrame, kayma: pd.Series) -> dict:
    e = G.egri
    kapsam = G._kararlar["kapsam"]
    ids = list(e.magaza.index)
    ok = [m for m in ids if e.kaynak[m] == "magaza"]
    okunamaz = [m for m in ids if e.kaynak[m] != "magaza"]
    ham = egri_modulu.ham(et, kapsam, sabitler.KARAR_GUNU)
    P = pd.DataFrame([e.profil_egrisi.loc[e.profil[m]].to_numpy() for m in ids], index=e.magaza.index, columns=SUTUNLAR)
    Z = pd.DataFrame([e.zincir] * len(ids), index=e.magaza.index, columns=SUTUNLAR)
    l1 = {ad: float(_l1(E, gercek, ok).mean())
          for ad, E in (("ham", ham), ("duzeltilmis", e.duzeltilmis), ("daraltilmis", e.magaza), ("profil", P),
                        ("zincir", Z))}
    fark = (e.duzeltilmis.loc[ok, SUTUNLAR] - ham.loc[ok, SUTUNLAR]).abs().to_numpy()
    kapsam_kal = kaynak.kapsam(et, sabitler.KAL_KARAR_GUNU)
    duz_kal = egri_modulu.duzeltilmis(et, kapsam_kal, sabitler.KAL_KARAR_GUNU)
    n_kal = egri_modulu.orneklem(et, kapsam_kal, sabitler.KAL_KARAR_GUNU)
    ok_kal = egri_modulu.okunabilir(duz_kal, n_kal)
    ortak = [m for m in ok if m in ok_kal.index and ok_kal[m]]
    karar = olcutler_egri.kararlilik(duz_kal.loc[ortak], e.duzeltilmis.loc[ortak])
    capraz = pd.crosstab(e.profil.loc[ok], kayma.reindex(ok)).sort_index()
    w = e.agirlik.loc[ok]
    az = [m for m in ok if w[m] < 0.9]
    yeni = {}
    for m in okunamaz:
        a = e.yeni_atama.get(m)
        yeni[m] = {"kaynak": e.kaynak[m], "n": float(e.n.get(m, 0.0)), "statik_profil": a, "profil": e.profil[m],
                   "kayma": int(kayma[m]), "l1_son": float(_l1(e.magaza, gercek, [m]).iloc[0]),
                   "l1_zincir": float(_l1(Z, gercek, [m]).iloc[0]),
                   "l1_statik_profil": None if a is None else float(np.abs(e.profil_egrisi.loc[a].to_numpy()
                                                                            - gercek.loc[m, SUTUNLAR].to_numpy()).sum())}
    return {
        "kappa": e.kappa, "kappa_izgara": [float(x) for x in egri_modulu.KAPPA_IZGARASI],
        "kappa_tablosu": None if e.kappa_tablosu is None else [{"kappa": float(r["kappa"]), "l1": float(r["l1"]),
                                                               "magaza": int(r["magaza"])}
                                                              for _, r in e.kappa_tablosu.iterrows()],
        "magaza": len(ids), "okunabilir": len(ok), "okunamaz": okunamaz, "en_az_adet": sabitler.EGRI_EN_AZ_ADET,
        "n_medyan": float(e.n.loc[ok].median()), "n_en_az": float(e.n.loc[ok].min()),
        "agirlik_medyan": float(w.median()), "agirlik_en_az": float(w.min()),
        "az_ornekli": {m: {"n": float(e.n[m]), "w": float(w[m]), "l1": float(_l1(e.magaza, gercek, [m]).iloc[0]),
                           "kayma": int(kayma[m])} for m in az},
        "profil": {p: int(n) for p, n in e.profil.value_counts().sort_index().items()},
        "profil_magaza": {str(m): str(p) for m, p in e.profil.items()},
        "profil_okunur": {p: int(n) for p, n in e.profil.loc[ok].value_counts().sort_index().items()},
        "profil_egrisi": {p: _satir(r) for p, r in e.profil_egrisi.iterrows()}, "zincir": _satir(e.zincir),
        "yeni_secim": {a: (_f(v) if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else v)
                       for a, v in e.yeni_secim.items()},
        "yeni": yeni, "sansur_tanisi": {a: (float(v) if isinstance(v, (float, np.floating)) else int(v))
                                        for a, v in e.sansur.items()},
        "l1": l1, "l1_magaza": len(ok), "sansur_en_buyuk": float(fark.max()), "sansur_ortalama": float(fark.mean()),
        "hat": {ad: _hat_satiri(et, kapsam, ok, gercek, h) for ad, h in HATLAR.items()},
        "kararlilik": {"l1": float(karar.mean()), "magaza": len(karar),
                       "kal_karar_gunu": sabitler.KAL_KARAR_GUNU.date().isoformat()},
        "ari": olcutler_egri.ari(e.profil.loc[ok], kayma), "ari_magaza": len(ok),
        "kayma_ham_2": int((hakem.kayma(G.w, kirp=False).reindex(ids) == 2).sum()),
        "profil_kayma": {"satirlar": [str(x) for x in capraz.index], "sutunlar": [int(x) for x in capraz.columns],
                         "degerler": capraz.to_numpy().astype(int).tolist()},
        "ham_duz_l1": {"ortalama": float(_l1(ham, e.duzeltilmis, ok).mean()), "en_cok": float(_l1(ham, e.duzeltilmis, ok).max())},
    }


def _giden_uzaklik(desenler, atama: pd.Series, E: pd.DataFrame, w: pd.Series) -> float:
    """Mağazaya giden beden payının (desen / adet) `E`'ye L1'i, ağırlıkla ortalanmış (beş bedenli oyun)."""
    D = np.asarray(desenler, dtype="float64")
    ids = list(atama.index)
    pay = D[atama.loc[ids].astype(int).to_numpy()] / D.sum(axis=1)[atama.loc[ids].astype(int).to_numpy(), None]
    l1 = np.abs(pay - E.loc[ids, SUTUNLAR].to_numpy(dtype="float64")).sum(axis=1)
    ww = w.reindex(ids).fillna(0.0).to_numpy()
    return float((l1 * ww).sum() / ww.sum())


def tasarim_blogu(G: oyun.YolGirdisi, gercek: pd.DataFrame) -> dict:
    e = G.egri
    out = {}
    L = np.asarray([sabitler.LUMODA_PAKET])
    tek = pd.Series(0, index=e.magaza.index)
    out["lumoda"] = {"paket_adet": sabitler.PAKET_ADET, "desenler": [paket_tasarim.desen_adi(L[0])],
                     "giden_gercek_l1": _giden_uzaklik(L, tek, gercek, G.agirlik(7)),
                     "giden_egri_l1": _giden_uzaklik(L, tek, e.magaza, G.agirlik(7))}
    for kol in TASARIM_KOLLARI:
        k = oyun.KOLLAR[kol]
        t = G.tasarim(kol)
        w = G.agirlik(k.adet)
        adlar = [paket_tasarim.desen_adi(d) for d in t.desenler]
        capraz = paket_tasarim.desen_profil_capraz(t, e.profil)
        say = pd.Series([adlar[int(i)] for i in t.atama.to_numpy()], index=t.atama.index)
        out[kol] = {"paket_adet": k.adet, "K": k.K, "egri": k.egri, "desenler": adlar,
                    "atama": {str(m): d for m, d in say.items()},
                    "desen_magaza": {d: int((say == d).sum()) for d in adlar},
                    "desen_agirlik": {d: float(w.reindex(say.index[say == d]).sum() / w.sum()) for d in adlar},
                    "profil_desen": {"satirlar": [str(x) for x in capraz.index], "sutunlar": [str(x) for x in capraz.columns],
                                     "degerler": capraz.to_numpy().astype(int).tolist()},
                    "toplam_uyumsuzluk": float(t.toplam_uyumsuzluk), "paket_basina": float(t.toplam_uyumsuzluk / w.sum()),
                    "en_iyi_mi": bool(t.en_iyi_mi), "yontem": t.yontem, "depo_uygun": t.depo_uygun,
                    "ayni": oyun.ayni_kol(G, kol),
                    "giden_gercek_l1": _giden_uzaklik(t.desenler, t.atama, gercek, w),
                    "giden_egri_l1": _giden_uzaklik(t.desenler, t.atama, G.egri_tablosu(k.egri), w)}
    return out


def kahin_blogu(G: oyun.YolGirdisi, gercek: pd.DataFrame) -> dict:
    k = G.kahin("p2")
    w = G.agirlik(7)
    t = G.tasarim("p2")
    G_ = gercek.loc[list(t.atama.index), SUTUNLAR].to_numpy(dtype="float64")
    kahin = pd.Series(np.argmin(paket_tasarim._eksik(G_, np.asarray(t.desenler)), axis=1), index=t.atama.index)
    adlar = [paket_tasarim.desen_adi(d) for d in t.desenler]
    return {**k, "farkli_agirlik_payi": float(w.reindex(k["farkli_magaza"]).fillna(0).sum() / w.sum()),
            "farkli": {m: {"tasarim": adlar[int(t.atama[m])], "kahin": adlar[int(kahin[m])],
                           "kaynak": G.egri.kaynak[m], "paket": float(w.get(m, 0.0))} for m in k["farkli_magaza"]},
            "giden_gercek_l1_kahin": _giden_uzaklik(t.desenler, kahin, gercek, w)}


def depo_blogu(G: oyun.YolGirdisi) -> dict:
    dep, sip = G._kararlar["depo"].sum(axis=0), G._kararlar["siparis"].sum(axis=0)
    out = {"ilk_siparis": [int(x) for x in sip], "hatali_dusulmus": [int(x) for x in dep], "pay": {}, "tasarim_ayni": {}}
    for a in (7, 12):
        w = float(G.agirlik(a).sum())
        out["pay"][str(a)] = {"siparis": _satir(sip.to_numpy() / (a * w)), "hatali_dusulmus": _satir(dep.to_numpy() / (a * w)),
                              "oyun": _satir(G.depo_payi(a))}
    for kol in TASARIM_KOLLARI:
        k = oyun.KOLLAR[kol]
        w = G.agirlik(k.adet)
        tas = {ad: paket_tasarim.tasarla(G.egri_tablosu(k.egri), w, k.K, np.asarray(out["pay"][str(k.adet)][ad]),
                                         adet=k.adet) for ad in ("siparis", "hatali_dusulmus")}
        out["tasarim_ayni"][kol] = {"iki_tanim": oyun.ayni_tasarim(tas["siparis"], tas["hatali_dusulmus"]),
                                    "oyun_siparis": oyun.ayni_tasarim(G.tasarim(kol), tas["siparis"])}
    return out


def ilk_sevkiyat_blogu(olcek: str) -> dict | None:
    """İlk Sevkiyat'ın önbellekli Lumoda koşularının anahtarları (TAM; salt okunur)."""
    if olcek != "tam":
        return None
    yollar_yolu = motor.KOSU_DIZINI.parent / "yollar.json"
    yollar = json.loads(yollar_yolu.read_text(encoding="utf-8"))["yollar"] if yollar_yolu.is_file() else {}
    satir = {}
    for p in range(sabitler.YOL_SAYISI):
        beklenen = al_oyun.MEVCUT_ANAHTARLAR.get("lumoda") if p == 0 else (
            yollar.get(str(p), {}).get("kosular", {}).get("lumoda", {}).get("anahtar"))
        a = kosucu.allocation_anahtari(p)
        satir[str(p)] = {"anahtar_ayni": a == beklenen, "onbellekte": kosucu.allocation_lumoda(p) is not None}
    return satir


def kur(ortam: oyun.Ortam) -> dict:
    t0 = time.perf_counter()
    G = oyun.YolGirdisi(0, ortam)
    gercek, kayma = hakem.gercek_pay(G.w), hakem.kayma(G.w)
    con, sakla = G._baglanti()
    try:
        et = egri_modulu.egri_tablolari(con, sabitler.KARAR_GUNU)
    finally:
        con.close()
        del sakla
    e = G.egri
    ok = [m for m in e.magaza.index if e.kaynak[m] == "magaza"]
    sonuc = {"surum": SURUM, "olcek": ortam.olcek, "kod": kod_ozeti(), "oyun_olcum_kodu": oyun.olcum_kodu(),
             "lumoda": G.lumoda.dizin.name, "lumoda_anahtar": G.lumoda.meta["anahtar"],
             "veri": veri_blogu(G), "paket": paket_blogu(G, gercek, ok), "egri": egri_blogu(G, et, gercek, kayma)}
    del et
    sonuc |= {"tasarim": tasarim_blogu(G, gercek), "k_egrisi": G.k_egrisi(), "kahin": kahin_blogu(G, gercek),
              "depo": depo_blogu(G), "ilk_sevkiyat": ilk_sevkiyat_blogu(ortam.olcek)}
    print(f"analiz: {time.perf_counter() - t0:.0f} sn", file=sys.stderr, flush=True)
    return sonuc


def _jsonla(x):
    if isinstance(x, dict):
        return {str(k): _jsonla(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonla(v) for v in x]
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    return x


def yaz(sonuc: dict, yol: Path) -> Path:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(_jsonla(sonuc), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return yol


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="analiz.py", description=__doc__.splitlines()[0])
    p.add_argument("--olcek", default="TAM", type=str.upper, choices=["TAM", "KUCUK"])
    a = p.parse_args(argv)
    olcek = a.olcek.lower()
    ortam = oyun.Ortam(olcek=olcek, cikti=sabitler.CIKTI if olcek == "tam" else sabitler.CIKTI / "kucuk",
                       ilerleme=False)
    print(f"yazıldı: {yaz(kur(ortam), hedef(olcek))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
