"""RPT dizisinin iki sahnesi: hikâye seçimi (spec §6).

`python -m rpt.hikaye_sec [--hikaye HIT_OPTION:GEC_OPTION] [--adaylar]` iki sahneyi ve
yazıların alıntılayabileceği bütün sayıları basar. Sahneler varsayılan olarak
`YURUTUCU_SECIMI`'dir (aşağıda); ölçüt merdiveni seçimin hangi ölçütleri tutmadığını
(`gevseyen`) hesaplar ve `--adaylar` ile en yakın sahneleri listeler.

İKİ SAHNE (sezon SS25, Collection; hikâye pazartesisi h = 3).

  hit      Beklenenden hızlı satan, yerli tedarikçili ürün. Banu'nun kuralı hikâye
           pazartesisinde (lansmandan 3. pazartesi) tetikleniyor: zincir STR'si ≥ %55.
           Birkaç mağazada o üç haftada stoksuz günler var. Yazıların 1.–5. sahnesi.
  geç gelen
           Uzak Doğu tedarikçili bir ürün; Lumoda'nın (Banu'nun kuralının) yayımlanan
           RPT'si indirimden kısa süre önce depoya giriyor ve mağazada satmıyor. 6. yazının
           sahnesi (hit'teki gibi kural lansmandan 3. pazartesi tetiklenmiş).

Ölçütler (bayrak adlarıyla; gevşetme sırası "gevşer" sütununda):

  hit        yerli          tedarikçi menşei Yerli (RPT süresi kısa)              (gevşemez)
             banu_h         kural h = 3'te tetikleniyor (tablodan; `aday.banu_kurali`) (gevşemez)
             dalga3         3. dalga                                              1. gevşer
             stoksuz        ≥ 3 mağazada, ≥ 3 stoksuz gün (üç hafta, beden ort.)  2. gevşer
  geç gelen  uzak_dogu      menşe Uzak Doğu                                       (gevşemez)
             banu_rpt       yayımlanmış Lumoda RPT'si var                         (gevşemez)
             gelis          RPT indirimden 7–28 gün önce depoya girmiş            1. gevşer
             bos            geldiği hafta taşıyan mağazaların ≥ %67'si boş        2. gevşer
             depoda         RPT'nin ≥ %75'i çıkış sabahı hâlâ depoda (FIFO)       3. gevşer
             banu_h         RPT hit'teki gibi 3. pazartesi (h = 3) verilmiş       4. gevşer

Gevşetme (blok-transfer `hikaye_sec` kalıbı): sıkı aramada aday yoksa TEK ölçüt (gevşetme
sırasıyla), sonra ikili, üçlü… kümeler. Aday veren ilk küme seçilir; `gevseyen` adayın
gerçekte tutmadığı ölçütlerdir. Hiçbiri vermezse `LookupError` (huni basılır). Gevşemezler
hikâyenin kendisidir; sezon (SS25) ve hat (Collection) havuzu belirler, gevşemez.

Sıra: hit — stoksuz mağaza sayısı, sonra ilk alıma satış oranı; geç gelen — RPT'nin geliş
gününün hedeften (indirime 14 gün) uzaklığı, sonra boş mağaza payı. Eşitlikte option_id.

`--hikaye HIT_OPTION:GEC_OPTION` seçimi geçersiz kılar; `gevseyen` o adayların tutmadığı
bütün ölçütleri (gevşemezler dahil) listeler.

Bu modül gizli gerçeğe (üreteç, hakem, motor) dokunmaz: yalnız yayımlanan v4 tablolarını
ve `aday` / `hikaye` / `kaynak` kurucularını kullanır. Gerçek talep rapora (Görev 10) kalır.
Plan (`plan_sezon`) yayımlanmaz, motordan gelir: `ozet(..., plan=)` verilirse basılır.
"""

import argparse
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import pandas as pd

from . import aday, hikaye, kaynak, miktar

SEZON = "SS25"
HAT = "Collection"
HIKAYE_HAFTASI = 3                 # hikâye pazartesisi: lansmandan 3. pazartesi (h)
STOKSUZ_GUN_ESIGI = 3              # mağaza "stoksuz günlü": üç haftada ≥ 3 stoksuz gün (beden ort.)
STOKSUZ_MAGAZA_MIN = 3             # hit: stoksuz günlü mağaza sayısı ≥ 3 ("birkaç")
GELIS_ARALIGI = (7, 28)            # geç gelen: RPT geliş günü indirime 7–28 gün kala
GELIS_HEDEF = 14                   # sıralamada hedef: indirime iki hafta kala (v3 sahnesi)
BOS_PAY_ESIGI = 2 / 3              # geç gelen: geldiği hafta taşıyan mağazaların ≥ %67'si boş
DEPODA_PAY_ESIGI = 0.75            # geç gelen: RPT'nin ≥ %75'i çıkış sabahı depoda
SATISSIZ_GUN = 28                  # replenishment kuralının baktığı pencere (a kuralı)

