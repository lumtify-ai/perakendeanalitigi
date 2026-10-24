"""Koşu ölçütleri (spec §4.2, §3.5): bir koşunun (`motor.Kosu` ya da tembel `KosuKaydi`) tablolarından,
kayıtlarından ve gizli gerçeğinden, koşunun test sezonunun Collection option'larında.

    hesapla(kosu, w, sezon)                 dict[str, float] (aşağıdaki ölçütler)
    option_tablosu(kosu, w, sezon)          option başına bileşenler (hesapla ve ceyrek bunları toplar)
    indirim_basi_str(kosu, w, sezon)        option_id → indirim başı STR (%; çeyreklerin ölçüsü)
    ceyrek(kosu, w, sezon, lumoda_str)      Lumoda'nın indirim başı STR çeyreklerine göre ölçütler
    isabet(kosu)                            kayıttaki tahmini satış ↔ gerçekleşen (WAPE)
    korunum(kosu, lumoda_kosu, kol_tipi)    aynı mal ve kol sözleşmeleri (dict[str, bool])
    yan_etki(kosu, lumoda_kosu, w, sezon)   test dışı option'lar, ikame, elle transfer

Bu modül ölçüm tarafındadır (koşu dışı: `simulasyon.KOSU_DISI`; `tests/test_sizinti.py`
`OLCUM_MODULLERI`). Koşunun gizli gerçek tablosunu (`gercek`) okur; dünyanın gizli alanlarına
(`lam`, `esneklik_hucre`, `gizli_*`) dokunmaz (onlar `hakem`'in). Dünyanın yalnız açık alanları
(option takvimi, ürün fiyatları, mağaza tipi, hücre yapısı) okunur. Tablolar yalnız gereken sütun ve
kapsam SKU'larıyla okunur. Oranlar yüzde; payda 0 ise NaN değil 0 (allocation kuralı), tanımsız
dağılım ölçüsü (hiç indirilen option yoksa medyan) NaN.

**Kapsam.** `sezon`un `LINE` (Collection) option'ları (`kaynak.test_optionlari`; tam ölçekte 210).
Option `o` için gün indisleri (`GUN_SIFIRI` ekseni): lansman `L`, indirim `I`, çıkış `C`. Satış
satırının hattı v4'teki gibi: ONL `online`, outlet akışı hücresi (`w.hucre_outlet_akisi`) `outlet`,
öteki `normal`. Satırın markdown oranı option × hat × haftanın (`fiyat`; hafta pazartesi başlar,
oran haftanın son günündeki) oranıdır.

**Para** (`satis`; `tutar` net: iade satırları negatif):

    ciro_sezon         Σ tutar, L ≤ gün < C (bütün mağazalar ve online)
    ciro_outlet        Σ tutar, C ≤ gün < C + 84 (outlet penceresi; bu pencereye düşen sezon
                       satışlarının iadesi de buradadır, bütün kollarda aynı kural)
    ciro_toplam        ciro_sezon + ciro_outlet
    brut_kar           ciro_toplam − Σ adet × alis_fiyati (aynı satırlar, net adet)
    katki              ciro_toplam − arz_alis (sezon katkısı; arz kollar arasında aynı, R4: kollar
                       arası katkı farkı = ciro farkı)
    markdown_tl        allocation `_para` tanımı: pozitif satış, kampanyasız (`kampanya_id` boş),
                       hat normal ya da online, satırın markdown oranı > 0, L ≤ gün < C;
                       Σ indirim_tutari. `markdown_tl_online` online hattı
    kampanya_tl        pozitif, kampanyalı, hat normal/online, L ≤ gün < C; Σ indirim_tutari
    islem_tl           pozitif, kampanyasız, hat normal/online, oran 0, L ≤ gün < C (işlem indirimi)
    outlet_indirim_tl  pozitif, hat outlet, C ≤ gün < C + 84; Σ indirim_tutari

**Mal:**

    arz_adet, arz_alis teslim edilmiş (`gerceklesen_teslim` dolu) `ilk` + `rpt` sipariş adedi
                       (kalite reddi düşülmez; v4 kalibrasyon STR'sinin paydası) ve alış değeri
    tam_fiyat_str      v4 kalibrasyon tanımı (allocation `_para`): 100 × kampanyasız pozitif satış,
                       satırın hattının ilk markdown haftasından önce, gün < C ÷ arz_adet
    son_str            100 × pozitif satış (gün < C) ÷ arz_adet
    cikis_kalan_*      C − 7'nin pazartesi fotoğrafı: mağaza (`stok`, fiziksel hücreler) ve depo
                       (`depo_stok`) adedi; `_adet` toplam, `_magaza_adet`, `_depo_adet`, `_liste`
                       (× liste fiyatı), `_alis` (× alış fiyatı). Yoldaki mal girmez
    olu_stok_adet/_alis depo stoğu, min(C + 120, koşunun son depo fotoğrafı) günü; × alış fiyatı

**İndirim davranışı** (`fiyat`, normal ve online hattı, haftası C'den önce başlayan):

    indirilen_option          oranı bir hafta > 0 olan option sayısı
    ilk_indirim_hafta_medyan  indirilen option'larda (ilk indirim haftası − I'nın haftası) ÷ 7,
                              medyan (negatif: sezon indiriminden önce; indirilen yoksa NaN)
    ort_en_derin              indirilen option'ların en derin oranının ortalaması (%; yoksa NaN)
    muaf_str_ind              hiç indirilmeyen option'ların indirim başı STR'si (Σ ÷ Σ, %; yoksa NaN)

İndirim başı STR (`indirim_basi_str`): 100 × pozitif satış (gün < I) ÷ arz_adet, option başına.

**Müşteri** (gizli gerçek, fiziksel mağazalar, karar penceresi: serbest pencere ≤ gün < C; allocation
`_musteri` tanımları): `bulunabilirlik` 100 × |talep > 0 ∧ kendi_satis > 0| ÷ |talep > 0|,
`kayip_orani` 100 × Σ karşılanmayan ÷ Σ talep.

**Tahmin isabeti** (`isabet`): kolun kaydındaki her (pazartesi d, option o) satırının `tahmini_satis`'i
(ufku d → C) ile gerçekleşen pozitif satış (normal ve online hattı, d ≤ gün < C). `wape` 100 × Σ|t − g|
÷ Σ g; `yanlilik` 100 × (Σ t − Σ g) ÷ Σ g; `wape_ilk` her option'ın ilk kayıt satırında; `satir`.
Tahmini satışı NaN olan satırlar (tekdüze) girmez.

**Korunum** (`korunum`; spec §3.5): `rpt_birebir` (`siparis`'in `rpt` satırları — option, SKU,
sipariş günü, gerçekleşen teslim, adet — Lumoda koşusununkiyle birebir), `ilk_dagitim_birebir` (test
option'larının `sevkiyat` tip `ilk_dagitim` satırları birebir), `arz_birebir` (test option'larının
teslim edilmiş ilk + RPT adedi ve kalite reddi option başına aynı), kolun kaydından ve uygulanan
fiyattan `merdiven` (oranlar yalnız `KADEMELER`), `siglasmaz` (option başına azalmaz), `pencere`
(karar penceresinden önce oran 0: kayıt satırı pencerede, `fiyat` haftasının son günü pencereden önce
olan haftada oran 0), `takvim_tabani` (taban > 0 olan kipte `I ≤ gün < C` arasında oran ≥ taban;
tabansız kipte True).

**Yan etki** (`yan_etki`; spec §0/13–14): pencere `[min L, max C + 84)` (test option'larının).
`ciro_farki_test_disi` (koşu − Lumoda, test dışı bütün option'lar: öteki sezonlar, Outlet line,
Basic, NOS), line başına `ciro_farki_<line>`, `ciro_test_disi_lumoda`; test option'larının ikameyle
aldığı satış `ikame_alinan` (pozitif satış − gizli gerçeğin `kendi_satis`'i; talepsiz hücre-gündeki
ikame alımı da girer) ve `_lumoda`, `_farki`; `ikame_giden` (test option'larından ikameye giden) ve
farkı; `elle_transfer_farki` (bütün option'lar, adet) ve `elle_transfer_farki_test`.
"""

