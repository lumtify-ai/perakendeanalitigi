"""Koşusuz veri analizi: raporun VERİ bölümünün yayımlanan veriden ölçümleri (`cikti/analiz.json`).

    cd vakalar/markdown
    PYTHONIOENCODING=utf-8 .venv/Scripts/python analiz.py                  # TAM: yayımlanan DuckDB → cikti/analiz.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python analiz.py --olcek KUCUK    # cikti/kucuk/analiz.json

Ölçüm tarafıdır (paket dışında, vaka kökünde; `rapor.py` gibi). Hiçbir sayı elle konmaz: hepsi tablolardan
SQL'le ölçülür (spec §0 keşif olguları; rapor yeniden basar). Kaynak TAM'da yayımlanan v4 DuckDB'si
(`kaynak.baglan()`; analistin gördüğü veri, yayımlamanın birkaç kirli kaydıyla), KÜÇÜK'te yol 0 Lumoda
koşusunun yayımlanan biçimi (geçici DuckDB dosyası, `oyun.Yol._baglanti`; koşu önbellekte olmalı, analiz
simülasyon başlatmaz). Gizli gerçek okunmaz.

**Tanım (Ruling R21).** Yazıların markdown TL'si, outlet indirimi, çıkışta kalanı, ölü stoğu ve STR çeyrekleri
`olcutler`'in tanımıdır: her sezonun `olcutler` bloğu yol 0 Lumoda koşusunda `olcutler.option_tablosu` / `ozetle` /
`ceyrek` ile ölçülür (YOL 0'ın Lumoda'sıyla aynı işlev, aynı koşu; rapor eşitliği korunumla sınar). Yol 0 Lumoda'sı
yayımlanan v4'ün temiz hâlidir (eşdeğerlik testi). Option tablosunun `md_ind` / `outlet_indirim` sütunları başka bir
tanımdır (keşif tanımı: indirim dönemi penceresi ve mağaza tipi; yazıda kullanılmaz).

**Sezonlar** (`analiz_sezonlari`): `sezon` tablosunda lansmanı verinin ilk gününden sonra, çıkış + 120'si
verinin son gününden önce olan sezonlar (TAM: SS23, AW23, SS24, AW24, SS25); test sezonları rapora tam,
öbürleri "beş sezonda" aralıklarına girer.

**Option tablosu** (`option_tablosu`; sezonun Collection option'ları; dalga başına lansman L, sezonun
indirimi I ve çıkışı C `sezon` tablosundan):

    arz_ilk, arz_rpt          teslim edilmiş (`gerceklesen_teslim` dolu) ilk / RPT sipariş adedi (olcutler `arz`)
    satis_tam                 pozitif satış, gün < I − 28 (Lumoda'nın indirim penceresinden önce)
    satis_erken               pozitif satış, I − 28 ≤ gün < I (Lumoda'nın erken indirim penceresi)
    satis_once                pozitif satış, gün < I (indirim başı STR'nin payı)
    satis_ind, ciro_ind       indirim dönemi I ≤ gün < C: pozitif adet; net ciro (Σ tutar, iade dahil)
    md_ind, kampanya_ind      keşif tanımı: indirim dönemi, pozitif, outlet mağazası dışı, kampanyasız /
                              kampanyalı Σ indirim (olcutler `markdown_tl` DEĞİL: o lansman → çıkış, oran > 0,
                              normal + online hat); `md_ind_net` iade satırları dahil (spec §0'ın 43,0 M'ı)
    brut_ind, liste_ind       indirim dönemi pozitif satırların Σ tutarı ve Σ adet × liste (fiyat payı)
    kalan_magaza, kalan_depo  C − 7 pazartesisinin `stok` ve `depo_stok` fotoğrafı (adet; × liste, × alış)
    outlet_akisi              `sevkiyat` tip `outlet_akisi` adedi
    outlet_satis, outlet_ciro outlet mağazalarında C ≤ gün < C + 84: pozitif adet, net ciro, Σ indirim
                              (keşif tanımı; `outlet_indirim` pozitif satırlar, `outlet_indirim_net` iade dahil)
    olu_stok                  `depo_stok`, min(C + 120, son gün) (adet, × alış)
    en_derin, ilk_md          `fiyat` normal hattı, haftası C'den önce: en derin oran, ilk oranlı hafta
    rpt_gec_adet              RPT, teslimi ≥ I − 28 (adet; ≥ 1 ise option sayılır)

**Bloklar** (`analiz.json` `sezonlar[sezon]`): `huni` (toplamlar), `kademe` (en derin oranın dağılımı:
oran → option sayısı; `erken_indirilen` I'dan önce oranı olan option), `str` (indirim başı STR = 100 ×
satis_once ÷ arz: p10 / p50 / p90; çeyrekler `olcutler.ceyrek`'in kuralıyla: STR, eşitlikte option_id,
`ceil(4 · sıra ÷ n)`; çeyrek başına option, STR aralığı, kalan, kalanın payı, indirim dönemi markdown TL,
ölü stok), `haftalik` (I − 56'nın haftasından çıkış haftasına pazartesi haftaları: pozitif satış;
`hafta` indirim haftasına göre), `olcutler` (yukarıda: ölçütler, STR p10/p50/p90, çeyrekler, alt yarının
kalan payı).

`kod`: analizi belirleyen kodun özeti (bu dosya, `markdown/kaynak.py`, `sabitler.py`, `olcutler.py`); rapor
eski analizi reddeder.
"""

