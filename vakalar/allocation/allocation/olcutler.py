"""Koşu ölçütleri (spec §4.2–4.3): bir koşunun (`motor.Kosu` ya da tembel `KosuKaydi`) gizli
gerçeğinden, tablolarından ve ilk dağıtım kaydından, `sezon`un `LINE` (Collection) option'larında.

    hesapla(kosu, w, harita, sezon)               dict[str, float] (aşağıdaki ölçütler)
    erken_birincil_talep(kosu, w, harita, sezon)  option_id, magaza_id, talep (kahinin girdisi)
    bulunabilirlik(...), sezon_sonu_kalan_yuzde(...)   kalibrasyonun da kullandığı iki ölçüt

Bu modül koşu dışıdır (`motor.KOSU_DISI`; gizli gerçeği okumaya izinli, `tests/test_sizinti.py`).
Dünyanın yalnız açık alanlarını okur. Tablolar yalnız gereken sütun ve oyun SKU'larıyla okunur.
Oranlar yüzde (`pay_wape` hariç: 0–1, kalibrasyonla aynı ölçek); payda 0 ise 0.

**Kapsam.** Option `o` (sezonun `LINE` option'ı) için pencere `[b_o, c_o)`: `b_o` option'ın ilk
dağıtımının mağazaya ilk varış günü (koşunun `sevkiyat`'ı; hiç varışı yoksa lansman günü, option
düşmez), `c_o` çıkış günü (hariç; o gün outlet akışı). Mağaza "fiziksel": `Harita.magaza_fiziksel`
(Online ve Outlet tipi hariç). Online ayrı satırlarda.

**Müşteri** (gizli gerçek, fiziksel, pencerede):

    bulunabilirlik         100 × |talep > 0 ∧ kendi_satis > 0| ÷ |talep > 0| (DM R22)
    bulunabilirlik_ilk4    aynısı `[b_o, b_o + 28)`
    kayip_orani            100 × Σ karşılanmayan ÷ Σ talep
    ikame_payi             100 × Σ ikameye_giden ÷ Σ karşılanmayan (kalanı kalıcı kayıp)
    kalici_kayip_orani     100 × Σ kalıcı kayıp ÷ Σ talep
    talep_adet, satis_adet Σ talep, Σ kendi_satis (ikame satışı hariç)

**Para** (`satis`, satış tarihi < çıkış; bütün mağazalar ve online):

    tam_fiyat_str          v4 kalibrasyon tanımı (`veri/tests/v4/test_kalibrasyon.py::collection_str`):
                           100 × kampanyasız, pozitif, satışın hattında (online / outlet / normal)
                           ilk markdown haftasından önce satılan adet ÷ teslim alınan ilk + RPT
                           sipariş adedi (kalite reddi düşülmez; v4'teki gibi)
    markdown_tl            markdown kaynaklı indirim: pozitif satış satırlarının `indirim_tutari`,
                           satır kampanyasız (`kampanya_id` boş: fiyatı kampanya belirlemedi) ve
                           option'ın o hattaki o haftalık markdown oranı (`fiyat.indirim_orani`)
                           > 0 iken. Kampanya indirimi (kampanya oranı markdown'ı aşınca satır
                           kampanyalıdır) ve işlem indirimi (yalnız markdown ve kampanya 0 iken
                           çıkar) girmez. `_fiziksel` (online dışı) ve `_online` ayrı
    brut_kar_tl            Σ tutar − Σ adet × alış fiyatı (`urun.alis_fiyati`), iade satırları
                           dahil (net); `_fiziksel`, `_online` ve toplam
    online_satis           online'ın pozitif satış adedi

**Mal akışı:**

    toplam_mal             depoya giren: `siparis`'in teslim edilmiş `ilk` + `rpt` adedi −
                           `kalite_kontrol`'ün o siparişlerdeki `hatali` adedi
    rpt_adet               teslim edilmiş RPT sipariş adedi (kalite reddinden önce)
    ilk_dagitim_adet       `sevkiyat` tip `ilk_dagitim` adedi
    replenishment_adet     `sevkiyat` tip `replenishment` adedi (depo → mağaza)
    elle_transfer_adet     `sevkiyat` tip `elle_transfer` adedi, çıkıştan önce
    sezon_sonu_kalan_yuzde 100 × (kalan_magaza_adet + kalan_depo_adet) ÷ toplam_mal
    kalan_magaza_adet      çıkışta mağazalardan outlet'e akış + fiziksel mağazalardan depoya stok
                           devri (çıkıştan sonra; iade, geç varış). Outlet mağazasının outlet
                           penceresi sonundaki devri outlet akışının kalanıdır, ikinci kez sayılmaz
    kalan_depo_adet        çıkışta depodan outlet'e akış + çıkıştan sonra depoya eklenen
                           (`kalan_depo_ek_adet`: koşunun son depo fotoğrafındaki stok − o güne dek
                           varan bütün stok devri; çıkış sonrası RPT varışı, online iadesi). Çıkmış
                           option'ın depo stoğu depoda kalır (motor): tutma kollarının depoda
                           bıraktığı mal da çıkışta outlet akışıyla buraya girer. Çıkışı koşunun
                           son depo fotoğrafından önce olmayan option'da ek 0
    kirpilan_adet          motorun kırptığı ilk dağıtım (`motor.kirpma_tablosu`, istenen − giden
                           paket × paket adedi); `lumoda` dışı kolda 0 olmalı
    tavan_kalan_adet       kolun kaydında ⌊U(1−t)⌋ − dağıtılan paket × paket adedi (kapsama tavanı
                           herkesi bağlayınca depoda kalan); kayıt kolun değilse 0
    adaysiz_option         kolun kararında hiç aday mağazası olmayan option (hiç dağıtılmaz;
                           Lumoda'da da öyle)

**Dağıtım isabeti:**

    pay_wape               option başına mağaza payı (ilk dağıtım adedi) ile erken birincil talep
                           payı arasında `kalibrasyon.option_wape`, ilk alımla ağırlıklı ortalama.
                           Mağaza kümesi option'ın fiziksel hücresi olan mağazalar (payı ya da
                           talebi olmayan 0)
    ilk_hucre              ilk dağıtım alan (fiziksel mağaza, option) çifti
    oturan_hucre           ilk varıştan 28 günde satışı (pozitif `satis`, ikame dahil) ilk dağıtım
                           adedinin %20'sinin altında kalan çift
    hizli_biten_hucre      14 günde satışı ilk dağıtım adedinin ≥ %80'i olan çift
    tavan_baglayan         kolun kaydındaki `tavanda` toplamı (tavanı uygulanmış ve paketi tavana
                           eşit mağaza; tavan olmasa da o kadar alacak mağazayı da sayar)

**Beden** (ortak `perakende_analitik.stok.gunluk_magaza`'nın günlük tablosu: satış öncesi raf,
`durum`; koşunun oyun SKU'larına daraltılmış tablolarından. Tanım RPT / DM'nin günlük tablosuyla
aynı; ertesi pazartesi fotoğrafı olmayan hafta, ör. çıkıştan önceki son hafta, uygun değildir ve
girmez):

    kirik_cift_pay_yuzde   DM R29: en az iki bedeni tabloda olan (fiziksel mağaza, option, gün)
                           çiftlerinden stoklu olanlarda (beden rafları toplamı > 0) çekirdek
                           bedenlerinden (`CEKIRDEK_BEDENLER`, beden sırası 2–4) biri boş
                           (raf ≤ 0) olanların payı
    beden_kayip_payi       100 × karşılanmayan talebin, bedeni boşken aynı çiftin başka bir bedeni
                           stoklu olduğu SKU-günlerdeki kısmı ÷ Σ karşılanmayan
    depoda_kalan_beden_b   beş bedenli option'larda beden sırası b'nin ilk dağıtımdan sonra depoda
                           kalan payı: option'ın son ilk dağıtım sevkinin ertesi sabahı depo
                           stoğu ÷ (o stok + ilk dağıtım adedi), option'lar toplanarak
    ilk_tukenen_beden_b    ilk dağıtım alan beş bedenli çiftlerde, varıştan sonra rafı ilk biten
                           (gün içinde biten ya da boş) bedenin dağılımı (aynı gün birden çok beden
                           biterse eşit bölünür); `tukenen_hucre_yuzde` en az bir bedeni biten çift

**Korunum** (`RuntimeError`): kendi satış ≤ talep (hücre-gün); ilk dağıtım kaydı kolunsa
`kirpilan_adet` 0, option başına dağıtılan paket ≤ ⌊U(1−t)⌋ ve tavan bağlamadıysa (`tavanda` 0)
eşit; `kalan_depo_ek_adet` ≥ 0.

**Erken birincil talep** (spec §0/11). Pencere lansmandan `ERKEN_GUN` (42) gün, sezonun erken
kesiminde kesilir (`kaynak.erken_kesim`, dahil): `[lansman, min(lansman + 42, kesim + 1))`.
Birincil talep gizli gerçeğin `talep` sütunudur: hücrenin kendi müşterisi (v4 `kayit_talep`
talep çekilişini satıştan ve ikameden önce kaydeder; başka hücreden gelen ikame satışı `talep`e
girmez). Fiziksel mağazalar; (option, mağaza) başına toplam.
"""