import duckdb
import numpy as np
import pandas as pd
from allocation import motor

from markdown import kaynak, sabitler
from markdown.politika import _KIP_PENCERE, _KIP_TABAN, KAYIT_SUTUNLARI, KIPLER

SATIS = ["tarih", "magaza_id", "urun_id", "adet", "tutar", "indirim_tutari", "kampanya_id"]
FIYAT = ["hafta_baslangic", "option_id", "hat", "indirim_orani"]
SIPARIS = ["siparis_id", "tip", "option_id", "urun_id", "siparis_tarihi", "gerceklesen_teslim", "adet"]
GERCEK = ["tarih", "magaza_id", "urun_id", "talep", "kendi_satis", "karsilanmayan", "ikameye_giden"]
SEVK = ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip", "paket_id"]
HATLAR = ("normal", "outlet", "online")
NORMAL, OUTLET, ONLINE = 0, 1, 2
OUTLET_GUN = 84
OLU_STOK_GUN = 120
CIKIS_FOTO_GUN = 7
_PAY = 1e-9
_K = np.asarray(sabitler.KADEMELER, dtype=float)
_GUN0 = np.datetime64(sabitler.GUN_SIFIRI, "D")


def _oran(pay, payda) -> float:
    return 100.0 * float(pay) / float(payda) if payda > 0 else 0.0


def _gun(s) -> np.ndarray:
    """Tarih sütunu → gün indisi (`GUN_SIFIRI` ekseni); NaT → en küçük int64."""
    t = pd.to_datetime(pd.Series(s)).to_numpy().astype("datetime64[D]")
    return np.where(np.isnat(t), np.iinfo(np.int64).min, (t - _GUN0).astype(np.int64))