HIT_OLCUTLERI = ("yerli", "banu_h", "dalga3", "stoksuz")
HIT_GEVSEK = ("dalga3", "stoksuz")                                  # gevşetme sırası
GEC_OLCUTLERI = ("uzak_dogu", "banu_rpt", "gelis", "bos", "depoda", "banu_h")
GEC_GEVSEK = ("gelis", "bos", "depoda", "banu_h")

# Yürütücünün seçimi (2026-10-10; kullanıcı yetki verdi, okuma kapısında sunulur).
# (hit option_id, geç gelen option_id). Gerekçe: görev raporu (task-9-report.md).
YURUTUCU_SECIMI = ("MDL0548-LCV", "MDL0609-GRM")


@dataclass
class Hikaye:
    hit_option: str
    hit_tedarikci: str
    gec_option: str
    gec_tedarikci: str
    magazalar: dict[str, list[str]]          # {"hit": [...], "gec": [...]}: yazıda anılacak mağaza_id'ler
    gevseyen: dict[str, list[str]]           # {"hit": [...], "gec": [...]}: tutmayan ölçütler


# ------------------------------------------------------------- özellikler (toplayıcı)


def gelis_durumu(t: dict, hh: pd.DataFrame, rpt: pd.DataFrame) -> pd.DataFrame:
    """RPT geldiği hafta, (option, taşıyan mağaza) başına durum.

    rpt: option_id, gelis (RPT'nin depoya girdiği gün). Taşıyan = option'ın ilk
    dağıtımından mal almış fiziksel mağaza. Geliş gününün pazartesi sabahı fotoğrafı
    (gelişten önceki ya da o günkü pazartesi): stok, `bos` (stok = 0); o pazartesiden
    önceki 28 günün satışı (`satis_28`), `satissiz` (bos ve satış 0: replenishment'ın
    "son dört haftada satış sıfır" kuralı bu mağazaya mal göndermezdi) ve lansmandan o
    pazartesiye satış."""
    o = rpt[["option_id", "gelis"]].dropna().drop_duplicates("option_id").copy()
    o["pzt"] = o["gelis"].dt.normalize() - pd.to_timedelta(o["gelis"].dt.dayofweek, unit="D")
    tas = hh[hh["ilk_dagitim"] > 0][["option_id", "magaza_id"]].drop_duplicates()
    tas = tas.merge(o[["option_id", "pzt"]], on="option_id")
    urun = t["urun"][["urun_id", "option_id"]]
    urun = urun[urun["option_id"].isin(o["option_id"])]
    st = t["stok"].merge(urun, on="urun_id").merge(o[["option_id", "pzt"]], on="option_id")
    st = st[st["tarih"] == st["pzt"]].groupby(["option_id", "magaza_id"])["adet"].sum().rename("stok")
    sa = t["satis"].merge(urun, on="urun_id").merge(o[["option_id", "pzt"]], on="option_id")
    sa = sa[(sa["adet"] > 0) & (sa["magaza_id"].astype(str) != kaynak.ONLINE) & (sa["tarih"] < sa["pzt"])]
    son28 = sa[sa["tarih"] >= sa["pzt"] - pd.Timedelta(days=SATISSIZ_GUN)]
    tas = tas.merge(st.reset_index(), on=["option_id", "magaza_id"], how="left")
    tas = tas.merge(son28.groupby(["option_id", "magaza_id"])["adet"].sum().rename("satis_28").reset_index(),
                    on=["option_id", "magaza_id"], how="left")
    tas = tas.merge(sa.groupby(["option_id", "magaza_id"])["adet"].sum().rename("satis_toplam").reset_index(),
                    on=["option_id", "magaza_id"], how="left")
    for k in ("stok", "satis_28", "satis_toplam"):
        tas[k] = tas[k].fillna(0).astype(int)
    tas["bos"] = tas["stok"] == 0
    tas["satissiz"] = tas["bos"] & (tas["satis_28"] == 0)
    return tas


