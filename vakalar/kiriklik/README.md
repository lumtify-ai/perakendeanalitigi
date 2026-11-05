# Kırıklık transferi (tekleme) vakası

Lumoda v4 sentetik verisinde kırıklık transferi (Transfer aşaması, Kırıklık Transferi dizisi) vakası: sezon sonuna
doğru kırık beden setlerinin kalan bedenlerini indirimden önce toplamanın kırıklığı ne kadar azalttığını, satışa ne
kadar döndüğünü ve maliyetine değip değmediğini aynı mal ve aynı indirimle ölçmek; uzmanın kuralını, serbest ve set
koşullu optimizasyonu ve gerçek talep girdili kahini yolun Lumoda koşusuyla kıyaslamak.
Tasarım: `docs/superpowers/specs/2026-10-25-kiriklik-transferi-design.md` (`docs/` ayrı depodur; uygulamadaki
sapmalar spec §8'de ve SDD kayıt defterinin Ruling'lerinde, R-PF1–R-PF4 ve R1–R38).

Sitedeki iki dizinin (Transfer: `site/src/content/yazi/transfer/kiriklik-transferi/`, 6 yazı; İş Zekası:
`site/src/content/yazi/is-zekasi/kiriklik-atil-stok/`, 2 kavram yazısı) ve demo kadranının
(`site/src/data/senaryolar/kiriklik-transferi.json`) bütün sayıları buradan, `cikti/rapor.txt`'ten çıkar (`cikti/`
git dışıdır; dosyayı `rapor.py` yeniden üretir). Bu dosya sayı vermez: sonuçlar rapordadır, aşağıda hangi bölümde
olduklarıyla anılır. Okuma sırası: Kurulum → Testler → Koşum → Simülasyon ve önbellek → Tanımlar → Kollar →
Sonuçlar → Kilit → Sınırlar.

## Kurulum

    cd vakalar/kiriklik
    python -m venv .venv
    .venv/Scripts/pip install numpy==2.5.4 pandas==2.3.3 duckdb==1.5.6 pyarrow==26.0.0 \
        scikit-learn==1.7.2 scipy==1.18.1 lightgbm==4.5.0 threadpoolctl==3.7.0 pulp==3.3.2
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (kaynak, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (yalnız hakem ve simülasyon)
    .venv/Scripts/pip install --no-deps -e ../allocation   # İlk Sevkiyat motoru ve yardımcıları
    .venv/Scripts/pip install --no-deps -e ../kumeleme
    .venv/Scripts/pip install --no-deps -e ../markdown     # tahmin: İndirim Takvimi'nin öğrenme modülü
    .venv/Scripts/pip install -e ".[dev]"

Kütüphane sürümleri Markdown (İndirim Takvimi) vakasının `.venv`'iyle (dolayısıyla İlk Sevkiyat'ınkiyle) aynıdır ve koşu
önbelleğinin anahtarındadır (numpy, pandas, pyarrow, duckdb, lightgbm, scikit-learn); biri değişirse bütün
koşular yeniden simüle edilir. `pulp` yalnız optimizasyon kolları içindir (Blok Transfer'in `.venv`'iyle aynı
sürüm) ve plan anahtarındadır (CBC çözümü sürüme bağlıdır). `allocation`, `kumeleme` ve `markdown` `--no-deps`
kurulur; hiçbir sürüm değişmemelidir.

**Veri.** `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`). Yoksa yayımlanan `veri-v4` dosyalarını
indirin ya da `cd veri && python -m perakende_veri.v4.uret`. Bir `git worktree`'de `veri/cikti` bulunmaz:
`PERAKENDE_V4_DB`'yi ana çalışma dizinindeki dosyaya gösterin. Izgara baştan sona aynı `PERAKENDE_V4_DB` ile koşulur.
`veri` işaretli testler dosya yoksa atlanır.

## Testler

