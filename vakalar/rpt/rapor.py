"""RPT dizisinin yayımlanacak BÜTÜN sayıları buradan basılır.

    .venv/Scripts/python rapor.py > cikti/rapor.txt

Kalıcı kural (spec 3.5): yazıya yeni bir sayı girmeden önce buraya eklenir.
Sayılar Türkçe biçimde basılır (binlik nokta, ondalık virgül); yazıya
kopyalanabilir.

Faz A bölümleri:
    HİKÂYE  (1. yazı)  seçilen option, pazartesi durumu, Lumoda'nın RPT'leri
    KARAR   (2. yazı)  eğri payları, yerli / Uzak Doğu kalan eğri, stoklu gün örneği
    SANSÜR  (3. yazı)  dört katmanlı kestirim hatası, plan hatası, eğri şekli

Faz B bölümleri (yol 0 = gerçek v3 talebi; aralıklar cikti/yollar.json'dan):
    ADAY    (4. yazı)  aday modeli: etiket, kural / lojistik / LightGBM, TL maliyet
    MİKTAR  (5. yazı)  belirsizlik, Banu / FRR / newsvendor miktarları, kollar
    SONUÇ   (6. yazı)  dağıtım kuralları, kollar tablosu, hikâye option'ları, yollar
"""

import sys
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from rpt import egri, hikaye, kaynak, sansur

OYUN = kaynak.OYUN_SEZONLARI
HIKAYE_SEZONU = "SS25"
ONCEKI_SEZON = {"SS25": "AW24", "AW24": "SS24"}
KARAR_H = 3   # Lumoda'nın gözden geçirme penceresinin ilk haftası (3–6)

# numpy 2.5 + pandas 2.3: Timedelta içinde "generic unit" uyarısı (bizim değil)
warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)


# ---------------------------------------------------------------------
# Biçim
# ---------------------------------------------------------------------

def s(x, ondalik: int = 0) -> str:
    """Türkçe sayı: 12.345 · 0,55 · −3,2."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    metin = f"{x:,.{ondalik}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return metin.replace("-", "−")


def y(x, ondalik: int = 1) -> str:
    """Yüzde: 0,123 → %12,3."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return "%" + s(100 * x, ondalik)


def t_(tarih) -> str:
    return pd.Timestamp(tarih).strftime("%Y-%m-%d") if pd.notna(tarih) else "—"


def baslik(metin: str) -> None:
    print()
    print("=" * 78)
    print(metin)
    print("=" * 78)


def alt(metin: str) -> None:
    print()
    print(f"--- {metin} ---")


# ---------------------------------------------------------------------
# Hazırlık
# ---------------------------------------------------------------------

@dataclass
class Veri:
    t: dict
    opt: pd.DataFrame
    hh: pd.DataFrame
    panel: pd.DataFrame
    gercek: pd.DataFrame
    egriler: dict        # (sezon, yöntem, hedef) → Egri
    kestirim: dict       # sezon → DataFrame (bütün h)
    hata: dict           # sezon → hata tablosu


def hazirla(t: dict | None = None, dunya=None) -> Veri:
    from perakende_veri.v3.dunya import dunya_kur

    t = t if t is not None else kaynak.veri_yukle()
    opt = kaynak.plan_ekle(kaynak.optionlar(t), dunya if dunya is not None else dunya_kur())
    hh = kaynak.hucre_hafta(t, opt)
    panel = kaynak.option_panel(t, opt, hh)
    gercek = sansur.gercek_talep(hh)

    egriler, kestirim, hata = {}, {}, {}
    for sezon in OYUN:
        for yontem in ("ham", "duzeltilmis"):
            for hedef in ("indirim", "cikis"):
                egriler[(sezon, yontem, hedef)] = egri.oyun_egrisi(t, opt, sezon, yontem, hedef=hedef)
        # Gerçek eğri: oyun sezonunun kendisinden, yalnız kıyas için (kâhin)
        egriler[(sezon, "gercek", "indirim")] = egri.egri_ogren(hh, opt, [sezon], "gercek")
        egriler[(sezon, "gercek", "cikis")] = egri.egri_ogren(hh, opt, [sezon], "gercek", hedef="cikis")
        o = opt[(opt["sezon_kodu"] == sezon) & (opt["line"] == "Collection")]
        h_ = hh[hh["option_id"].isin(o["option_id"])]
        kestirim[sezon] = pd.concat([
            sansur.kestir(h_, o, h, egriler[(sezon, "ham", "indirim")],
                          egriler[(sezon, "duzeltilmis", "indirim")])
            for h in sansur.KARAR_HAFTALARI
        ], ignore_index=True)
        hata[sezon] = sansur.hata_tablosu(kestirim[sezon], gercek)
    return Veri(t, opt, hh, panel, gercek, egriler, kestirim, hata)


