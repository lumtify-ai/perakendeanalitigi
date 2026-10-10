"""Sansürlü talep: "daha olsaydı ne kadar satardı?" — karar anında.

Lansmandan h hafta sonraki pazartesi sabahı (karar anı `t`), elde yalnız
`t`'den önceki günlerin satışı ve stok durumu vardır. Sezon talebini (lansman →
indirim başı; FRR'nin "sezon"u) dört katmanda kestiririz:

    a  çıplak       x: bugüne kadarki satış. Raporun gösterdiği sayı;
                    "sezonda bu kadar sattık" demenin karşılığı.
    b  stoklu gün   D / h · W: karar anı Basit'iyle düzeltilmiş bugüne kadarki
                    talep (D), haftalık hıza çevrilip planlı satış haftası (W)
                    kadar uzatılır. Sansürü görür, yaşam eğrisini görmez.
    c  eğri (FRR)   x / k_ham: çıplak satış, geçmiş sezonların ÇIPLAK satış
                    eğrisiyle ölçeklenir (Fisher–Rajaram–Raman 2001'deki
                    perakendecinin kuralı). Eğriyi görür, sansürü görmez —
                    iki kez: hem bu sezonun satışında hem eğriyi veren geçmiş
                    satışta.
    d  b + c        D / k_duz: düzeltilmiş talep, düzeltilmiş eğriyle.

Ek iki satır katmanları ayrıştırmak içindir: `a_hiz` (çıplak hız × W) ve
`c_duz_egri` (çıplak satış ÷ düzeltilmiş eğri).

KARAR ANI KESTİRİMİ (`karar_ani_talep`, saf fonksiyon; Ruling R5). Girdi ortak
paketin günlük tablosudur (`stok.gunluk_magaza` + `gunluk_online`: hücre-gün
başına satış öncesi stok, brüt satış, durum stoklu / tukenen / bos) ve Basit'in
özellik sütunları. Kestirici ortak `talep.Basit(karar_ani=t)`: havuzu yalnız
`t`'den önceki stoklu günlerdir, komşuluğu `t − 1`'de kesilir. Stoksuz (`bos`) ve
gün içinde tükenen (`tukenen`) günlerin kaybı ortak `kayip.kayip_yaz`
(bos: λ̂; tukenen: E[D | D ≥ s] − s). Hücre-gün talebi = brüt satış + kayıp.

KARAR HAVUZU (`havuz`: option_id, bas, isteğe bağlı son). Kestirim yalnız
havuzdaki option'ların `[bas, min(son, t))` günlerini görür: karar anı
katmanlarında karar sezonunun Collection option'ları, lansmandan `t`'ye; eğrinin
öğrenmesinde geçmiş sezonların option'ları, lansmandan çıkışa (`egri`). Basit'in
beden payı, göreli hızı, zincir ve son yedekleri bu havuzdan kurulur; aynı
fonksiyon motor içinde de (`politika.Oneri`, `anlik.gunluk_gorunumden`) aynı
havuzla çağrılır, sonuç havuzun dışındaki hiçbir satıra bağlı değildir.

KARAR ANINDA ÇEŞİT. `t`'ye dek hiç stoklanmamış hücre (bütün günleri `bos`,
satışı yok) havuzdan düşer: ortak günlük tablonun "hiç stoklanmamış hücre çeşit
kararıdır" kuralının (`stok.gunluk_magaza` e) karar anındaki karşılığı. Ortak kural
bütün pencereye bakar (gelecek bilgisi); bu kural onu kapsar, sonuç ortak kuralın
dışarıda bıraktığı hücrelere bağlı kalmaz.

KAPSAM. Mağaza ve online (`ONL`, depodan satar) hücreleri: RPT malı ikisine de
gider. Kestirim (a, b, c, d) ile gerçek talep (`gercek_talep`) aynı kapsamdadır.

SIZINTI. Kestirim yalnız `GOZLENEN` + Basit'in özellik sütunlarını okur;
gerçek talep, kayıp satış ya da hakem sütunları girdide dursa da okunmaz (test).
`t`'de ve sonrasındaki satırlar sonucu değiştirmez (test). Gerçek talep yalnız
argüman olarak `hata_tablosu`na ve `gercek_talep`e girer.
"""