Komutlar vakanın `.venv`'iyle, `vakalar/kiriklik` içinden; Windows konsolunda `PYTHONIOENCODING=utf-8`.

    .venv/Scripts/python -m pytest tests -q -m "not veri"         # hızlı takım: oyuncak fikstür
    .venv/Scripts/python -m pytest tests -q -m veri               # yayımlanan v4 gerekir
    .venv/Scripts/python -m pytest tests -q -m "veri and yavas"   # TAM eşdeğerlik

`test_esdegerlik_tam` (`tests/test_simulasyon.py`) `veri` ve `yavas` işaretlidir: yol 0 Lumoda koşusunu TAM'da koşar
(~4 dk, ~8 GB) ve yayımlanan v4'le tablo tablo karşılaştırır; varsayılanda atlanır, yalnız `-m` ifadesi `yavas`ı
anarsa koşar (`tests/conftest.py`). Karar modüllerinin kilidi `tests/test_sizinti.py`'dedir (aşağıda Kilit).

## Koşum

Komutlar `vakalar/kiriklik` içinden, bu sırayla; Windows konsolunda `PYTHONIOENCODING=utf-8`. TAM koşular sıralı ve
arka planda koşar; yarıda kalan ızgara önbellekten sürer. Izgara 47 TAM koşudur (Lumoda 5, yol 0'da sekiz kol koşusu,
ablasyon 2, yollar 1–4 için 32).

    # 1. planlar (isteğe bağlı: ızgara da kurar): yolun Lumoda koşusu önbellekte olmalı; simüle etmez
    .venv/Scripts/python -m kiriklik.oyun planlar --blok yol0
    .venv/Scripts/python -m kiriklik.oyun planlar --blok yollar --yol 2     # --yol P ile tek yol
    # 2. ızgara: Lumoda, planlar ve kol koşuları (ölçmez)
    .venv/Scripts/python -m kiriklik.oyun izgara --blok yol0        # Lumoda + {kural, opt, opt_set, kahin} × 2 sezon
    .venv/Scripts/python -m kiriklik.oyun izgara --blok ablasyon    # kural_28 × 2 sezon (yol 0)
    .venv/Scripts/python -m kiriklik.oyun izgara --blok yollar      # yol 1–4: Lumoda + 8 kol koşusu; --yol P ile tek yol
    # 3. ölçüm: önbellekteki bütün koşuları bugünkü ölçüm koduyla ölçer; koşmaz, plan kurmaz
    .venv/Scripts/python -m kiriklik.oyun olc                       # --zorla: ölçüm kodu aynı olsa da yeniden ölç
    # 4. koşusuz veri analizi (VERİ, KIRIKLIK, ATIL, UYGUNLUK): cikti/analiz.json
    .venv/Scripts/python analiz.py
    # 5. hikâye sahnesi: cikti/hikaye.json
    .venv/Scripts/python -m kiriklik.hikaye
    # 6. demo dosyası: site/src/data/senaryolar/kiriklik-transferi.json
    .venv/Scripts/python senaryolar.py
    # 7. rapor: yazıların bütün sayıları
    .venv/Scripts/python rapor.py > cikti/rapor.txt

`--blok hepsi` üç bloğu sırayla koşar. Bir yolun planları önce kurulur (`opt`, `opt_set` ve `kahin` bir optimizasyon
çözer), sonra kol koşuları sırayla koşar; plan önbelleğinde bulunan yeniden kurulmaz. Yol p > 0'ın planı o yolun
Lumoda koşusuna bağlıdır, bu yüzden Lumoda koşusu planlardan önce önbellekte olur (`izgara` onu da koşar).

