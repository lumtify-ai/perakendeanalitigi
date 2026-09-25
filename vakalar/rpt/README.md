# RPT — tekrar sipariş

Lumoda v3 sentetik verisi üstünde tedarikçiye tekrar sipariş (RPT) vakası.
Sitedeki `/planlama/rpt/` dizisinin bütün sayıları buradan çıkar. Tasarım:
`docs/superpowers/specs/2026-09-26-veri-v3-ve-rpt-design.md`, bölüm 3.

RPT burada **tedarikçiye verilen tekrar üretim siparişidir**; depodan mağazaya
tekrar sevkiyat (replenishment) değildir. Sezon başındaki ilk alım ve ilk
dağıtım veriden aynen alınır, bu vakanın konusu değildir.

## Kurulum ve koşum

    cd vakalar/rpt
    python -m venv .venv
    .venv/Scripts/python -m pip install -e ../../veri -e ".[dev]"
    .venv/Scripts/python -m pytest -q          # testler (hızlı + @pytest.mark.veri)

Veri yoksa önce üret: `cd veri && .venv/Scripts/python -m perakende_veri.v3.uret`

Yazıların alıntıladığı bütün sayıları basmak (~30 sn):

    .venv/Scripts/python rapor.py > cikti/rapor.txt

Windows konsolunda Türkçe karakter için `PYTHONIOENCODING=utf-8`.

## Durum

**Faz A (bu sürüm):** veri paneli, yaşam eğrisi, sansürlü talep kestirimi ve
ilk üç yazının sayıları. **Faz B (sırada):** aday modeli, newsvendor miktarı,
dağıtım kuralları, kollar (`rpt_yok`, `mevcut`, `frr`, `oneri`, `kahin`…) ve
alternatif talep yolları. Faz B motor yazmaz: aynı talebi v3'ün
`simule_et(dunya, talep, rpt_politikasi=..., dagitim_politikasi=...)`'i ile
farklı politikalarla yeniden oynatır; kaynak panelleri kolların çıktısına
(`hareket_tablolari`) aynen uygulanır.

## Modüller

| Modül | İşi |
|---|---|
| `kaynak.py` | v3 DuckDB tablolarını okur, kirli kayıtları ayıklar; hücre-hafta (mağaza × SKU × lansmandan beri hafta) ve option-hafta panelleri; `tarihten_once` ile karar sabahına kırpma |
| `egri.py` | Yaşam eğrisinin **şekli** (birikimli pay k_h), geçmiş sezonlardan: çıplak (sansürlü satış), stoklu gün düzeltmeli (Poisson IPF), gerçek (yalnız kıyas) |
| `sansur.py` | Sezon talebi kestirimi, dört katman (a çıplak · b stoklu gün hızı · c FRR eğri ölçeği · d b+c), gerçek talebe karşı hata |
| `hikaye.py` | "Bitti" haftası, hikâye adayları, mağaza tablosu, Lumoda'nın RPT'lerinin akıbeti |
| `rapor.py` | Yayımlanacak her sayı (HİKÂYE · KARAR · SANSÜR bölümleri) |

## İlkeler

- **Bilgi bu sezondan.** RPT kararının seviyesi (ürün ne kadar tutuyor) içinde
  bulunulan sezonun erken haftalarından gelir; geçmiş sezonlardan yalnız
  eğrinin **şekli** öğrenilir (kullanıcının "RPT geçmişe değil bu sezona
  bakar" cümlesi).
- **Sızıntı yok.** Oyun sezonları AW24 ve SS25. Eğri, tabloların oyun
  sezonunun ilk lansman sabahına kırpılmış hâlinden ve yalnız o güne kadar
  indirimi başlamış tam sezonlardan öğrenilir (AW24 ← SS24; SS25 ← SS24 +
  AW24). AW23 pencerede indirim öncesine yalnız bir günle göründüğü için
  kullanılmaz. Kestirim h. pazartesiden sonraki satırı okumaz. Üçü de testle
  kilitli (`test_sizinti_kalkani_egri_gelecegi_gormez`,
  `test_kestirim_kirpilmis_veriyle_ayni`).
- **Kayıp satış yalnız doğruluk ölçüsüdür.** Gerçek talep = satış + kayıp;
  hiçbir kestirim kayıp kolonunu okumaz (`test_kestirim_kayip_satisi_okumaz`).
  Raporda kayıp satıştan gelen her sayı "[gerçek, zincir görmez]" diye
  işaretlidir.
- **Sezon talebi = lansman → indirim başı** (FRR'nin "sezon"u). Çıkışa kadarki
  talep de ayrıca raporlanır (RPT'nin indirimde satacağı kısım için).
- **Plan gizli değildir.** Buyer planı (`plan_sezon`) tablolarda yok, dünyadan
  okunur; ama ilk alım ondan hesaplandı, zincir bu sayıyı bilir. Sürpriz ve
  gerçek beklenen talep okunmaz.

## Tanımlar

- **Hafta h:** lansmandan itibaren [lansman + 7h, lansman + 7h + 7). h.
  haftanın stoklu günü (h+1). pazartesinin fotoğrafındadır.
- **Tutan (hit):** gerçek talep / plan ≥ 1,5 (spec 2.12).
- **Bitti:** pazartesi sabahı depo ≤ ilk alımın %2'si ve depo + mağaza ≤ %20'si.
- **RPT akıbeti:** depo partiyi ayırt etmez; çıkışta depoda kalan (en fazla RPT
  kadar) RPT'den kalmış sayılır (FIFO). RPT'yi olduğundan iyi gösteren atama.

## Bilinen sınırlar ve veriden çıkan sürprizler

- **Üçüncü haftada biten tutan ürün yok.** SS25'in 16 tutan option'ından
  hiçbiri 3. hafta pazartesisine kadar "bitmiyor"; en erken biten (MDL190-HAK,
  yerli, planın 3,6 katı) 4. hafta pazartesisi biter, çoğu 6.–7. haftada.
  3. hafta pazartesisi, Lumoda'nın kuralının tetiklendiği gündür: depo o sabah
  son partiyi mağazalara gönderir. Hikâyenin haftası buna göre seçilmeli
  (rapor iki pazartesiyi de basar).
- **Stoklu gün düzeltmesi gün içi tükenmeyi göremez.** Hızlı satan hücre güne
  birkaç adetle açılır, öğleden sonra biter; o gün "stoklu" sayılır. Tutan
  ürünlerde düzeltme gerçek kaybın yarısı kadarını geri kazanır.
- **AW24'ün eğrisi yalnız bir bahar sezonundan** (SS24) öğrenilir; kış
  mevsimselliği farklıdır. AW24 hataları SS25'ten büyüktür.
- **Eğri gruplaması:** üst kategori × dalga, yalnız dalgadan kötü (grup başına
  birkaç option; gürültü). Seçilen: yalnız dalga.
- **Çıkış hedefli eğri** (`hedef="cikis"`), geçmiş sezonun çıkışı oyun
  başlangıcından sonraysa o sezonun son haftalarını göremez (AW24 için SS24'ün
  son haftası, SS25 için AW24'ün son iki haftası).
- İkame (stoksuz ürünün talebinin başka ürüne kayması) ve sergi etkisi v3'te
  modellenmez.
