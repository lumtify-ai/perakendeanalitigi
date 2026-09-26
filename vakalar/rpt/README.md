# RPT — tekrar sipariş

Lumoda v3 sentetik verisi üstünde tedarikçiye tekrar sipariş (RPT) vakası.
Sitedeki `/rpt/tekrar-siparis/` dizisinin bütün sayıları buradan çıkar. Tasarım:
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

Alternatif talep yollarını koşmak (10 yol, 4 süreç paralel, ~6 dk; önce bu):

    .venv/Scripts/python -m rpt.yollar          # cikti/yollar.json

Yazıların alıntıladığı bütün sayıları basmak (~2 dk; yol 0'ı baştan koşar):

    .venv/Scripts/python rapor.py > cikti/rapor.txt

Windows konsolunda Türkçe karakter için `PYTHONIOENCODING=utf-8`.

## Durum

**Faz A:** veri paneli, yaşam eğrisi, sansürlü talep kestirimi ve ilk üç
yazının sayıları. **Faz B:** aday modeli, newsvendor miktarı, dağıtım
kuralları, kollar ve alternatif talep yolları (4.–6. yazılar). Motor
yazılmaz: aynı talep v3'ün `simule_et(dunya, talep, rpt_politikasi=...,
dagitim_politikasi=...)`'i ile farklı politikalarla yeniden oynatılır
(bir koşu ~3 sn).

## Modüller

| Modül | İşi |
|---|---|
| `kaynak.py` | v3 DuckDB tablolarını okur, kirli kayıtları ayıklar; hücre-hafta (mağaza × SKU × lansmandan beri hafta) ve option-hafta panelleri; `tarihten_once` ile karar sabahına kırpma |
| `egri.py` | Yaşam eğrisinin **şekli** (birikimli pay k_h), geçmiş sezonlardan: çıplak (sansürlü satış), stoklu gün düzeltmeli (Poisson IPF), gerçek (yalnız kıyas) |
| `sansur.py` | Sezon talebi kestirimi, dört katman (a çıplak · b stoklu gün hızı · c FRR eğri ölçeği · d b+c), gerçek talebe karşı hata |
| `hikaye.py` | "Bitti" haftası, hikâye adayları, mağaza tablosu, Lumoda'nın RPT'lerinin akıbeti |
| `anlik.py` | Karar anı hesapları `Gorunum` üstünde (düzeltilmiş talep, option özeti); `Kaydedici` her pazartesi aday satırı kaydeder — eğitim ve karar aynı kodu görür |
| `dagitim.py` | RPT dağıtım kuralları: mevcut · b stoklu gün hızı · c yeniden lansman · d c + %30 depoda tutma |
| `miktar.py` | Banu %50 · FRR · newsvendor (belirsizlik geçmiş sezon hatasından, MOQ kapısı) |
| `aday.py` | Özellikler, sonradan-bakış etiketi (gerçek ve düzeltilmiş), kural / lojistik / LightGBM, TL değerlendirme |
| `politika.py` | Kollar: `rpt_yok`, `mevcut`, `frr` (h=2/3), `oneri`, `kahin` |
| `oyun.py` | Hazırlık (yolun gerçekleşen tarihi + öğrenme), dağıtım kuralı seçimi (SS24), kol koşuları |
| `olcutler.py` | Spec 3.4 ölçütleri, option düzeyinde, rpt_yok tabanına göre |
| `yollar.py` | 10 alternatif talep yolu, paralel, JSON |
| `rapor.py`, `rapor_b.py` | Yayımlanacak her sayı (HİKÂYE · KARAR · SANSÜR · ADAY · MİKTAR · SONUÇ) |

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

## Faz B'nin kurulumu

- **Kollar yalnız oyun sezonlarının (AW24, SS25) Collection option'larına
  dokunur**; öteki bütün option'larda Banu'nun kuralı ve bugünkü dağıtım
  işler. Dağıtım kuralları yalnız RPT'si GELMİŞ option'lara uygulanır: RPT'siz
  kolda b/c/d bugünkü kuralla birebir aynıdır (testli). Fark RPT'nin kendisinden
  gelir.
- **Kollar arası gürültü yok.** v3'ün iade ve işlem indirimi rastgeleliği (gün,
  hücre) başına tohumlanır ve politikadan bağımsızdır (`simule_et(...,
  operasyon_tohumu=42)`): RPT'si olmayan bir option her kolda birebir aynı
  sonuçlanır (testli). Alternatif yollar kendi operasyon tohumunu kullanır.
- **`mevcut` kolu v3'ün kendisidir**: dışa aktarılan tablolar birebir
  (`test_esdegerlik.py`).
- **Öğrenme** (eğri, belirsizlik, aday modeli) her yolun "gerçekleşen tarihi"nden
  (Banu'nun kuralı + bugünkü dağıtım), oyun sezonunun ilk lansman sabahına
  kırpılarak, yalnız önceki sezonlardan. **Dağıtım kuralı** oyundan önce SS24'te
  seçilir (Banu'nun RPT'leriyle, en yüksek SS24 kârı).
- **Değerleme:** gelir − (ilk alım + RPT) × alış; sezon sonunda kalan stok 0 TL
  (alt sınır). Taban `rpt_yok`.
- **Kâhin üst sınır değildir:** gerçek talebi ve teslim gecikmesini bilir ama
  zincir düzeyinde düşünür; mağazalar arası sıkışmayı ve dağıtımı bilmez. Kâr
  ölçütü indirimde satışı da içerdiği için tam fiyattan MOQ/2 satamayan ama
  kârlı siparişler verebilir (ölçütte "yanlış alarm" sayılır).
- **Sızıntı kalkanları (testli):** kâhin dışındaki kollar sonraki talebi
  bozunca aynı RPT'leri verir (kâhin vermez); kalibrasyon ve eğri oyun
  başlangıcından sonraki veri bozulunca değişmez; aday eğitimi yalnız önceki
  sezonlardan.

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
- **SS25'in öğrenmesi AW24'ün gerçekleşen (Banu'lu) tarihinden**; bir kol
  AW24'te başka RPT verseydi SS25'e giden geçmiş biraz farklı olurdu.
- **Belirsizlik (σ) kısmen örneklem içi**: SS24'ün öncesi olmadığı için SS24
  kestirimleri oyun sezonunun eğrisiyle yapılır.
- **AW24 aday modeli yalnız SS24'ün 483 satırından (22 pozitif) eğitilir** —
  kırılgan; rapor bunu yazar.
- **Uzak Doğu RPT'si pratikte hiç aday değil**: eğitim sezonlarında 14–15
  haftalık tedarikle etiketi pozitif tek satır yok; model Uzak Doğu'ya hiç RPT
  önermez.
- Aday etiketi ve newsvendor zincir düzeyinde stok akışı varsayar (mağazalar
  arası sıkışma yok): RPT lehine iyimser.
- İade oranı newsvendor'da yok sayılır; motor iadeyi satışla orantılı üretir.
