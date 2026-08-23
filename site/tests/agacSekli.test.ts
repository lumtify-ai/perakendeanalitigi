// site/tests/agacSekli.test.ts
//
// Ağaç şekli doğrulaması, gözden geçirmede tespit edilen beş sessiz hatanın
// tek ortak kaynağını kapatır: dosyaların *içi* doğrulanıyordu, *nerede
// durdukları* hiç doğrulanmıyordu.
import { describe, expect, it } from 'vitest'
import {
  agacSekliniDogrula,
  TANIM_ASGARI_UZUNLUK,
  type AgacDosyasi,
} from '../src/lib/agacSekli'

const TANIM =
  'Transfer, bir mağazada satmayan ürünü satabilecek başka bir mağazaya kaydırma kararıdır.'

/** Geçerli bir ağaç: iki alan, bir dizi (demo'lu), üç yazı, bir terim, bir kişi. */
function saglamAgac(): AgacDosyasi[] {
  return [
    { koleksiyon: 'alan', goreliYol: 'transfer.md', data: { tanim: TANIM } },
    { koleksiyon: 'alan', goreliYol: 'temeller.md', data: { tanim: TANIM } },
    {
      koleksiyon: 'dizi',
      goreliYol: 'transfer/blok-transfer.md',
      data: { alan: 'transfer', demo: true },
    },
    { koleksiyon: 'yazi', goreliYol: 'transfer/blok-transfer/magazanin-sorunu.mdx' },
    { koleksiyon: 'yazi', goreliYol: 'transfer/blok-transfer/sonuclar.mdx' },
    { koleksiyon: 'yazi', goreliYol: 'temeller/urun-hiyerarsisi.mdx' },
    { koleksiyon: 'sozluk', goreliYol: 'cover.md' },
    { koleksiyon: 'kadro', goreliYol: 'ali.md' },
  ]
}

describe('agacSekliniDogrula', () => {
  it('sağlam ağaçta hata vermez', () => {
    expect(agacSekliniDogrula(saglamAgac())).toEqual([])
  })
})

// Bugün: `dogrula` "temiz" der, `astro build` derlenmiş bir chunk dosyasını
// gösteren native abort ile çöker. İki ay sonra o mesajı okuyan kişi
// "alan dosyasını unuttum" sonucuna varamaz.
describe('yetim dizi ve yazı', () => {
  it('alan dosyası olmayan klasördeki diziyi yakalar', () => {
    const agac = saglamAgac()
    agac.push({
      koleksiyon: 'dizi',
      goreliYol: 'fiyatlama/dinamik-fiyat.md',
      data: { alan: 'fiyatlama' },
    })
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar).toHaveLength(1)
    expect(hatalar[0]).toContain('src/content/dizi/fiyatlama/dinamik-fiyat.md')
    expect(hatalar[0]).toContain('src/content/alan/fiyatlama.md')
  })

  it('alan dosyası olmayan klasördeki yazıyı yakalar', () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'yazi', goreliYol: 'fiyatlama/bir-yazi.mdx' })
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar.join('\n')).toContain('src/content/alan/fiyatlama.md')
  })
})

// Bugün: `.md` uzantılı bir yazı sessizce yok olur. Hata yok, uyarı yok.
describe('beklenmeyen uzantı', () => {
  it('yazi koleksiyonundaki .md dosyasını yakalar', () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'yazi', goreliYol: 'transfer/blok-transfer/taslak.md' })
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar).toHaveLength(1)
    expect(hatalar[0]).toContain('taslak.md')
    expect(hatalar[0]).toContain('.mdx')
  })

  it('alan koleksiyonundaki .mdx dosyasını yakalar', () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'alan', goreliYol: 'fiyatlama.mdx', data: { tanim: TANIM } })
    expect(agacSekliniDogrula(agac).join('\n')).toContain('fiyatlama.mdx')
  })

  it('uzantısı yanlış dosyayı sonraki adımlara sokmaz', () => {
    // Aksi hâlde tek dosya için hem "uzantı" hem "yetim" hatası basılırdı.
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'yazi', goreliYol: 'fiyatlama/taslak.md' })
    expect(agacSekliniDogrula(agac)).toHaveLength(1)
  })
})

