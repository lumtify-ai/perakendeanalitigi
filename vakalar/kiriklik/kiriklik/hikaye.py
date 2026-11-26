"""Hikâye sahnesi (tasarım §0 K14; Transfer dizisinin 1. yazısı): `cikti/hikaye.json`.

    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m kiriklik.hikaye [--olcek KUCUK]

Bu modül ölçüm tarafındadır (`simulasyon.KOSU_DISI`): simülasyon koşmaz, plan kurmaz. Yol 0'ın `kural` AW24 koşusu
ve yol 0 Lumoda koşusu önbellekte, `kural` planı plan önbelleğinde, koşu `oyun.json`'da bugünkü ölçüm koduyla geçerli
ölçülmüş olmalıdır (yoksa `Eksik`, çıkış 1). Koşular `oyun.json`'daki anahtarlarıyla salt okunur açılır (önbellekte
hiçbir şey silinmez ya da yazılmaz). Tarihler ve kesitler `olcutler`'in tanımıdır (`olcutler._Kapsam`).

**Adaylar** (`adaylar`): planın her alıcı çifti (alıcı mağaza, option): alınan adet, vericiler ve şehirleri, karar
sabahı kırık bedenleri (alıcının karar fotoğrafında stoğu sıfır bedenler) ve onların karar günü depo fotoğrafı
(`depo_stok`), Lumoda koşusunda indirim gününden önceki son pazartesi fotoğrafında çiftin kırık olup olmadığı (stoklu
ve en az bir bedeni sıfır). Süzgeçler (`SEVIYELER`, sırayla gevşer; seçilen seviye kaydedilir): `tam` alıcı İstanbul'da
(Ali), İstanbul dışında (Veli, Anadolu) en az üç verici; `iki_verici` aynısı en az iki vericiyle; `sehir_disi` alıcı
herhangi bir şehirde, alıcının şehri dışında en az iki verici. Her seviyede ayrıca: kırık bedenlerin hepsinin karar
günü depo stoğu sıfır ve alıcı Lumoda'da indirime kırık giriyor. Sıra: alınan adet büyükten küçüğe, eşitlikte
option_id, sonra alıcı. İlk aday sahnedir. KÜÇÜK dünyada (17 fiziksel mağaza, birkaç alıcı) bu seviyelerin hepsi boş
kalabilir; yalnız orada son seviye `kucuk_yedek` (alıcının şehri dışında en az bir verici) denenir (geliştirme; rapor
KÜÇÜK'ü her zaman taslak basar).

**Sahne** (`sahne`): option (model adı, renk, alt kategori, liste fiyatı), alıcı (ad, şehir), vericiler (ad, şehir,
adet, bedenler), karar sabahı alıcının beden stoğu ve kırık bedenleri (depo stoğuyla), alınan adet (bedene göre),
en erken ve en geç varış (karardan gün), alıcının indirim gününe kadar satışı `[karar, indirim)` pozitif adet: alınan
SKU'larda ve option'ın bütün bedenlerinde, kural koşusunda ve Lumoda'da (aynı hücreler), sahanın ölçüsüyle Σ min(varıştan
indirime satış, alınan); indirim öncesi fotoğrafta alıcı çiftin bedenleri iki koşuda (kırık mı).

**Verici başına** (Ruling R38; `varis_gunleri`, `lumoda_ilk_satis`): `varis_gun` kolun karar günü `elle_transfer` satırından
(verici → alıcı, bu option'ın SKU'ları; karardan gün); `lumoda` verilen her beden için Lumoda koşusunda o vericinin o
hücresinin `[karar, çıkış)` pozitif satış adedi, ilk satışın karardan günü ve o günün birim fiyatı: transfer yapılmasaydı o
beden vericide satacak mıydı.

**Sahne bütçesi** (`sahne_butcesi`, `butce`): kol − Lumoda, `[karar, çıkış)` net adet ve TL (iade dahil), aynı hücreler:
`alici` alıcının aldığı SKU'lar, `vericiler` her vericinin verdiği SKU'lar, `net` ikisinin toplamı. **Kargo** (`rota_kargosu`,
`kargo`): sahnenin verici rotaları × rota başı kargo, düşük ve orta maliyet; rotanın başka option taşıyıp taşımadığına
bakılmaz (rota tamamen bu sahneye yazılır).

`kod`: bu dosya, vakanın simülasyon kodu özeti ve ölçüm kodu özeti; rapor eski kaydı reddeder.
"""

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from allocation import motor