def _kodla(s: pd.Series, evren: pd.Index) -> np.ndarray:
    """Kimlik sütununun `evren`deki konumu (yoksa −1); kategorik sütunda kategoriler bir kez eşlenir."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        k = evren.get_indexer(pd.Index(s.cat.categories.astype(str)))
        kod = s.cat.codes.to_numpy()
        return np.where(kod >= 0, k[np.maximum(kod, 0)], -1)
    return evren.get_indexer(s.astype(str))


def _toplam(yer: np.ndarray, deger, n: int) -> np.ndarray:
    """`yer` ≥ 0 satırlarının `deger` toplamı, yer başına [n]."""
    yer = np.asarray(yer, dtype=np.int64)
    m = yer >= 0
    return np.bincount(yer[m], weights=np.asarray(deger, dtype=float)[m], minlength=n)


class _Yapi:
    """Dünyanın kimlik dizinleri, mağaza tipi ve satırın fiyat hattı (yalnız açık alanlar)."""

    def __init__(self, w):
        self.w = w
        self.urunler = pd.Index(w.urunler["urun_id"].astype(str))
        self.sku_option = np.asarray(w.sku_option, dtype=np.int64)
        self.liste = w.urunler["liste_fiyati"].to_numpy(dtype=float)
        self.alis = w.urunler["alis_fiyati"].to_numpy(dtype=float)
        self.magazalar = pd.Index(w.magazalar["magaza_id"].astype(str))
        tip = w.magazalar["tip"].astype(str).to_numpy()
        self.online = tip == "Online"
        self.fiziksel = ~np.isin(tip, ("Online", "Outlet"))
        S = len(self.urunler)
        oc = np.asarray(w.hucre_outlet_akisi, dtype=bool)
        self._outlet = np.unique(np.asarray(w.hucre_magaza, dtype=np.int64)[oc] * S
                                 + np.asarray(w.hucre_sku, dtype=np.int64)[oc])

    def sku(self, urun_id: pd.Series) -> np.ndarray:
        return _kodla(urun_id, self.urunler)

    def magaza(self, magaza_id: pd.Series) -> np.ndarray:
        return _kodla(magaza_id, self.magazalar)

    def hat(self, m: np.ndarray, s: np.ndarray) -> np.ndarray:
        """Satırın fiyat hattı (v4 `hat_indisi`): ONL online, outlet akışı hücresi outlet, öteki normal."""
        k = m.astype(np.int64) * len(self.urunler) + s
        outlet = (m >= 0) & (s >= 0) & np.isin(k, self._outlet)
        return np.where((m >= 0) & self.online[np.maximum(m, 0)], ONLINE, np.where(outlet, OUTLET, NORMAL))


class Kapsam(_Yapi):
    """Test sezonunun Collection option'ları ve kimlik eşlemeleri (yalnız açık alanlar)."""

    def __init__(self, w, sezon: str):
        super().__init__(w)
        opt = w.optionlar
        self.opt = kaynak.test_optionlari(opt, sezon)
        self.n = len(self.opt)
        self.konum = np.full(len(opt), -1, dtype=np.int64)
        self.konum[self.opt] = np.arange(self.n)
        self.option_idler = pd.Index(opt["option_id"].astype(str))
        self.option_id = self.option_idler.to_numpy()[self.opt]
        self.lansman = opt["lansman_gun"].to_numpy(dtype=np.int64)[self.opt]
        self.indirim = opt["indirim_gun"].to_numpy(dtype=np.int64)[self.opt]
        self.cikis = opt["cikis_gun"].to_numpy(dtype=np.int64)[self.opt]
        self.skular = self.urunler.to_numpy()[self.konum[self.sku_option] >= 0]

    def yer(self, s: np.ndarray) -> np.ndarray:
        """SKU indisinin kapsam içi option konumu (kapsam dışı ya da −1 → −1)."""
        return np.where(s >= 0, self.konum[self.sku_option[np.maximum(s, 0)]], -1)

    def pencere(self) -> np.ndarray:
        """Serbest karar penceresinin ilk günü (option başına)."""
        return kaynak.karar_penceresi(self.w.optionlar, self.opt, "serbest")


# ---------------------------------------------------------------------------
# Fiyat
# ---------------------------------------------------------------------------


class _Fiyat:
    """Kapsamın `fiyat` paneli: oran[konum, hat, hafta] (hafta = gün // 7; kayıtsız 0)."""

    def __init__(self, fiyat: pd.DataFrame, k: Kapsam):
        i = _kodla(fiyat["option_id"], k.option_idler)
        o = np.where(i >= 0, k.konum[np.maximum(i, 0)], -1)
        f = fiyat[o >= 0]
        o = o[o >= 0]
        gun = _gun(f["hafta_baslangic"])
        if len(gun) and (gun % 7 != 0).any():
            raise ValueError("fiyat haftası pazartesi değil")
        hafta = gun // 7
        self.bas = int(hafta.min()) if len(hafta) else 0
        H = int(hafta.max()) - self.bas + 1 if len(hafta) else 1
        h = pd.Index(HATLAR).get_indexer(f["hat"].astype(str))
        self.oran = np.zeros((k.n, 3, H))
        self.oran[o, h, hafta - self.bas] = f["indirim_orani"].to_numpy(dtype=float)
        self.k = k

    def satir_orani(self, yer: np.ndarray, hat: np.ndarray, gun: np.ndarray) -> np.ndarray:
        i = gun // 7 - self.bas
        icinde = (yer >= 0) & (i >= 0) & (i < self.oran.shape[2])
        return np.where(icinde, self.oran[np.maximum(yer, 0), hat, np.clip(i, 0, self.oran.shape[2] - 1)], 0.0)

    def haftalar(self) -> np.ndarray:
        """[H] haftaların ilk günü (gün indisi)."""
        return (self.bas + np.arange(self.oran.shape[2])) * 7

    def sezon_ici(self) -> np.ndarray:
        """[n, H] haftanın ilk günü < C."""
        return self.haftalar()[None, :] < self.k.cikis[:, None]

    def ilk_md(self, hat: int) -> np.ndarray:
        """[n] hattın oranı > 0 olan ilk haftanın ilk günü (yoksa en büyük int64)."""
        md = self.oran[:, hat, :] > 0
        ilk = np.where(md.any(1), self.haftalar()[np.argmax(md, axis=1)], np.iinfo(np.int64).max)
        return ilk


# ---------------------------------------------------------------------------
# Option tablosu ve toplama
# ---------------------------------------------------------------------------


