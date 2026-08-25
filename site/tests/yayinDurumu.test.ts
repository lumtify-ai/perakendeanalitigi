// site/tests/yayinDurumu.test.ts
//
// `hazirlaniyor` yazılar üretilir ama site haritasında ilan edilmez. Süzgeç
// astro.config.mjs içinden çağrılır; burada gerçek içerik ağacı üzerinde
// doğrulanır.
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { hazirlaniyorAdresleri, sitemapSuzgeci } from '../src/lib/yayinDurumu.mjs'

// Windows'ta new URL().pathname sürücü harfini bozar; fileURLToPath şart
const YAZI_KOKU = fileURLToPath(new URL('../src/content/yazi/', import.meta.url))

describe('hazirlaniyorAdresleri', () => {
  it('gerçek içerikteki hazırlanıyor yazıları bulur', () => {
    const adresler = hazirlaniyorAdresleri(YAZI_KOKU)
    expect(adresler).toContain('/tr/transfer/blok-transfer/sonuclar/')
    // İlk yayımlanan yazı: listede olmamalı
    expect(adresler).not.toContain('/tr/temeller/urun-hiyerarsisi/')
  })

  it('her adres eğik çizgiyle biter ve /tr/ ile başlar', () => {
    for (const adres of hazirlaniyorAdresleri(YAZI_KOKU)) {
      expect(adres).toMatch(/^\/tr\/.+\/$/)
    }
  })

  it('var olmayan kökte boş dizi döner', () => {
    expect(hazirlaniyorAdresleri(YAZI_KOKU + 'yok-boyle-bir-dizin')).toEqual([])
  })
})

describe('sitemapSuzgeci', () => {
  const suzgec = sitemapSuzgeci(['/tr/transfer/blok-transfer/sonuclar/'])

  it('dışarıda bırakılan adresi eler', () => {
    expect(suzgec('https://perakendeanalitigi.com/tr/transfer/blok-transfer/sonuclar/')).toBe(false)
  })

  it('diğer adresleri geçirir', () => {
    expect(suzgec('https://perakendeanalitigi.com/tr/transfer/blok-transfer/')).toBe(true)
    expect(suzgec('https://perakendeanalitigi.com/tr/')).toBe(true)
  })
})
