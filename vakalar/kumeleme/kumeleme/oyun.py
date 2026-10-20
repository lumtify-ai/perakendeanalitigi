"""Koşum (ölçüm yanı): kural grupları, bütün aileler × yöntemler × k, öneri, hakem, kararlılık, yeni
mağaza, ablasyon, hikâye ve demo bileşimleri tek koşuda; `cikti/sonuc.json`, `cikti/hikaye.json` ve
git'e giren `kumeler.json`.

    cd vakalar/kumeleme
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m kumeleme.oyun

Bu bir **ölçüm** modülüdür (`tests/test_sizinti.py`, `IZINLI_MODULLER`): gizli segmenti `hakem`'den
okur ve yalnız sonradan ölçer. Hiçbir seçim (k, aile, yöntem, öneri, yeni mağaza ataması, hikâye
sırası) gizli segmente bakmaz; seçimler karar modüllerindedir (`kural`, `ogren`, `yeni_magaza`,
`hikaye_sec`) ve burada yalnız çağrılır. Raporun (`rapor.py`) bastığı her sayı `sonuc.json`'dadır;
rapor veriyi okumaz, kümelemeyi koşmaz.

**Kimlik.** `sonuc.json` bugünkü paket kodunun özetini (`kod_ozeti`: `kumeleme/*.py`, satır sonları LF)
ve v4 dosyasının parmak izini (`veri_parmak_izi`: ad, boyut, değişiklik zamanı) taşır; rapor ikisini
bugünküyle karşılaştırır (farklıysa koşu eskidir: önce bu modül).

**Bloklar** (`kos`, bu sırayla; her biri `sonuc.json`'da bir anahtar):

    veri        kapsam (69 aday, 67 kümelenen, 2 yeni), dışarıda kalan fiziksel mağazalar, pencereler
    kural       K1-K4 etiketleri (kapsamın her mağazası), net ciro, ciro sınıfı eşikleri
    ozellik     aile başına boyut, doldurulan / düşen hücreler, kimlik
    ml          önerinin aday tablosu (S1, S2 × kmeans, ward × k; hakem ARI sonradan eklenir), boş
                siluet (adaylar), kararlılık-önce kuralının seçeceği aday (Ruling R9 açıklaması),
                önerinin yorumu
    hakem       K1-K4 ve öneri: ARI, AMI, toplam saflık, çapraz tablo, segment saflığı; metropol /
                metropol dışı ayrımı; K4 ↔ öneri (hakemsiz)
    kararlilik  önerinin yıllar arası ve önyükleme kararlılığı (`olcutler.kararlilik`), dönem
                bölmelerinin hakem ARI'si, K2 ve K3'ün yıllar arası ARI'si (aynı mağazalarda)
    yeni_magaza bırakbir (knn, merkez) ve doğruluk; statik kurallar (K1, K4) segment isabeti; iki
                gerçek yeni mağaza (`kumeler.json`'a knn ataması girer, Ruling R10)
    ablasyon    S1, S2, S4, S5, S1 + ölçek, S1 stoklu (alt blok ağırlığı) ve S1, S2 sütun orantılı
                ağırlık (Ruling R7) × yöntem × k: siluet, büyüklükler, hakem ARI/AMI, K2 ile ARI
    hikaye      `hikaye_kos.kayit` (aynı girdilerle; `cikti/hikaye.json` da yazılır)
    demo        {S1, S2, S4} × k {4..8}, k-means: hakem ARI, kararlılık (`ogren.kararlilik`), en küçük
                küme, siluet, kümeler (büyükten küçüğe) ve en ayırt edici özellikleri

**K2/K3 yıllar arası.** Önerinin yıllar arası karşılaştırmasıyla aynı mağazalarda (her iki dönemde de
`GECMIS_HAFTA_ESIGI` satışlı haftası olan) ve aynı dönem sonu günleriyle (`olcutler.DONEMLER`): ciro
sınıfı dönem sonundan önceki 12 ayın cirosuyla (`kural.ciro_sinifi`; kısa geçmişin yıllıklaştırması
için `gecmis_hafta` o günün `kaynak.kapsam`'ından), sıralama yalnız bu mağazalar arasında. K1 ve K4
statiktir: yıllar arası ARI tanım gereği 1.

**Yeni mağazada statik kural isabeti.** K1 ve K4 yalnız statik bilgiden kurulur, yeni mağaza satış
görmeden grubunu alır. Segment isabeti `olcutler.birakbir_dogruluk`'un kuralıyla: grubun, mağazanın
kendisi hariç çoğunluk segmenti (eşitlik ıska).
"""

import hashlib
import json
import math
import sys
import time
import warnings
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score

from kumeleme import (hakem, hikaye_kos, hikaye_sec, kaynak, kural, ogren, olcutler, ozellikler, sabitler,
                      yeni_magaza)