def _secim(v: Veri):
    """Hikâye option'ları: en erken biten yerli ve Uzak Doğu hit'i."""
    adaylar = hikaye.hikaye_adaylari(v.panel, v.opt, v.gercek, HIKAYE_SEZONU)
    yerli = adaylar[adaylar["mense"] == "Yerli"].iloc[0]
    uzak = adaylar[adaylar["mense"] == "Uzak Doğu"].iloc[0]
    return adaylar, yerli, uzak


def _pazartesi(o, h) -> pd.Timestamp:
    return pd.Timestamp(o["lansman_tarihi"]) + pd.Timedelta(days=7 * int(h))


def _tipik_rpt_hafta(v: Veri) -> dict:
    td = v.t["tedarikci"]
    return {m: int(np.median(td.loc[td["mense"] == m, "rpt_hafta"])) for m in ("Yerli", "Uzak Doğu")}


# ---------------------------------------------------------------------
# HİKÂYE (1. yazı)
# ---------------------------------------------------------------------

def _option_ozeti(v: Veri, o, h: int, etiket: str) -> None:
    e_io = v.egriler[(HIKAYE_SEZONU, "duzeltilmis", "indirim")]
    e_cx = v.egriler[(HIKAYE_SEZONU, "duzeltilmis", "cikis")]
    p = v.panel[v.panel["option_id"] == o["option_id"]].set_index("h")
    pzt = _pazartesi(o, h)
    satis = int(p.loc[p.index < h, "satis"].sum())
    print(f"[{etiket}] {o['model_adi']} — {o['renk']}  ({o['option_id']}, {o['model_kodu']})")
    print(f"  sezon {o['sezon_kodu']}, dalga {o['dalga']}, {o['ust_kategori']} / {o['alt_kategori']}, "
          f"{o['cinsiyet']}")
    print(f"  tedarikçi {o['tedarikci']} ({o['ulke']}, {o['mense']}), RPT süresi {o['rpt_hafta']} hafta, "
          f"MOQ {s(o['moq_option'])}")
    print(f"  lansman {t_(o['lansman_tarihi'])}, indirim başı {t_(o['indirim_baslangic'])}, "
          f"çıkış {t_(o['cikis_tarihi'])}")
    print(f"  ilk alım Q1 = {s(o['ilk_alim'])} (plan sezon talebi {s(o['plan_sezon'])}; "
          f"ilk dağıtımda mağazalara {s(p.loc[0, 'sevk'])})")
    print(f"  gerçek sezon talebi (lansman→indirim) {s(o['gercek_io'])} = planın {s(o['oran'], 2)} katı; "
          f"lansman→çıkış {s(o['gercek_cikis'])}")
    print(f"  'bitti' pazartesisi: lansman + {h} hafta = {t_(pzt)}")
    print(f"    bugüne kadar satış {s(satis)} (ilk alımın {y(satis / o['ilk_alim'])}); "
          f"depo {s(p.loc[h, 'depo_stok'])}; mağaza stoğu {s(p.loc[h, 'magaza_stok'])}")
    print(f"    taşıyan mağaza {p.loc[h, 'tasiyan_magaza']}, stoklu {p.loc[h, 'stoklu_magaza']}, "
          f"tamamen boş {p.loc[h, 'tasiyan_magaza'] - p.loc[h, 'stoklu_magaza']}")
    print(f"    [gerçek, zincir görmez] bugüne kadarki kayıp satış {s(p.loc[p.index < h, 'kayip'].sum())}")
    hafta_indirime = (pd.Timestamp(o["indirim_baslangic"]) - pzt).days / 7
    print(f"    bu pazartesiden indirim başına {s(hafta_indirime, 1)} hafta, çıkışa "
          f"{s((pd.Timestamp(o['cikis_tarihi']) - pzt).days / 7, 1)} hafta")
    L = int(o["rpt_hafta"])
    for hk in sorted({KARAR_H, h}):
        gelis_h = hk + L
        print(f"    h={hk} pazartesisi ({t_(_pazartesi(o, hk))}) sipariş verilse (kendi tedarikçisi, {L} hafta): "
              f"planlanan geliş {t_(_pazartesi(o, gelis_h))} (lansman + {gelis_h} hafta)")
        print(f"      gelişten sonra kalan eğri: indirime kadar {y(e_io.kalan((o['dalga'],), gelis_h))} "
              f"(sezon talebinin), çıkışa kadar {y(e_cx.kalan((o['dalga'],), gelis_h))} "
              f"(indirim dahil talebin)")
    print(f"    3. hafta pazartesisi durumu (h=3, {t_(_pazartesi(o, 3))}): satış "
          f"{s(p.loc[p.index < 3, 'satis'].sum())}, depo {s(p.loc[3, 'depo_stok'])}, mağaza "
          f"{s(p.loc[3, 'magaza_stok'])}, stoklu mağaza {p.loc[3, 'stoklu_magaza']}/{p.loc[3, 'tasiyan_magaza']}")


