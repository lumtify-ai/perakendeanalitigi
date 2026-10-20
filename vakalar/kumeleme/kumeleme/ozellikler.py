"""Mağaza özellikleri: satış karışımı, beden eğrisi, mevsimsellik, çeşitten arındırma, ölçek.

Kural: bu bir karar modülüdür; yalnız yayımlanan `satis`, `stok`, `magaza`, `urun` tablolarını okur,
gizli gerçeğe (`perakende_veri`, gizli mağaza tablosu) ve ölçüm modüllerine dokunmaz (AST kilidi,
`tests/test_sizinti.py`). Okunan her satır karar gününden öncedir (aşağıda pencere).

**Pencere** (`pencere`). Karar gününden önceki son `OZELLIK_HAFTA` = 104 **tamamlanmış**
pazartesi-pazar haftası: `[bas, bit)`, `bit` karar gününün haftasının pazartesisi (SS25: karar cuma
2025-02-07, pencere 2023-02-06 … 2025-02-02). Karar haftasının karar gününden önceki günleri de
okunmaz (hafta tamamlanmadı; `kaynak.kapsam`'ın `gecmis_hafta` tanımıyla aynı hafta). Stokta
pazartesi `d` fotoğrafı önceki yedi günü (`d−7 … d−1`) anlatır (`stoklu_gun`, v4 README); pencere
`bas < d <= bit` fotoğraflarını okur, yani tam olarak aynı 104 haftayı. `bit` fotoğrafı karar
gününden önce (pazartesi sabahı) çekilmiştir.

**Satış.** Brüt adet: pozitif adetli satırlar (iade, yani negatif adet, düşülmez), mükerrer satır
tek sayılır (`select distinct`, ortak `temiz_satis` ile aynı kural, pencereyle sınırlı). Line
grupları: `Collection` ve `Basic+NOS` (Basic ile NOS birlikte); Outlet line'ı (outlet
mağazalarının malı) bütün bloklardan dışarıdadır.

**Bloklar** (sütun adları `blok/...`; aileler blokların birleşimidir, `AILELER`):

    karisim         her line grubunda alt kategori, fiyat segmenti ve kalıp payları: bir
                    nitelik içinde paylar bire toplanır (`karisim/<grup>/<nitelik>/<değer>`).
                    İki grubun payları ayrı ayrı kurulur ve yan yana konur (birleşim); grup
                    payı (Collection'ın toplam içindeki payı) ayrı bir özellik değildir.
    beden           beden sırası 1-5 eğrisi, beden seti içinde: her setin içinde sıra payları,
                    sonra mağazanın sattığı setlerin eğrilerinin eşit ağırlıklı ortalaması
                    (`beden/<sıra>`). Böylece mağazanın kadın/erkek ya da harf/numara karışımı
                    eğriyi kaydırmaz. Tek bedenli set (Standart) eğri taşımaz, dışarıdadır.
    mevsim          12 takvim ayının payı (`mevsim/01` … `mevsim/12`): her ay için **satışlı gün
                    başına** brüt adet (pencerenin iki yılı birlikte), paylara çevrilir. Gün başına
                    hız, açılış, tadilat ve pencere kenarının ay payını bozmasını önler. Satışlı
                    gün: mağazanın en az bir brüt satışı olan gün.
    olcek           log günlük net ciro (pencerenin net `tutar`ı, iade dahil, ÷ satışlı gün),
                    log m², log kapasite. Karışımla aynı bloğa konmaz.

Satışlı gün (mevsim ve ölçek) ve ciro mağazanın **bütün** satışından sayılır (her line, her ürün;
`urun` tablosuyla eşleşmeyen satır da); paylardaki adet ise yalnız üç line'ın (Collection, Basic,
NOS) satışıdır.

**Çeşitten arındırma** (`*_stoklu` bloklar, S4). Mağaza gizli segmentiyle (v4'te gelir, kadın payı
ve m²'yle) seçilmiş bir çeşit taşır; ham satış payı bu yüzden kısmen çeşidi yansıtır. Arındırılmış
blokta pay, ham adet yerine **stoklu gün başına satış** hızından kurulur:

    karisim_stoklu  değer başına brüt adet ÷ stoklu option-gün
    beden_stoklu    set × sıra başına brüt adet ÷ stoklu SKU-gün (beden SKU niteliğidir)
    mevsim_stoklu   ay başına brüt adet ÷ stoklu option-gün

Stoklu gün yayımlanan `stok` fotoğraflarından okunur (`stoklu_gun`: haftanın satışa rafta malla
açılan gün sayısı; motorun günlük bayrağının haftalık toplamı, kesin). Option-gün haftada
option'ın SKU'larının en çok stoklu gününe eşittir (birleşimin alt sınırı: SKU'ların hangi gün
stoklu olduğu haftalık fotoğrafta yoktur). Mevsim için bir fotoğraf haftasının option-günleri
haftanın günlerine eşit bölünüp aylarına dağıtılır. İlk Sevkiyat'ın `kaynak.gunluk_matrisler`'i ve
ortak `perakende_analitik.stok` günlük stoğu yeniden kurar; burada gerekmez: mağaza × kategori
düzeyinde iki yılın hızı, günlük durumu değil yalnız stoklu gün sayısını ister ve o sayı yayımlanan
tabloda hazırdır (ortak modülün iki yıllık günlük tablosu ~1,2 GB; burada SS25'te ölçülen süreç
tepe belleği S4 için ~0,6 GB, süre ~10 sn).

**Bellek.** Satış ve stok DuckDB'de süzülüp toplanır, 13 haftalık dilimlerle okunur (mükerrer
satırın iki kopyası aynı gündedir, aynı dilime düşer); Python'a yalnız mağaza × kategori
toplamları gelir. Ciro kuruş olarak tamsayı toplanır: sonuç toplama sırasından bağımsızdır.

Hayalet stok (v4 README "Kirli kayıtlar": mağazanın taşımadığı SKU'da tek pazartesi fotoğrafı)
pencerenin içinde aynı imzayla ayıklanır: pencerede tek fotoğrafı olan, adetli ve pencerede hiç brüt
satışı olmayan hücre stoklu sayılmaz. Gerçek v4'te SS25 penceresinde, bütün fiziksel mağazalarda,
bu imza ortak `cesit_hucreleri`'nin bütün tablodan bulduğu 150 hayaletin pencereye düşen 100'üyle
birebir aynıdır (67 kümelenen mağazanın arındırılmış bloklarında etkisi birkaç hücredir).

**Gözlenmeyen hücre** (oran bloklarında: stoklu günü 0 olan kategori, satışlı günü 0 olan ay).
Hız tanımsızdır; 0 saymak çeşidi geri sokar. Stoklu günü 0 olan hücrede yine de satış olabilir
(o pencerede fotoğrafı olmayan hücre); o adet hıza girmez, alt blok başına
`X.attrs["dusen_satis"]`'ta sayılır. Nötr doldurulur: hücre = (o sütunun, gözlendiği
mağazalardaki medyan hızı) × (mağazanın gözlenen sütunlarda medyana göre medyan oranı), yani
"mağaza taşımadığı kategoride kendi düzeyinde ortalama bir mağaza gibi". Doldurulan hücre sayısı
blok başına `X.attrs["doldurulan"]`'dadır. Hiçbir mağazada gözlenmeyen sütun düşer. Doldurma
verilen mağaza kümesinin medyanını kullanır (mağaza kümesi değişirse doldurulan değer değişebilir;
gözlenen hücreler değişmez).

**Standartlama** (`standartla`). Her sütun mağazalar üstünde z-skora çevrilir (popülasyon
standart sapması); sabit sütun bilgi taşımaz ve düşer. Ağırlık iki katmanlıdır (Ruling R7):
bloklar eşittir (her bloğun toplam varyansı 1: karışımın ~45 sütunu mevsimin 12'sini ezmez), blok
içinde de **alt bloklar** eşittir. Alt blok karışımda (grup, nitelik) çiftidir: iki line grubu ×
alt kategori, fiyat segmenti, kalıp = 6 alt blok, her biri bloğun varyansının 1/6'sı (alt
kategorinin ~17 sütunu fiyat segmentinin 3 sütununu ezmez); beden, mevsim ve ölçekte alt blok
bloğun kendisidir. `S` alt bloklu bloğun `n` sütunlu alt bloğundaki her sütun √(n·S)'ye bölünür.
Ablasyon için `agirlik="sutun"`: blok içinde sütunlar eşit (blok √sütun sayısına bölünür).

**Kimlik** (`ozellik_kimligi`). Satır ve sütun adlarına göre sıralanmış tablonun SHA-256 özeti
(değerler 10 ondalığa yuvarlanır); satır ya da sütun sırasından bağımsızdır.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence

import duckdb
import numpy as np
import pandas as pd

from kumeleme import sabitler

AYRAC = "/"
LINE_GRUPLARI: dict[str, tuple[str, ...]] = {"Collection": ("Collection",), "Basic+NOS": ("Basic", "NOS")}
NITELIKLER = ("alt_kategori", "fiyat_segmenti", "kalip")
AYLAR = tuple(range(1, 13))
BLOKLAR = ("karisim", "beden", "mevsim", "olcek", "karisim_stoklu", "beden_stoklu", "mevsim_stoklu")
AILELER: dict[str, tuple[str, ...]] = {
    "S1": ("karisim",),                                       # satış karışımı
    "S2": ("karisim", "beden", "mevsim"),                     # + beden eğrisi + mevsimsellik
    "S4": ("karisim_stoklu", "beden_stoklu", "mevsim_stoklu"),  # S2, çeşitten arındırılmış
    "S5": ("karisim", "beden", "mevsim", "olcek"),            # S2 + ölçek (ablasyon)
}
_STOKLU = {"karisim_stoklu", "beden_stoklu", "mevsim_stoklu"}
_ALT_BLOKLU = {"karisim", "karisim_stoklu"}      # alt blokları (grup, nitelik) olan bloklar
_TABLOLAR = ("satis", "stok", "magaza")
_YUVARLAMA = 10
_ON = "_oz_"     # bağlantıda geçici nesnelerin öneki


def pencere(karar_gunu, hafta: int = sabitler.OZELLIK_HAFTA) -> tuple[pd.Timestamp, pd.Timestamp]:
    """`[bas, bit)`: karar gününden önceki son `hafta` tamamlanmış pazartesi-pazar haftası."""
    k = pd.Timestamp(karar_gunu).normalize()
    bit = k - pd.Timedelta(days=k.weekday())
    return bit - pd.Timedelta(weeks=hafta), bit


def _dilimler(bas: pd.Timestamp, bit: pd.Timestamp, hafta: int = 13):
    """`[bas, bit)` aralığını `hafta`lık ardışık dilimlere böler (son dilim kısa olabilir)."""
    d = bas
    while d < bit:
        e = min(d + pd.Timedelta(weeks=hafta), bit)
        yield d.to_pydatetime(), e.to_pydatetime()
        d = e


def _bloklar(aile: str) -> tuple[str, ...]:
    if aile in AILELER:
        return AILELER[aile]
    if aile in BLOKLAR:
        return (aile,)
    raise ValueError(f"bilinmeyen aile ya da blok: {aile!r} (aileler {list(AILELER)}, bloklar {list(BLOKLAR)})")


def _kimlikler(magazalar) -> list[str]:
    if isinstance(magazalar, pd.DataFrame):
        magazalar = magazalar["magaza_id"]
    ids = sorted({str(m) for m in magazalar})
    if not ids:
        raise ValueError("mağaza listesi boş")
    return ids


# ---------------------------------------------------------------------------
# Okuma: bağlantı ve toplamlar (DuckDB'de süzülür ve toplanır)
# ---------------------------------------------------------------------------


class _Okuyucu:
    """Bağlantı üstünde pencereli toplamlar; geçici nesneleri `kapat` siler."""

    def __init__(self, tablolar, urunler: pd.DataFrame, ids: list[str], bas, bit, stoklu: bool):
        if isinstance(tablolar, duckdb.DuckDBPyConnection):
            self.con, self._kendi = tablolar, False
        else:
            eksik = [ad for ad in ("satis",) + (("stok",) if stoklu else ()) if ad not in tablolar]
            if eksik:
                raise KeyError(f"tablolar eksik: {eksik}")
            self.con, self._kendi = duckdb.connect(":memory:"), True
            for ad in _TABLOLAR:
                if ad in tablolar:
                    self.con.register(ad, tablolar[ad])
        self.ids, self.bas, self.bit = ids, pd.Timestamp(bas), pd.Timestamp(bit)
        self._kayitli: list[str] = []
        self._gecici: list[str] = []
        try:
            self._kur(urunler, stoklu)
        except BaseException:
            self.kapat()
            raise

    def _kaydet(self, ad: str, df: pd.DataFrame) -> None:
        self.con.register(_ON + ad, df)
        self._kayitli.append(_ON + ad)

    def _tablo(self, ad: str, sql: str, params=()) -> None:
        self.con.execute(f"create or replace temp table {_ON}{ad} as {sql}", list(params))
        self._gecici.append(_ON + ad)

    def _kur(self, urunler: pd.DataFrame, stoklu: bool) -> None:
        u = urunler.loc[urunler["line"].astype(str).isin(
            [l for ls in LINE_GRUPLARI.values() for l in ls])]
        grup = {l: g for g, ls in LINE_GRUPLARI.items() for l in ls}
        tek = u.groupby(u["beden_seti"].astype(str))["beden_sira"].nunique()
        self.urun = pd.DataFrame({
            "urun_id": u["urun_id"].astype(str).to_numpy(),
            "option_id": u["option_id"].astype(str).to_numpy(),
            "grup": u["line"].astype(str).map(grup).to_numpy(),
            **{a: u[a].astype(str).to_numpy() for a in NITELIKLER},
            "beden_seti": u["beden_seti"].astype(str).to_numpy(),
            "beden_sira": u["beden_sira"].astype("int64").to_numpy(),
            "egri": u["beden_seti"].astype(str).map(tek).gt(1).to_numpy(),
        })
        self._kaydet("urun", self.urun)
        self._kaydet("m", pd.DataFrame({"m": self.ids}))
        # Satış, dilim dilim (tek sorguda `distinct` bütün pencerenin satırlarını belleğe alırdı):
        # hücre × ay brüt adet, mağaza × ay satışlı gün ve net ciro (kuruş).
        self._tablo("su", "select ''::varchar as m, ''::varchar as u, 0 as ay, 0::bigint as adet where false")
        self._tablo("sg", "select ''::varchar as m, 0 as ay, 0::bigint as gun, 0::bigint as kurus where false")
        for d0, d1 in _dilimler(self.bas, self.bit):
            temiz = (f"(select distinct * from satis where tarih >= ? and tarih < ? "
                     f"and magaza_id::varchar in (select m from {_ON}m))")
            self.con.execute(f"""
                insert into {_ON}su
                select magaza_id::varchar, urun_id::varchar, month(tarih), sum(adet)::bigint
                from {temiz} where adet > 0 group by all""", [d0, d1])
            self.con.execute(f"""
                insert into {_ON}sg
                select magaza_id::varchar, month(tarih),
                       count(distinct case when adet > 0 then tarih::date end)::bigint,
                       sum(round(tutar * 100))::bigint
                from {temiz} group by all""", [d0, d1])
        self.con.execute(f"create or replace temp table {_ON}su as "
                         f"select m, u, ay, sum(adet)::bigint as adet from {_ON}su group by all")
        self.con.execute(f"create or replace temp table {_ON}sg as select m, ay, sum(gun)::bigint as gun, "
                         f"sum(kurus)::bigint as kurus from {_ON}sg group by all")
        satisli = {r[0] for r in self.con.execute(f"select distinct m from {_ON}su").fetchall()}
        eksik = [m for m in self.ids if m not in satisli]
        if eksik:
            raise ValueError(f"pencerede [{self.bas.date()}, {self.bit.date()}) brüt satışı olmayan "
                             f"mağaza: {eksik}")
        if stoklu:
            self._stok_kur()

    def _stok_kur(self) -> None:
        """Stoklu günler: option-gün (nitelik ve fotoğraf haftası başına) ve SKU-gün (beden).

        Fotoğraflar `(bas, bit]`. Hayalet: pencerede tek fotoğrafı olan, adetli ve pencerede brüt
        satışı olmayan hücre. Option-gün dilim dilim toplanır (fotoğraf tarihi dilimleri ayırır)."""
        foto = (f"(select magaza_id::varchar as m, urun_id::varchar as u, tarih, adet, stoklu_gun "
                f"from stok where tarih > ? and tarih <= ? "
                f"and magaza_id::varchar in (select m from {_ON}m))")
        self._tablo("hucre", "select ''::varchar as m, ''::varchar as u, 0::bigint as n, 0 as adet where false")
        for d0, d1 in _dilimler(self.bas, self.bit):
            self.con.execute(f"insert into {_ON}hucre select m, u, count(*), max(adet) from {foto} f "
                             f"group by m, u", [d0, d1])
        self._tablo("hayalet", f"""
            select m, u from {_ON}hucre f group by m, u
            having sum(n) = 1 and max(adet) > 0
               and not exists (select 1 from {_ON}su s where s.m = f.m and s.u = f.u)""")
        self.con.execute(f"drop table {_ON}hucre")
        self._gecici.remove(_ON + "hucre")
        temiz = (f"(select f.*, x.option_id, x.egri, x.beden_seti, x.beden_sira from {foto} f "
                 f"join {_ON}urun x on x.urun_id = f.u "
                 f"where not exists (select 1 from {_ON}hayalet h where h.m = f.m and h.u = f.u))")
        nit = ", ".join(NITELIKLER)
        bos = ", ".join(f"''::varchar as {a}" for a in NITELIKLER)
        self._tablo("ogn", f"select ''::varchar as m, ''::varchar as grup, {bos}, 0::bigint as gun where false")
        self._tablo("ogh", "select ''::varchar as m, null::timestamp as tarih, 0::bigint as gun where false")
        self._tablo("ogb", "select ''::varchar as m, ''::varchar as beden_seti, 0::bigint as beden_sira, "
                           "0::bigint as gun where false")
        self._gecici.append(_ON + "og")
        for d0, d1 in _dilimler(self.bas, self.bit):
            self.con.execute(f"""
                create or replace temp table {_ON}og as
                select m, option_id, tarih, max(stoklu_gun)::bigint as gun
                from {temiz} t group by all""", [d0, d1])
            self.con.execute(f"""
                insert into {_ON}ogn
                with o as (select distinct option_id, grup, {nit} from {_ON}urun)
                select g.m, o.grup, {", ".join("o." + a for a in NITELIKLER)}, sum(g.gun)::bigint
                from {_ON}og g join o using (option_id) group by all""")
            self.con.execute(f"insert into {_ON}ogh select m, tarih, sum(gun)::bigint from {_ON}og group by all")
            self.con.execute(f"""
                insert into {_ON}ogb
                select m, beden_seti, beden_sira, sum(stoklu_gun)::bigint from {temiz} t
                where egri group by all""", [d0, d1])
        self.con.execute(f"drop table {_ON}og")
        self._gecici.remove(_ON + "og")

    def df(self, sql: str) -> pd.DataFrame:
        return self.con.execute(sql).df()

    def kapat(self) -> None:
        for ad in reversed(self._gecici):
            self.con.execute(f"drop table if exists {ad}")
        for ad in self._kayitli:
            self.con.unregister(ad)
        if self._kendi:
            self.con.close()

    # --- toplamlar --------------------------------------------------------

    def satis_nitelik(self) -> pd.DataFrame:
        return self.df(f"""
            select s.m, x.grup, {", ".join("x." + a for a in NITELIKLER)}, sum(s.adet)::bigint as adet
            from {_ON}su s join {_ON}urun x on x.urun_id = s.u group by all""")

    def gun_nitelik(self) -> pd.DataFrame:
        return self.df(f"select m, grup, {', '.join(NITELIKLER)}, sum(gun)::bigint as gun "
                       f"from {_ON}ogn group by all")

    def satis_beden(self) -> pd.DataFrame:
        return self.df(f"""
            select s.m, x.beden_seti, x.beden_sira, sum(s.adet)::bigint as adet
            from {_ON}su s join {_ON}urun x on x.urun_id = s.u where x.egri group by all""")

    def gun_beden(self) -> pd.DataFrame:
        return self.df(f"select m, beden_seti, beden_sira, sum(gun)::bigint as gun from {_ON}ogb group by all")

    def satis_ay(self) -> pd.DataFrame:
        return self.df(f"""
            select s.m, s.ay, sum(s.adet)::bigint as adet
            from {_ON}su s join {_ON}urun x on x.urun_id = s.u group by all""")

    def gun_ay(self) -> pd.DataFrame:
        return self.df(f"select m, ay, gun from {_ON}sg")

    def gun_hafta(self) -> pd.DataFrame:
        # sıralı: aylara bölme kesirli toplar, toplama sırası sabit olmalı (kimlik)
        return self.df(f"select m, tarih, sum(gun)::bigint as gun from {_ON}ogh group by all order by m, tarih")

    def ciro(self) -> pd.DataFrame:
        return self.df(f"select m, sum(kurus)::bigint as kurus, sum(gun)::bigint as gun "
                       f"from {_ON}sg group by m")

    def magaza(self) -> pd.DataFrame:
        return self.df("select magaza_id::varchar as m, metrekare, kapasite from magaza "
                       f"where magaza_id::varchar in (select m from {_ON}m)")


# ---------------------------------------------------------------------------
# Paylar ve nötr doldurma
# ---------------------------------------------------------------------------


def _pivot(df: pd.DataFrame, sutun: str, deger: str, ids: list[str], sutunlar=None) -> pd.DataFrame:
    if df.empty:
        p = pd.DataFrame(index=pd.Index(ids, name="m"))
    else:
        p = df.pivot_table(index="m", columns=sutun, values=deger, aggfunc="sum", fill_value=0)
        p = p.reindex(index=ids, fill_value=0)
    if sutunlar is not None:
        p = p.reindex(columns=sutunlar, fill_value=0)
    return p.astype("float64")


def _paya(R: pd.DataFrame, ad: str) -> pd.DataFrame:
    t = R.sum(axis=1)
    sifir = list(t.index[~(t > 0)])
    if sifir:
        raise ValueError(f"{ad}: payda sıfır (satış ya da stoklu gün yok): {sifir}")
    return R.div(t, axis=0)


def _oran(adet: pd.DataFrame, gun: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Hız = adet ÷ gün; gün 0 (ya da yok) ise NaN (gözlenmedi). İkinci değer: günü 0 olan
    hücrelerin satışı (hıza girmeyen, düşen brüt adet)."""
    sutunlar = gun.columns.union(adet.columns)
    a = adet.reindex(columns=sutunlar, fill_value=0)
    g = gun.reindex(index=a.index, columns=sutunlar, fill_value=0)
    dusen = int(round(a.where(~(g > 0), 0).to_numpy().sum()))
    return (a / g.where(g > 0)).dropna(axis=1, how="all"), dusen


