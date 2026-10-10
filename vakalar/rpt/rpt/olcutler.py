"""Kol ölçütleri (spec §4.4), bir koşunun tablolarından ve gizli gerçeğinden,
option düzeyinde. Ölçüm modülüdür: koşuyu etkilemez (`motor.KOSU_DISI`); sonucu
bir politikaya girerse (SS24'te seçilen dağıtım kuralı) o politikanın
`parametreler`'inden geçer.

    o   = ozet(kosu, "SS25")                    # option başına, mutlak
    o   = ozet(kosu, "SS25", taban=ozet(yok))   # + rpt_yok koluna göre farklar
    oz  = sezon_ozeti(o, kahin=ozet(kahin_kosusu, "SS25", taban=...))

`kosu` bir `motor.Kosu` ya da `motor.KosuKaydi`dır (`tablo(ad, sutunlar,
urunler)`: yalnız sezonun SKU'ları okunur).

DEĞERLEME. Gelir = koşunun gerçekleşen satış tutarı (`satis.tutar`: markdown,
kampanya ve işlem indirimi dahil, iadeler düşülmüş; outlet satışı dahil; pencere
sonuna dek). Maliyet = alış fiyatı × depoya GİREN adet (ilk alım + RPT; teslim
edilmiş sipariş adedi − kalite kontrolde reddedilen; reddedilen mal depoya girmez,
tedarikçiye döner). Pencere sonunda kalan stok 0 değerlidir (v4 README: çıkmış
sezonluk stok depoda kalır, bir daha satılmaz): kâr alt sınırdır.

KAYIP (gizli gerçekten, `Kosu.gercek`): karşılanmayan = talep − kendi satış;
kalıcı kayıp (müşteri hiçbir şey almadı) ve ikameye giden (başka SKU aldı) ayrı.
`_tf` sütunları indirim başından önceki günlerdir (tam fiyat dönemi). Kurtarılan
kayıp tabana (rpt_yok kolu, aynı tohum) göre karşılanmayanın düşüşüdür.

RPT. `rpt` sipariş adedi, `rpt_giren` depoya giren; `kalan_son` pencerenin son
günündeki depo stoğu + son pazartesi raf stoğu; `rpt_bosa` = min(rpt_giren,
kalan_son): satılmadan kalan RPT adedi (RPT marjinal mal sayılır). Yanlış alarm:
RPT'si olan option'ın tam fiyat satışı tabana göre MOQ/2'den az arttı (aday
modelinin etiketiyle aynı eşik).

Bağlam uyarısı (replenishment vakasının dersi): bir kol daha az mal gönderdiği
için de "iyi" görünebilir; her özette mağazaya giden adet (`magazaya`) ve tam
fiyat döneminin stoklu gün payı (`stoklu_pay_tf`) da durur.
"""

import numpy as np
import pandas as pd

DEPO = "DEPO"
OZET_SUTUNLARI = (
    "option_id", "sezon_kodu", "dalga", "mense", "moq", "alis_fiyati", "indirim_baslangic",
    "ilk_alim", "ilk_giren", "rpt", "rpt_giren", "rpt_siparis_tarihi", "rpt_teslim",
    "satis_tf", "satis_ind", "iade", "gelir", "maliyet", "kar", "magazaya", "stoklu_pay_tf",
    "talep", "karsilanmayan", "karsilanmayan_tf", "ikameye_giden", "kalici_kayip",
    "kalan_son", "rpt_bosa",
)
FARK_SUTUNLARI = ("d_kar", "d_gelir", "d_satis_tf", "d_satis_ind", "kurtarilan", "kurtarilan_tf",
                  "kurtarilan_kalici", "kurtarilan_ikame", "yanlis_alarm")
TAM_SAYI = ("ilk_alim", "ilk_giren", "rpt", "rpt_giren", "satis_tf", "satis_ind", "iade", "magazaya",
            "talep", "karsilanmayan", "karsilanmayan_tf", "ikameye_giden", "kalici_kayip",
            "kalan_son", "rpt_bosa", "moq")


def _metin(df: pd.DataFrame, sutunlar) -> pd.DataFrame:
    return df.assign(**{c: df[c].astype(str) for c in sutunlar if c in df.columns})


