"""RPT dizisinin (6 yazı, `/rpt/tekrar-siparis/`) yayımlanacak BÜTÜN sayıları buradan basılır.

    cd vakalar/rpt
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py [--hikaye HIT:GEC] > cikti/rapor.txt

Kalıcı kural: yazıya yeni bir sayı girmeden önce buraya eklenir; ortak sayı denetimi
(`python -m perakende_analitik.sayi_denetimi --yazi ../../site/src/content/yazi/rpt/tekrar-siparis
--rapor cikti/rapor.txt`) yazılardaki her sayının bu çıktıda geçtiğini denetler. Sayılar
Türkçe basılır (binlik nokta, ondalık virgül, `%12,3`, `−%3,2`). Uydurma sayı yasaktır;
elle konmuş anlatı sayıları yalnız ANLATI VARSAYIMLARI'ndadır ve orada etiketlidir.

Bölümler (bu başlıklarla, bu sırayla):

    A (yayımlanan v4 tabloları + hakem; bu dosya)
    === HİKÂYE ===       1. yazı: iki sahne (`hikaye_sec`), plan, ilk alım, Banu'nun RPT'si,
                         mağaza tabloları, gerçek talep ve kaybolan satış (hakem), Banu'nun
                         RPT'lerinin akıbeti (FIFO), bir sezonda kaç soru, hit'in sonu
    === KARAR ===        2. yazı: tedarikçiler, yaşam eğrisi payları, geliş sonrası kalan eğri,
                         karar anı Basit düzeltmesinin hit'teki karşılığı
    === SANSÜR ===       3. yazı: dört katman, hakeme karşı WAPE / yanlılık (AW24, SS25 × h),
                         eğrinin sansürü (çıplak / düzeltilmiş / gerçek), kategori × dalga
    B (oyun; `rapor_b.py`)
    === ADAY ===         4. yazı
    === MİKTAR ===       5. yazı
    === SONUÇ ===        6. yazı (dağıtım seçimi, kollar, ayrıştırma, kâhin, hikâye option'ları)
    === YOLLAR ===       6. yazı ("şans mı": 5 yol)
    === ANLATI VARSAYIMLARI ===
    === KORUNUM ===

Rapor önce tampona yazılır; korunum tutmazsa stdout'a tek satır gitmez, mesaj stderr'e,
çıkış kodu 1 (`tamponla`). Basılan her fark ve oran basılan işlenenlerden hesaplanır
(`yuv`, `fark`, `bolum`, `yuzde_bolum`): "A → B (+C)" satırı elle yapılan hesapla tutar.
Ölçülen süre basılmaz: aynı girdiyle iki koşu bayt bayt aynıdır.

PLAN (Ruling R8). Plan yayımlanmaz: `motor.politika_gorunumu(motor.dunya())`'dan (Lumoda'nın
gördüğü option planı) okunur ve `hikaye_sec.ozet(plan=)`'e verilir; `cikti/plan_sezon.csv`
okunmaz.

HAKEM. Kestirim girdidir, hakem ölçüdür. `perakende_analitik.hakem` yalnız burada içe aktarılır
(yayımlanan dünyanın gerçeği: hikâyenin gerçek talebi, SANSÜR'ün WAPE'si); `rpt` paketi onu
görmez (`tests/test_sizinti.py`). Oyun koşularının gerçeği her koşunun `Kosu.gercek`'inden
(`olcutler`) gelir. Hakem önbelleği yoksa kuran komut stderr'e yazılır, çıkış kodu 1.

ÖNBELLEK. Oyunun 14 + 4 koşusu ve yolların öğrenmesi `cikti/kosular`, `cikti/yollar`'dan okunur
(`oyun.hazirlik`, `oyun.tum_kollar`; ~4,5 saatlik ızgara). Rapor koşu kodu özetine girmez
(Ruling R3): bu dosyayı değiştirmek önbelleği bozmaz. Kaç koşunun önbellekten geldiği
stderr'e yazılır; önbellekte olmayan koşu motoru çalıştırır (dakikalar).
"""

import argparse
import contextlib
import io
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from perakende_analitik import hakem
from rpt import aday, egri, hazirla, hikaye, hikaye_sec, kaynak, motor, olcutler, oyun, politika, sansur

warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*force_all_finite.*", category=FutureWarning)

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
HAKEM_KOMUTU = "cd vakalar/ortak && .venv/Scripts/python -m perakende_analitik.hakem"
HAKEM_DOSYALARI = ("karsilanmayan.parquet", "ikame_alinan.parquet", "meta.json")

OYUN = oyun.OYUN                          # ("AW24", "SS25")
HIKAYE_SEZONU = "SS25"
ONCEKI_SEZON = {"SS25": "AW24", "AW24": "SS24"}
KARAR_H = hikaye_sec.HIKAYE_HAFTASI       # 3: Banu'nun kuralının ilk pazartesisi
HAFTALAR = sansur.KARAR_HAFTALARI         # 2..6
MENSELER = ("Yerli", "Yakın", "Uzak Doğu")
TUTAN_ESIGI = sansur.HIT_ESIGI            # gerçek / plan ≥ 1,5

# Katman adları (sansur.KATMAN_ADI v3'ten bayat: b ve d karar anı Basit'inden gelir; sansur.py
# koşu kod özetinde olduğundan burada yeniden adlandırılır, sansur.py değişmez)
KATMAN_ADI = {
    "a": "a  çıplak satış (rapor)",
    "b": "b  karar anı Basit'i (D) ÷ h × hafta",
    "c": "c  çıplak satış ÷ çıplak eğri (FRR)",
    "d": "d  karar anı Basit'i (D) ÷ düz. eğri",
    "a_hiz": "   çıplak hız × hafta",
    "c_duz_egri": "   çıplak satış ÷ düzeltilmiş eğri",
    "plan": "   buyer planı",
}

# Hikâyedeki elle sayılar (1.–3. yazı): veriden gelmez. Değer değişirse kayıt defterine yazılır.
#   toplanti_saati            1. yazının sahnesi ("Pazartesi, 09:15")
#   frr_*                     Fisher, Rajaram ve Raman (2001): ilk iki haftanın satışından sezon
#                             tahmininin hatası %8, alım komitesinin sezon öncesi tahmininin %55
ANLATI_VARSAYIMLARI = {"toplanti_saati": "09:15", "frr_ilk_iki_hafta_hatasi": 0.08,
                       "frr_alim_komitesi_hatasi": 0.55, "frr_yayin_yili": 2001}


# ---------------------------------------------------------------------------
# Biçim
# ---------------------------------------------------------------------------

def _yok(x) -> bool:
    if x is None or x is pd.NaT:
        return True
    try:
        return bool(isinstance(x, (float, np.floating)) and np.isnan(x))
    except TypeError:
        return False


def _sifir_mi(metin: str) -> bool:
    return metin.lstrip("-").replace(".", "").replace(",", "").strip("0") == ""


def s(x, ondalik: int = 0) -> str:
    """Türkçe sayı: 1.234.567 · 0,55 · −3,2 (yuvarlanınca sıfır olan negatif işaretsiz)."""
    if _yok(x):
        return "—"
    metin = f"{float(x):,.{ondalik}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if _sifir_mi(metin):
        metin = metin.lstrip("-")
    return metin.replace("-", "−")


def y(x, ondalik: int = 1) -> str:
    """Yüzde (x oran): 0,123 → %12,3; negatif → −%3,2."""
    if _yok(x):
        return "—"
    govde = s(abs(100 * float(x)), ondalik)
    return ("−%" if x < 0 and not _sifir_mi(govde) else "%") + govde


def tl(x, ondalik: int = 0) -> str:
    """TL tutarı: 4.978.979 TL."""
    return "—" if _yok(x) else f"{s(x, ondalik)} TL"


def mn(x, ondalik: int = 2) -> str:
    """Milyon: 8.688.770 → 8,69 milyon."""
    return "—" if _yok(x) else f"{s(float(x) / 1e6, ondalik)} milyon"


def t_(tarih) -> str:
    return pd.Timestamp(tarih).strftime("%Y-%m-%d") if not _yok(tarih) and pd.notna(tarih) else "—"


# Basılan her fark ve oran, işlenenlerin BASILAN (yuvarlanmış) değerlerinden hesaplanır.

def yuv(x, ondalik: int = 0) -> float:
    """`s(x, ondalik)`'ın bastığı değer."""
    return float(f"{float(x):.{ondalik}f}")


def fark(a, b, ondalik: int = 0) -> float:
    """b − a, ikisi de `ondalik` hanede basıldığı gibi."""
    return yuv(yuv(b, ondalik) - yuv(a, ondalik), ondalik)


def bolum(a, b, ondalik_a: int = 0, ondalik_b: int = 0) -> float | None:
    """a / b, ikisi de basıldığı gibi."""
    payda = yuv(b, ondalik_b)
    return yuv(a, ondalik_a) / payda if payda else None


def yuzde_bolum(a, b, ondalik: int = 1) -> float | None:
    """İki oranın basılan yüzdelerinin oranı: %22,4 / %39,4."""
    return bolum(100 * float(a), 100 * float(b), ondalik, ondalik)


def pay(a, b) -> float | None:
    """Basılan iki adedin oranı (yüzde basmak için)."""
    return bolum(a, b)


