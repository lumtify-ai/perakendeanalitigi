"""Yazı 1'in sahnesi: referans plan üzerinden deterministik hikâye seçimi (spec §5).

`python -m blok_transfer.hikaye_sec [--hikaye OPTION:ALICI:VERICI]` karar anında
sahneyi basar. Sahne: İstanbul'daki bir cadde mağazasında kışlık bir örgünün S-M-L'si
tükenmiş, uçlar (XS, XL) duruyor (alıcı, Ali'nin); Trabzon'daki bir mağazada aynı
option'ın seti tam ve az satıyor (verici, Veli'nin); planlar bu bloğu bu vericiden bu
alıcıya taşıyor.

Ölçütler (gevşetme sırasında ve `gevseyen`de kullanılan kısa adlarıyla):

    urun            sezon `AW25`, hat Collection ya da NOS, 5 bedenli      (gevşemez)
    alt_kategori    alt kategori üst giyim; öncelik Kazak > Sweatshirt > diğer üst giyim
    alici_istanbul  alıcı `sehir = İstanbul`                               (gevşemez)
    cadde           alıcı `tip = Cadde`
    alici_kirik     (alıcı, option) toplam stok > 0 ve S-M-L (sıra 2-4) üçü de 0 (gevşemez)
    trabzon         verici `sehir = Trabzon`; gevşerse İstanbul dışı herhangi bir mağaza
    verici_tam_set  vericide 5 bedenin hepsi > 0                           (gevşemez)
    greedy_hareketi açgözlü planda (verici, alıcı, option) hareketi var     (gevşemez)

Sıralama: önce alt kategori önceliği (Kazak, Sweatshirt, diğer üst giyim; yalnız
`alt_kategori` gevşerse üst giyim dışı en sona), sonra alıcı hücrenin ölçüm penceresindeki
kaybı (Basit, option toplamı) büyükten küçüğe, eşitlikte option_id, alıcı, planın
hareket değeri (`w`) büyükten küçüğe, verici.

Gevşetme: sıkı aramada aday yoksa TEK ölçüt (sırayla `alt_kategori`, `cadde`, `trabzon`),
sonra ikili (alt_kategori+cadde, alt_kategori+trabzon, cadde+trabzon). Aday veren ilk
gevşetme seçilir; `gevseyen` adayın gerçekte tutmadığı ölçütlerdir. Hiçbiri vermezse
`LookupError`. Gevşemez ölçütler hikâyenin kendisidir: kırık alıcı, tam setli verici ve
planın taşıdığı blok olmadan sahne yoktur.

Yan roller:

    ikinci_alici   aynı option'da kırık (toplam > 0, S-M-L'den biri 0) başka bir İstanbul
                   mağazası, ona en yüksek `w`'lu aday verici AYNI vericidir (ağ problemi:
                   iki alıcı aynı malı ister). Birden çoksa penceredeki kaybı en büyük olan.
    karsi_verici   aynı option'da en çok stoklu, cover < verici cover eşiği (6) olan İstanbul
                   mağazası (çok stok var ama hızlı satıyor: vericilik hak değil, bedel olur)

Bulunamazsa `None`; `gevseyen`e `ikinci_alici_yok` / `karsi_verici_yok` yazılır.

`--hikaye OPTION:ALICI:VERICI` seçimi geçersiz kılar; `gevseyen` o adayın tutmadığı
bütün ölçütleri (gevşemezler dahil) listeler. Planlar `cikti/planlar` önbelleğinden okunur.
"""

import argparse
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path

import pandas as pd

from . import hazirla, olcum
from .cekirdek import adaylar as adaylar_mod
from .cekirdek import metrikler, terazi, veri
from .cekirdek.parametreler import Parametreler
from .degerlendirme import boru_hatti

VARSAYILAN_CIKTI = Path(__file__).resolve().parents[1] / "cikti"

SEZON = "AW25"
HATLAR = ("Collection", "NOS")
BEDEN_SAYISI = 5
KATEGORI_ONCELIGI = ("Kazak", "Sweatshirt")
UST_GIYIM = ("Kazak", "Sweatshirt", "Mont", "Ceket", "Gömlek", "Bluz", "Tişört", "Trençkot")
ALICI_SEHRI = "İstanbul"
VERICI_SEHRI = "Trabzon"
ALICI_TIPI = "Cadde"
ORTA_BEDENLER = (2, 3, 4)            # S-M-L
GEVSEK_OLCUTLER = ("alt_kategori", "cadde", "trabzon")     # gevşetme sırası
GEVSEMEZ = ("urun", "alici_istanbul", "alici_kirik", "verici_bolge", "verici_tam_set",
            "greedy_hareketi")
