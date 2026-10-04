"""Yok-satma dizisinin yayımlanacak BÜTÜN sayıları buradan basılır (spec §6.1).

    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt

Kalıcı kural: yazıya yeni bir sayı girmeden önce buraya eklenir;
`sayi_denetimi.py` yazılardaki her sayının bu çıktıda geçtiğini denetler.
Sayılar Türkçe basılır (binlik nokta, ondalık virgül, `%12,3`, `−%3,2`).

Bölümler (bu başlıklarla, bu sırayla):

    === VERİ ===       yeniden kurmanın doğrulaması; yıl × kanal × durum gün sayıları
    === HİKÂYE ===     `hikaye_sec`in seçimi (ya da `--hikaye` ile elle, R24), line başına ilk
                       üç aday (tedarik payı, iki SKU'nun λ̂'sı); seçilen option'ın stoksuzluk
                       dönemi, kaybı (Basit), iki SKU'nun o günkü kaynağı, hakemden ikame /
                       kalıcı ayrışımı (AYRIŞIM'la aynı küme)
    === ÇARPANLAR ===  hafta günü (kanal), özel gün, ε̂ kampanya ve markdown (üst kategori)
    === KESTİRİM ===   2025; üç kestirici × WAPE ve yanlılık × düzey ve kırılım;
                       tükenen gün `kayip` / `kayip_saf`
    === AYRIŞIM ===    2025; tahmin · karşılanmayan · ikameye giden · kalıcı; çeşit dışı
    === LUMODA ===     Basit; 2023–2025 × kanal: kayıp adet, TL, net ciroya oranı, brüt marj;
                       line başına; 2025 son tükeniş (Basit ve hakem yan yana)
    === AĞAÇ ===       Basit; kaynak dalı × kanal: adet ve TL payları

Elle hikâye: `--hikaye OPTION_ID,MAGAZA_ID,YYYY-MM-DD` seçimi o adaya çevirir;
sıkı aramanın adayı değilse tutmadığı ölçütler basılır (`hikaye_sec.denetle`),
o gün o mağazada option'ın `bos` bedeni yoksa çıkış kodu 2.

Girdiler: `hazirla` çıktıları (`cikti/`), hakem önbelleği
(`vakalar/ortak/cikti/hakem/`) ve v4 DuckDB. Biri eksikse hangi komutun
koşulacağı stderr'e yazılır, çıkış kodu 2.

Rapor yalnız ölçer (R15): hiçbir kestirici burada ayarlanmaz. Gizli gerçek
(hakem) yalnız `degerlendir` ölçütlerine ve HİKÂYE'deki ikame / kalıcı
ayrışımına girer.

Korunum: groupby'lar NaN anahtarlı satırları sessizce düşürür (`kayip.ozet`,
`degerlendir`). Her kırılımın toplamı (Σ tahmin, Σ karşılanmayan, Σ adet, TL,
marj) bütünün toplamıyla karşılaştırılır; tutmazsa `KorunumHatasi` (rapor
durur).
"""

import argparse
import json
import pickle
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
import pyarrow.parquet as pq

from perakende_analitik import agac, degerlendir, hakem, kayip, kaynak, ozellikler
from perakende_analitik.carpanlar import OZEL_GUNLER
from yok_satma import hazirla, hikaye_sec

KESTIRICILER = ("naif", "basit", "ml")
AD = {"naif": "Naif", "basit": "Basit", "ml": "ML"}
YILLAR = (2023, 2024, 2025)
OLCUM_YILI = 2025
KANALLAR = ("magaza", "online")
HAZIRLA_KOMUTU = "cd vakalar/yok-satma && .venv/Scripts/python -m yok_satma.hazirla"
HAKEM_KOMUTU = "cd vakalar/ortak && .venv/Scripts/python -m perakende_analitik.hakem"
HAKEM_DOSYALARI = ("karsilanmayan.parquet", "ikame_alinan.parquet", "meta.json")
GUNLER = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
DUZEYLER = {"mağaza × option × hafta": ["magaza_id", "option_id", "hafta"],
            "zincir × hafta": ["hafta"], "toplam": []}
_TOLERANS = 1e-9          # korunum: göreli
_GB = 1024 ** 3


# ---------------------------------------------------------------------
# Biçim
# ---------------------------------------------------------------------

def _yok(x) -> bool:
    return x is None or (isinstance(x, (float, np.floating)) and np.isnan(x))


def s(x, ondalik: int = 0) -> str:
    """Türkçe sayı: 1.234.567 · 0,55 · −3,2."""
    if _yok(x):
        return "—"
    metin = f"{float(x):,.{ondalik}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return metin.replace("-", "−")


def y(x, ondalik: int = 1) -> str:
    """Yüzde: 0,123 → %12,3; negatif → −%3,2."""
    if _yok(x):
        return "—"
    return ("−%" if x < 0 else "%") + s(abs(100 * x), ondalik)


def yi(x, ondalik: int = 1) -> str:
    """İşaretli yüzde (yanlılık): +%2,7 · −%3,2."""
    if _yok(x):
        return "—"
    return ("+" if x > 0 else "") + y(x, ondalik)


def mn(x, ondalik: int = 1) -> str:
    """Milyon: 3.456.789 → 3,5 milyon."""
    return "—" if _yok(x) else f"{s(x / 1e6, ondalik)} milyon"


_BIRLER = {1: "'inde", 2: "'sinde", 3: "'ünde", 4: "'ünde", 5: "'inde", 6: "'sında",
           7: "'sinde", 8: "'inde", 9: "'unda"}
_ONLAR = {1: "'unda", 2: "'sinde", 3: "'unda", 4: "'ında", 5: "'sinde", 6: "'ında",
          7: "'inde", 8: "'inde", 9: "'ında"}


