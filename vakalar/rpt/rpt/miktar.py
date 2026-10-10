"""Ne kadar RPT: üç miktar kuralı.

    banu        ilk alımın %50'si, en az MOQ (Lumoda'nın v4 `LumodaRPT` kuralı)
    frr         Fisher–Rajaram–Raman (2001) perakendecisinin kuralı:
                Q2 = ((1 − ω) · x_k / k_k − Q1)⁺ — çıplak satış, çıplak eğri.
                ω iade oranı. Q2 MOQ'nun yarısından küçükse sipariş yok,
                değilse en az MOQ (FRR'de MOQ yok; bizim eklememiz).
    newsvendor  gelişten sonra kalan talebin dağılımı üstünde beklenen kârı
                en büyükleyen miktar (aşağıda).

NEWSVENDOR. Karar pazartesisi h, tedarik süresi L, geliş a = h + L.
Sezon talebi kestirimi d katmanıdır (`sansur`): Ŝ = D_h / k_h (D karar anı
Basit'iyle düzeltilmiş bugüne kadarki talep), tam fiyat penceresi için indirim
eğrisiyle, indirim dönemi için çıkış eğrisiyle. Belirsizlik çarpımsaldır:
S = Ŝ · exp(ε), ε ~ N(μ_h, σ_h); μ ve σ yalnız oyun sezonundan önce kapanmış
sezonlardan öğrenilir (`kalibrasyon`, aşağıda). Dağılım 200 sabit kantil
noktasıyla temsil edilir (deterministik).

    B    = geliş öncesi talep = S_cx · (k_cx(a) − k_cx(h))
    C0   = gelişte elde kalacak stok = (envanter pozisyonu − B)⁺
           envanter pozisyonu = depo + mağaza stoğu + yoldaki + açık siparişler
    Xtf  = gelişten indirime tam fiyat talebi = S_io · (1 − k_io(a))
    Xind = indirim dönemi talebi (gelişten sonra) = S_cx · (1 − k_cx(max(a, W)))
    Q'nun tam fiyat satışı  tf  = min(Q, (Xtf − C0)⁺)
    indirimli satışı        ind = min(Q − tf, (Xind − (C0 − Xtf)⁺)⁺)
    kâr = p · tf + p_ind · ind − c · Q      (çıkışta kalan 0 değerli)

Az alma maliyeti Cu = p − c (tam fiyat marjı), fazla alma maliyeti
Co = c − p_ind (indirimde satılırsa) ya da c (hiç satılmazsa); formül bu iki
maliyeti senaryolar üstünden kendisi tartar.

İNDİRİM FİYATI (v4). v4'te indirim içseldir (Lumoda'nın markdown kuralı STR'ye
bakar), planı yoktur. Beklenti geçmiş sezonların yayımlanan `fiyat` tablosundan
öğrenilir (`indirim_beklentisi`: dalga × indirim başına göre hafta ortalama
indirim oranı, yalnız oyun sezonu başlamadan biten haftalar); option'ın p_ind'i
indirim haftalarının bu oranlarının çıkış eğrisi paylarıyla ağırlıklı
ortalamasıdır (`indirim_fiyatlari`). Hafta indirim başına göre sayılır: SS'te
indirim lansmandan 20, AW'de 19 hafta sonra (perşembe) başlar; lansmana göre
saymak iki sezon türünü indirim başı çevresinde karıştırırdı. Oyun sezonunun
fiyatları okunmaz.

KALİBRASYON (v4; sızıntı kesildi). Geçmiş sezon P'nin her option'ı ve her karar
haftası h için hata r = log(hedef / d):
    d      karar anı kestirimi: lansman + 7h sabahı, yalnız o güne dek bilinenle
           (`sansur.karar_ozetleri`: karar anı Basit'i, karar havuzu P'nin
           option'ları), P'nin kendi oyun eğrisiyle (P'den önceki sezonlardan;
           veride P'den önce sezon yoksa oyun sezonunun eğrisi — örneklem içi,
           σ'yı biraz iyimser yapar)
    hedef  P'nin sezon talebi (lansman → indirim), oyun sezonunun ilk lansman
           sabahında bilinenle: ortak Basit'in karar anı moduyla doldurulmuş
           talep (`egri.gecmis_talep`, Ruling R4) — sahada kurulabilen sayı.
Gerçek talep (hakem) okunmaz: v3'teki gerçek kaybı okuyan kalibrasyonun
sızıntısı kesildi. μ, Basit'in sansürlü günlerdeki yanlılığını da taşır
(hedef de Basit'tir); gerçeğe karşı yanlılık yalnız raporda ölçülür.

MOQ KAPISI. En iyi Q MOQ'dan küçükse MOQ'nun beklenen kârı pozitifse MOQ,
değilse sipariş yok. Ayrıca MOQ'nun yarısını tam fiyattan satması
beklenmeyen sipariş verilmez: aday modelinin etiketi ve olcutler'in "yanlış
alarm" tanımı aynı eşiktir (tutarlılık).

SABİTLER. Karar modülleri üreteci (`perakende_veri`) içe aktarmaz (sızıntı
kilidi); Lumoda'nın RPT sabitleri burada kopyadır, v4 `sabitler` ile aynılığı
testle kilitli (`test_sabitler_v4_ile_ayni`).

Bilinen sadeleştirmeler: mağazalar arası dağılım (sıkışan stok) ve iade
yok sayılır; teslim sapması yok sayılır (planlanan geliş).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import egri, kaynak, sansur

KANTIL = 200
_Z = norm.ppf((np.arange(KANTIL) + 0.5) / KANTIL)

# Lumoda'nın v4 sabitleri (perakende_veri.v4.sabitler; testle kilitli)
ADIM = 10                 # YUVARLAMA_ADET: sipariş adedi 10'un katı
IADE_ORANI = 0.06         # IADE_ORANI_MAGAZA: FRR'nin ω'sı (mağaza iadesi)
RPT_MIKTAR_ORANI = 0.50   # Banu: ilk alımın yarısı
RPT_STR_ESIGI = 0.55      # Banu: zincir STR'si eşiği
RPT_ILK_HAFTA = 3         # Banu: lansmandan 3.–6. pazartesi
RPT_SON_HAFTA = 6

KALIBRASYON_HAFTALARI = sansur.KARAR_HAFTALARI
INDIRIM_HATTI = "normal"  # fiziksel mağaza hattı (online hattı aynı oranı izler)


def moq_yuvarla(miktar: float, moq: int) -> int:
    """En az MOQ, üstü 10'un katına yukarı (v4 `plan.moq_yuvarla`)."""
    return int(max(moq, np.ceil(miktar / ADIM - 1e-9) * ADIM))


