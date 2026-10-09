"""Yayımlanan v4 tablolarını okur; sezonluk option'lar için hücre-hafta ve
option-hafta panelleri kurar.

Vakanın bütün analizi bu iki panelin üstünde durur:

    hucre_hafta   (mağaza × SKU × lansmandan beri hafta)  satış, stoklu gün,
                  açık gün, ilk dağıtım adedi
    option_panel  (option × hafta)  zincir toplamları (mağaza + online satış)
                  + pazartesi fotoğrafları (depo, mağaza stoğu, taşıyan /
                  stoklu mağaza)

Ham tablolar `veri/cikti/v4/perakende.duckdb`'den ortak paketin
(`perakende_analitik.kaynak`) bağlantısı ve temizlik görünümleriyle okunur:
`temiz_satis` (mükerrer satır düşer) ve `cesit_hucreleri` (hayalet stok
düşer). Bu modül gizli gerçeğe (`perakende_veri`, hakem) dokunmaz.

HAFTA TANIMI. Sezonluk ürün pazartesi lanse edilir; h. hafta
[lansman + 7h, lansman + 7h + 7) günleridir. h. haftanın stoklu günü,
v4'ün `stok` tablosunun (lansman + 7(h+1)) pazartesisi fotoğrafındadır
(`stoklu_gun` önceki 7 günü sayar). h. haftanın pazartesi fotoğrafı
(depo, mağaza stoğu) haftanın başındaki, o günün hiçbir hareketinden önceki
durumdur: h = 0'da mağazalar henüz boştur (ilk dağıtım lansmandan en çok 3 gün
önce çıkar, lansman günü varır ve o gün sayılır).

V3'TEN FARKLAR.
  * `kayip` sütunları (hücre-hafta ve panel) ve `talep` YOK: v4'te kayıp satış
    tablosu yayımlanmaz. Gerçek talep yalnız hakemden (ve motorun gizli
    gerçeğinden) gelir; kestiriciler onu hiç görmez.
  * `sevkiyat` `hedef` + `varis_tarihi` taşır. Mağazaya varış = hedefi mağaza
    olan, varışı dolu sevkiyat; haftaya VARIŞ tarihiyle yazılır. Yolda kalan
    (varış boş) sayılmaz. Panelin `sevk`i yalnız `ilk_dagitim` +
    `replenishment`tır (outlet_akisi, stok_devri, elle / açılış / kapanış
    transferi, iade_depoya dışarıda); `geri_toplama` tipi yoktur.
  * `depo_stok` GÜNLÜKTÜR; panele yalnız pazartesi fotoğrafları girer (günlük
    toplamak ~7 kat şişirir). Yükleyici zaten yalnız pazartesileri okur;
    `option_panel` yine de her option'ın lansman gününe göre süzer.
  * Online (`ONL`) satış option panelinde `satis`a (STR payı) girer, ayrı
    `online_satis` olarak da görünür. Hücre evreninde yoktur: stok satırı
    olmadığı, mağazaya dağıtılmadığı için `hucre_hafta` ve `tasiyan_magaza`
    onu görmez.
  * Tedarikçi alanları (`rpt_hafta`, `moq_option`, `mense`, `uzmanlik`)
    tedarikçi tablosundan, `urun.tedarikci_id` üstünden gelir; ilk alım
    `siparis` `tip='ilk'` toplamıdır.
  * Plan bu modülün işi değildir (yayımlanmaz; Görev 4'te `motor`dan).

Paneller tablo sözlüğü alır; aynı fonksiyonlar motorun hareket tablolarına
da uygulanır (yayımlananla aynı şema).
"""

from pathlib import Path

import numpy as np
import pandas as pd
from perakende_analitik import kaynak as ortak

VERITABANI = ortak.VARSAYILAN_YOL

