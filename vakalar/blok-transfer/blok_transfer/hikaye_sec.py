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

Kullanıcı sahnesi: tam hikâye birleşimi (kazak + S-M-L üçü de 0 + Trabzon + cadde) karar anında
veride yoktur (yukarıdaki huni `LookupError` mesajında basılır). Kullanıcı ölçüt merdiveninin
en yakın sahneleri arasından birini seçti: `KULLANICI_SECIMI`. `sec` ve CLI `zorla` verilmezse
onu kullanır; greedy VE MIP planı artık bu bloğu taşımıyorsa açık hata verir (sessiz geri düşme
yok). Ölçüt merdiveni `gevseyen`i hesaplar (seçilen sahnenin tutmadığı ölçütler) ve `--adaylar`
ile en yakın sahneleri listeler.

Yan roller (gevşek):

    ikinci_alici   aday kümesinde AYNI (verici, option) bloğuna aday öteki alıcılardan `w`'si
                   en yüksek olan (bölge fark etmez); `rakip_alici_sayisi` bu öteki alıcıların
                   sayısıdır (ağ problemi: aynı mal birden çok alıcıya aday)
    karsi_verici   aynı option'da, cover < verici cover eşiği (6) olanlar arasında en çok stoklu
                   mağaza (bölge fark etmez). Yoksa aynı alt kategorideki öteki AW25
                   option'larda en çok stoklu, cover < eşik İstanbul mağazası; o zaman
                   `karsi_option_id` hangi option olduğunu söyler ve `gevseyen`e
                   `karsi_verici_baska_option` yazılır

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
# Kullanıcının seçtiği sahne (2026-10-08): tam hikâye birleşimi karar anında veride yok; ölçüt
# merdiveninin en yakın sahneleri arasından bunu seçti (kazak, Malatya vericisi; hem greedy hem
# MIP bloğu taşıyor). (option_id, alıcı, verici).
KULLANICI_SECIMI = ("MDL0673-HAK", "M018", "M071")
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
    rakip_alici_sayisi: int = 0              # aynı (verici, option) bloğuna aday öteki alıcılar
    karsi_option_id: str | None = None       # karşı vericinin option'ı (genelde option_id)


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


def _yan_roller(a: pd.Series, urunler, hucre, cover, w, cover_esigi: float) -> dict:
    """Gevşek yan roller (modül açıklaması): ikinci alıcı, rakip sayısı, karşı verici."""
    opt, alici, verici = a["option_id"], a["alici"], a["verici"]

    # ikinci alıcı: aynı (verici, option) bloğuna aday öteki alıcılardan en yüksek w
    rakip = w[(w["verici"] == verici) & (w["option_id"] == opt) & (w["alici"] != alici)]
    rakip = rakip.groupby("alici", as_index=False)["w"].max()
    ikinci = (rakip.sort_values(["w", "alici"], ascending=[False, True]).iloc[0]["alici"]
              if len(rakip) else None)

    # karşı verici: cover < eşik, en çok stoklu; önce aynı option, yoksa aynı alt kategori
    c = cover.set_index(["magaza_id", "option_id"])["cover"]
    hh = hucre[hucre["toplam"].gt(0)].copy()
    hh["cover"] = [c.get((m, o)) for m, o in zip(hh["magaza_id"], hh["option_id"])]
    hh = hh[hh["cover"].lt(cover_esigi) & ~hh["magaza_id"].isin([alici, verici, ikinci])]

    def en_cok(df):
        return (df.sort_values(["toplam", "magaza_id", "option_id"],
                               ascending=[False, True, True]).iloc[0]) if len(df) else None

    karsi = en_cok(hh[hh["option_id"] == opt])
    baska = False
    if karsi is None:
        u = urunler.set_index("option_id")
        ayni = set(u.index[(u["alt_kategori"] == u.loc[opt, "alt_kategori"])
                           & (u["sezon_kodu"] == SEZON)]) - {opt}
        karsi = en_cok(hh[hh["option_id"].isin(ayni) & hh["magaza_id"].isin(a["istanbul"])])
        baska = karsi is not None
    return {"ikinci": ikinci, "rakip_sayisi": int(len(rakip)),
            "karsi": None if karsi is None else str(karsi["magaza_id"]),
            "karsi_option": None if karsi is None else str(karsi["option_id"]),
            "karsi_baska_option": baska}


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

    satir = satir.copy()
    satir["istanbul"] = set(magazalar.loc[magazalar["sehir"] == ALICI_SEHRI, "magaza_id"])
    y = _yan_roller(satir, urunler, hucre, cover, w, cover_esigi)
    if y["ikinci"] is None:
        gevseyen.append("ikinci_alici_yok")
    if y["karsi"] is None:
        gevseyen.append("karsi_verici_yok")
    elif y["karsi_baska_option"]:
        gevseyen.append("karsi_verici_baska_option")
    h = Hikaye(option_id=str(satir["option_id"]), model_adi=str(satir["model_adi"]),
               alici=str(satir["alici"]), verici=str(satir["verici"]), ikinci_alici=y["ikinci"],
               karsi_verici=y["karsi"], mip_de_tasiyor=bool(satir["mip_var"]), gevseyen=gevseyen,
               rakip_alici_sayisi=y["rakip_sayisi"], karsi_option_id=y["karsi_option"])
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


