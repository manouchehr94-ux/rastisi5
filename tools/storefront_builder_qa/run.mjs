import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { chromium } from 'playwright-core';

const manifestPath = process.argv[2];
if (!manifestPath) {
  console.error('Usage: node run.mjs <runtime-manifest.json>');
  process.exit(2);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const reportDir = manifest.report_dir;
fs.mkdirSync(reportDir, { recursive: true });
const failureDir = path.join(reportDir, 'failures');
fs.mkdirSync(failureDir, { recursive: true });

const result = {
  started_at: new Date().toISOString(),
  store: manifest.store,
  registry_count: manifest.expected_registry_count,
  checks: [],
  section_matrix: [],
  page_matrix: [],
  console_errors: [],
  request_failures: [],
  summary: { passed: 0, failed: 0, warnings: 0, sections_tested: 0, pages_tested: 0 },
};
let failureSeq = 0;
let page;
let context;
let browser;

function cleanName(value) {
  return String(value || 'check').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || 'check';
}

async function launchSystemBrowser() {
  const preferred = manifest.browser_channel === 'auto'
    ? ['chrome', 'msedge']
    : [manifest.browser_channel];
  const errors = [];
  for (const channel of preferred) {
    try {
      return await chromium.launch({ channel, headless: !manifest.headed });
    } catch (error) {
      errors.push(`${channel}: ${error.message}`);
    }
  }

  if (process.platform === 'win32') {
    const candidates = [
      process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Google', 'Chrome', 'Application', 'chrome.exe'),
      process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe'),
    ].filter(Boolean);
    for (const executablePath of candidates) {
      if (!fs.existsSync(executablePath)) continue;
      try {
        return await chromium.launch({ executablePath, headless: !manifest.headed });
      } catch (error) {
        errors.push(`${executablePath}: ${error.message}`);
      }
    }
  }
  throw new Error(`No usable installed Chromium browser found. ${errors.join(' | ')}`);
}

async function screenshotFailure(name) {
  if (!page || page.isClosed()) return '';
  failureSeq += 1;
  const filename = `${String(failureSeq).padStart(3, '0')}-${cleanName(name)}.png`;
  const full = path.join(failureDir, filename);
  try {
    await page.screenshot({ path: full, fullPage: true });
    return path.relative(reportDir, full);
  } catch (_error) {
    return '';
  }
}

async function check(name, fn, options = {}) {
  const started = Date.now();
  try {
    const detail = await fn();
    result.checks.push({ name, status: 'PASS', ms: Date.now() - started, detail: detail ?? null });
    result.summary.passed += 1;
    console.log(`PASS  ${name}`);
    return { ok: true, detail };
  } catch (error) {
    const shot = await screenshotFailure(name);
    const status = options.warning ? 'WARN' : 'FAIL';
    result.checks.push({
      name,
      status,
      ms: Date.now() - started,
      error: error?.stack || error?.message || String(error),
      screenshot: shot,
    });
    if (options.warning) result.summary.warnings += 1;
    else result.summary.failed += 1;
    console.log(`${status.padEnd(5)} ${name} — ${error.message || error}`);
    return { ok: false, error };
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function clickAcceptingDialog(locator) {
  let handled = false;
  const handler = async (dialog) => {
    handled = true;
    await dialog.accept();
  };
  page.on('dialog', handler);
  try {
    await locator.click();
  } finally {
    page.off('dialog', handler);
  }
  return handled;
}

async function waitHtmxIdle() {
  await page.waitForFunction(() => !document.querySelector('.htmx-request'), null, { timeout: 12000 }).catch(() => {});
}

async function waitPreviewReady() {
  await page.locator('#sfbPreviewFrame').waitFor({ state: 'visible', timeout: 15000 });
  // Mutating controls use HTMX/fetch and then reload the already-visible iframe.
  // Waiting for the old document's readyState first can therefore return too early.
  await waitHtmxIdle();
  await page.waitForFunction(() => {
    const iframe = document.getElementById('sfbPreviewFrame');
    return Boolean(iframe && iframe.contentDocument && iframe.contentDocument.readyState === 'complete');
  }, null, { timeout: 15000 });
  await page.waitForTimeout(80);
}

async function previewFrame() {
  await waitPreviewReady();
  const frameElement = await page.locator('#sfbPreviewFrame').elementHandle();
  const frame = await frameElement.contentFrame();
  if (!frame) throw new Error('Preview frame is not available.');
  return frame;
}

async function assertPreviewHealthy() {
  const frame = await previewFrame();
  assert(frame.url().includes('/admin-portal/storefront-builder/preview/'), `Preview navigated away: ${frame.url()}`);
  const metrics = await frame.evaluate(() => ({
    ready: document.readyState,
    bodyText: (document.body?.innerText || '').slice(0, 500),
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    duplicateIds: (() => {
      const counts = new Map();
      document.querySelectorAll('[id]').forEach((el) => counts.set(el.id, (counts.get(el.id) || 0) + 1));
      return [...counts.entries()].filter(([, count]) => count > 1).map(([id, count]) => ({ id, count }));
    })(),
    brokenImages: [...document.images].filter((img) => img.complete && img.naturalWidth === 0).map((img) => img.currentSrc || img.src).slice(0, 20),
  }));
  assert(metrics.ready === 'complete', 'Preview document is not complete.');
  assert(!/Firefox Can.t Open This Page|This site can.t be reached|ERR_/i.test(metrics.bodyText), 'Browser error page appeared inside Preview.');
  assert(metrics.scrollWidth <= metrics.clientWidth + 3, `Root horizontal overflow: ${metrics.scrollWidth} > ${metrics.clientWidth}`);
  assert(metrics.duplicateIds.length === 0, `Duplicate DOM ids: ${JSON.stringify(metrics.duplicateIds.slice(0, 5))}`);
  return metrics;
}

async function sectionCount(key) {
  const frame = await previewFrame();
  return frame.locator(`[data-section-key="${key}"]`).count();
}

async function allPreviewSections() {
  const frame = await previewFrame();
  return frame.locator('[data-section-id]').evaluateAll((els) => els.map((el) => ({
    id: el.getAttribute('data-section-id'),
    key: el.getAttribute('data-section-key'),
    label: el.getAttribute('data-section-label'),
    locked: el.getAttribute('data-section-locked'),
    rect: (() => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height, top: r.top, right: r.right, bottom: r.bottom, left: r.left };
    })(),
  })));
}

async function waitSectionCount(key, expected, timeout = 12000) {
  await page.waitForFunction(({ key, expected }) => {
    const iframe = document.getElementById('sfbPreviewFrame');
    if (!iframe?.contentDocument) return false;
    return iframe.contentDocument.querySelectorAll(`[data-section-key="${key}"]`).length === expected;
  }, { key, expected }, { timeout });
  await waitPreviewReady();
}

async function waitSectionLockState(key, expected, timeout = 12000) {
  await page.waitForFunction(({ key, expected }) => {
    const iframe = document.getElementById('sfbPreviewFrame');
    const nodes = iframe?.contentDocument?.querySelectorAll(`[data-section-key="${key}"]`);
    if (!nodes || !nodes.length) return false;
    return nodes[nodes.length - 1].getAttribute('data-section-locked') === expected;
  }, { key, expected }, { timeout });
  await waitPreviewReady();
}

async function previewSectionKeyOrder() {
  const frame = await previewFrame();
  return frame.locator('[data-section-key]').evaluateAll(
    (els) => els.map((el) => el.getAttribute('data-section-key'))
  );
}

async function waitSectionKeyOrderChanged(before, timeout = 12000) {
  await page.waitForFunction(({ before }) => {
    const iframe = document.getElementById('sfbPreviewFrame');
    const doc = iframe?.contentDocument;
    if (!doc) return false;
    const current = [...doc.querySelectorAll('[data-section-key]')]
      .map((el) => el.getAttribute('data-section-key'));
    return JSON.stringify(current) !== JSON.stringify(before);
  }, { before }, { timeout });
  await waitPreviewReady();
}

async function previewSectionIdOrder() {
  const frame = await previewFrame();
  return frame.locator('[data-section-id]').evaluateAll(
    (els) => els.map((el) => el.getAttribute('data-section-id'))
  );
}

async function waitSectionIdOrderChanged(before, timeout = 12000) {
  await page.waitForFunction(({ before }) => {
    const iframe = document.getElementById('sfbPreviewFrame');
    const doc = iframe?.contentDocument;
    if (!doc) return false;
    const current = [...doc.querySelectorAll('[data-section-id]')]
      .map((el) => el.getAttribute('data-section-id'));
    return JSON.stringify(current) !== JSON.stringify(before);
  }, { before }, { timeout });
  await waitPreviewReady();
}

async function findLibraryCard(key) {
  const card = page.locator(`.sfb-library-panel .sfb-lib-card[data-section-key="${key}"]`).first();
  await card.waitFor({ state: 'attached', timeout: 6000 });
  return card;
}

async function addSection(key) {
  const before = await sectionCount(key);
  const card = await findLibraryCard(key);
  await card.scrollIntoViewIfNeeded();
  await card.click();
  await waitSectionCount(key, before + 1);
  return before + 1;
}

async function selectSection(key, nth = -1) {
  const frame = await previewFrame();
  const sections = frame.locator(`[data-section-key="${key}"]`);
  const count = await sections.count();
  assert(count > 0, `Section ${key} not present in preview.`);
  const section = nth < 0 ? sections.nth(count - 1) : sections.nth(nth);
  const expected = await section.evaluate((el) => ({
    id: el.getAttribute('data-section-id'),
    locked: el.getAttribute('data-section-locked') || '0',
    rowKey: el.getAttribute('data-section-row-key') || '',
  }));
  await section.evaluate((el) => {
    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: el.ownerDocument.defaultView }));
  });
  const drawer = page.locator(
    `#sfbInspectorBody .sfb-drawer-body[data-inspector-section-id="${expected.id}"]` +
    `[data-inspector-locked="${expected.locked}"][data-inspector-row-key="${expected.rowKey}"]`
  );
  await drawer.waitFor({ state: 'visible', timeout: 10000 });
  await waitHtmxIdle();
  return section;
}

