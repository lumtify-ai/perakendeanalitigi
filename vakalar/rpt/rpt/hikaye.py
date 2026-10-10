"""Hikâye yazısının (1. yazı) ve Lumoda'nın bugünkü RPT pratiğinin sayıları (v4).

    bitis_haftasi     tutan bir option'ın zincirde "bittiği" ilk pazartesi
    magaza_tablosu    seçilen pazartesi mağaza mağaza durum (satış, stoklu / stoksuz gün, stok)
    rpt_siparisleri   Lumoda'nın (Banu'nun kuralının) verdiği RPT'ler: ne zaman verildi, ne zaman geldi
    rpt_akibeti       o RPT adetlerinin kaderi: çıkışa dek çıktı mı, çıkışta depoda mı kaldı,
                      outlet'e mi aktı, pencere sonunda depoda mı kaldı

Hikâye seçimi `hikaye_sec`'tedir; burası seçilen sahnenin sayılarının kurucularıdır.
Gizli gerçeğe (kayıp satış, gerçek talep) dokunmaz: v4'te kayıp tablosu yayımlanmaz,
gerçek talep yalnız hakemden gelir (Görev 10, rapor).

"BİTTİ" TANIMI. Zincirin gözünden: pazartesi sabahı depoda ilk alımın
%2'sinden azı kalmış VE depo + mağaza stoğu ilk alımın %20'sinin altına
inmiş. Mağazada kalan birkaç yüz adet çoğunlukla kırık beden ve yavaş
mağazadadır; müşterinin gözünde ürün bitmiştir.

RPT AKIBETİ (atama kuralı). Depo SKU'yu ayırt eder ama partiyi etmez. RPT
adetlerinin kaderi option düzeyinde FIFO ile atanır: depoda önceden duran mal
önce çıkar, RPT ondan sonra; çıkış pazartesisi sabahı depoda kalan adet (en
fazla RPT adedi kadar) RPT'den kalmış sayılır. Depo yalnız mağazalara değil
online müşteriye de mal verir (online satış depodan karşılanır); bu yüzden
çıkıştan önce depodan çıkan RPT "mağazaya gitti" değil "çıkışa dek çıktı"dır.
v4'te çıkıştan sonra depo üç akışla oynar: `outlet_akisi` (depodan outlet
mağazalara; ürünün sezon sonu yolu), `stok_devri` (mağazalardan depoya dönen,
sıranın sonuna girer) ve pencere sonu stoğu. Kaderin üç kovası, FIFO sırasıyla
(RPT = giren adet, yani sipariş − kalite reddi):

    rpt_cikisa_kadar   geldikten sonra çıkıştan önce depodan çıkan (mağaza + online):
                       giren − çıkışta depoda duran
    rpt_outlete        çıkıştan sonra depodan outlet akışıyla çıkan
    rpt_depoda_kalan   pencere sonunda depoda kalan
    (toplam = giren)

FIFO, RPT'yi depodan en son çıkan mal sayar: çıkışa dek çıkan RPT'nin ALT sınırıdır.
Çıkışa dek çıkanın mağazaya giden payı da bir aralıktır: alt sınır
`rpt_magazaya_alt` = çıkışa dek çıkan − online net satış (negatifse 0; hepsi RPT'den karşılandıysa
mağazaya kalan), üst sınır `rpt_magazaya_ust` = çıkışa dek çıkan ve depodan mağazalara
giden toplam sevkiyatın küçüğü. Partinin bilinmediği belirsizlik aralığıdır; yazı hangisini
söylediğini belirtir.
"""

import numpy as np
import pandas as pd

BITTI_DEPO_PAYI = 0.02
BITTI_ZINCIR_PAYI = 0.20
DEPO = "DEPO"
ONLINE = "ONL"


def bitis_haftasi(panel: pd.DataFrame, opt: pd.DataFrame) -> pd.Series:
    """Option başına "bitti" koşulunun ilk sağlandığı h (pazartesi); yoksa NaN."""
    p = panel.merge(opt[["option_id", "ilk_alim"]], on="option_id")
    p = p[p["h"] >= 1]
    bitti = (p["depo_stok"] <= BITTI_DEPO_PAYI * p["ilk_alim"]) & (
        p["depo_stok"] + p["magaza_stok"] <= BITTI_ZINCIR_PAYI * p["ilk_alim"])
    return p[bitti].groupby("option_id")["h"].min().rename("bitti_h")