def ozellikler(t: dict, opt: pd.DataFrame, hh: pd.DataFrame, sezon: str = SEZON,
               h: int = HIKAYE_HAFTASI) -> pd.DataFrame:
    """Sezonun Collection option'ları için ölçüt girdileri (option başına bir satır).

    Karar anı durumu (STR, gönderilen, satılan) `aday.durum_tablodan` ile h. pazartesi
    sabahı, kırpılmış tablolardan; "kural h'de tetikleniyor" `aday.banu_kurali` ile aynı
    tanımdan. Yayımlanan RPT (Lumoda'nın) ve akıbeti `hikaye.rpt_siparisleri /
    rpt_akibeti`'nden; geldiği haftanın mağaza durumu `gelis_durumu`ndan."""
    o = opt[(opt["sezon_kodu"] == sezon) & (opt["line"] == HAT)].copy().reset_index(drop=True)
    if o.empty:
        raise ValueError(f"ozellikler: {sezon} {HAT} option'ı yok")
    # --- h. pazartesi sabahı zincir durumu (dalga başına lansman günü farklı)
    parca = []
    for _, g in o.groupby("lansman_tarihi"):
        k = pd.Timestamp(g["lansman_tarihi"].iloc[0]) + pd.Timedelta(days=7 * h)
        parca.append(aday.durum_tablodan(t, k, g["option_id"]))
    d = pd.concat(parca, ignore_index=True)
    d = d.rename(columns={"str": "str_h", "satilan": "satilan_h", "gonderilen": "gonderilen_h",
                          "depo": "depo_h", "magaza": "magaza_h", "stoklu_magaza_payi": "stoklu_pay_h",
                          "kirik_magaza_payi": "kirik_pay_h"})
    o = o.merge(d[["option_id", "str_h", "satilan_h", "gonderilen_h", "depo_h", "magaza_h",
                   "stoklu_pay_h", "kirik_pay_h", "rpt_sayisi"]], on="option_id", how="left")
    kural = o.assign(h=h, str=o["str_h"], gonderilen=o["gonderilen_h"], L=o["rpt_hafta"])
    o["banu_h"] = aday.banu_kurali(kural)
    o["satis_ilk_alim"] = o["satilan_h"] / o["ilk_alim"].clip(lower=1)
    # --- mağaza stoksuz günleri (ilk h hafta; ilk dağıtımdan mal almış mağazalar)
    c = hh[(hh["h"] < h) & (hh["ilk_dagitim"] > 0)]
    hucre = c.groupby(["option_id", "magaza_id", "urun_id"]).agg(
        stoklu=("stoklu_gun", "sum"), acik=("acik_gun", "sum"))
    m = hucre.groupby(["option_id", "magaza_id"]).mean()
    m["stoksuz"] = m["acik"] - m["stoklu"]
    ms = m.reset_index().groupby("option_id").agg(
        tasiyan_magaza=("magaza_id", "nunique"),
        stoksuz_magaza=("stoksuz", lambda s: int((s >= STOKSUZ_GUN_ESIGI).sum())),
        stoksuz_en_cok=("stoksuz", "max"))
    o = o.merge(ms, left_on="option_id", right_index=True, how="left")
    for k in ("tasiyan_magaza", "stoksuz_magaza"):
        o[k] = o[k].fillna(0).astype(int)
    # --- Lumoda'nın yayımlanan RPT'si ve akıbeti
    r = hikaye.rpt_siparisleri(t, opt)
    r = r[r["sezon_kodu"] == sezon][["option_id", "adet", "red", "giren", "siparis_tarihi", "siparis_h",
                                     "planlanan_teslim", "gerceklesen_teslim", "gelis_h",
                                     "indirime_kalan_gun"]].rename(columns={
        "adet": "rpt", "siparis_tarihi": "rpt_siparis", "siparis_h": "rpt_h",
        "gerceklesen_teslim": "rpt_teslim", "planlanan_teslim": "rpt_planlanan",
        "gelis_h": "rpt_gelis_h", "indirime_kalan_gun": "rpt_gelis_gun", "red": "rpt_red",
        "giren": "rpt_giren"})
    o = o.merge(r, on="option_id", how="left")
    o["banu_rpt"] = o["rpt"].notna()
    ak = hikaye.rpt_akibeti(t, opt, sezon)[["option_id", "gelis", "depo_cikista", "rpt_depoda_cikista",
                                            "rpt_cikisa_kadar", "rpt_outlete", "rpt_depoda_kalan",
                                            "depo_son"]]
    o = o.merge(ak, on="option_id", how="left")
    o["depoda_pay"] = o["rpt_depoda_cikista"] / o["rpt_giren"].where(o["rpt_giren"] > 0)
    # --- geldiği hafta mağaza durumu
    gd = gelis_durumu(t, hh, o.loc[o["banu_rpt"], ["option_id", "gelis"]])
    gs = gd.groupby("option_id").agg(gelis_tasiyan=("magaza_id", "nunique"), gelis_bos=("bos", "sum"),
                                     gelis_satissiz=("satissiz", "sum"))
    o = o.merge(gs, left_on="option_id", right_index=True, how="left")
    o["bos_pay"] = o["gelis_bos"] / o["gelis_tasiyan"].where(o["gelis_tasiyan"] > 0)
    return o