SIRA_DISI = len(UST_GIYIM)           # üst giyim dışı (yalnız alt_kategori gevşerse)


@dataclass
class Hikaye:
    option_id: str
    model_adi: str
    alici: str
    verici: str
    ikinci_alici: str | None
    karsi_verici: str | None
    mip_de_tasiyor: bool
    gevseyen: list[str]


# ------------------------------------------------------------- saf ölçüt mantığı

def _kategori_sirasi(alt: pd.Series) -> pd.Series:
    """Kazak 0, Sweatshirt 1, diğer üst giyim 2, üst giyim dışı 3."""
    sira = {k: i for i, k in enumerate(KATEGORI_ONCELIGI)}
    diger = len(KATEGORI_ONCELIGI)
    sira.update({k: diger for k in UST_GIYIM if k not in sira})
    return alt.map(sira).fillna(diger + 1).astype(int)


def _hucreler(stok: pd.DataFrame, urunler: pd.DataFrame) -> pd.DataFrame:
    """(mağaza, option) başına stok özeti: toplam, tam (bütün bedenler > 0),
    orta_sifir (S-M-L üçü de 0), orta_eksik (S-M-L'den biri 0). Satırı olmayan beden 0."""
    if not len(stok):
        return pd.DataFrame(columns=["magaza_id", "option_id", "toplam", "tam", "orta_sifir",
                                     "orta_eksik"])
    p = stok.pivot_table(index=["magaza_id", "option_id"], columns="beden_sira", values="adet",
                         aggfunc="sum", fill_value=0)
    orta = p.reindex(columns=list(ORTA_BEDENLER), fill_value=0)
    h = pd.DataFrame({"toplam": p.sum(axis=1), "pozitif": (p > 0).sum(axis=1),
                      "orta_sifir": (orta == 0).all(axis=1), "orta_eksik": (orta == 0).any(axis=1)})
    h = h.reset_index().merge(urunler[["option_id", "n_beden"]], on="option_id", how="left")
    h["tam"] = h["pozitif"] == h["n_beden"]
    return h.drop(columns=["pozitif", "n_beden"])


def _degerlendir(blok: pd.DataFrame, urunler, magazalar, hucre, kayip, greedy, mip) -> pd.DataFrame:
    """`blok` (verici, alici, option_id) satırlarına özellikler ve ölçüt bayrakları ekler."""
    a = blok[["verici", "alici", "option_id"]].drop_duplicates().astype(str)
    a = a.merge(urunler[["option_id", "model_adi", "alt_kategori", "line", "sezon_kodu", "n_beden"]],
                on="option_id", how="left")
    m = magazalar[["magaza_id", "sehir", "tip"]]
    a = a.merge(m.rename(columns={"magaza_id": "alici", "sehir": "alici_sehir", "tip": "alici_tip"}),
                on="alici", how="left")
    a = a.merge(m.rename(columns={"magaza_id": "verici", "sehir": "verici_sehir",
                                  "tip": "verici_tip"}), on="verici", how="left")
    ah = hucre[["magaza_id", "option_id", "orta_sifir", "toplam"]].rename(
        columns={"magaza_id": "alici", "orta_sifir": "alici_orta_sifir", "toplam": "alici_toplam"})
    vh = hucre[["magaza_id", "option_id", "tam"]].rename(
        columns={"magaza_id": "verici", "tam": "verici_tam"})
    a = a.merge(ah, on=["alici", "option_id"], how="left")
    a = a.merge(vh, on=["verici", "option_id"], how="left")
    a = a.merge(kayip.rename(columns={"magaza_id": "alici"}), on=["alici", "option_id"], how="left")
    a["kayip"] = a["kayip"].fillna(0.0)
    w = greedy[["verici", "alici", "option_id", "w"]].astype({"verici": str, "alici": str,
                                                                "option_id": str})
    a = a.merge(w.groupby(["verici", "alici", "option_id"], as_index=False)["w"].sum(),
                on=["verici", "alici", "option_id"], how="left")
    a["greedy_var"] = a["w"].notna()
    a["w"] = a["w"].fillna(0.0)
    mip_anahtar = set(zip(mip["verici"].astype(str), mip["alici"].astype(str),
                          mip["option_id"].astype(str)))
    a["mip_var"] = [(v, al, o) in mip_anahtar for v, al, o in zip(a.verici, a.alici, a.option_id)]
    a["kategori_sira"] = _kategori_sirasi(a["alt_kategori"])

    a["ok_urun"] = (a["sezon_kodu"] == SEZON) & a["line"].isin(HATLAR) & (a["n_beden"] == BEDEN_SAYISI)
    a["ok_alt_kategori"] = a["alt_kategori"].isin(UST_GIYIM)
    a["ok_alici_istanbul"] = a["alici_sehir"] == ALICI_SEHRI
    a["ok_cadde"] = a["alici_tip"] == ALICI_TIPI
    a["ok_alici_kirik"] = (a["alici_orta_sifir"].eq(True)
                           & (a["alici_toplam"].fillna(0) > 0))
    a["ok_trabzon"] = a["verici_sehir"] == VERICI_SEHRI
    a["ok_verici_bolge"] = a["verici_sehir"].notna() & (a["verici_sehir"] != ALICI_SEHRI)
    a["ok_verici_tam_set"] = a["verici_tam"].eq(True)
    a["ok_greedy_hareketi"] = a["greedy_var"]
    return a