def _fotograf(df: pd.DataFrame, k: Kapsam, hedef: np.ndarray, fiyat: np.ndarray | None = None) -> np.ndarray:
    """[n] `df` (tarih, urun_id, adet) satırlarından option'ın `hedef` günündeki adet toplamı (`fiyat`
    [S] verilirse adet × SKU fiyatı)."""
    s = k.sku(df["urun_id"])
    yer = k.yer(s)
    m = (yer >= 0) & (_gun(df["tarih"]) == hedef[np.maximum(yer, 0)])
    adet = df["adet"].to_numpy(dtype=float)
    return _toplam(np.where(m, yer, -1), adet if fiyat is None else adet * fiyat[np.maximum(s, 0)], k.n)


def _arz(siparis: pd.DataFrame, k: Kapsam) -> tuple[np.ndarray, np.ndarray]:
    s = k.sku(siparis["urun_id"])
    yer = k.yer(s)
    m = (yer >= 0) & siparis["tip"].astype(str).isin(["ilk", "rpt"]).to_numpy() \
        & siparis["gerceklesen_teslim"].notna().to_numpy()
    adet = siparis["adet"].to_numpy(dtype=float)
    return (_toplam(np.where(m, yer, -1), adet, k.n),
            _toplam(np.where(m, yer, -1), adet * k.alis[np.maximum(s, 0)], k.n))


def option_tablosu(kosu, w, sezon: str) -> pd.DataFrame:
    """Option başına bileşenler (modül notu; `option_id` sırası dünya option sırası)."""
    k = Kapsam(w, sezon)
    n = k.n
    t = {"option_id": k.option_id, "ust_kategori": w.optionlar["ust_kategori"].astype(str).to_numpy()[k.opt]}

    siparis = kosu.tablo("siparis", SIPARIS, urunler=k.skular)
    t["arz_adet"], t["arz_alis"] = _arz(siparis, k)
    del siparis

    fiyat = _Fiyat(kosu.tablo("fiyat", FIYAT), k)
    satis = kosu.tablo("satis", SATIS, urunler=k.skular)
    s = k.sku(satis["urun_id"])
    yer = k.yer(s)
    gun = _gun(satis["tarih"])
    m = k.magaza(satis["magaza_id"])
    hat = k.hat(m, s)
    adet = satis["adet"].to_numpy(dtype=np.int64)
    tutar = satis["tutar"].to_numpy(dtype=float)
    indirim = satis["indirim_tutari"].to_numpy(dtype=float)
    kampanyasiz = satis["kampanya_id"].isna().to_numpy()
    del satis
    yy = np.maximum(yer, 0)
    L, I, C = k.lansman[yy], k.indirim[yy], k.cikis[yy]
    var = yer >= 0
    sezon_ici = var & (gun >= L) & (gun < C)
    outlet_pen = var & (gun >= C) & (gun < C + OUTLET_GUN)
    pozitif = adet > 0
    nh = hat != OUTLET
    oran = fiyat.satir_orani(yer, hat, gun)
    ilk_md = np.stack([fiyat.ilk_md(h) for h in range(3)], axis=1)        # [n, 3]
    tam = var & pozitif & kampanyasiz & (gun < C) & (gun < ilk_md[yy, hat])
    alis = k.alis[np.maximum(s, 0)]

    def top(maske, deger):
        return _toplam(np.where(maske, yer, -1), deger, n)

    t["ciro_sezon"] = top(sezon_ici, tutar)
    t["ciro_outlet"] = top(outlet_pen, tutar)
    t["satilan_alis"] = top(sezon_ici | outlet_pen, adet * alis)
    md = sezon_ici & pozitif & kampanyasiz & nh & (oran > 0)
    t["markdown_tl"] = top(md, indirim)
    t["markdown_tl_online"] = top(md & (hat == ONLINE), indirim)
    t["kampanya_tl"] = top(sezon_ici & pozitif & ~kampanyasiz & nh, indirim)
    t["islem_tl"] = top(sezon_ici & pozitif & kampanyasiz & nh & (oran <= 0), indirim)
    t["outlet_indirim_tl"] = top(outlet_pen & pozitif & (hat == OUTLET), indirim)
    t["tam_fiyat_adet"] = top(tam, adet)
    t["satis_cikis"] = top(var & pozitif & (gun < C), adet)
    t["satis_indirim"] = top(var & pozitif & (gun < I), adet)
    del yer, gun, m, hat, adet, tutar, indirim, kampanyasiz, s

    # İndirim davranışı: normal ve online hattı, haftası C'den önce başlayan
    so = fiyat.sezon_ici()
    no = np.where(so[:, None, :], fiyat.oran[:, [NORMAL, ONLINE], :], 0.0).max(axis=1)     # [n, H]
    indirildi = (no > 0).any(1)
    t["ilk_indirim_gun"] = np.where(indirildi, fiyat.haftalar()[np.argmax(no > 0, axis=1)], np.nan)
    t["indirim_haftasi_gun"] = (k.indirim - k.indirim % 7).astype(float)
    t["en_derin"] = no.max(axis=1) if no.shape[1] else np.zeros(n)

    # Çıkış fotoğrafı (C − 7) ve ölü stok
    foto = k.cikis - CIKIS_FOTO_GUN
    stok = kosu.tablo("stok", ["tarih", "urun_id", "adet"], urunler=k.skular)
    depo = kosu.tablo("depo_stok", ["tarih", "urun_id", "adet"], urunler=k.skular)
    t["cikis_kalan_magaza_adet"] = _fotograf(stok, k, foto)
    t["cikis_kalan_depo_adet"] = _fotograf(depo, k, foto)
    t["cikis_kalan_liste"] = _fotograf(stok, k, foto, k.liste) + _fotograf(depo, k, foto, k.liste)
    t["cikis_kalan_alis"] = _fotograf(stok, k, foto, k.alis) + _fotograf(depo, k, foto, k.alis)
    del stok
    son = int(_gun(depo["tarih"]).max()) if len(depo) else 0
    olu = np.minimum(k.cikis + OLU_STOK_GUN, son)
    t["olu_stok_adet"] = _fotograf(depo, k, olu)
    t["olu_stok_alis"] = _fotograf(depo, k, olu, k.alis)
    del depo

    # Müşteri: fiziksel mağazalar, serbest karar penceresi → C
    g = kosu.tablo("gercek", GERCEK[:6], urunler=k.skular)
    yer = k.yer(k.sku(g["urun_id"]))
    gun = _gun(g["tarih"])
    mg = k.magaza(g["magaza_id"])
    yy = np.maximum(yer, 0)
    pen = k.pencere()
    ic = (yer >= 0) & (mg >= 0) & k.fiziksel[np.maximum(mg, 0)] & (gun >= pen[yy]) & (gun < k.cikis[yy])
    talep = g["talep"].to_numpy(dtype=np.int64)
    kendi = g["kendi_satis"].to_numpy(dtype=np.int64)
    if (kendi > talep).any():
        raise RuntimeError("korunum: kendi satış talebi aşıyor")
    t["talepli_hucre_gun"] = _toplam(np.where(ic & (talep > 0), yer, -1), np.ones(len(g)), n)
    t["bulunan_hucre_gun"] = _toplam(np.where(ic & (talep > 0) & (kendi > 0), yer, -1), np.ones(len(g)), n)
    t["talep"] = _toplam(np.where(ic, yer, -1), talep, n)
    t["karsilanmayan"] = _toplam(np.where(ic, yer, -1), g["karsilanmayan"].to_numpy(dtype=float), n)
    return pd.DataFrame(t)


