"""Hakem: gizli gerçeğin (karşılanmayan talep) tek kapısı.

`perakende_veri` (v4 üreteci) yalnız bu modülde içe aktarılır; bu modülü de
paketin hiçbir modülü içe aktarmaz (`tests/test_sizinti.py` kilitler):
önbelleği `oku()` ile vakanın raporu okur (`vakalar/yok-satma/rapor.py`) ve tabloyu
`degerlendir`e argüman olarak verir. Kestiriciler hakemin yazdığı dosyaları da okumaz.

Tam v4 koşusu bir kez yeniden üretilir (`python -m perakende_analitik.hakem`,
varsayılan politikalar, yayımlanan veriyle aynı tohum; `tests/v4/
test_esdegerlik.py` varsayılan koşunun yayımlanan veri olduğunu kanıtlar),
ham günlük talep kaydedilir ve hücre-gün başına şu ayrışma çıkarılır
(spec §4.7):

    kendi_satis    = ham `satis`'in pozitif satırı − alınan ikame (aynı gün, hücre)
    karsilanmayan  = talep − kendi_satis
    kalici_kayip   = `gizli_kayip` (ikameden sonra, kaynak hücrede)
    ikameye_giden  = karsilanmayan − kalici_kayip

Yalnız `talep > 0` ve `karsilanmayan > 0` hücre-günleri, yalnız pencere
(2023-01-01 – 2025-12-31). Yeniden üretilen yayımlanan tablolar DuckDB ile
karşılaştırılır (`dogrula`); biri tutmazsa hiçbir dosya yazılmaz.

Sızdırma yok: `kendi_satis`, `karsilanmayan`, `ikameye_giden` `degerlendir`'de
ölçüt olur, kestirici girdisi değildir.

Kurulum: `perakende-veri` PyPI'da değildir; yol ile kurulur:
`pip install -e ../../veri` (vakalar/ortak içinden).

Bellek: `talep` [gün, hücre] int16 (~0,3 GB); aynı boyutta ikinci bir yoğun
matris kurulmaz, kendi satış seyrek tutulur ve yalnız `talep > 0` hücre-
günlerinde fark alınır.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from perakende_veri.v4 import tablolar as v4_tablolar
from perakende_veri.v4.dunya import dunya_kur
from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.uret import yayimla

from perakende_analitik import kaynak

HAKEM_DIZINI = Path(__file__).resolve().parents[1] / "cikti" / "hakem"
KOMUT = "python -m perakende_analitik.hakem"

_HAKEM_SUTUNLARI = ["talep", "kendi_satis", "karsilanmayan", "ikameye_giden", "kalici_kayip"]
_ID_SUTUNLARI = ["magaza_id", "urun_id"]


def _anahtarli(df: pd.DataFrame, C: int, pozitif: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """(gun, hucre, adet) → (artan tekil anahtar `gun*C + hucre`, adet toplamı).

    `pozitif` iadeleri (negatif adet) eler. Motor bir hücre-güne tek satır
    yazar, anahtar zaten artandır (hızlı yol); değilse toplayarak tekilleştirir."""
    gun = df["gun"].to_numpy(dtype=np.int64)
    hucre = df["hucre"].to_numpy(dtype=np.int64)
    adet = df["adet"].to_numpy(dtype=np.int64)
    if pozitif:
        m = adet > 0
        gun, hucre, adet = gun[m], hucre[m], adet[m]
    anahtar = gun * C + hucre
    if len(anahtar) > 1 and not np.all(anahtar[1:] > anahtar[:-1]):
        tekil, ters = np.unique(anahtar, return_inverse=True)
        adet = np.bincount(ters, weights=adet, minlength=len(tekil)).astype(np.int64)
        anahtar = tekil
    return anahtar, adet


def _hucre_sirasi(dunya) -> np.ndarray:
    """Hücre → (magaza_id, urun_id) sözlük sırası (yayımlanan tabloların sırası)."""
    m = dunya.magazalar["magaza_id"].to_numpy().astype(str)[np.asarray(dunya.hucre_magaza)]
    u = dunya.urunler["urun_id"].to_numpy().astype(str)[np.asarray(dunya.hucre_sku)]
    sira = np.lexsort((u, m))
    rutbe = np.empty(len(sira), dtype=np.int64)
    rutbe[sira] = np.arange(len(sira))
    return rutbe


def karsilanmayan_tablosu(dunya, ham: dict) -> pd.DataFrame:
    """Hakem tablosu: `tarih, magaza_id, urun_id, talep, kendi_satis,
    karsilanmayan, ikameye_giden, kalici_kayip` (int32; yalnız `karsilanmayan
    > 0`, pencereli, (tarih, magaza_id, urun_id) sıralı).

    `ham`: `simule_et(..., kayit_talep=True)` çıktısı (`talep`, `satis`,
    `ikame_satis`, `gizli_kayip`). Ayrışma kimliği tutmazsa (`kendi_satis >
    talep`, `kalici_kayip > karsilanmayan`) sayıları söyleyen `RuntimeError`."""
    talep = np.asarray(ham["talep"])
    D, C = talep.shape
    bas, son = v4_tablolar.pencere()
    talep_duz = talep.reshape(-1)           # [D*C] görünüm, kopya yok

    # kendi satış (seyrek): pozitif satış − alınan ikame
    s_anahtar, kendi = _anahtarli(ham["satis"], C, pozitif=True)
    i_anahtar, ikame = _anahtarli(ham["ikame_satis"], C)
    if len(i_anahtar):
        sira = np.minimum(np.searchsorted(s_anahtar, i_anahtar), max(len(s_anahtar) - 1, 0))
        if not len(s_anahtar) or not np.array_equal(s_anahtar[sira], i_anahtar):
            raise RuntimeError("hakem: satışsız hücre-günde alınan ikame var")
        kendi[sira] -= ikame
    asan = (kendi > talep_duz[s_anahtar]) | (kendi < 0)
    if asan.any():
        raise RuntimeError(
            f"hakem: kendi_satis talebi asiyor ya da negatif: {int(asan.sum())} hücre-gün "
            f"(satış satırı {len(s_anahtar)})")

    # talep > 0 hücre-günleri (pencere) ve kendi satışla farkı
    pencere_duz = talep_duz[bas * C:(son + 1) * C]
    anahtar = np.flatnonzero(pencere_duz > 0)
    t = pencere_duz[anahtar].astype(np.int32)
    anahtar += bas * C
    sira = np.minimum(np.searchsorted(s_anahtar, anahtar), max(len(s_anahtar) - 1, 0))
    if len(s_anahtar):
        var = s_anahtar[sira] == anahtar
        k = np.where(var, kendi[sira], 0).astype(np.int32)
        del var
    else:
        k = np.zeros(len(anahtar), dtype=np.int32)
    del sira
    kars = t - k
    tut = kars > 0
    anahtar, t, k, kars = anahtar[tut], t[tut], k[tut], kars[tut]
    del tut

    # kalıcı kayıp (gizli_kayip) pencere içi; karşılanmayan hücre-günde olmalı
    g_anahtar, g_adet = _anahtarli(ham["gizli_kayip"], C)
    pen = (g_anahtar >= bas * C) & (g_anahtar < (son + 1) * C)
    g_anahtar, g_adet = g_anahtar[pen], g_adet[pen]
    kalici = np.zeros(len(anahtar), dtype=np.int32)
    if len(g_anahtar):
        sira = np.minimum(np.searchsorted(anahtar, g_anahtar), max(len(anahtar) - 1, 0))
        eslesti = (anahtar[sira] == g_anahtar) if len(anahtar) else np.zeros(len(g_anahtar), bool)
        yok = int((~eslesti).sum())
        if len(anahtar):
            kalici[sira[eslesti]] = g_adet[eslesti]
        if yok:
            raise RuntimeError(
                f"hakem: kalici_kayip karşılanmayan olmayan hücre-günde: {yok} hücre-gün")
    asan = kalici > kars
    if asan.any():
        raise RuntimeError(
            f"hakem: kalici_kayip karsilanmayani asiyor: {int(asan.sum())} / {len(kars)} hücre-gün")

    gun, hucre = anahtar // C, anahtar % C
    rutbe = _hucre_sirasi(dunya)
    siralama = gun * C + rutbe[hucre]
    if len(siralama) > 1 and not np.all(siralama[1:] > siralama[:-1]):
        p = np.argsort(siralama, kind="stable")
        gun, hucre, t, k, kars, kalici = gun[p], hucre[p], t[p], k[p], kars[p], kalici[p]
    ham_df = pd.DataFrame({
        "gun": gun, "hucre": hucre, "talep": t, "kendi_satis": k,
        "karsilanmayan": kars, "ikameye_giden": kars - kalici, "kalici_kayip": kalici,
    })
    return v4_tablolar.hucre_tablosu(dunya, ham_df)


def ikame_alinan_tablosu(dunya, ham: dict) -> pd.DataFrame:
    """Alıcı hücrede ikame satışı: `tarih, magaza_id, urun_id, adet` (int32;
    pencereli; bu adet `satis`'te zaten vardır)."""
    df = v4_tablolar.hucre_tablosu(dunya, ham["ikame_satis"])
    df["adet"] = df["adet"].astype(np.int32)
    return df.sort_values(["tarih", "magaza_id", "urun_id"], kind="stable").reset_index(drop=True)


def dogrula(tablolar: dict, con) -> dict[str, bool]:
    """Yeniden üretilen yayımlanan tabloları DuckDB ile karşılaştırır.

    Anahtarlar: `satis_satir`, `satis_adet` (Σ adet), `stok_satir`,
    `sevkiyat_satir`, `gunluk_satis` (her günün satış adedi toplamı).
    `tablolar`: `satis`, `stok`, `sevkiyat` (kirli, yayımlanan haliyle)."""
    satir, adet = con.execute("select count(*), coalesce(sum(adet), 0) from satis").fetchone()
    sonuc = {
        "satis_satir": len(tablolar["satis"]) == int(satir),
        "satis_adet": int(tablolar["satis"]["adet"].sum()) == int(adet),
        "stok_satir": len(tablolar["stok"]) == int(con.execute("select count(*) from stok").fetchone()[0]),
        "sevkiyat_satir": len(tablolar["sevkiyat"])
        == int(con.execute("select count(*) from sevkiyat").fetchone()[0]),
    }
    db = con.execute("select tarih, sum(adet) as adet from satis group by tarih").df()
    db = pd.Series(db["adet"].to_numpy(dtype=np.int64), index=pd.to_datetime(db["tarih"])).sort_index()
    yeni = tablolar["satis"].groupby("tarih", observed=True)["adet"].sum()
    yeni = pd.Series(yeni.to_numpy(dtype=np.int64), index=pd.to_datetime(yeni.index)).sort_index()
    sonuc["gunluk_satis"] = bool(db.index.equals(yeni.index) and np.array_equal(db.to_numpy(), yeni.to_numpy()))
    return sonuc


def _kos() -> tuple[pd.DataFrame, pd.DataFrame, dict, int]:
    """Tam v4 koşusu: (karşılanmayan, ikame alınan, doğrulanacak yayımlanan
    tablolar, dünya tohumu). Ağır: ~2–5 dk, birkaç GB."""
    dunya = dunya_kur(Olcek.TAM)
    ham = simule_et(dunya, kayit_talep=True)
    kars = karsilanmayan_tablosu(dunya, ham)
    ikame = ikame_alinan_tablosu(dunya, ham)
    del ham["talep"]
    tablolar = yayimla(dunya, ham)
    del ham
    return kars, ikame, {a: tablolar[a] for a in ("satis", "stok", "sevkiyat")}, int(dunya.tohum)


def kur(yol: Path = HAKEM_DIZINI) -> None:
    """Hakem önbelleğini kurar: `karsilanmayan.parquet`, `ikame_alinan.parquet`,
    `meta.json`. Doğrulama tutmazsa `RuntimeError`, hiçbir dosya yazılmaz."""
    yol = Path(yol)
    t0 = time.perf_counter()
    kars, ikame, tablolar, tohum = _kos()
    con = kaynak.baglan()
    try:
        dogrulama = dogrula(tablolar, con)
    finally:
        if con is not None:
            con.close()
    del tablolar
    basarisiz = [a for a, d in dogrulama.items() if not d]
    if basarisiz:
        raise RuntimeError(
            f"hakem: yeniden uretilen yayimlanan veri DuckDB ile ayni degil: {basarisiz}; "
            "hicbir dosya yazilmadi")
    yol.mkdir(parents=True, exist_ok=True)
    kars.to_parquet(yol / "karsilanmayan.parquet", index=False, compression="zstd")
    ikame.to_parquet(yol / "ikame_alinan.parquet", index=False, compression="zstd")
    meta = {
        "tohum": tohum,
        "sure_sn": round(time.perf_counter() - t0, 1),
        "dogrulama": dogrulama,
        "satir_sayilari": {"karsilanmayan": len(kars), "ikame_alinan": len(ikame)},
        "toplamlar": {s: int(kars[s].to_numpy().sum(dtype=np.int64)) for s in _HAKEM_SUTUNLARI},
    }
    (yol / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _r9(df: pd.DataFrame) -> pd.DataFrame:
    df["tarih"] = df["tarih"].astype("datetime64[ns]")
    for s in _ID_SUTUNLARI:
        df[s] = df[s].astype("category")
    for s in df.columns.drop(["tarih", *_ID_SUTUNLARI]):
        df[s] = df[s].astype("int32")
    return df


def oku(yol: Path = HAKEM_DIZINI) -> dict:
    """`karsilanmayan`, `ikame_alinan` (DataFrame, R9 türleri) ve `meta` (dict).
    Önbellek yoksa `FileNotFoundError` (kurma komutunu söyler)."""
    yol = Path(yol)
    dosyalar = [yol / a for a in ("karsilanmayan.parquet", "ikame_alinan.parquet", "meta.json")]
    yok = [d.name for d in dosyalar if not d.exists()]
    if yok:
        raise FileNotFoundError(f"{yol} icinde {', '.join(yok)} yok. Once kurun: {KOMUT}")
    return {
        "karsilanmayan": _r9(pd.read_parquet(dosyalar[0])),
        "ikame_alinan": _r9(pd.read_parquet(dosyalar[1])),
        "meta": json.loads(dosyalar[2].read_text(encoding="utf-8")),
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    kur()
    m = oku()["meta"]
    print(json.dumps(m, indent=2, ensure_ascii=False))
    print(f"Çıktı: {HAKEM_DIZINI}")


if __name__ == "__main__":
    main()
