/* Deterministic no-download CDP evidence: five profiles x seven widths. */
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import { assertAggregate } from './iteration22-company-public-h2-browser-probe.mjs'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
const chrome = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find(existsSync)
if (!chrome) throw new Error('local Chromium is required; the harness never downloads one')

const output = join(root, '.tmp', 'iteration22-visual')
const widths = [320, 390, 768, 1024, 1199, 1200, 1440]
const profiles = ['saved-artifact', 'deterministic-fallback', 'gate-closed', 'partial-long-limitations', 'long-public-strings']
const coverageIds = [
  'narrative', 'requisites',
  'finance_f1', 'finance_f2', 'finance_f3', 'finance_f4', 'finance_f5',
  'arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5',
  'sources_limitations',
]
const reportId = '00000000-0000-4000-8000-000000000001'
const canonicalPath = '/company/7701234567-company'
const claimsPath = `/claims?report_id=${reportId}`
const wait = ms => new Promise(done => setTimeout(done, ms))

async function json(url) {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`${url}: ${response.status}`)
  return response.json()
}

async function connect(url) {
  const ws = new WebSocket(url)
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail })
  let id = 0
  const pending = new Map()
  const listeners = new Map()
  ws.onmessage = event => {
    const message = JSON.parse(event.data)
    if (message.id !== undefined) {
      const item = pending.get(message.id)
      if (item) {
        pending.delete(message.id)
        message.error ? item.reject(new Error(message.error.message)) : item.resolve(message.result)
      }
      return
    }
    for (const listener of listeners.get(message.method) ?? []) listener(message.params ?? {})
  }
  return {
    call(method, params = {}) {
      const request = ++id
      const answer = new Promise((resolveReply, rejectReply) => pending.set(request, { resolve: resolveReply, reject: rejectReply }))
      ws.send(JSON.stringify({ id: request, method, params }))
      return answer
    },
    on(method, listener) {
      const current = listeners.get(method) ?? []
      current.push(listener)
      listeners.set(method, current)
    },
    close: () => ws.close(),
  }
}

async function launch(port, dir) {
  const process = spawn(chrome, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
    '--no-default-browser-check', '--disable-background-networking', '--disable-component-update',
    '--disable-domain-reliability', '--no-pings', '--force-prefers-reduced-motion',
    `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, 'about:blank',
  ], { cwd: root, stdio: 'ignore' })
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const page = (await json(`http://127.0.0.1:${port}/json/list`)).find(item => item.type === 'page')
      if (page) return { process, cdp: await connect(page.webSocketDebuggerUrl) }
    } catch {}
    await wait(50)
  }
  process.kill('SIGTERM')
  throw new Error('Chromium CDP endpoint did not start')
}

async function evaluate(cdp, expression) {
  const reply = await cdp.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (reply.exceptionDetails || !reply.result) {
    throw new Error(reply.exceptionDetails?.exception?.description ?? reply.exceptionDetails?.text ?? 'CDP evaluation failed')
  }
  return reply.result.value
}

async function waitFor(cdp, expression, description) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try { if (await evaluate(cdp, expression)) return } catch {}
    await wait(50)
  }
  throw new Error(`timed out waiting for ${description}`)
}

const snapshotExpression = `(()=>{
  const root=document.getElementById('company-public-h2-root');
  const state=JSON.parse(document.getElementById('company-public-h2-state')?.textContent||'null');
  const head={title:document.title,description:document.querySelector('meta[name="description"]')?.content||'',robots:document.querySelector('meta[name="robots"]')?.content||'',canonical:document.querySelector('link[rel="canonical"]')?.getAttribute('href')||'',stylesheet:document.querySelector('link[rel="stylesheet"]')?.getAttribute('href')||'',stylesheetIntegrity:document.querySelector('link[rel="stylesheet"]')?.getAttribute('integrity')||'',module:document.querySelector('script[type="module"]')?.getAttribute('src')||'',moduleIntegrity:document.querySelector('script[type="module"]')?.getAttribute('integrity')||''};
  const marker=e=>({tag:e.tagName,id:e.id||'',field:e.getAttribute('data-h2-field')||'',block:e.getAttribute('data-h2-block')||'',coverage:e.getAttribute('data-h2-coverage')||'',limitation:e.getAttribute('data-h2-limitation')||'',limitationBlock:e.getAttribute('data-h2-limitation-block')||'',limitationField:e.getAttribute('data-h2-limitation-field')||'',href:e.getAttribute('href')||'',className:e.getAttribute('class')||'',text:(e.textContent||'').replace(/\\s+/gu,' ').trim()});
  const surface={text:(root?.innerText||'').replace(/\\s+/gu,' ').trim(),sections:[...root.querySelectorAll(':scope > nav,:scope > header,:scope > section,:scope > aside')].map(e=>e.id||e.className),markers:[...root.querySelectorAll('[data-h2-field],[data-h2-block],[data-h2-coverage],[data-h2-limitation]')].map(marker),links:[...root.querySelectorAll('a')].map(marker)};
  return {head,surface,state,enhanced:root?.dataset.enhanced==='true'};
})()`