def magaza_tablosu(t: dict, hh: pd.DataFrame, option_id: str, h: int) -> pd.DataFrame:
    """h. pazartesi sabahı mağaza başına: lansmandan beri satış, stoklu gün ve
    stoksuz gün (bedenlerin ortalaması), stoklu beden / taşınan beden, o anki stok.

    Mağaza evreni: option'ın ilk dağıtımından mal almış (hücresinin `ilk_dagitim`ı
    > 0) fiziksel mağazalar; online (`ONL`) satış burada yok, option panelinde.
    Satış sıfır olsa da mal almış mağaza satırda kalır. Gerçek talep yoktur (hakem).
    """
    c = hh[(hh["option_id"] == option_id) & (hh["h"] < h) & (hh["ilk_dagitim"] > 0)]
    m = c.groupby("magaza_id").agg(satis=("satis", "sum"))
    hucre = c.groupby(["magaza_id", "urun_id"]).agg(stoklu=("stoklu_gun", "sum"), acik=("acik_gun", "sum"))
    hucre = hucre.groupby("magaza_id").mean()
    m["stoklu_gun_ort"] = hucre["stoklu"]
    m["acik_gun"] = hucre["acik"]
    m["stoksuz_gun_ort"] = m["acik_gun"] - m["stoklu_gun_ort"]
    lansman = pd.Timestamp(t["urun"].loc[t["urun"]["option_id"] == option_id, "lansman_tarihi"].iloc[0])
    gun = lansman + pd.Timedelta(days=7 * h)
    hucreler = c[["magaza_id", "urun_id"]].drop_duplicates()
    st = t["stok"][t["stok"]["tarih"] == gun].merge(hucreler, on=["magaza_id", "urun_id"])
    m["stok"] = st.groupby("magaza_id")["adet"].sum()
    m["stoklu_beden"] = st.groupby("magaza_id")["adet"].apply(lambda a: int((a > 0).sum()))
    m["beden"] = st.groupby("magaza_id")["adet"].size()
    kolonlar = [k for k in ("ad", "sehir", "bolge", "tip") if k in t["magaza"].columns]
    m = m.join(t["magaza"].set_index("magaza_id")[kolonlar])
    for k in ("stok", "stoklu_beden", "beden"):
        m[k] = m[k].fillna(0).astype(int)
    return m.sort_values(["satis", "ad"], ascending=[False, True]).reset_index()


def rpt_siparisleri(t: dict, opt: pd.DataFrame) -> pd.DataFrame:
    """Option başına RPT siparişleri (SKU satırları toplanmış); `giren` kalite
    kontrolde reddedilmeyip depoya giren adet (teslim edilmemişse 0)."""
    r = t["siparis"].query("tip == 'rpt'").groupby(
        ["siparis_id", "option_id", "siparis_tarihi", "planlanan_teslim", "gerceklesen_teslim"],
        dropna=False)["adet"].sum().reset_index()
    hatali = t["kalite_kontrol"].groupby("siparis_id")["hatali"].sum()
    r["red"] = r["siparis_id"].map(hatali).fillna(0).astype(int)
    r["giren"] = np.where(r["gerceklesen_teslim"].notna(), r["adet"] - r["red"], 0)
    r = r.merge(opt[["option_id", "sezon_kodu", "dalga", "mense", "rpt_hafta", "lansman_tarihi",
                     "indirim_baslangic", "cikis_tarihi", "ilk_alim"]], on="option_id")
    r["siparis_h"] = (r["siparis_tarihi"] - r["lansman_tarihi"]).dt.days / 7
    r["gelis_h"] = (r["gerceklesen_teslim"] - r["lansman_tarihi"]).dt.days / 7
    r["indirimden_sonra"] = r["gerceklesen_teslim"] >= r["indirim_baslangic"]
    r["indirime_kalan_gun"] = (r["indirim_baslangic"] - r["gerceklesen_teslim"]).dt.days
    r["indirime_kalan_hafta"] = r["indirime_kalan_gun"] / 7
    return r


