"""Hikâye seçimi: 1. yazının sahnesi veriden (spec §6 merdiveni).

Kural: bu bir karar modülüdür; yalnız yayımlanan veriden gelen tabloları okur, hakeme ve ölçüm
modüllerine dokunmaz (AST kilidi, `tests/test_sizinti.py`). **Gizli segment bu modüle yalnız
`sec(..., gizli=)` argümanıyla, bir `Series` olarak gelir**; bu modül onu kendisi okumaz. Argümanı
veren ölçüm tarafıdır (`hikaye_kos`: `hakem`'den okur, `hikaye_sec`'i çağırır, `cikti/hikaye.json`
yazar; `python -m kumeleme.hikaye_kos`). Kilit karar modülünün `hakem`'e ulaşmasına izin vermediği
için CLI bu modülde değil, ölçüm yanındaki o modüldedir.

**Sahne.** İki çift ve ortak bir ders:

1. çift (aynı grupta, farklı satan). Aynı **planlama hücresi**nde iki mağaza: aynı bölge ve aynı
   ciro sınıfı (Lumoda'nın K3 hücresi, birleşmemiş hâliyle); ikisi de **metropol** mağazası (aynı
   şehir; konum kuralı onları ayıramaz, spec §0/10) ve biri İstanbul (Ali'nin) mağazası; satış
   karışımı uzaklığı **üst çeyrekte** (`>=` bütün kümelenen mağaza çiftlerinin 0,75 nicelikli
   uzaklığı); **ML kümeleri farklı**.

2. çift (farklı grupta, aynı satan). **Farklı bölgede** iki mağaza, biri İstanbul (Ali'nin) biri
   değil (**Anadolu**, Veli'nin: metropol değil; Ankara ve İzmir mağazaları "Anadolu mağazası"
   sayılmaz, çünkü konum kuralı onları İstanbul'la aynı sınıfa koyar); karışım uzaklığı **alt
   çeyrekte** (`<=` 0,25 niceliği); **aynı ML kümesi**.

Karışım uzaklığı: S1 ailesinin (`ozellikler.standartla(X, "S1")`) öklid uzaklığı; ML kümesinin
kurulduğu uzayla aynı. Nicelikler kümelenen bütün mağaza çiftleri üzerindendir.

**Ders kalemleri.** Aynı 2-3 özellik iki çiftte de gösterilir: 1. çiftte ayrışan, 2. çiftte
ayrışmayan (puan = 1. çiftin farkı − 2. çiftin farkı, mağazalar arası standart sapmayla bölünmüş);
payı en az `KALEM_FARK_MIN` (üç puan) farklı, 2. çiftin farkı 1. çiftin yarısından az; her nitelikten
(alt kategori, fiyat segmenti, kalıp) en çok bir kalem; en az `KALEM_EN_AZ` kalem yoksa o sahne
geçersizdir.

**Sahne sırası.** Aday sahnelerin hepsi sıralanır: önce **ortak mağaza** (iki çiftte de geçen
mağaza: aynı İstanbul mağazası hem bir komşusundan ayrılıyor hem bir Anadolu mağazasına benziyor,
"Ali'nin Anadolu mağazası"), sonra karşıtlık (1. çiftin uzaklığı − 2. çiftin uzaklığı, büyük
iyi), sonra mağaza kimlikleri. Ortak mağaza şart değil, sıralama tercihidir.

**Hakem.** `gizli` verilirse sahne sırasında ilk **doğrulanan** sahne seçilir: 1. çiftin gizli
segmentleri farklı, 2. çiftinki aynı. Doğrulamaya takılıp atlanan sahne sayısı `elenen`'dedir;
sıfırdan büyükse seçim hakemsiz seçimden farklıdır ve yazı bunu bilir. Hiçbir sahne doğrulanmazsa
hata verilir.

**Gevşetme.** Sıkı merdivenin sahnesi bulunamazsa kademe kademe gevşer (`MERDIVEN`); her kademe
bir öncekine ekler ve gevşeyen kayıt `gevseyen`'e yazılır: (1) hücre aynı K3 grubu olur (sınıflar
birleşik hücre); (2) 1. çift iki metropol mağazası olmak zorunda değil; (3) uzaklık nicelikleri
0,70/0,30, (4) 0,60/0,40; (5) 2. çiftin Anadolu mağazası metropol de olabilir; (6) İstanbul şartı
kalkar; (7) 0,50/0,50. ML şartları (1. çift farklı, 2. çift aynı) ve 2. çiftin farklı bölge şartı
hiç gevşemez. Hiçbir kademede sahne yoksa hata.

**Alternatif sahne.** Birinci sahnenin mağazalarını hariç tutarak aynı merdivenle bulunan ikinci
sahne (`alternatif`); yoksa `None`.

**Zorlama.** `zorla=((a, b), (c, d))` verilen çiftleri doğrudan sahne yapar (yalnız kümelenen,
bilinen, ayrı mağazalar); sıkı merdivenin tutmayan şartları `gevseyen`'e yazılır
("zorlandı" ilk kayıttır).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from kumeleme import ozellikler

AILE = "S1"
KALEM_FARK_MIN = 0.03        # ders kaleminde 1. çiftin en az payı farkı (üç puan)
KALEM_SAYISI = 3
KALEM_EN_AZ = 2
UST, ALT = 0.75, 0.25        # sıkı nicelikler


@dataclass(frozen=True)
class Kademe:
    """Merdivenin bir kademesi: aranan şartlar ve o kademeye dek gevşeyenlerin kaydı."""
    hucre: str          # "bolge_sinif" (aynı bölge ve K2 sınıfı) | "k3" (aynı K3 grubu)
    metropol: bool      # 1. çift: iki mağaza da metropol
    istanbul: bool      # 1. çift: biri İstanbul; 2. çift: biri İstanbul biri değil
    anadolu: bool       # 2. çift: İstanbul olmayan mağaza Anadolu mağazası (metropol değil)
    ust: float          # 1. çift: uzaklık >= bu nicelik
    alt: float          # 2. çift: uzaklık <= bu nicelik
    gevseyen: tuple[str, ...]


def _merdiven() -> tuple[Kademe, ...]:
    k = Kademe("bolge_sinif", True, True, True, UST, ALT, ())
    adimlar = [
        ("hucre", "k3", "aynı hücre: aynı bölge ve ciro sınıfı yerine aynı K3 grubu (sınıfları birleşik hücre)"),
        ("metropol", False, "1. çift: iki mağazanın metropol olması şartı kalktı"),
        ("kuyruk", (0.70, 0.30), "uzaklık eşiği: 1. çift üst %30, 2. çift alt %30 (çeyrek yerine)"),
        ("kuyruk", (0.60, 0.40), "uzaklık eşiği: 1. çift üst %40, 2. çift alt %40"),
        ("anadolu", False, "2. çift: İstanbul olmayan mağaza metropol de olabilir (Ankara, İzmir)"),
        ("istanbul", False, "İstanbul şartı kalktı (1. çiftte İstanbul mağazası ve 2. çiftte İstanbul-Anadolu çifti aranmaz)"),
        ("kuyruk", (0.50, 0.50), "uzaklık eşiği: 1. çift üst yarı, 2. çift alt yarı"),
    ]
    sonuc = [k]
    for alan, deger, metin in adimlar:
        if alan == "kuyruk":
            k = Kademe(k.hucre, k.metropol, k.istanbul, k.anadolu, deger[0], deger[1], k.gevseyen + (metin,))
        else:
            k = Kademe(**{**k.__dict__, alan: deger, "gevseyen": k.gevseyen + (metin,)})
        sonuc.append(k)
    return tuple(sonuc)


MERDIVEN = _merdiven()


@dataclass(frozen=True)
class Hikaye:
    """Seçilen sahne.

    cift1, cift2   (m_a, m_b) ve (m_c, m_d); ortak mağaza varsa iki çiftte de ilktir
    kalemler       [(özellik, değer_a, değer_b)]: 1. çiftin ders kalemleri
    kalemler2      [(özellik, değer_c, değer_d)]: aynı özellikler, 2. çift
    mesafe         (1. çiftin, 2. çiftin) karışım uzaklığı
    esikler        {"ust": 1. çift eşiği, "alt": 2. çift eşiği} (kullanılan nicelikler)
    kuyruk         (ust nicelik, alt nicelik)
    gevseyen       gevşeyen şartların kaydı (boş: sıkı merdiven); zorlamada "zorlandı" + tutmayanlar
    elenen         gizli doğrulamaya takılıp atlanan sahne sayısı
    dogrulama      None (gizli verilmedi) ya da {"cift1_farkli", "cift2_ayni", "segmentler"}
    alternatif     ikinci sahne (hariç mağazalarla) ya da None"""
    cift1: tuple[str, str]
    cift2: tuple[str, str]
    kalemler: list
    kalemler2: list
    mesafe: tuple[float, float]
    esikler: dict
    kuyruk: tuple[float, float]
    gevseyen: list
    elenen: int = 0
    dogrulama: dict | None = None
    alternatif: "Hikaye | None" = field(default=None)

    def sozluk(self) -> dict:
        """JSON'a yazılabilir hâl (`cikti/hikaye.json`)."""
        return {
            "cift1": list(self.cift1), "cift2": list(self.cift2),
            "kalemler": [{"ozellik": o, "a": float(a), "b": float(b)} for o, a, b in self.kalemler],
            "kalemler2": [{"ozellik": o, "c": float(c), "d": float(d)} for o, c, d in self.kalemler2],
            "mesafe": [float(x) for x in self.mesafe],
            "esikler": {k: float(v) for k, v in self.esikler.items()},
            "kuyruk": [float(x) for x in self.kuyruk],
            "gevseyen": list(self.gevseyen), "elenen": int(self.elenen),
            "dogrulama": self.dogrulama,
            "alternatif": None if self.alternatif is None else self.alternatif.sozluk(),
        }