async function selectInspectorTab(name) {
  const tab = page.locator('#sfbInspectorBody .sfb-inspector-tabs button').filter({ hasText: name }).first();
  if (await tab.count() === 0) return false;
  await tab.click();
  await page.waitForTimeout(50);
  const selected = await tab.getAttribute('aria-selected');
  assert(selected === 'true', `${name} inspector tab did not become selected.`);
  return true;
}

async function inspectorButtonByTitle(part) {
  const button = page.locator(`#sfbInspectorBody .sfb-inspector-section-actions button[title*="${part}"]`).first();
  await button.waitFor({ state: 'attached', timeout: 5000 });
  return button;
}

async function clickUndo() {
  const button = page.locator('.sfb-prototype-history-controls button').first();
  await page.waitForFunction(() => {
    const b = document.querySelector('.sfb-prototype-history-controls button');
    return b && !b.disabled;
  }, null, { timeout: 8000 });
  await button.click();
  await waitPreviewReady();
}

async function clickRedo() {
  const button = page.locator('.sfb-prototype-history-controls button').nth(1);
  await page.waitForFunction(() => {
    const buttons = document.querySelectorAll('.sfb-prototype-history-controls button');
    return buttons[1] && !buttons[1].disabled;
  }, null, { timeout: 8000 });
  await button.click();
  await waitPreviewReady();
}

async function removeAllOfKey(key) {
  for (let safety = 0; safety < 8; safety += 1) {
    const count = await sectionCount(key);
    if (count === 0) return;
    await selectSection(key);
    const unlock = page.locator('#sfbInspectorBody .sfb-inspector-section-actions button[title*="بازکردن قفل"]').first();
    if (await unlock.count()) {
      await unlock.click();
      await waitSectionLockState(key, '0');
      await selectSection(key);
    }
    const remove = await inspectorButtonByTitle('حذف');
    if (await remove.isDisabled()) throw new Error(`Cannot clean up ${key}; remove button is disabled.`);
    await clickAcceptingDialog(remove);
    await waitSectionCount(key, count - 1);
  }
  throw new Error(`Cleanup safety limit exceeded for ${key}.`);
}