ONLINE = "ONL"
OYUN_SEZONLARI = ("AW24", "SS25")
# Pencerede (2023-01-01 → 2025-12-31) lansmandan indirime kadar eksiksiz
# görünen sezonlar, kronolojik. AW22 pencere başında yarımdır (lansman
# 2022'de), AW25'in indirimi pencerenin dışındadır (2026-01-02).
TAM_SEZONLAR = ("SS23", "AW23", "SS24", "AW24", "SS25")

TABLOLAR = (
    "magaza", "urun", "sezon", "tedarikci", "siparis", "kalite_kontrol", "satis", "stok",
    "depo_stok", "sevkiyat", "takvim",
)

# Panelin `sevk`ine giren sevkiyat tipleri (depodan mağazaya)
SEVK_TIPLERI = ("ilk_dagitim", "replenishment")


def baglan(yol: Path | str | None = None):
    """v4 DuckDB dosyasına salt okunur bağlanır (ortak `kaynak.baglan`)."""
    return ortak.baglan(yol)


def gecmis_sezonlar(oyun_sezonu: str) -> tuple[str, ...]:
    """Oyun sezonundan önce eksiksiz kapanmış sezonlar, kronolojik.

    AW24 → SS23, AW23, SS24; SS25 → SS23, AW23, SS24, AW24."""
    if oyun_sezonu not in TAM_SEZONLAR:
        raise ValueError(f"{oyun_sezonu} tam sezon değil; seçenekler: {TAM_SEZONLAR}")
    return TAM_SEZONLAR[:TAM_SEZONLAR.index(oyun_sezonu)]


def _nesne(df: pd.DataFrame) -> pd.DataFrame:
    """DuckDB ENUM sütunlarını (pandas category) düz string sütuna çevirir.

    Category sütunlarla groupby / merge, gözlenmeyen kombinasyonları
    üretebilir; `astype(object)` kategori nesnelerini paylaştığı için bellek
    maliyeti sütun başına bir işaretçidir."""
    for k in df.columns:
        if isinstance(df[k].dtype, pd.CategoricalDtype):
            df[k] = df[k].astype(object)
    return df


def veri_yukle(yol: Path | str | None = None, sezonlar=TAM_SEZONLAR) -> dict[str, pd.DataFrame]:
    """Yayımlanan v4'ten temiz tablo sözlüğü.

    Temizlik ortak görünümlerle, TÜM tablo üstünde yapılır (hayalet imzası
    bütün stok tarihine bakar); sonra hareket tabloları `sezonlar`ın
    ürünleriyle sınırlanır (bellek). `depo_stok` yalnız pazartesi fotoğrafları.
    Ana veri tabloları (magaza, urun, sezon, tedarikci, siparis,
    kalite_kontrol, takvim) tam gelir."""
    sezonlar = list(sezonlar)
    yer = ", ".join("?" * len(sezonlar))
    kapsam = f"(select urun_id from urun where sezon_kodu in ({yer}))"
    with baglan(yol) as con:
        ts = ortak.temiz_satis(con)
        cesit = ortak.cesit_hucreleri(con)
        sorgu = {
            "satis": f"select * from {ts} where urun_id in {kapsam} order by tarih, magaza_id, urun_id",
            "stok": f"select s.* from stok s join {cesit} c using (magaza_id, urun_id) "
                    f"where s.urun_id in {kapsam} order by s.tarih, s.magaza_id, s.urun_id",
            "depo_stok": f"select * from depo_stok where dayofweek(tarih) = 1 and urun_id in {kapsam} "
                         "order by tarih, urun_id",
            "sevkiyat": f"select * from sevkiyat where urun_id in {kapsam} order by tarih, urun_id, hedef",
        }
        t = {}
        for ad in TABLOLAR:
            if ad in sorgu:
                t[ad] = con.execute(sorgu[ad], sezonlar).df()
            else:
                t[ad] = con.execute(f"select * from {ad}").df()
    return {ad: _nesne(df) for ad, df in t.items()}


