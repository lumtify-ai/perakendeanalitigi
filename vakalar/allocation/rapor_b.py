"""Raporun veri yarısı: `rapor.py`'nin bastığı her sayının girdisi buradan gelir.

Bu dosya **motoru koşturmaz**. Oyun koşularını `cikti/kosular/`'dan, `cikti/oyun.json`'daki
(ve `cikti/yollar.json`'daki) anahtarla, yalnız okumak için açar (`Onbellek`): meta yoksa, anahtar
ölçülmüş kayıttakinden farklıysa, bir Parquet dosyası eksikse ya da kayıt bugünkü koşu kodu, v4
dosyası ve kütüphane sürümleriyle yazılmamışsa koşu geçersizdir. Okuyucu `motor.kos`'un tersine
bozuk kaydı silmez ve eksik koşuyu koşmaz. Ölçülmüş kaydın ölçüm kodu (`olcum_kodu`) bugünkü
`oyun.olcum_kodu()` olmalıdır.

Girdiler:

    cikti/oyun.json, secim.json, kalibrasyon.json, hikaye.json, yollar.json   (ölçülmüş kayıtlar)
    cikti/kosular/<ad>_<anahtar[:20]>/        (koşuların tabloları, gizli gerçek, kol kayıtları)
    veri/cikti/v4/perakende.duckdb            (yayımlanan dünya: VERİ; `lumoda` koşusuyla birebir,
                                               eşdeğerlik testi)
    site/src/data/senaryolar/ilk-sevkiyat.json (demo; `senaryolar.uret()` ile aynı olmalı)

**Kesin ve taslak.** `hazirla()` (kesin) bir girdi eksik ya da geçersizse `RuntimeError` verir
(rapor stdout'a hiçbir şey basmaz). `hazirla(taslak=True)` eksikleri `Veri.eksik`'e yazar ve
devam eder; rapor bu durumda eksik koşuya dayanan satırları "[eksik: …]" diye geçer (ızgara
bitmeden biçim denetimi için; çıktısı yazılara kaynak olamaz, çıkış kodu 2).

Dünyadan (`motor.dunya`, koşu değil; ~40 sn) yalnız şunlar okunur: `lumoda` koşusunun kırpma
tablosu (`motor.kirpma_tablosu`), option'ların Lumoda'nın kuralıyla paket sayısı (`ilk_alim × 0,70
÷ paket adedi`) ve erken penceredeki birincil talep (`olcutler.erken_hucre_gunleri`; kahinin
bağımsızlık varsayımı, spec §0/11).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

import senaryolar
from allocation import hikaye_sec, kaynak, motor, olcutler, oyun, sabitler
from allocation import yollar as yollar_modulu
from allocation.paylastir import paket_adedi

CIKTI = sabitler.CIKTI
ONBELLEK = motor.KOSU_DIZINI
SEZON, LINE = sabitler.OYUN_SEZONU, sabitler.LINE
ANAHTAR_ALANLARI = ("ad", "parametreler", "turler", "politikalar", "talep_tohumu", "operasyon_tohumu", "olcek",
                    "gun_sayisi", "kod", "veri", "surumler")
FIZIKSEL_TIPLER = ("AVM", "Cadde")
# Kahinin bağımsızlık varsayımı (spec §0/11): erken penceredeki birincil talep bu koşularda
# `lumoda`'nınkiyle hücre-gün birebir olmalı (yol 0; yollarda y<p>_lumoda ↔ y<p>_kahin).
BAGIMSIZLIK_GRUPLARI = ("pay", "sabit_takvim")


class Eksik(RuntimeError):
    """Raporun okuduğu bir koşu ya da dosya yok (taslakta satır "[eksik: …]" basılır)."""

    def __init__(self, *adlar: str):
        self.adlar = tuple(adlar)
        super().__init__("eksik: " + ", ".join(adlar))


def json_oku(yol: Path) -> dict | None:
    yol = Path(yol)
    return json.loads(yol.read_text(encoding="utf-8")) if yol.is_file() else None


# ---------------------------------------------------------------------------
# Önbellek (salt okunur)
# ---------------------------------------------------------------------------


def guncel_kimlik() -> dict:
    """Bugünkü koşu kodu özeti, v4 dosyasının parmak izi, kütüphane sürümleri."""
    return {"kod": motor.kod_ozeti(), "veri": motor.veri_parmak_izi(),
            "surumler": {p: motor._surum(p) for p in motor.SURUM_PAKETLERI}}


def _ayni(a, b) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def kayit_sorunlari(meta: dict, beklenen_anahtar: str, guncel: dict) -> list[str]:
    """Önbellekteki koşu kaydının bugünkü kodla, veriyle ve ölçülmüş kayıtla tutarsızlıkları (boşsa
    geçerli): anahtar aynı; `kod`, `veri`, `surumler` güncel; meta'nın anahtar alanlarının özeti
    anahtarın kendisi (`motor.kos` aynı özetle arar)."""
    sorun = []
    if meta.get("anahtar") != beklenen_anahtar:
        sorun.append("anahtar ölçülmüş kayıttakinden farklı")
    for a in ("kod", "veri", "surumler"):
        if not _ayni(meta.get(a), guncel.get(a)):
            sorun.append(f"{a} bugünkünden farklı")
    icerik = {a: meta[a] for a in ANAHTAR_ALANLARI if a in meta}
    if motor._ozet(icerik) != meta.get("anahtar"):
        sorun.append("meta alanlarının özeti anahtarı vermiyor")
    return sorun


class Onbellek:
    """Ölçülmüş kayıtlardaki (ad → {anahtar, ayni?}) koşuları önbellekten salt okunur açar.
    `ayni` takma adı tabanın dizinini açar (Ruling R30)."""

    def __init__(self, kosular: dict, dizin: Path = ONBELLEK, guncel: dict | None = None):
        self.kosular, self.dizin = kosular, Path(dizin)
        self.guncel = guncel if guncel is not None else guncel_kimlik()
        self.acilan: set[str] = set()

    def _dizin(self, ad: str) -> Path:
        e = self.kosular[ad]
        return motor._dizin(self.dizin, e.get("ayni", ad), e["anahtar"])

    def sorunlar(self, ad: str) -> list[str]:
        if ad not in self.kosular:
            return ["ölçülmüş kayıtta (oyun.json / yollar.json) yok"]
        d = self._dizin(ad)
        meta_yolu = d / "meta.json"
        if not meta_yolu.is_file():
            return [f"önbellekte yok ({d.name})"]
        meta = json.loads(meta_yolu.read_text(encoding="utf-8"))
        dosyalar = ([d / f"tablo_{a}.parquet" for a in meta.get("tablolar", [])]
                    + [d / f"kayit_{a}.parquet" for a in meta.get("kayitlar", [])] + [d / "gercek.parquet"])
        eksik = [p.name for p in dosyalar if not p.is_file()]
        sorun = [f"dosya eksik: {', '.join(eksik)}"] if eksik else []
        return sorun + kayit_sorunlari(meta, self.kosular[ad]["anahtar"], self.guncel)

    def ac(self, ad: str) -> motor.KosuKaydi:
        sorun = self.sorunlar(ad)
        if sorun:
            raise RuntimeError(f"{ad}: " + "; ".join(sorun))
        d = self._dizin(ad)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        kayitlar = {a: pd.read_parquet(d / f"kayit_{a}.parquet") for a in meta.get("kayitlar", [])}
        self.acilan.add(ad)
        return motor.KosuKaydi(dizin=d, meta=meta, kayitlar=kayitlar, onbellekten=True)


# ---------------------------------------------------------------------------
# Yayımlanan dünya (VERİ)
# ---------------------------------------------------------------------------

_OYUN = f"""select distinct option_id, dalga from urun where sezon_kodu = '{SEZON}' and line = '{LINE}'"""
_FIZ = "select magaza_id, sehir from magaza where tip in ('AVM', 'Cadde')"


def yayimlanan_kur(con) -> dict:
    """VERİ bölümünün tabloları (yayımlanan v4; oyun sezonunun `LINE` option'ları)."""
    q = lambda s: con.execute(s).df()  # noqa: E731
    dalga = q(f"""
        with o as ({_OYUN}),
        alim as (select s.option_id, sum(s.adet) as siparis,
                        sum(case when s.gerceklesen_teslim is not null then s.adet else 0 end) as teslim
                 from siparis s join o using (option_id) where s.tip = 'ilk' group by 1),
        dag as (select u.option_id, sum(v.adet) as ilk_dagitim, count(distinct v.hedef) as magaza
                from sevkiyat v join urun u using (urun_id) join o using (option_id)
                where v.tip = 'ilk_dagitim' and v.hedef in (select magaza_id from ({_FIZ})) group by 1)
        select o.dalga, count(*) as option, sum(alim.siparis) as ilk_alim, sum(alim.teslim) as teslim,
               sum(dag.ilk_dagitim) as ilk_dagitim, max(dag.magaza) as en_cok_magaza
        from o left join alim using (option_id) left join dag using (option_id)
        group by 1 order by 1""")
    lansman = q(f"select dalga, lansman_tarihi, indirim_baslangic, cikis_tarihi from sezon "
                f"where sezon_kodu = '{SEZON}' order by dalga")
    magaza = q(f"""
        with o as ({_OYUN})
        select f.magaza_id, f.sehir = 'İstanbul' as istanbul
        from ({_FIZ}) f where f.magaza_id in (
            select distinct v.hedef from sevkiyat v join urun u using (urun_id) join o using (option_id)
            where v.tip = 'ilk_dagitim')""")
    beden = q(f"""
        with o as ({_OYUN}),
        bes as (select option_id from urun join o using (option_id) group by 1 having count(*) = 5)
        select u.beden_sira, sum(s.adet) as adet from siparis s join urun u using (urun_id)
        where s.tip = 'ilk' and u.option_id in (select option_id from bes) group by 1 order by 1""")
    paket = q(f"""
        select p.beden_seti, p.beden_sira, p.adet from paket p
        where p.beden_seti in (select distinct beden_seti from urun join ({_OYUN}) o using (option_id))
        order by 1, 2""")
    bes_option = q(f"""
        with o as ({_OYUN}) select count(*) as n from (
            select option_id from urun join o using (option_id) group by 1 having count(*) = 5)""")["n"].iloc[0]
    return {"dalga": dalga, "lansman": lansman, "magaza": magaza, "beden": beden, "paket": paket,
            "bes_bedenli_option": int(bes_option)}


# ---------------------------------------------------------------------------
# Lumoda'nın kuralı, U, kırpma, aday kümesi (dünyadan ve önbellekten)
# ---------------------------------------------------------------------------


def kol_karar_ozeti(kayit: pd.DataFrame) -> pd.DataFrame:
    """Kolun kendi kararlarının option başına özeti (`politika` kaydı, Ruling R17): arg0, U,
    toplam, giden (paket), aday (mağaza sayısı), tavanda."""
    k = kayit[kayit["kol"].to_numpy(dtype=bool)]
    g = k.groupby("arg0")
    return pd.DataFrame({"U": g["U"].first(), "toplam": g["toplam"].first(), "giden": g["deger"].sum(),
                         "aday": g["indis"].agg(lambda i: int((i >= 0).sum())),
                         "tavanda": g["tavanda"].first()}).reset_index()


def lumoda_kurali(w, lumoda: motor.KosuKaydi, esit: motor.KosuKaydi) -> dict:
    """Oyun option'larında: Lumoda'nın kuralının paketi (ilk alım × 0,70 ÷ paket adedi), U (eşit
    kolun kaydından; t = 0'da her kol aynı U'yu görür), aday kümesi, motorun Lumoda'yı kırpması."""
    opt = kaynak.oyun_optionlari(w, SEZON)
    ids = w.optionlar["option_id"].astype(str).to_numpy()
    pk = np.array([paket_adedi(w, int(o)) for o in opt], dtype=np.int64)
    kural = np.array([int(w.ilk_alim[o] * sabitler.LUMODA_ILK_PAYI // p) for o, p in zip(opt, pk)], dtype=np.int64)
    oz = kol_karar_ozeti(esit.kayitlar["ilk_dagitim"]).set_index("arg0").reindex(opt)
    if oz["U"].isna().any():
        raise RuntimeError("pay_esit: kaydında karar olmayan oyun option'ı var")
    U = oz["U"].to_numpy(dtype=np.int64)
    beden = np.bincount(np.asarray(w.sku_option, dtype=np.int64), minlength=len(w.optionlar))[opt]
    kt = motor.kirpma_tablosu(lumoda, w)
    kt = kt[kt["option_id"].isin(set(ids[opt]))]
    pk_id = dict(zip(ids[opt], pk))
    kirpilan_paket = (kt["istenen_paket"] - kt["giden_paket"]).to_numpy(dtype=np.int64)
    kirpilan_adet = int((kirpilan_paket * kt["option_id"].map(pk_id).to_numpy(dtype=np.int64)).sum())
    return {
        "option": int(len(opt)), "ilk_alim": int(np.asarray(w.ilk_alim, dtype=np.int64)[opt].sum()),
        "paket_adedi": sorted(set(pk.tolist())), "kural_paket": int(kural.sum()), "kural_adet": int((kural * pk).sum()),
        "U_paket": int(U.sum()), "U_adet": int((U * pk).sum()), "U_baglayan": int((U < kural).sum()),
        "U_kural_ustu": int((U > kural).sum()),
        "aday_hucre": int(oz["aday"].sum()), "aday_sku_hucre": int((oz["aday"].to_numpy() * beden).sum()), "aday_magaza_ort": float(oz["aday"].mean()),
        "aday_magaza_min": int(oz["aday"].min()), "aday_magaza_max": int(oz["aday"].max()),
        "kirpilan_option": int(kt["option_id"].nunique()), "kirpilan_hucre": int(len(kt)),
        "kirpilan_paket": int(kirpilan_paket.sum()), "kirpilan_adet": kirpilan_adet,
    }


def kural_hucreleri(lumoda: motor.KosuKaydi) -> pd.DataFrame:
    """Lumoda'nın ilk dağıtımının (option, fiziksel mağaza) hücreleri, hikâye seçimiyle aynı
    tanımlarla (`hikaye_sec.hucreler`: varan ilk adet, pay sırası, 28 / 14 günlük satış, plan sırası)."""
    urun = lumoda.tablo("urun", ["urun_id", "option_id", "model_adi", "renk", "ust_kategori", "sezon_kodu", "line"])
    sku = set(hikaye_sec._oyun_urunleri(urun, SEZON)["urun_id"])
    ilk = hikaye_sec.ilk_tablosu(lumoda.tablo("sevkiyat", ["tip", "hedef", "urun_id", "adet", "varis_tarihi"], sku), urun)
    satis = hikaye_sec.satis_tablosu(lumoda.tablo("satis", ["tarih", "magaza_id", "urun_id", "adet"], sku), urun)
    bos = pd.DataFrame({"option_id": pd.Series([], dtype=str), "magaza_id": pd.Series([], dtype=str),
                        "adet": pd.Series([], dtype=np.int64)})
    return hikaye_sec.hucreler(ilk, satis, lumoda.tablo("magaza"), lumoda.tablo("magaza_plan"), bos)


def plan_tablosu(lumoda: motor.KosuKaydi) -> pd.DataFrame:
    """Oyun sezonunun mağaza planı (fiziksel mağazalar): magaza_id, ust_kategori, satis_hedefi, sira."""
    plan, mag = lumoda.tablo("magaza_plan"), lumoda.tablo("magaza")
    sira = hikaye_sec.plan_sirasi(plan, mag, SEZON)
    p = plan[(plan["sezon_kodu"].astype(str) == SEZON).to_numpy()]
    p = pd.DataFrame({"magaza_id": p["magaza_id"].astype(str).to_numpy(), "ust_kategori": p["ust_kategori"].astype(str).to_numpy(),
                      "satis_hedefi": p["satis_hedefi"].to_numpy(dtype=float)})
    return sira.merge(p, on=["magaza_id", "ust_kategori"], how="left")


def bagimsizlik(w, harita, ob: Onbellek, taban: str, adlar: list[str]) -> dict[str, bool | None]:
    """Erken penceredeki birincil talep (`olcutler.erken_hucre_gunleri`) `taban` koşusununkiyle
    hücre-gün birebir mi (ad → bool); açılamayan koşu None. Döner ayrıca "_taban": (satır, Σ talep)."""
    ref = olcutler.erken_hucre_gunleri(ob.ac(taban), w, harita)
    sonuc: dict = {"_taban": (int(len(ref)), int(ref["talep"].sum()))}
    for ad in adlar:
        try:
            k = ob.ac(ad)
        except RuntimeError:
            sonuc[ad] = None
            continue
        sonuc[ad] = bool(olcutler.erken_hucre_gunleri(k, w, harita).equals(ref))
    return sonuc


# ---------------------------------------------------------------------------
# Hazırlık
# ---------------------------------------------------------------------------


@dataclass
class Veri:
    """Raporun bütün girdileri (`hazirla`)."""

    oyun: dict
    kal: dict
    secim: dict | None = None
    hikaye: dict | None = None
    yollar: dict | None = None
    demo: dict | None = None              # senaryolar.uret() (bugünkü önbellekten)
    demo_dosya: dict | None = None        # sitedeki dosya
    olcum_kodu: str = ""
    gecerli: set = field(default_factory=set)          # oyun.json'da ölçülmüş ve önbellekte geçerli
    yol_gecerli: set = field(default_factory=set)      # (yol, kısa ad)
    yayimlanan: dict | None = None
    kural: dict | None = None
    hucreler: pd.DataFrame | None = None
    plan: pd.DataFrame | None = None
    bagimsizlik: dict | None = None
    yol_bagimsizlik: dict | None = None
    yollar_kodu: str | None = None
    acilan: set = field(default_factory=set)
    eksik: list = field(default_factory=list)
    taslak: bool = False


def gereken_kosular() -> list[str]:
    """Izgaranın bütün adları (yol 0; `oyun.IZGARA`)."""
    return list(oyun.tum_kosumlar())


def hazirla(cikti: Path = CIKTI, onbellek: Path = ONBELLEK, taslak: bool = False,
            demo_hedef: Path = senaryolar.HEDEF) -> Veri:
    """Girdileri okur ve doğrular (modül notu). Kesin modda ilk eksik `RuntimeError`."""
    eksik: list[str] = []

    def yok(neden: str) -> None:
        if not taslak:
            raise RuntimeError(neden)
        eksik.append(neden)

    oyun_k = json_oku(Path(cikti) / "oyun.json")
    kal = json_oku(Path(cikti) / "kalibrasyon.json")
    if oyun_k is None or kal is None:
        raise RuntimeError("cikti/oyun.json ya da cikti/kalibrasyon.json yok: önce ızgara (python -m allocation.oyun)")
    v = Veri(oyun=oyun_k, kal=kal, taslak=taslak, eksik=eksik, olcum_kodu=oyun.olcum_kodu())
    for ad, dosya in (("secim", "secim.json"), ("hikaye", "hikaye.json"), ("yollar", "yollar.json")):
        setattr(v, ad, json_oku(Path(cikti) / dosya))
        if getattr(v, ad) is None:
            yok(f"cikti/{dosya} yok")

    kosular = oyun_k.get("kosular", {})
    ob = Onbellek(kosular, onbellek)
    for ad in gereken_kosular():
        if ad not in kosular:
            yok(f"{ad}: oyun.json'da ölçülmüş kayıt yok (ızgara bitmedi)")
    for ad, e in kosular.items():
        sorun = ob.sorunlar(ad)
        if e.get("olcum_kodu") != v.olcum_kodu:
            sorun.append("ölçüm kodu bugünkünden farklı")
        if sorun:
            yok(f"{ad}: " + "; ".join(sorun))
        else:
            v.gecerli.add(ad)

    con = kaynak.baglan()
    try:
        v.yayimlanan = yayimlanan_kur(con)
    finally:
        con.close()

    if {"lumoda", "pay_esit"} <= v.gecerli:
        w = motor.dunya("tam")
        harita = kaynak.harita_kur(w)
        lum = ob.ac("lumoda")
        v.kural = lumoda_kurali(w, lum, ob.ac("pay_esit"))
        v.hucreler = kural_hucreleri(lum)
        v.plan = plan_tablosu(lum)
        adlar = sorted(a for a in v.gecerli if a != "lumoda" and "ayni" not in kosular[a]
                       and kosular[a].get("grup") in BAGIMSIZLIK_GRUPLARI)
        v.bagimsizlik = bagimsizlik(w, harita, ob, "lumoda", adlar)
        if v.yollar is not None:
            v.yol_bagimsizlik, yol_ob = {}, None
            for p in range(sabitler.YOL_SAYISI):
                y = v.yollar.get("yollar", {}).get(str(p), {})
                for kisa in oyun.YOL_KOLLARI:
                    if kisa not in y.get("kosular", {}):
                        yok(f"yol {p} {kisa}: yollar.json'da ölçülmüş kayıt yok (yollar bitmedi)")
            for p, y in sorted(v.yollar.get("yollar", {}).items(), key=lambda x: int(x[0])):
                kayit = {k["ad"]: k for k in y.get("kosular", {}).values()}
                yol_ob = Onbellek(kayit, onbellek, ob.guncel)
                for kisa, k in y.get("kosular", {}).items():
                    sorun = yol_ob.sorunlar(k["ad"])
                    if k.get("olcum_kodu") != v.olcum_kodu:
                        sorun.append("ölçüm kodu bugünkünden farklı")
                    if sorun:
                        yok(f"yol {p} {kisa}: " + "; ".join(sorun))
                    else:
                        v.yol_gecerli.add((p, kisa))
                if int(p) > 0 and {(p, "lumoda"), (p, "kahin")} <= v.yol_gecerli:
                    lumoda_adi, kahin_adi = y["kosular"]["lumoda"]["ad"], y["kosular"]["kahin"]["ad"]
                    v.yol_bagimsizlik[p] = bagimsizlik(w, harita, yol_ob, lumoda_adi, [kahin_adi])[kahin_adi]
                ob.acilan |= {f"y{p}:{a}" for a in yol_ob.acilan}
            v.yollar_kodu = yollar_modulu.kod_ozeti()
    else:
        yok("lumoda / pay_esit geçerli değil: KURAL, VERİ'nin U'su ve kahin bağımsızlığı basılamaz")

    try:
        v.demo = senaryolar.uret(oyun_k, onbellek=onbellek, surum="rapor")
    except RuntimeError as e:
        yok(f"demo: {e}")
    v.demo_dosya = json_oku(demo_hedef)
    if v.demo_dosya is None:
        yok(f"demo dosyası yok ({Path(demo_hedef).name}): önce `python senaryolar.py`")
    v.acilan = set(ob.acilan)
    return v