**Bellek ve disk (bu makinede ölçüldü).** Bir TAM koşu ~7,4 GB; plan kurmada (yol p'nin öğrenme adımı dahil) süreç
tepesi ~12,5 GB'tır (`cikti/ilerleme.jsonl`'ın `surec_tepe_gb` alanı). Yol p'nin planı o yolun Lumoda koşusunun
yayımlanan biçimini geçici bir DuckDB dosyasından okur (`%TEMP%`'te; sert öldürülen süreç bırakabilir). Disk: 46 koşu
bittiğinde `cikti/kosular/` ~6,6 GB, öğrenme önbelleği `cikti/ogrenme/` ~1,8 GB.

**Aynı önbelleğe iki süreç yazmaz.** `oyun`'un her koşusu `cikti/kosular/`'daki, kendi sürecinden önce kalmış
`.yaziliyor-*` dizinlerini siler (İlk Sevkiyat motoru, `_artiklari_sil`: süreç başlangıcından eski her `*.yaziliyor-*`
dizini). Paralel süreçler bu yüzden aynı anda başlatılır; başka bir koşu yazılırken yeni bir `oyun` süreci (ölçüm ya
da KÜÇÜK ızgara dahil) başlatılmaz, yazılmakta olan koşuyu silebilir. KÜÇÜK denemeleri ayrı bir `onbellek`le ya da
ızgara bittikten sonra koşun.

**KÜÇÜK ölçek** (geliştirme): `oyun planlar|izgara|olc --olcek KUCUK`, `analiz.py --olcek KUCUK`,
`python -m kiriklik.hikaye --olcek KUCUK`, `senaryolar.py --kucuk`, `rapor.py --kucuk` (çıktılar `cikti/kucuk/`;
rapor her zaman taslaktır, yazılara kaynak olamaz).

**Rapor** (`rapor.py`) veriyi okumaz, simülasyon koşmaz: `oyun.json`, `analiz.json`, `hikaye.json` ve demo dosyasını
basar. Bir girdi eksik ya da eskiyse ya da bir korunum denetimi bozulursa stdout boş kalır, mesaj stderr'e gider,
çıkış 1. Eski sayılan: ızgaranın bir koşusu `oyun.json`'da yok, geçersiz ya da bugünkü ölçüm koduyla ölçülmemiş;
koşunun önbelleği bugünkü vaka ve İlk Sevkiyat koduyla, v4 parmak iziyle, kütüphane sürümleriyle koşulmamış; planı
bugünkü karar koduyla kurulmamış; `analiz.json` ya da `hikaye.json` bugünkü kodla yazılmamış; demo dosyası
`senaryolar.uret()`'le aynı değil. `rapor.py --taslak` eksik girdiye dayanan bölümleri atlar (çıkış 2; yazılara
kaynak olamaz). `analiz.py`, `rapor.py`, `senaryolar.py` paket dışında, vaka kökündedir: paketin içinde olsalardı
sınıflandırma ve kilit testleri onları ölçüm modülü olarak isterdi.

Sayı denetimi (yazılar yazıldıktan sonra; ikisinde de çıkış 0 olmalı):

    .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi ../../site/src/content/yazi/transfer/kiriklik-transferi --rapor cikti/rapor.txt
    .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi ../../site/src/content/yazi/is-zekasi/kiriklik-atil-stok --rapor cikti/rapor.txt

Denetim bir sayının raporda geçtiğini sınar, anlamını değil: aynı rakam raporda başka bir bağlamda geçiyorsa
denetim geçer. Ortak çıkan sayılar (ayrışım bileşenleri gibi) raporun ilgili bölümüyle elle karşılaştırılır.

## Simülasyon ve önbellek

**Koşu** (`kiriklik.simulasyon.kos`): İlk Sevkiyat'ın motor adımları, vakanın yuvalarıyla.

- **Plan karar anında, çevrimdışı.** Karar gününe kadar her kolun dünyası yolun Lumoda koşusuyla birebir aynıdır;
  plan o koşunun yayımlanan biçimdeki tablolarından, karar gününden önceye kesilerek hesaplanır (karar günü
  pazartesi stok fotoğrafı dahil, o günün satışı hariç). Yol 0'da yayımlanan v4, yol p > 0'da o yolun Lumoda
  koşusunun yayımlanan biçimi (geçici DuckDB). Plan `elle_transfer` yuvasına enjekte edilir (`politika.KirikTransfer`):
  karar gününde önce planın satırları, sonra Lumoda'nın elle transferleri.