def rpt_akibeti(t: dict, opt: pd.DataFrame, sezon: str) -> pd.DataFrame:
    """Sezonun RPT'li option'ları: verilen, giren ve dört kovada kaderi (modül belgesi).

    Girdiler v4 akışlarıdır: `depo_stok` (çıkış pazartesisi sabahı ve pencerenin son
    pazartesisi; yükleyici yalnız pazartesileri okur), `sevkiyat` (depodan çıkan
    her mal: replenishment, outlet akışı; RPT geldikten sonra), `stok_devri`
    (çıkış günü mağazalardan depoya dönen). Atama FIFO (modül belgesi).

    Sütunlar: option_id, rpt (sipariş), red, rpt_giren, gelis, cikis_tarihi,
    depo_cikista, gelisten_cikisa_cikan (depodan mağazalara), online_gelisten_cikisa
    (net online satış), cikis_sonrasi_cikan (depodan çıkış gününden itibaren outlet akışıyla
    çıkan; `tip == 'outlet_akisi'`: çıkıştan sonra başka tiple çıkan nadir mal outlet'e
    sayılmaz, FIFO'da depoda kalan kovasında kalır),
    stok_devri (depoya dönen), depo_son (pencerenin son pazartesisi depo stoğu),
    rpt_depoda_cikista, rpt_cikisa_kadar, rpt_magazaya_alt, rpt_magazaya_ust,
    rpt_outlete, rpt_depoda_kalan.
    """
    r = rpt_siparisleri(t, opt)
    r = r[r["sezon_kodu"] == sezon]
    o = r.groupby("option_id").agg(rpt=("adet", "sum"), red=("red", "sum"), rpt_giren=("giren", "sum"),
                                   siparis=("siparis_id", "nunique"),
                                   indirimden_sonra=("indirimden_sonra", "any"),
                                   gelis=("gerceklesen_teslim", "min"))
    o = o.join(opt.set_index("option_id")[["cikis_tarihi", "ilk_alim"]])
    urun = t["urun"][["urun_id", "option_id"]]
    harita = urun[urun["option_id"].isin(o.index)]

    depo = t["depo_stok"].merge(harita, on="urun_id")
    cikis = depo.merge(o[["cikis_tarihi"]].reset_index(), on="option_id")
    cikis = cikis[cikis["tarih"] == cikis["cikis_tarihi"]]
    o["depo_cikista"] = cikis.groupby("option_id")["adet"].sum().reindex(o.index).fillna(0).astype(int)
    son = depo[depo["tarih"] == depo["tarih"].max()]
    o["depo_son"] = son.groupby("option_id")["adet"].sum().reindex(o.index).fillna(0).astype(int)

    sv = t["sevkiyat"].merge(harita, on="urun_id").merge(o[["gelis", "cikis_tarihi"]].reset_index(),
                                                          on="option_id")
    kaynak_ = sv["kaynak"].astype(str)
    hedef = sv["hedef"].astype(str)
    depodan = sv[(kaynak_ == DEPO) & (hedef != DEPO)]
    arada = depodan[(depodan["tarih"] >= depodan["gelis"]) & (depodan["tarih"] < depodan["cikis_tarihi"])]
    sonra = depodan[(depodan["tarih"] >= depodan["cikis_tarihi"])
                    & (depodan["tip"].astype(str) == "outlet_akisi")]
    devri = sv[(sv["tip"] == "stok_devri") & (hedef == DEPO) & (sv["tarih"] >= sv["cikis_tarihi"])]
    onl = t["satis"][t["satis"]["magaza_id"].astype(str) == ONLINE].merge(harita, on="urun_id").merge(
        o[["gelis", "cikis_tarihi"]].reset_index(), on="option_id")
    onl = onl[(onl["tarih"] >= onl["gelis"]) & (onl["tarih"] < onl["cikis_tarihi"])]
    o["online_gelisten_cikisa"] = onl.groupby("option_id")["adet"].sum().reindex(o.index).fillna(0).astype(int)
    o["gelisten_cikisa_cikan"] = arada.groupby("option_id")["adet"].sum().reindex(o.index).fillna(0).astype(int)
    o["cikis_sonrasi_cikan"] = sonra.groupby("option_id")["adet"].sum().reindex(o.index).fillna(0).astype(int)
    o["stok_devri"] = devri.groupby("option_id")["adet"].sum().reindex(o.index).fillna(0).astype(int)

    # FIFO: önce önceden duran mal (P), sonra RPT, sonra çıkışta depoya dönenler
    o["rpt_depoda_cikista"] = np.minimum(o["rpt_giren"], o["depo_cikista"])
    o["rpt_cikisa_kadar"] = o["rpt_giren"] - o["rpt_depoda_cikista"]
    onceden = o["depo_cikista"] - o["rpt_depoda_cikista"]
    o["rpt_outlete"] = np.clip(o["cikis_sonrasi_cikan"] - onceden, 0, o["rpt_depoda_cikista"])
    o["rpt_depoda_kalan"] = o["rpt_depoda_cikista"] - o["rpt_outlete"]
    # online net satış negatifse (iade satıştan çok) depodan online'a çıkan mal yoktur: 0 sayılır
    o["rpt_magazaya_alt"] = np.maximum(o["rpt_cikisa_kadar"] - o["online_gelisten_cikisa"].clip(lower=0), 0)
    o["rpt_magazaya_ust"] = np.minimum(o["rpt_cikisa_kadar"], o["gelisten_cikisa_cikan"])
    return o.reset_index()