async function assertSectionBox(key) {
  const frame = await previewFrame();
  const sections = frame.locator(`[data-section-key="${key}"]`);
  const count = await sections.count();
  assert(count > 0, `${key} missing in Preview.`);
  const box = await sections.nth(count - 1).boundingBox();
  assert(box && box.width > 30, `${key} has zero/narrow width.`);
  assert(box.height >= 1, `${key} has zero height.`);
  const root = await frame.evaluate(() => ({ width: document.documentElement.clientWidth }));
  assert(box.x >= -3 && box.x + box.width <= root.width + 3, `${key} is outside the preview viewport.`);
  return box;
}

async function recoverPreviewIfNeeded() {
  const iframe = page.locator('#sfbPreviewFrame');
  const handle = await iframe.elementHandle();
  const frame = await handle.contentFrame();
  if (frame && frame.url().includes('/admin-portal/storefront-builder/preview/')) return;
  await iframe.evaluate((el) => { el.src = el.dataset.previewUrl; });
  await waitPreviewReady();
}

async function exerciseStorefrontButtons(key) {
  const frame = await previewFrame();
  const section = frame.locator(`[data-section-key="${key}"]`).last();
  try {
    return await section.evaluate(async (root) => {
      const visible = (el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      };
      const targets = [...root.querySelectorAll('button, input[type="submit"]')]
        .filter((el) => !el.closest('.sfb-rsec-toolbar') && !el.disabled && visible(el))
        .slice(0, 16);
      const names = [];
      for (const target of targets) {
        if (!target.isConnected) continue;
        const before = location.href;
        names.push((target.innerText || target.value || target.title || target.getAttribute('aria-label') || target.tagName).trim());
        target.click();
        await new Promise((resolve) => setTimeout(resolve, 35));
        if (location.href !== before) throw new Error(`Interactive control navigated embedded Preview: ${before} -> ${location.href}`);
      }
      return { exercised: names.length, controls: names };
    });
  } finally {
    await recoverPreviewIfNeeded();
  }
}

async function assertLinkGuard(key) {
  const frame = await previewFrame();
  const section = frame.locator(`[data-section-key="${key}"]`).last();
  const link = section.locator('a[href]').first();
  if ((await link.count()) === 0 || !(await link.isVisible().catch(() => false))) return { skipped: 'no visible link' };
  const before = frame.url();
  await link.click({ timeout: 4000 }).catch(async () => {
    await link.evaluate((el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: el.ownerDocument.defaultView })));
  });
  await page.waitForTimeout(200);
  assert(frame.url() === before, `Section link navigated Builder preview: ${before} -> ${frame.url()}`);
  return { href: await link.getAttribute('href') };
}

async function auditInteractiveWiring(rootLocator, label) {
  const issues = await rootLocator.evaluate((root) => {
    const problems = [];
    const visible = (el) => {
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
    };
    for (const button of root.querySelectorAll('button')) {
      if (button.disabled || !visible(button)) continue;
      const buttonType = (button.getAttribute('type') || '').toLowerCase();
      const ckManaged = Boolean(button.closest('.ck'));
      const hasAction = Boolean(
        ckManaged ||
        (button.form && (buttonType === '' || buttonType === 'submit')) ||
        button.hasAttribute('hx-post') || button.hasAttribute('hx-get') ||
        button.hasAttribute('@click') || button.hasAttribute('x-on:click') ||
        button.hasAttribute('onclick')
      );
      const ckLabel = (
        button.getAttribute('data-cke-tooltip-text') ||
        button.querySelector('.ck-button__label')?.textContent ||
        ''
      ).trim();
      const text = (button.innerText || '').trim();
      const accessibleName = (
        text || button.getAttribute('aria-label') || button.title || ckLabel
      ).trim();
      if (!hasAction) problems.push(`unwired button: ${accessibleName || '<icon>'}`);
      if (!accessibleName) problems.push('icon button without accessible name');
    }
    for (const anchor of root.querySelectorAll('a')) {
      if (!visible(anchor)) continue;
      const href = (anchor.getAttribute('href') || '').trim();
      if (!href || href === '#' || href.toLowerCase().startsWith('javascript:')) {
        problems.push(`dead anchor: ${(anchor.innerText || anchor.getAttribute('aria-label') || '<link>').trim()}`);
      }
    }
    return problems;
  });
  assert(issues.length === 0, `${label}: ${issues.join(' | ')}`);
  return { controls_checked: await rootLocator.locator('button:visible,a:visible').count() };
}