import duckdb
import numpy as np
import pandas as pd
from perakende_analitik import stok as ortak_stok

from allocation import kalibrasyon, kaynak, motor, sabitler
from allocation.paylastir import paket_adedi

CEKIRDEK_BEDENLER = (2, 3, 4)
BES_BEDEN = 5
ILK4_GUN = 28
OTURAN_GUN, OTURAN_PAY = 28, 0.20
HIZLI_GUN, HIZLI_PAY = 14, 0.80
GERCEK = ["tarih", "magaza_id", "urun_id", "talep", "kendi_satis", "karsilanmayan", "ikameye_giden",
          "kalici_kayip"]
SEVK = ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip"]
SATIS = ["tarih", "magaza_id", "urun_id", "adet", "tutar", "indirim_tutari", "kampanya_id"]
SIPARIS = ["siparis_id", "tip", "option_id", "urun_id", "gerceklesen_teslim", "adet"]
GUN = np.timedelta64(1, "D")


def _oran(pay, payda) -> float:
    return 100.0 * float(pay) / float(payda) if payda > 0 else 0.0


def _kodla(s: pd.Series, evren: pd.Index) -> np.ndarray:
    """Kimlik sütununun `evren`deki konumu (yoksa ya da boşsa −1); kategorik sütunda kategoriler bir
    kez eşlenir."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        k = evren.get_indexer(pd.Index(s.cat.categories.astype(str)))
        kod = s.cat.codes.to_numpy()
        return np.where(kod >= 0, k[np.maximum(kod, 0)], -1)
    return evren.get_indexer(s.astype(str))


def _gun(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s).to_numpy().astype("datetime64[D]")


class Kapsam:
    """Sezonun `LINE` option'ları ve kimlik eşlemeleri (yalnız açık alanlar)."""

    def __init__(self, w, harita, optionlar):
        self.w, self.harita = w, harita
        self.opt = np.asarray(optionlar, dtype=np.int64)
        O = len(w.optionlar)
        self.secili = np.zeros(O, dtype=bool)
        self.secili[self.opt] = True
        self.urunler = pd.Index(w.urunler["urun_id"].astype(str))
        self.magazalar = pd.Index(w.magazalar["magaza_id"].astype(str))
        self.option_idler = pd.Index(w.optionlar["option_id"].astype(str))
        sku = self.secili[harita.sku_option]
        self.skular = self.urunler.to_numpy()[sku]
        self.lansman = _gun(w.optionlar["lansman_tarihi"])
        self.cikis = _gun(w.optionlar["cikis_tarihi"])
        self.beden_sayisi = np.bincount(harita.sku_option, minlength=O)
        tip = w.magazalar["tip"].astype(str).to_numpy()
        self.online = tip == "Online"
        self.outlet = tip == "Outlet"

    def sku(self, urun_id: pd.Series) -> np.ndarray:
        return _kodla(urun_id, self.urunler)

    def option(self, urun_id: pd.Series) -> np.ndarray:
        s = self.sku(urun_id)
        return np.where(s >= 0, self.harita.sku_option[np.maximum(s, 0)], -1)

    def magaza(self, magaza_id: pd.Series) -> np.ndarray:
        return _kodla(magaza_id, self.magazalar)

    def fiziksel(self, m: np.ndarray) -> np.ndarray:
        return (m >= 0) & np.asarray(self.harita.magaza_fiziksel)[np.maximum(m, 0)]

    def kapsamda(self, o: np.ndarray) -> np.ndarray:
        return (o >= 0) & self.secili[np.maximum(o, 0)]