def _notr_doldur(R: pd.DataFrame, ad: str) -> tuple[pd.DataFrame, int]:
    """NaN hücre = sütun medyan hızı × mağazanın gözlenen sütunlarda medyana oranının medyanı."""
    eksik = R.isna()
    n = int(eksik.to_numpy().sum())
    if n == 0:
        return R, 0
    med = R.median(axis=0, skipna=True)
    poz = med[med > 0].index
    duzey = R[poz].div(med[poz], axis=1).median(axis=1, skipna=True)
    tanimsiz = list(duzey.index[duzey.isna() & eksik.any(axis=1)])
    if tanimsiz:
        raise ValueError(f"{ad}: gözlenen hiçbir sütunu olmayan mağaza: {tanimsiz}")
    doldur = pd.DataFrame(np.outer(duzey.fillna(0).to_numpy(), med.to_numpy()),
                          index=R.index, columns=R.columns)
    return R.where(~eksik, doldur), n


def _adlandir(P: pd.DataFrame, *on: str) -> pd.DataFrame:
    P = P.copy()
    P.columns = [AYRAC.join([*on, str(c)]) for c in P.columns]
    return P


# ---------------------------------------------------------------------------
# Bloklar
# ---------------------------------------------------------------------------


def _karisim(o: _Okuyucu, stoklu: bool) -> tuple[pd.DataFrame, int, dict]:
    blok = "karisim_stoklu" if stoklu else "karisim"
    s = o.satis_nitelik()
    g = o.gun_nitelik() if stoklu else None
    parca, n, dusen = [], 0, {}
    for grup in LINE_GRUPLARI:
        for a in NITELIKLER:
            ad = f"{blok}/{grup}/{a}"
            adet = _pivot(s[s["grup"] == grup], a, "adet", o.ids)
            if stoklu:
                R, dusen[ad] = _oran(adet, _pivot(g[g["grup"] == grup], a, "gun", o.ids))
                R, k = _notr_doldur(R, ad)
                n += k
            else:
                R = adet
            parca.append(_adlandir(_paya(R, ad), blok, grup, a))
    return pd.concat(parca, axis=1), n, dusen


