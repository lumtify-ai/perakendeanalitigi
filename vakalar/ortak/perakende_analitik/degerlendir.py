"""Değerlendirme: kestirimi gizli gerçekle (hakem) karşılaştıran tek modül (spec §4.8).

`hakem`i içe aktarabilen tek modül burasıdır (`tests/test_sizinti.py` kilitler);
buradan kestiricilere hiçbir şey geri beslenmez (R15): ölçüt bir okumadır,
ayar düğmesi değil. Fonksiyonlar hakem tablosunu parametre alır
(`hakem.oku()["karsilanmayan"]`); modül `perakende_veri` kurulu olmadan da
içe aktarılabilir.

Karşılaştırma kuralı: tahmin, Kayıp tablosunun `kayip` (ya da `kayip_saf`)
sütunudur; gerçek, hakemin `karsilanmayan`ıdır. Hakemde olmayan hücre-gün,
gerçekte karşılanmayan talep yok demektir ve 0 sayılır (`eslestir`).

    wape      = Σ|t − g| / Σ g
    yanlilik  = Σ(t − g) / Σ g          (> 0: fazla tahmin)

t ve g önce `duzey`e (örn. mağaza × option × hafta) toplanır, fark ondan sonra
alınır. Toplam seviyede (`duzey = []`) WAPE = |yanlılık| olur; ince seviyede
satır dağılımı da cezalandırılır.

Kırılımlar (`kirilimlar`), her biri mağaza × option × hafta seviyesinde:

    durum   bos / tukenen (satırın kendi durumu)
    line    ürünün line'ı
    sure    (mağaza, SKU) için `eslesik`te ardışık takvim günleri bir koşudur;
            koşu uzunluğu <= 3 -> "kisa", aksi "uzun"; her satır koşusunun etiketini alır
    hit     gözlenebilir ölçüt: yalnız sezonluk option'lar (sezon_kodu <> 'DEVAMLI');
            STR = Σ net satış (temiz_satis, bütün kanallar, bütün pencere) ÷ Σ teslim
            edilmiş tedarikçi siparişi adedi; her sezon_kodu içinde STR'si en üst
            onda birde olan option "hit", kalanı (devamlı, teslimi olmayan dahil) "diger"
    kanal   "online" (magaza_id = ONL) / "magaza"
"""

import duckdb
import numpy as np
import pandas as pd

from perakende_analitik import kaynak

KISA_SURE = 3            # <= bu kadar ardışık gün: kısa stoksuzluk
HIT_DILIMI = 0.9         # STR'nin bu nicelinin üstü/eşiti: hit
KIRILIMLAR = ("durum", "line", "sure", "hit", "kanal")
_HAKEM_SUTUNLARI = ["karsilanmayan", "ikameye_giden", "kalici_kayip"]
_ANAHTAR = ["tarih", "magaza_id", "urun_id"]


# ------------------------------------------------------------- yardımcılar

def _kategorik(seri: pd.Series) -> pd.Series:
    return seri if isinstance(seri.dtype, pd.CategoricalDtype) else seri.astype("category")


def _evren(*seriler: pd.Series) -> pd.Index:
    """Serilerin değerlerinin (metne çevrilmiş) birleşimi; kategori evrenleri farklı olabilir."""
    evren = None
    for s in seriler:
        k = _kategorik(s).cat.categories.astype(str)
        evren = k if evren is None else evren.union(k)
    return evren


def _kodlar(seri: pd.Series, evren: pd.Index) -> np.ndarray:
    """Serinin her satırı için `evren`deki konum (int64)."""
    kat = _kategorik(seri)
    harita = evren.get_indexer(kat.cat.categories.astype(str))
    kod = kat.cat.codes.to_numpy()
    if (kod < 0).any():
        raise ValueError(f"{seri.name}: bos anahtar var")
    return harita[kod].astype(np.int64)


def _gun_sayisi(tarih: pd.Series) -> np.ndarray:
    return tarih.to_numpy().astype("datetime64[D]").astype(np.int64)