- **Aynı mal.** Her kolda RPT ve markdown yuvası aynı yolun Lumoda koşusunun kayıtlı kararlarının yeniden
  oynatılmasıdır (`allocation.politika.TakvimRPT`, `TakvimMarkdown`). Replenishment ve Lumoda'nın elle transferi
  tepkili kalır. Korunum (`olcutler.korunum`: `oncesi_birebir`, `rpt_birebir`, `fiyat_birebir`, `siparis_birebir`,
  `plan_kesilmedi`) bunu sonuçla sınar; tutmayan koşu `gecerli: false` olur, ölçülmez ve rapor reddeder.
- **Koşu başına tek test sezonu.** Bir kol koşusu AW24 ya da SS25'te karar verir, öteki sezon Lumoda'nındır; iki
  sezonun toplamı iki koşunun toplamıdır. İki sezon kış sonunda aynı gruplarda ikame ve elle transferle birbirine
  sızar, tek koşuda ikisini birlikte değiştirmek sezon farkını karıştırırdı.
- **Sürekli tedarik.** Basic/NOS sürekli tedarik siparişleri motorun içinde zincir satışından türer ve hiçbir yuva
  oynatamaz: tepkili kalır, farkı YAN ETKİ'de basılır; test kapsamının (Collection) arzı birebir kalır (R25).

**Koşu önbelleği** `cikti/kosular/<ad>_<anahtar[:20]>`. Anahtar (`simulasyon.hazirla`): ad, parametreler (`sezon`,
`kol`, `yol`), enjekte edilen yuvaların türü ve kimliği, tohumlar, ölçek, İlk Sevkiyat kod özeti, v4 parmak izi,
kütüphane sürümleri ve `vaka`: bu paketin `SIMULASYON_MODULLERI`'nin (`__init__`, `politika`, `simulasyon`) ve
onların ortak paket kapanışının içerik özeti. **Planın kimliği anahtarın içindedir** (`KirikTransfer.parametreler()`:
`plan` ve `karar_gun`). Karar modüllerinin (`sabitler`, `kaynak`, `olcu`, `uygunluk`, `tahmin`, `kural`, `model`,
`plan`) baytı anahtarda değildir: bir kod değişikliği koşunun anahtarını yalnız planın içeriği değişirse değiştirir.
Planı aynı çıkan kollar (ör. `kural`) önbellekten gelir, planı değişenler yeniden simüle edilir.

**Plan önbelleği** `cikti/planlar/<kol>_<sezon>_y<yol>_<anahtar[:20]>.{parquet,json}`. Anahtar: kol, sezon, yol,
ölçek, yolun Lumoda koşusunun anahtarı, **karar kapanışının kod özeti** (kiriklik karar modülleri, `markdown`
paketinin `ogrenme` / `kaynak` / `sabitler` modülleri, onların içe aktardığı ortak modüller; `kahin`'de ayrıca
`hakem.py`), PuLP sürümü ve `oyun.py`'nin planı biçimlendiren işlevlerinin kaynağı, **`KARAR_FONKSIYONLARI`**
(`_plan_hesapla`, `plan_kur`, `_girdi`, `kahin_fiyat_denetimi`, `karar_veritabani`, `Yol._baglanti`,
`Yol.karar_girdisi`, `Yol.ogrenilen`, `Yol.talep`). Karar kapanışı kararı değiştirebilecek her kodu kapsar; yalnız
ölçümü ve raporu değiştiren kod kapsamaz.

**Koşan süreç varken `oyun.py` değişmez.** `KARAR_FONKSIYONLARI` kaynağı `inspect.getsource` ile, yani süreç
çalışırken diskteki dosyadan okunur. `oyun.py`'ye eklenen ya da silinen tek bir satır, dosyayı baştan okuyan ve
sonradan plan anahtarı hesaplayan çalışan sürecin gördüğü işlev kaynağını kaydırır: aynı sürecin başında ve sonunda
kurduğu planlar farklı anahtarla yazılır, kısmi bir ızgara iki anahtara bölünür. Izgara sürerken ölçüm ya da rapor
düzeltmesi bu yüzden `oyun.py`'de değil, `olcutler.py`, `hikaye.py` ya da `rapor.py`'de yapılır (R38).

