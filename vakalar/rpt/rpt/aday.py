"""Bu ürün RPT'ye aday mı? — haftalık, option düzeyi sınıflandırıcı.

SATIRLAR. Collection option'ı × karar pazartesisi h = 2…6, henüz RPT'si
yokken (`anlik.Kaydedici` motor içinde kaydeder; özellikler politikanın
göreceğiyle aynı koddan gelir).

ÖZELLİKLER (spec 3.2): h · zincir STR'si · stoklu ve kırık mağaza payı ·
stoklu gün düzeltmeli haftalık hız ÷ Q1 · d kestirimi ÷ Q1 · FRR kestirimi
÷ Q1 · stok kapsaması (hafta) · indirime kalan hafta · RPT süresi · gelişten
sonra kalan eğri · tahmini ek talep ÷ Q1 · MOQ ÷ tahmini ek talep · menşe.

ETİKET (sonradan bakış). "Bu pazartesi max(MOQ, newsvendor) kadar RPT
verilseydi, tedarik süresi sonra gelen adetlerden en az MOQ/2'si tam
fiyattan satılır mıydı?" Stok akışı haftalık ve zincir düzeyindedir:
geliş öncesi talep eldeki envanter pozisyonunu tüketir, kalan stok gelişten
sonraki talebi önce karşılar, RPT ondan sonra satar (mağazalar arası sıkışma
yok sayılır — etiketi RPT lehine iyimser yapar). İki sürüm:
    (i)  gerçek    talep = satış + kayıp (simülasyonun doğrusu; gerçek bir
                   zincir bilemez)
    (ii) düzeltilmiş  talep = sezon kapandıktan sonra, bütün sezonun stoklu
                   günlerinden hücre seviyesi (a_c) ile doldurulmuş talep —
                   gerçek bir zincirin hesaplayabileceği.
Model (ii) ile eğitilir; (i) ile uyumu raporlanır.

MODELLER. Banu'nun kuralı (STR ≥ %55, h ≥ 3, yetişme) · lojistik regresyon
(ölçeklenmiş, sınıf dengeli) · LightGBM (küçük ağaçlar). Eğitim yalnız oyun
sezonundan önce kapanmış sezonlardan.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import anlik, miktar

OZELLIKLER = ["h", "str", "stoklu_magaza_payi", "kirik_magaza_payi", "hiz_q1", "d_q1", "frr_q1",
              "kapsama", "hafta_indirime", "L", "kalan_tf", "ekstra_q1", "moq_oran", "uzak"]
ESIK = 0.5


def ozellikler(kayit: pd.DataFrame, dunya, eg: dict, belirsizlik, p_ind: np.ndarray) -> pd.DataFrame:
    """Ham özet satırlarına eğri bağımlı özellikleri ve newsvendor miktarını ekler.

    eg: {(yöntem, hedef): Egri} — oyun sezonunun eğrileri (eğitim satırları da
    aynı eğriyle dönüştürülür; eğri yalnız geçmişten öğrenildi).
    """
    opt = dunya.optionlar
    e_io, e_cx, e_ham = eg[("duzeltilmis", "indirim")], eg[("duzeltilmis", "cikis")], eg[("ham", "indirim")]
    satir = []
    for r in kayit.itertuples(index=False):
        o = r.option
        dalga = int(opt.at[o, "dalga"])
        L = int(opt.at[o, "rpt_hafta"])
        Q1 = float(opt.at[o, "ilk_alim"])
        moq = int(opt.at[o, "moq_option"])
        W = (opt.at[o, "indirim_gun"] - opt.at[o, "lansman_gun"]) / 7.0
        h = r.h
        k_io, k_cx, k_ham = e_io.k((dalga,), h), e_cx.k((dalga,), h), e_ham.k((dalga,), h)
        S_io = r.D / max(k_io, 1e-6)
        S_cx = r.D / max(k_cx, 1e-6)
        a = h + L
        ip = r.depo + r.magaza + r.acik
        B = S_cx * (e_cx.k((dalga,), a) - k_cx)
        kalan = 1 - e_io.k((dalga,), a)
        ekstra = max(S_io * kalan - max(ip - B, 0.0), 0.0)
        mu, sg = belirsizlik.al(h)
        nv = miktar.newsvendor(r.D, h, L, W, e_io, e_cx, dalga, ip, float(opt.at[o, "liste_fiyati"]),
                               float(opt.at[o, "alis_fiyati"]), float(p_ind[o]), mu, sg, moq)
        haftalik = r.D / max(h, 1e-6)
        satir.append({
            **r._asdict(), "dalga": dalga, "L": L, "Q1": Q1, "moq": moq, "W": W,
            "hiz_q1": haftalik / Q1, "d_q1": S_io / Q1, "frr_q1": r.x / max(k_ham, 1e-6) / Q1,
            "kapsama": min(ip / max(haftalik, 1e-6), 52.0), "hafta_indirime": W - h,
            "kalan_tf": kalan, "ekstra_q1": ekstra / Q1, "moq_oran": min(moq / max(ekstra, 1.0), 10.0),
            "uzak": float(opt.at[o, "mense"] == "Uzak Doğu"), "ip": ip,
            "q_nv": nv["q"], "q_etiket": max(moq, nv["q"]), "beklenen_kar": nv["beklenen_kar"],
            "d_kestirim": S_io,
        })
    return pd.DataFrame(satir)


# ---------------------------------------------------------------------
# Etiket
# ---------------------------------------------------------------------

def haftalik_gercek(hh: pd.DataFrame) -> pd.DataFrame:
    """(option_id, h) → tam fiyat (indirim öncesi) ve bütün talep (gerçek)."""
    g = hh.groupby(["option_id", "h"]).agg(s_io=("satis_io", "sum"), k_io=("kayip_io", "sum"),
                                           s=("satis", "sum"), k=("kayip", "sum"))
    return pd.DataFrame({"tf": g["s_io"] + g["k_io"], "tum": g["s"] + g["k"]}).reset_index()


def haftalik_duzeltilmis(hh: pd.DataFrame, opt_t: pd.DataFrame, egriler_cx: dict) -> pd.DataFrame:
    """(option_id, h) → sonradan bakışla stoklu gün düzeltmeli talep.

    Hücre seviyesi a_c = Σ satış / Σ (stoklu gün × β_h), β_h çıkış eğrisinin
    haftalık payı / 7 (sezonun kendi eğrisi: `egriler_cx[sezon]`). Stoklu
    günü hiç olmayan hücreye SKU (yoksa option) birleşik seviyesi, ilk
    dağıtım ağırlığıyla. Stoksuz günlerin talebi a_c × β_h ile doldurulur.
    """
    h = hh.merge(opt_t[["option_id", "sezon_kodu", "dalga"]], on="option_id")
    parca = []
    for (sezon, dalga), d in h.groupby(["sezon_kodu", "dalga"]):
        if sezon not in egriler_cx:
            continue
        pay = egriler_cx[sezon]._satir((int(dalga),))
        beta = np.where(d["h"].to_numpy() < len(pay), pay[np.minimum(d["h"].to_numpy(), len(pay) - 1)], 0.0) / 7.0
        d = d.assign(beta=beta, maruz=d["stoklu_gun"] * beta)
        c = d.groupby(["option_id", "urun_id", "magaza_id"]).agg(
            s=("satis", "sum"), m=("maruz", "sum"), w=("ilk_dagitim", "first")).reset_index()
        c["w"] = c["w"] + 1.0
        seviye = np.empty(len(c))
        for _, idx in c.groupby("option_id").indices.items():
            cc = c.iloc[idx]
            seviye[idx] = anlik.hucre_duzeltme(cc["s"].to_numpy(), cc["m"].to_numpy(), None,
                                               pd.factorize(cc["urun_id"])[0], cc["w"].to_numpy())
        c["a"] = seviye
        d = d.merge(c[["option_id", "urun_id", "magaza_id", "a"]], on=["option_id", "urun_id", "magaza_id"])
        bos = (d["acik_gun"] - d["stoklu_gun"]).clip(lower=0)
        pay_io = np.divide(d["acik_io"], d["acik_gun"], out=np.zeros(len(d)), where=d["acik_gun"] > 0)
        d["tum"] = d["satis"] + bos * d["a"] * d["beta"]
        d["tf"] = d["satis_io"] + bos * pay_io * d["a"] * d["beta"]
        parca.append(d.groupby(["option_id", "h"])[["tf", "tum"]].sum().reset_index())
    return pd.concat(parca, ignore_index=True)


def etiketle(ozl: pd.DataFrame, dunya, haftalik: pd.DataFrame, p_ind: np.ndarray, ek: str) -> pd.DataFrame:
    """Satır başına sonradan-bakış etiketi ve kârı (kolon adları `ek` ile)."""
    opt = dunya.optionlar
    oid = opt["option_id"].to_numpy()
    tablo = {k: g.set_index("h") for k, g in haftalik.groupby("option_id")}
    etiket, kar, tf_sat = [], [], []
    for r in ozl.itertuples(index=False):
        o = r.option
        w = tablo.get(oid[o])
        h0, a = int(round(r.h)), int(round(r.h)) + r.L
        if w is None:
            etiket.append(False), kar.append(0.0), tf_sat.append(0.0)
            continue
        tum, tf = w["tum"], w["tf"]
        B = tum[(tum.index >= h0) & (tum.index < a)].sum()
        Xtf = tf[tf.index >= a].sum()
        Xind = (tum - tf)[(tum.index >= a)].sum()
        Q = r.q_etiket
        C0 = max(r.ip - B, 0.0)
        C1 = max(C0 - Xtf, 0.0)
        s_tf = min(Q, max(Xtf - C0, 0.0))
        s_ind = min(Q - s_tf, max(Xind - C1, 0.0))
        p, c = float(opt.at[o, "liste_fiyati"]), float(opt.at[o, "alis_fiyati"])
        etiket.append(s_tf >= r.moq / 2)
        kar.append(p * s_tf + float(p_ind[o]) * s_ind - c * Q)
        tf_sat.append(s_tf)
    return ozl.assign(**{f"etiket_{ek}": etiket, f"kar_{ek}": kar, f"tf_{ek}": tf_sat})


# ---------------------------------------------------------------------
# Modeller
# ---------------------------------------------------------------------

def banu_kurali(ozl: pd.DataFrame, dunya) -> np.ndarray:
    opt = dunya.optionlar
    lan = opt["lansman_gun"].to_numpy()[ozl["option"]]
    ind = opt["indirim_gun"].to_numpy()[ozl["option"]]
    yetisir = lan + 7 * 3 + 7 * ozl["L"].to_numpy() < ind
    return ((ozl["h"] >= 3) & (ozl["str"] >= 0.55) & yetisir).to_numpy()


class Modeller:
    """Lojistik ve LightGBM, (ii) etiketiyle eğitilir."""

    def __init__(self, egitim: pd.DataFrame, etiket: str = "etiket_duz"):
        import lightgbm as lgb

        X, y = egitim[OZELLIKLER].to_numpy(float), egitim[etiket].to_numpy(bool)
        self.n, self.pozitif = len(y), int(y.sum())
        self.lojistik = make_pipeline(StandardScaler(), LogisticRegression(
            C=1.0, class_weight="balanced", max_iter=2000)).fit(X, y)
        self.lgbm = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=7,
                                       min_child_samples=10, subsample=0.8, subsample_freq=1,
                                       colsample_bytree=0.8, is_unbalance=True, random_state=0,
                                       verbose=-1).fit(X, y)

    def olasilik(self, ozl: pd.DataFrame, model: str) -> np.ndarray:
        X = ozl[OZELLIKLER].to_numpy(float)
        m = self.lojistik if model == "lojistik" else self.lgbm
        return m.predict_proba(X)[:, 1]

    def katsayilar(self) -> pd.Series:
        lr = self.lojistik[-1]
        return pd.Series(lr.coef_[0], index=OZELLIKLER).sort_values(key=np.abs, ascending=False)


def degerlendir(tahmin: np.ndarray, ozl: pd.DataFrame, ek: str = "gercek") -> dict:
    """Satır düzeyi karışıklık, isabet, duyarlılık; TL maliyetleri (gerçek kâr).

    Yanlış alarm maliyeti: alarm verilip etiketi negatif satırların
    sonradan-bakış zararı (−kâr, pozitif kârlı olanlar hariç). Kaçırma
    maliyeti: alarm verilmeyen pozitif satırların kârı.
    Option düzeyi: option'ın ilk alarmında verilseydi elde edilecek kâr
    (politikanın yapacağı: ilk alarmda sipariş, en fazla bir RPT).
    """
    y = ozl[f"etiket_{ek}"].to_numpy(bool)
    kar = ozl[f"kar_{ek}"].to_numpy(float)
    t = np.asarray(tahmin, bool)
    tp, fp, fn, tn = int((t & y).sum()), int((t & ~y).sum()), int((~t & y).sum()), int((~t & ~y).sum())
    ilk = ozl.assign(_t=t).sort_values(["option", "h"])
    ilk = ilk[ilk["_t"]].groupby("option").head(1)
    return {
        "n": len(y), "pozitif": int(y.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "isabet": tp / (tp + fp) if tp + fp else np.nan,
        "duyarlilik": tp / (tp + fn) if tp + fn else np.nan,
        "yanlis_alarm_tl": float(-kar[t & ~y].clip(max=0).sum()),
        "kacirma_tl": float(kar[~t & y].clip(min=0).sum()),
        "ilk_alarm_option": int(len(ilk)),
        "ilk_alarm_kar_tl": float(ilk[f"kar_{ek}"].sum()),
    }