def _lumoda_rpt(v: Veri, o) -> None:
    r = hikaye.rpt_siparisleri(v.t, v.opt)
    r = r[r["option_id"] == o["option_id"]]
    if r.empty:
        print("  Lumoda'nın kuralı: RPT VERMEDİ.")
        L = int(o["rpt_hafta"])
        print(f"    (yetişme kontrolü: lansman + 3 + {L} hafta = {t_(_pazartesi(o, 3 + L))} "
              f"< indirim başı {t_(o['indirim_baslangic'])}? "
              f"{'evet' if _pazartesi(o, 3 + L) < o['indirim_baslangic'] else 'hayır → kural vermez'})")
        return
    ak = hikaye.rpt_akibeti(v.t, v.opt, o["sezon_kodu"]).set_index("option_id").loc[o["option_id"]]
    for _, x in r.iterrows():
        print(f"  Lumoda'nın kuralı: {t_(x['siparis_tarihi'])} (lansman + {s(x['siparis_h'], 0)} hafta) "
              f"{s(x['adet'])} adet RPT (ilk alımın %50'si, MOQ'ya yuvarlı)")
        print(f"    planlanan geliş {t_(x['planlanan_teslim'])}, gerçekleşen {t_(x['gerceklesen_teslim'])} "
              f"(lansman + {s(x['gelis_h'], 1)} hafta; indirime {s(x['indirime_kalan_hafta'], 1)} hafta kala)")
    print(f"    çıkışta ({t_(o['cikis_tarihi'])}) depoda {s(ak['depo_cikista'])}; FIFO ile RPT'den depoda kalan "
          f"{s(ak['rpt_depoda_kalan'])}, mağazaya giden {s(ak['rpt_magazaya'])}; "
          f"çıkışta mağazalardan geri toplanan {s(ak['geri_toplama'])}")
    p = v.panel[v.panel["option_id"] == o["option_id"]].set_index("h")
    gelis_h = int(np.floor(r["gelis_h"].min()))
    print(f"    geliş sonrası haftalık seyir (h: satış / kayıp[gerçek] / sevk / depo / stoklu mağaza):")
    for h in range(max(gelis_h - 1, 0), min(gelis_h + 5, p.index.max() + 1)):
        print(f"      h={h:2d}  {s(p.loc[h, 'satis']):>5} / {s(p.loc[h, 'kayip']):>5} / "
              f"{s(p.loc[h, 'sevk']):>5} / {s(p.loc[h, 'depo_stok']):>5} / "
              f"{p.loc[h, 'stoklu_magaza']}/{p.loc[h, 'tasiyan_magaza']}")