**Ölçüm önbelleği.** Ölçüm koşu önbelleğinden yeniden hesaplanır; `oyun.json` kaydı koşu anahtarı, Lumoda anahtarı,
plan kimliği ve ölçüm kodu (`oyun.OLCUM_OZETI`: `olcutler.py` ve içe aktardığı kiriklik modülleri,
`OLCUM_FONKSIYONLARI`, `OLCUM_SURUMU`) aynıysa yeniden ölçülmez. Ölçümü değiştiren bir düzeltme koşuları yeniden
simüle ettirmez, `oyun olc` ister; bu kapsamın dışında ölçümü değiştiren düzeltmede `OLCUM_SURUMU` bir artırılır.
Atlanan koşunun eski kaydı `gecerli: false` ile değiştirilir, eski ölçüm geçerli görünmez (R24). Yeniden ölçümde TL
toplamlarının son bitleri DuckDB'nin paralel toplamından oynayabilir (R26); rapor iki ondalık basar. `analiz.json` ve
`hikaye.json` kendi kod özetlerini taşır.

**Öğrenme önbelleği** `cikti/ogrenme/`: İndirim Takvimi'nin sınanmış öğrenme modülü (`markdown.ogrenme`, R8) yol ve
sezon başına bir kez öğrenir; kaynak kimliği (yol 0'da yayımlanan dosya, yol p'de o yolun Lumoda koşusu) ve kod
özetiyle.

## Tanımlar

Ayrıntı modül notlarında (`kiriklik/olcu.py`, `olcutler.py`, `uygunluk.py`, `analiz.py`); burada raporda karşılaşılan
adlar.

- **Asorti.** Her beş bedenli setin tek standart paketi 1-2-2-1-1; Standart (aksesuar) tek bedendir, kırıklığı
  tanımsızdır ve kapsam dışıdır.
- **Kırık beden.** Asortide olan ama mağazada stoğu sıfır olan beden. "Kırık" sözcüğü yalnız bunun için.
- **Net kırıklık** (ana ölçüt): kırık beden ÷ beden sayısı. **Kırık çift**: net kırıklığı sıfırdan büyük
  (mağaza, option) çifti.
- **Brüt kırıklık**: Σ max(0, asorti − stok) ÷ Σ asorti. Yazıda bu "eksik adet"tir, "kırık" denmez; asortinin
  altındaki ama sıfır olmayan beden brüte girer, neti etkilemez. **Dar kırık** Blok Transfer'in tanımıdır: ara beden
  (sıra 2–4) sıfır.
- **Toplu oranlar** stoklu çiftler üzerinden toplu hesaplanır; stoğu sıfır çift hiçbir paydaya girmez. Vericiyi
  boşaltmak oranı yapay iyileştirebilir, bu yüzden oranların yanında kırık çift ve kırık beden sayısı mutlak basılır;
  başlık ölçüsü kırık beden sayısıdır.
- **Kırık beden farkının ayrışımı** (kol − Lumoda; üç bileşenin toplamı farka eşit olmak zorundadır): **ortak** iki
  koşuda da stoklu çiftlerdeki fark; **kolda biten** yalnız Lumoda'da stoklu çiftlerin (kolda stoğu bitmiş) katkısı,
  eksidir; **Lumoda'da biten** yalnız kolda stoklu çiftlerin katkısı, artıdır.
- **Satmayan stok**: son 28 günde satışı 0; **atıl stok**: 28 günde 1 ile x arası satış (x = 2 option × mağaza
  düzeyinde, 1 SKU düzeyinde; rapor x ∈ {1, 2, 3} basar). İkisi ayrık sınıflardır ve yalnız en az 28 gündür rafta olan
  çift ya da hücre için tanımlıdır (rafta daha kısa olan `yeni` sayılır). Ölçü adet ve alış değeridir (R31).