const measureExpression = `(()=>{
  const root=document.getElementById('company-public-h2-root'),cta=root?.querySelector('.company-public-h2__cta'),reserver=root?.querySelector('.company-public-h2__cta-reserver'),live=root?.querySelector('.company-public-h2__live');
  const rect=e=>{const b=e.getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:b.width,height:b.height}};
  const overlaps=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
  const ctaRect=cta?rect(cta):null;
  const content=[...root.children].filter(e=>e!==cta&&e!==reserver&&e!==live&&getComputedStyle(e).display!=='none').map(e=>({name:e.id||e.className,box:rect(e)}));
  const focusableSelector='a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"]),[contenteditable="true"],audio[controls],video[controls]';
  const interactiveTargets=[...root.querySelectorAll(focusableSelector)];
  const links=[...root.querySelectorAll('a')];
  const coverage=[...root.querySelectorAll('li[data-h2-coverage]')].map(row=>({blockId:row.getAttribute('data-h2-coverage'),text:(row.textContent||'').replace(/\\s+/gu,' ').trim(),counts:[...row.querySelectorAll('span[data-h2-coverage]')].map(x=>({id:x.getAttribute('data-h2-coverage'),text:(x.textContent||'').trim()})),limitations:[...row.querySelectorAll('a[href^="#limitation-"]')].map(x=>x.getAttribute('href'))}));
  const style=cta?getComputedStyle(cta):null,rootStyle=root?getComputedStyle(root):null,reducedProbe=root?.querySelector('section');
  const breadcrumbNav=root.querySelector('nav[aria-label="Хлебные крошки"]');
  const neutralActions=[...root.querySelectorAll('#neutral-actions a')].map(x=>({path:x.getAttribute('href')||'',label:(x.textContent||'').trim()}));
  const ctaLink=root.querySelector('.company-public-h2__cta a');
  const accentColors=[...root.querySelectorAll('.company-public-h2__button--accent')].map(x=>{const color=getComputedStyle(x);return {background:color.backgroundColor,foreground:color.color}});
  const disabledFixture=document.createElement('a');disabledFixture.className='company-public-h2__button company-public-h2__button--accent';disabledFixture.setAttribute('aria-disabled','true');disabledFixture.textContent='noninteractive color fixture';root.append(disabledFixture);const disabledFixtureStyle=getComputedStyle(disabledFixture);const disabledColor={background:disabledFixtureStyle.backgroundColor,foreground:disabledFixtureStyle.color,opacity:disabledFixtureStyle.opacity,pointerEvents:disabledFixtureStyle.pointerEvents};disabledFixture.remove();
  const limitationItems=[...root.querySelectorAll('[data-h2-limitation]')].map(x=>({id:x.id,code:x.getAttribute('data-h2-limitation')||'',blockId:x.getAttribute('data-h2-limitation-block')||'',fieldId:x.getAttribute('data-h2-limitation-field')||'',message:(x.textContent||'').trim()}));
  return {scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,innerWidth,innerHeight,reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,reducedStyle:reducedProbe?{animation:getComputedStyle(reducedProbe).animationDuration,transition:getComputedStyle(reducedProbe).transitionDuration,scroll:getComputedStyle(reducedProbe).scrollBehavior}:null,rootStyle:rootStyle?{columnGap:rootStyle.columnGap}:null,ctaBox:ctaRect,ctaStyle:style?{position:style.position,display:style.display,width:style.width,top:style.top}:null,contentOverlap:ctaRect?content.filter(item=>overlaps(ctaRect,item.box)).map(item=>item.name):[],reserver:{inert:reserver?.hasAttribute('inert')===true,hidden:reserver?.getAttribute('aria-hidden')==='true',focusable:reserver?.querySelectorAll(focusableSelector).length??-1,box:reserver?rect(reserver):null},interactiveTargets:interactiveTargets.map(target=>({tag:target.tagName,href:target.getAttribute('href'),box:rect(target)})),claims:links.filter(x=>x.getAttribute('href')==='${claimsPath}').length,wrongClaims:links.filter(x=>(x.getAttribute('href')||'').startsWith('/claims?report_id=')&&x.getAttribute('href')!=='${claimsPath}').length,rootActions:links.filter(x=>x.closest('#neutral-actions')&&x.getAttribute('href')==='/').length,ctaLinks:links.filter(x=>x.closest('.company-public-h2__cta')).map(x=>x.getAttribute('href')),inPage:links.filter(x=>x.closest('#in-page-navigation')).map(x=>x.getAttribute('href')),accentColors,disabledColor,reportText:root?.querySelector('[data-h2-field="report_id"]')?.textContent||'',rootReportId:root?.dataset.reportId||'',breadcrumbs:{home:{path:breadcrumbNav?.querySelector('a')?.getAttribute('href')||'',label:(breadcrumbNav?.querySelector('a')?.textContent||'').trim()},current:(breadcrumbNav?.querySelector('[aria-current="page"]')?.textContent||'').trim()},neutralActions,cta:{heading:(root.querySelector('.company-public-h2__cta h2')?.textContent||'').trim(),copy:(root.querySelector('.company-public-h2__cta-copy')?.textContent||'').trim(),path:ctaLink?.getAttribute('href')||'',label:(ctaLink?.textContent||'').trim()},coverage,limitationItems,limitationIds:limitationItems.map(x=>x.id),chartArt:root?.querySelectorAll('svg,canvas').length,profileSignature:{heading:root?.querySelector('#narrative-title')?.textContent||'',displayName:root?.querySelector('[data-h2-field="identity.display_name"]')?.textContent||'',gate:!!root?.querySelector('#limitation-fixture_gate_closed'),partial:!!root?.querySelector('#limitation-fixture_partial'),partialMessageLength:(root?.querySelector('#limitation-fixture_partial')?.textContent||'').trim().length}};
})()`