def ozet(kosu, sezon: str, taban: pd.DataFrame | None = None, line: str = "Collection") -> pd.DataFrame:
    """Sezonun `line` option'ları için option başına ölçütler (`OZET_SUTUNLARI`;
    `taban` verilirse + `FARK_SUTUNLARI`), option_id sıralı. Bkz. modül notu."""
    urun = _metin(kosu.tablo("urun", ["urun_id", "option_id", "sezon_kodu", "line", "dalga",
                                      "alis_fiyati", "tedarikci_id", "lansman_tarihi"]),
                  ("urun_id", "option_id", "sezon_kodu", "line", "tedarikci_id"))
    u = urun[(urun["sezon_kodu"] == sezon) & (urun["line"] == line)]
    if u.empty:
        raise ValueError(f"ozet: {sezon} {line} option'ı yok")
    skular = sorted(u["urun_id"])
    harita = pd.Series(u["option_id"].to_numpy(), index=u["urun_id"].to_numpy())
    o = (u.drop_duplicates("option_id").sort_values("option_id")
         [["option_id", "sezon_kodu", "dalga", "alis_fiyati", "tedarikci_id", "lansman_tarihi"]])
    sz = _metin(kosu.tablo("sezon", ["sezon_kodu", "dalga", "indirim_baslangic"]), ("sezon_kodu",))
    o = o.merge(sz.drop_duplicates(["sezon_kodu", "dalga"]), on=["sezon_kodu", "dalga"], how="left")
    ted = _metin(kosu.tablo("tedarikci", ["tedarikci_id", "mense", "moq_option"]), ("tedarikci_id", "mense"))
    o = o.merge(ted.rename(columns={"moq_option": "moq"}), on="tedarikci_id", how="left")
    o = o.set_index("option_id")
    ids = o.index
    ind = pd.to_datetime(o["indirim_baslangic"])
    lan = pd.to_datetime(o["lansman_tarihi"])

    def opt(df) -> np.ndarray:
        return df["urun_id"].astype(str).map(harita).to_numpy()

    def topla(anahtar, deger) -> np.ndarray:
        seri = pd.Series(np.asarray(deger, dtype=float)).groupby(np.asarray(anahtar)).sum()
        return seri.reindex(ids).fillna(0.0).to_numpy()

    # Sipariş ve kalite: depoya giren adet
    sp = _metin(kosu.tablo("siparis", ["siparis_id", "tip", "urun_id", "siparis_tarihi",
                                       "gerceklesen_teslim", "adet"], urunler=skular),
                ("siparis_id", "tip", "urun_id"))
    sp = sp.assign(option_id=opt(sp))
    kal = _metin(kosu.tablo("kalite_kontrol", ["siparis_id", "hatali"]), ("siparis_id",))
    hatali = kal.groupby("siparis_id")["hatali"].sum()
    s = sp.groupby("siparis_id").agg(option_id=("option_id", "first"), tip=("tip", "first"),
                                     siparis_tarihi=("siparis_tarihi", "min"),
                                     teslim=("gerceklesen_teslim", "min"), adet=("adet", "sum"))
    s["giren"] = np.where(s["teslim"].notna(), s["adet"] - hatali.reindex(s.index).fillna(0), 0)
    sonuc = pd.DataFrame(index=ids)
    ilk, rpt = s[s["tip"] == "ilk"], s[s["tip"] == "rpt"]
    sonuc["ilk_alim"] = topla(ilk["option_id"], ilk["adet"])
    sonuc["ilk_giren"] = topla(ilk["option_id"], ilk["giren"])
    sonuc["rpt"] = topla(rpt["option_id"], rpt["adet"])
    sonuc["rpt_giren"] = topla(rpt["option_id"], rpt["giren"])
    r = rpt.groupby("option_id")
    sonuc["rpt_siparis_tarihi"] = r["siparis_tarihi"].min().reindex(ids)
    sonuc["rpt_teslim"] = r["teslim"].min().reindex(ids)

    # Satış
    sa = kosu.tablo("satis", ["tarih", "urun_id", "adet", "tutar"], urunler=skular)
    so = opt(sa)
    adet = sa["adet"].to_numpy(float)
    poz = adet > 0
    tf = pd.to_datetime(sa["tarih"]).to_numpy() < ind.reindex(so).to_numpy()
    sonuc["satis_tf"] = topla(so[poz & tf], adet[poz & tf])
    sonuc["satis_ind"] = topla(so[poz & ~tf], adet[poz & ~tf])
    sonuc["iade"] = -topla(so[~poz], adet[~poz])
    sonuc["gelir"] = topla(so, sa["tutar"].to_numpy(float))
    sonuc["maliyet"] = o["alis_fiyati"].to_numpy(float) * (sonuc["ilk_giren"] + sonuc["rpt_giren"])
    sonuc["kar"] = sonuc["gelir"] - sonuc["maliyet"]

    # Sevkiyat ve raf
    sv = _metin(kosu.tablo("sevkiyat", ["kaynak", "hedef", "urun_id", "adet"], urunler=skular),
                ("kaynak", "hedef"))
    giden = sv[(sv["kaynak"] == DEPO) & (sv["hedef"] != DEPO)]
    sonuc["magazaya"] = topla(opt(giden), giden["adet"])
    st = kosu.tablo("stok", ["tarih", "urun_id", "adet", "stoklu_gun"], urunler=skular)
    sto = opt(st)
    stt = pd.to_datetime(st["tarih"]).to_numpy()
    tfh = (stt > lan.reindex(sto).to_numpy()) & (stt <= ind.reindex(sto).to_numpy())
    n = topla(sto[tfh], np.ones(int(tfh.sum())))
    sonuc["stoklu_pay_tf"] = np.divide(topla(sto[tfh], st["stoklu_gun"].to_numpy(float)[tfh]), 7.0 * n,
                                       out=np.full(len(ids), np.nan), where=n > 0)

    # Gizli gerçek
    g = kosu.tablo("gercek", ["tarih", "urun_id", "talep", "karsilanmayan", "ikameye_giden", "kalici_kayip"],
                   urunler=skular)
    go = opt(g)
    gtf = pd.to_datetime(g["tarih"]).to_numpy() < ind.reindex(go).to_numpy()
    for c in ("talep", "karsilanmayan", "ikameye_giden", "kalici_kayip"):
        sonuc[c] = topla(go, g[c].to_numpy(float))
    sonuc["karsilanmayan_tf"] = topla(go[gtf], g["karsilanmayan"].to_numpy(float)[gtf])

    # Pencere sonunda kalan
    takvim = pd.to_datetime(kosu.tablo("takvim", ["tarih"])["tarih"])
    son, son_pzt = takvim.max(), takvim[takvim.dt.dayofweek == 0].max()
    ds = kosu.tablo("depo_stok", ["tarih", "urun_id", "adet"], urunler=skular)
    ds = ds[pd.to_datetime(ds["tarih"]).to_numpy() == son.to_datetime64()]
    rs = st[stt == son_pzt.to_datetime64()]
    sonuc["kalan_son"] = topla(opt(ds), ds["adet"]) + topla(opt(rs), rs["adet"])
    sonuc["rpt_bosa"] = np.minimum(sonuc["rpt_giren"], sonuc["kalan_son"])

    d = o.join(sonuc).reset_index()
    for c in TAM_SAYI:
        d[c] = d[c].astype(np.int64)
    d = d[list(OZET_SUTUNLARI)]
    if taban is not None:
        d = _farklar(d, taban)
    return d