import numpy as np
import pandas as pd
from perakende_analitik import hazirlik
from perakende_analitik import kayip as ortak_kayip
from perakende_analitik.carpanlar import Carpanlar, kodlar
from perakende_analitik.talep import Basit

from .egri import Egri

KATMANLAR = ("a", "b", "c", "d")
EK_KATMANLAR = ("a_hiz", "c_duz_egri")
KATMAN_ADI = {
    "a": "a  çıplak satış (rapor)",
    "b": "b  stoklu gün hızı × hafta",
    "c": "c  eğri ölçeği, çıplak (FRR)",
    "d": "d  stoklu gün + eğri",
    "a_hiz": "   çıplak hız × hafta",
    "c_duz_egri": "   çıplak satış ÷ düzeltilmiş eğri",
    "plan": "   buyer planı",
}
KARAR_HAFTALARI = (2, 3, 4, 5, 6)
HIT_ESIGI = 1.5   # gerçek / plan ≥ 1,5: "tutan" ürün
GOZLENEN = ("tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi", "brut_satis", "durum")
OZELLIKLER = tuple(hazirlik.KESTIRICI_OZELLIKLERI["basit"])
TALEP_SUTUNLARI = (*GOZLENEN, "tahmini_talep", "kayip", "talep")


# ---------------------------------------------------------------- havuz


def _sinirlar(seri: pd.Series, havuz: pd.DataFrame, t: pd.Timestamp):
    """Satır başına havuz penceresi [bas, son) (datetime64[ns]); havuzda olmayan
    option'ın satırı NaT. Kategori başına bir kez eşlenir (satır başına metin yok)."""
    kat = seri if isinstance(seri.dtype, pd.CategoricalDtype) else seri.astype("category")
    h = havuz.drop_duplicates("option_id")
    ids = pd.Index(h["option_id"].astype(str))
    bas = pd.to_datetime(h["bas"]).to_numpy("datetime64[ns]")
    son = (pd.to_datetime(h["son"]).to_numpy("datetime64[ns]") if "son" in h.columns
           else np.full(len(h), np.datetime64("NaT", "ns")))
    son = np.where(np.isnat(son) | (son > t.to_datetime64()), t.to_datetime64(), son)
    i = ids.get_indexer(kat.cat.categories.astype(str))
    nat = np.datetime64("NaT", "ns")
    bas_k = np.append(np.where(i >= 0, bas[np.maximum(i, 0)], nat), nat)
    son_k = np.append(np.where(i >= 0, son[np.maximum(i, 0)], nat), nat)
    kod = kat.cat.codes.to_numpy()
    kod = np.where(kod >= 0, kod, len(i))
    return bas_k[kod], son_k[kod]


def havuz_satirlari(gunluk: pd.DataFrame, t, havuz: pd.DataFrame) -> pd.DataFrame:
    """Karar havuzunun gözlenen satırları: option havuzda, `bas <= tarih < min(son, t)`;
    yalnız `GOZLENEN` + Basit özellik sütunları; `t`'ye dek hiç stoklanmamış hücreler
    düşer (bkz. modül notu)."""
    t = pd.Timestamp(t).normalize()
    eksik = [s for s in (*GOZLENEN, *OZELLIKLER) if s not in gunluk.columns]
    if eksik:
        raise ValueError(f"karar_ani_talep: günlük tabloda sütun yok: {eksik}")
    bas, son = _sinirlar(gunluk["option_id"], havuz, t)
    tarih = gunluk["tarih"].to_numpy("datetime64[ns]")
    sec = ~np.isnat(bas) & (tarih >= bas) & (tarih < son)
    g = gunluk.loc[sec, list(GOZLENEN) + list(OZELLIKLER)].reset_index(drop=True)
    # karar anında çeşit: t'ye dek en az bir stoklu / tükenen günü ya da satışı olan hücre
    m, _ = kodlar(g["magaza_id"])
    u, urunler = kodlar(g["urun_id"])
    anahtar = m.astype(np.int64) * (len(urunler) + 1) + u
    ters = pd.factorize(anahtar)[0]
    acik = ((g["durum"] != "bos").to_numpy() | (g["brut_satis"].to_numpy() > 0)).astype(float)
    stoklanmis = np.bincount(ters, acik, ters.max() + 1 if len(ters) else 0) > 0
    return g[stoklanmis[ters]].reset_index(drop=True)


