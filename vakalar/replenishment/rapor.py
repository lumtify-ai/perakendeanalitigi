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
from replenishment.depo import Depo, depo_kur, tedarik_et
from replenishment.dunya import dunya_kur
from replenishment.gecmis import yol_baslangici
from replenishment.ihtiyac import GuvenlikStoku, bedene_bol, magaza_beden_paylari
from replenishment.kalibrasyon import Kalibrasyon
from replenishment.kos import anlatim_kosulari, senaryo_anahtari, senaryolar
from replenishment.motor import gunu_isle
from replenishment.oyun import OyunAyari, oyna
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


# `olcutler.hesapla`'nın döndürdüğü BÜTÜN anahtarlar (bkz. o dosyanın
# return sözlüğü) — hiçbiri atlanmaz (rapor.py tek kaynak: yazıda geçen
# hiçbir sayı bu listenin dışında kalamaz). 45 satır × 20 sütun tek satırlık
# tablo olarak okunmaz; bu yüzden senaryo başına uzun biçim (long-form)
# kullanılır, kol (arm) başına gruplanır. Kırık-çift üçlüsü (ruling 3)
# `kirik_cift`'in HEMEN yanında basılır — ham sayı hiçbir yerde yalnız
# görünmez.
_YOL0_GRUPLARI = (
    ("talep/satış", ("talep_adet", "satis_adet", "kayip_adet", "kayip_orani")),
    ("servis", ("bulunabilirlik", "satisa_donme_gun", "str")),
    ("sevkiyat", ("gonderilen_adet", "satilmayan_gonderilen", "koli_sayisi",
                  "acik_adet", "depo_kalan")),
    ("maliyet/doluluk", ("toplama_maliyeti_tl", "acik_doluluk")),
    ("stok/dağılım", ("magaza_stok_son", "beden_sapmasi")),
    ("kırık çift (dürüst)", ("kirik_cift", "stoklu_cift_sayisi", "bos_cift_sayisi",
                             "kirik_cift_pay_yuzde")),
)


def _bolum_yol0(veri_yol0: dict) -> None:
    print("=== YOL 0 ===")
    print("(bütün ölçütler, senaryo başına uzun biçim; kırık çift hiçbir "
          "zaman stoklu/boş çift sayısı ve payı olmadan tek başına basılmaz)")
    onceki_yontem = None
    for senaryo in senaryolar():
        if senaryo["yontem"] != onceki_yontem:
            onceki_yontem = senaryo["yontem"]
            print(f"-- kol: {onceki_yontem} --")
        anahtar = senaryo_anahtari(senaryo)
        o = veri_yol0[anahtar]
        print(f"  {anahtar}")
        for grup_adi, alanlar in _YOL0_GRUPLARI:
            degerler = " · ".join(f"{a}={o[a]:,.1f}" for a in alanlar)
            print(f"    {grup_adi}: {degerler}")
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