# ---------------------------------------------------------------------------
# Kalibrasyonla ortak iki ölçüt
# ---------------------------------------------------------------------------


def baslangiclar(sevkiyat: pd.DataFrame, k: Kapsam) -> np.ndarray:
    """[O] datetime64[D]: option'ın ilk dağıtımının ilk varış günü; varışı olmayan kapsam
    option'ında lansman (modül notu)."""
    sv = sevkiyat[(sevkiyat["tip"].astype(str) == "ilk_dagitim").to_numpy() & sevkiyat["varis_tarihi"].notna().to_numpy()]
    o = k.option(sv["urun_id"])
    var = k.kapsamda(o)
    bas = k.lansman.copy()
    ilk = np.full(len(bas), np.datetime64("NaT"), dtype="datetime64[D]")
    if var.any():
        g = pd.Series(_gun(sv["varis_tarihi"])[var]).groupby(o[var]).min()
        ilk[g.index.to_numpy()] = g.to_numpy().astype("datetime64[D]")
    return np.where(np.isnat(ilk), bas, ilk)


def _musteri_maskesi(gercek: pd.DataFrame, k: Kapsam, bas: np.ndarray, ufuk: int | None = None):
    """(satır maskesi, option) gerçeğin kapsamdaki fiziksel, pencere içi satırları."""
    o = k.option(gercek["urun_id"])
    m = k.magaza(gercek["magaza_id"])
    secili = k.kapsamda(o) & k.fiziksel(m)
    t = _gun(gercek["tarih"])
    oo = np.maximum(o, 0)
    son = k.cikis[oo] if ufuk is None else np.minimum(k.cikis[oo], bas[oo] + ufuk * GUN)
    return secili & (t >= bas[oo]) & (t < son), o


def bulunabilirlik(gercek: pd.DataFrame, sevkiyat: pd.DataFrame, w, harita, optionlar,
                   ufuk: int | None = None) -> float:
    """Modül notu. `gercek`: `tarih, magaza_id, urun_id, talep, kendi_satis`; `sevkiyat`: en az
    `varis_tarihi, urun_id, tip`. `ufuk` gün verilirse pencere `[b_o, b_o + ufuk)`. Talepli
    hücre-gün yoksa 0."""
    k = Kapsam(w, harita, optionlar)
    icinde, _ = _musteri_maskesi(gercek, k, baslangiclar(sevkiyat, k), ufuk)
    talepli = icinde & (gercek["talep"].to_numpy() > 0)
    stoklu = talepli & (gercek["kendi_satis"].to_numpy() > 0)
    return _oran(int(stoklu.sum()), int(talepli.sum()))


def _alinan(siparis: pd.DataFrame, kalite: pd.DataFrame, k: Kapsam) -> dict[str, int]:
    """Teslim edilmiş ilk + RPT sipariş adedi, kalite reddi, RPT adedi (kapsam option'ları)."""
    ids = set(k.option_idler.to_numpy()[k.opt])
    sp = siparis[siparis["option_id"].astype(str).isin(ids).to_numpy()
                 & siparis["tip"].astype(str).isin(["ilk", "rpt"]).to_numpy()
                 & siparis["gerceklesen_teslim"].notna().to_numpy()]
    hatali = kalite[kalite["siparis_id"].astype(str).isin(set(sp["siparis_id"].astype(str))).to_numpy()]["hatali"]
    adet = sp["adet"].to_numpy(dtype=np.int64)
    return {"siparis": int(adet.sum()), "hatali": int(hatali.to_numpy(dtype=np.int64).sum()),
            "rpt": int(adet[(sp["tip"].astype(str) == "rpt").to_numpy()].sum())}