# ------------------------------------------------------------ kestirim


def karar_ani_talep(gunluk: pd.DataFrame, t, carpanlar: Carpanlar, havuz: pd.DataFrame,
                    komsu_gun: int = 14) -> pd.DataFrame:
    """Karar anı `t`'de havuzun hücre-gün talep kestirimi (saf; Ruling R5).

    gunluk     ortak günlük tablo (`GOZLENEN`) + Basit özellikleri (`OZELLIKLER`);
               başka sütunlar okunmaz
    t          karar anı (pazartesi sabahı); `t` ve sonrası hiçbir şeyi etkilemez
    carpanlar  karar anında bilinen çarpanlar (`hazirlik.carpanlar_kapanmis(…, t)`)
    havuz      option_id, bas[, son]: kestirimin göreceği option'lar ve günleri

    Dönüş (`TALEP_SUTUNLARI`): havuzun her hücre-günü; `tahmini_talep` Basit'in λ̂'sı
    (yalnız bos / tukenen; stoklu NaN), `kayip` (stoklu 0), `talep = brut_satis +
    kayip`. Toplamlar için `ozet`."""
    t = pd.Timestamp(t).normalize()
    g = havuz_satirlari(gunluk, t, havuz)
    if not (g["durum"] == "stoklu").any():
        raise ValueError(f"karar_ani_talep: {t.date()} öncesi havuzda stoklu gün yok")
    k = Basit(komsu_gun, carpanlar=carpanlar, karar_ani=t)
    k.egit(g)
    hedef = np.flatnonzero((g["durum"] != "stoklu").to_numpy())
    lam = np.full(len(g), np.nan)
    kay = np.zeros(len(g))
    if len(hedef):
        h = g.iloc[hedef]
        kd = ortak_kayip.kayip_yaz(h[list(GOZLENEN)], k.tahmin(h))
        lam[hedef] = kd["tahmini_talep"].to_numpy()
        kay[hedef] = kd["kayip"].to_numpy()
    sonuc = g[list(GOZLENEN)].copy()
    sonuc["tahmini_talep"] = lam
    sonuc["kayip"] = kay
    sonuc["talep"] = sonuc["brut_satis"].to_numpy(np.float64) + kay
    return sonuc


def ozet(talep: pd.DataFrame, duzey=("option_id",)) -> pd.DataFrame:
    """`karar_ani_talep` çıktısının toplamı: x (brüt satış), D (düzeltilmiş talep),
    stoklu_pay (stoklu ya da tükenen hücre-gün ÷ hücre-gün), hucre_gun.
    `duzey=("option_id", "urun_id")` option × beden, `+ ("magaza_id",)` hücre."""
    duzey = list(duzey)
    d = talep[duzey].copy()
    for s in duzey:
        d[s] = d[s].astype(str)
    d["x"] = talep["brut_satis"].to_numpy(np.float64)
    d["D"] = talep["talep"].to_numpy(np.float64)
    d["st"] = (talep["durum"] != "bos").to_numpy(np.float64)
    d["n"] = 1.0
    o = d.groupby(duzey, sort=True)[["x", "D", "st", "n"]].sum()
    o["stoklu_pay"] = o["st"] / o["n"]
    o = o.rename(columns={"n": "hucre_gun"})
    return o[["x", "D", "stoklu_pay", "hucre_gun"]].reset_index()


# ------------------------------------------------------------ katmanlar


