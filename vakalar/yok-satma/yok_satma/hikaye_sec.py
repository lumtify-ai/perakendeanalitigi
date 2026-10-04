"""Yazı 1'in açılış hikâyesinin ürünü: deterministik arama (spec §6.2, §7.1).

`python -m yok_satma.hikaye_sec` ilk 10 adayı ve seçileni (gevşetilen
ölçütlerle) basar. Hikâye: Ali ile Veli aynı ürünü ister, ikisi de bedenini
bulamaz; ürün merkez depodadır, önceki gece girmiştir (geç gelen tedarikçi
siparişi). Yani kayıp allocation'ın değil tedarikin / buying'in.

Ölçütler (numaraları gevşetme sırasında ve `gevsetilen`de kullanılır):

    1 cinsiyet                 ürünün `cinsiyet`i Erkek ya da Unisex
    2 veli_bolgesi             Veli'nin bölgesi: fiziksel mağaza, `magaza.sehir != "İstanbul"`
                               (R27: hikâye mağazası Veli'nin; Veli raporluyken mağazalarını
                               Ali yönetti; depodan-mağazaya dizisinde İstanbul Ali'de,
                               Anadolu Veli'de). `tip == Online` elenir
    3 iki_beden                aynı option'ın iki ayrı bedeni (SKU) o mağazada o gün `bos`
    4 onceki_gece_gec_teslim   iki SKU'nun da bir siparişi `tarih - 1 gün` teslim
                               edilmiş ve planlanandan geç (`gerceklesen_teslim >
                               planlanan_teslim`); depoya giriş bu gündür
    5 tedarik                  iki SKU'nun o günkü kaybı (Basit) pozitif ve
                               `kaynak == "tedarik"`; kaybı 0 olan bir satırın
                               tedarike yazılması hikâyeyi taşımaz, o yüzden
                               `kayip > 0` ölçütün parçasıdır
    6 donem_kayip              option'ın BU stoksuzluk dönemindeki zincir kaybı
                               (Basit `kayip`, bütün mağazalar ve ONL, `bos` ve
                               `tukenen` günleri) >= 1 adet (R23)

Dönem (R23): iki SKU'dan birinin depoda (`depo_stok.adet > 0`) son stoklu
olduğu gün d* (en geç `tarih - 1`); dönem d* + 1 .. `tarih - 1` (uçlar dahil).
İkisinin de depoda hiç stoklu günü yoksa dönem `depo_stok` kaydının ilk
gününde başlar. `donem_gun` = `tarih - baslangıç` (gün sayısı), `donem_kayip`
= option'ın (iki SKU değil, bütün bedenleri) o aralıktaki kaybı. Eski ölçüt
(tarihe kadar bütün birikim) yalnız bağlam için `birikmis_kayip` sütununda
durur: çok eski, çok satan bir option'ın ömür boyu kaybı hikâyenin "kayıp
oluşmaya başlamıştır"ını anlatmaz.

Aday = (option, mağaza, gün). Bir grupta ölçütleri tutan SKU'lardan
`beden_sira`sı en küçük iki tanesi seçilir: küçük olan Ali, büyük olan Veli.
Sıralama: dönem kaybı azalan, sonra option_id, tarih, magaza_id.

Gevşetme (R21): sıkı aramada aday yoksa TEK ölçüt düşürülür, sırayla 6, 5, 4,
3, 2, 1; ilk aday veren seçilir. Hiçbiri vermezse ikili kombinasyonlar aynı
öncelikle (6-5, 6-4, 6-3, 6-2, 6-1, 5-4, ...) denenir. Ölçüt 3 düşerse tek bir
`bos` SKU yeter ve `urun_id_ali == urun_id_veli` olur. `gevsetilen` kısa
adların listesidir (ölçüt numarası artan sırada).

Elle seçim (R24): `denetle` verilen bir (option, mağaza, gün) adayının hangi
ölçütleri tutmadığını söyler (adayı veren en küçük gevşetme kümesi);
`secim_ve_adaylar(..., hikaye=...)` seçimi o adaya çevirir. `rapor.py --hikaye`
bunu kullanır.

Bellek: günlük tablodan yalnız `bos` satırları ve dört sütun, kayıp
tablosundan yedi sütun okunur (pyarrow süzgeci); içeride kimlikler tamsayı
koda çevrilir. Gizli gerçeğe (`hakem`) dokunulmaz.
"""

