"""Raporun Faz B bölümleri: ADAY (4. yazı), MİKTAR (5. yazı), SONUÇ (6. yazı).

`rapor.py` çağırır; tek başına da koşar:

    .venv/Scripts/python rapor_b.py

Yol 0 (gerçek v3 talebi) burada baştan koşulur (~2 dk). Alternatif yolların
aralıkları `cikti/yollar.json`'dan okunur (`python -m rpt.yollar` üretir);
dosya yoksa bölüm bunu söyler.
"""

import json
import sys
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from rapor import alt, baslik, s, t_, y
from rpt import aday, miktar, olcutler, oyun, yollar

warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*force_all_finite.*", category=FutureWarning)

HIKAYE = {"yerli": "MDL190-HAK", "uzak": "MDL169-EKR"}
KOL_ADI = {
    "rpt_yok": "rpt_yok", "mevcut": "mevcut (Banu)", "frr2": "frr, h=2", "frr3": "frr, h=3",
    "oneri": "oneri (LightGBM)", "oneri_lojistik": "oneri (lojistik)", "kahin": "kâhin",
}


@dataclass
class VeriB:
    H: dict
    K: dict

    @property
    def b(self):
        return self.H["baglam"]

    @property
    def w(self):
        return self.H["baglam"].dunya


def hazirla_b(talep=None) -> VeriB:
    from perakende_veri.v3.dunya import dunya_kur, talep_matrisi

    w = dunya_kur()
    H = oyun.hazirlik(w, talep if talep is not None else talep_matrisi(w))
    K = oyun.tum_kollar(H)
    return VeriB(H, K)


def _oid(v: VeriB, option_id: str) -> int:
    return int(np.flatnonzero(v.w.optionlar["option_id"].to_numpy() == option_id)[0])


def _tarih(v: VeriB, gun) -> str:
    return t_(v.w.takvim["tarih"].iloc[int(gun)]) if gun is not None and gun >= 0 else "—"


# ---------------------------------------------------------------------
# ADAY (4. yazı)
# ---------------------------------------------------------------------

