"""Kollar: v4 motorunun `rpt` kancası (`g -> {option: adet}`).

Her kol (`KOLLAR`) oyun sezonlarının (AW24, SS25) Collection option'ları için kendi
kuralını, öteki bütün option'lar için Lumoda'nın bugünkü kuralını (`temel`, v4
`LumodaRPT`; `rpt.motor.lumoda("rpt")`) işletir — geçmiş ve gelecek sezonlar her
kolda aynıdır. Dağıtım kuralı ayrıdır (`dagitim.KURALLAR`, replenishment kancası).

    rpt_yok    oyun option'larına hiç RPT yok
    mevcut     Banu'nun kuralı: v4 `LumodaRPT`'nin kendisi (bütün option'lar)
    frr        Banu'nun tetiği (STR ≥ %55, yetişme) h. pazartesi; miktar FRR
               (çıplak satış ÷ çıplak eğri)
    oneri      aday modeli (olasılık ≥ eşik) + newsvendor, h = 2…6, ilk alarmda
    (kahin     ayrı modülde: `rpt.kahin.Kahin`; koşunun talebini bilir)

Option başına en fazla bir RPT: kol yalnız RPT'si olmayan (`rpt_sayisi == 0`)
oyun option'larına karar verir (Lumoda da öyle).

ÖNERİ KOLU, KARAR ANINDA. Her karar pazartesisi `t` kol kendi dünyasının geçmişinden
kestirir: `anlik.gunluk_gorunumden` (Görünüm → ortak günlük tablo; motor
`gecmis_kaydi`yla koşar, `gecmis_gerekir`) → `sansur.karar_ani_satirlari` (karar anı
Basit'i, karar havuzu = oyun sezonunun Collection option'ları, lansmandan `t`'ye;
Ruling R5) + `anlik.durum_gorunumden` → `aday.ozellikler` → model olasılığı ve
newsvendor miktarı. Tablo yolu aynı fonksiyonları yayımlanan tablolarla çağırır;
iki yol aynı girdide aynı kestirimi verir (`tests/test_anlik.py`).

ÇEVRİMDIŞI ÖĞRENİLENLER VERİDİR (`Ogrenilen`): option tablosu, eğriler, belirsizlik
(μ, σ), aday modelleri, p_ind, karar anı çarpanları, eşik. Kol onları argüman
alır; `parametreler()` her birinin özetini (pickle sha256) verir ve çağıran onu
`motor.kos(parametreler=…)`'e koyar: öğrenilen değişince koşu önbelleği de değişir.

SIZINTI. Kâhin dışındaki kollar yalnız `Gorunum`u, dünyanın kamuya açık alanlarını
ve geçmiş sezonlardan öğrenilmiş veriyi kullanır; bu modül `kahin`'i, `motor`'u,
üreteci, hakemi içe aktarmaz (`tests/test_sizinti.py`, geçişli; gizli alan listesi).
"""

import hashlib
import pickle
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import aday, anlik, miktar, sansur

OYUN_SEZONLARI = ("AW24", "SS25")
HAFTALAR = sansur.KARAR_HAFTALARI


def ozet_hash(nesne) -> str:
    """Çevrimdışı öğrenilmiş bir nesnenin özeti (pickle sha256, ilk 20 hane):
    koşu önbelleği anahtarı için (`parametreler`)."""
    return hashlib.sha256(pickle.dumps(nesne, protocol=5)).hexdigest()[:20]


@dataclass(frozen=True)
class Ogrenilen:
    """Kolların çevrimdışı öğrendikleri (yalnız oyun sezonundan önce kapanmış
    sezonlardan; bkz. `egri`, `miktar`, `aday`).

    optionlar   option başına: option_id, sezon_kodu, line, dalga, lansman_tarihi,
                indirim_baslangic, rpt_hafta, ilk_alim, moq_option, satis_hafta,
                liste_fiyati, alis_fiyati, mense (`aday.ozellikler`'in `opt`'u)
    egriler     sezon → {(yöntem, hedef): Egri}
    belirsizlik sezon → `miktar.Belirsizlik`
    modeller    sezon → `olasilik(ozl, model)` taşıyan nesne (`aday.Modeller`)
    p_ind       option_id → indirim dönemi beklenen fiyatı
    carpanlar   karar anı (pazartesi, Timestamp) → karar anında bilinen `Carpanlar`
                (`karar_anlari` ile listelenir)
    esik        aday modelinin olasılık eşiği"""

    optionlar: pd.DataFrame
    egriler: dict
    belirsizlik: dict = field(default_factory=dict)
    modeller: dict = field(default_factory=dict)
    p_ind: object = None
    carpanlar: dict = field(default_factory=dict)
    esik: float = aday.ESIK

    def carpan(self, t) -> object:
        t = pd.Timestamp(t).normalize()
        if t not in self.carpanlar:
            raise KeyError(f"Ogrenilen.carpanlar'da {t.date()} karar anı yok (karar_anlari ile kurun)")
        return self.carpanlar[t]

    def parametreler(self) -> dict:
        return {"optionlar": ozet_hash(self.optionlar), "egriler": ozet_hash(self.egriler),
                "belirsizlik": ozet_hash(self.belirsizlik), "modeller": ozet_hash(self.modeller),
                "p_ind": ozet_hash(self.p_ind),
                "carpanlar": ozet_hash(sorted(self.carpanlar.items(), key=lambda kv: kv[0])),
                "esik": float(self.esik)}


