# Lumoda — Sentetik Moda Perakende Veri Seti

perakendeanalitigi.com'daki vakalar bu veri setini kullanır.
Veri **tamamen sentetiktir**; hiçbir gerçek şirket, müşteri veya kişi
verisi içermez. Lumoda kurgusal bir moda perakende zinciridir.

## Sürümler

| Sürüm | Kapsam | Kim kullanır | Durum |
|---|---|---|---|
| **v2** | 2025, 80 model, sonsuz depo | `vakalar/blok-transfer`, `vakalar/replenishment`, yayımlanmış 14 yazı | **Dondurulmuş** |
| **v3** | 2024–2025, 242 model, sezon/dalga, tedarik, sonlu depo, RPT | `vakalar/rpt`, RPT dizisi | **Dondurulmuş** |
| **v4** | 2023–2025, 84 mağaza + online, 1.870 option, gizli segment, markdown, kampanya, ikame, açılış/kapanış, 18 tedarikçi, plan tabloları; B katmanı: müşteri, fiş, online davranış, yorum | Henüz yok; vakalar ve yazılar v4'e taşınacak | Yeni — aşağıda |

**v2 dondurulmuştur.** Modülleri (`perakende_veri/*.py`), tohumu ve çıktısı
bayt bayt aynı kalır; `tests/test_v2_donuk.py` her tablonun satır sayısını
ve içerik özetini (sıralı satırların sha256'sı) sabit değerlere karşı sınar.
v3 ayrı bir alt pakettir (`perakende_veri/v3/`); v2'nin mağaza, beden ve
talep çarpanlarını içe aktarır, değiştirmez.

**v3 de dondurulmuştur.** Aynı kilit `tests/test_v3_donuk.py`'de: v3'ün
modülleri, tohumu ve çıktısı artık değişmez.

v4 ayrı bir alt pakettir (`perakende_veri/v4/`). v2'yi ve v3'ü içe
aktarmaz; yalnız kökteki dışa aktarma fonksiyonunu kullanır.

Aşağıdaki bölümler sırayla v2'yi, v3'ü ve v4'ü anlatır.

# v2

## Kapsam

25 mağaza · 80 model → 240 option → 1.200 SKU · 2025 yılının tamamı

| Kimlik düzeyi | Örnek | Anlamı |
|---|---|---|
| model | `MDL003` | Ürün kodu + ürün adı. Tasarım; fiyat bu düzeyde belirlenir. |
| option | `MDL003-SYH` | Model × renk. Planlamanın ve transfer kararının birimi. |
| SKU | `MDL003-SYH-M` | Option × beden. En alt stok birimi. |

Kimlik okunabilir kurulmuştur: **SKU = ürün kodu – renk kodu – beden**.
Bir rapor satırına bakan kişi hangi model, hangi renk, hangi beden
olduğunu id'nin kendisinden görür.

## Tablolar

| Tablo | Satır | Açıklama |
|---|---:|---|
| `magaza` | 25 | Mağaza master'ı: şehir, tip, metrekare, kapasite |
| `urun` | 1.200 | SKU master'ı ve ürün hiyerarşisi |
| `takvim` | 365 | Tarih boyutu: hafta, ay, sezon, tatil |
| `satis` | ~532 bin | Günlük satış. **Negatif adet = iade.** |
| `stok` | ~643 bin | Haftalık stok fotoğrafı (pazartesileri) |
| `sevkiyat` | ~179 bin | Depodan mağazaya giren mal |
| `kayip_satis` | ~46 bin | Stoksuzluk yüzünden karşılanamayan talep |

### Ürün hiyerarşisi

Moda perakendesinde hiyerarşi bir sınıflandırma değil, **kararın kendisidir**:
transfer, ikmal ve sevkiyat algoritmalarının hepsi kapsamını bu ağaç üzerinden
tanımlar.

```
cinsiyet             Kadın · Erkek · Unisex
  ust_kategori       Üst Giyim · Alt Giyim · Dış Giyim
    alt_kategori     Tişört · Gömlek · Pantolon · Mont · …
      line           Basic · Collection · NOS · Outlet
        model        MDL003 "Balıkçı Yaka Kazak"
          option     MDL003-SYH
            SKU      MDL003-SYH-M
```

**Line** ürünün ticari rolünü ve yaşam döngüsünü söyler. Sezonluk/devamlı
ayrımı ayrı bir eksen değildir; line onu zaten taşır:

| Line | Anlamı | Sezon etkisi | Moda riski |
|---|---|---|---|
| `Basic` | Yıl boyu satılan temel ürün | Düşük | Düşük |
| `Collection` | Sezonluk koleksiyon | Tam | **Yüksek** |
| `NOS` | Never Out of Stock — stoğu asla bitmemeli | Neredeyse yok | En düşük |
| `Outlet` | Geçmiş sezondan devreden | Orta | Orta |

Outlet line'ı ağırlıklı olarak outlet mağazalarda bulunur (%15'e karşı %3).
Blok Transfer'in doğal kısıtlarından biri budur: outlet ürününü vitrin
mağazasına göndermek çözüm değildir.