def katman_hesapla(oz: pd.DataFrame, opt: pd.DataFrame, h: int, egri_ham: Egri,
                   egri_duz: Egri) -> pd.DataFrame:
    """Option başına x, D'den (`ozet`) katmanlar; `opt`: option_id, dalga,
    ust_kategori, satis_hafta[, plan_sezon]. Özette olmayan option x = D = 0."""
    kol = ["option_id", "dalga", "ust_kategori", "satis_hafta"]
    kol += [c for c in ("plan_sezon",) if c in opt.columns]
    k = opt[kol].drop_duplicates("option_id").copy()
    k["option_id"] = k["option_id"].astype(str)
    k = k.merge(oz, on="option_id", how="left")
    for c in ("x", "D", "stoklu_pay", "hucre_gun"):
        k[c] = k[c].fillna(0.0)

    def _k(e: Egri):
        return np.array([e.k(tuple(r[g] for g in e.grup), h) for r in k.to_dict("records")])

    k["k_ham"], k["k_duz"] = _k(egri_ham), _k(egri_duz)
    W = k["satis_hafta"]
    k["a"] = k["x"].astype(float)
    k["b"] = k["D"] / h * W
    k["c"] = k["x"] / k["k_ham"]
    k["d"] = k["D"] / k["k_duz"]
    k["a_hiz"] = k["x"] / h * W
    k["c_duz_egri"] = k["x"] / k["k_duz"]
    if "plan_sezon" in k.columns:
        k["plan"] = k["plan_sezon"]
    k["h"] = h
    return k


def karar_havuzu(opt: pd.DataFrame, sezon: str, t, line: str = "Collection") -> pd.DataFrame:
    """Karar havuzu (R5): karar sezonunun `line` option'ları, lansmanı `t`'den önce;
    pencere lansmandan `t`'ye (`son` yok)."""
    t = pd.Timestamp(t)
    o = opt[(opt["sezon_kodu"] == sezon) & (opt["line"] == line) & (opt["lansman_tarihi"] < t)]
    return pd.DataFrame({"option_id": o["option_id"].astype(str).to_numpy(),
                         "bas": pd.to_datetime(o["lansman_tarihi"]).to_numpy()})


def katmanlar(karar_ani, h: int, gunluk: pd.DataFrame, opt: pd.DataFrame, carpanlar: Carpanlar,
              egri_ham: Egri, egri_duz: Egri, havuz: pd.DataFrame | None = None,
              line: str = "Collection") -> pd.DataFrame:
    """Karar anı `karar_ani` (pazartesi) ve hafta `h`: lansmanı `karar_ani − 7h`
    olan `line` option'larının katmanları (`katman_hesapla` sütunları + karar_ani).

    `havuz` verilmezse `karar_havuzu` (karar sezonunun option'ları, lansmandan
    karar anına). Çarpanlar karar anında bilinenlerdir; çağıran verir."""
    t = pd.Timestamp(karar_ani).normalize()
    lansman = t - pd.Timedelta(days=7 * h)
    hedef = opt[(opt["lansman_tarihi"] == lansman) & (opt["line"] == line)]
    if hedef.empty:
        raise ValueError(f"katmanlar: {lansman.date()} lansmanlı {line} option'ı yok (t={t.date()}, h={h})")
    sezonlar = hedef["sezon_kodu"].unique()
    if len(sezonlar) != 1:
        raise ValueError(f"katmanlar: birden çok sezon {list(sezonlar)}")
    if havuz is None:
        havuz = karar_havuzu(opt, sezonlar[0], t, line)
    oz = ozet(karar_ani_talep(gunluk, t, carpanlar, havuz))
    k = katman_hesapla(oz, hedef, h, egri_ham, egri_duz)
    k["karar_ani"] = t
    return k


