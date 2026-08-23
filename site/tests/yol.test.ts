import { describe, expect, it } from 'vitest'
import { yaziAdresi, yaziYolunuAyristir } from '../src/lib/yol'

describe('yaziYolunuAyristir', () => {
  it('dizili alanın yazısını üç parçaya ayırır', () => {
    expect(yaziYolunuAyristir('transfer/blok-transfer/matematiksel-model')).toEqual({
      alan: 'transfer',
      dizi: 'blok-transfer',
      slug: 'matematiksel-model',
    })
  })

  it('tekil alanın yazısında dizi boştur', () => {
    expect(yaziYolunuAyristir('temeller/urun-hiyerarsisi')).toEqual({
      alan: 'temeller',
      dizi: null,
      slug: 'urun-hiyerarsisi',
    })
  })

  it('tek parçalı yolu reddeder', () => {
    expect(() => yaziYolunuAyristir('urun-hiyerarsisi')).toThrow(/iki veya üç parçalı/)
  })

  it('dört parçalı yolu reddeder', () => {
    expect(() => yaziYolunuAyristir('a/b/c/d')).toThrow(/iki veya üç parçalı/)
  })
})

describe('yaziAdresi', () => {
  it('dizili yazının adresini kurar', () => {
    const yol = { alan: 'transfer', dizi: 'blok-transfer', slug: 'sonuclar' }
    expect(yaziAdresi(yol)).toBe('/tr/transfer/blok-transfer/sonuclar/')
  })

  it('tekil yazının adresinde dizi geçmez', () => {
    const yol = { alan: 'temeller', dizi: null, slug: 'urun-hiyerarsisi' }
    expect(yaziAdresi(yol)).toBe('/tr/temeller/urun-hiyerarsisi/')
  })
})