def ozetle(t: pd.DataFrame) -> dict[str, float]:
    """`option_tablosu` satırlarından ölçütler (modül notu); her değer float."""
    ciro = float(t["ciro_sezon"].sum() + t["ciro_outlet"].sum())
    arz = float(t["arz_adet"].sum())
    ind = t["ilk_indirim_gun"].notna().to_numpy()
    muaf = t[~ind]
    hafta = (t["ilk_indirim_gun"][ind] - t["indirim_haftasi_gun"][ind]) / 7.0
    magaza, depo = float(t["cikis_kalan_magaza_adet"].sum()), float(t["cikis_kalan_depo_adet"].sum())
    return {
        "option_sayisi": float(len(t)),
        "ciro_sezon": float(t["ciro_sezon"].sum()), "ciro_outlet": float(t["ciro_outlet"].sum()),
        "ciro_toplam": ciro,
        "brut_kar": ciro - float(t["satilan_alis"].sum()),
        "katki": ciro - float(t["arz_alis"].sum()),
        "markdown_tl": float(t["markdown_tl"].sum()), "markdown_tl_online": float(t["markdown_tl_online"].sum()),
        "kampanya_tl": float(t["kampanya_tl"].sum()), "islem_tl": float(t["islem_tl"].sum()),
        "outlet_indirim_tl": float(t["outlet_indirim_tl"].sum()),
        "arz_adet": arz, "arz_alis": float(t["arz_alis"].sum()),
        "tam_fiyat_str": _oran(t["tam_fiyat_adet"].sum(), arz),
        "son_str": _oran(t["satis_cikis"].sum(), arz),
        "cikis_kalan_adet": magaza + depo, "cikis_kalan_magaza_adet": magaza, "cikis_kalan_depo_adet": depo,
        "cikis_kalan_liste": float(t["cikis_kalan_liste"].sum()), "cikis_kalan_alis": float(t["cikis_kalan_alis"].sum()),
        "olu_stok_adet": float(t["olu_stok_adet"].sum()), "olu_stok_alis": float(t["olu_stok_alis"].sum()),
        "indirilen_option": float(ind.sum()),
        "ilk_indirim_hafta_medyan": float(np.median(hafta)) if ind.any() else float("nan"),
        "ort_en_derin": 100.0 * float(t["en_derin"][ind].mean()) if ind.any() else float("nan"),
        "muaf_str_ind": _oran(muaf["satis_indirim"].sum(), muaf["arz_adet"].sum()) if len(muaf) else float("nan"),
        "bulunabilirlik": _oran(t["bulunan_hucre_gun"].sum(), t["talepli_hucre_gun"].sum()),
        "kayip_orani": _oran(t["karsilanmayan"].sum(), t["talep"].sum()),
    }


def hesapla(kosu, w, sezon: str) -> dict[str, float]:
    """Koşunun `sezon` ölçütleri (modül notu)."""
    return ozetle(option_tablosu(kosu, w, sezon))


def indirim_basi_str(kosu, w, sezon: str) -> pd.Series:
    """option_id → 100 × pozitif satış (gün < indirim_gun) ÷ arz (teslim edilmiş ilk + RPT)."""
    t = option_tablosu(kosu, w, sezon)
    return _str_serisi(t)


def _str_serisi(t: pd.DataFrame) -> pd.Series:
    arz = t["arz_adet"].to_numpy(dtype=float)
    v = np.divide(100.0 * t["satis_indirim"].to_numpy(dtype=float), arz, out=np.zeros(len(t)), where=arz > 0)
    return pd.Series(v, index=pd.Index(t["option_id"], name="option_id"), name="indirim_basi_str")


