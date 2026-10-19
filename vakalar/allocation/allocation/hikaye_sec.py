"""Hikâye seçimi (spec §6): 1. yazının ("Plan Böyle Diyor") sahnesi, yayımlanan veriden.

    .venv/Scripts/python -m allocation.hikaye_sec                   # cikti/hikaye.json
    .venv/Scripts/python -m allocation.hikaye_sec --hikaye MDL0702-BRD --adaylar

Sahne: oyun sezonunun (SS25) `LINE` (Collection) option'larından birinde Lumoda'nın plan payı
kuralı malı bir mağazaya yığmış, o mağaza neredeyse satmamış ("taşan"); aynı option'dan az alan
başka bir mağaza malı hızla bitirmiş ("biten"); ikisi de Veli'nin bölgesinde ve en iyi kol
(`cikti/secim.json`) yalnız karar öncesi bilgiyle taşana belirgin biçimde daha az, bitene daha
çok göndermiş.

**Merdiven** (`MERDIVEN`; her basamak bir öncekini bir ölçüt gevşeterek genişletir):

    1  yoğunlaşma   taşan, option'ın fiziksel mağazalara giden ilk dağıtımında en büyük adedi
                    almış (`pay_sirasi` 1) ve varıştan itibaren 28 günde ilk adedinin ≤ %10'unu
                    satmış (`tasan_satis`)
    2  biten        aynı option'da başka bir mağaza küçük pay almış (adedi option'ın fiziksel
                    mağaza ortalamasını ve taşanınkini aşmıyor) ve varıştan itibaren 14 günde
                    ilk adedinin ≥ %80'ini satmış
    3  Veli         ikisi de İstanbul dışı fiziksel mağaza (outlet ve online değil;
                    `kaynak.Harita.magaza_istanbul` / `magaza_fiziksel`'in kuralı, `magaza_tablosu`)
    4  plan         taşanın `magaza_plan`'daki satış hedefi sırası (oyun sezonu × option'ın üst
                    kategorisi, fiziksel mağazalar arasında, 1 = en büyük) ≤ 3 (`plan_sirasi`)
    5  kol          en iyi kol taşana ≤ %50'sini (`kol_orani`), bitene Lumoda'dan çok göndermiş

Gevşetme sırası (spec §6, brief): 1'in eşikleri (28 günlük satış ≤ %20, sonra payda ilk 3) → 4
düşer → 5'in oranı ≤ %70. 2 ve 3 gevşemez; 5 hiçbir basamakta düşmez (kol oranı < 1).
Hiçbir basamakta sahne yoksa `HikayeBulunamadi`.

"Tükenmiş" ayrı sınanmaz: 14 günde ilk adedin ≥ %80'ini satmak, ilk adedi bitirmeyi de kapsar
(stok yeniden kurulmaz; `olcutler`'in "hızlı biten" tanımıyla aynı pencere ve eşik).

**Sıralama.** Bir basamakta option başına en iyi çift: taşanda oturan adet (ilk adet − 28 günlük
satış) büyük olan, eşitlikte bitenin 14 günlük satış oranı yüksek olan, sonra kimlikler. Option'lar
aynı anahtarla sıralanır; sahne ilk basamağın ilk option'ıdır, `alternatif` merdivende ondan sonra
gelen ilk başka option (aynı ya da sonraki basamak). `zorla` (CLI `--hikaye`) o option'ı tuttuğu
ilk basamakta seçer.

**Adetler.** "İlk adet" option'ın mağazaya varan ilk dağıtımıdır (`sevkiyat` tip `ilk_dagitim`,
SKU'lar toplanır; varış = ilk varış günü), satışlar pozitif `satis` satırları (iade düşülmez),
`olcutler`'in oturan / hızlı biten pencereleriyle (varış günü dahil, [0, 28) ve [0, 14)).
Lumoda'da motor kırptığı için varan adet kararından az olabilir: hikâye mağazada duranı anlatır.
Kolun "karar kaydı" kolun koşusunun `sevkiyat`'ındaki ilk dağıtımdır: kolda kayıt ↔ `sevkiyat`
birebirdir (motor kırpmaz, `olcutler.hesapla` korunumu; mağaza kimliğiyle, dünyasız okunur).

Bu modül karar listesindedir (`tests/test_sizinti.py`): `motor`'u, `perakende_veri`'yi ve hakemi
içe aktarmaz; seçim işlevleri DataFrame alır. İnce CLI önbelleğe alınmış koşuları
(`cikti/oyun.json`'un anahtarıyla `cikti/kosular/<ad>_<anahtar[:20]>`, adlandırma
`motor._dizin`'le aynı, testli) Parquet'ten doğrudan okur; `oyun` da motoru içe aktardığı için
onun üstünden okunamaz. Gizli gerçek okunmaz.
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from allocation import sabitler

TASAN_GUN = 28           # taşanın satış penceresi (varıştan)
BITEN_GUN = 14           # bitenin satış penceresi
BITEN_PAY = 0.80         # bitenin 14 günde sattığı en az pay
_EPS = 1e-9


@dataclass(frozen=True)
class Basamak:
    """Merdivenin bir basamağı: eşikler ve o basamağa dek gevşeyen ölçütler."""

    gevseyen: tuple[str, ...]
    pay_sirasi: int              # taşanın option içindeki adet sırası en çok
    tasan_satis: float           # taşanın 28 günlük satışı ≤ bu × ilk adet
    plan_sirasi: int | None      # taşanın plan sırası en çok; None: ölçüt düştü
    kol_orani: float             # kol taşana ≤ bu × Lumoda'nın adedi


_S20, _P3, _PL, _K70 = ("1: 28 günde satış ≤ %20", "1: payda ilk 3", "4: plan sırası düştü",
                        "5: kol taşana ≤ %70")
MERDIVEN = (
    Basamak((), 1, 0.10, 3, 0.50),
    Basamak((_S20,), 1, 0.20, 3, 0.50),
    Basamak((_S20, _P3), 3, 0.20, 3, 0.50),
    Basamak((_S20, _P3, _PL), 3, 0.20, None, 0.50),
    Basamak((_S20, _P3, _PL, _K70), 3, 0.20, None, 0.70),
)


@dataclass(frozen=True)
class Hikaye:
    option_id: str
    ad: str
    tasan_magaza: str
    biten_magaza: str
    tasan_ilk_adet: int
    tasan_satis_28: int
    biten_ilk_adet: int
    biten_satis_14: int
    tasan_plan_sirasi: int       # 0: taşanın o üst kategoride planı yok
    kol_tasan_adet: int
    kol_biten_adet: int
    gevseyen: list[str]
    alternatif: str | None


class HikayeBulunamadi(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Yardımcı tablolar (yayımlanan biçimden)
# ---------------------------------------------------------------------------


def _oyun_urunleri(urun: pd.DataFrame, sezon: str, line: str = sabitler.LINE) -> pd.DataFrame:
    u = urun[(urun["sezon_kodu"].astype(str) == sezon).to_numpy() & (urun["line"].astype(str) == line).to_numpy()]
    return pd.DataFrame({"urun_id": u["urun_id"].astype(str).to_numpy(),
                         "option_id": u["option_id"].astype(str).to_numpy(),
                         "ad": (u["model_adi"].astype(str) + " " + u["renk"].astype(str)).to_numpy(),
                         "ust_kategori": u["ust_kategori"].astype(str).to_numpy()})


def ilk_tablosu(sevkiyat: pd.DataFrame, urun: pd.DataFrame, sezon: str = sabitler.OYUN_SEZONU) -> pd.DataFrame:
    """İlk dağıtımın (option, mağaza) başına varan adedi ve ilk varış günü (`sezon`un `LINE`
    option'ları): option_id, ad, ust_kategori, magaza_id, adet, varis."""
    sv = sevkiyat[(sevkiyat["tip"].astype(str) == "ilk_dagitim").to_numpy()]
    sv = pd.DataFrame({"urun_id": sv["urun_id"].astype(str).to_numpy(),
                       "magaza_id": sv["hedef"].astype(str).to_numpy(),
                       "adet": sv["adet"].to_numpy(dtype=np.int64),
                       "varis": pd.to_datetime(sv["varis_tarihi"]).to_numpy()})
    sv = sv.merge(_oyun_urunleri(urun, sezon), on="urun_id")
    t = sv.groupby(["option_id", "ad", "ust_kategori", "magaza_id"], as_index=False).agg(
        adet=("adet", "sum"), varis=("varis", "min"))
    return t.sort_values(["option_id", "magaza_id"], ignore_index=True)


def satis_tablosu(satis: pd.DataFrame, urun: pd.DataFrame, sezon: str = sabitler.OYUN_SEZONU) -> pd.DataFrame:
    """`satis` satırları `sezon`un `LINE` option'larına eşlenmiş: option_id, magaza_id, tarih, adet."""
    s = pd.DataFrame({"urun_id": satis["urun_id"].astype(str).to_numpy(),
                      "magaza_id": satis["magaza_id"].astype(str).to_numpy(),
                      "tarih": pd.to_datetime(satis["tarih"]).to_numpy(),
                      "adet": satis["adet"].to_numpy(dtype=np.int64)})
    s = s.merge(_oyun_urunleri(urun, sezon)[["urun_id", "option_id"]], on="urun_id")
    return s[["option_id", "magaza_id", "tarih", "adet"]].reset_index(drop=True)


def magaza_tablosu(mag: pd.DataFrame) -> pd.DataFrame:
    """magaza_id, ad, istanbul, fiziksel, veli (`mag` satır sırasıyla). Kural `kaynak.harita_kur`'un:
    İstanbul = şehir İstanbul; fiziksel = tip Online ve Outlet değil; Veli = fiziksel ve İstanbul
    dışı (testte haritayla birebir)."""
    ist = (mag["sehir"].astype(str) == "İstanbul").to_numpy(dtype=bool)
    fiz = ~np.isin(mag["tip"].astype(str).to_numpy(), ("Online", "Outlet"))
    return pd.DataFrame({"magaza_id": mag["magaza_id"].astype(str).to_numpy(),
                         "ad": mag["ad"].astype(str).to_numpy(), "istanbul": ist, "fiziksel": fiz,
                         "veli": fiz & ~ist})


def plan_sirasi(plan: pd.DataFrame, mag: pd.DataFrame, sezon: str = sabitler.OYUN_SEZONU) -> pd.DataFrame:
    """Mağazanın `sezon` × üst kategori satış hedefinin fiziksel mağazalar arasındaki sırası
    (1 = en büyük, eşitlikte en küçük sıra): magaza_id, ust_kategori, sira."""
    m = magaza_tablosu(mag)
    fiz = set(m.loc[m["fiziksel"], "magaza_id"])
    p = pd.DataFrame({"sezon_kodu": plan["sezon_kodu"].astype(str).to_numpy(),
                      "magaza_id": plan["magaza_id"].astype(str).to_numpy(),
                      "ust_kategori": plan["ust_kategori"].astype(str).to_numpy(),
                      "satis_hedefi": plan["satis_hedefi"].to_numpy(dtype=float)})
    p = p[(p["sezon_kodu"] == sezon) & p["magaza_id"].isin(fiz)].copy()
    p["sira"] = p.groupby("ust_kategori")["satis_hedefi"].rank(method="min", ascending=False).astype(np.int64)
    return p[["magaza_id", "ust_kategori", "sira"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Seçim
# ---------------------------------------------------------------------------


def _pencere_satisi(i: pd.DataFrame, satis: pd.DataFrame, gun: int) -> np.ndarray:
    s = satis[satis["adet"].to_numpy() > 0]
    s = pd.DataFrame({"option_id": s["option_id"].astype(str).to_numpy(),
                      "magaza_id": s["magaza_id"].astype(str).to_numpy(),
                      "tarih": pd.to_datetime(s["tarih"]).to_numpy(), "adet": s["adet"].to_numpy(dtype=np.int64)})
    s = s.merge(i[["option_id", "magaza_id", "varis"]], on=["option_id", "magaza_id"])
    g = (s["tarih"] - s["varis"]).dt.days.to_numpy()
    toplam = s[(g >= 0) & (g < gun)].groupby(["option_id", "magaza_id"])["adet"].sum()
    return toplam.reindex(pd.MultiIndex.from_frame(i[["option_id", "magaza_id"]]), fill_value=0).to_numpy()


def hucreler(ilk: pd.DataFrame, satis: pd.DataFrame, mag: pd.DataFrame, plan: pd.DataFrame,
             kol_kaydi: pd.DataFrame, sezon: str = sabitler.OYUN_SEZONU) -> pd.DataFrame:
    """(option, fiziksel mağaza) başına merdivenin okuduğu her şey: ilk adet, pay ve sırası, 28 / 14
    günlük satış, plan sırası, kolun adedi, Veli bayrağı."""
    m = magaza_tablosu(mag)
    i = ilk.assign(option_id=ilk["option_id"].astype(str), magaza_id=ilk["magaza_id"].astype(str))
    i = i[i["magaza_id"].isin(set(m.loc[m["fiziksel"], "magaza_id"])) & (i["adet"] > 0)].reset_index(drop=True)
    i = i.merge(m[["magaza_id", "ad", "veli"]].rename(columns={"ad": "magaza"}), on="magaza_id")
    g = i.groupby("option_id")["adet"]
    i["toplam"], i["magaza_sayisi"] = g.transform("sum"), g.transform("size")
    i["pay_sirasi"] = g.rank(method="min", ascending=False).astype(np.int64)
    i["satis_28"] = _pencere_satisi(i, satis, TASAN_GUN)
    i["satis_14"] = _pencere_satisi(i, satis, BITEN_GUN)
    ps = plan_sirasi(plan, mag, sezon).rename(columns={"sira": "plan_sirasi"})
    i = i.merge(ps, on=["magaza_id", "ust_kategori"], how="left")
    i["plan_sirasi"] = i["plan_sirasi"].fillna(0).astype(np.int64)
    k = kol_kaydi.assign(option_id=kol_kaydi["option_id"].astype(str), magaza_id=kol_kaydi["magaza_id"].astype(str))
    k = k.groupby(["option_id", "magaza_id"], as_index=False)["adet"].sum().rename(columns={"adet": "kol_adet"})
    i = i.merge(k, on=["option_id", "magaza_id"], how="left")
    i["kol_adet"] = i["kol_adet"].fillna(0).astype(np.int64)
    return i


_SUTUNLAR = ["option_id", "ad", "ust_kategori", "tasan_magaza_id", "tasan_magaza", "biten_magaza_id",
             "biten_magaza", "tasan_ilk_adet", "tasan_satis_28", "biten_ilk_adet", "biten_satis_14",
             "tasan_plan_sirasi", "kol_tasan_adet", "kol_biten_adet", "oturan", "biten_oran", "tasan_pay",
             "biten_pay", "toplam", "magaza_sayisi"]


def _ciftler(h: pd.DataFrame, b: Basamak) -> pd.DataFrame:
    adet = h["adet"].to_numpy(dtype=float)
    t = h["veli"] & (h["pay_sirasi"] <= b.pay_sirasi) & (h["satis_28"] <= b.tasan_satis * adet + _EPS)
    if b.plan_sirasi is not None:
        t &= (h["plan_sirasi"] >= 1) & (h["plan_sirasi"] <= b.plan_sirasi)
    bt = h["veli"] & (adet * h["magaza_sayisi"] <= h["toplam"] + _EPS) & (h["satis_14"] >= BITEN_PAY * adet - _EPS)
    ortak = ["option_id", "ad", "ust_kategori", "toplam", "magaza_sayisi"]
    oz = ["magaza_id", "magaza", "adet", "kol_adet"]
    c = h.loc[t, ortak + oz + ["satis_28", "plan_sirasi"]].merge(
        h.loc[bt, ["option_id"] + oz + ["satis_14"]], on="option_id", suffixes=("_t", "_b"))
    c = c[(c["magaza_id_t"] != c["magaza_id_b"]) & (c["adet_b"] < c["adet_t"])
          & (c["kol_adet_t"] <= b.kol_orani * c["adet_t"] + _EPS) & (c["kol_adet_b"] > c["adet_b"])]
    c = c.rename(columns={"magaza_id_t": "tasan_magaza_id", "magaza_t": "tasan_magaza", "adet_t": "tasan_ilk_adet",
                          "kol_adet_t": "kol_tasan_adet", "satis_28": "tasan_satis_28",
                          "plan_sirasi": "tasan_plan_sirasi", "magaza_id_b": "biten_magaza_id",
                          "magaza_b": "biten_magaza", "adet_b": "biten_ilk_adet", "kol_adet_b": "kol_biten_adet",
                          "satis_14": "biten_satis_14"})
    c = c.assign(oturan=c["tasan_ilk_adet"] - c["tasan_satis_28"],
                 biten_oran=c["biten_satis_14"] / c["biten_ilk_adet"],
                 tasan_pay=c["tasan_ilk_adet"] / c["toplam"], biten_pay=c["biten_ilk_adet"] / c["toplam"])
    c = c.sort_values(["oturan", "biten_oran", "option_id", "tasan_magaza_id", "biten_magaza_id"],
                      ascending=[False, False, True, True, True])
    return c.drop_duplicates("option_id")[_SUTUNLAR].reset_index(drop=True)


def adaylar(ilk, satis, mag, plan, kol_kaydi, basamak: Basamak, sezon: str = sabitler.OYUN_SEZONU) -> pd.DataFrame:
    """`basamak`ta sahne olabilen option'lar (option başına en iyi çift), sıralı."""
    return _ciftler(hucreler(ilk, satis, mag, plan, kol_kaydi, sezon), basamak)


def basamaklar(ilk, satis, mag, plan, kol_kaydi, sezon: str = sabitler.OYUN_SEZONU) -> list[pd.DataFrame]:
    """`MERDIVEN`'in her basamağının aday tablosu."""
    h = hucreler(ilk, satis, mag, plan, kol_kaydi, sezon)
    return [_ciftler(h, b) for b in MERDIVEN]


def _secim(tablolar: list[pd.DataFrame], zorla: str | None) -> tuple[int, pd.Series, str | None]:
    """(basamak indisi, sahnenin satırı, alternatif option)."""
    secilen = None
    for n, t in enumerate(tablolar):
        uyan = t[t["option_id"] == zorla] if zorla is not None else t
        if len(uyan):
            secilen = (n, uyan.iloc[0])
            break
    if secilen is None:
        kim = f"zorlanan option {zorla} " if zorla is not None else ""
        raise HikayeBulunamadi(f"{kim}merdivenin hiçbir basamağında sahne yok (5. ölçüt düşmez)")
    alternatif = None
    for t in tablolar:
        diger = t[t["option_id"] != secilen[1]["option_id"]]
        if len(diger):
            alternatif = str(diger.iloc[0]["option_id"])
            break
    return secilen[0], secilen[1], alternatif


def _hikaye(n: int, r: pd.Series, alternatif: str | None) -> Hikaye:
    return Hikaye(option_id=str(r["option_id"]), ad=str(r["ad"]), tasan_magaza=str(r["tasan_magaza"]),
                  biten_magaza=str(r["biten_magaza"]), tasan_ilk_adet=int(r["tasan_ilk_adet"]),
                  tasan_satis_28=int(r["tasan_satis_28"]), biten_ilk_adet=int(r["biten_ilk_adet"]),
                  biten_satis_14=int(r["biten_satis_14"]), tasan_plan_sirasi=int(r["tasan_plan_sirasi"]),
                  kol_tasan_adet=int(r["kol_tasan_adet"]), kol_biten_adet=int(r["kol_biten_adet"]),
                  gevseyen=list(MERDIVEN[n].gevseyen), alternatif=alternatif)


def sec(ilk: pd.DataFrame, satis: pd.DataFrame, mag: pd.DataFrame, plan: pd.DataFrame, kol_kaydi: pd.DataFrame,
        zorla: str | None = None, sezon: str = sabitler.OYUN_SEZONU) -> Hikaye:
    """Merdivenin ilk basamağındaki ilk sahne (`zorla`: o option'ın ilk basamağı).

    ilk        Lumoda'nın ilk dağıtımı: option_id, ad, ust_kategori, magaza_id, adet, varis
               (`ilk_tablosu`)
    satis      option_id, magaza_id, tarih, adet (`satis_tablosu`)
    mag        yayımlanan `magaza` (magaza_id, ad, sehir, tip)
    plan       yayımlanan `magaza_plan` (sezon_kodu, magaza_id, ust_kategori, satis_hedefi)
    kol_kaydi  en iyi kolun ilk dağıtımı: option_id, magaza_id, adet"""
    n, r, alt = _secim(basamaklar(ilk, satis, mag, plan, kol_kaydi, sezon), zorla)
    return _hikaye(n, r, alt)


# ---------------------------------------------------------------------------
# İnce CLI: önbelleğe alınmış koşulardan okur (motor yok)
# ---------------------------------------------------------------------------


def kosu_dizini_yolu(onbellek: Path, ad: str, anahtar: str) -> Path:
    """`motor._dizin`'in adlandırması (testte birebir)."""
    return Path(onbellek) / f"{ad}_{anahtar[:20]}"


def kosu_dizini(onbellek: Path, ad: str, anahtar: str) -> Path:
    """Koşunun önbellek dizini; `meta.json`'u yoksa ya da anahtarı tutmazsa `FileNotFoundError`."""
    d = kosu_dizini_yolu(onbellek, ad, anahtar)
    meta = d / "meta.json"
    if not meta.is_file() or json.loads(meta.read_text(encoding="utf-8")).get("anahtar") != anahtar:
        raise FileNotFoundError(f"{ad}: önbellekte anahtarı tutan koşu yok ({d})")
    return d


def _tablo(dizin: Path, ad: str, sutunlar=None, urunler=None) -> pd.DataFrame:
    suzgec = [("urun_id", "in", sorted(urunler))] if urunler is not None else None
    return pd.read_parquet(dizin / f"tablo_{ad}.parquet", columns=sutunlar, filters=suzgec)


def _json_oku(yol: Path) -> dict:
    if not yol.is_file():
        raise SystemExit(f"{yol.name} yok ({yol}): önce ızgaranın pay bloğu (python -m allocation.oyun)")
    return json.loads(yol.read_text(encoding="utf-8"))


def _kosu(oyun: dict, ad: str, onbellek: Path) -> Path:
    e = oyun["kosular"][ad]
    return kosu_dizini(onbellek, e.get("ayni", ad), e["anahtar"])


def _ozet(t: pd.DataFrame, n: int = 10) -> str:
    s = t.head(n)[["option_id", "ad", "tasan_magaza", "tasan_ilk_adet", "tasan_satis_28", "tasan_plan_sirasi",
                   "kol_tasan_adet", "biten_magaza", "biten_ilk_adet", "biten_satis_14", "kol_biten_adet"]]
    return s.to_string(index=False)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m allocation.hikaye_sec", description=__doc__.splitlines()[0])
    p.add_argument("--hikaye", metavar="OPTION", help="sahneyi bu option'a zorla")
    p.add_argument("--adaylar", action="store_true", help="her basamağın adaylarını bas")
    p.add_argument("--cikti", type=Path, default=sabitler.CIKTI)
    p.add_argument("--onbellek", type=Path, default=sabitler.CIKTI / "kosular")
    a = p.parse_args(argv)

    oyun = _json_oku(a.cikti / "oyun.json")
    secim = _json_oku(a.cikti / "secim.json")
    d_lum, d_kol = _kosu(oyun, "lumoda", a.onbellek), _kosu(oyun, secim["ad"], a.onbellek)
    urun = _tablo(d_lum, "urun", ["urun_id", "option_id", "model_adi", "renk", "ust_kategori", "sezon_kodu", "line"])
    skular = set(_oyun_urunleri(urun, sabitler.OYUN_SEZONU)["urun_id"])
    sv = ["tip", "hedef", "urun_id", "adet", "varis_tarihi"]
    ilk = ilk_tablosu(_tablo(d_lum, "sevkiyat", sv, skular), urun)
    satis = satis_tablosu(_tablo(d_lum, "satis", ["tarih", "magaza_id", "urun_id", "adet"], skular), urun)
    kol = ilk_tablosu(_tablo(d_kol, "sevkiyat", sv, skular), urun)[["option_id", "magaza_id", "adet"]]
    mag, plan = _tablo(d_lum, "magaza"), _tablo(d_lum, "magaza_plan")

    tablolar = basamaklar(ilk, satis, mag, plan, kol)
    n, r, alt = _secim(tablolar, a.hikaye)
    h = _hikaye(n, r, alt)
    alt_sahne = None
    if alt is not None:
        n2, r2, _ = _secim(tablolar, alt)
        alt_sahne = {**asdict(_hikaye(n2, r2, None)), "basamak": n2}
        del alt_sahne["alternatif"]
    ayrinti = {k: (v.item() if isinstance(v, np.generic) else v) for k, v in r.items()}
    icerik = {
        "sezon": sabitler.OYUN_SEZONU, "line": sabitler.LINE, "zorla": a.hikaye,
        "kol": {"kol": secim["kol"], "ad": secim["ad"]},
        "kaynak": {"lumoda": d_lum.name, "kol": d_kol.name},
        "basamak": n, "sahne": asdict(h), "alternatif_sahne": alt_sahne,
        "magaza_idleri": {"tasan": str(r["tasan_magaza_id"]), "biten": str(r["biten_magaza_id"])},
        "ayrinti": ayrinti, "aday_sayilari": [len(t) for t in tablolar],
        "merdiven": [asdict(b) for b in MERDIVEN],
    }
    a.cikti.mkdir(parents=True, exist_ok=True)
    gecici = a.cikti / "hikaye.json.yaziliyor"
    gecici.write_text(json.dumps(icerik, ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(a.cikti / "hikaye.json")

    if a.adaylar:
        for i, (b, t) in enumerate(zip(MERDIVEN, tablolar)):
            print(f"basamak {i} ({', '.join(b.gevseyen) or 'gevşeme yok'}): {len(t)} aday")
            if len(t):
                print(_ozet(t))
    print(f"sahne (basamak {n}, kol {secim['ad']}): {h.option_id} {h.ad} · taşan {h.tasan_magaza} "
          f"{h.tasan_ilk_adet} adet, 28 günde {h.tasan_satis_28}, plan sırası {h.tasan_plan_sirasi}, kol "
          f"{h.kol_tasan_adet} · biten {h.biten_magaza} {h.biten_ilk_adet} adet, 14 günde {h.biten_satis_14}, kol "
          f"{h.kol_biten_adet} · gevşeyen: {', '.join(h.gevseyen) or 'yok'}")
    print(f"alternatif: {alt or 'yok'}")


if __name__ == "__main__":
    sys.exit(main())