def _tutmayan(satir: pd.Series) -> list[str]:
    """Adayın tutmadığı ölçütler: gevşekler sırayla, sonra gevşemezler (`GEVSEMEZ` sırası)."""
    return [ad for ad in (*GEVSEK_OLCUTLER, *GEVSEMEZ) if not satir[f"ok_{ad}"]]


def _huni(tablo: pd.DataFrame) -> list[tuple[str, int]]:
    """Planın bloklarına ölçütleri sırayla uygulayınca kalan sayı (bulunamayan arama için tanı)."""
    kalan = pd.Series(True, index=tablo.index)
    sonuc = [("plan_bloklari", int(len(tablo)))]
    for ad in ("urun", "alici_istanbul", "alici_kirik", "verici_bolge", "verici_tam_set",
               *GEVSEK_OLCUTLER):
        kalan &= tablo[f"ok_{ad}"]
        sonuc.append((ad, int(kalan.sum())))
    return sonuc


def _huni_metni(huni: list[tuple[str, int]]) -> str:
    return " > ".join(f"{ad} {n}" for ad, n in huni)


def _yan_roller(a: pd.Series, magazalar, hucre, kayip, cover, w,
                cover_esigi: float) -> tuple[str | None, str | None]:
    opt, alici, verici = a["option_id"], a["alici"], a["verici"]
    istanbul = set(magazalar.loc[magazalar["sehir"] == ALICI_SEHRI, "magaza_id"].astype(str))
    h = hucre[(hucre["option_id"] == opt) & hucre["magaza_id"].isin(istanbul)
              & (hucre["magaza_id"] != alici)]

    # ikinci alıcı: kırık, ona en yüksek w'lu aday verici aynı verici; en çok kaybı olan
    kayip_opt = kayip[kayip["option_id"] == opt].set_index("magaza_id")["kayip"]
    adaylar = []
    for mag in h.loc[h["toplam"].gt(0) & h["orta_eksik"], "magaza_id"]:
        o = w[(w["alici"] == mag) & (w["option_id"] == opt)]
        if len(o) and o.sort_values(["w", "verici"], ascending=[False, True]).iloc[0]["verici"] == verici:
            adaylar.append((-float(kayip_opt.get(mag, 0.0)), mag))
    ikinci = min(adaylar)[1] if adaylar else None

    # karşı verici: en çok stoklu, cover < eşik
    c = cover[cover["option_id"] == opt].set_index("magaza_id")["cover"]
    karsi = h[h["toplam"].gt(0) & (h["magaza_id"] != ikinci)].copy()
    karsi = karsi[karsi["magaza_id"].map(c).lt(cover_esigi)]
    karsi_id = (karsi.sort_values(["toplam", "magaza_id"], ascending=[False, True])
                .iloc[0]["magaza_id"]) if len(karsi) else None
    return ikinci, karsi_id


