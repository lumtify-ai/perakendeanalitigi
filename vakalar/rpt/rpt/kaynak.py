"""v3 tablolarını okur; sezonluk option'lar için hücre-hafta ve option-hafta
panelleri kurar.

Vakanın bütün analizi bu iki panelin üstünde durur:

    hucre_hafta   (mağaza × SKU × lansmandan beri hafta)  satış, kayıp,
                  stoklu gün, açık gün, ilk dağıtım adedi
    option_panel  (option × hafta)  zincir toplamları + pazartesi
                  fotoğrafları (depo, mağaza stoğu, taşıyan / stoklu mağaza)

HAFTA TANIMI. Sezonluk ürün pazartesi lanse edilir; h. hafta
[lansman + 7h, lansman + 7h + 7) günleridir. h. haftanın stoklu günü,
v3'ün `stok` tablosunda (lansman + 7(h+1)) pazartesisinin fotoğrafındadır
(`stoklu_gun` önceki 7 günü sayar). h. haftanın pazartesi fotoğrafı
(depo, mağaza stoğu) haftanın başındaki, o günün hiçbir hareketinden
önceki durumdur: h = 0'da mağazalar henüz boştur.

KAYIP SATIŞ yalnız doğruluk ölçüsüdür (gerçek talep = satış + kayıp). Hiçbir
kestirim ve hiçbir politika onu okumaz; `sansur.py` bunu testle kilitler.

KİRLİ KAYITLAR. v3 üç tür kirli kayıt taşır (README): mükerrer satış satırı,
bedelsiz satış, hayalet stok. Adet analizinde ilk ve üçüncüsü önemlidir;
`temizle()` onları ayıklar (motor bir hücrenin bir gününe tek pozitif satış
satırı yazar; hayalet stok, hiç sevkiyatı, satışı ve kaybı olmayan bir
mağaza × SKU çiftinde durur).

Paneller tablo sözlüğü alır; aynı fonksiyonlar Faz B'de karşı-olgusal
kolların çıktısına (`perakende_veri.v3.uret.hareket_tablolari`) da uygulanır.
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

VERITABANI = Path(__file__).resolve().parents[3] / "veri" / "cikti" / "v3" / "perakende.duckdb"

OYUN_SEZONLARI = ("AW24", "SS25")
# Pencerede lansmandan indirime kadar eksiksiz görünen sezonlar. AW23'ün
# indirimi 2024-01-02'de başlar, pencere 2024-01-01'de açılır: AW23'ten
# indirim öncesine dair tek gün var, eğri öğrenmeye yaramaz. AW25'in
# indirimi pencerenin dışındadır.
TAM_SEZONLAR = ("SS24", "AW24", "SS25")

TABLOLAR = (
    "magaza", "urun", "sezon", "tedarikci", "siparis", "satis", "stok",
    "depo_stok", "sevkiyat", "kayip_satis", "takvim",
)


def tablolari_oku(yol: Path | str = VERITABANI) -> dict[str, pd.DataFrame]:
    """DuckDB'deki v3 tablolarını okur (temizlemeden)."""
    yol = Path(yol)
    if not yol.exists():
        raise FileNotFoundError(
            f"{yol} yok. Önce: cd veri && .venv/Scripts/python -m perakende_veri.v3.uret"
        )
    with duckdb.connect(str(yol), read_only=True) as c:
        return {t: c.execute(f"select * from {t}").df() for t in TABLOLAR}