def _haftalik_detaylar(dunya, con, kal: Kalibrasyon, alim: float, koli_kurali, oncelik: str = "cover") -> list[dict]:
    """Referans senaryoyu (yol 0, kural/varsayılan ss) `oyun.oyna` ile BİREBİR
    aynı adımlarla hafta hafta oynatır, ama her karar gününde o haftanın
    kararını üreten anlık görüntüyü de (ihtiyaç `n`, öngörü, stok, depo —
    dağıtımdan HEMEN önceki hâl) saklar; gerçek `sevk` ile devam eder (yani
    17. haftaya kadar gerçek yörüngeden sapma yok). Bu, tek bir günü değil,
    tam sezonu oynatıp hangi haftada açık kapasitenin gerçekten dolduğunu
    bulabilmek için gerekli — `oyun.oyna` bu ara durumları dışarı vermiyor."""
    talep, gecmis_satis, baslangic = yol_baslangici(dunya, 0, con)
    paylar = magaza_beden_paylari(gecmis_satis, dunya, dunya.gun(sabitler.OYUN_BAS))
    politika = KuralPolitikasi(kal.ss[kal.varsayilan_ss], kal.katsayilar)
    depo = depo_kur(dunya, alim, sabitler.OYUN_BAS, sabitler.OYUN_BIT)

    bas_gun = dunya.gun(sabitler.OYUN_BAS)
    bit_gun = dunya.gun(sabitler.OYUN_BIT)
    karar_gunleri = [bas_gun + 7 * k for k in range(sabitler.KARAR_SAYISI)]
    karar_sirasi = {g: k for k, g in enumerate(karar_gunleri)}

    durum = copy.deepcopy(baslangic)
    gozlenen = gecmis_satis.copy()
    rng = np.random.default_rng(sabitler.IADE_TOHUM)
    bekleyen_sevk = None
    sonuc: list[dict] = []

    for g in range(bas_gun, bit_gun + 1):
        gelen = bekleyen_sevk
        bekleyen_sevk = None
        satis, _kayip = gunu_isle(durum, g, talep[g], gelen, None, rng)
        gozlenen[g] = satis

        k = karar_sirasi.get(g)
        if k is None:
            continue
        if k % 2 == 0:
            tedarik_et(depo, dunya, g)

        gorulen = gozlenen.copy()
        gorulen[g + 1:] = 0
        hedef, ongoru = politika.hedef(gorulen, dunya, g, durum.stok, durum.stoklu_gunluk)
        n = bedene_bol(hedef, paylar, durum.stok, dunya)

        depo_once = Depo(koli=depo.koli.copy(), acik=depo.acik.copy())
        stok_once = durum.stok.copy()

        sevk = dagit(n, ongoru, durum.stok, depo, dunya, koli_kurali, kal.acik_kapasite, oncelik)
        bekleyen_sevk = sevk.gelen

        sonuc.append({
            "hafta": k, "gun": g, "n": n, "ongoru": ongoru,
            "stok": stok_once, "depo": depo_once,
            "acik_adet": float(sevk.acik_adet),
            "acik_kapasite_doldu": sevk.acik_adet >= kal.acik_kapasite,
        })
    return sonuc


def _en_cok_talep_gören_option(dunya, n) -> tuple:
    """(option_adi, oc_indeksleri) — o haftanın toplam mağaza ihtiyacı en
    yüksek option'ı."""
    O = len(dunya.optionlar)
    ihtiyac_opt = np.zeros(O, dtype=np.int64)
    np.add.at(ihtiyac_opt, dunya.oc_opt, n.sum(axis=1))
    en_asan = int(np.argmax(ihtiyac_opt))
    return dunya.optionlar[en_asan], np.where(dunya.oc_opt == en_asan)[0]


def _oncelik_karsilastir(dunya, kal: Kalibrasyon, koli_kurali, hafta: dict, oc_secili) -> None:
    for oncelik in ("cover", "ihtiyac", "esit"):
        depo_kopya = Depo(koli=hafta["depo"].koli.copy(), acik=hafta["depo"].acik.copy())
        sevk = dagit(hafta["n"], hafta["ongoru"], hafta["stok"], depo_kopya, dunya,
                     koli_kurali, kal.acik_kapasite, oncelik)
        print(f"  öncelik={oncelik}:")
        for oc in oc_secili:
            gonderilen = int(sevk.gelen[dunya.oc_hucre[oc]].sum())
            print(f"    mağaza {dunya.oc_magaza[oc]}: {gonderilen} adet gönderildi")