### Beden setleri

Beden tek bir ölçek değildir. Üst giyim harfle, alt giyim numarayla gider;
kadın ve erkek numaraları ayrıdır:

| Beden seti | Kademeler |
|---|---|
| Kadın Harf | XS · S · M · L · XL |
| Kadın Numara | 34 · 36 · 38 · 40 · 42 |
| Erkek Harf | S · M · L · XL · XXL |
| Erkek Numara | 30 · 32 · 34 · 36 · 38 |
| Unisex Harf / Numara | Erkek setleriyle aynı |

Bu yüzden analiz beden **etiketine** değil `beden_sira` kolonundaki
**sıraya** bakar (1…5). Kırıklık — ara bedenlerin tükenip uçların kalması —
etiket üzerinden tanımlanamaz: pantolonda "M" diye bir beden yoktur.
Talep eğrisi de aynı sebeple konumla tanımlıdır; her sette orta kademeler
satar, uçlar durur.

## Kullanım

En hızlı yol DuckDB dosyasıdır; kurulum gerektirmez:

```sql
-- Beden seti bozulmuş (mağaza, option) çiftleri:
-- stok var ama ara bedenler tükenmiş
WITH son AS (SELECT max(tarih) AS t FROM stok)
SELECT st.magaza_id, u.option_id, any_value(u.model_adi) AS urun,
       sum(st.adet) AS kalan_stok
FROM stok st JOIN urun u USING (urun_id), son
WHERE st.tarih = son.t
GROUP BY 1, 2
HAVING sum(st.adet) > 0
   AND count(*) FILTER (WHERE st.adet = 0 AND u.beden_sira IN (2, 3, 4)) > 0
ORDER BY kalan_stok DESC;
```

CSV ve Parquet sürümleri de aynı klasörde yayımlanır.

## Verinin kasten kusurlu yanları

Sentetik verinin klasik tuzağı fazla temiz olmasıdır. Aşağıdakiler
**bilinçli olarak** üretilir; hata değildir:

| Kusur | Neden var |
|---|---|
| Kayıp satış | Raf boşken gelen müşteri kaydedilmez; talep sansürlüdür |
| Ölü stok | Bazı option'lar bazı mağazalarda hiç tutmaz |
| Beden dengesizliği | Mağazanın beden eğrisi zincirin planından sapar |
| Kırıklık | 528 (mağaza, option) çiftinde ara bedenler tükenmiş |
| İade | Satışın ~%6'sı negatif satır olarak geri döner |
| Mükerrer satır | Çift girilmiş satışlar |
| Bedelsiz satır | `adet` dolu, `tutar` sıfır — manuel giriş hatası |
| Hayalet stok | Mağazanın çeşidinde olmayan üründe stok görünmesi |

Kirli kayıtlar satırların binde birinden azdır: veriyi kullanılamaz hale
getirmeden temizlik işini geri koyarlar.

### Dengesizlik nereden geliyor?

Bu veri setinin tek en önemli tasarım kararı budur. İkmal, **zincir
genelinde kurulmuş bir plana** göre yapılır: "bu tip mağazada bu üründen
haftada şu kadar satar". Gerçek talep ise **yereldir** — bir option bir
mağazada tutar, diğerinde hiç tutmaz; beden eğrisi semtten semte değişir.

Plan ile gerçek arasındaki bu fark bir yerde ölü stok, bir yerde
stoksuzluk üretir. İkmal her mağazayı kendi gerçek talebine göre
doldursaydı plan hep doğru çıkar ve **transfer edilecek bir şey olmazdı.**
Bu yüzden ikmal, bir hücrede kendi gerçekleşen satış hızına göre zaten
6 haftadan fazla stok varsa oraya mal göndermez — ölü stoğun üstüne
ölü stok yığmaz.