def _farklar(d: pd.DataFrame, taban: pd.DataFrame) -> pd.DataFrame:
    t = taban.set_index("option_id").reindex(d["option_id"])
    if t["kar"].isna().any():
        raise ValueError("ozet: tabanda olmayan option")
    d = d.copy()

    def fark(c):
        return d[c].to_numpy(float) - t[c].to_numpy(float)

    d["d_kar"], d["d_gelir"] = fark("kar"), fark("gelir")
    d["d_satis_tf"], d["d_satis_ind"] = fark("satis_tf"), fark("satis_ind")
    d["kurtarilan"] = -fark("karsilanmayan")
    d["kurtarilan_tf"] = -fark("karsilanmayan_tf")
    d["kurtarilan_kalici"] = -fark("kalici_kayip")
    d["kurtarilan_ikame"] = -fark("ikameye_giden")
    d["yanlis_alarm"] = (d["rpt"] > 0) & (d["d_satis_tf"] < d["moq"] / 2)
    return d


TOPLANAN = ("ilk_alim", "ilk_giren", "rpt", "rpt_giren", "satis_tf", "satis_ind", "iade", "gelir",
            "maliyet", "kar", "magazaya", "talep", "karsilanmayan", "karsilanmayan_tf", "ikameye_giden",
            "kalici_kayip", "kalan_son", "rpt_bosa",
            "d_kar", "d_gelir", "d_satis_tf", "d_satis_ind", "kurtarilan", "kurtarilan_tf",
            "kurtarilan_kalici", "kurtarilan_ikame")