import argparse
import copy
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from perakende_analitik import kaynak

VARSAYILAN_CIKTI = Path(__file__).resolve().parents[1] / "cikti"

OLCUTLER = {1: "cinsiyet", 2: "veli_bolgesi", 3: "iki_beden", 4: "onceki_gece_gec_teslim",
            5: "tedarik", 6: "donem_kayip"}
GEVSETME_SIRASI = (6, 5, 4, 3, 2, 1)        # sondan başa
CINSIYETLER = ("Erkek", "Unisex")
ALI_SEHRI = "İstanbul"                       # Ali'nin bölgesi; Veli'ninki dışı
EN_AZ_DONEM_KAYBI = 1.0                      # adet
HATLAR = ("Collection", "Basic", "NOS", "Outlet")
_K = 1 << 20                                 # (id, gün) tamsayı anahtarı için gün çarpanı

ADAY_SUTUNLARI = ["option_id", "model_adi", "renk", "line", "magaza_id", "tarih",
                  "urun_id_ali", "urun_id_veli", "donem_baslangic", "donem_gun",
                  "donem_kayip", "birikmis_kayip", "depoya_giris", "planlanan_teslim_ali",
                  "gerceklesen_teslim_ali", "planlanan_teslim_veli", "gerceklesen_teslim_veli"]


# ----------------------------------------------------------------- yardımcılar

def _gun(seri: pd.Series) -> np.ndarray:
    """datetime64 serisi -> 1970'ten beri gün sayısı (int64)."""
    return pd.to_datetime(seri).to_numpy().astype("datetime64[D]").astype("int64")


def _tarih(gun: np.ndarray) -> pd.Series:
    return pd.Series(gun.astype("datetime64[D]").astype("datetime64[ns]"))


def _kodla(seri: pd.Series, evren: pd.Index, ad: str) -> np.ndarray:
    """Kimlik serisi -> `evren`deki sıra no (int64); evrende olmayan hata verir."""
    if isinstance(seri.dtype, pd.CategoricalDtype):
        harita = evren.get_indexer(seri.cat.categories.astype(str))
        kod = seri.cat.codes.to_numpy()
        sonuc = np.where(kod >= 0, harita[np.maximum(kod, 0)], -1)
    else:
        sonuc = evren.get_indexer(seri.astype(str))
    if (sonuc < 0).any():
        raise ValueError(f"{ad}: boyut tablosunda olmayan kimlik var")
    return sonuc.astype("int64")


