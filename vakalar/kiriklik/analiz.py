"""Koşusuz veri analizi: İş Zekası yazılarının ("Kırıklık Nedir", "Atıl Stok Nedir") ve raporun VERİ, KIRIKLIK, ATIL,
UYGUNLUK bölümlerinin yayımlanan v4'ten ölçümleri (`cikti/analiz.json`; tasarım §4 `analiz.py` listesi).

    cd vakalar/kiriklik
    PYTHONIOENCODING=utf-8 .venv/Scripts/python analiz.py          # yayımlanan v4 (PERAKENDE_V4_DB) → cikti/analiz.json

Ölçüm tarafıdır (paket dışında, vaka kökünde; `rapor.py` gibi). Kaynak yol 0'ın yayımlanan v4 DuckDB'sidir
(`kaynak.baglan()`, salt okunur; analistin gördüğü veri, yayımlamanın kirli kayıtlarıyla); koşu okunmaz, simülasyon
başlatılmaz, gizli gerçek okunmaz. Hiçbir sayı elle konmaz. Tanımlar kiriklik paketinindir, burada yinelenmez:
kırıklık `olcu.cift_tablosu` / `olcu.ozet` (K1), atıl sınıfı `olcu.atil_sinifi` (K2), uygunluk `uygunluk.adaylar`
(K4, K18), karar girdisi `kaynak.karar_girdisi`.

**Sezonlar** (`SEZONLAR`): test sezonları AW24, SS25 ve önceki aynı tip sezonları AW23, SS24 (`ONCEKI`). Kapsam her
sezonda Collection SKU'ları (Standart beden seti hariç) × fiziksel mağazalar (AVM, Cadde): `kaynak`'ın süzgeci.

**Haftalar** (`haftalik`): sezonun ilk lansmanından çıkışa pazartesi stok fotoğrafları `[lansman, çıkış)`; `hafta`
indirim haftasına göre (0 indirim gününün haftası, −3 üç hafta önce), `hafta_lansman` ilk lansman haftasına göre.
Her hafta: bütün kapsamın `olcu.ozet`'i (kırık beden ve kırık çift, net ve brüt oran, dar tanımla kırık çift) ve
mağaza tipine göre (`tip`). Stoğu sıfır çift hiçbir paydaya girmez (`olcu` notu).

**Atıl stok** (K2, `sabitler.ATIL_*`): her pazartesi `t` için pencere `[t − 28, t)` pozitif satış (iade satırı
düşmez; mükerrer kopya düşer: `select distinct`, Ruling R1). Rafta süresi = `t` − çiftin (ya da hücrenin) stoğu
pozitif ilk pazartesi fotoğrafı (yayımlanan veride raf açılışının gözlenen karşılığı; Lumoda'nın elle transfer
kuralının "en az 28 gündür rafta" koşulu); 28 günden azsa `yeni` (ne atıl ne satmayan). Option × mağaza düzeyinde
x ∈ `ATIL_DUYARLILIK` için atıl (1 ≤ satış ≤ x) ve satmayan (satış 0; x'ten bağımsız): çift sayısı, mağaza stoğu
(`adet`) ve alış değeri (`alis` = Σ adet × alış fiyatı). SKU düzeyinde x = `ATIL_ESIK_SKU`: stoğu pozitif hücreler.
Kırıklıkla kesişim (`kirik_atil`): kırık ve tam (kırık olmayan) çiftlerin x = `ATIL_ESIK_OPTION` sınıflarına
dağılımı (çift ve adet): "kırık setin kalan bedenleri atıllaşıyor mu".

**Referans pazartesisi** (`referans`): indirim − 28'den sonraki ilk pazartesi (dahil); test sezonlarında karar günüdür
(`sabitler.KARAR`, denetlenir), önceki sezonlarda aynı konumdaki pazartesi. O fotoğrafta beden sırasına göre
(`beden_sirasi`: sıra başına sıfır stoklu çift sayısı ve stoklu çiftlerdeki payı, eksik adet; toplamları `olcu.ozet`'le
zorla eşit) ve mağaza tipine göre kırıklık.

**Uygunluk hunisi** (`huni`, yalnız test sezonları, karar anı `kaynak.karar_girdisi`): stoklu çift → kırık → eksik
bedenlerin hiçbirinin depoda stoğu yok → açık siparişi de yok (K18) → mağaza uygun (K4). İlk üç basamak
`uygunluk.adaylar`'ın mağazayı süzmediği okumasından (bütün mağazalar uygun sayılır: neden etiketinin önceliği
mağazayı öne aldığı için), son basamak gerçek girdiden. Çift ve option sayıları; ayrıca keşif olgularının yeniden
ölçümü (`kesif`: option, stoklu mağaza, SKU ve depoda stoğu olan SKU, depo stoğu tamamen sıfır option, option başına
medyan stoklu ve kırık çift, son 28 günde 6+ satan çift).

`kod`: analizi belirleyen kodun özeti (bu dosya, kiriklik `kaynak`, `olcu`, `uygunluk`, `sabitler`); `veri`: v4
dosyasının parmak izi. Rapor ikisi tutmayan analizi reddeder.
"""