# ------------------------------------------------------------- saf ölçüt mantığı


def hit_bayraklari(f: pd.DataFrame) -> pd.DataFrame:
    """Hit ölçüt bayrakları (bool, `HIT_OLCUTLERI` sütunları; f ile aynı indeks)."""
    return pd.DataFrame({
        "yerli": f["mense"] == "Yerli",
        "banu_h": f["banu_h"].astype(bool),
        "dalga3": f["dalga"] == 3,
        "stoksuz": f["stoksuz_magaza"] >= STOKSUZ_MAGAZA_MIN,
    }, index=f.index)[list(HIT_OLCUTLERI)]


def gec_bayraklari(f: pd.DataFrame) -> pd.DataFrame:
    """Geç gelen ölçüt bayrakları (bool, `GEC_OLCUTLERI` sütunları)."""
    lo, hi = GELIS_ARALIGI
    return pd.DataFrame({
        "uzak_dogu": f["mense"] == "Uzak Doğu",
        "banu_rpt": f["banu_rpt"].astype(bool),
        "gelis": f["rpt_gelis_gun"].between(lo, hi),
        "bos": f["bos_pay"] >= BOS_PAY_ESIGI,
        "depoda": f["depoda_pay"] >= DEPODA_PAY_ESIGI,
        "banu_h": f["banu_h"].astype(bool),
    }, index=f.index)[list(GEC_OLCUTLERI)].fillna(False).astype(bool)


def hit_sirasi(f: pd.DataFrame) -> pd.DataFrame:
    """Hit sıralaması: stoksuz mağaza çok, ilk alıma satış oranı yüksek, option_id."""
    return f.sort_values(["stoksuz_magaza", "satis_ilk_alim", "option_id"],
                         ascending=[False, False, True], kind="stable")


def gec_sirasi(f: pd.DataFrame) -> pd.DataFrame:
    """Geç gelen sıralaması: geliş günü hedefe (14 gün) yakın, boş mağaza payı yüksek, option_id."""
    f = f.assign(_uzak=(f["rpt_gelis_gun"] - GELIS_HEDEF).abs(), _bos=-f["bos_pay"].fillna(0))
    return f.sort_values(["_uzak", "_bos", "option_id"], kind="stable").drop(columns=["_uzak", "_bos"])


def huni(bayrak: pd.DataFrame) -> list[tuple[str, int]]:
    """Ölçütleri sütun sırasıyla ardışık uygulayınca kalan aday sayısı."""
    kalan = pd.Series(True, index=bayrak.index)
    sayi = [("havuz", int(len(bayrak)))]
    for c in bayrak.columns:
        kalan &= bayrak[c]
        sayi.append((c, int(kalan.sum())))
    return sayi


def merdiven(f: pd.DataFrame, bayrak: pd.DataFrame, gevsek: tuple[str, ...], sirala) -> tuple[pd.DataFrame, list[str]]:
    """Ölçüt merdiveni: aday veren ilk gevşetme kümesinin adayları (sıralı) ve gevşeyenler.

    Kümeler: boş (sıkı), sonra `gevsek` sırasıyla tekli, ikili, üçlü… Gevşemeyen ölçütlerin
    hepsi her kümede aranır. `gevseyen` seçilen (ilk sıradaki) adayın tutmadığı ölçütlerdir.
    Hiçbir küme aday vermezse LookupError (huni mesajda)."""
    gevsek = tuple(gevsek)
    sabit = [c for c in bayrak.columns if c not in gevsek]
    for boyut in range(len(gevsek) + 1):
        for kume in combinations(gevsek, boyut):
            gerek = sabit + [c for c in gevsek if c not in kume]
            maske = bayrak[gerek].all(axis=1)
            if maske.any():
                aday_ = sirala(f[maske])
                ilk = aday_.index[0]
                return aday_, [c for c in bayrak.columns if not bayrak.loc[ilk, c]]
    raise LookupError("hikaye bulunamadı; ardışık huni: " + ", ".join(f"{a} {n}" for a, n in huni(bayrak)))


def en_yakin(f: pd.DataFrame, bayrak: pd.DataFrame, sirala, n: int = 8) -> pd.DataFrame:
    """Tutmayan ölçüt sayısı az olandan başlayarak en yakın `n` aday (`--adaylar`)."""
    d = sirala(f).assign(tutmayan=lambda x: (~bayrak.loc[x.index]).sum(axis=1),
                         gevseyen=lambda x: [", ".join(c for c in bayrak.columns if not bayrak.loc[i, c])
                                             for i in x.index])
    return d.sort_values("tutmayan", kind="stable").head(n)