def aday_bolumu(v: VeriB) -> None:
    baslik("ADAY (4. yazı) — hangi ürün RPT'ye aday")
    print("  Satır: Collection option'ı × karar pazartesisi h = 2…6, henüz RPT'si yokken.")
    print("  Etiket: 'bu pazartesi max(MOQ, newsvendor) RPT verilseydi, gelen adetlerden en az MOQ/2")
    print("  tam fiyattan satılır mıydı?' (i) gerçek talep ile, (ii) sonradan stoklu gün düzeltmeli")
    print("  talep ile. Modeller (ii) ile, oyun sezonundan önce kapanmış sezonlarda eğitilir.")
    print("  Sınama satırları rpt_yok kolundan (RPT'nin kendisi envanteri değiştirmesin diye).")
    for G in v.b.oyun_sezonlari:
        at = v.H["aday"][G]
        e, t = at["egitim"], at["sinama"]
        alt(f"{G} — eğitim {', '.join(sorted(set(v.w.optionlar['sezon_kodu'].to_numpy()[e['option']])))}"
            f" ({len(e)} satır, {e['option'].nunique()} option), sınama {G} ({len(t)} satır)")
        for ad, d in (("eğitim", e), ("sınama", t)):
            print(f"  {ad}: pozitif (ii) {int(d['etiket_duz'].sum())} ({y(d['etiket_duz'].mean())}), "
                  f"pozitif (i) {int(d['etiket_gercek'].sum())} ({y(d['etiket_gercek'].mean())}); "
                  f"(i) ile (ii) aynı {y((d['etiket_duz'] == d['etiket_gercek']).mean())}; "
                  f"(ii) pozitif, (i) negatif {int((d['etiket_duz'] & ~d['etiket_gercek']).sum())}, "
                  f"tersi {int((~d['etiket_duz'] & d['etiket_gercek']).sum())}")
        # Sınama satırları rpt_yok kolundan: gerçekleşen tarihten küçük farklar (açıklama aşağıda)
        oid_ = v.w.optionlar["option_id"].to_numpy()
        km = v.H["kayit_mevcut"]
        m = t[["option", "h", "x"]].merge(km[["option", "h", "x"]], on=["option", "h"], suffixes=("", "_g"))
        fark = (m["x"] - m["x_g"]).abs()
        print(f"  NOT: sınama satırlarının {int((fark > 0).sum())}/{len(m)}'inde bugüne kadarki satış gerçekleşen "
              f"tarihten farklı (en çok {s(fark.max())} adet). Neden: motorun operasyon rastgele akışı (iade ve "
              f"işlem indirimi) bütün hücrelerce paylaşılır; bir kolda herhangi bir hücrenin satışı değişince "
              f"(ör. önceki sezonun RPT'si) sonraki bütün çekilişler kayar.")
        if len(e) < 600:
            print(f"  NOT: {G} eğitimi küçük ({len(e)} satır, {int(e['etiket_duz'].sum())} pozitif) — "
                  f"sonuçlar kırılgan.")
        m = v.b.modeller[G]
        tahminler = {
            "Banu kuralı (STR ≥ %55)": aday.banu_kurali(t, v.w),
            "lojistik (p ≥ 0,5)": m.olasilik(t, "lojistik") >= 0.5,
            "LightGBM (p ≥ 0,5)": m.olasilik(t, "lgbm") >= 0.5,
            "[mükemmel: etiket (i)]": t["etiket_gercek"].to_numpy(bool),
        }
        print(f"  {'model':26s} {'alarm':>5s} {'TP':>3s} {'FP':>4s} {'FN':>3s} {'isabet':>7s} "
              f"{'duyarl.':>7s} {'yanlış alarm TL':>15s} {'kaçırma TL':>12s} | {'ilk alarm':>9s} "
              f"{'ilk alarm kârı TL':>17s}")
        for ad, tah in tahminler.items():
            r = aday.degerlendir(tah, t, "gercek")
            print(f"  {ad:26s} {r['tp'] + r['fp']:>5d} {r['tp']:>3d} {r['fp']:>4d} {r['fn']:>3d} "
                  f"{y(r['isabet'], 0):>7s} {y(r['duyarlilik'], 0):>7s} {s(r['yanlis_alarm_tl']):>15s} "
                  f"{s(r['kacirma_tl']):>12s} | {r['ilk_alarm_option']:>9d} {s(r['ilk_alarm_kar_tl']):>17s}")
        print("  (etiket (i) ile; TL = sonradan bakış kârı; ilk alarm: option'ın ilk alarmında sipariş "
              "verilseydi, en fazla bir RPT)")
    alt("Lojistik regresyon katsayıları (SS25 modeli, ölçeklenmiş özellikler)")
    kat = v.b.modeller["SS25"].katsayilar()
    for ad, k in kat.items():
        print(f"  {ad:20s} {s(k, 2):>6s}")
    alt("Eğitim satırlarında pozitiflerin menşeye ve haftaya dağılımı (SS25 eğitimi)")
    e = v.H["aday"]["SS25"]["egitim"]
    for (uzak, h), g in e.groupby(["uzak", "h"]):
        print(f"  {'Uzak Doğu' if uzak else 'Yerli':9s} h={int(h)}: {len(g):3d} satır, pozitif "
              f"{int(g['etiket_duz'].sum())}")


# ---------------------------------------------------------------------
# MİKTAR (5. yazı)
# ---------------------------------------------------------------------