# ---------------------------------------------------------------------------
# Girdi
# ---------------------------------------------------------------------------


class _Dunya:
    """Kümelenen mağazaların uzaklıkları, öznitelikleri ve etiketleri (kimliğe göre sıralı)."""

    def __init__(self, ozellik, kapsam, kural_etiketleri, ml_etiket):
        for ad in ("k2", "k3"):
            if ad not in kural_etiketleri:
                raise KeyError(f"kural_etiketleri[{ad!r}] gerekli")
        kap = kapsam.copy()
        kap["magaza_id"] = kap["magaza_id"].astype(str)
        kap = kap.set_index("magaza_id")
        ids = sorted(kap.index[kap["kumelenir"].astype(bool)])
        eksik = [m for m in ids if m not in ozellik.index.astype(str)]
        if eksik:
            raise ValueError(f"özellik tablosunda kümelenen mağaza yok: {eksik[:5]}")
        ml = ml_etiket.copy()
        ml.index = ml.index.astype(str)
        eksik = [m for m in ids if m not in ml.index]
        if eksik:
            raise ValueError(f"ML etiketi olmayan kümelenen mağaza: {eksik[:5]}")
        X = ozellik.copy()
        X.index = X.index.astype(str)
        self.X = X.loc[ids]
        self.ids = ids
        self.bolge = kap.loc[ids, "bolge"].astype(str)
        self.istanbul = kap.loc[ids, "istanbul"].astype(bool)
        self.metropol = kap.loc[ids, "metropol"].astype(bool)
        self.ml = ml.loc[ids]
        self.k2 = self._etiket(kural_etiketleri["k2"], ids, "k2")
        self.k3 = self._etiket(kural_etiketleri["k3"], ids, "k3")
        Z = ozellikler.standartla(self.X, AILE)
        A = Z.to_numpy(dtype="float64")
        self.D = np.sqrt(((A[:, None, :] - A[None, :, :]) ** 2).sum(-1))
        self.sira = {m: i for i, m in enumerate(ids)}
        v = self.D[np.triu_indices(len(ids), 1)]
        self.mesafeler = v

    @staticmethod
    def _etiket(s, ids, ad):
        s = s.copy()
        s.index = s.index.astype(str)
        eksik = [m for m in ids if m not in s.index]
        if eksik:
            raise ValueError(f"{ad} etiketi olmayan kümelenen mağaza: {eksik[:5]}")
        return s.loc[ids]

    def d(self, a, b):
        return float(self.D[self.sira[a], self.sira[b]])

    def esikler(self, kademe):
        return (float(np.quantile(self.mesafeler, kademe.ust)),
                float(np.quantile(self.mesafeler, kademe.alt)))