def _capraz_oncelik_ornekleri(dunya, con, kal: Kalibrasyon) -> None:
    """3. yazı için iki örnek (yol 0, alım %60, kural/varsayılan ss, koli C).

    Örnek 1 (ilk karar günü): brief'in "depo talebinin en çok aştığı
    option"u KELİMESİ KELİMESİNE gerçekleşmiyor — bir sezonluk depo alımı
    tek günün ihtiyacını hiçbir zaman aşmaz (depo daima günlük ihtiyaçtan
    kat kat büyük). Bunun yerine o gün en çok mağaza talebi toplayan
    option gösterilir; bu haftada üç öncelik kuralı ÖZDEŞ sonuç verir
    çünkü açık kapasite ilk haftada henüz bağlayıcı değildir.

    Örnek 2: açık kapasitenin GERÇEKTEN dolduğu ilk haftayı arar (cover
    önceliğiyle referans yörünge boyunca) ve orada üç önceliğin farklı
    mağazalara farklı adet gönderdiğini gösterir — 3. yazının ihtiyaç
    duyduğu asıl örnek budur. Hiçbir hafta dolmazsa uydurma bir örnek
    ÜRETİLMEZ; en yakın hafta adıyla bildirilir."""
    koli_kurali = kal.koli["C"]
    haftalar = _haftalik_detaylar(dunya, con, kal, sabitler.EN_SIKI_ALIM, koli_kurali, oncelik="cover")

    ilk = haftalar[0]
    option_adi, oc_secili = _en_cok_talep_gören_option(dunya, ilk["n"])
    print("örnek 1: yol 0, alım %60, İLK karar günü. NOT: bu, brief'in tarif "
          "ettiği 'depo talebini en çok aşan option' DEĞİLDİR — bir sezonluk "
          "depo alımı hiçbir zaman tek günün ihtiyacını aşmaz; burada gösterilen "
          f"o gün en çok mağaza talebi toplayan option: {option_adi}.")
    print(f"  toplam mağaza ihtiyacı {int(ilk['n'][oc_secili].sum())} adet")
    for oc in oc_secili:
        print(f"  mağaza {dunya.oc_magaza[oc]}: ihtiyaç {int(ilk['n'][oc].sum())} adet")
    _oncelik_karsilastir(dunya, kal, koli_kurali, ilk, oc_secili)
    print("  not: üç öncelik burada özdeş sonuç verir — ilk haftada açık "
          "kapasite henüz bağlayıcı değil (bkz. örnek 2).")

    baglayan = next((h for h in haftalar if h["acik_kapasite_doldu"]), None)
    if baglayan is None:
        en_yakin = max(haftalar, key=lambda h: h["acik_adet"])
        oran = en_yakin["acik_adet"] / kal.acik_kapasite * 100
        print(f"\nörnek 2: referans senaryoda (yol 0, kural, alım %60, koli C, "
              f"öncelik=cover) 17 karar haftasının HİÇBİRİNDE açık kapasite "
              f"dolmadı — üç öncelik kuralı bu senaryoda sezon boyunca aynı "
              f"sonucu üretir. En yakın hafta: {en_yakin['hafta'] + 1}. karar, "
              f"{en_yakin['acik_adet']:.0f}/{kal.acik_kapasite} adet "
              f"(kapasitenin %{oran:.1f}'i) — bu, uydurulmuş bir örnek DEĞİL, "
              f"en yakın gerçek haftadır.")
        return

    option_adi2, oc_secili2 = _en_cok_talep_gören_option(dunya, baglayan["n"])
    print(f"\nörnek 2: açık kapasitenin GERÇEKTEN dolduğu ilk hafta — "
          f"{baglayan['hafta'] + 1}. karar (yol 0, kural, alım %60, koli C): "
          f"cover önceliğiyle {baglayan['acik_adet']:.0f}/{kal.acik_kapasite} "
          f"adet (kapasite doldu). O haftada en çok mağaza talebi toplayan "
          f"option: {option_adi2}.")
    for oc in oc_secili2:
        print(f"  mağaza {dunya.oc_magaza[oc]}: ihtiyaç {int(baglayan['n'][oc].sum())} adet")
    _oncelik_karsilastir(dunya, kal, koli_kurali, baglayan, oc_secili2)


def _kalibrasyon_nesnesi(kal_json: dict) -> Kalibrasyon:
    """JSON'dan Kalibrasyon nesnesi; iki bölüm de aynı kurulumu kullanır."""
    return Kalibrasyon(
        katsayilar=kal_json["katsayilar"],
        ss={ad: GuvenlikStoku(**d) for ad, d in kal_json["ss"].items()},
        varsayilan_ss=kal_json["varsayilan_ss"],
        koli={ad: KoliKurali(**d) for ad, d in kal_json["koli"].items()},
        hedef_bulunabilirlik=kal_json["hedef_bulunabilirlik"],
        acik_kapasite=kal_json["acik_kapasite"],
        tahmin_parametreleri=kal_json["tahmin_parametreleri"],
        tablo=kal_json["tablo"],
    )


def _bolum_anlatim(dunya, con, kal_json: dict) -> None:
    print("=== ANLATIM ===")
    kal = _kalibrasyon_nesnesi(kal_json)
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

    _capraz_oncelik_ornekleri(dunya, con, kal)
    print()


