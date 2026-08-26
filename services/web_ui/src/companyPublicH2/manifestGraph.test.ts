import { describe, expect, it } from 'vitest'
// The release generator intentionally remains plain Node ESM so it can run
// before TypeScript compilation in the isolated asset-build command.
// @ts-expect-error no declaration file is emitted for the build script
import { collectCompanyPublicH2AssetGraph } from '../../scripts/company-public-h2-manifest.mjs'

const entry = 'src/companyPublicH2/main.tsx'

describe('Company Public H2 Vite manifest closure', () => {
  it('traverses imports, dynamic imports, and node.assets deterministically', () => {
    const graph = collectCompanyPublicH2AssetGraph({
      [entry]: {
        file: 'assets/company-public-h2.entry0000.js',
        css: ['assets/company-public-h2.entry0000.css'],
        imports: ['static.ts'],
        dynamicImports: ['charts.ts'],
        isEntry: true,
      },
      'static.ts': {
        file: 'assets/company-public-h2.static000.js',
        assets: ['assets/company-public-h2.static000.css'],
      },
      'charts.ts': {
        file: 'assets/company-public-h2.zzzzzzzz.js',
        css: ['assets/company-public-h2.aaaaaaaa.css'],
        assets: ['assets/company-public-h2.mmmmmmmm.js'],
        // Rollup may point a dynamic entry back at the main shared chunk. The
        // traversal must terminate without reclassifying the entry pair.
        imports: ['chart-helper.ts', entry],
      },
      'chart-helper.ts': { file: 'assets/company-public-h2.bbbbbbbb.js' },
    })

    expect(graph.entryJsFile).toBe('assets/company-public-h2.entry0000.js')
    expect(graph.entryCssFile).toBe('assets/company-public-h2.entry0000.css')
    expect(graph.reachableFiles).toEqual([
      'assets/company-public-h2.aaaaaaaa.css',
      'assets/company-public-h2.bbbbbbbb.js',
      'assets/company-public-h2.entry0000.css',
      'assets/company-public-h2.entry0000.js',
      'assets/company-public-h2.mmmmmmmm.js',
      'assets/company-public-h2.static000.css',
      'assets/company-public-h2.static000.js',
      'assets/company-public-h2.zzzzzzzz.js',
    ])
    expect(graph.optionalFiles).toEqual([
      'assets/company-public-h2.aaaaaaaa.css',
      'assets/company-public-h2.bbbbbbbb.js',
      'assets/company-public-h2.mmmmmmmm.js',
      'assets/company-public-h2.static000.css',
      'assets/company-public-h2.static000.js',
      'assets/company-public-h2.zzzzzzzz.js',
    ])
  })

  it('rejects a missing referenced manifest node', () => {
    expect(() => collectCompanyPublicH2AssetGraph({
      [entry]: {
        file: 'assets/company-public-h2.entry0000.js',
        css: ['assets/company-public-h2.entry0000.css'],
        dynamicImports: ['missing.ts'],
        isEntry: true,
      },
    })).toThrow(/missing reachable Vite manifest node missing\.ts/u)
  })

  it('rejects every reachable unsupported asset, including node.assets', () => {
    expect(() => collectCompanyPublicH2AssetGraph({
      [entry]: {
        file: 'assets/company-public-h2.entry0000.js',
        css: ['assets/company-public-h2.entry0000.css'],
        assets: ['assets/company-public-h2.font0000.woff2'],
        isEntry: true,
      },
    })).toThrow(/unsupported type/u)
  })
})
