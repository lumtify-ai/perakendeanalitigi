"""Senaryo koşucusu: kalibre edilmiş parametrelerle her (yol, senaryo)
çiftini bir kez oynatıp `Sonuc.olcutler`'i diske yazar.

Bir yolun başlangıcı (`gecmis.yol_baslangici`'nin günler boyu geçmiş
oynatması) yalnız bir kez kurulur; o yolun 36 senaryosu bu tek kurulumun
üzerine sırayla (aynı süreç içinde) koşulur — her senaryo kendi bağımsız
`Durum` kopyasıyla başlar (`oyun.oyna` başlangıç durumunu yerinde
değiştirir). Yollar birbirinden bağımsız olduğundan `ProcessPoolExecutor`
ile paralel çalıştırılır; her worker'a yalnız picklenebilir veri
(`yol: int`, `kal: Kalibrasyon`) geçirilir, DuckDB bağlantısı ve `Dunya`
worker içinde yeniden kurulur.

Kaldığı yerden sürme: bir (yol, senaryo) sonucu zaten `cikti/yol{y}/
{anahtar}.json` olarak varsa o senaryo atlanır — yarıda kesilen bir koşu
tekrar başlatıldığında yalnız eksik dosyalar üretilir. Yazma atomiktir
(`.tmp`'ye yazılıp yeniden adlandırılır) — yarıda kesilme bozuk/yarım bir
JSON bırakmaz.
"""

import copy
import dataclasses
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from math import floor
from pathlib import Path

from . import kaynak, sabitler
from .dunya import Dunya, dunya_kur
from .gecmis import yol_baslangici
from .ihtiyac import magaza_beden_paylari
from .kalibrasyon import Kalibrasyon, kalibre_et
from .oyun import OyunAyari, oyna
from .politika import KuralPolitikasi, TahminPolitikasi
from .tahmin import Tahminci

# LightGBM tahmincisinin eğitimde kullandığı ilk pazartesi (bkz.
# tahmin.Tahminci docstring'i: "2025-02-03 → gün 33") — kalibrasyonda
# hiperparametre_sec'in kendi iç doğrulama penceresinden bağımsız, oyun
# dönemindeki gerçek Tahminci'nin sabit eğitim başlangıcı.
TAHMIN_ILK_KARAR_GUNU = "2025-02-03"

_KOLI_SECENEKLERI = ("A", "B", "C")
_SS_SECENEKLERI = ("sabit", "ros", "istatistik")


def senaryolar() -> list[dict]:
    """36 senaryo: {"yontem": "kural", "alim": a, "koli": k, "ss": aile} (27)
    + {"yontem": "tahmin", "alim": a, "koli": k} (9)."""
    liste: list[dict] = []
    for alim in sabitler.ALIM_ORANLARI:
        for koli in _KOLI_SECENEKLERI:
            for ss in _SS_SECENEKLERI:
                liste.append({"yontem": "kural", "alim": alim, "koli": koli, "ss": ss})
    for alim in sabitler.ALIM_ORANLARI:
        for koli in _KOLI_SECENEKLERI:
            liste.append({"yontem": "tahmin", "alim": alim, "koli": koli})
    return liste


def senaryo_anahtari(senaryo: dict) -> str:
    ss = senaryo.get("ss")
    return f"{senaryo['yontem']}|{round(senaryo['alim'] * 100)}|{senaryo['koli']}|{ss or '-'}"


def _dosya_adi(anahtar: str) -> str:
    """`|`, Windows dosya adlarında geçersizdir; diskteki dosya adı için
    `_` ile değiştirilir. Mantıksal anahtar (JSON içeriğinde, raporlarda)
    değişmez — yalnız dosya sistemi görünümü sanitize edilir."""
    return anahtar.replace("|", "_")


def _politika(senaryo: dict, kal: Kalibrasyon, dunya: Dunya):
    if senaryo["yontem"] == "kural":
        return KuralPolitikasi(kal.ss[senaryo["ss"]], kal.katsayilar)
    ilk_karar_gunu = dunya.gun(TAHMIN_ILK_KARAR_GUNU)
    return TahminPolitikasi(Tahminci(kal.tahmin_parametreleri, ilk_karar_gunu))


