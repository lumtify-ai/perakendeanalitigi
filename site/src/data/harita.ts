// site/src/data/harita.ts
//
// Lumtify'ın perakende planlama haritasının tek kaynaklı kopyası:
// https://www.lumtify.com/perakende-planlama/
//
// Sıra, ad ve slug burada tutulur; başka hiçbir dosya bunu tekrarlamaz.
// Aşama slug'ları **kalıcıdır** — yazısı olmayan aşamalar da şimdiden
// sabitlenir ki ilk yazı geldiğinde ad tartışılmasın. Algoritma kimlikleri
// adrese çıkmaz; yalnızca dizi frontmatter'ında başvuru için kullanılır.
//
// Lumtify haritası değişirse (aşama eklenir, ad değişir) yalnızca bu dosya
// güncellenir. Yayında sayfası olan bir aşamanın slug'ı değişirse
// `public/_redirects` satırı eklemek zorunludur — yoksa eski bağlantılar
// 404 verir.

/** Bir plânlama algoritması: görünen ad ve dizi frontmatter'ında kullanılan kimlik. */
export type Algoritma = { id: string; ad: string }

/** Haritadaki tek bir aşama: kalıcı sıra numarası, kalıcı slug, ad ve algoritmaları. */
export type Asama = { no: number; slug: string; ad: string; algoritmalar: Algoritma[] }

/** Lumtify haritasının iki fazı. */
export type FazSlug = 'sezon-oncesi' | 'sezon-ici'

export type Faz = { slug: FazSlug; ad: string; asamalar: Asama[] }

export const HARITA: Faz[] = [
  {
    slug: 'sezon-oncesi',
    ad: 'Sezon Öncesi',
    asamalar: [
      {
        no: 1,
        slug: 'mfp',
        ad: 'Merchandise Financial Planning',
        algoritmalar: [{ id: 'uzun-donem-talep', ad: 'Uzun dönem talep tahmini (makro)' }],
      },
      {
        no: 2,
        slug: 'range-plan',
        ad: 'Range Plan',
        algoritmalar: [{ id: 'yasam-egrisi', ad: 'Ürün yaşam eğrisi tahminleme' }],
      },
      {
        no: 3,
        slug: 'urun-stratejileri',
        ad: 'Ürün stratejileri',
        algoritmalar: [{ id: 'trend-takip', ad: 'Tüketici trend takip sistemi' }],
      },
      {
        no: 4,
        slug: 'koleksiyon',
        ad: 'Koleksiyon geliştirme',
        algoritmalar: [
          { id: 'tasarim-oneri', ad: 'Yapay zeka ürün tasarım öneri modeli' },
          { id: 'urun-performans', ad: 'Ürün performans tahminleme' },
          { id: 'sku-rasyonalizasyonu', ad: 'SKU rasyonalizasyonu' },
        ],
      },
      {
        no: 5,
        slug: 'assortment',
        ad: 'Assortment Planning',
        algoritmalar: [
          { id: 'ilk-fiyat', ad: 'İlk fiyat belirleme algoritması' },
          { id: 'orta-donem-talep', ad: 'Orta dönem talep tahmini' },
          { id: 'beden-prepack', ad: 'Beden analizi (PrePack optimizasyonu)' },
        ],
      },
      {
        no: 6,
        slug: 'magaza-kumeleme',
        ad: 'Mağaza kümeleme',
        algoritmalar: [{ id: 'magaza-gruplama', ad: 'Yapay zeka ile mağaza gruplama' }],
      },
      {
        no: 7,
        slug: 'tedarik',
        ad: 'Tedarik',
        algoritmalar: [
          { id: 'tedarikci-performans', ad: 'Tedarikçi performans ve risk takibi' },
          { id: 'tedarikci-secim', ad: 'Tedarikçi seçim öneri sistemi' },
        ],
      },
    ],
  },
  {
    slug: 'sezon-ici',
    ad: 'Sezon İçi',
    asamalar: [
      {
        no: 8,
        slug: 'allocation',
        ad: 'Allocation — ilk sevkiyat',
        algoritmalar: [
          { id: 'ilk-sevkiyat', ad: 'Otomatik ilk sevkiyat önerisi' },
          { id: 'strateji-oneri', ad: 'Strateji öneri modelleri' },
        ],
      },
      {
        no: 9,
        slug: 'replenishment',
        ad: 'Replenishment',
        algoritmalar: [{ id: 'otomatik-ikmal', ad: 'Tahmin tabanlı otomatik ikmal' }],
      },
      {
        no: 10,
        slug: 'rpt',
        ad: 'RPT',
        algoritmalar: [
          { id: 'rpt-gereksinim', ad: 'RPT gereksinim tahminleme' },
          { id: 'rpt-adet', ad: 'RPT adet hesaplama' },
        ],
      },
      {
        no: 11,
        slug: 'transfer',
        ad: 'Mağazalar arası transfer',
        algoritmalar: [
          { id: 'transfer-optimizasyonu', ad: 'Mağazalar arası ürün optimizasyonu' },
          { id: 'blok-tekleme-kiriklik', ad: 'Blok, tekleme ve kırıklık kararları' },
          { id: 'acma-kapama', ad: 'Mağaza açma/kapama etkisi' },
        ],
      },
      {
        no: 12,
        slug: 'indirim',
        ad: 'İndirim, promosyon ve kampanya',
        algoritmalar: [
          { id: 'fiyat-elastikiyeti', ad: 'Fiyat elastikiyeti modeli' },
          { id: 'markdown', ad: 'Markdown optimizasyonu' },
        ],
      },
      {
        no: 13,
        slug: 'is-zekasi',
        ad: 'İş zekası',
        algoritmalar: [
          { id: 'yok-satma', ad: 'Yok satma ve satış kaybı hesaplama' },
          { id: 'kiriklik-atil-stok', ad: 'Kırıklık ve atıl stok analizi' },
          { id: 'algoritma-basari', ad: 'Algoritma başarı hesaplama' },
        ],
      },
      {
        no: 14,
        slug: 'depo-lojistik',
        ad: 'Depo ve lojistik',
        algoritmalar: [
          { id: 'ag-tasarimi', ad: 'Ağ tasarımı optimizasyonu' },
          { id: 'depo-yerlesim', ad: 'Depo yerleşim optimizasyonu' },
          { id: 'depo-toplama', ad: 'Depo toplama optimizasyonu' },
          { id: 'rota', ad: 'Rota optimizasyonu' },
          { id: 'iade-kolileme', ad: 'İade ürün kolileme optimizasyonu' },
        ],
      },
      {
        no: 15,
        slug: 'crm',
        ad: 'CRM ve müşteri analitiği',
        algoritmalar: [
          { id: 'musteri-segmentasyonu', ad: 'Müşteri segmentasyonu' },
          { id: 'musteri-terk', ad: 'Müşteri terk tahmini' },
          { id: 'ltv', ad: 'Yaşam boyu değer (LTV) tahmini' },
          { id: 'urun-oneri', ad: 'Ürün öneri sistemleri' },
          { id: 'dinamik-fiyatlama', ad: 'Dinamik fiyatlama' },
          { id: 'urun-siralama', ad: 'Ürün sıralama algoritması' },
          { id: 'yorum-siniflandirma', ad: 'Yorum sınıflandırma' },
          { id: 'kampanya-kitle', ad: 'Kampanya kitle belirleme' },
        ],
      },
    ],
  },
]

