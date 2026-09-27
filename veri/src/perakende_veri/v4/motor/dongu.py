"""v4 stok-satış motoru: `simule_et` (günlük döngü).

Talep dünyanındır (gerçek λ + sayaç tabanlı tekdüze); motor o talebi stok
kısıtı altında satışa çevirir. Satış + gizli kayıp = talep özdeşliği
kurulum gereği tutar ve aynı müşteri akışı başka politikalarla yeniden
oynatılabilir:

    dunya = dunya_kur()
    ham   = simule_et(dunya)                                   # Lumoda
    kol   = simule_et(dunya, Politikalar(replenishment=...))   # karşı-olgusal

BAŞLANGIÇ (d = 0, 2022-07-04 pazartesi, döngüden önce)
======================================================

Devamlı (Basic/NOS) option'lar için bir `baslangic` siparişi (hatasız,
d = 0'da depoda): açık fiziksel mağazaların devamlı hücrelerine 28 günlük
plan hedefi (`sevkiyat` tip `baslangic`, yolda süresiz: pencereden önce
rafta) ve depoya option başına (tedarik süresi + 2 + emniyet) haftalık
zincir planı (v3 ısınma kuralı). Sezonluk ürünlerin stoğu yoktur; ilk
siparişleri dünyada hazırdır (`siparis_gun` negatif olabilir: d = 0'da
zaten verilmiştir; asla dizi indisi olarak kullanılmaz).

GÜNLÜK SIRA (spec §6.1; [T13]/[T14] = o görevde doldurulur)
============================================================

 1. FOTOĞRAF. Depo stoğu her gün (görünür SKU: devamlı hep, sezonluk ilk
    teslimden çıkış + 7'ye kadar, ve stoğu olan her SKU); mağaza stoğu
    yalnız pazartesi (penceresi açık fiziksel hücreler, mağaza açıksa ya da
    stoğu varsa; `stoklu_gun` = d−7 … d−1 günlerinin 17. adım bayrağı).
    Günün hiçbir hareketinden önce: dünkü kapanış = bugünkü açılış.
 2. TESLİM. gerceklesen_gun == d siparişleri: kalite kontrol (ilk
    siparişte dünyada önceden çekilmiş `hatali`; RPT/sürekli siparişte
    `sayac_uretici_option(d, "kalite", o)` ile), depoya `adet − hatali`;
    `kalite` kaydı.
 3. VARIŞLAR. Yolda kuyruğundan bugün varanlar stoğa (depo ya da hücre).
    Hedef mağaza bugün kapalıysa mal aynı gün depoya döner (`sevkiyat` tip
    `geri_yonlendirme`, hücreden depoya, yolda süresiz).
 4. OLAYLAR [T14]. Açılış / kapanış / tadilat transferleri
    (`politikalar.acilis`, `kapanis`).
 5. İLK DAĞITIM. Option'ın karar günü = max(lansman − en uzak aday
    mağazanın yolda süresi, ilk siparişin gerçek teslimi): `paket_secimi`
    ve `ilk_dagitim` (paket sayısı) çağrılır; motor aday olmayan, varış
    günü kapalı ve kapanış kararlı mağazaları sıfırlar, paketleri depodaki
    SKU'lara sığdırır (max paket = min_s depo[s] ÷ içerik[s]; mağazalar en
    büyük kalanla orantılı küçülür). Her mağazaya sevk günü = max(lansman −
    yolda_gun(depo→mağaza), karar günü): mal lansmana yetişir; sonraki
    günlere düşen sevkler bekler ve o gün depoya yeniden sığdırılır.
    Paket × paket içeriği SKU'lara (`sevkiyat` tip `ilk_dagitim`,
    `paket_id`). ONL (depodan satar) ve outlet akışı hücreleri almaz.
 6. ÇIKIŞ / OUTLET [T13]. cikis_gun == d option'lar için
    `outlet_akisi(g, os)` transferleri (şimdilik boş).
 7. RPT [T13] (pazartesi). `rpt(g)` → {option: adet | SKU dizisi};
    sipariş tedarik süresi sonra, önceden çekilmiş sapmayla gelir.
 8. SÜREKLİ TEDARİK (pazartesi, d % 14 == 0). Devamlı option'lar, v3'ün
    SKU düzeyindeki (s, S) kuralı: plan × düzeltme (son 56 günün zincir
    brüt satışı ÷ aynı dönemin planı, [0,7; 1,6]); bir bedenin envanter
    pozisyonu (depo + açık sipariş) (L + emniyet) haftalık planın altındaysa
    her beden (L + 2 + emniyet) haftaya tamamlanır, en az MOQ. Politika
    değildir.
 9. MARKDOWN [T13] (pazartesi). `markdown(g)` → [O, 3] (normal / outlet /
    online hattı); değişen oranlar `fiyat` kaydına.
10. REPLENİSHMENT (pazartesi). `replenishment(g)` → [C] istek; motor
    dağıtılamaz hücreleri sıfırlar (ONL, outlet akışı, ilk dağıtımı
    bitmemiş ya da çıkmış option, kapalı / kapanış kararlı mağaza), depo
    yetmeyen SKU'larda `orantili_kes` (v3) ve yola çıkarır.
11. ELLE TRANSFER [T14] (pazartesi). `elle_transfer(g)` (şimdilik boş).
12. FİYAT. markdown (hücrenin hattı) ve kampanya; `oran_talep = max(md,
    kampanya)`.
13. TALEP. `u = sayac_uretici(d, "talep").random(C)`; `λ = lam.gun(d) ×
    (1 − oran_talep)^(−ε)`; `talep = PoissonTersCDF(u, λ)`.
14. SATIŞ. Fiziksel hücre: `min(talep, raf)`; ONL: replenishment
    sevkinden SONRA **kalan** depodan `min(talep, depo[sku])`. Kalan talep
    gizli kayıp. İşlem indirimi (u_indirim < 0,08, oran 0 iken %30) yalnız
    fiyata.
15. İKAME [T13].
16. İADE. Fiziksel: n = d−7 satışı, Binom(n, 0,06 × (1 + 4 × tedarikçinin
    gizli hatalı oranı)), mağaza rafına (mağaza bugün kapalıysa aynı gün
    depoya, `sevkiyat` tip `iade_depoya`). ONL: n = d−10 satışı, oran 0,27
    × aynı kalite izi, depoya. `satis`e negatif satır (satış günü fiyatı).
17. STOKLU BAYRAĞI. stoklu[d, c] = satış öncesi raf > 0 (ONL: depo > 0) —
    müşterinin bulduğu.

Rastgelelik politikadan bağımsızdır: her gün `talep`, `indirim`, `iade`
amaçları birer `random(C)` çeker; kalite (gün, option) anahtarlıdır.

Mal defteri (`test_stok_korunumu`): her `sevkiyat` satırı `gun`de
kaynaktan (kaynak_hucre ya da depo, −1) çıkar, `varis_gun`de hedefe
(hedef_hucre ya da depo) girer; depo ayrıca teslim (adet − hatalı), online
satış ve online iadeyle; hücre satış ve mağaza iadesiyle değişir.
"""