KAYIT_SURUMU = 1
PAKET = Path(__file__).resolve().parent
SONUC = sabitler.CIKTI / "sonuc.json"
HIKAYE = sabitler.CIKTI / "hikaye.json"
KUMELER = sabitler.KOK / "kumeler.json"

OZELLIK_AILELERI = ("S1", "S2", "S4", "S5")
# ablasyon aileleri: ad → (temel aile, bloklar); S1 + ölçek S5'in ölçek bloğunu, S1 stoklu S4'ün
# karışım bloğunu kullanır (bloklar ayrı kurulur; sütun alt kümesi aynı tablodur)
ABLASYON_AILELERI: dict[str, tuple[str, tuple[str, ...]]] = {
    "S1": ("S1", ("karisim",)),
    "S2": ("S2", ("karisim", "beden", "mevsim")),
    "S4": ("S4", ("karisim_stoklu", "beden_stoklu", "mevsim_stoklu")),
    "S5": ("S5", ("karisim", "beden", "mevsim", "olcek")),
    "S1+olcek": ("S5", ("karisim", "olcek")),
    "S1_stoklu": ("S4", ("karisim_stoklu",)),
}
SUTUN_AGIRLIK_AILELERI = ("S1", "S2")       # Ruling R7: sütun orantılı ağırlık ablasyonu
DEMO_AILELERI = ("S1", "S2", "S4")
DEMO_K = (4, 5, 6, 7, 8)
DEMO_YONTEM = "kmeans"
YORUM_N = 3
KURALLAR = ("k1", "k2", "k3", "k4")
GIZLI_ALAN = "olcum_gizli_segment"   # kumeler.json: yalnız ölçüm (kahin küme kolu)


# ---------------------------------------------------------------------------
# Kimlik
# ---------------------------------------------------------------------------


