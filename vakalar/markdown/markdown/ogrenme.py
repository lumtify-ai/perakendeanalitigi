"""Öğrenme: test sezonunun en erken karar gününden önceki yayımlanan satırlardan, bir kez (spec §3.1–3.2,
§0/9–10). Karar modülüdür: `perakende_veri`'yi ve ölçüm tarafını içe aktarmaz, gizli tablolara dokunmaz
(AST kilidi).

    ogren(con, test_sezonu, bitis, onbellek=None, kaynak_kimligi=None) -> Ogrenilen

`con` yayımlanan v4 tablolarını (tablo adlarıyla) gösteren bir DuckDB bağlantısıdır: yol 0'da
`kaynak.baglan()`, öteki yollarda o yolun yayımlanan biçimi `:memory:`'ye kayıtlı (Ruling R10). Yalnız
tablo adları üstünden SQL kullanılır; dosyaya özgü hiçbir şey yok.

**Bitiş kesimi.** Kullanılan her satır `bitis`ten öncedir. Ortak paketin günlük tablosu
(`hazirlik.gunluk_yaz`) bitişten önceye kesilmiş tablolarla (`kaynak.yayimlanan_tablolar(..., bitis)`)
kurulan bir `:memory:` bağlantısında yazılır: bitiş sabahının stok fotoğrafı ve depo stoğu da görünmez
(tam hafta kuralıyla son eksik hafta düşer; ONL'nin son günü ileri kurulumla). Öteki bütün sorgular
açıkça `< bitis` süzer; özellikler (`ozellikler.ekle`) açık tablolardan (ürün, mağaza, takvim, kampanya,
sezon) ve günlük tablonun günlerine ait fiyat haftalarından okunur.

**Öğrenilenler** (`Ogrenilen`):

    eps_kampanya, eps_markdown, hafta_gunu, ozel_gun, beden_payi
        ortak `carpanlar.ogren` (`hazirlik.carpanlar_yaz`): bitişten önceki bütün stoklu hücre-günler
        (`"*"` havuz). Kampanya ε̂'sı fark-içinde-fark (karar), markdown ε̂'sı içsel (tuzak, rapor).
    eps_saf
        `veri/tests/v4/test_ogrenilebilirlik.py::esneklik_saf`in yayımlanan veri kısmı: brüt satış
        (adet > 0, ham `satis`), çıkıştan önce, outlet mağazaları hariç; haftalık option × mağaza × hat
        adedi, yalnız hattın fiyat oranı > 0 olan haftalar; log(adet) = a + b · log(1 − oran), ε̂ = −b.
    yasam
        aynı tip kapanmış sezonların (aşağıda) Collection'ı, alt kategori × dalga × lansmandan hafta.
        Satış stoklu hücre-günlerde (ortak tablonun `durum = stoklu`su, outlet mağazası hariç, çıkıştan
        önce) `karakter`e (hafta günü × özel gün × (1 − max(md, kampanya))^(−ε̂_kampanya[üst]); yaşam
        hariç) bölünür. Eğri **eşleşmiş hücre zinciriyle** kurulur: w → w+1 bağı, iki haftada da
        stoklu günü olan hücrelerde `Σ m·r(w+1) ÷ Σ m·r(w)` (r = hücrenin o haftaki düzeltilmiş
        günlük hızı, m = iki haftanın stoklu gün sayısının küçüğü). Böylece hızlı satan hücrenin erken
        bitmesi (stoklu hücre bileşiminin kayması) eğriyi düşürmez. Bağ, eşleşmiş stoklu hücre-gün
        `YASAM_ESIGI`'nden azsa üst kategori × dalga bağı, o da yoksa line × dalga bağı, o da yoksa 1
        kullanılır (`kaynak` sütunu). I(0) = 1, I(w+1) = I(w) · bağ(w); eğri oranları verir
        (tahmin I(gelecek hafta) ÷ I(şimdiki hafta) kullanır). Öğrenilen son haftadan sonrası son değer.
        Tablo: `sezon_tipi, duzey, grup, dalga, hafta, carpan, kaynak` (`duzey` alt_kategori /
        ust_kategori / line; `kaynak` o haftaya giren bağın düzeyi).
    kalinti
        aynı tip sezonların Collection'ı: outlet penceresinde ([çıkış, çıkış + 84)) outlet tipi
        mağazaların net cirosu (iade satırları dahil) ÷ çıkıştan 7 gün önceki mağaza (`stok`) + depo
        (`depo_stok`) stoğunun liste değeri; sezonlar birlikte (Σ ÷ Σ). Normal mağazaların çıkıştan
        sonraki satırları yalnız çıkış öncesi satışların iadesidir; outlet cirosu değildir.
    iade
        kanal başına (`magaza` fiziksel, `online` ONL): aynı tip sezonların Collection satışında
        −Σ negatif adet ÷ Σ pozitif adet (outlet mağazaları hariç; mükerrer satır tek).
    islem
        işlem indirimi beklentisi: kampanyasız (`kampanya_id` boş) ve hattının fiyat oranı 0 olan,
        çıkıştan önceki brüt satış satırlarında Σ indirim_tutari ÷ Σ (tutar + indirim_tutari)
        (outlet mağazaları ve bedelsiz satırlar hariç). Motor tam fiyatta rastgele işlem indirimi
        uygular; beklenen ciro bunu `etkin oran`a koyar (spec §0/9).

**Aynı tip kapanmış sezonlar:** `sezon` tablosunda kodu test sezonunun ön ekiyle (SS / AW) başlayan,
test sezonu olmayan, ilk lansmanı verinin ilk satış gününden sonra ve son çıkışı + 84 gün (outlet
penceresinin sonu) bitişten önce olan sezonlar (SS25 ← SS23, SS24; AW24 ← AW23). Yoksa `ValueError`.

**Önbellek.** `onbellek` verilirse günlük tablo (`gunluk.parquet`) ve ortak çarpanlar (`carpanlar.pkl`)
`onbellek/<anahtar>_<test sezonu>/`'nde tutulur; anahtar kaynağın kimliği (yol 0: DuckDB dosyasının adı,
boyutu, değişiklik zamanı; ya da çağıranın `kaynak_kimligi`), test sezonu, bitiş ve ortak paketin
`hazirlik`'in geçişli olarak içe aktardığı bütün modüllerin (günlük tablo, ağaç, kayıp, talep, çarpanlar,
özellikler, stok, kaynak), `markdown.kaynak`'ın, `markdown.sabitler`'in ve bu modülün kendisinin kod
özetidir (`_kod_dosyalari`, `kimlik.json`; Ruling R14: önbellek koşular arasında yeniden kullanılır, eski
kodla kurulmuş girdi sessizce okunmasın). Bellek içi
bağlantıda `kaynak_kimligi` zorunludur. `ONBELLEK_SURUMU` bu modüldeki kesim/pencere kuralı değişince
artırılır. `Ogrenilen.kimlik()` öğrenilen değerlerin içerik özetidir (pickle baytı değil).
"""