def _beden(o: _Okuyucu, stoklu: bool) -> tuple[pd.DataFrame, int, dict]:
    blok = "beden_stoklu" if stoklu else "beden"
    siralar = sorted(o.urun.loc[o.urun["egri"], "beden_sira"].unique())
    setler = sorted(o.urun.loc[o.urun["egri"], "beden_seti"].unique())
    s = o.satis_beden()
    g = o.gun_beden() if stoklu else None
    toplam = pd.DataFrame(0.0, index=o.ids, columns=siralar)
    sayi = pd.Series(0, index=o.ids)
    n, dusen = 0, {}
    for b in setler:
        ad = f"{blok}/{b}"
        adet = _pivot(s[s["beden_seti"] == b], "beden_sira", "adet", o.ids)
        if stoklu:
            R, dusen[ad] = _oran(adet, _pivot(g[g["beden_seti"] == b], "beden_sira", "gun", o.ids))
            R = R.loc[R.notna().any(axis=1)]                  # seti hiç taşımayan mağaza: set yok
            R, k = _notr_doldur(R, ad)
            n += k
        else:
            R = adet.loc[adet.sum(axis=1) > 0]                # seti hiç satmayan mağaza: set yok
        if R.empty:
            continue
        P = _paya(R, ad).reindex(columns=siralar, fill_value=0.0)
        toplam.loc[P.index] += P
        sayi.loc[P.index] += 1
    yok = list(sayi.index[sayi == 0])
    if yok:
        raise ValueError(f"{blok}: beden eğrisi taşıyan hiçbir sette satışı/stoğu olmayan mağaza: {yok}")
    return _adlandir(toplam.div(sayi, axis=0), blok), n, dusen


