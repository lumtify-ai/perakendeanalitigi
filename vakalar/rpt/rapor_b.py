"""Raporun B bölümleri (oyun): ADAY (4. yazı), MİKTAR (5. yazı), SONUÇ ve YOLLAR (6. yazı).

`rapor.py` çağırır (`hazirla_b`, sonra bölümler); tek başına koşmaz (A'nın verisine dayanır).

Koşular `oyun`un önbelleğinden okunur (`oyun.dagitim_tablosu` / `tum_kollar` ile aynı
anahtarlar: ızgara yeniden koşulmaz). `oyun.py` koşu kod özetindedir (Ruling R3); ölçüm
yardımcılarının bu raporda gereken hâlleri burada kopyadır (`kollar_olc`: `oyun.ozet_tablosu`
+ option tabloları; `secim_kosulari`: `oyun.dagitim_tablosu` + koşular), oyun.py değişmez.

Ölçütler her koşunun gizli gerçeğinden (`olcutler`, `Kosu.gercek`); hakem burada yok.
Kâhin (Ruling R7): aynı tohumla koşulmuş `rpt_yok` koşusunun talebini bilen kol, "RPT
verilmeseydi gelecek talebi bilen"; zincir düzeyinde düşünür, üst sınır değildir.
"""

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from rapor import (HAFTALAR, HIKAYE_SEZONU, KARAR_H, MENSELER, OYUN, alt, baslik, bolum, fark, fifo_denetimleri,
                   mn, olcut_denetimleri, pay, s, t_, tl, y)
from rpt import aday, dagitim, hikaye, kaynak, miktar, olcutler, oyun, yollar

KOL_ADI = {
    "rpt_yok": "RPT yok", "mevcut": "Banu", "frr2": "FRR, h=2", "frr3": "FRR, h=3",
    "oneri": "öneri (LightGBM)", "oneri_lojistik": "öneri (lojistik)", "kahin": "kâhin",
}
OZELLIK_ADI = {
    "h": "karar haftası h", "str": "zincir STR'si", "stoklu_magaza_payi": "stoklu mağaza payı",
    "kirik_magaza_payi": "kırık mağaza payı", "hiz_q1": "düzeltilmiş haftalık hız ÷ ilk alım",
    "d_q1": "d kestirimi ÷ ilk alım", "frr_q1": "FRR kestirimi ÷ ilk alım", "kapsama": "stok kapsaması (hafta)",
    "hafta_indirime": "indirime kalan hafta", "L": "tedarikçinin RPT süresi",
    "kalan_tf": "gelişten sonra kalan tam fiyat talep payı", "ekstra_q1": "tahmini ek talep ÷ ilk alım",
    "moq_oran": "MOQ ÷ tahmini ek talep", "uzak": "Uzak Doğu tedarikçisi",
}


@dataclass
class VeriB:
    secim: pd.DataFrame                    # SS24 dağıtım seçimi (kural başına sezon özeti)
    en_iyi: str
    K: dict                                # (kol, kural) → KosuKaydi
    secim_kosulari: dict                   # kural → KosuKaydi (SS24)
    o: dict = field(default_factory=dict)  # (kol, kural, sezon) → option tablosu (rpt_yok tabanlı)
    oz: dict = field(default_factory=dict)  # (kol, kural, sezon) → sezon özeti
    akibet: dict = field(default_factory=dict)  # (kol, kural, sezon) → FIFO akıbeti (koşunun tablolarından)
    sinama: pd.DataFrame | None = None
    yollar: dict | None = None
    oyun_json: dict | None = None
    hazirlik_onbellekten: bool = True

    def onbellek_durumu(self) -> dict:
        d = {"lumoda (hazırlık)": bool(self.hazirlik_onbellekten)}
        d |= {f"{k}|{r}": bool(v.onbellekten) for (k, r), v in self.K.items() if (k, r) != ("mevcut", "a")}
        d |= {f"seçim {r}": bool(v.onbellekten) for r, v in self.secim_kosulari.items()}
        return d


FIFO_KOLLARI = [("mevcut", "a"), ("mevcut", "b"), ("mevcut", "c"), ("mevcut", "d"), ("frr3", "b"),
                ("oneri", "b"), ("oneri_lojistik", "b"), ("kahin", "b")]


