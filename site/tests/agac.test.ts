import { describe, expect, it } from 'vitest'
import { alanYazilari, diziYazilari, komsular } from '../src/lib/agac'

const YAZILAR = [
  { id: 'transfer/blok-transfer/sonuclar', data: { baslik: 'Sonuçlar', tip: 'sonuc', sira: 3, durum: 'yayinda', ozet: 'ö' } },
  { id: 'transfer/blok-transfer/giris', data: { baslik: 'Giriş', tip: 'hikaye', sira: 1, durum: 'yayinda', ozet: 'ö' } },
  { id: 'transfer/blok-transfer/model', data: { baslik: 'Model', tip: 'teknik', sira: 2, durum: 'hazirlaniyor', ozet: 'ö' } },
  { id: 'temeller/urun-hiyerarsisi', data: { baslik: 'Ürün Hiyerarşisi', tip: 'anlatici', sira: 1, durum: 'yayinda', ozet: 'ö' } },
]

describe('diziYazilari', () => {
  it('yazıları sıraya göre döndürür', () => {
    const sirali = diziYazilari(YAZILAR, 'transfer', 'blok-transfer')
    expect(sirali.map((y) => y.slug)).toEqual(['giris', 'model', 'sonuclar'])
  })

  it('adresleri kurar', () => {
    const sirali = diziYazilari(YAZILAR, 'transfer', 'blok-transfer')
    expect(sirali[0].adres).toBe('/transfer/blok-transfer/giris/')
  })

  it('hazırlanan yazıyı listede tutar', () => {
    // Kapsamı göstermek için görünür kalır, ama durumu işaretlidir
    const sirali = diziYazilari(YAZILAR, 'transfer', 'blok-transfer')
    expect(sirali[1].durum).toBe('hazirlaniyor')
  })

  it('başka diziyi karıştırmaz', () => {
    expect(diziYazilari(YAZILAR, 'transfer', 'atil-tekleme')).toEqual([])
  })
})

describe('alanYazilari', () => {
  it('tekil alanın yazılarını döndürür', () => {
    const sirali = alanYazilari(YAZILAR, 'temeller')
    expect(sirali.map((y) => y.slug)).toEqual(['urun-hiyerarsisi'])
  })

  it('dizili alanın yazılarını doğrudan döndürmez', () => {
    expect(alanYazilari(YAZILAR, 'transfer')).toEqual([])
  })
})

describe('komsular', () => {
  it('ortadaki yazının iki komşusu olur', () => {
    const sirali = diziYazilari(YAZILAR, 'transfer', 'blok-transfer')
    const { onceki, sonraki } = komsular(sirali, 'model')
    expect(onceki?.slug).toBe('giris')
    expect(sonraki?.slug).toBe('sonuclar')
  })

  it('ilk yazının öncekisi yoktur', () => {
    const sirali = diziYazilari(YAZILAR, 'transfer', 'blok-transfer')
    expect(komsular(sirali, 'giris').onceki).toBeNull()
  })

  it('son yazının sonrakisi yoktur', () => {
    const sirali = diziYazilari(YAZILAR, 'transfer', 'blok-transfer')
    expect(komsular(sirali, 'sonuclar').sonraki).toBeNull()
  })
})