async function testSection(definition) {
  const row = { key: definition.key, label: definition.label, checks: [], status: 'PASS' };
  const run = async (name, fn, opts = {}) => {
    const outcome = await check(`section:${definition.key}:${name}`, fn, opts);
    row.checks.push({ name, status: outcome.ok ? 'PASS' : (opts.warning ? 'WARN' : 'FAIL') });
    if (!outcome.ok && !opts.warning) row.status = 'FAIL';
    if (!outcome.ok && opts.warning && row.status === 'PASS') row.status = 'WARN';
    return outcome;
  };

  try {
    await run('add-from-library', async () => {
      await addSection(definition.key);
      return { count: await sectionCount(definition.key) };
    });
    await run('render-box-and-overflow', async () => {
      const box = await assertSectionBox(definition.key);
      await assertPreviewHealthy();
      return box;
    });
    await run('click-opens-inspector', async () => {
      await selectSection(definition.key);
      const heading = (await page.locator('#sfbInspectorHeading').textContent().catch(() => page.locator('.sfb-prototype-panel-head h3').textContent())) || '';
      assert(heading.includes(definition.label), `Inspector heading does not contain ${definition.label}: ${heading}`);
      return heading.trim();
    });
    await run('inspector-control-wiring', async () => auditInteractiveWiring(page.locator('#sfbInspectorBody'), definition.key));
    await run('inline-toolbar-capability-contract', async () => {
      const frame = await previewFrame();
      const section = frame.locator(`[data-section-key="${definition.key}"]`).last();
      const toolbar = section.locator('.sfb-rsec-toolbar');
      assert((await toolbar.count()) === 1, `Inline toolbar missing for ${definition.key}.`);
      const commands = await toolbar.locator('[data-cmd]').evaluateAll((els) => els.map((el) => el.dataset.cmd).sort());
      assert(JSON.stringify(commands) === JSON.stringify(['down', 'duplicate', 'lock', 'remove', 'toggle', 'up'].sort()), `Inline toolbar command set mismatch for ${definition.key}.`);
      const duplicate = toolbar.locator('[data-cmd="duplicate"]');
      const remove = toolbar.locator('[data-cmd="remove"]');
      assert((await duplicate.isDisabled()) === !definition.duplicable, `Inline Duplicate capability mismatch for ${definition.key}.`);
      assert((await remove.isDisabled()) === !definition.removable, `Inline Remove capability mismatch for ${definition.key}.`);
      return { commands, duplicable: definition.duplicable, removable: definition.removable };
    });
    await run('basic-advanced-tabs', async () => {
      const basic = await selectInspectorTab('پایه');
      const advanced = await selectInspectorTab('پیشرفته');
      assert(basic && advanced, 'Basic/Advanced tabs are missing.');
      await selectInspectorTab('پایه');
    });
    await run('internal-links-stay-in-builder', async () => assertLinkGuard(definition.key));
    await run('storefront-buttons-smoke', async () => exerciseStorefrontButtons(definition.key));

    await run('settings-save-noop', async () => {
      const expectedPage = new URL(page.url()).searchParams.get('page') || 'home';
      const form = page.locator('#sfbInspectorBody form[action*="/settings/"]').first();
      if ((await form.count()) === 0) return { skipped: 'no settings form' };
      const submit = form.locator('button[type="submit"]').filter({ hasText: 'ذخیره' }).first();
      if ((await submit.count()) === 0) return { skipped: 'no save button' };
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 12000 }),
        submit.click(),
      ]);
      await waitPreviewReady();
      assert(page.url().includes('/admin-portal/storefront-builder/'), `Save navigated away: ${page.url()}`);
      const actualPage = new URL(page.url()).searchParams.get('page') || 'home';
      assert(actualPage === expectedPage, `Save changed Builder page: ${expectedPage} -> ${actualPage}`);
      await assertPreviewHealthy();
      return { saved: true };
    });

    if (await sectionCount(definition.key)) await selectSection(definition.key);
    await run('hide-and-undo', async () => {
      const before = await sectionCount(definition.key);
      assert(before > 0, `Cannot test hide/undo; ${definition.key} is not present on the active page.`);
      const toggle = await inspectorButtonByTitle('نمایش/مخفی');
      await toggle.click();
      await waitSectionCount(definition.key, Math.max(0, before - 1));
      await clickUndo();
      await waitSectionCount(definition.key, before);
    });

    await selectSection(definition.key);
    await run('lock-unlock-and-command-disable', async () => {
      let lockedByThisCheck = false;
      try {
        const lock = await inspectorButtonByTitle('قفل');
        await lock.click();
        await waitSectionLockState(definition.key, '1');
        lockedByThisCheck = true;

        await selectSection(definition.key);
        const up = await inspectorButtonByTitle('انتقال به بالا');
        const down = await inspectorButtonByTitle('انتقال به پایین');
        assert(await up.isDisabled(), 'Move-up remains enabled while section is locked.');
        assert(await down.isDisabled(), 'Move-down remains enabled while section is locked.');
      } finally {
        if (lockedByThisCheck && await sectionCount(definition.key)) {
          await selectSection(definition.key).catch(() => {});
          const unlock = page.locator('#sfbInspectorBody .sfb-inspector-section-actions button[title*="بازکردن قفل"]').first();
          if (await unlock.count()) {
            await unlock.click();
            await waitSectionLockState(definition.key, '0');
            await selectSection(definition.key);
          }
        }
      }
    });

    await run('duplicate-capability', async () => {
      const button = await inspectorButtonByTitle('کپی بخش');
      const before = await sectionCount(definition.key);
      if (!definition.duplicable) {
        assert(await button.isDisabled(), `Registry says duplicable=False but Duplicate is enabled for ${definition.key}.`);
        return { before, after: before, duplicable: false };
      }
      await button.click();
      await waitSectionCount(definition.key, before + 1);
      const after = await sectionCount(definition.key);
      assert(after === before + 1, `Expected duplicate count ${before + 1}, got ${after}.`);
      await clickUndo();
      await waitSectionCount(definition.key, before);
      return { before, after, duplicable: true };
    });

    if (await sectionCount(definition.key)) await selectSection(definition.key);
    await run('move-up-and-undo', async () => {
      const beforeKeys = await previewSectionKeyOrder();
      const up = await inspectorButtonByTitle('انتقال به بالا');
      if (await up.isDisabled()) return { skipped: 'move disabled' };
      await up.click();
      await waitSectionKeyOrderChanged(beforeKeys);
      const afterKeys = await previewSectionKeyOrder();
      assert(JSON.stringify(afterKeys) !== JSON.stringify(beforeKeys), 'Move-up did not change section order.');
      await clickUndo();
      await waitPreviewReady();
      return { before: beforeKeys, after: afterKeys };
    });

    if (await sectionCount(definition.key)) await selectSection(definition.key);
    await run('remove-and-undo', async () => {
      const remove = await inspectorButtonByTitle('حذف');
      const before = await sectionCount(definition.key);
      if (!definition.removable) {
        assert(await remove.isDisabled(), 'Registry says removable=False but remove button is enabled.');
        return { removable: false };
      }
      await clickAcceptingDialog(remove);
      await waitSectionCount(definition.key, before - 1);
      await clickUndo();
      await waitSectionCount(definition.key, before);
    });
  } catch (error) {
    row.status = 'FAIL';
    row.fatal = error.stack || error.message || String(error);
    await screenshotFailure(`section-${definition.key}-fatal`);
  } finally {
    if (definition.removable) {
      try {
        await removeAllOfKey(definition.key);
      } catch (cleanupError) {
        row.status = 'FAIL';
        row.cleanup_error = cleanupError.message || String(cleanupError);
      }
    }
  }

  result.section_matrix.push(row);
  result.summary.sections_tested += 1;
}

async function addRichText(count) {
  for (let i = 0; i < count; i += 1) await addSection('rich_text');
}

