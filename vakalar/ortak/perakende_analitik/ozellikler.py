"""Hücre-günlerin gözlemlenebilir özellikleri (kestiricilerin girdisi).

`ekle(con, hucre_gunler)` günlük tablonun anahtarlarına (`tarih`, `magaza_id`,
`urun_id`) yalnız yayımlanan tablolardan okunabilen özellikleri ekler. Gizli
gerçeğe dokunmaz; kayıp satışı bilmez.

Özellikler ve tanımları:

    hafta_gunu          0 = pazartesi ... 6 = pazar
    tatil               `takvim.tatil_mi` (takvimde olmayan gün: False)
    black_friday        gün, `tip = 'black_friday'` bir kampanyanın içinde mi
                        (günün trafik bayrağı; hücrenin kapsamından bağımsız)
    indirim_baslangici  gün, ürünün (sezon_kodu, dalga) için `sezon.indirim_baslangic`
                        gününden başlayan 7 günlük pencerede mi (devamlıda False)
    markdown_orani      `fiyat` panelinden, günün haftasının pazartesisine ait
                        satır; satır yoksa 0. Hat: `ONL` -> online; Outlet tipi
                        mağazada gün >= ürünün `cikis_tarihi` -> outlet; aksi normal
    kampanya_orani      o gün hücreyi kapsayan kampanyaların en büyük `oran`ı
                        (yoksa 0). Boş kapsam = hepsi; `kapsam_ust_kategori`,
                        `kapsam_line`, `kapsam_bolge` virgüllü listelerdir ve
                        ürünün `ust_kategori` / `line`, mağazanın `bolge` değeriyle
                        eşleşir. Bölgeli kampanya online'ı kapsamaz
    kampanya_id         kampanya_orani'nı veren kampanya (yoksa boş)
    oran                max(markdown_orani, kampanya_orani): etiket indirimi
    yas_gun             gün - ürünün lansman tarihi (gün); devamlıda -1
    line, ust_kategori, alt_kategori, fiyat_segmenti, beden_sira,
    liste_fiyati, alis_fiyati        ürün öznitelikleri
    magaza_tipi, sehir, metrekare    mağaza öznitelikleri (ONL: tip Online)
    kanal               "online" (ONL) ya da "magaza"

Bellek ve hız: girdi 50-70 M satıra çıkabilir. DuckDB yalnız küçük boyut
tablolarını (ürün, mağaza, kampanya x gün, fiyat paneli) kurar; satırlara
dağıtım `category` kodlarıyla numpy dizi indekslemesidir (satır başı Python
yok). Sütunlar kompakt türde döner: kategori, `float32` oran/fiyat, `int8` /
`int16` / `int32` küçük tamsayılar, `bool`. `sutunlar` yalnız istenen
özellikleri hesaplar (bellek sınırlı kalır).
"""

import duckdb
import numpy as np
import pandas as pd

OZELLIKLER = [
    "hafta_gunu", "tatil", "black_friday", "indirim_baslangici",
    "markdown_orani", "kampanya_orani", "kampanya_id", "oran", "yas_gun",
    "line", "ust_kategori", "alt_kategori", "fiyat_segmenti", "beden_sira",
    "magaza_tipi", "sehir", "metrekare", "kanal", "liste_fiyati", "alis_fiyati",
]

_URUN_KATEGORILERI = ("line", "ust_kategori", "alt_kategori", "fiyat_segmenti")
_HATLAR = ("normal", "outlet", "online")
_SENTINEL_GUN = np.int32(2_000_000_000)   # "hiç" (çıkış tarihi yok)


def _kodla(seri: pd.Series, idler: pd.Index, ad: str) -> np.ndarray:
    """Anahtar sütununu boyut tablosundaki satır sırasına çevirir (int32).

    `category` sütunda yalnız kategori listesi eşlenir, satır başına metin
    karşılaştırması yapılmaz. Boyutta olmayan anahtar ValueError verir."""
    kat = seri if isinstance(seri.dtype, pd.CategoricalDtype) else seri.astype("category")
    harita = idler.get_indexer(kat.cat.categories)
    kodlar = kat.cat.codes.to_numpy()
    if (kodlar < 0).any():
        raise ValueError(f"{ad}: boş anahtar var")
    kullanilan = np.bincount(kodlar, minlength=len(harita)) > 0
    eksik = kat.cat.categories[(harita < 0) & kullanilan]
    if len(eksik):
        raise ValueError(f"{ad}: boyut tablosunda yok: {list(eksik[:5])}")
    return harita.astype(np.int32)[kodlar]


