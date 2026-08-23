// site/tests/build.test.ts
import { execSync } from 'node:child_process'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { beforeAll, describe, expect, it } from 'vitest'

const DIST = fileURLToPath(new URL('../dist/', import.meta.url))

function oku(yol: string): string {
  return readFileSync(DIST + yol, 'utf-8')
}

beforeAll(() => {
  execSync('npm run build', { cwd: fileURLToPath(new URL('..', import.meta.url)), stdio: 'inherit' })
}, 300_000)

describe('build çıktısı', () => {
  it('türkçe ana sayfa üretilir', () => {
    expect(existsSync(DIST + 'tr/index.html')).toBe(true)
  })

  it('kök adres türkçeye yönlenir', () => {
    expect(existsSync(DIST + 'index.html')).toBe(true)
    expect(oku('index.html')).toContain('/tr/')
  })

  it('sayfa dili türkçe işaretlenir', () => {
    expect(oku('tr/index.html')).toContain('lang="tr"')
  })
})

describe('içerik koleksiyonları', () => {
  it('beş koleksiyon da dolu', async () => {
    const { readdirSync } = await import('node:fs')
    const icerik = fileURLToPath(new URL('../src/content/', import.meta.url))
    for (const ad of ['alan', 'dizi', 'yazi', 'sozluk', 'kadro']) {
      expect(readdirSync(icerik + ad).length).toBeGreaterThan(0)
    }
  })
})
