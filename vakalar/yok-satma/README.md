# Yok satma — stoksuz günün kayıp satışı

Lumoda v4 verisi üstünde stoksuzluk (yok satma) vakası: stoksuz günlerin
(`bos`, `tukenen`) talebi üç kestiriciyle (Naif, Basit, ML) kurulur, kayıp
satış yazılır ve kaynak ağacıyla (lojistik, allocation, tedarik, planlama)
dallara ayrılır. Kestiriciler ve ölçüm ortak pakettedir
(`vakalar/ortak/perakende_analitik`); bu dizin vakanın koşum ve rapor
katmanıdır.

## Kurulum

    cd vakalar/yok-satma
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak -e ../../veri -e ".[dev]"
    .venv/Scripts/python -m pytest -q

`../../veri` (`perakende-veri`) yalnız raporun hakem karşılaştırması için
gerekir (`rapor.py`; hakem gizli gerçeği o paketle yeniden kurar);
`hazirla` onu kullanmaz. Linux/macOS'ta `.venv/bin/...`.

Veri: `veri/cikti/v4/perakende.duckdb` (yayımlanan `lumoda-v4.duckdb`'yi bu
adla koyun ya da `PERAKENDE_V4_DB` ortam değişkeniyle ya da `--db` ile
gösterin; indirme:
<https://github.com/lumtify-ai/perakendeanalitigi/releases/tag/veri-v4>).

## Ara çıktılar: `hazirla`

    .venv/Scripts/python -m yok_satma.hazirla            # cikti/ altına

| Dosya | İçerik |
|---|---|
| `gunluk.parquet` | 2023–2025 bütün uygun mağaza ve online hücre-günleri (`stok.gunluk_magaza` + `stok.gunluk_online`, stoklu dahil) |
| `carpanlar.pkl` | `carpanlar.ogren`, 2023–2024 stoklu günlerinden (Basit'in gün karakteri) |
| `kayip_naif.parquet`, `kayip_basit.parquet`, `kayip_ml.parquet` | her kestirici için yalnız `bos` ve `tukenen` satırları: günlük tablo + `tahmini_talep`, `satis`, `kayip`, `kayip_saf`, `kaynak`, `firsat` |
| `sure.json` | adım başına saniye, tepe bellek, satır sayıları |

Kestiricilerin `egit`'i bütün pencerenin stoklu günlerini görür (ML yine
yalnız 2023–2024'ten eğitim örneği çeker); tahmin bütün pencerenin stoksuz
günleri içindir. Her adım kendi dosyasına yazılır ve dosya varsa atlanır.
Bağımlılıklar: `carpanlar`, `naif`, `ml` ← `gunluk`; `basit` ← `gunluk` +
`carpanlar`. Bir adım yeniden koşunca bağımlıları da koşar; `--adim` seçiminin
dışında kalan bağımlıların dosyası silinir (sonraki çağrı yeniden kurar).
`cikti/kaynak.json` v4 dosyasının yolunu, boyutunu ve mtime'ını tutar; başka bir
`--db` (ya da değişmiş dosya) bütün çıktıları geçersiz kılar.

    --cikti DIR     çıktı dizini (varsayılan vakalar/yok-satma/cikti)
    --db PATH       v4 DuckDB dosyası
    --yeniden       var olanları da yeniden hesapla
    --adim AD       yalnız bu adımı yeniden koş (gunluk, carpanlar, naif, basit, ml;
                    tekrarlanabilir; seçim dışındaki bağımlıların dosyası silinir)

Bütçe: tam koşu ≤ 45 dk, tepe bellek ≤ 20 GB (32 GB makine). Ölçülen
(gerçek v4, 12 çekirdek): ~17 dk (gunluk 564 sn, carpanlar 44, naif 67,
basit 81, ml 283), tepe 12,3 GB (ML adımı); ayrıntı `cikti/sure.json`.

## Hikâye ürünü: `hikaye_sec`

    .venv/Scripts/python -m yok_satma.hikaye_sec         # ilk 10 aday + seçilen

`hazirla` çıktılarından (`gunluk.parquet`, `kayip_basit.parquet`) yazı 1'in
açılış hikâyesinin ürününü seçer: Erkek/Unisex, İstanbul'da fiziksel mağaza,
aynı gün iki bedeni `bos`, önceki gece geç teslim edilmiş siparişle depoya
girmiş, kaybı `tedarik`e yazılmış, option'ın bu stoksuzluk dönemindeki (depoda
son stoklu günden `tarih - 1`e) zincir kaybı ≥ 1 adet; dönem kaybı azalan sıralanır.
CLI ayrıca her `line` için en iyi 3 option'ı basar. Aday yoksa tek ölçüt (6, 5, 4, 3, 2, 1 sırasıyla), sonra ikili
gevşetilir; hangi ölçütlerin gevştiği basılır. Ayrıntı modül açıklamasında.