def varsayilan_secim(greedy: pd.DataFrame, mip: pd.DataFrame) -> tuple[str, str, str]:
    """`KULLANICI_SECIMI`; greedy VE MIP bloğu hâlâ taşımıyorsa `LookupError` (geri düşme yok)."""
    opt, alici, verici = KULLANICI_SECIMI
    eksik = [ad for ad, plan in (("greedy", greedy), ("mip", mip))
             if not ((plan["verici"].astype(str) == verici) & (plan["alici"].astype(str) == alici)
                     & (plan["option_id"].astype(str) == opt)).any()]
    if eksik:
        raise LookupError(f"KULLANICI_SECIMI {KULLANICI_SECIMI} artik su planlarda tasinmiyor: "
                          f"{', '.join(eksik)}. Kod ya da veri degisti; --adaylar en yakin "
                          "sahneleri listeler, --hikaye ile baska sahne secilir.")
    return KULLANICI_SECIMI


def yakin_adaylar(urunler, magazalar, stok, greedy, mip, kayip, n: int = 10) -> pd.DataFrame:
    """Planın bloklarını tutmadıkları ölçüt sayısına göre sıralar (en yakın sahneler):
    sayı artan, kategori önceliği, kayıp azalan, option_id. `tutmayan` ölçüt adlarıdır."""
    urunler = urunler.astype({"option_id": str})
    magazalar = magazalar.astype({"magaza_id": str})
    hucre = _hucreler(stok.astype({"magaza_id": str, "option_id": str}), urunler)
    t = _degerlendir(greedy, urunler, magazalar, hucre,
                     kayip.astype({"magaza_id": str, "option_id": str}), greedy, mip)
    tm = t.apply(_tutmayan, axis=1)
    t = t.assign(tutmayan=tm.map(", ".join), n_tutmayan=tm.map(len))
    t = t.sort_values(["n_tutmayan", "kategori_sira", "kayip", "option_id", "alici", "verici"],
                      ascending=[True, True, False, True, True, True], kind="stable")
    return t.head(n)[["option_id", "alt_kategori", "alici", "verici", "kayip", "w", "mip_var",
                      "n_tutmayan", "tutmayan"]].reset_index(drop=True)