def _yol_calistir(yol: int, kal: Kalibrasyon) -> None:
    dunya = dunya_kur()
    con = kaynak.baglan()
    talep, gecmis_satis, baslangic = yol_baslangici(dunya, yol, con)
    paylar = magaza_beden_paylari(gecmis_satis, dunya, dunya.gun(sabitler.OYUN_BAS))

    yol_dizini = sabitler.CIKTI / f"yol{yol}"
    yol_dizini.mkdir(parents=True, exist_ok=True)

    for senaryo in senaryolar():
        hedef = yol_dizini / f"{_dosya_adi(senaryo_anahtari(senaryo))}.json"
        if hedef.exists():
            continue

        politika = _politika(senaryo, kal, dunya)
        ayar = OyunAyari(
            alim_orani=senaryo["alim"],
            kural=kal.koli[senaryo["koli"]],
            acik_kapasite=kal.acik_kapasite,
        )
        durum = copy.deepcopy(baslangic)
        sonuc = oyna(dunya, talep, gecmis_satis, durum, politika, ayar, paylar)

        _json_yaz(hedef, sonuc.olcutler)


def _json_yaz(hedef: Path, veri) -> None:
    gecici = hedef.with_suffix(hedef.suffix + ".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    gecici.replace(hedef)


def kos(yollar: range, kal: Kalibrasyon, isci: int = 4) -> None:
    """Her (yol, senaryo) için Sonuc.olcutler'i cikti/yol{y}/{anahtar}.json'a
    yazar; dosya varsa atlar (yarıda kalan koşu kaldığı yerden sürer).
    Yollar ProcessPoolExecutor(isci) ile paralel; bir yolun içinde senaryolar
    sırayla (yol başlangıcı bir kez kurulur)."""
    yollar_listesi = list(yollar)
    if not yollar_listesi:
        return
    with ProcessPoolExecutor(max_workers=isci) as havuz:
        gorevler = [havuz.submit(_yol_calistir, yol, kal) for yol in yollar_listesi]
        for gorev in as_completed(gorevler):
            gorev.result()  # bir worker hata verirse burada yükselir


def anlatim_kosulari(kal: Kalibrasyon) -> dict:
    """Yalnız yol 0, kural/varsayılan ss/alım %60/koli C: oncelik "cover",
    "ihtiyac", "esit" → üç Sonuc.olcutler. Ayrıca açık TL ve açık kapasite
    duyarlılıkları (varsayılan senaryoda, oncelik="cover")."""
    dunya = dunya_kur()
    con = kaynak.baglan()
    talep, gecmis_satis, baslangic = yol_baslangici(dunya, 0, con)
    paylar = magaza_beden_paylari(gecmis_satis, dunya, dunya.gun(sabitler.OYUN_BAS))
    politika = KuralPolitikasi(kal.ss[kal.varsayilan_ss], kal.katsayilar)

    def _kos(oncelik: str, acik_kapasite: int) -> dict:
        ayar = OyunAyari(
            alim_orani=0.60, kural=kal.koli["C"], acik_kapasite=acik_kapasite, oncelik=oncelik
        )
        durum = copy.deepcopy(baslangic)
        return oyna(dunya, talep, gecmis_satis, durum, politika, ayar, paylar).olcutler

    oncelikler = {oncelik: _kos(oncelik, kal.acik_kapasite) for oncelik in ("cover", "ihtiyac", "esit")}
    varsayilan_olcut = oncelikler["cover"]

    acik_tl_duyarliligi = {
        tl: varsayilan_olcut["acik_adet"] * tl + varsayilan_olcut["koli_sayisi"] * sabitler.KOLI_TL
        for tl in sabitler.ACIK_TL_DUYARLILIK
    }

    haftalik_ort = kaynak.haftalik_sevkiyat_ortalamasi(
        con, sabitler.OYUN_BAS, sabitler.OYUN_BIT, sabitler.KARAR_SAYISI
    )
    acik_kapasite_duyarliligi = {
        oran: _kos("cover", floor(haftalik_ort * oran)) for oran in sabitler.ACIK_KAPASITE_DUYARLILIK
    }

    return {
        "oncelik": oncelikler,
        "acik_tl_duyarliligi": acik_tl_duyarliligi,
        "acik_kapasite_duyarliligi": acik_kapasite_duyarliligi,
    }


if __name__ == "__main__":
    _dunya = dunya_kur()
    _con = kaynak.baglan()
    _kal = kalibre_et(_dunya, _con)

    sabitler.CIKTI.mkdir(parents=True, exist_ok=True)
    _json_yaz(sabitler.CIKTI / "kalibrasyon.json", dataclasses.asdict(_kal))

    kos(range(0, 21), _kal)