import argparse
import hashlib
import json
import math
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from markdown import kaynak, olcutler, oyun, sabitler, simulasyon

KOK = Path(__file__).resolve().parent
SURUM = 1
OUTLET_GUN = 84
OLU_STOK_GUN = 120
CIKIS_FOTO_GUN = 7
LUMODA_ONCE_GUN = 28        # Lumoda'nın kuralı indirim − 28'den başlar (LumodaMarkdown)
HAFTALIK_ONCE_GUN = 56      # haftalık eğri indirimden 8 hafta önce başlar (serbest pencere)


class Eksik(RuntimeError):
    """Analizin dayandığı koşu önbellekte yok: analiz simülasyon başlatmaz (stderr, çıkış 1)."""


def hedef(olcek: str = "tam") -> Path:
    return (oyun.CIKTI if olcek == "tam" else oyun.CIKTI / "kucuk") / "analiz.json"


def kod_ozeti() -> str:
    """Analizi belirleyen kodun özeti (LF)."""
    h = hashlib.sha256()
    for y in (Path(__file__).resolve(), *(simulasyon.PAKET_KOKU / f"{m}.py" for m in ("kaynak", "sabitler", "olcutler"))):
        h.update(y.name.encode() + b"\0" + y.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Sorgular
# ---------------------------------------------------------------------------


def _u(sezon: str) -> str:
    """Sezonun Collection SKU'ları ve option günleri (DATE)."""
    s = sezon.replace("'", "")
    return f"""
    u as (
      select u.urun_id::varchar as urun_id, u.option_id::varchar as option_id, u.dalga,
             u.liste_fiyati as liste, u.alis_fiyati as alis, u.ust_kategori::varchar as ust_kategori,
             u.alt_kategori::varchar as alt_kategori,
             cast(z.lansman_tarihi as date) as L, cast(z.indirim_baslangic as date) as I,
             cast(z.cikis_tarihi as date) as C
      from urun u join sezon z on z.sezon_kodu::varchar = u.sezon_kodu::varchar and z.dalga = u.dalga
      where u.line::varchar = '{sabitler.LINE}' and u.sezon_kodu::varchar = '{s}'
    )"""


def veri_sinirlari(con) -> tuple[pd.Timestamp, pd.Timestamp]:
    a, b = con.execute("select min(tarih), max(tarih) from satis").fetchone()
    return pd.Timestamp(a).normalize(), pd.Timestamp(b).normalize()


def analiz_sezonlari(con) -> list[str]:
    """Lansmanı verinin içinde ve çıkış + 120'si son günden önce olan sezonlar (çıkış sırasıyla)."""
    bas, son = veri_sinirlari(con)
    z = con.execute("select sezon_kodu::varchar as s, min(lansman_tarihi) as l, max(cikis_tarihi) as c "
                    "from sezon group by 1").df()
    z = z[(pd.to_datetime(z["l"]) >= bas) & (pd.to_datetime(z["c"]) + np.timedelta64(OLU_STOK_GUN, "D") <= son)]
    return list(z.sort_values("c")["s"])


def option_tablosu(con, sezon: str) -> pd.DataFrame:
    """Sezonun Collection option'ları başına bileşenler (modül notu)."""
    _, son = veri_sinirlari(con)
    son_s = son.date().isoformat()
    sql = f"""
    with {_u(sezon)},
    sat as (
      select u.option_id, s.tarih::date as t, s.adet, s.tutar, s.indirim_tutari, s.kampanya_id,
             m.tip::varchar as mtip, u.liste, u.I, u.C
      from satis s join u on s.urun_id::varchar = u.urun_id
      join magaza m on m.magaza_id::varchar = s.magaza_id::varchar
    ),
    sa as (
      select option_id,
        sum(case when adet > 0 and t < I - interval 28 day then adet else 0 end) as satis_tam,
        sum(case when adet > 0 and t >= I - interval 28 day and t < I then adet else 0 end) as satis_erken,
        sum(case when adet > 0 and t < I then adet else 0 end) as satis_once,
        sum(case when adet > 0 and t >= I and t < C then adet else 0 end) as satis_ind,
        sum(case when t >= I and t < C then tutar else 0 end) as ciro_ind,
        sum(case when adet > 0 and t >= I and t < C and mtip <> 'Outlet' and kampanya_id is null
                 then indirim_tutari else 0 end) as md_ind,
        sum(case when t >= I and t < C and mtip <> 'Outlet' and kampanya_id is null
                 then indirim_tutari else 0 end) as md_ind_net,
        sum(case when adet > 0 and t >= I and t < C and mtip <> 'Outlet' and kampanya_id is not null
                 then indirim_tutari else 0 end) as kampanya_ind,
        sum(case when adet > 0 and t >= I and t < C then tutar else 0 end) as brut_ind,
        sum(case when adet > 0 and t >= I and t < C then adet * liste else 0 end) as liste_ind,
        sum(case when adet > 0 and mtip = 'Outlet' and t >= C and t < C + interval {OUTLET_GUN} day
                 then adet else 0 end) as outlet_satis,
        sum(case when mtip = 'Outlet' and t >= C and t < C + interval {OUTLET_GUN} day
                 then tutar else 0 end) as outlet_ciro,
        sum(case when adet > 0 and mtip = 'Outlet' and t >= C and t < C + interval {OUTLET_GUN} day
                 then tutar else 0 end) as outlet_brut,
        sum(case when adet > 0 and mtip = 'Outlet' and t >= C and t < C + interval {OUTLET_GUN} day
                 then adet * liste else 0 end) as outlet_liste,
        sum(case when adet > 0 and mtip = 'Outlet' and t >= C and t < C + interval {OUTLET_GUN} day
                 then indirim_tutari else 0 end) as outlet_indirim,
        sum(case when mtip = 'Outlet' and t >= C and t < C + interval {OUTLET_GUN} day
                 then indirim_tutari else 0 end) as outlet_indirim_net
      from sat group by 1
    ),
    ar as (
      select u.option_id,
        sum(case when s.tip::varchar = 'ilk' then s.adet else 0 end) as arz_ilk,
        sum(case when s.tip::varchar = 'rpt' then s.adet else 0 end) as arz_rpt,
        sum(s.adet * u.alis) as arz_alis,
        sum(case when s.tip::varchar = 'rpt' and cast(s.gerceklesen_teslim as date) >= u.I - interval 28 day
                 then s.adet else 0 end) as rpt_gec_adet
      from siparis s join u on s.urun_id::varchar = u.urun_id
      where s.tip::varchar in ('ilk', 'rpt') and s.gerceklesen_teslim is not null group by 1
    ),
    km as (
      select u.option_id, sum(k.adet) as kalan_magaza, sum(k.adet * u.liste) as kalan_magaza_liste,
             sum(k.adet * u.alis) as kalan_magaza_alis
      from stok k join u on k.urun_id::varchar = u.urun_id
      where k.tarih::date = u.C - interval {CIKIS_FOTO_GUN} day group by 1
    ),
    kd as (
      select u.option_id, sum(k.adet) as kalan_depo, sum(k.adet * u.liste) as kalan_depo_liste,
             sum(k.adet * u.alis) as kalan_depo_alis
      from depo_stok k join u on k.urun_id::varchar = u.urun_id
      where k.tarih::date = u.C - interval {CIKIS_FOTO_GUN} day group by 1
    ),
    ol as (
      select u.option_id, sum(k.adet) as olu_stok, sum(k.adet * u.alis) as olu_stok_alis
      from depo_stok k join u on k.urun_id::varchar = u.urun_id
      where k.tarih::date = least(u.C + interval {OLU_STOK_GUN} day, date '{son_s}') group by 1
    ),
    oa as (
      select u.option_id, sum(v.adet) as outlet_akisi
      from sevkiyat v join u on v.urun_id::varchar = u.urun_id
      where v.tip::varchar = 'outlet_akisi' group by 1
    ),
    fo as (
      select f.option_id::varchar as option_id, max(f.indirim_orani) as en_derin,
             min(case when f.indirim_orani > 0 then f.hafta_baslangic::date end) as ilk_md
      from fiyat f join (select distinct option_id, C from u) o on f.option_id::varchar = o.option_id
      where f.hat::varchar = 'normal' and f.hafta_baslangic::date < o.C group by 1
    ),
    op as (select option_id, any_value(dalga) as dalga, any_value(liste) as liste,
                  any_value(ust_kategori) as ust_kategori, any_value(alt_kategori) as alt_kategori,
                  any_value(L) as L, any_value(I) as I, any_value(C) as C from u group by 1)
    select * from op left join ar using (option_id) left join sa using (option_id)
      left join km using (option_id) left join kd using (option_id) left join ol using (option_id)
      left join oa using (option_id) left join fo using (option_id)
    order by option_id
    """
    t = con.execute(sql).df()
    sayi = [c for c in t.columns if c not in ("option_id", "ust_kategori", "alt_kategori", "L", "I", "C",
                                                "ilk_md", "en_derin")]
    t[sayi] = t[sayi].fillna(0).astype(float)
    t["en_derin"] = t["en_derin"].fillna(0.0).astype(float)
    for c in ("L", "I", "C", "ilk_md"):
        t[c] = pd.to_datetime(t[c])
    t["arz"] = t["arz_ilk"] + t["arz_rpt"]
    return t


def haftalik(con, sezon: str) -> pd.DataFrame:
    """Sezonun Collection'ında I − 56'nın haftasından çıkış haftasına haftalık pozitif satış (hafta: indirim
    haftasına göre)."""
    sql = f"""
    with {_u(sezon)}
    select date_trunc('week', s.tarih::date) as hafta_bas, sum(s.adet) as adet
    from satis s join u on s.urun_id::varchar = u.urun_id
    where s.adet > 0 and s.tarih::date >= date_trunc('week', u.I - interval {HAFTALIK_ONCE_GUN} day)
      and s.tarih::date < u.C
    group by 1 order by 1
    """
    t = con.execute(sql).df()
    I = con.execute(f"with {_u(sezon)} select min(I) from u").fetchone()[0]
    i0 = pd.Timestamp(I) - np.timedelta64(pd.Timestamp(I).weekday(), "D")
    t["hafta_bas"] = pd.to_datetime(t["hafta_bas"])
    t["hafta"] = ((t["hafta_bas"] - i0).dt.days // 7).astype(int)
    return t


# ---------------------------------------------------------------------------
# Bloklar
# ---------------------------------------------------------------------------


def _toplam(t: pd.DataFrame, c: str) -> float:
    return float(t[c].sum())


def huni(t: pd.DataFrame) -> dict:
    h = {c: _toplam(t, c) for c in ("arz_ilk", "arz_rpt", "arz", "arz_alis", "satis_tam", "satis_erken",
                                    "satis_once", "satis_ind", "ciro_ind", "md_ind", "md_ind_net", "kampanya_ind", "brut_ind",
                                    "liste_ind", "kalan_magaza", "kalan_depo", "outlet_akisi", "outlet_satis",
                                    "outlet_ciro", "outlet_brut", "outlet_liste", "outlet_indirim", "outlet_indirim_net", "olu_stok",
                                    "olu_stok_alis", "rpt_gec_adet")}
    h["kalan"] = h["kalan_magaza"] + h["kalan_depo"]
    h["kalan_liste"] = _toplam(t, "kalan_magaza_liste") + _toplam(t, "kalan_depo_liste")
    h["kalan_alis"] = _toplam(t, "kalan_magaza_alis") + _toplam(t, "kalan_depo_alis")
    h["ind_fiyat_payi"] = h["brut_ind"] / h["liste_ind"] if h["liste_ind"] else None
    h["outlet_fiyat_payi"] = h["outlet_brut"] / h["outlet_liste"] if h["outlet_liste"] else None
    h["option"] = len(t)
    h["rpt_gec_option"] = int((t["rpt_gec_adet"] > 0).sum())
    h["rpt_option"] = int((t["arz_rpt"] > 0).sum())
    return h


def kademe(t: pd.DataFrame) -> dict:
    derin = t["en_derin"].round(4)
    return {"dagilim": {f"{x:.2f}": int(n) for x, n in derin.value_counts().sort_index().items()},
            "erken_indirilen": int((t["ilk_md"].notna() & (t["ilk_md"] < t["I"])).sum()),
            "lumoda_oncesi_indirilen": int((t["ilk_md"].notna()
                                            & (t["ilk_md"] < t["I"] - np.timedelta64(LUMODA_ONCE_GUN, "D"))).sum())}


def ceyrek_etiketi(str_: np.ndarray, option_id: np.ndarray) -> np.ndarray:
    """1 en düşük STR, 4 en yüksek; sıralama STR, eşitlikte option_id; `ceil(4 · sıra ÷ n)` (olcutler.ceyrek)."""
    sira = pd.DataFrame({"str": str_, "id": option_id}).sort_values(["str", "id"]).index.to_numpy()
    rank = np.empty(len(str_), dtype=np.int64)
    rank[sira] = np.arange(1, len(str_) + 1)
    return np.ceil(4 * rank / max(len(str_), 1)).astype(np.int64)


def str_blogu(t: pd.DataFrame) -> dict:
    arz = t["arz"].to_numpy(dtype=float)
    s = np.divide(100.0 * t["satis_once"].to_numpy(dtype=float), arz, out=np.zeros(len(t)), where=arz > 0)
    q = ceyrek_etiketi(s, t["option_id"].to_numpy())
    kalan = (t["kalan_magaza"] + t["kalan_depo"]).to_numpy(dtype=float)
    toplam_kalan = float(kalan.sum())
    ceyrekler = []
    for c in range(1, 5):
        m = q == c
        ceyrekler.append({"ceyrek": c, "option": int(m.sum()), "str_alt": float(s[m].min()) if m.any() else None,
                          "str_ust": float(s[m].max()) if m.any() else None,
                          "str_ort": float(100.0 * t["satis_once"][m].sum() / arz[m].sum()) if arz[m].sum() else None,
                          "kalan": float(kalan[m].sum()), "kalan_payi": float(kalan[m].sum() / toplam_kalan)
                          if toplam_kalan else None, "md_ind": float(t["md_ind"][m].sum()),
                          "md_ind_net": float(t["md_ind_net"][m].sum()),
                          "olu_stok": float(t["olu_stok"][m].sum()), "arz": float(arz[m].sum())})
    return {"p10": float(np.percentile(s, 10)), "p50": float(np.percentile(s, 50)), "p90": float(np.percentile(s, 90)),
            "ceyrekler": ceyrekler,
            "alt_yari_kalan_payi": float(kalan[q <= 2].sum() / toplam_kalan) if toplam_kalan else None,
            "option_str": {str(o): float(x) for o, x in zip(t["option_id"], s)}}


def sezon_blogu(con, sezon: str) -> dict:
    t = option_tablosu(con, sezon)
    hf = haftalik(con, sezon)
    gun = {c: pd.Timestamp(t[c].min()).date().isoformat() for c in ("L", "I", "C")}
    return {"gunler": {"lansman_ilk": gun["L"], "indirim": gun["I"], "cikis": gun["C"]},
            "huni": huni(t), "kademe": kademe(t), "str": str_blogu(t),
            "haftalik": [{"hafta": int(r.hafta), "adet": float(r.adet)} for r in hf.itertuples()]}


# ---------------------------------------------------------------------------
# Kurulum
# ---------------------------------------------------------------------------


def _lumoda_hazirlik(ortam: oyun.Ortam):
    return simulasyon.hazirla(simulasyon.lumoda_adi(0), None, 0, ortam.olcek, parametreler={}, rpt_takvimi=None,
                              gun_sayisi=ortam.gun_sayisi)


OLCUTLER_ALANLARI = ("arz_adet", "markdown_tl", "markdown_tl_online", "outlet_indirim_tl", "katki", "ciro_toplam",
                     "cikis_kalan_adet", "cikis_kalan_magaza_adet", "cikis_kalan_depo_adet", "cikis_kalan_liste",
                     "cikis_kalan_alis", "olu_stok_adet", "olu_stok_alis", "option_sayisi")


def olcutler_blogu(kosu, w, sezon: str) -> dict:
    """Yol 0 Lumoda koşusunun `sezon` ölçütleri `olcutler`'in kendi işlevleriyle (YOL 0'ın tanımı; Ruling R21):
    ölçütler (`OLCUTLER_ALANLARI`), indirim başı STR'si (p10 / p50 / p90) ve çeyrekleri (`olcutler.ceyrek`: kalan,
    kalanın payı, markdown TL, ölü stok), alt yarının kalan payı."""
    t = olcutler.option_tablosu(kosu, w, sezon)
    o = olcutler.ozetle(t)
    st = olcutler.indirim_basi_str(kosu, w, sezon, tablo=t)
    c = olcutler.ceyrek(kosu, w, sezon, st, tablo=t)
    kalan = float(c["cikis_kalan_adet"].sum())
    ceyrekler = [{"ceyrek": int(r.ceyrek), "option": int(r.option_sayisi), "str_alt": float(r.str_alt),
                  "str_ust": float(r.str_ust), "kalan": float(r.cikis_kalan_adet), "kalan_payi": float(r.cikis_kalan_adet) / kalan if kalan else None,
                  "markdown_tl": float(r.markdown_tl), "olu_stok": float(r.olu_stok_adet), "katki": float(r.katki),
                  "arz": float(r.arz_adet)} for r in c.itertuples()]
    v = st.to_numpy(dtype=float)
    return {"olcutler": {a: float(o[a]) for a in OLCUTLER_ALANLARI}, "ceyrekler": ceyrekler,
            "str": {"p10": float(np.percentile(v, 10)), "p50": float(np.percentile(v, 50)),
                    "p90": float(np.percentile(v, 90))},
            "alt_yari_kalan_payi": float(sum(r["kalan"] for r in ceyrekler[:2]) / kalan) if kalan else None}


def kur(ortam: oyun.Ortam, con=None) -> dict:
    """analiz.json'un içeriği. Yayımlanan veri TAM'da yayımlanan DuckDB, KÜÇÜK'te yol 0 Lumoda koşusunun yayımlanan
    biçimi; `olcutler` blokları yol 0 Lumoda koşusundan (önbellekte değilse `Eksik`, analiz simülasyon başlatmaz).
    `con` verilirse (testler) yalnız onu okur, `olcutler` bloğu kurulmaz."""
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="markdown_analiz_") as dizin:
        kapat, Y, lumoda_anahtar, kaynak_adi = con is None, None, None, "verilen"
        if con is None:
            h = _lumoda_hazirlik(ortam)
            if not simulasyon.onbellekte_mi(h, ortam.onbellek):
                raise Eksik(f"yol 0 Lumoda koşusu ({h.ad}_{h.anahtar[:20]}) {ortam.onbellek} önbelleğinde yok: "
                            "analiz simülasyon başlatmaz; önce python -m markdown.oyun izgara --blok yol0")
            Y = oyun.Yol(0, ortam)
            con, _ = Y._baglanti(Path(dizin))
            lumoda_anahtar = Y.lumoda.meta["anahtar"]
            kaynak_adi = "yayimlanan" if ortam.yayimlanan_mi(0) else f"vaka:{Y.lumoda.dizin.name}"
        try:
            sezonlar = analiz_sezonlari(con)
            bas, son = veri_sinirlari(con)
            bloklar = {s: sezon_blogu(con, s) for s in sezonlar}
        finally:
            if kapat:
                con.close()
        if Y is not None:
            for s in sezonlar:
                bloklar[s]["olcutler"] = olcutler_blogu(Y.lumoda, Y.w, s)
    print(f"analiz: {time.perf_counter() - t0:.0f} sn", file=sys.stderr, flush=True)
    return {"surum": SURUM, "olcek": ortam.olcek, "kod": kod_ozeti(), "kaynak": kaynak_adi,
            "lumoda_anahtar": lumoda_anahtar, "veri": {"ilk_gun": bas.date().isoformat(), "son_gun": son.date().isoformat()},
            "analiz_sezonlari": sezonlar, "sezonlar": bloklar}


def _jsonla(x):
    if isinstance(x, dict):
        return {str(k): _jsonla(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonla(v) for v in x]
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if math.isnan(float(x)) else float(x)
    return x


def yaz(sonuc: dict, yol: Path) -> Path:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(_jsonla(sonuc), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return yol


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="analiz.py", description=__doc__.splitlines()[0])
    p.add_argument("--olcek", default="TAM", type=str.upper, choices=["TAM", "KUCUK"])
    a = p.parse_args(argv)
    ortam = oyun._ortam(a.olcek)
    ortam = oyun.Ortam(olcek=ortam.olcek, cikti=ortam.cikti, ilerleme=False)
    try:
        sonuc = kur(ortam)
    except Eksik as e:
        print(f"Eksik: {e}", file=sys.stderr)
        return 1
    print(f"yazıldı: {yaz(sonuc, hedef(ortam.olcek))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