def sec(con, karar: date, greedy, mip, kayip: pd.DataFrame,
        zorla: tuple[str, str, str] | None = None, p: Parametreler | None = None) -> Hikaye:
    """Hikâyeyi veriden seçer. `greedy` ve `mip` `boru_hatti`nin `Plan`ları; `kayip`
    `hazirla.oku_kayip` çıktısı (ham Basit satırları). `p` varsayılan model sabitleri.
    `zorla` yoksa `KULLANICI_SECIMI` (`varsayilan_secim` doğrular)."""
    p = p or Parametreler()
    if zorla is None:
        zorla = varsayilan_secim(greedy.hareketler, mip.hareketler)
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
    strr_hepsi = metrikler.strler(con, karar)
    evren = set(g["magazalar"]["magaza_id"])
    kt = olcum.kayip_tablosu(kayip, karar, p.olcum_hafta, evren, "kayip").astype(
        {"magaza_id": str, "urun_id": str})
    magaza = g["magazalar"].set_index("magaza_id")
    urun_onbellek: dict[str, pd.DataFrame] = {}

    def urunleri(opt):
        if opt not in urun_onbellek:
            urun_onbellek[opt] = con.execute(
                "select u.urun_id, u.beden, u.beden_sira, u.renk, u.liste_fiyati from urun u "
                "where u.option_id = ? order by u.beden_sira", [opt]).df()
        return urun_onbellek[opt]

    def rol(m, opt):
        urun = urunleri(opt)
        stok = g["stok"][(g["stok"]["option_id"] == opt) & (g["stok"]["magaza_id"] == m)]
        cv = g["cover"][(g["cover"]["option_id"] == opt) & (g["cover"]["magaza_id"] == m)]
        st = strr_hepsi[(strr_hepsi["option_id"] == opt) & (strr_hepsi["magaza_id"] == m)]
        s = stok.merge(urun[["urun_id", "beden"]], on="urun_id")
        adet = dict(zip(s["beden"], s["adet"].astype(int)))
        k = kt.merge(urun[["urun_id", "beden"]].astype(str), on="urun_id", how="inner")
        k = k[k["magaza_id"] == m]
        return {
            "magaza_id": m, "option_id": opt, "ad": magaza.loc[m, "ad"],
            "sehir": magaza.loc[m, "sehir"], "tip": magaza.loc[m, "tip"],
            "bedenler": {b: adet.get(b, 0) for b in urun["beden"]},
            "toplam": int(sum(adet.values())),
            "hiz_8h": _sozluk(cv["hiz"].iloc[0]) if len(cv) else 0.0,   # stoklu hücrelerde
            "cover": _sozluk(cv["cover"].iloc[0]) if len(cv) else p.buyuk_cover,
            "str": _sozluk(st["str_orani"].iloc[0]) if len(st) else None,
            "pencere_kaybi": int(k["kayip"].sum()),
            "kayip_beden": {b: int(x) for b, x in zip(k["beden"], k["kayip"])},
        }

    urun = urunleri(h.option_id)
    secili = g["urunler"].set_index("option_id").loc[h.option_id]
    sonuc = {
        "option": {"option_id": h.option_id, "model_adi": h.model_adi,
                   "alt_kategori": secili["alt_kategori"], "line": secili["line"],
                   "sezon_kodu": secili["sezon_kodu"], "renk": urun["renk"].iloc[0],
                   "liste_fiyati": _sozluk(urun["liste_fiyati"].iloc[0]),
                   "bedenler": list(urun["beden"])},
        "karar": karar.isoformat(), "mip_de_tasiyor": h.mip_de_tasiyor, "gevseyen": h.gevseyen,
        "rakip_alici_sayisi": h.rakip_alici_sayisi,
        "alici": rol(h.alici, h.option_id), "verici": rol(h.verici, h.option_id),
        "ikinci_alici": rol(h.ikinci_alici, h.option_id) if h.ikinci_alici else None,
        "karsi_verici": (rol(h.karsi_verici, h.karsi_option_id or h.option_id)
                         if h.karsi_verici else None),
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
        # aynı (verici, option) bloğuna aday alıcılar, w sırasıyla (ağ problemi kanıtı)
        w = g["w"][(g["w"]["verici"] == h.verici) & (g["w"]["option_id"] == h.option_id)]
        w = w.sort_values(["w", "alici"], ascending=[False, True]).head(5)
        sonuc["blok_alici_adaylari"] = [{"alici": a_, "w": float(x)}
                                        for a_, x in zip(w["alici"], w["w"])]
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
        print(f"\n{ad}: {r['ad']} ({r['magaza_id']}, {r['sehir']}, {r['tip']})  "
              f"option {r['option_id']}")
        print(f"  stok: {beden}  toplam {r['toplam']}")
        print(f"  hiz (8 hafta): {r['hiz_8h']:.2f}/hafta  cover: {r['cover']:.1f}  STR: {str_}")
        kb = "  ".join(f"{b}:{x}" for b, x in r["kayip_beden"].items()) or "-"
        print(f"  pencere kaybi (Basit): {r['pencere_kaybi']}  beden beden: {kb}")
    print(f"\nrakip alici sayisi (ayni verici+option blogunun ote adaylari): "
          f"{o['rakip_alici_sayisi']}")
    if o.get("blok_alici_adaylari"):
        print("blogun aday alicilari (w):",
              [(a["alici"], round(a["w"], 1)) for a in o["blok_alici_adaylari"]])


def main(argv: list[str] | None = None) -> dict:
    a = argparse.ArgumentParser(prog="python -m blok_transfer.hikaye_sec",
                                description=__doc__.split("\n")[0])
    a.add_argument("--hikaye", metavar="OPTION:ALICI:VERICI", default=None,
                   help=f"secimi gecersiz kilar (varsayilan KULLANICI_SECIMI {KULLANICI_SECIMI})")
    a.add_argument("--adaylar", action="store_true",
                   help="olcut merdivenine en yakin sahneleri listele")
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
    if zorla is None:
        zorla = varsayilan_secim(greedy.hareketler, mip.hareketler)
    if args.adaylar:
        ya = yakin_adaylar(girdi["urunler"], girdi["magazalar"], girdi["stok"],
                           greedy.hareketler, mip.hareketler, girdi["kayip"])
        print("olcut merdivenine en yakin sahneler (tutmayan olcut sayisina gore):")
        with pd.option_context("display.width", 220, "display.max_columns", 20):
            print(ya.to_string(index=False))
        print()
    h, _ = _sec_ic(greedy=greedy.hareketler, mip=mip.hareketler, zorla=zorla,
                   cover_esigi=p.verici_cover_esigi, **girdi)
    o = ozet(con, karar, h, kayip, greedy=greedy, mip=mip, p=p, girdi=girdi)
    _yaz(o)
    return o


if __name__ == "__main__":
    main()