def miktar_bolumu(v: VeriB) -> None:
    baslik("MİKTAR (5. yazı) — ne kadar, ne zaman")
    w = v.w
    opt = w.optionlar
    alt("Kestirim belirsizliği (d katmanı, log(gerçek/kestirim), geçmiş sezonlardan)")
    for G in v.b.oyun_sezonlari:
        bel = v.b.belirsizlik[G]
        print(f"  {G} ← {', '.join(bel.sezonlar)}: " + "; ".join(
            f"h={h}: μ {s(bel.mu[h], 3)}, σ {s(bel.sigma[h], 3)}" for h in sorted(bel.mu)))

    alt("Fiyat, maliyet, indirim fiyatı (Collection, oyun sezonları, option ortalaması)")
    mask = v.b.oyun_maskesi()
    p, c, pi = opt["liste_fiyati"].to_numpy()[mask], opt["alis_fiyati"].to_numpy()[mask], v.b.p_ind[mask]
    print(f"  liste {s(p.mean())} TL, alış {s(c.mean())} TL (liste/alış {s((p / c).mean(), 2)}), "
          f"indirim dönemi beklenen fiyat {s(pi.mean())} TL (listenin {y((pi / p).mean())})")
    print(f"  Cu = liste − alış ≈ {s((p - c).mean())} TL; Co = alış − indirim fiyatı ≈ {s((c - pi).mean())} TL "
          f"(indirimde satılırsa; negatifse indirimde satmak bile kârlı), hiç satılmazsa {s(c.mean())} TL")
    print(f"  kritik oran (yalnız tam fiyat vs hiç satılmaz): Cu/(Cu+c) = {y(((p - c) / p).mean())}")

    alt("Hikâye option'ları, h=3 pazartesisi: dört miktar")
    print("  (gerçekleşen tarihin h=3 sabahı — HİKÂYE/SANSÜR bölümleriyle aynı x, D, d)")
    kahin = v.K["rp"][("kahin", v.K["en_iyi"])]
    for etiket, oid in HIKAYE.items():
        o = _oid(v, oid)
        G = opt.at[o, "sezon_kodu"]
        # Gerçekleşen tarihin (Banu'nun gördüğü) h=3 sabahı; Faz A ile birebir
        km = v.H["kayit_mevcut"]
        km = km[(km["option"] == o) & (km["h"] == 3)]
        if km.empty:
            continue
        r = aday.ozellikler(km, w, v.b.egriler[G], v.b.belirsizlik[G], v.b.p_ind).iloc[0]
        e = v.b.egriler[G]
        dalga = int(opt.at[o, "dalga"])
        mu, sg = v.b.belirsizlik[G].al(3)
        nv = miktar.newsvendor(r["D"], 3, int(r["L"]), r["W"], e[("duzeltilmis", "indirim")],
                               e[("duzeltilmis", "cikis")], dalga, r["ip"], float(opt.at[o, "liste_fiyati"]),
                               float(opt.at[o, "alis_fiyati"]), float(v.b.p_ind[o]), mu, sg, int(r["moq"]))
        q_banu = miktar.banu(float(w.ilk_alim[o]), int(r["moq"]))
        q_frr = miktar.frr(r["x"], e[("ham", "indirim")].k((dalga,), 3), float(w.ilk_alim[o]), int(r["moq"]))
        plan = kahin.plan.get(o)
        print(f"  {oid} ({opt.at[o, 'mense']}, RPT {int(r['L'])} hf, MOQ {s(r['moq'])}, Q1 {s(w.ilk_alim[o])}):")
        print(f"    bugüne kadar x = {s(r['x'])}, D = {s(r['D'])}; d kestirimi {s(r['d_kestirim'])}; "
              f"envanter pozisyonu {s(r['ip'])} (depo {s(r['depo'])}, mağaza {s(r['magaza'])}, açık {s(r['acik'])})")
        print(f"    beklenen: geliş öncesi talep {s(nv['B'])}, gelişten indirime tam fiyat talep {s(nv['Xtf'])}, "
              f"indirim dönemi {s(nv['Xind'])}")
        print(f"    Banu %50: {s(q_banu)} · FRR: {s(q_frr)} · newsvendor: {s(nv['q'])} "
              f"(kapısız en iyi {s(nv['q_serbest'])}; beklenen tam fiyat satış {s(nv['beklenen_tf'])}, "
              f"indirimli {s(nv['beklenen_ind'])}, kâr {s(nv['beklenen_kar'])} TL)")
        if plan:
            print(f"    kâhin: {_tarih(v, plan[0])} (h={(plan[0] - opt.at[o, 'lansman_gun']) // 7}) {s(plan[1])} adet")
        else:
            print("    kâhin: RPT vermez")

    alt("Kollara göre RPT miktarı ve akıbeti (en iyi dağıtımla; yerli / Uzak Doğu)")
    en = v.K["en_iyi"]
    for G in v.b.oyun_sezonlari:
        ops = oyun.oyun_optionlari(w, G)
        taban = olcutler.option_olcutleri(w, v.K["ham"][("rpt_yok", "mevcut")], ops).set_index("option")
        print(f"  {G}:")
        for kol in ("mevcut", "frr2", "frr3", "oneri", "oneri_lojistik", "kahin"):
            k = olcutler.option_olcutleri(w, v.K["ham"][(kol, en)], ops).set_index("option")
            parca = []
            for m in ("Yerli", "Uzak Doğu"):
                km = k[(k["mense"] == m) & (k["rpt"] > 0)]
                tm = taban.loc[km.index]
                parca.append(f"{m} {len(km)} option / {s(km['rpt'].sum())} adet, ek tf {s((km['satis_tf'] - tm['satis_tf']).sum())}"
                             f", ek ind {s((km['satis_ind'] - tm['satis_ind']).sum())}, Δkâr {s((km['kar'] - tm['kar']).sum())}")
            print(f"    {KOL_ADI[kol]:18s} " + " | ".join(parca))

    alt("oneri kolunun kararları (h, olasılık, miktar), SS25")
    rp = v.K["rp"][("oneri", en)]
    for gun, o, q, bilgi in rp.kayit:
        if opt.at[o, "sezon_kodu"] != "SS25":
            continue
        print(f"  {opt.at[o, 'option_id']:12s} {opt.at[o, 'mense']:9s} h={int(bilgi['h'])} p={s(bilgi['p'], 2)} "
              f"{s(q):>6s} adet ({_tarih(v, gun)})")