def karar_anlari(optionlar: pd.DataFrame, sezon: str, haftalar=HAFTALAR,
                 line: str = "Collection") -> list[pd.Timestamp]:
    """Sezonun `line` dalgalarının karar pazartesileri (lansman + 7h, h ∈ haftalar), sıralı."""
    o = optionlar[(optionlar["sezon_kodu"] == sezon) & (optionlar["line"] == line)]
    return sorted({pd.Timestamp(lan).normalize() + pd.Timedelta(days=7 * int(h))
                   for lan in pd.to_datetime(o["lansman_tarihi"]).unique() for h in haftalar})


class KolRPT:
    """Oyun option'ları için `karar`, ötekiler için `temel` (Lumoda)."""

    ad = "kol"
    gecmis_gerekir = False

    def __init__(self, temel, oyun_sezonlari=OYUN_SEZONLARI):
        self.temel = temel
        self.oyun_sezonlari = tuple(oyun_sezonlari)
        self.kayit: list[dict] = []
        self._w = None

    def _hazirla(self, w) -> None:
        if self._w is w:
            return
        self._w = w
        opt = w.optionlar
        self.oyun = ((opt["line"] == "Collection").to_numpy()
                     & opt["sezon_kodu"].isin(self.oyun_sezonlari).to_numpy())
        self.lansman = opt["lansman_gun"].to_numpy()
        self.indirim = opt["indirim_gun"].to_numpy()
        self.option_id = opt["option_id"].astype(str).to_numpy()
        self.sezon = opt["sezon_kodu"].astype(str).to_numpy()
        self.dalga = opt["dalga"].to_numpy()
        ted = w.tedarikciler.set_index("tedarikci_id")
        self.L = ted.loc[opt["tedarikci_id"], "rpt_hafta"].to_numpy().astype(int)
        self.moq = ted.loc[opt["tedarikci_id"], "moq_option"].to_numpy().astype(int)

    def karar(self, g, adaylar: np.ndarray) -> dict:
        return {}

    def __call__(self, g) -> dict:
        self._hazirla(g.dunya)
        dis = {int(o): q for o, q in self.temel(g).items() if not self.oyun[o]}
        h_gun = g.gun - self.lansman
        aday_ = np.flatnonzero(self.oyun & (h_gun >= 0) & (h_gun % 7 == 0) & (np.asarray(g.rpt_sayisi) == 0))
        ic = self.karar(g, aday_) if aday_.size else {}
        return {**dis, **ic}

    def _kaydet(self, g, o: int, adet: int, **bilgi) -> None:
        self.kayit.append({"gun": int(g.gun), "option": int(o), "option_id": self.option_id[o],
                           "h": int((g.gun - self.lansman[o]) // 7), "adet": int(adet), **bilgi})

    def parametreler(self) -> dict:
        """Koşu önbelleği anahtarına girecek tanım (`motor.kos(parametreler=…)`)."""
        return {"kol": self.ad, "oyun_sezonlari": list(self.oyun_sezonlari)}

    def kayit_tablosu(self) -> pd.DataFrame:
        """Kolun oyun option'larına verdiği RPT'ler (motor koşu kaydına alır)."""
        if not self.kayit:
            return pd.DataFrame(columns=["gun", "option", "option_id", "h", "adet"])
        return pd.DataFrame(self.kayit)


class RPTYok(KolRPT):
    ad = "rpt_yok"


class Mevcut(KolRPT):
    """Banu'nun kuralı: v4 `LumodaRPT`'nin kendisi, bütün option'lar için (oyun
    option'larının kararları kayda geçer). `rpt_yok` + Lumoda dağıtımıyla birlikte
    varsayılan motor = yayımlanan dünya."""

    ad = "mevcut"

    def __call__(self, g) -> dict:
        self._hazirla(g.dunya)
        sonuc = self.temel(g)
        for o, q in sorted(sonuc.items()):
            if self.oyun[o]:
                self._kaydet(g, o, int(q))
        return sonuc


class FRR(KolRPT):
    """Banu'nun tetiği `hafta`. pazartesi (zincir STR ≥ %55, lansman + 3 hafta + RPT
    süresi < indirim başı, mağazalara mal gitmiş); miktar FRR: Q2 = ((1 − ω) x / k_ham − Q1)⁺,
    x dünkü akşama dek zincir brüt satışı, k_ham çıplak eğrinin (indirim hedefli)
    h. haftaya birikimi."""

    ad = "frr"

    def __init__(self, temel, ogrenilen: Ogrenilen, hafta: int = 3, oyun_sezonlari=OYUN_SEZONLARI):
        super().__init__(temel, oyun_sezonlari)
        self.ogrenilen = ogrenilen
        self.hafta = int(hafta)

    def parametreler(self) -> dict:
        return {**super().parametreler(), "hafta": self.hafta,
                "egriler": ozet_hash({s: e[("ham", "indirim")] for s, e in self.ogrenilen.egriler.items()})}

    def karar(self, g, adaylar):
        w = g.dunya
        gonderilen = np.asarray(g.gonderilen_option)
        satilan = np.asarray(g.satilan_option)
        sonuc = {}
        for o in adaylar:
            h = (g.gun - self.lansman[o]) // 7
            if h != self.hafta:
                continue
            yetisir = self.lansman[o] + 7 * miktar.RPT_ILK_HAFTA + 7 * self.L[o] < self.indirim[o]
            str_ = satilan[o] / gonderilen[o] if gonderilen[o] > 0 else 0.0
            if gonderilen[o] <= 0 or str_ < miktar.RPT_STR_ESIGI or not yetisir:
                continue
            e = self.ogrenilen.egriler[self.sezon[o]][("ham", "indirim")]
            x = float(satilan[o])
            k = e.k((int(self.dalga[o]),), h)
            q = miktar.frr(x, k, float(np.asarray(w.ilk_alim)[o]), int(self.moq[o]))
            if q > 0:
                sonuc[int(o)] = q
                self._kaydet(g, o, q, x=x, str=float(str_))
        return sonuc


class Oneri(KolRPT):
    """Aday modeli + newsvendor; her karar pazartesisi karar anı kestirimi kendi
    dünyasının geçmişinden (modül notu)."""

    ad = "oneri"
    gecmis_gerekir = True

    def __init__(self, temel, ogrenilen: Ogrenilen, model: str = "lgbm", haftalar=HAFTALAR,
                 oyun_sezonlari=OYUN_SEZONLARI):
        super().__init__(temel, oyun_sezonlari)
        self.ogrenilen = ogrenilen
        self.model = model
        self.haftalar = tuple(int(h) for h in haftalar)
        self.kurucu = None

    def parametreler(self) -> dict:
        return {**super().parametreler(), "model": self.model, "haftalar": list(self.haftalar),
                "ogrenilen": self.ogrenilen.parametreler()}

    def karar(self, g, adaylar):
        w = g.dunya
        h = (g.gun - self.lansman[adaylar]) // 7
        adaylar = adaylar[np.isin(h, self.haftalar)]
        if not adaylar.size:
            return {}
        if self.kurucu is None or self.kurucu.w is not w:
            self.kurucu = anlik.GunlukKurucu(w)
        t = pd.Timestamp(g.tarih).normalize()
        ogr = self.ogrenilen
        opt = ogr.optionlar
        konum = {oid: i for i, oid in enumerate(self.option_id)}
        sonuc = {}
        for sezon in sorted(set(self.sezon[adaylar])):
            ids = set(self.option_id[adaylar[self.sezon[adaylar] == sezon]])
            havuz = sansur.karar_havuzu(opt, sezon, t)
            gunluk = self.kurucu(g, havuz)
            satir = sansur.karar_ani_satirlari(gunluk, opt, sezon, t, self.haftalar, ogr.carpan(t))
            satir = satir[satir["option_id"].astype(str).isin(ids)].reset_index(drop=True)
            if satir.empty:
                continue
            durum = anlik.durum_gorunumden(g, satir["option_id"], self.kurucu.idx)
            kayit = satir.merge(durum, on="option_id", how="left")
            ozl = aday.ozellikler(kayit, opt, ogr.egriler[sezon], ogr.belirsizlik[sezon], ogr.p_ind)
            p = ogr.modeller[sezon].olasilik(ozl, self.model)
            for r, pr in zip(ozl.itertuples(index=False), p):
                if pr >= ogr.esik and r.q_nv > 0:
                    o = konum[str(r.option_id)]
                    sonuc[o] = int(r.q_nv)
                    self._kaydet(g, o, int(r.q_nv), p=float(pr), x=float(r.x), D=float(r.D),
                                 str=float(r.str), ip=float(r.ip))
        return sonuc


KOLLAR = {"rpt_yok": RPTYok, "mevcut": Mevcut, "frr": FRR, "oneri": Oneri}