def _kategori(seri: pd.Series) -> tuple[np.ndarray, pd.Index]:
    """Boyut sütunundan (satır -> kategori kodu, kategoriler); boş değer -1."""
    k = pd.Categorical(seri)
    return k.codes, k.categories


def _kategorik(kodlar: np.ndarray, kategoriler: pd.Index) -> pd.Categorical:
    return pd.Categorical.from_codes(kodlar, categories=kategoriler)


def _gun_sayisi(sutun: str) -> str:
    """SQL: tarih sütununu 1970-01-01'den gün sayısına çevirir."""
    return f"date_diff('day', date '1970-01-01', {sutun}::date)"


def _liste_icerir(kapsam: str, deger: str) -> str:
    """SQL: virgüllü kapsam listesi boş ya da `deger` onda geçiyor."""
    return (f"(coalesce(trim({kapsam}), '') = '' or "
            f"list_contains(list_transform(string_split({kapsam}, ','), x -> trim(x)), {deger}))")


class _Hesap:
    """Bir `ekle` çağrısının ortak ara değerleri; özellik başına tembel."""

    def __init__(self, con: duckdb.DuckDBPyConnection, hucre_gunler: pd.DataFrame):
        self.con = con
        self.urun = con.execute(f"""
            select u.urun_id::varchar as urun_id, u.option_id::varchar as option_id,
                   u.ust_kategori::varchar as ust_kategori, u.alt_kategori::varchar as alt_kategori,
                   u.line::varchar as line, u.fiyat_segmenti::varchar as fiyat_segmenti,
                   coalesce(u.beden_sira, -1)::int as beden_sira,
                   u.alis_fiyati::float as alis_fiyati, u.liste_fiyati::float as liste_fiyati,
                   coalesce({_gun_sayisi('u.lansman_tarihi')}, 0) as lansman,
                   (u.lansman_tarihi is not null and u.sezon_kodu::varchar <> 'DEVAMLI') as yasli,
                   coalesce({_gun_sayisi('u.cikis_tarihi')}, {int(_SENTINEL_GUN)}) as cikis,
                   (u.sezon_kodu::varchar <> 'DEVAMLI' and s.indirim_baslangic is not null) as ib_var,
                   coalesce({_gun_sayisi('s.indirim_baslangic')}, 0) as ib
            from urun u
            left join sezon s on s.sezon_kodu::varchar = u.sezon_kodu::varchar and s.dalga = u.dalga
            order by u.urun_id::varchar
        """).fetchdf()
        self.magaza = con.execute("""
            select magaza_id::varchar as magaza_id, tip::varchar as tip, sehir::varchar as sehir,
                   bolge::varchar as bolge, metrekare::int as metrekare
            from magaza order by magaza_id::varchar
        """).fetchdf()
        self.uk = _kodla(hucre_gunler["urun_id"], pd.Index(self.urun["urun_id"]), "urun_id")
        self.mk = _kodla(hucre_gunler["magaza_id"], pd.Index(self.magaza["magaza_id"]), "magaza_id")
        tarih = hucre_gunler["tarih"]
        gun = tarih.to_numpy().astype("datetime64[D]").astype(np.int64)
        self.gun = gun.astype(np.int32)
        del gun
        self.g0 = int(self.gun.min()) if len(self.gun) else 0
        self.g1 = int(self.gun.max()) if len(self.gun) else 0
        self._onbellek: dict = {}

    def _bir_kez(self, anahtar: str, uret):
        if anahtar not in self._onbellek:
            self._onbellek[anahtar] = uret()
        return self._onbellek[anahtar]

    # ------------------------------------------------------------- takvim

    def hafta_gunu(self) -> np.ndarray:
        # 1970-01-01 perşembedir; pazartesi = 0
        return self._bir_kez("hafta_gunu", lambda: ((self.gun + 3) % 7).astype(np.int8))

    def _gun_bayragi(self, sql: str) -> np.ndarray:
        """SQL'in döndürdüğü gün sayıları için [g0, g1] aralığında bool dizi."""
        dizi = np.zeros(self.g1 - self.g0 + 1, dtype=bool)
        gunler = self.con.execute(sql).fetchnumpy()["gun"].astype(np.int64)
        gunler = gunler[(gunler >= self.g0) & (gunler <= self.g1)]
        dizi[gunler - self.g0] = True
        return dizi

    def tatil(self) -> np.ndarray:
        dizi = self._gun_bayragi(
            f"select {_gun_sayisi('tarih')} as gun from takvim where tatil_mi")
        return dizi[self.gun - self.g0]

    def black_friday(self) -> np.ndarray:
        dizi = self._gun_bayragi(f"""
            select g.i as gun from range({self.g0}, {self.g1 + 1}) g(i)
            where exists (select 1 from kampanya k where k.tip::varchar = 'black_friday'
                          and g.i between {_gun_sayisi('k.baslangic')} and {_gun_sayisi('k.bitis')})""")
        return dizi[self.gun - self.g0]

    def indirim_baslangici(self) -> np.ndarray:
        ib = self.urun["ib"].to_numpy(np.int32)[self.uk]
        var = self.urun["ib_var"].to_numpy(bool)[self.uk]
        fark = self.gun - ib
        return var & (fark >= 0) & (fark < 7)

    # ------------------------------------------------------------- fiyat

    def markdown_orani(self) -> np.ndarray:
        def uret():
            opsiyonlar = pd.Index(sorted(self.urun["option_id"].unique()))
            opt_u = opsiyonlar.get_indexer(self.urun["option_id"]).astype(np.int32)
            m0 = self.g0 - (self.g0 + 3) % 7        # g0'ın pazartesisi
            m1 = self.g1 - (self.g1 + 3) % 7
            nhafta = (m1 - m0) // 7 + 1
            panel = np.zeros((len(opsiyonlar), nhafta, len(_HATLAR)), dtype=np.float32)
            ham = self.con.execute(f"""
                select o.kod as opt, ({_gun_sayisi('f.hafta_baslangic')} - {m0}) // 7 as hafta,
                       case f.hat::varchar when 'normal' then 0 when 'outlet' then 1
                                           else 2 end as hat,
                       f.indirim_orani::float as oran
                from fiyat f
                join (select option_id::varchar as o, row_number() over (order by option_id::varchar) - 1 as kod
                      from (select distinct option_id from urun)) o on o.o = f.option_id::varchar
                where {_gun_sayisi('f.hafta_baslangic')} between {m0} and {m1}
            """).fetchnumpy()
            panel[ham["opt"], ham["hafta"], ham["hat"]] = ham["oran"]

            online = (self.magaza["tip"] == "Online").to_numpy()[self.mk]
            outlet_m = (self.magaza["tip"] == "Outlet").to_numpy()[self.mk]
            cikis = self.urun["cikis"].to_numpy(np.int32)[self.uk]
            hat = np.where(online, 2, np.where(outlet_m & (self.gun >= cikis), 1, 0)).astype(np.int32)
            hafta = (self.gun - (self.gun + 3) % 7 - m0) // 7
            return panel.reshape(-1)[(opt_u[self.uk] * nhafta + hafta) * len(_HATLAR) + hat]
        return self._bir_kez("markdown_orani", uret)

    # ---------------------------------------------------------- kampanya

    def _kampanya(self) -> tuple[np.ndarray, np.ndarray, pd.Index]:
        """(satır başına kampanya oranı, kampanya kodu (-1 yok), kampanya kimlikleri)."""
        def uret():
            uc = self.urun[["ust_kategori", "line"]].drop_duplicates().reset_index(drop=True)
            uc["kod"] = np.arange(len(uc), dtype=np.int32)
            uc_u = (self.urun[["ust_kategori", "line"]]
                    .merge(uc, on=["ust_kategori", "line"], how="left")["kod"].to_numpy(np.int32))
            bk = self.magaza[["bolge"]].drop_duplicates().reset_index(drop=True)
            bk["kod"] = np.arange(len(bk), dtype=np.int32)
            bk["onl"] = False
            # online, bölgeli kampanyaya kapalıdır: kendi anahtarı olsun
            onl = pd.DataFrame({"bolge": ["\0ONL"], "kod": [len(bk)], "onl": [True]})
            bk = pd.concat([bk, onl], ignore_index=True)
            bk_m = np.where((self.magaza["tip"] == "Online").to_numpy(), len(bk) - 1,
                            bk.set_index("bolge")["kod"].reindex(self.magaza["bolge"]).fillna(-1)
                            .to_numpy()).astype(np.int32)
            kimlikler = pd.Index(sorted(
                r[0] for r in self.con.execute("select kampanya_id::varchar from kampanya").fetchall()))
            nuc, nbk, ngun = len(uc), len(bk), self.g1 - self.g0 + 1
            oran = np.zeros(ngun * nuc * nbk, dtype=np.float32)
            kod = np.full(ngun * nuc * nbk, -1, dtype=np.int16)

            self.con.register("_uc", uc)
            self.con.register("_bk", bk)
            try:
                ham = self.con.execute(f"""
                    select g.i - {self.g0} as gi, uc.kod as uc, bk.kod as bk,
                           k.kampanya_id::varchar as kid, k.oran::float as oran
                    from range({self.g0}, {self.g1 + 1}) g(i)
                    join kampanya k
                      on g.i between {_gun_sayisi('k.baslangic')} and {_gun_sayisi('k.bitis')}
                    cross join _uc uc
                    cross join _bk bk
                    where {_liste_icerir('k.kapsam_ust_kategori', 'uc.ust_kategori')}
                      and {_liste_icerir('k.kapsam_line', 'uc.line')}
                      and (coalesce(trim(k.kapsam_bolge), '') = ''
                           or (not bk.onl and {_liste_icerir('k.kapsam_bolge', 'bk.bolge')}))
                    qualify row_number() over (partition by g.i, uc.kod, bk.kod
                                               order by k.oran desc, k.kampanya_id::varchar) = 1
                """).fetchnumpy()
            finally:
                self.con.unregister("_uc")
                self.con.unregister("_bk")
            hucre = (ham["gi"].astype(np.int64) * nuc + ham["uc"]) * nbk + ham["bk"]
            oran[hucre] = ham["oran"]
            kod[hucre] = kimlikler.get_indexer(ham["kid"]).astype(np.int16)

            satir = ((self.gun - self.g0) * np.int32(nuc) + uc_u[self.uk]) * np.int32(nbk) + bk_m[self.mk]
            return oran[satir], kod[satir], kimlikler
        return self._bir_kez("kampanya", uret)

    def kampanya_orani(self) -> np.ndarray:
        return self._kampanya()[0]

    def kampanya_id(self) -> pd.Categorical:
        _, kod, kimlikler = self._kampanya()
        return _kategorik(kod, kimlikler)

    def oran(self) -> np.ndarray:
        return np.maximum(self.markdown_orani(), self.kampanya_orani())

    # ------------------------------------------------------------- ürün

    def yas_gun(self) -> np.ndarray:
        lansman = self.urun["lansman"].to_numpy(np.int32)[self.uk]
        yasli = self.urun["yasli"].to_numpy(bool)[self.uk]
        return np.where(yasli, self.gun - lansman, -1).astype(np.int16)

    def urun_kategorisi(self, ad: str) -> pd.Categorical:
        kodlar, kategoriler = _kategori(self.urun[ad])
        return _kategorik(kodlar[self.uk], kategoriler)

    def beden_sira(self) -> np.ndarray:
        return self.urun["beden_sira"].to_numpy(np.int16)[self.uk]

    def liste_fiyati(self) -> np.ndarray:
        return self.urun["liste_fiyati"].to_numpy(np.float32)[self.uk]

    def alis_fiyati(self) -> np.ndarray:
        return self.urun["alis_fiyati"].to_numpy(np.float32)[self.uk]

    # ----------------------------------------------------------- mağaza

    def magaza_kategorisi(self, sutun: str) -> pd.Categorical:
        kodlar, kategoriler = _kategori(self.magaza[sutun])
        return _kategorik(kodlar[self.mk], kategoriler)

    def metrekare(self) -> np.ndarray:
        return self.magaza["metrekare"].to_numpy(np.int32)[self.mk]

    def kanal(self) -> pd.Categorical:
        onl = (self.magaza["tip"] == "Online").to_numpy()[self.mk]
        return _kategorik(onl.astype(np.int8), pd.Index(["magaza", "online"]))


