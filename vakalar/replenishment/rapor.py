"""Yazıların alıntıladığı bütün sayıları basar. `cikti/` altındaki JSON'ları
(kalibrasyon ve 21 yolun senaryoları) OKUR, sweep'i yeniden koşmaz.

    .venv/Scripts/python rapor.py > cikti/rapor.txt

Yazı düzenlerken tek kaynak budur (global-constraints: uydurma sayı yasak).

Merkez bölüm (=== 20 YOL ===) bir ayrıştırmadır, iki-yönlü bir kıyas değil:
`tahmin_taban − kural` (aynı politika, farklı öngörü → ÖNGÖRÜ ETKİSİ) ve
`tahmin − tahmin_taban` (aynı öngörü, farklı politika → POLİTİKA ETKİSİ)
ayrı ayrı raporlanır (20 alternatif yol üzerinden min/medyan/max/aynı yön).

`kirik_cift` hiçbir yerde tek başına basılmaz (stoksuz bir çift "kırık"
sayılmaz — raf boşsa iyi görünmek yanıltıcıdır). Dürüst hali
(`kirik_cift_pay_yuzde`, stoklu/boş çift sayılarıyla) yalnız yol 0'ın 27
kadran senaryosu için var; bu senaryolar `_regen_yol0_dial.py` ile bir kez
yeniden oynatılıp diske yazıldı (bkz. o script, task-11-report.md). Kalan
yol0 senaryoları ve yol 1-20 eski (kirik_cift alanı olmayan) JSON'ları
taşıyor; bu yüzden büyük tablolarda kirik metriği hiç basılmıyor.
"""
import copy
import json
import statistics
from pathlib import Path

from replenishment import kaynak, sabitler
from replenishment.dagitim import KoliKurali, dagit
from replenishment.depo import Depo, depo_kur
from replenishment.dunya import dunya_kur
from replenishment.gecmis import yol_baslangici
from replenishment.ihtiyac import GuvenlikStoku, bedene_bol, magaza_beden_paylari
from replenishment.kalibrasyon import Kalibrasyon
from replenishment.kos import anlatim_kosulari, senaryo_anahtari, senaryolar
from replenishment.motor import gunu_isle
from replenishment.politika import KuralPolitikasi

import numpy as np

CIKTI = sabitler.CIKTI

# ---------------------------------------------------------------------
# Saf yardımcılar (TDD: tests/test_rapor.py)
# ---------------------------------------------------------------------


def yirmi_yol_ozeti(fark_listesi: list[float]) -> dict:
    """(min, medyan, max, kaç yolun farkı pozitif, n). Boş liste kabul
    edilmez (çağıran en az bir yol vermeli)."""
    return {
        "min": min(fark_listesi),
        "medyan": statistics.median(fark_listesi),
        "max": max(fark_listesi),
        "pozitif": sum(1 for f in fark_listesi if f > 0),
        "n": len(fark_listesi),
    }


def yol_metrik(veri: dict, yol: int, anahtar: str, metrik: str) -> float:
    return veri[yol][anahtar][metrik]


def kombinasyon_farki(
    veri: dict, yollar: list[int], eslesmeler: list[tuple[str, str]], metrik: str
) -> list[float]:
    """Her yol için `eslesmeler`deki (sağ, sol) anahtar çiftlerinin metrik
    farkının ORTALAMASI — yol başına tek sayı (20 yolun özetini almadan
    önce, aynı yolun birden çok alım/koli kombinasyonunu tek sayıya
    indirger)."""
    sonuc = []
    for yol in yollar:
        farklar = [
            yol_metrik(veri, yol, sag, metrik) - yol_metrik(veri, yol, sol, metrik)
            for sag, sol in eslesmeler
        ]
        sonuc.append(sum(farklar) / len(farklar))
    return sonuc


def forecast_etkisi_eslesmeleri(alimlar: list[int], koliler: list[str]) -> list[tuple[str, str]]:
    """ÖNGÖRÜ ETKİSİ: tahmin_taban − kural, aynı politika (koli kuralı +
    ROS güvenlik stoku), farklı öngörü (LightGBM'e karşı kural formülü)."""
    return [
        (f"tahmin_taban|{a}|{k}|ros", f"kural|{a}|{k}|ros")
        for a in alimlar for k in koliler
    ]


