"""Oyun: kolları aynı müşteri akışında, v4 motorunda koşturur (spec §3.6, §4.4).

    H   = hazirlik(yol=0)                 # gerçekleşen tarih + öğrenme
    e   = dagitim_secimi(H)               # SS24'te dört dağıtım kuralı
    K   = tum_kollar(H, en_iyi=e)         # {(kol, kural): KosuKaydi}, 14 çift
    tab = ozet_tablosu(K, "SS25")         # kol × ölçüt (rpt_yok tabanına göre)

    .venv/Scripts/python -m rpt.oyun      # yol 0'ın bütün ızgarası; cikti/oyun.json

YOL. Bir yol bir talep tohumudur (`talep_tohumu(yol)`: yol 0 yayımlanan dünya,
`None`; yol p > 0 `TALEP_TABANI + p`). Dünya (mağazalar, ürünler, beklenen talep,
sürprizler) ve operasyon çekilişleri bütün yollarda aynıdır; yalnız müşteri
akışı değişir. Yol içinde bütün kollar aynı tohumu paylaşır: kol farkları yalnız
kararlardan gelir.

HAZIRLIK (`hazirlik`). Önce yolun "gerçekleşen tarihi": Lumoda'nın bugünkü
politikalarıyla (Banu'nun RPT kuralı, bugünkü dağıtım) motor koşusu
(`motor.kos(ad="lumoda")`). Yol 0'da bu koşunun yayımlanan biçimi yayımlanan
v4'ün kendisidir (`tests/test_motor.py::test_mevcut_kol_yayimlanan_tablolarla_ayni`);
öğrenme yayımlanan DuckDB'den ve `hazirla`'nın günlük tablosundan yapılır. Yol
p > 0'da koşunun yayımlanan biçimi (`motor.yayimlanan_bicim`: aynı kirli
kayıtlar) yolun dizininde bir DuckDB'ye yazılır, günlük tablo ondan kurulur
(`hazirla.main`), öğrenme aynı kodla yapılır. Öğrenme (`ogren`) yalnız
yayımlanan biçimdeki tablolardan, kolun gördüğü bilgiyle (Ruling R4):

    eğriler       oyun sezonu G'nin ilk lansman sabahında, G'den önce kapanmış
                  sezonlardan (`egri.oyun_egrileri`)
    karar kaydı   geçmiş sezonların karar satırları (`aday.karar_kaydi`; her satır
                  kendi karar anında bilinenle)
    belirsizlik   μ, σ (`miktar.kalibrasyon`)
    p_ind         geçmiş sezonların yayımlanan `fiyat`ı (`miktar.indirim_beklentisi`)
    modeller      lojistik + LightGBM, (ii) etiketiyle (`aday.etiket_duz`), yalnız
                  G'den önce kapanmış sezonların satırları
    çarpanlar     oyunun her karar pazartesisi için o anda bilinenler
                  (`hazirla.carpan_bulucu`)

Öğrenilenler kolun verisidir (`politika.Ogrenilen`); özetleri kolun
`parametreler()`'inden koşu anahtarına girer (`motor.politika_kimligi`, R-T4f).
Öğrenme yolun dizininde önbelleklidir (`ogrenme.pkl`; anahtar: veri dosyasının
ve günlük tablonun parmak izi + koşu kod özeti).

BASİTLEŞTİRME (v3'ten). SS25'in öğrenmesi AW24'ün GERÇEKLEŞEN (Banu'lu) tarihini
kullanır, kolun kendi AW24'ünü değil; öneri kolunun SS25 kararlarındaki karar anı
çarpanları da öyle. Kolun karar anı kestirimi ise kendi dünyasının geçmişindendir
(`politika.Oneri`, R5).

DAĞITIM KURALI SEÇİMİ (`dagitim_secimi`). Oyundan önce, SS24'te: Banu'nun RPT'leri,
dört kural yalnız SS24'ün Collection option'larına; SS24 Collection kârı en yüksek
RPT kuralı (b, c, d arasından; a bugünkü kuraldır, karşılaştırma tabanı). SS24'ün
çıkış eğrisi AW24'ün ilk lansman sabahında bilinenle (R4). Seçilen kural kolun
dağıtım politikasına `kural` olarak girer (anahtarda).

KÂHİN (Ruling R7). Kâhin kolu aynı tohumla koşulmuş `rpt_yok` koşusunun gizli
talebini görür ("RPT verilmeseydi gelecek talebi bilen üst sınır").

KOŞULAR. Bütün koşular `motor.kos(..., tembel=True)` ile (önbellek
`cikti/kosular/`, sıralı); dönen `KosuKaydi` tabloları diskten istendikçe okur.
`(mevcut, a)` hazırlık koşusunun kendisidir (aynı politikalar; sarmalayıcıların
motoru bozmadığı `tests/test_esdegerlik.py`'de sınanır). Biten her koşu
`ilerleme` dosyasına (ad, saniye, önbellekten mi) yazılır; yarıda kalan ızgara
yeniden başlatılınca önbellekten devam eder.
"""