def temizle(t: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Mükerrer pozitif satış satırlarını ve hayalet stok satırlarını atar."""
    t = dict(t)
    satis = t["satis"]
    poz = satis[satis["adet"] > 0]
    mukerrer = poz.index[poz.duplicated(["tarih", "magaza_id", "urun_id"])]
    t["satis"] = satis.drop(index=mukerrer).reset_index(drop=True)

    # Hayalet: hiç hareketi olmayan VE yalnız bir iki fotoğrafta görünen çift.
    # Gerçek hücre açık olduğu her pazartesi fotoğraftadır (en kısa ömür,
    # pencereye giren AW23 kuyruğu, 9 pazartesi); hareketsiz ama gerçek
    # hücreler (sıfır talepli "ölü" hücre) böylece korunur.
    anahtar = ["magaza_id", "urun_id"]
    hareketli = pd.concat(
        [t[ad][anahtar] for ad in ("sevkiyat", "satis", "kayip_satis")]
    ).drop_duplicates().assign(_hareket=True)
    sayi = t["stok"].groupby(anahtar).size().rename("_sayi").reset_index()
    stok = t["stok"].merge(hareketli, on=anahtar, how="left").merge(sayi, on=anahtar)
    hayalet = stok["_hareket"].isna() & (stok["_sayi"] <= 2)
    t["stok"] = stok[~hayalet].drop(columns=["_hareket", "_sayi"]).reset_index(drop=True)
    return t


def veri_yukle(yol: Path | str = VERITABANI) -> dict[str, pd.DataFrame]:
    return temizle(tablolari_oku(yol))


def optionlar(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Sezonluk option'ların öznitelikleri (yalnız tablolardan).

    `ilk_alim`, `siparis` tablosundaki tip='ilk' satırlarının toplamıdır —
    zincirin kendi kayıtlarında bildiği sayı.
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
        t["tedarikci"][["tedarikci_id", "ad", "ulke", "mense", "rpt_hafta", "moq_option"]]
        .rename(columns={"ad": "tedarikci"}),
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


def plan_ekle(opt: pd.DataFrame, dunya) -> pd.DataFrame:
    """Buyer'ın planını (lansman → indirim başı plan talebi) ekler.

    Plan tablolarda yok, dünyada (`dunya_kur().optionlar.plan_sezon`); ama
    gizli değildir: ilk alım ondan hesaplandı, zincir bu sayıyı bilir.
    Sürpriz ve gerçek beklenen talep ise gizlidir ve buradan okunmaz.
    """
    plan = dunya.optionlar.set_index("option_id")["plan_sezon"]
    opt = opt.copy()
    opt["plan_sezon"] = opt["option_id"].map(plan).astype(float)
    return opt


def _hafta(tarih: pd.Series, lansman: pd.Series) -> np.ndarray:
    return ((tarih - lansman).dt.days // 7).to_numpy()


def hucre_hafta(t: dict[str, pd.DataFrame], opt: pd.DataFrame, sezonlar=TAM_SEZONLAR) -> pd.DataFrame:
    """(magaza_id, urun_id, h) paneli, lansmandan çıkışa kadar.

    satis        brüt satış (iadeler hariç)
    kayip        kayıp satış — YALNIZ doğruluk ölçüsü
    stoklu_gun   h. haftada gün açılışında stoğu > 0 olan gün (0–7)
    acik_gun     h. haftada hücrenin açık olduğu gün (çıkış günü kapalı)
    satis_io, kayip_io, acik_io
                 aynıları yalnız indirim başından ÖNCEKİ günler için. AW'de
                 indirim perşembe başlar; o haftanın satışı ikiye bölünür.
                 Sezon talebi (eğri ve sansür) lansman → indirim başıdır.
    ilk_dagitim  hücrenin ilk dağıtımda aldığı adet (hafta satırlarında aynı)
    """
    opt = opt[opt["sezon_kodu"].isin(sezonlar)]
    urun = t["urun"][["urun_id", "option_id"]].merge(
        opt[["option_id", "lansman_tarihi", "cikis_tarihi", "indirim_baslangic"]], on="option_id"
    )

    # Hücre evreni: stok fotoğrafında görünen (açık) mağaza × SKU çiftleri
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

    def _haftalik(df, deger, ad):
        df = df.merge(urun, on="urun_id")
        df = df[(df["tarih"] >= df["lansman_tarihi"]) & (df["tarih"] < df["cikis_tarihi"])]
        df = df.assign(h=_hafta(df["tarih"], df["lansman_tarihi"]),
                       _io=np.where(df["tarih"] < df["indirim_baslangic"], df[deger], 0))
        g = df.groupby(["magaza_id", "urun_id", "h"])
        return pd.concat([g[deger].sum().rename(ad), g["_io"].sum().rename(ad + "_io")], axis=1)

    satis = t["satis"][t["satis"]["adet"] > 0]
    anahtar = ["magaza_id", "urun_id", "h"]
    panel = panel.merge(_haftalik(satis, "adet", "satis").reset_index(), on=anahtar, how="left")
    panel = panel.merge(_haftalik(t["kayip_satis"], "kayip_adet", "kayip").reset_index(), on=anahtar, how="left")
    panel = panel.merge(stok[anahtar + ["stoklu_gun"]], on=anahtar, how="left")
    ilk = t["sevkiyat"].query("tip == 'ilk_dagitim'").groupby(["magaza_id", "urun_id"])["adet"].sum()
    panel = panel.merge(ilk.rename("ilk_dagitim").reset_index(), on=["magaza_id", "urun_id"], how="left")
    for k in ("satis", "kayip", "satis_io", "kayip_io", "stoklu_gun", "ilk_dagitim"):
        panel[k] = panel[k].fillna(0).astype(int)
    return panel[["magaza_id", "urun_id", "option_id", "h", "satis", "kayip", "stoklu_gun",
                  "acik_gun", "satis_io", "kayip_io", "acik_io", "ilk_dagitim"]]


def option_panel(t: dict[str, pd.DataFrame], opt: pd.DataFrame, hh: pd.DataFrame | None = None,
                 sezonlar=TAM_SEZONLAR) -> pd.DataFrame:
    """(option_id, h) paneli: zincir toplamları ve haftabaşı fotoğrafları.

    satis, kayip, talep (= satis + kayip, doğruluk), stoklu_gun ve acik_gun
    (hücre-gün), sevk (ilk dağıtım + replenishment, adet), depo_stok ve
    magaza_stok (h. haftanın pazartesi sabahı), tasiyan_magaza (açık hücresi
    olan mağaza), stoklu_magaza (pazartesi sabahı en az bir bedeninde stok
    olan mağaza), kum_satis, kum_sevk (h. haftanın sonuna kadar).
    """
    if hh is None:
        hh = hucre_hafta(t, opt, sezonlar)
    opt = opt[opt["sezon_kodu"].isin(sezonlar)]
    p = hh.groupby(["option_id", "h"])[
        ["satis", "kayip", "stoklu_gun", "acik_gun", "satis_io", "kayip_io"]].sum().reset_index()
    p["talep"] = p["satis"] + p["kayip"]
    p = p.merge(opt[["option_id", "lansman_tarihi"]], on="option_id")
    p["hafta_basi"] = p["lansman_tarihi"] + pd.to_timedelta(7 * p["h"], unit="D")

    urun = t["urun"][["urun_id", "option_id"]].merge(opt[["option_id", "lansman_tarihi"]], on="option_id")

    sevk = t["sevkiyat"][t["sevkiyat"]["tip"] != "geri_toplama"].merge(urun, on="urun_id")
    sevk = sevk[sevk["tarih"] >= sevk["lansman_tarihi"]]
    sevk = sevk.assign(h=_hafta(sevk["tarih"], sevk["lansman_tarihi"]))
    p = p.merge(sevk.groupby(["option_id", "h"])["adet"].sum().rename("sevk").reset_index(),
                on=["option_id", "h"], how="left")

    def _fotograf(df, deger):
        df = df.merge(urun, on="urun_id")
        df = df[df["tarih"] >= df["lansman_tarihi"]]
        return df.assign(h=_hafta(df["tarih"], df["lansman_tarihi"]))

    depo = _fotograf(t["depo_stok"], "adet").groupby(["option_id", "h"])["adet"].sum().rename("depo_stok")
    ms = _fotograf(t["stok"], "adet")
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

    Hareketler (satış, kayıp, sevkiyat) `sinir`den önceki günler; pazartesi
    fotoğrafları (stok, depo_stok) `sinir` dahil — fotoğraf günün hiçbir
    hareketinden önce çekilir, karar sabahı elde vardır.

    Sızıntı kalkanının temeli: bir oyun sezonu için öğrenilen her şey
    (eğri, kalibrasyon) bu kırpılmış tablolardan öğrenilir. Ana veri
    tabloları (urun, sezon, tedarikçi, mağaza) takvim gibi önceden
    bilinir ve kırpılmaz. Siparişler sipariş tarihine göre kırpılır.
    """
    sinir = pd.Timestamp(sinir)
    t = dict(t)
    for ad in ("satis", "sevkiyat", "kayip_satis"):
        t[ad] = t[ad][t[ad]["tarih"] < sinir].reset_index(drop=True)
    for ad in ("stok", "depo_stok"):
        t[ad] = t[ad][t[ad]["tarih"] <= sinir].reset_index(drop=True)
    t["siparis"] = t["siparis"][t["siparis"]["siparis_tarihi"] < sinir].reset_index(drop=True)
    return t


def sezon_baslangici(t: dict[str, pd.DataFrame], sezon_kodu: str) -> pd.Timestamp:
    s = t["sezon"]
    return pd.Timestamp(s.loc[s["sezon_kodu"] == sezon_kodu, "lansman_tarihi"].min())