def politika_etkisi_eslesmeleri(alimlar: list[int], koliler: list[str]) -> list[tuple[str, str]]:
    """POLİTİKA ETKİSİ: tahmin − tahmin_taban, aynı öngörü (LightGBM),
    farklı politika (taban yok ↔ kural kolunun tabanı var)."""
    return [
        (f"tahmin|{a}|{k}|-", f"tahmin_taban|{a}|{k}|ros")
        for a in alimlar for k in koliler
    ]


def koli_farki_eslesmeleri(alimlar: list[int], ss: str, sol_koli: str, sag_koli: str) -> list[tuple[str, str]]:
    """Kural kolunda iki koli kuralı arası fark (aynı ss ailesi), alım
    oranları üzerinden."""
    return [(f"kural|{a}|{sag_koli}|{ss}", f"kural|{a}|{sol_koli}|{ss}") for a in alimlar]


def ss_farki_eslesmeleri(alimlar: list[int], koliler: list[str], sol_ss: str, sag_ss: str) -> list[tuple[str, str]]:
    """Kural kolunda iki güvenlik stoku ailesi arası fark, alım × koli
    kombinasyonları üzerinden."""
    return [
        (f"kural|{a}|{k}|{sag_ss}", f"kural|{a}|{k}|{sol_ss}")
        for a in alimlar for k in koliler
    ]


# ---------------------------------------------------------------------
# Disk okuma
# ---------------------------------------------------------------------


def _yol_yukle(cikti: Path, yol: int) -> dict[str, dict]:
    """{senaryo_anahtari: olcutler} — o yolun cikti/yol{n}/ altındaki 45
    dosyası."""
    sonuc = {}
    for senaryo in senaryolar():
        anahtar = senaryo_anahtari(senaryo)
        dosya = cikti / f"yol{yol}" / f"{anahtar.replace('|', '_')}.json"
        sonuc[anahtar] = json.loads(dosya.read_text(encoding="utf-8"))
    return sonuc