async function rowLayoutGeometry(expectedSpans) {
  const frame = await previewFrame();
  const sections = frame.locator('[data-section-key="rich_text"]');
  const boxes = [];
  for (let i = 0; i < expectedSpans.length; i += 1) {
    const box = await sections.nth(i).boundingBox();
    assert(box, `Missing rich_text box ${i}.`);
    boxes.push(box);
  }
  const topSpread = Math.max(...boxes.map((b) => b.y)) - Math.min(...boxes.map((b) => b.y));
  assert(topSpread < 6, `Row members are not aligned: top spread=${topSpread}px`);
  const totalWidth = boxes.reduce((sum, b) => sum + b.width, 0);
  const observed = boxes.map((b) => b.width / totalWidth);
  const expected = expectedSpans.map((span) => span / expectedSpans.reduce((a, b) => a + b, 0));
  observed.forEach((ratio, index) => {
    assert(Math.abs(ratio - expected[index]) < 0.09, `Width ratio mismatch at ${index}: got ${ratio.toFixed(3)}, expected ${expected[index].toFixed(3)}`);
  });
  return { observed, expected, topSpread };
}

async function testRowLayouts() {
  await removeAllOfKey('rich_text').catch(() => {});
  await addRichText(4);
  const presets = [
    ['half', [6, 6]],
    ['quarter_left', [3, 9]],
    ['quarter_right', [9, 3]],
    ['third_left', [4, 8]],
    ['third_right', [8, 4]],
    ['thirds', [4, 4, 4]],
    ['quarters', [3, 3, 3, 3]],
  ];
  for (const [mode, spans] of presets) {
    await check(`layout:${mode}`, async () => {
      await selectSection('rich_text', 0);
      await selectInspectorTab('پیشرفته');
      const button = page.locator(`#sfbInspectorBody .sfb-row-layout-presets button[value="${mode}"]`).first();
      assert((await button.count()) === 1, `Row preset ${mode} is missing.`);
      assert(!(await button.isDisabled()), `Row preset ${mode} is disabled unexpectedly.`);
      await button.click();
      await waitPreviewReady();
      const geometry = await rowLayoutGeometry(spans);

      // Responsive check on the asymmetric 3+9 case: mobile must stack and
      // must not create root horizontal overflow.
      if (mode === 'quarter_left') {
        const mobile = page.locator('.sfb-device-toggle button').filter({ hasText: 'موبایل' }).first();
        await mobile.click();
        await page.waitForTimeout(120);
        await assertPreviewHealthy();
        const frame = await previewFrame();
        const boxes = [];
        for (let i = 0; i < spans.length; i += 1) boxes.push(await frame.locator('[data-section-key="rich_text"]').nth(i).boundingBox());
        assert(Math.abs(boxes[0].y - boxes[1].y) > 8, 'Composite desktop row did not stack on mobile.');
        const desktop = page.locator('.sfb-device-toggle button').filter({ hasText: 'دسکتاپ' }).first();
        await desktop.click();
        await page.waitForTimeout(120);
      }

      await selectSection('rich_text', 0);
      await selectInspectorTab('پیشرفته');
      const full = page.locator('#sfbInspectorBody .sfb-row-layout-presets button[value="full"]').first();
      await full.click();
      await waitPreviewReady();
      return geometry;
    });
  }
  await removeAllOfKey('rich_text').catch(() => {});
}

async function revealInlineToolbar(section) {
  await section.scrollIntoViewIfNeeded();
  await section.hover();
  const toolbar = section.locator('.sfb-rsec-toolbar');
  await toolbar.waitFor({ state: 'visible', timeout: 5000 });
  return toolbar;
}

async function testInlineCanvasToolbar() {
  await check('canvas:inline-toolbar-command-surface', async () => {
    await switchBuilderPage('home');
    await removeAllOfKey('rich_text').catch(() => {});
    try {
      await addSection('rich_text');
      await selectSection('rich_text');

      let frame = await previewFrame();
      let section = frame.locator('[data-section-key="rich_text"]').last();
      let toolbar = await revealInlineToolbar(section);

      const commands = await toolbar
        .locator('[data-cmd]')
        .evaluateAll((els) => els.map((el) => el.dataset.cmd).sort());
      const expected = ['down', 'duplicate', 'lock', 'remove', 'toggle', 'up'].sort();
      assert(
        JSON.stringify(commands) === JSON.stringify(expected),
        `Inline toolbar command mismatch: ${JSON.stringify(commands)}`
      );

      const before = await sectionCount('rich_text');

      // Duplicate causes a Preview re-render. Re-select/re-hover afterwards
      // rather than trying to click controls that belonged to the old DOM.
      await toolbar.locator('[data-cmd="duplicate"]').click();
      await waitSectionCount('rich_text', before + 1);
      await clickUndo();
      await waitSectionCount('rich_text', before);

      await selectSection('rich_text');
      frame = await previewFrame();
      section = frame.locator('[data-section-key="rich_text"]').last();
      toolbar = await revealInlineToolbar(section);

      await toolbar.locator('[data-cmd="lock"]').click();
      await waitSectionLockState('rich_text', '1');

      // Lock also re-renders the section; acquire the new element and reveal
      // its toolbar before exercising Unlock.
      await selectSection('rich_text');
      frame = await previewFrame();
      section = frame.locator('[data-section-key="rich_text"]').last();
      toolbar = await revealInlineToolbar(section);

      assert(
        (await section.getAttribute('data-section-locked')) === '1',
        'Inline lock command did not lock section.'
      );
      await toolbar.locator('[data-cmd="lock"]').click();
      await waitSectionLockState('rich_text', '0');

      // Unlock re-renders again. Re-select and hover before Remove so this
      // remains a real user-visible interaction, not a forced hidden click.
      await selectSection('rich_text');
      frame = await previewFrame();
      section = frame.locator('[data-section-key="rich_text"]').last();
      toolbar = await revealInlineToolbar(section);

      await clickAcceptingDialog(toolbar.locator('[data-cmd="remove"]'));
      await waitSectionCount('rich_text', before - 1);
      await clickUndo();
      await waitSectionCount('rich_text', before);

      return { commands };
    } finally {
      await removeAllOfKey('rich_text').catch(() => {});
    }
  });
}