def _hafta_aylara(gh: pd.DataFrame) -> pd.DataFrame:
    """Fotoğraf `d`'nin option-günlerini `d−7 … d−1` günlerine eşit böler, aylara toplar."""
    gun = pd.to_datetime(gh["tarih"]).dt.normalize()
    parca = [pd.DataFrame({"m": gh["m"].to_numpy(), "ay": (gun - pd.Timedelta(days=k)).dt.month.to_numpy(),
                           "gun": gh["gun"].to_numpy() / 7.0}) for k in range(1, 8)]
    return pd.concat(parca, ignore_index=True).groupby(["m", "ay"], as_index=False)["gun"].sum()


def _mevsim(o: _Okuyucu, stoklu: bool) -> tuple[pd.DataFrame, int, dict]:
    blok = "mevsim_stoklu" if stoklu else "mevsim"
    adet = _pivot(o.satis_ay(), "ay", "adet", o.ids, AYLAR)
    gun = _hafta_aylara(o.gun_hafta()) if stoklu else o.gun_ay()
    R, d = _oran(adet, _pivot(gun, "ay", "gun", o.ids, AYLAR))     # hiç gözlenmeyen ay düşer
    R, n = _notr_doldur(R, blok)
    P = _paya(R, blok)
    P.columns = [f"{a:02d}" for a in P.columns]
    return _adlandir(P, blok), n, ({blok: d} if stoklu else {})