def _anahtar_dizisi(df: pd.DataFrame, mev: pd.Index, uev: pd.Index) -> np.ndarray:
    """(tarih, magaza_id, urun_id) -> tek int64 anahtar; kategori evrenlerinden bağımsız."""
    return ((_gun_sayisi(df["tarih"]) * len(mev) + _kodlar(df["magaza_id"], mev)) * len(uev)
            + _kodlar(df["urun_id"], uev))


def _anahtarlar(*cerceveler: pd.DataFrame) -> list[np.ndarray]:
    mev = _evren(*(c["magaza_id"] for c in cerceveler))
    uev = _evren(*(c["urun_id"] for c in cerceveler))
    return [_anahtar_dizisi(c, mev, uev) for c in cerceveler]


def _hafta(tarih: pd.Series) -> pd.Series:
    """Haftanın pazartesisi."""
    return (tarih - pd.to_timedelta(tarih.dt.dayofweek, unit="D")).dt.normalize()


def _etiketle(kodlu: pd.Series, kucuk: pd.Series) -> pd.Categorical:
    """`kodlu` (category) serisinin her kategorisi için `kucuk` etiketini satırlara dağıtır.

    `kucuk`: indeksi kategori adı (metin) olan seri; olmayan kategori NaN. Satır başına
    Python yok: etiketler kategori başına bir kez hesaplanır, satırlara kodla dağılır."""
    kat = _kategorik(kodlu)
    deger = kucuk.reindex(kat.cat.categories.astype(str)).to_numpy(dtype=object)
    etiket = pd.Categorical(deger)
    kod = etiket.codes[kat.cat.codes.to_numpy()]
    return pd.Categorical.from_codes(kod, categories=etiket.categories)


def _urun_sutunu(con: duckdb.DuckDBPyConnection, kodlu: pd.Series, sutun: str) -> pd.Categorical:
    """`urun` tablosundan, `kodlu` (urun_id) satırlarına `sutun` etiketi."""
    urun = con.execute(f"select urun_id::varchar as urun_id, {sutun}::varchar as deger "
                       "from urun").fetchdf().set_index("urun_id")["deger"]
    return _etiketle(kodlu, urun)


def _sutun(eslesik: pd.DataFrame, ad: str, con=None) -> pd.Series | pd.Categorical:
    """`eslesik`te varsa o sütun; yoksa türetilir (`hafta`; `option_id`, `line` -> urun tablosu)."""
    if ad in eslesik.columns:
        return eslesik[ad]
    if ad == "hafta":
        return _hafta(eslesik["tarih"])
    if ad in ("option_id", "line") and con is not None:
        return _urun_sutunu(con, eslesik["urun_id"], ad)
    raise ValueError(f"duzey sutunu yok ve turetilemez: {ad}")


# ----------------------------------------------------------------- eşleştir

def eslestir(kayip_df: pd.DataFrame, hakem_df: pd.DataFrame) -> pd.DataFrame:
    """Kayıp tablosuna hakemin `karsilanmayan`, `ikameye_giden`, `kalici_kayip` sütunlarını ekler.

    (tarih, magaza_id, urun_id) üzerinde sol birleşim; hakemde olmayan hücre-gün 0 (int32).
    Kayıp tablosunun bütün sütunları, sırası ve indeksi korunur. İki çerçevenin kimlik
    kategori evrenleri farklı olabilir (metne göre eşlenir). Hakemde tekrarlı anahtar
    ValueError verir."""
    ka, ha = _anahtarlar(kayip_df, hakem_df)
    sira = np.argsort(ha, kind="stable")
    ha = ha[sira]
    if len(ha) > 1 and (ha[1:] == ha[:-1]).any():
        raise ValueError("hakem anahtari (tarih, magaza_id, urun_id) tekil degil")
    if len(ha):
        poz = np.minimum(np.searchsorted(ha, ka), len(ha) - 1)
        var = ha[poz] == ka
    else:
        poz = np.zeros(len(ka), dtype=np.int64)
        var = np.zeros(len(ka), dtype=bool)
    cikti = kayip_df.copy(deep=False)
    for s in _HAKEM_SUTUNLARI:
        deger = hakem_df[s].to_numpy()[sira]
        cikti[s] = (np.where(var, deger[poz], 0) if len(ha) else np.zeros(len(ka))).astype("int32")
    return cikti


