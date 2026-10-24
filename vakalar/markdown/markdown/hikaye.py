"""Hikâye (spec §6, §0/3): iki lacivert tulum, Oduncu Gömlek, her koldan fiyat yolu ve sonuç, tek-option ε
hesabı (`cikti/hikaye.json`).

    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m markdown.hikaye [--olcek KUCUK]

Bu modül ölçüm tarafındadır (`simulasyon.KOSU_DISI`; `tests/test_sizinti.py` `OLCUM_MODULLERI`). Simülasyon
koşmaz: yol 0 Lumoda koşusu ve kolların koşuları önbellekte, ölçümleri `oyun.json`'da olmalıdır (yoksa
`Eksik`). Dünyanın gizli alanlarına dokunmaz; tek-option hesabının gerçek ε'si `hakem`'den gelir.

**Sahne** (`SAHNE`, kullanıcı onaylı): SS25, `cok` MDL0606-LCV (1. dalga, malın hepsi baştan), `az`
MDL0605-LCV (3. dalga, erken biter), `gomlek` MDL0563-YSL (3. yazının örneği). KÜÇÜK dünyada bu option'lar
yoktur; `sahne_sec` aynı rolleri kuralla seçer (yalnız geliştirme; rapor KÜÇÜK'ü her zaman taslak basar):
`cok` 1. dalganın en çok ölü stoklusu, `az` 3. dalganın indirim başı STR'si en yükseği, `gomlek` indirim
− 28'den sonra en çok RPT alanı.

**Yayımlanan veriden** (TAM yayımlanan DuckDB, KÜÇÜK yol 0 Lumoda'sının yayımlanan biçimi; `oyun.Yol`):
künye (dalga, liste ve alış fiyatı, arz: ilk / RPT, RPT siparişleri), lansman haftasından çıkış + 84'e
pazartesi haftaları (`haftalik_seri`: pozitif satış, normal ve outlet hattının oranı, fiziksel mağaza
stoğu, outlet mağazası stoğu, depo; hafta indirim haftasına ve lansmana göre), karar günü (serbest
pencerenin ilk pazartesisi) ve indirim günü (indirim haftasının pazartesisi) stoğu: fiziksel mağaza
(outlet hariç) / depo, İstanbul (şehir "İstanbul") / Anadolu ve en büyük stoklu mağazalar (ad, şehir),
indirim başı STR, çıkıştan 7 gün önce kalan (mağaza / depo), çıkış + 120'de depoda ölü stok, Lumoda'nın
en derin oranı ve ilk oranlı haftası. Gömlek: Lumoda'nın STR'si (fiziksel mağaza brüt satışı ÷ depodan
mağazalara giden, indirim gününden önce; `LumodaMarkdown`'ın tanımı) ve arza göre STR, RPT'nin adedi ve
teslim gününün indirim gününe göre farkı, ölü stok.

**Kollardan** (yol 0, SS25; `oyun.json` ve koşu önbelleği): her kolun (Lumoda dahil) üç option'daki
haftalık normal hat oranı (lansman haftasından çıkış haftasına), ilk oranlı hafta, en derin oran ve
sonuç (option tablosundan: çıkışa kadar satış, çıkışta kalan, ölü stok, toplam ciro, markdown TL,
katkı); kolun karar günündeki kayıt satırı. Ders (`ders`): `opt`, `cok`'u Lumoda'nın kuralının
başlayabileceği günden (indirim − 28) önce indiriyor mu; `az`'ı çıkıştan önce indiriyor mu.
Pazartesi listesi (`pazartesi_listesi`): `opt` kaydı, karar günü ve indirim günü. İlk indirim haftasının
dağılımı (`indirim_haftalari`): yol 0'ın her kolunda, iki test sezonunda, option tablosundan.

**Tek-option ε hesabı** (`esneklik`; 4. yazı). `cok`'un karar günü, yol 0. Karar anı (`karar_ani`) yol 0
Lumoda koşusunun tablolarından motorun 9. adımındaki `Gorunum`'e kurulur (o güne dek bütün kollarda
SS25 aynıdır: hiçbir kol karar penceresinden önce oranı değiştirmez, RPT takvimdir): mağaza stoğu =
pazartesi fotoğrafı + o gün varan − o gün 9. adımdan önce çıkan; yolda = o güne dek yola çıkmış, sonra
varacak (o günün replenishment ve elle transferi hariç); depo = depo fotoğrafı + o günün teslimi (hatalı
düşülmüş, motorun `en_buyuk_kalan` bölüşümüyle) + varan − ilk dağıtım; satış geçmişi son 28 günün pozitif
satışı; stoklu günler fiziksel hücrede haftalık fotoğrafların `stoklu_gun` sayısından (satışlı günler
stokludur, sayının kalanı haftanın öteki günlerine), ONL'de günün depo fotoğrafından. `Tahminci`
(SS25'in bütün test option'ları, ε̂ kampanya, kolun boş oran geçmişi) taban talebi, satılabilir stoğu
verir; `D` = çıkışa kadar tam fiyat talep. Dört ε (saf, markdown, kampanya: öğrenilen; gerçek: hücre ε'si,
`hakem.kahin_girdisi`) için temizleme indirimi `1 − r = (D ÷ X0)^(1/ε)` (D ≥ X0 ise 0; merdivende üstteki
basamak) ve aynı `d`, aynı stokla `model.coz`un önerdiği yol. Doğrulama: aynı günün `opt_SS25` ve
`opt_tuzak_SS25` kayıtları (satılabilir stok bütün option'larda; sahne option'ında oran, tahmini satış,
beklenen kalan) yeniden kurulan karar anının sonucuyla aynı olmalı (rapor korunumu).

`kod`: bu dosya, vakanın simülasyon kodu özeti ve ölçüm kodu özeti; rapor eski kaydı reddeder.
"""

import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from allocation import motor
from perakende_veri.v4.plan import en_buyuk_kalan

from markdown import hakem, kaynak, model, oyun, politika, sabitler, simulasyon
from markdown.tahmin import PAY_GUN, Tahminci

SAHNE = {"cok": "MDL0606-LCV", "az": "MDL0605-LCV", "gomlek": "MDL0563-YSL"}
SEZON = "SS25"
KAYIT_SURUMU = 1
EN_BUYUK_MAGAZA = 5
LISTE_SATIRI = 10
OUTLET_GUN = 84
OLU_STOK_GUN = 120
CIKIS_FOTO_GUN = 7
LUMODA_ONCE_GUN = 28
ISTANBUL = "İstanbul"
DEPO = "DEPO"
_GUN0 = pd.Timestamp(sabitler.GUN_SIFIRI)
_K = np.asarray(sabitler.KADEMELER, dtype=float)
# motorun 9. adımından (markdown) önce çıkan sevk tipleri (dongu.py adım 3–6)
_ONCE_CIKAN_MAGAZA = ("geri_yonlendirme", "acilis_transferi", "kapanis_transferi", "outlet_akisi", "stok_devri")
_ONCE_CIKAN_DEPO = ("ilk_dagitim", "acilis_transferi", "outlet_akisi")
_SONRA_CIKAN = ("replenishment", "elle_transfer", "iade_depoya")