def ekle(con: duckdb.DuckDBPyConnection, hucre_gunler: pd.DataFrame,
         sutunlar: list[str] | None = None) -> pd.DataFrame:
    """`hucre_gunler`in (tarih, magaza_id, urun_id) anahtarlarına özellikleri ekler.

    `sutunlar` verilirse yalnız o özellikler hesaplanır (None: bütün
    `OZELLIKLER`); dönen çerçeve girdi sütunlarını aynı sırayla ve istenen
    özellikleri `OZELLIKLER` sırasıyla içerir. Satır sırası ve indeks
    korunur, girdi değişmez (sütunlar yeni çerçevede, girdi sütunları
    kopyalanmadan paylaşılır). `magaza_id` ve `urun_id` `category` ya da düz
    metin olabilir; boyut tablolarında bulunmayan anahtar ValueError verir."""
    if sutunlar is None:
        istenen = list(OZELLIKLER)
    else:
        bilinmeyen = [s for s in sutunlar if s not in OZELLIKLER]
        if bilinmeyen:
            raise ValueError(f"bilinmeyen özellik sütunu: {bilinmeyen}; geçerliler: {OZELLIKLER}")
        istenen = [s for s in OZELLIKLER if s in set(sutunlar)]

    h = _Hesap(con, hucre_gunler)
    uretici = {
        "hafta_gunu": h.hafta_gunu, "tatil": h.tatil, "black_friday": h.black_friday,
        "indirim_baslangici": h.indirim_baslangici, "markdown_orani": h.markdown_orani,
        "kampanya_orani": h.kampanya_orani, "kampanya_id": h.kampanya_id, "oran": h.oran,
        "yas_gun": h.yas_gun, "beden_sira": h.beden_sira, "liste_fiyati": h.liste_fiyati,
        "alis_fiyati": h.alis_fiyati, "metrekare": h.metrekare, "kanal": h.kanal,
        "magaza_tipi": lambda: h.magaza_kategorisi("tip"),
        "sehir": lambda: h.magaza_kategorisi("sehir"),
    }
    for ad in _URUN_KATEGORILERI:
        uretici[ad] = lambda ad=ad: h.urun_kategorisi(ad)

    cikti = hucre_gunler.copy(deep=False)
    for ad in istenen:
        cikti[ad] = uretici[ad]()
    return cikti


def etiket_fiyati(df: pd.DataFrame) -> pd.Series:
    """Etiket fiyatı: `liste_fiyati × (1 − oran)` (float64, df'nin indeksiyle)."""
    return df["liste_fiyati"].astype("float64") * (1.0 - df["oran"].astype("float64"))


def yol_suresi(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Mağaza başına depodan yol süresi (gün): `varis_tarihi − tarih`in en sık değeri.

    Yalnız kaynağı `DEPO` olan ve varış tarihi dolu sevkiyat satırları sayılır;
    beraberlikte küçük değer seçilir. Hiç depo sevkiyatı almamış mağaza
    (ör. `ONL`) sözlükte yoktur."""
    satirlar = con.execute("""
        select hedef::varchar as magaza_id,
               date_diff('day', tarih::date, varis_tarihi::date) as gun, count(*) as n
        from sevkiyat
        where kaynak::varchar = 'DEPO' and varis_tarihi is not null and hedef::varchar <> 'DEPO'
        group by 1, 2
        qualify row_number() over (partition by hedef::varchar order by count(*) desc,
                                   date_diff('day', tarih::date, varis_tarihi::date)) = 1
    """).fetchall()
    return {m: int(g) for m, g, _ in satirlar}