def ceyrek(kosu, w, sezon: str, lumoda_str: pd.Series) -> pd.DataFrame:
    """Lumoda koşusunun indirim başı STR'sine göre çeyrekler (1 en düşük, 4 en yüksek; sıralama STR,
    eşitlikte option_id; `ceil(4 · sıra ÷ n)`): çeyrek başına `ozetle` ölçütleri ve `str_alt`,
    `str_ust` (çeyreğin Lumoda STR aralığı). `lumoda_str` bütün kapsam option'larını kapsamalı."""
    t = option_tablosu(kosu, w, sezon)
    eksik = sorted(set(t["option_id"]) - set(map(str, lumoda_str.index)))
    if eksik:
        raise ValueError(f"lumoda_str'de olmayan option'lar: {eksik[:5]}")
    s = pd.Series(lumoda_str.to_numpy(dtype=float), index=lumoda_str.index.astype(str)).reindex(t["option_id"])
    sira = pd.DataFrame({"str": s.to_numpy(), "id": t["option_id"].to_numpy()}).sort_values(["str", "id"]).index
    rank = np.empty(len(t), dtype=np.int64)
    rank[sira.to_numpy()] = np.arange(1, len(t) + 1)
    q = np.ceil(4 * rank / max(len(t), 1)).astype(np.int64)
    satirlar = []
    for c in range(1, 5):
        m = q == c
        satirlar.append({"ceyrek": c, "str_alt": float(s.to_numpy()[m].min()) if m.any() else float("nan"),
                         "str_ust": float(s.to_numpy()[m].max()) if m.any() else float("nan"),
                         **ozetle(t[m])})
    return pd.DataFrame(satirlar)


# ---------------------------------------------------------------------------
# Tahmin isabeti
# ---------------------------------------------------------------------------


def _kol_kaydi(kosu) -> pd.DataFrame:
    kayit = kosu.kayitlar.get("markdown")
    if kayit is None or list(kayit.columns) != list(KAYIT_SUTUNLARI):
        raise ValueError("koşunun markdown kaydı bir kolun kaydı değil (Lumoda koşusu mu?): "
                         f"{None if kayit is None else list(kayit.columns)}")
    return kayit


def isabet(kosu, w=None) -> dict[str, float]:
    """Kolun pazartesi kaydındaki tahmini satış ↔ gerçekleşen (modül notu)."""
    w = motor.dunya(kosu.meta["olcek"]) if w is None else w
    kayit = _kol_kaydi(kosu)
    kayit = kayit[np.isfinite(kayit["tahmini_satis"].to_numpy(dtype=float))]
    if not len(kayit):
        return {"wape": float("nan"), "yanlilik": float("nan"), "wape_ilk": float("nan"), "satir": 0.0}
    O = len(w.optionlar)
    opt = np.unique(kayit["option"].to_numpy(dtype=np.int64))
    konum = np.full(O, -1, dtype=np.int64)
    konum[opt] = np.arange(len(opt))
    cikis = w.optionlar["cikis_gun"].to_numpy(dtype=np.int64)
    y = _Yapi(w)
    sku_o = y.sku_option
    satis = kosu.tablo("satis", ["tarih", "magaza_id", "urun_id", "adet"],
                       urunler=y.urunler.to_numpy()[np.isin(sku_o, opt)])
    s = y.sku(satis["urun_id"])
    yer = np.where(s >= 0, konum[sku_o[np.maximum(s, 0)]], -1)
    gun = _gun(satis["tarih"])
    adet = satis["adet"].to_numpy(dtype=np.int64)
    hat = y.hat(y.magaza(satis["magaza_id"]), s)
    m = (yer >= 0) & (adet > 0) & (hat != OUTLET)
    bas = int(gun[m].min()) if m.any() else 0
    D = int(max(gun[m].max() if m.any() else 0, cikis[opt].max())) - bas + 2
    gunluk = np.zeros((len(opt), D))
    np.add.at(gunluk, (yer[m], gun[m] - bas), adet[m])
    kum = np.concatenate([np.zeros((len(opt), 1)), np.cumsum(gunluk, axis=1)], axis=1)   # kum[:, i] = Σ < bas+i
    ko = konum[kayit["option"].to_numpy(dtype=np.int64)]
    d = np.clip(kayit["gun"].to_numpy(dtype=np.int64) - bas, 0, D)
    c = np.clip(cikis[kayit["option"].to_numpy(dtype=np.int64)] - bas, 0, D)
    gercek = kum[ko, c] - kum[ko, np.minimum(d, c)]
    tahmin = kayit["tahmini_satis"].to_numpy(dtype=float)
    ilk = kayit.groupby("option")["gun"].transform("min").to_numpy() == kayit["gun"].to_numpy()

    def wape(mm):
        g = gercek[mm].sum()
        return _oran(np.abs(tahmin[mm] - gercek[mm]).sum(), g) if mm.any() else float("nan")

    tum = np.ones(len(kayit), dtype=bool)
    return {"wape": wape(tum), "yanlilik": _oran(tahmin.sum() - gercek.sum(), gercek.sum()),
            "wape_ilk": wape(ilk), "satir": float(len(kayit))}


# ---------------------------------------------------------------------------
# Korunum
# ---------------------------------------------------------------------------


def _tablo_esit(a: pd.DataFrame, b: pd.DataFrame, sutunlar: list[str]) -> bool:
    def kanon(df):
        df = df[sutunlar].copy()
        for c in sutunlar:
            if not pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].astype(str)
        return df.sort_values(sutunlar).reset_index(drop=True)
    return len(a) == len(b) and kanon(a).equals(kanon(b))


