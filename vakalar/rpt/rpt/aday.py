"""Bu ürün RPT'ye aday mı? — haftalık, option düzeyi sınıflandırıcı.

SATIRLAR. Collection option'ı × karar pazartesisi h = 2…6 (`karar_kaydi`), henüz
RPT'si yokken. Bir satır karar sabahı `t = lansman + 7h`'de bilinen iki parçadan
kurulur:
    talep   x (bugüne dek brüt satış) ve D (karar anı Basit'iyle düzeltilmiş talep),
            `sansur.karar_ozetleri` — günlük tablonun `t`'den önceki satırlarının
            saf fonksiyonu (Ruling R5; motor içi yol aynı fonksiyonu çağırır)
    durum   zincirin o sabahki durumu (`DURUM_KOLONLARI`): tablo yolunda
            `durum_tablodan` (yayımlanan tablolar `kaynak.tarihten_once(t)`'ye
            kırpılarak); motor içinde aynı sütunlar `Gorunum`dan
            (`anlik.durum_gorunumden`)
Özellikler (`ozellikler`) bu satırın ve option'ın kamuya açık alanlarının
(tedarikçi, ilk alım, takvim, fiyat) saf fonksiyonudur.

DURUM. STR Banu'nunkiyle aynı tanım (v4 `LumodaRPT`): dünkü akşama kadar brüt
satış (mağaza + online) ÷ bu sabaha kadar depodan mağazalara çıkan (ilk dağıtım,
replenishment, depodan outlet akışı, açılış transferi). Tablodan kurulan bu STR ile
Banu'nun kuralı yayımlanan RPT siparişlerini birebir üretir (testli). Depo ve
mağaza stoğu o sabahın pazartesi fotoğrafı; yolda = çıkmış ama `t`'ye dek
varmamış, hedefi depo olmayan HER sevkiyat (mağazadan mağazaya transfer ve outlet
akışı dahil: zincirin envanter pozisyonunu hafifçe fazla sayar; depodan çıkan
zaten depo fotoğrafında değildir); açık = `t`'den önce verilmiş, `t`'ye dek teslim olmamış
sipariş; stoklu / kırık mağaza payı o sabahın mağaza fotoğrafından (yalnız o
sabah fotoğrafta görünen mağazalar: gelecekteki kapanış okunmaz).

ÖZELLİKLER (spec 3.2; v3'teki 14): h · zincir STR'si · stoklu ve kırık mağaza
payı · haftalık hız ÷ Q1 (hız D'den) · d kestirimi ÷ Q1 · FRR kestirimi ÷ Q1 ·
stok kapsaması (hafta) · indirime kalan hafta · RPT süresi · gelişten sonra kalan
eğri · tahmini ek talep ÷ Q1 · MOQ ÷ tahmini ek talep · menşe (Uzak Doğu).

ETİKET (sonradan bakış). "Bu pazartesi max(MOQ, newsvendor) kadar RPT verilseydi,
tedarik süresi sonra gelen adetlerden en az MOQ/2'si tam fiyattan satılır
mıydı?" Stok akışı haftalık ve zincir düzeyindedir: geliş öncesi talep eldeki
envanter pozisyonunu tüketir, kalan stok gelişten sonraki talebi önce karşılar,
RPT ondan sonra satar (mağazalar arası sıkışma yok sayılır — etiketi RPT lehine
iyimser yapar). Etiketin talebi argümandır (`etiket(…, talep)`: hücre-gün
`tarih, option_id, talep`); iki sürüm:
    (i)  gercek  gerçek talep (raporda hakemden, `olcutler.gercek_gunluk`; gerçek
                 bir zincir bilemez)
    (ii) duz     ortak Basit'in karar anı moduyla doldurulmuş talep, karar anı =
                 oyun sezonunun ilk lansman sabahı (Ruling R4; `egri.gecmis_talep`)
                 — gerçek bir zincirin o sabah hesaplayabileceği
Model (ii) ile eğitilir; (i) ile uyumu raporlanır (`uyum`).

MODELLER. Banu'nun kuralı (STR ≥ %55, h 3–6, yetişme, RPT'siz) · lojistik
regresyon (ölçeklenmiş, sınıf dengeli) · LightGBM (küçük ağaçlar). Eğitim yalnız
oyun sezonundan önce kapanmış sezonlardan (`egitim_satirlari`; `Modeller` başka
sezon görürse ValueError).

Bu modül gizli gerçeği (hakem, üreteç, motor) içe aktarmaz; gerçek talep yalnız
etiketin argümanı olarak gelir.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import egri, kaynak, miktar, sansur

OZELLIKLER = ["h", "str", "stoklu_magaza_payi", "kirik_magaza_payi", "hiz_q1", "d_q1", "frr_q1",
              "kapsama", "hafta_indirime", "L", "kalan_tf", "ekstra_q1", "moq_oran", "uzak"]
ESIK = 0.5
HAFTALAR = sansur.KARAR_HAFTALARI
DURUM_KOLONLARI = ("satilan", "gonderilen", "str", "depo", "magaza", "yolda", "acik",
                   "stoklu_magaza_payi", "kirik_magaza_payi", "rpt_sayisi")
DEPO = "DEPO"


# ---------------------------------------------------------------------
# Karar sabahı durumu (tablo yolu)
# ---------------------------------------------------------------------


def durum_tablodan(t: dict, karar_ani, optionlar) -> pd.DataFrame:
    """Karar sabahı `karar_ani` (pazartesi) option'ların zincir durumu, yalnız
    yayımlanan tablolardan, `kaynak.tarihten_once(t, karar_ani)` ile kırpılarak.

    t: tablo sözlüğü (`kaynak.veri_yukle` / `temizle` biçimi: urun, satis, stok,
    depo_stok, sevkiyat, siparis). Dönüş: option_id + `DURUM_KOLONLARI`; verisi
    olmayan option sıfır."""
    k = pd.Timestamp(karar_ani).normalize()
    ids = pd.Index(pd.unique(pd.Series(list(optionlar), dtype=object).astype(str)), name="option_id")
    u = t["urun"][["urun_id", "option_id"]].astype(str).drop_duplicates("urun_id")
    u = u[u["option_id"].isin(ids)]
    skular = set(u["urun_id"])
    harita = u.set_index("urun_id")["option_id"]

    def _sku(df):
        u = df["urun_id"]
        return u if u.dtype == object else u.astype(str)

    def _sec(df):
        return df[_sku(df).isin(skular)]

    kirpik = kaynak.tarihten_once({ad: _sec(t[ad]) for ad in ("satis", "sevkiyat", "stok", "depo_stok",
                                                              "siparis")}, k)

    def _opt(df):
        return _sku(df).map(harita)

    s = kirpik["satis"]
    s = s[s["adet"] > 0]
    satilan = s["adet"].groupby(_opt(s)).sum()
    sv = kirpik["sevkiyat"]
    kaynak_ = sv["kaynak"].astype(str)
    hedef = sv["hedef"].astype(str)
    giden = sv[(kaynak_ == DEPO) & (hedef != DEPO)]
    gonderilen = giden["adet"].groupby(_opt(giden)).sum()
    yol = sv[sv["varis_tarihi"].isna() & (hedef != DEPO)]
    yolda = yol["adet"].groupby(_opt(yol)).sum()
    d = kirpik["depo_stok"]
    d = d[d["tarih"] == k]
    depo = d["adet"].groupby(_opt(d)).sum()
    st = kirpik["stok"]
    st = st[st["tarih"] == k]
    st = st.assign(option_id=_opt(st), dolu=st["adet"] > 0, bos=st["adet"] == 0)
    magaza = st.groupby("option_id")["adet"].sum()
    # observed: kategorik kimlikte fotoğrafta görünmeyen mağaza paydaya girmez
    mg = st.groupby(["option_id", "magaza_id"], observed=True)[["dolu", "bos"]].max()
    stoklu_pay = mg["dolu"].groupby(level=0).mean()
    kirik_pay = (mg["dolu"] & mg["bos"]).groupby(level=0).mean()
    sp = kirpik["siparis"]
    acik_sp = sp[sp["gerceklesen_teslim"].isna()]
    acik = acik_sp["adet"].groupby(acik_sp["option_id"].astype(str)).sum()
    rpt = sp[sp["tip"] == "rpt"]
    rpt_sayisi = rpt.groupby(rpt["option_id"].astype(str))["siparis_id"].nunique()

    r = pd.DataFrame(index=ids)
    for ad, seri in (("satilan", satilan), ("gonderilen", gonderilen), ("depo", depo), ("magaza", magaza),
                     ("yolda", yolda), ("acik", acik), ("stoklu_magaza_payi", stoklu_pay),
                     ("kirik_magaza_payi", kirik_pay), ("rpt_sayisi", rpt_sayisi)):
        r[ad] = seri.reindex(ids).fillna(0).to_numpy(float)
    r["str"] = np.divide(r["satilan"], r["gonderilen"], out=np.zeros(len(r)), where=r["gonderilen"] > 0)
    r["rpt_sayisi"] = r["rpt_sayisi"].astype(int)
    return r.reset_index()[["option_id", *DURUM_KOLONLARI]]


def tablo_durumu(t: dict):
    """`karar_kaydi`nın `durum_bul`u: (karar_ani, option_id'ler) → `durum_tablodan`."""
    return lambda karar_ani, ids: durum_tablodan(t, karar_ani, ids)


def karar_kaydi(gunluk: pd.DataFrame, opt: pd.DataFrame, sezonlar, carpanlar_bul, durum_bul,
                haftalar=HAFTALAR, line: str = "Collection") -> pd.DataFrame:
    """Sezonların `line` option'ları × karar haftası: x, D (`sansur.karar_ozetleri`) +
    karar sabahı durumu (`durum_bul(karar_ani, option_id'ler)` → `DURUM_KOLONLARI`).
    Her satır yalnız kendi karar anından önce bilinenden kurulur."""
    oz = sansur.karar_ozetleri(gunluk, opt, sezonlar, haftalar, carpanlar_bul, line)
    parca = []
    for k, g in oz.groupby("karar_ani", sort=False):
        d = durum_bul(k, g["option_id"]).copy()
        d["option_id"] = d["option_id"].astype(str)
        parca.append(g.merge(d[["option_id", *DURUM_KOLONLARI]], on="option_id", how="left"))
    if not parca:
        return oz.assign(**{c: pd.Series(dtype=float) for c in DURUM_KOLONLARI})
    return pd.concat(parca, ignore_index=True)


def egitim_satirlari(kayit: pd.DataFrame, oyun_sezonu: str) -> pd.DataFrame:
    """Eğitim satırları: oyun sezonundan önce kapanmış sezonlar, henüz RPT'si yokken."""
    gecmis = kaynak.gecmis_sezonlar(oyun_sezonu)
    return kayit[kayit["sezon_kodu"].isin(gecmis) & (kayit["rpt_sayisi"] == 0)].reset_index(drop=True)


# ---------------------------------------------------------------------
# Özellikler
# ---------------------------------------------------------------------


def ozellikler(kayit: pd.DataFrame, opt: pd.DataFrame, eg: dict, belirsizlik, p_ind) -> pd.DataFrame:
    """Karar satırlarına (`karar_kaydi`) eğri bağımlı özellikleri ve newsvendor miktarını
    ekler. Saf fonksiyon.

    opt   option_id, sezon_kodu, dalga, rpt_hafta, ilk_alim, moq_option, satis_hafta,
          liste_fiyati, alis_fiyati, mense, lansman_tarihi, indirim_baslangic
    eg    {(yöntem, hedef): Egri} — oyun sezonunun eğrileri (eğitim satırları da aynı
          eğriyle dönüştürülür; eğri yalnız geçmişten öğrenildi)
    belirsizlik  `miktar.Belirsizlik`; p_ind: option_id → indirim dönemi fiyatı
    """
    o = opt.drop_duplicates("option_id").assign(option_id=lambda x: x["option_id"].astype(str))
    o = o.set_index("option_id")
    e_io, e_cx, e_ham = eg[("duzeltilmis", "indirim")], eg[("duzeltilmis", "cikis")], eg[("ham", "indirim")]
    satir = []
    for r in kayit.to_dict("records"):
        oid = str(r["option_id"])
        a_ = o.loc[oid]
        dalga = int(a_["dalga"])
        L = int(a_["rpt_hafta"])
        Q1 = max(float(a_["ilk_alim"]), 1.0)
        moq = int(a_["moq_option"])
        W = float(a_["satis_hafta"])
        p, c, pi = float(a_["liste_fiyati"]), float(a_["alis_fiyati"]), float(p_ind[oid])
        h = int(r["h"])
        D, x = float(r["D"]), float(r["x"])
        k_io, k_cx, k_ham = e_io.k((dalga,), h), e_cx.k((dalga,), h), e_ham.k((dalga,), h)
        S_io = D / max(k_io, 1e-6)
        S_cx = D / max(k_cx, 1e-6)
        a = h + L
        ip = float(r["depo"] + r["magaza"] + r["yolda"] + r["acik"])
        B = S_cx * (e_cx.k((dalga,), a) - k_cx)
        kalan = 1 - e_io.k((dalga,), a)
        ekstra = max(S_io * kalan - max(ip - B, 0.0), 0.0)
        mu, sg = belirsizlik.al(h)
        nv = miktar.newsvendor(D, h, L, W, e_io, e_cx, dalga, ip, p, c, pi, mu, sg, moq)
        haftalik = D / max(h, 1e-6)
        satir.append({
            **r, "option_id": oid, "sezon_kodu": r.get("sezon_kodu", a_["sezon_kodu"]), "dalga": dalga,
            "lansman_tarihi": a_["lansman_tarihi"], "indirim_baslangic": a_["indirim_baslangic"],
            "L": L, "Q1": Q1, "moq": moq, "W": W, "p": p, "c": c, "p_ind": pi,
            "hiz_q1": haftalik / Q1, "d_q1": S_io / Q1, "frr_q1": x / max(k_ham, 1e-6) / Q1,
            "kapsama": min(ip / max(haftalik, 1e-6), 52.0), "hafta_indirime": W - h,
            "kalan_tf": kalan, "ekstra_q1": ekstra / Q1, "moq_oran": min(moq / max(ekstra, 1.0), 10.0),
            "uzak": float(a_["mense"] == "Uzak Doğu"), "ip": ip,
            "q_nv": nv["q"], "q_etiket": max(moq, nv["q"]), "beklenen_kar": nv["beklenen_kar"],
            "d_kestirim": S_io,
        })
    return pd.DataFrame(satir)


# ---------------------------------------------------------------------
# Etiket
# ---------------------------------------------------------------------


def haftalik(talep: pd.DataFrame, opt: pd.DataFrame) -> pd.DataFrame:
    """Hücre-gün talepten (`tarih, option_id, talep`) (option_id, h) → tf (tam fiyat:
    indirim başından önceki günler) ve tum (lansman → çıkış)."""
    o = opt[["option_id", "lansman_tarihi", "indirim_baslangic", "cikis_tarihi"]].drop_duplicates("option_id")
    o = o.assign(option_id=o["option_id"].astype(str))
    d = pd.DataFrame({"option_id": talep["option_id"].astype(str).to_numpy(),
                      "tarih": talep["tarih"].to_numpy("datetime64[ns]"),
                      "talep": talep["talep"].to_numpy(np.float64)}).merge(o, on="option_id")
    d = d[(d["tarih"] >= d["lansman_tarihi"]) & (d["tarih"] < d["cikis_tarihi"])]
    d["h"] = (d["tarih"] - d["lansman_tarihi"]).dt.days // 7
    d["tf"] = np.where(d["tarih"] < d["indirim_baslangic"], d["talep"], 0.0)
    return d.groupby(["option_id", "h"])[["tf", "talep"]].sum().rename(columns={"talep": "tum"}).reset_index()


def etiketle(ozl: pd.DataFrame, haftalik_: pd.DataFrame, ek: str) -> pd.DataFrame:
    """Satır başına sonradan-bakış etiketi ve kârı (`etiket_<ek>`, `kar_<ek>`,
    `tf_<ek>`). ozl: option_id, h, L, ip, q_etiket, moq, p, c, p_ind."""
    tablo = {str(k): g.set_index("h") for k, g in haftalik_.groupby("option_id")}
    etiket, kar, tf_sat = [], [], []
    for r in ozl.itertuples(index=False):
        w = tablo.get(str(r.option_id))
        h0 = int(round(r.h))
        a = h0 + int(r.L)
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
        etiket.append(s_tf >= r.moq / 2)
        kar.append(r.p * s_tf + r.p_ind * s_ind - r.c * Q)
        tf_sat.append(s_tf)
    return ozl.assign(**{f"etiket_{ek}": etiket, f"kar_{ek}": kar, f"tf_{ek}": tf_sat})


def etiket(ozl: pd.DataFrame, talep: pd.DataFrame, opt: pd.DataFrame, ek: str) -> pd.DataFrame:
    """`etiketle(ozl, haftalik(talep, opt), ek)`: talep argümandır — (i) gerçek talep
    (`ek="gercek"`), (ii) Basit'le doldurulmuş talep (`ek="duz"`)."""
    return etiketle(ozl, haftalik(talep, opt), ek)


def etiket_duz(ozl: pd.DataFrame, gunluk: pd.DataFrame, opt: pd.DataFrame, oyun_sezonu: str,
               carpanlar_bul, line: str = "Collection") -> pd.DataFrame:
    """Etiket (ii), Ruling R4'le: talep = ortak Basit'in karar anı moduyla doldurulmuş
    talep, karar anı oyun sezonunun ilk lansman sabahı (`egri.gecmis_talep(…, t0)`,
    çarpanlar `carpanlar_bul(t0)`). Yalnız geçmiş sezon satırları (eğitim) için:
    `ozl`'de geçmiş olmayan sezon varsa ValueError (o satırların talebi t0'da
    bilinmez, etiket sessizce negatif çıkardı)."""
    gecmis = kaynak.gecmis_sezonlar(oyun_sezonu)
    disari = sorted(set(ozl["sezon_kodu"]) - set(gecmis))
    if disari:
        raise ValueError(f"etiket_duz: {oyun_sezonu} için geçmiş olmayan sezon satırı {disari}")
    t0 = egri.oyun_baslangici(opt, oyun_sezonu)
    talep = egri.gecmis_talep(gunluk, opt, oyun_sezonu, carpanlar_bul(t0), line)
    return etiket(ozl, talep, opt, "duz")


def uyum(ozl: pd.DataFrame, ek1: str = "gercek", ek2: str = "duz") -> dict:
    """İki etiketin satır düzeyi uyumu: ikisi / yalnız biri / hiçbiri, uyum oranı, κ."""
    a, b = ozl[f"etiket_{ek1}"].to_numpy(bool), ozl[f"etiket_{ek2}"].to_numpy(bool)
    n = len(a)
    ikisi, y1, y2, hic = int((a & b).sum()), int((a & ~b).sum()), int((~a & b).sum()), int((~a & ~b).sum())
    po = (ikisi + hic) / n if n else np.nan
    pe = (a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())) if n else np.nan
    return {"n": n, "ikisi": ikisi, f"yalniz_{ek1}": y1, f"yalniz_{ek2}": y2, "hicbiri": hic,
            "uyum": po, "kappa": (po - pe) / (1 - pe) if n and pe < 1 else np.nan,
            f"pozitif_{ek1}": int(a.sum()), f"pozitif_{ek2}": int(b.sum())}