async function testLibraryDrag() {
  await check('library:drag-drop-onto-canvas', async () => {
    const key = 'rich_text';
    await removeAllOfKey(key).catch(() => {});
    try {
      const before = await sectionCount(key);
      const card = await findLibraryCard(key);
      const dt = await page.evaluateHandle(() => new DataTransfer());
      await card.dispatchEvent('dragstart', { dataTransfer: dt });
      const overlay = page.locator('.sfb-library-drop-overlay');
      await overlay.waitFor({ state: 'visible', timeout: 5000 });
      const box = await overlay.boundingBox();
      assert(box, 'Drop overlay has no bounding box.');
      await overlay.dispatchEvent('dragover', {
        dataTransfer: dt,
        clientX: box.x + box.width / 2,
        clientY: box.y + box.height / 2,
      });
      await page.waitForFunction(() => {
        const overlay = document.querySelector('.sfb-library-drop-overlay');
        return overlay && overlay.dataset.dragKey === 'rich_text' && overlay.dataset.dropIndex !== '';
      }, null, { timeout: 5000 });
      const addResponse = page.waitForResponse((response) =>
        response.request().method() === 'POST' && /\/storefront-builder\/sections\/add\/$/.test(new URL(response.url()).pathname),
        { timeout: 8000 }
      );
      await overlay.dispatchEvent('drop', {
        dataTransfer: dt,
        clientX: box.x + box.width / 2,
        clientY: box.y + box.height / 2,
      });
      const response = await addResponse;
      assert(response.ok(), `Library drop add returned HTTP ${response.status()}.`);
      await waitSectionCount(key, before + 1);
    } finally {
      await removeAllOfKey(key).catch(() => {});
    }
  });
}

async function testGlobalShell() {
  await check('shell:authenticated-builder-loads', async () => {
    assert(page.url().includes('/admin-portal/storefront-builder/'), `Unexpected builder URL: ${page.url()}`);
    assert(!page.url().includes('/login/'), 'QA session was not accepted.');
    await waitPreviewReady();
  });

  await check('shell:three-pane-layout-and-topbar', async () => {
    const values = await page.evaluate(() => {
      const rect = (selector) => document.querySelector(selector)?.getBoundingClientRect();
      const top = rect('.sfb-prototype-topbar');
      const lib = rect('.sfb-library-panel');
      const work = rect('.sfb-workspace');
      const inspector = rect('.sfb-inspector-panel');
      return {
        top: top && { width: top.width, height: top.height },
        lib: lib && { width: lib.width, height: lib.height },
        work: work && { width: work.width, height: work.height },
        inspector: inspector && { width: inspector.width, height: inspector.height },
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    assert(values.top && values.top.height >= 50 && values.top.height <= 85, `Unexpected topbar height: ${JSON.stringify(values.top)}`);
    assert(values.lib && values.lib.width >= 240 && values.lib.width <= 380, `Unexpected Library width: ${JSON.stringify(values.lib)}`);
    assert(values.inspector && values.inspector.width >= 280 && values.inspector.width <= 390, `Unexpected Inspector width: ${JSON.stringify(values.inspector)}`);
    assert(values.work && values.work.width > 500, `Workspace too narrow: ${JSON.stringify(values.work)}`);
    assert(values.overflow <= 3, `Builder root horizontal overflow: ${values.overflow}px`);
    return values;
  });

  await check('shell:all-top-level-buttons-are-wired', async () => auditInteractiveWiring(page.locator('.sfb-shell'), 'builder shell'));

  await check('shell:desktop-logical-viewport-is-1440', async () => {
    const data = await page.locator('#sfbPreviewFrame').evaluate((iframe) => ({
      declared: iframe.dataset.desktopViewportWidth,
      styleWidth: iframe.style.width,
      transform: iframe.style.transform,
    }));
    assert(data.declared === '1440', `Desktop viewport declaration is ${data.declared}`);
    assert(data.styleWidth === '1440px', `Desktop iframe logical width is ${data.styleWidth}`);
    assert(data.transform.includes('scale('), `Desktop iframe is not scaled: ${data.transform}`);
    await assertPreviewHealthy();
    return data;
  });

  await check('shell:desktop-mobile-toggle', async () => {
    const mobile = page.locator('.sfb-device-toggle button').filter({ hasText: 'موبایل' }).first();
    const desktop = page.locator('.sfb-device-toggle button').filter({ hasText: 'دسکتاپ' }).first();
    await mobile.click();
    await page.waitForTimeout(120);
    const mobileData = await page.locator('#sfbPreviewFrame').evaluate((iframe) => ({ width: iframe.style.width, transform: iframe.style.transform }));
    assert(mobileData.transform === 'none', `Mobile iframe still transformed: ${mobileData.transform}`);
    await assertPreviewHealthy();
    await desktop.click();
    await page.waitForTimeout(120);
    const desktopData = await page.locator('#sfbPreviewFrame').evaluate((iframe) => ({ width: iframe.style.width, transform: iframe.style.transform }));
    assert(desktopData.width === '1440px', 'Desktop logical width did not restore after mobile toggle.');
    return { mobileData, desktopData };
  });

  await check('shell:add-modal-focus-and-escape', async () => {
    const add = page.locator('.sfb-floating-add');
    await add.focus();
    await add.click();
    const dialog = page.locator('#sfbAddModal [role="dialog"], .sfb-add-modal [role="dialog"]').first();
    await dialog.waitFor({ state: 'visible' });
    const focusedInside = await page.evaluate(() => {
      const dialog = document.querySelector('#sfbAddModal [role="dialog"], .sfb-add-modal [role="dialog"]');
      return dialog && dialog.contains(document.activeElement);
    });
    assert(focusedInside, 'Focus did not move into Add dialog.');
    await page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'hidden' });
    const focusedAdd = await add.evaluate((el) => document.activeElement === el);
    assert(focusedAdd, 'Focus was not restored to Add button after closing dialog.');
  });

  await check('shell:fullscreen-enter-and-escape', async () => {
    const button = page.locator('.sfb-fullscreen-btn').first();
    await button.click();
    await page.waitForFunction(() => document.querySelector('.sfb-shell')?.classList.contains('sfb-fullscreen'));
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('.sfb-shell')?.classList.contains('sfb-fullscreen'));
  });

  await check('shell:preview-link-opens-real-draft-preview', async () => {
    const previewLink = page.locator('.sfb-prototype-topbar a').filter({ hasText: 'پیش‌نمایش' }).first();
    const popupPromise = context.waitForEvent('page');
    await previewLink.click();
    const popup = await popupPromise;
    await popup.waitForLoadState('domcontentloaded');
    assert(popup.url().includes('/admin-portal/storefront-builder/preview/'), `Unexpected preview popup URL: ${popup.url()}`);
    await popup.close();
  });

  await page.screenshot({ path: path.join(reportDir, 'builder-desktop-shell.png'), fullPage: true });
}