import dataclasses
import gc
import hashlib
import json
import pickle
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from perakende_analitik import carpanlar as ortak_carpanlar
from perakende_analitik import agac, hazirlik, kayip, ozellikler, stok, talep
from perakende_analitik import kaynak as ortak_kaynak

from markdown import kaynak, sabitler

ONBELLEK_SURUMU = 1
OUTLET_PENCERE_GUN = 84      # Lumoda'nın outlet penceresi (çıkıştan sonra)
KALINTI_ONCE_GUN = 7         # kalıntının paydası: çıkıştan bu kadar gün önceki stok
YASAM_ESIGI = 200            # bir yaşam bağı için en az eşleşmiş stoklu hücre-gün
YASAM_DUZEYLERI = ("alt_kategori", "ust_kategori", "line")
SEZON_TIPLERI = ("SS", "AW")

# Günlük tablonun kurulduğu bağlantıya kesilerek kopyalanan tablolar (stok.gunluk_* ve özellikler)
_GUNLUK_TABLOLARI = ("satis", "stok", "sevkiyat", "depo_stok", "siparis", "magaza_olay", "fiyat",
                     "magaza", "urun", "sezon", "takvim", "kampanya")
# yaşam düzeltmesi için `karakter`in okuduğu özellikler
_YASAM_OZELLIKLERI = ["hafta_gunu", "tatil", "black_friday", "indirim_baslangici", "oran", "yas_gun",
                      "line", "ust_kategori", "alt_kategori", "kanal"]