def karar_ozetleri(gunluk: pd.DataFrame, opt: pd.DataFrame, sezonlar, haftalar, carpanlar_bul,
                   line: str = "Collection") -> pd.DataFrame:
    """Sezonların her dalgası ve her `h` için karar anı `t = lansman + 7h`'de o dalganın
    `line` option'larının x ve D'si (`ozet`): option_id, sezon_kodu, dalga, h, karar_ani,
    x, D, stoklu_pay. Karar havuzu `karar_havuzu(opt, sezon, t)`, çarpanlar
    `carpanlar_bul(t)` (karar anında bilinenler). Sıra: sezon, lansman, h, option_id.
    Aday satırlarının (`aday.karar_kaydi`) ve kalibrasyonun (`miktar.kalibrasyon`)
    ortak girdisi."""
    parca = []
    for sezon in sezonlar:
        o = opt[(opt["sezon_kodu"] == sezon) & (opt["line"] == line)]
        bellek: dict = {}     # karar anı → özet (aynı t'de birden çok dalga)
        for lansman in sorted(o["lansman_tarihi"].unique()):
            for h in haftalar:
                t = pd.Timestamp(lansman) + pd.Timedelta(days=7 * int(h))
                if t not in bellek:
                    bellek[t] = ozet(karar_ani_talep(gunluk, t, carpanlar_bul(t),
                                                     karar_havuzu(opt, sezon, t, line)))
                parca.append(_dalga_satirlari(o, lansman, int(h), t, bellek[t]))
    if not parca:
        return pd.DataFrame(columns=list(KARAR_OZETI_SUTUNLARI))
    return pd.concat(parca, ignore_index=True)


KARAR_OZETI_SUTUNLARI = ("option_id", "sezon_kodu", "dalga", "h", "karar_ani", "x", "D", "stoklu_pay")


def _dalga_satirlari(o: pd.DataFrame, lansman, h: int, t: pd.Timestamp, oz: pd.DataFrame) -> pd.DataFrame:
    """`lansman` dalgasının option'ları × (h, t): `oz`dan (`ozet`) x, D, stoklu_pay."""
    hedef = o[o["lansman_tarihi"] == lansman][["option_id", "sezon_kodu", "dalga"]].copy()
    hedef["option_id"] = hedef["option_id"].astype(str)
    hedef = hedef.drop_duplicates("option_id").sort_values("option_id")
    k = hedef.merge(oz[["option_id", "x", "D", "stoklu_pay"]], on="option_id", how="left")
    k[["x", "D", "stoklu_pay"]] = k[["x", "D", "stoklu_pay"]].fillna(0.0)
    k.insert(3, "h", int(h))
    k.insert(4, "karar_ani", t)
    return k


def karar_ani_satirlari(gunluk: pd.DataFrame, opt: pd.DataFrame, sezon: str, t, haftalar, carpanlar,
                        line: str = "Collection") -> pd.DataFrame:
    """Tek karar anı `t` (pazartesi): sezonun lansmanı `t − 7h` (h ∈ `haftalar`) olan
    `line` option'larının `karar_ozetleri` satırları (aynı sütunlar, aynı tanım).
    Motor içi kol her pazartesi bunu kendi dünyasının günlük tablosuyla
    (`anlik.gunluk_gorunumden`) çağırır; tablo yolu `karar_ozetleri` ile aynı satırı
    üretir (Ruling R5). O pazartesi karar haftasında dalga yoksa boş tablo."""
    t = pd.Timestamp(t).normalize()
    o = opt[(opt["sezon_kodu"] == sezon) & (opt["line"] == line)]
    lansmanlar = set(pd.to_datetime(o["lansman_tarihi"]).unique())
    dalgalar = [(t - pd.Timedelta(days=7 * int(h)), int(h)) for h in haftalar]
    dalgalar = sorted((lan, h) for lan, h in dalgalar if lan in lansmanlar)
    if not dalgalar:
        return pd.DataFrame(columns=list(KARAR_OZETI_SUTUNLARI))
    oz = ozet(karar_ani_talep(gunluk, t, carpanlar, karar_havuzu(opt, sezon, t, line)))
    return pd.concat([_dalga_satirlari(o, lan, h, t, oz) for lan, h in dalgalar], ignore_index=True)


def sezon_katmanlari(sezon: str, h: int, gunluk: pd.DataFrame, opt: pd.DataFrame, carpanlar_bul,
                     egri_ham: Egri, egri_duz: Egri, line: str = "Collection") -> pd.DataFrame:
    """Sezonun her dalgası için `katmanlar(lansman + 7h, h, …)`; `carpanlar_bul(t)`
    karar anı çarpanlarını verir (ör. `hazirla.carpanlar`)."""
    o = opt[(opt["sezon_kodu"] == sezon) & (opt["line"] == line)]
    parca = []
    for lansman in sorted(o["lansman_tarihi"].unique()):
        t = pd.Timestamp(lansman) + pd.Timedelta(days=7 * h)
        parca.append(katmanlar(t, h, gunluk, opt, carpanlar_bul(t), egri_ham, egri_duz, line=line))
    return pd.concat(parca, ignore_index=True)


