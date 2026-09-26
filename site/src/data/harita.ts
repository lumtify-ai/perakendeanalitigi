// site/src/data/harita.ts
//
// Lumtify'ın perakende planlama haritasından türeyen, sitenin kendi
// haritasının tek kaynağı: https://www.lumtify.com/perakende-planlama/
// Faz dağılımı ve algoritma listesi kullanıcı kararıyla Lumtify'dan ayrışır
// (spec §0.1 madde 8 ve 10).
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

/**
 * Haritanın üç fazı. İlk ikisi sezon ekseninin iki yanı; üçüncüsü o eksende
 * durmayan ama her karara veri taşıyan süreçler (spec §0.1 madde 8).
 */
export type FazSlug = 'sezon-oncesi' | 'sezon-ici' | 'diger-surecler'

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
    ],
  },
  {
    slug: 'sezon-ici',
    ad: 'Sezon İçi',
    asamalar: [
      {
        no: 7,
        slug: 'allocation',
        ad: 'Allocation — ilk sevkiyat',
        algoritmalar: [
          { id: 'ilk-sevkiyat', ad: 'Otomatik ilk sevkiyat önerisi' },
          { id: 'strateji-oneri', ad: 'Strateji öneri modelleri' },
        ],
      },
      {
        no: 8,
        slug: 'replenishment',
        ad: 'Replenishment',
        algoritmalar: [{ id: 'otomatik-ikmal', ad: 'Tahmin tabanlı otomatik ikmal' }],
      },
      {
        no: 9,
        slug: 'rpt',
        ad: 'RPT',
        algoritmalar: [
          { id: 'rpt-gereksinim-adet', ad: 'RPT gereksinim tahminleme ve adet hesaplama' },
        ],
      },
      {
        no: 10,
        slug: 'transfer',
        ad: 'Mağazalar arası transfer',
        algoritmalar: [
          { id: 'blok-transfer', ad: 'Blok transfer' },
          { id: 'tekleme-transfer', ad: 'Tekleme transfer' },
          { id: 'acma-kapama-transferi', ad: 'Mağaza açma-kapama transferi' },
        ],
      },
      {
        no: 11,
        slug: 'indirim',
        ad: 'İndirim, promosyon ve kampanya',
        algoritmalar: [
          { id: 'fiyat-elastikiyeti', ad: 'Fiyat elastikiyeti modeli' },
          { id: 'markdown', ad: 'Markdown optimizasyonu' },
        ],
      },
    ],
  },
  {
    slug: 'diger-surecler',
    ad: 'Diğer Süreçler',
    asamalar: [
      {
        no: 12,
        slug: 'tedarik',
        ad: 'Tedarik',
        algoritmalar: [
          { id: 'tedarikci-performans-secim', ad: 'Tedarikçi performans ve seçim öneri sistemi' },
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
          { id: 'urun-siralama', ad: 'Ürün sıralama algoritması' },
          { id: 'yorum-siniflandirma', ad: 'Yorum sınıflandırma' },
        ],
      },
    ],
  },
]

/**
 * Kök dizinde aşama slug'ı olamayacak adlar: üç faz slug'ı (her birinin
 * kendi sayfası var), `temeller` (harita dışı raf), ve içerik
 * ağacındaki diğer koleksiyon kökleri (`sozluk`, `kadro`, `veri-seti`).
 * Bir aşama bunlardan biriyle çakışırsa iki farklı anlam aynı yolu
 * paylaşır ve Astro sessizce yanlış sayfayı üretir.
 */
export const AYRILMIS_KOK_ADLAR: readonly string[] = [
  'sezon-oncesi',
  'sezon-ici',
  'diger-surecler',
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