# ---------------------------------------------------------------------------
# Kalemler
# ---------------------------------------------------------------------------


def _nitelik(sutun: str) -> str:
    """`karisim/<grup>/<nitelik>/<değer>` sütununun niteliği."""
    p = str(sutun).split(ozellikler.AYRAC)
    return p[2] if len(p) > 2 else p[0]


def _kalemler(w: _Dunya, cift1, cift2, *, kati: bool):
    """Ders kalemleri: (kalemler, kalemler2) ya da yetersizse None (`kati`: eşiklerle)."""
    a, b = cift1
    c, d = cift2
    X = w.X
    sd = X.std(axis=0, ddof=0)
    f1 = (X.loc[a] - X.loc[b]).abs()
    f2 = (X.loc[c] - X.loc[d]).abs()
    puan = ((f1 - f2) / sd.where(sd > 1e-12)).dropna()
    uygun = puan.index
    if kati:
        uygun = [s for s in puan.index if f1[s] >= KALEM_FARK_MIN and f2[s] < f1[s] / 2]
    sirali = sorted(uygun, key=lambda s: (-round(float(puan[s]), 12), s))
    secilen, nitelik = [], set()
    for s in sirali:
        if _nitelik(s) in nitelik:
            continue
        secilen.append(s)
        nitelik.add(_nitelik(s))
        if len(secilen) == KALEM_SAYISI:
            break
    if kati and len(secilen) < KALEM_EN_AZ:
        return None
    return ([(s, float(X.at[a, s]), float(X.at[b, s])) for s in secilen],
            [(s, float(X.at[c, s]), float(X.at[d, s])) for s in secilen])