def _kalan(sevkiyat: pd.DataFrame, k: Kapsam, depo: pd.DataFrame | None) -> dict[str, int]:
    """Sezon sonu kalanın bileşenleri (modül notu)."""
    o = k.option(sevkiyat["urun_id"])
    sv = sevkiyat[k.kapsamda(o)]
    tip = sv["tip"].astype(str).to_numpy()
    adet = sv["adet"].to_numpy(dtype=np.int64)
    kaynak_depo = (sv["kaynak"].astype(str) == "DEPO").to_numpy()
    akis = tip == "outlet_akisi"
    devir = tip == "stok_devri"
    fiz_devir = devir & k.fiziksel(k.magaza(sv["kaynak"]))
    sonuc = {"akis_magaza": int(adet[akis & ~kaynak_depo].sum()), "akis_depo": int(adet[akis & kaynak_depo].sum()),
             "devir_fiziksel": int(adet[fiz_devir].sum()), "depo_ek": 0}
    if depo is not None and len(depo):
        T = _gun(depo["tarih"]).max()
        cikmis = k.secili & (k.cikis < T)
        do = k.option(depo["urun_id"])
        son = depo[(_gun(depo["tarih"]) == T) & k.kapsamda(do) & cikmis[np.maximum(do, 0)]]
        sv_o = o[k.kapsamda(o)]
        varan = devir & sv["varis_tarihi"].notna().to_numpy()
        varan &= _gun(sv["varis_tarihi"].fillna(pd.Timestamp("2262-01-01"))) < T
        varan &= cikmis[np.maximum(sv_o, 0)]
        ek = int(son["adet"].to_numpy(dtype=np.int64).sum()) - int(adet[varan].sum())
        if ek < 0:
            raise RuntimeError(f"çıkıştan sonra depodan mal çıkmış: son depo stoğu varan stok devrinden {-ek} eksik")
        sonuc["depo_ek"] = ek
    return sonuc


def sezon_sonu_kalan_yuzde(sevkiyat: pd.DataFrame, siparis: pd.DataFrame, kalite: pd.DataFrame,
                           w, harita, optionlar, depo: pd.DataFrame | None = None) -> float:
    """Modül notu. `siparis`: `siparis_id, tip, option_id, gerceklesen_teslim, adet`; `kalite`:
    `siparis_id, hatali`; `depo` (`depo_stok`: `tarih, urun_id, adet`) verilmezse çıkış sonrası
    depo eki 0. Teslim alınan mal yoksa 0."""
    k = Kapsam(w, harita, optionlar)
    a = _alinan(siparis, kalite, k)
    kalan = sum(_kalan(sevkiyat, k, depo).values())
    return _oran(kalan, a["siparis"] - a["hatali"])


# ---------------------------------------------------------------------------
# Erken birincil talep
# ---------------------------------------------------------------------------


def erken_pencere(w, k: Kapsam, sezon: str) -> tuple[np.ndarray, np.ndarray]:
    """[O] (başlangıç, bitiş hariç) datetime64[D]: lansmandan 42 gün, erken kesimde (dahil) kesik."""
    kesim = np.datetime64(kaynak.erken_kesim(w, sezon).date(), "D")
    bas = k.lansman
    return bas, np.minimum(bas + sabitler.ERKEN_GUN * GUN, kesim + GUN)


def erken_hucre_gunleri(kosu, w, harita, sezon: str = sabitler.OYUN_SEZONU) -> pd.DataFrame:
    """Erken penceredeki fiziksel hücre-günlerin birincil talebi: `tarih, magaza_id, urun_id,
    talep` (talep > 0 satırları, gizli gerçeğin sırasıyla). Kahinin bağımsızlık testinin
    karşılaştırdığı tablo."""
    k = Kapsam(w, harita, kaynak.oyun_optionlari(w, sezon))
    g = kosu.tablo("gercek", ["tarih", "magaza_id", "urun_id", "talep"], urunler=k.skular)
    o = k.option(g["urun_id"])
    bas, son = erken_pencere(w, k, sezon)
    t = _gun(g["tarih"])
    oo = np.maximum(o, 0)
    sec = k.kapsamda(o) & k.fiziksel(k.magaza(g["magaza_id"])) & (t >= bas[oo]) & (t < son[oo])
    g = g[sec & (g["talep"].to_numpy() > 0)].reset_index(drop=True)
    return pd.DataFrame({"tarih": pd.to_datetime(g["tarih"]).to_numpy(), "magaza_id": g["magaza_id"].astype(str).to_numpy(),
                         "urun_id": g["urun_id"].astype(str).to_numpy(), "talep": g["talep"].to_numpy(dtype=np.int64)})


