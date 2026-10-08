"""Blok Transfer dizisinin yayımlanacak BÜTÜN sayıları buradan basılır (spec §6).

    cd vakalar/blok-transfer
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py [--hikaye OPTION:ALICI:VERICI] > cikti/rapor.txt

Kalıcı kural: yazıya yeni bir sayı girmeden önce buraya eklenir; ortak sayı denetimi
(`python -m perakende_analitik.sayi_denetimi`) yazılardaki her sayının bu çıktıda
geçtiğini denetler. Sayılar Türkçe basılır (binlik nokta, ondalık virgül, `%12,3`,
`−%3,2`). Uydurma sayı yasaktır; elle konmuş anlatı sayıları yalnız ANLATI
VARSAYIMLARI'ndadır ve orada "varsayım" diye etiketlidir.

Bölümler (bu başlıklarla, bu sırayla):

    === VERİ ===                  evren, option, hücre, kırık çift, kombinatorik üst sınır,
                                  geçmiş mağazalar arası transferler, sezon ve indirim takvimi
    === KARAR ANI ===             karar, ölçüm penceresi, sezon, indirime kalan hafta
    === HİKÂYE ===                kullanıcının sahnesi (`hikaye_sec`), `--hikaye` geçersiz kılar
    === REFERANS SENARYO ===      aday, değişken, kısıt; `--- greedy ---`, `--- mip ---`
    === AÇGÖZLÜ ADIM TABLOSU ===
    === İKİ PLANIN FARKI ===      ortak blok, alıcısı farklı, aynı malı taşıyorlar mı, örnek rota
    === LP GEVŞETMESİ ===         gevşek, tam sayı, boşluk, kesirli x/y, CBC son sınırı
    === GETİRİ ===                STR, örtük ve gerçekleşen oranlar, brüt kâr, marj, kâr-ağırlıklı
                                  plan, maliyet paketleri, ölçülen noktada net kâr, ızgara
    === DEMO KADRANI ===          spec'teki altı satır, iki yöntem (önbellekten; Ruling R3)
    === ANLATI VARSAYIMLARI ===
    === KORUNUM ===               özet ↔ hareket tablosu, kurtarılan ≤ payda, p ∈ [0, 1],
                                  hakem ve Basit paydası aynı evrende, LP ≥ CBC sınırı ≥ MIP

Rapor önce tampona yazılır; korunum tutmazsa stdout'a tek satır gitmez, mesaj stderr'e,
çıkış kodu 1 (`tamponla`). Basılan her fark ve oran basılan işlenenlerden hesaplanır
(`yuv`, `fark`, `bolum`): "A → B (+C)" satırı elle yapılan hesapla tutar.

Girdiler: v4 DuckDB, `hazirla` çıktıları (`cikti/`), plan önbelleği (`cikti/planlar`;
yoksa çözücü koşar, MIP hücresi dakikalar sürer) ve hakem önbelleği
(`vakalar/ortak/cikti/hakem/`). Hakem ya da hazırlık eksikse hangi komutun koşulacağı
stderr'e yazılır, çıkış kodu 1.

Kestirim girdidir, hakem ölçüdür: hakem (`perakende_analitik.hakem`) yalnız burada içe
aktarılır, `blok_transfer` paketi onu görmez (`tests/test_sizinti.py`). Hakem tablosu
okunur okunmaz ölçüm penceresine süzülür ve `olcum`a argüman olarak verilir; hakem
yakalamasının paydası Basit'inkiyle aynı hücre evrenidir (evren mağazaları × çeşit
hücreleri), çeşit dışı karşılanmayan talep ayrıca basılır.
"""

import argparse
import contextlib
import io
import math
import sys
import time
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

import getiri
import senaryolar
from blok_transfer import degerlendirme, hazirla, hikaye_sec, olcum
from blok_transfer.cekirdek import adaylar as adaylar_mod
from blok_transfer.cekirdek import metrikler, terazi, veri
from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cozuculer import mip
from perakende_analitik import hakem, kaynak

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
ONBELLEK = CIKTI / "planlar"
HAKEM_KOMUTU = "cd vakalar/ortak && .venv/Scripts/python -m perakende_analitik.hakem"
HAKEM_DOSYALARI = ("karsilanmayan.parquet", "ikame_alinan.parquet", "meta.json")

REFERANS = Parametreler()          # verici cover ≥ 6, alıcı tavanı kapalı, asgari hız 1
YONTEMLER = ("greedy", "mip")
# Spec §6 DEMO KADRANI: (verici cover eşiği, alıcı cover tavanı); 0 = tavan kapalı.
DEMO_SATIRLARI = [(6, 0), (6, 3), (6, 6), (14, 6), (18, 14), (26, 6)]
KORUNUM_TOLERANSI_TL = senaryolar.KORUNUM_TOLERANSI_TL

# Hikâyedeki elle sayılar (1. ve 2. yazı): veriden gelmez, kurgunun varsayımıdır. Değer
# değişirse kayıt defterine yazılır; türeyen sayılar (toplam saat, kalan çift) buradan basılır.
ANLATI_VARSAYIMLARI = {"cift_basina_dakika": 10, "haftalik_mesai_saat": 90, "aksam_cozulen_cift": 40}


# ---------------------------------------------------------------------------
# Biçim
# ---------------------------------------------------------------------------

def _yok(x) -> bool:
    return x is None or (isinstance(x, (float, np.floating)) and np.isnan(x))


def s(x, ondalik: int = 0) -> str:
    """Türkçe sayı: 1.234.567 · 0,55 · −3,2."""
    if _yok(x):
        return "—"
    metin = f"{float(x):,.{ondalik}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return metin.replace("-", "−")


def y(x, ondalik: int = 1) -> str:
    """Yüzde (x oran): 0,123 → %12,3; negatif → −%3,2."""
    if _yok(x):
        return "—"
    return ("−%" if x < 0 else "%") + s(abs(100 * x), ondalik)


def tl(x, ondalik: int = 0) -> str:
    """TL tutarı: 4.978.979 TL (ondalık istenirse 5.006.978,84 TL)."""
    return "—" if _yok(x) else f"{s(x, ondalik)} TL"


def mn(x, ondalik: int = 2) -> str:
    """Milyon: 4.978.979 → 4,98 milyon."""
    return "—" if _yok(x) else f"{s(x / 1e6, ondalik)} milyon"


def _oran(pay, payda) -> float | None:
    return pay / payda if payda else None


# Basılan her fark ve oran, işlenenlerin BASILAN (yuvarlanmış) değerlerinden hesaplanır:
# "A → B (+C)" ya da "A / B = C" satırı okuyucunun elle yapacağı hesapla kuruşu kuruşuna tutsun.

def yuv(x, ondalik: int = 0) -> float:
    """`s(x, ondalik)`'ın bastığı değer (aynı yuvarlama: biçimleme)."""
    return float(f"{float(x):.{ondalik}f}")


def fark(a, b, ondalik: int = 0) -> float:
    """b − a, ikisi de `ondalik` hanede basıldığı gibi."""
    return yuv(yuv(b, ondalik) - yuv(a, ondalik), ondalik)


def bolum(a, b, ondalik_a: int = 0, ondalik_b: int = 0) -> float | None:
    """a / b, ikisi de basıldığı gibi."""
    payda = yuv(b, ondalik_b)
    return yuv(a, ondalik_a) / payda if payda else None


def tamponla(govde) -> tuple[int, str]:
    """`govde()`yi stdout'u tamponlayarak koşar: (0, metin) ya da korunum bozulursa (1, "")
    ve mesaj stderr'e. Rapor stdout'a korunumdan önce tek satır yazmaz."""
    tampon = io.StringIO()
    try:
        with contextlib.redirect_stdout(tampon):
            govde()
    except AssertionError as e:
        print(e, file=sys.stderr)
        return 1, ""
    return 0, tampon.getvalue()


# ---------------------------------------------------------------------------
# Girdi kapıları
# ---------------------------------------------------------------------------

def hakem_eksik(dizin: Path) -> list[str]:
    """Hakem önbelleğinde eksik dosyalar ve kuran komut (boşsa hepsi var)."""
    yok = [d for d in HAKEM_DOSYALARI if not (Path(dizin) / d).exists()]
    if not yok:
        return []
    return [f"{dizin} icinde {', '.join(yok)} yok. Once koşun: {HAKEM_KOMUTU}"]


def _ayristir(argv: list[str] | None) -> argparse.Namespace:
    a = argparse.ArgumentParser(prog="rapor.py", description=__doc__.split("\n")[0])
    a.add_argument("--hikaye", metavar="OPTION:ALICI:VERICI", default=None,
                   help="sahneyi geçersiz kılar (varsayılan hikaye_sec.KULLANICI_SECIMI)")
    a.add_argument("--hakem", type=Path, default=hakem.HAKEM_DIZINI,
                   help=f"hakem önbelleği (varsayılan {hakem.HAKEM_DIZINI})")
    a.add_argument("--db", type=Path, default=None, help="v4 DuckDB (varsayılan: ortak yol)")
    return a.parse_args(argv)