def hikaye_bolumu(v: Veri) -> None:
    baslik("HİKÂYE (1. yazı) — Üçüncü haftada biten ürün")
    adaylar, yerli, uzak = _secim(v)

    alt(f"{HIKAYE_SEZONU} Collection'ın tutan option'ları (gerçek/plan ≥ 1,5), bitiş haftasına göre")
    print("  'bitti' = pazartesi sabahı depo ≤ ilk alımın %2'si VE depo+mağaza ≤ %20'si")
    print(f"  {'option':12s} {'model':18s} {'menşe':9s} {'dl':>2s} {'RPT':>3s} {'oran':>5s} "
          f"{'bitti_h':>7s} | h=3: {'satış':>5s} {'depo':>5s} {'mağaza':>6s} {'stoklu':>6s}")
    for _, a in adaylar.iterrows():
        print(f"  {a['option_id']:12s} {a['model_adi'][:18]:18s} {a['mense']:9s} {a['dalga']:>2d} "
              f"{a['rpt_hafta']:>3d} {s(a['oran'], 2):>5s} {s(a['bitti_h']):>7s} | "
              f"{s(a['satis_h3']):>11s} {s(a['depo_stok_h3']):>5s} {s(a['magaza_stok_h3']):>6s} "
              f"{a['stoklu_magaza_h3']:>3.0f}/{a['tasiyan_magaza_h3']:<2.0f}")
    h3_biten = adaylar[adaylar["bitti_h"] <= 3]
    print(f"  3. hafta pazartesisine (h ≤ 3) kadar biten tutan option: {len(h3_biten)}")
    print(f"  bitiş haftası dağılımı: " + ", ".join(
        f"h={int(h)}: {n}" for h, n in adaylar["bitti_h"].value_counts().sort_index().items()))

    alt("Seçilen option (yerli)")
    _option_ozeti(v, yerli, int(yerli["bitti_h"]), "YERLİ")
    _lumoda_rpt(v, yerli)

    alt(f"Mağaza tablosu — {yerli['option_id']}, {t_(_pazartesi(yerli, yerli['bitti_h']))} sabahı")
    mt = hikaye.magaza_tablosu(v.t, v.hh, yerli["option_id"], int(yerli["bitti_h"]))
    print(f"  {'mağaza':22s} {'tip':10s} {'satış':>6s} {'stoklu gün*':>11s} {'açık gün':>8s} "
          f"{'stok':>5s} {'stoklu beden':>12s} | {'gerçek talep**':>14s}")
    for _, m in mt.head(5).iterrows():
        print(f"  {m['ad'][:22]:22s} {m['tip'][:10]:10s} {s(m['satis']):>6s} {s(m['stoklu_gun_ort'], 1):>11s} "
              f"{s(m['acik_gun']):>8s} {s(m['stok']):>5s} {m['stoklu_beden']:>6.0f}/{m['beden']:<5.0f} | "
              f"{s(m['gercek_talep']):>14s}")
    print(f"  (toplam {len(mt)} mağaza; * bedenlerin ortalaması; ** satış + kayıp, zincir görmez)")

    alt("Uzak Doğu örneği")
    _option_ozeti(v, uzak, int(uzak["bitti_h"]), "UZAK DOĞU")
    _lumoda_rpt(v, uzak)

    alt("Veli'nin hatırası — Lumoda'nın RPT'lerinin akıbeti")
    for sezon in (ONCEKI_SEZON[HIKAYE_SEZONU], HIKAYE_SEZONU):
        ak = hikaye.rpt_akibeti(v.t, v.opt, sezon)
        r = hikaye.rpt_siparisleri(v.t, v.opt)
        r = r[r["sezon_kodu"] == sezon]
        print(f"  {sezon}: {len(ak)} option'a {len(r)} RPT, toplam {s(ak['rpt'].sum())} adet geldi")
        print(f"    mağazaya giden (FIFO) {s(ak['rpt_magazaya'].sum())} ({y(ak['rpt_magazaya'].sum() / ak['rpt'].sum())}), "
              f"çıkışta depoda kalan {s(ak['rpt_depoda_kalan'].sum())} "
              f"({y(ak['rpt_depoda_kalan'].sum() / ak['rpt'].sum())})")
        print(f"    RPT'li option'larda çıkışta mağazadan geri toplanan {s(ak['geri_toplama'].sum())}")
        print(f"    indirim başladıktan sonra gelen RPT: {int(r['indirimden_sonra'].sum())} "
              f"({s(r.loc[r['indirimden_sonra'], 'adet'].sum())} adet)")
        print(f"    menşeye göre: " + "; ".join(
            f"{m} {len(g)} RPT, {s(g['adet'].sum())} adet, geç gelen {int(g['indirimden_sonra'].sum())}"
            for m, g in r.groupby("mense")))

    alt("Bir sezonda kaç soru")
    o = v.opt[(v.opt["sezon_kodu"] == HIKAYE_SEZONU) & (v.opt["line"] == "Collection")]
    hafta = 6 - 3 + 1
    r = hikaye.rpt_siparisleri(v.t, v.opt)
    r = r[r["sezon_kodu"] == HIKAYE_SEZONU]
    print(f"  {HIKAYE_SEZONU} Collection: {o['model_kodu'].nunique()} model, {len(o)} option × "
          f"{hafta} karar pazartesisi (lansman + 3…6 hafta) = {len(o) * hafta} soru")
    print(f"  menşeye göre option: " + ", ".join(f"{m} {n}" for m, n in o["mense"].value_counts().items()))
    print(f"  Lumoda'nın verdiği RPT: {len(r)} ({r['option_id'].nunique()} option), "
          f"{s(r['adet'].sum())} adet; indirim başından sonra gelen {int(r['indirimden_sonra'].sum())}")
    gr = v.gercek.merge(o, on="option_id")
    tutan = gr[gr["gercek_io"] / gr["plan_sezon"] >= 1.5]
    print(f"  tutan option (gerçek/plan ≥ 1,5): {len(tutan)}; bunlardan RPT verilen "
          f"{int(tutan['option_id'].isin(r['option_id']).sum())}")
    tutmayan_rpt = r[~r["option_id"].isin(tutan["option_id"])]["option_id"].nunique()
    print(f"  RPT verilip tutan olmayan option: {tutmayan_rpt}")