def sezon_ozeti(o: pd.DataFrame, kahin: pd.DataFrame | None = None) -> dict:
    """`ozet` tablosunun sezon toplamları (`TOPLANAN`'dan var olanlar) + sayımlar.

    rpt_option   RPT'si olan option sayısı
    yanlis_alarm (tabanlı özette) yanlış alarm sayısı
    rpt_ek_tf / rpt_ek_ind / rpt_str
                 RPT'li option'ların tabana göre ek satışı; ek satış ÷ giren RPT
    kacirilan    `kahin` (kâhin kolunun tabanlı özeti) verilirse: kolun RPT
                 vermediği, kâhinin RPT verip kârı tabana göre artırdığı option
                 sayısı ve kâhinin o option'lardaki kâr artışı (`kacirilan_tl`)"""
    k = o.set_index("option_id")
    oz = {c: float(k[c].sum()) for c in TOPLANAN if c in k.columns}
    oz["option"] = int(len(k))
    rptli = k["rpt"] > 0
    oz["rpt_option"] = int(rptli.sum())
    oz["stoklu_pay_tf"] = float(k["stoklu_pay_tf"].mean())
    if "yanlis_alarm" in k.columns:
        oz["yanlis_alarm"] = int(k["yanlis_alarm"].sum())
        oz["rpt_ek_tf"] = float(k.loc[rptli, "d_satis_tf"].sum())
        oz["rpt_ek_ind"] = float(k.loc[rptli, "d_satis_ind"].sum())
        oz["rpt_str"] = ((oz["rpt_ek_tf"] + oz["rpt_ek_ind"]) / oz["rpt_giren"]
                         if oz["rpt_giren"] > 0 else float("nan"))
    if kahin is not None:
        kh = kahin.set_index("option_id").reindex(k.index)
        kazanc = kh["d_kar"]
        kacan = (~rptli) & (kh["rpt"] > 0) & (kazanc > 0)
        oz["kacirilan"] = int(kacan.sum())
        oz["kacirilan_tl"] = float(kazanc[kacan].sum())
    return oz


def gercek_gunluk(satis: pd.DataFrame, karsilanmayan: pd.DataFrame, ikame_alinan: pd.DataFrame,
                  urun: pd.DataFrame, opsiyonlar=None) -> pd.DataFrame:
    """Hücre-gün gerçek talep (ölçüm; kestiricilere verilmez): `tarih, magaza_id,
    urun_id, option_id, talep`, yalnız talebi pozitif satırlar.

        talep = pozitif satış − alınan ikame + karşılanmayan

    satis          yayımlanan TEMİZ satış (`kaynak.temiz_satis`; iade satırları atılır)
    karsilanmayan  hakem tablosu (`hakem.oku()["karsilanmayan"]`; talep − kendi satış)
    ikame_alinan   hakem tablosu (alıcı hücrede ikame satışı; satışta zaten var)
    urun           urun_id → option_id
    opsiyonlar     verilirse yalnız bu option'lar (bellek)

    Hakemin kendi satışı ham satıştan gelir; temiz satış ondan yalnız kirletme
    farkı kadar ayrılır (mükerrer satır temizlikte düşer)."""
    u = urun[["urun_id", "option_id"]].drop_duplicates("urun_id").astype({"urun_id": str,
                                                                         "option_id": str})
    if opsiyonlar is not None:
        u = u[u["option_id"].isin(set(map(str, opsiyonlar)))]
    secili = set(u["urun_id"])

    def _parca(df, kolon, isaret, pozitif=False):
        d = df[["tarih", "magaza_id", "urun_id", kolon]]
        d = d[d["urun_id"].astype(str).isin(secili)]
        if pozitif:
            d = d[d[kolon] > 0]
        return pd.DataFrame({"tarih": pd.to_datetime(d["tarih"]).to_numpy("datetime64[ns]"),
                             "magaza_id": d["magaza_id"].astype(str).to_numpy(),
                             "urun_id": d["urun_id"].astype(str).to_numpy(),
                             "talep": isaret * d[kolon].to_numpy(np.int64)})

    g = pd.concat([_parca(satis, "adet", 1, pozitif=True),
                   _parca(ikame_alinan, "adet", -1),
                   _parca(karsilanmayan, "karsilanmayan", 1)], ignore_index=True)
    g = g.groupby(["tarih", "magaza_id", "urun_id"], sort=True)["talep"].sum().reset_index()
    if (g["talep"] < 0).any():
        raise ValueError(f"gercek_gunluk: {int((g['talep'] < 0).sum())} hücre-günde alınan ikame "
                         "satışı aşıyor (satış tablosu temiz satış mı?)")
    g = g[g["talep"] > 0].merge(u, on="urun_id")
    return g[["tarih", "magaza_id", "urun_id", "option_id", "talep"]].reset_index(drop=True)