def kod_ozeti(paket: Path = PAKET) -> str:
    """Paket kaynaklarının (`*.py`, ada göre) ad + içerik SHA-256'sı; satır sonları LF."""
    h = hashlib.sha256()
    for yol in sorted(Path(paket).glob("*.py")):
        h.update(yol.name.encode("utf-8") + b"\0")
        h.update(yol.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def veri_parmak_izi(yol: Path | None = None) -> list:
    """v4 DuckDB dosyasının kimliği: ad, boyut, değişiklik zamanı (yoksa "yok")."""
    yol = Path(yol) if yol is not None else Path(kaynak.VERITABANI)
    if not yol.exists():
        return ["yok", yol.name]
    d = yol.stat()
    return [yol.name, d.st_size, d.st_mtime_ns]


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _j(x):
    """JSON'a uygun değer (numpy, pandas, tuple, NaN → None)."""
    if isinstance(x, dict):
        return {str(k): _j(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_j(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(float(x)) else float(x)
    if isinstance(x, pd.Timestamp):
        return x.strftime("%Y-%m-%d")
    return x


def _etiketler(s: pd.Series) -> dict:
    """magaza_id → etiket (kimlik sırasıyla)."""
    s = s.copy()
    s.index = s.index.astype(str)
    return {m: _j(s[m]) for m in sorted(s.index)}


def _capraz(e: pd.Series, gizli: pd.Series) -> dict:
    t = olcutler.capraz(e, gizli)
    return {"satirlar": [_j(v) for v in t.index], "sutunlar": [str(c) for c in t.columns],
            "degerler": [[int(v) for v in r] for r in t.to_numpy()]}


def metin(icerik: dict) -> str:
    return json.dumps(_j(icerik), ensure_ascii=False, indent=1) + "\n"


# ---------------------------------------------------------------------------
# Girdiler
# ---------------------------------------------------------------------------


def _ham_satis(con, bas, bit) -> pd.DataFrame:
    s = con.execute("select * from satis where tarih >= ? and tarih < ?",
                    [pd.Timestamp(bas).to_pydatetime(), pd.Timestamp(bit).to_pydatetime()]).df()
    s["magaza_id"] = s["magaza_id"].astype(str)
    return s


def girdiler(con, karar_gunu=sabitler.KARAR_GUNU) -> dict:
    """Yayımlanan v4'ten kapsam, ham özellik tabloları (S1, S2, S4, S5) ve kural grupları."""
    t = kaynak.yayimlanan_tablolar(con, ("magaza", "magaza_olay", "urun"))
    gunluk = con.execute(
        "select distinct tarih::date::timestamp as tarih, magaza_id::varchar as magaza_id, "
        "1 as adet from satis where adet > 0 and tarih < ?", [karar_gunu]).df()
    k = kaynak.kapsam(t["magaza"], t["magaza_olay"], gunluk, karar_gunu)
    ham = _ham_satis(con, karar_gunu - pd.DateOffset(years=1), karar_gunu)
    ids = k.loc[k["kumelenir"], "magaza_id"]
    X = {a: ozellikler.ozellik_tablosu(con, ids, t["urun"], karar_gunu, a) for a in OZELLIK_AILELERI}
    k2 = kural.ciro_sinifi(ham, k, karar_gunu)
    return {"tablolar": t, "gunluk": gunluk, "kapsam": k, "X": X, "ciro": kural.net_ciro(ham, k, karar_gunu),
            "k1": kural.bolge(k), "k2": k2, "k3": kural.bolge_ciro(k, k2), "k4": kural.konum(k)}


def aile_tablosu(X: dict, ad: str) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Ablasyon ailesinin ham tablosu ve blokları (`ABLASYON_AILELERI`)."""
    temel, bloklar = ABLASYON_AILELERI[ad]
    T = X[temel]
    sutun = [c for c in T.columns if str(c).split(ozellikler.AYRAC, 1)[0] in bloklar]
    return T[sutun], bloklar


# ---------------------------------------------------------------------------
# Bloklar
# ---------------------------------------------------------------------------


def veri_blogu(g: dict, karar_gunu) -> dict:
    m = g["tablolar"]["magaza"]
    k = g["kapsam"]
    tip = m["tip"].astype(str)
    fiziksel = m[~tip.isin(kaynak.YASAK_TIP)]
    lansman = kaynak.lansman_gunu(karar_gunu)
    disarida = []
    for _, r in fiziksel[~fiziksel["magaza_id"].astype(str).isin(k["magaza_id"])].iterrows():
        acilis = pd.Timestamp(r["acilis_tarihi"])
        neden = "lansmandan sonra açılıyor" if acilis > lansman else "kapanmış ya da kapanış kararı verilmiş"
        disarida.append({"magaza_id": str(r["magaza_id"]), "ad": str(r["ad"]), "neden": neden,
                         "acilis": acilis, "kapanis": pd.Timestamp(r["kapanis_tarihi"])
                         if pd.notna(r["kapanis_tarihi"]) else None})
    bas, bit = ozellikler.pencere(karar_gunu)
    return {
        "karar_gunu": pd.Timestamp(karar_gunu), "lansman": lansman,
        "tip_sayilari": {str(a): int(n) for a, n in tip.value_counts().sort_index().items()},
        "fiziksel": len(fiziksel), "disarida": sorted(disarida, key=lambda d: d["magaza_id"]),
        "kapsam": [{c: _j(r[c]) for c in ("magaza_id", "ad", "sehir", "bolge", "tip", "metrekare", "enlem",
                                           "istanbul", "metropol", "gecmis_hafta", "kumelenir", "yeni")}
                   for _, r in k.iterrows()],
        "ozellik_penceresi": [bas, bit - pd.Timedelta(days=1)],
        "ciro_penceresi": [pd.Timestamp(karar_gunu) - pd.DateOffset(years=1),
                           pd.Timestamp(karar_gunu) - pd.Timedelta(days=1)],
        "gecmis_hafta_esigi": sabitler.GECMIS_HAFTA_ESIGI,
    }


def kural_blogu(g: dict) -> dict:
    k = g["kapsam"]
    kum = k.loc[k["kumelenir"], "magaza_id"]
    ciro, k2 = g["ciro"], g["k2"]
    esik = {s: float(ciro[kum][k2[kum] == s].min()) for s in ("A", "B")}
    yillik = k.set_index("magaza_id")
    kisa = sorted(m for m in kum if yillik.at[m, "gecmis_hafta"] < sabitler.TAM_YIL_HAFTA)
    return {"etiketler": {r: _etiketler(g[r]) for r in KURALLAR}, "net_ciro": _etiketler(ciro),
            "esikler": esik, "yillik_kisa": kisa,
            "oranlar": {"A": sabitler.CIRO_A, "B": sabitler.CIRO_B}, "k3_en_az": sabitler.K3_EN_AZ}


def ozellik_blogu(X: dict) -> dict:
    out = {}
    for ad in ABLASYON_AILELERI:
        T, bloklar = aile_tablosu(X, ad)
        Z = ozellikler.standartla(T, bloklar)
        doldurulan = {b: int(n) for b, n in X[ABLASYON_AILELERI[ad][0]].attrs.get("doldurulan", {}).items()
                      if b in bloklar}
        dusen = {b: int(n) for b, n in X[ABLASYON_AILELERI[ad][0]].attrs.get("dusen_satis", {}).items()
                 if b.split(ozellikler.AYRAC, 1)[0] in bloklar}
        out[ad] = {"bloklar": list(bloklar), "magaza": int(T.shape[0]), "sutun": int(T.shape[1]),
                   "standart_sutun": int(Z.shape[1]),
                   "blok_sutun": {b: int(sum(str(c).split(ozellikler.AYRAC, 1)[0] == b for c in T.columns))
                                  for b in bloklar},
                   "alt_blok": {b: len({ozellikler.alt_blok(c) for c in T.columns
                                        if str(c).split(ozellikler.AYRAC, 1)[0] == b}) for b in bloklar},
                   "doldurulan": doldurulan, "dusen_satis": dusen, "kimlik": ozellikler.ozellik_kimligi(T)}
    return out


def _satirlar(tablo: pd.DataFrame) -> list[dict]:
    return [{c: _j(r[c]) for c in tablo.columns} for _, r in tablo.iterrows()]


def ml_blogu(g: dict, o: ogren.Oneri, gizli: pd.Series) -> dict:
    X = g["X"]
    tablo = o.tablo.copy()
    ari, ami = [], []
    Z = {a: ozellikler.standartla(X[a], a) for a in ogren.ONERI_AILELERI}
    for _, r in tablo.iterrows():
        e = ogren.kume(Z[r["aile"]], r["yontem"], int(r["k"]))
        a, b = olcutler.ari_ami(e, gizli)
        ari.append(a)
        ami.append(b)
    tablo["ari"], tablo["ami"] = ari, ami
    aday = tablo[tablo["secilen"]]
    bos = [{"aile": r["aile"], "yontem": r["yontem"], "k": int(r["k"]),
            "bos_siluet": ogren.bos_siluet(X[r["aile"]], r["aile"], r["yontem"], int(r["k"]))}
           for _, r in aday.iterrows()]
    # Ruling R9: kararlılık birincil olsaydı (ilk taslağın kuralı) seçilecek aday
    kk = aday.sort_values(["kararlilik", "k"], ascending=[False, True]).iloc[0]
    yor = ogren.yorum(X[o.aile], o.etiket, n=YORUM_N)
    ham = X[o.aile].copy()
    ham.index = ham.index.astype(str)
    ham = ham.loc[o.etiket.index]
    yorum = {}
    for c, liste in yor.items():
        uye = o.etiket.index[o.etiket == c]
        yorum[str(c)] = [{"ozellik": f, "z": z, "kume_ort": float(ham.loc[uye, f].mean()),
                          "genel_ort": float(ham[f].mean())} for f, z in liste]
    best = tablo[tablo["uygun"]].sort_values(["ari", "k"], ascending=[False, True]).iloc[0]
    return {"aday_tablosu": _satirlar(tablo), "bos_siluet": bos,
            "kararlilik_once": {"aile": kk["aile"], "yontem": kk["yontem"], "k": int(kk["k"]),
                                "kararlilik": float(kk["kararlilik"]), "siluet": float(kk["siluet"]),
                                "ari": float(kk["ari"])},
            "hakemle_en_iyi": {"aile": best["aile"], "yontem": best["yontem"], "k": int(best["k"]),
                               "ari": float(best["ari"])},
            "oneri": {"aile": o.aile, "yontem": o.yontem, "k": o.k, "kimlik": o.kimlik,
                      "etiket": _etiketler(o.etiket),
                      "boyutlar": sorted(o.etiket.value_counts().tolist(), reverse=True),
                      "ozellik_kimligi": ozellikler.ozellik_kimligi(X[o.aile])},
            "yorum": yorum, "en_kucuk_kume": sabitler.EN_KUCUK_KUME, "silu_esitlik": ogren.SILUET_ESITLIK, "kararlilik_esitlik": ogren.KARARLILIK_ESITLIK,
            "kararlilik_ornek": ogren.KARARLILIK_ORNEK, "kararlilik_oran": ogren.KARARLILIK_ORAN,
            "bos_ornek": ogren.BOS_ORNEK}


def _gruplar(g: dict, o: ogren.Oneri) -> dict[str, pd.Series]:
    kum = list(o.etiket.index)
    return {**{r: g[r].loc[kum] for r in KURALLAR}, "ml": o.etiket}


def sehir_iklim_uyumu(magazalar: pd.DataFrame, gizli_tablo: pd.DataFrame) -> dict:
    """Vakanın yazılı şehir → iklim tablosu (`kaynak.SEHIR_IKLIM`) ile simülatörün mağaza iklim ekseninin
    (gizli; yalnız ölçüm) şehir başına uyumu (Ruling R5). Online dışı bütün mağazaların şehirleri; yazım farkı
    ("ilıman" / "ılıman") yok sayılır."""
    m = magazalar[magazalar["tip"].astype(str) != "Online"][["magaza_id", "sehir"]].astype(str)
    gt = gizli_tablo.assign(magaza_id=gizli_tablo["magaza_id"].astype(str))
    t = m.merge(gt[["magaza_id", "iklim"]], on="magaza_id", how="inner")
    t["iklim"] = t["iklim"].astype(str).str.replace("ilıman", "ılıman")
    sehirler, farkli = sorted(t["sehir"].unique()), []
    for sehir in sehirler:
        gercek = sorted(t.loc[t["sehir"] == sehir, "iklim"].unique())
        if gercek != [kaynak.SEHIR_IKLIM.get(sehir)]:
            farkli.append({"sehir": sehir, "vaka": kaynak.SEHIR_IKLIM.get(sehir), "simulator": gercek})
    return {"sehir": len(sehirler), "ortusen": len(sehirler) - len(farkli), "farkli": farkli,
            "vaka_tablosu": len(kaynak.SEHIR_IKLIM)}


def hakem_blogu(g: dict, o: ogren.Oneri, gizli: pd.Series) -> dict:
    k = g["kapsam"].set_index("magaza_id")
    kum = list(o.etiket.index)
    metropol = k.loc[kum, "metropol"].astype(bool)
    out = {"segment_sayilari": {str(s): int(n) for s, n in gizli.loc[kum].value_counts().sort_index().items()},
           "gruplar": {}}
    for ad, e in _gruplar(g, o).items():
        ari, ami = olcutler.ari_ami(e, gizli)
        bolum = {}
        for alt, maske in (("metropol", metropol), ("metropol_disi", ~metropol)):
            ee = e[maske.to_numpy()]
            a2, m2 = olcutler.ari_ami(ee, gizli)
            bolum[alt] = {"n": int(len(ee)), "ari": a2, "ami": m2, "grup": int(ee.nunique()),
                          "segment": int(gizli.loc[ee.index].nunique())}
        sf = olcutler.saflik(e, gizli)
        out["gruplar"][ad] = {
            "ari": ari, "ami": ami, "toplam_saflik": olcutler.toplam_saflik(e, gizli), "grup": int(e.nunique()),
            "capraz": _capraz(e, gizli), "bolum": bolum,
            "saflik": {s: {"n": int(sf.at[s, "n"]), "kume": _j(sf.at[s, "kume"]), "pay": float(sf.at[s, "pay"]),
                           "kume_payi": float(sf.at[s, "kume_payi"])} for s in sf.index}}
    k4 = g["k4"].loc[kum]
    out["k4_ml"] = {"ari": float(adjusted_rand_score(k4.to_numpy(), o.etiket.to_numpy())),
                    "capraz": {"satirlar": sorted(k4.unique()), "sutunlar": sorted(int(c) for c in o.etiket.unique()),
                               "degerler": pd.crosstab(k4.to_numpy(), o.etiket.to_numpy()).to_numpy().tolist()}}
    out["sehir_iklim"] = sehir_iklim_uyumu(g["tablolar"]["magaza"], hakem.dunya().gizli_magaza)
    return out


def _k2_donem(g: dict, con, ortak: list[str], gun: pd.Timestamp) -> tuple[pd.Series, pd.Series]:
    t = g["tablolar"]
    kd = kaynak.kapsam(t["magaza"], t["magaza_olay"], g["gunluk"], gun)
    kd = kd[kd["magaza_id"].isin(ortak)].copy()
    if sorted(kd["magaza_id"]) != sorted(ortak):
        raise ValueError(f"{gun.date()}: dönem kapsamı ortak mağazaları içermiyor")
    kd["kumelenir"] = True
    kd["yeni"] = False
    ham = _ham_satis(con, gun - pd.DateOffset(years=1), gun)
    k2 = kural.ciro_sinifi(ham, kd, gun)
    return k2, kural.bolge_ciro(kd, k2)


def kararlilik_blogu(g: dict, con, o: ogren.Oneri, gizli: pd.Series) -> dict:
    fn = partial(ogren.kume, yontem=o.yontem, k=o.k)
    r = olcutler.kararlilik(fn, con, g["kapsam"], g["tablolar"]["urun"], aile=o.aile, ozellik=g["X"][o.aile])
    adlar = list(olcutler.DONEMLER)
    ortak = list(r["etiketler"][adlar[0]].index)
    donem_hakem = {d: olcutler.ari_ami(e, gizli)[0] for d, e in r["etiketler"].items()}
    kural_ari = {}
    k2s, k3s = {}, {}
    for d, (gun, _) in olcutler.DONEMLER.items():
        k2s[d], k3s[d] = _k2_donem(g, con, ortak, pd.Timestamp(gun))
    for ad, s in (("k2", k2s), ("k3", k3s)):
        kural_ari[ad] = float(adjusted_rand_score(s[adlar[0]].loc[ortak].to_numpy(),
                                                  s[adlar[1]].loc[ortak].to_numpy()))
    k2_degisen = int((k2s[adlar[0]].loc[ortak] != k2s[adlar[1]].loc[ortak]).sum())
    return {
        "donem": [{"donem": d, "bas": row["bas"], "bit": row["bit"] - pd.Timedelta(days=1), "hafta": int(row["hafta"]),
                   "magaza": int(row["magaza"])} for d, row in r["donem"].iterrows()],
        "disarida": r["disarida"],
        "satisli_hafta_disarida": {m: {d: int(r["satisli_hafta"].at[m, d]) for d in adlar} for m in r["disarida"]},
        "ari": {f"{a}|{b}": v for (a, b), v in r["ari"].items()},
        "donem_boyutlar": {d: sorted(e.value_counts().tolist(), reverse=True) for d, e in r["etiketler"].items()},
        "donem_hakem_ari": donem_hakem,
        "degisme": _etiketler(r["degisme"]), "gorulme": _etiketler(r["gorulme"]),
        "degisme_ort": r["degisme_ort"], "onyukleme_ari": r["onyukleme_ari"], "ornek": olcutler.ONYUKLEME_ORNEK,
        "alt_orneklem": float(o.tablo.loc[o.tablo["oneri"], "kararlilik"].iloc[0]),
        "kural_ari": kural_ari, "k2_degisen": k2_degisen, "kural_magaza": len(ortak),
    }


def _ozet(ozet: pd.DataFrame, tablo: pd.DataFrame) -> dict:
    gruplar = {"hepsi": tablo, "metropol": tablo[tablo["metropol"]], "metropol_disi": tablo[~tablo["metropol"]]}
    out = {}
    for ad, d in gruplar.items():
        out[ad] = {"n": int(ozet.at[ad, "n"]),
                   **{o: int(d[o].sum()) for o in ("dogru_kume", "dogru_segment", "kume_dogru_segment",
                                                   "taban_kume", "taban_segment")}}
    return out


def yeni_magaza_blogu(g: dict, o: ogren.Oneri, gizli: pd.Series) -> dict:
    k = g["kapsam"]
    kum = k[k["kumelenir"]]
    Z = ozellikler.standartla(g["X"][o.aile], o.aile)
    fn = partial(ogren.kume, yontem=o.yontem, k=o.k)
    out = {"komsu": yeni_magaza.KOMSU, "varsayilan": "knn", "yontemler": {}}
    for yontem in yeni_magaza.YONTEMLER:
        b = yeni_magaza.birakbir(kum, Z, fn, yontem=yontem)
        t, ozet = olcutler.birakbir_dogruluk(b, gizli)
        out["yontemler"][yontem] = {
            "ayni_bolme": int(b["ayni_bolme"].sum()), "ozet": _ozet(ozet, t),
            "magazalar": [{"magaza_id": r["magaza_id"], "gercek_kume": int(r["gercek_kume"]),
                           "atanan": int(r["atanan"]), "metropol": bool(r["metropol"]),
                           "dogru_kume": bool(r["dogru_kume"]), "dogru_segment": bool(r["dogru_segment"])}
                          for _, r in t.iterrows()]}
    statik = {}
    ids = list(o.etiket.index)
    for ad in ("k1", "k4"):
        e = g[ad].loc[ids]
        tb = pd.DataFrame({"magaza_id": ids, "gercek_kume": e.to_numpy(), "atanan": e.to_numpy(),
                           "metropol": kum.set_index("magaza_id").loc[ids, "metropol"].astype(bool).to_numpy()})
        t, ozet = olcutler.birakbir_dogruluk(tb, gizli)
        statik[ad] = _ozet(ozet, t)
    out["statik_kural"] = statik
    yeni = k[k["yeni"]]
    gercek = {}
    cogunluk = {int(c): olcutler._cogunluk(gizli.loc[o.etiket.index[o.etiket == c]]) for c in sorted(o.etiket.unique())}
    for yontem in yeni_magaza.YONTEMLER:
        a = yeni_magaza.ata(yeni, kum, o.etiket, yontem=yontem)
        for m, c in a.items():
            gercek.setdefault(m, {})[yontem] = int(c)
    for _, r in yeni.iterrows():
        m = r["magaza_id"]
        gercek[m].update({"ad": r["ad"], "sehir": r["sehir"], "bolge": r["bolge"], "tip": r["tip"],
                          "metrekare": int(r["metrekare"]), "metropol": bool(r["metropol"]),
                          "gecmis_hafta": int(r["gecmis_hafta"]),
                          **{ad: _j(g[ad][m]) for ad in KURALLAR}, "gizli": str(gizli[m]),
                          "knn_segment": cogunluk[gercek[m]["knn"]],
                          "merkez_segment": cogunluk[gercek[m]["merkez"]]})
    out["gercek"] = {m: gercek[m] for m in sorted(gercek)}
    out["kume_cogunluk_segment"] = {str(c): s for c, s in cogunluk.items()}
    return out


def _izgara(Z: pd.DataFrame, k2: pd.Series, gizli: pd.Series) -> list[dict]:
    satir = []
    for yontem in ogren.YONTEMLER:
        secilen, t = ogren.k_sec(Z, yontem)
        for _, r in t.iterrows():
            e = ogren.kume(Z, yontem, int(r["k"]))
            ari, ami = olcutler.ari_ami(e, gizli)
            satir.append({"yontem": yontem, "k": int(r["k"]), "siluet": float(r["siluet"]),
                          "en_kucuk": int(r["en_kucuk"]), "boyutlar": [int(v) for v in r["boyutlar"]],
                          "uygun": bool(r["uygun"]), "secilen": bool(r["secilen"]), "ari": ari, "ami": ami,
                          "ari_k2": float(adjusted_rand_score(k2.loc[e.index].to_numpy(), e.to_numpy())),
                          "kimlik": r["kimlik"]})
    return satir


def ablasyon_blogu(g: dict, o: ogren.Oneri, gizli: pd.Series) -> dict:
    ids = list(o.etiket.index)
    k2 = g["k2"].loc[ids]
    out = {"alt_blok": {}, "sutun": {}, "k2_ml_ari": float(adjusted_rand_score(k2.to_numpy(), o.etiket.to_numpy()))}
    for ad in ABLASYON_AILELERI:
        T, bloklar = aile_tablosu(g["X"], ad)
        out["alt_blok"][ad] = _izgara(ozellikler.standartla(T, bloklar), k2, gizli)
    for ad in SUTUN_AGIRLIK_AILELERI:
        T, bloklar = aile_tablosu(g["X"], ad)
        out["sutun"][ad] = _izgara(ozellikler.standartla(T, bloklar, agirlik="sutun"), k2, gizli)
    # S1 ↔ S1 stoklu ve S2 ↔ S4: önerinin yöntemi ve k'sıyla iki bölmenin uyumu (hakemsiz)
    uyum = {}
    for a, b in (("S1", "S1_stoklu"), ("S2", "S4"), ("S1", "S1+olcek"), ("S2", "S5")):
        ea = ogren.kume(ozellikler.standartla(*aile_tablosu(g["X"], a)), o.yontem, o.k)
        eb = ogren.kume(ozellikler.standartla(*aile_tablosu(g["X"], b)), o.yontem, o.k)
        uyum[f"{a}|{b}"] = float(adjusted_rand_score(ea.loc[ids].to_numpy(), eb.loc[ids].to_numpy()))
    out["uyum"] = uyum
    out["sabit_k"] = o.k
    out["sabit_yontem"] = o.yontem
    return out


def demo_blogu(g: dict, gizli: pd.Series) -> dict:
    out = {}
    for aile in DEMO_AILELERI:
        X = g["X"][aile]
        Z = ozellikler.standartla(X, aile)
        for k in DEMO_K:
            e = ogren.kume(Z, DEMO_YONTEM, k)
            boy = e.value_counts()
            sira = sorted(boy.index, key=lambda c: (-int(boy[c]), int(c)))
            yor = ogren.yorum(X, e, n=1)
            out[f"{aile}|{k}"] = {
                "ari": olcutler.ari_ami(e, gizli)[0], "kararlilik": ogren.kararlilik(Z, DEMO_YONTEM, k),
                "en_kucuk": int(boy.min()), "siluet": ogren.siluet(Z, e),
                "kumeler": [{"kume": int(c), "magaza": int(boy[c]), "ozellik": yor[int(c)][0][0],
                             "z": float(yor[int(c)][0][1])} for c in sira]}
    return out


def kumeler_kaydi(sonuc: dict) -> dict:
    """Git'e giren `kumeler.json`: karar günü eşlemeleri (Ruling R3; İlk Sevkiyat yol 0 okur).

    `kural` K1-K4 kapsamın her mağazasına (yeni dahil); `ml` önerinin kümelenen mağazaları ve yeni
    mağazaların statik ataması (knn, Ruling R10); `olcum_gizli_segment` yalnız ölçüm içindir (kahin
    küme kolu: kümelemenin ulaşabileceği en iyi yapı), karar kodu okumaz."""
    v = sonuc["veri"]
    o = sonuc["ml"]["oneri"]
    ym = sonuc["yeni_magaza"]
    kural_adlari = {"k1": "bölge", "k2": "ciro sınıfı", "k3": "bölge × ciro sınıfı", "k4": "konum"}
    kural_e = sonuc["kural"]["etiketler"]
    return {
        "surum": KAYIT_SURUMU,
        "karar_gunu": v["karar_gunu"],
        "kod": sonuc["kod"],
        "kapsam": {"kumelenen": [r["magaza_id"] for r in v["kapsam"] if r["kumelenir"]],
                   "yeni": [r["magaza_id"] for r in v["kapsam"] if r["yeni"]]},
        "kural": {ad: {"ad": kural_adlari[ad], "etiket": kural_e[ad],
                       "kimlik": ogren.bolme_kimligi(pd.Series(kural_e[ad]))} for ad in KURALLAR},
        "ml": {"aile": o["aile"], "yontem": o["yontem"], "k": o["k"], "kimlik": o["kimlik"],
               "ozellik_kimligi": o["ozellik_kimligi"], "etiket": o["etiket"],
               "yeni_magaza": {"yontem": ym["varsayilan"], "komsu": ym["komsu"],
                               "atama": {m: r[ym["varsayilan"]] for m, r in ym["gercek"].items()}}},
        GIZLI_ALAN: {
            "not": "YALNIZ ÖLÇÜM: gizli segment (hakem); karar kodu okumaz. Kahin küme kolu içindir.",
            "etiket": sonuc["gizli_kapsam"]},
    }


def kumeler_oku(yol: Path = KUMELER, olcum: bool = False) -> dict:
    """`kumeler.json`'u okur. Gizli segment alanı (`GIZLI_ALAN`) yalnız `olcum=True` ile döner: kahin küme
    kolu (ölçüm) dışındaki her okuyucu (İlk Sevkiyat'ın K1, K2, ML kolları) onu hiç görmez. Bu modül ölçüm
    yanıdır; karar modülleri onu içe aktarmaz (sızıntı kilidi), etiketleri argüman olarak alır."""
    yol = Path(yol)
    if not yol.is_file():
        raise FileNotFoundError(f"{yol} yok: önce `python -m kumeleme.oyun`")
    k = json.loads(yol.read_text(encoding="utf-8"))
    if k.get("surum") != KAYIT_SURUMU:
        raise ValueError(f"{yol.name}: kayıt sürümü {k.get('surum')} (beklenen {KAYIT_SURUMU})")
    if not olcum:
        k.pop(GIZLI_ALAN, None)
    return k


def kos(karar_gunu=sabitler.KARAR_GUNU, ilerleme=None) -> dict:
    """Bütün bloklar (modül notu); `sonuc.json`'un içeriği."""
    say = ilerleme or (lambda m: None)
    con = kaynak.baglan()
    try:
        say("girdiler")
        g = girdiler(con, karar_gunu)
        say("hakem (dünya)")
        gizli_tum = hakem.gizli_segment()
        ids = list(g["kapsam"].loc[g["kapsam"]["kumelenir"], "magaza_id"])
        gizli = gizli_tum.loc[ids]
        say("öneri")
        o = ogren.oneri(None, g["kapsam"], None, karar_gunu,
                        ozellik={a: g["X"][a] for a in ogren.ONERI_AILELERI})
        sonuc = {"surum": KAYIT_SURUMU, "kod": kod_ozeti(), "veri_izi": veri_parmak_izi(),
                 "veri": veri_blogu(g, karar_gunu), "kural": kural_blogu(g), "ozellik": ozellik_blogu(g["X"])}
        say("ml")
        sonuc["ml"] = ml_blogu(g, o, gizli)
        say("hakem")
        sonuc["hakem"] = hakem_blogu(g, o, gizli)
        say("kararlılık")
        sonuc["kararlilik"] = kararlilik_blogu(g, con, o, gizli)
    finally:
        con.close()
    say("yeni mağaza")
    sonuc["yeni_magaza"] = yeni_magaza_blogu(g, o, gizli_tum)
    say("ablasyon")
    sonuc["ablasyon"] = ablasyon_blogu(g, o, gizli)
    say("hikâye")
    hg = {"kapsam": g["kapsam"], "ozellik": g["X"][hikaye_sec.AILE], "k1": g["k1"], "k2": g["k2"],
          "k3": g["k3"], "k4": g["k4"], "ciro": g["ciro"], "oneri": o}
    h, hakemsiz, gizli_s = hikaye_kos.calistir(hg)
    sonuc["hikaye"] = hikaye_kos.kayit(hg, h, hakemsiz, gizli_s)
    say("demo")
    sonuc["demo"] = demo_blogu(g, gizli)
    sonuc["gizli_kapsam"] = _etiketler(gizli_tum.loc[list(g["kapsam"]["magaza_id"])])
    return _j(sonuc)


def yaz(sonuc: dict, sonuc_yol: Path = SONUC, kumeler_yol: Path = KUMELER, hikaye_yol: Path = HIKAYE) -> None:
    Path(sonuc_yol).parent.mkdir(parents=True, exist_ok=True)
    Path(sonuc_yol).write_text(metin(sonuc), encoding="utf-8", newline="\n")
    Path(hikaye_yol).write_text(json.dumps(sonuc["hikaye"], ensure_ascii=False, indent=1) + "\n",
                                encoding="utf-8", newline="\n")
    Path(kumeler_yol).write_text(metin(kumeler_kaydi(sonuc)), encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    # numpy 2.5 + pandas 2.3: Timedelta içinde "generic unit" uyarısı (bizim değil; pyproject'teki süzgeçle aynı)
    warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)
    bas = time.monotonic()

    def say(m):
        print(f"[{time.monotonic() - bas:6.0f} sn] {m}", file=sys.stderr, flush=True)

    sonuc = kos(ilerleme=say)
    yaz(sonuc)
    say(f"yazıldı: {SONUC}, {KUMELER}, {HIKAYE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