# ---------------------------------------------------------------------
# SONUÇ (6. yazı)
# ---------------------------------------------------------------------

KOLON = [("rpt_option", "RPT opt", 0), ("rpt", "RPT adet", 0), ("rpt_magazaya", "mağazaya", 0),
         ("rpt_depoda_kalan", "depoda kalan", 0), ("rpt_indirimden_sonra", "geç gelen", 0),
         ("rpt_ek_tf", "ek tf satış", 0), ("rpt_ek_ind", "ek ind satış", 0),
         ("kurtarilan_kayip", "kurtarılan kayıp", 0), ("kurtarilan_kayip_tl", "kurtarılan TL", 0),
         ("delta_kar", "Δ brüt kâr TL", 0), ("yanlis_alarm", "yanlış alarm", 0),
         ("kacirilan", "kaçırılan", 0), ("magazaya", "mağazaya toplam", 0), ("stoklu_pay_tf", "stoklu pay", 3)]


def _kollar_tablosu(tab: pd.DataFrame, satirlar) -> None:
    print("  " + f"{'kol':26s}" + "".join(f"{b:>17s}" for _, b, _ in KOLON))
    for kol, kural in satirlar:
        r = tab[(tab["kol"] == kol) & (tab["kural"] == kural)]
        if r.empty:
            continue
        r = r.iloc[0]
        ad = f"{KOL_ADI[kol]} / {kural}"
        hucre = []
        for k, _, od in KOLON:
            val = r[k]
            hucre.append(f"{y(val, 1) if k == 'stoklu_pay_tf' else s(val, od):>17s}")
        print(f"  {ad:26s}" + "".join(hucre))