def _sec_ic(urunler, magazalar, stok, greedy, mip, kayip, cover, w, zorla=None,
            cover_esigi: float = 6.0) -> tuple[Hikaye, pd.DataFrame]:
    """(hikâye, ilgili gevşetmenin sıralı aday tablosu). Tablo `zorla` verilmişse tek satır."""
    urunler = urunler.astype({"option_id": str})
    magazalar = magazalar.astype({"magaza_id": str})
    stok = stok.astype({"magaza_id": str, "option_id": str})
    kayip = kayip.astype({"magaza_id": str, "option_id": str})
    cover = cover.astype({"magaza_id": str, "option_id": str})
    w = w.astype({"verici": str, "alici": str, "option_id": str})
    hucre = _hucreler(stok, urunler)

    if zorla is not None:
        opt, alici, verici = (str(x) for x in zorla)
        if opt not in set(urunler["option_id"]):
            raise LookupError(f"--hikaye: bilinmeyen option {opt}")
        for m in (alici, verici):
            if m not in set(magazalar["magaza_id"]):
                raise LookupError(f"--hikaye: bilinmeyen mağaza {m}")
        blok = pd.DataFrame([(verici, alici, opt)], columns=["verici", "alici", "option_id"])
        tablo = _degerlendir(blok, urunler, magazalar, hucre, kayip, greedy, mip)
        satir = tablo.iloc[0]
        gevseyen = _tutmayan(satir)
    else:
        tablo = tablo_hepsi = _degerlendir(greedy, urunler, magazalar, hucre, kayip, greedy, mip)
        sabit = tablo[["ok_urun", "ok_alici_istanbul", "ok_alici_kirik", "ok_verici_bolge",
                       "ok_verici_tam_set", "ok_greedy_hareketi"]].all(axis=1)
        tablo = tablo[sabit]
        gevsetmeler = [(), *[(g,) for g in GEVSEK_OLCUTLER], *combinations(GEVSEK_OLCUTLER, 2)]
        secilen = None
        for gevset in gevsetmeler:
            ok = pd.Series(True, index=tablo.index)
            for ad in GEVSEK_OLCUTLER:
                if ad not in gevset:
                    ok &= tablo[f"ok_{ad}"]
            if ok.any():
                secilen = tablo[ok].sort_values(
                    ["kategori_sira", "kayip", "option_id", "alici", "w", "verici"],
                    ascending=[True, False, True, True, False, True], kind="stable")
                break
        if secilen is None:
            raise LookupError(
                "hikaye icin aday yok: en cok iki olcut gevsetilse de (alt_kategori, cadde, "
                "trabzon) planin tasidigi hicbir blok sahneyi kurmuyor. Olcutler sirayla "
                "uygulandiginda kalan blok sayisi: " + _huni_metni(_huni(tablo_hepsi)))
        tablo, satir = secilen, secilen.iloc[0]
        gevseyen = _tutmayan(satir)

    ikinci, karsi = _yan_roller(satir, magazalar, hucre, kayip, cover, w,
                                cover_esigi)
    if ikinci is None:
        gevseyen.append("ikinci_alici_yok")
    if karsi is None:
        gevseyen.append("karsi_verici_yok")
    h = Hikaye(option_id=str(satir["option_id"]), model_adi=str(satir["model_adi"]),
               alici=str(satir["alici"]), verici=str(satir["verici"]), ikinci_alici=ikinci,
               karsi_verici=karsi, mip_de_tasiyor=bool(satir["mip_var"]), gevseyen=gevseyen)
    return h, tablo


def sec_tablolardan(urunler: pd.DataFrame, magazalar: pd.DataFrame, stok: pd.DataFrame,
                    greedy: pd.DataFrame, mip: pd.DataFrame, kayip: pd.DataFrame,
                    cover: pd.DataFrame, w: pd.DataFrame,
                    zorla: tuple[str, str, str] | None = None,
                    cover_esigi: float = 6.0) -> Hikaye:
    """Ölçüt mantığı, yalnız DataFrame girdileriyle (`sec` bunları veriden toplar).

    urunler   option_id, model_adi, alt_kategori, line, sezon_kodu, n_beden
    magazalar magaza_id, ad, sehir, tip (evren mağazaları)
    stok      karar günü SKU stoğu: magaza_id, option_id, urun_id, beden_sira, adet
    greedy    açgözlü planın hareketleri: verici, alici, option_id, adet, w
    mip       MIP planın hareketleri (aynı sütunlar)
    kayip     alıcı hücrenin pencere kaybı: magaza_id, option_id, kayip (option toplamı)
    cover     magaza_id, option_id, cover
    w         aday vericilerin net değeri: verici, alici, option_id, w
    zorla     (option_id, alıcı, verici): seçimi geçersiz kılar"""
    return _sec_ic(urunler, magazalar, stok, greedy, mip, kayip, cover, w, zorla, cover_esigi)[0]


