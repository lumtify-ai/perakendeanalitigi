// site/tests/basliklar.test.ts
import { describe, expect, it } from 'vitest'
import { yaziBasliklari } from '../src/lib/basliklar'

describe('yaziBasliklari', () => {
  it('yalnızca h2 başlıklarını sırasıyla, slug ve metinle verir', () => {
    const sonuc = yaziBasliklari([
      { depth: 2, slug: 'kapsam', text: 'Kapsam' },
      { depth: 3, slug: 'ayrinti', text: 'Ayrıntı' },
      { depth: 1, slug: 'baslik', text: 'Başlık' },
      { depth: 2, slug: 'sonuc', text: 'Sonuç' },
    ])
    expect(sonuc).toEqual([
      { slug: 'kapsam', text: 'Kapsam' },
      { slug: 'sonuc', text: 'Sonuç' },
    ])
  })

  it('başlıksız yazıda boş liste', () => {
    expect(yaziBasliklari([])).toEqual([])
  })
})