def baslik(metin: str) -> None:
    print(f"\n=== {metin} ===")


def alt(metin: str) -> None:
    print(f"\n--- {metin} ---")


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
# Korunum
# ---------------------------------------------------------------------------

def korunum(denetimler: list[tuple[str, bool]]) -> int:
    """Denetimlerin hepsi tutmalı; tutmayanlar adlarıyla AssertionError. Döner: denetim sayısı."""
    if not denetimler:
        raise AssertionError("korunum: hiç denetim yok")
    hatalar = [ad for ad, ok in denetimler if not bool(ok)]
    if hatalar:
        raise AssertionError("korunum bozuldu:\n  " + "\n  ".join(hatalar))
    return len(denetimler)


def fifo_denetimleri(ak: pd.DataFrame, etiket: str) -> list[tuple[str, bool]]:
    """`hikaye.rpt_akibeti` kovaları: giren adedi tam bölüşür, negatif değil, mağazaya giden
    aralığı çıkışa dek çıkanın içinde, çıkışta depoda duran RPT depo stoğunu aşmaz."""
    k = ak[["rpt_cikisa_kadar", "rpt_outlete", "rpt_depoda_kalan"]]
    return [
        (f"{etiket}: FIFO kovaları = giren RPT", bool((k.sum(axis=1) == ak["rpt_giren"]).all())),
        (f"{etiket}: FIFO kovaları ≥ 0", bool((k >= 0).all().all())),
        (f"{etiket}: mağazaya alt ≤ üst ≤ çıkışa dek çıkan",
         bool(((ak["rpt_magazaya_alt"] <= ak["rpt_magazaya_ust"])
               & (ak["rpt_magazaya_ust"] <= ak["rpt_cikisa_kadar"])).all())),
        (f"{etiket}: çıkışta depodaki RPT ≤ çıkışta depo",
         bool((ak["rpt_depoda_cikista"] <= ak["depo_cikista"]).all())),
    ]


def olcut_denetimleri(o: pd.DataFrame, oz: dict, etiket: str) -> list[tuple[str, bool]]:
    """Kol ölçütleri: option tablosunun toplamı sezon özetine eşit (Δkâr, kurtarılan ve
    parçaları), kurtarılan = kalıcı + ikame (her option), boşa RPT ≤ giren ≤ sipariş."""
    d = [(f"{etiket}: Σ option Δkâr = sezon Δkâr", abs(float(o["d_kar"].sum()) - oz["d_kar"]) < 1.0)]
    for c in ("kurtarilan", "kurtarilan_kalici", "kurtarilan_ikame"):
        d.append((f"{etiket}: Σ option {c} = sezon {c}", abs(float(o[c].sum()) - oz[c]) < 1e-6))
    d.append((f"{etiket}: kurtarılan = kalıcı + ikame",
              bool(np.allclose(o["kurtarilan"], o["kurtarilan_kalici"] + o["kurtarilan_ikame"]))))
    d.append((f"{etiket}: boşa RPT ≤ giren RPT ≤ sipariş",
              bool(((o["rpt_bosa"] <= o["rpt_giren"]) & (o["rpt_giren"] <= o["rpt"])).all())))
    return d


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
    a.add_argument("--hikaye", metavar="HIT:GEC", default=None,
                   help=f"sahneleri geçersiz kılar (varsayılan hikaye_sec.YURUTUCU_SECIMI "
                        f"{hikaye_sec.YURUTUCU_SECIMI})")
    a.add_argument("--hakem", type=Path, default=hakem.HAKEM_DIZINI,
                   help=f"hakem önbelleği (varsayılan {hakem.HAKEM_DIZINI})")
    return a.parse_args(argv)


# ---------------------------------------------------------------------------
# Veri (A): yayımlanan tablolar, plan, hakem, katmanlar, eğriler, hikâye
# ---------------------------------------------------------------------------

@dataclass
class VeriA:
    H: oyun.Hazirlik                   # yol 0'ın gerçekleşen tarihi ve öğrendikleri
    opt: pd.DataFrame                  # option'lar + plan_sezon, plan_cikis (politika görünümü)
    t: dict
    hh: pd.DataFrame                   # oyun sezonlarının hücre-hafta paneli
    panel: pd.DataFrame                # oyun sezonlarının option paneli
    f: pd.DataFrame                    # hikâye seçiminin özellik tablosu (SS25)
    hik: hikaye_sec.Hikaye
    oz: dict                           # hikaye_sec.ozet (plan ile)
    gg: pd.DataFrame                   # hakem gerçek talebi, hücre-gün (Collection, TAM sezonlar)
    kars: pd.DataFrame                 # hakem karşılanmayan, oyun sezonlarının Collection SKU'ları
    gercek: pd.DataFrame               # option başına gerçek talep (lansman → indirim / çıkış)
    katman: dict                       # sezon → katman tablosu (bütün h)
    hata: dict                         # sezon → hata tablosu (hakeme karşı)
    egri_yeniden: dict                 # sezon → rapor içinde yeniden kurulan düzeltilmiş eğri
    egri_kat: dict                     # sezon → düzeltilmiş eğri, kategori × dalga
    egri_gercek: dict = field(default_factory=dict)       # (sezon, hedef) → oyun sezonunun gerçek eğrisi
    egri_gecmis_gercek: dict = field(default_factory=dict)  # sezon → öğrenme sezonlarının gerçek eğrisi
    egri_kat_gercek: dict = field(default_factory=dict)     # sezon → gerçek eğri, kategori × dalga
    ikame: pd.DataFrame | None = None                       # hakem ikame_alinan, oyun Collection SKU'ları
    depo_ertesi: dict = field(default_factory=dict)         # option → (gün, depo stoğu)
    rpt_yay: pd.DataFrame | None = None                     # yayımlanan RPT siparişleri
    akibet: dict = field(default_factory=dict)              # sezon → yayımlanan RPT akıbeti (FIFO)

    @property
    def ogr(self):
        return self.H.ogrenilen


def _plan_ekle(opt: pd.DataFrame) -> pd.DataFrame:
    """Option tablosuna Lumoda'nın gördüğü sezon planı (R8): `politika_gorunumu`."""
    pb = motor.politika_gorunumu(motor.dunya())
    p = pb.optionlar[["option_id", "plan_sezon", "plan_cikis", "ilk_alim"]].rename(
        columns={"ilk_alim": "ilk_alim_dunya"})
    p = p.assign(option_id=p["option_id"].astype(str))
    return opt.assign(option_id=opt["option_id"].astype(str)).merge(p, on="option_id", how="left")