def sonuc_bolumu(v: VeriB) -> None:
    baslik("SONUÇ (6. yazı) — RPT geldi, mağazada satış sıfır")
    w = v.w
    opt = w.optionlar
    en = v.K["en_iyi"]
    alt("Dağıtım kuralının seçimi (oyundan önce, SS24'te; Banu'nun RPT'leri)")
    for r in v.K["secim"].itertuples(index=False):
        print(f"  {r.kural:7s} SS24 Collection kârı {s(r.kar)} TL, kayıp satış {s(r.kayip)}, "
              f"RPT mağazaya {s(r.rpt_magazaya)}, depoda kalan {s(r.rpt_depoda_kalan)}, tam fiyat satış {s(r.satis_tf)}")
    print(f"  seçilen kural: {en}  (b = stoklu gün hızı, c = yeniden lansman, d = c + %30 depoda tutma)")
    print("  Değerleme: gelir − (ilk alım + RPT) × alış; çıkışta kalan stok 0 TL. Taban: rpt_yok.")

    tablolar = {G: oyun.ozet_tablosu(w, v.K["ham"], G, ("kahin", en)) for G in v.b.oyun_sezonlari}
    for G, tab in tablolar.items():
        alt(f"Kollar — {G} (Collection, {len(oyun.oyun_optionlari(w, G))} option)")
        _kollar_tablosu(tab, oyun.kol_listesi(en))
        r0 = tab[(tab["kol"] == "rpt_yok")].iloc[0]
        print(f"  taban (rpt_yok): kâr {s(r0['kar'])} TL, tam fiyat satış {s(r0['satis_tf'])}, "
              f"kayıp {s(r0['kayip_tf'] + r0['kayip_ind'])} ({s(r0['kayip_tl'])} TL)")
        k = tab.set_index(["kol", "kural"])
        kahin = k.loc[("kahin", en), "delta_kar"]
        for kol in ("mevcut", "frr3", "oneri"):
            d = k.loc[(kol, en), "delta_kar"]
            print(f"  {KOL_ADI[kol]} / {en}: kâhinin Δkârının {y(d / kahin) if kahin else '—'}'i")
        ops = oyun.oyun_optionlari(w, G)
        tb = olcutler.option_olcutleri(w, v.K["ham"][("rpt_yok", "mevcut")], ops).set_index("option")
        kk = olcutler.option_olcutleri(w, v.K["ham"][("oneri", en)], ops).set_index("option")
        rptsiz = kk["rpt"] == 0
        gurultu = (kk["kar"] - tb["kar"])[rptsiz]
        print(f"  gürültü payı: oneri/{en} kolunda RPT'siz {int(rptsiz.sum())} option'ın Δkârı toplam "
              f"{s(gurultu.sum())} TL (en büyük mutlak {s(gurultu.abs().max())} TL) — ortak operasyon "
              f"akışının (iade, işlem indirimi) kaymasından; kol farklarının içindeki rastgele kısım")
        print(f"  dağıtımın payı (Banu'nun RPT'leri): mevcut→{en} Δkâr "
              f"{s(k.loc[('mevcut', en), 'delta_kar'] - k.loc[('mevcut', 'mevcut'), 'delta_kar'])} TL; "
              f"kararın payı: mevcut/{en} → oneri/{en} "
              f"{s(k.loc[('oneri', en), 'delta_kar'] - k.loc[('mevcut', en), 'delta_kar'])} TL")

    alt("Hikâye: MDL169-EKR'nin 750 adedi (Banu'nun RPT'si) her dağıtım kuralıyla")
    o = _oid(v, HIKAYE["uzak"])
    for kural in ("mevcut", "b", "c", "d"):
        r = olcutler.option_olcutleri(w, v.K["ham"][("mevcut", kural)], [o]).iloc[0]
        print(f"  {kural:7s} RPT {s(r['rpt'])} geldi {_tarih(v, r['rpt_gelis_gun'])}; mağazaya {s(r['rpt_magazaya'])}, "
              f"çıkışta depoda {s(r['rpt_depoda_kalan'])}; satış tf {s(r['satis_tf'])} ind {s(r['satis_ind'])}, "
              f"kayıp {s(r['kayip_tf'] + r['kayip_ind'])}, kâr {s(r['kar'])} TL")
    r = olcutler.option_olcutleri(w, v.K["ham"][("rpt_yok", "mevcut")], [o]).iloc[0]
    print(f"  rpt_yok satış tf {s(r['satis_tf'])} ind {s(r['satis_ind'])}, kayıp {s(r['kayip_tf'] + r['kayip_ind'])}, "
          f"kâr {s(r['kar'])} TL")

    alt("Hikâye: MDL190-HAK kollara göre")
    o = _oid(v, HIKAYE["yerli"])
    for kol, kural in (("rpt_yok", "mevcut"), ("mevcut", "mevcut"), ("mevcut", en), ("frr3", en),
                       ("oneri", en), ("kahin", en)):
        r = olcutler.option_olcutleri(w, v.K["ham"][(kol, kural)], [o]).iloc[0]
        siparis = (f"sipariş {_tarih(v, r['rpt_gun'])} (h={(r['rpt_gun'] - opt.at[o, 'lansman_gun']) // 7}) "
                   f"{s(r['rpt'])} adet, geliş {_tarih(v, r['rpt_gelis_gun'])}; mağazaya {s(r['rpt_magazaya'])}, "
                   f"depoda {s(r['rpt_depoda_kalan'])}" if r["rpt"] > 0 else "RPT yok")
        print(f"  {KOL_ADI[kol] + ' / ' + kural:26s} {siparis}; satış tf {s(r['satis_tf'])} ind {s(r['satis_ind'])}, "
              f"kayıp {s(r['kayip_tf'] + r['kayip_ind'])}, kâr {s(r['kar'])} TL")

    alt("Alternatif talep yolları (aynı beklenen talep, farklı tohum)")
    if not yollar.CIKTI.exists():
        print("  cikti/yollar.json yok — önce: .venv/Scripts/python -m rpt.yollar")
        return
    Y = json.loads(yollar.CIKTI.read_text(encoding="utf-8"))
    print(f"  {len(Y)} yol; seçilen dağıtım kuralı: " + ", ".join(
        f"{k}: {n}" for k, n in pd.Series([y_["en_iyi"] for y_ in Y.values()]).value_counts().items()))
    for G in v.b.oyun_sezonlari:
        print(f"  {G}:")
        for anahtar, ad in (("mevcut|mevcut", "mevcut / mevcut"), ("mevcut|en_iyi", "mevcut / en iyi"),
                            ("frr3|mevcut", "frr h=3 / mevcut"), ("frr3|en_iyi", "frr h=3 / en iyi"),
                            ("oneri|en_iyi", "oneri / en iyi"), ("kahin|en_iyi", "kâhin / en iyi")):
            d = np.array([y_["sezon"][G][anahtar]["delta_kar"] for y_ in Y.values() if anahtar in y_["sezon"][G]])
            kk = np.array([y_["sezon"][G][anahtar]["kurtarilan_kayip"] for y_ in Y.values()
                           if anahtar in y_["sezon"][G]])
            if not len(d):
                continue
            print(f"    {ad:18s} Δkâr min {s(d.min())} · medyan {s(np.median(d))} · max {s(d.max())} TL "
                  f"(pozitif {int((d > 0).sum())}/{len(d)}); kurtarılan kayıp medyan {s(np.median(kk))}")
        fark = [y_["sezon"][G]["oneri|en_iyi"]["delta_kar"] - y_["sezon"][G]["mevcut|mevcut"]["delta_kar"]
                for y_ in Y.values()]
        fark_d = [y_["sezon"][G]["mevcut|en_iyi"]["delta_kar"] - y_["sezon"][G]["mevcut|mevcut"]["delta_kar"]
                  for y_ in Y.values()]
        print(f"    oneri/en iyi − mevcut/mevcut: medyan {s(np.median(fark))} TL, aynı yön "
              f"{int((np.array(fark) > 0).sum())}/{len(fark)}; yalnız dağıtım (Banu'nun RPT'leri): medyan "
              f"{s(np.median(fark_d))} TL, {int((np.array(fark_d) > 0).sum())}/{len(fark_d)}")