def _bolum_line(dunya, con, kal_json: dict) -> None:
    """Referans senaryoyu line kırılımıyla raporlar.

    Toplam rakam NOS ile Collection'ı birbirine karıştırıyor: NOS'un stoğu
    tanımı gereği bitmemeli (tedarikçiden iki haftada bir tamamlanıyor),
    Collection ise sezon başında bir kez alınıyor ve biten bitiyor. Aynı
    kuralın ikisine ne yaptığı ancak burada görünür.
    """
    from replenishment.olcutler import line_kirilimi

    print()
    print("=== LINE KIRILIMI ===")
    kal = _kalibrasyon_nesnesi(kal_json)
    talep, gecmis_satis, baslangic = yol_baslangici(dunya, 0, con)
    paylar = magaza_beden_paylari(gecmis_satis, dunya, dunya.gun(sabitler.OYUN_BAS))
    politika = KuralPolitikasi(kal.ss["ros"], kal.katsayilar)
    bas_gun, bit_gun = dunya.gun(sabitler.OYUN_BAS), dunya.gun(sabitler.OYUN_BIT)

    for alim in (sabitler.EN_SIKI_ALIM, 0.80):
        ayar = OyunAyari(alim, kal.koli["C"], kal.acik_kapasite)
        durum = copy.deepcopy(baslangic)
        sonuc = oyna(dunya, talep, gecmis_satis, durum, politika, ayar, paylar)
        kirilim = line_kirilimi(durum, dunya, talep, sonuc.gozlenen, bas_gun, bit_gun)
        print(f"referans: yol 0 · kural · ros · koli C · alım %{alim * 100:.0f}")
        print(f"  {'line':12s}{'talep':>10s}{'satış':>10s}{'kayıp%':>9s}{'bulun.%':>9s}{'son stok':>10s}")
        for line, d in kirilim.items():
            print(
                f"  {line:12s}{d['talep_adet']:10,.0f}{d['satis_adet']:10,.0f}"
                f"{d['kayip_orani']:9.1f}{d['bulunabilirlik']:9.1f}{d['magaza_stok_son']:10,.0f}"
            )


def _bolum_koli(dunya, con, kal_json: dict) -> None:
    """Koli kısıtının bedeli ne? Koliyi tamamen kapatıp ölçeriz.

    Sezgi "koli bir kısıttır, açık adet daha isabetlidir" der. Ölçüm tersini
    söylüyor: açık toplama haftalık kapasiteyle sınırlı olduğu için, koli
    olmadan zincir istediği hacmi hiç taşıyamıyor.
    """
    print()
    print("=== KOLİ KISITI ===")
    kal = _kalibrasyon_nesnesi(kal_json)
    talep, gecmis_satis, baslangic = yol_baslangici(dunya, 0, con)
    paylar = magaza_beden_paylari(gecmis_satis, dunya, dunya.gun(sabitler.OYUN_BAS))
    politika = KuralPolitikasi(kal.ss["ros"], kal.katsayilar)

    print("referans: yol 0 · kural · ros · alım %80 · öncelik cover")
    print(f"  {'kural':16s}{'bulun.%':>9s}{'kayıp%':>8s}{'koli':>9s}{'açık':>9s}"
          f"{'gönderilen':>12s}{'maliyet TL':>13s}{'TL/adet':>9s}{'beden sapma%':>14s}")
    for ad, kural in (("koli C + açık", kal.koli["C"]), ("yalnız açık", KoliKurali("yok"))):
        ayar = OyunAyari(0.80, kural, kal.acik_kapasite)
        sonuc = oyna(dunya, talep, gecmis_satis, copy.deepcopy(baslangic), politika, ayar, paylar)
        o = sonuc.olcutler
        birim = o["toplama_maliyeti_tl"] / o["gonderilen_adet"] if o["gonderilen_adet"] else 0.0
        print(f"  {ad:16s}{o['bulunabilirlik']:9.1f}{o['kayip_orani']:8.1f}{o['koli_sayisi']:9,.0f}"
              f"{o['acik_adet']:9,.0f}{o['gonderilen_adet']:12,.0f}{o['toplama_maliyeti_tl']:13,.0f}"
              f"{birim:9.2f}{o['beden_sapmasi']:14.1f}")
    print(f"  açık toplama tavanı: {kal.acik_kapasite:,}/hafta × {sabitler.KARAR_SAYISI} hafta "
          f"= {kal.acik_kapasite * sabitler.KARAR_SAYISI:,} adet")


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

    _bolum_line(dunya, con, kal_json)
    _bolum_koli(dunya, con, kal_json)
    _bolum_anlatim(dunya, con, kal_json)


if __name__ == "__main__":
    main()