import numpy as np
import pandas as pd

from .. import sabitler
from ..dunya import yolda_gun
from ..plan import en_buyuk_kalan
from ..politika import Politikalar, Transferler, paket_tablosu
from ..rastgele import sayac_uretici_option
from ..tedarik import hatali_adet
from .durum import (
    YOK_GUN,
    Durum,
    Gorunum,
    Kayit,
    magaza_takvimi,
    orantili_kes,
    paketleri_sigdir,
    salt_okunur,
    surekli_tedarik,
    topla,
)
from .satis import (
    gunun_birim_fiyati,
    hat_indisi,
    iade_cek,
    satis_yap,
    talep_cek,
    tekduzeler,
)

GECMIS_FIYAT = max(sabitler.IADE_GECIKME_MAGAZA, sabitler.IADE_GECIKME_ONLINE) + 1


def simule_et(
    dunya,
    politikalar: Politikalar | None = None,
    gun_sayisi: int | None = None,
    operasyon_tohumu: int = sabitler.TOHUM,
    kayit_talep: bool = False,
) -> dict:
    """Motoru koşar; ham sonuçları (gün, hücre/SKU/mağaza indisli) döndürür.

    politikalar       None ise `Politikalar()` (Lumoda)
    gun_sayisi        yalnız ilk n günü koş; ilk n gün tam koşunun ilk n
                      günüyle birebir aynıdır
    operasyon_tohumu  indirim, iade ve kalite çekilişlerinin tohumu (talep
                      dünyanın tohumuyla çekilir)
    kayit_talep       True ise `talep` [D, C] int16 de döner

    Dönen sözlük: `satis` (gun, hucre, adet, tutar, indirim_tutari,
    kampanya_id; iade negatif satır), `gizli_kayip` (gun, hucre, adet),
    `ikame_satis` [T13], `sevkiyat` (gun, varis_gun, kaynak, hedef,
    kaynak_hucre, hedef_hucre, sku, adet, tip, paket_id; −1 = depo /
    paketsiz), `stok` (pazartesi: gun, hucre, adet, stoklu_gun),
    `depo_stok` (günlük: gun, sku, adet), `siparis` (sözlük listesi: tip,
    option, siparis_gun, planlanan_gun, gerceklesen_gun, skular, adetler,
    tedarikci, teslimde hatali/numune), `kalite` (teslim başına), `fiyat`
    (markdown değişimleri: gun, option, hat, oran), `son_durum`,
    `gun_sayisi`.
    """
    pol = Politikalar() if politikalar is None else politikalar
    w = dunya
    D = w.gun_sayisi if gun_sayisi is None else gun_sayisi
    C, S, O, M = len(w.cesit), len(w.urunler), len(w.optionlar), len(w.magazalar)
    opt = w.optionlar
    ho, hs, hm = w.hucre_option, w.hucre_sku, w.hucre_magaza
    onl, outlet_c = w.hucre_online, w.hucre_outlet_akisi
    fiz = ~onl
    lansman = opt["lansman_gun"].to_numpy()
    cikis = opt["cikis_gun"].to_numpy()
    sezonluk = opt["sezonluk"].to_numpy(dtype=bool)
    ted = np.asarray(w.tedarikci_idx)
    L_o = w.tedarikciler["rpt_hafta"].to_numpy()[ted]
    moq_o = w.tedarikciler["moq_option"].to_numpy()[ted]
    alan = opt["alt_kategori"].map(sabitler.ALT_KATEGORI_ALAN).to_numpy()
    uyum_o = alan == w.tedarikciler["uzmanlik"].to_numpy()[ted]
    liste = w.urunler["liste_fiyati"].to_numpy(dtype=float)[hs]
    tarihler = pd.DatetimeIndex(w.takvim["tarih"])
    option_skulari = [np.flatnonzero(w.sku_option == o) for o in range(O)]
    hucre_pencere = lambda d: (w.hucre_acilis <= d) & (d < w.hucre_kapanis)  # noqa: E731
    acik, kapanacak = magaza_takvimi(w, max(D, 1))
    y_m = yolda_gun(w.depo_mesafe_km, depo=True)
    hat_c = hat_indisi(w.magazalar, hm)
    eps_c = np.asarray(w.esneklik_hucre, dtype=float)
    kalite_izi = 1.0 + sabitler.IADE_KALITE_CARPANI * w.gizli_tedarikci["hatali_orani"].to_numpy()[ted][ho]
    p_iade = np.where(onl, sabitler.IADE_ORANI_ONLINE, sabitler.IADE_ORANI_MAGAZA) * kalite_izi
    _, _, icerik = paket_tablosu(w.paketler)
    beden_sira = w.urunler["beden_sira"].to_numpy()
    assert len(np.unique(hs[onl])) == int(onl.sum()), "ONL'de SKU başına tek hücre"

    # Hücre arama: (mağaza, SKU) → hücre
    anahtar = hm.astype(np.int64) * S + hs
    sira = np.argsort(anahtar, kind="stable")
    anahtar_sirali = anahtar[sira]

    def hucre_bul(m: np.ndarray, s: np.ndarray) -> np.ndarray:
        k = np.asarray(m, dtype=np.int64) * S + np.asarray(s, dtype=np.int64)
        i = np.minimum(np.searchsorted(anahtar_sirali, k), C - 1)
        return np.where(anahtar_sirali[i] == k, sira[i], -1)

    z = Durum(D, C, S, O, M)
    kay = Kayit()
    birim_gecmisi = np.zeros((GECMIS_FIYAT, C))
    talep_kaydi = np.zeros((D, C), dtype=np.int16) if kayit_talep else None

    def gorunum(d: int) -> Gorunum:
        acik_sip = tuple(
            {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in s.items()
             if k not in ("gerceklesen_gun", "hatali", "numune", "no")}
            for s in z.siparisler if s["gerceklesen_gun"] > d
        )
        return Gorunum(
            dunya=w, gun=d, tarih=tarihler[d],
            magaza_stok=salt_okunur(z.stok), depo=salt_okunur(z.depo),
            yolda=salt_okunur(z.yolda_hucre),
            satis_gecmisi=salt_okunur(z.satis_gecmisi[:d]),
            stoklu_gecmisi=salt_okunur(z.stoklu_gecmisi[:d]),
            satis_28=salt_okunur(z.satis_28),
            gonderilen_option=salt_okunur(z.gonderilen_option),
            satilan_option=salt_okunur(z.satilan_option),
            rpt_sayisi=salt_okunur(z.rpt_sayisi),
            ilk_dagitim_gun=salt_okunur(z.ilk_dagitim_gun),
            fiyat_orani=salt_okunur(z.fiyat_orani),
            acik_magaza=salt_okunur(acik[d]), kapanacak=salt_okunur(kapanacak[d]),
            acik_siparisler=acik_sip,
        )

    def siparis_ekle(s: dict) -> None:
        s["no"] = len(z.siparisler)
        z.siparis_ekle(s)

    def depodan_hucrelere(d, hucreler, adet, tip, paket=-1):
        """Depodan mağaza hücrelerine sevk (yolda süreyle)."""
        m = hm[hucreler]
        varis = d + y_m[m]
        z.depo -= topla(hs[hucreler], adet, S)
        z.yola_cikar(varis, hucreler, hs[hucreler], adet)
        z.gonderilen_option += topla(ho[hucreler], adet, O)
        kay.sevk(d, varis, -1, m, -1, hucreler, hs[hucreler], adet, tip, paket)

    # --- Başlangıç: devamlılar -------------------------------------------
    baslangic_hedef = np.rint(w.ileri_plan(0, sabitler.REPL_HEDEF_GUN)).astype(np.int64)
    uygun0 = fiz & ~outlet_c & acik[0][hm] & ~kapanacak[0][hm] & ~sezonluk[ho]
    bas_raf = np.where(uygun0, baslangic_hedef, 0)
    bas_raf_sku = topla(hs, bas_raf, S)
    for o in np.flatnonzero(~sezonluk):
        hafta = int(L_o[o]) + sabitler.SUREKLI_GOZDEN_GECIRME_HAFTA + sabitler.SUREKLI_EMNIYET_HAFTA[opt.at[o, "line"]]
        sk = option_skulari[o]
        depo_payi = en_buyuk_kalan(int(round(w.ileri_plan_option(0, 7 * hafta)[o])), w.sku_beden_payi[sk])
        adetler = depo_payi + bas_raf_sku[sk]
        s = {"tip": "baslangic", "option": int(o), "siparis_gun": 0, "planlanan_gun": 0,
             "gerceklesen_gun": 0, "skular": sk, "adetler": adetler, "tedarikci": int(ted[o]),
             "hatali": np.zeros(len(sk), dtype=np.int64), "numune": 0, "no": len(z.siparisler)}
        z.siparisler.append(s)
        z.depo[sk] += adetler
        z.ilk_dagitim_gun[o] = 0
    raf = np.flatnonzero(bas_raf > 0)
    z.depo -= topla(hs[raf], bas_raf[raf], S)
    z.stok[raf] += bas_raf[raf]
    z.gonderilen_option += topla(ho[raf], bas_raf[raf], O)
    kay.sevk(0, 0, -1, hm[raf], -1, raf, hs[raf], bas_raf[raf], "baslangic")

    for s in w.ilk_siparisler:
        siparis_ekle({k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in s.items()})

    # --- Takvimler ---------------------------------------------------------
    ilk_teslim = np.full(O, YOK_GUN)
    for s in w.ilk_siparisler:
        ilk_teslim[s["option"]] = max(int(s["gerceklesen_gun"]), 0)
    depo_gorunur_bas = np.where(sezonluk, ilk_teslim, -1)[w.sku_option]
    depo_gorunur_son = np.where(sezonluk, cikis + 7, YOK_GUN)[w.sku_option]

    aday_magaza = np.zeros((O, M), dtype=bool)
    ilk_aday = fiz & ~outlet_c
    aday_magaza[ho[ilk_aday], hm[ilk_aday]] = True
    karar_gunleri: dict[int, list[int]] = {}
    for o in np.flatnonzero(sezonluk & (ilk_teslim < YOK_GUN)):
        if not aday_magaza[o].any():
            continue
        karar = max(int(lansman[o]) - int(y_m[aday_magaza[o]].max()), int(ilk_teslim[o]), 0)
        karar_gunleri.setdefault(karar, []).append(int(o))
    cikis_gunleri: dict[int, list[int]] = {}
    for o in np.flatnonzero(sezonluk):
        cikis_gunleri.setdefault(int(cikis[o]), []).append(int(o))
    bekleyen_ilk: dict[int, list[tuple]] = {}   # sevk günü → [(o, mağazalar, paketler, paket sayıları)]

    def ilk_sevk(d, o, ms, ps, ns):
        """Paketli ilk dağıtım sevki; paket sayıları depoya sığdırılır."""
        sk = option_skulari[o]
        ic = icerik[ps[:, None], beden_sira[sk][None, :]]            # [n_m, n_s]
        ns = paketleri_sigdir(ns, ic, z.depo[sk])
        dolu = ns > 0
        if not dolu.any():
            return
        ms, ps, ic, ns = ms[dolu], ps[dolu], ic[dolu], ns[dolu]
        adet = (ns[:, None] * ic).ravel()
        hucreler = hucre_bul(np.repeat(ms, len(sk)), np.tile(sk, len(ms)))
        paket = np.repeat(ps, len(sk))
        g = (adet > 0) & (hucreler >= 0)
        depodan_hucrelere(d, hucreler[g], adet[g], "ilk_dagitim", paket[g])

    def transfer_uygula(d: int, tr: Transferler, tip: str) -> None:
        """Genel transfer: kaynak stoğuyla sınırlı, hedefte hücre yoksa atılır."""
        for k, h, s, a in zip(*(np.asarray(x, dtype=np.int64) for x in (tr.kaynak, tr.hedef, tr.sku, tr.adet))):
            if a <= 0 or k == h:
                continue
            kc = int(hucre_bul([k], [s])[0]) if k >= 0 else -1
            hc = int(hucre_bul([h], [s])[0]) if h >= 0 else -1
            if (k >= 0 and kc < 0) or (h >= 0 and hc < 0):
                continue
            a = int(min(a, z.stok[kc] if k >= 0 else z.depo[s]))
            if a <= 0:
                continue
            if k >= 0:
                z.stok[kc] -= a
            else:
                z.depo[s] -= a
            if k >= 0 and h >= 0:
                sure = int(yolda_gun(w.mesafe_km[k, h], depo=False))
            else:
                sure = int(y_m[h if h >= 0 else k])
            z.yola_cikar(np.array([d + sure]), np.array([hc]), np.array([s]), np.array([a]))
            if h >= 0 and k < 0:
                z.gonderilen_option[w.sku_option[s]] += a
            kay.sevk(d, d + sure, k, h, kc, hc, [s], [a], tip)

    # --- Günlük döngü ------------------------------------------------------
    for d in range(D):
        pazartesi = tarihler[d].dayofweek == 0

        # 1) Fotoğraf
        gorunur = np.flatnonzero(
            ((depo_gorunur_bas <= d) & (d <= depo_gorunur_son)) | (z.depo > 0)
        )
        kay.depo.append((d, gorunur, z.depo[gorunur].copy()))
        if pazartesi:
            acik_h = np.flatnonzero(hucre_pencere(d) & fiz & (acik[d][hm] | (z.stok > 0)))
            stoklu_gun = z.stoklu_gecmisi[max(d - 7, 0):d, acik_h].sum(axis=0)
            kay.stok.append((d, acik_h, z.stok[acik_h].copy(), stoklu_gun.astype(np.int64)))

        # 2) Teslim + kalite
        ureticiler: dict[int, np.random.Generator] = {}
        for s in z.teslim_takvimi.pop(d, []):
            o, sk, adetler = s["option"], s["skular"], s["adetler"]
            if "hatali" not in s:
                if o not in ureticiler:
                    ureticiler[o] = sayac_uretici_option(d, "kalite", o, operasyon_tohumu)
                numune, hatali = hatali_adet(
                    ureticiler[o], w.gizli_tedarikci, np.array([s["tedarikci"]]),
                    np.array([int(adetler.sum())]), np.array([uyum_o[o]]),
                )
                s["numune"] = int(numune[0])
                s["hatali"] = en_buyuk_kalan(int(hatali[0]), adetler)
            z.depo[sk] += adetler - s["hatali"]
            z.acik_sku[sk] -= adetler
            kay.kalite.append({
                "gun": d, "siparis": s["no"], "tip": s["tip"], "option": o,
                "tedarikci": s["tedarikci"], "adet": int(adetler.sum()),
                "numune": int(s["numune"]), "hatali": int(np.sum(s["hatali"])),
            })

        # 3) Varışlar
        for hh, sk, ad in z.varanlar(d):
            h = hh >= 0
            z.depo += topla(sk[~h], ad[~h], S)
            hh, sk, ad = hh[h], sk[h], ad[h]
            z.stok[hh] += ad
            kapali = ~acik[d][hm[hh]]
            if kapali.any():
                c, a = hh[kapali], ad[kapali]
                z.stok[c] -= a
                z.depo += topla(hs[c], a, S)
                kay.sevk(d, d, hm[c], -1, c, -1, hs[c], a, "geri_yonlendirme")

        # 4) Olaylar [T14]

        # 5) İlk dağıtım
        for o, ms, ps, ns in bekleyen_ilk.pop(d, []):
            ilk_sevk(d, o, ms, ps, ns)
        if d in karar_gunleri:
            g = gorunum(d)
            for o in karar_gunleri[d]:
                ps = np.asarray(pol.paket_secimi(g, o), dtype=np.int64)
                ns = np.maximum(np.asarray(pol.ilk_dagitim(g, o), dtype=np.int64), 0)
                sevk_gun = np.maximum(int(lansman[o]) - y_m, d)
                varis = np.minimum(sevk_gun + y_m, D - 1)
                ns = np.where(aday_magaza[o] & ~kapanacak[d] & acik[varis, np.arange(M)], ns, 0)
                sk = option_skulari[o]
                ic = icerik[ps[:, None], beden_sira[sk][None, :]]
                ns = paketleri_sigdir(ns, ic, z.depo[sk])
                dolu = np.flatnonzero(ns > 0)
                z.ilk_dagitim_gun[o] = int(sevk_gun[dolu].max()) if dolu.size else d
                for gun in np.unique(sevk_gun[dolu]):
                    mm = dolu[sevk_gun[dolu] == gun]
                    if gun == d:
                        ilk_sevk(d, o, mm, ps[mm], ns[mm])
                    else:
                        bekleyen_ilk.setdefault(int(gun), []).append((o, mm, ps[mm], ns[mm]))

        # 6) Çıkış / outlet akışı [T13]
        if d in cikis_gunleri:
            transfer_uygula(d, pol.outlet_akisi(gorunum(d), np.array(cikis_gunleri[d])), "outlet_akisi")

        if pazartesi:
            g = gorunum(d)
            # 7) RPT [T13]
            for o, miktar in sorted(pol.rpt(g).items()):
                sk = option_skulari[o]
                adetler = (
                    en_buyuk_kalan(int(miktar), w.sku_beden_payi[sk])
                    if np.ndim(miktar) == 0 else np.asarray(miktar, dtype=np.int64)
                )
                if adetler.sum() <= 0:
                    continue
                k = min(int(z.rpt_sayisi[o]), w.sapma_rpt.shape[1] - 1)
                planlanan = d + 7 * int(L_o[o])
                siparis_ekle({
                    "tip": "rpt", "option": int(o), "siparis_gun": d, "planlanan_gun": planlanan,
                    "gerceklesen_gun": planlanan + int(w.sapma_rpt[o, k]),
                    "skular": sk, "adetler": adetler, "tedarikci": int(ted[o]),
                })
                z.rpt_sayisi[o] += 1

            # 8) Sürekli tedarik
            if d % (7 * sabitler.SUREKLI_GOZDEN_GECIRME_HAFTA) == 0:
                surekli_tedarik(w, z, d, sezonluk, L_o, moq_o, ted, option_skulari, siparis_ekle)

            # 9) Markdown [T13]
            yeni = np.asarray(pol.markdown(g), dtype=float)
            degisen = np.argwhere(yeni != z.fiyat_orani)
            if len(degisen):
                kay.fiyat.append((d, degisen[:, 0], degisen[:, 1], yeni[degisen[:, 0], degisen[:, 1]]))
                z.fiyat_orani[:] = yeni

            # 10) Replenishment
            istek = np.asarray(pol.replenishment(g), dtype=np.int64)
            dagitilabilir = (
                (z.ilk_dagitim_gun[ho] < d) & (d < cikis[ho]) & fiz & ~outlet_c
                & acik[d][hm] & ~kapanacak[d][hm]
            )
            gonder = orantili_kes(np.where(dagitilabilir, np.maximum(istek, 0), 0), hs, z.depo)
            hucreler = np.flatnonzero(gonder > 0)
            if hucreler.size:
                depodan_hucrelere(d, hucreler, gonder[hucreler], "replenishment")

            # 11) Elle transfer [T14]
            transfer_uygula(d, pol.elle_transfer(g), "elle_transfer")

        # 12) Fiyat
        u = tekduzeler(d, C, w.tohum, operasyon_tohumu)
        md = z.fiyat_orani[ho, hat_c]
        kamp = w.kampanya_takvimi(d)[hm, ho]
        oran_talep = np.maximum(md, kamp)

        # 13) Talep
        talep = talep_cek(u["talep"], w.lam.gun(d), oran_talep, eps_c)
        if talep_kaydi is not None:
            talep_kaydi[d] = talep

        # 14) Satış
        stoklu = np.where(onl, z.depo[hs] > 0, z.stok > 0)
        satilan = satis_yap(talep, z.stok, z.depo, onl, hs)
        z.stok -= np.where(onl, 0, satilan)
        z.depo -= topla(hs[onl], satilan[onl], S)
        birim, _ = gunun_birim_fiyati(liste, md, kamp, u["indirim"])
        birim_gecmisi[d % GECMIS_FIYAT] = birim
        satan = np.flatnonzero(satilan > 0)
        if satan.size:
            a = satilan[satan]
            kay.satis.append((d, satan, a, np.round(birim[satan] * a, 2),
                              np.round((liste[satan] - birim[satan]) * a, 2), -1))
        kayip = talep - satilan
        kayip_olan = np.flatnonzero(kayip > 0)
        if kayip_olan.size:
            kay.kayip.append((d, kayip_olan, kayip[kayip_olan]))
        z.satis_gecmisi[d] = satilan
        z.satis_28 += satilan
        if d >= sabitler.OLU_STOK_PENCERESI_GUN:
            z.satis_28 -= z.satis_gecmisi[d - sabitler.OLU_STOK_PENCERESI_GUN]
        z.satilan_option += topla(ho, satilan, O)
        z.satilan_option_kum[d + 1] = z.satilan_option

        # 15) İkame [T13]

        # 16) İade
        n = np.zeros(C, dtype=np.int64)
        gecikme = np.where(onl, sabitler.IADE_GECIKME_ONLINE, sabitler.IADE_GECIKME_MAGAZA)
        for gec, maske in ((sabitler.IADE_GECIKME_MAGAZA, fiz), (sabitler.IADE_GECIKME_ONLINE, onl)):
            if d >= gec:
                n[maske] = z.satis_gecmisi[d - gec, maske]
        iade = iade_cek(u["iade"], n, p_iade)
        donen = np.flatnonzero(iade > 0)
        if donen.size:
            a = iade[donen]
            b = birim_gecmisi[(d - gecikme[donen]) % GECMIS_FIYAT, donen]
            kay.satis.append((d, donen, -a, -np.round(b * a, 2), -np.round((liste[donen] - b) * a, 2), -1))
            o_mask = onl[donen]
            z.depo += topla(hs[donen[o_mask]], a[o_mask], S)
            fc, fa = donen[~o_mask], a[~o_mask]
            z.stok[fc] += fa
            kapali = ~acik[d][hm[fc]]
            if kapali.any():
                c, ca = fc[kapali], fa[kapali]
                z.stok[c] -= ca
                z.depo += topla(hs[c], ca, S)
                kay.sevk(d, d, hm[c], -1, c, -1, hs[c], ca, "iade_depoya")

        # 17) Stoklu bayrağı
        z.stoklu_gecmisi[d] = stoklu

    ham = {
        "satis": Kayit.tablo(kay.satis, "hucre", ["adet", "tutar", "indirim_tutari", "kampanya_id"]),
        "gizli_kayip": Kayit.tablo(kay.kayip, "hucre", ["adet"]),
        "ikame_satis": pd.DataFrame(columns=["gun", "hucre", "adet"]),
        "sevkiyat": kay.sevkiyat_tablosu(),
        "stok": Kayit.tablo(kay.stok, "hucre", ["adet", "stoklu_gun"]),
        "depo_stok": Kayit.tablo(kay.depo, "sku", ["adet"]),
        "siparis": z.siparisler,
        "kalite": pd.DataFrame(
            kay.kalite,
            columns=["gun", "siparis", "tip", "option", "tedarikci", "adet", "numune", "hatali"],
        ),
        "fiyat": Kayit.tablo([(p[0], p[1], p[2], p[3]) for p in kay.fiyat], "option", ["hat", "oran"]),
        "son_durum": {
            "magaza_stok": z.stok, "depo": z.depo,
            "yolda_hucre": z.yolda_hucre, "yolda_depo": z.yolda_depo,
            "fiyat_orani": z.fiyat_orani,
        },
        "gun_sayisi": D,
    }
    if talep_kaydi is not None:
        ham["talep"] = talep_kaydi
    return ham
