"""Yazıların alıntıladığı bütün sayıları gerçek veriden basar.

    .venv/Scripts/python rapor.py

Yazı düzenlerken tek kaynak budur. Model spec §1: uydurma sayı yasaktır.
"""
from dataclasses import replace

import pulp

import getiri
from blok_transfer import degerlendirme
from blok_transfer.cekirdek import adaylar as adaylar_mod
from blok_transfer.cekirdek import metrikler, terazi, veri
from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cozuculer import mip

REFERANS = Parametreler()          # verici ≥ 6, alıcı tavanı kapalı, min_satis 1


def _kesirli(degiskenler) -> int:
    """Kaç tanesi ne 0 ne 1; yani gevşetme gerçekten gevşemiş mi."""
    return sum(
        1
        for d in degiskenler
        if d.value() is not None and 1e-6 < d.value() < 1 - 1e-6
    )


def _lp_bosluk(df, kapasite, p) -> tuple[float, float, int, int]:
    """(LP gevşetmesi, tam sayı çözüm, kesirli x sayısı, kesirli y sayısı)."""
    model, x, y = mip.kur(df, kapasite, p)
    for degisken in list(x.values()) + list(y.values()):
        degisken.cat = pulp.LpContinuous
        degisken.lowBound, degisken.upBound = 0, 1
    model.solve(pulp.PULP_CBC_CMD(msg=0))
    gevsek = pulp.value(model.objective)
    kesirli_x, kesirli_y = _kesirli(x.values()), _kesirli(y.values())
    plan = mip.cozumle(df, kapasite, p)
    ozet = degerlendirme.ozetle(plan, p)
    return gevsek, ozet["net_kazanc_tl"], kesirli_x, kesirli_y


def _rota_dagilimi(plan) -> dict[int, int]:
    """Rota başına taşınan option sayısının dağılımı: {1: 147, 2: 42, ...}."""
    h = plan.hareketler
    if not len(h):
        return {}
    sayim = h.groupby(["verici", "alici"]).size().value_counts()
    return {int(k): int(sayim[k]) for k in sorted(sayim.index)}


def _farkli_alici(a_plan, b_plan) -> tuple[int, int]:
    """(iki planın ortak (verici, option) bloğu, bunların kaçında alıcı farklı)."""

    def harita(plan):
        h = plan.hareketler
        return {(v, o): al for v, al, o in zip(h.verici, h.alici, h.option_id)}

    a, b = harita(a_plan), harita(b_plan)
    ortak = set(a) & set(b)
    return len(ortak), sum(1 for k in ortak if a[k] != b[k])