def secim_ayristir(metin: str) -> tuple[str, str]:
    """`HIT_OPTION:GEC_OPTION` → (hit, geç gelen)."""
    parca = metin.split(":")
    if len(parca) != 2 or not all(parca):
        raise ValueError(f"--hikaye HIT_OPTION:GEC_OPTION biçiminde olmalı, verilen: {metin!r}")
    return parca[0], parca[1]


def _satir(f: pd.DataFrame, option_id: str, ad: str) -> pd.Series:
    s = f[f["option_id"] == option_id]
    if s.empty:
        raise LookupError(f"{ad} option'ı havuzda yok: {option_id} (havuz: {SEZON} {HAT})")
    return s.iloc[0]


def sec_ozellikten(f: pd.DataFrame, secim: tuple[str, str] | None = None) -> dict:
    """Saf seçim: özellik tablosundan iki sahne.

    secim verilirse (hit, geç gelen) o ikili; gevseyen, adayın tutmadığı BÜTÜN ölçütlerdir.
    Verilmezse merdivenin ilk sırası. Döner: {"hit": satır, "gec": satır, "gevseyen":
    {"hit": [...], "gec": [...]}, "merdiven": {...ilk sıralar}}."""
    hb, gb = hit_bayraklari(f), gec_bayraklari(f)
    sonuc = {"merdiven": {"hit": None, "gec": None}}
    try:
        hadaylar, hgev = merdiven(f, hb, HIT_GEVSEK, hit_sirasi)
        sonuc["merdiven"]["hit"] = hadaylar.iloc[0]["option_id"]
    except LookupError:
        if secim is None:
            raise
    try:
        gadaylar, ggev = merdiven(f, gb, GEC_GEVSEK, gec_sirasi)
        sonuc["merdiven"]["gec"] = gadaylar.iloc[0]["option_id"]
    except LookupError:
        if secim is None:
            raise
    if secim is None:
        hit, gec = hadaylar.iloc[0], gadaylar.iloc[0]
        hg, gg = hgev, ggev
    else:
        hit, gec = _satir(f, secim[0], "hit"), _satir(f, secim[1], "geç gelen")
        hg = [c for c in hb.columns if not hb.loc[hit.name, c]]
        gg = [c for c in gb.columns if not gb.loc[gec.name, c]]
    sonuc.update(hit=hit, gec=gec, gevseyen={"hit": hg, "gec": gg})
    if hit["option_id"] == gec["option_id"]:
        raise ValueError(f"hit ve geç gelen aynı option olamaz: {hit['option_id']}")
    return sonuc


# ------------------------------------------------------------- mağazalar ve sec


def hit_magazalari(t: dict, hh: pd.DataFrame, option_id: str, h: int = HIKAYE_HAFTASI,
                   n_satis: int = 4) -> list[str]:
    """Hit sahnesinde anılacak mağazalar: h. pazartesiye dek en çok satan `n_satis` mağaza +
    ilk 15 satıcı içinde en çok stoksuz günü olan (zaten listede değilse). Satış sırasıyla."""
    tablo = hikaye.magaza_tablosu(t, hh, option_id, h)
    sec_ = list(tablo["magaza_id"].head(n_satis))
    ilk = tablo.head(15)
    if not ilk.empty:
        sec_.append(ilk.sort_values(["stoksuz_gun_ort", "satis"], ascending=[False, False])
                    .iloc[0]["magaza_id"])
    sirali = dict.fromkeys(tablo["magaza_id"])
    return [m for m in sirali if m in set(sec_)]


def gec_magazalari(t: dict, hh: pd.DataFrame, f_satir: pd.Series, n: int = 4) -> list[str]:
    """Geç gelen sahnesinde anılacak mağazalar: RPT geldiği hafta boş olup lansmandan beri en
    çok satmış `n` mağaza (satış sırasıyla): "mal geldi, ürünün en çok satıldığı mağaza boş"."""
    g = gelis_durumu(t, hh, pd.DataFrame({"option_id": [f_satir["option_id"]], "gelis": [f_satir["gelis"]]}))
    g = g[g["bos"]].sort_values(["satis_toplam", "magaza_id"], ascending=[False, True])
    return list(g["magaza_id"].head(n))