function isLoopback(url, fixturePort) {
  if (url.startsWith('data:')) return true
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' && parsed.hostname === '127.0.0.1' && parsed.port === String(fixturePort)
  } catch { return false }
}

function coverageMatches(measured, state, limitationIds) {
  if (measured.length !== coverageIds.length || state.length !== coverageIds.length) return false
  const knownIds = new Set(limitationIds)
  return coverageIds.every((blockId, index) => {
    const actual = measured[index], expected = state.find(item => item.block_id === blockId)
    if (actual.blockId !== blockId || !expected) return false
    if (!actual.text.includes(expected.state) || !actual.text.includes(expected.population_scope)) return false
    const expectedCounts = ['total', 'returned', 'eligible']
      .filter(name => expected[name] !== null && expected[name] !== undefined)
      .map(name => ({ id: `${blockId}.${name}`, text: `${name}: ${expected[name]}` }))
    const expectedLimitations = expected.limitation_codes.map(code => `#limitation-${code}`)
    return JSON.stringify(actual.counts) === JSON.stringify(expectedCounts)
      && JSON.stringify(actual.limitations) === JSON.stringify(expectedLimitations)
      && expectedLimitations.every(href => knownIds.has(href.slice(1)))
  })
}

function profileMatches(profile, signature) {
  if (profile === 'saved-artifact') return signature.heading === 'Описание деятельности' && !signature.gate && !signature.partial
  if (profile === 'deterministic-fallback') return signature.heading.includes('подтверждённый шаблон') && !signature.gate && !signature.partial
  if (profile === 'gate-closed') return signature.gate && !signature.partial
  if (profile === 'partial-long-limitations') return signature.partial && !signature.gate && signature.partialMessageLength >= 300
  return profile === 'long-public-strings' && signature.displayName.includes('длинный профиль') && !signature.gate && !signature.partial
}

