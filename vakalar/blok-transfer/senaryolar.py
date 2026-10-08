"""Demo senaryolarını üretir (elle koşulur; build'in parçası DEĞİL — site spec §7).

    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py

16 (verici eşiği × alıcı tavanı) hücresi × 2 yöntem. Planlar `cikti/planlar` önbelleğinden
okunur: MIP hücreleri 10 sn ile 12 dk arası sürer, yeniden koşum anidir. Önce
`python -m blok_transfer.hazirla` koşmuş olmalı (Basit kayıp tablosu).

Her sonuç `ozet` (Demo.astro'nun çizdiği ölçütler, bu dosyadaki sırayla) ile birlikte sonuç
düzeyinde `durum` (ve MIP için `bosluk_yuzde`) taşır; Demo bunları çizmez. Yakalama ölçütü
ileriye bakandır: planın taşıdığı mal, karar anından sonraki 8 haftada kaybı ne kadar
karşıladı (`olcum`, Basit kayıp tablosu).
"""
import json
import subprocess
from dataclasses import replace
from datetime import date
from itertools import product
from pathlib import Path

import pandas as pd

from blok_transfer import degerlendirme, hazirla, olcum
from blok_transfer.cekirdek import veri
from blok_transfer.cekirdek.parametreler import Parametreler

PARAMETRELER = [
    {
        "ad": "verici_cover_esigi",
        "etiket": "Gönderen mağazada asgari cover (hafta)",
        "degerler": [6, 14, 18, 26],
    },
    {
        "ad": "alici_cover_tavani",
        "etiket": "Alıcı mağazada azami cover (hafta)",
        "degerler": [0, 3, 6, 14],
        # 0 = üçüncü kapı kapalı; alıcı yalnız kırık ya da stoksuz olabilir.
        # Yayımlanmış referans senaryo budur.
        "deger_etiketleri": {"0": "kapalı"},
    },
    {"ad": "yontem", "etiket": "Çözüm yöntemi", "degerler": ["greedy", "mip"]},
]
KOK = Path(__file__).resolve().parent
CIKTI = KOK / "cikti"
ONBELLEK = CIKTI / "planlar"
HEDEF = KOK.parents[1] / "site" / "src" / "data" / "senaryolar" / "blok-transfer.json"
OLCUM_HAFTA = Parametreler().olcum_hafta
KORUNUM_TOLERANSI_TL = 0.5      # MIP net kazancı açgözlüden en fazla bu kadar düşük olabilir

# Demo.astro ölçütleri sözlüğün ekleme sırasıyla basıyor: manşet ölçütler (net kazanç ve
# yakalama) üstte, çözüm süresi en altta. Sırayı burada kuruyoruz, bileşen dizi bilmiyor.
OLCUT_SIRASI = ["option_sayisi", "tasinan_adet", "rota_sayisi", "bosalan_magaza",
                "net_kazanc_tl", "kayip_yakalama_yuzde", "sure_sn"]


def _surum() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        sha = "yerel"
    return f"{sha} {date.today().isoformat()}"