def main() -> None:
    con = veri.baglan()
    karar = veri.karar_tarihi(con)
    kapasite = adaylar_mod.kapasite_boslugu(con, karar)

    magaza_sayisi = con.execute("select count(*) from magaza").fetchone()[0]
    option_sayisi = con.execute("select count(distinct option_id) from urun").fetchone()[0]
    kiriklar = metrikler.kiriklar(con, karar)

    print("=== VERİ ===")
    print(f"mağaza {magaza_sayisi} · option {option_sayisi}")
    print(f"kırık (mağaza, option) çifti: {len(kiriklar)}")
    print(f"kırık × alıcı adayı: {len(kiriklar)} × {magaza_sayisi - 1} = "
          f"{len(kiriklar) * (magaza_sayisi - 1):,}")
    print(f"kombinatorik üst sınır: {magaza_sayisi} × {magaza_sayisi - 1} × "
          f"{option_sayisi} = {magaza_sayisi * (magaza_sayisi - 1) * option_sayisi:,}")

    df = terazi.agirliklandir(adaylar_mod.uret(con, karar, REFERANS), REFERANS)
    rotalar = sorted(set(zip(df.verici, df.alici)))
    blok_kisiti = len(df.groupby(["verici", "option_id"]))
    kapasite_kisiti = df.alici.nunique()
    rota_bagi = len(df)
    koli_kisiti = len(rotalar)

    print("\n=== REFERANS SENARYO (verici ≥ 6 · alıcı tavanı kapalı) ===")
    print(f"aday: {len(df)}")
    print(f"x değişkeni {len(df)} + y değişkeni {len(rotalar)} = "
          f"{len(df) + len(rotalar)} ikili değişken")
    print(f"kısıt: blok {blok_kisiti} + kapasite {kapasite_kisiti} + "
          f"rota bağlama {rota_bagi} + koli {koli_kisiti} = "
          f"{blok_kisiti + kapasite_kisiti + rota_bagi + koli_kisiti}")

    kirik_kume = set(zip(kiriklar.magaza_id, kiriklar.option_id))
    planlar = {}
    for yontem in ("greedy", "mip"):
        plan, ozet = degerlendirme.boru_hatti(con, karar, REFERANS, yontem)
        planlar[yontem] = plan
        yakalama = degerlendirme.kayip_satis_yakalama(plan, con, karar)
        h = plan.hareketler
        dagilim = _rota_dagilimi(plan)
        adreslenen = len(
            {(a, o) for a, o in zip(h.alici, h.option_id) if (a, o) in kirik_kume}
        )
        print(f"\n--- {yontem} ---")
        for ad, deger in ozet.items():
            print(f"  {ad}: {deger:,}" if isinstance(deger, int) else f"  {ad}: {deger}")
        print(f"  kayip_yakalama: {yakalama:.1%}")
        print("  rota başına option dağılımı: "
              + " · ".join(f"{k}→{dagilim[k]}" for k in sorted(dagilim)))
        print(f"  adreslenen kırık çift: {adreslenen}")

    sayac = planlar["greedy"].sayaclar
    print("\n=== AÇGÖZLÜ ADIM TABLOSU ===")
    print(f"  SQL'in bulduğu aday: {len(df)}")
    print(f"  puanı pozitif olan: {sayac['pozitif']}")
    print(f"  'bu blok zaten verildi' diye atlanan: {sayac['blok']}")
    print(f"  kapasite yüzünden atlanan: {sayac['kapasite']}")
    print(f"  seçilen hareket: {sayac['secilen']}")
    print(f"  minimum koli filtresinin kestiği: {sayac['min_koli_kesilen']}")

    ortak, farkli = _farkli_alici(planlar["greedy"], planlar["mip"])
    print(f"\nİki planın ortak (verici, option) bloğu: {ortak} · "
          f"alıcısı farklı olan: {farkli}")

    gevsek, tam, kesirli_x, kesirli_y = _lp_bosluk(df, kapasite, REFERANS)
    print(f"\nLP gevşetmesi {gevsek:,.2f} · tam sayı {tam:,.2f} · "
          f"boşluk {gevsek - tam:,.2f} TL ({(gevsek - tam) / tam:.4%})")
    print(f"gevşetilmiş çözümde kesirli çıkan: {kesirli_x}/{len(df)} x · "
          f"{kesirli_y}/{len(rotalar)} y")

    print("\n=== GETİRİ ===")
    strler = metrikler.strler(con, karar)
    str_haritasi = {
        (m, o): s
        for m, o, s in zip(strler.magaza_id, strler.option_id, strler.str_orani)
    }
    g = planlar["greedy"].hareketler
    str_verici = [str_haritasi[(v, o)] for v, o in zip(g.verici, g.option_id)
                  if (v, o) in str_haritasi]
    str_alici = [str_haritasi[(a, o)] for a, o in zip(g.alici, g.option_id)
                 if (a, o) in str_haritasi]
    print(f"  STR: verici ortalaması %{sum(str_verici) / len(str_verici) * 100:.1f} → "
          f"alıcı ortalaması %{sum(str_alici) / len(str_alici) * 100:.1f}")

    # "Adreslenen kırık çift"in ayna görüntüsü: alıcı tarafında kaç kırığı
    # kapattığımızı sayıyoruz, burada verici tarafında kaç kırık açtığımızı.
    # Ayrıca yazılmış bir kısıt yok; aday üretimi kırık rafı verici saymıyor.
    # Yayımlanan "hiçbir hareket kırık seti verici yapmıyor" cümlesinin kanıtı
    # bu satır, ve sıfır kalmaya devam ettiği burada görülüyor.
    kirik_verici = len(
        {(v, o) for v, o in zip(g.verici, g.option_id) if (v, o) in kirik_kume}
    )
    print(f"  kırık seti verici yapan çift: {kirik_verici}")

    # Modelin örtük olasılığı: min(adet, hız × ufuk) / adet. Yazının çekirdek
    # karşıtlığı bu sayıdır — sahada alıcı tarafında %70 üstü istisnadır.
    olasilik = g.merge(
        df[["verici", "alici", "option_id", "hiz_verici", "hiz_alici"]],
        on=["verici", "alici", "option_id"], how="left",
    )
    H = REFERANS.ufuk_hafta
    p_alici = (olasilik.hiz_alici * H / olasilik.adet).clip(upper=1.0)
    p_verici = (olasilik.hiz_verici * H / olasilik.adet).clip(upper=1.0)
    print(f"  modelin varsaydığı satma oranı — alıcı: ort %{p_alici.mean() * 100:.1f}, "
          f"medyan %{p_alici.median() * 100:.1f}")
    print(f"  kalsaydı satma oranı          — verici: ort %{p_verici.mean() * 100:.1f}, "
          f"medyan %{p_verici.median() * 100:.1f}")
    print(f"  alıcıda %100'e dayanan hareket: {int((p_alici >= 1).sum())}/{len(olasilik)} · "
          f"vericide %0: {int((p_verici <= 0).sum())}/{len(olasilik)}")
    # Hesabın iki ölçülen tabanı: brüt kâr olasılık farkının çarpıldığı sayı,
    # maliyet değeri de yıpranmanın oranlandığı sayı. İkisi de `urun`
    # tablosundaki fiyatlardan çıkıyor, yani yazıdaki tutarların kaynağı bu.
    hareketler = getiri.hareketleri_getir(con, karar)
    toplam_adet = int(hareketler.adet.sum())
    rota = len(hareketler.groupby(["verici", "alici"]))
    brut_kar = float((hareketler.adet * (hareketler.liste - hareketler.alis)).sum())
    maliyet_degeri = float((hareketler.adet * hareketler.alis).sum())
    ciro_listesi = float((hareketler.adet * hareketler.liste).sum())
    print(f"\n  brüt kâr (liste − alış) {brut_kar:,.2f} TL · "
          f"maliyet değeri (alış) {maliyet_degeri:,.2f} TL")
    print(f"  taşınan adet {toplam_adet:,} · sevkiyat {rota} · "
          f"liste değeri {ciro_listesi:,.2f} TL")

    # Kâr katmanının ciro katmanına ne kattığı, veri setinin marjına bağlı.
    # Bu sentetik sette alış/liste oranı sabit; yani kâra çevirmek ölçeği
    # değiştirir, sıralamayı değiştirmez. Yazı bunu söylemek zorunda.
    urun_sayisi, oran_min, oran_maks = con.execute(
        "select count(*), min(alis_fiyati / liste_fiyati), "
        "max(alis_fiyati / liste_fiyati) from urun"
    ).fetchone()
    print(f"  brüt marj (brüt kâr / liste değeri) %{brut_kar / ciro_listesi * 100:.1f}")
    print(f"  alış/liste oranı: {urun_sayisi:,} ürünün hepsinde "
          f"{oran_min:.4f} (min {oran_min:.6f} · maks {oran_maks:.6f}) → "
          f"marj ürüne göre değişmiyor")

    # Net kârı p_a=100 / p_v=0 ile basıyoruz: o noktada olasılık farkı 1
    # olduğu için net kâr doğrudan "brüt kâr − maliyet"i gösterir ve paketler
    # arasındaki fark çıplak okunur. Başabaş fark zaten kadranlardan bağımsız,
    # bu yüzden hangi noktada bastığımızdan etkilenmiyor.
    print("\n  maliyet paketleri (getiri.py):")
    for ad in getiri.PARAMETRELER[2]["degerler"]:
        paket = getiri.MALIYET_PAKETLERI[ad]
        sonuc = getiri.hesapla(hareketler, paket, 100.0, 0.0)
        toplama = paket.toplama_birim_tl * toplam_adet
        kargo = paket.kargo_rota_tl * rota
        yipranma = paket.yipranma_orani * maliyet_degeri
        print(f"    {ad:7} başabaş fark {sonuc['basabas_fark_puan']:>5.1f} puan · "
              f"net kâr (100/0) {sonuc['net_kar_tl']:>12,.0f} TL")
        print(f"            toplama {toplama:>10,.0f} · kargo {kargo:>10,.0f} · "
              f"yıpranma {yipranma:>10,.0f} · toplam {toplama + kargo + yipranma:>11,.0f} TL")
        print(f"            yıpranma adet başına {yipranma / toplam_adet:>6,.2f} TL")

    print("\n=== DEMO KADRANI ===")
    for vv, aa in [(6, 0), (6, 3), (6, 6), (14, 6), (18, 14), (26, 6)]:
        p = replace(REFERANS, verici_cover_esigi=float(vv), alici_cover_tavani=float(aa))
        satir = []
        for yontem in ("greedy", "mip"):
            plan, ozet = degerlendirme.boru_hatti(con, karar, p, yontem)
            oran = degerlendirme.kayip_satis_yakalama(plan, con, karar)
            satir.append(
                f"{yontem} {ozet['option_sayisi']} hrkt / {ozet['rota_sayisi']} rota / "
                f"{ozet['net_kazanc_tl']:,.0f} TL / {oran:.1%}"
            )
        etiket = "kapalı" if aa == 0 else str(aa)
        print(f"  verici≥{vv:<3} alıcı≤{etiket:<6} | " + "  ·  ".join(satir))


if __name__ == "__main__":
    main()