import hashlib
import json
import pickle
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import aday, dagitim, egri, hazirla, kahin, kaynak, miktar, motor, olcutler, politika

OYUN = politika.OYUN_SEZONLARI                  # ("AW24", "SS25")
SECIM_SEZONU = "SS24"
TALEP_TABANI = 20261009
CIKTI = Path(__file__).resolve().parents[1] / "cikti"
YOLLAR_DIZINI = CIKTI / "yollar"
ILERLEME = CIKTI / "ilerleme.jsonl"
KURAL_ADAYLARI = ("b", "c", "d")


def talep_tohumu(yol: int, taban: int = TALEP_TABANI) -> int | None:
    """Yolun talep tohumu: yol 0 yayımlanan dünya (None), yol p > 0 `taban + p`."""
    return None if int(yol) == 0 else int(taban) + int(yol)


def _ilerleme(ad: str, sn: float, onbellekten: bool, dosya: Path | None = ILERLEME, **ek) -> None:
    satir = {"ad": ad, "sn": round(float(sn), 1), "onbellekten": bool(onbellekten),
             "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"), **ek}
    print(json.dumps(satir, ensure_ascii=False), flush=True)
    if dosya is not None:
        Path(dosya).parent.mkdir(parents=True, exist_ok=True)
        with open(dosya, "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False) + "\n")


def _kos(ad: str, ilerleme: Path | None = ILERLEME, **kw):
    t0 = time.perf_counter()
    k = motor.kos(ad=ad, tembel=True, **kw)
    _ilerleme(ad, time.perf_counter() - t0, k.onbellekten, ilerleme,
              motor_sn=k.meta.get("motor_sn"), tepe_gb=k.meta.get("tepe_bellek_gb"))
    return k


# ---------------------------------------------------------------------------
# Hazırlık
# ---------------------------------------------------------------------------


@dataclass
class Hazirlik:
    """Bir yolun gerçekleşen tarihi ve ondan öğrenilenler (modül notu)."""

    yol: int
    talep_tohumu: int | None
    kosu: motor.KosuKaydi              # Lumoda koşusu (gerçekleşen tarih; = (mevcut, a))
    ogrenilen: politika.Ogrenilen
    egriler_cx: dict                   # sezon → çıkış eğrisi (OYUN + SECIM_SEZONU)
    kayit: pd.DataFrame                # geçmiş sezonların karar satırları
    egitim: dict                       # oyun sezonu → etiketli eğitim satırları
    db: Path
    veri_dizini: Path
    onbellek: Path
    olcek: str = "tam"
    sure: dict = field(default_factory=dict)


def _sha(*parca) -> str:
    return hashlib.sha256(json.dumps(parca, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _parmak(yol: Path) -> list:
    d = Path(yol).stat()
    return [Path(yol).name, d.st_size, d.st_mtime_ns]


def veritabani_kur(kosu, db: Path, olcek: str = "tam") -> Path:
    """Koşunun yayımlanan biçimini (`motor.yayimlanan_bicim`) `db`'ye yazar (yayımlanan
    v4 DuckDB'siyle aynı yol: tablo başına `CREATE TABLE … AS SELECT`). Yanındaki
    `<db>.kosu` koşunun anahtarını tutar; aynı koşudan kurulmuşsa yeniden yazmaz."""
    import duckdb

    db = Path(db)
    iz = db.with_suffix(".kosu")
    anahtar = kosu.meta["anahtar"]
    if db.exists() and iz.exists() and iz.read_text(encoding="utf-8") == anahtar:
        return db
    db.parent.mkdir(parents=True, exist_ok=True)
    tablolar = motor.yayimlanan_bicim({a: kosu.tablo(a) for a in kosu.meta["tablolar"]}, olcek)
    gecici = db.with_name(db.name + ".yaziliyor")
    gecici.unlink(missing_ok=True)
    con = duckdb.connect(str(gecici))
    try:
        for ad, df in tablolar.items():
            con.register("gecici", df)
            con.execute(f"CREATE TABLE {ad} AS SELECT * FROM gecici")
            con.unregister("gecici")
    finally:
        con.close()
    del tablolar
    iz.unlink(missing_ok=True)
    gecici.replace(db)
    iz.write_text(anahtar, encoding="utf-8")
    return db


def gunluk_kur(db: Path, veri_dizini: Path) -> Path:
    """`hazirla`'nın günlük tablosu (`veri_dizini/gunluk.parquet`), `db`'den; varsa ve
    aynı dosyadan kurulmuşsa yeniden kurmaz."""
    hazirla.main(["--cikti", str(veri_dizini), "--db", str(db)])
    return Path(veri_dizini) / hazirla.GUNLUK


def ogren(db: Path, veri_dizini: Path, kosu=None) -> dict:
    """Oyun sezonlarının öğrenmesi (modül notu), yalnız `db`'nin yayımlanan
    tablolarından ve `veri_dizini`'ndeki günlük tablodan. `kosu` (gerçekleşen
    tarihin koşusu) verilirse eğitim satırlarına yalnız rapor için (i) etiketi
    eklenir (`etiket_gercek`; model onu görmez)."""
    sure = {}
    t0 = time.perf_counter()
    con = kaynak.baglan(db)
    try:
        yol = hazirla.gunluk_yolu(veri_dizini, con)
        bul = hazirla.carpan_bulucu(con, yol, veri_dizini)
        t = kaynak.veri_yukle(db)
        opt = kaynak.optionlar(t)
        gecmis = kaynak.gecmis_sezonlar(OYUN[-1])
        gunluk = hazirla.havuz_gunlugu(yol, con, egri.gecmis_havuzu(opt, gecmis),
                                       egri.oyun_baslangici(opt, OYUN[-1]))
        sure["gunluk"] = time.perf_counter() - t0

        a = time.perf_counter()
        egriler = {G: egri.oyun_egrileri(gunluk, opt, G, bul(egri.oyun_baslangici(opt, G))) for G in OYUN}
        t_secim = egri.oyun_baslangici(opt, OYUN[0])
        cx_secim = egri.egri_ogren(egri.gecmis_talep(gunluk, opt, OYUN[0], bul(t_secim)), opt,
                                   [SECIM_SEZONU], "duzeltilmis", hedef="cikis")
        sure["egri"] = time.perf_counter() - a

        a = time.perf_counter()
        kayit = aday.karar_kaydi(gunluk, opt, gecmis, bul, aday.tablo_durumu(t))
        sure["karar_kaydi"] = time.perf_counter() - a

        a = time.perf_counter()
        onbellek_egri = dict(egriler)
        belirsizlik, modeller, egitim, p_ind = {}, {}, {}, []
        col = opt["line"] == "Collection"
        for G in OYUN:
            belirsizlik[G] = miktar.kalibrasyon(gunluk, opt, G, bul, egriler=onbellek_egri, ozetler=kayit)
            beklenti = miktar.indirim_beklentisi(con, G)
            kapsam = opt[col & opt["sezon_kodu"].isin(kaynak.gecmis_sezonlar(G) + (G,))]
            p_g = miktar.indirim_fiyatlari(kapsam, beklenti, egriler[G][("duzeltilmis", "cikis")])
            p_ind.append(p_g[kapsam.loc[kapsam["sezon_kodu"] == G, "option_id"].astype(str)])
            ozl = aday.ozellikler(aday.egitim_satirlari(kayit, G), opt, egriler[G], belirsizlik[G], p_g)
            ozl = aday.etiket_duz(ozl, gunluk, opt, G, bul)
            modeller[G] = aday.Modeller(ozl, G)
            egitim[G] = ozl
        sure["model"] = time.perf_counter() - a

        carpanlar = {k: bul(k) for G in OYUN for k in politika.karar_anlari(opt, G)}
    finally:
        con.close()
    del gunluk, t

    if kosu is not None:          # yalnız rapor: (i) gerçek etiket, modele girmez
        for G in OYUN:
            ozl = egitim[G]
            skular = _skular(kosu, ozl["option_id"].unique())
            egitim[G] = aday.etiket(ozl, _gercek_talep(kosu, skular), opt, "gercek")

    # Kimlik içerik özetlerinden bir kez (pickle gidiş-dönüşü özeti değiştirebilir; R-T4f)
    ogr = politika.Ogrenilen(optionlar=opt, egriler=egriler, belirsizlik=belirsizlik, modeller=modeller,
                             p_ind=pd.concat(p_ind).rename("p_ind"), carpanlar=carpanlar).sabitle()
    cx = {G: egriler[G][("duzeltilmis", "cikis")] for G in OYUN} | {SECIM_SEZONU: cx_secim}
    sure["toplam"] = time.perf_counter() - t0
    return {"ogrenilen": ogr, "egriler_cx": cx, "kayit": kayit, "egitim": egitim, "sure": sure}


def _skular(kosu, optionlar) -> list[str]:
    u = kosu.tablo("urun", ["urun_id", "option_id"])
    return sorted(u.loc[u["option_id"].astype(str).isin(set(map(str, optionlar))), "urun_id"].astype(str))


def _gercek_talep(kosu, skular) -> pd.DataFrame:
    """Koşunun gizli hücre-gün talebi (`tarih, urun_id, option_id, talep`), yalnız `skular`."""
    g = kosu.tablo("gercek", ["tarih", "urun_id", "talep"], urunler=skular)
    u = kosu.tablo("urun", ["urun_id", "option_id"], urunler=skular)
    harita = pd.Series(u["option_id"].astype(str).to_numpy(), index=u["urun_id"].astype(str).to_numpy())
    return g.assign(urun_id=g["urun_id"].astype(str), option_id=g["urun_id"].astype(str).map(harita))


def _ogrenme_anahtari(db: Path, veri_dizini: Path, kosu) -> str:
    return _sha({"db": _parmak(db), "gunluk": _parmak(Path(veri_dizini) / hazirla.GUNLUK),
                 "kod": motor.kod_ozeti(), "hazirla": hashlib.sha256(
                     Path(hazirla.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                 "kosu": kosu.meta["anahtar"], "oyun": list(OYUN), "secim": SECIM_SEZONU})


def hazirlik(yol: int = 0, onbellek: Path = motor.KOSU_DIZINI, yollar_dizini: Path = YOLLAR_DIZINI,
             ilerleme: Path | None = ILERLEME, olcek: str = "tam", taban: int = TALEP_TABANI) -> Hazirlik:
    """Yolun gerçekleşen tarihi (Lumoda koşusu) ve öğrenmesi (modül notu). Yol 0
    yayımlanan DuckDB'den ve `hazirla`'nın günlük tablosundan öğrenir; yol p > 0
    kendi DuckDB'sini ve günlük tablosunu `yollar_dizini/yol<p>/`'de kurar.
    `olcek="kucuk"` (deneme) her yolda kendi DuckDB'sini kurar."""
    tt = talep_tohumu(yol, taban)
    sure = {}
    a = time.perf_counter()
    kosu = _kos("lumoda", ilerleme, rpt=None, parametreler={}, talep_tohumu=tt, onbellek=onbellek,
                olcek=olcek)
    sure["kosu"] = time.perf_counter() - a
    dizin = Path(yollar_dizini) / f"yol{yol}"
    dizin.mkdir(parents=True, exist_ok=True)
    if yol == 0 and olcek == "tam":
        db, veri_dizini = Path(kaynak.VERITABANI), hazirla.VARSAYILAN_CIKTI
    else:
        a = time.perf_counter()
        db, veri_dizini = veritabani_kur(kosu, dizin / "perakende.duckdb", olcek), dizin
        sure["veritabani"] = time.perf_counter() - a
    a = time.perf_counter()
    gunluk_kur(db, veri_dizini)
    sure["gunluk_tablo"] = time.perf_counter() - a

    dosya = dizin / "ogrenme.pkl"
    anahtar = _ogrenme_anahtari(db, veri_dizini, kosu)
    ogr = None
    if dosya.exists():
        with open(dosya, "rb") as f:
            kayitli = pickle.load(f)
        if kayitli.get("anahtar") == anahtar:
            ogr = kayitli["ogrenme"]
    if ogr is None:
        ogr = ogren(db, veri_dizini, kosu)
        gecici = dosya.with_suffix(".pkl.yaziliyor")
        with open(gecici, "wb") as f:
            pickle.dump({"anahtar": anahtar, "ogrenme": ogr}, f, protocol=5)
        gecici.replace(dosya)
        _ilerleme(f"y{yol}_ogrenme", ogr["sure"]["toplam"], False, ilerleme,
                  adimlar={k: round(v, 1) for k, v in ogr["sure"].items()})
    sure["ogrenme"] = ogr["sure"]
    return Hazirlik(yol=int(yol), talep_tohumu=tt, kosu=kosu, ogrenilen=ogr["ogrenilen"],
                    egriler_cx=ogr["egriler_cx"], kayit=ogr["kayit"], egitim=ogr["egitim"], db=Path(db),
                    veri_dizini=Path(veri_dizini), onbellek=Path(onbellek), olcek=olcek, sure=sure)


# ---------------------------------------------------------------------------
# Kollar
# ---------------------------------------------------------------------------


KOL_ADLARI = ("rpt_yok", "mevcut", "frr2", "frr3", "oneri", "oneri_lojistik", "kahin")


def kol_politikasi(H: Hazirlik, kol: str, kahin_kosusu=None):
    """Kolun RPT politikası (temel: Lumoda'nın bugünkü RPT kuralı). Kâhin aynı
    yolun `rpt_yok` koşusunun gizli talebini alır (R7)."""
    temel = motor.lumoda("rpt")
    ogr = H.ogrenilen
    if kol == "rpt_yok":
        return politika.RPTYok(temel)
    if kol == "mevcut":
        return politika.Mevcut(temel)
    if kol in ("frr2", "frr3"):
        return politika.FRR(temel, ogr, hafta=int(kol[-1]))
    if kol == "oneri":
        return politika.Oneri(temel, ogr)
    if kol == "oneri_lojistik":
        return politika.Oneri(temel, ogr, model="lojistik")
    if kol == "kahin":
        if kahin_kosusu is None:
            raise ValueError("kâhin kolu aynı yolun rpt_yok koşusunu ister (kahin_kosusu=)")
        opt = ogr.optionlar
        oyun_opt = opt.loc[(opt["line"] == "Collection") & opt["sezon_kodu"].isin(OYUN), "option_id"]
        talep = _gercek_talep(kahin_kosusu, _skular(kahin_kosusu, oyun_opt))
        return kahin.Kahin(talep[["tarih", "urun_id", "talep"]], temel, ogr,
                           talep_kimligi=f"rpt_yok:{kahin_kosusu.meta['anahtar'][:20]}")
    raise ValueError(f"kol {KOL_ADLARI}'den biri olmalı: {kol!r}")


def dagitim_politikasi(H: Hazirlik, kural: str, sezonlar=OYUN):
    return dagitim.KURALLAR[kural](motor.lumoda("replenishment"), {s: H.egriler_cx[s] for s in sezonlar},
                                   oyun_sezonlari=tuple(sezonlar))


def kos(H: Hazirlik, kol: str, kural: str = "a", kahin_kosusu=None, onbellek="hazirlik",
        ilerleme: Path | None = ILERLEME):
    """Kolu verilen dağıtım kuralıyla koşar (`KosuKaydi`). Kâhin için `kahin_kosusu`
    verilmezse aynı yolun (rpt_yok, a) koşusu (önbellekten) kullanılır."""
    if kol == "kahin" and kahin_kosusu is None:
        kahin_kosusu = kos(H, "rpt_yok", "a", ilerleme=ilerleme)
    rp = kol_politikasi(H, kol, kahin_kosusu)
    rep = dagitim_politikasi(H, kural)
    ob = H.onbellek if onbellek == "hazirlik" else onbellek
    return _kos(f"y{H.yol}_{kol}_{kural}", ilerleme, rpt=rp, replenishment=rep,
                parametreler={"kol": kol, "kural": kural}, talep_tohumu=H.talep_tohumu, onbellek=ob,
                olcek=H.olcek)


def kol_listesi(en_iyi: str) -> list[tuple[str, str]]:
    """Yol 0'ın 14 (kol, dağıtım kuralı) çifti (v3'ün listesi; "mevcut" kural a)."""
    return [
        ("rpt_yok", "a"), ("mevcut", "a"),
        ("mevcut", "b"), ("mevcut", "c"), ("mevcut", "d"),
        ("frr2", "a"), ("frr3", "a"), ("frr2", en_iyi), ("frr3", en_iyi),
        ("oneri", "a"), ("oneri", en_iyi), ("oneri_lojistik", en_iyi),
        ("kahin", "a"), ("kahin", en_iyi),
    ]


def yol_listesi(en_iyi: str) -> list[tuple[str, str]]:
    """Alternatif yolların kolları: beş kol, seçilen kuralla (+ tabanlar)."""
    return [("rpt_yok", "a"), ("mevcut", "a"), ("mevcut", en_iyi), ("frr3", en_iyi),
            ("oneri", en_iyi), ("kahin", en_iyi)]


def tum_kollar(H: Hazirlik, en_iyi: str | None = None, ciftler=None,
               ilerleme: Path | None = ILERLEME) -> dict:
    """(kol, kural) → `KosuKaydi`. `ciftler` verilmezse `kol_listesi(en_iyi)`;
    `en_iyi` verilmezse `dagitim_secimi(H)`. Önce taban (rpt_yok, a); (mevcut, a)
    hazırlık koşusudur."""
    if ciftler is None:
        ciftler = kol_listesi(en_iyi if en_iyi is not None else dagitim_secimi(H, ilerleme=ilerleme))
    ciftler = list(dict.fromkeys(ciftler))
    sonuc = {("rpt_yok", "a"): kos(H, "rpt_yok", "a", ilerleme=ilerleme)}
    for kol, kural in ciftler:
        if (kol, kural) in sonuc:
            continue
        if (kol, kural) == ("mevcut", "a"):
            sonuc[(kol, kural)] = H.kosu
            continue
        sonuc[(kol, kural)] = kos(H, kol, kural, kahin_kosusu=sonuc[("rpt_yok", "a")], ilerleme=ilerleme)
    return {("rpt_yok", "a"): sonuc[("rpt_yok", "a")]} | {c: sonuc[c] for c in ciftler}


# ---------------------------------------------------------------------------
# Dağıtım kuralı seçimi (SS24)
# ---------------------------------------------------------------------------


def dagitim_tablosu(H: Hazirlik, ilerleme: Path | None = ILERLEME) -> pd.DataFrame:
    """Banu'nun RPT'leri + dört kural yalnız SS24'e: SS24 Collection özeti (kural başına)."""
    satir = []
    for kural in dagitim.KURAL_ADLARI:
        rep = dagitim_politikasi(H, kural, (SECIM_SEZONU,))
        k = _kos(f"y{H.yol}_secim_{kural}", ilerleme, replenishment=rep,
                 parametreler={"secim": SECIM_SEZONU, "kural": kural}, talep_tohumu=H.talep_tohumu,
                 onbellek=H.onbellek, olcek=H.olcek)
        oz = olcutler.sezon_ozeti(olcutler.ozet(k, SECIM_SEZONU))
        satir.append({"kural": kural, **{c: oz[c] for c in (
            "kar", "gelir", "karsilanmayan", "kalici_kayip", "satis_tf", "satis_ind", "rpt", "rpt_giren",
            "rpt_bosa", "magazaya", "stoklu_pay_tf")}})
    return pd.DataFrame(satir)


def en_iyi_kural(tablo: pd.DataFrame) -> str:
    """SS24 seçiminde kârı en yüksek RPT dağıtım kuralı (b, c, d arasından)."""
    s = tablo[tablo["kural"].isin(KURAL_ADAYLARI)]
    return str(s.loc[s["kar"].idxmax(), "kural"])


def dagitim_secimi(H: Hazirlik, ilerleme: Path | None = ILERLEME) -> str:
    return en_iyi_kural(dagitim_tablosu(H, ilerleme))


# ---------------------------------------------------------------------------
# Ölçüm
# ---------------------------------------------------------------------------


def ozet_tablosu(kosular: dict, sezon: str, kahin_anahtari=None) -> pd.DataFrame:
    """Kol × ölçüt (`olcutler.sezon_ozeti`), (rpt_yok, a) tabanına göre; kâhin
    anahtarı verilmezse kurallı kâhin çifti (yoksa (kahin, a))."""
    taban = olcutler.ozet(kosular[("rpt_yok", "a")], sezon)
    if kahin_anahtari is None:
        kh = [c for c in kosular if c[0] == "kahin"]
        kahin_anahtari = next((c for c in kh if c[1] != "a"), kh[0] if kh else None)
    kh_oz = olcutler.ozet(kosular[kahin_anahtari], sezon, taban) if kahin_anahtari else None
    satir = []
    for (kol, kural), k in kosular.items():
        o = kh_oz if (kol, kural) == kahin_anahtari else olcutler.ozet(k, sezon, taban)
        satir.append({"kol": kol, "kural": kural, **olcutler.sezon_ozeti(o, kh_oz)})
    return pd.DataFrame(satir)


def sinama(H: Hazirlik, kosu_yok, yollar_dizini: Path = YOLLAR_DIZINI) -> pd.DataFrame:
    """Aday modelinin sınama satırları: oyun sezonlarının karar satırları `rpt_yok`
    kolunun dünyasında (RPT'siz, kolun karar anında gördüğüyle: günlük tablo o
    dünyanın yayımlanan biçiminden, çarpanlar hazırlığın öğrendikleri), öğrenilen
    eğri / belirsizlik / p_ind'le özellikler, (i) gerçek etiket o koşunun gizli
    talebinden; model olasılıkları (`p_lgbm`, `p_lojistik`) ve Banu'nun kuralı
    (`banu`). Dizin `yol<p>/rpt_yok/` (DuckDB + günlük tablo + `sinama.parquet`)."""
    dizin = Path(yollar_dizini) / f"yol{H.yol}" / "rpt_yok"
    cikti = dizin / "sinama.parquet"
    iz = dizin / "sinama.anahtar"
    anahtar = _sha(kosu_yok.meta["anahtar"], H.ogrenilen.parametreler(), motor.kod_ozeti())
    if cikti.exists() and iz.exists() and iz.read_text(encoding="utf-8") == anahtar:
        return pd.read_parquet(cikti)
    db = veritabani_kur(kosu_yok, dizin / "perakende.duckdb", H.olcek)
    gunluk_kur(db, dizin)
    ogr = H.ogrenilen
    opt = ogr.optionlar
    con = kaynak.baglan(db)
    try:
        yol = hazirla.gunluk_yolu(dizin, con)
        t = kaynak.veri_yukle(db, sezonlar=OYUN)
        havuz = pd.concat([sansur_havuzu(opt, G) for G in OYUN], ignore_index=True)
        son = max(politika.karar_anlari(opt, G)[-1] for G in OYUN)
        gunluk = hazirla.havuz_gunlugu(yol, con, havuz, son + pd.Timedelta(days=1))
    finally:
        con.close()
    kayit = aday.karar_kaydi(gunluk, opt, OYUN, ogr.carpan, aday.tablo_durumu(t))
    del gunluk, t
    parca = []
    for G in OYUN:
        k = kayit[(kayit["sezon_kodu"] == G) & (kayit["rpt_sayisi"] == 0)]
        ozl = aday.ozellikler(k, opt, ogr.egriler[G], ogr.belirsizlik[G], ogr.p_ind)
        ozl = aday.etiket(ozl, _gercek_talep(kosu_yok, _skular(kosu_yok, ozl["option_id"].unique())),
                          opt, "gercek")
        ozl["p_lgbm"] = ogr.modeller[G].olasilik(ozl, "lgbm")
        ozl["p_lojistik"] = ogr.modeller[G].olasilik(ozl, "lojistik")
        ozl["banu"] = aday.banu_kurali(ozl)
        parca.append(ozl)
    s = pd.concat(parca, ignore_index=True)
    s.to_parquet(cikti, index=False)
    iz.write_text(anahtar, encoding="utf-8")
    return s


def sansur_havuzu(opt: pd.DataFrame, sezon: str) -> pd.DataFrame:
    """Sezonun Collection option'ları, lansmandan (karar satırlarının günlük havuzu)."""
    o = opt[(opt["sezon_kodu"] == sezon) & (opt["line"] == "Collection")]
    return pd.DataFrame({"option_id": o["option_id"].astype(str).to_numpy(),
                         "bas": pd.to_datetime(o["lansman_tarihi"]).to_numpy()})


# ---------------------------------------------------------------------------
# Komut
# ---------------------------------------------------------------------------


OLCUT_ALANLARI = ("kar", "d_kar", "gelir", "maliyet", "satis_tf", "satis_ind", "kurtarilan", "kurtarilan_tf",
                  "kurtarilan_kalici", "kurtarilan_ikame", "karsilanmayan", "kalici_kayip", "rpt",
                  "rpt_giren", "rpt_option", "rpt_bosa", "yanlis_alarm", "rpt_ek_tf", "rpt_ek_ind",
                  "rpt_str", "magazaya", "stoklu_pay_tf", "kacirilan", "kacirilan_tl", "option")


def tablo_sozlugu(tab: pd.DataFrame) -> dict:
    """`ozet_tablosu` → {"kol|kural": {ölçüt: değer}} (JSON için)."""
    return {f"{r['kol']}|{r['kural']}": {c: (None if pd.isna(r[c]) else float(r[c]))
                                         for c in OLCUT_ALANLARI if c in r}
            for r in tab.to_dict("records")}


def main(argv=None) -> dict:
    """Yol 0'ın ızgarası: hazırlık → dağıtım seçimi (SS24) → 14 kol → özetler
    (`cikti/oyun.json`) → aday sınama satırları."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.perf_counter()
    H = hazirlik(0)
    secim = dagitim_tablosu(H)
    en_iyi = en_iyi_kural(secim)
    print(secim.to_string(), flush=True)
    print(f"en iyi kural: {en_iyi}", flush=True)
    K = tum_kollar(H, en_iyi=en_iyi)
    sonuc = {"yol": 0, "en_iyi": en_iyi, "secim": secim.to_dict("records"),
             "hazirlik_sure": H.sure, "sezon": {}}
    for G in OYUN:
        tab = ozet_tablosu(K, G)
        print(f"\n{G}\n{tab[['kol', 'kural', 'kar', 'd_kar', 'kurtarilan', 'rpt', 'rpt_option', 'rpt_bosa', 'yanlis_alarm']].to_string()}",
              flush=True)
        sonuc["sezon"][G] = tablo_sozlugu(tab)
    a = time.perf_counter()
    s = sinama(H, K[("rpt_yok", "a")])
    _ilerleme("y0_sinama", time.perf_counter() - a, False, satir=int(len(s)))
    sonuc["sinama_satir"] = int(len(s))
    sonuc["sure"] = time.perf_counter() - t0
    (CIKTI / "oyun.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str),
                                     encoding="utf-8")
    return sonuc


if __name__ == "__main__":
    main()