# ---------------------------------------------------------------------------
# Adaylar ve sıralama
# ---------------------------------------------------------------------------


def _ciftler(w: _Dunya, haric):
    ids = [m for m in w.ids if m not in haric]
    return [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]]


def _cift1_adaylari(w: _Dunya, kademe, esik_ust, haric):
    uygun = []
    for a, b in _ciftler(w, haric):
        if w.bolge[a] != w.bolge[b] or w.ml[a] == w.ml[b]:
            continue
        hucre = (w.k2[a] == w.k2[b]) if kademe.hucre == "bolge_sinif" else (w.k3[a] == w.k3[b])
        if not hucre:
            continue
        if kademe.metropol and not (w.metropol[a] and w.metropol[b]):
            continue
        if kademe.istanbul and not (w.istanbul[a] or w.istanbul[b]):
            continue
        if w.d(a, b) >= esik_ust - 1e-12:
            uygun.append((a, b))
    return uygun


def _cift2_adaylari(w: _Dunya, kademe, esik_alt, haric):
    uygun = []
    for a, b in _ciftler(w, haric):
        if w.bolge[a] == w.bolge[b] or w.ml[a] != w.ml[b]:
            continue
        if kademe.istanbul and w.istanbul[a] == w.istanbul[b]:
            continue
        if kademe.anadolu and (w.metropol[a] and not w.istanbul[a] or w.metropol[b] and not w.istanbul[b]):
            continue
        if w.d(a, b) <= esik_alt + 1e-12:
            uygun.append((a, b))
    return uygun