# ----------------------------------------------------------------- veri toplama

def _girdiler(con, karar: date, p: Parametreler, kayip: pd.DataFrame) -> dict:
    """`sec_tablolardan`ın veriye bağlı girdileri (planlar hariç)."""
    veri.gorunumler(con, karar)
    urunler = con.execute(
        "select option_id, any_value(model_adi) as model_adi, any_value(alt_kategori) as "
        "alt_kategori, any_value(line) as line, any_value(sezon_kodu) as sezon_kodu, "
        "count(*) as n_beden from urun group by 1").df()
    magazalar = con.execute(
        "select m.magaza_id, m.ad, m.sehir, m.tip from magaza m join bt_magaza b using (magaza_id)"
    ).df()
    stok = con.execute(
        "select s.magaza_id, u.option_id, s.urun_id, u.beden_sira, s.adet "
        "from bt_stok s join urun u using (urun_id) where s.tarih = ?", [karar]).df()
    return {
        "urunler": urunler, "magazalar": magazalar, "stok": stok,
        "kayip": _pencere_kayip(con, kayip, karar, p, set(magazalar["magaza_id"])),
        "cover": metrikler.coverlar(con, karar, p)[["magaza_id", "option_id", "hiz", "cover"]],
        "w": terazi.agirliklandir(adaylar_mod.uret(con, karar, p), p)[
            ["verici", "alici", "option_id", "w"]],
    }


def _pencere_kayip(con, kayip: pd.DataFrame, karar: date, p: Parametreler,
                   evren: set[str]) -> pd.DataFrame:
    """Ham `kayip_basit` satırlarından pencere içi hücre kaybı, option toplamı:
    `[magaza_id, option_id, kayip]`."""
    t = olcum.kayip_tablosu(kayip, karar, p.olcum_hafta, evren, "kayip")
    eslem = con.execute("select urun_id, option_id from urun").df().astype(str)
    t = t.astype({"urun_id": str}).merge(eslem, on="urun_id", how="left")
    return (t.groupby(["magaza_id", "option_id"], as_index=False)["kayip"].sum()
            .astype({"magaza_id": str}))


def sec(con, karar: date, greedy, mip, kayip: pd.DataFrame,
        zorla: tuple[str, str, str] | None = None, p: Parametreler | None = None) -> Hikaye:
    """Hikâyeyi veriden seçer. `greedy` ve `mip` `boru_hatti`nin `Plan`ları; `kayip`
    `hazirla.oku_kayip` çıktısı (ham Basit satırları). `p` varsayılan model sabitleri."""
    p = p or Parametreler()
    g = _girdiler(con, karar, p, kayip)
    return sec_tablolardan(greedy=greedy.hareketler, mip=mip.hareketler, zorla=zorla,
                           cover_esigi=p.verici_cover_esigi, **g)


# ------------------------------------------------------------------------ özet

def _sozluk(v):
    """numpy/pandas skalerleri düz Python'a."""
    if hasattr(v, "item"):
        return v.item()
    return v


