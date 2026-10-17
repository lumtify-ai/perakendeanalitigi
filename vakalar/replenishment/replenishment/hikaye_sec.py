"""1. yazının sahnesi: hikâye seçimi (spec §6, Ruling R31).

    .venv/Scripts/python -m replenishment.oyun hikaye-girdi        # bir kez: koşulardan girdi
    .venv/Scripts/python -m replenishment.hikaye_sec [--hikaye OPTION:SKU] [--adaylar]

KURGU. Ali (İstanbul mağazaları) ve Veli (Anadolu) bir pazartesi aynı ürünün kıt depo
stoğu için çarpışır; Veli önce yazdığı için Ali'nin mağazalarında bedenler biter; Pars tek
bir sabah toplama emriyle "kıt malı en hızlı satan yere gönder" der. Sahne yayımlanan
dünyada (`lumoda_kisitsiz` koşusu = yayımlanan v4, Ruling R4), oyun penceresinde aranır.

BİRİM. Bir (pazartesi, SKU): o sabah Lumoda'nın fiziksel mağaza istekleri ve depodan
giden `replenishment` sevki. Mağaza kümeleri (kişi `kaynak.fiziksel_magazalar`'ın `istanbul`
bayrağından: İstanbul = Ali, değilse Veli):

    ali_gitmeyen   isteyip hiç mal almayan İstanbul mağazaları
    veli_giden     mal alan (sevk > 0) Anadolu mağazaları

HIZ. Stoklu gün hızı = stoklu günlerdeki satış / stoklu gün (günlük tablo `stok.gunluk_magaza`:
satış öncesi stok > 0, yani `durum != 'bos'`; brüt satış). Küme hızı havuzlanır (Σ satış /
Σ stoklu mağaza-günü). `sonra`: pazartesiden başlayan `HIZ_GUN` gün; `once`: önceki
`HIZ_GUN` gün (karar anında görünen geçmiş).

ÖLÇÜTLER (`OLCUTLER`, huni sırası; Ruling R32):

    kesim        Lumoda'nın istekleri depoyu aşmış: istek toplamı > giden toplamı
                 (kısıtsız Lumoda'da fark yalnız depo stoğundan: orantılı kesim)    gevşemez
    iki_bolge    hem İstanbul hem Anadolu istemiş ve yön hikâyeninki: ≥ 1 ali_gitmeyen,
                 ≥ 1 veli_giden                                                     gevşemez
    once_de      kesimden önceki `HIZ_GUN` günde ali_gitmeyen'in stoklu gün hızı
                 veli_giden'inkinden yüksek: Pars'ın kuralı ("kıt malı en hızlı satana")
                 karar anında bilinenle malı Ali'ye gönderirdi                      3. gevşer
    sonra_da     sonraki `HIZ_GUN` günde de ali_gitmeyen daha hızlı (iki yan da en az bir
                 stoklu gün)                                                        2. gevşer
    bedenli      ürün bedenli (beden seti "Standart" değil): "bedenler biter"       1. gevşer

Gevşetme (RPT / blok-transfer `hikaye_sec` kalıbı): sıkı aramada aday yoksa TEK ölçüt
(`GEVSEK` sırasıyla), sonra ikili, üçlü küme gevşer; aday veren ilk küme seçilir. `gevseyen`
seçilen sahnenin tutmadığı ölçütlerdir. Hiçbiri vermezse `LookupError` (huni mesajda).
Sıra gerekçesi: `bedenli` hikâyenin süsü; `sonra_da` dersin teyidi; `once_de` dersin kendisi
(Pars'ın kuralının karar anında kullanabildiği bilgi), en son gevşer.

RAPOR SÜTUNU `kural_iyi` (R31, R32: merdivende değil): o option'da, oyun penceresinde
`demo_kural_a100_kisitsiz` (kural, kısıtsız depo) `lumoda_kisitsiz`'den iyi: bulunabilirlik
yüksek YA DA kayıp oranı düşük (`olcutler.musteri_olcutleri` tanımı; değer girdiden). Bütün
pencerenin option ölçütü kuralın yalın hedef düzeyini (R30) o pazartesinin dağıtım kararıyla
karıştırdığı için ölçüt olmaktan çıktı; hunide ve `hikaye.json`'da basılır.

SIRA (aynı kümede; R32): önce ölçek tercihi (`olcek`: istek toplamı ≥ `OLCEK_ISTEK` = bir koli
ve giden ≥ 1; filtre değil), sonra kanıt (`kanit`): önce ve sonra pencerelerinin Poisson
z'lerinin küçüğü, z = (h_ali − h_veli) / √(max(s_ali, 1) / g_ali² + max(s_veli, 1) / g_veli²)
(h hız, s satış, g stoklu mağaza-günü): hız farkını, her hızın arkasındaki stoklu günü ve
adedi tek sayıda tartar; sonra istek toplamı (büyük önce), pazartesi, SKU.

`--hikaye OPTION:SKU` seçimi zorlar (SKU'nun en az ölçütü tutmayan pazartesisi); CLI'nin
varsayılanı `YURUTUCU_SECIMI`. Alternatif: seçilen option dışarıda bırakılınca merdivenin
ilk sırası.

"BOŞ RAFTA SATIŞ" (`sansur_ornegi`): takvim günü hızı (satış / uygun gün) ile stoklu gün hızı
arasındaki farkın en büyük olduğu hücre (en az `SANSUR_MIN_STOKLU` stoklu gün ve en az bir
boş gün); CLI sahnenin SKU'sunda, oyun penceresinde arar (yoksa option'ında).

SIZINTI. Bu modül karar modülleri listesindedir (`tests/test_sizinti.py`): ne motoru ne
üreteci ne hakemi içe aktarır. Koşulardan gelen her şey (Lumoda istek kaydı, sevkiyat, iki
kolun option ölçütleri) `python -m replenishment.oyun hikaye-girdi`'nin yazdığı
`cikti/hikaye_girdi/`'den veri olarak okunur; `kaynak.json`'daki koşu anahtarları
`cikti/oyun.json`'unkilerle tutmalıdır (`girdi_dogrula`). Satış ve stok yayımlanan DuckDB'den.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from perakende_analitik import stok

from . import kaynak
from .sabitler import CIKTI, OYUN_BAS, OYUN_BIT

HIZ_GUN = 28                     # stoklu gün hızı penceresi (sonraki / önceki dört hafta)
SANSUR_MIN_STOKLU = 7            # boş rafta satış hücresi: en az bir haftalık stoklu gün
KOSULAR = {"lumoda": "lumoda_kisitsiz", "kural": "demo_kural_a100_kisitsiz"}    # R31
GIRDI_DIZINI = CIKTI / "hikaye_girdi"
OYUN_DOSYASI = CIKTI / "oyun.json"
HIKAYE_DOSYASI = CIKTI / "hikaye.json"
DUCKDB_BELLEK = "6GB"

OLCEK_ISTEK = 7                  # ölçek tercihi: istek toplamı ≥ bir koli (standart 7)

OLCUTLER = ("kesim", "iki_bolge", "once_de", "sonra_da", "bedenli")     # R32
GEVSEK = ("bedenli", "sonra_da", "once_de")                 # gevşetme sırası

# Yürütücünün seçimi (kullanıcı tam yetki verdi; okuma kapısında sunulur): R32 merdiveninin ilk
# sırası, birebir, iki pencerede de en güçlü kanıt (görev 11 düzeltme raporu). (option_id, SKU);
# pazartesi SKU'dan seçilir.
YURUTUCU_SECIMI = ("MDL0639-BEJ", "MDL0639-BEJ-XL")


@dataclass
class Hikaye:
    option_id: str
    sku: str
    pazartesi: date
    pazartesi_indeksi: int                 # oyun penceresinin kaçıncı pazartesisi (0'dan)
    ali_magazalari: list[str]              # o sabah isteyen İstanbul mağazaları
    veli_magazalari: list[str]             # o sabah isteyen Anadolu mağazaları
    giden: list[str]                       # mal alan mağazalar
    gitmeyen: list[str]                    # isteyip hiç mal almayan mağazalar
    gevseyen: list[str]                    # sahnenin tutmadığı ölçütler
    alternatif: str | None                 # "OPTION:SKU"


# ------------------------------------------------------------- günlük diziler


def _gun(x) -> pd.Series:
    return pd.to_datetime(x).dt.normalize()


def _kod(s: pd.Series, evren: pd.Index) -> np.ndarray:
    """Kimlik sütunundan `evren` indisi (evren dışı −1); kategorik sütunda kategoriler bir
    kez eşlenir (milyonlarca satır)."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        k = np.append(evren.get_indexer(s.cat.categories.astype(str)), -1)
        return k[s.cat.codes.to_numpy()]          # kod −1 (boş) → son öğe, −1
    return evren.get_indexer(s.astype(str))


