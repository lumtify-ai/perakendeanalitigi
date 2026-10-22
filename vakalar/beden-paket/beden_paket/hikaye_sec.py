"""Hikâye seçimi: 1. yazının sahnesi veriden (spec §6 merdiveni).

Kural: bu bir karar modülüdür; yalnız yayımlanan tablolardan ve karar anındaki eğriden (`egri.Egri`)
okur, hakeme ve ölçüm modüllerine dokunmaz (AST kilidi, `tests/test_sizinti.py`). Gizli beden kayması
bu modüle yalnız `sec(..., kayma=)` argümanıyla, bir `Series` olarak gelir; bu modül onu kendisi
okumaz. Argümanı veren ölçüm tarafıdır (`hikaye_kos`; `python -m beden_paket.hikaye_kos`). Sahne
yalnız karar gününden önceki satırlardan kurulur; yayımlanan `sevkiyat`'ın ilk dağıtım satırları
burada okunabilir (eğri okumaz: spec §0/13; bu hikâyedir, eğri değil).

**Sahne.** Aynı paketi alan iki mağaza ve bir Collection option'ı:

- **Büyük** mağaza: profili `buyuk` (eğrisi okunabilen: `Egri.kaynak` "magaza"), Anadolu'da
  (İstanbul dışı; Veli'nin). Option'da 4. ve 5. beden varıştan sonraki ilk `ERKEN_HAFTA` (2) tam
  haftada rafsız gün görür (biter) ve öteki bedenlerin hepsinden önce biter (öteki bedenler daha geç
  biter ya da hiç bitmez), 1. beden `PENCERE_HAFTA` (8) hafta boyunca hiç rafsız kalmaz ve pencerenin
  sonunda rafta mal vardır.
- **Küçük** mağaza: profili `kucuk`, İstanbul'da (Ali'nin); tersi: 1. ve 2. beden ilk haftalarda
  biter, 5. beden kalır.
- İkisine giden ilk dağıtım paketi aynıdır ve Lumoda'nın standart paketidir (`LUMODA_PAKET`;
  yayımlanan `sevkiyat`'ın `ilk_dagitim` satırları ve `paket` tablosundan: paket sayısı = beden
  adedi ÷ paketin o bedendeki içeriği, bütün bedenlerde aynı).

**Haftalar.** Mağazaya varıştan (`varis_tarihi`) sonraki ilk pazartesi `bas`; hafta k = [bas + 7(k−1),
bas + 7k), fotoğrafı bas + 7k pazartesisidir (`stoklu_gun` önceki yedi günü anlatır). Rafsız gün
= 7 − `stoklu_gun`. Biten hafta: rafsız günü olan ilk hafta. Kalan beden: pencerenin bütün
fotoğrafları var, hiçbirinde rafsız gün yok ve son fotoğrafta adet > 0. Satış: haftalık satışın
(`tarih` haftanın pazartesisi) [bas, bas + 7 × `PENCERE_HAFTA`) aralığı. Pencere karar gününden
önce bitmelidir.

**Sahne sırası.** Önce kadroya uyan roller (büyük Anadolu, küçük İstanbul), sonra biten hedef beden
sayısı (çok iyi), sonra biten haftaların toplamı (erken iyi), sonra kalan bedenlerin son
fotoğraftaki adedi (çok iyi), sonra option ve mağaza kimlikleri.

**Gevşetme** (`ADIMLAR`, `MERDIVEN`; her kademe öncekine ekler, gevşeyen kayda `gevseyen`'e
yazılır): (1) erken pencere 3 hafta, (2) 4 hafta; (3) iki mağaza aynı option yerine aynı sezonun aynı
beden setli (benzer) option'ları; (4) option kalibrasyon sezonundan (`KAL_KARAR_GUNU`'nden sonraki
ilk lansmanın sezonu; SS24) değil, karar öncesi her Collection sezonundan; (5) roller serbest:
bölge-profil dağılımı veride tersse büyüğe kayık mağaza İstanbul'da, küçüğe kayık Anadolu'da olabilir
(kurgu veriye uyar, kimin mağazası olduğu değişir, ders aynı kalır; sırada kadroya uyan önce); (6)
hedef bedenlerin öteki bedenlerden önce bitmesi şartı kalkar; (7) biten hedef bedenlerin ikisi birden
değil biri (büyükte 4. ya da 5., küçükte 1. ya da 2.). Ders en son gevşer. Hiçbir kademede sahne yoksa hata.

**Hakem.** `kayma` verilirse (mağaza → etkin gizli kayma, −1 / 0 / +1) sahne sırasında ilk
**doğrulanan** sahne seçilir: büyük mağazanın kayması +1, küçüğünki −1. Atlanan sahne sayısı
`elenen`'dedir. Hiçbir sahne doğrulanmazsa hata.

**Alternatif.** Birinci sahnenin iki mağazasını dışlayarak aynı merdivenle bulunan ikinci sahne
(`alternatif`); yoksa `None`.
"""

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from beden_paket import kaynak, sabitler