# ------------------------------------------------------------ doğruluk


def gercek_talep(gercek_gunluk: pd.DataFrame, opt: pd.DataFrame) -> pd.DataFrame:
    """Doğruluk ölçüsü (yalnız argümandan): option başına gerçek talep.

    gercek_gunluk  hücre-gün gerçek talep: tarih, option_id, talep (çağıran
                   kurar; ör. `olcutler.gercek_gunluk`, hakemden)
    Dönüş: option_id, gercek_io (lansman → indirim başı; kestirimlerin hedefi),
    gercek_cikis (lansman → çıkış)."""
    o = opt[["option_id", "lansman_tarihi", "indirim_baslangic", "cikis_tarihi"]].copy()
    o["option_id"] = o["option_id"].astype(str)
    g = gercek_gunluk[["tarih", "option_id", "talep"]].copy()
    g["option_id"] = g["option_id"].astype(str)
    g = g.merge(o, on="option_id")
    g = g[g["tarih"] >= g["lansman_tarihi"]]
    io = g[g["tarih"] < g["indirim_baslangic"]].groupby("option_id")["talep"].sum()
    cx = g[g["tarih"] < g["cikis_tarihi"]].groupby("option_id")["talep"].sum()
    r = pd.DataFrame({"option_id": o["option_id"]})
    r["gercek_io"] = r["option_id"].map(io).fillna(0.0).astype(float)
    r["gercek_cikis"] = r["option_id"].map(cx).fillna(0.0).astype(float)
    return r


def hata_olcutleri(tahmin: pd.Series, gercek: pd.Series) -> dict:
    """MAPE (option ortalaması), ağırlıklı APE (Σ|e| / Σgerçek), medyan APE,
    yanlılık (Σe / Σgerçek). Yüzde değil oran döner."""
    e = tahmin - gercek
    ape = (e.abs() / gercek).replace([np.inf, -np.inf], np.nan)
    return {
        "n": int(len(gercek)),
        "mape": float(ape.mean()),
        "wape": float(e.abs().sum() / gercek.sum()),
        "medyan_ape": float(ape.median()),
        "yanlilik": float(e.sum() / gercek.sum()),
    }


def hata_tablosu(katman: pd.DataFrame, gercek: pd.DataFrame, hit_esigi: float = HIT_ESIGI,
                 katmanlar_=KATMANLAR + EK_KATMANLAR + ("plan",)) -> pd.DataFrame:
    """Uzun tablo: h × katman × kesit (tümü / tutan / tutmayan) × ölçüt.

    `gercek`: option_id, gercek_io (argüman; ör. `gercek_talep`). Tutan / tutmayan
    kesiti `plan_sezon` varsa (gerçek / plan ≥ `hit_esigi`)."""
    g = gercek[["option_id", "gercek_io"]].copy()
    g["option_id"] = g["option_id"].astype(str)
    k = katman.assign(option_id=katman["option_id"].astype(str)).merge(g, on="option_id")
    k = k[k["gercek_io"] > 0]
    kesitler = [("tümü", None)]
    if "plan_sezon" in k.columns:
        k["tutan"] = k["gercek_io"] / k["plan_sezon"] >= hit_esigi
        kesitler += [("tutan", True), ("tutmayan", False)]
    satirlar = []
    for h, kh in k.groupby("h"):
        for kesit, deger in kesitler:
            kk = kh if deger is None else kh[kh["tutan"] == deger]
            if kk.empty:
                continue
            for kat in katmanlar_:
                if kat not in kk.columns:
                    continue
                satirlar.append({"h": h, "katman": kat, "kesit": kesit,
                                 **hata_olcutleri(kk[kat], kk["gercek_io"])})
    return pd.DataFrame(satirlar)