# ---------------------------------------------------------------------
# Modeller
# ---------------------------------------------------------------------


def banu_kurali(ozl: pd.DataFrame) -> np.ndarray:
    """Banu'nun (v4 `LumodaRPT`) tetiği: lansmandan 3.–6. pazartesi, STR ≥ %55,
    lansman + 3 hafta + RPT süresi < indirim başı, mağazalara mal gitmiş, RPT'siz."""
    yetisir = (pd.to_datetime(ozl["lansman_tarihi"])
               + pd.to_timedelta(7 * miktar.RPT_ILK_HAFTA + 7 * ozl["L"].astype(int), unit="D")
               < pd.to_datetime(ozl["indirim_baslangic"]))
    return ((ozl["h"] >= miktar.RPT_ILK_HAFTA) & (ozl["h"] <= miktar.RPT_SON_HAFTA)
            & (ozl["str"] >= miktar.RPT_STR_ESIGI) & yetisir & (ozl["gonderilen"] > 0)
            & (ozl["rpt_sayisi"] == 0)).to_numpy()


class Modeller:
    """Lojistik ve LightGBM, (ii) etiketiyle, yalnız `oyun_sezonu`ndan önce kapanmış
    sezonların satırlarıyla eğitilir (başka sezon satırı ValueError)."""

    def __init__(self, egitim: pd.DataFrame, oyun_sezonu: str, etiket: str = "etiket_duz"):
        import lightgbm as lgb

        gecmis = kaynak.gecmis_sezonlar(oyun_sezonu)
        disari = sorted(set(egitim["sezon_kodu"]) - set(gecmis))
        if disari:
            raise ValueError(f"Modeller: {oyun_sezonu} için eğitimde geçmiş olmayan sezon {disari}")
        self.sezonlar = tuple(s for s in gecmis if s in set(egitim["sezon_kodu"]))
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
    """Satır düzeyi karışıklık, isabet, duyarlılık; TL maliyetleri (`kar_<ek>`).

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
    ilk = ozl.assign(_t=t).sort_values(["option_id", "h"])
    ilk = ilk[ilk["_t"]].groupby("option_id").head(1)
    return {
        "n": len(y), "pozitif": int(y.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "isabet": tp / (tp + fp) if tp + fp else np.nan,
        "duyarlilik": tp / (tp + fn) if tp + fn else np.nan,
        "yanlis_alarm_tl": float(-kar[t & ~y].clip(max=0).sum()),
        "kacirma_tl": float(kar[~t & y].clip(min=0).sum()),
        "ilk_alarm_option": int(len(ilk)),
        "ilk_alarm_kar_tl": float(ilk[f"kar_{ek}"].sum()),
    }