# ---------------------------------------------------------------------------
# Ölçüm zemini: kayıp tabloları bir kez kurulur
# ---------------------------------------------------------------------------

class Zemin:
    """Evren, iki kayıp tablosu (Basit, hakem) ve vericilerin pencere satışı.

    Hakem tablosu çeşit hücrelerine süzülür (Ruling, Görev 7): Basit çeşit dışını hiç
    kestirmez, iki payda aynı hücre evreninde olsun."""

    def __init__(self, con, karar: date, kayip: pd.DataFrame, kars: pd.DataFrame, hafta: int):
        self.con, self.karar, self.hafta = con, karar, hafta
        self.evren = set(con.execute("select magaza_id from bt_magaza").df()["magaza_id"].astype(str))
        cesit = kaynak.cesit_hucreleri(con)
        self.hucreler = con.execute(
            f"select c.magaza_id, c.urun_id from {cesit} c "
            "join bt_magaza m on m.magaza_id::varchar = c.magaza_id").df()
        self.basit = olcum.kayip_tablosu(kayip, karar, hafta, self.evren, "kayip")
        self.hakem = olcum.kayip_tablosu(kars, karar, hafta, self.evren, "karsilanmayan",
                                         hucreler=self.hucreler)
        self.hakem_evren = olcum.kayip_tablosu(kars, karar, hafta, self.evren, "karsilanmayan")
        tum = {str(m) for m in kars["magaza_id"].astype(str).unique()}
        self.hakem_tum = olcum.kayip_tablosu(kars, karar, hafta, tum, "karsilanmayan")
        self.hakem_onl = olcum.kayip_tablosu(kars, karar, hafta, {"ONL"}, "karsilanmayan")
        self.satis = olcum.verici_satisi(con, karar, hafta)
        # "aynı hücre evreni" iddiasının denetimi: Basit'in kayıp yazdığı hücreler çeşit içinde mi
        h = self.hucreler.astype(str).drop_duplicates().assign(_cesit=True)
        b = self.basit.astype({"magaza_id": str, "urun_id": str}).merge(
            h, on=["magaza_id", "urun_id"], how="left")
        disari = b[b["_cesit"].isna()]
        self.basit_cesit_disi = (len(disari), int(disari["kayip"].sum()))

    def olc(self, hareketler: pd.DataFrame) -> tuple[olcum.Olcum, olcum.Olcum]:
        """(Basit, hakem) ölçümü; `p_verici` iki sürümde aynıdır (gözlenen satış)."""
        veri.gorunumler(self.con, self.karar)
        tas = olcum.tasinan(self.con, hareketler, self.karar)
        return olcum.olc(tas, self.basit, self.satis), olcum.olc(tas, self.hakem, self.satis)


# ---------------------------------------------------------------------------
# Saf yardımcılar
# ---------------------------------------------------------------------------

def rota_dagilimi(h: pd.DataFrame) -> dict[int, int]:
    """Rota başına taşınan option sayısının dağılımı: {1: 147, 2: 42, ...}."""
    if not len(h):
        return {}
    sayim = h.groupby(["verici", "alici"], observed=True).size().value_counts()
    return {int(k): int(sayim[k]) for k in sorted(sayim.index)}


def _bloklar(h: pd.DataFrame) -> dict[tuple[str, str], tuple[str, int]]:
    """(verici, option) → (alıcı, adet)."""
    return {(str(v), str(o)): (str(a), int(n))
            for v, a, o, n in zip(h.verici, h.alici, h.option_id, h.adet)}