def _metin(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        if isinstance(df[c].dtype, pd.CategoricalDtype):
            df[c] = df[c].astype(str)
    return df


def kosu_akibeti(kosu, opt: pd.DataFrame, sezon: str) -> pd.DataFrame:
    """Bir koşunun RPT akıbeti (`hikaye.rpt_akibeti`, FIFO), koşunun kendi tablolarından:
    sezonun Collection SKU'ları; `depo_stok` yalnız pazartesileri (yayımlanan yükleyiciyle aynı)."""
    c = opt[(opt["sezon_kodu"] == sezon) & (opt["line"] == "Collection")]
    u = _metin(kosu.tablo("urun", ["urun_id", "option_id"]))
    u = u[u["option_id"].isin(set(c["option_id"].astype(str)))]
    sku = list(u["urun_id"])
    ds = _metin(kosu.tablo("depo_stok", ["tarih", "urun_id", "adet"], urunler=sku))
    sa = _metin(kosu.tablo("satis", ["tarih", "magaza_id", "urun_id", "adet"], urunler=sku))
    t = {
        "urun": u,
        "siparis": _metin(kosu.tablo("siparis", urunler=sku)),
        "kalite_kontrol": _metin(kosu.tablo("kalite_kontrol")),
        "depo_stok": ds[pd.to_datetime(ds["tarih"]).dt.dayofweek == 0].reset_index(drop=True),
        "sevkiyat": _metin(kosu.tablo("sevkiyat", ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip"],
                                      urunler=sku)),
        "satis": sa[sa["magaza_id"] == kaynak.ONLINE].reset_index(drop=True),
    }
    return hikaye.rpt_akibeti(t, opt, sezon)


def secim_kosulari(H) -> tuple[pd.DataFrame, dict]:
    """`oyun.dagitim_tablosu`'nun kopyası (aynı koşu adları ve parametreler: önbellekten), koşularla."""
    satir, kosular = [], {}
    for kural in dagitim.KURAL_ADLARI:
        rep = oyun.dagitim_politikasi(H, kural, (oyun.SECIM_SEZONU,))
        k = oyun._kos(f"y{H.yol}_secim_{kural}", None, replenishment=rep,
                      parametreler={"secim": oyun.SECIM_SEZONU, "kural": kural}, talep_tohumu=H.talep_tohumu,
                      onbellek=H.onbellek, olcek=H.olcek)
        oz = olcutler.sezon_ozeti(olcutler.ozet(k, oyun.SECIM_SEZONU))
        kosular[kural] = k
        satir.append({"kural": kural, **{c: oz[c] for c in (
            "kar", "gelir", "karsilanmayan", "kalici_kayip", "satis_tf", "satis_ind", "rpt", "rpt_giren",
            "rpt_bosa", "magazaya", "stoklu_pay_tf", "ikameye_giden")}})
    return pd.DataFrame(satir), kosular


def kollar_olc(K: dict, sezon: str, kahin_anahtari) -> tuple[dict, dict]:
    """`oyun.ozet_tablosu`'nun kopyası; option tablolarını da döndürür."""
    taban = olcutler.ozet(K[("rpt_yok", "a")], sezon)
    kh = olcutler.ozet(K[kahin_anahtari], sezon, taban)
    o, oz = {}, {}
    for anahtar, k in K.items():
        tab = kh if anahtar == kahin_anahtari else olcutler.ozet(k, sezon, taban)
        o[anahtar] = tab
        oz[anahtar] = olcutler.sezon_ozeti(tab, kh)
    return o, oz


def hazirla_b(va) -> VeriB:
    H = va.H
    secim, sk = secim_kosulari(H)
    en_iyi = oyun.en_iyi_kural(secim)
    K = oyun.tum_kollar(H, en_iyi=en_iyi, ilerleme=None)
    vb = VeriB(secim=secim, en_iyi=en_iyi, K=K, secim_kosulari=sk, hazirlik_onbellekten=H.kosu.onbellekten)
    for G in OYUN:
        o, oz = kollar_olc(K, G, ("kahin", en_iyi))
        for (kol, kural) in K:
            vb.o[(kol, kural, G)] = o[(kol, kural)]
            vb.oz[(kol, kural, G)] = oz[(kol, kural)]
        for kol, kural in FIFO_KOLLARI:
            if (kol, kural) in K:
                vb.akibet[(kol, kural, G)] = kosu_akibeti(K[(kol, kural)], va.opt, G)
    for kural, k in sk.items():
        vb.akibet[("secim", kural, oyun.SECIM_SEZONU)] = kosu_akibeti(k, va.opt, oyun.SECIM_SEZONU)
    vb.sinama = oyun.sinama(H, K[("rpt_yok", "a")])
    vb.yollar = json.loads(yollar.CIKTI.read_text(encoding="utf-8")) if yollar.CIKTI.exists() else None
    oj = oyun.CIKTI / "oyun.json"
    vb.oyun_json = json.loads(oj.read_text(encoding="utf-8")) if oj.exists() else None
    return vb


def _kayit(vb: VeriB, kol: str, kural: str) -> pd.DataFrame:
    k = vb.K[(kol, kural)].kayitlar.get("rpt")
    return pd.DataFrame(columns=["gun", "option", "option_id", "h", "adet"]) if k is None else k


def _mense(va, ids) -> pd.Series:
    return va.opt.set_index("option_id").loc[list(ids), "mense"]


# ---------------------------------------------------------------------------
# ADAY (4. yazı)
# ---------------------------------------------------------------------------

def aday_bolumu(va, vb: VeriB, ek: list) -> None:
    baslik("ADAY (4. yazı) — Hangi ürün RPT'ye aday")
    print("  Satır: Collection option'ı × karar pazartesisi h = 2…6, henüz RPT'si yokken.")
    print("  Etiket: 'bu pazartesi max(MOQ, newsvendor) RPT verilseydi, gelen maldan en az MOQ/2'si tam")
    print("  fiyattan satılır mıydı?' (i) gerçek talep ile (sahada yok), (ii) sezon sonunda karar anı Basit'iyle")
    print("  doldurulmuş talep ile (sahada kurulabilir; oyun sezonunun ilk lansman sabahında bilinenle).")
    print("  Modeller (ii) ile, oyun sezonundan önce kapanmış sezonların satırlarıyla eğitilir; sınama")
    print("  satırları rpt_yok kolunun dünyasından (kolun karar anında gördüğüyle), etiket (i) o koşunun talebinden.")
    ogr = va.ogr
    alt("Eğitim satırları ve iki etiketin uyumu")
    for G in OYUN:
        e = va.H.egitim[G]
        u = aday.uyum(e)
        m = ogr.modeller[G]
        print(f"  {G} eğitimi ({', '.join(m.sezonlar)}; {s(len(e))} satır, {s(e['option_id'].nunique())} option): "
              f"pozitif (ii) {s(u['pozitif_duz'])} ({y(pay(u['pozitif_duz'], u['n']))}), pozitif (i) "
              f"{s(u['pozitif_gercek'])} ({y(pay(u['pozitif_gercek'], u['n']))})")
        print(f"    ikisi pozitif {s(u['ikisi'])}, yalnız (i) {s(u['yalniz_gercek'])}, yalnız (ii) {s(u['yalniz_duz'])}, "
              f"ikisi negatif {s(u['hicbiri'])}; aynı sonuç {y(u['uyum'])}, κ {s(u['kappa'], 3)}")
        ek.append((f"{G} modeli eğitim satırı = eğitim tablosu", m.n == len(e) and m.pozitif == u["pozitif_duz"]))
    for G in OYUN:
        e = va.H.egitim[G]
        alt(f"{G} eğitiminde pozitifler (ii) menşe × h (satır / pozitif)")
        _mense_h_tablosu(e, "etiket_duz", va.opt.set_index("option_id")["mense"])

    s_ = vb.sinama
    for G in OYUN:
        t = s_[s_["sezon_kodu"] == G]
        alt(f"{G} sınaması (rpt_yok dünyası; {s(len(t))} satır = {s(t['option_id'].nunique())} option × "
            f"{s(t['h'].nunique())} hafta)")
        print(f"  pozitif (i) {s(t['etiket_gercek'].sum())} ({y(pay(t['etiket_gercek'].sum(), len(t)))})")
        _mense_h_tablosu(t, "etiket_gercek", va.opt.set_index("option_id")["mense"])
        tah = {
            "Banu kuralı (STR ≥ %55, h 3–6)": t["banu"].to_numpy(bool),
            "lojistik (p ≥ 0,5)": t["p_lojistik"].to_numpy() >= aday.ESIK,
            "LightGBM (p ≥ 0,5)": t["p_lgbm"].to_numpy() >= aday.ESIK,
            "mükemmel (etiket (i))": t["etiket_gercek"].to_numpy(bool),
        }
        print(f"  {'model':31s} {'alarm':>5s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'isabet':>7s} {'duyarl.':>7s} "
              f"{'yanlış alarm TL':>16s} {'kaçırma TL':>15s} | {'ilk alarm':>9s} {'ilk alarm kârı TL':>18s}")
        sonuc = {}
        for ad, tt in tah.items():
            r = aday.degerlendir(tt, t, "gercek")
            sonuc[ad] = r
            print(f"  {ad:31s} {s(r['tp'] + r['fp']):>5s} {s(r['tp']):>4s} {s(r['fp']):>4s} {s(r['fn']):>4s} "
                  f"{y(r['isabet']):>7s} {y(r['duyarlilik']):>7s} {s(r['yanlis_alarm_tl']):>16s} "
                  f"{s(r['kacirma_tl']):>15s} | {s(r['ilk_alarm_option']):>9s} {s(r['ilk_alarm_kar_tl']):>18s}")
        mk = sonuc["mükemmel (etiket (i))"]["ilk_alarm_kar_tl"]
        print("  ilk alarm kârı, mükemmelin: " + "; ".join(
            f"{ad.split(' (')[0]} {y(pay(r['ilk_alarm_kar_tl'], mk))}" for ad, r in sonuc.items()
            if not ad.startswith("mükemmel")))
        print("  (TL: sonradan bakış kârı (i); yanlış alarm = alarm verilip etiketi negatif satırların zararı, "
              "kaçırma = alarmsız pozitif satırların kârı; ilk alarm: option'ın ilk alarmında sipariş, en fazla bir RPT)")
        print("  milyon TL: " + "; ".join(
            f"{ad.split(' (')[0]} yanlış alarm {mn(r['yanlis_alarm_tl'], 1)}, kaçırma {mn(r['kacirma_tl'], 1)}, "
            f"ilk alarm {mn(r['ilk_alarm_kar_tl'], 1)}" for ad, r in sonuc.items()))

    for G in OYUN:
        alt(f"Lojistik regresyon katsayıları ({G} modeli, ölçeklenmiş özellikler; büyükten küçüğe)")
        kat = ogr.modeller[G].katsayilar()
        for i, (ad, k) in enumerate(kat.items(), start=1):
            print(f"  {i:2d}. {OZELLIK_ADI.get(ad, ad):42s} {s(k, 2):>6s}")
        en = abs(kat.iloc[0])
        st = kat["str"]
        print(f"  zincir STR'si {list(kat.index).index('str') + 1}. sırada; |katsayı| en büyüğe "
              f"oranı {s(bolum(abs(st), abs(en), 2, 2), 2)} (|{s(st, 2)}| / |{s(en, 2)}|)")

    alt("Öneri kolu LightGBM ile ve lojistikle (aynı dağıtım)")
    for G in OYUN:
        a = _kayit(vb, "oneri", vb.en_iyi)
        b = _kayit(vb, "oneri_lojistik", vb.en_iyi)
        sa = set(a.loc[a["option_id"].map(_sezon_haritasi(va)) == G, "option_id"])
        sb = set(b.loc[b["option_id"].map(_sezon_haritasi(va)) == G, "option_id"])
        da = vb.oz[("oneri", vb.en_iyi, G)]["d_kar"]
        db = vb.oz[("oneri_lojistik", vb.en_iyi, G)]["d_kar"]
        print(f"  {G}: LightGBM {s(len(sa))} option, lojistik {s(len(sb))} option; ortak {s(len(sa & sb))}, yalnız "
              f"LightGBM {s(len(sa - sb))}, yalnız lojistik {s(len(sb - sa))}; Δkâr LightGBM {tl(da)}, lojistik {tl(db)} "
              f"(fark {tl(fark(db, da))})")


def _ad(anahtar: str) -> str:
    """"kol|kural" → okunur ad: "Banu / b"."""
    kol, kural = anahtar.split("|")
    return f"{KOL_ADI[kol]} / {kural}"


def _sezon_haritasi(va) -> pd.Series:
    return va.opt.set_index("option_id")["sezon_kodu"]


def _mense_h_tablosu(d: pd.DataFrame, etiket: str, mense: pd.Series) -> None:
    """Satır / pozitif, menşe × h (menşe option tablosundan)."""
    d = d.assign(_m=d["option_id"].astype(str).map(mense).to_numpy())
    print(f"    {'menşe':9s} " + " ".join(f"{'h=' + str(h):>9s}" for h in HAFTALAR) + f" {'toplam':>11s}")
    for m in MENSELER:
        g = d[d["_m"] == m]
        if g.empty:
            continue
        print(f"    {m:9s} " + " ".join(
            f"{s(len(g[g['h'] == h])) + '/' + s(g.loc[g['h'] == h, etiket].sum()):>9s}" for h in HAFTALAR)
              + f" {s(len(g)) + '/' + s(g[etiket].sum()):>11s}")


# ---------------------------------------------------------------------------
# MİKTAR (5. yazı)
# ---------------------------------------------------------------------------

def _hikaye_satiri(va, oid: str, h: int) -> pd.Series:
    """Yayımlanan dünyanın (Banu'nun gördüğü) h. pazartesi sabahı: karar anı x, D (SANSÜR
    katmanlarıyla aynı) + tablodan durum → `aday.ozellikler` satırı."""
    ogr = va.ogr
    o = va.opt.set_index("option_id").loc[oid]
    G = o["sezon_kodu"]
    k = va.katman[G]
    k = k[(k["option_id"] == oid) & (k["h"] == h)]
    karar = pd.Timestamp(k["karar_ani"].iloc[0])
    kayit = k[["option_id", "h", "karar_ani", "x", "D", "stoklu_pay"]].assign(sezon_kodu=G, dalga=int(o["dalga"]))
    durum = aday.durum_tablodan(va.t, karar, [oid])
    kayit = kayit.merge(durum, on="option_id")
    return aday.ozellikler(kayit, ogr.optionlar, ogr.egriler[G], ogr.belirsizlik[G], ogr.p_ind).iloc[0]


def miktar_bolumu(va, vb: VeriB, ek: list) -> None:
    baslik("MİKTAR (5. yazı) — Ne kadar, ne zaman")
    ogr = va.ogr
    opt = ogr.optionlar
    alt("Fiyat, maliyet, indirim dönemi beklenen fiyatı (Collection, option ortalaması)")
    for ad, sez in (("AW24 + SS25", OYUN), *((G, (G,)) for G in OYUN)):
        c = opt[(opt["line"] == "Collection") & opt["sezon_kodu"].isin(sez)]
        p, cc = c["liste_fiyati"].astype(float), c["alis_fiyati"].astype(float)
        pi = ogr.p_ind.reindex(c["option_id"].astype(str)).to_numpy(float)
        P, C, PI = p.mean(), cc.mean(), float(np.mean(pi))
        print(f"  {ad}: liste {tl(P)}, alış {tl(C)} (liste / alış {s(bolum(P, C), 2)}), indirim dönemi beklenen "
              f"fiyat {tl(PI)} (indirim fiyatı / liste {y(pay(PI, P))})")
        print(f"    Cu = liste − alış = {s(P)} − {s(C)} ≈ {tl(fark(C, P))}; Co (indirimde satılırsa) = alış − "
              f"indirim fiyatı = {s(C)} − {s(PI)} ≈ {tl(fark(PI, C))}; Co (hiç satılmazsa) = alış {tl(C)}")
        print(f"    kritik oran (tam fiyat vs hiç satılmaz) Cu / (Cu + alış) = {s(fark(C, P))} / "
              f"({s(fark(C, P))} + {s(C)}) = {y(bolum(fark(C, P), fark(C, P) + round(C)))}")
        print(f"    indirim fiyatı alışın üstünde olan option {s((pi > cc.to_numpy()).sum())}/{s(len(c))}")
    alt("Kestirim belirsizliği: log(hedef / d kestirimi), geçmiş sezonlardan (hedef: Basit'le doldurulmuş talep)")
    for G in OYUN:
        b = ogr.belirsizlik[G]
        print(f"  {G} ← {', '.join(b.sezonlar)}: " + "; ".join(
            f"h={h}: μ {s(b.mu[h], 3)}, σ {s(b.sigma[h], 3)} (n={s(b.n[h])})" for h in sorted(b.mu)))

    alt(f"Hikâye option'ları: {KARAR_H}. pazartesi ve Banu'nun sipariş pazartesisi (yayımlanan dünyanın "
        f"sabahı, Banu'nun gördüğü)")
    yay = va.rpt_yay.set_index("option_id")
    sahneler = [(va.hik.hit_option, KARAR_H)]
    gh = int(round(yay.loc[va.hik.gec_option, "siparis_h"])) if va.hik.gec_option in yay.index else KARAR_H
    sahneler += [(va.hik.gec_option, h) for h in sorted({KARAR_H, gh})]
    for oid, hh in sahneler:
        r = _hikaye_satiri(va, oid, hh)
        o = opt.set_index("option_id").loc[oid]
        G = o["sezon_kodu"]
        e = ogr.egriler[G]
        d = int(o["dalga"])
        mu, sg = ogr.belirsizlik[G].al(hh)
        nv = miktar.newsvendor(r["D"], hh, int(r["L"]), r["W"], e[("duzeltilmis", "indirim")],
                               e[("duzeltilmis", "cikis")], d, r["ip"], r["p"], r["c"], r["p_ind"], mu, sg, int(r["moq"]))
        q_banu = miktar.banu(float(o["ilk_alim"]), int(r["moq"]))
        q_frr = miktar.frr(float(r["satilan"]), e[("ham", "indirim")].k((d,), hh), float(o["ilk_alim"]),
                           int(r["moq"]))
        print(f"  {oid} ({o['model_adi']} {o['renk']}; {o['mense']}, RPT {s(r['L'])} hafta, MOQ {s(r['moq'])}, "
              f"ilk alım {s(o['ilk_alim'])}), {hh}. pazartesi; zincir STR {y(r['str'])}"
              f"{' (Banu eşiği aşılmış)' if r['str'] >= miktar.RPT_STR_ESIGI else ''}:")
        print(f"    bugüne kadar brüt satış x {s(r['x'])}, düzeltilmiş talep D {s(r['D'])}; d kestirimi (lansman → indirim) "
              f"{s(r['d_kestirim'])}; envanter pozisyonu {s(r['ip'])} (depo {s(r['depo'])} + mağaza {s(r['magaza'])} "
              f"+ yolda {s(r['yolda'])} + açık sipariş {s(r['acik'])})")
        print(f"    liste {tl(r['p'])}, alış {tl(r['c'])}, indirim fiyatı {tl(r['p_ind'])}; μ {s(mu, 3)}, σ {s(sg, 3)}")
        print(f"    beklenen talep: bugünden RPT'nin gelişine {s(nv['B'])}, gelişten indirime tam fiyat {s(nv['Xtf'])}, "
              f"indirim dönemi (gelişten sonra) {s(nv['Xind'])}")
        print(f"    Banu (ilk alımın yarısı) {s(q_banu)} · FRR {s(q_frr)} · newsvendor {s(nv['q'])} (MOQ kapısız en iyi "
              f"{s(nv['q_serbest'])}; beklenen tam fiyat satış {s(nv['beklenen_tf'])}, indirimli {s(nv['beklenen_ind'])}, "
              f"kâr {tl(nv['beklenen_kar'])})")
        ek.append((f"{oid} h={hh}: newsvendor miktarı = aday özelliğinin q_nv'si", int(nv["q"]) == int(r["q_nv"])))
        if hh != max(h_ for o_, h_ in sahneler if o_ == oid):
            continue
        for kol in ("mevcut", "frr3", "oneri", "oneri_lojistik", "kahin"):
            kk = _kayit(vb, kol, vb.en_iyi)
            kk = kk[kk["option_id"] == oid]
            if kk.empty:
                print(f"    {KOL_ADI[kol]} / {vb.en_iyi}: RPT vermedi")
                continue
            x = kk.iloc[0]
            ekb = f", p {s(x['p'], 2)}" if "p" in kk.columns and pd.notna(x.get("p")) else ""
            print(f"    {KOL_ADI[kol]} / {vb.en_iyi}: {s(x['h'])}. pazartesi ({t_(_gun(va, x['gun']))}) {s(x['adet'])} "
                  f"adet{ekb}")

    alt("Ne zaman: kolların RPT kararları, karar haftasına ve menşeye göre (seçilen dağıtımla)")
    sh = _sezon_haritasi(va)
    for kol in ("mevcut", "frr3", "oneri", "oneri_lojistik", "kahin"):
        kk = _kayit(vb, kol, vb.en_iyi)
        for G in OYUN:
            g = kk[kk["option_id"].map(sh) == G]
            if g.empty:
                print(f"  {KOL_ADI[kol]:22s} {G}: RPT yok")
                continue
            mm = _mense(va, g["option_id"]).to_numpy()
            print(f"  {KOL_ADI[kol]:22s} {G}: {s(len(g))} RPT, {s(g['adet'].sum())} adet; h: " + ", ".join(
                f"{int(h)}→{s(n)}" for h, n in g["h"].value_counts().sort_index().items()) + "; menşe: " + ", ".join(
                f"{m} {s((mm == m).sum())}" for m in MENSELER if (mm == m).any()))

    alt("Menşeye göre: RPT'li option'ların tabana (RPT yok) göre farkı (seçilen dağıtım)")
    for G in OYUN:
        print(f"  {G}:")
        for kol in ("mevcut", "frr3", "oneri", "kahin"):
            for kural in (("a", vb.en_iyi) if kol == "mevcut" else (vb.en_iyi,)):
                o = vb.o[(kol, kural, G)]
                rp = o[o["rpt"] > 0]
                parca = []
                for m in MENSELER:
                    g = rp[rp["mense"] == m]
                    parca.append(f"{m} {s(len(g))} opt / {s(g['rpt'].sum())} adet, ek tf {s(g['d_satis_tf'].sum())}, "
                                 f"ek ind {s(g['d_satis_ind'].sum())}, Δkâr {tl(g['d_kar'].sum())}")
                print(f"    {KOL_ADI[kol] + ' / ' + kural:22s} " + " | ".join(parca))
                print(f"    {'':22s} RPT'li toplam Δkâr {tl(rp['d_kar'].sum())}; RPT'siz option'ların Δkârı "
                      f"{tl(o.loc[o['rpt'] == 0, 'd_kar'].sum())}; sezon Δkârı {tl(o['d_kar'].sum())}")


def _gun(va, gun) -> pd.Timestamp:
    """Motor günü → tarih (takvim: dünyanın ısınma başlangıcından)."""
    from rpt import motor
    return pd.Timestamp(motor._gun_tarihi([int(gun)])[0])


# ---------------------------------------------------------------------------
# SONUÇ (6. yazı)
# ---------------------------------------------------------------------------

def _fifo_satiri(ak: pd.DataFrame) -> str:
    g = ak["rpt_giren"].sum()
    return (f"giren {s(g)}: çıkışta depoda {s(ak['rpt_depoda_cikista'].sum())} ({y(pay(ak['rpt_depoda_cikista'].sum(), g))}), "
            f"çıkışa dek çıkan {s(ak['rpt_cikisa_kadar'].sum())} (mağazaya {s(ak['rpt_magazaya_alt'].sum())}–"
            f"{s(ak['rpt_magazaya_ust'].sum())}), outlet'e {s(ak['rpt_outlete'].sum())}, pencere sonu depoda "
            f"{s(ak['rpt_depoda_kalan'].sum())}")


KOLON = [("rpt_option", "RPT opt", 0), ("rpt", "RPT adet", 0), ("rpt_giren", "giren", 0),
         ("rpt_bosa", "boşa (son)", 0), ("rpt_ek_tf", "ek tf", 0), ("rpt_ek_ind", "ek ind", 0),
         ("kurtarilan", "kurtarılan", 0), ("kurtarilan_kalici", "kalıcı", 0), ("kurtarilan_ikame", "ikame", 0),
         ("d_kar", "Δ kâr TL", 0), ("yanlis_alarm", "yanl. alarm", 0), ("kacirilan", "kaçırılan", 0),
         ("magazaya", "mağazaya", 0), ("stoklu_pay_tf", "stoklu pay", 3)]


def sonuc_bolumu(va, vb: VeriB, ek: list) -> None:
    baslik("SONUÇ (6. yazı) — RPT geldi, mağazada satış sıfır")
    en = vb.en_iyi
    print("  Değerleme: gelir (gerçekleşen satış tutarı; markdown, kampanya, outlet dahil) − alış × depoya giren "
          "(ilk alım + RPT − kalite reddi); pencere sonunda kalan stok 0 TL. Taban: RPT yok (aynı talep tohumu).")
    print("  Kurtarılan kayıp = tabana göre karşılanmayan talebin düşüşü (kalıcı kayıp + başka ürüne ikame).")
    print("  Kâhin: aynı tohumlu RPT yok koşusunun talebini bilen kol (RPT verilmeseydi gelecek talebi bilen); "
          "gerçek teslim gecikmesini de bilir; zincir düzeyinde düşünür, üst sınır değildir.")

    alt(f"Dağıtım kuralının seçimi (oyundan önce, {oyun.SECIM_SEZONU}; Banu'nun RPT'leri, dört kural)")
    a0 = vb.secim.set_index("kural").loc["a", "kar"]
    for r in vb.secim.itertuples(index=False):
        ak = vb.akibet[("secim", r.kural, oyun.SECIM_SEZONU)]
        print(f"  {r.kural}: {oyun.SECIM_SEZONU} Collection kârı {tl(r.kar)} ({mn(r.kar, 1)}; a'ya göre "
              f"{tl(fark(a0, r.kar))}), karşılanmayan {s(r.karsilanmayan)} (kalıcı {s(r.kalici_kayip)}), tam fiyat "
              f"satış {s(r.satis_tf)}, indirimli {s(r.satis_ind)}, mağazaya giden (bütün mal) {s(r.magazaya)}")
        print(f"     RPT {s(r.rpt)} adet; {_fifo_satiri(ak)}; pencere sonu kalan RPT (boşa) {s(r.rpt_bosa)}")
        ek += fifo_denetimleri(ak, f"seçim {r.kural}")
    sk_ = vb.secim.set_index("kural")["kar"]
    print(f"  b − d: {tl(sk_['b'])} − {tl(sk_['d'])} = {tl(fark(sk_['d'], sk_['b']))} "
          f"(SS24 Collection kârının {y(pay(fark(sk_['d'], sk_['b']), sk_['b']), 2)}); b − a {tl(fark(sk_['a'], sk_['b']))}")
    print(f"  seçilen kural: {en} (b stoklu gün hızı, c yeniden lansman, d c + %30 depoda tutma; a bugünkü kural, "
          f"taban); oyun.json'daki seçim {vb.oyun_json['en_iyi'] if vb.oyun_json else '—'}")
    if vb.oyun_json:
        ek.append(("seçilen dağıtım kuralı = oyun.json", vb.oyun_json["en_iyi"] == en))

    gec = va.hik.gec_option
    alt(f"Geç gelen ({gec}): Banu'nun RPT'si her dağıtım kuralıyla")
    t0 = vb.o[("rpt_yok", "a", HIKAYE_SEZONU)].set_index("option_id").loc[gec]
    for kural in ("a", "b", "c", "d"):
        o = vb.o[("mevcut", kural, HIKAYE_SEZONU)].set_index("option_id").loc[gec]
        ak = vb.akibet[("mevcut", kural, HIKAYE_SEZONU)].set_index("option_id")
        fifo = (f"çıkışta depoda {s(ak.loc[gec, 'rpt_depoda_cikista'])}, çıkışa dek çıkan "
                f"{s(ak.loc[gec, 'rpt_cikisa_kadar'])} (mağazaya {s(ak.loc[gec, 'rpt_magazaya_alt'])}–"
                f"{s(ak.loc[gec, 'rpt_magazaya_ust'])}), outlet'e {s(ak.loc[gec, 'rpt_outlete'])}"
                if gec in ak.index else "RPT yok")
        print(f"  {kural}: RPT {s(o['rpt'])} (giren {s(o['rpt_giren'])}), geldi {t_(o['rpt_teslim'])}; {fifo}; satış "
              f"tf {s(o['satis_tf'])} ind {s(o['satis_ind'])}, karşılanmayan {s(o['karsilanmayan'])}, kâr {tl(o['kar'])} "
              f"(RPT yoka göre {tl(o['d_kar'])})")
    print(f"  RPT yok: satış tf {s(t0['satis_tf'])} ind {s(t0['satis_ind'])}, karşılanmayan {s(t0['karsilanmayan'])}, "
          f"kâr {tl(t0['kar'])}")

    for G in OYUN:
        alt(f"Kollar — {G} (Collection, {s(len(vb.o[('rpt_yok', 'a', G)]))} option; taban RPT yok)")
        _kollar_tablosu(vb, G)
        t = vb.oz[("rpt_yok", "a", G)]
        print(f"  taban (RPT yok): kâr {tl(t['kar'])} ({mn(t['kar'], 1)}), tam fiyat satış {s(t['satis_tf'])}, "
              f"indirimli {s(t['satis_ind'])}, karşılanmayan {s(t['karsilanmayan'])} (kalıcı {s(t['kalici_kayip'])}, "
              f"ikame {s(t['ikameye_giden'])}), pencere sonu kalan {s(t['kalan_son'])}")
        print("  milyon TL Δkâr: " + "; ".join(
            f"{KOL_ADI[k]}/{r} {mn(vb.oz[(k, r, G)]['d_kar'], 1)}" for k, r in oyun.kol_listesi(en) if (k, r) != ("rpt_yok", "a")))
        for kol, kural in FIFO_KOLLARI:
            ak = vb.akibet.get((kol, kural, G))
            if ak is None or ak.empty:
                continue
            print(f"  FIFO {KOL_ADI[kol]} / {kural}: {_fifo_satiri(ak)}")
            ek += fifo_denetimleri(ak, f"{kol}|{kural} {G}")
        kh = vb.oz[("kahin", en, G)]["d_kar"]
        print("  kâhinin Δkârının payı: " + "; ".join(
            f"{KOL_ADI[k]}/{r} {y(pay(vb.oz[(k, r, G)]['d_kar'], kh))}" for k, r in
            (("mevcut", "a"), ("mevcut", en), ("frr3", en), ("oneri", en), ("oneri_lojistik", en))))
        da = vb.oz[("mevcut", "a", G)]["d_kar"]
        db = vb.oz[("mevcut", en, G)]["d_kar"]
        do = vb.oz[("oneri", en, G)]["d_kar"]
        dag, kar = fark(da, db), fark(db, do)
        print(f"  ayrıştırma: dağıtımın payı (Banu'nun RPT'leri, a → {en}) {tl(dag)} ({mn(dag, 1)}); kararın payı "
              f"(Banu / {en} → öneri / {en}) {tl(kar)} ({mn(kar, 1)}); karar / dağıtım = {s(bolum(kar, dag), 2)}; "
              f"toplam (Banu / a → öneri / {en}) {tl(fark(da, do))} ({mn(fark(da, do), 1)})")
        o = vb.o[("oneri", en, G)]
        rs = o.loc[o["rpt"] == 0, "d_kar"]
        print(f"  RPT'siz option'lar (öneri / {en}): {s(len(rs))} option, Δkâr toplamı {tl(rs.sum())}, en büyük mutlak "
              f"{tl(rs.abs().max())}. v4'te talep fiyata bağlı ve ikame var: RPT'li bir option'ın bulunurluğu "
              f"komşu option'ların satışını değiştirir; RPT almayan option'ların kârı kollar arasında birebir aynı değil")
        for (k_, r_), kk in vb.K.items():
            ek += olcut_denetimleri(vb.o[(k_, r_, G)], vb.oz[(k_, r_, G)], f"{k_}|{r_} {G}")
        # Banu kolu (mevcut, a) yayımlanan dünyadır: RPT'leri yayımlanan RPT'lerle aynı
        yay = va.rpt_yay[va.rpt_yay["sezon_kodu"] == G]
        m = vb.o[("mevcut", "a", G)]
        ek.append((f"Banu / a {G}: RPT option ve adet = yayımlanan",
                   int((m["rpt"] > 0).sum()) == yay["option_id"].nunique() and int(m["rpt"].sum()) == int(yay["adet"].sum())))
        if G in va.akibet:
            ya, ka = va.akibet[G], vb.akibet[("mevcut", "a", G)]
            ek.append((f"Banu / a {G}: koşunun FIFO'su = yayımlanan tabloların FIFO'su",
                       all(int(ya[c].sum()) == int(ka[c].sum()) for c in
                           ("rpt_giren", "rpt_depoda_cikista", "rpt_cikisa_kadar", "rpt_outlete", "rpt_depoda_kalan"))))

    for ad_, oid_ in (("Hit", va.hik.hit_option), ("Geç gelen", va.hik.gec_option)):
        alt(f"{ad_} ({oid_}) kollara göre")
        _option_kollari(va, vb, oid_)


def _option_kollari(va, vb: VeriB, hit: str) -> None:
    en = vb.en_iyi
    for kol, kural in (("rpt_yok", "a"), ("mevcut", "a"), ("mevcut", en), ("frr3", en), ("oneri", en),
                       ("oneri_lojistik", en), ("kahin", "a"), ("kahin", en)):
        o = vb.o[(kol, kural, HIKAYE_SEZONU)].set_index("option_id").loc[hit]
        lan = pd.Timestamp(va.opt.set_index("option_id").loc[hit, "lansman_tarihi"])
        if o["rpt"] > 0:
            h_ = (pd.Timestamp(o["rpt_siparis_tarihi"]) - lan).days / 7
            ak = vb.akibet.get((kol, kural, HIKAYE_SEZONU))
            fifo = ""
            if ak is not None and hit in set(ak["option_id"]):
                a_ = ak.set_index("option_id").loc[hit]
                fifo = (f"; çıkışta depoda {s(a_['rpt_depoda_cikista'])}, outlet'e {s(a_['rpt_outlete'])}, mağazaya "
                        f"{s(a_['rpt_magazaya_alt'])}–{s(a_['rpt_magazaya_ust'])}")
            sip = (f"sipariş {t_(o['rpt_siparis_tarihi'])} ({s(h_)}. pazartesi) {s(o['rpt'])} adet, geldi "
                   f"{t_(o['rpt_teslim'])} (lansman + {s((pd.Timestamp(o['rpt_teslim']) - lan).days / 7, 1)} hafta){fifo}")
        else:
            sip = "RPT yok"
        print(f"  {KOL_ADI[kol] + ' / ' + kural:22s} {sip}; satış tf {s(o['satis_tf'])} ind {s(o['satis_ind'])}, "
              f"karşılanmayan {s(o['karsilanmayan'])} (tam fiyat döneminde {s(o['karsilanmayan_tf'])}), pencere sonu kalan "
              f"{s(o['kalan_son'])}, kâr {tl(o['kar'])}" + (f" (RPT yoka göre {tl(o['d_kar'])})" if "d_kar" in o else ""))


def _kollar_tablosu(vb: VeriB, G: str) -> None:
    print("  " + f"{'kol / kural':24s}" + "".join(f"{b:>13s}" for _, b, _ in KOLON))
    for kol, kural in oyun.kol_listesi(vb.en_iyi):
        r = vb.oz[(kol, kural, G)]
        hucre = []
        for k, _, od in KOLON:
            v = r.get(k, np.nan)
            hucre.append(f"{y(v, 1) if k == 'stoklu_pay_tf' else s(v, od):>13s}")
        print(f"  {KOL_ADI[kol] + ' / ' + kural:24s}" + "".join(hucre))
    print("  (boşa (son): pencere sonunda depoda + rafta kalan, en çok giren RPT kadar; yanlış alarm: RPT'li option'ın "
          "tam fiyat satışı tabana göre MOQ/2'den az arttı; kaçırılan: kâhinin RPT verip kâr ettiği, kolun RPT "
          "vermediği option)")


# ---------------------------------------------------------------------------
# YOLLAR (6. yazı: şans mı)
# ---------------------------------------------------------------------------

def yollar_bolumu(va, vb: VeriB, ek: list) -> None:
    baslik("YOLLAR (6. yazı) — Şans mı: aynı dünya, farklı müşteri akışı")
    Y = vb.yollar
    if Y is None:
        print("  cikti/yollar.json yok — önce: .venv/Scripts/python -m rpt.yollar")
        ek.append(("yollar.json var", False))
        return
    yl = Y["yollar"]
    en = Y["en_iyi"]
    print(f"  {s(len(yl))} yol; talep tohumu: yol 0 yayımlanan dünya, yol p > 0 {Y['taban']} + p "
          f"({', '.join(str(yl[k]['talep_tohumu']) for k in sorted(yl, key=int) if yl[k]['talep_tohumu'])}); "
          f"dünya ve operasyon aynı, yalnız müşteri akışı değişir")
    print(f"  dağıtım kuralı her yolda {en} (yol 0'ın {oyun.SECIM_SEZONU} seçimi; yollarda yeniden seçilmez); her yolda "
          f"öğrenme (eğri, belirsizlik, aday modeli) o yolun gerçekleşen tarihinden yeniden yapılır")
    for G in OYUN:
        n = [yl[k]["ogrenme"][G]["egitim_satir"] for k in yl]
        p = [yl[k]["ogrenme"][G]["egitim_pozitif"] for k in yl]
        sg = [yl[k]["ogrenme"][G]["sigma"]["3"] for k in yl]
        print(f"  {G} eğitimi yollar arasında: {s(min(n))}–{s(max(n))} satır, {s(min(p))}–{s(max(p))} pozitif; "
              f"σ (h=3) {s(min(sg), 3)}–{s(max(sg), 3)}")
    ciftler = [("mevcut|a", "Banu / a"), (f"mevcut|{en}", f"Banu / {en}"), (f"frr3|{en}", f"FRR h=3 / {en}"),
               (f"oneri|{en}", f"öneri / {en}"), (f"kahin|{en}", f"kâhin / {en}")]
    for G in OYUN:
        alt(f"{G}: rpt_yok'a göre, {s(len(yl))} yol (min · medyan · max)")
        for anahtar, ad in ciftler:
            d = np.array([yl[k]["sezon"][G][anahtar]["d_kar"] for k in yl])
            kk = np.array([yl[k]["sezon"][G][anahtar]["kurtarilan"] for k in yl])
            bo = np.array([yl[k]["sezon"][G][anahtar]["rpt_bosa"] for k in yl])
            ya = np.array([yl[k]["sezon"][G][anahtar]["yanlis_alarm"] for k in yl])
            print(f"  {ad:15s} Δkâr {tl(d.min())} · {tl(np.median(d))} · {tl(d.max())} ({mn(d.min(), 1)} · "
                  f"{mn(np.median(d), 1)} · {mn(d.max(), 1)}; pozitif {s((d > 0).sum())}/{s(len(d))}); kurtarılan "
                  f"{s(kk.min())} · {s(np.median(kk))} · {s(kk.max())}; boşa RPT {s(bo.min())} · {s(np.median(bo))} · "
                  f"{s(bo.max())}; yanlış alarm {s(ya.min())}–{s(ya.max())}")
        oz = Y["ozet"][G]
        print("  öneri önde (Δkâr, yol sayısı): " + "; ".join(
            f"{_ad(r.split('|', 1)[1])} karşısında {s(v['onde'])}/{s(v['yol'])}" for r, v in oz.items() if r.startswith("oneri_onde")))
        yollar_ = sorted(yl, key=int)
        print("  yol başına Δkâr (yol " + ", ".join(yollar_) + "):")
        for anahtar, ad in ciftler:
            print(f"    {ad:15s} " + " · ".join(tl(yl[k]["sezon"][G][anahtar]["d_kar"]) for k in yollar_))
        for a_, b_, ad in ((f"oneri|{en}", "mevcut|a", f"öneri / {en} − Banu / a"),
                           (f"mevcut|{en}", "mevcut|a", f"yalnız dağıtım (Banu / {en} − Banu / a)"),
                           (f"oneri|{en}", f"mevcut|{en}", f"yalnız karar (öneri / {en} − Banu / {en})")):
            f_ = np.array([fark(yl[k]["sezon"][G][b_]["d_kar"], yl[k]["sezon"][G][a_]["d_kar"]) for k in yollar_])
            print(f"  {ad}: medyan {tl(np.median(f_))} ({mn(np.median(f_), 1)}), en küçük {tl(f_.min())}, pozitif "
                  f"{s((f_ > 0).sum())}/{s(len(f_))}")
        # yol 0 = bu raporun oyun koşuları
        y0 = yl["0"]["sezon"][G]
        for anahtar in [c for c, _ in ciftler] + ["rpt_yok|a"]:
            kol, kural = anahtar.split("|")
            ek.append((f"yollar.json yol 0 {G} {anahtar} = oyun koşusu",
                       abs(y0[anahtar]["d_kar"] - vb.oz[(kol, kural, G)]["d_kar"]) < 1.0
                       and y0[anahtar]["kurtarilan"] == vb.oz[(kol, kural, G)].get("kurtarilan", 0.0)))