def bulunma(n) -> str:
    """Sayı + bulunma eki, okunuşun son kelimesine göre: 20'sinde, 24'ünde, 1.000'inde."""
    n = abs(int(n))
    if n == 0:
        ek = "'ında"                       # sıfır
    elif n % 10:
        ek = _BIRLER[n % 10]
    elif n % 100:
        ek = _ONLAR[n % 100 // 10]
    elif n % 1000:
        ek = "'ünde"                       # yüz
    elif n % 1_000_000:
        ek = "'inde"                       # bin
    elif n % 1_000_000_000:
        ek = "'unda"                       # milyon
    else:
        ek = "'ında"                       # milyar
    return s(n) + ek


def t_(tarih) -> str:
    return pd.Timestamp(tarih).strftime("%Y-%m-%d") if tarih is not None and pd.notna(tarih) else "—"


def baslik(ad: str, aciklama: str = "") -> None:
    print()
    print(f"=== {ad} ===")
    if aciklama:
        print(aciklama)


def alt(metin: str) -> None:
    print()
    print(f"--- {metin} ---")


# ---------------------------------------------------------------------
# Korunum
# ---------------------------------------------------------------------

class KorunumHatasi(AssertionError):
    """Bir kırılımın toplamı bütünün toplamını tutmuyor (düşen satır var)."""


def korunum(ad: str, parca: float, butun: float) -> None:
    """`parca` (kırılımların toplamı) `butun`e göreli 1e-9 içinde eşit değilse hata."""
    parca, butun = float(parca), float(butun)
    if not abs(parca - butun) <= _TOLERANS * max(1.0, abs(butun)):
        raise KorunumHatasi(f"korunum tutmuyor: {ad}: kirilimlarin toplami {parca!r}, "
                            f"butun {butun!r} (fark {parca - butun!r})")


# ---------------------------------------------------------------------
# Girdiler
# ---------------------------------------------------------------------

def eksikler(cikti: Path, hakem_dizini: Path) -> list[str]:
    """Eksik girdi dosyaları ve üreten komutlar (boşsa hepsi var)."""
    mesaj = []
    yok = [d for d in hazirla.DOSYALAR.values() if not (cikti / d).exists()]
    if yok:
        mesaj.append(f"{cikti} icinde {', '.join(yok)} yok. Once koşun: {HAZIRLA_KOMUTU}")
    yok = [d for d in HAKEM_DOSYALARI if not (hakem_dizini / d).exists()]
    if yok:
        mesaj.append(f"{hakem_dizini} icinde {', '.join(yok)} yok. Once koşun: {HAKEM_KOMUTU}")
    return mesaj


def _parquet(yol: Path) -> str:
    """DuckDB içinde parquet okuma ifadesi."""
    return "read_parquet('" + Path(yol).resolve().as_posix().replace("'", "''") + "')"


def _yil_araligi(yil: int) -> list[tuple]:
    return [("tarih", ">=", pd.Timestamp(f"{yil}-01-01")),
            ("tarih", "<=", pd.Timestamp(f"{yil}-12-31"))]


def _kanal(magaza_id: pd.Series) -> np.ndarray:
    return np.where(magaza_id.astype(str).to_numpy() == "ONL", "online", "magaza")


# ---------------------------------------------------------------------
# VERİ
# ---------------------------------------------------------------------

def _haftalik_korunum(con, satis: str) -> tuple[int, int]:
    """S(pzt) + varış − çıkış − net satış (pzt..paz) = S(pzt + 7) tutan / bütün hücre-hafta."""
    return con.execute(f"""
        with
        s as (select magaza_id::varchar m, urun_id::varchar u, tarih::date p, adet from stok),
        v as (select hedef::varchar m, urun_id::varchar u,
                     date_trunc('week', varis_tarihi::date)::date p, sum(adet) n
              from sevkiyat where varis_tarihi is not null group by 1, 2, 3),
        c as (select kaynak::varchar m, urun_id::varchar u,
                     date_trunc('week', tarih::date)::date p, sum(adet) n
              from sevkiyat group by 1, 2, 3),
        a as (select magaza_id::varchar m, urun_id::varchar u,
                     date_trunc('week', tarih::date)::date p, sum(adet) n
              from {satis} group by 1, 2, 3)
        select count(*) filter (where b.adet = s.adet + coalesce(v.n, 0) - coalesce(c.n, 0)
                                              - coalesce(a.n, 0)),
               count(*)
        from s join s b on b.m = s.m and b.u = s.u and b.p = s.p + 7
        left join v on v.m = s.m and v.u = s.u and v.p = s.p
        left join c on c.m = s.m and c.u = s.u and c.p = s.p
        left join a on a.m = s.m and a.u = s.u and a.p = s.p
    """).fetchone()


def _stoklu_gun_eslesmesi(con, gunluk: Path) -> pd.DataFrame:
    """Tam 7 günü uygun hücre-haftalarda `durum <> bos` gün sayısı = ertesi pazartesinin `stoklu_gun`ü."""
    return con.execute(f"""
        with h as (
            select magaza_id m, urun_id u, date_trunc('week', tarih::date)::date p,
                   count(*) filter (where durum <> 'bos') sg
            from {_parquet(gunluk)} where magaza_id <> 'ONL'
            group by 1, 2, 3 having count(*) = 7)
        select year(h.p) as yil, count(*) filter (where h.sg = s.stoklu_gun) as uyan,
               count(*) as toplam
        from h join stok s on s.magaza_id::varchar = h.m and s.urun_id::varchar = h.u
                          and s.tarih::date = h.p + 7
        group by 1 order by 1
    """).fetchdf()


def _depo_zinciri(con) -> tuple[int, int]:
    """Teslimsiz günlerde depo_stok(d+1) = depo_stok(d) + varış − çıkış − online net satış."""
    satis = kaynak.temiz_satis(con)
    return con.execute(f"""
        with
        ds as (select urun_id::varchar u, tarih::date d, adet from depo_stok),
        teslim as (select distinct urun_id::varchar u, gerceklesen_teslim::date d
                   from siparis where gerceklesen_teslim is not null),
        varis as (select urun_id::varchar u, varis_tarihi::date d, sum(adet) n
                  from sevkiyat where hedef::varchar = 'DEPO' and varis_tarihi is not null
                  group by 1, 2),
        cikis as (select urun_id::varchar u, tarih::date d, sum(adet) n
                  from sevkiyat where kaynak::varchar = 'DEPO' group by 1, 2),
        onl as (select urun_id::varchar u, tarih::date d, sum(adet) n
                from {satis} where magaza_id::varchar = 'ONL' group by 1, 2)
        select count(*) filter (where b.adet = a.adet + coalesce(v.n, 0) - coalesce(c.n, 0)
                                              - coalesce(o.n, 0)),
               count(*)
        from ds a
        join ds b on b.u = a.u and b.d = a.d + 1
        left join varis v on v.u = a.u and v.d = a.d
        left join cikis c on c.u = a.u and c.d = a.d
        left join onl o on o.u = a.u and o.d = a.d
        where not exists (select 1 from teslim t where t.u = a.u and t.d = a.d)
    """).fetchone()


def veri_bolumu(con, cikti: Path) -> None:
    baslik("VERİ", "Yeniden kurmanın doğrulaması (spec §3) ve uygun hücre-gün sayıları.")
    gunluk = cikti / "gunluk.parquet"

    alt("Haftalık stok korunumu (mağaza, bütün hücre-haftalar)")
    print("  S(pzt) + Σ varış − Σ çıkış − Σ net satış (pzt..paz) = S(ertesi pzt);"
          " ertesi pazartesi fotoğrafı olan her hücre-hafta")
    for ad, tablo in (("temiz_satis (mükerrer satır ayıklanmış)", kaynak.temiz_satis(con)),
                      ("ham satis (mükerrer satır dahil)", "satis")):
        uyan, toplam = _haftalik_korunum(con, tablo)
        print(f"  {ad}: {s(uyan)} / {s(toplam)} = {y(uyan / toplam if toplam else np.nan, 4)}"
              f"; tutmayan {s(toplam - uyan)} hücre-hafta")

    alt("Günlük durumun stoklu_gun ile eşleşmesi (mağaza)")
    print("  tam 7 günü uygun hücre-hafta: `durum` ≠ bos gün sayısı = ertesi pazartesinin stoklu_gun'ü")
    es = _stoklu_gun_eslesmesi(con, gunluk)
    for r in es.itertuples():
        print(f"  {r.yil}: {s(r.uyan)} / {s(r.toplam)} = {y(r.uyan / r.toplam, 4)}")
    if len(es):
        u, t = int(es["uyan"].sum()), int(es["toplam"].sum())
        print(f"  toplam: {s(u)} / {s(t)} = {y(u / t, 4)}; tutmayan {s(t - u)}")

    alt("Online: depo zinciri (teslimsiz günler)")
    print("  depo_stok(d+1) = depo_stok(d) + Σ varış(DEPO) − Σ çıkış(DEPO) − online net satış(d);"
          " tedarikçi teslimi olan SKU-günler hariç (hatalı adet yayımlanmaz)")
    uyan, toplam = _depo_zinciri(con)
    print(f"  {s(uyan)} / {s(toplam)} SKU-gün = {y(uyan / toplam if toplam else np.nan, 4)}"
          f"; tutmayan {s(toplam - uyan)}")

    alt("Uygun hücre-gün sayıları (yıl × kanal × durum)")
    print("  bos: satış öncesi stok ≤ 0 · tukenen: stok > 0 ve brüt satış ≥ stok · stoklu: diğerleri")
    say = con.execute(f"""
        select year(tarih) as yil,
               case when magaza_id = 'ONL' then 'online' else 'magaza' end as kanal,
               durum, count(*) as n
        from {_parquet(gunluk)} group by 1, 2, 3
    """).fetchdf()
    tablo = say.pivot_table(index=["yil", "kanal"], columns="durum", values="n",
                            aggfunc="sum", fill_value=0)
    for d in ("stoklu", "tukenen", "bos"):
        if d not in tablo.columns:
            tablo[d] = 0
    print(f"  {'yıl':>4s} {'kanal':7s} {'stoklu':>12s} {'tukenen':>10s} {'bos':>12s}"
          f" {'toplam':>12s} {'stoksuz payı':>12s} {'bos payı':>9s}")

    def satir(etiket_yil, etiket_kanal, r):
        top = r["stoklu"] + r["tukenen"] + r["bos"]
        print(f"  {etiket_yil:>4} {etiket_kanal:7s} {s(r['stoklu']):>12s} {s(r['tukenen']):>10s}"
              f" {s(r['bos']):>12s} {s(top):>12s}"
              f" {y((r['tukenen'] + r['bos']) / top if top else np.nan):>12s}"
              f" {y(r['bos'] / top if top else np.nan):>9s}")

    for yil in sorted(tablo.index.get_level_values(0).unique()):
        for kanal in KANALLAR:
            if (yil, kanal) in tablo.index:
                satir(yil, kanal, tablo.loc[(yil, kanal)])
        satir(yil, "toplam", tablo.loc[yil].sum())
    hepsi = tablo.sum()
    satir("hepsi", "", hepsi)

    alt("Satır sayıları")
    n_gunluk = pq.ParquetFile(gunluk).metadata.num_rows
    korunum("VERİ gun sayilari toplami = gunluk satiri",
            hepsi["stoklu"] + hepsi["tukenen"] + hepsi["bos"], n_gunluk)
    print(f"  gunluk.parquet: {s(n_gunluk)} uygun hücre-gün (stoklu dahil)")
    stoksuz = int(hepsi["tukenen"] + hepsi["bos"])
    for ad in KESTIRICILER:
        n = pq.ParquetFile(cikti / hazirla.DOSYALAR[ad]).metadata.num_rows
        korunum(f"VERİ kayip_{ad} satiri = bos + tukenen", n, stoksuz)
        print(f"  kayip_{ad}.parquet: {s(n)} satır (= bos + tukenen)")


# ---------------------------------------------------------------------
# HİKÂYE
# ---------------------------------------------------------------------

def _gecikme(planlanan, gerceklesen) -> str:
    if planlanan is None or gerceklesen is None:
        return "—"
    return s((pd.Timestamp(gerceklesen) - pd.Timestamp(planlanan)).days)


def _gun_no(tarih) -> np.ndarray:
    """Tarih(ler) -> 1970'ten gün sayısı (int64)."""
    return pd.to_datetime(pd.Series(tarih)).to_numpy().astype("datetime64[D]").astype(np.int64)


def _kosu(stoksuz: set, magaza: str, gun: pd.Timestamp) -> int:
    """`gun`de biten ardışık stoksuz gün sayısı (o gün dahil); `stoksuz` = {(mağaza, gün no)}."""
    g = int(_gun_no([gun])[0])
    n = 0
    while (magaza, g - n) in stoksuz:
        n += 1
    return n


def _secim_yazdir(con, sec: dict, aday: pd.DataFrame, gevsetilen) -> pd.DataFrame:
    urun = con.execute("select urun_id::varchar as urun_id, beden, beden_sira, model_adi, renk, "
                       "line, cinsiyet, sezon_kodu, ust_kategori, alt_kategori, liste_fiyati, "
                       "alis_fiyati from urun where option_id = ? order by beden_sira",
                       [sec["option_id"]]).fetchdf()
    magaza = con.execute("select magaza_id::varchar as magaza_id, ad, sehir, tip from magaza"
                         ).fetchdf().set_index("magaza_id")
    u = urun.set_index("urun_id")
    ilk = urun.iloc[0]
    m = magaza.loc[sec["magaza_id"]]
    print(f"  option {sec['option_id']}: {ilk['model_adi']} — {ilk['renk']} ({ilk['cinsiyet']}, "
          f"{ilk['line']}, {ilk['sezon_kodu']}, {ilk['ust_kategori']} / {ilk['alt_kategori']})")
    print(f"    liste fiyatı {s(ilk['liste_fiyati'], 2)} TL, alış {s(ilk['alis_fiyati'], 2)} TL; "
          f"bedenler: {', '.join(urun['beden'].astype(str))} ({len(urun)} SKU)")
    print(f"  Ali'nin bedeni {sec['urun_id_ali']} ({u.loc[sec['urun_id_ali'], 'beden']}), "
          f"Veli'nin bedeni {sec['urun_id_veli']} ({u.loc[sec['urun_id_veli'], 'beden']})")
    print(f"  mağaza {sec['magaza_id']} ({m['ad']}, {m['sehir']}, {m['tip']}); gün {t_(sec['tarih'])}")
    print(f"  depoya giriş {t_(sec['depoya_giris'])} (önceki gece); sipariş planlanan teslim "
          f"{t_(sec['planlanan_teslim'])}, gerçekleşen {t_(sec['gerceklesen_teslim'])} "
          f"({_gecikme(sec['planlanan_teslim'], sec['gerceklesen_teslim'])} gün geç)")
    if "planlanan_teslim_veli" in sec:
        print(f"    Veli'nin SKU'su: planlanan {t_(sec['planlanan_teslim_veli'])}, gerçekleşen "
              f"{t_(sec['gerceklesen_teslim_veli'])} "
              f"({_gecikme(sec['planlanan_teslim_veli'], sec['gerceklesen_teslim_veli'])} gün geç)")
    print(f"  stoksuzluk dönemi (R23): {t_(sec['donem_baslangic'])} .. {t_(sec['tarih'] - timedelta(days=1))}"
          f" = {s(sec['donem_gun'])} gün (iki SKU'dan birinin depoda son stoklu olduğu günün ertesinden"
          f" hikâye gününün öncesine)")
    if sec.get("elle"):
        print(f"  elle seçildi (--hikaye); tutmayan ölçütler: "
              f"{', '.join(sec['gevsetilen']) if sec['gevsetilen'] else 'yok (sıkı aramanın adayı)'}")
    print(f"  arama: {len(aday)} aday (option × mağaza × gün); gevşetilen: "
          f"{', '.join(gevsetilen) if gevsetilen else 'yok (bütün ölçütler tuttu)'}")
    return urun


def _zincir_stoksuzlugu(con, cikti: Path, sec: dict) -> None:
    gun = pd.Timestamp(sec["tarih"])
    bas = pd.Timestamp(sec["donem_baslangic"])
    df = con.execute(f"""
        select magaza_id as m, tarih as d, count(*) as n,
               count(*) filter (where durum = 'bos') as bos
        from {_parquet(cikti / 'gunluk.parquet')}
        where option_id = ? and tarih <= ? group by 1, 2
    """, [sec["option_id"], gun.to_pydatetime()]).fetchdf()
    df["d"] = pd.to_datetime(df["d"])
    fiz = df[df["m"] != "ONL"]
    donem = fiz[(fiz["d"] >= bas) & (fiz["d"] < gun)]
    print("  stoksuz = option'ın en az bir bedeni `bos` (gün satışa boş açıldı); tamamen = bütün uygun"
          " bedenleri `bos`")
    print(f"  dönemde ({s(sec['donem_gun'])} gün, fiziksel mağazalar): option'ı taşıyan "
          f"{s(donem['m'].nunique())} mağaza; stoksuz gün yaşayan {s(donem.loc[donem['bos'] > 0, 'm'].nunique())}"
          f" mağaza; stoksuz mağaza-gün {s((donem['bos'] > 0).sum())}, tamamen boş mağaza-gün "
          f"{s((donem['bos'] == donem['n']).sum())}, boş SKU-gün {s(donem['bos'].sum())}")
    o_gun = fiz[fiz["d"] == gun]
    stoksuz = set(zip(fiz.loc[fiz["bos"] > 0, "m"], _gun_no(fiz.loc[fiz["bos"] > 0, "d"]).tolist()))
    kosular = pd.Series({m: _kosu(stoksuz, m, gun) for m in o_gun.loc[o_gun["bos"] > 0, "m"]},
                        dtype="int64")
    print(f"  hikâye günü: option'ı taşıyan {s(len(o_gun))} mağazanın {bulunma((o_gun['bos'] > 0).sum())}"
          f" stoksuz, {bulunma((o_gun['bos'] == o_gun['n']).sum())} tamamen boş")
    if len(kosular):
        print(f"    kaç gündür stoksuz (o gün dahil, ardışık): medyan {s(kosular.median(), 1)}, "
              f"en çok {s(kosular.max())}, en az {s(kosular.min())} gün; seçilen mağazada "
              f"{s(kosular.get(sec['magaza_id'], 0))} gün")
    onl = df[(df["m"] == "ONL") & (df["d"] == gun)]
    if len(onl):
        print(f"    online: {s(onl['bos'].iloc[0])} / {s(onl['n'].iloc[0])} beden boş")
    iki = con.execute(f"""
        select tarih as d, count(*) filter (where durum = 'bos') as bos
        from {_parquet(cikti / 'gunluk.parquet')}
        where magaza_id = ? and urun_id in (?, ?) and tarih <= ? group by 1
    """, [sec["magaza_id"], sec["urun_id_ali"], sec["urun_id_veli"], gun.to_pydatetime()]).fetchdf()
    iki["d"] = pd.to_datetime(iki["d"])
    gerek = 1 if sec["urun_id_ali"] == sec["urun_id_veli"] else 2
    ikisi = {(sec["magaza_id"], d) for d in _gun_no(iki.loc[iki["bos"] >= gerek, "d"]).tolist()}
    print(f"    seçilen mağazada Ali'nin ve Veli'nin bedeni birlikte {s(_kosu(ikisi, sec['magaza_id'], gun))}"
          f" gündür boş (o gün dahil, ardışık)")


def _hikaye_kaybi(con, cikti: Path, kars: pd.DataFrame, sec: dict, urun: pd.DataFrame) -> None:
    gun = pd.Timestamp(sec["tarih"])
    bas = pd.Timestamp(sec["donem_baslangic"])
    k = pd.read_parquet(cikti / hazirla.DOSYALAR["basit"],
                        filters=[("option_id", "in", [sec["option_id"]])])
    donem = k[(k["tarih"] >= bas) & (k["tarih"] < gun)]
    toplam = float(donem["kayip"].sum())
    korunum("HİKÂYE donem kaybi = hikaye_sec donem_kayip", toplam, sec["donem_kayip"])
    z = kayip.ozet(donem, [], con)
    print(f"  dönem kaybı (Basit, option'ın bütün bedenleri, bütün mağazalar ve online): "
          f"{s(toplam)} adet ({s(toplam, 1)}), {s(z['kayip_tl'].sum())} TL (etiket fiyatıyla), "
          f"brüt marj {s(z['kayip_marj'].sum())} TL")
    kk = kayip.ozet(donem, ["kanal"], con)
    korunum("HİKÂYE donem kaybi kanal toplami", kk["kayip_adet"].sum(), toplam)
    for r in kk.itertuples():
        print(f"    {r.kanal}: {s(r.kayip_adet)} adet, {s(r.kayip_tl)} TL")
    kd = kayip.ozet(donem, ["kaynak"], con)
    korunum("HİKÂYE donem kaybi dal toplami", kd["kayip_adet"].sum(), toplam)
    print("    dal: " + ("; ".join(f"{r.kaynak} {s(r.kayip_adet)} adet ({y(r.kayip_adet / toplam)})"
                                   for r in kd.itertuples() if r.kayip_adet > 0) or "—"))
    o_gun = k[k["tarih"] == gun]
    print(f"  hikâye günü zincir kaybı (Basit): {s(o_gun['kayip'].sum(), 1)} adet")
    print("  iki SKU o gün (seçilen mağaza):")
    for kim, sku in (("Ali", sec["urun_id_ali"]), ("Veli", sec["urun_id_veli"])):
        r = k[(k["tarih"] == gun) & (k["magaza_id"].astype(str) == sec["magaza_id"])
              & (k["urun_id"].astype(str) == sku)]
        if r.empty:
            print(f"    {kim} {sku}: kayıp tablosunda yok")
            continue
        r = r.iloc[0]
        print(f"    {kim} {sku}: durum {r['durum']}, satış öncesi stok {s(r['satis_oncesi'])}, "
              f"λ̂ {s(r['tahmini_talep'], 2)}, kayıp {s(r['kayip'], 2)} adet; kaynak {r['kaynak']} "
              f"(fırsat {t_(r['firsat'])})")

    alt("Hikâye: hakemden ikame / kalıcı ayrışımı (gizli gerçek)")
    print("  karşılanmayan = talep − kendi satış; ikameye giden + kalıcı kayıp = karşılanmayan")
    print("  AYRIŞIM'la aynı tanım: dönemin kayıp tablosu satırları (bos + tukenen) hakemle eşleşir")
    skular = set(urun["urun_id"].astype(str))
    h = kars[kars["urun_id"].astype(str).isin(skular)].reset_index(drop=True)
    hd = h[(h["tarih"] >= bas) & (h["tarih"] < gun)]
    ayr = degerlendir.ayrisim(degerlendir.eslestir(donem, h))
    korunum("HİKÂYE ayrisim tahmin = donem kaybi", ayr["tahmin"], toplam)
    ka, ik, kl = ayr["karsilanmayan"], ayr["ikameye_giden"], ayr["kalici_kayip"]
    korunum("HİKÂYE hakem ikame + kalici = karsilanmayan", ik + kl, ka)
    print(f"  dönemde option (bütün mağazalar ve online, kayıp tablosundaki hücre-günler): "
          f"karşılanmayan {s(ka)}, ikameye giden {s(ik)} ({y(ik / ka if ka else np.nan)}), kalıcı "
          f"{s(kl)} ({y(kl / ka if ka else np.nan)}); Basit kestirimi ÷ karşılanmayan = "
          f"{s(toplam / ka if ka else np.nan, 2)}")
    dis = int(hd["karsilanmayan"].sum()) - ka
    print(f"  kayıp tablosu dışında kalan (stoklu gün ya da uygun olmayan hücre-gün): {s(dis)} adet"
          f"; dönemde hakemin toplamı {s(int(hd['karsilanmayan'].sum()))}")
    for kim, sku in (("Ali", sec["urun_id_ali"]), ("Veli", sec["urun_id_veli"])):
        r = h[(h["tarih"] == gun) & (h["magaza_id"].astype(str) == sec["magaza_id"])
              & (h["urun_id"].astype(str) == sku)]
        if r.empty:
            print(f"    {kim} {sku} o gün: karşılanmayan talep yok")
        else:
            r = r.iloc[0]
            print(f"    {kim} {sku} o gün: talep {s(r['talep'])}, karşılanmayan {s(r['karsilanmayan'])}"
                  f" = ikameye giden {s(r['ikameye_giden'])} + kalıcı {s(r['kalici_kayip'])}")


def _hat_tablosu(cikti: Path, aday: pd.DataFrame) -> None:
    """Her line'ın ilk üç option'ı + dönem kaybının tedarik payı ve iki SKU'nun o günkü λ̂'sı."""
    tablo = hikaye_sec.hatta_gore(aday)
    if tablo.empty:
        print("  (aday yok)")
        return
    k = pd.read_parquet(cikti / hazirla.DOSYALAR["basit"],
                        columns=["tarih", "magaza_id", "urun_id", "option_id", "kayip", "kaynak",
                                 "tahmini_talep"],
                        filters=[("option_id", "in", list(tablo["option_id"].astype(str)))])
    for c in ("magaza_id", "urun_id", "option_id", "kaynak"):
        k[c] = k[c].astype(str)
    print("  tedarik payı: dönem kaybının (Basit) kaynağı `tedarik` olan kısmı · λ̂: Ali'nin /"
          " Veli'nin SKU'sunun o gün o mağazadaki tahmini talebi (Basit)")
    print(f"  {'line':10s} {'option':12s} {'model':24s} {'renk':10s} {'mağaza':6s} {'gün':10s}"
          f" {'planlanan':10s} {'gerçekleşen':11s} {'dönem':>5s} {'dönem kaybı':>11s}"
          f" {'birikmiş':>9s} {'tedarik payı':>12s} {'λ̂ Ali':>7s} {'λ̂ Veli':>7s}")
    for r in tablo.itertuples():
        o = k[k["option_id"] == str(r.option_id)]
        d = o[(o["tarih"] >= r.donem_baslangic) & (o["tarih"] < r.tarih)]
        top = d["kayip"].sum()
        pay = d.loc[d["kaynak"] == "tedarik", "kayip"].sum() / top if top > 0 else np.nan
        o_gun = o[(o["tarih"] == r.tarih) & (o["magaza_id"] == str(r.magaza_id))].set_index("urun_id")
        lam = [o_gun["tahmini_talep"].get(str(u), np.nan) for u in (r.urun_id_ali, r.urun_id_veli)]
        print(f"  {str(r.line):10s} {str(r.option_id):12s} {str(r.model_adi)[:24]:24s}"
              f" {str(r.renk)[:10]:10s} {str(r.magaza_id):6s} {t_(r.tarih):10s}"
              f" {t_(r.planlanan_teslim_ali):10s} {t_(r.gerceklesen_teslim_ali):11s}"
              f" {s(r.donem_gun):>5s} {s(r.donem_kayip):>11s} {s(r.birikmis_kayip):>9s}"
              f" {y(pay):>12s} {s(lam[0], 2):>7s} {s(lam[1], 2):>7s}")


def hikaye_bolumu(con, cikti: Path, kars: pd.DataFrame, db=None, hikaye=None) -> None:
    """`hikaye` = (option_id, magaza_id, tarih) verilirse seçim odur (R24); yoksa `secim()`."""
    baslik("HİKÂYE", "Yazı 1'in ürünü (`hikaye_sec`; kurgu kapısında kullanıcı seçer).")
    try:
        sec, aday, gevsetilen = hikaye_sec.secim_ve_adaylar(cikti, db, hikaye)
    except LookupError as e:
        if hikaye is not None:
            raise
        print(f"  hikâye adayı yok: {e}")
        return

    alt("Seçilen (hikaye_sec.secim)" if hikaye is None else "Seçilen (elle, --hikaye)")
    urun = _secim_yazdir(con, sec, aday, gevsetilen)

    alt("Her line için en iyi 3 option (dönem kaybı azalan; option başına en üst satır)")
    _hat_tablosu(cikti, aday)

    alt("Seçilen option'ın stoksuzluğu (zincir)")
    _zincir_stoksuzlugu(con, cikti, sec)
    alt("Seçilen option'ın kaybı (Basit) ve iki SKU'nun kaynağı")
    _hikaye_kaybi(con, cikti, kars, sec, urun)


# ---------------------------------------------------------------------
# ÇARPANLAR
# ---------------------------------------------------------------------

def carpanlar_bolumu(cikti: Path) -> None:
    baslik("ÇARPANLAR", "Basit'in gün karakteri; 2023–2024 stoklu günlerinden öğrenildi "
                        "(carpanlar.pkl).")
    with open(cikti / hazirla.DOSYALAR["carpanlar"], "rb") as f:
        c = pickle.load(f)
    sure = cikti / "sure.json"
    if sure.exists():
        n = json.loads(sure.read_text(encoding="utf-8")).get("adimlar", {}).get("carpanlar", {})
        if "satir" in n:
            print(f"  öğrenilen stoklu hücre-gün: {s(n['satir'])}")

    alt("Hafta günü (kanal başına; yedi günün ortalaması 1)")
    print(f"  {'kanal':7s} " + " ".join(f"{g:>6s}" for g in GUNLER)
          + "  hafta sonu ÷ hafta içi (Cmt–Paz ortalaması ÷ Pzt–Cum ortalaması)")
    for kanal in sorted({k for k, _ in c.hafta_gunu}):
        v = [c.hafta_gunu.get((kanal, g), np.nan) for g in range(7)]
        oran = np.mean(v[5:]) / np.mean(v[:5]) if np.isfinite(v).all() else np.nan
        print(f"  {kanal:7s} " + " ".join(f"{s(x, 3):>6s}" for x in v) + f"  {s(oran, 2)}")

    alt("Özel gün çarpanları (aynı option'ın ±7 ve ±14 gün komşularına göre; fiyat etkisi çıkmış)")
    aciklama = {"black_friday": "Black Friday cuması", "black_friday_devami": "Black Friday'in diğer günleri",
                "tatil": "resmî tatil", "indirim_baslangici": "sezon indiriminin ilk 7 günü"}
    for ad in OZEL_GUNLER:
        print(f"  {ad:20s} {s(c.ozel_gun.get(ad, np.nan), 3):>6s}  ({aciklama.get(ad, ad)})")

    alt("Fiyat esnekliği ε̂ (üst kategori başına): kampanyadan ve markdown'dan, yan yana")
    print("  satış ∝ (1 − oran)^(−ε̂). Kampanya: dışsal, fark-içinde-fark (Basit bunu kullanır)."
          " Markdown: içsel (iyi satmayana indirim gelir), yalnız rapor; yanlı.")
    print(f"  {'üst kategori':16s} {'ε̂ kampanya':>11s} {'ε̂ markdown':>11s} {'fark':>6s}"
          f"  %30 indirimde satış × (kampanya / markdown)")
    anahtarlar = sorted((set(c.esneklik_kampanya) | set(c.esneklik_markdown)) - {"*"})
    for ust in anahtarlar + (["*"] if "*" in c.esneklik_kampanya or "*" in c.esneklik_markdown else []):
        ek = c.esneklik_kampanya.get(ust, np.nan)
        em = c.esneklik_markdown.get(ust, np.nan)
        etiket = "hepsi (*)" if ust == "*" else ust
        print(f"  {etiket:16s} {s(ek, 2):>11s} {s(em, 2):>11s} {s(ek - em, 2):>6s}"
              f"  {s(0.7 ** -ek, 2)} / {s(0.7 ** -em, 2)}")


# ---------------------------------------------------------------------
# KESTİRİM ve AYRIŞIM (2025, hakeme karşı)
# ---------------------------------------------------------------------

def _kayip_2025(cikti: Path, ad: str) -> pd.DataFrame:
    return pd.read_parquet(cikti / hazirla.DOSYALAR[ad],
                           columns=["tarih", "magaza_id", "urun_id", "option_id", "durum",
                                    "kayip", "kayip_saf"],
                           filters=_yil_araligi(OLCUM_YILI)).reset_index(drop=True)


def olcum_yap(con, cikti: Path, kars25: pd.DataFrame) -> dict:
    """Her kestirici için düzey ölçütleri, kırılımlar, tükenen gün ve ayrışım (korunum denetimli)."""
    sonuc = {}
    for ad in KESTIRICILER:
        e = degerlendir.eslestir(_kayip_2025(cikti, ad), kars25)
        t_top = float(e["kayip"].to_numpy(np.float64).sum())
        g_top = float(e["karsilanmayan"].to_numpy(np.int64).sum())

        duzey = {}
        for etiket, sutunlar in DUZEYLER.items():
            o = degerlendir.olcutler(e, sutunlar, "kayip", con)
            korunum(f"{ad} {etiket} Σtahmin", o["tahmin"], t_top)
            korunum(f"{ad} {etiket} Σkarsilanmayan", o["karsilanmayan"], g_top)
            duzey[etiket] = o

        kir = degerlendir.kirilimlar(e, con)       # bütün 2025 bir arada (sure koşuları bölünmez)
        for k in degerlendir.KIRILIMLAR:
            parca = kir[kir["kirilim"] == k]
            korunum(f"{ad} kirilim {k} Σtahmin", parca["tahmin"].sum(), t_top)
            korunum(f"{ad} kirilim {k} Σkarsilanmayan", parca["karsilanmayan"].sum(), g_top)

        tuk = e[(e["durum"] == "tukenen").to_numpy()]
        tukenen = {}
        for tahmin in ("kayip", "kayip_saf"):
            tt = float(tuk[tahmin].to_numpy(np.float64).sum())
            for etiket, sutunlar in (("hücre-gün", ["tarih", "magaza_id", "urun_id"]),
                                     ("mağaza × option × hafta", DUZEYLER["mağaza × option × hafta"]),
                                     ("toplam", [])):
                o = degerlendir.olcutler(tuk, sutunlar, tahmin, con)
                if len(tuk):
                    korunum(f"{ad} tukenen {tahmin} {etiket} Σtahmin", o["tahmin"], tt)
                tukenen[(tahmin, etiket)] = o

        ayr = degerlendir.ayrisim(e)
        korunum(f"{ad} ayrisim Σkarsilanmayan", ayr["karsilanmayan"], g_top)
        korunum(f"{ad} ayrisim ikame + kalici", ayr["ikameye_giden"] + ayr["kalici_kayip"],
                ayr["karsilanmayan"])
        sonuc[ad] = {"duzey": duzey, "kir": kir, "tukenen": tukenen, "ayrisim": ayr,
                     "satir": len(e), "tukenen_satir": len(tuk)}
        del e, tuk
    return sonuc


def _olcut_hucre(o: dict) -> str:
    return f"{y(o['wape']):>7s} {yi(o['yanlilik']):>8s}"


def kestirim_bolumu(olcum: dict) -> None:
    baslik("KESTİRİM", f"{OLCUM_YILI}; kestirim (kayıp tablosu) ↔ hakemin karşılanmayan talebi.")
    print("  WAPE = Σ|t − g| ÷ Σg · yanlılık = Σ(t − g) ÷ Σg (+: fazla tahmin); t ve g önce düzeye "
          "toplanır, fark sonra alınır")
    print("  t = `kayip` (spec'in ana ölçüsü; tükenen günde Poisson koşullu fazla E[D | D ≥ s] − s);"
          " g = hakemin karşılanmayanı, hakemde olmayan hücre-gün 0")
    print("  Not (R15): rapor yalnız ölçer; kestiriciler hakeme göre ayarlanmaz.")
    b = olcum["basit"]
    print(f"  kayıp tablosu {OLCUM_YILI} satırı (bos + tukenen): {s(b['satir'])}; "
          f"tükenen {s(b['tukenen_satir'])}")

    alt("Düzeyler")
    print(f"  {'düzey':26s} {'grup':>10s} {'Σg':>11s} | "
          + " | ".join(f"{AD[a]:>5s} {'WAPE':>7s} {'yanlılık':>8s} {'Σt':>11s}" for a in KESTIRICILER))
    for etiket in DUZEYLER:
        o0 = olcum["basit"]["duzey"][etiket]
        print(f"  {etiket:26s} {s(o0['grup']):>10s} {s(o0['karsilanmayan']):>11s} | "
              + " | ".join(f"{'':5s} {_olcut_hucre(olcum[a]['duzey'][etiket])} "
                           f"{s(olcum[a]['duzey'][etiket]['tahmin']):>11s}" for a in KESTIRICILER))

    alt("Kırılımlar (mağaza × option × hafta düzeyinde)")
    print("  durum: satırın kendi durumu · line: ürünün line'ı · sure: (mağaza, SKU)'nun ardışık"
          " stoksuz gün koşusu, kisa ≤ 3 gün, uzun > 3")
    print("  hit: sezonluk option, sezonu içinde STR'si (net satış ÷ teslim edilen sipariş) en üst"
          " onda birde; diger: kalanı (devamlı dahil) · kanal: online (ONL) / magaza")
    print(f"  {'kırılım':8s} {'değer':12s} {'Σg':>11s} | "
          + " | ".join(f"{AD[a]:>5s} {'WAPE':>7s} {'yanlılık':>8s} {'Σt':>11s}" for a in KESTIRICILER))
    tablo = {a: olcum[a]["kir"].set_index(["kirilim", "deger"]) for a in KESTIRICILER}
    for k in degerlendir.KIRILIMLAR:
        degerler = sorted(set().union(*(tablo[a].loc[k].index for a in KESTIRICILER
                                        if k in tablo[a].index.get_level_values(0))))
        for d in degerler:
            g = tablo["basit"].loc[(k, d), "karsilanmayan"] if (k, d) in tablo["basit"].index else np.nan
            hucre = []
            for a in KESTIRICILER:
                if (k, d) in tablo[a].index:
                    r = tablo[a].loc[(k, d)]
                    hucre.append(f"{'':5s} {_olcut_hucre(r)} {s(r['tahmin']):>11s}")
                else:
                    hucre.append(f"{'':5s} {'—':>7s} {'—':>8s} {'—':>11s}")
            print(f"  {k:8s} {d[:12]:12s} {s(g):>11s} | " + " | ".join(hucre))

    alt("Tükenen gün: kayip (Poisson koşullu) ve kayip_saf (max(0, λ̂ − s)), hakeme karşı")
    print("  kayip = E[D | D ≥ s] − s, D ~ Poisson(λ̂) (ana ölçü) · kayip_saf = max(0, λ̂ − s)"
          " (karşılaştırma); s = satış öncesi stok")
    print(f"  {'düzey':26s} {'hesap':10s} {'Σg':>9s} | "
          + " | ".join(f"{AD[a]:>5s} {'WAPE':>7s} {'yanlılık':>8s} {'Σt':>9s}" for a in KESTIRICILER))
    for etiket in ("hücre-gün", "mağaza × option × hafta", "toplam"):
        for tahmin in ("kayip", "kayip_saf"):
            o0 = olcum["basit"]["tukenen"][(tahmin, etiket)]
            print(f"  {etiket:26s} {tahmin:10s} {s(o0['karsilanmayan']):>9s} | "
                  + " | ".join(f"{'':5s} {_olcut_hucre(olcum[a]['tukenen'][(tahmin, etiket)])} "
                               f"{s(olcum[a]['tukenen'][(tahmin, etiket)]['tahmin']):>9s}"
                               for a in KESTIRICILER))


def ayrisim_bolumu(cikti: Path, kars25: pd.DataFrame, olcum: dict) -> None:
    baslik("AYRIŞIM", f"{OLCUM_YILI}; kayıp tablosundaki hücre-günler (bos + tukenen), hakemle "
                      "eşleşmiş.")
    print("  Σ karşılanmayan (hakem) = Σ ikameye giden + Σ kalıcı kayıp; ikame satışı `satis`'te "
          "normal satış görünür")
    print("  Σ tahmin = Σ kayip (spec'in ana ölçüsü); Σ kayip_saf karşılaştırma için (tükenen günde"
          " max(0, λ̂ − s)); R15: rapor yalnız ölçer")
    print(f"  {'kestirici':9s} {'Σ tahmin':>11s} {'Σ kayip_saf':>11s} {'Σ karşılanm.':>12s}"
          f" {'Σ ikame':>10s} {'Σ kalıcı':>10s} {'ikame payı':>10s} {'kalıcı payı':>11s}"
          f" {'tahmin÷karş.':>12s} {'tahmin÷kalıcı':>13s}")
    for a in KESTIRICILER:
        r = olcum[a]["ayrisim"]
        ka = r["karsilanmayan"]
        print(f"  {AD[a]:9s} {s(r['tahmin']):>11s} {s(r.get('kayip_saf', np.nan)):>11s} {s(ka):>12s}"
              f" {s(r['ikameye_giden']):>10s} {s(r['kalici_kayip']):>10s}"
              f" {y(r['ikameye_giden'] / ka if ka else np.nan):>10s}"
              f" {y(r['kalici_kayip'] / ka if ka else np.nan):>11s}"
              f" {s(r['tahmin'] / ka if ka else np.nan, 3):>12s}"
              f" {s(r['tahmin'] / r['kalici_kayip'] if r['kalici_kayip'] else np.nan, 3):>13s}")

    alt("Çeşit dışı: hakemin karşılanmayanı kestirimin kapsamı dışında nerede kaldı")
    uygun = pd.read_parquet(cikti / "gunluk.parquet", columns=["tarih", "magaza_id", "urun_id"],
                            filters=_yil_araligi(OLCUM_YILI))
    anahtar = pd.read_parquet(cikti / hazirla.DOSYALAR["basit"],
                              columns=["tarih", "magaza_id", "urun_id"], filters=_yil_araligi(OLCUM_YILI))
    c = degerlendir.cesit_disi(kars25, uygun, anahtar)
    del uygun, anahtar
    icinde = c["toplam_adet"] - c["disi_adet"] - c["stoklu_adet"]
    korunum("AYRIŞIM cesit disi: icinde = kayip tablosundaki karsilanmayan", icinde,
            olcum["basit"]["ayrisim"]["karsilanmayan"])
    top = c["toplam_adet"]
    print(f"  hakemin {OLCUM_YILI} karşılanmayanı: {s(top)} adet ({s(c['toplam_satir'])} hücre-gün)")
    print(f"    uygun olmayan hücre-günlerde (çeşit dışı, kapalı mağaza, lansman öncesi, çıkmış ürün):"
          f" {s(c['disi_adet'])} adet ({y(c['disi_pay'], 2)}), {s(c['disi_satir'])} hücre-gün")
    print(f"    uygun ama stoklu günlerde (kayıp tablosunda yok): {s(c['stoklu_adet'])} adet "
          f"({y(c['stoklu_pay'], 2)}), {s(c['stoklu_satir'])} hücre-gün")
    print(f"    kayıp tablosundaki hücre-günlerde (yukarıdaki Σ karşılanmayan): {s(icinde)} adet "
          f"({y(icinde / top if top else np.nan, 2)})")


# ---------------------------------------------------------------------
# LUMODA ve AĞAÇ (Basit, bütün pencere)
# ---------------------------------------------------------------------

def basit_tam(con, cikti: Path) -> pd.DataFrame:
    """Basit kayıp tablosu (bütün pencere) + `oran`, `kanal` (ozet bir kez hesaplasın)."""
    kb = pd.read_parquet(cikti / hazirla.DOSYALAR["basit"],
                         columns=["tarih", "magaza_id", "urun_id", "kayip", "kaynak"])
    return ozellikler.ekle(con, kb, ["oran", "kanal"])


def _ozet_denetimli(kb: pd.DataFrame, duzey: list[str], con, zincir: pd.DataFrame, ad: str):
    o = kayip.ozet(kb, duzey, con)
    for c in ("kayip_adet", "kayip_tl", "kayip_marj"):
        korunum(f"{ad} {'×'.join(duzey)} {c}", o[c].sum(), zincir[c].iloc[0])
    return o


def lumoda_bolumu(con, kb: pd.DataFrame, cikti: Path, kars25: pd.DataFrame) -> pd.DataFrame:
    baslik("LUMODA", "Basit kestiricisiyle (spec'in seçimi) Lumoda'nın stok kaynaklı kaybı, "
                     "2023–2025.")
    print("  kayıp TL = Σ kayıp × o günün etiket fiyatı (liste × (1 − oran)); brüt marj = Σ kayıp ×"
          " (etiket − alış)")
    print("  net ciro = Σ satis.tutar (temiz_satis, iade dahil), aynı yıl × kanal; net satış adedi"
          " aynı kaynaktan")
    zincir = kayip.ozet(kb, [], con)
    korunum("LUMODA zincir adet", zincir["kayip_adet"].iloc[0], kb["kayip"].to_numpy(np.float64).sum())
    yk = _ozet_denetimli(kb, ["yil", "kanal"], con, zincir, "LUMODA")
    satis = kaynak.temiz_satis(con)
    ciro = con.execute(f"""
        select year(tarih) as yil,
               case when magaza_id::varchar = 'ONL' then 'online' else 'magaza' end as kanal,
               sum(tutar)::double as ciro, sum(adet)::bigint as adet
        from {satis} where tarih::date between date '{YILLAR[0]}-01-01' and date '{YILLAR[-1]}-12-31'
        group by 1, 2
    """).fetchdf()
    yk["kanal"] = yk["kanal"].astype(str)
    t = yk.merge(ciro, on=["yil", "kanal"], how="outer").fillna(0)
    print(f"  {'yıl':>5s} {'kanal':7s} {'kayıp adet':>11s} {'kayıp TL':>15s} {'net ciro TL':>16s}"
          f" {'kayıp÷ciro':>10s} {'brüt marj TL':>14s} {'net satış adet':>14s} {'kayıp÷satış':>11s}")

    def satir(yil, kanal, r):
        print(f"  {yil:>5} {kanal:7s} {s(r['kayip_adet']):>11s} {s(r['kayip_tl']):>15s}"
              f" {s(r['ciro']):>16s} {y(r['kayip_tl'] / r['ciro'] if r['ciro'] else np.nan, 2):>10s}"
              f" {s(r['kayip_marj']):>14s} {s(r['adet']):>14s}"
              f" {y(r['kayip_adet'] / r['adet'] if r['adet'] else np.nan, 2):>11s}")

    sutun = ["kayip_adet", "kayip_tl", "kayip_marj", "ciro", "adet"]
    for yil in YILLAR:
        parca = t[t["yil"] == yil]
        for kanal in KANALLAR:
            r = parca[parca["kanal"] == kanal]
            satir(yil, kanal, r[sutun].sum())
        satir(yil, "toplam", parca[sutun].sum())
    for kanal in KANALLAR:
        satir("hepsi", kanal, t.loc[t["kanal"] == kanal, sutun].sum())
    satir("hepsi", "toplam", t[sutun].sum())
    print(f"  (milyon: 2023–2025 kayıp {mn(zincir['kayip_adet'].iloc[0], 2)} adet, "
          f"{mn(zincir['kayip_tl'].iloc[0])} TL, brüt marj {mn(zincir['kayip_marj'].iloc[0])} TL; "
          + "; ".join(f"{yil}: {mn(t.loc[t['yil'] == yil, 'kayip_tl'].sum())} TL" for yil in YILLAR)
          + ")")
    _hat_kirilimi(con, kb, zincir)
    _son_tukenis(con, cikti, kars25)
    return zincir


def _hat_kirilimi(con, kb: pd.DataFrame, zincir: pd.DataFrame) -> None:
    alt("Line başına (Basit): kayıp ve net ciro")
    print("  line: ürünün line'ı (Collection sezonluk, Basic / NOS devamlı, Outlet); kayıp payı ="
          " line'ın kayıp TL'si ÷ bütün kayıp TL; kayıp÷ciro = aynı line'ın net cirosuna oranı")
    lk = _ozet_denetimli(kb, ["yil", "line"], con, zincir, "LUMODA line")
    lk["line"] = lk["line"].astype(str)
    satis = kaynak.temiz_satis(con)
    ciro = con.execute(f"""
        select year(s.tarih) as yil, u.line::varchar as line, sum(s.tutar)::double as ciro
        from {satis} s join urun u on u.urun_id = s.urun_id
        where s.tarih::date between date '{YILLAR[0]}-01-01' and date '{YILLAR[-1]}-12-31'
        group by 1, 2
    """).fetchdf()
    for donem, yillar in ((str(OLCUM_YILI), (OLCUM_YILI,)), ("2023–2025", YILLAR)):
        k = lk[lk["yil"].isin(yillar)].groupby("line")[["kayip_adet", "kayip_tl"]].sum()
        c = ciro[ciro["yil"].isin(yillar)].groupby("line")["ciro"].sum()
        t = k.join(c, how="outer").fillna(0.0)
        top_tl = t["kayip_tl"].sum()
        print(f"  {donem}:")
        print(f"    {'line':11s} {'kayıp adet':>11s} {'kayıp TL':>15s} {'kayıp payı':>10s}"
              f" {'net ciro TL':>16s} {'kayıp÷ciro':>10s}")
        sirali = [h for h in hikaye_sec.HATLAR if h in t.index] + sorted(set(t.index) - set(hikaye_sec.HATLAR))
        for h, r in list(t.loc[sirali].iterrows()) + [("toplam", t.sum())]:
            print(f"    {h:11s} {s(r['kayip_adet']):>11s} {s(r['kayip_tl']):>15s}"
                  f" {y(r['kayip_tl'] / top_tl if top_tl else np.nan):>10s} {s(r['ciro']):>16s}"
                  f" {y(r['kayip_tl'] / r['ciro'] if r['ciro'] else np.nan, 2):>10s}")


def _son_tukenis(con, cikti: Path, kars25: pd.DataFrame) -> None:
    alt(f"Son tükeniş ({OLCUM_YILI}, line başına): Basit kaybı ve hakemin karşılanmayanı yan yana")
    print("  son tükeniş: hücrenin (mağaza × SKU) pencere içindeki son stoklu açılışından (durum ≠ bos)"
          " SONRAKİ günler; mal bitti ve hücrenin uygun penceresi kapanana (ya da 2025 sonuna) dek"
          " yeniden gelmedi")
    print("  diğer: aynı hücre sonradan yeniden stoklandı · ikisi de kayıp tablosunun 2025 hücre-günleri"
          " (bos + tukenen), hakemle eşleşmiş (AYRIŞIM'la aynı küme)")
    e = degerlendir.eslestir(_kayip_2025(cikti, "basit"), kars25)[
        ["tarih", "magaza_id", "urun_id", "kayip", "karsilanmayan"]]
    con.register("_son_tukenis", e)
    try:
        df = con.execute(f"""
            with son as (
                select magaza_id as m, urun_id as u,
                       max(tarih) filter (where durum <> 'bos') as son
                from {_parquet(cikti / 'gunluk.parquet')} group by 1, 2)
            select u.line::varchar as line,
                   case when son.son is null then 'hic' when e.tarih > son.son then 'son'
                        else 'diger' end as tur,
                   sum(e.kayip) as kayip, sum(e.karsilanmayan)::bigint as kars
            from _son_tukenis e
            join son on son.m = e.magaza_id::varchar and son.u = e.urun_id::varchar
            join urun u on u.urun_id::varchar = e.urun_id::varchar
            group by 1, 2
        """).fetchdf()
    finally:
        con.unregister("_son_tukenis")
    korunum("LUMODA son tukenis Σkayip", df["kayip"].sum(), e["kayip"].to_numpy(np.float64).sum())
    korunum("LUMODA son tukenis Σkarsilanmayan", df["kars"].sum(),
            e["karsilanmayan"].to_numpy(np.int64).sum())
    tablo = df.pivot_table(index="line", columns="tur", values=["kayip", "kars"], aggfunc="sum",
                           fill_value=0)
    for olcu in ("kayip", "kars"):
        for tur in ("son", "diger", "hic"):
            if (olcu, tur) not in tablo.columns:
                tablo[(olcu, tur)] = 0
    print(f"    {'line':11s} | {'Basit son':>10s} {'diğer':>10s} {'son payı':>8s} |"
          f" {'hakem son':>10s} {'diğer':>10s} {'son payı':>8s}")
    sirali = [h for h in hikaye_sec.HATLAR if h in tablo.index] + sorted(
        set(tablo.index) - set(hikaye_sec.HATLAR))
    for h, r in list(tablo.loc[sirali].iterrows()) + [("toplam", tablo.sum())]:
        ks, kd = r[("kayip", "son")], r[("kayip", "diger")] + r[("kayip", "hic")]
        hs, hd = r[("kars", "son")], r[("kars", "diger")] + r[("kars", "hic")]
        print(f"    {h:11s} | {s(ks):>10s} {s(kd):>10s} {y(ks / (ks + kd) if ks + kd else np.nan):>8s} |"
              f" {s(hs):>10s} {s(hd):>10s} {y(hs / (hs + hd) if hs + hd else np.nan):>8s}")
    hic = tablo.sum()
    if hic[("kayip", "hic")] or hic[("kars", "hic")]:
        print(f"    (diğer içinde, pencerede hiç stoklu açılışı olmayan hücreler: Basit "
              f"{s(hic[('kayip', 'hic')])}, hakem {s(hic[('kars', 'hic')])})")


def agac_bolumu(con, kb: pd.DataFrame, zincir: pd.DataFrame) -> None:
    baslik("AĞAÇ", "Basit kaybının kaynak dalları (agac.kaynak_ata): her kayıp hücre-günü tek dal.")
    print("  sıra: lojistik → mağaza → allocation → tedarik → planlama; fırsat pencereden önceyse"
          " bilinmiyor (ayrı)")
    print("  allocation: fırsatta (yol süresini karşılayan son pazartesi) depoda mal vardı · tedarik:"
          " planlanan teslim fırsattan önce, gerçekleşen sonra · planlama: diğerleri")
    print("  online'da fırsat aynı gündür ve depo online'ın stoğudur: allocation dalı online'da boş")
    ak = _ozet_denetimli(kb, ["yil", "kaynak", "kanal"], con, zincir, "AĞAÇ")
    ak["kaynak"] = ak["kaynak"].astype(str)
    ak["kanal"] = ak["kanal"].astype(str)
    bilinen_dallar = [d for d in agac.DALLAR if d != "bilinmiyor"]
    bos_dal = {"lojistik": "bu veride yok (yol süresi sabit, gecikme yok)",
               "magaza": "bu veride yok (raf / mağaza deposu ayrımı yok)"}

    for donem, yillar in (("2023–2025", YILLAR), (str(OLCUM_YILI), (OLCUM_YILI,))):
        parca = ak[ak["yil"].isin(yillar)]
        for kanal in KANALLAR + ("toplam",):
            p = parca if kanal == "toplam" else parca[parca["kanal"] == kanal]
            dal = p.groupby("kaynak")[["kayip_adet", "kayip_tl"]].sum()
            dal = dal.reindex(list(agac.DALLAR), fill_value=0.0)
            top_a, top_t = dal["kayip_adet"].sum(), dal["kayip_tl"].sum()
            korunum(f"AĞAÇ {donem} {kanal} dal toplami adet", top_a, p["kayip_adet"].sum())
            bil_a = top_a - dal.loc["bilinmiyor", "kayip_adet"]
            bil_t = top_t - dal.loc["bilinmiyor", "kayip_tl"]
            alt(f"Ağaç {donem}, {kanal}: {s(top_a)} adet, {s(top_t)} TL")
            print(f"  {'dal':11s} {'adet':>11s} {'adet payı':>9s} {'TL':>15s} {'TL payı':>8s}"
                  f"   (pay: bilinmiyor hariç toplamda)")
            for d in bilinen_dallar:
                a, tl = dal.loc[d, "kayip_adet"], dal.loc[d, "kayip_tl"]
                not_ = f"  {bos_dal[d]}" if d in bos_dal else ""
                print(f"  {d:11s} {s(a):>11s} {y(a / bil_a if bil_a else np.nan):>9s} {s(tl):>15s}"
                      f" {y(tl / bil_t if bil_t else np.nan):>8s}{not_}")
            a, tl = dal.loc["bilinmiyor", "kayip_adet"], dal.loc["bilinmiyor", "kayip_tl"]
            print(f"  {'bilinmiyor':11s} {s(a):>11s} {y(a / top_a if top_a else np.nan, 2):>9s}"
                  f" {s(tl):>15s} {y(tl / top_t if top_t else np.nan, 2):>8s}"
                  f"   (ayrı; pay bütün toplamda; fırsat 2023-01-01'den önce, depo kaydı yok)")


# ---------------------------------------------------------------------
# Akış
# ---------------------------------------------------------------------

def _ayristir(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python rapor.py", description=__doc__.split("\n")[0])
    p.add_argument("--cikti", type=Path, default=hazirla.VARSAYILAN_CIKTI,
                   help=f"hazirla çıktıları (varsayılan {hazirla.VARSAYILAN_CIKTI})")
    p.add_argument("--db", type=Path, default=None,
                   help=f"v4 DuckDB dosyası (varsayılan {kaynak.VARSAYILAN_YOL})")
    p.add_argument("--hakem", type=Path, default=hakem.HAKEM_DIZINI,
                   help=f"hakem önbelleği (varsayılan {hakem.HAKEM_DIZINI})")
    p.add_argument("--hikaye", type=_hikaye_arg, default=None, metavar="OPTION,MAGAZA,YYYY-MM-DD",
                   help="hikâye seçimini elle ver (varsayılan hikaye_sec.secim); sıkı aramanın "
                        "adayı değilse tutmadığı ölçütler basılır")
    return p.parse_args(argv)


def _hikaye_arg(metin: str) -> tuple[str, str, pd.Timestamp]:
    parca = [x.strip() for x in metin.split(",")]
    if len(parca) != 3:
        raise argparse.ArgumentTypeError("biçim: OPTION_ID,MAGAZA_ID,YYYY-MM-DD")
    try:
        gun = pd.Timestamp(parca[2])
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"tarih okunamadı: {parca[2]}") from e
    return parca[0], parca[1], gun


def main(argv: list[str] | None = None) -> int:
    a = _ayristir(argv)
    eksik = eksikler(Path(a.cikti), Path(a.hakem))
    if eksik:
        for m in eksik:
            print(m, file=sys.stderr)
        return 2
    try:
        con = kaynak.baglan(a.db)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    bas = time.perf_counter()
    try:
        kars = hakem.oku(a.hakem)["karsilanmayan"]
        veri_bolumu(con, a.cikti)
        try:
            hikaye_bolumu(con, a.cikti, kars, a.db, a.hikaye)
        except LookupError as e:          # yalnız --hikaye: o gün o mağazada bos beden yok
            print(f"--hikaye gecersiz: {e}", file=sys.stderr)
            return 2
        carpanlar_bolumu(a.cikti)
        kars25 = kars[(kars["tarih"].dt.year == OLCUM_YILI).to_numpy()].reset_index(drop=True)
        olcum = olcum_yap(con, a.cikti, kars25)
        kestirim_bolumu(olcum)
        ayrisim_bolumu(a.cikti, kars25, olcum)
        del kars, olcum
        kb = basit_tam(con, a.cikti)
        zincir = lumoda_bolumu(con, kb, a.cikti, kars25)
        agac_bolumu(con, kb, zincir)
    finally:
        con.close()
    bilgi = psutil.Process().memory_info()
    tepe = getattr(bilgi, "peak_wset", bilgi.rss)
    print(f"rapor: {time.perf_counter() - bas:.0f} sn, tepe bellek {tepe / _GB:.2f} GB",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