class _Hazir:
    """Bir aramanın değişmeyen girdileri: tamsayı kodlu `bos` satırları,
    ölçüt 4 ve 5 anahtarları, birikmiş kayıp tablosu."""

    def __init__(self, con, gunluk: pd.DataFrame, kayip: pd.DataFrame):
        urun = con.execute("select urun_id, option_id, cinsiyet, beden_sira, model_adi, renk, "
                           "line from urun "
                           "order by urun_id").df()
        magaza = con.execute("select magaza_id, sehir, tip from magaza order by magaza_id").df()
        late = con.execute("select siparis_id, urun_id, planlanan_teslim, gerceklesen_teslim "
                           "from siparis where gerceklesen_teslim > planlanan_teslim").df()

        self.urunler = pd.Index(urun["urun_id"].astype(str))
        self.magazalar = pd.Index(magaza["magaza_id"].astype(str))
        self.opsiyonlar = pd.Index(np.unique(urun["option_id"].astype(str)))
        self.sku_option = self.opsiyonlar.get_indexer(urun["option_id"].astype(str))
        self.con = con
        self.sku_sira = urun["beden_sira"].to_numpy("int64")
        self.sku_bilgi = urun[["model_adi", "renk", "line"]].reset_index(drop=True)
        # depo kaydının ilk günü: hiç stoklu günü olmayan SKU'nun dönemi buradan başlar
        ilk = con.execute("select min(tarih) from depo_stok").fetchone()[0]
        self.depo_ilk = int(_gun(pd.Series([ilk]))[0]) if ilk is not None else 0
        self.sku_erkek = urun["cinsiyet"].isin(CINSIYETLER).to_numpy()
        self.magaza_veli = ((magaza["sehir"] != ALI_SEHRI) & (magaza["tip"] != "Online")).to_numpy()
        nu, nm = len(self.urunler), len(self.magazalar)
        self._nu, self._nm = nu, nm

        # --- stoksuz (bos) SKU-günler
        if "durum" in gunluk.columns:
            gunluk = gunluk[gunluk["durum"] == "bos"]
        self.gun = _gun(gunluk["tarih"])
        self.mag = _kodla(gunluk["magaza_id"], self.magazalar, "gunluk.magaza_id")
        self.sku = _kodla(gunluk["urun_id"], self.urunler, "gunluk.urun_id")
        self.opt = self.sku_option[self.sku]

        # --- ölçüt 4: (SKU, teslim günü) anahtarı; aynı anahtarda en geç kalan sipariş
        late = late.dropna(subset=["gerceklesen_teslim"]).copy()
        late["sku"] = _kodla(late["urun_id"], self.urunler, "siparis.urun_id")
        late["ger"] = _gun(late["gerceklesen_teslim"])
        late["gecikme"] = late["ger"] - _gun(late["planlanan_teslim"])
        late = late.sort_values(["sku", "ger", "gecikme", "siparis_id"],
                                ascending=[True, True, False, True], kind="stable")
        late = late.drop_duplicates(["sku", "ger"]).reset_index(drop=True)
        late["anahtar"] = late["sku"] * _K + late["ger"]
        self.late = late                                   # anahtara göre sıralı
        self.f4 = np.isin(self.sku * _K + (self.gun - 1), late["anahtar"].to_numpy())

        # --- ölçüt 5: kaynağı tedarik, kaybı pozitif (gün, mağaza, SKU)
        ked = kayip[(kayip["kaynak"] == "tedarik") & (kayip["kayip"] > 0)]
        anahtar5 = self._anahtar(_gun(ked["tarih"]),
                                 _kodla(ked["magaza_id"], self.magazalar, "kayip.magaza_id"),
                                 _kodla(ked["urun_id"], self.urunler, "kayip.urun_id"))
        self.f5 = np.isin(self._anahtar(self.gun, self.mag, self.sku), anahtar5)

        # --- ölçüt 6: option başına günlük kayıp toplamı ve içeren birikim
        opt_k = self.sku_option[_kodla(kayip["urun_id"], self.urunler, "kayip.urun_id")]
        gun_k = _gun(kayip["tarih"])
        toplam = kayip["kayip"].fillna(0.0).to_numpy("float64")
        gunluk_kayip = pd.Series(toplam).groupby(opt_k * _K + gun_k).sum().sort_index()
        self.birikim_anahtar = gunluk_kayip.index.to_numpy("int64")
        self.birikim = gunluk_kayip.groupby(self.birikim_anahtar // _K).cumsum().to_numpy()

    def daralt(self, option_id: str, magaza_id: str, tarih) -> "_Hazir":
        """Yalnız tek (option, mağaza, gün) `bos` satırlarını taşıyan kopya (`denetle` için)."""
        o = self.opsiyonlar.get_indexer([str(option_id)])[0]
        m = self.magazalar.get_indexer([str(magaza_id)])[0]
        if o < 0 or m < 0:
            raise LookupError(f"bilinmeyen option ya da magaza: {option_id}, {magaza_id}")
        g = int(_gun(pd.Series([pd.Timestamp(tarih)]))[0])
        maske = (self.opt == o) & (self.mag == m) & (self.gun == g)
        dar = copy.copy(self)
        for ad in ("gun", "mag", "sku", "opt", "f4", "f5"):
            setattr(dar, ad, getattr(self, ad)[maske])
        return dar

    def _anahtar(self, gun, mag, sku):
        return (gun * self._nm + mag) * self._nu + sku

    def onceki_birikim(self, opt: np.ndarray, gun: np.ndarray) -> np.ndarray:
        """`gun`den ÖNCEKİ günlerin (gün dahil değil) option kayıp birikimi."""
        yer = np.searchsorted(self.birikim_anahtar, opt * _K + gun, side="left") - 1
        gecerli = (yer >= 0) & (self.birikim_anahtar[np.maximum(yer, 0)] // _K == opt)
        return np.where(gecerli, self.birikim[np.maximum(yer, 0)], 0.0)

    def son_stoklu_gun(self, sku: np.ndarray, gun: np.ndarray) -> np.ndarray:
        """Her (SKU, gün) için `gun`den önceki en son depo-stoklu gün (adet > 0);
        yoksa depo kaydının ilk gününden bir önceki gün."""
        girdi = pd.DataFrame({"urun_id": self.urunler[sku].to_numpy(), "tarih": _tarih(gun)})
        self.con.register("_aday_depo", girdi.drop_duplicates())
        try:
            son = self.con.execute(
                "select c.urun_id, c.tarih, max(d.tarih) as son from _aday_depo c "
                "left join depo_stok d on d.urun_id = c.urun_id and d.tarih < c.tarih "
                "and d.adet > 0 group by c.urun_id, c.tarih").df()
        finally:
            self.con.unregister("_aday_depo")
        son = girdi.merge(son, on=["urun_id", "tarih"], how="left")["son"]
        return np.where(son.notna(), _gun(son.fillna(pd.Timestamp("1970-01-01"))),
                        self.depo_ilk - 1)

    def teslim(self, sku: np.ndarray, gun: np.ndarray) -> tuple[pd.Series, pd.Series]:
        """`gun - 1` günü teslim edilen (geç) siparişin planlanan ve gerçekleşen tarihi (NaT olabilir)."""
        anahtar = self.late["anahtar"].to_numpy()
        if len(anahtar) == 0:
            bos = pd.Series(pd.NaT, index=range(len(sku)), dtype="datetime64[ns]")
            return bos, bos.copy()
        ara = sku * _K + (gun - 1)
        yer = np.minimum(np.searchsorted(anahtar, ara), len(anahtar) - 1)
        var = anahtar[yer] == ara
        planlanan = self.late["planlanan_teslim"].to_numpy("datetime64[ns]")[yer]
        gerceklesen = self.late["gerceklesen_teslim"].to_numpy("datetime64[ns]")[yer]
        nat = np.datetime64("NaT", "ns")
        return (pd.Series(np.where(var, planlanan, nat), dtype="datetime64[ns]"),
                pd.Series(np.where(var, gerceklesen, nat), dtype="datetime64[ns]"))


# ----------------------------------------------------------------------- arama

def _adaylar(h: _Hazir, gevset: frozenset[int]) -> pd.DataFrame:
    """`gevset` ölçütleri düşürülmüş aday tablosu (sıralı)."""
    maske = np.ones(len(h.gun), bool)
    if 1 not in gevset:
        maske &= h.sku_erkek[h.sku]
    if 2 not in gevset:
        maske &= h.magaza_veli[h.mag]
    if 4 not in gevset:
        maske &= h.f4
    if 5 not in gevset:
        maske &= h.f5

    e = pd.DataFrame({"opt": h.opt[maske], "mag": h.mag[maske], "gun": h.gun[maske],
                      "sku": h.sku[maske]})
    e["sira"] = h.sku_sira[e["sku"]]
    anahtar = ["opt", "mag", "gun"]
    e = e.sort_values(anahtar + ["sira", "sku"], kind="stable")
    e["no"] = e.groupby(anahtar, sort=False).cumcount()
    ilk = e[e["no"] == 0].drop(columns=["sira", "no"]).rename(columns={"sku": "sku_ali"})
    ikinci = e[e["no"] == 1][anahtar + ["sku"]].rename(columns={"sku": "sku_veli"})
    a = ilk.merge(ikinci, on=anahtar, how="left")
    if 3 not in gevset:
        a = a[a["sku_veli"].notna()]
    a["sku_veli"] = a["sku_veli"].fillna(a["sku_ali"]).astype("int64")

    a = a.reset_index(drop=True)
    opt, gun = a["opt"].to_numpy(), a["gun"].to_numpy()
    if len(a):
        son = np.maximum(h.son_stoklu_gun(a["sku_ali"].to_numpy(), gun),
                         h.son_stoklu_gun(a["sku_veli"].to_numpy(), gun))
    else:
        son = np.zeros(0, "int64")
    baslangic = son + 1
    a["baslangic"] = baslangic
    a["birikmis_kayip"] = h.onceki_birikim(opt, gun)
    a["donem_kayip"] = a["birikmis_kayip"] - h.onceki_birikim(opt, baslangic)
    if 6 not in gevset:
        a = a[a["donem_kayip"] >= EN_AZ_DONEM_KAYBI - 1e-9]
    a = a.reset_index(drop=True)

    gun = a["gun"].to_numpy()
    pl_a, ge_a = h.teslim(a["sku_ali"].to_numpy(), gun)
    pl_v, ge_v = h.teslim(a["sku_veli"].to_numpy(), gun)
    # depoya giriş: ikisinden biri önceki gece geç teslim aldıysa o gece
    depoya = _tarih(gun - 1).where(ge_a.notna() | ge_v.notna())
    bilgi = h.sku_bilgi.iloc[a["sku_ali"].to_numpy()].reset_index(drop=True)
    sonuc = pd.DataFrame({
        "option_id": h.opsiyonlar[a["opt"]].to_numpy(),
        "model_adi": bilgi["model_adi"], "renk": bilgi["renk"], "line": bilgi["line"],
        "magaza_id": h.magazalar[a["mag"]].to_numpy(),
        "tarih": _tarih(gun),
        "urun_id_ali": h.urunler[a["sku_ali"]].to_numpy(),
        "urun_id_veli": h.urunler[a["sku_veli"]].to_numpy(),
        "donem_baslangic": _tarih(a["baslangic"].to_numpy()),
        "donem_gun": (gun - a["baslangic"].to_numpy()).astype("int32"),
        "donem_kayip": a["donem_kayip"].to_numpy(),
        "birikmis_kayip": a["birikmis_kayip"].to_numpy(),
        "depoya_giris": depoya,
        "planlanan_teslim_ali": pl_a, "gerceklesen_teslim_ali": ge_a,
        "planlanan_teslim_veli": pl_v, "gerceklesen_teslim_veli": ge_v})
    sonuc = sonuc.sort_values(["donem_kayip", "option_id", "tarih", "magaza_id",
                               "urun_id_ali"],
                              ascending=[False, True, True, True, True], kind="stable")
    sonuc = sonuc.reset_index(drop=True)[ADAY_SUTUNLARI]
    for c in ("option_id", "magaza_id", "urun_id_ali", "urun_id_veli", "line"):
        sonuc[c] = sonuc[c].astype("category")
    return sonuc


def adaylar(con, gunluk: pd.DataFrame, kayip: pd.DataFrame,
            gevset: tuple[int, ...] = ()) -> pd.DataFrame:
    """Sıralı aday tablosu; `gevset` düşürülecek ölçüt numaraları (varsayılan: hepsi geçerli).

    `gunluk`: tarih, magaza_id, urun_id (+ `durum` varsa yalnız `bos` alınır);
    `kayip`: tarih, magaza_id, urun_id, kayip, kaynak (bos ve tukenen satırları).
    Sütunlar: `ADAY_SUTUNLARI`. Teslim sütunları o SKU'nun `tarih - 1` günü
    teslim edilmiş geç siparişinindir (yoksa NaT)."""
    return _adaylar(_Hazir(con, gunluk, kayip), frozenset(gevset))


def gevsetme_sirasi() -> list[tuple[int, ...]]:
    """Denenecek gevşetmeler: sıkı, tekliler (6..1), sonra ikililer aynı öncelikle."""
    return [(), *[(n,) for n in GEVSETME_SIRASI], *combinations(GEVSETME_SIRASI, 2)]


def ara(con, gunluk: pd.DataFrame, kayip: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """İlk aday veren gevşetmenin aday tablosu ve `gevsetilen` kısa adları.

    En çok iki ölçüt gevşetilse de aday çıkmazsa `LookupError`."""
    return _ara(_Hazir(con, gunluk, kayip))


def _ara(h: _Hazir) -> tuple[pd.DataFrame, list[str]]:
    for gevset in gevsetme_sirasi():
        a = _adaylar(h, frozenset(gevset))
        if len(a):
            return a, [OLCUTLER[n] for n in sorted(gevset)]
    raise LookupError("hikaye icin aday yok: en cok iki olcut gevsetilse de hicbir "
                      "option-magaza-gun olcutleri tutmuyor")


def _denetle(h: _Hazir, option_id: str, magaza_id: str, tarih) -> tuple[pd.DataFrame, list[str]]:
    dar = h.daralt(option_id, magaza_id, tarih)
    for n in range(len(OLCUTLER) + 1):
        for gevset in combinations(GEVSETME_SIRASI, n):
            a = _adaylar(dar, frozenset(gevset))
            if len(a):
                return a.head(1).reset_index(drop=True), [OLCUTLER[k] for k in sorted(gevset)]
    raise LookupError(f"{option_id}, {magaza_id}, {pd.Timestamp(tarih).date()}: o gun o magazada "
                      "option'in bos bedeni yok (hicbir gevsetmeyle aday degil)")


def denetle(con, gunluk: pd.DataFrame, kayip: pd.DataFrame, option_id: str, magaza_id: str,
            tarih) -> tuple[pd.DataFrame, list[str]]:
    """Verilen (option, mağaza, gün) adayının tutmadığı ölçütler.

    Dönüş: o adayın satırı (`ADAY_SUTUNLARI`, tek satır) ve tutmadığı ölçütlerin kısa
    adları (boş: sıkı aramanın adayıdır). Tutmayanlar, adayı veren EN KÜÇÜK gevşetme
    kümesidir (boyut artan; aynı boyutta `GEVSETME_SIRASI` önceliği). Ölçüt 3 düşerse
    Ali ve Veli aynı SKU olabilir. Option'ın o gün o mağazada hiç `bos` bedeni yoksa
    `LookupError`."""
    return _denetle(_Hazir(con, gunluk, kayip), option_id, magaza_id, tarih)


# ----------------------------------------------------------------------- seçim

def _oku(cikti: Path):
    g = pd.read_parquet(cikti / "gunluk.parquet", columns=["tarih", "magaza_id", "urun_id"],
                        filters=[("durum", "in", ["bos"])])
    k = pd.read_parquet(cikti / "kayip_basit.parquet",
                        columns=["tarih", "magaza_id", "urun_id", "kayip", "kaynak"])
    return g, k


def secim_ve_adaylar(cikti: Path | str = VARSAYILAN_CIKTI, db: Path | str | None = None,
                     hikaye: tuple[str, str, object] | None = None
                     ) -> tuple[dict, pd.DataFrame, list[str] | None]:
    """(seçim, aday tablosu, aramanın gevşettiği ölçütler); arama bir kez koşar.

    Aday tablosu ve gevşetilenler `ara`nınkidir. Seçim, `hikaye` yoksa tablonun ilk
    adayıdır (`secim()` ile aynı sözlük). `hikaye = (option_id, magaza_id, tarih)`
    verilirse seçim o adaydır (`denetle`); sözlüğün `gevsetilen`i o adayın TUTMADIĞI
    ölçütlerdir ve `elle: True` eklenir. Elle seçimde arama hiç aday vermezse tablo boş,
    gevşetilenler None döner; seçimsiz aramada `LookupError`."""
    con = kaynak.baglan(db)
    try:
        h = _Hazir(con, *_oku(Path(cikti)))
        try:
            aday, gevsetilen = _ara(h)
        except LookupError:
            if hikaye is None:
                raise
            aday, gevsetilen = pd.DataFrame(columns=ADAY_SUTUNLARI), None
        if hikaye is None:
            return _sozluk(aday, gevsetilen), aday, gevsetilen
        satir, tutmayan = _denetle(h, *hikaye)
        return {**_sozluk(satir, tutmayan), "elle": True}, aday, gevsetilen
    finally:
        con.close()


def _gunu(x) -> date | None:
    return None if pd.isna(x) else pd.Timestamp(x).date()


def secim(cikti: Path | str = VARSAYILAN_CIKTI, db: Path | str | None = None) -> dict:
    """Hikâye ürününü seçer: `ara`nın ilk adayı.

    Anahtarlar: option_id, urun_id_ali (küçük beden_sira), urun_id_veli (büyük),
    magaza_id, tarih, depoya_giris, planlanan_teslim, gerceklesen_teslim,
    donem_baslangic, donem_gun, donem_kayip (R23 dönemi, bkz. modül açıklaması),
    gevsetilen (kısa ad listesi; sıkı aramada boş). Tarihler `datetime.date`.

    `planlanan_teslim` / `gerceklesen_teslim` Ali'nin SKU'sunun `tarih - 1`
    günü teslim edilen geç siparişidir (ölçüt 4 gevşemişse None olabilir).
    Veli'nin SKU'sununki farklıysa (ya da yalnız birinde varsa) ayrıca
    `planlanan_teslim_veli` ve `gerceklesen_teslim_veli` eklenir."""
    return secim_ve_adaylar(cikti, db)[0]


def _sozluk(aday: pd.DataFrame, gevsetilen: list[str]) -> dict:
    """`ara` sonucunun ilk adayı `secim` sözlüğü olarak."""
    s = aday.iloc[0]
    sonuc = {"option_id": str(s["option_id"]), "urun_id_ali": str(s["urun_id_ali"]),
             "urun_id_veli": str(s["urun_id_veli"]), "magaza_id": str(s["magaza_id"]),
             "tarih": _gunu(s["tarih"]), "depoya_giris": _gunu(s["depoya_giris"]),
             "planlanan_teslim": _gunu(s["planlanan_teslim_ali"]),
             "gerceklesen_teslim": _gunu(s["gerceklesen_teslim_ali"]),
             "donem_baslangic": _gunu(s["donem_baslangic"]), "donem_gun": int(s["donem_gun"]),
             "donem_kayip": float(s["donem_kayip"]), "gevsetilen": gevsetilen}
    veli = (_gunu(s["planlanan_teslim_veli"]), _gunu(s["gerceklesen_teslim_veli"]))
    if veli != (sonuc["planlanan_teslim"], sonuc["gerceklesen_teslim"]):
        sonuc["planlanan_teslim_veli"], sonuc["gerceklesen_teslim_veli"] = veli
    return sonuc


# ------------------------------------------------------------------------- CLI

GOSTER = ["option_id", "model_adi", "renk", "line", "magaza_id", "tarih", "planlanan_teslim_ali",
          "gerceklesen_teslim_ali", "donem_gun", "donem_kayip", "birikmis_kayip"]


def hatta_gore(aday: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Her `line` için en iyi `n` option (option başına en üst sıradaki satır).

    Aday tablosunun sırası korunur; hatlar `HATLAR` sırasında, ardından
    tabloda görünen diğer hatlar alfabetik. Kullanıcı bu tablodan seçer."""
    ilk = aday.drop_duplicates("option_id", keep="first")
    hatlar = [h for h in HATLAR if h in set(ilk["line"].astype(str))]
    hatlar += sorted(set(ilk["line"].astype(str)) - set(hatlar))
    parcalar = [ilk[ilk["line"].astype(str) == h].head(n) for h in hatlar]
    return pd.concat(parcalar, ignore_index=True) if parcalar else ilk.head(0)


def main(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(prog="python -m yok_satma.hikaye_sec",
                                description=__doc__.split("\n")[0])
    p.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI,
                   help=f"hazirla ciktilari (varsayilan {VARSAYILAN_CIKTI})")
    p.add_argument("--db", type=Path, default=None,
                   help=f"v4 DuckDB dosyasi (varsayilan {kaynak.VARSAYILAN_YOL})")
    a = p.parse_args(argv)
    sec, aday, gevsetilen = secim_ve_adaylar(a.cikti, a.db)
    print(f"gevsetilen: {gevsetilen if gevsetilen else 'yok (tum olcutler saglandi)'}")
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(f"aday sayisi: {len(aday)}; ilk 10:")
        print(aday.head(10)[GOSTER].to_string())
        print("her line icin en iyi 3 option (option basina en ust satir):")
        print(hatta_gore(aday)[GOSTER].to_string())
    print("secilen:")
    for ad, deger in sec.items():
        print(f"  {ad}: {deger}")
    return sec


if __name__ == "__main__":
    main()