def _sirala_cift(w: _Dunya, cift, ortak):
    """Ortak mağaza ilk; yoksa İstanbul mağazası ilk; sonra kimlik."""
    a, b = cift
    if ortak in cift:
        return (ortak, b if a == ortak else a)
    if w.istanbul[b] and not w.istanbul[a]:
        return (b, a)
    return (a, b)


def _sahneler(w: _Dunya, kademe, haric):
    """Kademenin bütün aday sahneleri, sahne sırasıyla: (cift1, cift2, esik_ust, esik_alt)."""
    ust, alt = w.esikler(kademe)
    p1 = _cift1_adaylari(w, kademe, ust, haric)
    p2 = _cift2_adaylari(w, kademe, alt, haric)
    sahne = []
    for c1 in p1:
        for c2 in p2:
            ortak = sorted(set(c1) & set(c2))
            if len(ortak) > 1:                       # aynı çift (ya da aynı iki mağaza): sahne değil
                continue
            o = ortak[0] if ortak else None
            k1, k2 = _sirala_cift(w, c1, o), _sirala_cift(w, c2, o)
            anahtar = (0 if o else 1, -(w.d(*k1) - w.d(*k2)), k1, k2)
            sahne.append((anahtar, k1, k2))
    sahne.sort(key=lambda s: s[0])
    return [(k1, k2) for _, k1, k2 in sahne], ust, alt


def _dogrula(gizli, c1, c2):
    seg = {m: str(gizli[m]) for m in (*c1, *c2)}
    d = {"cift1_farkli": seg[c1[0]] != seg[c1[1]], "cift2_ayni": seg[c2[0]] == seg[c2[1]],
         "segmentler": seg}
    return d


def _gizli_hazirla(gizli, w: _Dunya):
    if gizli is None:
        return None
    g = gizli.copy()
    g.index = g.index.astype(str)
    eksik = [m for m in w.ids if m not in g.index]
    if eksik:
        raise ValueError(f"gizli segmenti olmayan kümelenen mağaza: {eksik[:5]}")
    return g


def _bul(w: _Dunya, gizli, haric) -> Hikaye | None:
    elenen = 0
    for kademe in MERDIVEN:
        sahneler, ust, alt = _sahneler(w, kademe, haric)
        for c1, c2 in sahneler:
            kal = _kalemler(w, c1, c2, kati=True)
            if kal is None:
                continue
            dog = None
            if gizli is not None:
                dog = _dogrula(gizli, c1, c2)
                if not (dog["cift1_farkli"] and dog["cift2_ayni"]):
                    elenen += 1
                    continue
            return Hikaye(cift1=c1, cift2=c2, kalemler=kal[0], kalemler2=kal[1],
                          mesafe=(w.d(*c1), w.d(*c2)), esikler={"ust": ust, "alt": alt},
                          kuyruk=(kademe.ust, kademe.alt), gevseyen=list(kademe.gevseyen),
                          elenen=elenen, dogrulama=dog)
    if elenen:
        raise ValueError(f"hikâye bulunamadı: {elenen} aday sahneyi hakem doğrulamadı "
                         f"(1. çiftin gizli segmentleri farklı, 2. çiftinki aynı değil)")
    raise ValueError("uygun hikâye sahnesi bulunamadı: merdivenin hiçbir kademesinde sahne yok")


# ---------------------------------------------------------------------------
# Zorlama
# ---------------------------------------------------------------------------