ERKEN_HAFTA = 2
PENCERE_HAFTA = sabitler.EGRI_PENCERE_HAFTA
HEDEF = {"buyuk": (4, 5), "kucuk": (1, 2)}         # ilk haftalarda biten bedenler
KALAN = {"buyuk": 1, "kucuk": 5}                    # pencere boyunca rafta kalan beden
SEZONLUK = "Collection"
_GUN = pd.Timedelta(days=1)
_HAFTA = pd.Timedelta(weeks=1)


@dataclass(frozen=True)
class Kademe:
    """Merdivenin bir kademesi: aranan şartlar ve o kademeye dek gevşeyenlerin kaydı."""
    erken: int          # hedef bedenler varıştan sonraki ilk `erken` tam haftada biter
    ayni_option: bool   # iki mağaza aynı option'da (False: aynı sezon ve beden setinde)
    sezon: str          # "kal": kalibrasyon sezonu | "hepsi": karar öncesi her Collection sezonu
    roller: str         # "kadro": büyük Anadolu, küçük İstanbul | "serbest": biri İstanbul biri Anadolu
    iki_beden: bool     # iki hedef beden birden biter (False: biri)
    once: bool          # erken biten hedef bedenler öteki bedenlerin hepsinden önce biter
    gevseyen: tuple[str, ...]


ADIMLAR = (
    ("erken", 3, "erken pencere: hedef bedenler ilk 3 haftada (2 yerine) biter"),
    ("erken", 4, "erken pencere: hedef bedenler ilk 4 haftada biter"),
    ("ayni_option", False, "option: iki mağaza aynı option yerine aynı sezonun aynı beden setli option'ları"),
    ("sezon", "hepsi", "sezon: kalibrasyon sezonu yerine karar öncesi her Collection sezonu"),
    ("roller", "serbest", "roller serbest: büyüğe kayık mağaza İstanbul'da, küçüğe kayık Anadolu'da olabilir "
                          "(kurgu veriye uyar; kadroya uyan önce)"),
    ("once", False, "sıra: hedef bedenlerin öteki bedenlerden önce bitmesi şartı kalktı (aynı hafta ya da "
                    "sonra biten başka beden olabilir)"),
    ("iki_beden", False, "ders: hedef bedenlerin ikisi birden değil biri biter (büyükte 4. ya da 5., küçükte "
                         "1. ya da 2.)"),
)


def _merdiven() -> tuple[Kademe, ...]:
    k = Kademe(ERKEN_HAFTA, True, "kal", "kadro", True, True, ())
    sonuc = [k]
    for alan, deger, metin in ADIMLAR:
        k = replace(k, **{alan: deger}, gevseyen=k.gevseyen + (metin,))
        sonuc.append(k)
    return tuple(sonuc)


MERDIVEN = _merdiven()