def ozet(con, karar: date, h: Hikaye, kayip: pd.DataFrame, greedy=None, mip=None,
         p: Parametreler | None = None, girdi: dict | None = None) -> dict:
    """Rapor için sahne sayıları.

    `option`: kimlik ve ürün özellikleri; her rol (`alici`, `verici`, `ikinci_alici`,
    `karsi_verici`) için: mağaza adı/şehir/tip, beden beden stok, toplam, 8 haftalık hız,
    cover, STR, penceredeki kayıp (toplam ve beden beden). `hareket`: planların bu bloğa
    ve ikinci alıcıya verdiği adet ve `w` (planlar verildiyse). `girdi`: `_girdiler`in çıktısı
    (verilmezse toplanır; veri sorguları pahalıdır, CLI aynısını yeniden kullanır)."""
    p = p or Parametreler()
    g = girdi if girdi is not None else _girdiler(con, karar, p, kayip)
    urun = con.execute(
        "select u.urun_id, u.beden, u.beden_sira, u.renk, u.liste_fiyati from urun u "
        "where u.option_id = ? order by u.beden_sira", [h.option_id]).df()
    secili = g["urunler"].set_index("option_id").loc[h.option_id]
    stok = g["stok"][g["stok"]["option_id"] == h.option_id]
    cv = g["cover"][g["cover"]["option_id"] == h.option_id].set_index("magaza_id")
    hiz, cover = cv["hiz"], cv["cover"]            # stoklu hücreler; hız yoksa 0
    strr = metrikler.strler(con, karar)
    strr = strr[strr["option_id"] == h.option_id].set_index("magaza_id")["str_orani"]
    evren = set(g["magazalar"]["magaza_id"])
    kt = olcum.kayip_tablosu(kayip, karar, p.olcum_hafta, evren, "kayip").astype({"magaza_id": str,
                                                                                 "urun_id": str})
    kt = kt.merge(urun[["urun_id", "beden"]].astype(str), on="urun_id", how="inner")
    magaza = g["magazalar"].set_index("magaza_id")

    def rol(m):
        s = stok[stok["magaza_id"] == m].merge(urun[["urun_id", "beden"]], on="urun_id")
        adet = dict(zip(s["beden"], s["adet"].astype(int)))
        k = kt[kt["magaza_id"] == m]
        return {
            "magaza_id": m, "ad": magaza.loc[m, "ad"], "sehir": magaza.loc[m, "sehir"],
            "tip": magaza.loc[m, "tip"],
            "bedenler": {b: adet.get(b, 0) for b in urun["beden"]},
            "toplam": int(sum(adet.values())),
            "hiz_8h": _sozluk(hiz.get(m, 0.0)),
            "cover": _sozluk(cover.get(m, p.buyuk_cover)),
            "str": _sozluk(strr.get(m)) if m in strr.index else None,
            "pencere_kaybi": int(k["kayip"].sum()),
            "kayip_beden": {b: int(x) for b, x in zip(k["beden"], k["kayip"])},
        }

    sonuc = {
        "option": {"option_id": h.option_id, "model_adi": h.model_adi,
                   "alt_kategori": secili["alt_kategori"], "line": secili["line"],
                   "sezon_kodu": secili["sezon_kodu"], "renk": urun["renk"].iloc[0],
                   "liste_fiyati": _sozluk(urun["liste_fiyati"].iloc[0]),
                   "bedenler": list(urun["beden"])},
        "karar": karar.isoformat(), "mip_de_tasiyor": h.mip_de_tasiyor, "gevseyen": h.gevseyen,
        "alici": rol(h.alici), "verici": rol(h.verici),
        "ikinci_alici": rol(h.ikinci_alici) if h.ikinci_alici else None,
        "karsi_verici": rol(h.karsi_verici) if h.karsi_verici else None,
    }
    if greedy is not None and mip is not None:
        def hareket(plan, verici, alici):
            r = plan.hareketler
            r = r[(r["verici"].astype(str) == verici) & (r["alici"].astype(str) == alici)
                  & (r["option_id"].astype(str) == h.option_id)]
            return ({"adet": int(r["adet"].sum()), "w": float(r["w"].sum())} if len(r) else None)
        sonuc["hareket"] = {
            "greedy": hareket(greedy, h.verici, h.alici), "mip": hareket(mip, h.verici, h.alici),
            "greedy_ikinci": hareket(greedy, h.verici, h.ikinci_alici) if h.ikinci_alici else None,
            "mip_ikinci": hareket(mip, h.verici, h.ikinci_alici) if h.ikinci_alici else None}
        # ikinci alıcının aday vericileri, w sırasıyla (ağ problemi kanıtı)
        if h.ikinci_alici:
            w = g["w"][(g["w"]["alici"] == h.ikinci_alici) & (g["w"]["option_id"] == h.option_id)]
            w = w.sort_values(["w", "verici"], ascending=[False, True]).head(3)
            sonuc["ikinci_alici_adaylari"] = [{"verici": v, "w": float(x)}
                                              for v, x in zip(w["verici"], w["w"])]
    return sonuc


