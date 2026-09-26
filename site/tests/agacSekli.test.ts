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
    { koleksiyon: 'alan', goreliYol: 'temeller.md', data: { tanim: TANIM, baslik: 'Temeller' } },
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
    // Tekil yazı yalnızca Temeller'de durabildiği için çakışma da orada
    // mümkün (aşama altındaki tekil yazı ayrı bir kuralla reddedilir).
    const agac = saglamAgac()
    agac.push({
      koleksiyon: 'dizi',
      goreliYol: 'temeller/urun-hiyerarsisi.md',
      data: { alan: 'temeller' },
    })
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar).toHaveLength(1)
    expect(hatalar[0]).toContain('/temeller/urun-hiyerarsisi/')
    expect(hatalar[0]).toContain('src/content/dizi/temeller/urun-hiyerarsisi.md')
    expect(hatalar[0]).toContain('src/content/yazi/temeller/urun-hiyerarsisi.mdx')
  })

  it("demo sayfasıyla çakışan yazı slug'ını yakalar", () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'yazi', goreliYol: 'transfer/blok-transfer/demo.mdx' })
    expect(agacSekliniDogrula(agac).join('\n')).toContain('/transfer/blok-transfer/demo/')
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
    expect(hatalar.join('\n')).toContain('/sozluk/')
    expect(hatalar.join('\n')).toContain('src/pages/sozluk.astro')
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

// Alan dosyası ile Lumtify haritası arasındaki bağ: bir alan ya bir harita
// aşamasıdır ya da `temeller` raftır, üçüncü bir seçenek yoktur. Bugün bu
// kontrol yok — yanlış yazılmış bir aşama slug'ı build'i hiç kırmadan sessizce
// "harita dışı raf" gibi davranır ve aşama sayfasından hiç görünmez.
describe('harita tutarlılığı', () => {
  it('haritada olmayan alan dosyası reddedilir', () => {
    const agac: AgacDosyasi[] = [
      { koleksiyon: 'alan', goreliYol: 'replenishmnt.md', data: { tanim: TANIM } },
    ]
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar).toHaveLength(1)
    expect(hatalar[0]).toContain('replenishmnt')
    expect(hatalar[0]).toContain('src/data/harita.ts')
  })

  it('temeller haritada değil ama geçerli', () => {
    const agac: AgacDosyasi[] = [
      { koleksiyon: 'alan', goreliYol: 'temeller.md', data: { tanim: TANIM, baslik: 'Temeller' } },
    ]
    expect(agacSekliniDogrula(agac)).toEqual([])
  })

  it('faz adresleri sabit rotadır', () => {
    const agac: AgacDosyasi[] = [
      { koleksiyon: 'alan', goreliYol: 'sezon-ici.md', data: { tanim: TANIM } },
    ]
    // Sezon-ici hem harita üyesi değil hem de sabit bir rotayla çakışıyor;
    // ikisi de ayrı hata satırı üretir, burada yalnız adres çakışmasını arıyoruz.
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar.join('\n')).toContain('/sezon-ici/')
  })

  it('üçüncü fazın adresi de sabit rotadır', () => {
    const agac: AgacDosyasi[] = [
      { koleksiyon: 'alan', goreliYol: 'diger-surecler.md', data: { tanim: TANIM } },
    ]
    const hatalar = agacSekliniDogrula(agac).join('\n')
    expect(hatalar).toContain('/diger-surecler/')
    expect(hatalar).toContain('src/pages/diger-surecler.astro')
  })

  it('harita aşamasında baslik yazılamaz', () => {
    const agac: AgacDosyasi[] = [
      { koleksiyon: 'alan', goreliYol: 'rpt.md', data: { tanim: TANIM, baslik: 'X' } },
    ]
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar.join('\n')).toContain('başlık haritadan gelir')
  })

  it('temeller başlıksız reddedilir', () => {
    const agac: AgacDosyasi[] = [
      { koleksiyon: 'alan', goreliYol: 'temeller.md', data: { tanim: TANIM } },
    ]
    expect(agacSekliniDogrula(agac)).not.toEqual([])
  })

  // Site haritası kuralı (yayinDurumu.mjs · pasifAsamaAdresleri) aşamayı
  // `yazi/<aşama>/` altındaki yayında yazıya bakarak aktif sayar; noindex
  // kuralı (haritaDurumu.ts · asamaAktifMi) algoritmayı kapsayan yayında
  // diziye bakar. Aşamanın doğrudan altındaki tekil yazı ikisini ayırırdı:
  // sayfa site haritasında ilan edilir ama noindex basar. Tekil yazı
  // yalnızca Temeller rafında durur.
  it('harita aşamasının doğrudan altındaki tekil yazı reddedilir', () => {
    const agac = saglamAgac()
    agac.push({ koleksiyon: 'yazi', goreliYol: 'transfer/tek-basina.mdx' })
    const hatalar = agacSekliniDogrula(agac)
    expect(hatalar).toHaveLength(1)
    expect(hatalar[0]).toContain('src/content/yazi/transfer/tek-basina.mdx')
    expect(hatalar[0]).toContain('temeller')
  })

  it('Temeller rafındaki tekil yazıya izin verilir', () => {
    // saglamAgac temeller/urun-hiyerarsisi.mdx taşıyor.
    expect(agacSekliniDogrula(saglamAgac())).toEqual([])
  })

  it('dizisi olmayan aşamanın alan dosyası reddedilir', () => {
    const agac: AgacDosyasi[] = [
      { koleksiyon: 'alan', goreliYol: 'indirim.md', data: { tanim: TANIM } },
    ]
    expect(agacSekliniDogrula(agac)).not.toEqual([])
  })
})