import argparse
import dataclasses
import hashlib
import json
import math
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from allocation import motor

from kiriklik import kaynak, olcu, sabitler, uygunluk

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
HEDEF = CIKTI / "analiz.json"
SURUM = 1
SEZONLAR = ("AW23", "SS24", "AW24", "SS25")
ONCEKI = {"AW24": "AW23", "SS25": "SS24"}
REFERANS_GUN = 28                     # referans pazartesisi: indirim − 28'den sonraki ilk pazartesi
SATIS_ESIGI = 6                       # keşif: son 28 günde 6+ adet satan çift
KOD_MODULLERI = ("kaynak", "olcu", "uygunluk", "sabitler")
OZET_ALANLARI = ("stoklu_cift", "kirik_cift", "dar_kirik_cift", "kirik_beden", "beden", "eksik_adet", "asorti",
                 "net_oran", "brut_oran", "kirik_cift_oran")


def kod_ozeti() -> str:
    """Analizi belirleyen kodun özeti (dosya adı + içerik, satır sonları LF)."""
    paket = KOK / "kiriklik"
    h = hashlib.sha256()
    for y in (Path(__file__).resolve(), *(paket / f"{m}.py" for m in KOD_MODULLERI)):
        h.update(y.name.encode() + b"\0" + y.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Tarihler
# ---------------------------------------------------------------------------


def _pazartesi(d: date) -> date:
    """d ya da ondan önceki son pazartesi."""
    return d - timedelta(days=d.weekday())


def _sonraki_pazartesi(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


def sezon_gunleri(con, sezon: str) -> dict:
    """Sezonun ilk lansmanı, indirim ve çıkış günleri (`sezon` tablosu; `kaynak.sezon_dates`), referans pazartesisi."""
    indirim, cikis = kaynak.sezon_dates(con, sezon)
    lansman = pd.Timestamp(con.execute("select min(lansman_tarihi) from sezon where sezon_kodu = ?",
                                       [sezon]).fetchone()[0]).date()
    referans = _sonraki_pazartesi(indirim - timedelta(days=REFERANS_GUN))
    if sezon in sabitler.KARAR and referans != sabitler.KARAR[sezon]:
        raise ValueError(f"{sezon}: referans pazartesisi {referans}, karar günü {sabitler.KARAR[sezon]}")
    return {"lansman": lansman, "indirim": indirim, "cikis": cikis, "referans": referans}


def pazartesiler(gunler: dict) -> list[date]:
    """[ilk lansman, çıkış) aralığının pazartesileri."""
    d = _sonraki_pazartesi(gunler["lansman"])
    out = []
    while d < gunler["cikis"]:
        out.append(d)
        d += timedelta(days=7)
    return out


def hafta_no(d: date, gunler: dict) -> int:
    """İndirim haftasına göre hafta (0 indirim gününün haftası)."""
    return (_pazartesi(d) - _pazartesi(gunler["indirim"])).days // 7


# ---------------------------------------------------------------------------
# Sorgular
# ---------------------------------------------------------------------------


def _on_ek(sezon: str) -> tuple[str, list]:
    yer = ", ".join("?" for _ in sabitler.FIZIKSEL_TIPLER)
    sql = f"""with
        sku as (select urun_id, option_id, beden_sira, alis_fiyati from urun
                where sezon_kodu = ? and line = ? and beden_seti <> ?),
        mag as (select magaza_id, tip from magaza where tip in ({yer}))"""
    return sql, [sezon, sabitler.LINE, sabitler.STANDART_BEDEN_SETI, *sabitler.FIZIKSEL_TIPLER]


def fotograflar(con, sezon: str, gunler: list[date]) -> pd.DataFrame:
    """Pazartesi stok fotoğrafları: [tarih, magaza_id, tip, urun_id, option_id, beden_sira, alis, stok]."""
    on, par = _on_ek(sezon)
    yer = ", ".join("?" for _ in gunler)
    df = con.execute(f"""{on}
        select cast(t.tarih as date) as tarih, t.magaza_id::varchar as magaza_id, m.tip::varchar as tip,
               t.urun_id::varchar as urun_id, s.option_id::varchar as option_id, s.beden_sira,
               s.alis_fiyati as alis, sum(t.adet)::bigint as stok
        from stok t join sku s using (urun_id) join mag m using (magaza_id)
        where cast(t.tarih as date) in ({yer})
        group by all""", [*par, *gunler]).fetchdf()
    df["tarih"] = pd.to_datetime(df["tarih"]).dt.date
    return df.astype({"beden_sira": np.int64, "stok": np.int64})


def haftalik_satis(con, sezon: str, bas: date, son: date) -> pd.DataFrame:
    """Hücre × pazartesi haftası pozitif satış [bas, son): [hafta, magaza_id, urun_id, adet] (mükerrer kopya düşer)."""
    on, par = _on_ek(sezon)
    df = con.execute(f"""{on}
        select cast(date_trunc('week', t.tarih) as date) as hafta, t.magaza_id::varchar as magaza_id,
               t.urun_id::varchar as urun_id, sum(t.adet)::bigint as adet
        from (select distinct * from satis where tarih >= ? and tarih < ? and adet > 0) t
        join sku s using (urun_id) join mag m using (magaza_id)
        group by all""", [*par, bas, son]).fetchdf()
    df["hafta"] = pd.to_datetime(df["hafta"]).dt.date
    return df


# ---------------------------------------------------------------------------
# Bloklar
# ---------------------------------------------------------------------------


def _tip_ozetleri(cift: pd.DataFrame, tip: pd.Series) -> dict:
    t = cift.merge(tip, on="magaza_id")
    return {x: olcu.ozet(t[t["tip"] == x]) for x in sabitler.FIZIKSEL_TIPLER}


def _hucre(foto: pd.DataFrame) -> pd.DataFrame:
    return foto[["magaza_id", "option_id", "beden_sira", "stok"]]


def beden_sirasi(foto: pd.DataFrame, oz: dict) -> list[dict]:
    """Stoklu çiftlerde beden sırası başına: sıfır stoklu (kırık) çift, stoklu çiftlerdeki payı, eksik adet. Tanım
    `olcu.cift_tablosu`'nundur; burada sıraya ayrılır ve aynı fotoğrafın `olcu.ozet`'iyle (`oz`) eşitliği zorlanır:
    çift sayısı = stoklu çift, Σ sıra kırık çift = kırık beden, Σ sıra eksik adet = eksik adet (yoksa `ValueError`)."""
    st = (foto.pivot_table(index=["magaza_id", "option_id"], columns="beden_sira", values="stok", aggfunc="sum",
                           fill_value=0).reindex(columns=[1, 2, 3, 4, 5], fill_value=0))
    st = st[st.sum(axis=1) > 0]
    n = len(st)
    out = []
    for i, a in enumerate(sabitler.ASORTI, start=1):
        k = int((st[i] == 0).sum())
        out.append({"beden_sira": i, "asorti": int(a), "kirik_cift": k, "pay": k / n if n else 0.0,
                    "eksik_adet": int(np.maximum(0, a - st[i].to_numpy()).sum())})
    if (n, sum(x["kirik_cift"] for x in out), sum(x["eksik_adet"] for x in out)) != (
            oz["stoklu_cift"], oz["kirik_beden"], oz["eksik_adet"]):
        raise ValueError("beden sırası tablosu olcu.ozet ile tutmuyor (stoklu çift, kırık beden, eksik adet)")
    return out


def _atil_satiri(siniflar: dict, adet: np.ndarray, alis: np.ndarray) -> dict:
    """Sınıf dizileri ({ad: sınıf}) → sayılar."""
    out = {}
    for ad, s in siniflar.items():
        out[ad] = {c: {"n": int((s == c).sum()), "adet": int(adet[s == c].sum()), "alis": float(alis[s == c].sum())}
                   for c in ("satmayan", "atil", "satan", "yeni")}
    return out


def atil_haftasi(foto: pd.DataFrame, satis: pd.DataFrame, ilk_cift: pd.Series, ilk_hucre: pd.Series, t: date,
                 cift: pd.DataFrame) -> dict:
    """`t` pazartesisinin atıl ve satmayan stoğu (modül notu)."""
    pencere = satis[(satis["hafta"] >= t - timedelta(days=sabitler.ATIL_PENCERE_GUN)) & (satis["hafta"] < t)]
    hucre_satis = pencere.groupby(["magaza_id", "urun_id"])["adet"].sum()
    f = foto[foto["stok"] > 0].copy()
    f["satis"] = hucre_satis.reindex(pd.MultiIndex.from_frame(f[["magaza_id", "urun_id"]])).fillna(0).to_numpy()
    f["deger"] = f["stok"] * f["alis"]
    # option × mağaza
    c = f.groupby(["magaza_id", "option_id"], as_index=False).agg(stok=("stok", "sum"), deger=("deger", "sum"),
                                                                    satis=("satis", "sum"))
    ilk = ilk_cift.reindex(pd.MultiIndex.from_frame(c[["magaza_id", "option_id"]])).to_numpy()
    rafta = np.array([(t - d).days for d in ilk], dtype=np.int64)
    siniflar = {f"x{x}": olcu.atil_sinifi(c["satis"].to_numpy(), rafta, esik=x) for x in sabitler.ATIL_DUYARLILIK}
    cift_ = _atil_satiri(siniflar, c["stok"].to_numpy(), c["deger"].to_numpy())
    # SKU
    ilk_h = ilk_hucre.reindex(pd.MultiIndex.from_frame(f[["magaza_id", "urun_id"]])).to_numpy()
    rafta_h = np.array([(t - d).days for d in ilk_h], dtype=np.int64)
    sku = _atil_satiri({"x": olcu.atil_sinifi(f["satis"].to_numpy(), rafta_h, esik=sabitler.ATIL_ESIK_SKU)},
                       f["stok"].to_numpy(), f["deger"].to_numpy())["x"]
    # kırıklıkla kesişim (x = ATIL_ESIK_OPTION)
    k = c.merge(cift[["magaza_id", "option_id", "kirik"]], on=["magaza_id", "option_id"], how="left")
    if k["kirik"].isna().any():
        raise ValueError("atıl çift kırıklık tablosunda yok")
    s = siniflar[f"x{sabitler.ATIL_ESIK_OPTION}"]
    kir = k["kirik"].to_numpy(dtype=bool)
    kesisim = {}
    for ad, m in (("kirik", kir), ("tam", ~kir)):
        kesisim[ad] = _atil_satiri({"x": s[m]}, c["stok"].to_numpy()[m], c["deger"].to_numpy()[m])["x"]
    return {"cift": cift_, "sku": sku, "kirik_atil": kesisim}


def sezon_blogu(con, sezon: str) -> dict:
    """Sezonun haftalık kırıklık ve atıl stok serisi, referans pazartesisi kesitleri (modül notu)."""
    gunler = sezon_gunleri(con, sezon)
    pts = pazartesiler(gunler)
    foto = fotograflar(con, sezon, pts)
    satis = haftalik_satis(con, sezon, pts[0] - timedelta(days=sabitler.ATIL_PENCERE_GUN), gunler["cikis"])
    pozitif = foto[foto["stok"] > 0]
    ilk_hucre = pozitif.groupby(["magaza_id", "urun_id"])["tarih"].min()
    ilk_cift = pozitif.groupby(["magaza_id", "option_id"])["tarih"].min()
    tip = foto[["magaza_id", "tip"]].drop_duplicates()
    haftalik, referans = [], None
    for t in pts:
        f = foto[foto["tarih"] == t]
        cift = olcu.cift_tablosu(_hucre(f))
        satir = {"tarih": t.isoformat(), "hafta": hafta_no(t, gunler),
                 "hafta_lansman": (t - _pazartesi(gunler["lansman"])).days // 7, "butun": olcu.ozet(cift),
                 "tip": _tip_ozetleri(cift, tip), "atil": atil_haftasi(f, satis, ilk_cift, ilk_hucre, t, cift)}
        haftalik.append(satir)
        if t == gunler["referans"]:
            referans = {"tarih": t.isoformat(), "hafta": satir["hafta"], "butun": satir["butun"],
                        "tip": satir["tip"], "beden_sirasi": beden_sirasi(f, satir["butun"])}
    if referans is None:
        raise ValueError(f"{sezon}: referans pazartesisi {gunler['referans']} sezonun haftalarında yok")
    return {"gunler": {a: d.isoformat() for a, d in gunler.items()},
            "indirime_gun": (gunler["indirim"] - gunler["referans"]).days, "haftalik": haftalik, "referans": referans}


def _medyan(s: pd.Series) -> float | None:
    return float(s.median()) if len(s) else None


def huni(con, sezon: str) -> dict:
    """Karar anının uygunluk hunisi ve keşif olgularının yeniden ölçümü (modül notu)."""
    g = kaynak.karar_girdisi(con, sezon)
    cift = olcu.cift_tablosu(g.hucre)
    oz = olcu.ozet(cift)
    gercek = uygunluk.adaylar(g)
    serbest = uygunluk.adaylar(dataclasses.replace(g, magaza=g.magaza.assign(uygun=True)))
    if len(gercek) != oz["kirik_cift"] or len(serbest) != oz["kirik_cift"]:
        raise ValueError(f"{sezon}: aday tablosu kırık çift sayısıyla tutmuyor")
    depoda_yok = serbest[serbest["neden"] != "depoda_var"]
    acik_yok = serbest[serbest["uygun"]]
    magaza = gercek[gercek["uygun"]]
    if not set(zip(magaza.magaza_id, magaza.option_id)) <= set(zip(acik_yok.magaza_id, acik_yok.option_id)):
        raise ValueError(f"{sezon}: mağazası uygun aday açık siparişsiz adaylarda değil")
    kirik = cift[cift["kirik"]]
    basamaklar = [("stoklu", cift), ("kirik", kirik), ("depoda_yok", depoda_yok), ("acik_siparis_yok", acik_yok),
                  ("magaza_uygun", magaza)]
    sku = g.hucre.drop_duplicates("urun_id")
    depo_opt = sku.groupby("option_id")["depo"].sum()
    son28 = g.satis[(g.satis["tarih"] >= pd.Timestamp(g.karar - timedelta(days=sabitler.ATIL_PENCERE_GUN)))
                    & (g.satis["adet"] > 0)]
    son28 = son28.merge(g.hucre[["magaza_id", "urun_id", "option_id"]], on=["magaza_id", "urun_id"])
    cift_satis = son28.groupby(["magaza_id", "option_id"])["adet"].sum()
    cs = cift_satis.reindex(pd.MultiIndex.from_frame(cift[["magaza_id", "option_id"]])).fillna(0)
    stoklu_opt = cift.groupby("option_id").size()
    kirik_opt = kirik.groupby("option_id").size().reindex(stoklu_opt.index, fill_value=0)
    return {
        "karar": g.karar.isoformat(), "indirime_gun": (g.indirim - g.karar).days, "ozet": oz,
        "basamaklar": [{"ad": ad, "cift": int(len(t)), "option": int(t["option_id"].nunique())} for ad, t in basamaklar],
        "neden": {n: int((gercek["neden"] == n).sum()) for n in uygunluk.NEDENLER},
        "kesif": {"option": int(cift["option_id"].nunique()), "magaza": int(cift["magaza_id"].nunique()),
                  "sku": int(len(sku)), "sku_depolu": int((sku["depo"] > 0).sum()),
                  "option_deposuz": int((depo_opt == 0).sum()), "option_toplam": int(len(depo_opt)),
                  "option_basina_stoklu_medyan": _medyan(stoklu_opt), "option_basina_kirik_medyan": _medyan(kirik_opt),
                  "son28_esik": SATIS_ESIGI, "son28_esik_ustu": int((cs.to_numpy() >= SATIS_ESIGI).sum()),
                  "magaza_fiziksel": int(len(g.magaza)), "magaza_uygun": int(g.magaza["uygun"].sum())},
    }


# ---------------------------------------------------------------------------
# Kurulum
# ---------------------------------------------------------------------------


def kur(con) -> dict:
    """analiz.json'un içeriği (`con`: yayımlanan v4 ya da aynı şemada bir bağlantı)."""
    t0 = time.perf_counter()
    bas, son = (pd.Timestamp(x).date() for x in con.execute("select min(tarih), max(tarih) from satis").fetchone())
    sezonlar = {z: sezon_blogu(con, z) for z in SEZONLAR}
    huniler = {z: huni(con, z) for z in sabitler.TEST_SEZONLARI}
    print(f"analiz: {time.perf_counter() - t0:.0f} sn", file=sys.stderr, flush=True)
    return {"surum": SURUM, "olcek": "tam", "kod": kod_ozeti(), "kaynak": "yayimlanan",
            "veri": motor.veri_parmak_izi(), "veri_gunleri": {"ilk": bas.isoformat(), "son": son.isoformat()},
            "sezonlar": list(SEZONLAR), "onceki": ONCEKI, "sezon": sezonlar, "huni": huniler}


def _jsonla(x):
    if isinstance(x, dict):
        return {str(k): _jsonla(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonla(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if math.isnan(float(x)) else float(x)
    return x


def yaz(sonuc: dict, yol: Path = HEDEF) -> Path:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".yaziliyor")
    gecici.write_text(json.dumps(_jsonla(sonuc), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    gecici.replace(yol)
    return yol


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="analiz.py", description=__doc__.splitlines()[0])
    p.parse_args(argv)
    con = kaynak.baglan()
    try:
        sonuc = kur(con)
    finally:
        con.close()
    print(f"yazıldı: {yaz(sonuc)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