async function switchBuilderPage(value) {
  const selector = page.locator('.sfb-page-switcher select');
  if ((await selector.inputValue()) === value) return;
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    selector.selectOption(value),
  ]);
  await waitPreviewReady();
}

async function testPageSelector() {
  const selector = page.locator('.sfb-page-switcher select');
  const values = await selector.locator('option').evaluateAll((options) => options.map((o) => ({ value: o.value, label: o.textContent.trim() })));
  await check('pages:selector-contract', async () => {
    const expected = manifest.page_types.map((item) => item.value).sort();
    const actual = values.map((item) => item.value).sort();
    assert(JSON.stringify(actual) === JSON.stringify(expected), `Page selector mismatch: ${JSON.stringify(actual)} vs ${JSON.stringify(expected)}`);
    return values;
  });

  for (const item of values) {
    const row = { page: item.value, label: item.label, status: 'PASS' };
    const outcome = await check(`page:${item.value}:preview-and-library`, async () => {
      await switchBuilderPage(item.value);
      await assertPreviewHealthy();
      const cardKeys = await page.locator('.sfb-library-panel .sfb-lib-card[data-section-key]').evaluateAll((els) => els.map((el) => el.dataset.sectionKey).sort());
      const expectedKeys = (manifest.library_by_page[item.value] || []).map((d) => d.key).sort();
      assert(JSON.stringify(cardKeys) === JSON.stringify(expectedKeys), `Library keys mismatch on ${item.value}.`);
      const frame = await previewFrame();
      assert(new URL(frame.url()).searchParams.get('page') === item.value, `Preview iframe page mismatch on ${item.value}: ${frame.url()}`);
      return { library_count: cardKeys.length };
    });
    row.status = outcome.ok ? 'PASS' : 'FAIL';
    result.page_matrix.push(row);
    result.summary.pages_tested += 1;
  }

  await switchBuilderPage('home');
}

async function testGlobalPanelsAndLinks() {
  for (const label of ['هدر', 'فوتر', 'ظاهر سایت']) {
    await check(`global-panel:${label}`, async () => {
      const button = page.locator('.sfb-library-panel .sfb-prototype-block-btn').filter({ hasText: label }).first();
      await button.click();
      await page.locator('#sfbInspectorBody form:visible').first().waitFor({ state: 'visible', timeout: 10000 });
      await auditInteractiveWiring(page.locator('#sfbInspectorBody'), label);
      const submit = page.locator('#sfbInspectorBody button[type="submit"]:visible').filter({ hasText: /ذخیره/ }).first();
      if (await submit.count()) {
        await Promise.all([
          page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 12000 }),
          submit.click(),
        ]);
        await waitPreviewReady();
      }
    });
  }

  for (const label of ['مگامنو', 'تاریخچه نسخه‌ها']) {
    await check(`global-link:${label}`, async () => {
      const anchor = page.locator('.sfb-library-panel a').filter({ hasText: label }).first();
      assert((await anchor.count()) === 1, `${label} link missing.`);
      const href = await anchor.getAttribute('href');
      const response = await context.request.get(new URL(href, manifest.origin).toString());
      assert(response.status() >= 200 && response.status() < 400, `${label} returned HTTP ${response.status()}`);
      return { href, status: response.status() };
    });
  }
}

async function testKeyboardHistory() {
  await check('keyboard:undo-redo-shortcuts', async () => {
    await removeAllOfKey('rich_text').catch(() => {});
    try {
      const baseline = await sectionCount('rich_text');
      await addSection('rich_text');
      await waitSectionCount('rich_text', baseline + 1);
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+Z' : 'Control+Z');
      await waitSectionCount('rich_text', baseline);
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+Shift+Z' : 'Control+Shift+Z');
      await waitSectionCount('rich_text', baseline + 1);
    } finally {
      await removeAllOfKey('rich_text').catch(() => {});
    }
  });

  await check('keyboard:alt-arrow-section-move', async () => {
    await removeAllOfKey('rich_text').catch(() => {});
    try {
      await addSection('rich_text');
      const frame = await previewFrame();
      const section = frame.locator('[data-section-key="rich_text"]').last();
      await section.focus();
      const before = await previewSectionIdOrder();
      await section.press('Alt+ArrowUp');
      await waitSectionIdOrderChanged(before);
      const after = await previewSectionIdOrder();
      assert(JSON.stringify(before) !== JSON.stringify(after), 'Alt+ArrowUp did not move selected section.');
    } finally {
      await removeAllOfKey('rich_text').catch(() => {});
    }
  });
}

async function testDestructiveTopLevelControls() {
  await check('topbar:publish-button-real-submit', async () => {
    await addSection('rich_text');
    const publish = page.locator('.sfb-prototype-topbar button').filter({ hasText: 'انتشار' }).first();
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }),
      clickAcceptingDialog(publish),
    ]);
    assert(page.url().includes('/admin-portal/storefront-builder/'), `Publish navigated unexpectedly: ${page.url()}`);
    await waitPreviewReady();
  });

  await check('library:discard-draft-real-submit', async () => {
    const form = page.locator('.sfb-prototype-library-links form[action*="/discard/"]').first();
    assert((await form.count()) === 1, 'Discard Draft form is missing.');
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }),
      clickAcceptingDialog(form.locator('button[type="submit"]')),
    ]);
    assert(page.url().includes('/admin-portal/storefront-builder/'), `Discard navigated unexpectedly: ${page.url()}`);
    await waitPreviewReady();
  });
}