# ----------------------------------------------------------------- ölçütler

def _toplamlar(eslesik: pd.DataFrame, duzey: list[str], tahmin: str,
               con=None) -> pd.DataFrame:
    """`duzey` gruplarında Σt ve Σg (sütunlar `t`, `g`); `duzey` boşsa tek satır."""
    t = eslesik[tahmin].to_numpy(dtype=np.float64)
    g = eslesik["karsilanmayan"].to_numpy(dtype=np.float64)
    if not duzey:
        return pd.DataFrame({"t": [t.sum()], "g": [g.sum()]}) if len(t) else \
            pd.DataFrame({"t": [], "g": []})
    kolon = {c: _sutun(eslesik, c, con) for c in duzey}
    kolon["t"], kolon["g"] = t, g
    df = pd.DataFrame(kolon, index=eslesik.index)
    return df.groupby(duzey, observed=True, sort=False)[["t", "g"]].sum()


def _olcut(top: pd.DataFrame) -> dict:
    t = top["t"].to_numpy()
    g = top["g"].to_numpy()
    gt = g.sum()
    paydali = gt > 0
    return {
        "wape": float(np.abs(t - g).sum() / gt) if paydali else float("nan"),
        "yanlilik": float((t - g).sum() / gt) if paydali else float("nan"),
        "tahmin": float(t.sum()),
        "karsilanmayan": float(gt),
        "grup": int(len(top)),
    }


def olcutler(eslesik: pd.DataFrame, duzey: list[str], tahmin: str = "kayip",
             con: duckdb.DuckDBPyConnection | None = None) -> dict:
    """Önce `duzey`e toplar, sonra WAPE ve yanlılığı hesaplar (g = `karsilanmayan`).

    `tahmin`: karşılaştırılacak tahmin sütunu (`kayip` ya da `kayip_saf`). `duzey` sütunları
    `eslesik`te olabilir ya da türetilir (`hafta`: haftanın pazartesisi; `option_id`, `line`:
    `con` verilirse `urun` tablosundan). Boş `duzey` toplamdır (tek grup).
    Dönüş: `wape`, `yanlilik`, `tahmin` (Σt), `karsilanmayan` (Σg), `grup` (grup sayısı);
    Σg = 0 ise oranlar NaN."""
    return _olcut(_toplamlar(eslesik, list(duzey), tahmin, con))


# --------------------------------------------------------------- kırılımlar

def _sure_etiketi(eslesik: pd.DataFrame) -> pd.Categorical:
    """Her satır için kendi (mağaza, SKU) ardışık-gün koşusunun `kisa` / `uzun` etiketi."""
    mev, uev = _evren(eslesik["magaza_id"]), _evren(eslesik["urun_id"])
    hucre = _kodlar(eslesik["magaza_id"], mev) * len(uev) + _kodlar(eslesik["urun_id"], uev)
    gun = _gun_sayisi(eslesik["tarih"])
    sira = np.lexsort((gun, hucre))
    h, d = hucre[sira], gun[sira]
    kes = np.ones(len(sira), dtype=bool)
    if len(sira) > 1:
        kes[1:] = (h[1:] != h[:-1]) | (d[1:] - d[:-1] != 1)
    kosu = np.cumsum(kes) - 1
    uzunluk = np.bincount(kosu) if len(kosu) else np.zeros(0, dtype=np.int64)
    uzun = np.empty(len(sira), dtype=np.int8)
    uzun[sira] = (uzunluk[kosu] > KISA_SURE).astype(np.int8)
    return pd.Categorical.from_codes(uzun, categories=["kisa", "uzun"])