def temizle(t: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Tablo sözlüğünü ortak görünümlerle temizler (mükerrer satış, hayalet stok).

    `veri_yukle` ham DuckDB'de aynı görünümleri kullanır; bu fonksiyon
    sözlük girdileri içindir (testler, harici tablolar). `satis`, `stok`,
    `sevkiyat` ve `urun` tablolarını içermelidir."""
    import duckdb

    con = duckdb.connect()
    try:
        for ad in ("satis", "stok", "sevkiyat", "urun"):
            con.register(ad, t[ad])
        ts = ortak.temiz_satis(con)
        cesit = ortak.cesit_hucreleri(con)
        t = dict(t)
        t["satis"] = _nesne(con.execute(
            f"select * from {ts} order by tarih, magaza_id, urun_id").df())
        t["stok"] = _nesne(con.execute(
            f"select s.* from stok s join {cesit} c using (magaza_id, urun_id) "
            "order by s.tarih, s.magaza_id, s.urun_id").df())
    finally:
        con.close()
    return t


def optionlar(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Sezonluk option'ların öznitelikleri (yalnız tablolardan).

    Tedarikçi alanları (`rpt_hafta`, `moq_option`, `mense`, `uzmanlik`,
    `ilk_siparis_hafta`) `urun.tedarikci_id` üstünden tedarikçi tablosundan
    gelir. `ilk_alim`, `siparis` tablosundaki tip='ilk' satırlarının
    toplamıdır — zincirin kendi kayıtlarında bildiği sayı.
    """
    urun = t["urun"]
    opt = urun[urun["sezon_kodu"] != "DEVAMLI"].drop_duplicates("option_id")[
        ["option_id", "model_kodu", "model_adi", "renk", "cinsiyet", "ust_kategori",
         "alt_kategori", "line", "sezon_kodu", "dalga", "lansman_tarihi", "cikis_tarihi",
         "tedarikci_id", "alis_fiyati", "liste_fiyati"]
    ].copy()
    sezon = t["sezon"].drop_duplicates("sezon_kodu")[["sezon_kodu", "indirim_baslangic"]]
    opt = opt.merge(sezon, on="sezon_kodu", how="left")
    opt = opt.merge(
        t["tedarikci"][["tedarikci_id", "ad", "ulke", "mense", "rpt_hafta", "moq_option",
                        "ilk_siparis_hafta", "uzmanlik"]].rename(columns={"ad": "tedarikci"}),
        on="tedarikci_id", how="left",
    )
    ilk = t["siparis"].query("tip == 'ilk'").groupby("option_id")["adet"].sum()
    opt["ilk_alim"] = opt["option_id"].map(ilk).fillna(0).astype(int)
    opt["dalga"] = opt["dalga"].astype(int)
    for k in ("lansman_tarihi", "cikis_tarihi", "indirim_baslangic"):
        opt[k] = pd.to_datetime(opt[k])
    # Planlı satış haftası: lansmandan indirim başına (AW'de indirim
    # perşembe başlar; kesirli hafta)
    opt["satis_hafta"] = (opt["indirim_baslangic"] - opt["lansman_tarihi"]).dt.days / 7.0
    return opt.reset_index(drop=True)


def _hafta(tarih: pd.Series, lansman: pd.Series) -> np.ndarray:
    return ((tarih - lansman).dt.days // 7).to_numpy()


def hucre_hafta(t: dict[str, pd.DataFrame], opt: pd.DataFrame, sezonlar=TAM_SEZONLAR) -> pd.DataFrame:
    """(magaza_id, urun_id, h) paneli, lansmandan çıkışa kadar.

    satis        brüt satış (iadeler hariç), fiziksel mağaza; online yok
    stoklu_gun   h. haftada gün açılışında stoğu > 0 olan gün (0–7)
    acik_gun     h. haftada hücrenin açık olduğu gün (çıkış günü kapalı)
    satis_io, acik_io
                 aynıları yalnız indirim başından ÖNCEKİ günler için. AW'de
                 indirim perşembe başlar; o haftanın satışı ikiye bölünür.
                 Sezon talebi (eğri ve sansür) lansman → indirim başıdır.
    ilk_dagitim  hücrenin ilk dağıtımda aldığı (varan) adet (hafta satırlarında aynı)

    Hücre evreni: temiz `stok` fotoğrafında görünen (açık) mağaza × SKU
    çiftleri; ONL'nin stok satırı yoktur, evrende değildir.
    """
    opt = opt[opt["sezon_kodu"].isin(sezonlar)]
    urun = t["urun"][["urun_id", "option_id"]].merge(
        opt[["option_id", "lansman_tarihi", "cikis_tarihi", "indirim_baslangic"]], on="option_id"
    )

    stok = t["stok"].merge(urun, on="urun_id")
    stok = stok[(stok["tarih"] > stok["lansman_tarihi"]) & (stok["tarih"] <= stok["cikis_tarihi"])]
    stok = stok.assign(h=_hafta(stok["tarih"], stok["lansman_tarihi"]) - 1)
    hucreler = stok[["magaza_id", "urun_id", "option_id", "lansman_tarihi", "cikis_tarihi",
                     "indirim_baslangic"]].drop_duplicates(
        ["magaza_id", "urun_id"])

    son_h = ((hucreler["cikis_tarihi"] - hucreler["lansman_tarihi"]).dt.days + 6) // 7
    idx = np.repeat(np.arange(len(hucreler)), son_h.to_numpy())
    panel = hucreler.iloc[idx].reset_index(drop=True)
    panel["h"] = np.concatenate([np.arange(n) for n in son_h.to_numpy()])
    hafta_basi = panel["lansman_tarihi"] + pd.to_timedelta(7 * panel["h"], unit="D")
    panel["acik_gun"] = np.clip((panel["cikis_tarihi"] - hafta_basi).dt.days, 0, 7)
    panel["acik_io"] = np.clip((panel["indirim_baslangic"] - hafta_basi).dt.days, 0, 7)

    satis = t["satis"][(t["satis"]["adet"] > 0) & (t["satis"]["magaza_id"] != ONLINE)]
    anahtar = ["magaza_id", "urun_id", "h"]
    s = _satis_hafta(satis, urun, ["magaza_id", "urun_id", "h"], "satis")
    panel = panel.merge(s.reset_index(), on=anahtar, how="left")
    panel = panel.merge(stok[anahtar + ["stoklu_gun"]], on=anahtar, how="left")
    sv = t["sevkiyat"]
    ilk = sv[(sv["tip"] == "ilk_dagitim") & sv["varis_tarihi"].notna()].groupby(
        ["hedef", "urun_id"])["adet"].sum()
    ilk = ilk.rename("ilk_dagitim").reset_index().rename(columns={"hedef": "magaza_id"})
    panel = panel.merge(ilk, on=["magaza_id", "urun_id"], how="left")
    for k in ("satis", "satis_io", "stoklu_gun", "ilk_dagitim"):
        panel[k] = panel[k].fillna(0).astype(int)
    return panel[["magaza_id", "urun_id", "option_id", "h", "satis", "stoklu_gun",
                  "acik_gun", "satis_io", "acik_io", "ilk_dagitim"]]


def _satis_hafta(satis: pd.DataFrame, urun: pd.DataFrame, anahtar: list[str], ad: str) -> pd.DataFrame:
    """Pozitif satış satırlarını lansman → çıkış arasında haftalandırır;
    `ad` (hafta toplamı) ve `ad_io` (yalnız indirim öncesi günler) döndürür."""
    df = satis.merge(urun, on="urun_id")
    df = df[(df["tarih"] >= df["lansman_tarihi"]) & (df["tarih"] < df["cikis_tarihi"])]
    df = df.assign(h=_hafta(df["tarih"], df["lansman_tarihi"]),
                   _io=np.where(df["tarih"] < df["indirim_baslangic"], df["adet"], 0))
    g = df.groupby(anahtar)
    return pd.concat([g["adet"].sum().rename(ad), g["_io"].sum().rename(ad + "_io")], axis=1)


def option_panel(t: dict[str, pd.DataFrame], opt: pd.DataFrame, hh: pd.DataFrame | None = None,
                 sezonlar=TAM_SEZONLAR) -> pd.DataFrame:
    """(option_id, h) paneli: zincir toplamları ve haftabaşı fotoğrafları.

    magaza_satis, online_satis, satis (= ikisinin toplamı; STR payı),
    satis_io (indirim öncesi günler, mağaza + online), stoklu_gun ve acik_gun
    (hücre-gün, yalnız mağaza), sevk (mağazaya VARAN ilk dağıtım +
    replenishment, adet; varış haftasına), depo_stok ve magaza_stok (h.
    haftanın pazartesi sabahı), tasiyan_magaza (açık hücresi olan mağaza),
    stoklu_magaza (pazartesi sabahı en az bir bedeninde stok olan mağaza),
    kum_satis, kum_sevk (h. haftanın sonuna kadar).

    Pazartesi sabahı fotoğrafta depo ile mağaza arasında yolda kalan mal
    görünmez (o gün varacaklar, önceki günlerde çıkmış olabilir).
    """
    if hh is None:
        hh = hucre_hafta(t, opt, sezonlar)
    opt = opt[opt["sezon_kodu"].isin(sezonlar)]
    p = hh.groupby(["option_id", "h"])[["satis", "satis_io", "stoklu_gun", "acik_gun"]].sum().reset_index()
    p = p.rename(columns={"satis": "magaza_satis", "satis_io": "magaza_satis_io"})
    p = p.merge(opt[["option_id", "lansman_tarihi"]], on="option_id")
    p["hafta_basi"] = p["lansman_tarihi"] + pd.to_timedelta(7 * p["h"], unit="D")

    urun = t["urun"][["urun_id", "option_id"]].merge(
        opt[["option_id", "lansman_tarihi", "cikis_tarihi", "indirim_baslangic"]], on="option_id")

    # Online satış: stok satırı yok, hücre evreninde değil; option satışına girer
    onl = t["satis"][(t["satis"]["adet"] > 0) & (t["satis"]["magaza_id"] == ONLINE)]
    o = _satis_hafta(onl, urun, ["option_id", "h"], "online_satis").reset_index()
    p = p.merge(o, on=["option_id", "h"], how="left")
    for k in ("online_satis", "online_satis_io"):
        p[k] = p[k].fillna(0).astype(int)
    p["satis"] = p["magaza_satis"] + p["online_satis"]
    p["satis_io"] = p["magaza_satis_io"] + p["online_satis_io"]
    p = p.drop(columns=["magaza_satis_io", "online_satis_io"])

    sv = t["sevkiyat"]
    sevk = sv[sv["tip"].isin(SEVK_TIPLERI) & sv["varis_tarihi"].notna()].merge(urun, on="urun_id")
    sevk = sevk[sevk["varis_tarihi"] >= sevk["lansman_tarihi"]]
    sevk = sevk.assign(h=_hafta(sevk["varis_tarihi"], sevk["lansman_tarihi"]))
    p = p.merge(sevk.groupby(["option_id", "h"])["adet"].sum().rename("sevk").reset_index(),
                on=["option_id", "h"], how="left")

    def _fotograf(df):
        df = df.merge(urun[["urun_id", "option_id", "lansman_tarihi"]], on="urun_id")
        df = df[df["tarih"] >= df["lansman_tarihi"]]
        return df.assign(h=_hafta(df["tarih"], df["lansman_tarihi"]))

    # Günlük depo stoğundan yalnız pazartesi fotoğrafları (lansman günü pazartesidir)
    d = _fotograf(t["depo_stok"])
    d = d[(d["tarih"] - d["lansman_tarihi"]).dt.days % 7 == 0]
    depo = d.groupby(["option_id", "h"])["adet"].sum().rename("depo_stok")
    ms = _fotograf(t["stok"])
    ms = ms[(ms["tarih"] - ms["lansman_tarihi"]).dt.days % 7 == 0]
    magaza_opt = ms.groupby(["option_id", "h", "magaza_id"])["adet"].sum().reset_index()
    ozet = magaza_opt.groupby(["option_id", "h"]).agg(
        magaza_stok=("adet", "sum"),
        stoklu_magaza=("adet", lambda a: int((a > 0).sum())),
    )
    tasiyan = hh.groupby("option_id")["magaza_id"].nunique().rename("tasiyan_magaza")
    p = p.merge(depo.reset_index(), on=["option_id", "h"], how="left")
    p = p.merge(ozet.reset_index(), on=["option_id", "h"], how="left")
    p = p.merge(tasiyan.reset_index(), on="option_id", how="left")
    for k in ("sevk", "depo_stok", "magaza_stok", "stoklu_magaza"):
        p[k] = p[k].fillna(0).astype(int)
    p = p.sort_values(["option_id", "h"]).reset_index(drop=True)
    p["kum_satis"] = p.groupby("option_id")["satis"].cumsum()
    p["kum_sevk"] = p.groupby("option_id")["sevk"].cumsum()
    return p.drop(columns="lansman_tarihi")


def tarihten_once(t: dict[str, pd.DataFrame], sinir) -> dict[str, pd.DataFrame]:
    """Tabloları `sinir` gününün sabahına kırpar: o güne kadar bilinen.

    Hareketler (satış, sevkiyat) `sinir`den önceki günler; pazartesi
    fotoğrafları (stok, depo_stok) `sinir` dahil — fotoğraf günün hiçbir
    hareketinden önce çekilir, karar sabahı elde vardır.

    Gelecek bilgisi de kırpılır: `sinir`e dek varmamış sevkiyatın
    `varis_tarihi`, `sinir`e dek teslim olmamış siparişin `gerceklesen_teslim`i
    boşaltılır (yolda / bekleyen; çıkış ve sipariş bilinir, varış bilinmez);
    planlanan teslim sipariş anında bilinir, kalır. Kalite kontrol teslim
    tarihine göre kırpılır.

    Sızıntı kalkanının temeli: bir oyun sezonu için öğrenilen her şey
    (eğri, kalibrasyon) bu kırpılmış tablolardan öğrenilir. Ana veri
    tabloları (urun, sezon, tedarikçi, mağaza) takvim gibi önceden
    bilinir ve kırpılmaz. Siparişler sipariş tarihine göre kırpılır.
    """
    sinir = pd.Timestamp(sinir)
    t = dict(t)
    t["satis"] = t["satis"][t["satis"]["tarih"] < sinir].reset_index(drop=True)
    sv = t["sevkiyat"][t["sevkiyat"]["tarih"] < sinir].copy()
    sv["varis_tarihi"] = sv["varis_tarihi"].where(sv["varis_tarihi"] < sinir, pd.NaT)
    t["sevkiyat"] = sv.reset_index(drop=True)
    for ad in ("stok", "depo_stok"):
        t[ad] = t[ad][t[ad]["tarih"] <= sinir].reset_index(drop=True)
    sp = t["siparis"][t["siparis"]["siparis_tarihi"] < sinir].copy()
    sp["gerceklesen_teslim"] = sp["gerceklesen_teslim"].where(sp["gerceklesen_teslim"] < sinir, pd.NaT)
    t["siparis"] = sp.reset_index(drop=True)
    if "kalite_kontrol" in t:
        k = t["kalite_kontrol"]
        t["kalite_kontrol"] = k[k["teslim_tarihi"] < sinir].reset_index(drop=True)
    return t


def sezon_baslangici(t: dict[str, pd.DataFrame], sezon_kodu: str) -> pd.Timestamp:
    s = t["sezon"]
    return pd.Timestamp(s.loc[s["sezon_kodu"] == sezon_kodu, "lansman_tarihi"].min())