# ---------------------------------------------------------------------
# KARAR (2. yazı)
# ---------------------------------------------------------------------

def karar_bolumu(v: Veri) -> None:
    baslik("KARAR (2. yazı) — yaşam eğrisi kadranı")
    tip = _tipik_rpt_hafta(v)
    for sezon in OYUN:
        alt(f"{sezon} eğrisi (öğrenildiği sezonlar: "
            f"{', '.join(v.egriler[(sezon, 'duzeltilmis', 'indirim')].sezonlar)}; stoklu gün düzeltmeli)")
        e = v.egriler[(sezon, "duzeltilmis", "indirim")]
        eh = v.egriler[(sezon, "ham", "indirim")]
        for d in (1, 2, 3):
            print(f"  dalga {d}: k_2 = {y(e.k((d,), 2))}, k_3 = {y(e.k((d,), 3))}, k_4 = {y(e.k((d,), 4))}, "
                  f"k_6 = {y(e.k((d,), 6))}   (çıplak eğriyle k_2 {y(eh.k((d,), 2))}, k_3 {y(eh.k((d,), 3))})")

    alt("Tedarikçiler")
    for _, td in v.t["tedarikci"].iterrows():
        print(f"  {td['tedarikci_id']} {td['ad']:24s} {td['ulke']:10s} {td['mense']:9s} "
              f"ilk sipariş {td['ilk_siparis_hafta']} hf, RPT {td['rpt_hafta']} hf, MOQ {td['moq_option']}")
    r = hikaye.rpt_siparisleri(v.t, v.opt)
    r["sapma_gun"] = (r["gerceklesen_teslim"] - r["planlanan_teslim"]).dt.days
    for m, g in r.groupby("mense"):
        print(f"  gerçekleşen RPT teslim sapması, {m}: ortalama {s(g['sapma_gun'].mean(), 1)} gün, "
              f"en çok {s(g['sapma_gun'].max())} gün (n={len(g)})")
    print(f"  tipik RPT süresi: yerli {tip['Yerli']} hafta (4–6), Uzak Doğu {tip['Uzak Doğu']} hafta (14–15)")

    alt(f"Lansman + {KARAR_H} hafta verilen RPT: gelişten sonra kalan eğri ({HIKAYE_SEZONU} eğrisi)")
    e_io = v.egriler[(HIKAYE_SEZONU, "duzeltilmis", "indirim")]
    e_cx = v.egriler[(HIKAYE_SEZONU, "duzeltilmis", "cikis")]
    o = v.opt[v.opt["sezon_kodu"] == HIKAYE_SEZONU].drop_duplicates("dalga").set_index("dalga")
    print(f"  {'dalga':5s} {'sezon hf':>8s} {'menşe':9s} {'L':>3s} {'geliş h':>7s} "
          f"{'indirime kalan':>14s} {'çıkışa kalan':>12s}")
    for d in (1, 2, 3):
        for m in ("Yerli", "Uzak Doğu"):
            L = tip[m]
            gh = KARAR_H + L
            print(f"  {d:>5d} {s(o.loc[d, 'satis_hafta'], 1):>8s} {m:9s} {L:>3d} {gh:>7d} "
                  f"{y(e_io.kalan((d,), gh)):>14s} {y(e_cx.kalan((d,), gh)):>12s}")
    print("  (indirime kalan: lansman→indirim talebinin gelişten sonraki payı;"
          " çıkışa kalan: lansman→çıkış talebinin, indirim dahil)")

    alt("Stoklu gün düzeltmesi örneği (hikâyenin yerli option'ı)")
    _, yerli, _ = _secim(v)
    oid = yerli["option_id"]
    for h in sorted({KARAR_H, int(yerli["bitti_h"])}):
        c = v.hh[(v.hh["option_id"] == oid) & (v.hh["h"] < h)]
        k = sansur.duzeltilmis_talep(c, h).iloc[0]
        st, ac = c["stoklu_gun"].sum(), c["acik_gun"].sum()
        print(f"  h={h}: satış x = {s(k['x'])}, stoklu hücre-gün {s(st)} / açık {s(ac)} ({y(st / ac)})")
        print(f"       çıplak haftalık hız {s(k['x'] / h, 1)}; düzeltilmiş haftalık talep {s(k['D'] / h, 1)} "
              f"(+{y(k['D'] / k['x'] - 1)}); [gerçek, zincir görmez] haftalık "
              f"{s((c['satis'].sum() + c['kayip'].sum()) / h, 1)}")