- **Doldurulamaz beden ve uygun alıcı.** Karar anında deposu da, indirimden önce teslim planlı açık siparişi de sıfır
  olan SKU doldurulamaz (replenishment kapatamaz). Çift kırık, bütün kırık bedenleri doldurulamaz, option Collection,
  mağaza fiziksel (AVM/Cadde), açık ve kapanış kararsızsa uygun alıcı adayıdır.
- **Kesitler** (dört pazartesi stok fotoğrafı, sabah, satıştan önce): `karar` (karar sabahı), `varis_sonrasi` (karar
  + 7'den sonraki ilk pazartesi), `indirim_oncesi` (indirim gününden önceki son pazartesi), `cikis_oncesi` (çıkış −
  7). **Kapsamlar**: transfer edilen option'ların alıcı, verici ve birleşik çiftleri; sezonun bütün Collection
  stoğu (`butun`).
- **Pencereler** (yarı açık): `tam` [karar, indirim), `indirim` [indirim, çıkış), `outlet` [çıkış, çıkış + 84),
  `toplam` üçünün birleşimi. Karardan önce iki koşu birebir aynı olduğu için ölçüm karar gününde başlar; koşunun
  kapsamadığı pencere ve kesit `None` olur.
- **Rota.** Tekil (verici, alıcı) mağaza çifti, bütün option'lar üzerinden: aynı çift birçok option taşısa da bir
  kargo ödenir. Karar (optimizasyonun rota değişkeni) ve ölçüm aynı tanımdadır.
- **Saha ölçüsü.** Alıcıda alınan adedin satışa dönme oranı: Σ min(hücrenin varıştan sonraki satışı, alınan) ÷
  Σ alınan, indirim gününe (`saha_indirime`) ve çıkışa (`saha_cikisa`) kadar. Sahada görülebilen tek ölçüdür;
  vericiyi görmez.
- **Gerçek etki** (yalnız simülasyonda): transfer edilen option'ların bütün mağaza ve kanallarında net satış adedi
  farkı (kol − Lumoda) ÷ taşınan adet; vericide kaybedilen ve alıcıda kazanılan adet ayrı satırdır. Saha ile etki
  arasındaki fark sahanın vericiyi görmediğidir.
- **Para.** Ciro farkı pencere başına (tam fiyat, indirim, outlet); brüt kâr farkı; transfer maliyeti üç pakette
  (düşük, orta, yüksek: toplama adet başı, kargo rota başı, yıpranma alış değerinin oranı); **net** = ciro farkı
  (toplam) − maliyet. Aynı mal olduğu için ciro farkı katkı farkıdır. `opt` ailesi orta paketle karar verir, ölçüm üç
  paketle basar.
- **Stok.** Çıkışta kalan (mağaza ve depo; adet, liste ve alış değeri), outlet'e giden, ölü stok.
- **Plan.** Hareket, adet, rota, alıcı ve verici sayısı, tamamlanan set, rota başına adet medyanı; malın kaynağı (tam
  setten alınan adet, verici hücre, verdikten sonra sıfırlanan hücre); çözücü durumu ve gap.
- **Yan etki.** Replenishment ve elle transfer farkı, gizli kayıp farkı, test dışı option'ların ciro farkı, sürekli
  sipariş farkı.
- **Tahmin isabeti.** Kolların gördüğü tahmin (`tahmin.ufuk_talebi`) ile kahinin gerçek talebi: Σ talep, WAPE ve
  yanlılık; bütün hücreler ve optimizasyonun alıcı hücreleri ayrı.
- **Yol.** İlk Sevkiyat'ın 5 talep yolu: yol 0 yayımlanan dünya, yol 1–4 aynı dünyada başka müşteri akışı; her
  yolda plan o yolun Lumoda koşusunun yayımlanan biçiminden kurulur.