## Bu veri setinin yetmediği yerler

Dürüstlük için: aşağıdakiler bilinçli sadeleştirmelerdir.

- **Sepet kimliği yok.** `satis` günlük toplam düzeyindedir; birlikte satın
  alma analizi yapılamaz. Sepet analizi gerektiren bir vaka geldiğinde
  veri seti bu düzeyde yeniden üretilir.
- **Sell-through yüksek.** İkmal hedefe göre çalıştığı için sezon sonunda
  gerçek hayattakinden az stok kalır; gerçek zincirlerde ilk dağıtım bir
  bahistir ve fazlası eritilir.
- **Fiyat sabit.** İndirim işlem bazında rastgeledir; sezon sonu indirim
  takvimi modellenmemiştir. Fiyatlama alanı geldiğinde `fiyat_gecmisi` ve
  `kampanya` tabloları eklenecektir.
- **Sezon kodu yok.** Ürünler `S1`/`S2` gibi bir sezon koduna bağlı değildir;
  sezon davranışı line üzerinden gelir. Koleksiyon devri gerektiren bir vaka
  geldiğinde eklenecektir.
- **Beden setleri beş kademe.** Gerçek zincirlerde ayakkabı 36–45, takım
  elbise 46–58 gibi çok daha uzun setler vardır. Bu sürümde giyim dışına
  çıkılmamıştır.
- **Uzun stoksuzluk kendini besliyor.** İkmal kuralı hücrenin *gerçekleşen*
  satışına bakar (yukarıdaki "Dengesizlik nereden geliyor?"): stoksuz kalan
  hücre satamaz, satamayınca yavaş görünür, yavaş göründüğü için ikmal de
  almaz ve stoksuz kalmayı sürdürür. Kuralın bedeli budur ve marjinal
  değildir: son 26 haftanın tamamında hiç stok görmemiş 336 (mağaza, ürün)
  hücresi var. Gerçek zincirde bu hücreleri bir planlamacı elle açar; bu veri
  setinde açan kimse yok, o yüzden kayıp satış gerçekte olacağından daha
  yoğun birikir.
- **Tedarik yok.** Açık sipariş, tedarik süresi ve depo stoğu bu sürümde yok.
- **Transfer geçmişi yok.** Mağazalar arası geçmiş sevkler modellenmemiştir;
  tekrar-transfer soğuma kuralları bu veriyle sınanamaz.

## Yeniden üretim

```bash
cd veri
python -m venv .venv && .venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
python -m perakende_veri.uret
```

Tohum sabittir (`42`); aynı komut her zaman aynı veriyi üretir. Üretim
birkaç saniye sürer ve `veri/cikti/v2/` altına yazar.

Testler:

```bash
pytest                      # tüm testler
pytest tests/test_kalite.py # yalnızca veri gerçekçiliği doğrulamaları
```

`test_kalite.py` üretilmiş veriye karşı çalışır ve verinin inandırıcılık
eşiklerini korur: mevsimsellik görünür mü, beden dengesizliği var mı,
kayıp satış oranı makul mü, kırıklık oluşuyor mu.

# v3

`python -m perakende_veri.v3.uret` → `veri/cikti/v3/` (DuckDB, Parquet, CSV;
v2 ile aynı biçim). Tohum `42`; üretim ~5 sn, yazma ~10 sn. Tasarım:
`docs/superpowers/specs/2026-09-26-veri-v3-ve-rpt-design.md`, bölüm 2.