def _gunluk_diziler(satis: pd.DataFrame, stoklu: pd.DataFrame, M: pd.Index, U: pd.Index, t0: pd.Timestamp):
    """Uygun hücre-günleri (`stoklu`'nun satırları; evren M × U içinde) için diziler:
    hücre `c` = m·|U| + u, gün (t0'dan), stoklu bayrağı, o günün satışı (`satis` aynı
    hücre-günde toplanır; `stoklu`'da satırı olmayan satış atılır)."""
    C = len(M) * len(U)

    def anahtar(df):
        m, u = _kod(df["magaza_id"], M), _kod(df["urun_id"], U)
        g = (_gun(df["tarih"]) - t0).dt.days.to_numpy(dtype=np.int64)
        var = (m >= 0) & (u >= 0)
        c = m.astype(np.int64) * len(U) + u
        return var, c, g

    var, c, g = anahtar(stoklu)
    st = stoklu["stoklu"].to_numpy(dtype=bool)[var]
    c, g = c[var], g[var]
    svar, sc, sg = anahtar(satis)
    sk = sg[svar] * C + sc[svar]
    sa = pd.Series(satis["adet"].to_numpy(dtype=float)[svar]).groupby(sk).sum()
    i = pd.Index(sa.index).get_indexer(g * C + c)
    adet = np.where(i >= 0, sa.to_numpy()[np.maximum(i, 0)], 0.0)
    return c, g, st, adet


# ------------------------------------------------------------- mağaza tablosu ve özellikler