def turetilmis_bolumu(v: VeriB, v_a=None) -> None:
    """Yazılarda elle türetilen sayılar (kural: yayımlanan her sayı rapordan)."""
    from rpt import hikaye, sansur

    baslik("YAZI TÜRETİLMİŞLERİ — yazılarda kullanılan türetilmiş sayılar")
    w = v.w
    opt = w.optionlar
    if v_a is not None:
        oid = HIKAYE["yerli"]
        o = v_a.opt.set_index("option_id").loc[oid]
        p = v_a.panel[v_a.panel["option_id"] == oid].set_index("h")
        k67 = p.loc[[6, 7], "kayip"]
        print(f"  (1) {oid} h=6 + h=7 kayıp satış [gerçek]: {s(k67.iloc[0])} + {s(k67.iloc[1])} = {s(k67.sum())}")
        r = hikaye.rpt_siparisleri(v_a.t, v_a.opt)
        rpt = int(r.loc[r["option_id"] == oid, "adet"].sum())
        print(f"  (2) {oid} Q1 + Banu RPT: {s(o['ilk_alim'])} + {s(rpt)} = {s(o['ilk_alim'] + rpt)}")
        bitti = int(hikaye.bitis_haftasi(v_a.panel, v_a.opt)[oid])
        mt = hikaye.magaza_tablosu(v_a.t, v_a.hh, oid, bitti).set_index("ad")
        akm = mt.loc[[a for a in mt.index if "Akmerkez" in a][0], "satis"]
        bag = mt.loc[[a for a in mt.index if "Bağdat" in a][0], "satis"]
        print(f"  (3) h={bitti} mağaza tablosu: İstanbul Akmerkez satış ÷ İstanbul Bağdat Caddesi satış = "
              f"{s(akm)} / {s(bag)} = {s(akm / bag, 1)}")
        x3 = p.loc[p.index < 3, "satis"].sum()
        print(f"  (4) {oid} h=3'e kadar satış ÷ Q1 = {s(x3)} / {s(o['ilk_alim'])} = {y(x3 / o['ilk_alim'])}")
        c = v_a.hh[(v_a.hh["option_id"] == oid) & (v_a.hh["h"] < 3)]
        k = sansur.duzeltilmis_talep(c, 3).iloc[0]
        ham, duz, gercek = k["x"] / 3, k["D"] / 3, (c["satis"].sum() + c["kayip"].sum()) / 3
        print(f"  (5) h=3 stoklu gün düzeltmesinin kapattığı ham→gerçek haftalık açığın payı: "
              f"({s(duz, 1)} − {s(ham, 1)}) / ({s(gercek, 1)} − {s(ham, 1)}) = {y((duz - ham) / (gercek - ham), 0)}")
        tab = v_a.hata["SS25"].set_index(["kesit", "katman", "h"])
        d2, p2 = tab.loc[("tümü", "d", 2), "wape"], tab.loc[("tümü", "plan", 2), "wape"]
        print(f"  (6) SS25 h=2: d katmanı WAPE ÷ plan WAPE = {y(d2)} / {y(p2)} = {s(d2 / p2, 2)}")
    else:
        print("  (1)–(6) Faz A verisi gerekir: rapor.py üzerinden koşun.")

    en = v.K["en_iyi"]
    print(f"  (7) Banu'nun RPT'leri menşeye göre, dağıtım {en} (AW24 + SS25):")
    top = {}
    for G in v.b.oyun_sezonlari:
        ops = oyun.oyun_optionlari(w, G)
        taban = olcutler.option_olcutleri(w, v.K["ham"][("rpt_yok", "mevcut")], ops).set_index("option")
        k = olcutler.option_olcutleri(w, v.K["ham"][("mevcut", en)], ops).set_index("option")
        for m in ("Yerli", "Uzak Doğu"):
            km = k[(k["mense"] == m) & (k["rpt"] > 0)]
            tm = taban.loc[km.index]
            dk, dtf = (km["kar"] - tm["kar"]).sum(), (km["satis_tf"] - tm["satis_tf"]).sum()
            a = top.setdefault(m, [0, 0.0, 0.0, 0])
            a[0] += len(km); a[1] += dk; a[2] += dtf; a[3] += km["rpt"].sum()
            print(f"      {G} {m:9s}: {len(km)} option, {s(km['rpt'].sum())} adet, Δkâr {s(dk)} TL, "
                  f"ek tam fiyat satış {s(dtf)}")
    for m, (n, dk, dtf, adet) in top.items():
        print(f"      toplam {m:9s}: {n} option, {s(adet)} adet, Δkâr {s(dk)} TL, ek tam fiyat satış {s(dtf)}")
    print("  (8) Collection kâr tabanı (rpt_yok) ve Banu'nun Δkârı:")
    for G in v.b.oyun_sezonlari:
        tab = oyun.ozet_tablosu(w, {k_: v.K["ham"][k_] for k_ in
                                    [("rpt_yok", "mevcut"), ("mevcut", "mevcut"), ("mevcut", en)]}, G, None)
        t = tab.set_index(["kol", "kural"])
        taban = t.loc[("rpt_yok", "mevcut"), "kar"]
        for kural in ("mevcut", en):
            dk = t.loc[("mevcut", kural), "delta_kar"]
            print(f"      {G}: taban {s(taban)} TL; Banu / {kural} Δkâr {s(dk)} TL = tabanın {y(dk / taban)}")


def faz_b(v_a=None) -> VeriB:
    v = hazirla_b()
    aday_bolumu(v)
    miktar_bolumu(v)
    sonuc_bolumu(v)
    turetilmis_bolumu(v, v_a)
    return v


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    faz_b()