function exactDtoBindingsMatch(measured, state) {
  const expectedBreadcrumbs = {
    home: { path: state.breadcrumbs[0].path, label: state.breadcrumbs[0].label },
    current: state.breadcrumbs[1].label,
  }
  const expectedActions = state.actions.map(item => ({ path: item.path, label: item.label }))
  const expectedCta = {
    heading: state.primary_claim_cta.heading,
    copy: state.primary_claim_cta.desktop_copy,
    path: state.primary_claim_cta.path,
    label: state.primary_claim_cta.button_label,
  }
  const expectedLimitations = state.limitations.map(item => ({
    id: `limitation-${item.code}`,
    code: item.code,
    blockId: item.block_id ?? '',
    fieldId: item.field_id ?? '',
    message: item.message,
  }))
  return measured.rootReportId === state.report_id
    && measured.reportText === state.report_id
    && JSON.stringify(measured.breadcrumbs) === JSON.stringify(expectedBreadcrumbs)
    && JSON.stringify(measured.neutralActions) === JSON.stringify(expectedActions)
    && JSON.stringify(measured.cta) === JSON.stringify(expectedCta)
    && JSON.stringify(measured.limitationItems) === JSON.stringify(expectedLimitations)
}

async function runCell(profile, width, fixturePort) {
  const port = 9222 + profiles.indexOf(profile) * widths.length + widths.indexOf(width)
  const browser = await launch(port, join(output, `chromium-${profile}-${width}`))
  try {
    const { cdp } = browser
    const requests = [], responses = [], forbiddenRequests = [], consoleErrors = [], runtimeExceptions = [], loadingFailures = [], eventFailures = []
    let heldModuleRequest = null
    let releaseHeldModule
    const moduleHeld = new Promise(resolveHeld => { releaseHeldModule = resolveHeld })
    cdp.on('Network.requestWillBeSent', event => requests.push({ url: event.request.url, type: event.type }))
    cdp.on('Network.responseReceived', event => responses.push({ url: event.response.url, type: event.type, status: event.response.status }))
    cdp.on('Network.loadingFailed', event => loadingFailures.push({ errorText: event.errorText, blockedReason: event.blockedReason ?? null }))
    cdp.on('Runtime.consoleAPICalled', event => {
      if (event.type === 'error' || event.type === 'assert') consoleErrors.push(event.args.map(value => value.value ?? value.description ?? '').join(' '))
    })
    cdp.on('Runtime.exceptionThrown', event => runtimeExceptions.push(event.exceptionDetails?.exception?.description ?? event.exceptionDetails?.text ?? 'runtime exception'))
    cdp.on('Log.entryAdded', event => { if (event.entry?.level === 'error') consoleErrors.push(event.entry.text) })
    cdp.on('Fetch.requestPaused', event => {
      Promise.resolve().then(async () => {
        const url = event.request.url
        if (!isLoopback(url, fixturePort)) {
          forbiddenRequests.push(url)
          await cdp.call('Fetch.failRequest', { requestId: event.requestId, errorReason: 'BlockedByClient' })
          return
        }
        if (url.includes('/assets/company-public-h2.') && url.endsWith('.js') && heldModuleRequest === null) {
          heldModuleRequest = event.requestId
          releaseHeldModule()
          return
        }
        await cdp.call('Fetch.continueRequest', { requestId: event.requestId })
      }).catch(error => eventFailures.push(String(error)))
    })

    await cdp.call('Page.enable')
    await cdp.call('Runtime.enable')
    await cdp.call('Network.enable')
    await cdp.call('Log.enable')
    await cdp.call('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] })
    await cdp.call('Emulation.setDeviceMetricsOverride', { width, height: 1200, deviceScaleFactor: 1, mobile: false })
    await cdp.call('Emulation.setEmulatedMedia', { media: 'screen', features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] })

    const pageUrl = `http://127.0.0.1:${fixturePort}${canonicalPath}?profile=${profile}`
    const navigation = await cdp.call('Page.navigate', { url: pageUrl })
    if (navigation.errorText) throw new Error(`navigation failed: ${navigation.errorText}`)
    await Promise.race([moduleHeld, wait(6000).then(() => { throw new Error('module request was not intercepted') })])
    await waitFor(cdp, `document.getElementById('company-public-h2-root')!==null&&document.styleSheets.length>0`, 'complete SSR and stylesheet')
    const ssr = await evaluate(cdp, snapshotExpression)
    if (ssr.enhanced) throw new Error('React takeover occurred before the SSR snapshot')

    await cdp.call('Fetch.continueRequest', { requestId: heldModuleRequest })
    await waitFor(cdp, `document.getElementById('company-public-h2-root')?.dataset.enhanced==='true'`, 'successful React takeover')
    const react = await evaluate(cdp, snapshotExpression)
    const before = await evaluate(cdp, measureExpression)

    const ctaButton = await evaluate(cdp, `(()=>{const item=document.querySelector('.company-public-h2__cta a');if(!item)return null;item.addEventListener('click',event=>event.preventDefault(),{once:true});const box=item.getBoundingClientRect();return {x:box.left+box.width/2,y:box.top+box.height/2}})()`)
    if (!ctaButton) throw new Error('primary CTA is absent')
    await cdp.call('Input.dispatchMouseEvent', { type: 'mouseMoved', x: ctaButton.x, y: ctaButton.y })
    const hoverColors = await evaluate(cdp, `(()=>{const style=getComputedStyle(document.querySelector('.company-public-h2__cta a'));return {background:style.backgroundColor,foreground:style.color}})()`)
    await cdp.call('Input.dispatchMouseEvent', { type: 'mousePressed', x: ctaButton.x, y: ctaButton.y, button: 'left', clickCount: 1 })
    const activeColors = await evaluate(cdp, `(()=>{const style=getComputedStyle(document.querySelector('.company-public-h2__cta a'));return {background:style.backgroundColor,foreground:style.color}})()`)
    await cdp.call('Input.dispatchMouseEvent', { type: 'mouseReleased', x: ctaButton.x, y: ctaButton.y, button: 'left', clickCount: 1 })

    await evaluate(cdp, 'window.scrollTo(0, document.documentElement.scrollHeight)')
    await wait(75)
    const bottom = await evaluate(cdp, measureExpression)

    const special = [390, 1024, 1440].includes(width)
    let keyboard = null, zoom = null
    if (special) {
      await evaluate(cdp, `(()=>{const a=document.querySelector('#in-page-navigation a[href="#requisites"]');a.focus();return document.activeElement===a})()`)
      await cdp.call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 })
      await cdp.call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 })
      await wait(100)
      keyboard = await evaluate(cdp, `(()=>{const target=document.getElementById('requisites'),live=document.querySelector('.company-public-h2__live');return {hash:location.hash,targetFocused:document.activeElement===target,targetTabIndex:target?.getAttribute('tabindex'),announcement:live?.textContent||'',targetVisible:!!target&&target.getBoundingClientRect().top>=0&&target.getBoundingClientRect().top<innerHeight}})()`)
      const zoomCssWidth = Math.floor(width / 2)
      await cdp.call('Emulation.setDeviceMetricsOverride', { width: zoomCssWidth, height: 600, deviceScaleFactor: 2, mobile: false })
      await wait(100)
      await evaluate(cdp, 'window.scrollTo(0, document.documentElement.scrollHeight)')
      await evaluate(cdp, `document.querySelector('.company-public-h2__cta a')?.focus({preventScroll:false})`)
      await wait(50)
      zoom = await evaluate(cdp, `(()=>{const c=document.querySelector('.company-public-h2__cta'),r=c?.getBoundingClientRect(),v=visualViewport;const visibleWidth=r&&v?Math.max(0,Math.min(r.right,v.offsetLeft+v.width)-Math.max(r.left,v.offsetLeft)):0;return {requestedPhysicalWidth:${width},cssWidth:innerWidth,reflowFactor:${width}/innerWidth,devicePixelRatio,visualWidth:v?.width??innerWidth,visualHeight:v?.height??innerHeight,offsetLeft:v?.offsetLeft??0,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,scrollLeft:document.documentElement.scrollLeft,ctaIntersectsVisual:!!r&&!!v&&visibleWidth>0,ctaVisibleWidth:visibleWidth,contentOverlap:(()=>{if(!r)return [];const root=document.getElementById('company-public-h2-root');return [...root.children].filter(e=>!e.matches('.company-public-h2__cta,.company-public-h2__cta-reserver,.company-public-h2__live')&&getComputedStyle(e).display!=='none').filter(e=>{const b=e.getBoundingClientRect();return r.left<b.right&&r.right>b.left&&r.top<b.bottom&&r.bottom>b.top}).map(e=>e.id||e.className)})()}})()`)
    }

    const screenshot = await cdp.call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
    writeFileSync(join(output, `${profile}-${width}.png`), Buffer.from(screenshot.data, 'base64'))
    await wait(100)

    const expectedMode = width < 1200 ? 'fixed' : 'sticky'
    const expectedDisplay = width < 768 ? 'grid' : width < 1200 ? 'flex' : 'block'
    const expectedPaths = new Set([pageUrl, `http://127.0.0.1:${fixturePort}${ssr.head.stylesheet}`, `http://127.0.0.1:${fixturePort}${ssr.head.module}`, `http://127.0.0.1:${fixturePort}/favicon.ico`])
    const observedHttp = requests.filter(item => item.url.startsWith('http:')).map(item => item.url)
    const unexpectedHttp = observedHttp.filter(url => !expectedPaths.has(url))
    const missingAssets = [ssr.head.stylesheet, ssr.head.module].filter(path => !observedHttp.includes(`http://127.0.0.1:${fixturePort}${path}`))
    const expectedStatuses = new Map([
      [pageUrl, 200],
      [`http://127.0.0.1:${fixturePort}${ssr.head.stylesheet}`, 200],
      [`http://127.0.0.1:${fixturePort}${ssr.head.module}`, 200],
      [`http://127.0.0.1:${fixturePort}/favicon.ico`, 204],
    ])
    const unexpectedStatuses = responses.filter(item => expectedStatuses.has(item.url) && item.status !== expectedStatuses.get(item.url))
    const documentResponses = responses.filter(item => item.type === 'Document' && item.url === pageUrl)
    const checks = {
      http_200: navigation.frameId !== undefined && documentResponses.length === 1 && documentResponses[0].status === 200,
      ssr_before_takeover: !ssr.enhanced && ssr.surface.text.length > 0,
      takeover: react.enhanced,
      unchanged_head: JSON.stringify(ssr.head) === JSON.stringify(react.head),
      ssr_react_parity: JSON.stringify(ssr.surface) === JSON.stringify(react.surface),
      exact_binding: exactDtoBindingsMatch(before, react.state),
      exact_links: before.claims === 2 && before.wrongClaims === 0 && before.rootActions === 1 && JSON.stringify(before.ctaLinks) === JSON.stringify([claimsPath]) && JSON.stringify(before.inPage) === JSON.stringify(['#requisites', '#finance', '#arbitration']),
      cta_colors: before.accentColors.length === 3 && before.accentColors.every(item => item.background === 'rgb(238, 90, 42)' && item.foreground === 'rgb(17, 24, 39)') && hoverColors.background === 'rgb(243, 107, 63)' && hoverColors.foreground === 'rgb(17, 24, 39)' && activeColors.background === 'rgb(230, 83, 39)' && activeColors.foreground === 'rgb(17, 24, 39)' && before.disabledColor.background === 'rgb(246, 198, 181)' && before.disabledColor.foreground === 'rgb(90, 42, 27)' && before.disabledColor.opacity === '1' && before.disabledColor.pointerEvents === 'none',
      one_primary_cta: before.ctaLinks.length === 1,
      inert_reserver: before.reserver.inert && before.reserver.hidden && before.reserver.focusable === 0,
      minimum_targets: before.interactiveTargets.length > 0 && before.interactiveTargets.every(item => item.box.height >= 44 && item.box.width >= 44),
      exact_coverage: coverageMatches(before.coverage, react.state.coverage, before.limitationIds),
      no_chart_art: before.chartArt === 0,
      no_overflow: before.scrollWidth <= before.clientWidth && bottom.scrollWidth <= bottom.clientWidth,
      no_overlap: bottom.contentOverlap.length === 0 && (width >= 1200 || bottom.reserver.box.height + 1 >= bottom.ctaBox.height),
      cta_breakpoint: before.ctaStyle.position === expectedMode && before.ctaStyle.display === expectedDisplay && before.ctaBox.left >= 0 && before.ctaBox.right <= before.clientWidth + 0.5 && (width < 1200 || (before.ctaStyle.width === '320px' && before.ctaStyle.top === '24px' && before.rootStyle.columnGap === '32px')),
      reduced_motion: before.reduced && before.reducedStyle.animation === '0s' && before.reducedStyle.transition === '0s' && before.reducedStyle.scroll === 'auto',
      network_isolated: forbiddenRequests.length === 0 && unexpectedHttp.length === 0 && unexpectedStatuses.length === 0 && missingAssets.length === 0 && eventFailures.length === 0 && loadingFailures.length === 0,
      no_console_errors: consoleErrors.length === 0 && runtimeExceptions.length === 0,
      valid_distinct_profile: profileMatches(profile, before.profileSignature),
      keyboard_anchor: !special || (keyboard.hash === '#requisites' && keyboard.targetFocused && keyboard.targetTabIndex === '-1' && keyboard.targetVisible && keyboard.announcement.includes('Реквизиты')),
      zoom_200: !special || (zoom.reflowFactor >= 1.99 && zoom.reflowFactor <= 2.01 && zoom.devicePixelRatio >= 1.99 && zoom.scrollWidth <= zoom.clientWidth && zoom.scrollLeft === 0 && zoom.ctaIntersectsVisual && zoom.contentOverlap.length === 0),
    }
    return {
      profile, width, pass: Object.values(checks).every(Boolean), html_bytes: Buffer.byteLength(react.surface.text),
      checks, requests, responses, forbidden_requests: forbiddenRequests, unexpected_http: unexpectedHttp, unexpected_statuses: unexpectedStatuses,
      console_errors: consoleErrors, runtime_exceptions: runtimeExceptions, loading_failures: loadingFailures,
      measurements: { ssr, react, before, hoverColors, activeColors, bottom, keyboard, zoom },
    }
  } finally {
    browser.cdp.close()
    browser.process.kill('SIGTERM')
    await wait(75)
  }
}