from kiriklik import olcu, olcutler, oyun, sabitler, simulasyon

SEZON = "AW24"
KOL = "kural"
YOL = 0
KAYIT_SURUMU = 2
ISTANBUL = "İstanbul"
SEVIYELER = (("tam", 3, "istanbul"), ("iki_verici", 2, "istanbul"), ("sehir_disi", 2, "sehir"))
KUCUK_SEVIYESI = ("kucuk_yedek", 1, "sehir")
LISTE = 10                      # basılan aday satırı


class Eksik(RuntimeError):
    """Sahnenin dayandığı koşu, plan ya da ölçüm yok ya da eski (stderr, çıkış 1)."""


def kod_ozeti() -> str:
    h = hashlib.sha256()
    h.update(Path(__file__).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    h.update(simulasyon.vaka_kod_ozeti().encode() + b"\0" + oyun.olcum_kodu().encode())
    return h.hexdigest()


def hedef(olcek: str = "tam") -> Path:
    return oyun.varsayilan_ortam(olcek).cikti / "hikaye.json"


# ---------------------------------------------------------------------------
# Girdiler
# ---------------------------------------------------------------------------


def kosu_oku(onbellek: Path, ad: str, anahtar: str) -> motor.KosuKaydi:
    """Önbellekteki koşunun tembel kaydı, salt okunur (yoksa ya da anahtarı tutmuyorsa `Eksik`; hiçbir şey silinmez)."""
    dizin = motor._dizin(Path(onbellek), ad, anahtar)
    m = dizin / "meta.json"
    meta = json.loads(m.read_text(encoding="utf-8")) if m.is_file() else {}
    if meta.get("anahtar") != anahtar:
        raise Eksik(f"{ad} koşusu önbellekte yok ya da anahtarı farklı: {dizin}")
    eksik = [t for t in meta["tablolar"] if not (dizin / f"tablo_{t}.parquet").is_file()]
    if eksik:
        raise Eksik(f"{ad} koşusunun tabloları eksik: {eksik}")
    return motor.KosuKaydi(dizin=dizin, meta=meta, kayitlar={})


def girdiler(o: oyun.Ortam) -> dict:
    """oyun.json'dan kural AW24 kaydı ve yol 0 Lumoda'sı; plan önbellekten; iki koşu (modül notu)."""
    kayit = json.loads(o.oyun_yolu.read_text(encoding="utf-8")) if o.oyun_yolu.is_file() else None
    if kayit is None:
        raise Eksik(f"{o.oyun_yolu} yok: önce python -m kiriklik.oyun izgara ve olc")
    ad = oyun.kosu_adi(KOL, SEZON, YOL)
    r = (kayit.get("kosular") or {}).get(ad)
    lum = (kayit.get("lumoda") or {}).get(str(YOL)) or {}
    if not r or r.get("gecerli") is not True or r.get("olcum") is None:
        raise Eksik(f"oyun.json: {ad} geçerli ölçülmüş değil")
    if r.get("olcum_ozeti") != oyun.olcum_kodu():
        raise Eksik(f"oyun.json: {ad} bugünkü ölçüm koduyla ölçülmemiş (python -m kiriklik.oyun olc)")
    if not lum.get("anahtar") or r.get("lumoda_anahtari") != lum["anahtar"]:
        raise Eksik(f"oyun.json: {ad} yol 0'ın Lumoda koşusuyla ölçülmemiş")
    kol = kosu_oku(o.onbellek, ad, r["anahtar"])
    lumoda = kosu_oku(o.onbellek, simulasyon.lumoda_adi(YOL), lum["anahtar"])
    p = oyun.plan_kur(KOL, SEZON, YOL, o.olcek, lumoda, ortam=o, kur=False)
    if p is None or p.kimlik != r.get("plan_kimligi"):
        raise Eksik(f"{KOL} {SEZON} planı önbellekte yok ya da kimliği oyun.json'dakinden farklı")
    if (((kol.meta.get("politikalar") or {}).get("elle_transfer") or {}).get("parametreler") or {}).get("plan") \
            != p.kimlik:
        raise Eksik(f"{ad} koşusu bu planla koşulmamış")
    return {"kayit": r, "lumoda_kaydi": lum, "kol": kol, "lumoda": lumoda, "plan": p}


# ---------------------------------------------------------------------------
# Sorgular
# ---------------------------------------------------------------------------


def _foto(s, ad: str, gun: date, magazalar: list[str]) -> pd.DataFrame:
    """Sezon kapsamının `gun` mağaza fotoğrafı, verilen mağazalarda: [magaza_id, urun_id, adet]."""
    f = olcutler._fotograflar(s, ad, [gun])
    return f[f["magaza_id"].isin(magazalar)][["magaza_id", "urun_id", "adet"]]


def _satis(s, ad: str, hucre: pd.DataFrame, bas: date, son: date) -> pd.DataFrame:
    """`hucre` [magaza_id, urun_id] satırlarının [bas, son) pozitif satışı (adet)."""
    s.kaydet("hk_hucre", hucre[["magaza_id", "urun_id"]].drop_duplicates())
    t = s.df(f"""
        select h.magaza_id, h.urun_id, sum(case when t.adet > 0 then t.adet else 0 end)::bigint as adet
        from hk_hucre h join {s.t(ad, "satis")} t
          on cast(t.magaza_id as varchar) = h.magaza_id and cast(t.urun_id as varchar) = h.urun_id
        where t.tarih >= ? and t.tarih < ? group by 1, 2""", pd.Timestamp(bas), pd.Timestamp(son))
    return hucre[["magaza_id", "urun_id"]].drop_duplicates().merge(t, on=["magaza_id", "urun_id"], how="left").fillna(
        {"adet": 0}).astype({"adet": np.int64})


def _satis_gunlu(s, ad: str, hucre: pd.DataFrame, son: date) -> pd.DataFrame:
    """`hucre` [magaza_id, urun_id, varis] satırlarının [varis, son) pozitif satışı (saha ölçüsü)."""
    s.kaydet("hk_varis", hucre)
    t = s.df(f"""
        select h.magaza_id, h.urun_id, sum(case when t.adet > 0 then t.adet else 0 end)::bigint as adet
        from hk_varis h join {s.t(ad, "satis")} t
          on cast(t.magaza_id as varchar) = h.magaza_id and cast(t.urun_id as varchar) = h.urun_id
        where h.varis is not null and t.tarih >= h.varis and t.tarih < ? group by 1, 2""", pd.Timestamp(son))
    return hucre[["magaza_id", "urun_id"]].merge(t, on=["magaza_id", "urun_id"], how="left").fillna(
        {"adet": 0}).astype({"adet": np.int64})


def _satis_satirlari(s, ad: str, hucre: pd.DataFrame, bas: date, son: date) -> pd.DataFrame:
    """`hucre` [magaza_id, urun_id] satırlarının [bas, son) ham satışı: [magaza_id, urun_id, tarih, adet, tutar]."""
    s.kaydet("hk_sahne", hucre[["magaza_id", "urun_id"]].drop_duplicates())
    return s.df(f"""
        select h.magaza_id, h.urun_id, t.tarih, cast(t.adet as bigint) as adet, t.tutar
        from hk_sahne h join {s.t(ad, "satis")} t
          on cast(t.magaza_id as varchar) = h.magaza_id and cast(t.urun_id as varchar) = h.urun_id
        where t.tarih >= ? and t.tarih < ?
        order by t.tarih""", pd.Timestamp(bas), pd.Timestamp(son))


def varis_gunleri(elle: pd.DataFrame, alici: str, skular, karar: date) -> dict[str, int]:
    """Verici → bu alıcıya, bu SKU'lardaki satırlarının en erken varışı (karardan gün); `elle` karar gününün
    `elle_transfer` satırları [kaynak, hedef, urun_id, varis_tarihi]."""
    x = elle[(elle["hedef"].astype(str) == alici) & elle["urun_id"].astype(str).isin(list(skular))]
    en_erken = x.groupby(x["kaynak"].astype(str))["varis_tarihi"].min()
    return {str(v): int((pd.Timestamp(t).date() - karar).days) for v, t in en_erken.items()}


def lumoda_ilk_satis(satirlar: pd.DataFrame, magaza: str, urun_id: str, karar: date) -> dict:
    """Hücrenin pozitif satış adedi, ilk satışın karardan günü ve o günün birim fiyatı (satış yoksa adet 0, ikisi None)."""
    t = satirlar[(satirlar["magaza_id"] == magaza) & (satirlar["urun_id"] == urun_id) & (satirlar["adet"] > 0)]
    if t.empty:
        return {"adet": 0, "ilk_gun": None, "ilk_fiyat": None}
    ilk = t["tarih"].min()
    g = t[t["tarih"] == ilk]
    return {"adet": int(t["adet"].sum()), "ilk_gun": int((pd.Timestamp(ilk).date() - karar).days),
            "ilk_fiyat": float(g["tutar"].sum() / g["adet"].sum())}


def sahne_butcesi(kol: pd.DataFrame, lumoda: pd.DataFrame, alici: pd.DataFrame, verici: pd.DataFrame) -> dict:
    """Kol − Lumoda net adet ve TL, yalnız verilen hücreler [magaza_id, urun_id] (modül notu "Sahne bütçesi")."""
    def fark(hucre: pd.DataFrame) -> dict:
        def topla(t: pd.DataFrame) -> tuple[int, float]:
            x = t.merge(hucre[["magaza_id", "urun_id"]].drop_duplicates(), on=["magaza_id", "urun_id"])
            return int(x["adet"].sum()), float(x["tutar"].sum())
        (a, b), (c, d) = topla(kol), topla(lumoda)
        return {"adet": a - c, "tl": b - d}

    al, ve = fark(alici), fark(verici)
    return {"alici": al, "vericiler": ve, "net": {"adet": al["adet"] + ve["adet"], "tl": al["tl"] + ve["tl"]}}


def rota_kargosu(rota: int) -> dict[str, float]:
    """Rota sayısı × rota başı kargo, düşük ve orta maliyet."""
    return {p: int(rota) * sabitler.MALIYET_PAKETLERI[p].kargo_rota_tl for p in ("dusuk", "orta")}


def _bedenler(st: pd.DataFrame, sku: pd.DataFrame, magaza: str, option: str) -> dict[int, int]:
    """Çiftin beden sırası → stok (fotoğrafta satırı olmayan beden 0)."""
    o = sku[sku["option_id"] == option]
    x = st[st["magaza_id"] == magaza].set_index("urun_id")["adet"]
    return {int(r.beden_sira): int(x.get(r.urun_id, 0)) for r in o.sort_values("beden_sira").itertuples()}


def _kirik(bedenler: dict[int, int]) -> bool:
    """Stoklu ve en az bir bedeni sıfır (`olcu.cift_tablosu`'nun tanımı)."""
    h = pd.DataFrame({"magaza_id": "m", "option_id": "o", "beden_sira": list(bedenler), "stok": list(bedenler.values())})
    c = olcu.cift_tablosu(h)
    return bool(len(c) and c["kirik"].iloc[0])


# ---------------------------------------------------------------------------
# Adaylar ve sahne
# ---------------------------------------------------------------------------


def adaylar(g: dict) -> tuple[pd.DataFrame, dict]:
    """Planın bütün alıcı çiftleri, süzgeç bayraklarıyla (modül notu); ve bağlam (tablolar, kesitler)."""
    kol, lum, p = g["kol"], g["lumoda"], g["plan"]
    k = olcutler._Kapsam(kol, SEZON)
    h = p.hareketler.astype({"option_id": str, "urun_id": str, "verici": str, "alici": str})
    mag = kol.tablo("magaza", ["magaza_id", "ad", "sehir", "tip"]).astype(str).set_index("magaza_id")
    urun = kol.tablo("urun", ["urun_id", "option_id", "model_adi", "renk", "alt_kategori", "beden", "beden_sira",
                              "liste_fiyati"]).astype({"urun_id": str, "option_id": str})
    alicilar = sorted(set(h["alici"]))
    with olcutler._sql(kol=kol, lum=lum) as s:
        s.kaydet("sku", k.sku)
        karar_st = _foto(s, "kol", k.karar, alicilar)
        depo = olcutler._depo(s, "kol", [k.karar]).set_index("urun_id")["adet"]
        oncesi = {"kol": _foto(s, "kol", k.kesit["indirim_oncesi"], alicilar),
                  "lumoda": _foto(s, "lum", k.kesit["indirim_oncesi"], alicilar)}
        elle = olcutler._karar_gunu_elle(s, "kol", k.karar)
        varis = olcutler._varislar(h, elle)
        sku_hucre = h[["alici", "option_id"]].drop_duplicates().merge(k.sku[["urun_id", "option_id"]], on="option_id")
        sku_hucre = sku_hucre.rename(columns={"alici": "magaza_id"})[["magaza_id", "urun_id"]]
        satis = {ad: _satis(s, kisa, sku_hucre, k.karar, k.indirim) for ad, kisa in (("kol", "kol"), ("lumoda", "lum"))}
        saha = _satis_gunlu(s, "kol", varis[["magaza_id", "urun_id", "varis"]], k.indirim)
    satirlar = []
    for (alici, option), x in h.groupby(["alici", "option_id"], sort=True):
        st = _bedenler(karar_st, k.sku, alici, option)
        kirik_sira = [b for b, a in st.items() if a == 0]
        kirik_sku = k.sku[(k.sku["option_id"] == option) & k.sku["beden_sira"].isin(kirik_sira)]["urun_id"]
        vericiler = x.groupby("verici")["adet"].sum()
        sehir = mag.loc[alici, "sehir"]
        v_sehir = [mag.loc[v, "sehir"] for v in vericiler.index]
        satirlar.append({
            "alici": alici, "option_id": option, "alinan": int(x["adet"].sum()), "sehir": sehir,
            "verici": int(len(vericiler)), "verici_istanbul_disi": int(sum(c != ISTANBUL for c in v_sehir)),
            "verici_sehir_disi": int(sum(c != sehir for c in v_sehir)),
            "kirik_beden": len(kirik_sira), "depo_bos": bool(all(int(depo.get(u, 0)) == 0 for u in kirik_sku)),
            "lumoda_kirik": _kirik(_bedenler(oncesi["lumoda"], k.sku, alici, option)),
        })
    t = pd.DataFrame(satirlar)
    if len(t):
        t = t.sort_values(["alinan", "option_id", "alici"], ascending=[False, True, True], kind="mergesort")
    return t.reset_index(drop=True), {"k": k, "h": h, "mag": mag, "urun": urun, "karar_st": karar_st, "depo": depo,
                                      "oncesi": oncesi, "varis": varis, "satis": satis, "saha": saha, "elle": elle,
                                      "kol": kol, "lumoda": lum}


def suz(t: pd.DataFrame, seviye: tuple) -> pd.DataFrame:
    """Seviyenin süzgeci (modül notu)."""
    ad, en_az, yer = seviye
    if t.empty:
        return t
    m = t["depo_bos"] & t["lumoda_kirik"]
    m &= (t["sehir"] == ISTANBUL) & (t["verici_istanbul_disi"] >= en_az) if yer == "istanbul" \
        else (t["verici_sehir_disi"] >= en_az)
    return t[m]


def seviyeler(olcek: str) -> tuple:
    return SEVIYELER + ((KUCUK_SEVIYESI,) if olcek == "kucuk" else ())


def sec(t: pd.DataFrame, olcek: str = "tam") -> tuple[str, pd.DataFrame]:
    """İlk boş olmayan seviye ve adayları; hiçbir seviyede aday yoksa `Eksik`."""
    for seviye in seviyeler(olcek):
        a = suz(t, seviye)
        if len(a):
            return seviye[0], a
    raise Eksik(f"{KOL} {SEZON} planında sahne ölçütlerine uyan alıcı yok (seviyeler: {[s[0] for s in seviyeler(olcek)]})")


def _beden_adi(urun: pd.DataFrame, option: str) -> dict[int, str]:
    u = urun[urun["option_id"] == option]
    return {int(r.beden_sira): str(r.beden) for r in u.itertuples()}


def sahne(alici: str, option: str, b: dict) -> dict:
    """Seçilen alıcının sahne sayıları (modül notu)."""
    k, h, mag, urun = b["k"], b["h"], b["mag"], b["urun"]
    x = h[(h["alici"] == alici) & (h["option_id"] == option)]
    ad = _beden_adi(urun, option)
    u = urun[urun["option_id"] == option].iloc[0]
    st = _bedenler(b["karar_st"], k.sku, alici, option)
    sku = k.sku[k.sku["option_id"] == option].set_index("beden_sira")["urun_id"]
    kirik = [s for s, a in st.items() if a == 0]
    alinan_sku = sorted(set(x["urun_id"]))
    alici_h = pd.DataFrame({"magaza_id": alici, "urun_id": alinan_sku})
    verici_h = pd.DataFrame({"magaza_id": x["verici"].to_numpy(), "urun_id": x["urun_id"].to_numpy()}).drop_duplicates()
    with olcutler._sql(kol=b["kol"], lum=b["lumoda"]) as s_:
        kol_s = _satis_satirlari(s_, "kol", pd.concat([alici_h, verici_h]), k.karar, k.cikis)
        lum_s = _satis_satirlari(s_, "lum", pd.concat([alici_h, verici_h]), k.karar, k.cikis)
    varislar = varis_gunleri(b["elle"], alici, alinan_sku, k.karar)
    vericiler = []
    for v, y in x.groupby("verici", sort=False):
        satirlar = y.sort_values("beden_sira")
        vericiler.append({"magaza_id": v, "ad": mag.loc[v, "ad"], "sehir": mag.loc[v, "sehir"],
                          "adet": int(y["adet"].sum()),
                          "bedenler": {ad[int(r.beden_sira)]: int(r.adet) for r in satirlar.itertuples()},
                          "varis_gun": varislar[v],
                          "lumoda": {ad[int(r.beden_sira)]: lumoda_ilk_satis(lum_s, v, r.urun_id, k.karar)
                                     for r in satirlar.itertuples()}})
    vericiler.sort(key=lambda r: (-r["adet"], r["magaza_id"]))
    var = b["varis"][(b["varis"]["magaza_id"] == alici) & b["varis"]["urun_id"].isin(alinan_sku)]
    saha = b["saha"].merge(var[["magaza_id", "urun_id", "alinan"]], on=["magaza_id", "urun_id"])

    def satis_(ad_: str, skular) -> int:
        t = b["satis"][ad_]
        return int(t[(t["magaza_id"] == alici) & t["urun_id"].isin(skular)]["adet"].sum())

    def oncesi(ad_: str) -> dict:
        bd = _bedenler(b["oncesi"][ad_], k.sku, alici, option)
        return {"bedenler": {ad[s]: a for s, a in bd.items()}, "kirik": _kirik(bd),
                "kirik_bedenler": [ad[s] for s, a in bd.items() if a == 0], "stok": int(sum(bd.values()))}

    tum = list(sku.to_numpy())
    return {
        "option": {"option_id": option, "model_adi": str(u["model_adi"]), "renk": str(u["renk"]),
                   "alt_kategori": str(u["alt_kategori"]), "liste_fiyati": float(u["liste_fiyati"])},
        "alici": {"magaza_id": alici, "ad": mag.loc[alici, "ad"], "sehir": mag.loc[alici, "sehir"]},
        "vericiler": vericiler,
        "karar": {"bedenler": {ad[s]: a for s, a in st.items()}, "asorti": dict(zip(ad.values(), sabitler.ASORTI)),
                  "kirik_bedenler": [ad[s] for s in kirik],
                  "kirik_depo": {ad[s]: int(b["depo"].get(sku[s], 0)) for s in kirik}},
        "alinan": int(x["adet"].sum()),
        "alinan_bedenler": {ad[int(s)]: int(a) for s, a in x.groupby("beden_sira")["adet"].sum().items()},
        "en_erken_varis_gun": min(r["varis_gun"] for r in vericiler),
        "en_gec_varis_gun": max(r["varis_gun"] for r in vericiler),
        "butce": sahne_butcesi(kol_s, lum_s, alici_h, verici_h),
        "kargo": {"rota": len(vericiler), **rota_kargosu(len(vericiler))},
        "satis_indirime": {"kural": {"alinan_sku": satis_("kol", alinan_sku), "option": satis_("kol", tum)},
                           "lumoda": {"alinan_sku": satis_("lumoda", alinan_sku), "option": satis_("lumoda", tum)}},
        "saha_indirime": int(np.minimum(saha["adet"], saha["alinan"]).sum()),
        "indirim_oncesi": {"kural": oncesi("kol"), "lumoda": oncesi("lumoda")},
        "tarihler": {"karar": k.karar.isoformat(), "indirim": k.indirim.isoformat(),
                     "indirim_oncesi": k.kesit["indirim_oncesi"].isoformat()},
        "indirime_gun": (k.indirim - k.karar).days,
        "indirim_oncesi_gun": (k.kesit["indirim_oncesi"] - k.karar).days,
    }


def kur(o: oyun.Ortam) -> dict:
    """hikaye.json'un içeriği; adaylar tablosu stdout'a."""
    g = girdiler(o)
    t, b = adaylar(g)
    seviye, a = sec(t, o.olcek)
    alici, option = a.iloc[0]["alici"], a.iloc[0]["option_id"]
    print(f"hikâye: {len(t)} alıcı çifti; seviye {seviye}: {len(a)} aday (ilk {min(LISTE, len(a))})")
    print(a.head(LISTE).to_string(index=False))
    return {"surum": KAYIT_SURUMU, "kod": kod_ozeti(), "olcek": o.olcek, "sezon": SEZON, "kol": KOL, "yol": YOL,
            "kosu": {"ad": g["kayit"]["ad"], "anahtar": g["kayit"]["anahtar"]},
            "lumoda_anahtari": g["lumoda_kaydi"]["anahtar"], "plan_kimligi": g["plan"].kimlik,
            "olcum_ozeti": oyun.olcum_kodu(), "alici_cift": int(len(t)), "seviye": seviye,
            "seviyeler": {s[0]: int(len(suz(t, s))) for s in seviyeler(o.olcek)},
            "adaylar": json.loads(a.head(LISTE * 2).to_json(orient="records", force_ascii=False)),
            "sahne": sahne(alici, option, b)}


def yaz(sonuc: dict, yol: Path) -> Path:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".yaziliyor")
    gecici.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    gecici.replace(yol)
    return yol


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="python -m kiriklik.hikaye", description=__doc__.splitlines()[0])
    p.add_argument("--olcek", default="TAM", type=str.upper, choices=["TAM", "KUCUK"])
    a = p.parse_args(argv)
    o = oyun.varsayilan_ortam(a.olcek.lower())
    try:
        sonuc = kur(o)
    except Eksik as e:
        print(f"Eksik: {e}", file=sys.stderr)
        return 1
    print(f"yazıldı: {yaz(sonuc, hedef(o.olcek))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