def hit_etiketleri(con: duckdb.DuckDBPyConnection) -> pd.Series:
    """option_id (metin) -> "hit" / "diger" (gözlenebilir ölçüt, sezon içinde STR'nin en üst onda biri).

    STR = Σ net satış (temiz_satis, bütün kanallar) ÷ Σ teslim edilmiş sipariş adedi
    (`gerceklesen_teslim` dolu). Yalnız `sezon_kodu <> 'DEVAMLI'` option'lar ve teslimi
    olanlar sıralanır; her `sezon_kodu` içinde STR >= %90 nicelik hit'tir. Sıralanmayanlar
    (devamlı, teslimsiz) "diger" olarak listede yer alır."""
    satis = kaynak.temiz_satis(con)
    tablo = con.execute(f"""
        with
        opt as (select option_id::varchar as o, max(sezon_kodu::varchar) as sezon from urun
                group by 1),
        net as (select u.option_id::varchar as o, sum(s.adet)::double as satis
                from {satis} s join urun u on u.urun_id = s.urun_id group by 1),
        teslim as (select option_id::varchar as o, sum(adet)::double as teslim from siparis
                   where gerceklesen_teslim is not null group by 1)
        select opt.o as option_id, opt.sezon, coalesce(net.satis, 0) as satis, teslim.teslim
        from opt left join net on net.o = opt.o left join teslim on teslim.o = opt.o
    """).fetchdf()
    sirali = tablo["sezon"].ne("DEVAMLI") & (tablo["teslim"] > 0)
    tablo["str"] = np.where(sirali, tablo["satis"] / tablo["teslim"].where(tablo["teslim"] > 0), np.nan)
    esik = tablo.groupby("sezon")["str"].transform(lambda s: s.quantile(HIT_DILIMI))
    hit = sirali & (tablo["str"] >= esik)
    return pd.Series(np.where(hit, "hit", "diger"), index=tablo["option_id"].to_numpy())


def kirilimlar(eslesik: pd.DataFrame, con: duckdb.DuckDBPyConnection,
               tahmin: str = "kayip") -> pd.DataFrame:
    """Her (kirilim, deger) için mağaza × option × hafta seviyesinde WAPE ve yanlılık.

    Sütunlar: `kirilim`, `deger`, `wape`, `yanlilik`, `tahmin`, `karsilanmayan`, `grup`.
    Kırılımlar ve tanımları modül açıklamasında. `eslesik`te `option_id` / `line` yoksa
    `urun` tablosundan türetilir."""
    magaza = _kategorik(eslesik["magaza_id"])
    opt = _sutun(eslesik, "option_id", con)
    temel = pd.DataFrame({
        "magaza_id": magaza, "option_id": opt, "hafta": _hafta(eslesik["tarih"]),
        "t": eslesik[tahmin].to_numpy(dtype=np.float64),
        "g": eslesik["karsilanmayan"].to_numpy(dtype=np.float64),
    }, index=eslesik.index)
    anahtar = ["deger", "magaza_id", "option_id", "hafta"]

    etiket = {
        "durum": lambda: _kategorik(eslesik["durum"]),
        "line": lambda: _sutun(eslesik, "line", con),
        "sure": lambda: _sure_etiketi(eslesik),
        "hit": lambda: _etiketle(_kategorik(pd.Series(opt, index=eslesik.index)), hit_etiketleri(con)),
        "kanal": lambda: _etiketle(magaza, pd.Series(
            ["online" if m == "ONL" else "magaza" for m in magaza.cat.categories.astype(str)],
            index=magaza.cat.categories.astype(str))),
    }
    parcalar = []
    for k in KIRILIMLAR:
        temel["deger"] = etiket[k]()
        top = temel.groupby(anahtar, observed=True, sort=False)[["t", "g"]].sum().reset_index()
        for deger, grup in top.groupby("deger", observed=True, sort=True):
            satir = _olcut(grup)
            satir.update(kirilim=k, deger=str(deger))
            parcalar.append(satir)
    cikti = pd.DataFrame(parcalar)
    return cikti[["kirilim", "deger", "wape", "yanlilik", "tahmin", "karsilanmayan", "grup"]]


