"""Lumoda'nın bugünkü kararları — v4 motorunun varsayılan politikaları.

Dokuz politika vardır (spec §6.2) ve hepsi enjekte edilebilir
(`Politikalar`); arayüz ve günlük sıra için `motor.dongu`'nun belgesine
bakın. Her politika yalnız `Gorunum`'u okur (kamuya açık alanlar, bkz.
`motor.durum.Gorunum`); gizli gerçeğe (gerçek λ, esneklik, tedarikçi
profili, segment) bakmaz.

    ilk_dagitim(g, o)   -> [M] paket sayısı          (Görev 12, Lumoda)
    paket_secimi(g, o)  -> [M] paket indisi          (Görev 12, Lumoda)
    replenishment(g)    -> [C] depodan istenen adet  (Görev 12, Lumoda)
    rpt(g)              -> {option: adet}            (Görev 13, `LumodaRPT`, v3)
    markdown(g)         -> [O, 3] indirim oranı      (Görev 13, `LumodaMarkdown`)
    acilis(g, m)        -> Transferler               (Görev 14; şimdilik boş)
    kapanis(g, m)       -> Transferler               (Görev 14; şimdilik boş)
    elle_transfer(g)    -> Transferler               (Görev 14; şimdilik boş)
    outlet_akisi(g, os) -> Transferler               (Görev 13, Lumoda)

Tedarikçi seçimi burada değildir: `dunya_kur(tedarikci_secimi=…)`
parametresidir (sipariş dünyada önceden kurulur).

v4 hiçbir v2/v3/kök modülünü içe aktarmaz (v3 `mevcut_dagitim` ve
`LumodaRPT` kuralları kopyalanmıştır).
"""

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from . import sabitler
from .plan import en_buyuk_kalan, moq_yuvarla


# ---------------------------------------------------------------------------
# Transferler
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Transferler:
    """Mal hareketi istekleri, satır başına: `kaynak` → `hedef` (mağaza
    satır indisi; −1 = depo), `sku`, `adet`. Motor kaynağın stoğuyla
    sınırlar, hedefte hücre yoksa satırı atar, yolda süreyi uygular."""

    kaynak: np.ndarray
    hedef: np.ndarray
    sku: np.ndarray
    adet: np.ndarray

    @staticmethod
    def bos() -> "Transferler":
        z = np.zeros(0, dtype=np.int64)
        return Transferler(z, z, z, z)


# ---------------------------------------------------------------------------
# Paket tablosu
# ---------------------------------------------------------------------------


def paket_tablosu(paketler: pd.DataFrame) -> tuple[np.ndarray, dict[str, int], np.ndarray]:
    """(`paket_idleri` [P], beden seti → standart paket indisi,
    `icerik` [P, K]: paket indisi × beden_sira → adet).

    Paket indisi `paket_idleri` sırasıdır (ilk görülme; `sevkiyat.paket_id`
    bu indisi taşır, −1 = paketsiz). `icerik[p, beden_sira]`; paketin
    taşımadığı beden 0."""
    ids = paketler["paket_id"].drop_duplicates().to_numpy()
    idx = {p: i for i, p in enumerate(ids)}
    K = int(paketler["beden_sira"].max()) + 1
    icerik = np.zeros((len(ids), K), dtype=np.int64)
    p = paketler["paket_id"].map(idx).to_numpy()
    icerik[p, paketler["beden_sira"].to_numpy()] = paketler["adet"].to_numpy()
    set_idx = {}
    for bs, pid in zip(paketler["beden_seti"], paketler["paket_id"]):
        set_idx.setdefault(bs, idx[pid])
    return ids, set_idx, icerik


# ---------------------------------------------------------------------------
# Lumoda: ilk dağıtım, paket, replenishment
# ---------------------------------------------------------------------------


def _option_magazalari(w, o: int) -> np.ndarray:
    """[M] bool: option'ın ilk dağıtım alabilecek hücresi olan mağazalar
    (fiziksel, outlet akışı olmayan hücre)."""
    maske = (w.hucre_option == o) & ~w.hucre_online & ~w.hucre_outlet_akisi
    sonuc = np.zeros(len(w.magazalar), dtype=bool)
    sonuc[w.hucre_magaza[maske]] = True
    return sonuc


def lumoda_paket_secimi(g, o: int) -> np.ndarray:
    """[M] paket indisi: her mağazaya option'ın beden setinin tek standart
    paketi (Lumoda'da set başına bir paket)."""
    w = g.dunya
    _, set_idx, _ = paket_tablosu(w.paketler)
    return np.full(len(w.magazalar), set_idx[w.optionlar.at[o, "beden_seti"]], dtype=np.int64)