def _kol_beyani(kosu) -> dict:
    return ((kosu.meta.get("politikalar") or {}).get("markdown") or {}).get("parametreler") or {}


def korunum(kosu, lumoda_kosu, kol_tipi: str, w=None) -> dict[str, bool]:
    """Aynı mal ve kol sözleşmeleri (modül notu). `kol_tipi` kolun kipi (`politika.KIPLER`: serbest,
    takvim, erken_yok, taban; kural ve kahin serbest, tekdüze takvim kipindedir): pencere ve taban
    ondan; kolun beyanı (`meta` politika kimliği) daha yüksek taban taşıyorsa (tekdüze) o da sınanır.
    Kolun beyan ettiği pencere kipinkiyle çelişirse `ValueError`."""
    if kol_tipi not in KIPLER:
        raise ValueError(f"kol_tipi {KIPLER}'den biri olmalı: {kol_tipi!r}")
    w = motor.dunya(kosu.meta["olcek"]) if w is None else w
    beyan = _kol_beyani(kosu)
    pencere_tipi = _KIP_PENCERE[kol_tipi]
    if beyan.get("pencere", pencere_tipi) != pencere_tipi:
        raise ValueError(f"kolun penceresi {beyan.get('pencere')!r}, kip {kol_tipi!r} {pencere_tipi!r} ister")
    taban = max(_KIP_TABAN[kol_tipi], float(beyan.get("taban", 0.0)))
    kayit = _kol_kaydi(kosu)
    test = np.unique(np.asarray(beyan["test_optionlari"], dtype=np.int64)) if "test_optionlari" in beyan \
        else np.unique(kayit["option"].to_numpy(dtype=np.int64))
    opt = w.optionlar
    ids = opt["option_id"].astype(str).to_numpy()
    test_id = set(ids[test])
    urunler = pd.Index(w.urunler["urun_id"].astype(str))
    skular = urunler.to_numpy()[np.isin(np.asarray(w.sku_option, dtype=np.int64), test)]
    sonuc = {}

    # Aynı mal
    sp = [x.tablo("siparis", SIPARIS) for x in (kosu, lumoda_kosu)]
    rpt = [x[x["tip"].astype(str) == "rpt"] for x in sp]
    sonuc["rpt_birebir"] = _tablo_esit(*rpt, ["option_id", "urun_id", "siparis_tarihi", "gerceklesen_teslim", "adet"])
    sv = [x.tablo("sevkiyat", SEVK, urunler=skular) for x in (kosu, lumoda_kosu)]
    ilk = [x[x["tip"].astype(str) == "ilk_dagitim"] for x in sv]
    sonuc["ilk_dagitim_birebir"] = _tablo_esit(*ilk, SEVK)
    arz = []
    for x, s in zip((kosu, lumoda_kosu), sp):
        s = s[s["option_id"].astype(str).isin(test_id) & s["tip"].astype(str).isin(["ilk", "rpt"])
              & s["gerceklesen_teslim"].notna()]
        kk = x.tablo("kalite_kontrol", ["siparis_id", "hatali"])
        kk = kk[kk["siparis_id"].astype(str).isin(set(s["siparis_id"].astype(str)))]
        hat = kk.merge(s[["siparis_id", "option_id"]].drop_duplicates("siparis_id").astype(str), on="siparis_id")
        arz.append((s.groupby(s["option_id"].astype(str))["adet"].sum().sort_index().to_dict(),
                    hat.groupby("option_id")["hatali"].sum().sort_index().to_dict()))
    sonuc["arz_birebir"] = arz[0] == arz[1]

    # Kolun kaydı
    kayit = kayit.sort_values(["option", "gun"], kind="stable")
    oran = kayit["oran"].to_numpy(dtype=float)
    o = kayit["option"].to_numpy(dtype=np.int64)
    gun = kayit["gun"].to_numpy(dtype=np.int64)
    merdiven_k = bool(np.all(np.abs(oran[:, None] - _K[None, :]).min(axis=1) < _PAY)) if len(oran) else True
    ayni = o[1:] == o[:-1]
    siglasmaz_k = bool(np.all(oran[1:][ayni] >= oran[:-1][ayni] - _PAY))
    pen = np.full(len(opt), np.iinfo(np.int64).max)
    pen[test] = kaynak.karar_penceresi(opt, test, pencere_tipi)
    pencere_k = bool(np.all(gun >= pen[o]))
    indirim = opt["indirim_gun"].to_numpy(dtype=np.int64)
    cikis = opt["cikis_gun"].to_numpy(dtype=np.int64)
    tb = (gun >= indirim[o]) & (gun < cikis[o])
    taban_k = bool(np.all(oran[tb] >= taban - _PAY)) if taban > 0 else True

    # Uygulanan fiyat: test option'larının normal ve online hattı
    f = kosu.tablo("fiyat", FIYAT)
    f = f[f["option_id"].astype(str).isin(test_id) & f["hat"].astype(str).isin(["normal", "online"])]
    fo = pd.Index(ids).get_indexer(f["option_id"].astype(str))
    fg = _gun(f["hafta_baslangic"])
    fr = f["indirim_orani"].to_numpy(dtype=float)
    sezon_ici = fg < cikis[fo]
    merdiven_f = bool(np.all(np.abs(fr[:, None] - _K[None, :]).min(axis=1) < _PAY)) if len(fr) else True
    sira = np.lexsort((fg, f["hat"].astype(str).to_numpy(), fo))
    a_o, a_h, a_g, a_r = fo[sira], f["hat"].astype(str).to_numpy()[sira], fg[sira], fr[sira]
    s_ici = sezon_ici[sira]
    ayni = (a_o[1:] == a_o[:-1]) & (a_h[1:] == a_h[:-1]) & s_ici[1:] & s_ici[:-1]
    siglasmaz_f = bool(np.all(a_r[1:][ayni] >= a_r[:-1][ayni] - _PAY))
    pencere_f = bool(np.all((fr <= 0) | (fg + 6 >= pen[fo])))         # oran haftanın son günündeki
    son_gun = fg + 6
    tbf = sezon_ici & (son_gun >= indirim[fo]) & (son_gun < cikis[fo])
    taban_f = bool(np.all(fr[tbf] >= taban - _PAY)) if taban > 0 else True

    sonuc.update(merdiven=merdiven_k and merdiven_f, siglasmaz=siglasmaz_k and siglasmaz_f,
                 pencere=pencere_k and pencere_f, takvim_tabani=taban_k and taban_f)
    return sonuc