# ----------------------------------------------------------------- ayrışım

def ayrisim(eslesik: pd.DataFrame) -> dict:
    """Σ tahmin (`kayip`), Σ karşılanmayan, Σ ikameye giden, Σ kalıcı kayıp (+ Σ `kayip_saf`, varsa)."""
    cikti = {"tahmin": float(eslesik["kayip"].to_numpy(dtype=np.float64).sum())}
    if "kayip_saf" in eslesik.columns:
        cikti["kayip_saf"] = float(eslesik["kayip_saf"].to_numpy(dtype=np.float64).sum())
    for s in _HAKEM_SUTUNLARI:
        cikti[s] = int(eslesik[s].to_numpy().sum(dtype=np.int64))
    return cikti


# ---------------------------------------------------------------- çeşit dışı

def cesit_disi(hakem_df: pd.DataFrame, uygun: pd.DataFrame,
               kayip_keys: pd.DataFrame | None = None) -> dict:
    """Hakemin karşılanmayan talebi, kestirimin kapsamı dışında nerede kaldı.

    `uygun`: uygun hücre-günlerin anahtarları (`tarih`, `magaza_id`, `urun_id`; ~70 M satır
    olabilir). Anahtarlar tek int64'e kodlanır, karşılaştırma DuckDB yarı / ters birleşimleridir
    (pandas birleşimi yok). Dönüş:

        toplam_adet, toplam_satir     hakemin tamamı
        disi_adet, disi_satir         uygun olmayan hücre-günlerde
        disi_pay                      disi_adet / toplam_adet (satır payı: disi_satir_pay)

    `kayip_keys` (Kayıp tablosu ya da anahtarları) verilirse uygun günlerde ama Kayıp
    tablosunda olmayan (stoklu sınıflı gün) karşılanmayan da hesaplanır:
    `stoklu_adet`, `stoklu_satir`, `stoklu_pay` (toplama oranı); ~0 olmalı."""
    cerceveler = [hakem_df[_ANAHTAR], uygun[_ANAHTAR]]
    if kayip_keys is not None:
        cerceveler.append(kayip_keys[_ANAHTAR])
    anahtarlar = _anahtarlar(*cerceveler)
    h = pd.DataFrame({"k": anahtarlar[0], "a": hakem_df["karsilanmayan"].to_numpy(dtype=np.int64)})
    con = duckdb.connect()
    try:
        con.register("h", h)
        con.register("u", pd.DataFrame({"k": anahtarlar[1]}))
        if kayip_keys is not None:
            con.register("kk", pd.DataFrame({"k": anahtarlar[2]}))
        toplam_satir, toplam_adet = con.execute("select count(*), coalesce(sum(a), 0) from h").fetchone()
        disi_satir, disi_adet = con.execute(
            "select count(*), coalesce(sum(a), 0) from h anti join u on h.k = u.k").fetchone()
        cikti = {
            "toplam_adet": int(toplam_adet), "toplam_satir": int(toplam_satir),
            "disi_adet": int(disi_adet), "disi_satir": int(disi_satir),
            "disi_pay": float(disi_adet) / float(toplam_adet) if toplam_adet else float("nan"),
            "disi_satir_pay": float(disi_satir) / float(toplam_satir) if toplam_satir else float("nan"),
        }
        if kayip_keys is not None:
            satir, adet = con.execute(
                "select count(*), coalesce(sum(a), 0) from h semi join u on h.k = u.k "
                "anti join kk on h.k = kk.k").fetchone()
            cikti.update(stoklu_adet=int(adet), stoklu_satir=int(satir),
                         stoklu_pay=float(adet) / float(toplam_adet) if toplam_adet else float("nan"))
    finally:
        con.close()
    return cikti