/**
 * Kök dizinde aşama slug'ı olamayacak adlar: iki faz slug'ı (aşama
 * dizinlerinin üst dizinleri), `temeller` (harita dışı raf), ve içerik
 * ağacındaki diğer koleksiyon kökleri (`sozluk`, `kadro`, `veri-seti`).
 * Bir aşama bunlardan biriyle çakışırsa iki farklı anlam aynı yolu
 * paylaşır ve Astro sessizce yanlış sayfayı üretir.
 */
export const AYRILMIS_KOK_ADLAR: readonly string[] = [
  'sezon-oncesi',
  'sezon-ici',
  'temeller',
  'sozluk',
  'kadro',
  'veri-seti',
]

/** Harita dışı raf; alan dosyası olur ama aşama değildir (bkz. AYRILMIS_KOK_ADLAR). */
export const TEMELLER = 'temeller'

/** Slug'a göre aşamayı ve içinde bulunduğu fazı bulur. */
export function asamaBul(slug: string): { faz: Faz; asama: Asama } | undefined {
  for (const faz of HARITA) {
    const asama = faz.asamalar.find((a) => a.slug === slug)
    if (asama) return { faz, asama }
  }
  return undefined
}

/** Kimliğe göre algoritmayı, içinde bulunduğu aşamayı ve fazı bulur. */
export function algoritmaBul(
  id: string,
): { faz: Faz; asama: Asama; algoritma: Algoritma } | undefined {
  for (const faz of HARITA) {
    for (const asama of faz.asamalar) {
      const algoritma = asama.algoritmalar.find((a) => a.id === id)
      if (algoritma) return { faz, asama, algoritma }
    }
  }
  return undefined
}