def sec(t: dict, opt: pd.DataFrame, hh: pd.DataFrame, zorla: tuple[str, str] | None = None,
        sezon: str = SEZON, f: pd.DataFrame | None = None) -> Hikaye:
    """Sahneleri seçer. `zorla` (hit, geç gelen) verilmezse `YURUTUCU_SECIMI`.

    f verilmezse `ozellikler`den kurulur. Seçim merdivenin ilk sırası değilse ya da
    ölçütleri tutmuyorsa `gevseyen` bunu söyler."""
    if f is None:
        f = ozellikler(t, opt, hh, sezon)
    s = sec_ozellikten(f, zorla or YURUTUCU_SECIMI)
    hit, gec = s["hit"], s["gec"]
    return Hikaye(
        hit_option=hit["option_id"], hit_tedarikci=hit["tedarikci"],
        gec_option=gec["option_id"], gec_tedarikci=gec["tedarikci"],
        magazalar={"hit": hit_magazalari(t, hh, hit["option_id"]),
                   "gec": gec_magazalari(t, hh, gec)},
        gevseyen=s["gevseyen"])


# ------------------------------------------------------------- ozet (yazıların alıntılayacağı sayılar)


def _tam(x) -> int:
    return int(round(float(x)))


def ozet(t: dict, opt: pd.DataFrame, hh: pd.DataFrame, f: pd.DataFrame, h: Hikaye,
         plan: pd.Series | None = None, hikaye_haftasi: int = HIKAYE_HAFTASI) -> dict:
    """İki sahnenin yazılarda alıntılanabilecek bütün sayıları (düz Python türleri).

    plan: option_id → plan_sezon (isteğe bağlı; yayımlanmaz, motordan gelir)."""
    ids = [h.hit_option, h.gec_option]
    panel = kaynak.option_panel(t, opt[opt["option_id"].isin(ids)], hh[hh["option_id"].isin(ids)],
                                (opt.loc[opt["option_id"] == ids[0], "sezon_kodu"].iloc[0],))
    ted = t["tedarikci"].set_index("tedarikci_id")
    urun = t["urun"][["urun_id", "option_id"]]
    st = t["stok"].merge(urun[urun["option_id"].isin(ids)], on="urun_id")
    son_pzt = st["tarih"].max()
    raf_son = st[st["tarih"] == son_pzt].groupby("option_id")["adet"].sum()

    def ortak(oid: str) -> dict:
        r = f[f["option_id"] == oid].iloc[0]
        p = panel[panel["option_id"] == oid].set_index("h")
        haftalik = [int(p.loc[w, "satis"]) for w in range(hikaye_haftasi) if w in p.index]
        d = {
            "option_id": oid, "model_adi": r["model_adi"], "renk": r["renk"], "alt_kategori": r["alt_kategori"],
            "sezon_kodu": r["sezon_kodu"], "dalga": int(r["dalga"]),
            "lansman": r["lansman_tarihi"].date().isoformat(), "indirim": r["indirim_baslangic"].date().isoformat(),
            "tedarikci": r["tedarikci"], "ulke": r["ulke"], "mense": r["mense"],
            "rpt_hafta": int(r["rpt_hafta"]), "moq": int(r["moq_option"]),
            "ilk_alim": int(r["ilk_alim"]),
            "plan": (_tam(plan[oid]) if plan is not None and oid in plan.index else None),
            "hikaye_haftasi": hikaye_haftasi,
            "haftalik_satis": haftalik,
            "online_satis": int(p.loc[[w for w in range(hikaye_haftasi) if w in p.index], "online_satis"].sum()),
            "satilan": _tam(r["satilan_h"]), "satilan_ilk_alim": float(r["satis_ilk_alim"]),
            "gonderilen": _tam(r["gonderilen_h"]), "str": float(r["str_h"]),
            "depo_stok": _tam(r["depo_h"]), "magaza_stok": _tam(r["magaza_h"]),
            "stoklu_magaza": _tam(p.loc[hikaye_haftasi, "stoklu_magaza"]) if hikaye_haftasi in p.index else None,
            "tasiyan_magaza": int(r["tasiyan_magaza"]),
            "stoksuz_magaza": int(r["stoksuz_magaza"]), "stoksuz_en_cok": float(r["stoksuz_en_cok"]),
            "banu_esik": miktar.RPT_STR_ESIGI, "banu_tetik": bool(r["banu_h"]),
            "rpt": None if pd.isna(r["rpt"]) else {
                "adet": int(r["rpt"]), "red": int(r["rpt_red"]), "giren": int(r["rpt_giren"]),
                "siparis": r["rpt_siparis"].date().isoformat(), "siparis_h": float(r["rpt_h"]),
                "planlanan_teslim": r["rpt_planlanan"].date().isoformat(),
                "teslim": r["rpt_teslim"].date().isoformat(), "teslim_h": float(r["rpt_gelis_h"]),
                "gecikme_gun": int((r["rpt_teslim"] - r["rpt_planlanan"]).days),
                "indirime_kalan_gun": int(r["rpt_gelis_gun"]),
                "depo_cikista": int(r["depo_cikista"]), "depoda_cikista": int(r["rpt_depoda_cikista"]),
                "depoda_pay": float(r["depoda_pay"]), "cikisa_kadar": int(r["rpt_cikisa_kadar"]),
                "outlete": int(r["rpt_outlete"]), "depoda_kalan": int(r["rpt_depoda_kalan"]),
                "gelis_tasiyan": int(r["gelis_tasiyan"]), "gelis_bos": int(r["gelis_bos"]),
                "gelis_satissiz": int(r["gelis_satissiz"]), "bos_pay": float(r["bos_pay"]),
                "depo_son": int(r["depo_son"]), "raf_son": int(raf_son.get(oid, 0)),
                "kalan_son": int(r["depo_son"]) + int(raf_son.get(oid, 0)),
            },
        }
        if d["rpt"]:
            d["rpt"]["bosa"] = min(d["rpt"]["giren"], d["rpt"]["kalan_son"])
        return d

    def tablo(oid: str, idler: list[str]) -> list[dict]:
        m = hikaye.magaza_tablosu(t, hh, oid, hikaye_haftasi).set_index("magaza_id").loc[idler]
        return [{"magaza_id": i, "ad": r["ad"], "sehir": r.get("sehir"), "tip": r["tip"],
                 "satis": int(r["satis"]), "stoklu_gun_ort": float(r["stoklu_gun_ort"]),
                 "stoksuz_gun_ort": float(r["stoksuz_gun_ort"]), "acik_gun": float(r["acik_gun"]),
                 "stok": int(r["stok"]), "stoklu_beden": int(r["stoklu_beden"]), "beden": int(r["beden"])}
                for i, r in m.iterrows()]

    def gec_tablo(oid: str, idler: list[str]) -> list[dict]:
        r = f[f["option_id"] == oid].iloc[0]
        g = gelis_durumu(t, hh, pd.DataFrame({"option_id": [oid], "gelis": [r["gelis"]]}))
        g = g.set_index("magaza_id").loc[idler].join(t["magaza"].set_index("magaza_id")[["ad", "sehir", "tip"]])
        return [{"magaza_id": i, "ad": x["ad"], "sehir": x["sehir"], "tip": x["tip"], "stok": int(x["stok"]),
                 "satis_28": int(x["satis_28"]), "satis_toplam": int(x["satis_toplam"])}
                for i, x in g.iterrows()]

    hit, gec = ortak(h.hit_option), ortak(h.gec_option)
    hit["magazalar"] = tablo(h.hit_option, h.magazalar["hit"])
    gec["magazalar"] = gec_tablo(h.gec_option, h.magazalar["gec"])
    return {"hit": hit, "gec": gec, "gevseyen": h.gevseyen}