# ------------------------------------------------------------------------- CLI

def hikaye_ayristir(metin: str) -> tuple[str, str, str]:
    """`OPTION:ALICI:VERICI` → (option_id, alıcı, verici)."""
    parca = metin.split(":")
    if len(parca) != 3 or not all(parca):
        raise ValueError(f"--hikaye OPTION:ALICI:VERICI biçiminde olmalı, verilen: {metin!r}")
    return parca[0], parca[1], parca[2]


def _yaz(o: dict) -> None:
    op = o["option"]
    print(f"option: {op['option_id']}  {op['model_adi']}  ({op['alt_kategori']}, {op['line']}, "
          f"{op['sezon_kodu']}, {op['renk']}, liste {op['liste_fiyati']:.0f} TL)")
    print(f"karar anı: {o['karar']}  |  MIP de tasiyor: {o['mip_de_tasiyor']}  |  "
          f"gevseyen: {o['gevseyen'] or 'yok (tum olcutler saglandi)'}")
    bedenler = op["bedenler"]
    print("hareket:", o.get("hareket"))
    for ad in ("alici", "verici", "ikinci_alici", "karsi_verici"):
        r = o[ad]
        if r is None:
            print(f"\n{ad}: yok")
            continue
        beden = "  ".join(f"{b}:{r['bedenler'][b]}" for b in bedenler)
        str_ = f"{r['str']:.2f}" if r["str"] is not None else "-"
        print(f"\n{ad}: {r['ad']} ({r['magaza_id']}, {r['sehir']}, {r['tip']})")
        print(f"  stok: {beden}  toplam {r['toplam']}")
        print(f"  hiz (8 hafta): {r['hiz_8h']:.2f}/hafta  cover: {r['cover']:.1f}  STR: {str_}")
        kb = "  ".join(f"{b}:{x}" for b, x in r["kayip_beden"].items()) or "-"
        print(f"  pencere kaybi (Basit): {r['pencere_kaybi']}  beden beden: {kb}")
    if o.get("ikinci_alici_adaylari"):
        print("\nikinci alicinin aday vericileri (w):",
              [(a["verici"], round(a["w"], 1)) for a in o["ikinci_alici_adaylari"]])


def main(argv: list[str] | None = None) -> dict:
    a = argparse.ArgumentParser(prog="python -m blok_transfer.hikaye_sec",
                                description=__doc__.split("\n")[0])
    a.add_argument("--hikaye", metavar="OPTION:ALICI:VERICI", default=None,
                   help="secimi gecersiz kilar (ornek OPT123:M010:M058)")
    a.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI,
                   help=f"hazirla ciktilari (varsayilan {VARSAYILAN_CIKTI})")
    a.add_argument("--db", type=Path, default=None, help="v4 DuckDB dosyasi (varsayilan: ortak yol)")
    args = a.parse_args(argv)
    zorla = hikaye_ayristir(args.hikaye) if args.hikaye else None

    con = veri.baglan(args.db)
    p = Parametreler()
    karar = veri.karar_ani(con)
    veri.gorunumler(con, karar)
    greedy, _ = boru_hatti(con, karar, p, "greedy", onbellek=args.cikti / "planlar")
    mip, _ = boru_hatti(con, karar, p, "mip", onbellek=args.cikti / "planlar")
    kayip = hazirla.oku_kayip(args.cikti, con, karar, p.olcum_hafta)

    girdi = _girdiler(con, karar, p, kayip)
    h, tablo = _sec_ic(greedy=greedy.hareketler, mip=mip.hareketler, zorla=zorla,
                       cover_esigi=p.verici_cover_esigi, **girdi)
    if zorla is None:
        goster = ["option_id", "model_adi", "alt_kategori", "alici", "verici", "kayip", "w",
                  "mip_var"]
        print(f"gevsetmeden sonra aday sayisi: {len(tablo)}; ilk 10:")
        with pd.option_context("display.width", 200, "display.max_columns", 20):
            print(tablo.head(10)[goster].to_string(index=False))
        print()
    o = ozet(con, karar, h, kayip, greedy=greedy, mip=mip, p=p, girdi=girdi)
    _yaz(o)
    return o


if __name__ == "__main__":
    main()