def magaza_tablosu(istekler: pd.DataFrame, sevkiyat: pd.DataFrame, satis: pd.DataFrame,
                   stoklu: pd.DataFrame, mag: pd.DataFrame, gun: int = HIZ_GUN) -> pd.DataFrame:
    """(pazartesi, SKU, isteyen fiziksel mağaza) başına satır.

    istekler   tarih (pazartesi), magaza_id, urun_id, option_id, beden_seti, istek
    sevkiyat   tarih (çıkış), magaza_id (hedef), urun_id, adet: depodan replenishment
    satis      tarih, magaza_id, urun_id, adet (günlük brüt satış)
    stoklu     tarih, magaza_id, urun_id, stoklu (bool): uygun hücre-günleri
    mag        `kaynak.fiziksel_magazalar` (magaza_id, istanbul)

    Sütunlar: tarih, urun_id, magaza_id, option_id, beden_seti, istek, giden, istanbul,
    stoklu_gun / satis (sonraki `gun` gün, stoklu günler), once_stoklu_gun / once_satis
    (önceki `gun` gün). `mag`'da olmayan (online) mağaza düşer."""
    a = ["tarih", "magaza_id", "urun_id"]
    ist = istekler.loc[istekler["istek"].to_numpy() > 0, a + ["option_id", "beden_seti", "istek"]].copy()
    ist["tarih"] = _gun(ist["tarih"])
    for s in ("magaza_id", "urun_id"):
        ist[s] = ist[s].astype(str)
    ist = ist.groupby(a, as_index=False, sort=False).agg(
        option_id=("option_id", "first"), beden_seti=("beden_seti", "first"), istek=("istek", "sum"))
    sv = pd.DataFrame({"tarih": _gun(sevkiyat["tarih"]), "magaza_id": sevkiyat["magaza_id"].astype(str),
                       "urun_id": sevkiyat["urun_id"].astype(str), "giden": sevkiyat["adet"].to_numpy()})
    sv = sv.groupby(a, as_index=False)["giden"].sum()
    t = ist.merge(sv, on=a, how="left")
    t["giden"] = t["giden"].fillna(0).astype(np.int64)
    t["istek"] = t["istek"].astype(np.int64)
    kisi = mag.assign(magaza_id=mag["magaza_id"].astype(str)).set_index("magaza_id")["istanbul"].astype(bool)
    t = t[t["magaza_id"].isin(kisi.index)].reset_index(drop=True)
    t["istanbul"] = t["magaza_id"].map(kisi).to_numpy(dtype=bool)
    for onek in ("", "once_"):
        t[f"{onek}stoklu_gun"] = 0
        t[f"{onek}satis"] = 0.0
    if t.empty:
        return t
    M, U = pd.Index(sorted(t["magaza_id"].unique())), pd.Index(sorted(t["urun_id"].unique()))
    t0 = t["tarih"].min() - pd.Timedelta(gun, unit="D")
    c, g, st, adet = _gunluk_diziler(satis, stoklu, M, U, t0)
    C = len(M) * len(U)
    tc = M.get_indexer(t["magaza_id"]).astype(np.int64) * len(U) + U.get_indexer(t["urun_id"])
    tg = (t["tarih"] - t0).dt.days.to_numpy(dtype=np.int64)
    sg_s, sa_s = np.zeros(len(t), dtype=np.int64), np.zeros(len(t))
    sg_o, sa_o = np.zeros(len(t), dtype=np.int64), np.zeros(len(t))
    for p in np.unique(tg):
        sec_ = tg == p
        for sg_, sa_, lo, hi in ((sg_s, sa_s, p, p + gun), (sg_o, sa_o, p - gun, p)):
            m = st & (g >= lo) & (g < hi)
            sg_[sec_] = np.bincount(c[m], minlength=C)[tc[sec_]]
            sa_[sec_] = np.bincount(c[m], weights=adet[m], minlength=C)[tc[sec_]]
    t["stoklu_gun"], t["satis"], t["once_stoklu_gun"], t["once_satis"] = sg_s, sa_s, sg_o, sa_o
    return t.sort_values(["tarih", "urun_id", "magaza_id"], ignore_index=True)


def _ilk_pazartesi(bas) -> pd.Timestamp:
    b = pd.Timestamp(bas).normalize()
    return b + pd.Timedelta((7 - b.dayofweek) % 7, unit="D")


def _hiz(satis: pd.Series, gun: pd.Series) -> pd.Series:
    return satis / gun.where(gun > 0)