# ------------------------------------------------------------- CLI


def _yaz(o: dict) -> None:
    for ad, baslik in (("hit", "HİT"), ("gec", "GEÇ GELEN")):
        s = o[ad]
        print(f"\n=== {baslik}: {s['option_id']}  {s['model_adi']} {s['renk']} ({s['alt_kategori']}, {s['sezon_kodu']}, "
              f"{s['dalga']}. dalga)")
        print(f"gevseyen: {o['gevseyen'][ad] or 'yok (tum olcutler saglandi)'}")
        print(f"lansman {s['lansman']}  indirim {s['indirim']}  tedarikci {s['tedarikci']} ({s['ulke']}, {s['mense']})  "
              f"RPT suresi {s['rpt_hafta']} hafta  MOQ {s['moq']}")
        plan = f"plan {s['plan']}" if s["plan"] is not None else "plan -(motordan; verilmedi)"
        print(f"ilk alim {s['ilk_alim']}  {plan}")
        print(f"{s['hikaye_haftasi']}. pazartesiye dek satis {s['satilan']} (ilk alimin {s['satilan_ilk_alim']:.3f}'i; "
              f"haftalik {s['haftalik_satis']}; online {s['online_satis']})  gonderilen {s['gonderilen']}  STR {s['str']:.3f}  "
              f"Banu kurali (esik {s['banu_esik']}): {'TETIKLENIYOR' if s['banu_tetik'] else 'tetiklenmiyor'}")
        print(f"o sabah: depo {s['depo_stok']}  magaza stogu {s['magaza_stok']}  stoklu magaza {s['stoklu_magaza']}/"
              f"{s['tasiyan_magaza']}  stoksuz gunlu magaza (>= {STOKSUZ_GUN_ESIGI} gun) {s['stoksuz_magaza']}  "
              f"en cok stoksuz gun {s['stoksuz_en_cok']:.1f}")
        r = s["rpt"]
        if r:
            print(f"Banu RPT: {r['adet']} adet (red {r['red']}, giren {r['giren']}), siparis {r['siparis']} "
                  f"(h {r['siparis_h']:.0f}), planlanan teslim {r['planlanan_teslim']}, teslim {r['teslim']} "
                  f"(h {r['teslim_h']:.2f}; gecikme {r['gecikme_gun']} gun), indirime {r['indirime_kalan_gun']} gun kala")
            print(f"  gelis haftasi: tasiyan {r['gelis_tasiyan']} magaza, bos {r['gelis_bos']} (%{100 * r['bos_pay']:.1f}), "
                  f"bos ve son {SATISSIZ_GUN} gun satissiz {r['gelis_satissiz']}")
            print(f"  akibet (FIFO): cikista depoda {r['depoda_cikista']} (depo {r['depo_cikista']}; "
                  f"giren adedin %{100 * r['depoda_pay']:.1f}), cikisa dek cikan {r['cikisa_kadar']}, "
                  f"outlete akan {r['outlete']}, pencere sonu depoda kalan {r['depoda_kalan']}")
            print(f"  pencere sonu: depo {r['depo_son']} + raf {r['raf_son']} = {r['kalan_son']} adet kalmis; "
                  f"satilmayan RPT (min(giren, kalan)) {r['bosa']}")
        print("magazalar:")
        for m in s["magazalar"]:
            if "satis_28" in m:
                print(f"  {m['magaza_id']} {m['ad']} ({m['sehir']}, {m['tip']}): gelis haftasi stok {m['stok']}, "
                      f"son {SATISSIZ_GUN} gun satis {m['satis_28']}, lansmandan beri {m['satis_toplam']}")
            else:
                print(f"  {m['magaza_id']} {m['ad']} ({m['sehir']}, {m['tip']}): satis {m['satis']}, "
                      f"stoklu gun {m['stoklu_gun_ort']:.1f}/{m['acik_gun']:.0f} (stoksuz {m['stoksuz_gun_ort']:.1f}), "
                      f"stok {m['stok']}, stoklu beden {m['stoklu_beden']}/{m['beden']}")