# önbellek anahtarına kod özeti giren modüller (bu modülün kendisi `_kod_dosyalari`'nda): `hazirlik` ve
# geçişli içe aktarımları (testle sınanır), vakanın `kaynak`'ı ve `sabitler`'i
_KOD_MODULLERI = (hazirlik, agac, ortak_carpanlar, kayip, ozellikler, stok, talep, ortak_kaynak,
                  kaynak, sabitler)


# ---------------------------------------------------------------------------
# Ogrenilen
# ---------------------------------------------------------------------------


def _kanonik(x):
    """İçerik özeti için JSON'a çevrilebilir kanonik biçim (kayan noktalar `repr`ile tam)."""
    if isinstance(x, pd.DataFrame):
        return {"sutunlar": [str(c) for c in x.columns],
                "turler": [str(t) for t in x.dtypes],
                "csv": x.to_csv(index=False, lineterminator="\n")}
    if isinstance(x, dict):
        return [[_kanonik(k), _kanonik(v)] for k, v in sorted(x.items(), key=lambda kv: repr(kv[0]))]
    if isinstance(x, (list, tuple)):
        return [_kanonik(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return repr(float(x))
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, date):
        return x.isoformat()
    return x


@dataclass(frozen=True)
class Ogrenilen:
    """Bir (yol, test sezonu) için öğrenilenler (modül docstring'i). Değişmez kabul edilir."""

    test_sezonu: str
    bitis: date
    sezonlar: tuple            # aynı tip kapanmış sezonlar (yaşam, kalıntı, iade)
    eps_kampanya: dict         # ust_kategori -> ε̂ ("*" havuz)
    eps_markdown: dict         # ust_kategori -> ε̂ ("*" havuz); yanlı (tuzak)
    eps_saf: float             # saf regresyon ε̂ (yalnız rapor)
    yasam: pd.DataFrame        # sezon_tipi, duzey, grup, dalga, hafta, carpan, kaynak
    hafta_gunu: dict           # (kanal, 0..6) -> çarpan
    ozel_gun: dict             # tür -> çarpan
    beden_payi: pd.DataFrame   # magaza_id, option_id, urun_id, pay ("*" zincir)
    kalinti: float             # çıkışta kalan birimin değeri ÷ liste fiyatı
    iade: dict                 # "magaza" / "online" -> iade payı
    islem: float               # tam fiyatta beklenen işlem indirimi oranı

    def kimlik(self) -> str:
        """Öğrenilen değerlerin içerik özeti (sha256, ilk 16 hane)."""
        icerik = {f.name: _kanonik(getattr(self, f.name)) for f in dataclasses.fields(self)}
        metin = json.dumps(icerik, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(metin.encode("utf-8")).hexdigest()[:16]

    def eps(self, ust_kategori: str, tablo: str = "kampanya") -> float:
        """Üst kategorinin ε̂'sı (`tablo` "kampanya" ya da "markdown"); yoksa havuz `"*"`, o da yoksa 0."""
        t = self.eps_kampanya if tablo == "kampanya" else self.eps_markdown
        return float(t.get(str(ust_kategori), t.get("*", 0.0)))

    def yasam_egrisi(self, alt_kategori: str, ust_kategori: str, dalga: int) -> np.ndarray:
        """Hafta başına yaşam çarpanı (I(0) = 1): alt kategori × dalga eğrisi; yoksa üst kategori ×
        dalga, o da yoksa line × dalga; hiçbiri yoksa düz `[1]`."""
        y = self.yasam
        for duzey, grup in (("alt_kategori", alt_kategori), ("ust_kategori", ust_kategori),
                            ("line", sabitler.LINE)):
            s = y[(y["duzey"] == duzey) & (y["grup"] == str(grup)) & (y["dalga"] == int(dalga))]
            if len(s):
                return s.sort_values("hafta")["carpan"].to_numpy(dtype=float)
        return np.ones(1)


def yasam_orani(egri: np.ndarray, hafta: np.ndarray) -> np.ndarray:
    """Eğrinin `hafta` değerleri: negatif hafta 0'a, öğrenilen son haftanın ötesi son değere."""
    return np.asarray(egri, float)[np.clip(np.asarray(hafta, np.int64), 0, len(egri) - 1)]


# ---------------------------------------------------------------------------
# Sezonlar
# ---------------------------------------------------------------------------


def _veri_basi(con) -> date:
    return pd.Timestamp(con.execute("select min(tarih) from satis").fetchone()[0]).date()


def ayni_tip_sezonlar(con, test_sezonu: str, bitis: date) -> tuple[str, ...]:
    """Aynı tip kapanmış sezonlar, lansman sırasıyla (modül docstring'i)."""
    tip = test_sezonu[:2]
    if tip not in SEZON_TIPLERI:
        raise ValueError(f"sezon kodu {SEZON_TIPLERI}'den biriyle başlamalı: {test_sezonu!r}")
    s = con.execute("""
        select sezon_kodu::varchar as s, min(lansman_tarihi)::date as lansman,
               max(cikis_tarihi)::date as cikis
        from sezon group by 1 order by 2, 1""").df()
    bas = _veri_basi(con)
    son = pd.Timestamp(bitis) - pd.Timedelta(days=OUTLET_PENCERE_GUN)
    uygun = s[s["s"].str.startswith(tip) & (s["s"] != test_sezonu)
              & (pd.to_datetime(s["lansman"]) >= pd.Timestamp(bas))
              & (pd.to_datetime(s["cikis"]) <= son)]
    if uygun.empty:
        raise ValueError(f"{test_sezonu} için {bitis} tarihinde aynı tip kapanmış sezon yok "
                         f"(çıkış + {OUTLET_PENCERE_GUN} gün bitişten önce olmalı)")
    return tuple(uygun["s"])


def _liste(degerler) -> str:
    """SQL `in (...)` listesi (yalnız sezon kodları gibi güvenli dizgeler)."""
    for v in degerler:
        if not str(v).replace("_", "").isalnum():
            raise ValueError(f"geçersiz değer: {v!r}")
    return ", ".join(f"'{v}'" for v in degerler)


# ---------------------------------------------------------------------------
# Günlük tablo ve ortak çarpanlar (önbellekli)
# ---------------------------------------------------------------------------


def _kod_dosyalari() -> tuple[Path, ...]:
    """Önbellek anahtarının kod özetine giren dosyalar: bu modül ve `_KOD_MODULLERI`."""
    return (Path(__file__),) + tuple(Path(m.__file__) for m in _KOD_MODULLERI)


def _kod_ozeti(dosyalar=None) -> str:
    """`ONBELLEK_SURUMU` ve dosya içeriklerinin (satır sonu LF'ye) özeti; varsayılan `_kod_dosyalari()`."""
    h = hashlib.sha256(str(ONBELLEK_SURUMU).encode())
    for yol in (_kod_dosyalari() if dosyalar is None else dosyalar):
        h.update(Path(yol).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()[:16]


def kaynak_kimligi_bul(con) -> str | None:
    """Bağlantının DuckDB dosyasının kimliği (ad, boyut, değişiklik zamanı); bellek içiyse None."""
    satirlar = con.execute("select path from duckdb_databases() "
                           "where not internal and path is not null").fetchall()
    yollar = [Path(p) for (p,) in satirlar if p and p != ":memory:"]
    if not yollar:
        return None
    d = yollar[0].stat()
    return f"{yollar[0].name}:{d.st_size}:{d.st_mtime_ns}"


def _kesik_baglanti(con, bitis: date) -> tuple[duckdb.DuckDBPyConnection, dict]:
    """Bitişten önceye kesilmiş tablolarla `:memory:` bağlantı (kayıtlı DataFrame'ler bağlantı açıkken
    yaşamalı; çağıran kapatır)."""
    t = kaynak.yayimlanan_tablolar(con, _GUNLUK_TABLOLARI, bitis=pd.Timestamp(bitis))
    yeni = duckdb.connect(":memory:")
    for ad, df in t.items():
        yeni.register(ad, df)
    return yeni, t


def _hazirla(con, bitis: date, onbellek: Path | None, anahtar: dict,
             gecici: Path) -> tuple[Path, ortak_carpanlar.Carpanlar]:
    """(günlük tablo yolu, ortak çarpanlar); önbellekte geçerli kayıt varsa yeniden kurmaz."""
    if onbellek is None:
        dizin = gecici
    else:
        ozet = hashlib.sha256(json.dumps(anahtar, sort_keys=True).encode()).hexdigest()[:16]
        dizin = Path(onbellek) / f"{ozet}_{anahtar['test_sezonu']}"
    gunluk, carp, kimlik = dizin / "gunluk.parquet", dizin / "carpanlar.pkl", dizin / "kimlik.json"
    if onbellek is not None and kimlik.exists() and gunluk.exists() and carp.exists():
        if json.loads(kimlik.read_text(encoding="utf-8")) == anahtar:
            with open(carp, "rb") as f:
                return gunluk, pickle.load(f)
    dizin.mkdir(parents=True, exist_ok=True)
    kimlik.unlink(missing_ok=True)
    son = bitis - timedelta(days=1)
    kesik, sakla = _kesik_baglanti(con, bitis)
    try:
        hazirlik.gunluk_yaz(kesik, gunluk, (_veri_basi(kesik), son))
        hazirlik.carpanlar_yaz(kesik, gunluk, carp, son)
    finally:
        kesik.close()
        del sakla
        gc.collect()
    with open(carp, "rb") as f:
        c = pickle.load(f)
    if onbellek is not None:
        kimlik.write_text(json.dumps(anahtar, ensure_ascii=False, sort_keys=True, indent=1),
                          encoding="utf-8")
    return gunluk, c


# ---------------------------------------------------------------------------
# Yaşam eğrisi
# ---------------------------------------------------------------------------


def _urunler(con, sezonlar) -> pd.DataFrame:
    return con.execute(f"""
        select urun_id::varchar as urun_id, option_id::varchar as option_id,
               sezon_kodu::varchar as sezon, dalga::int as dalga,
               ust_kategori::varchar as ust_kategori, alt_kategori::varchar as alt_kategori,
               cikis_tarihi as cikis
        from urun where line::varchar = '{sabitler.LINE}' and sezon_kodu::varchar in ({_liste(sezonlar)})
        order by urun_id""").df()


def yasam_kayitlari(con, gunluk: Path, c: ortak_carpanlar.Carpanlar, sezonlar) -> pd.DataFrame:
    """Hücre × lansmandan hafta başına düzeltilmiş satış ve stoklu gün: `hucre, hafta, A, N, dalga,
    alt_kategori, ust_kategori` (sezon sezon okunur; bellek sınırlı)."""
    urun = _urunler(con, sezonlar)                       # urun_id sırasıyla; satır = ürün kodu
    magazalar = con.execute("select magaza_id::varchar as m, tip::varchar = 'Outlet' as outlet "
                            "from magaza order by 1").df()
    nu = len(urun)
    u_cikis = urun["cikis"].to_numpy(dtype="datetime64[ns]")
    duz = dataclasses.replace(c, yasam=ortak_carpanlar._bos_yasam())   # yaşam çarpanı 1
    parcalar = []
    for sezon in sezonlar:
        u = urun[urun["sezon"] == sezon]
        if u.empty:
            continue
        df = pd.read_parquet(gunluk, columns=["tarih", "magaza_id", "urun_id", "option_id",
                                              "brut_satis", "durum"],
                             filters=[("durum", "in", ["stoklu"]),
                                      ("option_id", "in", sorted(u["option_id"].unique()))])
        # kimlikler kategori kodlarından sabit kodlara (satır başına dizge yok)
        uk = pd.Index(urun["urun_id"]).get_indexer(df["urun_id"].cat.categories.astype(str))[
            df["urun_id"].cat.codes.to_numpy()]
        mk = pd.Index(magazalar["m"]).get_indexer(df["magaza_id"].cat.categories.astype(str))[
            df["magaza_id"].cat.codes.to_numpy()]
        tut = (uk >= 0) & (mk >= 0)
        tut[tut] &= (df["tarih"].to_numpy()[tut] < u_cikis[uk[tut]]) \
            & ~magazalar["outlet"].to_numpy(bool)[mk[tut]]
        df, uk, mk = df[tut].reset_index(drop=True), uk[tut], mk[tut]
        if df.empty:
            continue
        df = ozellikler.ekle(con, df, _YASAM_OZELLIKLERI)
        k = ortak_carpanlar.karakter(df, duz).to_numpy()
        g = pd.DataFrame({"hucre": mk.astype(np.int64) * nu + uk,
                          "hafta": df["yas_gun"].to_numpy().astype(np.int64) // 7,
                          "A": df["brut_satis"].to_numpy(np.float64) / k, "N": 1.0})
        del df, k
        g = g[g["hafta"] >= 0].groupby(["hucre", "hafta"], sort=True)[["A", "N"]].sum().reset_index()
        ui = (g["hucre"].to_numpy() % nu).astype(np.int64)
        for s in ("dalga", "alt_kategori", "ust_kategori"):
            g[s] = urun[s].to_numpy()[ui]
        parcalar.append(g)
        gc.collect()
    if not parcalar:
        return pd.DataFrame(columns=["hucre", "hafta", "A", "N", "dalga", "alt_kategori", "ust_kategori"])
    return pd.concat(parcalar, ignore_index=True)


def yasam_egrileri(kayit: pd.DataFrame, sezon_tipi: str, esik: int = YASAM_ESIGI) -> pd.DataFrame:
    """Eşleşmiş hücre zinciriyle yaşam eğrileri (modül docstring'i, `yasam`)."""
    sutunlar = ["sezon_tipi", "duzey", "grup", "dalga", "hafta", "carpan", "kaynak"]
    if kayit.empty:
        return pd.DataFrame(columns=sutunlar)
    k = kayit.sort_values(["hucre", "hafta"]).reset_index(drop=True)
    ayni = (k["hucre"].to_numpy()[1:] == k["hucre"].to_numpy()[:-1]) \
        & (k["hafta"].to_numpy()[1:] == k["hafta"].to_numpy()[:-1] + 1)
    i = np.flatnonzero(ayni)
    m = np.minimum(k["N"].to_numpy()[i], k["N"].to_numpy()[i + 1])
    bag = pd.DataFrame({
        "hafta": k["hafta"].to_numpy()[i], "dalga": k["dalga"].to_numpy()[i],
        "alt_kategori": k["alt_kategori"].to_numpy()[i], "ust_kategori": k["ust_kategori"].to_numpy()[i],
        "line": sabitler.LINE, "M": m,
        "pay": m * k["A"].to_numpy()[i + 1] / k["N"].to_numpy()[i + 1],
        "payda": m * k["A"].to_numpy()[i] / k["N"].to_numpy()[i],
    })
    baglar = {}
    for duzey in YASAM_DUZEYLERI:
        t = bag.groupby([duzey, "dalga", "hafta"])[["M", "pay", "payda"]].sum()
        ok = (t["M"] >= esik) & (t["pay"] > 0) & (t["payda"] > 0)
        baglar[duzey] = (t["pay"] / t["payda"])[ok].to_dict()

    # alt -> üst eşlemesi (en sık); grup başına eğri boyu: dalganın line bağlarının son haftası + 1
    ust_of = (kayit.groupby("alt_kategori")["ust_kategori"].agg(lambda s: s.value_counts().index[0])
              .to_dict())
    boy = {}
    for (_g, dl, w) in baglar["line"]:
        boy[dl] = max(boy.get(dl, 0), int(w) + 1)

    satirlar = []
    gruplar = {duzey: sorted(kayit[[duzey, "dalga"]].drop_duplicates().itertuples(index=False, name=None))
               for duzey in ("alt_kategori", "ust_kategori")}
    gruplar["line"] = sorted({(sabitler.LINE, int(dl)) for dl in kayit["dalga"].unique()})
    for di, duzey in enumerate(YASAM_DUZEYLERI):
        for grup, dl in gruplar[duzey]:
            dl = int(dl)
            zincir = [(duzey, grup)]
            if duzey == "alt_kategori":
                zincir += [("ust_kategori", ust_of.get(grup)), ("line", sabitler.LINE)]
            elif duzey == "ust_kategori":
                zincir += [("line", sabitler.LINE)]
            deger, I = 1.0, [(0, 1.0, duzey)]
            for w in range(boy.get(dl, 0)):
                bag_w, kaynak_w = 1.0, "yok"
                for z_duzey, z_grup in zincir:
                    v = baglar[z_duzey].get((z_grup, dl, w))
                    if v is not None:
                        bag_w, kaynak_w = float(v), z_duzey
                        break
                deger *= bag_w
                I.append((w + 1, deger, kaynak_w))
            satirlar += [(sezon_tipi, duzey, str(grup), dl, h, v, kz) for h, v, kz in I]
    y = pd.DataFrame(satirlar, columns=sutunlar)
    y["dalga"] = y["dalga"].astype(np.int64)
    y["hafta"] = y["hafta"].astype(np.int64)
    return y


# ---------------------------------------------------------------------------
# Kalıntı, iade, işlem indirimi, saf ε
# ---------------------------------------------------------------------------


def kalinti(con, sezonlar, bitis: date) -> float:
    """Outlet penceresi net cirosu ÷ çıkıştan 7 gün önceki mağaza + depo stoğunun liste değeri."""
    r = con.execute(f"""
        with u as (select urun_id::varchar as u, liste_fiyati as l, cikis_tarihi::date as c
                   from urun where line::varchar = '{sabitler.LINE}'
                     and sezon_kodu::varchar in ({_liste(sezonlar)})),
        o as (select magaza_id::varchar as m from magaza where tip::varchar = 'Outlet'),
        ciro as (select sum(round(x.tutar * 100)::hugeint) as t
                 from (select distinct * from satis where tarih < $b) x
                 join u on u.u = x.urun_id::varchar
                 where x.magaza_id::varchar in (select m from o)
                   and x.tarih::date >= u.c and x.tarih::date < u.c + {OUTLET_PENCERE_GUN}),
        ms as (select sum(k.adet::hugeint * round(u.l * 100)::hugeint) as v
               from stok k join u on u.u = k.urun_id::varchar
               where k.tarih < $b and k.tarih::date = u.c - {KALINTI_ONCE_GUN}
                 and k.magaza_id::varchar <> 'ONL'),
        ds as (select sum(d.adet::hugeint * round(u.l * 100)::hugeint) as v
               from depo_stok d join u on u.u = d.urun_id::varchar
               where d.tarih < $b and d.tarih::date = u.c - {KALINTI_ONCE_GUN})
        select (select t from ciro), (select v from ms), (select v from ds)""",
                    {"b": pd.Timestamp(bitis)}).fetchone()
    ciro, magaza, depo = (int(x or 0) for x in r)       # kuruş; tam sayı toplam (sıradan bağımsız)
    payda = magaza + depo
    if payda <= 0:
        raise ValueError(f"kalıntı: {sezonlar} için çıkıştan önce stok yok")
    return ciro / payda


def iade(con, sezonlar, bitis: date) -> dict[str, float]:
    """Kanal başına iade payı (−Σ negatif adet ÷ Σ pozitif adet)."""
    satirlar = con.execute(f"""
        with u as (select urun_id::varchar as u from urun where line::varchar = '{sabitler.LINE}'
                     and sezon_kodu::varchar in ({_liste(sezonlar)}))
        select case when x.magaza_id::varchar = 'ONL' then 'online' else 'magaza' end as k,
               -coalesce(sum(x.adet) filter (where x.adet < 0), 0) as iade,
               coalesce(sum(x.adet) filter (where x.adet > 0), 0) as satis
        from (select distinct * from satis where tarih < $b) x
        join u on u.u = x.urun_id::varchar
        join magaza m on m.magaza_id::varchar = x.magaza_id::varchar
        where m.tip::varchar <> 'Outlet'
        group by 1 order by 1""", {"b": pd.Timestamp(bitis)}).fetchall()
    sonuc = {k: (float(i) / float(s) if s > 0 else 0.0) for k, i, s in satirlar}
    return {k: sonuc.get(k, 0.0) for k in ("magaza", "online")}


def islem(con, bitis: date) -> float:
    """Tam fiyatta (kampanyasız, fiyat oranı 0) satırlarda indirim payı."""
    r = con.execute("""
        select sum(round(x.indirim_tutari * 100)::hugeint),
               sum(round(x.tutar * 100)::hugeint + round(x.indirim_tutari * 100)::hugeint)
        from (select distinct * from satis where tarih < $b) x
        join urun u on u.urun_id::varchar = x.urun_id::varchar
        join magaza m on m.magaza_id::varchar = x.magaza_id::varchar
        left join (select * from fiyat where hafta_baslangic < $b) f
          on f.option_id::varchar = u.option_id::varchar
         and f.hafta_baslangic = date_trunc('week', x.tarih)
         and f.hat::varchar = case when x.magaza_id::varchar = 'ONL' then 'online' else 'normal' end
        where x.adet > 0 and x.tutar > 0 and x.kampanya_id is null and m.tip::varchar <> 'Outlet'
          and (u.cikis_tarihi is null or x.tarih < u.cikis_tarihi)
          and coalesce(f.indirim_orani, 0) = 0""", {"b": pd.Timestamp(bitis)}).fetchone()
    indirim, brut = (int(x or 0) for x in r)            # kuruş
    return indirim / brut if brut > 0 else 0.0


def eps_saf(con, bitis: date) -> float:
    """Saf regresyon ε̂ (veri testinin `esneklik_saf` tanımı, yayımlanan veri)."""
    h = con.execute("""
        with s as (
            select date_trunc('week', x.tarih) as hafta, u.option_id::varchar as o,
                   x.magaza_id::varchar as m,
                   case when x.magaza_id::varchar = 'ONL' then 'online' else 'normal' end as hat,
                   sum(x.adet) as adet
            from satis x
            join urun u on u.urun_id::varchar = x.urun_id::varchar
            join magaza mg on mg.magaza_id::varchar = x.magaza_id::varchar
            where x.adet > 0 and x.tarih < $b and u.cikis_tarihi is not null
              and x.tarih < u.cikis_tarihi and mg.tip::varchar <> 'Outlet'
            group by 1, 2, 3, 4)
        select s.adet, f.indirim_orani as oran
        from s join fiyat f
          on f.hafta_baslangic = s.hafta and f.option_id::varchar = s.o and f.hat::varchar = s.hat
        where f.indirim_orani > 0 and f.hafta_baslangic < $b
        order by s.hafta, s.o, s.m, s.hat""", {"b": pd.Timestamp(bitis)}).df()
    if len(h) < 2:
        return float("nan")
    return float(-np.polyfit(np.log(1.0 - h["oran"].to_numpy(float)),
                             np.log(h["adet"].to_numpy(float)), 1)[0])


# ---------------------------------------------------------------------------
# Arayüz
# ---------------------------------------------------------------------------


def ogren(con, test_sezonu: str, bitis: date | str, onbellek: Path | None = None,
          kaynak_kimligi: str | None = None) -> Ogrenilen:
    """Test sezonu için öğrenilenler; yalnız `bitis`ten önceki satırlar (modül docstring'i)."""
    bitis = pd.Timestamp(bitis).date()
    sezonlar = ayni_tip_sezonlar(con, test_sezonu, bitis)
    anahtar = None
    if onbellek is not None:
        kimlik = kaynak_kimligi if kaynak_kimligi is not None else kaynak_kimligi_bul(con)
        if kimlik is None:
            raise ValueError("bellek içi bağlantıda önbellek için kaynak_kimligi verilmeli")
        anahtar = {"kaynak": str(kimlik), "test_sezonu": test_sezonu, "bitis": bitis.isoformat(),
                   "kod": _kod_ozeti()}
    with tempfile.TemporaryDirectory(prefix="markdown_ogrenme_") as gecici:
        gunluk, c = _hazirla(con, bitis, onbellek, anahtar or {"test_sezonu": test_sezonu},
                             Path(gecici))
        kayit = yasam_kayitlari(con, gunluk, c, sezonlar)
    yasam = yasam_egrileri(kayit, test_sezonu[:2])
    del kayit
    gc.collect()
    return Ogrenilen(
        test_sezonu=test_sezonu, bitis=bitis, sezonlar=tuple(sezonlar),
        eps_kampanya=dict(c.esneklik_kampanya), eps_markdown=dict(c.esneklik_markdown),
        eps_saf=eps_saf(con, bitis), yasam=yasam,
        hafta_gunu=dict(c.hafta_gunu), ozel_gun=dict(c.ozel_gun),
        beden_payi=c.beden_payi.reset_index(drop=True),
        kalinti=kalinti(con, sezonlar, bitis), iade=iade(con, sezonlar, bitis),
        islem=islem(con, bitis),
    )