def plan_farki(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """İki planın (verici, option) blok kümesi farkı."""
    ba, bb = _bloklar(a), _bloklar(b)
    ortak = set(ba) & set(bb)
    return {
        "ortak": len(ortak),
        "ortak_alici_farkli": sum(1 for k in ortak if ba[k][0] != bb[k][0]),
        "ortak_ayni_hareket": sum(1 for k in ortak if ba[k][0] == bb[k][0]),
        "yalniz_a": len(set(ba) - set(bb)),
        "yalniz_b": len(set(bb) - set(ba)),
        "ortak_adet": sum(ba[k][1] for k in ortak),
        "yalniz_a_adet": sum(ba[k][1] for k in set(ba) - set(bb)),
        "yalniz_b_adet": sum(bb[k][1] for k in set(bb) - set(ba)),
        "ayni_mal": set(ba) == set(bb),
    }


def ornek_rota(greedy_h: pd.DataFrame, mip_h: pd.DataFrame) -> dict | None:
    """MIP'in, blokları açgözlü planda en az iki farklı alıcıya giden rotaları içinden en çok
    option taşıyanı (eşitlikte adet, sonra rota kimliği). Bloğu açgözlünün hiç taşımadığı
    option'lar sayılır ama alıcı çeşitliliğine girmez."""
    gb = _bloklar(greedy_h)
    adaylar = []
    for (v, a), grup in mip_h.groupby(["verici", "alici"], observed=True):
        satirlar = [(str(o), int(n), gb.get((str(v), str(o)), (None, 0))[0])
                    for o, n in zip(grup.option_id, grup.adet)]
        alicilar = {g for _, _, g in satirlar if g is not None}
        if len(alicilar) >= 2:
            adaylar.append((-len(satirlar), -sum(n for _, n, _ in satirlar), str(v), str(a),
                            satirlar))
    if not adaylar:
        return None
    _, _, v, a, satirlar = min(adaylar)
    return {"verici": v, "alici": a, "option": len(satirlar),
            "adet": sum(n for _, n, _ in satirlar), "satirlar": sorted(satirlar)}


def ortuk_oranlar(hareketler: pd.DataFrame, aday: pd.DataFrame, H: int) -> pd.DataFrame:
    """Modelin hareket başına örtük satma oranları: min(adet, hız × H) / adet (alıcı, verici)."""
    m = hareketler[["verici", "alici", "option_id", "adet"]].astype(
        {"verici": str, "alici": str, "option_id": str}).merge(
        aday[["verici", "alici", "option_id", "hiz_verici", "hiz_alici"]].astype(
            {"verici": str, "alici": str, "option_id": str}),
        on=["verici", "alici", "option_id"], how="left")
    return pd.DataFrame({
        "p_alici": (m.hiz_alici * H / m.adet).clip(upper=1.0),
        "p_verici": (m.hiz_verici * H / m.adet).clip(upper=1.0),
    })


def hareket_basina_p_alici(tas: pd.DataFrame, kayip_t: pd.DataFrame) -> pd.Series:
    """Hareket başına gerçekleşen alıcı oranı Σ_s min(taşınan, kayıp) / adet. Aynı alıcı
    SKU'suna iki verici giderse kayıp ikisine de sayılır (yalnız dağılım için; toplam oran
    `olcum.olc`tan gelir ve orada kayıp bir kez kurtarılır)."""
    t = tas.astype({"alici": str, "urun_id": str}).merge(
        kayip_t.astype({"magaza_id": str, "urun_id": str}).rename(columns={"magaza_id": "alici"}),
        on=["alici", "urun_id"], how="left")
    t["kurtarilan"] = np.minimum(t.adet, t.kayip.fillna(0))
    g = t.groupby(["verici", "alici", "option_id"], observed=True)[["adet", "kurtarilan"]].sum()
    return g.kurtarilan / g.adet


# ---------------------------------------------------------------------------
# Korunum
# ---------------------------------------------------------------------------

def korunum(planlar: dict[str, tuple[pd.DataFrame, dict]], olcumler: dict[str, olcum.Olcum],
            evren: set[str], kayip_tablolari: dict[str, pd.DataFrame], p: Parametreler,
            ek: list[tuple[str, bool]] = ()) -> int:
    """Raporun iç tutarlılığı. Tutanların sayısını döndürür; biri tutmazsa `AssertionError`
    (hepsi tek mesajda).

    planlar          ad → (hareket tablosu, özet): özet sayıları tablodan yeniden hesaplanır
    olcumler         ad → Olcum: 0 ≤ kurtarılan ≤ payda, kurtarılan ≤ taşınan, oranlar ∈ [0, 1]
    kayip_tablolari  ad → kayıp tablosu: hiçbir hücre `evren` dışında değil (hakem ve
                     Basit paydası aynı evren)
    ek               (açıklama, koşul) çiftleri: raporun kendi denetimleri"""
    hatalar: list[str] = []
    sayac = 0

    def denet(kosul: bool, mesaj: str) -> None:
        nonlocal sayac
        sayac += 1
        if not kosul:
            hatalar.append(mesaj)

    for ad, (h, oz) in planlar.items():
        rota = len(h.groupby(["verici", "alici"], observed=True)) if len(h) else 0
        adet = int(h.adet.sum()) if len(h) else 0
        net = (float(h.w.sum()) if len(h) else 0.0) - rota * p.rota_sabiti_tl
        denet(oz["option_sayisi"] == len(h), f"{ad}: option_sayisi {oz['option_sayisi']} ≠ {len(h)}")
        denet(oz["tasinan_adet"] == adet, f"{ad}: tasinan_adet {oz['tasinan_adet']} ≠ {adet}")
        denet(oz["rota_sayisi"] == rota, f"{ad}: rota_sayisi {oz['rota_sayisi']} ≠ {rota}")
        denet(oz["bosalan_magaza"] == (h.verici.nunique() if len(h) else 0),
              f"{ad}: bosalan_magaza tutmuyor")
        denet(abs(oz["net_kazanc_tl"] - net) <= 0.01,
              f"{ad}: net_kazanc_tl {oz['net_kazanc_tl']} ≠ Σw − R·rota {net:.2f}")
        denet(not (len(h) and h.duplicated(["verici", "option_id"]).any()),
              f"{ad}: aynı (verici, option) bloğu iki kez taşınıyor")
    for ad, o in olcumler.items():
        denet(0 <= o.kurtarilan <= o.payda + 1e-9,
              f"{ad}: kurtarilan {o.kurtarilan} payda {o.payda}'yı aşıyor")
        denet(o.kurtarilan <= o.tasinan_adet + 1e-9,
              f"{ad}: kurtarilan {o.kurtarilan} > taşınan {o.tasinan_adet}")
        for alan in ("yakalama", "p_alici", "p_verici"):
            deger = getattr(o, alan)
            denet(0 <= deger <= 1, f"{ad}: {alan} = {deger} ∉ [0, 1]")
    evren_s = {str(m) for m in evren}
    for ad, t in kayip_tablolari.items():
        disari = set(t["magaza_id"].astype(str)) - evren_s
        denet(not disari, f"{ad} paydası evren dışına taşıyor: {sorted(disari)[:5]}")
    for mesaj, kosul in ek:
        denet(bool(kosul), mesaj)
    if hatalar:
        raise AssertionError("korunum bozuldu:\n  " + "\n  ".join(hatalar))
    return sayac


# ---------------------------------------------------------------------------
# Bölümler
# ---------------------------------------------------------------------------

def _magaza_adlari(con) -> dict[str, str]:
    return {str(m): a for m, a in con.execute("select magaza_id, ad from magaza").fetchall()}


def veri_bolumu(con, karar: date, p: Parametreler) -> dict:
    print("=== VERİ ===")
    gun = karar.isoformat()
    toplam, fiziksel = con.execute(
        "select count(*), count(*) filter (where magaza_id <> 'ONL') from magaza").fetchone()
    evren_n = con.execute("select count(*) from bt_magaza").fetchone()[0]
    kapali, acilmamis = con.execute(
        "select count(*) filter (where kapanis_tarihi is not null and kapanis_tarihi <= ?::timestamp), "
        "count(*) filter (where acilis_tarihi > ?::timestamp) from magaza where magaza_id <> 'ONL'",
        [gun, gun]).fetchone()
    tadilat = fiziksel - evren_n - kapali - acilmamis
    print(f"mağaza tablosu {s(toplam)} satır (online dahil) · fiziksel mağaza {s(fiziksel)}")
    print(f"evren (karar anında açık, tadilatta değil, fiziksel): {s(evren_n)} mağaza · "
          f"dışarıda kalan fiziksel {s(fiziksel - evren_n)} (kapalı {kapali}, henüz açılmamış "
          f"{acilmamis}, tadilatta {tadilat})")
    tipler = con.execute("select m.tip, count(*) from magaza m join bt_magaza b using (magaza_id) "
                         "group by 1 order by 1").fetchall()
    print("evren mağaza tipi: " + " · ".join(f"{t} {n}" for t, n in tipler))
    sehir = con.execute("select count(*) filter (where m.sehir = 'İstanbul'), count(distinct m.sehir) "
                        "from magaza m join bt_magaza b using (magaza_id)").fetchone()
    print(f"evrende İstanbul mağazası {sehir[0]} · şehir sayısı {sehir[1]}")

    option_n, sku_n = con.execute("select count(distinct option_id), count(*) from urun").fetchone()
    tek_beden = con.execute("select count(*) from (select option_id from urun group by 1 "
                            "having count(*) = 1)").fetchone()[0]
    stok = metrikler.stok_fotografi(con, karar)
    kiriklar = metrikler.kiriklar(con, karar)
    print(f"option {s(option_n)} · SKU {s(sku_n)} · tek bedenli option {s(tek_beden)}")
    print(f"karar anında stoklu option {s(stok.option_id.nunique())} · stoklu (mağaza, option) "
          f"hücresi {s(len(stok))} · stoktaki adet {s(stok.adet.sum())}")
    hucre = evren_n * option_n
    stoklu_o = stok.option_id.nunique()
    print(f"mağaza × option hücresi: {s(evren_n)} × {s(option_n)} = {s(hucre)} · karar anında stoklu "
          f"option üzerinden {s(evren_n)} × {s(stoklu_o)} = {s(evren_n * stoklu_o)}")
    print(f"kırık (mağaza, option) çifti: {s(len(kiriklar))}")
    print(f"kırık × alıcı adayı: {s(len(kiriklar))} × {s(evren_n - 1)} = "
          f"{s(len(kiriklar) * (evren_n - 1))} olası hareket")
    ust = evren_n * (evren_n - 1) * option_n
    print(f"kombinatorik üst sınır M × (M − 1) × O: {s(evren_n)} × {s(evren_n - 1)} × "
          f"{s(option_n)} = {s(ust)} · stoklu option üzerinden {s(evren_n)} × {s(evren_n - 1)} × "
          f"{s(stoklu_o)} = {s(evren_n * (evren_n - 1) * stoklu_o)}")

    # Nominal kapasite neden kullanılmıyor (spec §3.3): karar günü doluluğu
    dol = con.execute(
        "select m.magaza_id, m.kapasite, sum(st.adet) as stok from bt_stok st "
        "join magaza m using (magaza_id) where st.tarih = ?::timestamp group by 1, 2", [gun]).df()
    oran = dol.stok / dol.kapasite
    print(f"nominal kapasite doluluğu (stok / kapasite, karar günü): medyan {s(oran.median(), 2)} · "
          f"en düşük {s(oran.min(), 2)} · en yüksek {s(oran.max(), 2)} · "
          f"kapasitesini aşan mağaza {int((oran > 1).sum())}/{len(oran)}")
    bosluk = adaylar_mod.kapasite_boslugu(con, karar, tepe_hafta=p.tepe_hafta)
    sifir = sum(1 for b in bosluk.values() if b == 0)
    print(f"tepe-stok kapasite boşluğu ({p.tepe_hafta} hafta): toplam {s(sum(bosluk.values()))} adet · "
          f"boşluğu 0 olan mağaza {sifir}/{len(bosluk)}")

    print("\ngeçmiş mağazalar arası sevkiyat (kaynak ve hedef mağaza, sevk tarihi < karar):")
    gecmis = con.execute(
        "select tip::varchar as tip, count(*) as satir, sum(adet) as adet, min(tarih) as ilk, "
        "max(tarih) as son from sevkiyat where kaynak::varchar not in ('DEPO', 'ONL') "
        "and hedef::varchar not in ('DEPO', 'ONL') and tarih < ?::timestamp group by 1 order by 2 desc",
        [gun]).df()
    for r in gecmis.itertuples():
        print(f"  {r.tip:18} {s(r.satir):>7} satır · {s(r.adet):>9} adet · "
              f"{r.ilk.date()} – {r.son.date()}")
    print(f"  toplam {s(gecmis.satir.sum())} satır · {s(gecmis.adet.sum())} adet")
    esik = karar - timedelta(weeks=p.soguma_hafta)
    sog = con.execute(
        "select sv.tip::varchar as tip, count(distinct (sv.magaza_id, u.option_id)) as hucre "
        "from bt_sevkiyat sv join urun u using (urun_id) "
        "where sv.tarih > ?::timestamp and sv.tarih <= ?::timestamp group by 1 order by 2 desc",
        [esik.isoformat(), gun]).df()
    sog_toplam = con.execute(
        "select count(distinct (sv.magaza_id, u.option_id)) from bt_sevkiyat sv join urun u "
        "using (urun_id) where sv.tarih > ?::timestamp and sv.tarih <= ?::timestamp",
        [esik.isoformat(), gun]).fetchone()[0]
    print(f"soğumadaki (mağaza, option) hücresi (varış son {p.soguma_hafta} hafta): {s(sog_toplam)} · "
          + " · ".join(f"{r.tip} {s(r.hucre)}" for r in sog.itertuples()))

    print("\nsezon takvimi (sezon tablosu, AW25):")
    for r in con.execute("select dalga, lansman_tarihi, indirim_baslangic, cikis_tarihi from sezon "
                         "where sezon_kodu = 'AW25' order by dalga").fetchall():
        print(f"  dalga {r[0]}: lansman {r[1].date()} · indirim başlangıcı {r[2].date()} · "
              f"çıkış {r[3].date()}")
    sezonlar = con.execute("select count(distinct sezon_kodu) from sezon").fetchone()[0]
    print(f"veride sezon kodu: {sezonlar} sezon · urun.sezon_kodu ve takvim.sezon_kodu dolu")
    son_stok, son_satis = con.execute(
        "select (select max(tarih) from stok), (select max(tarih) from satis)").fetchone()
    print(f"veri karar anında bitmiyor: son stok fotoğrafı {son_stok.date()} "
          f"(karardan {(son_stok.date() - karar).days // 7} hafta sonra) · son satış {son_satis.date()}")
    return {"kirik": kiriklar, "evren_n": evren_n, "option_n": option_n, "ust_sinir": ust,
            "bosluk": bosluk}


def karar_bolumu(con, karar: date, p: Parametreler) -> None:
    print("\n=== KARAR ANI ===")
    bas, bit = olcum.pencere(karar, p.olcum_hafta)
    sezon = con.execute("select sezon_kodu from takvim where tarih = ?::timestamp",
                        [karar.isoformat()]).fetchone()[0]
    indirim = con.execute("select min(indirim_baslangic) from sezon where sezon_kodu = ?",
                          [sezon]).fetchone()[0].date()
    print(f"karar anı: {karar.isoformat()} (pazartesi stok fotoğrafı) · sezon {sezon}")
    print(f"ölçüm penceresi: {bas.isoformat()} – {(bit - timedelta(days=1)).isoformat()} "
          f"({p.olcum_hafta} hafta, ikinci uç {bit.isoformat()} dahil değil)")
    gun = (indirim - karar).days
    print(f"karardan indirim başlangıcına ({indirim.isoformat()}): {gun} gün = {s(gun / 7, 1)} hafta · "
          f"pencere sonundan indirime {(indirim - bit).days} gün")


def hikaye_bolumu(con, karar, p, kayip, zemin: Zemin, greedy, mip_plan, zorla, adlar) -> dict:
    print("\n=== HİKÂYE ===")
    girdi = hikaye_sec._girdiler(con, karar, p, kayip)
    if zorla is None:
        zorla = hikaye_sec.varsayilan_secim(greedy.hareketler, mip_plan.hareketler)
        print(f"sahne: kullanıcının seçimi (hikaye_sec.KULLANICI_SECIMI {zorla})")
    else:
        print(f"sahne: --hikaye {':'.join(zorla)}")
    h = hikaye_sec.sec_tablolardan(greedy=greedy.hareketler, mip=mip_plan.hareketler, zorla=zorla,
                                   cover_esigi=p.verici_cover_esigi, **girdi)
    o = hikaye_sec.ozet(con, karar, h, kayip, greedy=greedy, mip=mip_plan, p=p, girdi=girdi)
    op = o["option"]
    print(f"option {op['option_id']} · {op['model_adi']} · {op['alt_kategori']} · {op['line']} · "
          f"{op['sezon_kodu']} · {op['renk']} · liste fiyatı {tl(op['liste_fiyati'], 2)}")
    print(f"bedenler: {', '.join(op['bedenler'])}")
    print(f"gevşeyen ölçütler: {', '.join(o['gevseyen']) or 'yok'}")
    print(f"aynı bloğa aday öteki alıcı (w > 0): {o['rakip_alici_sayisi']}")

    hk = zemin.hakem.astype({"magaza_id": str, "urun_id": str})
    urun = con.execute("select urun_id, beden from urun where option_id = ? order by beden_sira",
                       [h.option_id]).df().astype(str)
    sevk_satis = con.execute(
        "with sv as (select sv.magaza_id, sum(sv.adet) a from bt_sevkiyat sv join urun u using (urun_id) "
        "where u.option_id = ? and sv.tarih <= ?::timestamp group by 1), "
        "st as (select s.magaza_id, sum(s.adet) a from bt_satis s join urun u using (urun_id) "
        "where u.option_id = ? and s.tarih <= ?::timestamp group by 1) "
        "select sv.magaza_id, sv.a, coalesce(st.a, 0) from sv left join st using (magaza_id)",
        [h.option_id, karar.isoformat(), h.option_id, karar.isoformat()]).fetchall()
    sevk_satis = {str(m): (int(a), int(b)) for m, a, b in sevk_satis}

    for rol in ("alici", "verici", "ikinci_alici", "karsi_verici"):
        r = o[rol]
        print(f"\n{rol}: " + ("yok" if r is None else
              f"{r['ad']} ({r['magaza_id']}, {r['sehir']}, {r['tip']}) · option {r['option_id']}"))
        if r is None:
            continue
        print("  stok: " + " · ".join(f"{b} {n}" for b, n in r["bedenler"].items())
              + f" · toplam {r['toplam']}")
        hiz = r["hiz_8h"]
        cover = "—" if r["cover"] >= p.buyuk_cover else s(r["cover"], 1)
        print(f"  hız (8 stoklu hafta ort.) {s(hiz, 2)}/hafta · 8 haftada {s(yuv(hiz or 0, 2) * 8, 2)} adet · "
              f"cover {cover} hafta · STR {y(r['str'])}")
        if r["option_id"] == h.option_id and r["magaza_id"] in sevk_satis:
            a, b = sevk_satis[r["magaza_id"]]
            print(f"  STR kaynağı: karara dek varan sevkiyat {a} adet, net satış {b} adet")
        kb = r["kayip_beden"]
        print(f"  pencere kaybı (Basit) {r['pencere_kaybi']} · beden beden: "
              + (" · ".join(f"{b} {kb[b]}" for b in r["bedenler"] if b in kb) or "—"))
        if r["option_id"] == h.option_id:
            k = urun.merge(hk[hk.magaza_id == r["magaza_id"]], on="urun_id")
            print(f"  pencere karşılanmayan talebi (hakem) {int(k.kayip.sum())} · beden beden: "
                  + (" · ".join(f"{b} {int(x)}" for b, x in zip(k.beden, k.kayip)) or "—"))

    hareket = o.get("hareket", {})
    for ad in ("greedy", "mip"):
        hr = hareket.get(ad)
        print(f"\n{ad}: bloğu (verici → alıcı) " + (f"taşıyor · {hr['adet']} adet · w {tl(hr['w'], 2)}"
                                                    if hr else "taşımıyor"))
    for ad, plan in (("greedy", greedy), ("mip", mip_plan)):
        r = plan.hareketler
        r = r[(r.verici.astype(str) == h.verici) & (r.option_id.astype(str) == h.option_id)]
        hedef = ", ".join(f"{adlar[str(a)]} ({a})" for a in r.alici.astype(str)) or "taşımıyor"
        print(f"{ad}: {adlar[h.verici]} bloğunun alıcısı: {hedef}")
    print("bloğun aday alıcıları (w, büyükten küçüğe): " + " · ".join(
        f"{adlar[str(a['alici'])]} {tl(a['w'], 2)}" for a in o.get("blok_alici_adaylari", [])))

    # sahne bloğu gerçekten ne kurtardı (ölçüm penceresi)
    blok = greedy.hareketler
    blok = blok[(blok.verici.astype(str) == h.verici) & (blok.alici.astype(str) == h.alici)
                & (blok.option_id.astype(str) == h.option_id)]
    if len(blok):
        ob, oh = zemin.olc(blok)
        print(f"sahne bloğu pencerede: taşınan {ob.tasinan_adet} · kurtarılan Basit "
              f"{s(ob.kurtarilan)} / hakem {s(oh.kurtarilan)} · vericide de satılacak olan "
              f"{s(ob.p_verici * ob.tasinan_adet)} adet")
    return o


def kapasite_engeli(h: pd.DataFrame, df: pd.DataFrame, kapasite: dict) -> tuple[int, int, int]:
    """Planın taşımadığı (serbest) bloklardan puanı pozitif adaylar içinde alıcısının kalan
    boşluğuna sığmayanlar: (engellenen serbest blok, bunların alıcı mağazası, boşluğu 0 olan
    aday alıcı). Kapasite plana bağlıysa ilk sayı > 0'dır."""
    kullanilan = h.groupby(h.alici.astype(str), observed=True).adet.sum().to_dict() if len(h) else {}
    tasinan = {(str(v), str(o)) for v, o in zip(h.verici, h.option_id)}
    d = df[df.w > 0].astype({"verici": str, "alici": str, "option_id": str})
    d = d[[(v, o) not in tasinan for v, o in zip(d.verici, d.option_id)]]
    kalan = d.alici.map(lambda a: kapasite.get(a, 0) - kullanilan.get(a, 0))
    engel = d[d.adet > kalan]
    sifir = sum(1 for a in set(df.alici.astype(str)) if kapasite.get(a, 0) == 0)
    return (len(engel.groupby(["verici", "option_id"])) if len(engel) else 0,
            engel.alici.nunique(), sifir)


def plan_bolumu(ad: str, plan, oz: dict, ob, oh, kirik_kume: set, kapasite: dict, p,
                df: pd.DataFrame) -> dict:
    h = plan.hareketler
    print(f"\n--- {ad} ---")
    rota = oz["rota_sayisi"]
    sw = float(h.w.sum())
    print(f"  hareket (option) {s(oz['option_sayisi'])} · adet {s(oz['tasinan_adet'])} · "
          f"rota (sevkiyat) {s(rota)} · boşalan verici {s(oz['bosalan_magaza'])} · "
          f"alıcı mağaza {s(h.alici.nunique())}")
    print(f"  net kazanç {tl(oz['net_kazanc_tl'])} ({mn(oz['net_kazanc_tl'])}) = Σw "
          f"{tl(sw)} − {s(rota)} rota × {s(p.rota_sabiti_tl)} TL ({tl(rota * p.rota_sabiti_tl)})")
    sure = (f"{s(plan.sure_sn * 1000, 1)} ms" if plan.sinir is None and plan.sure_sn < 1
            else f"{s(plan.sure_sn, 1)} sn")
    print(f"  çözüm süresi {sure} · durum {oz['durum']}"
          + (f" · boşluk %{s(oz['bosluk_yuzde'], 2)} · son sınır {tl(plan.sinir)}"
             if oz.get("bosluk_yuzde") is not None else ""))
    print(f"  kayıp yakalama — Lumoda (Basit) {y(ob.yakalama)} ({s(ob.kurtarilan)} / "
          f"{s(ob.payda)}) · hakem {y(oh.yakalama)} ({s(oh.kurtarilan)} / {s(oh.payda)})")
    print(f"  gerçekleşen p_alıcı — Basit {y(ob.p_alici)} · hakem {y(oh.p_alici)} · "
          f"p_verici {y(ob.p_verici)}")
    dag = rota_dagilimi(h)
    print("  rota başına option dağılımı: "
          + " · ".join(f"{k} option {s(dag[k])} rota" for k in sorted(dag)))
    adres = len({(str(a), str(o)) for a, o in zip(h.alici, h.option_id)} & kirik_kume)
    kirik_v = len({(str(v), str(o)) for v, o in zip(h.verici, h.option_id)} & kirik_kume)
    print(f"  adreslenen kırık çift: {s(adres)} / {s(len(kirik_kume))} ({y(adres / len(kirik_kume))})")
    print(f"  kırık seti verici yapan çift: {kirik_v}")
    kullanilan = h.groupby(h.alici.astype(str), observed=True).adet.sum()
    dolu = [a for a, n in kullanilan.items() if n >= kapasite.get(a, 0)]
    toplam_bosluk = sum(kapasite.get(a, 0) for a in kullanilan.index)
    print(f"  kapasite: boşluğu tamamen dolan alıcı {len(dolu)}/{len(kullanilan)} · "
          f"alıcıların boşluğunun {y(_oran(kullanilan.sum(), toplam_bosluk))}'i kullanıldı")
    eb, ea, sifir = kapasite_engeli(h, df, kapasite)
    print(f"  kapasite bağladı mı: planın taşımadığı puanı pozitif bloklardan {s(eb)} tanesi alıcısının "
          f"kalan boşluğuna sığmıyor ({s(ea)} alıcı) · aday alıcılardan boşluğu 0 olan {sifir}")
    net_tutar = yuv(oz["net_kazanc_tl"]) == yuv(sw) - rota * p.rota_sabiti_tl
    return {"adreslenen": adres, "kirik_verici": kirik_v, "kapasite_dolu": len(dolu), "sw": sw,
            "net_tutar": net_tutar}


def adim_bolumu(aday_n: int, plan) -> None:
    sy = plan.sayaclar
    print("\n=== AÇGÖZLÜ ADIM TABLOSU ===")
    print(f"  SQL'in bulduğu aday: {s(aday_n)}")
    print(f"  puanı pozitif olan: {s(sy['pozitif'])} (puanı ≤ 0 olduğu için döngünün durduğu: "
          f"{s(aday_n - sy['pozitif'])})")
    print(f"  'bu blok zaten verildi' diye atlanan: {s(sy['blok'])}")
    print(f"  kapasite yüzünden atlanan: {s(sy['kapasite'])}")
    print(f"  seçilen hareket: {s(sy['secilen'])}")
    print(f"  minimum koli filtresinin kestiği: {s(sy['min_koli_kesilen'])}")
    h = plan.hareketler
    rota = len(h.groupby(["verici", "alici"], observed=True))
    print(f"  kalan plan: {s(len(h))} hareket · {s(h.adet.sum())} adet · {s(rota)} rota")


def fark_bolumu(greedy, mip_plan, oz_g, oz_m, ozel_g, ozel_m, adlar, p) -> dict:
    print("\n=== İKİ PLANIN FARKI ===")
    f = plan_farki(greedy.hareketler, mip_plan.hareketler)
    print(f"  açgözlü {s(oz_g['option_sayisi'])} blok · MIP {s(oz_m['option_sayisi'])} blok")
    print(f"  ortak (verici, option) bloğu: {s(f['ortak'])} ({s(f['ortak_adet'])} adet) · "
          f"bunların alıcısı farklı olan: {s(f['ortak_alici_farkli'])} · aynı hareket: "
          f"{s(f['ortak_ayni_hareket'])}")
    print(f"  yalnız açgözlünün taşıdığı blok: {s(f['yalniz_a'])} ({s(f['yalniz_a_adet'])} adet) · "
          f"yalnız MIP'in: {s(f['yalniz_b'])} ({s(f['yalniz_b_adet'])} adet)")
    print(f"  aynı malı taşıyorlar mı: {'evet' if f['ayni_mal'] else 'hayır'}")
    dnet = fark(oz_g["net_kazanc_tl"], oz_m["net_kazanc_tl"])
    drota = oz_g["rota_sayisi"] - oz_m["rota_sayisi"]
    print(f"  net kazanç farkı (MIP − açgözlü): {tl(oz_m['net_kazanc_tl'])} − {tl(oz_g['net_kazanc_tl'])} = "
          f"{tl(dnet)} = Σw farkı {tl(fark(ozel_g['sw'], ozel_m['sw']))} + rota farkı {s(drota)} × "
          f"{s(p.rota_sabiti_tl)} TL ({tl(drota * p.rota_sabiti_tl)})")
    print(f"  açgözlü, MIP'in net kazancının {y(bolum(oz_g['net_kazanc_tl'], oz_m['net_kazanc_tl']))}'ini "
          f"buluyor · aradaki fark {y(bolum(dnet, oz_m['net_kazanc_tl']))}")
    ms = greedy.sure_sn * 1000
    # basılan iki değerden: MIP sn (bir ondalık) × 1000 / açgözlü ms (bir ondalık)
    kat = yuv(mip_plan.sure_sn, 1) * 1000 / yuv(ms, 1) if yuv(ms, 1) else None
    print(f"  çözüm süresi: MIP {s(mip_plan.sure_sn, 1)} sn / açgözlü {s(ms, 1)} ms = {s(kat)} kat")

    o = ornek_rota(greedy.hareketler, mip_plan.hareketler)
    print("\n  örnek rota (MIP'in, blokları açgözlüde en az iki farklı alıcıya giden en dolu rotası):")
    if o is None:
        print("    yok")
    else:
        print(f"    {adlar[o['verici']]} ({o['verici']}) → {adlar[o['alici']]} ({o['alici']}) · "
              f"{o['option']} option · {s(o['adet'])} adet")
        for opt, n, g in o["satirlar"]:
            hedef = f"{adlar[g]} ({g})" if g else "taşımıyor"
            print(f"    {opt:14} {n:>4} adet · açgözlü planda: {adlar[o['verici']]} → {hedef}")
        farkli = len({g for _, _, g in o["satirlar"] if g})
        ayni = sum(1 for _, _, g in o["satirlar"] if g == o["alici"])
        baska = sum(1 for _, _, g in o["satirlar"] if g and g != o["alici"])
        print(f"    açgözlü bu blokları {farkli} farklı alıcıya gönderiyor · MIP'le aynı alıcıya "
              f"({adlar[o['alici']]}) giden {ayni}, başka alıcıya giden {baska}, taşımadığı "
              f"{o['option'] - ayni - baska}")
    return f


def lp_bolumu(df: pd.DataFrame, kapasite: dict, mip_plan, oz_m: dict, p) -> float:
    print("\n=== LP GEVŞETMESİ ===")
    t0 = time.perf_counter()
    model, x, yv = mip.kur(df, kapasite, p)
    for d in list(x.values()) + list(yv.values()):
        d.cat = pulp.LpContinuous
        d.lowBound, d.upBound = 0, 1
    model.solve(pulp.PULP_CBC_CMD(msg=0))
    sure = time.perf_counter() - t0

    def kesirli(degiskenler) -> int:
        return sum(1 for d in degiskenler if d.value() is not None and 1e-6 < d.value() < 1 - 1e-6)

    gevsek = pulp.value(model.objective)
    tam = mip_plan.amac
    print(f"  LP gevşetmesi (üst sınır) {tl(gevsek, 2)} · LP durumu {pulp.LpStatus[model.status]} · "
          f"kurma + çözme {s(sure, 1)} sn")
    print(f"  tam sayı çözüm (MIP planı) {tl(tam, 2)}")
    print(f"  boşluk {tl(fark(tam, gevsek, 2), 2)} ({y(bolum(fark(tam, gevsek, 2), tam, 2, 2), 2)})")
    print(f"  gevşetilmiş çözümde kesirli çıkan: {s(kesirli(x.values()))}/{s(len(x))} x · "
          f"{s(kesirli(yv.values()))}/{s(len(yv))} y")
    if mip_plan.sinir is not None:
        print(f"  CBC son sınırı {tl(mip_plan.sinir, 2)} · MIP boşluğu %{s(oz_m['bosluk_yuzde'], 2)} "
              f"(göreli tolerans %{s(p.mip_bosluk_orani * 100, 1)}) · CBC'nin LP'den kapattığı "
              f"{tl(fark(mip_plan.sinir, gevsek, 2), 2)}")
    return gevsek


def demo_bolumu(con, karar, zemin: Zemin, planlar: dict, olcumler: dict, ek: list) -> None:
    print("\n=== DEMO KADRANI ===")
    print("  (spec'teki altı satır; planlar önbellekten; yakalama Lumoda (Basit) / hakem)")
    sonuc = {}
    for vv, aa in DEMO_SATIRLARI:
        p = replace(REFERANS, verici_cover_esigi=float(vv), alici_cover_tavani=float(aa))
        etiket = "kapalı" if aa == 0 else str(aa)
        parca = []
        oz_y = {}
        for yontem in YONTEMLER:
            plan, oz = degerlendirme.boru_hatti(con, karar, p, yontem, onbellek=ONBELLEK)
            ob, oh = zemin.olc(plan.hareketler)
            ad = f"demo {vv}|{aa}|{yontem}"
            planlar[ad] = (plan.hareketler, oz)
            olcumler[f"{ad} basit"], olcumler[f"{ad} hakem"] = ob, oh
            oz_y[yontem] = oz
            sonuc[(vv, aa, yontem)] = (oz, ob, oh)
            bosluk = f" %{s(oz['bosluk_yuzde'], 2)}" if oz.get("bosluk_yuzde") is not None else ""
            parca.append(f"{yontem} {s(oz['option_sayisi'])} hrkt / {s(oz['rota_sayisi'])} rota / "
                         f"{tl(oz['net_kazanc_tl'])} / {y(ob.yakalama)} · {y(oh.yakalama)} / "
                         f"{oz['durum']}{bosluk}")
        m, g = oz_y["mip"], oz_y["greedy"]
        if m["durum"] in ("optimal", "limit"):
            ek.append((f"demo {vv}|{aa}: MIP net kazancı açgözlüden {KORUNUM_TOLERANSI_TL} TL'den "
                       "fazla düşük", m["net_kazanc_tl"] >= g["net_kazanc_tl"] - KORUNUM_TOLERANSI_TL))
        print(f"  verici≥{vv:<3} alıcı≤{etiket:<6} | " + "  ·  ".join(parca))

    def karsilastir(a, b):
        for yontem in YONTEMLER:
            oa, ba, ha = sonuc[(*a, yontem)]
            ob_, bb, hb = sonuc[(*b, yontem)]
            dn = fark(oa["net_kazanc_tl"], ob_["net_kazanc_tl"])
            print(f"  {yontem}: {a[0]}|{a[1]} → {b[0]}|{b[1]}: hareket {s(oa['option_sayisi'])} → "
                  f"{s(ob_['option_sayisi'])} ({'+' if ob_['option_sayisi'] >= oa['option_sayisi'] else ''}"
                  f"{s(ob_['option_sayisi'] - oa['option_sayisi'])}) · "
                  f"adet {s(oa['tasinan_adet'])} → {s(ob_['tasinan_adet'])} · net {tl(oa['net_kazanc_tl'])} → {tl(ob_['net_kazanc_tl'])} "
                  f"({'+' if dn >= 0 else ''}{tl(dn)}, {'+' if dn >= 0 else ''}"
                  f"{y(bolum(dn, oa['net_kazanc_tl']))}) · yakalama Basit {y(ba.yakalama, 2)} → "
                  f"{y(bb.yakalama, 2)} · hakem {y(ha.yakalama, 2)} → {y(hb.yakalama, 2)}")

    print("\n  (karşılaştırmalarda yakalama iki ondalıkla: bir ondalıkta eşit görünen farklar için)")
    print("  eşik dersi (alıcı tavanını açmak):")
    karsilastir((6, 0), (6, 6))
    print("  18/14 ile 14/6:")
    karsilastir((14, 6), (18, 14))


def getiri_bolumu(con, karar, p, greedy, mip_plan, aday, zemin: Zemin, olc_g, olc_m,
                  planlar: dict, ek: list) -> None:
    print("\n=== GETİRİ ===")
    g = greedy.hareketler
    H = p.ufuk_hafta

    strler = metrikler.strler(con, karar)
    str_h = {(str(m), str(o)): v for m, o, v in zip(strler.magaza_id, strler.option_id, strler.str_orani)}
    sv = [str_h[(str(v), str(o))] for v, o in zip(g.verici, g.option_id) if (str(v), str(o)) in str_h]
    sa = [str_h[(str(a), str(o))] for a, o in zip(g.alici, g.option_id) if (str(a), str(o)) in str_h]
    str_v, str_a = float(np.mean(sv)), float(np.mean(sa))
    str_fark = fark(str_v * 100, str_a * 100, 1)
    print(f"  STR (açgözlü referans plan, karara dek): verici ortalaması {y(str_v)} ({len(sv)} hareket) · "
          f"alıcı ortalaması {y(str_a)} ({len(sa)} hareket) · fark {s(str_fark, 1)} puan")

    print("\n  model ne varsaydı — veri ne dedi (açgözlü referans plan):")
    ort = ortuk_oranlar(g, aday, H)
    print(f"    modelin varsaydığı alıcı satma oranı: ort {y(ort.p_alici.mean())} · medyan "
          f"{y(ort.p_alici.median())} · %100'e dayanan {s((ort.p_alici >= 1).sum())}/{s(len(ort))} hareket")
    print(f"    modelin varsaydığı 'kalsaydı vericide satma' oranı: ort {y(ort.p_verici.mean())} · "
          f"medyan {y(ort.p_verici.median())} · %0 olan {s((ort.p_verici <= 0).sum())}/{s(len(ort))} hareket")
    ob, oh = olc_g
    print(f"    gerçekleşen p_alıcı (pencerede kayba giden taşınan mal): Lumoda (Basit) {y(ob.p_alici)} · "
          f"hakem {y(oh.p_alici)}")
    print(f"    gerçekleşen p_verici (taşınan malın vericide pencerede satılan payı, üst sınır): "
          f"{y(ob.p_verici)}")
    mb, mh = olc_m
    print(f"    MIP planı: p_alıcı Basit {y(mb.p_alici)} · hakem {y(mh.p_alici)} · p_verici {y(mb.p_verici)}")
    tas = olcum.tasinan(con, g, karar)
    for ad, kt in (("Basit", zemin.basit), ("hakem", zemin.hakem)):
        hb = hareket_basina_p_alici(tas, kt)
        print(f"    hareket başına gerçekleşen p_alıcı ({ad}): medyan {y(hb.median())} · "
              f"%70 ve üstü {s((hb >= 0.7).sum())}/{s(len(hb))} hareket ({y((hb >= 0.7).mean())}) · "
              f"%100 olan {s((hb >= 1).sum())} · %0 olan {s((hb <= 0).sum())}")

    hareketler = getiri.hareketleri_getir(con, karar)
    adet = int(hareketler.adet.sum())
    rota = len(hareketler.groupby(["verici", "alici"], observed=True))
    brut = float((hareketler.adet * (hareketler.liste - hareketler.alis)).sum())
    maliyet_deg = float((hareketler.adet * hareketler.alis).sum())
    liste = float((hareketler.adet * hareketler.liste).sum())
    ek.append(("getiri hareketleri açgözlü referans planla aynı (blok kümesi ve adet)",
               plan_farki(hareketler, g)["ayni_mal"] and adet == int(g.adet.sum())))
    print(f"\n  brüt kâr (liste − alış) {tl(brut, 2)} · maliyet değeri (alış) {tl(maliyet_deg, 2)}")
    print(f"  taşınan adet {s(adet)} · sevkiyat {s(rota)} · liste değeri {tl(liste, 2)} · "
          f"brüt marj (brüt kâr / liste) {y(brut / liste)}")
    urun_n, o_min, o_maks = con.execute(
        "select count(distinct option_id), min(alis_fiyati / liste_fiyati), "
        "max(alis_fiyati / liste_fiyati) from urun").fetchone()
    ho = hareketler.alis / hareketler.liste
    print(f"  alış/liste oranı: {s(urun_n)} option'da {s(o_min, 3)} – {s(o_maks, 3)} "
          f"(brüt marj {y(1 - o_maks)} – {y(1 - o_min)}) · taşınan malda {s(ho.min(), 3)} – "
          f"{s(ho.max(), 3)} (brüt marj {y(1 - ho.max())} – {y(1 - ho.min())}) → marj ürüne göre değişiyor")

    print("\n  kâr-ağırlıklı plan (w brüt kârla: adet başına liste − alış):")
    df_kar = terazi.agirliklandir(aday, p, deger="kar")
    wk = {(str(v), str(a), str(o)): w for v, a, o, w in
          zip(df_kar.verici, df_kar.alici, df_kar.option_id, df_kar.w)}
    for yontem, ciro_plan in (("greedy", greedy), ("mip", mip_plan)):
        plan_k, oz_k = degerlendirme.boru_hatti(con, karar, p, yontem, onbellek=ONBELLEK, deger="kar")
        planlar[f"kar {yontem}"] = (plan_k.hareketler, oz_k)
        hc, hk = ciro_plan.hareketler, plan_k.hareketler
        kc = {(str(v), str(a), str(o)) for v, a, o in zip(hc.verici, hc.alici, hc.option_id)}
        kk = {(str(v), str(a), str(o)) for v, a, o in zip(hk.verici, hk.alici, hk.option_id)}
        rc = len(hc.groupby(["verici", "alici"], observed=True))
        ciro_kar = sum(wk[k] for k in kc) - rc * p.rota_sabiti_tl
        dk = fark(ciro_kar, oz_k["net_kazanc_tl"])
        bosluk = f" · boşluk %{s(oz_k['bosluk_yuzde'], 2)}" if oz_k.get("bosluk_yuzde") is not None else ""
        print(f"    {yontem}: {s(len(hk))} hareket · ciro planından farklı hareket: yalnız kâr planında "
              f"{s(len(kk - kc))}, yalnız ciro planında {s(len(kc - kk))} (ortak {s(len(kk & kc))}) · "
              f"durum {oz_k['durum']}{bosluk}")
        print(f"      net kazanç kâr cinsinden: kâr planı {tl(oz_k['net_kazanc_tl'])} · ciro planı "
              f"kârla değerlenince {tl(ciro_kar)} · fark {tl(dk)} "
              f"({y(bolum(dk, ciro_kar), 2)})")

    pa, pv = ob.p_alici * 100, ob.p_verici * 100
    pa_h = oh.p_alici * 100
    na, nv = getiri.olculen_nokta(pa), getiri.olculen_nokta(pv)
    olcen_fark = fark(pv, pa, 1)
    print(f"\n  ölçülen nokta: p_alıcı {s(pa, 1)} · p_verici {s(pv, 1)} · fark {s(olcen_fark, 1)} puan "
          f"(kadranda {na} / {nv}) · hakemle p_alıcı {s(pa_h, 1)}, fark {s(fark(pv, pa_h, 1), 1)} puan")
    print("  maliyet paketleri (getiri.py; toplama ve kargo varsayım, yıpranma saha kalibrasyonu):")
    for ad in ("dusuk", "orta", "yuksek"):
        pk = getiri.MALIYET_PAKETLERI[ad]
        toplama, kargo = pk.toplama_birim_tl * adet, pk.kargo_rota_tl * rota
        yip = pk.yipranma_orani * maliyet_deg
        olc = getiri.hesapla(hareketler, pk, pa, pv)
        kadran = getiri.hesapla(hareketler, pk, float(na), float(nv))
        hak = getiri.hesapla(hareketler, pk, pa_h, pv)
        print(f"    {ad:7} toplama {s(adet)} adet × {s(pk.toplama_birim_tl)} TL = {tl(toplama)} · "
              f"kargo {s(rota)} sevkiyat × {s(pk.kargo_rota_tl)} TL = {tl(kargo)} · yıpranma "
              f"%{s(pk.yipranma_orani * 100)} × maliyet değeri = {tl(yip)} · toplam "
              f"{tl(yuv(toplama) + yuv(kargo) + yuv(yip))}")
        print(f"            yıpranma adet başına {tl(yip / adet, 2)} (beş taşımada {tl(5 * yuv(yip / adet, 2), 2)}) · "
              f"başabaş fark {s(olc['basabas_fark_puan'], 1)} puan · başabaş alıcı ihtimali "
              f"(vericide {s(pv, 1)}) %{s(yuv(pv, 1) + yuv(olc['basabas_fark_puan'], 1), 1)}")
        print(f"            ölçülen noktada net kâr {tl(olc['net_kar_tl'])} · kadranda ({na}/{nv}) "
              f"{tl(kadran['net_kar_tl'])} · hakemin p_alıcısıyla {tl(hak['net_kar_tl'])} · "
              f"ciro etkisi (ölçülen) {tl(olc['ciro_etkisi_tl'])}")
        print(f"            STR farkı {s(str_fark, 1)} puan vs başabaş "
              f"{s(olc['basabas_fark_puan'], 1)} · ölçülen fark {s(olcen_fark, 1)} puan "
              f"{'≥' if olcen_fark >= yuv(olc['basabas_fark_puan'], 1) else '<'} başabaş")

    icerik = getiri.uret(con, karar, ob)
    sonuclar = icerik["sonuclar"]
    netler = {k: v["ozet"]["net_kar_tl"] for k, v in sonuclar.items()}
    en_kotu, en_iyi = min(netler, key=netler.get), max(netler, key=netler.get)
    karli = sum(1 for v in netler.values() if v > 0)
    kad = [k["degerler"] for k in icerik["parametreler"]]
    print(f"\n  getiri ızgarası: alıcı {kad[0]} × verici {kad[1]} × paket {len(kad[2])} = {len(netler)} hücre · "
          f"kârlı {karli} · zararlı {len(netler) - karli}")
    print(f"    en kötü hücre {en_kotu}: {tl(netler[en_kotu])} · en iyi hücre {en_iyi}: {tl(netler[en_iyi])}")
    for paket in ("dusuk", "orta", "yuksek"):
        kz = sum(1 for k, v in netler.items() if k.endswith(paket) and v > 0)
        print(f"    {paket}: kârlı {kz}/{len(netler) // 3}")


def anlati_bolumu(kirik: int) -> None:
    """ANLATI VARSAYIMLARI: 1. ve 2. yazının elle sayıları ve onlardan türeyenler."""
    v = ANLATI_VARSAYIMLARI
    print("\n=== ANLATI VARSAYIMLARI ===")
    print("(kurgunun varsayımı, veriden değil; değişirse kayıt defterine yazılır)")
    for anahtar, deger in v.items():
        print(f"  {anahtar}: {s(deger)} (varsayım)")
    saat = kirik * v["cift_basina_dakika"] / 60
    print(f"  toplam saat = kırık {s(kirik)} × {v['cift_basina_dakika']} dakika / 60 = {s(saat, 1)} saat "
          f"(≈ {s(round(saat))} saat) · haftalık mesainin {s(bolum(saat, v['haftalik_mesai_saat'], 1), 1)} katı")
    print(f"  kalan çift = kırık {s(kirik)} − akşam çözülen {v['aksam_cozulen_cift']} = "
          f"{s(kirik - v['aksam_cozulen_cift'])}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    a = _ayristir(argv)
    eksik = hakem_eksik(Path(a.hakem))
    if eksik:
        for m in eksik:
            print(m, file=sys.stderr)
        return 1
    try:
        zorla = hikaye_sec.hikaye_ayristir(a.hikaye) if a.hikaye else None
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    try:
        con = veri.baglan(a.db)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    p = REFERANS
    karar = veri.karar_ani(con)
    veri.gorunumler(con, karar)
    try:
        kayip = hazirla.oku_kayip(CIKTI, con, karar, p.olcum_hafta)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1

    bas_sure = time.perf_counter()
    # hakem büyük: okunur okunmaz ölçüm penceresine süzülür
    kars = hakem.oku(Path(a.hakem))["karsilanmayan"]
    pb, pbit = olcum.pencere(karar, p.olcum_hafta)
    kars = kars.loc[(kars["tarih"] >= pd.Timestamp(pb)) & (kars["tarih"] < pd.Timestamp(pbit)),
                    ["tarih", "magaza_id", "urun_id", "karsilanmayan"]].reset_index(drop=True)

    # Bütün rapor tampona yazılır; korunum tutmazsa stdout'a tek satır gitmez (tamponla).
    kod, metin = tamponla(lambda: _govde(con, karar, p, kayip, kars, zorla))
    if kod:
        return kod
    sys.stdout.write(metin)
    print(f"rapor süresi {time.perf_counter() - bas_sure:.0f} sn", file=sys.stderr)
    return 0


def _olcum_paydasi(zemin: Zemin) -> None:
    """Yakalama paydaları: Basit ve hakem aynı hücre evreninde mi, dışarıda ne kaldı."""
    print("\nölçüm paydası (ölçüm penceresi, adet):")
    print(f"  Basit kaybı (evren içi) {s(zemin.basit.kayip.sum())} · çeşit hücresi dışında kalan Basit "
          f"hücresi {s(zemin.basit_cesit_disi[0])} ({s(zemin.basit_cesit_disi[1])} adet)")
    print(f"  hakem karşılanmayan talebi: toplam {s(zemin.hakem_tum.kayip.sum())} · online "
          f"{s(zemin.hakem_onl.kayip.sum())} · evren içi {s(zemin.hakem_evren.kayip.sum())} · evren içi "
          f"çeşit içi (hakem paydası) {s(zemin.hakem.kayip.sum())} · evren içi çeşit dışı (paydaya "
          f"girmez) {s(zemin.hakem_evren.kayip.sum() - zemin.hakem.kayip.sum())}")
    print(f"  hakem / Basit paydası {s(bolum(zemin.hakem.kayip.sum(), zemin.basit.kayip.sum()), 2)}")


def _govde(con, karar: date, p: Parametreler, kayip: pd.DataFrame, kars: pd.DataFrame,
           zorla) -> None:
    """Raporun bütün bölümleri, sırasıyla; en sonda korunum (tutmazsa AssertionError)."""
    adlar = _magaza_adlari(con)
    v = veri_bolumu(con, karar, p)
    karar_bolumu(con, karar, p)
    zemin = Zemin(con, karar, kayip, kars, p.olcum_hafta)

    greedy, oz_g = degerlendirme.boru_hatti(con, karar, p, "greedy", onbellek=ONBELLEK)
    mip_plan, oz_m = degerlendirme.boru_hatti(con, karar, p, "mip", onbellek=ONBELLEK)
    veri.gorunumler(con, karar)

    hikaye_bolumu(con, karar, p, kayip, zemin, greedy, mip_plan, zorla, adlar)

    # --- referans senaryo
    veri.gorunumler(con, karar)
    aday = adaylar_mod.uret(con, karar, p)
    df = terazi.agirliklandir(aday, p)
    kapasite = adaylar_mod.kapasite_boslugu(con, karar, tepe_hafta=p.tepe_hafta)
    rotalar = sorted(set(zip(df.verici, df.alici)))
    blok_k, kap_k = len(df.groupby(["verici", "option_id"])), df.alici.nunique()
    n_deg = len(df) + len(rotalar)
    print("\n=== REFERANS SENARYO (verici ≥ 6 · alıcı tavanı kapalı · asgari hız 1) ===")
    print(f"aday: {s(len(df))} (puanı pozitif {s((df.w > 0).sum())}) · aday verici mağaza "
          f"{s(df.verici.nunique())} · aday alıcı mağaza {s(df.alici.nunique())} · aday option "
          f"{s(df.option_id.nunique())}")
    print(f"kümenin dışarıda bıraktığı üçlü: {s(v['ust_sinir'])} − {s(len(df))} = {s(v['ust_sinir'] - len(df))}")
    print(f"x değişkeni {s(len(df))} + y değişkeni {s(len(rotalar))} = {s(n_deg)} ikili değişken")
    print(f"olası atama 2^{s(n_deg)} ≈ 10^{s(math.floor(n_deg * math.log10(2)))}")
    print(f"kısıt: blok {s(blok_k)} + kapasite {s(kap_k)} + rota bağlama {s(len(df))} + koli "
          f"{s(len(rotalar))} = {s(blok_k + kap_k + len(df) + len(rotalar))}")
    _olcum_paydasi(zemin)

    kirik_kume = {(str(m), str(o)) for m, o in zip(v["kirik"].magaza_id, v["kirik"].option_id)}
    olc_g, olc_m = zemin.olc(greedy.hareketler), zemin.olc(mip_plan.hareketler)
    ozel_g = plan_bolumu("greedy", greedy, oz_g, *olc_g, kirik_kume, kapasite, p, df)
    ozel_m = plan_bolumu("mip", mip_plan, oz_m, *olc_m, kirik_kume, kapasite, p, df)

    adim_bolumu(len(df), greedy)
    fark_bolumu(greedy, mip_plan, oz_g, oz_m, ozel_g, ozel_m, adlar, p)
    gevsek = lp_bolumu(df, kapasite, mip_plan, oz_m, p)

    planlar = {"greedy": (greedy.hareketler, oz_g), "mip": (mip_plan.hareketler, oz_m)}
    olcumler = {"greedy basit": olc_g[0], "greedy hakem": olc_g[1],
                "mip basit": olc_m[0], "mip hakem": olc_m[1]}
    sy = greedy.sayaclar
    tolerans = 1.0 + 1e-6 * abs(gevsek)        # TL: CBC log sınırı ve LP çözümü yuvarlı
    ek = [
        ("açgözlü sayaçları: pozitif = blok + kapasite + seçilen",
         sy["pozitif"] == sy["blok"] + sy["kapasite"] + sy["secilen"]),
        ("açgözlü sayaçları: seçilen − min koli = plan", sy["secilen"] - sy["min_koli_kesilen"] == len(greedy.hareketler)),
        ("referans: MIP net kazancı açgözlüden düşük değil",
         mip_plan.durum not in ("optimal", "limit")
         or oz_m["net_kazanc_tl"] >= oz_g["net_kazanc_tl"] - KORUNUM_TOLERANSI_TL),
        ("ölçümün taşınan adedi = özetin taşınan adedi (greedy)", olc_g[0].tasinan_adet == oz_g["tasinan_adet"]),
        ("ölçümün taşınan adedi = özetin taşınan adedi (mip)", olc_m[0].tasinan_adet == oz_m["tasinan_adet"]),
        ("hakem ve Basit paydası aynı evrenle süzüldü", olc_g[0].payda == float(zemin.basit.kayip.sum())
         and olc_g[1].payda == float(zemin.hakem.kayip.sum())),
        ("basılan net kazanç = basılan Σw − rota × R (greedy)", ozel_g["net_tutar"]),
        ("basılan net kazanç = basılan Σw − rota × R (mip)", ozel_m["net_tutar"]),
        (f"LP gevşetmesi ({gevsek:.2f}) ≥ CBC sınırı ({mip_plan.sinir}) ≥ MIP amacı ({mip_plan.amac:.2f})",
         mip_plan.sinir is not None and gevsek + tolerans >= mip_plan.sinir
         and mip_plan.sinir + tolerans >= mip_plan.amac),
    ]

    getiri_bolumu(con, karar, p, greedy, mip_plan, aday, zemin, olc_g, olc_m, planlar, ek)
    demo_bolumu(con, karar, zemin, planlar, olcumler, ek)
    anlati_bolumu(len(v["kirik"]))

    n = korunum(planlar, olcumler, zemin.evren,
                {"Basit": zemin.basit, "hakem": zemin.hakem}, p, ek)
    print("\n=== KORUNUM ===")
    print(f"  {n} denetim tuttu (özet ↔ hareket tablosu, kurtarılan ≤ payda, p ∈ [0, 1], "
          "paydalar aynı evrende, MIP ≥ açgözlü, LP ≥ CBC sınırı ≥ MIP)")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