def hazirla_a(hakem_dizini: Path, zorla: tuple[str, str] | None = None) -> VeriA:
    """A bölümlerinin bütün girdileri (stdout'a yazan alt adımlar çağıranda stderr'e yönlenir)."""
    H = oyun.hazirlik(0, ilerleme=None)
    opt = _plan_ekle(H.ogrenilen.optionlar)

    # Katmanlar (karar anı), eğrinin yeniden kurulması (korunum) ve kategori × dalga eğrisi
    katman, egri_yeniden, egri_kat = {}, {}, {}
    con = kaynak.baglan()
    try:
        yol = hazirla.gunluk_yolu(hazirla.VARSAYILAN_CIKTI, con)
        bul = hazirla.carpan_bulucu(con, yol)
        for G in OYUN:
            eg = H.ogrenilen.egriler[G]
            son = max(politika.karar_anlari(opt, G))
            gun = hazirla.havuz_gunlugu(yol, con, oyun.sansur_havuzu(opt, G), son + pd.Timedelta(days=1))
            katman[G] = pd.concat([sansur.sezon_katmanlari(G, h, gun, opt, bul, eg[("ham", "indirim")],
                                                           eg[("duzeltilmis", "indirim")]) for h in HAFTALAR],
                                  ignore_index=True)
            del gun
            gecmis = kaynak.gecmis_sezonlar(G)
            t0 = egri.oyun_baslangici(opt, G)
            gun = hazirla.havuz_gunlugu(yol, con, egri.gecmis_havuzu(opt, gecmis), t0)
            talep = egri.gecmis_talep(gun, opt, G, bul(t0))
            del gun
            egri_yeniden[G] = egri.egri_ogren(talep, opt, gecmis, "duzeltilmis")
            egri_kat[G] = egri.egri_ogren(talep, opt, gecmis, "duzeltilmis", ("ust_kategori", "dalga"))
            del talep
    finally:
        con.close()

    # Yayımlanan tablolar, paneller, hikâye
    t = kaynak.veri_yukle()
    hh = kaynak.hucre_hafta(t, opt, OYUN)
    panel = kaynak.option_panel(t, opt, hh, OYUN)
    f = hikaye_sec.ozellikler(t, opt, hh)
    # R9: geç gelen sahnede Banu'nun RPT'si zarar ettirmiş olmalı; ölçüt oyun koşularından veri olarak
    f = hikaye_sec.banu_zarari_ekle(f, banu_kar_farki(H, HIKAYE_SEZONU))
    hik = hikaye_sec.sec(t, opt, hh, zorla=zorla, f=f)
    oz = hikaye_sec.ozet(t, opt, hh, f, hik, plan=opt.set_index("option_id")["plan_sezon"])

    # Hakem: gerçek talep (hücre-gün) ve karşılanmayan (kalıcı / ikame)
    hk = hakem.oku(hakem_dizini)
    col = opt[(opt["line"] == "Collection") & opt["sezon_kodu"].isin(kaynak.TAM_SEZONLAR)]
    gg = olcutler.gercek_gunluk(t["satis"], hk["karsilanmayan"], hk["ikame_alinan"], t["urun"],
                                col["option_id"])
    u = t["urun"][["urun_id", "option_id"]].astype(str)
    oyun_col = set(col.loc[col["sezon_kodu"].isin(OYUN), "option_id"])
    u = u[u["option_id"].isin(oyun_col)]
    kars = hk["karsilanmayan"]
    kars = kars[kars["urun_id"].astype(str).isin(set(u["urun_id"]))]
    kars = kars.assign(urun_id=kars["urun_id"].astype(str), magaza_id=kars["magaza_id"].astype(str))
    kars = kars.merge(u, on="urun_id").reset_index(drop=True)
    ikame = hk["ikame_alinan"]
    ikame = ikame[ikame["urun_id"].astype(str).isin(set(u["urun_id"]))]
    ikame = ikame.assign(urun_id=ikame["urun_id"].astype(str), magaza_id=ikame["magaza_id"].astype(str))
    ikame = ikame.merge(u, on="urun_id").reset_index(drop=True)
    del hk
    gercek = sansur.gercek_talep(gg, opt)
    hata = {G: sansur.hata_tablosu(katman[G], gercek) for G in OYUN}

    v = VeriA(H=H, opt=opt, t=t, hh=hh, panel=panel, f=f, hik=hik, oz=oz, gg=gg, kars=kars, gercek=gercek,
              katman=katman, hata=hata, egri_yeniden=egri_yeniden, egri_kat=egri_kat, ikame=ikame)
    for G in OYUN:
        for hedef in ("indirim", "cikis"):
            v.egri_gercek[(G, hedef)] = egri.egri_ogren(None, opt, [G], "gercek", hedef=hedef, gercek=gg)
        v.egri_gecmis_gercek[G] = egri.egri_ogren(None, opt, kaynak.gecmis_sezonlar(G), "gercek", gercek=gg)
        v.egri_kat_gercek[G] = egri.egri_ogren(None, opt, [G], "gercek", ("ust_kategori", "dalga"), gercek=gg)

    # Hikâye pazartesisinin ertesi günü depo stoğu (günlük `depo_stok`; yükleyici pazartesileri okur)
    with kaynak.baglan() as con:
        for oid in (hik.hit_option, hik.gec_option):
            o = opt.set_index("option_id").loc[oid]
            gun = pd.Timestamp(o["lansman_tarihi"]) + pd.Timedelta(days=7 * KARAR_H + 1)
            d = con.execute("select sum(d.adet) from depo_stok d join urun u using (urun_id) "
                            "where u.option_id = ? and d.tarih = ?", [oid, gun.date()]).fetchone()[0]
            v.depo_ertesi[oid] = (gun, float(d or 0))
    v.rpt_yay = hikaye.rpt_siparisleri(t, opt)
    for G in (ONCEKI_SEZON[HIKAYE_SEZONU], HIKAYE_SEZONU):
        v.akibet[G] = hikaye.rpt_akibeti(t, opt, G)
    return v


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _o(v: VeriA, oid: str) -> pd.Series:
    return v.opt.set_index("option_id").loc[oid]


def _pzt(o: pd.Series, h: float) -> pd.Timestamp:
    return pd.Timestamp(o["lansman_tarihi"]) + pd.Timedelta(days=round(7 * float(h)))


def _col(v: VeriA, sezon: str) -> pd.DataFrame:
    o = v.opt
    return o[(o["sezon_kodu"] == sezon) & (o["line"] == "Collection")]