@dataclass(frozen=True)
class Hikaye:
    """Seçilen sahne.

    buyuk, kucuk   mağaza kaydı: magaza, istanbul, profil, egri [5], option, sezon, beden_seti,
                   varis, bas (ilk tam haftanın pazartesisi), desen, paket, satis, bedenler
                   [{beden_sira, beden, gelen, satis, biten_hafta, bos_gun, kalan}]
    kademe         merdivenin kaçıncı kademesi (0 sıkı)
    gevseyen       gevşeyen şartların kaydı (boş: sıkı merdiven)
    roller         "kadro" (büyük Anadolu, küçük İstanbul) | "ters"
    zincir         [5] zincir eğrisi (karşılaştırma için)
    elenen         hakem doğrulamasına takılıp atlanan sahne sayısı
    dogrulama      None ya da {"kayma": {m: k}, "buyuk": bool, "kucuk": bool}
    alternatif     ikinci sahne (ilk sahnenin mağazaları dışında) ya da None"""
    buyuk: dict
    kucuk: dict
    kademe: int
    gevseyen: list
    roller: str
    zincir: list
    elenen: int = 0
    dogrulama: dict | None = None
    alternatif: "Hikaye | None" = field(default=None)

    def sozluk(self) -> dict:
        """JSON'a yazılabilir hâl (`cikti/hikaye.json`)."""
        return {"buyuk": self.buyuk, "kucuk": self.kucuk, "kademe": int(self.kademe),
                "gevseyen": list(self.gevseyen), "roller": self.roller, "zincir": list(self.zincir),
                "elenen": int(self.elenen), "dogrulama": self.dogrulama,
                "pencere_hafta": PENCERE_HAFTA,
                "alternatif": None if self.alternatif is None else self.alternatif.sozluk()}


# ---------------------------------------------------------------------------
# Hücreler: mağaza × option
# ---------------------------------------------------------------------------


def _pazartesi(t: pd.Series) -> pd.Series:
    """Tarihten sonraki (ya da aynı gün) ilk pazartesi."""
    t = pd.to_datetime(t).dt.normalize()
    return t + pd.to_timedelta((7 - t.dt.weekday) % 7, unit="D")


def _kal_sezonu(urun: pd.DataFrame) -> set[str]:
    """Kalibrasyon sezonu: `KAL_KARAR_GUNU`'nden sonraki ilk Collection lansmanının sezonu."""
    c = urun[urun["line"].astype(str) == SEZONLUK]
    lans = pd.to_datetime(c["lansman_tarihi"])
    sonra = lans[lans > sabitler.KAL_KARAR_GUNU]
    if sonra.empty:
        return set()
    return set(c.loc[lans == sonra.min(), "sezon_kodu"].astype(str))


def _desen(paket: pd.DataFrame) -> dict[str, tuple[int, ...]]:
    """paket_id → beş bedenli içerik (beden sırası 1..5)."""
    p = paket.assign(paket_id=paket["paket_id"].astype(str))
    t = p.pivot_table(index="paket_id", columns="beden_sira", values="adet", aggfunc="sum", fill_value=0)
    t = t.reindex(columns=range(1, sabitler.BEDEN_SAYISI + 1), fill_value=0)
    return {pid: tuple(int(x) for x in r) for pid, r in zip(t.index, t.to_numpy())}