def _olcek(o: _Okuyucu, stoklu: bool) -> tuple[pd.DataFrame, int, dict]:
    c = o.ciro().set_index("m").reindex(o.ids)
    m = o.magaza().set_index("m").reindex(o.ids)
    X = pd.DataFrame({"log_gunluk_ciro": (c["kurus"] / 100.0) / c["gun"],
                      "log_kapasite": m["kapasite"].astype("float64"),
                      "log_metrekare": m["metrekare"].astype("float64")}, index=o.ids)
    kotu = list(X.index[~(X > 0).all(axis=1)])
    if kotu:
        raise ValueError(f"olcek: ciro, m² ya da kapasite pozitif değil: {kotu}")
    return _adlandir(np.log(X), "olcek"), 0, {}


_KURUCU = {"karisim": (_karisim, False), "beden": (_beden, False), "mevsim": (_mevsim, False),
           "olcek": (_olcek, False), "karisim_stoklu": (_karisim, True),
           "beden_stoklu": (_beden, True), "mevsim_stoklu": (_mevsim, True)}


def ozellik_tablosu(tablolar: duckdb.DuckDBPyConnection | Mapping[str, pd.DataFrame],
                    magazalar: Iterable[str] | pd.DataFrame, urunler: pd.DataFrame, karar_gunu,
                    aile: str, *, hafta: int = sabitler.OZELLIK_HAFTA) -> pd.DataFrame:
    """Mağaza × özellik tablosu (modül notu); satırlar `magaza_id` sırasıyla, sütunlar blok sırasıyla.

    tablolar    yayımlanan v4'e bağlantı (`kaynak.baglan`) ya da `satis`, `stok`, `magaza`
                DataFrame'leri (stok yalnız `*_stoklu` bloklar için gerekir)
    magazalar   mağaza kimlikleri ya da `magaza_id` sütunlu tablo (örneğin `kapsam`'ın
                kümelenen satırları)
    urunler     yayımlanan `urun` tablosu
    aile        `AILELER` anahtarı (S1, S2, S4, S5) ya da tek blok adı (`BLOKLAR`)

    `attrs["doldurulan"]`: blok → nötr doldurulan hücre sayısı. `attrs["dusen_satis"]` (yalnız
    `*_stoklu` bloklarda): alt blok (karışımda `blok/grup/nitelik`, bedende `blok/set`, mevsimde
    blok) → stoklu günü 0 olan hücrelerin hıza girmeyen brüt adedi. Pencerede brüt satışı olmayan
    mağaza `ValueError`."""
    bloklar = _bloklar(aile)
    ids = _kimlikler(magazalar)
    bas, bit = pencere(karar_gunu, hafta)
    o = _Okuyucu(tablolar, urunler, ids, bas, bit, stoklu=bool(_STOKLU & set(bloklar)))
    try:
        parca, doldurulan, dusen = [], {}, {}
        for blok in bloklar:
            kur, stoklu = _KURUCU[blok]
            X, doldurulan[blok], d = kur(o, stoklu)
            dusen.update(d)
            parca.append(X[sorted(X.columns)])
    finally:
        o.kapat()
    X = pd.concat(parca, axis=1)
    X.index.name = "magaza_id"
    X.columns.name = None
    X.attrs["doldurulan"] = doldurulan
    if dusen:
        X.attrs["dusen_satis"] = dusen
    return X