def _haftalik_gercek(v: VeriA, oid: str) -> pd.DataFrame:
    """Option'ın lansmandan haftalık: gerçek talep (hakem; mağaza + online), karşılanmayan,
    kalıcı kayıp, ikameye giden, ayrıca mağaza (ONL hariç) karşılanmayanı."""
    o = _o(v, oid)
    lan = pd.Timestamp(o["lansman_tarihi"])
    g = v.gg[v.gg["option_id"] == oid]
    g = g.assign(h=(pd.to_datetime(g["tarih"]) - lan).dt.days // 7)
    k = v.kars[v.kars["option_id"] == oid]
    k = k.assign(h=(pd.to_datetime(k["tarih"]) - lan).dt.days // 7)
    r = pd.DataFrame({"talep": g.groupby("h")["talep"].sum()})
    for c in ("karsilanmayan", "kalici_kayip", "ikameye_giden"):
        r[c] = k.groupby("h")[c].sum()
    r["karsilanmayan_magaza"] = k[k["magaza_id"] != kaynak.ONLINE].groupby("h")["karsilanmayan"].sum()
    # satış (temiz, pozitif; mağaza + online) − başka üründen ikameyle alınan = kendi satış;
    # gerçek talep = kendi satış + karşılanmayan (hakem tanımı)
    u = v.t["urun"][["urun_id", "option_id"]].astype(str)
    sku = set(u.loc[u["option_id"] == oid, "urun_id"])
    sa = v.t["satis"]
    sa = sa[sa["urun_id"].astype(str).isin(sku) & (sa["adet"] > 0)]
    r["satis"] = sa.groupby(((pd.to_datetime(sa["tarih"]) - lan).dt.days // 7).to_numpy())["adet"].sum()
    ik = v.ikame[v.ikame["option_id"] == oid]
    r["ikame_alinan"] = ik.groupby(((pd.to_datetime(ik["tarih"]) - lan).dt.days // 7).to_numpy())["adet"].sum()
    r = r.fillna(0.0).sort_index()
    r["kendi_satis"] = r["satis"] - r["ikame_alinan"]
    return r


def banu_kar_farki(H, sezon: str) -> pd.Series:
    """option_id → Banu'nun koşusunun (mevcut, a: yayımlanan dünya) option kârı − RPT yok
    koşusununki (aynı talep tohumu), sezonun Collection option'ları (oyun koşularının önbelleğinden;
    Ruling R9'un geç gelen ölçütü `hikaye_sec.banu_zarari_ekle`'ye veri olarak)."""
    yok = oyun.kos(H, "rpt_yok", "a", ilerleme=None)
    o = olcutler.ozet(H.kosu, sezon, olcutler.ozet(yok, sezon))
    return o.set_index("option_id")["d_kar"]


def _magaza_gercek(v: VeriA, oid: str, h: int) -> pd.DataFrame:
    """h. pazartesiye dek mağaza başına gerçek talep ve karşılanmayan (kalıcı / ikame)."""
    o = _o(v, oid)
    lan = pd.Timestamp(o["lansman_tarihi"])
    son = lan + pd.Timedelta(days=7 * h)
    g = v.gg[(v.gg["option_id"] == oid) & (v.gg["tarih"] >= lan) & (v.gg["tarih"] < son)]
    k = v.kars[(v.kars["option_id"] == oid) & (v.kars["tarih"] >= lan) & (v.kars["tarih"] < son)]
    r = pd.DataFrame({"gercek_talep": g.groupby("magaza_id")["talep"].sum()})
    for c in ("karsilanmayan", "kalici_kayip", "ikameye_giden"):
        r[c] = k.groupby("magaza_id")[c].sum()
    return r.fillna(0.0)


# ---------------------------------------------------------------------------
# HİKÂYE (1. yazı)
# ---------------------------------------------------------------------------

def sk(x) -> str:
    """Tam sayıysa ondalıksız, değilse bir ondalıkla (13 · 13,5)."""
    return s(x, 0) if float(x) == round(float(x)) else s(x, 1)


def aralik(seri: pd.Series) -> str:
    """min–max; ikisi eşitse tek değer."""
    a, b = seri.min(), seri.max()
    return sk(a) if a == b else f"{sk(a)}–{sk(b)}"


def tipik_rpt_suresi(td: pd.DataFrame) -> dict:
    """Menşe → tedarikçilerin medyan RPT süresi (hafta; kesirli olabilir: Uzak Doğu 13,5). KARAR
    tablosu ve HİKÂYE aynı değeri kullanır."""
    return {m: float(td.loc[td["mense"] == m, "rpt_hafta"].median()) for m in MENSELER}


def _tedarik_ozeti(v: VeriA) -> None:
    td = v.t["tedarikci"]
    tip = tipik_rpt_suresi(td)
    alt("Tedarikçiler: ilk siparişin lansmandan kaç hafta önce verildiği, RPT süresi, MOQ")
    for m in MENSELER:
        g = td[td["mense"] == m]
        print(f"  {m:9s} {len(g)} tedarikçi: ilk sipariş lansmandan {aralik(g['ilk_siparis_hafta'])} hafta önce "
              f"(medyan {sk(g['ilk_siparis_hafta'].median())}); RPT süresi {aralik(g['rpt_hafta'])} hafta "
              f"(medyan {sk(tip[m])}); MOQ {aralik(g['moq_option'])} adet")
    print(f"  (menşe sayısı {td['mense'].nunique()}: {', '.join(MENSELER)}; Yakın = Mısır)")


def _sahne_ozeti(v: VeriA, ad: str, s_: dict) -> None:
    o = _o(v, s_["option_id"])
    g = v.gercek.set_index("option_id").loc[s_["option_id"]]
    print(f"  {s_['model_adi']} {s_['renk']} ({s_['option_id']}; {s_['alt_kategori']}, {s_['sezon_kodu']}, "
          f"{s_['dalga']}. dalga)")
    print(f"  tedarikçi {s_['tedarikci']} ({s_['ulke']}, {s_['mense']}); RPT süresi {s_['rpt_hafta']} hafta; "
          f"MOQ {s(s_['moq'])}")
    print(f"  lansman {s_['lansman']}, indirim başı {s_['indirim']}, çıkış {t_(o['cikis_tarihi'])}; "
          f"lansmandan indirime {s(o['satis_hafta'], 1)} hafta")
    plan, plan_cx = float(o["plan_sezon"]), float(o["plan_cikis"])
    print(f"  plan (lansman → indirim) {s(plan)}; plan (lansman → çıkış) {s(plan_cx)}; ilk alım "
          f"{s(s_['ilk_alim'])} (ilk alım / plan {y(bolum(s_['ilk_alim'], plan))}; "
          f"ilk alım − plan {s(fark(plan, s_['ilk_alim']))})")
    print(f"  [hakem] gerçek talep lansman → indirim {s(g['gercek_io'])} = planın {s(bolum(g['gercek_io'], plan), 2)} "
          f"katı, ilk alımın {s(bolum(g['gercek_io'], s_['ilk_alim']), 2)} katı; lansman → çıkış "
          f"{s(g['gercek_cikis'])}")
    h = s_["hikaye_haftasi"]
    print(f"  {h}. pazartesi ({t_(_pzt(o, h))}) sabahı: {h} haftada satış (mağaza + online) {s(s_['satilan'])} "
          f"(haftalık {' / '.join(s(x) for x in s_['haftalik_satis'])}; online {s(s_['online_satis'])}); satış / ilk "
          f"alım {y(pay(s_['satilan'], s_['ilk_alim']))}")
    print(f"    depodan mağazalara gönderilen {s(s_['gonderilen'])}; zincir STR {y(s_['str'])} (satış ÷ "
          f"gönderilen; Banu'nun eşiği {y(s_['banu_esik'], 0)}: "
          f"{'tetikleniyor' if s_['banu_tetik'] else 'tetiklenmiyor'})")
    print(f"    depo {s(s_['depo_stok'])}, mağaza stoğu {s(s_['magaza_stok'])}, stoklu mağaza "
          f"{s(s_['stoklu_magaza'])}/{s(s_['tasiyan_magaza'])}; ≥ {hikaye_sec.STOKSUZ_GUN_ESIGI} stoksuz günü "
          f"olan mağaza {s(s_['stoksuz_magaza'])} (en çok {s(s_['stoksuz_en_cok'], 1)} gün, beden ortalaması)")
    gun, d = v.depo_ertesi[s_["option_id"]]
    print(f"    ertesi gün ({t_(gun)}) depo stoğu {s(d)} (o sabahın replenishment'ı çıktıktan sonra)")


def _rpt_satiri(v: VeriA, s_: dict) -> None:
    r = s_["rpt"]
    o = _o(v, s_["option_id"])
    if not r:
        print("  Banu'nun kuralı RPT vermedi.")
        return
    yarim = 0.5 * s_["ilk_alim"]
    print(f"  Banu'nun kuralı: ilk alımın %50'si = {s(yarim)} → MOQ'ya ve 10'un katına → {s(r['adet'])} adet; "
          f"sipariş {r['siparis']} (lansman + {s(r['siparis_h'])} hafta)")
    print(f"    planlanan teslim {r['planlanan_teslim']} (lansman + {s(r['siparis_h'] + s_['rpt_hafta'])} hafta), "
          f"gerçekleşen {r['teslim']} (lansman + {s(r['teslim_h'], 1)} hafta; gecikme {s(r['gecikme_gun'])} gün); "
          f"indirime {s(r['indirime_kalan_gun'])} gün ({s(r['indirime_kalan_gun'] / 7, 1)} hafta) kala")
    sip, tes = pd.Timestamp(r["siparis"]), pd.Timestamp(r["teslim"])
    d = aday.durum_tablodan(v.t, sip, [s_["option_id"]]).iloc[0]
    print(f"    siparişten gelişe {s((tes - sip).days)} gün ({s((tes - sip).days / 7, 1)} hafta); sipariş sabahı "
          f"({s(r['siparis_h'])}. pazartesi) satış {s(d['satilan'])}, gönderilen {s(d['gonderilen'])}, STR "
          f"{y(d['str'])}; depo {s(d['depo'])}, mağaza stoğu {s(d['magaza'])}")
    print(f"    kalite kontrolde reddedilen {s(r['red'])}, depoya giren {s(r['giren'])}; geliş haftası taşıyan "
          f"{s(r['gelis_tasiyan'])} mağazadan boş olan {s(r['gelis_bos'])} ({y(pay(r['gelis_bos'], r['gelis_tasiyan']))}), "
          f"boş ve son {hikaye_sec.SATISSIZ_GUN} günde satışsız {s(r['gelis_satissiz'])}")
    print(f"    akıbet (FIFO, depo partiyi ayırt etmez): çıkış sabahı ({t_(o['cikis_tarihi'])}) depoda "
          f"{s(r['depoda_cikista'])} (giren RPT'ye oranı {y(pay(r['depoda_cikista'], r['giren']))}; depodaki "
          f"bütün mal {s(r['depo_cikista'])}); çıkışa dek depodan çıkan {s(r['cikisa_kadar'])} (mağazaya "
          f"{s(r['magazaya_alt'])}–{s(r['magazaya_ust'])}, gerisi online)")
    print(f"    çıkıştan sonra outlet akışıyla {s(r['outlete'])}; pencere sonunda depoda RPT'den kalan "
          f"{s(r['depoda_kalan'])}; pencere sonu zincirde (depo {s(r['depo_son'])} + raf {s(r['raf_son'])}) "
          f"{s(r['kalan_son'])}, satılmadan kalan RPT (min(giren, kalan)) {s(r['bosa'])}")


def _magaza_tablosu(v: VeriA, oid: str, h: int, idler: list[str] | None, n: int = 5) -> pd.DataFrame:
    mt = hikaye.magaza_tablosu(v.t, v.hh, oid, h)
    mg = _magaza_gercek(v, oid, h)
    mt = mt.join(mg, on="magaza_id").fillna({c: 0.0 for c in mg.columns})
    sec_ = mt[mt["magaza_id"].isin(idler)] if idler is not None else mt.head(n)
    print(f"  {'mağaza':22s} {'tip':9s} {'satış':>6s} {'stoklu gün':>10s} {'stoksuz':>7s} {'stok':>5s} "
          f"{'st. beden':>9s} | {'gerçek talep':>12s} {'karşılanmayan':>13s} {'kalıcı':>6s} {'ikame':>5s}")
    for _, m in sec_.iterrows():
        print(f"  {str(m['ad'])[:22]:22s} {str(m['tip'])[:9]:9s} {s(m['satis']):>6s} "
              f"{s(m['stoklu_gun_ort'], 1) + '/' + s(m['acik_gun']):>10s} {s(m['stoksuz_gun_ort'], 1):>7s} "
              f"{s(m['stok']):>5s} {s(m['stoklu_beden']) + '/' + s(m['beden']):>9s} | {s(m['gercek_talep']):>12s} "
              f"{s(m['karsilanmayan']):>13s} {s(m['kalici_kayip']):>6s} {s(m['ikameye_giden']):>5s}")
    print(f"  (taşıyan {len(mt)} mağaza; stoklu / stoksuz gün beden ortalaması; gerçek talep ve karşılanmayan "
          f"hakemden, zincir görmez)")
    return mt


def _stoksuz_karsilastirma(m: pd.DataFrame) -> None:
    """Tablodaki en çok ve en az stoksuz günlü mağaza: rapordaki satış oranı ile gerçek talep
    oranı (stoksuz günler satışı keser, talebi kesmez)."""
    en = m.sort_values(["stoksuz_gun_ort", "satis"], ascending=[False, False]).iloc[0]
    az = m.sort_values(["stoksuz_gun_ort", "satis"], ascending=[True, False]).iloc[0]
    print(f"  en çok stoksuz günlü ({en['ad']}, {s(en['stoksuz_gun_ort'], 1)} gün) ile en az stoksuz günlü "
          f"({az['ad']}, {s(az['stoksuz_gun_ort'], 1)} gün): satış {s(en['satis'])} / {s(az['satis'])} = "
          f"{s(bolum(en['satis'], az['satis']), 2)} kat; gerçek talep {s(en['gercek_talep'])} / "
          f"{s(az['gercek_talep'])} = {s(bolum(en['gercek_talep'], az['gercek_talep']), 2)} kat")


def hikaye_bolumu(v: VeriA, ek: list) -> None:
    baslik("HİKÂYE (1. yazı) — Üçüncü Pazartesi")
    o = v.oz
    hit, gec = o["hit"], o["gec"]
    _tedarik_ozeti(v)

    alt("Sahne seçimi (hikaye_sec; spec §6)")
    hb, gb = hikaye_sec.hit_bayraklari(v.f), hikaye_sec.gec_bayraklari(v.f)
    print("  hit huni: " + " → ".join(f"{a} {s(n)}" for a, n in hikaye_sec.huni(hb)))
    print("  geç gelen huni: " + " → ".join(f"{a} {s(n)}" for a, n in hikaye_sec.huni(gb)))
    print(f"  seçim: hit {hit['option_id']}, geç gelen {gec['option_id']}; gevşeyen ölçüt: hit "
          f"{o['gevseyen']['hit'] or 'yok'}, geç gelen {o['gevseyen']['gec'] or 'yok'}")

    alt(f"Hit — {hit['model_adi']} {hit['renk']}")
    _sahne_ozeti(v, "hit", hit)
    _rpt_satiri(v, hit)
    ho = _o(v, hit["option_id"])
    e_io = v.ogr.egriler[HIKAYE_SEZONU][("duzeltilmis", "indirim")]
    e_cx = v.ogr.egriler[HIKAYE_SEZONU][("duzeltilmis", "cikis")]
    d = int(ho["dalga"])
    gelis_plan = KARAR_H + int(ho["rpt_hafta"])
    gelis = hit["rpt"]["teslim_h"]
    print(f"  eğri ({HIKAYE_SEZONU} düzeltilmiş, {d}. dalga): planlanan gelişte (lansman + {gelis_plan} hafta) "
          f"kalan pay: indirime kadarki talepte {y(e_io.kalan((d,), gelis_plan))}, çıkışa kadarki talepte "
          f"{y(e_cx.kalan((d,), gelis_plan))}; gerçekleşen gelişte (+{s(gelis, 1)} hafta) "
          f"{y(e_io.kalan((d,), gelis))} / {y(e_cx.kalan((d,), gelis))}")

    alt(f"Hit — {KARAR_H}. pazartesi mağaza tablosu ({t_(_pzt(ho, KARAR_H))} sabahı; sahnenin mağazaları)")
    mt3 = _magaza_tablosu(v, hit["option_id"], KARAR_H, v.hik.magazalar["hit"])
    _stoksuz_karsilastirma(mt3[mt3["magaza_id"].isin(v.hik.magazalar["hit"])])

    alt(f"Hit — {KARAR_H + 1}. pazartesi ({t_(_pzt(ho, KARAR_H + 1))} sabahı; bir hafta sonra), en çok satan 5 mağaza")
    p = v.panel[v.panel["option_id"] == hit["option_id"]].set_index("h")
    x4 = p.loc[p.index < KARAR_H + 1, "satis"].sum()
    print(f"  {KARAR_H + 1} haftada satış {s(x4)} (satış / ilk alım {y(pay(x4, hit['ilk_alim']))}); depo "
          f"{s(p.loc[KARAR_H + 1, 'depo_stok'])}, mağaza stoğu {s(p.loc[KARAR_H + 1, 'magaza_stok'])}, stoklu mağaza "
          f"{s(p.loc[KARAR_H + 1, 'stoklu_magaza'])}/{s(p.loc[KARAR_H + 1, 'tasiyan_magaza'])} (sezonda mal alan "
          f"{s(p.loc[KARAR_H + 1, 'tasiyan_magaza'])} mağaza; ilk dağıtım {s(hit['tasiyan_magaza'])} mağazaya)")
    mt4 = _magaza_tablosu(v, hit["option_id"], KARAR_H + 1, None, 5)
    _stoksuz_karsilastirma(mt4.head(5))

    alt("Hit — zincirde gerçek talep ve kaybolan satış [hakem]")
    hg = _haftalik_gercek(v, hit["option_id"])
    for hh_ in (KARAR_H, KARAR_H + 1):
        g = hg.loc[(hg.index >= 0) & (hg.index < hh_)]
        xs = p.loc[p.index < hh_, "satis"].sum()
        print(f"  ilk {hh_} hafta: satış {s(g['satis'].sum())} (başka üründen ikameyle alınan "
              f"{s(g['ikame_alinan'].sum())}; kendi satış {s(g['kendi_satis'].sum())}) + karşılanmayan "
              f"{s(g['karsilanmayan'].sum())} = gerçek talep {s(g['talep'].sum())}; karşılanmayanın kalıcı kaybı "
              f"{s(g['kalici_kayip'].sum())}, başka ürüne ikamesi {s(g['ikameye_giden'].sum())}; mağazalarda "
              f"{s(g['karsilanmayan_magaza'].sum())}")
        ek.append((f"hit ilk {hh_} hafta: kendi satış + karşılanmayan = gerçek talep (hakem)",
                   g["kendi_satis"].sum() + g["karsilanmayan"].sum() == g["talep"].sum()))
        ek.append((f"hit ilk {hh_} hafta: satış = option paneli satışı", g["satis"].sum() == xs))

    alt(f"Hit'in sonu — haftalık seyir (h: satış / gerçek talep / karşılanmayan / mağazaya varan / "
        f"depo / stoklu mağaza)")
    son_h = int(p.index.max())
    for w in range(0, min(int(np.ceil(gelis)) + 5, son_h + 1)):
        gh = hg.loc[w] if w in hg.index else pd.Series(0.0, index=hg.columns)
        print(f"    h={w:2d}  {s(p.loc[w, 'satis']):>6s} / {s(gh['talep']):>6s} / {s(gh['karsilanmayan']):>6s} / "
              f"{s(p.loc[w, 'sevk']):>6s} / {s(p.loc[w, 'depo_stok']):>6s} / "
              f"{s(p.loc[w, 'stoklu_magaza'])}/{s(p.loc[w, 'tasiyan_magaza'])}")
    ara = hg.loc[(hg.index >= KARAR_H) & (hg.index < int(np.floor(gelis)))]
    print(f"  sipariş haftasından (h={KARAR_H}) gelişin haftasına (h={int(np.floor(gelis))}) dek "
          f"{len(ara)} hafta: karşılanmayan {s(ara['karsilanmayan'].sum())} (kalıcı {s(ara['kalici_kayip'].sum())}, "
          f"ikame {s(ara['ikameye_giden'].sum())}), gerçek talep {s(ara['talep'].sum())}, satış "
          f"{s(p.loc[(p.index >= KARAR_H) & (p.index < int(np.floor(gelis))), 'satis'].sum())}")
    gr = v.gercek.set_index("option_id").loc[hit["option_id"]]
    toplam = hit["ilk_alim"] + hit["rpt"]["adet"]
    print(f"  [hakem] sezon (lansman → indirim) gerçek talep {s(gr['gercek_io'])} = planın "
          f"{s(bolum(gr['gercek_io'], ho['plan_sezon']), 2)} katı; ilk alım + RPT = {s(hit['ilk_alim'])} + "
          f"{s(hit['rpt']['adet'])} = {s(toplam)} (gerçek talebe oranı {y(pay(toplam, gr['gercek_io']))})")
    sz = hg.loc[(hg.index >= 0) & (hg.index < int(np.ceil(ho['satis_hafta'])))]
    print(f"  [hakem] lansman → indirim karşılanmayan {s(sz['karsilanmayan'].sum())} (kalıcı "
          f"{s(sz['kalici_kayip'].sum())}, ikame {s(sz['ikameye_giden'].sum())})")

    alt(f"Geç gelen — {gec['model_adi']} {gec['renk']} (6. yazının sahnesi)")
    _sahne_ozeti(v, "gec", gec)
    _rpt_satiri(v, gec)
    go = _o(v, gec["option_id"])
    d = int(go["dalga"])
    gp_ = round(gec["rpt"]["siparis_h"]) + int(go["rpt_hafta"])
    bk = v.f.set_index("option_id").loc[gec["option_id"], "banu_dkar"]
    print(f"  [oyun koşuları] Banu'nun RPT'si bu option'da RPT yoka göre kâr farkı {tl(bk)} (R9: zararlı RPT; "
          f"Banu / a ile RPT yok, aynı talep)")
    print(f"  eğri ({HIKAYE_SEZONU} düzeltilmiş, {d}. dalga): planlanan gelişte (lansman + "
          f"{gp_} hafta) indirime kalan {y(e_io.kalan((d,), gp_))}, "
          f"çıkışa kalan {y(e_cx.kalan((d,), gp_))}; gerçekleşen gelişte (+"
          f"{s(gec['rpt']['teslim_h'], 1)} hafta) {y(e_io.kalan((d,), gec['rpt']['teslim_h']))} / "
          f"{y(e_cx.kalan((d,), gec['rpt']['teslim_h']))}")
    print("  geldiği hafta boş olup lansmandan beri en çok satan mağazalar (stok / son 28 gün satış / "
          "lansmandan beri satış):")
    for m in gec["magazalar"]:
        print(f"    {m['ad']} ({m['tip']}): {s(m['stok'])} / {s(m['satis_28'])} / {s(m['satis_toplam'])}")
    gp = v.panel[v.panel["option_id"] == gec["option_id"]].set_index("h")
    gh = _haftalik_gercek(v, gec["option_id"])
    print(f"  haftalık seyir (h: satış / gerçek talep / karşılanmayan / mağazaya varan / depo / stoklu mağaza ÷ "
          f"sezonda mal alan mağaza; ilk dağıtım {s(gec['tasiyan_magaza'])} mağazaya, geliş haftası taşıyan "
          f"{s(gec['rpt']['gelis_tasiyan'])}):")
    gl = gec["rpt"]["teslim_h"]
    for w in range(max(int(np.floor(gl)) - 2, 0), int(gp.index.max()) + 1):
        x = gh.loc[w] if w in gh.index else pd.Series(0.0, index=gh.columns)
        print(f"    h={w:2d}  {s(gp.loc[w, 'satis']):>6s} / {s(x['talep']):>6s} / {s(x['karsilanmayan']):>6s} / "
              f"{s(gp.loc[w, 'sevk']):>6s} / {s(gp.loc[w, 'depo_stok']):>6s} / "
              f"{s(gp.loc[w, 'stoklu_magaza'])}/{s(gp.loc[w, 'tasiyan_magaza'])}")

    alt("Veli'nin hatırası — Banu'nun RPT'lerinin akıbeti (yayımlanan dünya, FIFO)")
    for G in (ONCEKI_SEZON[HIKAYE_SEZONU], HIKAYE_SEZONU):
        ak = v.akibet[G]
        r = v.rpt_yay[v.rpt_yay["sezon_kodu"] == G]
        giren = ak["rpt_giren"].sum()
        print(f"  {G}: {s(len(ak))} option'a {s(len(r))} RPT, sipariş {s(ak['rpt'].sum())} adet, kalite reddi "
              f"{s(ak['red'].sum())}, depoya giren {s(giren)}")
        print(f"    çıkış sabahı depoda {s(ak['rpt_depoda_cikista'].sum())} ({y(pay(ak['rpt_depoda_cikista'].sum(), giren))}); "
              f"çıkışa dek depodan çıkan {s(ak['rpt_cikisa_kadar'].sum())} ({y(pay(ak['rpt_cikisa_kadar'].sum(), giren))}; "
              f"mağazaya {s(ak['rpt_magazaya_alt'].sum())}–{s(ak['rpt_magazaya_ust'].sum())})")
        print(f"    çıkıştan sonra outlet'e akan {s(ak['rpt_outlete'].sum())} ({y(pay(ak['rpt_outlete'].sum(), giren))}), "
              f"pencere sonunda depoda kalan {s(ak['rpt_depoda_kalan'].sum())}")
        print(f"    indirim başladıktan sonra gelen RPT {s(r['indirimden_sonra'].sum())} "
              f"({s(r.loc[r['indirimden_sonra'], 'adet'].sum())} adet)")
        mm = r.merge(ak[["option_id", "rpt_depoda_cikista", "rpt_giren"]], on="option_id")
        for m in MENSELER:
            g = mm[mm["mense"] == m]
            if g.empty:
                continue
            print(f"    {m:9s}: {s(len(g))} RPT, {s(g['adet'].sum())} adet; geç gelen {s(g['indirimden_sonra'].sum())}; "
                  f"çıkışta depoda {s(g['rpt_depoda_cikista'].sum())} ({y(pay(g['rpt_depoda_cikista'].sum(), g['rpt_giren'].sum()))})")
        ek += fifo_denetimleri(ak, f"yayımlanan {G}")

    alt("Bir sezonda kaç soru")
    for G in (HIKAYE_SEZONU, ONCEKI_SEZON[HIKAYE_SEZONU]):
        c = _col(v, G)
        n_h = miktar_ilk_son()
        r = v.rpt_yay[v.rpt_yay["sezon_kodu"] == G]
        gr = v.gercek.merge(c[["option_id", "plan_sezon", "mense"]], on="option_id")
        oran = gr["gercek_io"] / gr["plan_sezon"]
        tutan = gr[oran >= TUTAN_ESIGI]
        rpt_opt = set(r["option_id"])
        print(f"  {G} Collection: {s(c['model_kodu'].nunique())} model, {s(len(c))} option × {n_h} karar "
              f"pazartesisi (lansman + 3…6 hafta) = {s(len(c) * n_h)} soru; 2…6 haftayla "
              f"{s(len(c) * len(HAFTALAR))}")
        print(f"    menşeye göre option: " + ", ".join(f"{m} {s((c['mense'] == m).sum())}" for m in MENSELER))
        print(f"    Banu'nun RPT'si: {s(len(r))} ({s(len(rpt_opt))} option), {s(r['adet'].sum())} adet; indirim "
              f"başladıktan sonra gelen {s(r['indirimden_sonra'].sum())}")
        print(f"    [hakem + plan] tutan option (gerçek / plan ≥ {s(TUTAN_ESIGI, 1)}): {s(len(tutan))}; bunlardan RPT "
              f"verilen {s(tutan['option_id'].isin(rpt_opt).sum())}; RPT verilip tutan olmayan "
              f"{s(len(rpt_opt - set(tutan['option_id'])))}")
        print(f"    gerçek / plan dağılımı: medyan {s(oran.median(), 2)}, %90'ı {s(oran.quantile(0.9), 2)}, en "
              f"büyük {s(oran.max(), 2)}; ≥ 1,2 olan {s((oran >= 1.2).sum())}, ≥ 1 olan {s((oran >= 1).sum())}")
        q = c["ilk_alim"] / c["plan_sezon"]
        print(f"    ilk alım / plan: medyan {s(q.median(), 3)} ({y(q.median())}), en küçük {s(q.min(), 3)}, en büyük "
              f"{s(q.max(), 3)}; ilk alımı planın üstünde olan option {s((q > 1).sum())}")


def miktar_ilk_son() -> int:
    """Banu'nun kuralının baktığı pazartesi sayısı (3…6)."""
    from rpt import miktar
    return miktar.RPT_SON_HAFTA - miktar.RPT_ILK_HAFTA + 1


# ---------------------------------------------------------------------------
# KARAR (2. yazı)
# ---------------------------------------------------------------------------

def karar_bolumu(v: VeriA, ek: list) -> None:
    baslik("KARAR (2. yazı) — RPT kararı nasıl verilir")
    c = _col(v, HIKAYE_SEZONU)
    print(f"  {HIKAYE_SEZONU} Collection {s(len(c))} option; her pazartesi bakılan ürün (lansman + 3…6 hafta "
          f"penceresinde) dalga başına {s(c.groupby('dalga').size().min())}–{s(c.groupby('dalga').size().max())}")
    alt("Yaşam eğrisi: ilk h haftanın indirime kadarki talepteki payı k_h (düzeltilmiş; çıplak eğri parantezde)")
    for G in OYUN:
        e = v.ogr.egriler[G][("duzeltilmis", "indirim")]
        eh = v.ogr.egriler[G][("ham", "indirim")]
        print(f"  {G} eğrisi (öğrenme sezonları {', '.join(e.sezonlar)}; karar anı Basit'iyle düzeltilmiş):")
        for d in (1, 2, 3):
            print(f"    dalga {d}: " + ", ".join(f"k_{h} {y(e.k((d,), h))}" for h in (2, 3, 4, 6))
                  + f"   (çıplak: k_2 {y(eh.k((d,), 2))}, k_3 {y(eh.k((d,), 3))})")
    o = c.drop_duplicates("dalga").set_index("dalga")
    print("  lansmandan indirime hafta: " + ", ".join(f"dalga {d} {s(o.loc[d, 'satis_hafta'], 1)}" for d in (1, 2, 3)))

    alt("Tedarikçiler")
    td = v.t["tedarikci"]
    for _, r in td.iterrows():
        print(f"  {r['tedarikci_id']} {r['ad']:26s} {r['ulke']:10s} {r['mense']:9s} ilk sipariş "
              f"{s(r['ilk_siparis_hafta'])} hafta önce, RPT {s(r['rpt_hafta'])} hafta, MOQ {s(r['moq_option'])}")
    r = v.rpt_yay[v.rpt_yay["gerceklesen_teslim"].notna()].copy()
    r["sapma"] = (r["gerceklesen_teslim"] - r["planlanan_teslim"]).dt.days
    for m in MENSELER:
        g = r[r["mense"] == m]
        if g.empty:
            continue
        print(f"  gerçekleşen RPT teslim sapması (yayımlanan bütün RPT'ler), {m}: ortalama {s(g['sapma'].mean(), 1)} "
              f"gün, en çok {s(g['sapma'].max())} gün, en erken {s(g['sapma'].min())} gün (n={s(len(g))})")
    tip = tipik_rpt_suresi(td)

    alt(f"Lansman + {KARAR_H} hafta verilen RPT: gelişten sonra kalan eğri ({HIKAYE_SEZONU} eğrisi, menşenin medyan "
        f"RPT süresiyle)")
    e_io = v.ogr.egriler[HIKAYE_SEZONU][("duzeltilmis", "indirim")]
    e_cx = v.ogr.egriler[HIKAYE_SEZONU][("duzeltilmis", "cikis")]
    print(f"  {'dalga':5s} {'menşe':9s} {'L':>4s} {'geliş h':>7s} {'indirime kalan':>14s} {'çıkışa kalan':>12s}")
    for d in (1, 2, 3):
        for m in MENSELER:
            L = tip[m]
            gh = KARAR_H + L
            print(f"  {d:>5d} {m:9s} {sk(L):>4s} {sk(gh):>7s} {y(e_io.kalan((d,), gh)):>14s} "
                  f"{y(e_cx.kalan((d,), gh)):>12s}")
    print("  (indirime kalan: lansman → indirim talebinin gelişten sonraki payı; çıkışa kalan: lansman → çıkış "
          "talebinin, indirim dahil)")
    alt("Sipariş haftasına göre kalan eğri (hikâyenin iki option'ı, kendi RPT süreleriyle)")
    for oid in (v.hik.hit_option, v.hik.gec_option):
        oo = _o(v, oid)
        d, L = int(oo["dalga"]), int(oo["rpt_hafta"])
        print(f"  {oid} (dalga {d}, RPT {L} hafta): " + "; ".join(
            f"h={h} → geliş {h + L}: indirime {y(e_io.kalan((d,), h + L))}, çıkışa {y(e_cx.kalan((d,), h + L))}"
            for h in HAFTALAR))

    alt("Karar anı Basit düzeltmesi, hit (zincir: mağaza + online; Satış Kaybı dizisinin yöntemi)")
    hit = v.hik.hit_option
    hg = _haftalik_gercek(v, hit)
    k = v.katman[HIKAYE_SEZONU]
    for h in (KARAR_H, KARAR_H + 1):
        r = k[(k["option_id"] == hit) & (k["h"] == h)].iloc[0]
        gercek = hg.loc[hg.index < h, "talep"].sum()
        ham, duz, gr = yuv(yuv(r["x"]) / h, 1), yuv(yuv(r["D"]) / h, 1), yuv(yuv(gercek) / h, 1)
        print(f"  h={h}: brüt satış x {s(r['x'])}, karar anı Basit'iyle düzeltilmiş talep D {s(r['D'])} "
              f"(+{y(pay(fark(r['x'], r['D']), r['x']))}); hücre-gün {s(r['hucre_gun'])}, stoklu ya da tükenen pay "
              f"{y(r['stoklu_pay'])}")
        print(f"       haftalık: çıplak {s(ham, 1)}, düzeltilmiş {s(duz, 1)}, [hakem] gerçek {s(gr, 1)}; düzeltmenin "
              f"kapattığı açık ({s(duz, 1)} − {s(ham, 1)}) / ({s(gr, 1)} − {s(ham, 1)}) = "
              f"{y((duz - ham) / (gr - ham)) if gr != ham else '—'}")


# ---------------------------------------------------------------------------
# SANSÜR (3. yazı)
# ---------------------------------------------------------------------------

def sansur_bolumu(v: VeriA, ek: list) -> None:
    baslik("SANSÜR (3. yazı) — Ne kadar daha satardı")
    print("  Hedef: lansman → indirim başı gerçek talep (hakem: kendi satış + karşılanmayan; mağaza + online).")
    print("  Kestirim karar anında: karar pazartesisinden önceki günler, karar anı Basit'i (ortak paket),")
    print("  çarpanlar o anda kapanmış sezonlardan. Eğriler oyun sezonundan önce kapanmış sezonlardan:")
    for G in OYUN:
        print(f"    {G} ← {', '.join(v.ogr.egriler[G][('duzeltilmis', 'indirim')].sezonlar)}")
    print("  WAPE = Σ|hata| / Σgerçek; yanlılık = Σhata / Σgerçek; MAPE = option ortalaması.")

    alt("Gizli gerçek, oyun sezonları (Collection, lansman → indirim) [hakem]")
    for G in OYUN:
        c = _col(v, G)
        g = v.gercek[v.gercek["option_id"].isin(c["option_id"])]
        u = c.set_index("option_id")
        kk = v.kars[v.kars["option_id"].isin(c["option_id"])]
        kk = kk[kk["tarih"] < kk["option_id"].map(u["indirim_baslangic"])]
        kk = kk[kk["tarih"] >= kk["option_id"].map(u["lansman_tarihi"])]
        onl = v.gg[v.gg["option_id"].isin(c["option_id"]) & (v.gg["magaza_id"] == kaynak.ONLINE)]
        onl = onl[(onl["tarih"] < onl["option_id"].map(u["indirim_baslangic"]))
                  & (onl["tarih"] >= onl["option_id"].map(u["lansman_tarihi"]))]
        top = g["gercek_io"].sum()
        print(f"  {G}: {s(len(c))} option, gerçek talep {s(top)} (online {s(onl['talep'].sum())}, "
              f"{y(pay(onl['talep'].sum(), top))}); karşılanmayan {s(kk['karsilanmayan'].sum())} "
              f"({y(pay(kk['karsilanmayan'].sum(), top))}): kalıcı kayıp {s(kk['kalici_kayip'].sum())}, başka ürüne "
              f"ikame {s(kk['ikameye_giden'].sum())} ({y(pay(kk['ikameye_giden'].sum(), kk['karsilanmayan'].sum()))})")

    for G in OYUN:
        tab = v.hata[G]
        for kesit in ("tümü", "tutan", "tutmayan"):
            tk = tab[tab["kesit"] == kesit]
            if tk.empty:
                continue
            n = int(tk["n"].iloc[0])
            alt(f"{G} — {kesit} (n={n})")
            print(f"  {'katman':38s} " + " ".join(f"{'h=' + str(h):>21s}" for h in HAFTALAR))
            print(f"  {'':38s} " + " ".join(f"{'WAPE  yanl.   MAPE':>21s}" for _ in HAFTALAR))
            for kat in sansur.KATMANLAR + sansur.EK_KATMANLAR + ("plan",):
                sat = tk[tk["katman"] == kat].set_index("h")
                print(f"  {KATMAN_ADI[kat]:38s} " + " ".join(
                    f"{y(sat.loc[h, 'wape'], 1):>6s} {y(sat.loc[h, 'yanlilik'], 1):>7s} {y(sat.loc[h, 'mape'], 0):>6s}"
                    for h in HAFTALAR))
            ek.append((f"hata tablosu {G} {kesit}: her katmanda aynı n", bool(tk.groupby("h")["n"].nunique().max() == 1)))

    alt("FRR karşılığı (FRR 2001: ilk iki haftadan tahmin %8, alım komitesi %55)")
    for G in OYUN:
        tk = v.hata[G][v.hata[G]["kesit"] == "tümü"].set_index(["katman", "h"])
        d2, p2, c2 = tk.loc[("d", 2), "wape"], tk.loc[("plan", 2), "wape"], tk.loc[("c", 2), "wape"]
        print(f"  {G}: h=2'de d {y(d2)}, FRR kuralı (c) {y(c2)}, buyer planı {y(p2)}; d / plan = "
              f"{y(d2)} / {y(p2)} = {s(yuzde_bolum(d2, p2), 2)}; h=3'te d {y(tk.loc[('d', 3), 'wape'])}, "
              f"h=6'da d {y(tk.loc[('d', 6), 'wape'])}; dört katmandan (a, b, c, d) en iyisi h=2'de "
              f"{min(sansur.KATMANLAR, key=lambda k_: tk.loc[(k_, 2), 'wape'])}")

    alt("Hikâye option'larında katmanlar (sezon talebi kestirimi, lansman → indirim)")
    for oid in (v.hik.hit_option, v.hik.gec_option):
        oo = _o(v, oid)
        g = v.gercek.set_index("option_id").loc[oid]
        k = v.katman[HIKAYE_SEZONU]
        k = k[k["option_id"] == oid].set_index("h")
        print(f"  {oid} ({oo['model_adi']} {oo['renk']}, {oo['mense']}): [hakem] gerçek {s(g['gercek_io'])}, plan "
              f"{s(oo['plan_sezon'])}, ilk alım {s(oo['ilk_alim'])}")
        for h in HAFTALAR:
            r = k.loc[h]
            print(f"    h={h}: a {s(r['a']):>6s} · b {s(r['b']):>6s} · c {s(r['c']):>6s} · d {s(r['d']):>6s} · "
                  f"çıplak hız×hafta {s(r['a_hiz']):>6s} · çıplak÷düz.eğri {s(r['c_duz_egri']):>6s}   (x {s(r['x'])}, "
                  f"D {s(r['D'])}, k_çıplak {y(r['k_ham'])}, k_düz {y(r['k_duz'])}, stoklu pay {y(r['stoklu_pay'])}; "
                  f"d / gerçek {s(bolum(r['d'], g['gercek_io']), 2)})")

    alt("Stoklu ya da tükenen hücre-gün payı (karar anına dek), tutan / tutmayan option'lar")
    for G in OYUN:
        k = v.katman[G].merge(v.gercek, on="option_id")
        k["tutan"] = k["gercek_io"] / k["plan_sezon"] >= TUTAN_ESIGI
        for h in (3, 6):
            kh = k[k["h"] == h]
            print(f"  {G} h={h}: tutan {y(kh.loc[kh['tutan'], 'stoklu_pay'].mean())} (n={s(kh['tutan'].sum())}), "
                  f"tutmayan {y(kh.loc[~kh['tutan'], 'stoklu_pay'].mean())}")

    alt("Eğri şekli: çıplak (sansürlü satış) vs düzeltilmiş (Basit) vs gerçek (hakem), birikimli pay k_h, %")
    for G in OYUN:
        eh = v.ogr.egriler[G][("ham", "indirim")]
        ed = v.ogr.egriler[G][("duzeltilmis", "indirim")]
        eg = v.egri_gercek[(G, "indirim")]
        print(f"  {G} (öğrenme: {', '.join(ed.sezonlar)}; gerçek: oyun sezonu {G})")
        for d in (1, 2, 3):
            hs = range(1, 9)
            print(f"    dalga {d} h:      " + " ".join(f"{h:>5d}" for h in hs))
            for ad, e in (("çıplak", eh), ("düzeltilmiş", ed), ("gerçek", eg)):
                print(f"      {ad:12s}  " + " ".join(f"{s(100 * e.k((d,), h), 1):>5s}" for h in hs))
            fh = [fark(100 * ed.k((d,), h), 100 * eh.k((d,), h), 1) for h in range(1, 7)]
            print("      çıplak − düzeltilmiş (puan), h=1..6: " + " ".join(s(f_, 1) for f_ in fh)
                  + f"   en büyük {s(max(fh), 1)}")
        gg_ = v.egri_gecmis_gercek[G]
        mae_d = np.mean([abs(ed.k((d,), h) - gg_.k((d,), h)) for d in (1, 2, 3) for h in range(1, 7)])
        mae_h = np.mean([abs(eh.k((d,), h) - gg_.k((d,), h)) for d in (1, 2, 3) for h in range(1, 7)])
        mae_o = np.mean([abs(ed.k((d,), h) - eg.k((d,), h)) for d in (1, 2, 3) for h in range(1, 7)])
        mae_oh = np.mean([abs(eh.k((d,), h) - eg.k((d,), h)) for d in (1, 2, 3) for h in range(1, 7)])
        print(f"    öğrenme sezonlarının kendi gerçek eğrisine ortalama mutlak uzaklık (h=1..6, üç dalga): "
              f"düzeltilmiş {s(100 * mae_d, 2)} puan, çıplak {s(100 * mae_h, 2)} puan")
        print(f"    oyun sezonunun ({G}) gerçek eğrisine: düzeltilmiş {s(100 * mae_o, 2)} puan, çıplak "
              f"{s(100 * mae_oh, 2)} puan")
        ye = v.egri_yeniden[G]
        ayni = all(np.allclose(ye.paylar[k_], ed.paylar[k_]) for k_ in ed.paylar) and set(ye.paylar) == set(ed.paylar)
        ek.append((f"rapor içinde kurulan {G} düzeltilmiş eğrisi = oyunun öğrendiği", ayni))

    alt("Gruplama: yalnız dalga vs üst kategori × dalga (düzeltilmiş), oyun sezonunun gerçek eğrisine uzaklık")
    for G in OYUN:
        ed = v.ogr.egriler[G][("duzeltilmis", "indirim")]
        ek_ = v.egri_kat[G]
        gk = v.egri_kat_gercek[G]
        fd, fk = [], []
        for anahtar in gk.paylar:
            for h in range(1, 7):
                fd.append(abs(ed.k((anahtar[1],), h) - gk.k(anahtar, h)))
                fk.append(abs(ek_.k(anahtar, h) - gk.k(anahtar, h)))
        print(f"  {G}: yalnız dalga {s(100 * np.mean(fd), 2)} puan, kategori × dalga {s(100 * np.mean(fk), 2)} puan "
              f"({s(len(gk.paylar))} grup; oyunun eğrisi: yalnız dalga)")


# ---------------------------------------------------------------------------
# ANLATI VARSAYIMLARI
# ---------------------------------------------------------------------------

def anlati_bolumu(d_wape_h2: float, plan_wape_h2: float) -> None:
    """ANLATI VARSAYIMLARI: yazıların elle sayıları (veriden gelmez) ve onlardan türeyenler."""
    v = ANLATI_VARSAYIMLARI
    print("\n=== ANLATI VARSAYIMLARI ===")
    print("  (anlatının sabitleri: veriden gelmez; varsayım ya da literatür, kaynağıyla)")
    print(f"  toplanti_saati = {v['toplanti_saati']}  (varsayım: 1. yazının pazartesi toplantısı)")
    print(f"  frr_ilk_iki_hafta_hatasi = {y(v['frr_ilk_iki_hafta_hatasi'], 0)}  (literatür: Fisher, Rajaram ve "
          f"Raman {v['frr_yayin_yili']}; ilk iki haftanın satışından sezon tahmini)")
    print(f"  frr_alim_komitesi_hatasi = {y(v['frr_alim_komitesi_hatasi'], 0)}  (literatür: aynı çalışma; alım "
          f"komitesinin sezon öncesi tahmini)")
    print(f"  frr_yayin_yili = {v['frr_yayin_yili']}")
    f_ = yuzde_bolum(v["frr_ilk_iki_hafta_hatasi"], v["frr_alim_komitesi_hatasi"], 0)
    l_ = yuzde_bolum(d_wape_h2, plan_wape_h2)
    print(f"  türeyen: FRR'nin oranı {y(v['frr_ilk_iki_hafta_hatasi'], 0)} / {y(v['frr_alim_komitesi_hatasi'], 0)} "
          f"= {s(f_, 2)}; Lumoda {HIKAYE_SEZONU} h=2, d / plan = {y(d_wape_h2)} / {y(plan_wape_h2)} = {s(l_, 2)} "
          f"(SANSÜR bölümü)")


# ---------------------------------------------------------------------------
# Komut
# ---------------------------------------------------------------------------

def a_denetimleri(v: VeriA) -> list[tuple[str, bool]]:
    """A girdilerinin korunumu: plan dünyasının ilk alımı yayımlananla aynı, gerçek talep
    negatif değil, hikâyenin haftalık satış toplamı karar sabahının satışına eşit."""
    c = v.opt[(v.opt["line"] == "Collection") & v.opt["sezon_kodu"].isin(kaynak.TAM_SEZONLAR)]
    d = [("politika görünümünün ilk alımı = yayımlanan ilk alım (SS23…SS25 Collection)",
          bool((c["ilk_alim"] == c["ilk_alim_dunya"]).all())),
         ("plan pozitif (oyun sezonları Collection)",
          bool((c.loc[c["sezon_kodu"].isin(OYUN), "plan_sezon"] > 0).all())),
         ("hakem gerçek talebi ≥ 0", bool((v.gercek[["gercek_io", "gercek_cikis"]] >= 0).all().all())),
         ("hakem gerçek talebi: lansman → çıkış ≥ lansman → indirim",
          bool((v.gercek["gercek_cikis"] >= v.gercek["gercek_io"]).all()))]
    for sahne in ("hit", "gec"):
        o = v.oz[sahne]
        d.append((f"hikâye {sahne}: haftalık satış toplamı = karar sabahı satış",
                  sum(o["haftalik_satis"]) == o["satilan"]))
    return d


def govde(va: VeriA, vb) -> None:
    """Raporun bütün bölümleri, sırasıyla; en sonda korunum (tutmazsa AssertionError)."""
    import rapor_b

    ek: list = a_denetimleri(va)
    print("RPT dizisi (Tekrar Sipariş) — v4 raporu. Kaynak: yayımlanan v4 tabloları, motorun politika görünümü "
          "(plan), hakem (yayımlanan dünyanın gerçeği), oyun koşuları (cikti/kosular), yollar (cikti/yollar.json).")
    hikaye_bolumu(va, ek)
    karar_bolumu(va, ek)
    sansur_bolumu(va, ek)
    rapor_b.aday_bolumu(va, vb, ek)
    rapor_b.miktar_bolumu(va, vb, ek)
    rapor_b.sonuc_bolumu(va, vb, ek)
    rapor_b.yollar_bolumu(va, vb, ek)
    tk = va.hata[HIKAYE_SEZONU][va.hata[HIKAYE_SEZONU]["kesit"] == "tümü"].set_index(["katman", "h"])
    anlati_bolumu(tk.loc[("d", 2), "wape"], tk.loc[("plan", 2), "wape"])
    n = korunum(ek)
    print("\n=== KORUNUM ===")
    print(f"  {n} denetim tuttu (FIFO kovaları = giren RPT, Σ option = sezon özeti, kurtarılan = kalıcı + ikame, "
          f"boşa ≤ giren ≤ sipariş, raporun eğrisi = oyunun eğrisi, plan dünyası = yayımlanan ilk alım, "
          f"yollar.json yol 0 = oyun koşuları, Banu kolu = yayımlanan RPT'ler)")


def main(argv: list[str] | None = None) -> int:
    a = _ayristir(argv)
    eksik = hakem_eksik(a.hakem)
    if eksik:
        for m in eksik:
            print(m, file=sys.stderr)
        return 1
    import rapor_b

    zorla = hikaye_sec.secim_ayristir(a.hikaye) if a.hikaye else None
    # Girdiler: alt adımların ilerleme satırları stdout'u kirletmesin (stderr'e)
    with contextlib.redirect_stdout(sys.stderr):
        va = hazirla_a(a.hakem, zorla)
        vb = rapor_b.hazirla_b(va)
    kod, metin = tamponla(lambda: govde(va, vb))
    if kod:
        return kod
    sys.stdout.write(metin)
    kosular = vb.onbellek_durumu()
    print(f"koşu önbelleği: {sum(kosular.values())}/{len(kosular)} koşu önbellekten okundu"
          + ("" if all(kosular.values()) else f"; yeniden koşulan: {[k for k, b in kosular.items() if not b]}"),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