def hucreler(tablolar: dict, adaylar: list[str], karar_gunu) -> pd.DataFrame:
    """Aday mağazaların karar öncesi Collection ilk dağıtımları (mağaza × option) ve pencere ölçüleri
    (modül notu). Bir satır: magaza_id, option_id, sezon, beden_seti, varis, bas, desen, paket ve beden
    sırası b = 1..5 için gelen_b, satis_b, biten_b (hafta ya da NaN), bos_b (rafsız gün), kalan_b
    (son fotoğrafın adedi), tam_b (pencerenin bütün fotoğrafları var mı), beden_b (beden adı)."""
    karar = pd.Timestamp(karar_gunu).normalize()
    u = kaynak.bes_bedenli(tablolar["urun"])
    u = u[(u["line"].astype(str) == SEZONLUK) & (pd.to_datetime(u["lansman_tarihi"]) < karar)]
    u = pd.DataFrame({"urun_id": u["urun_id"].astype(str).to_numpy(), "option_id": u["option_id"].astype(str).to_numpy(),
                      "sezon": u["sezon_kodu"].astype(str).to_numpy(), "beden_seti": u["beden_seti"].astype(str).to_numpy(),
                      "beden": u["beden"].astype(str).to_numpy(), "b": u["beden_sira"].to_numpy(dtype=np.int64)})
    ad = set(adaylar)
    sv = tablolar["sevkiyat"]
    sv = sv[(sv["tip"].astype(str) == "ilk_dagitim").to_numpy() & (pd.to_datetime(sv["tarih"]) < karar).to_numpy()
            & sv["hedef"].astype(str).isin(ad).to_numpy()]
    sv = pd.DataFrame({"magaza_id": sv["hedef"].astype(str).to_numpy(), "urun_id": sv["urun_id"].astype(str).to_numpy(),
                       "varis": pd.to_datetime(sv["varis_tarihi"]).to_numpy(), "adet": sv["adet"].to_numpy(dtype=np.int64),
                       "paket_id": sv["paket_id"].astype(str).to_numpy()}).merge(u, on="urun_id", how="inner")
    if sv.empty:
        return pd.DataFrame()
    desen = _desen(tablolar["paket"])
    g = sv.groupby(["magaza_id", "option_id"], sort=True)
    h = g.agg(sezon=("sezon", "first"), beden_seti=("beden_seti", "first"), varis=("varis", "min"),
              paket_idler=("paket_id", lambda s: tuple(sorted(set(s))))).reset_index()
    h["bas"] = _pazartesi(h["varis"])
    h = h[h["bas"] + PENCERE_HAFTA * _HAFTA <= karar].reset_index(drop=True)
    if h.empty:
        return h
    gelen = sv.pivot_table(index=["magaza_id", "option_id"], columns="b", values="adet", aggfunc="sum",
                           fill_value=0).reindex(columns=range(1, 6), fill_value=0)
    h = h.join(gelen.rename(columns=lambda b: f"gelen_{b}"), on=["magaza_id", "option_id"])
    desenler, paketler = [], []
    for pids, *ad_b in zip(h["paket_idler"], *(h[f"gelen_{b}"] for b in range(1, 6))):
        d = desen.get(pids[0]) if len(pids) == 1 else None
        n = None
        if d is not None and all(x >= 0 for x in d) and sum(d) > 0:
            oranlar = {a // x for a, x in zip(ad_b, d) if x > 0}
            if len(oranlar) == 1 and all(a == next(iter(oranlar)) * x for a, x in zip(ad_b, d)):
                n = next(iter(oranlar))
        desenler.append("-".join(map(str, d)) if d is not None and n is not None else None)
        paketler.append(n)
    h["desen"], h["paket"] = desenler, paketler
    h = h.drop(columns=["paket_idler"])

    adlar = u.drop_duplicates(["option_id", "b"]).pivot(index="option_id", columns="b", values="beden")
    sku = u.set_index("urun_id")
    secili = set(h["option_id"])
    st = tablolar["stok"]
    st = st[st["magaza_id"].astype(str).isin(ad).to_numpy() & st["urun_id"].astype(str).isin(
        set(u.loc[u["option_id"].isin(secili), "urun_id"])).to_numpy() & (pd.to_datetime(st["tarih"]) < karar).to_numpy()]
    st = pd.DataFrame({"magaza_id": st["magaza_id"].astype(str).to_numpy(), "urun_id": st["urun_id"].astype(str).to_numpy(),
                       "tarih": pd.to_datetime(st["tarih"]).to_numpy(), "adet": st["adet"].to_numpy(dtype=np.int64),
                       "stoklu": st["stoklu_gun"].to_numpy(dtype=np.int64)})
    st["option_id"] = st["urun_id"].map(sku["option_id"])
    st["b"] = st["urun_id"].map(sku["b"]).astype(np.int64)
    st = st.merge(h[["magaza_id", "option_id", "bas"]], on=["magaza_id", "option_id"], how="inner")
    k = (st["tarih"] - st["bas"]) / _HAFTA
    st = st[(k >= 1) & (k <= PENCERE_HAFTA) & (k == np.floor(k))].assign(k=k.astype(np.int64))
    st["bos"] = (7 - st["stoklu"]).clip(lower=0)

    sa = tablolar["satis"]
    sa = sa[sa["magaza_id"].astype(str).isin(ad).to_numpy() & (pd.to_datetime(sa["tarih"]) < karar).to_numpy()
            & (sa["adet"].to_numpy() > 0)]
    sa = pd.DataFrame({"magaza_id": sa["magaza_id"].astype(str).to_numpy(), "urun_id": sa["urun_id"].astype(str).to_numpy(),
                       "tarih": pd.to_datetime(sa["tarih"]).to_numpy(), "adet": sa["adet"].to_numpy(dtype=np.int64)})
    sa = sa[sa["urun_id"].isin(sku.index)]
    sa["option_id"] = sa["urun_id"].map(sku["option_id"])
    sa["b"] = sa["urun_id"].map(sku["b"]).astype(np.int64)
    sa = sa.merge(h[["magaza_id", "option_id", "bas"]], on=["magaza_id", "option_id"], how="inner")
    sa = sa[(sa["tarih"] >= sa["bas"]) & (sa["tarih"] < sa["bas"] + PENCERE_HAFTA * _HAFTA)]
    satis = sa.pivot_table(index=["magaza_id", "option_id"], columns="b", values="adet", aggfunc="sum",
                           fill_value=0).reindex(columns=range(1, 6), fill_value=0)
    h = h.join(satis.rename(columns=lambda b: f"satis_{b}"), on=["magaza_id", "option_id"])

    anahtar = ["magaza_id", "option_id", "b"]
    biten = st[st["bos"] > 0].groupby(anahtar)["k"].min().rename("biten")
    bos = st.groupby(anahtar)["bos"].sum().rename("bos")
    foto = st.groupby(anahtar)["k"].nunique().rename("foto")
    son = st[st["k"] == PENCERE_HAFTA].groupby(anahtar)["adet"].sum().rename("kalan")
    olcu = pd.concat([biten, bos, foto, son], axis=1).reset_index()
    for ad_, deger in (("biten", np.nan), ("bos", 0), ("foto", 0), ("kalan", 0)):
        p = olcu.pivot_table(index=["magaza_id", "option_id"], columns="b", values=ad_, aggfunc="first")
        p = p.reindex(columns=range(1, 6))
        h = h.join(p.rename(columns=lambda b, a=ad_: f"{a}_{b}"), on=["magaza_id", "option_id"])
        for b in range(1, 6):
            if ad_ != "biten":
                h[f"{ad_}_{b}"] = h[f"{ad_}_{b}"].fillna(deger).astype(np.int64)
    for b in range(1, 6):
        h[f"satis_{b}"] = h[f"satis_{b}"].fillna(0).astype(np.int64)
        h[f"tam_{b}"] = h[f"foto_{b}"] == PENCERE_HAFTA
        h[f"beden_{b}"] = h["option_id"].map(adlar[b]) if b in adlar.columns else None
    return h.sort_values(["magaza_id", "option_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Adaylar ve sıralama
# ---------------------------------------------------------------------------


def _uygun(h: pd.DataFrame, rol: str, kademe: Kademe, kal_sezon: set) -> pd.DataFrame:
    """`rol` ("buyuk" | "kucuk") için kademenin şartını sağlayan hücreler; ek sütunlar: n_biten (erken
    biten hedef beden sayısı), erken (onların haftaları toplamı), kalan (kalan bedenin son adedi)."""
    hedef, kal = HEDEF[rol], KALAN[rol]
    obur = [b for b in range(1, sabitler.BEDEN_SAYISI + 1) if b not in hedef]
    H = np.column_stack([h[f"biten_{b}"].to_numpy(dtype="float64") for b in hedef])
    erken = H <= kademe.erken
    n = erken.sum(axis=1)
    sart = (n == len(hedef)) if kademe.iki_beden else (n >= 1)
    son_hedef = np.where(erken, H, -np.inf).max(axis=1)
    ilk_obur = np.fmin.reduce(np.column_stack([h[f"biten_{b}"].to_numpy(dtype="float64") for b in obur]),
                              axis=1, initial=np.inf)
    once = (son_hedef < ilk_obur) if kademe.once else np.ones(len(h), dtype=bool)
    kalir = h[f"tam_{kal}"].to_numpy() & (h[f"bos_{kal}"].to_numpy() == 0) & (h[f"kalan_{kal}"].to_numpy() > 0)
    lumoda = (h["desen"] == "-".join(map(str, sabitler.LUMODA_PAKET))).to_numpy()
    sezon = np.ones(len(h), dtype=bool) if kademe.sezon == "hepsi" else h["sezon"].isin(kal_sezon).to_numpy()
    sec = sart & once & kalir & lumoda & sezon
    d = h.loc[sec].copy()
    d["n_biten"] = n[sec]
    d["erken"] = np.where(erken[sec], H[sec], 0).sum(axis=1)
    d["kalan"] = d[f"kalan_{kal}"]
    return d


def _sahneler(h: pd.DataFrame, dunya: dict, kademe: Kademe, haric: frozenset) -> list[tuple]:
    """Kademenin aday sahneleri, sahne sırasıyla: (buyuk satırı, kucuk satırı, ters mi)."""
    ist = dunya["istanbul"]
    sahne = []
    for ters in ((False,) if kademe.roller == "kadro" else (False, True)):
        rb = h[h["magaza_id"].map(lambda m: dunya["profil"].get(m) == "buyuk" and ist[m] == ters)]
        rk = h[h["magaza_id"].map(lambda m: dunya["profil"].get(m) == "kucuk" and ist[m] != ters)]
        rb = _uygun(rb[~rb["magaza_id"].isin(haric)], "buyuk", kademe, dunya["kal_sezon"])
        rk = _uygun(rk[~rk["magaza_id"].isin(haric)], "kucuk", kademe, dunya["kal_sezon"])
        if rb.empty or rk.empty:
            continue
        on = ["option_id"] if kademe.ayni_option else ["sezon", "beden_seti"]
        c = rb.merge(rk, on=on, suffixes=("_b", "_k"))
        if c.empty:
            continue
        for _, r in c.iterrows():
            ob = r["option_id"] if kademe.ayni_option else r["option_id_b"]
            ok = r["option_id"] if kademe.ayni_option else r["option_id_k"]
            anahtar = (int(ters), -(r["n_biten_b"] + r["n_biten_k"]), r["erken_b"] + r["erken_k"],
                       -(r["kalan_b"] + r["kalan_k"]), ob, ok, r["magaza_id_b"], r["magaza_id_k"])
            sahne.append((anahtar, (r["magaza_id_b"], ob), (r["magaza_id_k"], ok), ters))
    sahne.sort(key=lambda x: x[0])
    return [(b, k, t) for _, b, k, t in sahne]


def _kayit(h: pd.DataFrame, dunya: dict, hucre: tuple[str, str]) -> dict:
    m, o = hucre
    r = h[(h["magaza_id"] == m) & (h["option_id"] == o)].iloc[0]
    bedenler = []
    for b in range(1, 6):
        biten = r[f"biten_{b}"]
        bedenler.append({"beden_sira": b, "beden": None if r[f"beden_{b}"] is None else str(r[f"beden_{b}"]),
                         "gelen": int(r[f"gelen_{b}"]), "satis": int(r[f"satis_{b}"]),
                         "biten_hafta": None if pd.isna(biten) else int(biten), "bos_gun": int(r[f"bos_{b}"]),
                         "kalan": int(r[f"kalan_{b}"])})
    return {"magaza": m, "istanbul": bool(dunya["istanbul"][m]), "profil": dunya["profil"][m],
            "egri": [float(x) for x in dunya["egri"].loc[m]], "option": o, "sezon": str(r["sezon"]),
            "beden_seti": str(r["beden_seti"]), "varis": pd.Timestamp(r["varis"]).date().isoformat(),
            "bas": pd.Timestamp(r["bas"]).date().isoformat(), "desen": r["desen"], "paket": int(r["paket"]),
            "satis": int(sum(x["satis"] for x in bedenler)), "bedenler": bedenler}


def _bul(h: pd.DataFrame, dunya: dict, kayma, haric: frozenset) -> Hikaye:
    elenen = 0
    for i, kademe in enumerate(MERDIVEN):
        for b, k, ters in _sahneler(h, dunya, kademe, haric):
            dog = None
            if kayma is not None:
                kb, kk = int(kayma[b[0]]), int(kayma[k[0]])
                dog = {"kayma": {b[0]: kb, k[0]: kk}, "buyuk": kb == 1, "kucuk": kk == -1}
                if not (dog["buyuk"] and dog["kucuk"]):
                    elenen += 1
                    continue
            return Hikaye(buyuk=_kayit(h, dunya, b), kucuk=_kayit(h, dunya, k), kademe=i,
                          gevseyen=list(kademe.gevseyen), roller="ters" if ters else "kadro",
                          zincir=[float(x) for x in dunya["zincir"]], elenen=elenen, dogrulama=dog)
    if elenen:
        raise ValueError(f"hikâye sahnesi bulunamadı: {elenen} aday sahneyi hakem doğrulamadı "
                         "(büyük mağazanın kayması +1, küçüğünki −1 değil)")
    raise ValueError("uygun hikâye sahnesi bulunamadı: merdivenin hiçbir kademesinde sahne yok")


# ---------------------------------------------------------------------------
# Giriş
# ---------------------------------------------------------------------------


def sec(tablolar: dict, egri, karar_gunu, *, kayma: pd.Series | None = None) -> Hikaye:
    """Sahneyi seçer (modül notu).

    tablolar   yayımlanan: magaza, magaza_olay, urun, satis (en az tarih, magaza_id, urun_id, adet;
               günlük ya da haftalık), stok (pazartesi fotoğrafları), sevkiyat, paket
    egri       karar anındaki `egri.Egri` (profil, kaynak, mağaza eğrisi, zincir)
    kayma      mağaza → etkin gizli kayma (isteğe bağlı; yalnız doğrulama, ölçüm tarafı verir)"""
    k = kaynak.kapsam(tablolar, karar_gunu).set_index("magaza_id")
    adaylar = [m for m in egri.magaza.index if egri.kaynak.get(m) == "magaza" and m in k.index
               and egri.profil.get(m) in HEDEF]
    dunya = {"istanbul": k["istanbul"].astype(bool).to_dict(), "profil": egri.profil.to_dict(),
             "egri": egri.magaza, "zincir": egri.zincir, "kal_sezon": _kal_sezonu(tablolar["urun"])}
    if kayma is not None:
        kayma = kayma.copy()
        kayma.index = kayma.index.astype(str)
        eksik = [m for m in adaylar if m not in kayma.index]
        if eksik:
            raise ValueError(f"kayması olmayan aday mağaza: {eksik[:5]}")
    h = hucreler(tablolar, adaylar, karar_gunu)
    if h.empty:
        raise ValueError("uygun hikâye sahnesi bulunamadı: aday mağazaların karar öncesi ilk dağıtımı yok")
    birinci = _bul(h, dunya, kayma, frozenset())
    try:
        alt = _bul(h, dunya, kayma, frozenset({birinci.buyuk["magaza"], birinci.kucuk["magaza"]}))
    except ValueError:
        alt = None
    return replace(birinci, alternatif=alt)