# ---------------------------------------------------------------------------
# Standartlama ve kimlik
# ---------------------------------------------------------------------------


def alt_blok(sutun: str) -> str:
    """Sütunun alt bloğu: karışımda `blok/grup/nitelik` (ör. `karisim/Collection/kalip`), diğer
    bloklarda bloğun kendisi."""
    parca = str(sutun).split(AYRAC)
    return AYRAC.join(parca[:3]) if parca[0] in _ALT_BLOKLU else parca[0]


def standartla(X: pd.DataFrame, aileler: str | Sequence[str], *, agirlik: str = "alt_blok") -> pd.DataFrame:
    """Z-skor (popülasyon sapması), sabit sütun düşer; her blok toplam varyansı 1.

    `aileler`: `AILELER` anahtarı ya da blok adları; her sütun bunlardan birine (`blok/...`
    ön ekiyle) ait olmalı, her blokta en az bir sabit olmayan sütun bulunmalı.

    agirlik     "alt_blok" (varsayılan, Ruling R7): blok içinde her alt blok (`alt_blok`) eşit
                varyans alır; `S` alt bloklu bloğun `n` sütunlu alt bloğu √(n·S)'ye bölünür
                (karışımda iki grup × üç nitelik: her biri 1/6). "sutun" (ablasyon): blok
                sütun sayısının kareköküne bölünür; sütunlar eşit, alt bloklar sütun sayısıyla
                orantılı (karışımda alt kategorinin ~17 sütunu fiyat segmentini ve kalıbı ezer)."""
    if agirlik not in ("alt_blok", "sutun"):
        raise ValueError(f"bilinmeyen ağırlık: {agirlik!r} (alt_blok, sutun)")
    bloklar = _bloklar(aileler) if isinstance(aileler, str) else tuple(aileler)
    if X.isna().to_numpy().any():
        raise ValueError("özellik tablosunda NaN var")
    blok_ad = pd.Index([str(c).split(AYRAC, 1)[0] for c in X.columns])
    disarida = sorted(set(blok_ad) - set(bloklar))
    if disarida:
        raise ValueError(f"listelenmeyen bloğun sütunları: {disarida}")
    parca = []
    for b in bloklar:
        Z = X.loc[:, (blok_ad == b)].astype("float64")
        sd = Z.std(axis=0, ddof=0)
        Z = Z.loc[:, sd > 1e-12]
        if Z.shape[1] == 0:
            raise ValueError(f"{b}: sütun yok ya da hepsi sabit")
        Z = (Z - Z.mean(axis=0)) / sd[Z.columns]
        if agirlik == "sutun":
            bolen = pd.Series(np.sqrt(Z.shape[1]), index=Z.columns)
        else:
            alt = pd.Series([alt_blok(c) for c in Z.columns], index=Z.columns)
            bolen = np.sqrt(alt.map(alt.value_counts()) * alt.nunique())
        parca.append(Z / bolen)
    return pd.concat(parca, axis=1)


def ozellik_kimligi(X: pd.DataFrame) -> str:
    """İçerik özeti (SHA-256 hex): satır/sütun sırasından bağımsız, değerler 10 ondalık."""
    if X.index.has_duplicates or X.columns.has_duplicates:
        raise ValueError("satır ya da sütun adı tekrarlı")
    Y = X.sort_index(axis=0).sort_index(axis=1)
    h = hashlib.sha256(json.dumps({"satir": [str(i) for i in Y.index], "sutun": [str(c) for c in Y.columns]},
                                  ensure_ascii=False).encode("utf-8"))
    v = np.round(Y.to_numpy(dtype="float64"), _YUVARLAMA) + 0.0     # -0.0 -> 0.0
    v = np.where(np.isnan(v), np.nan, v)                             # tek NaN biçimi
    h.update(np.ascontiguousarray(v, dtype="<f8").tobytes())
    return h.hexdigest()
