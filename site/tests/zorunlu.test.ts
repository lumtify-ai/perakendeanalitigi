// site/tests/zorunlu.test.ts
import { describe, expect, it } from 'vitest'
import { zorunlu } from '../src/lib/zorunlu'

describe('zorunlu', () => {
  it('var olan girdiyi olduğu gibi döndürür', () => {
    const girdi = { data: { baslik: 'Transfer' } }
    expect(zorunlu(girdi, 'alan', 'transfer')).toBe(girdi)
  })

  it('undefined girdide koleksiyonu ve id\'yi söyleyen bir hata atar', () => {
    expect(() => zorunlu(undefined, 'alan', 'fiyatlama')).toThrowError(
      /alan.*fiyatlama.*src\/content\/alan\/fiyatlama\.md/s,
    )
  })

  it('null girdide de hata atar', () => {
    expect(() => zorunlu(null, 'dizi', 'transfer/blok-transfer')).toThrowError(/blok-transfer/)
  })

  it('sahte boş değerleri (0, boş dize) geçirir', () => {
    // Yalnızca yokluk hatadır; 0 ya da '' geçerli bir değer olabilir.
    expect(zorunlu(0, 'x', 'y')).toBe(0)
    expect(zorunlu('', 'x', 'y')).toBe('')
  })
})