def main(argv: list[str] | None = None) -> dict:
    a = argparse.ArgumentParser(prog="python -m rpt.hikaye_sec", description=__doc__.split("\n")[0])
    a.add_argument("--hikaye", metavar="HIT_OPTION:GEC_OPTION", default=None,
                   help=f"secimi gecersiz kilar (varsayilan YURUTUCU_SECIMI {YURUTUCU_SECIMI})")
    a.add_argument("--adaylar", action="store_true", help="olcut merdivenine en yakin sahneleri listele")
    a.add_argument("--db", type=Path, default=None, help="v4 DuckDB dosyasi (varsayilan: ortak yol)")
    a.add_argument("--plan", type=Path, default=Path(__file__).resolve().parents[1] / "cikti" / "plan_sezon.csv",
                   help="option_id,plan_sezon CSV (varsa basilir; plan yayimlanmaz, motordan gelir)")
    args = a.parse_args(argv)
    zorla = secim_ayristir(args.hikaye) if args.hikaye else None

    t = kaynak.veri_yukle(args.db, sezonlar=(SEZON,))
    opt = kaynak.optionlar(t)
    hh = kaynak.hucre_hafta(t, opt, (SEZON,))
    f = ozellikler(t, opt, hh)
    plan = None
    if args.plan.exists():
        plan = pd.read_csv(args.plan).set_index("option_id")["plan_sezon"]
    hb, gb = hit_bayraklari(f), gec_bayraklari(f)
    print(f"merdiven huni (hit): {huni(hb)}")
    print(f"merdiven huni (gec gelen): {huni(gb)}")
    if args.adaylar:
        with pd.option_context("display.width", 250, "display.max_columns", 30):
            kol = ["option_id", "model_adi", "renk", "dalga", "tedarikci", "tutmayan", "gevseyen"]
            print("\nHIT en yakin adaylar:")
            print(en_yakin(f, hb, hit_sirasi)[kol + ["str_h", "satis_ilk_alim", "stoksuz_magaza", "ilk_alim"]]
                  .to_string(index=False))
            print("\nGEC GELEN en yakin adaylar:")
            print(en_yakin(f, gb, gec_sirasi)[kol + ["rpt", "rpt_h", "rpt_gelis_gun", "bos_pay", "depoda_pay"]]
                  .to_string(index=False))
    h = sec(t, opt, hh, zorla=zorla, f=f)
    s = sec_ozellikten(f)
    print(f"\nmerdivenin ilk sirasi: hit {s['merdiven']['hit']}, gec gelen {s['merdiven']['gec']}"
          f"  (secim {h.hit_option}, {h.gec_option})")
    o = ozet(t, opt, hh, f, h, plan=plan)
    _yaz(o)
    return o


if __name__ == "__main__":
    main()