- **Fark kuralı.** Farklar basılan iki ondalıklı değerlerden; tek ondalıklı her fark iki ondalıklının bir kez yarım
  yukarı yuvarlanmışıdır. "k/5 yolda önde" yol başına farkın işaretidir.

## Kollar

Hepsi aynı uygunluk kümesinde karar verir; maliyet yalnız optimizasyonun amacına girer, ölçümde bütün kollara aynı
uygulanır.

| Kol | Ne | Yol |
|---|---|---|
| `lumoda` | kırıklık transferi yok (taban çizgisi; yol 0 = yayımlanan v4) | 0–4 |
| `kural` | uzmanın kuralı: alıcı = o option'ı sezonda en iyi satan uygun mağaza (puan = STD, son 7, 14, 28 gün sıralarının eşit ağırlıklı ortalaması); vericiler o option'da seti zaten kırık, en düşük puanlı önce; alıcı ya tamamlanır ya dokunulmaz; verici bir option'da tek kullanımlık; maliyete bakmaz | 0–4 |
| `kural_28` | aynı kural, puan yalnız son 28 gün (sansür tuzağı ayrıştırması) | 0 |
| `opt` | bütün option'lar tek tamsayılı programda: taşınan her adedin beklenen ek cirosu − vericide kaybedilen − maliyet (orta paket); set koşulu yok, verici her mağaza olabilir | 0–4 |
| `opt_set` | `opt` + kuralın iki koşulu: alıcı seti tamamlar (her beden ≥ 1), verici yalnız kırık çift | 0–4 |
| `kahin` | `opt`'un gerçek taban talep, hücre esnekliği ve gerçekleşen fiyat yolu girdili hâli (`hakem.kahin_girdisi`) | 0–4 |

Çözücü: önce tam programın LP gevşetmesi (geçerli üst sınır), sonra LP'de açık rotalarla daraltılmış tamsayılı program
(CBC, seri, düğüm sınırı, süre sınırı yok); set koşulunda ayrıca kesmeli kök düğüm sınırı. Plan kaydı gap'i ve çözücü
durumunu taşır, rapor basar (R16, R18, R19).

## Sonuçlar

Sayılar `cikti/rapor.txt`'tedir; bu dosya sayı vermez. Bölümler sırasıyla: VERİ, KIRIKLIK, ATIL, UYGUNLUK (koşusuz,
`analiz.py`); PLAN; YOL 0; YOLLAR; AYRIŞIM; SATIŞA DÖNÜŞ; PARA; TAHMİN; YAN ETKİ; HİKÂYE; DEMO; KORUNUM. Başlık
soruları raporda tek satırdır (`SORU n · …`): SORU 1, 5, 6 SATIŞA DÖNÜŞ'te; SORU 2 PARA'da; SORU 3, 4, 7 AYRIŞIM'da;
SORU 8 HİKÂYE'de. Nedensel beklentiler `beklenti (K13) …: TUTUYOR | TUTMUYOR` satırıdır. YOLLAR beş yolda farkın
işaretini ve medyanını basar. Tutmayan beklentiler spec §8'de ve yazılarda söylenir.

## Kilit

Karar modülleri (`sabitler`, `kaynak`, `olcu`, `uygunluk`, `tahmin`, `kural`, `model`, `plan`) `perakende_veri`'yi,
`allocation.motor`'u, `allocation.politika`'yı ve ölçüm modüllerini içe aktarmaz; `lam`, `esneklik*`, `gercek` ve
`gizli_*` adlarını okumaz, dinamik içe aktarım (`import_module`, `__import__`) kullanmaz. Gizli gerçeğe yalnız ölçüm
tarafı dokunur: `hakem` (kahin girdisi) ve `simulasyon`; `olcutler` yalnız koşunun `gercek` tablosundan
`karsilanmayan`ı okur. `politika` yalnız `perakende_veri.v4.politika`'dan yuva türünü alır. Her modül tam bir
kümededir (karar, simülasyon, ölçüm); AST kilidi ve sınıflandırma `tests/test_sizinti.py`'dedir.