def erken_birincil_talep(kosu, w, harita, sezon: str = sabitler.OYUN_SEZONU) -> pd.DataFrame:
    """(option, fiziksel mağaza) başına erken penceredeki birincil talep (modül notu):
    `option_id, magaza_id, talep` (int64; talebi olan çiftler; option_id, magaza_id sıralı)."""
    g = erken_hucre_gunleri(kosu, w, harita, sezon)
    u = pd.Series(w.urunler["option_id"].astype(str).to_numpy(), index=w.urunler["urun_id"].astype(str).to_numpy())
    g["option_id"] = g["urun_id"].map(u).to_numpy()
    t = g.groupby(["option_id", "magaza_id"], as_index=False, sort=True)["talep"].sum()
    return t.astype({"option_id": str, "magaza_id": str, "talep": np.int64})[["option_id", "magaza_id", "talep"]]


# ---------------------------------------------------------------------------
# Bileşenler
# ---------------------------------------------------------------------------


def _musteri(gercek: pd.DataFrame, k: Kapsam, bas: np.ndarray) -> dict[str, float]:
    if (gercek["kendi_satis"].to_numpy() > gercek["talep"].to_numpy()).any():
        raise RuntimeError("korunum: kendi satış talebi aşıyor")
    icinde, _ = _musteri_maskesi(gercek, k, bas)
    ilk4, _ = _musteri_maskesi(gercek, k, bas, ILK4_GUN)
    talep = gercek["talep"].to_numpy(dtype=np.int64)
    kendi = gercek["kendi_satis"].to_numpy(dtype=np.int64)
    sonuc = {}
    for ad, m in (("bulunabilirlik", icinde), ("bulunabilirlik_ilk4", ilk4)):
        t = m & (talep > 0)
        sonuc[ad] = _oran(int((t & (kendi > 0)).sum()), int(t.sum()))
    T = int(talep[icinde].sum())
    kars = int(gercek["karsilanmayan"].to_numpy(dtype=np.int64)[icinde].sum())
    sonuc.update({
        "talep_adet": float(T), "satis_adet": float(kendi[icinde].sum()),
        "kayip_orani": _oran(kars, T),
        "ikame_payi": _oran(int(gercek["ikameye_giden"].to_numpy(dtype=np.int64)[icinde].sum()), kars),
        "kalici_kayip_orani": _oran(int(gercek["kalici_kayip"].to_numpy(dtype=np.int64)[icinde].sum()), T),
    })
    return sonuc


def _hat(m: np.ndarray, k: Kapsam) -> np.ndarray:
    """Satışın fiyat hattı (v4 `hat_indisi`; Collection'da outlet mağazası = outlet akışı hücresi)."""
    mm = np.maximum(m, 0)
    return np.where(k.online[mm], "online", np.where(k.outlet[mm], "outlet", "normal"))


def _para(satis: pd.DataFrame, fiyat: pd.DataFrame, k: Kapsam, alinan_siparis: int) -> dict[str, float]:
    o = k.option(satis["urun_id"])
    t = _gun(satis["tarih"])
    sec = k.kapsamda(o) & (t < k.cikis[np.maximum(o, 0)])
    s, o, t = satis[sec].reset_index(drop=True), o[sec], t[sec]
    m = k.magaza(s["magaza_id"])
    onl = k.online[np.maximum(m, 0)]
    hat = _hat(m, k)
    adet = s["adet"].to_numpy(dtype=np.int64)
    tutar = s["tutar"].to_numpy(dtype=float)
    indirim = s["indirim_tutari"].to_numpy(dtype=float)
    kampanyasiz = s["kampanya_id"].isna().to_numpy()
    pozitif = adet > 0

    # markdown: option × hat × hafta oranı
    f = fiyat[fiyat["option_id"].astype(str).isin(set(k.option_idler.to_numpy()[k.opt])).to_numpy()]
    fo = _kodla(f["option_id"], k.option_idler)
    hafta = _gun(f["hafta_baslangic"])
    fh = f["hat"].astype(str).to_numpy()
    oran = pd.Series(f["indirim_orani"].to_numpy(dtype=float),
                     index=pd.MultiIndex.from_arrays([fo, fh, hafta.astype(np.int64)]))
    oran = oran[~oran.index.duplicated()]
    ilk_md = oran[oran > 0].reset_index().groupby(["level_0", "level_1"])["level_2"].min()
    pzt = (t - ((t.astype(np.int64) - 4) % 7) * GUN).astype(np.int64)   # 1970-01-05 pazartesi
    s_oran = oran.reindex(pd.MultiIndex.from_arrays([o, hat, pzt])).fillna(0.0).to_numpy()
    s_ilk = ilk_md.reindex(pd.MultiIndex.from_arrays([o, hat])).to_numpy(dtype=float)
    etiket = pozitif & kampanyasiz & ~(t.astype(np.int64) >= np.nan_to_num(s_ilk, nan=np.inf))
    md = pozitif & kampanyasiz & (s_oran > 0)

    alis = np.asarray(k.w.urunler["alis_fiyati"], dtype=float)[np.maximum(k.sku(s["urun_id"]), 0)]
    kar = tutar - adet * alis
    return {
        "tam_fiyat_str": _oran(int(adet[etiket].sum()), alinan_siparis),
        "markdown_tl_fiziksel": float(indirim[md & ~onl].sum()), "markdown_tl_online": float(indirim[md & onl].sum()),
        "markdown_tl": float(indirim[md].sum()),
        "brut_kar_tl_fiziksel": float(kar[~onl].sum()), "brut_kar_tl_online": float(kar[onl].sum()),
        "brut_kar_tl": float(kar.sum()),
        "online_satis": float(adet[onl & pozitif].sum()),
    }