rmSync(output, { recursive: true, force: true })
mkdirSync(output, { recursive: true })
const fixturePort = 8122
const server = spawn('python', ['scripts/serve-iteration22-company-public-h2-fixture.py'], {
  cwd: root,
  env: { ...process.env, ITERATION22_FIXTURE_PORT: String(fixturePort) },
  stdio: 'ignore',
})
try {
  await wait(500)
  if (server.exitCode !== null) throw new Error('fixture server exited')
  const cells = []
  for (const profile of profiles) {
    for (const width of widths) {
      const cell = await runCell(profile, width, fixturePort)
      writeFileSync(join(output, `${profile}-${width}.json`), JSON.stringify(cell, null, 2))
      cells.push(cell)
    }
  }
  const fixtureRequests = await json(`http://127.0.0.1:${fixturePort}/__requests`)
  const allowedFixtureRequests = fixtureRequests.every(value => value.startsWith(`${canonicalPath}?profile=`) || value === '/__requests' || value === '/favicon.ico' || value.startsWith('/assets/company-public-h2.'))
  const aggregate = {
    executed: cells.length,
    passed: cells.filter(cell => cell.pass).length,
    failed: cells.filter(cell => !cell.pass).length,
    skipped: 0,
    profiles, widths, coverage_ids: coverageIds,
    allowed_requests: allowedFixtureRequests,
    fixture_requests: fixtureRequests,
    cells,
  }
  writeFileSync(join(output, 'aggregate.json'), JSON.stringify(aggregate, null, 2))
  assertAggregate(aggregate)
  console.log(`PASS iteration22 browser matrix: ${aggregate.passed}/${aggregate.executed}`)
} finally {
  server.kill('SIGTERM')
}