## Sınırlar

- **Bu dünyada sergileme etkisi yok.** Talep hücre (mağaza × SKU) başınadır; kırık set kalan bedenlerin satışını
  düşürmez. Kırıklığın zararı yalnız eksik bedenin karşılanmayan talebidir (komşu bedene ikame, alt kategori ikamesi).
  Kırık setin sergilemeyi bozduğu gerekçesi ölçülmez; gerçek bir zincirde kırıklığın bedeli daha büyük olabilir.
- **Tahminin ikame ve yaşam eğrisi yanlılığı.** Yayımlanan satış ikameyle gelen satışı da içerir; kardeş ürünler
  tükendikçe kalanlara kayan talep yaşam eğrisine birikir ve eğri olduğundan yavaş düşer. Açık veriyle ayrıştırılamaz,
  düzeltilmez; TAHMİN bölümü yanlılığı kahinin gerçek talebine göre basar. Kampanya satışlarının taban penceresinden
  arındırılması bu sınırdan ayrı bir hataydı ve düzeltildi (R33).
- **Çözücü.** Sınır tam programın LP gevşetmesidir (set koşulunda kesmeli kök düğüm sınırı da); plan daraltılmış bir
  tamsayılı programın çözümüdür. Yazılar "optimuma en fazla %x uzak" der, "optimum" demez; daraltma LP'nin açmadığı
  bir rotayı kaçırabilir (gap bunu kapsar).
- **Kuralın vericisi tek kullanımlık, ilk atlamada durur.** Verici bir option'da bir kez verir (R6); bir option'da ilk
  tamamlanamayan alıcıdan sonra hiçbir alıcı tamamlanamaz, çünkü tamamlatan beden vericilerde tükenmiştir (R5, B1).
  Bu kuralın okuması ve doğal sınırıdır; "atlanan alıcı verici olur" denmez.
- **Sürekli tedarik tepkili.** Basic/NOS sürekli tedarik siparişleri motorun içinde türer, oynatılamaz; transferin bu
  mallara ikameyle etkisi YAN ETKİ'de basılır, Collection arzı birebir korunur (R25).
- **Sezon başına tek karar.** Plan karar gününde bir kez kurulur ve uygulanır; sonraki haftalarda yeniden plan ve
  vericinin sonradan yeniden doldurulması planlanmaz (replenishment tepkili çalışır).
- **Genel yeniden dağıtım.** Serbest optimizasyon seti tamamlamak zorunda değildir ve malı tam setlerden de alabilir;
  kırıklık transferinden uzaklaşır (R36). Kullanıcının tanımına sadık karşılaştırma `kural` ↔ `opt_set`'tir.
- **Tek sentetik zincir.** Tek zincir, iki test sezonu, beş yol; sonuçların başka bir zincire taşınabilirliği
  ölçülmedi. Gerçek bir zincirde hakem yoktur: kahin ve gizli gerçeğe dayanan ölçüler (gerçek etki, vericide kayıp)
  yalnız bu vakada vardır; sahada vericinin kaybını ancak kontrol grubu gösterir.

## Dosyalar

`kiriklik/`: `sabitler`, `kaynak` (yayımlanan tablolardan karar girdisi), `olcu` (kırıklık ve atıl ölçüleri),
`uygunluk` (doldurulamaz beden, uygun alıcı, ihtiyaç), `tahmin` (hücre ufuk talebi, öğrenme), `kural`, `model`
(optimizasyon), `plan` (saf veri), `politika` (`KirikTransfer` yuvası), `simulasyon` (koşu, önbellek, takvim), `hakem`
(kahin girdisi), `olcutler` (ölçüm ve korunum), `oyun` (plan önbelleği, ızgara, ölçüm), `hikaye` (sahne). Vaka
kökünde `analiz.py` (koşusuz veri analizi), `senaryolar.py` (demo), `rapor.py`. Testler `tests/`; sahte rapor
girdileri `tests/sahte_rapor.py`.