async function main() {
  browser = await launchSystemBrowser();
  context = await browser.newContext({ viewport: { width: 1650, height: 950 }, locale: 'fa-IR' });
  await context.addCookies([manifest.session]);
  await context.tracing.start({ screenshots: true, snapshots: true });
  page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') result.console_errors.push({ text: message.text(), location: message.location() });
  });
  page.on('pageerror', (error) => result.console_errors.push({ text: error.message, pageerror: true }));
  page.on('requestfailed', (request) => {
    const url = request.url();
    if (!url.startsWith('data:')) result.request_failures.push({ url, method: request.method(), error: request.failure()?.errorText || '' });
  });
  await page.goto(manifest.builder_url, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await testGlobalShell();
  await testPageSelector();
  await testGlobalPanelsAndLinks();

  const homeDefinitions = manifest.library_by_page.home || [];
  await check('registry:browser-home-library-is-nonempty', async () => {
    assert(homeDefinitions.length > 0, 'Home library manifest is empty.');
    return { home_library_count: homeDefinitions.length, registry_count: manifest.expected_registry_count };
  });

  // Exhaustive unique-section coverage: every general block is exercised once
  // on Home; context-specific blocks are then exercised on the first page where
  // they are actually allowed. This covers all registry definitions without
  // pointlessly repeating the same general block six times.
  const testedKeys = new Set(['announcement_bar']);
  await check('registry:hidden-announcement-sentinel-renders', async () => {
    await switchBuilderPage('home');
    const frame = await previewFrame();
    assert((await frame.locator('[data-section-key="announcement_bar"]').count()) === 1, 'Hidden announcement-bar sentinel did not render.');
  });

  for (const pageInfo of manifest.page_types) {
    await switchBuilderPage(pageInfo.value);
    const definitions = manifest.library_by_page[pageInfo.value] || [];
    for (const definition of definitions) {
      if (testedKeys.has(definition.key)) continue;
      testedKeys.add(definition.key);
      console.log(`\n=== SECTION ${definition.key} / ${definition.label} @ ${pageInfo.value} ===`);
      await testSection(definition);
    }
  }

  await check('registry:all-definitions-covered', async () => {
    const allKeys = new Set(manifest.all_definitions.map((item) => item.key));
    const missing = [...allKeys].filter((key) => !testedKeys.has(key));
    assert(missing.length === 0, `Registry definitions missing browser coverage: ${missing.join(', ')}`);
    assert(testedKeys.size === manifest.expected_registry_count, `Covered ${testedKeys.size}, registry has ${manifest.expected_registry_count}.`);
    return { covered: testedKeys.size };
  });

  await switchBuilderPage('home');
  await testInlineCanvasToolbar();
  await testLibraryDrag();
  await testRowLayouts();
  await testKeyboardHistory();

  await check('browser:console-errors', async () => {
    const meaningful = result.console_errors.filter((item) => !/favicon/i.test(item.text || ''));
    assert(meaningful.length === 0, `Console/page errors: ${JSON.stringify(meaningful.slice(0, 8))}`);
    return { count: meaningful.length };
  });
  await check('browser:request-failures', async () => {
    const meaningful = result.request_failures.filter((item) => {
      if (/favicon/i.test(item.url || '')) return false;
      const expectedPreviewAbort = (
        item.method === 'GET' &&
        item.error === 'net::ERR_ABORTED' &&
        /\/admin-portal\/storefront-builder\/preview\/\?page=/.test(item.url || '')
      );
      return !expectedPreviewAbort;
    });
    assert(meaningful.length === 0, `Failed network requests: ${JSON.stringify(meaningful.slice(0, 8))}`);
    return { count: meaningful.length };
  });

  // Publish and Discard are tested last because they intentionally alter Draft /
  // Published pointers. The Python wrapper restores the entire SQLite image.
  await testDestructiveTopLevelControls();

  await page.screenshot({ path: path.join(reportDir, 'builder-final.png'), fullPage: true });
}

try {
  await main();
} catch (error) {
  result.summary.failed += 1;
  result.checks.push({ name: 'qa-runner:fatal', status: 'FAIL', error: error.stack || error.message || String(error) });
  console.error(error.stack || error);
} finally {
  result.finished_at = new Date().toISOString();
  if (context) {
    try { await context.tracing.stop({ path: path.join(reportDir, 'playwright-trace.zip') }); } catch (_error) {}
  }
  if (browser) {
    try { await browser.close(); } catch (_error) {}
  }

  const sectionFailures = result.section_matrix.filter((row) => row.status === 'FAIL').length;
  const sectionWarnings = result.section_matrix.filter((row) => row.status === 'WARN').length;
  result.summary.section_failures = sectionFailures;
  result.summary.section_warnings = sectionWarnings;

  fs.writeFileSync(path.join(reportDir, 'browser-result.json'), JSON.stringify(result, null, 2), 'utf8');
  const markdown = [
    '# Storefront Builder Browser QA',
    '',
    `- Passed checks: **${result.summary.passed}**`,
    `- Failed checks: **${result.summary.failed}**`,
    `- Warnings: **${result.summary.warnings}**`,
    `- Sections tested: **${result.summary.sections_tested}**`,
    `- Pages tested: **${result.summary.pages_tested}**`,
    '',
    '## Section matrix',
    '',
    '| Section | Label | Result |',
    '|---|---|---|',
    ...result.section_matrix.map((row) => `| ${row.key} | ${String(row.label).replaceAll('|', '\\|')} | ${row.status} |`),
    '',
    '## Page matrix',
    '',
    '| Page | Result |',
    '|---|---|',
    ...result.page_matrix.map((row) => `| ${row.page} | ${row.status} |`),
    '',
    '## Failed / warning checks',
    '',
    ...result.checks.filter((item) => item.status !== 'PASS').map((item) => `- **${item.status}** ${item.name}: ${String(item.error || '').split('\n')[0]}`),
  ].join('\n');
  fs.writeFileSync(path.join(reportDir, 'browser-report.md'), markdown, 'utf8');
}

process.exit(result.summary.failed > 0 ? 1 : 0);