def lumoda_ilk_dagitim(g, o: int) -> np.ndarray:
    """[M] paket sayısı.

    Toplam paket = ⌊ilk alım × ILK_DAGITIM_PAYI ÷ paket adedi⌋; mağazalara
    `magaza_plan`'daki (option'ın sezonu × üst kategorisi) satış hedefi
    payıyla, en büyük kalanla bölünür. Aday mağaza: option'ın fiziksel,
    outlet akışı olmayan hücresi var; kapanış kararı verilmemiş; bugün açık
    ya da lansmana kadar açılacak (yayımlanan `acilis_tarihi`) ve lansmandan
    önce kapanmıyor. Kalan ilk alım depoda kalır (online + replenishment).
    """
    w = g.dunya
    opt = w.optionlar
    mag = w.magazalar
    lansman_t = opt.at[o, "lansman_tarihi"]
    aday = _option_magazalari(w, o) & ~np.asarray(g.kapanacak)
    acilis_t = pd.to_datetime(mag["acilis_tarihi"])
    kapanis_t = pd.to_datetime(mag["kapanis_tarihi"])
    aday &= np.asarray(g.acik_magaza) | (acilis_t <= lansman_t).to_numpy()
    aday &= ~(kapanis_t.notna() & (kapanis_t <= lansman_t)).to_numpy()
    if not aday.any():
        return np.zeros(len(mag), dtype=np.int64)

    mp = w.plan_tablolari["magaza_plan"]
    sec = mp[(mp.sezon_kodu == opt.at[o, "sezon_kodu"]) & (mp.ust_kategori == opt.at[o, "ust_kategori"])]
    hedef = (
        sec.set_index("magaza_id")["satis_hedefi"]
        .reindex(mag["magaza_id"]).fillna(0).to_numpy(dtype=float)
    )
    pay = np.where(aday, hedef, 0.0)
    if pay.sum() <= 0:
        pay = aday.astype(float)

    _, set_idx, icerik = paket_tablosu(w.paketler)
    paket_adedi = int(icerik[set_idx[opt.at[o, "beden_seti"]]].sum())
    toplam = int(w.ilk_alim[o] * sabitler.ILK_DAGITIM_PAYI // paket_adedi)
    return en_buyuk_kalan(toplam, pay)


def lumoda_replenishment(g) -> np.ndarray:
    """[C] haftalık replenishment isteği (v3 `mevcut_dagitim` kuralı).

    Hedef    önümüzdeki 28 günün PLAN talebi (sürprizi, yerel sapmayı
             bilmez; planlı indirimin talep artışını bilir)
    İstek    max(hedef − mağaza stoğu − yolda, 0) (v4: yoldaki mal sayılır)
    Kapı     hücre yeni değilse (option'ın ilk dağıtımından beri ≥ 28 gün)
             ve son 28 günlük satış hızıyla zaten 4 haftalık stoğu varsa mal
             gitmez — hız sıfırsa HİÇ gitmez (kasıtlı v3 kusuru).
    Sıfır    ONL hücreleri (online depodan satar), kapalı ve kapanış kararı
             verilmiş mağazalar.

    Depo yetmezse motor istekleri SKU içinde orantılı keser; dağıtılamaz
    hücreleri (ilk dağıtımı bitmemiş, çıkmış, outlet akışı) motor sıfırlar.
    """
    w = g.dunya
    hedef = np.rint(w.ileri_plan(g.gun, sabitler.REPL_HEDEF_GUN)).astype(np.int64)
    eksik = np.maximum(hedef - g.magaza_stok - g.yolda, 0)
    ilk_gun = g.ilk_dagitim_gun[w.hucre_option]
    yeni = (g.gun - ilk_gun) < sabitler.OLU_STOK_PENCERESI_GUN
    haftalik_hiz = g.satis_28 / sabitler.OLU_STOK_PENCERESI_GUN * 7.0
    uygun = yeni | (g.magaza_stok < haftalik_hiz * sabitler.OLU_STOK_HEDEF_HAFTA)
    magaza_uygun = np.asarray(g.acik_magaza) & ~np.asarray(g.kapanacak)
    uygun &= magaza_uygun[w.hucre_magaza] & ~w.hucre_online
    return np.where(uygun, eksik, 0)


# ---------------------------------------------------------------------------
# Lumoda: RPT, markdown, outlet akışı (Görev 13)
# ---------------------------------------------------------------------------


def _tedarikci_sutunu(w, sutun: str) -> np.ndarray:
    """[O] option'ın tedarikçisinin yayımlanan bir sütunu (`optionlar.tedarikci_id`
    üzerinden; gizli profil okunmaz)."""
    t = w.tedarikciler.set_index("tedarikci_id")[sutun]
    return t.loc[w.optionlar["tedarikci_id"]].to_numpy()


def _str(pay: np.ndarray, gonderilen: np.ndarray) -> np.ndarray:
    """[O] STR = pay ÷ mağazalara giden (hiç gitmemişse 0)."""
    gonderilen = np.asarray(gonderilen)
    return np.divide(pay, gonderilen, out=np.zeros(len(gonderilen)), where=gonderilen > 0)


class LumodaRPT:
    """Her pazartesi, lansmandan 3–6 hafta sonraki Collection option'ları
    (v3 `LumodaRPT` birebir; RPT süresi ve MOQ option'ın tedarikçisinden).

    Tetik    zincir STR'si (brüt satış ÷ mağazalara giden) ≥ %55
    Yetişme  lansman + 3 hafta + RPT süresi < indirim başı
             (siparişin verildiği güne değil lansmana bakar; teslim
             sapmasını görmez — kasıtlı kusur)
    Miktar   ilk alımın %50'si, en az MOQ (10'un katına yukarı)
    Sınır    option başına en fazla bir RPT

    STR'nin payı dünkü akşama kadarki satış, paydası bu sabaha kadar
    mağazalara giden (ilk dağıtım + replenishment + depodan outlet akışı;
    mağazadan geri dönüş düşülmez).
    """

    def __init__(
        self,
        str_esigi: float = sabitler.RPT_STR_ESIGI,
        ilk_hafta: int = sabitler.RPT_ILK_HAFTA,
        son_hafta: int = sabitler.RPT_SON_HAFTA,
        miktar_orani: float = sabitler.RPT_MIKTAR_ORANI,
    ):
        self.str_esigi = str_esigi
        self.ilk_hafta = ilk_hafta
        self.son_hafta = son_hafta
        self.miktar_orani = miktar_orani

    def __call__(self, g) -> dict[int, int]:
        w = g.dunya
        opt = w.optionlar
        d = g.gun
        h = d - opt["lansman_gun"].to_numpy()
        pencere = (h >= 7 * self.ilk_hafta) & (h <= 7 * self.son_hafta)
        aday = (
            (opt["line"].to_numpy() == "Collection")
            & pencere
            & (np.asarray(g.rpt_sayisi) == 0)
            & (np.asarray(g.gonderilen_option) > 0)
        )
        if not aday.any():
            return {}
        rpt_hafta = _tedarikci_sutunu(w, "rpt_hafta")
        yetisir = (
            opt["lansman_gun"].to_numpy() + 7 * self.ilk_hafta + 7 * rpt_hafta
        ) < opt["indirim_gun"].to_numpy()
        secilen = np.flatnonzero(
            aday & (_str(g.satilan_option, g.gonderilen_option) >= self.str_esigi) & yetisir
        )
        if not secilen.size:
            return {}
        moq = _tedarikci_sutunu(w, "moq_option")
        miktar = moq_yuvarla(self.miktar_orani * np.asarray(w.ilk_alim)[secilen], moq[secilen])
        return {int(o): int(m) for o, m in zip(secilen, miktar)}


class LumodaMarkdown:
    """Lumoda'nın markdown kuralı, [O, 3] (normal / outlet / online hattı).

    Normal ve online hat (aynı oran): Collection ve Outlet line, her
    pazartesi `indirim_gun − 28`'den çıkışa kadar.
        beklenen = 0,80 × min(1, (d − lansman) ÷ (indirim − lansman))
        STR (fiziksel mağazaların brüt satışı, ONL hariç ÷ mağazalara
        giden; payla payda aynı kanaldan) < 0,7 × beklenen ise bir kademe
        derinleşir (haftada en fazla bir kademe); d ≥ indirim_gun iken en az
        %30. Kademeler %20 / 30 / 40 / 50 / 70; oran hiç sığlaşmaz.
    İçseldir: STR'si düşük option daha erken ve daha derin indirilir (esneklik
    tuzağı). Devamlı (Basic/NOS) option'lar bu kuralla hiç indirilmez.

    Outlet hattı (outlet akışı hücreleri): Collection option çıkış gününde
    %50'den başlar, her 4 haftada bir kademe (en çok %70), outlet penceresi
    boyunca. Outlet mağazasında normal pencereyle satılan Outlet line normal
    hattı izler (motor hücreyi hattına eşler).
    """

    def __init__(
        self,
        kademeler=sabitler.MARKDOWN_KADEMELERI,
        once_gun: int = sabitler.MARKDOWN_ONCE_GUN,
        beklenen_str: float = sabitler.MARKDOWN_BEKLENEN_STR,
        tetik: float = sabitler.MARKDOWN_TETIK,
        indirim_tabani: float = sabitler.MARKDOWN_INDIRIM_TABANI,
        outlet_baslangic: float = sabitler.OUTLET_MARKDOWN_BASLANGIC,
        outlet_aralik_gun: int = sabitler.OUTLET_MARKDOWN_ARALIK_GUN,
        outlet_omru_gun: int = sabitler.OUTLET_OMRU_GUN,
    ):
        self.kademeler = np.asarray(kademeler, dtype=float)
        self.once_gun = once_gun
        self.beklenen_str = beklenen_str
        self.tetik = tetik
        self.indirim_tabani = indirim_tabani
        self.outlet_baslangic = outlet_baslangic
        self.outlet_aralik_gun = outlet_aralik_gun
        self.outlet_omru_gun = outlet_omru_gun

    def __call__(self, g) -> np.ndarray:
        w = g.dunya
        opt = w.optionlar
        d = g.gun
        k = self.kademeler
        yeni = np.array(g.fiyat_orani, dtype=float, copy=True)
        lan, ind, cik = (opt[c].to_numpy() for c in ("lansman_gun", "indirim_gun", "cikis_gun"))
        sezonluk = opt["sezonluk"].to_numpy(dtype=bool)

        # Normal ve online hat
        su_an = np.maximum(yeni[:, 0], yeni[:, 2])
        aktif = sezonluk & (d >= lan) & (d >= ind - self.once_gun) & (d < cik)
        if aktif.any():
            ilerleme = np.clip((d - lan) / np.maximum(ind - lan, 1), 0.0, 1.0)
            beklenen = self.beklenen_str * ilerleme
            str_ = _str(g.satilan_option_magaza, g.gonderilen_option)
            derin = aktif & (str_ < self.tetik * beklenen)
            sonraki = k[np.minimum(np.searchsorted(k, su_an + 1e-9, side="right"), len(k) - 1)]
            oran = np.where(derin, np.maximum(su_an, sonraki), su_an)
            oran = np.where(aktif & (d >= ind), np.maximum(oran, self.indirim_tabani), oran)
            yeni[:, 0] = np.where(aktif, oran, yeni[:, 0])
            yeni[:, 2] = np.where(aktif, oran, yeni[:, 2])

        # Outlet hattı (outlet akışıyla gelen Collection)
        t = d - cik
        outlet = (opt["line"].to_numpy() == "Collection") & (t >= 0) & (t < self.outlet_omru_gun)
        if outlet.any():
            bas = int(np.searchsorted(k, self.outlet_baslangic - 1e-9))
            hedef = k[np.minimum(bas + np.maximum(t, 0) // self.outlet_aralik_gun, len(k) - 1)]
            yeni[:, 1] = np.where(outlet, np.maximum(yeni[:, 1], hedef), yeni[:, 1])
        return yeni


def lumoda_outlet_akisi(g, os: np.ndarray) -> Transferler:
    """Sezon çıkışında kalan stok outlet mağazalarına (`os` bugün çıkan
    option'lar).

    Hedef    bugün açık, kapanış kararı verilmemiş ve option'ı outlet akışı
             hücresi olarak taşıyan outlet mağazaları
    Mağaza   her normal fiziksel mağazanın (AVM/cadde) o option'daki stoğu
             en yakın hedef outlet mağazasına (`mesafe_km`)
    Depo     option'ın depo stoğu hedef outlet mağazalarına son 28 günün
             outlet hattı satış payıyla (bütün option'lar; hiç yoksa
             kapasite payıyla), SKU başına en büyük kalanla

    Hedef yoksa transfer yok (motor kapanmış penceredeki raf stoğunu
    `stok_devri` ile depoya devreder). Yolda süre motorca uygulanır.
    """
    w = g.dunya
    mag = w.magazalar
    tip = mag["tip"].to_numpy()
    M = len(mag)
    hm, hs, ho = w.hucre_magaza, w.hucre_sku, w.hucre_option
    outlet_c = np.asarray(w.hucre_outlet_akisi)
    stok = np.asarray(g.magaza_stok)
    depo = np.asarray(g.depo)
    uygun_m = (tip == "Outlet") & np.asarray(g.acik_magaza) & ~np.asarray(g.kapanacak)
    normal_m = ~np.isin(tip, ["Outlet", "Online"])
    # Son 28 günün outlet hattı satışı (mağaza başına)
    outlet_satis = np.bincount(hm[outlet_c], np.asarray(g.satis_28)[outlet_c], minlength=M)
    kapasite = mag["kapasite"].to_numpy(dtype=float)

    k, h, s, a = [], [], [], []
    for o in np.asarray(os, dtype=np.int64):
        oc = ho == o
        hedef_m = np.zeros(M, dtype=bool)
        hedef_m[hm[oc & outlet_c]] = True
        hedef_m &= uygun_m
        hedefler = np.flatnonzero(hedef_m)
        if hedefler.size == 0:
            continue
        # Normal mağazalar → en yakın hedef
        kc = np.flatnonzero(oc & normal_m[hm] & (stok > 0))
        if kc.size:
            en_yakin = hedefler[np.argmin(w.mesafe_km[np.ix_(hm[kc], hedefler)], axis=1)]
            k.append(hm[kc]); h.append(en_yakin); s.append(hs[kc]); a.append(stok[kc])
        # Depo → satış (yoksa kapasite) payıyla
        pay = outlet_satis[hedefler].astype(float)
        if pay.sum() <= 0:
            pay = kapasite[hedefler]
        for sk in np.flatnonzero((w.sku_option == o) & (depo > 0)):
            bol = en_buyuk_kalan(int(depo[sk]), pay)
            v = bol > 0
            k.append(np.full(int(v.sum()), -1)); h.append(hedefler[v])
            s.append(np.full(int(v.sum()), sk)); a.append(bol[v])
    if not k:
        return Transferler.bos()
    b = lambda x: np.concatenate(x).astype(np.int64)  # noqa: E731
    return Transferler(b(k), b(h), b(s), b(a))


lumoda_rpt = LumodaRPT()
lumoda_markdown = LumodaMarkdown()


# ---------------------------------------------------------------------------
# Yer tutucular (Görev 14 doldurur; imzalar sabit)
# ---------------------------------------------------------------------------


def lumoda_acilis(g, m: int) -> Transferler:
    """Görev 14: yeni mağazanın açılış transferi. Şimdilik boş."""
    return Transferler.bos()


def lumoda_kapanis(g, m: int) -> Transferler:
    """Görev 14: kapanan mağazanın stoğu. Şimdilik boş."""
    return Transferler.bos()


def lumoda_elle_transfer(g) -> Transferler:
    """Görev 14: bölge müdürünün haftalık elle transferleri. Şimdilik boş."""
    return Transferler.bos()


def lumoda_politikalari() -> dict[str, Callable]:
    """Dokuz politikanın Lumoda karşılıkları (`Politikalar` alan sırası)."""
    return dict(_LUMODA)


_LUMODA: dict[str, Callable] = {
    "ilk_dagitim": lumoda_ilk_dagitim,
    "paket_secimi": lumoda_paket_secimi,
    "replenishment": lumoda_replenishment,
    "rpt": lumoda_rpt,
    "markdown": lumoda_markdown,
    "acilis": lumoda_acilis,
    "kapanis": lumoda_kapanis,
    "elle_transfer": lumoda_elle_transfer,
    "outlet_akisi": lumoda_outlet_akisi,
}


def _varsayilan(ad: str):
    return field(default_factory=lambda: _LUMODA[ad])


@dataclass
class Politikalar:
    """Motorun enjekte edilebilir kararları; her alan varsayılan olarak
    Lumoda'nın bugünkü pratiğidir. Vaka yalnız değiştirdiği alanı verir:
    `Politikalar(replenishment=benim_kuralim)`."""

    ilk_dagitim: Callable = _varsayilan("ilk_dagitim")
    paket_secimi: Callable = _varsayilan("paket_secimi")
    replenishment: Callable = _varsayilan("replenishment")
    rpt: Callable = _varsayilan("rpt")
    markdown: Callable = _varsayilan("markdown")
    acilis: Callable = _varsayilan("acilis")
    kapanis: Callable = _varsayilan("kapanis")
    elle_transfer: Callable = _varsayilan("elle_transfer")
    outlet_akisi: Callable = _varsayilan("outlet_akisi")