def ozellikler(tablo: pd.DataFrame, kural_olcut: pd.DataFrame, bas=OYUN_BAS) -> pd.DataFrame:
    """(pazartesi, SKU) başına ölçüt girdileri. kural_olcut: option_id, bulunabilirlik_kural,
    bulunabilirlik_lumoda, kayip_orani_kural, kayip_orani_lumoda (oyun penceresi, R31).

    Sütunlar: istek_toplam, giden_toplam, n_istek, n_ali_istek, n_veli_istek, n_ali_gitmeyen,
    n_veli_giden; ali_gitmeyen ve veli_giden kümelerinin `sg_*` (stoklu mağaza-günü), `sat_*`,
    `hiz_*` (sonra) ve `once_*` karşılıkları; pazartesi_indeksi; kural ölçütleri."""
    t = tablo
    ist = t["istanbul"].to_numpy(dtype=bool)
    gitti = t["giden"].to_numpy() > 0
    ali, veli = ist & ~gitti, ~ist & gitti
    d = pd.DataFrame({
        "tarih": t["tarih"], "urun_id": t["urun_id"], "option_id": t["option_id"], "beden_seti": t["beden_seti"],
        "istek": t["istek"], "giden": t["giden"], "n_istek": 1, "n_ali_istek": ist.astype(int),
        "n_veli_istek": (~ist).astype(int), "n_ali_gitmeyen": ali.astype(int), "n_veli_giden": veli.astype(int)})
    for onek in ("", "once_"):
        for kume, maske in (("ali", ali), ("veli", veli)):
            d[f"{onek}sg_{kume}"] = np.where(maske, t[f"{onek}stoklu_gun"], 0)
            d[f"{onek}sat_{kume}"] = np.where(maske, t[f"{onek}satis"], 0.0)
    toplam = [c for c in d.columns if c not in ("tarih", "urun_id", "option_id", "beden_seti", "istek", "giden")]
    f = d.groupby(["tarih", "urun_id"], as_index=False, sort=True).agg(
        option_id=("option_id", "first"), beden_seti=("beden_seti", "first"),
        istek_toplam=("istek", "sum"), giden_toplam=("giden", "sum"), **{c: (c, "sum") for c in toplam})
    for onek in ("", "once_"):
        for kume in ("ali", "veli"):
            f[f"{onek}hiz_{kume}"] = _hiz(f[f"{onek}sat_{kume}"], f[f"{onek}sg_{kume}"])
    f["pazartesi_indeksi"] = ((f["tarih"] - _ilk_pazartesi(bas)).dt.days // 7).astype(int)
    ko = kural_olcut[["option_id", "bulunabilirlik_kural", "bulunabilirlik_lumoda", "kayip_orani_kural",
                      "kayip_orani_lumoda"]].drop_duplicates("option_id")
    return f.merge(ko, on="option_id", how="left")


# ------------------------------------------------------------- saf ölçüt mantığı


def bayraklar(f: pd.DataFrame) -> pd.DataFrame:
    """Ölçüt bayrakları (bool, `OLCUTLER` sütunları; f ile aynı indeks). Tanımsız değer
    (NaN hız) ölçütü tutmaz."""
    return pd.DataFrame({
        "kesim": f["istek_toplam"] > f["giden_toplam"],
        "iki_bolge": (f["n_ali_gitmeyen"] > 0) & (f["n_veli_giden"] > 0),
        "once_de": f["once_hiz_ali"] > f["once_hiz_veli"],
        "sonra_da": f["hiz_ali"] > f["hiz_veli"],
        "bedenli": f["beden_seti"].fillna("").astype(str) != "Standart",
    }, index=f.index)[list(OLCUTLER)].fillna(False).astype(bool)


def kural_iyi(f: pd.DataFrame) -> pd.Series:
    """Rapor sütunu (merdivende değil; R31, R32): option'da kural bulunabilirliği yüksek ya da
    kayıp oranı düşük. Ölçüt yoksa False."""
    return ((f["bulunabilirlik_kural"] > f["bulunabilirlik_lumoda"])
            | (f["kayip_orani_kural"] < f["kayip_orani_lumoda"])).fillna(False).astype(bool)


def _z(sat_a, sg_a, sat_v, sg_v) -> pd.Series:
    ha, hv = _hiz(sat_a, sg_a), _hiz(sat_v, sg_v)
    se = np.sqrt(np.maximum(sat_a, 1) / sg_a.where(sg_a > 0) ** 2 + np.maximum(sat_v, 1) / sg_v.where(sg_v > 0) ** 2)
    return (ha - hv) / se


def kanit(f: pd.DataFrame) -> pd.DataFrame:
    """Kanıt sütunları: `z_once`, `z_sonra` (Poisson z; modül notu), `kanit` = küçüğü,
    `olcek` (istek toplamı ≥ `OLCEK_ISTEK` ve giden ≥ 1)."""
    zo = _z(f["once_sat_ali"], f["once_sg_ali"], f["once_sat_veli"], f["once_sg_veli"])
    zs = _z(f["sat_ali"], f["sg_ali"], f["sat_veli"], f["sg_veli"])
    return pd.DataFrame({"z_once": zo, "z_sonra": zs, "kanit": np.fmin(zo, zs),
                         "olcek": (f["istek_toplam"] >= OLCEK_ISTEK) & (f["giden_toplam"] >= 1)}, index=f.index)


def sirala(f: pd.DataFrame) -> pd.DataFrame:
    """Aynı ölçüt kümesindeki adayların sırası (modül notu): ölçek, kanıt, istek, pazartesi, SKU."""
    k = kanit(f)
    x = f.assign(_olcek=k["olcek"], _kanit=k["kanit"].fillna(-np.inf))
    x = x.sort_values(["_olcek", "_kanit", "istek_toplam", "tarih", "urun_id"],
                      ascending=[False, False, False, True, True], kind="stable")
    return x.drop(columns=["_olcek", "_kanit"])


def huni(bayrak: pd.DataFrame) -> list[tuple[str, int]]:
    """Ölçütleri sütun sırasıyla ardışık uygulayınca kalan aday sayısı."""
    kalan = pd.Series(True, index=bayrak.index)
    sayi = [("havuz", int(len(bayrak)))]
    for c in bayrak.columns:
        kalan &= bayrak[c]
        sayi.append((c, int(kalan.sum())))
    return sayi


def _kumeler(gevsek: tuple[str, ...]):
    for boyut in range(len(gevsek) + 1):
        yield from combinations(gevsek, boyut)


def merdiven_sayilari(bayrak: pd.DataFrame, gevsek: tuple[str, ...] = GEVSEK) -> list[tuple[tuple[str, ...], int]]:
    """Gevşetme kümesi (sırasıyla) → o kümeyle aday sayısı (merdivenin tamamı)."""
    sonuc = []
    for kume in _kumeler(gevsek):
        gerek = [c for c in bayrak.columns if c not in kume]
        sonuc.append((kume, int(bayrak[gerek].all(axis=1).sum())))
    return sonuc


def merdiven(f: pd.DataFrame, bayrak: pd.DataFrame, gevsek: tuple[str, ...] = GEVSEK,
             sirala_=sirala) -> tuple[pd.DataFrame, list[str]]:
    """Aday veren ilk gevşetme kümesinin adayları (sıralı) ve ilk adayın tutmadığı
    ölçütler. Gevşemeyenler her kümede aranır. Aday yoksa LookupError (huni mesajda)."""
    for kume in _kumeler(tuple(gevsek)):
        gerek = [c for c in bayrak.columns if c not in kume]
        maske = bayrak[gerek].all(axis=1)
        if maske.any():
            aday = sirala_(f[maske])
            ilk = aday.index[0]
            return aday, [c for c in bayrak.columns if not bayrak.loc[ilk, c]]
    raise LookupError("hikaye bulunamadı; ardışık huni: " + ", ".join(f"{a} {n}" for a, n in huni(bayrak)))


def en_yakin(f: pd.DataFrame, bayrak: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Tutmayan ölçüt sayısı az olandan başlayarak en yakın `n` aday (`--adaylar`)."""
    d = sirala(f)
    d = d.assign(tutmayan=(~bayrak.loc[d.index]).sum(axis=1).to_numpy())
    d = d.sort_values("tutmayan", kind="stable").head(n)
    return d.assign(gevseyen=[", ".join(c for c in bayrak.columns if not bayrak.loc[i, c]) for i in d.index])


def secim_ayristir(metin: str) -> tuple[str, str]:
    """`OPTION:SKU` → (option_id, SKU)."""
    parca = metin.split(":")
    if len(parca) != 2 or not all(parca):
        raise ValueError(f"--hikaye OPTION:SKU biçiminde olmalı, verilen: {metin!r}")
    return parca[0], parca[1]


def sec_ozellikten(f: pd.DataFrame, zorla: tuple[str, str] | None = None) -> dict:
    """Saf seçim: {"satir", "gevseyen", "ilk" (merdivenin ilk sırası ya da None),
    "alternatif" ((satır, gevseyen) ya da None)}.

    zorla (option, SKU): SKU'nun en az ölçütü tutmayan pazartesisi (eşitlikte `sirala`);
    gevseyen, onun tutmadığı BÜTÜN ölçütlerdir (gevşemezler dahil). SKU havuzda yoksa
    LookupError, başka option'ınsa ValueError."""
    b = bayraklar(f)
    ilk = None
    try:
        aday, gev = merdiven(f, b)
        ilk = aday.iloc[0]
    except LookupError:
        if zorla is None:
            raise
    if zorla is None:
        satir, gevseyen = ilk, gev
    else:
        option, sku = zorla
        s = f[f["urun_id"] == sku]
        if s.empty:
            raise LookupError(f"zorlanan SKU havuzda yok (oyun penceresinde Lumoda istememiş): {sku}")
        if (s["option_id"] != option).any():
            raise ValueError(f"{sku} {option} option'ının değil: {s['option_id'].iloc[0]}")
        s = sirala(s)
        s = s.assign(_t=(~b.loc[s.index]).sum(axis=1).to_numpy()).sort_values("_t", kind="stable")
        satir = f.loc[s.index[0]]
        gevseyen = [c for c in OLCUTLER if not b.loc[satir.name, c]]
    alternatif = None
    disi = f["option_id"] != satir["option_id"]
    if disi.any():
        try:
            aday, gev = merdiven(f[disi], b[disi])
            alternatif = (aday.iloc[0], gev)
        except LookupError:
            pass
    return {"satir": satir, "gevseyen": gevseyen, "ilk": ilk, "alternatif": alternatif}


def _hikaye(satir: pd.Series, gevseyen: list[str], tablo: pd.DataFrame, alternatif: str | None) -> Hikaye:
    m = tablo[(tablo["tarih"] == satir["tarih"]) & (tablo["urun_id"] == satir["urun_id"])]
    m = m.sort_values("magaza_id")

    def ids(maske) -> list[str]:
        return [str(x) for x in m.loc[maske, "magaza_id"]]

    return Hikaye(
        option_id=str(satir["option_id"]), sku=str(satir["urun_id"]), pazartesi=pd.Timestamp(satir["tarih"]).date(),
        pazartesi_indeksi=int(satir["pazartesi_indeksi"]),
        ali_magazalari=ids(m["istanbul"]), veli_magazalari=ids(~m["istanbul"]),
        giden=ids(m["giden"] > 0), gitmeyen=ids(m["giden"] == 0),
        gevseyen=list(gevseyen), alternatif=alternatif)


def _ad(satir: pd.Series) -> str:
    return f"{satir['option_id']}:{satir['urun_id']}"


def sec(istekler: pd.DataFrame, sevkiyat: pd.DataFrame, satis: pd.DataFrame, stoklu: pd.DataFrame,
        mag: pd.DataFrame, kural_olcut: pd.DataFrame, zorla: tuple[str, str] | None = None, *,
        tablo: pd.DataFrame | None = None, f: pd.DataFrame | None = None) -> Hikaye:
    """Sahneyi seçer (girdiler `magaza_tablosu` / `ozellikler`'deki gibi). zorla verilmezse
    merdivenin ilk sırası. `tablo` / `f` önceden kurulduysa yeniden kurulmaz."""
    if tablo is None:
        tablo = magaza_tablosu(istekler, sevkiyat, satis, stoklu, mag)
    if f is None:
        f = ozellikler(tablo, kural_olcut)
    s = sec_ozellikten(f, zorla)
    alt = _ad(s["alternatif"][0]) if s["alternatif"] is not None else None
    return _hikaye(s["satir"], s["gevseyen"], tablo, alt)


# ------------------------------------------------------------- boş rafta satış


def hucre_hizlari(satis: pd.DataFrame, stoklu: pd.DataFrame) -> pd.DataFrame:
    """Hücre (magaza_id, urun_id) başına: takvim_gun (uygun gün = `stoklu` satırı),
    stoklu_gun, satis (bütün uygun günler), satis_stoklu, hiz_takvim, hiz_stoklu, fark
    (stoklu − takvim)."""
    M = pd.Index(sorted(stoklu["magaza_id"].astype(str).unique()))
    U = pd.Index(sorted(stoklu["urun_id"].astype(str).unique()))
    t0 = _gun(stoklu["tarih"]).min()
    c, _, st, adet = _gunluk_diziler(satis, stoklu, M, U, t0)
    C = len(M) * len(U)
    takvim = np.bincount(c, minlength=C)
    h = pd.DataFrame({
        "magaza_id": np.repeat(M.to_numpy(), len(U)), "urun_id": np.tile(U.to_numpy(), len(M)),
        "takvim_gun": takvim, "stoklu_gun": np.bincount(c[st], minlength=C),
        "satis": np.bincount(c, weights=adet, minlength=C), "satis_stoklu": np.bincount(c[st], weights=adet[st], minlength=C),
    })[takvim > 0].reset_index(drop=True)
    h["hiz_takvim"] = h["satis"] / h["takvim_gun"]
    h["hiz_stoklu"] = _hiz(h["satis_stoklu"], h["stoklu_gun"])
    h["fark"] = h["hiz_stoklu"] - h["hiz_takvim"]
    return h


def sansur_ornegi(satis: pd.DataFrame, stoklu: pd.DataFrame,
                  min_stoklu: int = SANSUR_MIN_STOKLU) -> tuple[str, str]:
    """1. yazının "boş rafta satış" tuzağı: takvim günü hızıyla stoklu gün hızı arasındaki
    fark en büyük hücre (en az `min_stoklu` stoklu gün ve en az bir boş gün; eşitlikte
    mağaza, SKU). Aday yoksa LookupError."""
    h = hucre_hizlari(satis, stoklu)
    h = h[(h["stoklu_gun"] >= min_stoklu) & (h["takvim_gun"] > h["stoklu_gun"])]
    if h.empty:
        raise LookupError("boş rafta satış hücresi yok (yeterli stoklu günü ve boş günü olan hücre yok)")
    r = h.sort_values(["fark", "magaza_id", "urun_id"], ascending=[False, True, True], kind="stable").iloc[0]
    return str(r["magaza_id"]), str(r["urun_id"])


# ------------------------------------------------------------- girdi


def girdi_dogrula(kaynak_json: dict, oyun_json: dict, kosular: dict = KOSULAR) -> None:
    """Girdinin koşuları (`kaynak.json`: rol → {ad, anahtar}) `kosular`'daki adlar (R31) olmalı ve
    anahtarları `oyun.json`'daki ölçülmüş koşularınkiyle aynı olmalı."""
    kayit = oyun_json.get("kosular", {})
    girdi = kaynak_json.get("kosular", {})
    for rol, ad in kosular.items():
        beklenen = kayit.get(ad, {}).get("anahtar")
        if beklenen is None:
            raise RuntimeError(f"{ad} oyun.json'da yok: önce `python -m replenishment.oyun izgara`")
        e = girdi.get(rol)
        if e is None or e.get("ad") != ad:
            raise RuntimeError(f"hikâye girdisinin {rol} koşusu {ad} değil (R31): {e}")
        if e.get("anahtar") != beklenen:
            raise RuntimeError(f"hikâye girdisi bayat: {ad} anahtarı oyun.json'dakinden farklı; "
                               "`python -m replenishment.oyun hikaye-girdi` ile yeniden kurun")


def girdi_oku(dizin: Path = GIRDI_DIZINI, oyun_yolu: Path = OYUN_DOSYASI, kosular: dict = KOSULAR) -> dict:
    """`hikaye-girdi` çıktısı: {"istekler", "sevkiyat", "kural_olcut" (DataFrame), "kaynak" (dict)}."""
    dizin = Path(dizin)
    if not (dizin / "kaynak.json").exists():
        raise FileNotFoundError(f"hikâye girdisi yok ({dizin}): önce `python -m replenishment.oyun hikaye-girdi`")
    kaynak_json = json.loads((dizin / "kaynak.json").read_text(encoding="utf-8"))
    girdi_dogrula(kaynak_json, json.loads(Path(oyun_yolu).read_text(encoding="utf-8")), kosular)
    sonuc = {ad: pd.read_parquet(dizin / f"{ad}.parquet") for ad in ("istekler", "sevkiyat", "kural_olcut")}
    sonuc["kaynak"] = kaynak_json
    return sonuc


# ------------------------------------------------------------- ozet (yazının sayıları)


def _sayi(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    if isinstance(x, (np.integer, int)) and not isinstance(x, bool):
        return int(x)
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return None if np.isnan(v) else (int(v) if v.is_integer() and abs(v) < 2**53 else v)
    return x


def _json_degeri(x):
    if isinstance(x, (np.integer, np.floating)):
        return _sayi(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, (date, pd.Timestamp)):
        return x.isoformat()
    raise TypeError(type(x).__name__)


def _hizlar(sg, sat) -> dict:
    return {"stoklu_gun": _sayi(sg), "satis": _sayi(sat), "hiz": (float(sat) / float(sg)) if sg else None}


def ozet(h: Hikaye, tablo: pd.DataFrame, f: pd.DataFrame, mag: pd.DataFrame, urunler: pd.DataFrame) -> dict:
    """Sahnenin yazıda alıntılanabilecek sayıları (düz Python türleri). urunler: urun_id,
    option_id, model_adi, renk, alt_kategori, line, beden, lansman_tarihi."""
    p = pd.Timestamp(h.pazartesi)
    r = f[(f["tarih"] == p) & (f["urun_id"] == h.sku)].iloc[0]
    u = urunler.assign(urun_id=urunler["urun_id"].astype(str)).set_index("urun_id").loc[h.sku]
    m = tablo[(tablo["tarih"] == p) & (tablo["urun_id"] == h.sku)].sort_values("magaza_id")
    bilgi = mag.assign(magaza_id=mag["magaza_id"].astype(str)).set_index("magaza_id")
    lansman = pd.Timestamp(u["lansman_tarihi"])
    b = bayraklar(f.loc[[r.name]]).iloc[0]
    k = kanit(f.loc[[r.name]]).iloc[0]
    magazalar = [{
        "magaza_id": x["magaza_id"], "ad": bilgi.loc[x["magaza_id"], "ad"], "sehir": bilgi.loc[x["magaza_id"], "sehir"],
        "kisi": "Ali" if x["istanbul"] else "Veli", "istek": _sayi(x["istek"]), "giden": _sayi(x["giden"]),
        "sonra": _hizlar(x["stoklu_gun"], x["satis"]), "once": _hizlar(x["once_stoklu_gun"], x["once_satis"]),
    } for _, x in m.iterrows()]

    def grup(maske) -> dict:
        g = m[maske]
        return {"magazalar": list(g["magaza_id"]), **_hizlar(g["stoklu_gun"].sum(), g["satis"].sum()),
                "once": _hizlar(g["once_stoklu_gun"].sum(), g["once_satis"].sum())}

    kural = {k: _sayi(r[k]) for k in ("bulunabilirlik_kural", "bulunabilirlik_lumoda", "kayip_orani_kural",
                                      "kayip_orani_lumoda")}
    kural["iyi"] = [ad for ad, iyi in (
        ("bulunabilirlik", r["bulunabilirlik_kural"] > r["bulunabilirlik_lumoda"]),
        ("kayip_orani", r["kayip_orani_kural"] < r["kayip_orani_lumoda"])) if bool(iyi)]
    return {
        "option_id": h.option_id, "sku": h.sku, "model_adi": u["model_adi"], "renk": u["renk"],
        "alt_kategori": u["alt_kategori"], "line": u["line"], "beden": u["beden"], "beden_seti": r["beden_seti"],
        "lansman": lansman.date().isoformat(), "pazartesi": p.date().isoformat(),
        "pazartesi_indeksi": h.pazartesi_indeksi, "pazartesi_sirasi": h.pazartesi_indeksi + 1,
        "lansmandan_gun": int((p - lansman).days), "hiz_penceresi_gun": HIZ_GUN,
        "istek_toplam": _sayi(r["istek_toplam"]), "giden_toplam": _sayi(r["giden_toplam"]),
        "n_istek_magaza": _sayi(r["n_istek"]), "n_ali_istek": _sayi(r["n_ali_istek"]),
        "n_veli_istek": _sayi(r["n_veli_istek"]),
        "ali_magazalari": h.ali_magazalari, "veli_magazalari": h.veli_magazalari,
        "giden": h.giden, "gitmeyen": h.gitmeyen,
        "olcutler": {c: bool(b[c]) for c in OLCUTLER}, "gevseyen": h.gevseyen, "alternatif": h.alternatif,
        "kural_iyi": bool(kural_iyi(f.loc[[r.name]]).iloc[0]),
        "kanit": {"z_once": _sayi(k["z_once"]), "z_sonra": _sayi(k["z_sonra"]), "kanit": _sayi(k["kanit"]),
                  "olcek": bool(k["olcek"])},
        "gruplar": {"ali_gitmeyen": grup(m["istanbul"] & (m["giden"] == 0)),
                    "veli_giden": grup(~m["istanbul"] & (m["giden"] > 0))},
        "kural_olcut": kural, "magazalar": magazalar,
    }


# ------------------------------------------------------------- CLI


def _sansur(satis: pd.DataFrame, stoklu: pd.DataFrame, h: Hikaye, urunler: pd.DataFrame, mag: pd.DataFrame) -> dict:
    """Sahnenin SKU'sunda (yoksa option'ında), oyun penceresinde boş rafta satış hücresi."""
    pen_st = (_gun(stoklu["tarih"]) >= pd.Timestamp(OYUN_BAS)) & (_gun(stoklu["tarih"]) <= pd.Timestamp(OYUN_BIT))
    pen_sa = (_gun(satis["tarih"]) >= pd.Timestamp(OYUN_BAS)) & (_gun(satis["tarih"]) <= pd.Timestamp(OYUN_BIT))
    skular = urunler.loc[urunler["option_id"] == h.option_id, "urun_id"].astype(str)
    for kapsam, kume in (("sku", {h.sku}), ("option", set(skular))):
        st = stoklu[pen_st & stoklu["urun_id"].astype(str).isin(kume)]
        sa = satis[pen_sa & satis["urun_id"].astype(str).isin(kume)]
        try:
            magaza, sku = sansur_ornegi(sa, st)
        except LookupError:
            continue
        hz = hucre_hizlari(sa, st)
        x = hz[(hz["magaza_id"] == magaza) & (hz["urun_id"] == sku)].iloc[0]
        ad = mag.assign(magaza_id=mag["magaza_id"].astype(str)).set_index("magaza_id")
        return {"kapsam": kapsam, "magaza_id": magaza, "ad": ad.loc[magaza, "ad"], "sehir": ad.loc[magaza, "sehir"],
                "sku": sku, **{k: _sayi(x[k]) for k in ("takvim_gun", "stoklu_gun", "satis", "satis_stoklu",
                                                       "hiz_takvim", "hiz_stoklu", "fark")}}
    return {"kapsam": None}


def main(argv: list[str] | None = None) -> dict:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = argparse.ArgumentParser(prog="python -m replenishment.hikaye_sec", description=__doc__.split("\n")[0])
    a.add_argument("--hikaye", metavar="OPTION:SKU", default=None,
                   help=f"seçimi zorlar (varsayılan YURUTUCU_SECIMI {YURUTUCU_SECIMI})")
    a.add_argument("--adaylar", action="store_true", help="ölçüt merdivenine en yakın sahneleri listele")
    a.add_argument("--girdi", type=Path, default=GIRDI_DIZINI)
    a.add_argument("--oyun", type=Path, default=OYUN_DOSYASI)
    a.add_argument("--db", type=Path, default=None, help="v4 DuckDB (varsayılan: ortak yol)")
    a.add_argument("--cikti", type=Path, default=HIKAYE_DOSYASI)
    args = a.parse_args(argv)
    zorla = secim_ayristir(args.hikaye) if args.hikaye else YURUTUCU_SECIMI

    g = girdi_oku(args.girdi, args.oyun)
    con = kaynak.baglan(args.db)
    con.execute(f"SET memory_limit='{DUCKDB_BELLEK}'")
    con.execute("SET enable_progress_bar=false")
    mag = kaynak.fiziksel_magazalar(con)
    urunler = con.execute("""
        select urun_id::varchar as urun_id, option_id::varchar as option_id, model_adi, renk, alt_kategori,
               line::varchar as line, beden, beden_seti, lansman_tarihi from urun""").df()
    istekler = g["istekler"].merge(urunler[["urun_id", "option_id", "beden_seti"]], on="urun_id", how="left")
    gl = stok.gunluk_magaza(con, OYUN_BAS - timedelta(days=HIZ_GUN), OYUN_BIT)
    satis = gl[["tarih", "magaza_id", "urun_id"]].assign(adet=gl["brut_satis"].to_numpy())
    stoklu = gl[["tarih", "magaza_id", "urun_id"]].assign(stoklu=(gl["durum"].astype(str) != "bos").to_numpy())
    del gl

    tablo = magaza_tablosu(istekler, g["sevkiyat"], satis, stoklu, mag)
    f = ozellikler(tablo, g["kural_olcut"])
    b = bayraklar(f)
    ki = kural_iyi(f)
    funnel = huni(b)
    kumeler = merdiven_sayilari(b)
    tekil = {c: int(b[c].sum()) for c in OLCUTLER} | {"kural_iyi (rapor)": int(ki.sum())}
    birebir = b.all(axis=1)
    rapor = {"birebir": int(birebir.sum()), "birebir_kural_iyi": int((birebir & ki).sum()),
             "birebir_olcek": int((birebir & kanit(f)["olcek"]).sum())}
    print(f"merdiven huni: {funnel} + kural_iyi (rapor) {rapor['birebir_kural_iyi']}")
    print(f"tekil: {tekil}")
    print(f"birebir adaylar: {rapor}")
    print("gevşetme kümeleri: " + ", ".join(f"{'+'.join(k) or 'sıkı'} {n}" for k, n in kumeler))
    if args.adaylar:
        kol = ["tarih", "urun_id", "tutmayan", "gevseyen", "istek_toplam", "giden_toplam", "n_ali_gitmeyen",
               "n_veli_giden", "once_sg_ali", "once_sat_ali", "once_sg_veli", "once_sat_veli", "sg_ali", "sat_ali",
               "sg_veli", "sat_veli", "z_once", "z_sonra", "kural_iyi"]
        x = f[b["kesim"] & b["iki_bolge"]]
        x = en_yakin(x, b).join(kanit(x)[["z_once", "z_sonra"]]).assign(kural_iyi=ki)
        with pd.option_context("display.width", 300, "display.max_columns", 30):
            print(x[kol].to_string(index=False))

    s = sec_ozellikten(f, zorla)
    alt = s["alternatif"]
    h = _hikaye(s["satir"], s["gevseyen"], tablo, _ad(alt[0]) if alt else None)
    ilk = _ad(s["ilk"]) if s["ilk"] is not None else None
    o = {
        "sahne": ozet(h, tablo, f, mag, urunler),
        "alternatif": ozet(_hikaye(alt[0], alt[1], tablo, None), tablo, f, mag, urunler) if alt else None,
        "secim": {"yurutucu": ":".join(YURUTUCU_SECIMI), "zorla": args.hikaye, "merdiven_ilk": ilk,
                  "merdiven_ilk_pazartesi": s["ilk"]["tarih"].date().isoformat() if s["ilk"] is not None else None},
        "merdiven": {"olcutler": list(OLCUTLER), "gevsetme_sirasi": list(GEVSEK), "huni": funnel, "tekil": tekil,
                     "rapor": rapor, "olcek_istek": OLCEK_ISTEK,
                     "kumeler": [{"gevseyen": list(k), "aday": n} for k, n in kumeler]},
        "sansur": _sansur(satis, stoklu, h, urunler, mag),
        "kaynak": g["kaynak"],
    }
    Path(args.cikti).parent.mkdir(parents=True, exist_ok=True)
    Path(args.cikti).write_text(json.dumps(o, ensure_ascii=False, indent=1, default=_json_degeri), encoding="utf-8")
    sh = o["sahne"]
    print(f"\nmerdivenin ilk sırası: {ilk}  (seçim {h.option_id}:{h.sku}, alternatif {h.alternatif})")
    print(f"sahne: {sh['model_adi']} {sh['renk']} {sh['beden']} ({sh['alt_kategori']}, {sh['line']}); "
          f"{sh['pazartesi_sirasi']}. pazartesi, lansmandan {sh['lansmandan_gun']} gün; istek {sh['istek_toplam']}, "
          f"giden {sh['giden_toplam']}; gevşeyen {h.gevseyen or 'yok'}")
    for k in ("ali_gitmeyen", "veli_giden"):
        gr = sh["gruplar"][k]
        print(f"  {k}: {gr['magazalar']} stoklu gün {gr['stoklu_gun']}, satış {gr['satis']}, hız {gr['hiz']}; "
              f"önce hız {gr['once']['hiz']}")
    print(f"  kanıt: {sh['kanit']}")
    print(f"  kural ölçütü (rapor): {sh['kural_olcut']}")
    print(f"  sansür: {o['sansur']}")
    print(f"yazıldı: {args.cikti}")
    return o


if __name__ == "__main__":
    main()
