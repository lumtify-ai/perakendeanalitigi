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
    acilis(g, m)        -> Transferler               (Görev 14, yalnız depodan)
    kapanis(g, m)       -> Transferler               (Görev 14, bütün stok depoya)
    elle_transfer(g)    -> Transferler               (Görev 14, `LumodaElleTransfer`)
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
from .rastgele import sayac_uretici


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
    Kapı     hücre yeni değilse (max(option'ın ilk dağıtımı, mağazanın
             açılışı)'ndan beri ≥ 28 gün)
             ve son 28 günlük satış hızıyla zaten 4 haftalık stoğu varsa mal
             gitmez — hız sıfırsa HİÇ gitmez (kasıtlı v3 kusuru).
    Sıfır    ONL hücreleri (online depodan satar) ve bugün kapalı mağazalar.
    Kapanış  kapanış kararı verilmiş mağazaya kapanış gününe dek gönderir ve
             hedefi kararı yok sayar: o mağazanın hücrelerinde hedef, karar
             gününden önceki son pazartesinin 28 günlük plan hedefinde sabit
             kalır (plan kapanışı bilir ve daralır; kimse replenishment
             listesini düzeltmez — kasıtlı kusur). Mağaza anlamlı stokla
             kapanır, stok kapanış transferiyle depoya döner.

    Depo yetmezse motor istekleri SKU içinde orantılı keser; dağıtılamaz
    hücreleri (ilk dağıtımı bitmemiş, çıkmış, outlet akışı) motor sıfırlar.
    """
    w = g.dunya
    hedef = np.rint(w.ileri_plan(g.gun, sabitler.REPL_HEDEF_GUN)).astype(np.int64)
    for m, karar_pzt in _kapanis_karar_pazartesileri(w).items():
        if g.kapanacak[m] and g.acik_magaza[m]:
            c = w.hucre_magaza == m
            sabit = np.rint(w.ileri_plan(karar_pzt, sabitler.REPL_HEDEF_GUN)[c]).astype(np.int64)
            hedef[c] = sabit
    eksik = np.maximum(hedef - g.magaza_stok - g.yolda, 0)
    ilk_gun = np.maximum(
        np.asarray(g.ilk_dagitim_gun)[w.hucre_option], _acilis_gunleri(w)[w.hucre_magaza]
    )
    yeni = (g.gun - ilk_gun) < sabitler.OLU_STOK_PENCERESI_GUN
    haftalik_hiz = g.satis_28 / sabitler.OLU_STOK_PENCERESI_GUN * 7.0
    uygun = yeni | (g.magaza_stok < haftalik_hiz * sabitler.OLU_STOK_HEDEF_HAFTA)
    uygun &= np.asarray(g.acik_magaza)[w.hucre_magaza] & ~w.hucre_online
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
# Lumoda: açılış, kapanış, elle transfer (Görev 14)
# ---------------------------------------------------------------------------


def _acilis_gunleri(w) -> np.ndarray:
    """[M] mağazanın yayımlanan açılış tarihinin gün indisi (0 = ısınma
    başı; pencereden önce açılanlar negatif)."""
    t = pd.to_datetime(w.magazalar["acilis_tarihi"])
    return (t - pd.Timestamp(sabitler.ISINMA_BASLANGIC)).dt.days.to_numpy(dtype=np.int64)


def _kapanis_karar_pazartesileri(w) -> dict[int, int]:
    """{mağaza: kapanış karar gününden önceki (kesin) son pazartesi} (gün
    indisi; d = 0 pazartesidir). `magaza_olay` kamuya açıktır."""
    idx = {mid: i for i, mid in enumerate(w.magazalar["magaza_id"])}
    bas = pd.Timestamp(sabitler.ISINMA_BASLANGIC)
    sonuc = {}
    for r in w.magaza_olay[w.magaza_olay.olay == "kapanis"].itertuples():
        karar = int((pd.Timestamp(r.karar_tarihi) - bas).days)
        sonuc[idx[r.magaza_id]] = max((karar - 1) // 7 * 7, 0)
    return sonuc


def lumoda_acilis(g, m: int) -> Transferler:
    """Yeni mağazanın açılış transferi (Lumoda: "yalnız depodan, ne varsa").

    Motor bunu açılıştan `yolda_gun(depo → m)` gün önce çağırır; mal açılış
    günü varır.
    Hücreler  mağazanın açılış günü penceresi açık fiziksel, outlet akışı
              olmayan hücreleri; ilk dağıtımı bu mağazayı kapsamayan
              option'lar (lansman < açılış: dalga dağıtıldığında mağaza
              henüz yoktu; devamlılar dahil). Lansmanı açılışta ya da sonra
              olan option'lar ilk dağıtımdan pay alır.
    Hedef     açılış gününden itibaren 28 günlük plan talebi (Lumoda planı
              mağazanın açılışını ve olgunlaşmasını bilir)
    İstek     max(hedef − raf − yolda, 0)
    Kaynak    yalnız depo; depo neyi karşılıyorsa (SKU başına min(istek,
              depo) — mağazada SKU başına tek hücre, orantılı kesme tek
              istekte budur). Diğer mağazalardan hiçbir şey alınmaz
              (derinlikli mağazalar kullanılmaz). Depoda ne varsa alır —
              online (depodan satar) aç kalsa bile (kasıtlı naif pratik).
    """
    w = g.dunya
    acilis = int(_acilis_gunleri(w)[m])
    hm, hs, ho = w.hucre_magaza, w.hucre_sku, w.hucre_option
    lansman = w.optionlar["lansman_gun"].to_numpy()
    c = np.flatnonzero(
        (hm == m) & ~w.hucre_online & ~w.hucre_outlet_akisi
        & (w.hucre_acilis <= acilis) & (acilis < w.hucre_kapanis)
        & (lansman[ho] < acilis)
    )
    if c.size == 0:
        return Transferler.bos()
    hedef = np.rint(w.ileri_plan(acilis, sabitler.REPL_HEDEF_GUN)[c]).astype(np.int64)
    istek = np.maximum(hedef - np.asarray(g.magaza_stok)[c] - np.asarray(g.yolda)[c], 0)
    adet = np.minimum(istek, np.asarray(g.depo)[hs[c]])
    v = adet > 0
    n = int(v.sum())
    return Transferler(
        kaynak=np.full(n, -1, dtype=np.int64), hedef=np.full(n, m, dtype=np.int64),
        sku=hs[c][v].astype(np.int64), adet=adet[v].astype(np.int64),
    )


def lumoda_kapanis(g, m: int) -> Transferler:
    """Kapanış günü (motor satıştan ve stok devrinden önce çağırır):
    mağazanın bütün raf stoğu depoya (Lumoda: "bütün stok depoya"; satılacağı
    mağazaya ya da outlet'e dağıtmaz). Yoldaki mal varışta depoya döner
    (motor)."""
    w = g.dunya
    stok = np.asarray(g.magaza_stok)
    c = np.flatnonzero((w.hucre_magaza == m) & (stok > 0))
    n = c.size
    return Transferler(
        kaynak=np.full(n, m, dtype=np.int64), hedef=np.full(n, -1, dtype=np.int64),
        sku=w.hucre_sku[c].astype(np.int64), adet=stok[c].astype(np.int64),
    )


class LumodaElleTransfer:
    """Bölge müdürlerinin pazartesi elle transferleri (kural dışı, gerekçesiz).

    Her pazartesi `sayac_uretici(d, "elle", operasyon_tohumu).random((7, 2 + 2·maks))` tek
    çekiliş (politikadan bağımsız sabit boy); satır r = bölge r (fiziksel
    mağazaların bölge adları sıralı), sütun 0 → k = ⌊4u⌋ ∈ {0..3}, sütun
    1 + 2j / 2 + 2j → j. transferin kaynağı / hedefi.
    Kaynak  bölgede (mağaza, option) çiftleri, (mağaza, option) sırasıyla:
            mağaza bugün açık ve kapanış kararsız; option'ın hücreleri
            penceresinde ve en az 28 gündür rafta (pencere başı ve mağazanın
            açılışı ≥ 28 gün önce: "son 28 günde satış 0" anlamlı olsun);
            son 28 günde satış 0; option stoğu (bütün bedenler) ≥ 3.
            j. seçim kalan adaylardan ⌊u · n⌋ (aynı çift iki kez seçilmez).
    Hedef   aynı bölgede başka, bugün açık, kapanış kararsız ve o option'ın
            penceresi açık hücresi olan mağazalardan ⌊u · n⌋ (ihtiyaca
            bakılmaz); yoksa o seçim boş geçer.
    Miktar  kaynağın o option'daki bütün stoğu (bütün bedenler).
    """

    BOLGE_SAYISI = 7

    def __init__(
        self,
        maks: int = sabitler.ELLE_TRANSFER_MAKS,
        stok_esigi: int = sabitler.ELLE_STOK_ESIGI,
        pencere_gun: int = sabitler.ELLE_SATIS_PENCERESI_GUN,
    ):
        self.maks = maks
        self.stok_esigi = stok_esigi
        self.pencere_gun = pencere_gun

    def __call__(self, g) -> Transferler:
        w = g.dunya
        d = g.gun
        u = sayac_uretici(d, "elle", g.operasyon_tohumu).random(
            (self.BOLGE_SAYISI, 2 + 2 * self.maks)
        )
        mag = w.magazalar
        O = len(w.optionlar)
        fiziksel = (mag["tip"] != "Online").to_numpy()
        bolge = mag["bolge"].to_numpy()
        bolgeler = sorted(set(bolge[fiziksel]))
        if len(bolgeler) > self.BOLGE_SAYISI:
            raise ValueError(f"{len(bolgeler)} bölge; çekiliş {self.BOLGE_SAYISI} satırlık")
        uygun_m = fiziksel & np.asarray(g.acik_magaza) & ~np.asarray(g.kapanacak)

        hm, ho = w.hucre_magaza, w.hucre_option
        stok_c = np.asarray(g.magaza_stok)
        c = np.flatnonzero(
            (w.hucre_acilis <= d) & (d < w.hucre_kapanis) & ~w.hucre_online & uygun_m[hm]
        )
        cift, ters = np.unique(hm[c].astype(np.int64) * O + ho[c], return_inverse=True)
        stok = np.bincount(ters, stok_c[c], minlength=cift.size)
        satis = np.bincount(ters, np.asarray(g.satis_28)[c], minlength=cift.size)
        cm, co = cift // O, cift % O
        rafta = np.full(cift.size, np.iinfo(np.int64).max, dtype=np.int64)
        np.minimum.at(rafta, ters, np.asarray(w.hucre_acilis)[c].astype(np.int64))
        rafta = np.maximum(rafta, _acilis_gunleri(w)[cm])
        aday = (stok >= self.stok_esigi) & (satis == 0) & (rafta <= d - self.pencere_gun)

        k_, h_, s_, a_ = [], [], [], []
        for r, b in enumerate(bolgeler):
            n_tr = min(int(u[r, 0] * (self.maks + 1)), self.maks)
            kalan = np.flatnonzero(aday & (bolge[cm] == b))
            for j in range(n_tr):
                if kalan.size == 0:
                    break
                i = kalan[min(int(u[r, 1 + 2 * j] * kalan.size), kalan.size - 1)]
                kalan = kalan[kalan != i]
                m, o = int(cm[i]), int(co[i])
                hedefler = np.unique(cm[(co == o) & (bolge[cm] == b) & (cm != m)])
                if hedefler.size == 0:
                    continue
                m2 = int(hedefler[min(int(u[r, 2 + 2 * j] * hedefler.size), hedefler.size - 1)])
                kc = c[(hm[c] == m) & (ho[c] == o) & (stok_c[c] > 0)]
                k_.append(np.full(kc.size, m)); h_.append(np.full(kc.size, m2))
                s_.append(w.hucre_sku[kc]); a_.append(stok_c[kc])
        if not k_:
            return Transferler.bos()
        b_ = lambda x: np.concatenate(x).astype(np.int64)  # noqa: E731
        return Transferler(b_(k_), b_(h_), b_(s_), b_(a_))


lumoda_elle_transfer = LumodaElleTransfer()


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