# ---------------------------------------------------------------------------
# Yan etki
# ---------------------------------------------------------------------------


def _satis_urun(kosu, bas: np.datetime64, bit: np.datetime64) -> pd.DataFrame:
    """`satis`'ten [bas, bit) penceresinde urun_id başına Σ tutar (tembel kayıtta Parquet'ten süzerek)."""
    sorgu = ("select cast(urun_id as varchar) as urun_id, sum(tutar) as tutar from {k} "
             "where tarih >= ? and tarih < ? group by 1")
    con = duckdb.connect(":memory:")
    try:
        prm = [pd.Timestamp(bas), pd.Timestamp(bit)]
        if isinstance(kosu, motor.KosuKaydi):
            yol = str(kosu._yol("satis")).replace("'", "''")
            return con.execute(sorgu.format(k=f"read_parquet('{yol}')"), prm).df()
        con.register("satis_t", kosu.tablolar["satis"][["tarih", "urun_id", "tutar"]])
        return con.execute(sorgu.format(k="satis_t"), prm).df()
    finally:
        con.close()


def _elle(kosu, bas, bit, skular=None) -> float:
    sv = kosu.tablo("sevkiyat", ["tarih", "urun_id", "adet", "tip"], urunler=skular)
    t = pd.to_datetime(sv["tarih"]).to_numpy()
    m = (sv["tip"].astype(str) == "elle_transfer").to_numpy() & (t >= bas) & (t < bit)
    return float(sv["adet"].to_numpy(dtype=np.int64)[m].sum())


def _ikame(kosu, k: Kapsam, bas, bit) -> tuple[float, float]:
    """(test option'larının ikameyle aldığı satış, ikameye giden) [bas, bit) penceresinde."""
    s = kosu.tablo("satis", ["tarih", "urun_id", "adet"], urunler=k.skular)
    t = pd.to_datetime(s["tarih"]).to_numpy()
    a = s["adet"].to_numpy(dtype=np.int64)
    pozitif = float(a[(a > 0) & (t >= bas) & (t < bit)].sum())
    g = kosu.tablo("gercek", ["tarih", "urun_id", "kendi_satis", "ikameye_giden"], urunler=k.skular)
    tg = pd.to_datetime(g["tarih"]).to_numpy()
    mg = (tg >= bas) & (tg < bit)
    return (pozitif - float(g["kendi_satis"].to_numpy(dtype=np.int64)[mg].sum()),
            float(g["ikameye_giden"].to_numpy(dtype=np.int64)[mg].sum()))


def yan_etki(kosu, lumoda_kosu, w, sezon: str) -> dict[str, float]:
    """Test dışı option'ların ciro farkı, ikame, elle transfer (modül notu)."""
    k = Kapsam(w, sezon)
    bas = _GUN0 + np.timedelta64(int(k.lansman.min()), "D")
    bit = _GUN0 + np.timedelta64(int((k.cikis + OUTLET_GUN).max()), "D")
    bas, bit = bas.astype("datetime64[ns]"), bit.astype("datetime64[ns]")
    sku_line = pd.Series(w.optionlar["line"].astype(str).to_numpy()[k.sku_option], index=k.urunler)
    test_sku = set(k.skular)
    ciro = []
    for x in (kosu, lumoda_kosu):
        u = _satis_urun(x, bas, bit)
        u = u[~u["urun_id"].isin(test_sku)]
        ciro.append(u.groupby(u["urun_id"].map(sku_line))["tutar"].sum())
    fark = ciro[0].sub(ciro[1], fill_value=0.0)
    sonuc = {"ciro_farki_test_disi": float(fark.sum()), "ciro_test_disi_lumoda": float(ciro[1].sum())}
    for line in sorted(set(w.optionlar["line"].astype(str))):
        sonuc[f"ciro_farki_{line.lower()}"] = float(fark.get(line, 0.0))
    (al, gi), (al_l, gi_l) = _ikame(kosu, k, bas, bit), _ikame(lumoda_kosu, k, bas, bit)
    sonuc.update(ikame_alinan=al, ikame_alinan_lumoda=al_l, ikame_alinan_farki=al - al_l,
                 ikame_giden=gi, ikame_giden_lumoda=gi_l, ikame_giden_farki=gi - gi_l)
    sonuc["elle_transfer_farki"] = _elle(kosu, bas, bit) - _elle(lumoda_kosu, bas, bit)
    sonuc["elle_transfer_farki_test"] = (_elle(kosu, bas, bit, k.skular)
                                         - _elle(lumoda_kosu, bas, bit, k.skular))
    return sonuc