def banu(ilk_alim: float, moq: int, oran: float = RPT_MIKTAR_ORANI) -> int:
    return moq_yuvarla(oran * ilk_alim, moq)


def frr(x: float, k: float, ilk_alim: float, moq: int, omega: float = IADE_ORANI) -> int:
    if k <= 0:
        return 0
    q2 = max((1 - omega) * x / k - ilk_alim, 0.0)
    return moq_yuvarla(q2, moq) if q2 >= moq / 2 else 0


# ---------------------------------------------------------------- indirim


def indirim_beklentisi(con, sezon_kodu: str, hat: str = INDIRIM_HATTI,
                       line: str = "Collection") -> dict:
    """{(dalga, hafta): ortalama indirim oranı}: oyun sezonundan önce kapanmış
    sezonların (`kaynak.gecmis_sezonlar`) `line` option'larının yayımlanan haftalık
    `fiyat`ı (`hat`); `hafta` option'ın indirim başı haftasına göredir:
    (hafta_baslangic − lansman) // 7 − w0, w0 = (indirim_baslangic − lansman) // 7
    (indirim başını içeren hafta 0, öncesi negatif; `indirim_fiyatlari` aynı w0'la
    okur), lansman ≤ hafta < çıkış. İndirim başı yayımlanan `sezon` tablosundan
    (sezon × dalga). Yalnız oyun sezonunun ilk lansman sabahına dek BİTMİŞ haftalar
    (`fiyat` haftanın sonundaki oranı taşır: hafta_baslangic + 7 ≤ t0): oyun
    sezonunun ve sonrasının fiyatı okunmaz."""
    gecmis = kaynak.gecmis_sezonlar(sezon_kodu)
    if not gecmis:
        raise ValueError(f"indirim_beklentisi: {sezon_kodu}'den önce kapanmış sezon yok")
    t0 = con.execute("select min(lansman_tarihi) from sezon where sezon_kodu::varchar = ?",
                     [sezon_kodu]).fetchone()[0]
    if t0 is None:
        raise ValueError(f"indirim_beklentisi: {sezon_kodu} sezon tablosunda yok")
    yer = ", ".join("?" * len(gecmis))
    df = con.execute(f"""
        with o as (
            select distinct u.option_id::varchar as option_id, u.dalga, u.lansman_tarihi,
                   u.cikis_tarihi, s.indirim_baslangic
            from urun u join sezon s on s.sezon_kodu::varchar = u.sezon_kodu::varchar
                                    and s.dalga = u.dalga
            where u.sezon_kodu::varchar in ({yer}) and u.line::varchar = ?)
        select o.dalga::integer as dalga,
               (date_diff('day', o.lansman_tarihi, f.hafta_baslangic) // 7
                - date_diff('day', o.lansman_tarihi, o.indirim_baslangic) // 7)::integer as hafta,
               avg(f.indirim_orani) as oran
        from fiyat f join o on f.option_id::varchar = o.option_id
        where f.hat::varchar = ? and f.hafta_baslangic >= o.lansman_tarihi
          and f.hafta_baslangic < o.cikis_tarihi
          and f.hafta_baslangic + interval 7 day <= ?
        group by 1, 2 order by 1, 2""", [*gecmis, line, hat, pd.Timestamp(t0)]).df()
    return {(int(r.dalga), int(r.hafta)): float(r.oran) for r in df.itertuples(index=False)}