def _ilk_adet(sevkiyat: pd.DataFrame, k: Kapsam) -> pd.DataFrame:
    """İlk dağıtımın (fiziksel mağaza, option) başına adedi ve ilk varış günü."""
    sv = sevkiyat[(sevkiyat["tip"].astype(str) == "ilk_dagitim").to_numpy()]
    o, m = k.option(sv["urun_id"]), k.magaza(sv["hedef"])
    sec = k.kapsamda(o) & k.fiziksel(m)
    df = pd.DataFrame({"o": o[sec], "m": m[sec], "adet": sv["adet"].to_numpy(dtype=np.int64)[sec],
                       "varis": pd.to_datetime(sv["varis_tarihi"]).to_numpy()[sec]})
    return df.groupby(["o", "m"], as_index=False).agg(adet=("adet", "sum"), varis=("varis", "min"))


def _isabet(ilk: pd.DataFrame, erken: pd.DataFrame, satis: pd.DataFrame, k: Kapsam) -> dict[str, float]:
    h = k.harita
    hucre = k.secili[h.hucre_option] & ~h.hucre_online & np.asarray(h.magaza_fiziksel)[h.hucre_magaza]
    evren = pd.DataFrame({"option": h.hucre_option[hucre], "magaza": h.hucre_magaza[hucre]}).drop_duplicates()
    e = pd.DataFrame({"option": _kodla(erken["option_id"], k.option_idler), "magaza": k.magaza(erken["magaza_id"]),
                      "talep": erken["talep"].to_numpy(dtype=float)})
    gercek = evren.merge(e, on=["option", "magaza"], how="left").fillna({"talep": 0.0})
    pay = ilk.rename(columns={"o": "option", "m": "magaza", "adet": "pay"})[["option", "magaza", "pay"]]
    agirlik = pd.Series(np.asarray(k.w.ilk_alim, dtype=float)[k.opt], index=k.opt)
    wape = kalibrasyon.pay_wape(pay.astype({"pay": float}), gercek, agirlik) if len(gercek) else float("nan")

    # oturan / hızlı biten: ilk varıştan itibaren pozitif satış
    o, m = k.option(satis["urun_id"]), k.magaza(satis["magaza_id"])
    pozitif = satis["adet"].to_numpy() > 0
    sec = k.kapsamda(o) & k.fiziksel(m) & pozitif
    sa = pd.DataFrame({"o": o[sec], "m": m[sec], "t": pd.to_datetime(satis["tarih"]).to_numpy()[sec],
                       "adet": satis["adet"].to_numpy(dtype=np.int64)[sec]})
    sa = sa.merge(ilk[["o", "m", "varis"]], on=["o", "m"], how="inner")
    gun = (sa["t"] - sa["varis"]).dt.days.to_numpy()
    s28 = sa[(gun >= 0) & (gun < OTURAN_GUN)].groupby(["o", "m"])["adet"].sum()
    s14 = sa[(gun >= 0) & (gun < HIZLI_GUN)].groupby(["o", "m"])["adet"].sum()
    idx = pd.MultiIndex.from_frame(ilk[["o", "m"]])
    q = ilk["adet"].to_numpy(dtype=float)
    s28 = s28.reindex(idx, fill_value=0).to_numpy(dtype=float)
    s14 = s14.reindex(idx, fill_value=0).to_numpy(dtype=float)
    dolu = q > 0
    return {"pay_wape": float(wape), "ilk_hucre": float(dolu.sum()),
            "oturan_hucre": float((dolu & (s28 < OTURAN_PAY * q)).sum()),
            "hizli_biten_hucre": float((dolu & (s14 >= HIZLI_PAY * q)).sum())}


def _kayit_olcutleri(kosu, w, k: Kapsam) -> dict[str, float]:
    """Kırpma, tavan ve korunum (kayıt kolunsa)."""
    kirp = motor.kirpma_tablosu(kosu, w)
    kirp = kirp[kirp["option_id"].isin(set(k.option_idler.to_numpy()[k.opt]))]
    pk = {o: paket_adedi(w, int(o)) for o in k.opt}
    ko = _kodla(kirp["option_id"], k.option_idler)
    kirpilan = int(sum((kirp["istenen_paket"] - kirp["giden_paket"]).to_numpy()
                       * np.array([pk[o] for o in ko], dtype=np.int64)))
    kayit = kosu.kayitlar.get("ilk_dagitim")
    sonuc = {"kirpilan_adet": float(kirpilan), "tavan_baglayan": 0.0, "tavan_kalan_adet": 0.0,
             "adaysiz_option": 0.0}
    if kayit is None or "kol" not in kayit.columns:
        return sonuc
    kendi = kayit[kayit["kol"].to_numpy(dtype=bool) & k.secili[kayit["arg0"].to_numpy()]]
    if kirpilan or len(kirp):
        raise RuntimeError(f"korunum: kolun kararını motor kırptı ({len(kirp)} (option, mağaza), {kirpilan} adet)")
    oz = kendi.groupby("arg0").agg(toplam=("toplam", "first"), tavanda=("tavanda", "first"),
                                    giden=("deger", "sum"), aday=("indis", lambda i: bool((i >= 0).any())))
    if (oz["giden"] > oz["toplam"]).any():
        raise RuntimeError("korunum: kol ⌊U(1−t)⌋'dan fazla paket dağıttı")
    bagsiz = oz["aday"] & (oz["tavanda"] == 0)
    if (oz.loc[bagsiz, "giden"] != oz.loc[bagsiz, "toplam"]).any():
        raise RuntimeError("korunum: tavan bağlamadığı hâlde dağıtılan paket ⌊U(1−t)⌋'dan az")
    pk_o = np.array([pk[int(o)] for o in oz.index], dtype=np.int64)
    kalan = (oz["toplam"] - oz["giden"]).to_numpy() * pk_o
    aday = oz["aday"].to_numpy(dtype=bool)
    sonuc.update(tavan_baglayan=float(oz["tavanda"].sum()), tavan_kalan_adet=float(kalan[aday].sum()),
                 adaysiz_option=float((~aday).sum()))
    return sonuc