// Bugün: tekil yazı ile dizi aynı slug'ı alırsa sessiz bir [WARN] çıkar ve
// sayfalardan biri hiç üretilmez.
describe('adres çakışması', () => {
  it('tekil yazı ile dizi aynı adrese çıkınca yakalar', () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'yazi', goreliYol: 'transfer/blok-transfer.mdx' })
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar).toHaveLength(1)
    expect(hatalar[0]).toContain('/tr/transfer/blok-transfer/')
    expect(hatalar[0]).toContain('src/content/dizi/transfer/blok-transfer.md')
    expect(hatalar[0]).toContain('src/content/yazi/transfer/blok-transfer.mdx')
  })

  it("demo sayfasıyla çakışan yazı slug'ını yakalar", () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'yazi', goreliYol: 'transfer/blok-transfer/demo.mdx' })
    expect(agacSekliniDogrula(agac).join('\n')).toContain('/tr/transfer/blok-transfer/demo/')
  })

  it("demo üretmeyen dizide demo slug'ına izin verir", () => {
    const agac = saglamAgac().map((dosya) =>
      dosya.koleksiyon === 'dizi' ? { ...dosya, data: { alan: 'transfer', demo: false } } : dosya,
    )
    agac.push({ koleksiyon: 'yazi', goreliYol: 'transfer/blok-transfer/demo.mdx' })
    expect(agacSekliniDogrula(agac)).toEqual([])
  })

  it('sabit rotayla çakışan alan adını yakalar', () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'alan', goreliYol: 'sozluk.md', data: { tanim: TANIM } })
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar.join('\n')).toContain('/tr/sozluk/')
    expect(hatalar.join('\n')).toContain('src/pages/tr/sozluk.astro')
  })
})

// Bugün: üç parçalı bir dizi yolu yanlış URL'de sayfa üretir.
describe('dizi derinliği', () => {
  it('üç parçalı dizi yolunu yakalar', () => {
    const agac = saglamAgac()
    agac.push({
      koleksiyon: 'dizi',
      goreliYol: 'transfer/aile/blok.md',
      data: { alan: 'transfer' },
    })
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar).toHaveLength(1)
    expect(hatalar[0]).toContain('transfer/aile/blok.md')
    expect(hatalar[0]).toContain('<alan>/<dizi>.md')
  })

  it('tek parçalı dizi yolunu yakalar', () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'dizi', goreliYol: 'blok.md', data: { alan: 'transfer' } })
    expect(agacSekliniDogrula(agac)).toHaveLength(1)
  })

  it('dört parçalı yazı yolunu yakalar', () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'yazi', goreliYol: 'transfer/blok-transfer/alt/x.mdx' })
    expect(agacSekliniDogrula(agac)).toHaveLength(1)
  })

  it('iki ve üç parçalı yazı yollarına izin verir', () => {
    expect(agacSekliniDogrula(saglamAgac())).toEqual([])
  })
})

// Bugün: `z.string()` boş dizeyi geçirir.
describe('alan tanımı', () => {
  it('boş tanımı yakalar', () => {
    const agac = saglamAgac().map((dosya) =>
      dosya.goreliYol === 'transfer.md' ? { ...dosya, data: { tanim: '' } } : dosya,
    )
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar).toHaveLength(1)
    expect(hatalar[0]).toContain('src/content/alan/transfer.md')
    expect(hatalar[0]).toContain(String(TANIM_ASGARI_UZUNLUK))
  })

  it('yalnızca boşluktan oluşan tanımı yakalar', () => {
    const agac = saglamAgac().map((dosya) =>
      dosya.goreliYol === 'transfer.md' ? { ...dosya, data: { tanim: '   \n  ' } } : dosya,
    )
    expect(agacSekliniDogrula(agac)).toHaveLength(1)
  })

  it('eksik tanım alanını yakalar', () => {
    const agac = saglamAgac().map((dosya) =>
      dosya.goreliYol === 'transfer.md' ? { ...dosya, data: {} } : dosya,
    )
    expect(agacSekliniDogrula(agac)).toHaveLength(1)
  })
})