class Eksik(RuntimeError):
    """Hikâyenin dayandığı koşu ya da ölçüm yok: hikâye simülasyon başlatmaz (stderr, çıkış 1)."""


def kod_ozeti() -> str:
    h = hashlib.sha256()
    h.update(Path(__file__).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    h.update(simulasyon.vaka_kod_ozeti().encode() + b"\0" + oyun.olcum_kodu().encode())
    return h.hexdigest()


def _t(x) -> pd.Timestamp:
    return pd.Timestamp(x).normalize()


def _pazartesi(t) -> pd.Timestamp:
    t = _t(t)
    return t - pd.Timedelta(np.timedelta64(t.weekday(), "D"))


def _gun(t) -> int:
    return int((_t(t) - _GUN0).days)


def _iso(t) -> str | None:
    return None if t is None or pd.isna(t) else _t(t).date().isoformat()


def _f(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


# ---------------------------------------------------------------------------
# Yayımlanan tablolardan (DuckDB bağlantısı)
# ---------------------------------------------------------------------------


def _sorgu(con, sql: str, prm=()) -> pd.DataFrame:
    return con.execute(sql, list(prm)).df()


def kunye(con, oid: str) -> dict:
    """Option'ın künyesi ve arzı (`sezon` tablosunun günleri; teslim edilmiş ilk / RPT)."""
    u = _sorgu(con, """
        select any_value(u.model_adi::varchar) as model_adi, any_value(u.renk::varchar) as renk,
               any_value(u.dalga) as dalga, any_value(u.liste_fiyati) as liste, any_value(u.alis_fiyati) as alis,
               any_value(u.ust_kategori::varchar) as ust, any_value(u.alt_kategori::varchar) as alt_kategori,
               any_value(u.sezon_kodu::varchar) as sezon, any_value(z.lansman_tarihi) as L,
               any_value(z.indirim_baslangic) as I, any_value(z.cikis_tarihi) as C, count(*) as sku
        from urun u join sezon z on z.sezon_kodu::varchar = u.sezon_kodu::varchar and z.dalga = u.dalga
        where u.option_id::varchar = ?""", [oid])
    if not len(u) or u["sku"].iloc[0] == 0:
        raise KeyError(f"option yok: {oid}")
    r = u.iloc[0]
    sp = _sorgu(con, """
        select tip::varchar as tip, siparis_id::varchar as siparis_id, min(siparis_tarihi) as siparis,
               min(gerceklesen_teslim) as teslim, sum(adet) as adet
        from siparis where option_id::varchar = ? and tip::varchar in ('ilk', 'rpt')
          and gerceklesen_teslim is not null group by 1, 2 order by 3, 2""", [oid])
    I = _t(r["I"])
    rpt = [{"siparis": _iso(x.siparis), "teslim": _iso(x.teslim), "adet": int(x.adet),
            "teslim_indirime_gun": int((_t(x.teslim) - I).days), "siparis_indirime_gun": int((_t(x.siparis) - I).days)}
           for x in sp[sp["tip"] == "rpt"].itertuples()]
    L, C = _t(r["L"]), _t(r["C"])
    karar = max(I - pd.Timedelta(np.timedelta64(sabitler.ERKEN_GUN, "D")),
                L + pd.Timedelta(np.timedelta64(sabitler.RPT_SON_GUN, "D")))
    karar = karar + pd.Timedelta(np.timedelta64((7 - karar.weekday()) % 7, "D"))      # ilk pazartesi
    return {"option_id": oid, "model_adi": r["model_adi"], "renk": r["renk"], "dalga": int(r["dalga"]),
            "liste": float(r["liste"]), "alis": float(r["alis"]), "ust_kategori": r["ust"],
            "alt_kategori": r["alt_kategori"], "sezon": r["sezon"], "lansman": _iso(L), "indirim": _iso(I),
            "cikis": _iso(C), "karar_gunu": _iso(karar), "indirim_pazartesi": _iso(_pazartesi(I)),
            "arz_ilk": int(sp.loc[sp["tip"] == "ilk", "adet"].sum()), "arz_rpt": int(sp.loc[sp["tip"] == "rpt", "adet"].sum()),
            "rpt": rpt}


def haftalik_seri(con, oid: str, k: dict) -> list[dict]:
    """Lansman haftasından çıkış + 84'ün haftasına pazartesi haftaları (modül notu)."""
    L, I, C = _t(k["lansman"]), _t(k["indirim"]), _t(k["cikis"])
    bas, son = _pazartesi(L), _pazartesi(C + pd.Timedelta(np.timedelta64(OUTLET_GUN, "D")))
    haftalar = pd.date_range(bas, son, freq="7D")
    sat = _sorgu(con, """
        select date_trunc('week', s.tarih::date) as h, sum(s.adet) as adet
        from satis s join urun u on u.urun_id::varchar = s.urun_id::varchar
        where u.option_id::varchar = ? and s.adet > 0 group by 1""", [oid])
    fiy = _sorgu(con, """
        select hafta_baslangic::date as h, hat::varchar as hat, max(indirim_orani) as oran
        from fiyat where option_id::varchar = ? group by 1, 2""", [oid])
    stk = _sorgu(con, """
        select k.tarih::date as h, (m.tip::varchar = 'Outlet') as outlet, sum(k.adet) as adet
        from stok k join urun u on u.urun_id::varchar = k.urun_id::varchar
        join magaza m on m.magaza_id::varchar = k.magaza_id::varchar
        where u.option_id::varchar = ? and m.tip::varchar <> 'Online' group by 1, 2""", [oid])
    dep = _sorgu(con, """
        select k.tarih::date as h, sum(k.adet) as adet from depo_stok k
        join urun u on u.urun_id::varchar = k.urun_id::varchar where u.option_id::varchar = ? group by 1""", [oid])

    def harita(df, maske=None):
        df = df if maske is None else df[maske]
        return {_t(a): float(b) for a, b in zip(df["h"], df["adet" if "adet" in df else "oran"])}

    s, d = harita(sat), harita(dep)
    mg, ou = harita(stk, ~stk["outlet"].astype(bool)), harita(stk, stk["outlet"].astype(bool))
    fn, fo = harita(fiy, fiy["hat"] == "normal"), harita(fiy, fiy["hat"] == "outlet")
    i0, l0 = _pazartesi(I), _pazartesi(L)
    return [{"hafta_bas": _iso(h), "hafta": int((h - i0).days // 7), "hafta_lansman": int((h - l0).days // 7),
             "satis": s.get(h, 0.0), "oran": fn.get(h), "outlet_oran": fo.get(h), "magaza_stok": mg.get(h, 0.0),
             "outlet_stok": ou.get(h, 0.0), "depo": d.get(h, 0.0)} for h in haftalar]


def stok_dagilimi(con, oid: str, gun, n: int = EN_BUYUK_MAGAZA) -> dict:
    """`gun` pazartesisinin fiziksel mağaza (outlet hariç) stoğu: İstanbul / Anadolu ve en büyük `n` mağaza;
    depo."""
    g = _t(gun).date().isoformat()
    m = _sorgu(con, f"""
        select k.magaza_id::varchar as magaza_id, any_value(m.ad::varchar) as ad, any_value(m.sehir::varchar) as sehir,
               sum(k.adet) as adet
        from stok k join urun u on u.urun_id::varchar = k.urun_id::varchar
        join magaza m on m.magaza_id::varchar = k.magaza_id::varchar
        where u.option_id::varchar = ? and k.tarih::date = date '{g}' and m.tip::varchar not in ('Outlet', 'Online')
        group by 1 order by 4 desc, 1""", [oid])
    d = _sorgu(con, f"""
        select coalesce(sum(k.adet), 0) as adet from depo_stok k join urun u on u.urun_id::varchar = k.urun_id::varchar
        where u.option_id::varchar = ? and k.tarih::date = date '{g}'""", [oid])
    ist = m["sehir"] == ISTANBUL
    return {"gun": g, "magaza": float(m["adet"].sum()), "depo": float(d["adet"].iloc[0]),
            "istanbul": float(m.loc[ist, "adet"].sum()), "anadolu": float(m.loc[~ist, "adet"].sum()),
            "magaza_sayisi": int((m["adet"] > 0).sum()),
            "en_buyuk": [{"magaza_id": r.magaza_id, "ad": r.ad, "sehir": r.sehir, "adet": float(r.adet),
                          "istanbul": r.sehir == ISTANBUL} for r in m.head(n).itertuples()]}


def _depo_gunu(con, oid: str, gun) -> float:
    g = _t(gun).date().isoformat()
    return float(_sorgu(con, f"""select coalesce(sum(k.adet), 0) as a from depo_stok k join urun u
        on u.urun_id::varchar = k.urun_id::varchar where u.option_id::varchar = ? and k.tarih::date = date '{g}'""",
                        [oid])["a"].iloc[0])


def _magaza_gunu(con, oid: str, gun) -> float:
    g = _t(gun).date().isoformat()
    return float(_sorgu(con, f"""select coalesce(sum(k.adet), 0) as a from stok k join urun u
        on u.urun_id::varchar = k.urun_id::varchar where u.option_id::varchar = ? and k.tarih::date = date '{g}'""",
                        [oid])["a"].iloc[0])


def _son_gun(con) -> pd.Timestamp:
    return _t(con.execute("select max(tarih) from depo_stok").fetchone()[0])


def satis_once(con, oid: str, gun, fiziksel: bool = False) -> float:
    g = _t(gun).date().isoformat()
    ek = "and m.tip::varchar <> 'Online'" if fiziksel else ""
    return float(_sorgu(con, f"""select coalesce(sum(s.adet), 0) as a from satis s
        join urun u on u.urun_id::varchar = s.urun_id::varchar join magaza m on m.magaza_id::varchar = s.magaza_id::varchar
        where u.option_id::varchar = ? and s.adet > 0 and s.tarih::date < date '{g}' {ek}""", [oid])["a"].iloc[0])


def magazaya_giden(con, oid: str, gun) -> float:
    """Depodan fiziksel mağazalara giden adet, `gun`den önce (Lumoda STR'sinin paydası)."""
    g = _t(gun).date().isoformat()
    return float(_sorgu(con, f"""select coalesce(sum(v.adet), 0) as a from sevkiyat v
        join urun u on u.urun_id::varchar = v.urun_id::varchar
        where u.option_id::varchar = ? and v.kaynak::varchar = '{DEPO}' and v.hedef::varchar not in ('{DEPO}', 'ONL')
          and v.tarih::date < date '{g}'""", [oid])["a"].iloc[0])


def _lumoda_orani(seri: list[dict], k: dict) -> dict:
    sezon_ici = [r for r in seri if r["hafta_bas"] < k["cikis"] and r["oran"] is not None]
    oranli = [r for r in sezon_ici if r["oran"] > 0]
    return {"en_derin": max((r["oran"] for r in sezon_ici), default=0.0),
            "ilk_indirim_hafta": oranli[0]["hafta"] if oranli else None}


def tulum(con, oid: str) -> dict:
    """Bir tulumun hikâyesi (modül notu)."""
    k = kunye(con, oid)
    seri = haftalik_seri(con, oid, k)
    I, C = _t(k["indirim"]), _t(k["cikis"])
    arz = k["arz_ilk"] + k["arz_rpt"]
    foto = C - pd.Timedelta(np.timedelta64(CIKIS_FOTO_GUN, "D"))
    olu = min(C + pd.Timedelta(np.timedelta64(OLU_STOK_GUN, "D")), _son_gun(con))
    so = satis_once(con, oid, I)
    return {**k, "arz": arz, "haftalik": seri, "satis_once": so, "str_ind": 100.0 * so / arz if arz else 0.0,
            "karar": stok_dagilimi(con, oid, k["karar_gunu"]), "indirim_gunu": stok_dagilimi(con, oid, k["indirim_pazartesi"]),
            "cikis_kalan": {"magaza": _magaza_gunu(con, oid, foto), "depo": _depo_gunu(con, oid, foto)},
            "olu_stok": _depo_gunu(con, oid, olu), "lumoda": _lumoda_orani(seri, k)}


def gomlek(con, oid: str) -> dict:
    """Oduncu Gömlek: Lumoda'nın kör noktası (modül notu)."""
    k = kunye(con, oid)
    I, C = _t(k["indirim"]), _t(k["cikis"])
    arz = k["arz_ilk"] + k["arz_rpt"]
    fiz, giden, hepsi = satis_once(con, oid, I, fiziksel=True), magazaya_giden(con, oid, I), satis_once(con, oid, I)
    seri = haftalik_seri(con, oid, k)
    olu = min(C + pd.Timedelta(np.timedelta64(OLU_STOK_GUN, "D")), _son_gun(con))
    return {**k, "arz": arz, "satis_once_fiziksel": fiz, "magazaya_giden": giden, "satis_once": hepsi,
            "str_lumoda": fiz / giden if giden else 0.0, "str_arz": hepsi / arz if arz else 0.0,
            "olu_stok": _depo_gunu(con, oid, olu), "haftalik": seri, "lumoda": _lumoda_orani(seri, k)}


def sahne_sec(con, sezon: str = SEZON) -> dict:
    """Sahnenin option'ları: `SAHNE` dünyada varsa o; yoksa (KÜÇÜK) kurallı yedekler (modül notu)."""
    var = set(_sorgu(con, "select distinct option_id::varchar as o from urun")["o"])
    if all(o in var for o in SAHNE.values()):
        return dict(SAHNE)
    s = sezon.replace("'", "")
    t = _sorgu(con, f"""
        with u as (select u.urun_id::varchar as urun_id, u.option_id::varchar as option_id, u.dalga,
                          cast(z.indirim_baslangic as date) as I, cast(z.cikis_tarihi as date) as C
                   from urun u join sezon z on z.sezon_kodu::varchar = u.sezon_kodu::varchar and z.dalga = u.dalga
                   where u.line::varchar = '{sabitler.LINE}' and u.sezon_kodu::varchar = '{s}'),
        ar as (select u.option_id, sum(s.adet) as arz,
                      sum(case when s.tip::varchar = 'rpt' and cast(s.gerceklesen_teslim as date) >= u.I - interval 28 day
                               then s.adet else 0 end) as gec
               from siparis s join u on s.urun_id::varchar = u.urun_id
               where s.tip::varchar in ('ilk', 'rpt') and s.gerceklesen_teslim is not null group by 1),
        sa as (select u.option_id, sum(case when s.adet > 0 and s.tarih::date < u.I then s.adet else 0 end) as once
               from satis s join u on s.urun_id::varchar = u.urun_id group by 1),
        ol as (select u.option_id, sum(k.adet) as olu from depo_stok k join u on k.urun_id::varchar = u.urun_id
               where k.tarih::date = least(u.C + interval 120 day, (select max(tarih)::date from depo_stok)) group by 1)
        select o.option_id, o.dalga, coalesce(ar.arz, 0) as arz, coalesce(ar.gec, 0) as gec,
               coalesce(sa.once, 0) as once, coalesce(ol.olu, 0) as olu
        from (select option_id, any_value(dalga) as dalga from u group by 1) o
        left join ar using (option_id) left join sa using (option_id) left join ol using (option_id)
        order by option_id""")
    t["str"] = np.where(t["arz"] > 0, t["once"] / t["arz"].where(t["arz"] > 0, 1), 0.0)
    d1, d3 = t[t["dalga"] == 1], t[t["dalga"] == 3]
    cok = d1.sort_values(["olu", "option_id"], ascending=[False, True])["option_id"].iloc[0]
    az = d3[d3["option_id"] != cok].sort_values(["str", "option_id"], ascending=[False, True])["option_id"].iloc[0]
    kalan = t[~t["option_id"].isin([cok, az])]
    gm = kalan.sort_values(["gec", "option_id"], ascending=[False, True])["option_id"].iloc[0]
    return {"cok": cok, "az": az, "gomlek": gm}


# ---------------------------------------------------------------------------
# Karar anı (yol 0 Lumoda koşusunun tablolarından)
# ---------------------------------------------------------------------------


class _Pencere:
    """`[gun, C]` geçmiş dizisinin yalnız `[bas, bas + W)` günlerini tutan görünümü: `x[a:b, hucreler]`."""

    def __init__(self, bas: int, dizi: np.ndarray):
        self.bas, self.dizi = int(bas), dizi

    def __getitem__(self, anahtar):
        satir, sutun = anahtar
        if not isinstance(satir, slice) or satir.step not in (None, 1):
            raise TypeError("yalnız ardışık gün dilimi")
        a, b = int(satir.start), int(satir.stop)
        if a < self.bas or b > self.bas + len(self.dizi):
            raise IndexError(f"geçmiş penceresi [{self.bas}, {self.bas + len(self.dizi)}) dışında: [{a}, {b})")
        return self.dizi[a - self.bas:b - self.bas][:, sutun]


def hucre_bul(w, magaza_id, urun_id) -> np.ndarray:
    """(magaza_id, urun_id) → dünya hücre indisi (yoksa −1)."""
    S = len(w.urunler)
    m = pd.Index(w.magazalar["magaza_id"].astype(str)).get_indexer(pd.Series(magaza_id).astype(str))
    s = pd.Index(w.urunler["urun_id"].astype(str)).get_indexer(pd.Series(urun_id).astype(str))
    anahtar = np.asarray(w.hucre_magaza, dtype=np.int64) * S + np.asarray(w.hucre_sku, dtype=np.int64)
    sira = np.argsort(anahtar, kind="stable")
    sirali = anahtar[sira]
    k = np.where((m >= 0) & (s >= 0), m.astype(np.int64) * S + s, -1)
    i = np.minimum(np.searchsorted(sirali, k), len(sirali) - 1)
    return np.where((k >= 0) & (sirali[i] == k), sira[i], -1)


def _gunler(sutun) -> np.ndarray:
    t = pd.to_datetime(pd.Series(sutun)).to_numpy().astype("datetime64[D]")
    g = (t - np.datetime64(sabitler.GUN_SIFIRI, "D")).astype(np.int64)
    return np.where(np.isnat(t), np.iinfo(np.int64).min, g)


def karar_ani(kosu, w, gun: int, test_idx) -> SimpleNamespace:
    """Motorun `gun` pazartesisindeki 9. adım (markdown) `Gorunum`'ü, test option'larının hücrelerinde (modül
    notu). Dönüş `Tahminci`'nin okuduğu alanları taşır; geçmiş dizileri yalnız son 28 günü tutar."""
    gun = int(gun)
    if (gun + _GUN0.weekday()) % 7:
        raise ValueError(f"karar anı pazartesi olmalı: gün {gun}")
    test_idx = np.asarray(test_idx, dtype=np.int64)
    S, C, O = len(w.urunler), len(w.hucre_magaza), len(w.optionlar)
    so = np.asarray(w.sku_option, dtype=np.int64)
    sku_test = np.isin(so, test_idx)
    urun_id = w.urunler["urun_id"].astype(str).to_numpy()
    skular = urun_id[sku_test]
    sku_ix = pd.Index(urun_id)
    online = np.asarray(w.hucre_online, dtype=bool)
    hs = np.asarray(w.hucre_sku, dtype=np.int64)
    bas = gun - PAY_GUN

    # Satış geçmişi (pozitif satış = brüt; ikame dahil)
    s = kosu.tablo("satis", ["tarih", "magaza_id", "urun_id", "adet"], urunler=skular)
    g = _gunler(s["tarih"])
    a = s["adet"].to_numpy(dtype=np.int64)
    m = (a > 0) & (g >= bas) & (g < gun)
    c = hucre_bul(w, s["magaza_id"][m], s["urun_id"][m])
    if (c < 0).any():
        raise ValueError("karar anı: hücresi olmayan satış satırı")
    satis = np.zeros((PAY_GUN, C), dtype=np.int64)
    np.add.at(satis, (g[m] - bas, c), a[m])
    del s

    # Stoklu günler: fiziksel hücrede haftalık fotoğrafın stoklu_gun sayısı, ONL'de günün depo fotoğrafı
    stoklu = np.zeros((PAY_GUN, C), dtype=bool)
    st = kosu.tablo("stok", ["tarih", "magaza_id", "urun_id", "adet", "stoklu_gun"], urunler=skular)
    sg = _gunler(st["tarih"])
    for p in range(bas + 7, gun + 1, 7):
        r = st[sg == p]
        hc = hucre_bul(w, r["magaza_id"], r["urun_id"])
        sayi = np.zeros(C, dtype=np.int64)
        np.add.at(sayi, hc[hc >= 0], r["stoklu_gun"].to_numpy(dtype=np.int64)[hc >= 0])
        blok = slice(p - 7 - bas, p - bas)
        satisli = satis[blok] > 0
        stoklu[blok] |= satisli
        kalan = sayi - satisli.sum(0)
        fiz = ~online
        if (kalan[fiz] < 0).any():
            raise ValueError(f"karar anı: {p} fotoğrafında stoklu gün satışlı günden az")
        for i in range(6, -1, -1):                   # kalan stoklu günler haftanın son günlerinden
            ek = fiz & (kalan > 0) & ~stoklu[blok][i]
            stoklu[p - 7 - bas + i, ek] = True
            kalan = kalan - ek
    dp = kosu.tablo("depo_stok", ["tarih", "urun_id", "adet"], urunler=skular)
    dg = _gunler(dp["tarih"])
    on_c = np.flatnonzero(online & np.isin(hs, np.flatnonzero(sku_test)))
    for i in range(PAY_GUN):
        r = dp[dg == bas + i]
        dolu = np.zeros(S, dtype=bool)
        dolu[sku_ix.get_indexer(r["urun_id"].astype(str))[r["adet"].to_numpy() > 0]] = True
        stoklu[i, on_c] |= dolu[hs[on_c]]
        stoklu[i, on_c] |= satis[i, on_c] > 0

    # Mağaza stoğu, yolda, depo (9. adım)
    magaza = np.zeros(C, dtype=np.int64)
    r = st[sg == gun]
    hc = hucre_bul(w, r["magaza_id"], r["urun_id"])
    np.add.at(magaza, hc[hc >= 0], r["adet"].to_numpy(dtype=np.int64)[hc >= 0])
    sv = kosu.tablo("sevkiyat", ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip"], urunler=skular)
    t0, t1 = _gunler(sv["tarih"]), _gunler(sv["varis_tarihi"])
    kay, hed, tip = (sv[x].astype(str).to_numpy() for x in ("kaynak", "hedef", "tip"))
    adet = sv["adet"].to_numpy(dtype=np.int64)
    varis_var = t1 > np.iinfo(np.int64).min
    gel = varis_var & (t1 == gun) & (hed != DEPO)
    hc = hucre_bul(w, hed[gel], sv["urun_id"][gel])
    np.add.at(magaza, hc[hc >= 0], adet[gel][hc >= 0])
    cik = (t0 == gun) & (kay != DEPO) & np.isin(tip, _ONCE_CIKAN_MAGAZA)
    hc = hucre_bul(w, kay[cik], sv["urun_id"][cik])
    np.subtract.at(magaza, hc[hc >= 0], adet[cik][hc >= 0])
    yolda = np.zeros(C, dtype=np.int64)
    yol = varis_var & (hed != DEPO) & (t1 > gun) & ((t0 < gun) | ((t0 == gun) & ~np.isin(tip, _SONRA_CIKAN)))
    hc = hucre_bul(w, hed[yol], sv["urun_id"][yol])
    np.add.at(yolda, hc[hc >= 0], adet[yol][hc >= 0])

    depo = np.zeros(S, dtype=np.int64)
    r = dp[dg == gun]
    np.add.at(depo, sku_ix.get_indexer(r["urun_id"].astype(str)), r["adet"].to_numpy(dtype=np.int64))
    sp = kosu.tablo("siparis", ["siparis_id", "urun_id", "gerceklesen_teslim", "adet"], urunler=skular)
    sp = sp[_gunler(sp["gerceklesen_teslim"]) == gun]
    if len(sp):
        kk = kosu.tablo("kalite_kontrol", ["siparis_id", "hatali"])
        hatali = dict(zip(kk["siparis_id"].astype(str), kk["hatali"].astype(int)))
        for sid, grup in sp.groupby(sp["siparis_id"].astype(str)):
            ix = sku_ix.get_indexer(grup["urun_id"].astype(str))
            sira = np.argsort(ix, kind="stable")
            ix, ad = ix[sira], grup["adet"].to_numpy(dtype=np.int64)[sira]
            depo[ix] += ad - en_buyuk_kalan(int(hatali.get(sid, 0)), ad)
    gir = varis_var & (t1 == gun) & (hed == DEPO) & ~((t0 == gun) & (tip == "iade_depoya"))
    np.add.at(depo, sku_ix.get_indexer(sv["urun_id"][gir].astype(str)), adet[gir])
    dcik = (t0 == gun) & (kay == DEPO) & np.isin(tip, _ONCE_CIKAN_DEPO)
    np.subtract.at(depo, sku_ix.get_indexer(sv["urun_id"][dcik].astype(str)), adet[dcik])

    # Açık siparişler (Gorunum'ün açık kopyası; Tahminci satılabilir stoğa sayar, R28): bugünden önce
    # verilmiş (bugünün RPT'si 7. adımda, Gorunum'den sonra), bugün ya da önce teslim edilmemiş
    ac = kosu.tablo("siparis", ["siparis_id", "option_id", "urun_id", "siparis_tarihi", "planlanan_teslim",
                                "gerceklesen_teslim", "adet"], urunler=skular)
    t_sip, t_ger = _gunler(ac["siparis_tarihi"]), _gunler(ac["gerceklesen_teslim"])
    ac = ac[(t_sip < gun) & ((t_ger > gun) | (t_ger == np.iinfo(np.int64).min))]
    opt_ix = pd.Index(w.optionlar["option_id"].astype(str))
    acik_siparisler = tuple(
        {"option": int(opt_ix.get_loc(str(grup["option_id"].iloc[0]))),
         "planlanan_gun": int(_gunler(grup["planlanan_teslim"].iloc[:1])[0]),
         "skular": sku_ix.get_indexer(grup["urun_id"].astype(str)),
         "adetler": grup["adet"].to_numpy(dtype=np.int64)}
        for _sid, grup in ac.groupby(ac["siparis_id"].astype(str), sort=True))

    return SimpleNamespace(dunya=w, gun=gun, tarih=_GUN0 + pd.Timedelta(np.timedelta64(gun, "D")),
                           magaza_stok=magaza, depo=depo, yolda=yolda, satis_gecmisi=_Pencere(bas, satis),
                           stoklu_gecmisi=_Pencere(bas, stoklu), satis_oncesi_gecmisi=None, fiyat_gecmisi=None,
                           fiyat_orani=np.zeros((O, 3)), acik_siparisler=acik_siparisler)


def temizleme_indirimi(talep: float, stok: float, eps: float) -> float:
    """`1 − r = (talep ÷ stok)^(1/ε)`: talep tam fiyatta stoğu eritmiyorsa stoğu eritecek indirim; talep ≥ stok
    ise 0 (ε ≤ 0'da tanımsız: NaN)."""
    if stok <= 0 or talep >= stok:
        return 0.0
    if eps <= 0:
        return float("nan")
    return float(1.0 - (talep / stok) ** (1.0 / eps))


def _bos_gecmis(o):
    return np.zeros(0, dtype=np.int64), np.zeros(0)


def _karar(t: Tahminci, g, o: int, liste: float, indirim: int, cikis: int, eps, kalinti: float) -> dict:
    """`Optimizasyon._karar`'ın bir option için adımları (serbest kip, k0 = 0): tahmin + DP."""
    ufuk = np.arange(int(g.gun), int(cikis))
    hucre, d = t.taban(g, o, ufuk)
    X0, pay = t.satilabilir(g, o, hucre, d)
    carpan, etkin = t.carpan(g, o, ufuk, eps)
    z = model.coz(d, pay, X0, liste, carpan, etkin, 0, politika.izinli(ufuk, indirim, 0.0),
                  t.iade_payi(g, o, hucre, d), kalinti)
    return {"hucre": hucre, "d": d, "X0": float(X0), "pay": pay, "talep": float(np.asarray(d).sum()),
            "kademe": [float(_K[k]) for k in z.kademe], "oran": float(_K[z.kademe[0]]),
            "tahmini_satis": float(z.beklenen_satis.sum()), "beklenen_kalan": float(z.beklenen_kalan),
            "beklenen_ciro": float(z.beklenen_ciro)}


def _kayit_satiri(kosu, gun: int, o: int) -> dict | None:
    k = (kosu.kayitlar or {}).get("markdown")
    if k is None or list(k.columns) != list(politika.KAYIT_SUTUNLARI):
        return None
    r = k[(k["gun"] == gun) & (k["option"] == o)]
    return None if not len(r) else {c: float(r[c].iloc[0]) for c in politika.KAYIT_SUTUNLARI[2:]}


def esneklik_hesabi(Y: oyun.Yol, lumoda, kosular: dict, oid: str) -> dict:
    """Tek-option ε hesabı ve karar anının doğrulaması (modül notu). `kosular`: kol → tembel koşu kaydı."""
    w = Y.w
    opt = w.optionlar
    o = int(np.flatnonzero(opt["option_id"].astype(str).to_numpy() == oid)[0])
    idx = Y.test_idx(SEZON)
    gun = int(kaynak.karar_penceresi(opt, np.array([o]), "serbest")[0])
    liste = float(opt["liste_fiyati"].iloc[o])
    indirim, cikis = int(opt["indirim_gun"].iloc[o]), int(opt["cikis_gun"].iloc[o])
    og = Y.ogrenilen(SEZON)
    g = karar_ani(lumoda, w, gun, idx)
    ust = str(opt["ust_kategori"].iloc[o])
    t = Tahminci(og, idx, eps=og.eps_kampanya, oran_gecmisi=_bos_gecmis)
    ana = _karar(t, g, o, liste, indirim, cikis, t.option_eps(g, o), og.kalinti)
    gercek_girdi = hakem.kahin_girdisi(w, [o], ufuk=np.array([gun]))
    eps_gercek = gercek_girdi.eps
    if not np.array_equal(gercek_girdi.hucre, ana["hucre"]):
        raise ValueError("gerçek ε hücreleri tahmincinin hücreleriyle eşleşmiyor")
    Dc = np.asarray(ana["d"]).sum(0)
    eps_ort = float((Dc * eps_gercek).sum() / Dc.sum()) if Dc.sum() > 0 else float(eps_gercek.mean())
    epsler = [("saf", og.eps_saf, og.eps_saf), ("markdown", og.eps(ust, "markdown"), og.eps(ust, "markdown")),
              ("kampanya", og.eps(ust), og.eps(ust)), ("gercek", eps_ort, eps_gercek)]
    satirlar = []
    for ad, deger, dp_eps in epsler:
        if ad == "kampanya":
            z = ana
        else:
            carpan, etkin = t.carpan(g, o, np.arange(gun, cikis), dp_eps)
            zz = model.coz(ana["d"], ana["pay"], ana["X0"], liste, carpan, etkin, 0,
                           politika.izinli(np.arange(gun, cikis), indirim, 0.0),
                           t.iade_payi(g, o, ana["hucre"], ana["d"]), og.kalinti)
            z = {"kademe": [float(_K[k]) for k in zz.kademe], "oran": float(_K[zz.kademe[0]]),
                 "tahmini_satis": float(zz.beklenen_satis.sum()), "beklenen_kalan": float(zz.beklenen_kalan),
                 "beklenen_ciro": float(zz.beklenen_ciro)}
        ham = temizleme_indirimi(ana["talep"], ana["X0"], float(deger))
        satirlar.append({"ad": ad, "eps": float(deger), "temizleme_ham": _f(ham),
                         "temizleme_kademe": None if math.isnan(ham) else float(politika.merdivene(ham)),
                         "dp_oran": z["oran"], "dp_yol": z["kademe"], "dp_kalan": z["beklenen_kalan"],
                         "dp_satis": z["tahmini_satis"], "dp_ciro": z["beklenen_ciro"]})

    # Doğrulama: aynı günün kol kayıtları
    dogrulama = {}
    for kol, tablo in (("opt", og.eps_kampanya), ("opt_tuzak", og.eps_markdown)):
        k = kosular.get(kol)
        if k is None:
            continue
        tt = t if kol == "opt" else Tahminci(og, idx, eps=tablo, oran_gecmisi=_bos_gecmis)
        z = ana if kol == "opt" else _karar(tt, g, o, liste, indirim, cikis, tt.option_eps(g, o), og.kalinti)
        kayit = k.kayitlar["markdown"]
        gunun = kayit[kayit["gun"] == gun]
        x_esit = []
        for oo, sat in zip(gunun["option"].to_numpy(dtype=np.int64), gunun["satilabilir"].to_numpy(dtype=float)):
            h, dd = tt.taban(g, int(oo), np.arange(gun, int(opt["cikis_gun"].iloc[int(oo)])))
            x_esit.append(bool(np.isclose(tt.satilabilir(g, int(oo), h, dd)[0], sat, rtol=1e-9, atol=1e-6)))
        r = _kayit_satiri(k, gun, o) or {}
        dogrulama[kol] = {"kayit": r, "hesap": {"oran": z["oran"], "satilabilir": z["X0"], "tahmini_satis": z["tahmini_satis"],
                                                "beklenen_kalan": z["beklenen_kalan"]},
                          "satilabilir_option": len(x_esit), "satilabilir_esit": int(sum(x_esit)),
                          "esit": bool(r) and all(np.isclose(r[c], v, rtol=1e-9, atol=1e-6) for c, v in
                                                   (("oran", z["oran"]), ("satilabilir", z["X0"]),
                                                    ("tahmini_satis", z["tahmini_satis"]),
                                                    ("beklenen_kalan", z["beklenen_kalan"]))) and all(x_esit)}
    kararlar = {kol: (_kayit_satiri(k, gun, o) or {}).get("oran") for kol, k in kosular.items()}
    return {"option_id": oid, "gun": _iso(_GUN0 + pd.Timedelta(np.timedelta64(gun, "D"))),
            "indirime_hafta": (gun - (indirim - (indirim + _GUN0.weekday()) % 7)) // 7,
            "satilabilir": ana["X0"], "talep": ana["talep"], "liste": liste, "kalinti": float(og.kalinti),
            "ust_kategori": ust, "epsler": satirlar, "dogrulama": dogrulama, "kol_kararlari": kararlar,
            "ogrenilen": og.kimlik()}


# ---------------------------------------------------------------------------
# Kollar
# ---------------------------------------------------------------------------


def _kosu_kaydi(ortam: oyun.Ortam, e: dict):
    dizin = motor._dizin(ortam.onbellek, e["ad"], e["anahtar"])
    return motor._oku_tembel(dizin, e["anahtar"]) if (dizin / "meta.json").is_file() else None


def _fiyat_yolu(kosu, w, oid: str, k: dict) -> list[dict]:
    f = kosu.tablo("fiyat", ["hafta_baslangic", "option_id", "hat", "indirim_orani"])
    f = f[(f["option_id"].astype(str) == oid) & (f["hat"].astype(str) == "normal")]
    h = pd.to_datetime(f["hafta_baslangic"]).dt.normalize()
    oran = dict(zip(h, f["indirim_orani"].astype(float)))
    i0, L, C = _pazartesi(k["indirim"]), _pazartesi(k["lansman"]), _t(k["cikis"])
    return [{"hafta": int((x - i0).days // 7), "oran": float(oran.get(x, 0.0))}
            for x in pd.date_range(L, C - pd.Timedelta(np.timedelta64(1, "D")), freq="7D")]


SONUC_SUTUNLARI = ("arz_adet", "satis_cikis", "satis_indirim", "cikis_kalan_magaza_adet", "cikis_kalan_depo_adet",
                   "olu_stok_adet", "ciro_sezon", "ciro_outlet", "markdown_tl", "arz_alis")


def kol_yollari(ortam: oyun.Ortam, kayit: dict, sahne: dict, kunyeler: dict) -> tuple[dict, dict, list]:
    """(kol → option → {fiyat yolu, sonuç, karar günü kaydı}, kol → tembel koşu, eksik kollar)."""
    kosular = kayit.get("kosular", {})
    w = motor.dunya(ortam.olcek)
    opt_ids = w.optionlar["option_id"].astype(str).to_numpy()
    sonuc, kayitlar, eksik = {}, {}, []
    for kol in (oyun.LUMODA, *oyun.YOL0_KOLLARI):
        ad = oyun.kosu_adi(0, kol) if kol == oyun.LUMODA else oyun.kosu_adi(0, kol, SEZON)
        e = kosular.get(ad)
        k = _kosu_kaydi(ortam, e) if e else None
        if e is None or k is None or e.get("olcum_kodu") != oyun.olcum_kodu():
            eksik.append(ad)
            continue
        tab = e["option_tablosu"][SEZON] if kol == oyun.LUMODA else e["option_tablosu"]
        t = pd.read_parquet(Path(ortam.cikti) / tab).set_index("option_id")
        kol_s = {}
        for rol, oid in sahne.items():
            kn = kunyeler[rol]
            yol = _fiyat_yolu(k, w, oid, kn)
            oranli = [r for r in yol if r["oran"] > 0]
            r = t.loc[oid]
            o = int(np.flatnonzero(opt_ids == oid)[0])
            kol_s[rol] = {"fiyat_yolu": yol, "ilk_indirim_hafta": oranli[0]["hafta"] if oranli else None,
                          "en_derin": max((x["oran"] for x in yol), default=0.0),
                          "sonuc": {c: float(r[c]) for c in SONUC_SUTUNLARI},
                          "karar_gunu_kaydi": None if kol == oyun.LUMODA else _kayit_satiri(k, _gun(kn["karar_gunu"]), o)}
            s = kol_s[rol]["sonuc"]
            s["ciro_toplam"] = s["ciro_sezon"] + s["ciro_outlet"]
            s["katki"] = s["ciro_toplam"] - s["arz_alis"]
            s["cikis_kalan_adet"] = s["cikis_kalan_magaza_adet"] + s["cikis_kalan_depo_adet"]
        sonuc[kol] = {"kosu": ad, "anahtar": e["anahtar"], "optionlar": kol_s}
        kayitlar[kol] = k
    return sonuc, kayitlar, eksik


def indirim_haftalari(ortam: oyun.Ortam, kayit: dict) -> dict:
    """kol → test sezonu → ilk oranlı haftanın dağılımı (option tablosundan; hafta indirim haftasına göre):
    `{"hafta": {"−8": n, ...}, "yok": n, "option": n}`. Kaydı ya da ölçümü eksik (kol, sezon) girmez."""
    kosular = kayit.get("kosular", {})
    out: dict = {}
    for kol in (oyun.LUMODA, *oyun.YOL0_KOLLARI):
        for z in sabitler.TEST_SEZONLARI:
            ad = oyun.kosu_adi(0, kol) if kol == oyun.LUMODA else oyun.kosu_adi(0, kol, z)
            e = kosular.get(ad)
            if e is None or e.get("olcum_kodu") != oyun.olcum_kodu():
                continue
            tab = e["option_tablosu"][z] if kol == oyun.LUMODA else e["option_tablosu"]
            yol = Path(ortam.cikti) / tab
            if not yol.is_file():
                continue
            t = pd.read_parquet(yol, columns=["ilk_indirim_gun", "indirim_haftasi_gun"])
            var = t["ilk_indirim_gun"].notna()
            h = ((t.loc[var, "ilk_indirim_gun"] - t.loc[var, "indirim_haftasi_gun"]) // 7).astype(int)
            out.setdefault(kol, {})[z] = {"hafta": {str(int(k)): int(v) for k, v in h.value_counts().sort_index().items()},
                                          "yok": int((~var).sum()), "option": int(len(t))}
    return out


def pazartesi_listesi(kosu, w, gun: int, n: int = LISTE_SATIRI) -> dict:
    """Kolun `gun` kaydı: karar veren option sayısı, oranı > 0 olanlar ve satılabilir stoğu en büyük `n` satır."""
    k = kosu.kayitlar["markdown"]
    r = k[k["gun"] == gun].copy()
    ids = w.optionlar["option_id"].astype(str).to_numpy()
    r["option_id"] = ids[r["option"].to_numpy(dtype=np.int64)]
    r = r.sort_values(["satilabilir", "option_id"], ascending=[False, True])
    return {"gun": _iso(_GUN0 + pd.Timedelta(np.timedelta64(int(gun), "D"))), "option": int(len(r)),
            "indirimli": int((r["oran"] > 0).sum()),
            "oranlar": {f"{x:.2f}": int(m) for x, m in r["oran"].round(4).value_counts().sort_index().items()},
            "satirlar": [{"option_id": x.option_id, "oran": float(x.oran), "tahmini_satis": float(x.tahmini_satis),
                          "satilabilir": float(x.satilabilir), "beklenen_kalan": float(x.beklenen_kalan)}
                         for x in r.head(n).itertuples()]}


# ---------------------------------------------------------------------------
# Kurulum
# ---------------------------------------------------------------------------


def kur(ortam: oyun.Ortam) -> dict:
    if not ortam.oyun_yolu.is_file():
        raise Eksik(f"{ortam.oyun_yolu} yok: önce python -m markdown.oyun izgara --blok yol0")
    kayit = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))
    h = simulasyon.hazirla(simulasyon.lumoda_adi(0), None, 0, ortam.olcek, parametreler={}, rpt_takvimi=None,
                           gun_sayisi=ortam.gun_sayisi)
    if not simulasyon.onbellekte_mi(h, ortam.onbellek):
        raise Eksik(f"yol 0 Lumoda koşusu ({h.ad}_{h.anahtar[:20]}) önbellekte yok: hikâye simülasyon başlatmaz")
    Y = oyun.Yol(0, ortam)
    lumoda = Y.lumoda
    with tempfile.TemporaryDirectory(prefix="markdown_hikaye_") as dizin:
        con, _ = Y._baglanti(Path(dizin))
        try:
            sahne = sahne_sec(con)
            tulumlar = {rol: tulum(con, sahne[rol]) for rol in ("cok", "az")}
            gm = gomlek(con, sahne["gomlek"])
        finally:
            con.close()
    kunyeler = {**tulumlar, "gomlek": gm}
    kollar, kosular, eksik = kol_yollari(ortam, kayit, sahne, kunyeler)
    if kosular.get("opt") is None:
        raise Eksik("opt_SS25 koşusu önbellekte ya da oyun.json'da bugünkü ölçüm koduyla yok")
    w = Y.w
    cok = tulumlar["cok"]
    I_gun = _gun(cok["indirim"])
    esn = esneklik_hesabi(Y, lumoda, {k: v for k, v in kosular.items() if k != oyun.LUMODA}, sahne["cok"])
    lumoda_bas = I_gun - LUMODA_ONCE_GUN
    i0 = I_gun - (I_gun + _GUN0.weekday()) % 7
    yollar_opt = kollar["opt"]["optionlar"]
    ilk_cok = yollar_opt["cok"]["ilk_indirim_hafta"]
    ders = {"cok_opt_ilk_indirim_hafta": ilk_cok, "lumoda_baslangic_hafta": (lumoda_bas - i0) // 7,
            "cok_lumoda_oncesi": ilk_cok is not None and i0 + 7 * ilk_cok < lumoda_bas,
            "cok_indirim_oncesi": ilk_cok is not None and ilk_cok < 0,
            "az_opt_indirdi": yollar_opt["az"]["ilk_indirim_hafta"] is not None,
            "az_opt_ilk_indirim_hafta": yollar_opt["az"]["ilk_indirim_hafta"]}
    liste = {"karar_gunu": pazartesi_listesi(kosular["opt"], w, _gun(cok["karar_gunu"])),
             "indirim_gunu": pazartesi_listesi(kosular["opt"], w, _gun(cok["indirim_pazartesi"]))}
    karar_penceresi = int(kaynak.karar_penceresi(w.optionlar, np.flatnonzero(
        w.optionlar["option_id"].astype(str).to_numpy() == sahne["cok"]), "serbest")[0])
    return {"surum": KAYIT_SURUMU, "kod": kod_ozeti(), "olcek": ortam.olcek, "sezon": SEZON, "sahne": sahne,
            "sahne_yedek": sahne != SAHNE, "lumoda_anahtar": lumoda.meta["anahtar"],
            "olcum_kodu": oyun.olcum_kodu(), "tulumlar": tulumlar, "gomlek": gm, "kollar": kollar,
            "eksik_kollar": eksik, "esneklik": esn, "ders": ders, "pazartesi_listesi": liste,
            "indirim_haftalari": indirim_haftalari(ortam, kayit),
            "karar_gunu_tutarli": _iso(_GUN0 + pd.Timedelta(np.timedelta64(karar_penceresi, "D"))) == cok["karar_gunu"]}


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


def hedef(ortam: oyun.Ortam) -> Path:
    return Path(ortam.cikti) / "hikaye.json"


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="python -m markdown.hikaye", description=__doc__.splitlines()[0])
    p.add_argument("--olcek", default="TAM", type=str.upper, choices=["TAM", "KUCUK"])
    a = p.parse_args(argv)
    o = oyun._ortam(a.olcek)
    ortam = oyun.Ortam(olcek=o.olcek, cikti=o.cikti, ilerleme=False)
    try:
        h = kur(ortam)
    except Eksik as e:
        print(f"Eksik: {e}", file=sys.stderr)
        return 1
    yol = hedef(ortam)
    yol.write_text(json.dumps(_jsonla(h), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    e = h["esneklik"]
    print(f"hikaye: sahne {h['sahne']}, eksik kol {h['eksik_kollar'] or 'yok'}, karar anı doğrulaması "
          f"{ {k: v['esit'] for k, v in e['dogrulama'].items()} }, ders {h['ders']} -> {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