def _oran(beklenti: dict, dalga: int, hafta: int) -> float:
    if (dalga, hafta) in beklenti:
        return beklenti[(dalga, hafta)]
    aday = [w for d, w in beklenti if d == dalga]
    if aday:
        return beklenti[(dalga, min(aday, key=lambda w: (abs(w - hafta), -w)))]
    return float(np.mean(list(beklenti.values()))) if beklenti else 0.0


def indirim_fiyatlari(opt: pd.DataFrame, beklenti: dict, egri_cx: egri.Egri | None = None) -> pd.Series:
    """option_id → indirim dönemi beklenen fiyatı p_ind = liste × (1 − ō).

    ō: option'ın indirim haftalarının ([indirim başı haftası, çıkış)) beklenen
    oranları (`indirim_beklentisi`, indirim başı haftasına göre w − w0; olmayan hafta
    dalganın en yakın haftası), çıkış
    eğrisinin o haftalardaki paylarıyla ağırlıklı (talep indirimin ilk haftalarında
    yoğundur); eğri yoksa ya da payları sıfırsa eşit ağırlık."""
    sonuc = {}
    for r in opt.drop_duplicates("option_id").itertuples(index=False):
        lan = pd.Timestamp(r.lansman_tarihi)
        w0 = (pd.Timestamp(r.indirim_baslangic) - lan).days // 7
        w1 = -(-(pd.Timestamp(r.cikis_tarihi) - lan).days // 7)
        haftalar = np.arange(w0, max(w1, w0 + 1))
        oran = np.array([_oran(beklenti, int(r.dalga), int(w - w0)) for w in haftalar])
        agirlik = np.ones(len(haftalar))
        if egri_cx is not None:
            pay = egri_cx._satir((int(r.dalga),))
            a = np.where(haftalar < len(pay), pay[np.minimum(haftalar, len(pay) - 1)], 0.0)
            if a.sum() > 0:
                agirlik = a
        sonuc[str(r.option_id)] = float(r.liste_fiyati) * (1 - float((agirlik * oran).sum() / agirlik.sum()))
    return pd.Series(sonuc, name="p_ind")


# ---------------------------------------------------------------- kalibrasyon


@dataclass(frozen=True)
class Belirsizlik:
    mu: dict      # h → ortalama log(hedef / kestirim)
    sigma: dict   # h → std
    n: dict
    sezonlar: tuple

    def al(self, h: float):
        hs = sorted(self.mu)
        k = min(hs, key=lambda x: abs(x - h))
        return self.mu[k], self.sigma[k]


def _sezon_talebi(talep: pd.DataFrame, opt: pd.DataFrame) -> pd.Series:
    """option_id → lansman ≤ tarih < indirim başı talep toplamı (hücre-gün `talep`)."""
    o = opt[["option_id", "lansman_tarihi", "indirim_baslangic"]].drop_duplicates("option_id").copy()
    o["option_id"] = o["option_id"].astype(str)
    d = pd.DataFrame({"option_id": talep["option_id"].astype(str).to_numpy(),
                      "tarih": talep["tarih"].to_numpy("datetime64[ns]"),
                      "talep": talep["talep"].to_numpy(np.float64)}).merge(o, on="option_id")
    d = d[(d["tarih"] >= d["lansman_tarihi"]) & (d["tarih"] < d["indirim_baslangic"])]
    return d.groupby("option_id")["talep"].sum()


def egri_kaynagi(opt: pd.DataFrame, sezon: str, oyun_sezonu: str, line: str = "Collection") -> str:
    """Geçmiş sezon `sezon`un karar anı kestiriminde kullanılacak eğrinin oyun sezonu:
    `sezon`un kendisi (eğrisi `sezon`dan önceki sezonlardan) — veride ondan önce kapanmış
    `line` option'ı yoksa (SS23) oyun sezonu."""
    once = kaynak.gecmis_sezonlar(sezon)
    var = ((opt["sezon_kodu"].isin(once)) & (opt["line"] == line)).any() if once else False
    return sezon if var else oyun_sezonu


def kalibrasyon(gunluk: pd.DataFrame, opt: pd.DataFrame, oyun_sezonu: str, carpanlar_bul,
                egriler: dict | None = None, ozetler: pd.DataFrame | None = None,
                haftalar=KALIBRASYON_HAFTALARI, line: str = "Collection") -> Belirsizlik:
    """Oyun sezonundan önce kapanmış sezonlarda d katmanının log hatası (modül notu).

    gunluk         ortak günlük tablo + Basit özellikleri; geçmiş sezonların
                   satırları (oyunun ilk lansman sabahından sonrası okunmaz)
    carpanlar_bul  t → karar anında bilinen çarpanlar
    egriler        {oyun sezonu: {(yöntem, hedef): Egri}} önbelleği; eksik eğri
                   `egri.oyun_egrileri` ile kurulup buraya eklenir
    ozetler        `sansur.karar_ozetleri` çıktısı (geçmiş sezonlar × `haftalar`);
                   verilmezse kurulur (aday satırlarıyla paylaşmak için)
    """
    gecmis = tuple(s for s in kaynak.gecmis_sezonlar(oyun_sezonu)
                   if ((opt["sezon_kodu"] == s) & (opt["line"] == line)).any())
    t0 = egri.oyun_baslangici(opt, oyun_sezonu)
    egriler = {} if egriler is None else egriler

    def _egri(sezon):
        if sezon not in egriler:
            egriler[sezon] = egri.oyun_egrileri(gunluk, opt, sezon,
                                                carpanlar_bul(egri.oyun_baslangici(opt, sezon)))
        return egriler[sezon][("duzeltilmis", "indirim")]

    hedef = _sezon_talebi(egri.gecmis_talep(gunluk, opt, oyun_sezonu, carpanlar_bul(t0), line), opt)
    if ozetler is None:
        ozetler = sansur.karar_ozetleri(gunluk, opt, gecmis, haftalar, carpanlar_bul, line)
    oz = ozetler[ozetler["sezon_kodu"].isin(gecmis) & ozetler["h"].isin(haftalar)]
    if (oz["karar_ani"] >= t0).any():
        raise ValueError("kalibrasyon: karar anı oyun başlangıcından sonra olan satır var")
    parca = []
    for P, p in oz.groupby("sezon_kodu", sort=False):
        e = _egri(egri_kaynagi(opt, P, oyun_sezonu, line))
        k = np.array([e.k((int(d),), int(h)) for d, h in zip(p["dalga"], p["h"])])
        d = p["D"].to_numpy(float) / np.maximum(k, 1e-6)
        y = p["option_id"].astype(str).map(hedef).fillna(0.0).to_numpy(float)
        gecerli = (d > 0) & (y > 0)
        parca.append(pd.DataFrame({"h": p["h"].to_numpy()[gecerli],
                                   "r": np.log(y[gecerli] / d[gecerli])}))
    r = pd.concat(parca, ignore_index=True)
    ozet = r.groupby("h")["r"].agg(["mean", "std", "size"])
    return Belirsizlik(mu={int(h): float(v) for h, v in ozet["mean"].items()},
                       sigma={int(h): float(v) for h, v in ozet["std"].items()},
                       n={int(h): int(v) for h, v in ozet["size"].items()}, sezonlar=gecmis)


# ---------------------------------------------------------------- newsvendor


def senaryolar(D, h, L, W, egri_io, egri_cx, dalga, mu, sigma):
    """Senaryo başına (B, Xtf, Xind) dizileri."""
    k_io, k_cx = egri_io.k((dalga,), h), egri_cx.k((dalga,), h)
    m = np.exp(mu + sigma * _Z)
    S_io = D / max(k_io, 1e-6) * m
    S_cx = D / max(k_cx, 1e-6) * m
    a = h + L
    B = S_cx * (egri_cx.k((dalga,), a) - k_cx)
    Xtf = S_io * (1 - egri_io.k((dalga,), a))
    Xind = S_cx * (1 - egri_cx.k((dalga,), max(a, W)))
    return B, Xtf, Xind


def kar_egrisi(Q: np.ndarray, B, Xtf, Xind, ip, p, p_ind, c):
    """Q ızgarası için beklenen (tam fiyat satış, indirimli satış, kâr)."""
    C0 = np.maximum(ip - B, 0.0)
    C1 = np.maximum(C0 - Xtf, 0.0)
    ihtiyac_tf = np.maximum(Xtf - C0, 0.0)[None, :]
    ihtiyac_ind = np.maximum(Xind - C1, 0.0)[None, :]
    Qm = Q[:, None].astype(float)
    tf = np.minimum(Qm, ihtiyac_tf)
    ind = np.minimum(Qm - tf, ihtiyac_ind)
    kar = p * tf + p_ind * ind - c * Qm
    return tf.mean(1), ind.mean(1), kar.mean(1)


def newsvendor(D, h, L, W, egri_io, egri_cx, dalga, ip, p, c, p_ind, mu, sigma, moq,
               ust: float | None = None) -> dict:
    """Beklenen kârı en büyük RPT miktarı (MOQ kapılı). Sözlük döndürür."""
    B, Xtf, Xind = senaryolar(D, h, L, W, egri_io, egri_cx, dalga, mu, sigma)
    ust = ust if ust is not None else max(np.percentile(Xtf + Xind, 99), moq) + ADIM
    Q = np.arange(0, int(ust) + ADIM, ADIM)
    tf, ind, kar = kar_egrisi(Q, B, Xtf, Xind, ip, p, p_ind, c)
    i = int(np.argmax(kar))
    q = int(Q[i])
    if 0 < q < moq:
        j = int(np.searchsorted(Q, moq))
        q = moq if j < len(Q) and kar[j] > 0 else 0
    if q > 0:
        j = int(np.searchsorted(Q, q))
        if tf[j] < moq / 2:
            q = 0
    j = int(np.searchsorted(Q, q))
    return {"q": q, "q_serbest": int(Q[i]), "beklenen_tf": float(tf[j]), "beklenen_ind": float(ind[j]),
            "beklenen_kar": float(kar[j]), "ip": float(ip), "Xtf": float(np.mean(Xtf)),
            "Xind": float(np.mean(Xind)), "B": float(np.mean(B))}
