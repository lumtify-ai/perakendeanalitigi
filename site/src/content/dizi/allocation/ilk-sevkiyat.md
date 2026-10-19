---
baslik: İlk Sevkiyat
alan: allocation
algoritmalar: [ilk-sevkiyat, strateji-oneri]
ozet: >-
  Yeni bir ürün henüz hiç satış görmeden hangi mağazaya kaç paket gider ve
  ne kadarı depoda kalır? Kategori planına bakan kural, benzer ürünlerin
  geçmişi ve bir tahmin modeli aynı sezonda yarışır.
# Spec §8 demo: true ister; src/data/senaryolar/ilk-sevkiyat.json gelene
# kadar false (Demo.astro dosyasız demo sayfasında build'i durdurur).
demo: false
---

Bu dizi, sezon başında yeni bir ürünün mağazalara ilk sevkiyatını baştan
kurar. Kararın neden satış görmeden verildiğini, malın kurala ya da
tahmine göre nasıl paylaştırıldığını, ne kadarının depoda tutulacağını ve
başarının sezon sonunda nasıl ölçüleceğini anlatır.