def _zorlanan(w: _Dunya, zorla, gizli) -> Hikaye:
    try:
        (a, b), (c, d) = zorla
    except (TypeError, ValueError) as e:
        raise ValueError("zorla: ((m_a, m_b), (m_c, m_d)) beklenir") from e
    c1, c2 = (str(a), str(b)), (str(c), str(d))
    for m in (*c1, *c2):
        if m not in w.sira:
            raise ValueError(f"zorla: kümelenen mağazalar arasında değil: {m!r}")
    if c1[0] == c1[1] or c2[0] == c2[1]:
        raise ValueError("zorla: çift aynı mağazadan kurulamaz")
    k = MERDIVEN[0]
    ust, alt = w.esikler(k)
    (a, b), (c, d) = c1, c2
    kayit = ["zorlandı"]
    if w.bolge[a] != w.bolge[b]:
        kayit.append("1. çift: bölgeler farklı (aynı bölge olmalı)")
    elif w.k2[a] != w.k2[b]:
        kayit.append("1. çift: ciro sınıfları farklı (aynı olmalı)")
    if not (w.metropol[a] and w.metropol[b]):
        kayit.append("1. çift: iki mağaza da metropol değil")
    if not (w.istanbul[a] or w.istanbul[b]):
        kayit.append("1. çift: İstanbul mağazası yok")
    if w.ml[a] == w.ml[b]:
        kayit.append("1. çift: ML kümeleri aynı (farklı olmalı)")
    if w.d(a, b) < ust - 1e-12:
        kayit.append("1. çift: karışım uzaklığı üst çeyrekte değil")
    if w.bolge[c] == w.bolge[d]:
        kayit.append("2. çift: bölge aynı (farklı bölge olmalı)")
    if w.istanbul[c] == w.istanbul[d]:
        kayit.append("2. çift: İstanbul-Anadolu çifti değil")
    elif any(w.metropol[m] and not w.istanbul[m] for m in (c, d)):
        kayit.append("2. çift: İstanbul olmayan mağaza metropol (Anadolu mağazası değil)")
    if w.ml[c] != w.ml[d]:
        kayit.append("2. çift: ML kümeleri farklı (aynı olmalı)")
    if w.d(c, d) > alt + 1e-12:
        kayit.append("2. çift: karışım uzaklığı alt çeyrekte değil")
    ortak = sorted(set(c1) & set(c2))
    o = ortak[0] if len(ortak) == 1 else None
    c1, c2 = _sirala_cift(w, c1, o) if o else c1, _sirala_cift(w, c2, o) if o else c2
    kal = _kalemler(w, c1, c2, kati=False)
    dog = None if gizli is None else _dogrula(gizli, c1, c2)
    return Hikaye(cift1=c1, cift2=c2, kalemler=kal[0], kalemler2=kal[1], mesafe=(w.d(*c1), w.d(*c2)),
                  esikler={"ust": ust, "alt": alt}, kuyruk=(k.ust, k.alt), gevseyen=kayit, elenen=0,
                  dogrulama=dog)


# ---------------------------------------------------------------------------
# Giriş
# ---------------------------------------------------------------------------


def sec(ozellik: pd.DataFrame, kapsam: pd.DataFrame, kural_etiketleri: Mapping[str, pd.Series],
        ml_etiket: pd.Series, gizli: pd.Series | None = None, zorla=None) -> Hikaye:
    """Sahneyi seçer (modül notu).

    ozellik           mağaza × ham S1 özellikleri (`karisim/<grup>/<nitelik>/<değer>` payları)
    kapsam            `kaynak.kapsam`: `magaza_id, bolge, istanbul, metropol, kumelenir`
    kural_etiketleri  {"k2": ciro sınıfı, "k3": bölge×sınıf} (magaza_id dizinli)
    ml_etiket         mağaza → ML kümesi (önerilen küme)
    gizli             mağaza → gizli segment (isteğe bağlı; yalnız doğrulama)
    zorla             ((m_a, m_b), (m_c, m_d)): verilen çiftler sahne olur"""
    w = _Dunya(ozellik, kapsam, kural_etiketleri, ml_etiket)
    g = _gizli_hazirla(gizli, w)
    if zorla is not None:
        return _zorlanan(w, zorla, g)
    birinci = _bul(w, g, frozenset())
    try:
        alt = _bul(w, g, frozenset({*birinci.cift1, *birinci.cift2}))
    except ValueError:
        alt = None
    return Hikaye(**{**birinci.__dict__, "alternatif": alt})
