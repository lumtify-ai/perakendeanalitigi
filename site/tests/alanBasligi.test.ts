// site/tests/alanBasligi.test.ts
//
// Aşama alanının başlığı frontmatter'da tekrar edilmez, haritadan gelir;
// yalnızca harita dışı raf (Temeller) kendi başlığını taşır.
import { describe, expect, it } from 'vitest'
import { alanBasligi } from '../src/lib/alanBasligi'

describe('alanBasligi', () => {
  it('aşama alanının başlığını haritadan alır', () => {
    expect(alanBasligi('rpt', {})).toBe('RPT')
    expect(alanBasligi('replenishment', {})).toBe('Replenishment')
  })

  it('harita dışı rafın başlığını frontmatter’dan alır', () => {
    expect(alanBasligi('temeller', { baslik: 'Temeller' })).toBe('Temeller')
  })

  it('haritada olmayan ve başlığı olmayan alanda alan kimliğiyle hata fırlatır', () => {
    expect(() => alanBasligi('bilinmez', {})).toThrowError(/bilinmez/)
  })
})