def _gunluk(kosu, k: Kapsam, bas, bit) -> pd.DataFrame:
    """Oyun SKU'larının günlük mağaza tablosu (ortak `stok.gunluk_magaza`), koşunun tablolarından."""
    tablolar = {"satis": kosu.tablo("satis", SATIS, urunler=k.skular),
                "stok": kosu.tablo("stok", urunler=k.skular),
                "sevkiyat": kosu.tablo("sevkiyat", urunler=k.skular),
                "urun": kosu.tablo("urun", urunler=k.skular),
                "magaza": kosu.tablo("magaza"), "magaza_olay": kosu.tablo("magaza_olay")}
    con = duckdb.connect(":memory:")
    try:
        for ad, df in tablolar.items():
            con.register(ad, df)
        return ortak_stok.gunluk_magaza(con, bas, bit)
    finally:
        con.close()


def _beden(gunluk: pd.DataFrame, gercek: pd.DataFrame, ilk: pd.DataFrame, k: Kapsam, bas: np.ndarray
           ) -> dict[str, float]:
    h = k.harita
    s, m = k.sku(gunluk["urun_id"]), k.magaza(gunluk["magaza_id"])
    o = np.where(s >= 0, h.sku_option[np.maximum(s, 0)], -1)
    t = _gun(gunluk["tarih"])
    oo = np.maximum(o, 0)
    sec = k.kapsamda(o) & k.fiziksel(m) & (t >= bas[oo]) & (t < k.cikis[oo]) & (k.beden_sayisi[oo] >= 2)
    g = pd.DataFrame({"m": m[sec], "o": o[sec], "s": s[sec], "b": h.sku_beden_sira[s[sec]],
                      "t": t[sec].astype(np.int64), "raf": gunluk["satis_oncesi"].to_numpy(dtype=np.int64)[sec],
                      "durum": gunluk["durum"].cat.codes.to_numpy()[sec]})
    durum = list(gunluk["durum"].cat.categories)
    STOKLU = durum.index("stoklu")
    g["pozitif"] = np.maximum(g["raf"].to_numpy(), 0)
    g["cekirdek_bos"] = np.isin(g["b"].to_numpy(), CEKIRDEK_BEDENLER) & (g["raf"].to_numpy() <= 0)
    cift = g.groupby(["m", "o", "t"]).agg(n=("s", "size"), toplam=("pozitif", "sum"), kirik=("cekirdek_bos", "any"))
    cift = cift[cift["n"] >= 2]
    stoklu = cift["toplam"] > 0
    sonuc = {"stoklu_cift_gun": float(stoklu.sum()),
             "kirik_cift_pay_yuzde": _oran(int((stoklu & cift["kirik"]).sum()), int(stoklu.sum()))}

    # beden kaybı: bedeni boşken çiftin başka bedeni stoklu
    g = g.join(cift["toplam"].rename("cift_toplam"), on=["m", "o", "t"], how="inner")
    beden_bos = (g["raf"].to_numpy() <= 0) & (g["cift_toplam"].to_numpy() - g["pozitif"].to_numpy() > 0)
    bb = g.loc[beden_bos, ["m", "s", "t"]]
    icinde, _ = _musteri_maskesi(gercek, k, bas)
    gk = pd.DataFrame({"m": k.magaza(gercek["magaza_id"])[icinde], "s": k.sku(gercek["urun_id"])[icinde],
                       "t": _gun(gercek["tarih"])[icinde].astype(np.int64),
                       "kars": gercek["karsilanmayan"].to_numpy(dtype=np.int64)[icinde]})
    payda = int(gk["kars"].sum())
    pay = int(gk.merge(bb, on=["m", "s", "t"], how="inner")["kars"].sum())
    sonuc["beden_kayip_payi"] = _oran(pay, payda)

    # ilk tükenen beden: ilk dağıtım alan beş bedenli çiftler, varıştan sonra
    bes = ilk[k.beden_sayisi[ilk["o"].to_numpy()] == BES_BEDEN]
    gg = g[k.beden_sayisi[g["o"].to_numpy()] == BES_BEDEN].merge(
        bes.assign(v=bes["varis"].to_numpy().astype("datetime64[D]").astype(np.int64))[["o", "m", "v"]],
        on=["o", "m"], how="inner")
    biten = gg[(gg["t"] >= gg["v"]) & (gg["durum"] != STOKLU)]
    ilk_gun = biten.groupby(["m", "o"])["t"].transform("min")
    ilk_biten = biten[biten["t"] == ilk_gun]
    agirlik = 1.0 / ilk_biten.groupby(["m", "o"])["b"].transform("size")
    dagilim = agirlik.groupby(ilk_biten["b"]).sum()
    n_biten = int(ilk_biten.groupby(["m", "o"]).ngroups)
    for b in range(1, BES_BEDEN + 1):
        sonuc[f"ilk_tukenen_beden_{b}"] = _oran(float(dagilim.get(b, 0.0)), n_biten)
    sonuc["tukenen_hucre_yuzde"] = _oran(n_biten, int((bes["adet"] > 0).sum()))
    return sonuc