# ---------------------------------------------------------------------
# SANSÜR (3. yazı)
# ---------------------------------------------------------------------

def sansur_bolumu(v: Veri) -> None:
    baslik("SANSÜR (3. yazı) — ne kadar daha satardı")
    print("  Hedef: lansman → indirim başı gerçek talep (satış + kayıp). Collection option'ları.")
    print("  Eğriler oyun sezonundan önce kapanmış sezonlardan (AW24 ← SS24; SS25 ← SS24 + AW24).")
    print("  WAPE = Σ|hata| / Σgerçek; yanlılık = Σhata / Σgerçek; MAPE = option ortalaması.")
    for sezon in OYUN:
        tab = v.hata[sezon]
        for kesit in ("tümü", "tutan", "tutmayan"):
            tk = tab[tab["kesit"] == kesit]
            n = int(tk["n"].iloc[0])
            alt(f"{sezon} — {kesit} (n={n})")
            print(f"  {'katman':38s} " + " ".join(f"{'h=' + str(h):>22s}" for h in sansur.KARAR_HAFTALARI))
            print(f"  {'':38s} " + " ".join(f"{'WAPE  yanl.  MAPE':>22s}" for _ in sansur.KARAR_HAFTALARI))
            for kat in sansur.KATMANLAR + sansur.EK_KATMANLAR + ("plan",):
                satir = tk[tk["katman"] == kat].set_index("h")
                print(f"  {sansur.KATMAN_ADI[kat]:38s} " + " ".join(
                    f"{y(satir.loc[h, 'wape'], 0):>6s} {y(satir.loc[h, 'yanlilik'], 0):>6s} "
                    f"{y(satir.loc[h, 'mape'], 0):>7s} " for h in sansur.KARAR_HAFTALARI))

    alt("Hikâye option'larında katmanlar (sezon talebi kestirimi, lansman → indirim)")
    _, yerli, uzak = _secim(v)
    for o in (yerli, uzak):
        k = v.kestirim[HIKAYE_SEZONU]
        k = k[k["option_id"] == o["option_id"]].set_index("h")
        print(f"  {o['option_id']} ({o['model_adi']}, {o['mense']}): gerçek {s(o['gercek_io'])}, "
              f"plan {s(o['plan_sezon'])}, ilk alım {s(o['ilk_alim'])}")
        for h in sansur.KARAR_HAFTALARI:
            r = k.loc[h]
            print(f"    h={h}: a {s(r['a']):>6s} · b {s(r['b']):>6s} · c {s(r['c']):>6s} · d {s(r['d']):>6s}"
                  f"   (k_ham {y(r['k_ham'])}, k_düz {y(r['k_duz'])}, stoklu pay {y(r['stoklu_pay'])})")

    alt("FRR karşılığı (FRR 2001: ilk iki haftadan tahmin %8, alım komitesi %55)")
    for sezon in OYUN:
        tab = v.hata[sezon]
        tk = tab[(tab["kesit"] == "tümü")].set_index(["katman", "h"])
        print(f"  {sezon}: h=2'de d katmanı WAPE {y(tk.loc[('d', 2), 'wape'])}, FRR kuralı (c) "
              f"{y(tk.loc[('c', 2), 'wape'])}, buyer planı {y(tk.loc[('plan', 2), 'wape'])}; "
              f"h=3'te d {y(tk.loc[('d', 3), 'wape'])}")

    alt("Stoklu pay: karar anına kadar hücre-günlerin stoklu oranı")
    for sezon in OYUN:
        k = v.kestirim[sezon].merge(v.gercek, on="option_id")
        k["tutan"] = k["gercek_io"] / k["plan_sezon"] >= sansur.HIT_ESIGI
        for h in (3, 6):
            kh = k[k["h"] == h]
            print(f"  {sezon} h={h}: tutan {y(kh.loc[kh['tutan'], 'stoklu_pay'].mean())}, "
                  f"tutmayan {y(kh.loc[~kh['tutan'], 'stoklu_pay'].mean())}")

    alt("Eğri şekli: çıplak (sansürlü satış) vs düzeltilmiş vs gerçek, birikimli pay k_h")
    for sezon in OYUN:
        eh = v.egriler[(sezon, "ham", "indirim")]
        ed = v.egriler[(sezon, "duzeltilmis", "indirim")]
        eg = v.egriler[(sezon, "gercek", "indirim")]
        print(f"  {sezon} (öğrenme: {', '.join(ed.sezonlar)}; gerçek: {sezon}'in kendisi)")
        for d in (1, 2, 3):
            hs = range(1, 9)
            print(f"    dalga {d} h:      " + " ".join(f"{h:>5d}" for h in hs))
            for ad, e in (("çıplak", eh), ("düzeltilmiş", ed), ("gerçek", eg)):
                print(f"      {ad:12s}  " + " ".join(f"{s(100 * e.k((d,), h), 1):>5s}" for h in hs))
            fark_h = [100 * (eh.k((d,), h) - ed.k((d,), h)) for h in range(1, 7)]
            print(f"      çıplak − düzeltilmiş (puan), h=1..6: " + " ".join(s(f, 1) for f in fark_h)
                  + f"   en büyük {s(max(fark_h), 1)}")
        # Aynı düzeltilmiş eğriyi öğrenme sezonunun GERÇEK eğrisiyle kıyas
        gecmis_gercek = egri.egri_ogren(v.hh, v.opt, ed.sezonlar, "gercek")
        mae_d = np.mean([abs(ed.k((d,), h) - gecmis_gercek.k((d,), h)) for d in (1, 2, 3) for h in range(1, 7)])
        mae_h = np.mean([abs(eh.k((d,), h) - gecmis_gercek.k((d,), h)) for d in (1, 2, 3) for h in range(1, 7)])
        print(f"    öğrenme sezonlarının kendi gerçek eğrisine ortalama mutlak uzaklık (h=1..6): "
              f"düzeltilmiş {s(100 * mae_d, 2)} puan, çıplak {s(100 * mae_h, 2)} puan")

    alt("Gruplama: dalga vs üst kategori × dalga (düzeltilmiş), oyun sezonunun gerçek eğrisine uzaklık")
    for sezon in OYUN:
        ed = v.egriler[(sezon, "duzeltilmis", "indirim")]
        ek = egri.oyun_egrisi(v.t, v.opt, sezon, "duzeltilmis", grup=("ust_kategori", "dalga"))
        gk = egri.egri_ogren(v.hh, v.opt, [sezon], "gercek", grup=("ust_kategori", "dalga"))
        fark_d, fark_k = [], []
        for anahtar in gk.paylar:
            for h in range(1, 7):
                fark_d.append(abs(ed.k((anahtar[1],), h) - gk.k(anahtar, h)))
                fark_k.append(abs(ek.k(anahtar, h) - gk.k(anahtar, h)))
        print(f"  {sezon}: yalnız dalga {s(100 * np.mean(fark_d), 2)} puan, "
              f"kategori × dalga {s(100 * np.mean(fark_k), 2)} puan "
              f"({len(gk.paylar)} grup; seçilen: yalnız dalga)")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    v = hazirla()
    hikaye_bolumu(v)
    karar_bolumu(v)
    sansur_bolumu(v)
    from rapor_b import faz_b

    faz_b(v)


if __name__ == "__main__":
    main()