25 mağaza (v2'ninkilerle aynı) · 242 model → 720 option → 3.600 SKU ·
**2024-01-01 … 2025-12-31** (731 gün, 105 pazartesi). Simülasyon
2023-07-03'te başlar (ısınma); ısınmanın hareketleri dışa aktarılmaz, yalnız
siparişleri (`siparis`) yazılır.

## Tablolar

| Tablo | Satır | Açıklama |
|---|---:|---|
| `magaza` | 25 | v2 ile aynı |
| `urun` | 3.600 | v2 kolonları − `uretici` + `sezon_kodu` (Basic/NOS: `DEVAMLI`), `dalga` (1–3), `lansman_tarihi`, `cikis_tarihi` (devamlıda boş), `tedarikci_id` |
| `takvim` | 731 | + `sezon_kodu` (ticari sezon: son ilk dalgası başlamış sezon), `indirim_donemi_mi` |
| `sezon` | 15 | `sezon_kodu, dalga, lansman_tarihi, indirim_baslangic, cikis_tarihi` |
| `tedarikci` | 8 | `tedarikci_id, ad, ulke, mense, ilk_siparis_hafta, rpt_hafta, moq_option` |
| `siparis` | ~14,5 bin | SKU düzeyi: `siparis_id, tip (ilk / rpt / surekli), option_id, urun_id, tedarikci_id, siparis_tarihi, planlanan_teslim, gerceklesen_teslim, adet` |
| `satis` | ~978 bin | v2 şeması. `indirim_tutari` planlı indirimi ve işlem indirimini birlikte taşır |
| `stok` | ~1,05 milyon | Mağaza, pazartesi fotoğrafı + **`stoklu_gun`** |
| `depo_stok` | ~109 bin | Depo, pazartesi fotoğrafı: `tarih, urun_id, adet` |
| `sevkiyat` | ~319 bin | + `tip`: `ilk_dagitim` / `replenishment` / `geri_toplama` (negatif adet) |
| `kayip_satis` | ~119 bin | v2 şeması |

Fotoğraflar (`stok`, `depo_stok`) pazartesi sabahı, günün hiçbir hareketinden
önce çekilir. `stok` açık hücreleri taşır (lansman ≤ tarih ≤ çıkış; devamlılar
hep); `depo_stok` sezonluk SKU'ları ilk teslimden çıkıştan bir hafta sonrasına
kadar, devamlıları hep taşır.

## Sezonlar ve ürün ömrü

| Sezon | Dalga 1 | Dalga 2 | Dalga 3 | İndirim başı | Çıkış |
|---|---|---|---|---|---|
| AW23 | 2023-08-21 | 2023-09-25 | 2023-10-30 | 2024-01-02 | 2024-02-26 |
| SS24 | 2024-02-12 | 2024-03-18 | 2024-04-22 | 2024-07-01 | 2024-08-26 |
| AW24 | 2024-08-19 | 2024-09-23 | 2024-10-28 | 2025-01-02 | 2025-02-24 |
| SS25 | 2025-02-10 | 2025-03-17 | 2025-04-21 | 2025-06-30 | 2025-08-25 |
| AW25 | 2025-08-18 | 2025-09-22 | 2025-10-27 | (2026-01-02) | (2026-02-23) |

Her sezon 36 Collection + 6 Outlet modeli (2–4 renk, 12 renklik palet),
her dalgada üçte biri. 22 Basic (3 renk) ve 10 NOS (2 renk) pencere boyunca
devamlıdır. Collection/Outlet lansmanda doğar, **yaşam eğrisiyle** söner
(tepe 4. hafta, 12. hafta tepenin ~%36'sı), indirim başından çıkışa kadar
%30 (ilk 4 hafta) / %50 indirimle satılır (talep ×1,6 / ×2,2), çıkış günü
mağazada kalan stok depoya geri toplanır. 2025 talebi 2024'ün %6 üstü.

**AW25 sağdan sansürlüdür:** pencere bittiğinde ürünler hâlâ raftadır;
indirim ve çıkışları pencerenin dışındadır (`sezon` tablosunda planlı
tarihleriyle durur). Pencereden sonra gelecek siparişlerin
`gerceklesen_teslim`i boştur — gerçek bir zincirin yıl sonu fotoğrafı gibi.

## Tedarik

| Menşe | Tedarikçi | İlk sipariş | RPT / sürekli | MOQ (option) | Teslim sapması |
|---|---|---|---|---:|---|
| Yerli | v2'nin 5 üreticisi | 10–12 hafta | 4–6 hafta | 300 | ±3 gün |
| Uzak Doğu | Ningbo, Dhaka, Ho Chi Minh merkezli (kurgusal) | 24–30 hafta | 12–16 hafta | 600 | 0…+21 gün, sağa çarpık |

Süre tedarikçi başına bir kez çekilir (sabittir); gerçekleşen teslim onun
etrafında sapar. Dış giyim ve jean ağırlıklı Uzak Doğu; Collection'ın %42'si.
MOQ bir alt sınırdır, kat değil: miktar en az MOQ, üstü 10'un katına yuvarlanır.

**Plan ve ilk alım.** Plan = sürprizsiz beklenen talep (çeşitteki mağazalar ×
yaşam eğrisi × mevsim; yerel sapmanın ve sürprizin yalnız ortalaması),
lansmandan indirim başına kadar. İlk alım = plan ÷ 0,80; lansmandan ilk
sipariş süresi kadar önce verilir, lansmandan bir hafta önce depoda olması
planlanır. Geç gelirse ilk dağıtım geliş günü yapılır. İlk alımın %60'ı plan
payına göre mağazalara gider, %40'ı depoda kalır. Basic/NOS için iki haftada
bir **sürekli** sipariş (SKU düzeyinde, satışla düzeltilmiş plana göre).

**Sonlu depo, haftalık replenishment** (pazartesi): hedef önümüzdeki 28
günün planı; v2'nin ölü stok kapısı aynen (hücrenin son 28 günlük hızıyla 4
haftalık stoğu varsa mal gitmez, **hız sıfırsa hiç gitmez**); ilk dağıtımdan
sonraki 28 gün hücre yenidir, kapıdan muaftır; depo yetmezse istekler SKU
içinde orantılı kesilir.

## Lumoda'nın RPT pratiği (veride gerçekten verilmiş siparişler)

Banu her pazartesi lansmandan 3–6 hafta sonraki Collection option'larına
bakar: zincir STR'si (brüt satış ÷ mağazalara giden) ≥ %55 ve "lansman + 3
hafta + RPT süresi < indirim başı" ise ilk alımın %50'si kadar (en az MOQ)
RPT verir; option başına en fazla bir. Gelen RPT depoya girer ve normal
replenishment'la dağıtılır. Tam sezonlarda (SS24, AW24, SS25) sezon başına
34–38 RPT; %29–38'i indirimden sonra gelir; çıkışta RPT adedinin %63–74'ü
kadar stok hâlâ depodadır. RPT geldiğinde hızı sıfır görünen stoksuz
hücreler (hücrelerin %13'ü) sonraki kayıp satışın %46'sını taşır ama
sevkiyatın %5'ini alır. Kuralın kusurları kasıtlıdır (spec 2.8).

## Stoklu gün

`stok.stoklu_gun`: fotoğraftan önceki 7 günde, **satışa açıldığında**
(o günün teslim, dağıtım ve iadesinden sonra, talepten önce) mağaza
stoğu > 0 olan gün sayısı. Satış olan gün stokludur; satışsız kayıp olan gün
stoksuzdur. Sansürlü talep tahmini (hız = satış ÷ stoklu gün) veriden
yapılabilir.

## v3'ün kasten kusurlu yanları

v2'nin listesi (kayıp satış, ölü stok, beden dengesizliği, kırıklık, iade
~%6, mükerrer 80, bedelsiz 50, hayalet stok 60 satır) iki yıla ölçekli
geçerlidir. Üstüne:

| Kusur | Neden var |
|---|---|
| Ürün sürprizi | SS24+AW24 Collection option'larının ~%22'si planın 1,5 katından fazla, ~%38'i 0,7'sinden az talep görür; plan bilmez |
| Hit'ler erken biter | Sürprizli option'da depo indirimden önce tükenir; RPT'nin varlık sebebi |
| Geç RPT | Yetişme kontrolü teslim sapmasını ve sipariş haftasını görmez |
| RPT depoda kalır | Stoksuz kalan hücrenin hızı sıfır görünür, kapı mal göndermez (dizinin 4. sorusu) |
| Kayıp satış ~%15 | Collection ~%27, Outlet ~%27, Basic ~%4, NOS ~%1. v2'den (%8) yüksek: ürün sürprizi + mağazalar arası transfer yok |
| AW25 sağdan sansürlü | Pencere sezonun ortasında kapanır |
| Isınma | 2023'ün ikinci yarısı simüle edilir ama yayımlanmaz; AW23 pencereye indirimde girer |

## Bu sürümün sadeleştirmeleri

- Talep ürünler arası bağımsızdır: ikame yok (stoksuz ürünün talebi başka
  ürüne kaymaz), sergi etkisi yok (stoksuzluk sonrası talep düşmez).
- Talep lansman gününden başlar; ilk sipariş geç gelirse aradaki talep kayıptır.
- Transfer yok: hücreler arası dengesizliği yalnız replenishment düzeltir.
- İade, satıldığı günün planlı fiyatıyla (işlem indirimi hariç) geri ödenir;
  çıkmış hücrede iade yazılmaz.
- Kumaş rezervasyonu, OTB, fiyat optimizasyonu yok (indirim takvimi sabit).
- Plan tablo olarak yayımlanmaz; gizli dünyadan (`dunya_kur`) okunur.

## Vakalar için: gizli dünya ve yeniden oynatma

```python
from perakende_veri.v3.dunya import dunya_kur, talep_matrisi
from perakende_veri.v3.simulasyon import simule_et
from perakende_veri.v3.uret import hareket_tablolari

dunya = dunya_kur()              # çeşit, plan, beklenen talep, sürpriz, τ, teslim sapmaları
talep = talep_matrisi(dunya)     # [gün, hücre] int16, politikadan bağımsız
ham = simule_et(dunya, talep, rpt_politikasi=..., dagitim_politikasi=...)
tablolar = hareket_tablolari(dunya, ham)   # pencereli, kimlikli, temiz
```

Varsayılan politikalarla (`LumodaRPT`, `mevcut_dagitim`) motor yayımlanan
tabloları birebir üretir (`tests/test_v3_esdegerlik.py`). Günlük işlem
sırası, rastgele akışlar (operasyon rastgeleliği — iade ve işlem indirimi —
(gün, hücre) başına anahtarlıdır: bir politika bazı hücrelerin satışını
değiştirince diğer hücrelerin iade ve indirimleri aynen kalır) ve politika arayüzü `v3/simulasyon.py` ve
`v3/dunya.py` belgelerindedir. Beklenen talep:
`dunya.gercek_statik[c] * dunya.g_gercek[d, dunya.hucre_option[c]]`
(plan için `plan_statik`, `g_plan`); gün indisi 0 = 2023-07-03.

Testler: `pytest tests/test_v3_*.py` (birim + eşdeğerlik + `test_v3_kalite.py`,
üretilmiş veriye karşı).

# v4

`python -m perakende_veri.v4.uret` → `veri/cikti/v4/` (DuckDB, Parquet,
CSV). Tohum `2026`; üretim ~5 dakika (son koşu 319 sn). Tasarım:
`docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md`. **Tablo
sözlüğü, gizli gerçek ve politika enjeksiyonu için:
[`src/perakende_veri/v4/README.md`](src/perakende_veri/v4/README.md).**

84 fiziksel mağaza + online (`ONL`) · 1.870 option → 8.506 SKU ·
**2023-01-01 … 2025-12-31** (1.096 gün). Simülasyon 2022-07-04'te başlar.

v3'ün üstüne gelenler:

- **Mağazalar arası fark gizli.** Dört eksen (iklim, gelir, müşteri
  profili, konum) altı segmentte toplanır; tablolarda yok. Satış karışımından
  kümeleme kısmen bulur.
- **Fiyat oynar.** Markdown Lumoda'nın STR kuralıyla, içsel. Kampanyalar
  dışsal. Saf fiyat–talep regresyonu esnekliği yanlış bulur; kampanyalar
  doğru tahmin verir.
- **İkame ve kanibalizasyon.** Stoksuz ürünün talebinin bir kısmı komşu
  option'a geçer; çok option taşıyan mağazada her option daha az satar.
- **Mağaza açılır, kapanır, tadilata girer.** 6 açılış, 4 kapanış, 2
  tadilat; transferleri `sevkiyat`'ta.
- **18 tedarikçi, gizli profil, kalite kontrol.** Gecikme ve hatalı oranı
  sipariş ve kalite tablosundan kısmen öğrenilir.
- **Plan tabloları yayımlanır:** MFP, range, mağaza planı. Plan bilerek naif.
- **Kayıp satış yayımlanmaz.** Gizli gerçekle birlikte ayrıca üretilir.
- **Politikalar enjekte edilebilir.** Vaka kendi replenishment'ını,
  markdown'ını, transferini takar, aynı dünyada koşar.

| Tablo | Satır |
|---|---:|
| `satis` | 17.917.462 |
| `stok` | 10.324.671 |
| `depo_stok` | 4.608.870 |
| `sevkiyat` | 3.703.982 |
| `fiyat` | 120.850 |
| `siparis` | 38.508 |
| `kalite_kontrol` | 7.822 |
| boyut ve plan tabloları (11 tablo) | 85 … 8.506 |

Ham CSV 1,63 GB; Parquet 131 MB; DuckDB 218 MB.

Testler: `pytest -m "not yavas"` (hızlı) ve `pytest -m yavas` (tam koşu:
kalibrasyon bantları, öğrenilebilirlik). Sonuçlar v4 README'sinde.

## İndirme

v4'ün hazır dosyaları [`veri-v4` release'inde](https://github.com/lumtify-ai/perakendeanalitigi/releases/tag/veri-v4).
İki ayrı set var; tam veri için ikisi birlikte kullanılır (anahtarlar
`urun_id`, `magaza_id`, `kampanya_id`).

**A katmanı: perakende verisi** (mağaza, ürün, takvim, fiyat, kampanya,
günlük satış, stok, depo stoku, sevkiyat, sipariş, tedarikçi, planlar; 18 tablo):

| Varlık | Boyut |
|---|---:|
| [`lumoda-v4.duckdb`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4.duckdb) | 209 MB |
| [`lumoda-v4-parquet.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-parquet.zip) | 86 MB |
| [`lumoda-v4-csv.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-csv.zip) | 176 MB |

**B katmanı: CRM** (müşteri, fiş, fiş satırı, online liste özeti, online
olay kaydı, yorum; 6 tablo):

| Varlık | Boyut |
|---|---:|
| [`lumoda-v4-crm.duckdb`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-crm.duckdb) | 1.217 MB |
| [`lumoda-v4-crm-parquet.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-crm-parquet.zip) | 347 MB |
| [`lumoda-v4-crm-csv.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-crm-csv.zip) | 572 MB |
| [`lumoda-v4-olay-parquet.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-olay-parquet.zip) | 163 MB |

B'nin Parquet ve CSV zip'leri olay kaydını içermez; o yalnız Parquet olarak
kendi zip'indedir. B'nin DuckDB dosyası olay kaydı dahil altı tabloyu taşır.
Dosyalar A ve B bölümlerindeki `uret` komutlarıyla yerelde de üretilebilir
(aynı tohum; bit düzeyinde aynılık aynı makine ve numpy sürümünde).

## v4 B katmanı: CRM

`python -m perakende_veri.v4.crm.uret` → `veri/cikti/v4_crm/` (DuckDB,
Parquet, CSV). A'nın satışını (tohum 2026) fişlere ve müşterilere ayrıştırır;
B'nin tohumu `4242`. Tasarım:
`docs/superpowers/specs/2026-09-28-veri-v4-crm-design.md`. **Tablo
sözlüğü, tutarlılık sözleşmesi, gizli gerçek ve bantlar için:
[`src/perakende_veri/v4/crm/README.md`](src/perakende_veri/v4/crm/README.md).**

- **Müşteri nüfusu.** Yedi gizli arketip, gizli tercihler, beden, ziyaret
  hızı, sepet, kart okutma, terk. Mağazada fişlerin ~%58'i kartlı
  (kimlikli), online'ın hepsi.
- **Fişler satışı birebir verir.** `fis_satir`'ın gün × mağaza × SKU
  toplamı A'nın temiz satışına kuruşu kuruşuna eşit; iadeler orijinal fiş
  satırına bağlı.
- **Terk ve LTV gizli.** Stoksuzluk, iade, beden uyumsuzluğu ve ev
  mağazasının kapanması terki artırır. "2026'da gelecek mi" ve 2026
  harcaması gizli gerçekte.
- **Online liste özeti ve 13 haftalık olay kaydı.** Sıralama enjekte
  edilebilir bir politika; tıklamada konum yanlılığı var.
- **Yorumlar** 7.000 metinlik etiketli Türkçe kütüphaneden; kim ve neden
  yazar gizli.

| Tablo | Satır |
|---|---:|
| `fis_satir` | 31.923.447 |
| `online_olay` (yalnız Parquet) | 23.901.935 |
| `fis` (iadeler dahil) | 16.764.655 |
| `musteri` | 2.106.860 |
| `online_liste_gunluk` | 609.905 |
| `yorum` | 74.394 |

Ham CSV 3.146 MB (olay kaydı hariç); Parquet 888 MB; DuckDB 1.217 MB. Üretim
A dahil ~19 dakika ve ~20 GB boş bellek ister.

Testler: `pytest tests/v4/crm -m "not yavas"` ve `-m yavas` (bantlar,
öğrenilebilirlik). Sonuçlar CRM README'sinde.

# Lisans

Veri CC BY 4.0 ile dağıtılır (bkz. depo kökündeki `LICENSE-VERI`).
Üretici kod MIT'dir.