def _depoda_kalan_beden(sevkiyat: pd.DataFrame, depo: pd.DataFrame, k: Kapsam) -> dict[str, float]:
    h = k.harita
    sv = sevkiyat[(sevkiyat["tip"].astype(str) == "ilk_dagitim").to_numpy()]
    s = k.sku(sv["urun_id"])
    o = np.where(s >= 0, h.sku_option[np.maximum(s, 0)], -1)
    sec = k.kapsamda(o) & (k.beden_sayisi[np.maximum(o, 0)] == BES_BEDEN)
    sv = pd.DataFrame({"o": o[sec], "s": s[sec], "t": _gun(sv["tarih"])[sec],
                      "adet": sv["adet"].to_numpy(dtype=np.int64)[sec]})
    son = sv.groupby("o")["t"].max() + GUN                       # son sevkin ertesi sabahı
    giden = sv.groupby("s")["adet"].sum()
    ds = k.sku(depo["urun_id"])
    d = pd.DataFrame({"s": ds, "t": _gun(depo["tarih"]), "adet": depo["adet"].to_numpy(dtype=np.int64)})
    d = d[ds >= 0]
    d["o"] = h.sku_option[d["s"].to_numpy()]
    d = d[d["o"].isin(son.index)]
    d = d[d["t"].to_numpy() == son.reindex(d["o"]).to_numpy()]
    kalan = d.groupby("s")["adet"].sum().reindex(giden.index, fill_value=0)
    b = h.sku_beden_sira[giden.index.to_numpy()]
    sonuc = {}
    for bb in range(1, BES_BEDEN + 1):
        m = b == bb
        sonuc[f"depoda_kalan_beden_{bb}"] = _oran(int(kalan.to_numpy()[m].sum()),
                                                   int(kalan.to_numpy()[m].sum() + giden.to_numpy()[m].sum()))
    return sonuc


# ---------------------------------------------------------------------------
# Hepsi
# ---------------------------------------------------------------------------


def hesapla(kosu, w, harita, sezon: str = sabitler.OYUN_SEZONU) -> dict[str, float]:
    """Koşunun ölçütleri (modül notu); her değer `float`."""
    k = Kapsam(w, harita, kaynak.oyun_optionlari(w, sezon))
    sevk = kosu.tablo("sevkiyat", SEVK, urunler=k.skular)
    bas = baslangiclar(sevk, k)
    sonuc = {}

    gercek = kosu.tablo("gercek", GERCEK, urunler=k.skular)
    sonuc |= _musteri(gercek, k, bas)

    siparis = kosu.tablo("siparis", SIPARIS, urunler=k.skular)
    kalite = kosu.tablo("kalite_kontrol", ["siparis_id", "hatali"])
    depo = kosu.tablo("depo_stok", ["tarih", "urun_id", "adet"], urunler=k.skular)
    a = _alinan(siparis, kalite, k)
    kl = _kalan(sevk, k, depo)
    toplam_mal = a["siparis"] - a["hatali"]
    sonuc.update({
        "toplam_mal": float(toplam_mal), "rpt_adet": float(a["rpt"]),
        "kalan_magaza_adet": float(kl["akis_magaza"] + kl["devir_fiziksel"]),
        "kalan_depo_adet": float(kl["akis_depo"] + kl["depo_ek"]), "kalan_depo_ek_adet": float(kl["depo_ek"]),
        "sezon_sonu_kalan_yuzde": _oran(sum(kl.values()), toplam_mal),
    })
    o = k.option(sevk["urun_id"])
    tip = sevk["tip"].astype(str).to_numpy()
    adet = sevk["adet"].to_numpy(dtype=np.int64)
    once = _gun(sevk["tarih"]) < k.cikis[np.maximum(o, 0)]
    sonuc.update({"ilk_dagitim_adet": float(adet[tip == "ilk_dagitim"].sum()),
                  "replenishment_adet": float(adet[tip == "replenishment"].sum()),
                  "elle_transfer_adet": float(adet[(tip == "elle_transfer") & once].sum())})
    sonuc |= _depoda_kalan_beden(sevk, depo, k)
    del siparis, kalite, depo

    satis = kosu.tablo("satis", SATIS, urunler=k.skular)
    sonuc |= _para(satis, kosu.tablo("fiyat", ["hafta_baslangic", "option_id", "hat", "indirim_orani"]), k,
                   a["siparis"])
    ilk = _ilk_adet(sevk, k)
    sonuc |= _isabet(ilk, erken_birincil_talep(kosu, w, harita, sezon), satis, k)
    del satis
    sonuc |= _kayit_olcutleri(kosu, w, k)

    if len(k.opt):
        gun_bas = pd.Timestamp(bas[k.opt].min()).date()
        gun_son = (pd.Timestamp(k.cikis[k.opt].max()) - pd.Timedelta(days=1)).date()
        sonuc |= _beden(_gunluk(kosu, k, gun_bas, gun_son), gercek, ilk, k, bas)
    return {a: float(v) for a, v in sonuc.items()}