def _kalibrasyon_yukle(cikti: Path) -> dict:
    return json.loads((cikti / "kalibrasyon.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------
# Bölümler
# ---------------------------------------------------------------------


def _bolum_veri(dunya, con) -> None:
    print("=== VERİ ===")
    bas_gun, bit_gun = dunya.gun(sabitler.OYUN_BAS), dunya.gun(sabitler.OYUN_BIT)
    gun_sayisi = bit_gun - bas_gun + 1
    oc_sayisi = len(dunya.oc_hucre)
    print(f"oyun dönemi: {gun_sayisi} gün · karar sayısı: {sabitler.KARAR_SAYISI}")
    print(f"option-mağaza (OC) çifti: {oc_sayisi}")

    line_option = {}
    for line, opt in zip(dunya.oc_line, dunya.oc_option):
        line_option.setdefault(line, set()).add(opt)
    for line in sorted(line_option):
        print(f"  line {line}: {len(line_option[line])} option")

    acik_kapasite = _kalibrasyon_yukle(CIKTI)["acik_kapasite"]
    haftalik_ort = kaynak.haftalik_sevkiyat_ortalamasi(
        con, sabitler.OYUN_BAS, sabitler.OYUN_BIT, sabitler.KARAR_SAYISI
    )
    print(f"açık kapasite: {acik_kapasite:,} adet/hafta (haftalık v2 sevkiyat ortalaması "
          f"{haftalik_ort:,.0f} × {sabitler.ACIK_KAPASITE_ORANI})")
    print()


def _bolum_depo(dunya) -> None:
    from replenishment.depo import _line_per_option, _nos_alim, _tek_alim_maskesi

    print("=== DEPO ===")
    line_per_option = _line_per_option(dunya)
    tek_alim = _tek_alim_maskesi(line_per_option)

    for alim in sabitler.ALIM_ORANLARI:
        depo = depo_kur(dunya, alim, sabitler.OYUN_BAS, sabitler.OYUN_BIT)
        koli = int(depo.koli[tek_alim].sum())
        acik = int(depo.acik[tek_alim].sum())
        print(f"alım %{round(alim * 100)}: Collection+Outlet {koli:,} koli · {acik:,} açık adet")

    nos_hedefi = _nos_alim(dunya, dunya.sezon[dunya.gun(sabitler.OYUN_BAS)])
    nos_toplam = float(nos_hedefi[~tek_alim].sum())
    print(f"NOS/Basic hedef (zincir plan talebinin {sabitler.TEDARIK_HEDEF_HAFTA} haftası): "
          f"{nos_toplam:,.0f} adet")
    print()


def _bolum_kalibrasyon(kal: dict) -> None:
    print("=== KALİBRASYON ===")
    print("özel gün katsayıları (kategori → gün katsayısı):")
    for kategori, deger in sorted(kal["katsayilar"].items()):
        print(f"  {kategori}: {deger:.2f}")
    print(f"hedef bulunabilirlik: %{kal['hedef_bulunabilirlik']:.1f}")
    print(f"sabit seçilen: {kal['ss']['sabit']['deger']} adet · "
          f"ros seçilen: {kal['ss']['ros']['deger']} gün")
    print(f"varsayılan güvenlik stoku ailesi: {kal['varsayilan_ss']}")
    for ad in ("A", "B", "C"):
        k = kal["koli"][ad]
        print(f"  koli {ad}: alfa={k['alfa']} beta={k['beta']} gama={k['gama']}")
    print(f"açık kapasite: {kal['acik_kapasite']:,} adet/hafta")
    print(f"tahmin parametreleri: {kal['tahmin_parametreleri']}")

    print(f"ön oyun tablosu: {len(kal['tablo'])} satır")
    asamalar: dict[str, list[dict]] = {}
    for satir in kal["tablo"]:
        asamalar.setdefault(satir["asama"], []).append(satir)
    for asama, satirlar in asamalar.items():
        en_iyi = max(satirlar, key=lambda s: s["bulunabilirlik"])
        print(f"  {asama}: {len(satirlar)} satır · en yüksek bulunabilirlik "
              f"%{en_iyi['bulunabilirlik']:.1f}")
    print()


_YOL0_TABLO_METRIKLERI = (
    "bulunabilirlik", "kayip_orani", "satisa_donme_gun", "magaza_stok_son",
    "toplama_maliyeti_tl", "acik_doluluk", "beden_sapmasi", "str",
)


def _bolum_yol0(veri_yol0: dict) -> None:
    print("=== YOL 0 ===")
    print("(kirik_cift bu tabloda yok — tek başına yanıltıcı, bkz. modül "
          "docstring'i; dürüst hali yalnız ANLATIM'daki 27 kadran satırında var)")
    baslik = "senaryo".ljust(28) + "".join(m.rjust(16) for m in _YOL0_TABLO_METRIKLERI)
    print(baslik)
    for senaryo in senaryolar():
        anahtar = senaryo_anahtari(senaryo)
        o = veri_yol0[anahtar]
        satir = anahtar.ljust(28) + "".join(f"{o[m]:16.1f}" for m in _YOL0_TABLO_METRIKLERI)
        print(satir)
    print()


def _bolum_yirmi_yol(veri_yollari: dict, kal: dict) -> None:
    print("=== 20 YOL ===")
    yollar = list(range(1, sabitler.YOL_SAYISI + 1))
    alimlar = [round(a * 100) for a in sabitler.ALIM_ORANLARI]
    koliler = ["A", "B", "C"]
    metrikler = ("kayip_orani", "bulunabilirlik", "satisa_donme_gun",
                 "magaza_stok_son", "toplama_maliyeti_tl")

    print("-- ÖNGÖRÜ ETKİSİ (tahmin_taban − kural, aynı politika/ROS, farklı öngörü) --")
    for m in metrikler:
        farklar = kombinasyon_farki(veri_yollari, yollar, forecast_etkisi_eslesmeleri(alimlar, koliler), m)
        o = yirmi_yol_ozeti(farklar)
        print(f"  {m}: min {o['min']:.2f} · medyan {o['medyan']:.2f} · max {o['max']:.2f} · "
              f"pozitif {o['pozitif']}/{o['n']}")

    print("-- POLİTİKA ETKİSİ (tahmin − tahmin_taban, aynı öngörü, farklı politika) --")
    for m in metrikler:
        farklar = kombinasyon_farki(veri_yollari, yollar, politika_etkisi_eslesmeleri(alimlar, koliler), m)
        o = yirmi_yol_ozeti(farklar)
        print(f"  {m}: min {o['min']:.2f} · medyan {o['medyan']:.2f} · max {o['max']:.2f} · "
              f"pozitif {o['pozitif']}/{o['n']}")

    varsayilan_ss = kal["varsayilan_ss"]
    print(f"-- KOLİ KURALI (kural kolu, ss={varsayilan_ss}) --")
    for sol, sag in (("A", "B"), ("A", "C")):
        for m in metrikler:
            farklar = kombinasyon_farki(
                veri_yollari, yollar, koli_farki_eslesmeleri(alimlar, varsayilan_ss, sol, sag), m
            )
            o = yirmi_yol_ozeti(farklar)
            print(f"  koli {sag}-{sol} · {m}: min {o['min']:.2f} · medyan {o['medyan']:.2f} · "
                  f"max {o['max']:.2f} · pozitif {o['pozitif']}/{o['n']}")

    print("-- GÜVENLİK STOKU AİLESİ (kural kolu) --")
    for sol, sag in (("sabit", "ros"), ("sabit", "istatistik"), ("ros", "istatistik")):
        for m in ("magaza_stok_son", "bulunabilirlik"):
            farklar = kombinasyon_farki(
                veri_yollari, yollar, ss_farki_eslesmeleri(alimlar, koliler, sol, sag), m
            )
            o = yirmi_yol_ozeti(farklar)
            print(f"  {sag}-{sol} · {m}: min {o['min']:.2f} · medyan {o['medyan']:.2f} · "
                  f"max {o['max']:.2f} · pozitif {o['pozitif']}/{o['n']}")
    print()


def _hafta1_asim_ornegi(dunya, con, kal: Kalibrasyon) -> None:
    """3. yazı örneği: yol 0, alım %60, ilk karar haftasında depo
    talebinin en çok aştığı option'ın mağaza başına ihtiyacı ve üç
    öncelikle (cover/ihtiyac/esit) giden adetler. Yalnız BİR gün
    (ilk karar günü) oynatılır — tam sezon koşulmaz."""
    talep, gecmis_satis, baslangic = yol_baslangici(dunya, 0, con)
    paylar = magaza_beden_paylari(gecmis_satis, dunya, dunya.gun(sabitler.OYUN_BAS))
    politika = KuralPolitikasi(kal.ss[kal.varsayilan_ss], kal.katsayilar)

    bas_gun = dunya.gun(sabitler.OYUN_BAS)
    durum = copy.deepcopy(baslangic)
    rng = np.random.default_rng(sabitler.IADE_TOHUM)
    satis, _kayip = gunu_isle(durum, bas_gun, talep[bas_gun], None, None, rng)
    gozlenen = gecmis_satis.copy()
    gozlenen[bas_gun] = satis
    gorulen = gozlenen.copy()
    gorulen[bas_gun + 1:] = 0

    hedef, ongoru = politika.hedef(gorulen, dunya, bas_gun, durum.stok, durum.stoklu_gunluk)
    n = bedene_bol(hedef, paylar, durum.stok, dunya)

    depo = depo_kur(dunya, 0.60, sabitler.OYUN_BAS, sabitler.OYUN_BIT)
    O = len(dunya.optionlar)
    ihtiyac_opt = np.zeros(O, dtype=np.int64)
    np.add.at(ihtiyac_opt, dunya.oc_opt, n.sum(axis=1))
    # "depo talebinin en çok aştığı option": ilk karar gününde toplam mağaza
    # ihtiyacı en yüksek option — depo bu option için en çok karar vermek
    # zorunda kalıyor, birden çok mağaza aynı kısıtlı kaynağa talip oluyor.
    en_asan = int(np.argmax(ihtiyac_opt))
    option_adi = dunya.optionlar[en_asan]
    depo_opt_toplami = int(depo.koli[en_asan] * sabitler.KOLI_ADET + depo.acik[en_asan].sum())

    oc_secili = np.where(dunya.oc_opt == en_asan)[0]
    print(f"örnek: yol 0, alım %60, ilk karar günü, en çok talep gören option {option_adi}")
    print(f"  toplam mağaza ihtiyacı {int(ihtiyac_opt[en_asan])} adet · depoda {depo_opt_toplami} adet")
    for oc in oc_secili:
        print(f"  mağaza {dunya.oc_magaza[oc]}: ihtiyaç {int(n[oc].sum())} adet")

    for oncelik in ("cover", "ihtiyac", "esit"):
        depo_kopya = Depo(koli=depo.koli.copy(), acik=depo.acik.copy())
        sevk = dagit(n, ongoru, durum.stok, depo_kopya, dunya, kal.koli["C"],
                     kal.acik_kapasite, oncelik)
        print(f"  öncelik={oncelik}:")
        for oc in oc_secili:
            gonderilen = int(sevk.gelen[dunya.oc_hucre[oc]].sum())
            print(f"    mağaza {dunya.oc_magaza[oc]}: {gonderilen} adet gönderildi")


def _bolum_anlatim(dunya, con, kal_json: dict) -> None:
    print("=== ANLATIM ===")
    kal = Kalibrasyon(
        katsayilar=kal_json["katsayilar"],
        ss={ad: GuvenlikStoku(**d) for ad, d in kal_json["ss"].items()},
        varsayilan_ss=kal_json["varsayilan_ss"],
        koli={ad: KoliKurali(**d) for ad, d in kal_json["koli"].items()},
        hedef_bulunabilirlik=kal_json["hedef_bulunabilirlik"],
        acik_kapasite=kal_json["acik_kapasite"],
        tahmin_parametreleri=kal_json["tahmin_parametreleri"],
        tablo=kal_json["tablo"],
    )
    kosullar = anlatim_kosulari(kal)
    print("öncelik kuralları (yol 0, kural/varsayılan ss, alım %60, koli C):")
    for oncelik, olcut in kosullar["oncelik"].items():
        print(f"  {oncelik}: bulunabilirlik %{olcut['bulunabilirlik']:.1f} · "
              f"kayıp %{olcut['kayip_orani']:.1f} · beden sapması %{olcut['beden_sapmasi']:.1f}")

    print("açık TL duyarlılığı (aynı senaryo, koli+açık adet sabit, TL/adet değişken):")
    for tl, maliyet in kosullar["acik_tl_duyarliligi"].items():
        print(f"  {tl} TL/adet: {maliyet:,.0f} TL toplama maliyeti")

    print("açık kapasite duyarlılığı (haftalık v2 sevkiyat ortalamasının oranı):")
    for oran, olcut in kosullar["acik_kapasite_duyarliligi"].items():
        print(f"  ×{oran}: bulunabilirlik %{olcut['bulunabilirlik']:.1f} · "
              f"kayıp %{olcut['kayip_orani']:.1f}")

    _hafta1_asim_ornegi(dunya, con, kal)
    print()


def main() -> None:
    dunya = dunya_kur()
    con = kaynak.baglan()
    kal_json = _kalibrasyon_yukle(CIKTI)

    _bolum_veri(dunya, con)
    _bolum_depo(dunya)
    _bolum_kalibrasyon(kal_json)

    veri_yol0 = _yol_yukle(CIKTI, 0)
    _bolum_yol0(veri_yol0)

    veri_yollari = {yol: _yol_yukle(CIKTI, yol) for yol in range(1, sabitler.YOL_SAYISI + 1)}
    _bolum_yirmi_yol(veri_yollari, kal_json)

    _bolum_anlatim(dunya, con, kal_json)


if __name__ == "__main__":
    main()