def olcum_zemini(con, karar: date, kayip: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ölçüm için bir kez hazırlanan iki tablo: evren içi pencere kaybı (Basit) ve vericilerin
    penceredeki net satışı. Evren `bt_magaza`: planın dokunabildiği mağazalar."""
    veri.gorunumler(con, karar)
    evren = set(con.execute("select magaza_id from bt_magaza").df()["magaza_id"].astype(str))
    return (olcum.kayip_tablosu(kayip, karar, OLCUM_HAFTA, evren, "kayip"),
            olcum.verici_satisi(con, karar, OLCUM_HAFTA))


def olc_plan(con, karar: date, hareketler: pd.DataFrame, zemin) -> olcum.Olcum:
    kayip_t, satis = zemin
    return olcum.olc(olcum.tasinan(con, hareketler, karar), kayip_t, satis)


def referans_olcum(con, karar: date, kayip: pd.DataFrame, onbellek: Path | None = None) -> olcum.Olcum:
    """Yazıların referans planının (varsayılan parametreler, açgözlü) ileriye bakan ölçümü.
    Getiri katmanının ölçülen noktaları (p_alıcı, p_verici) buradan gelir."""
    plan, _ = degerlendirme.boru_hatti(con, karar, Parametreler(), "greedy", onbellek=onbellek)
    return olc_plan(con, karar, plan.hareketler, olcum_zemini(con, karar, kayip))


def _hucre(con, karar: date, zemin, verici, tavan, yontem: str, onbellek: Path | None) -> dict:
    """Tek (verici, tavan, yöntem) hücresi: sonuç sözlüğü + `net` (korunum denetimi için)."""
    anahtar = f"{verici}|{tavan}|{yontem}"
    p = replace(Parametreler(), verici_cover_esigi=float(verici), alici_cover_tavani=float(tavan))
    plan, ozet = degerlendirme.boru_hatti(con, karar, p, yontem, onbellek=onbellek)
    if plan.durum == "hata":
        raise RuntimeError(f"{anahtar}: çözücü çözüm bulamadı (durum 'hata'); üretim durdu")
    o = olc_plan(con, karar, plan.hareketler, zemin)
    ozet = {**ozet, "kayip_yakalama_yuzde": round(o.yakalama * 100, 1)}
    sonuc = {
        "ozet": {ad: ozet[ad] for ad in OLCUT_SIRASI},
        "durum": ozet["durum"],
        "satirlar": [],
    }
    if ozet["bosluk_yuzde"] is not None:
        sonuc["bosluk_yuzde"] = ozet["bosluk_yuzde"]
    return sonuc


def uret(con, karar: date, kayip: pd.DataFrame, onbellek: Path | None = None) -> dict:
    """16 hücre × 2 yöntem. `kayip`: Basit kayıp tablosu (`hazirla.oku_kayip`).

    Denetimler: çözücü 'hata' derse `RuntimeError`; MIP 'optimal' ya da 'limit' durumunda
    bir hücrede açgözlüden `KORUNUM_TOLERANSI_TL`'den fazla düşük net kazanç verirse
    `RuntimeError` (MIP ≥ açgözlü yapısal garanti değil, burada denetlenir)."""
    zemin = olcum_zemini(con, karar, kayip)
    sonuclar = {}
    for verici in PARAMETRELER[0]["degerler"]:
        for tavan in PARAMETRELER[1]["degerler"]:
            hucre = {y: _hucre(con, karar, zemin, verici, tavan, y, onbellek)
                     for y in PARAMETRELER[2]["degerler"]}
            mip, greedy = hucre["mip"], hucre["greedy"]
            if (mip["durum"] in ("optimal", "limit")
                    and mip["ozet"]["net_kazanc_tl"] < greedy["ozet"]["net_kazanc_tl"] - KORUNUM_TOLERANSI_TL):
                raise RuntimeError(
                    f"{verici}|{tavan}: MIP ({mip['durum']}) net kazancı "
                    f"{mip['ozet']['net_kazanc_tl']:,.2f} TL, açgözlüden "
                    f"{greedy['ozet']['net_kazanc_tl']:,.2f} TL düşük; korunum bozuldu")
            for yontem, sonuc in hucre.items():
                sonuclar[f"{verici}|{tavan}|{yontem}"] = sonuc
    return {"surum": _surum(), "parametreler": PARAMETRELER, "sonuclar": sonuclar}


def olu_adimlar(sonuclar: dict, parametreler: list[dict]) -> list[str]:
    """Bir kadranın iki komşu değerinin, DİĞER kadranların bütün birleşimlerinde (yöntem MIP)
    aynı `option_sayisi` ve `net_kazanc_tl` verdiği adımlar: ekranda o adıma basan okuyucu hiçbir
    şeyin değişmediğini görür. Boş liste = ölü adım yok. Eksik hücre adımı ölü saymaz."""
    kadranlar = [i for i, p in enumerate(parametreler) if p["ad"] != "yontem"]

    def imza(kombinasyon: dict) -> tuple | None:
        anahtar = "|".join(str(kombinasyon[p["ad"]]) for p in parametreler)
        ozet = sonuclar.get(anahtar, {}).get("ozet")
        return None if ozet is None else (ozet["option_sayisi"], ozet["net_kazanc_tl"])

    olu = []
    for i in kadranlar:
        kadran = parametreler[i]
        digerleri = [parametreler[j] for j in kadranlar if j != i]
        for a, b in zip(kadran["degerler"], kadran["degerler"][1:]):
            ayni = True
            for degerler in product(*[d["degerler"] for d in digerleri]):
                sabit = {"yontem": "mip", **{d["ad"]: v for d, v in zip(digerleri, degerler)}}
                ia, ib = imza({**sabit, kadran["ad"]: a}), imza({**sabit, kadran["ad"]: b})
                if ia is None or ia != ib:
                    ayni = False
                    break
            if ayni:
                olu.append(f"{kadran['ad']}: {a} → {b}")
    return olu


def tarama(con, karar: date, kayip: pd.DataFrame, verici_degerleri, alici_degerleri,
           onbellek: Path | None = None) -> pd.DataFrame:
    """MIP satırları, (verici, alıcı tavanı) ızgarası: ölü adım çıkarsa değer kümesini seçmek için
    (Ruling R2). Raporun DEMO KADRANI bölümü de aynı fonksiyonu çağırır."""
    zemin = olcum_zemini(con, karar, kayip)
    satirlar = []
    for verici, tavan in product(verici_degerleri, alici_degerleri):
        s = _hucre(con, karar, zemin, verici, tavan, "mip", onbellek)
        satirlar.append({
            "verici": verici,
            "alici_tavani": tavan,
            "option_sayisi": s["ozet"]["option_sayisi"],
            "net_kazanc_tl": s["ozet"]["net_kazanc_tl"],
            "kayip_yakalama_yuzde": s["ozet"]["kayip_yakalama_yuzde"],
            "durum": s["durum"],
            "bosluk_yuzde": s.get("bosluk_yuzde"),
        })
    return pd.DataFrame(satirlar)


def yaz(icerik: dict, yol: Path) -> None:
    metin = json.dumps(icerik, ensure_ascii=False, indent=1)
    boyut = len(metin.encode("utf-8"))
    if boyut >= 500 * 1024:
        raise ValueError(f"Senaryo dosyası bütçeyi aşıyor: {boyut} bayt ≥ 500 KB (site spec §7)")
    yol.write_text(metin, encoding="utf-8")


if __name__ == "__main__":
    con = veri.baglan()
    karar = veri.karar_ani(con)
    kayip = hazirla.oku_kayip(CIKTI, con, karar, OLCUM_HAFTA)
    icerik = uret(con, karar, kayip, onbellek=ONBELLEK)
    olu = olu_adimlar(icerik["sonuclar"], icerik["parametreler"])
    if olu:
        raise SystemExit("Ölü adım var, dosya yazılmadı (değer kümesini `tarama` ile değiştirin):\n  "
                         + "\n  ".join(olu))
    yaz(icerik, HEDEF)
    print(f"yazildi: {HEDEF}")
