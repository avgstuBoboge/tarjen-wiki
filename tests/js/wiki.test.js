// tests/js/wiki.test.js
// 用 node:test 跑（node ≥ 18 自带，无 npm install）。
// 跑法：node --test tests/js/
//
// wiki.js 是浏览器脚本（挂在 window.Wiki 上），用 vm 模块跑在带 mock 的 sandbox 里。

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const WIKI_JS = fs.readFileSync(
  path.join(__dirname, '..', '..', 'docs', 'assets', 'wiki.js'),
  'utf8'
);

// ---- sandbox loader ----

/**
 * 跑一次 wiki.js 在带 mock 的 vm context 里，返回 window.Wiki。
 *
 * @param {object} opts
 * @param {string} [opts.token]     预置 token
 * @param {Function} [opts.fetchImpl] 自定义 fetch
 * @param {object}   [opts.elements]  document.getElementById mock 返回的元素，key = id
 */
function loadWiki({ token = '', fetchImpl = null, elements = {} } = {}) {
  const store = {};
  if (token) store['gh_token_v1'] = token;

  const localStorage = {
    getItem(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem(k, v) { store[k] = String(v); },
    removeItem(k) { delete store[k]; },
  };

  const document = {
    getElementById(id) { return elements[id] || null; },
    addEventListener: () => {},
    removeEventListener: () => {},
  };

  // window 需要 addEventListener/removeEventListener，因为 wiki.js 直接调
  const win = {
    addEventListener: () => {},
    removeEventListener: () => {},
  };

  // Node 18+ 移除了 global btoa/atob，但 wiki.js 用了
  const btoa = (s) => Buffer.from(s, 'binary').toString('base64');
  const atob = (s) => Buffer.from(s, 'base64').toString('binary');

  const ctx = {
    window: win,
    localStorage,
    document,
    console,
    fetch: fetchImpl,
    setTimeout,
    clearTimeout,
    btoa, atob,
    confirm: () => true,  // 默认点「确定」
  };
  vm.createContext(ctx);
  vm.runInContext(WIKI_JS, ctx);
  return { Wiki: win.Wiki, store, win, doc: document };
}

// ---- token ----

test('getToken returns "" when not configured', () => {
  const { Wiki } = loadWiki();
  assert.equal(Wiki.getToken(), '');
});

test('setToken + getToken roundtrip', () => {
  const { Wiki, store } = loadWiki();
  Wiki.setToken('ghp_test_xxx');
  assert.equal(Wiki.getToken(), 'ghp_test_xxx');
  assert.equal(store['gh_token_v1'], 'ghp_test_xxx');
});

test('setToken("") removes the key', () => {
  const { Wiki, store } = loadWiki({ token: 'old' });
  Wiki.setToken('');
  assert.equal(Wiki.getToken(), '');
  assert.equal(store['gh_token_v1'], undefined);
});

// ---- URLs ----

test('apiUrl constructs correct Contents API URL', () => {
  const { Wiki } = loadWiki();
  assert.equal(
    Wiki.apiUrl('contests.csv'),
    'https://api.github.com/repos/tarjen/tarjen-wiki/contents/contests.csv'
  );
});

test('rawUrl constructs correct raw URL', () => {
  const { Wiki } = loadWiki();
  assert.equal(
    Wiki.rawUrl('docs/contests/foo.md'),
    'https://raw.githubusercontent.com/tarjen/tarjen-wiki/main/docs/contests/foo.md'
  );
});

// ---- esc ----

test('esc escapes all dangerous chars', () => {
  const { Wiki } = loadWiki();
  assert.equal(Wiki.esc('<script>'), '&lt;script&gt;');
  assert.equal(Wiki.esc('a&b'), 'a&amp;b');
  assert.equal(Wiki.esc(`"foo" 'bar'`), '&quot;foo&quot; &#39;bar&#39;');
  assert.equal(Wiki.esc(''), '');
  assert.equal(Wiki.esc(null), '');
  assert.equal(Wiki.esc(undefined), '');
});

// ---- commitFile ----

test('commitFile: GET SHA → PUT with same SHA + b64 content', async () => {
  const calls = [];
  const fakeFetch = async (url, opts = {}) => {
    calls.push({ url, method: opts.method || 'GET', body: opts.body, headers: opts.headers });
    if (calls.length === 1) return { ok: true, status: 200, json: async () => ({ sha: 'abc123' }) };
    return { ok: true, status: 200, json: async () => ({ commit: { sha: 'new' } }) };
  };
  const { Wiki } = loadWiki({ token: 'ghp_t', fetchImpl: fakeFetch });

  const result = await Wiki.commitFile('contests.csv', 'hello,world\n', 'test commit');

  assert.equal(calls.length, 2);
  // 1) GET
  assert.equal(calls[0].method, 'GET');
  assert.ok(calls[0].url.endsWith('?ref=main'), 'should pass ?ref=main');
  // 2) PUT
  assert.equal(calls[1].method, 'PUT');
  const body = JSON.parse(calls[1].body);
  assert.equal(body.sha, 'abc123', 'should pass SHA from GET');
  assert.equal(body.branch, 'main');
  assert.equal(body.message, 'test commit');
  assert.equal(body.content, Buffer.from('hello,world\n').toString('base64'),
    'content should be base64 of UTF-8 string');
  // 3) Authorization header should be set
  assert.match(calls[0].headers.Authorization, /^Bearer ghp_t$/);
  // 4) Should return the PUT response
  assert.equal(result.commit.sha, 'new');
});

test('commitFile: 401 → friendly Chinese error', async () => {
  const fakeFetch = async () => ({
    ok: false, status: 401,
    json: async () => ({ message: 'Bad credentials' }),
  });
  const { Wiki } = loadWiki({ token: 'ghp_bad', fetchImpl: fakeFetch });
  await assert.rejects(
    Wiki.commitFile('contests.csv', 'x', 'm'),
    /Token 无效或已过期.*Bad credentials/
  );
});

test('commitFile: 404 → friendly "找不到文件" error', async () => {
  const fakeFetch = async () => ({
    ok: false, status: 404,
    json: async () => ({ message: 'Not Found' }),
  });
  const { Wiki } = loadWiki({ token: 'ghp_t', fetchImpl: fakeFetch });
  await assert.rejects(
    Wiki.commitFile('wrong.csv', 'x', 'm'),
    /找不到文件.*Not Found/
  );
});

test('commitFile: 500 GET → raw error message', async () => {
  const fakeFetch = async () => ({
    ok: false, status: 500,
    json: async () => ({ message: 'Internal server error' }),
  });
  const { Wiki } = loadWiki({ token: 'ghp_t', fetchImpl: fakeFetch });
  await assert.rejects(
    Wiki.commitFile('contests.csv', 'x', 'm'),
    /Internal server error/
  );
});

test('commitFile: PUT 422 (e.g. SHA mismatch) propagates message', async () => {
  let n = 0;
  const fakeFetch = async (url, opts = {}) => {
    n++;
    if (n === 1) return { ok: true, status: 200, json: async () => ({ sha: 'old' }) };
    return {
      ok: false, status: 422,
      json: async () => ({ message: 'does not match' }),
    };
  };
  const { Wiki } = loadWiki({ token: 'ghp_t', fetchImpl: fakeFetch });
  await assert.rejects(
    Wiki.commitFile('contests.csv', 'x', 'm'),
    /does not match/
  );
});

test('commitFile: without token → throws "No PAT configured"', async () => {
  const { Wiki } = loadWiki();
  await assert.rejects(
    Wiki.commitFile('contests.csv', 'x', 'm'),
    /No PAT configured/
  );
});

test('commitFile: b64 handles non-ASCII (中文) correctly', async () => {
  const calls = [];
  const fakeFetch = async (url, opts = {}) => {
    calls.push({ url, method: opts.method || 'GET', body: opts.body });
    if (calls.length === 1) return { ok: true, status: 200, json: async () => ({ sha: 's' }) };
    return { ok: true, status: 200, json: async () => ({}) };
  };
  const { Wiki } = loadWiki({ token: 't', fetchImpl: fakeFetch });
  await Wiki.commitFile('c.csv', '中文,2024.1.1\n', 'msg');
  const body = JSON.parse(calls[1].body);
  // decode and compare
  const decoded = Buffer.from(body.content, 'base64').toString('utf8');
  assert.equal(decoded, '中文,2024.1.1\n');
});

// ---- wireTokenUI ----

test('wireTokenUI: refresh shows configured state when token exists', () => {
  const inp = { value: '' };
  const btnSv = { addEventListener: () => {} };
  const btnCl = { style: {}, addEventListener: () => {} };
  const st = { textContent: '' };
  const { Wiki } = loadWiki({
    token: 'ghp_x',
    elements: { 'gh-token': inp, 'btn-save-token': btnSv, 'btn-clear-token': btnCl, 'token-status': st },
  });
  Wiki.wireTokenUI();
  assert.equal(inp.value, '••••••••••');
  assert.equal(st.textContent, '✓ 已配置');
});

test('wireTokenUI: refresh shows unconfigured state when no token', () => {
  const inp = { value: '' };
  const btnCl = { style: {}, addEventListener: () => {} };
  const st = { textContent: '' };
  const { Wiki } = loadWiki({
    elements: { 'gh-token': inp, 'btn-clear-token': btnCl, 'token-status': st },
  });
  Wiki.wireTokenUI();
  assert.equal(inp.value, '');
  assert.equal(st.textContent, '未配置');
  assert.equal(btnCl.style.display, 'none');
});

test('wireTokenUI: save button persists new token', () => {
  let saveHandler;
  const inp = { value: '' };
  const btnSv = { addEventListener: (_evt, fn) => { saveHandler = fn; } };
  const btnCl = { style: {}, addEventListener: () => {} };
  const { Wiki, store } = loadWiki({
    elements: { 'gh-token': inp, 'btn-save-token': btnSv, 'btn-clear-token': btnCl, 'token-status': { textContent: '' } },
  });
  Wiki.wireTokenUI();
  inp.value = 'ghp_new_token';
  saveHandler();
  assert.equal(store['gh_token_v1'], 'ghp_new_token');
});

test('wireTokenUI: paste with bullet prefix (••) is rejected', () => {
  let saveHandler;
  const inp = { value: '' };
  const btnSv = { addEventListener: (_evt, fn) => { saveHandler = fn; } };
  const { Wiki, store } = loadWiki({
    elements: { 'gh-token': inp, 'btn-save-token': btnSv, 'btn-clear-token': { style: {}, addEventListener: () => {} }, 'token-status': { textContent: '' } },
  });
  Wiki.wireTokenUI();
  inp.value = '••••••••••';
  saveHandler();
  // 没有真的 token 写进去
  assert.equal(store['gh_token_v1'], undefined);
});

test('wireTokenUI: clear button wipes token', () => {
  let clearHandler;
  const inp = { value: '' };
  const btnSv = { addEventListener: () => {} };
  const btnCl = { style: {}, addEventListener: (_evt, fn) => { clearHandler = fn; } };
  const { Wiki, store } = loadWiki({
    token: 'old',
    elements: { 'gh-token': inp, 'btn-save-token': btnSv, 'btn-clear-token': btnCl, 'token-status': { textContent: '' } },
  });
  Wiki.wireTokenUI();
  clearHandler();
  assert.equal(store['gh_token_v1'], undefined);
});

test('wireTokenUI: missing DOM elements → silent no-op (graceful degrade)', () => {
  const { Wiki } = loadWiki();  // 没有任何 elements
  // 不应抛
  assert.doesNotThrow(() => Wiki.wireTokenUI());
});

// ---- wireBeforeUnload ----

test('wireBeforeUnload: dirty → preventDefault on beforeunload', () => {
  const winListeners = {};
  const win = {
    addEventListener: (evt, fn) => { winListeners[evt] = fn; },
    removeEventListener: () => {},
  };
  const docListeners = {};
  const document = {
    addEventListener: (evt, fn) => { docListeners[evt] = fn; },
    getElementById: () => null,
  };
  const { Wiki } = loadWiki();
  // override window & document
  Wiki.wireBeforeUnload(function () { return true; }, null);
  // 找到并调 beforeunload handler——需要重写测试方法，调用 wiki.js 注册的 listener
  // 用 monkey-patch 重做：
  // 我们重新 load wiki.js 这一次用我们的 win/document
  const localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  const btoa = (s) => Buffer.from(s, "binary").toString("base64");
  const atob = (s) => Buffer.from(s, "base64").toString("binary");
  const ctx = { window: win, document, localStorage, console, setTimeout, clearTimeout, confirm: () => true, btoa, atob };
  vm.createContext(ctx);
  vm.runInContext(WIKI_JS, ctx);
  ctx.window.Wiki.wireBeforeUnload(function () { return true; }, null);
  const e = { preventDefault: () => { e._prevented = true; }, returnValue: null };
  winListeners.beforeunload(e);
  assert.equal(e._prevented, true);
  assert.equal(e.returnValue, '');
});

test('wireBeforeUnload: clean → no preventDefault', () => {
  const winListeners = {};
  const win = {
    addEventListener: (evt, fn) => { winListeners[evt] = fn; },
    removeEventListener: () => {},
  };
  const document = { addEventListener: () => {}, getElementById: () => null };
  const localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  const btoa = (s) => Buffer.from(s, "binary").toString("base64");
  const atob = (s) => Buffer.from(s, "base64").toString("binary");
  const ctx = { window: win, document, localStorage, console, setTimeout, clearTimeout, confirm: () => true, btoa, atob };
  vm.createContext(ctx);
  vm.runInContext(WIKI_JS, ctx);
  ctx.window.Wiki.wireBeforeUnload(function () { return false; }, null);
  const e = { preventDefault: () => { e._prevented = true; }, returnValue: null };
  winListeners.beforeunload(e);
  assert.equal(e._prevented, undefined);
});

test('wireBeforeUnload: Ctrl+S calls onSave', () => {
  const winListeners = {};
  const docListeners = {};
  const win = { addEventListener: (evt, fn) => { winListeners[evt] = fn; }, removeEventListener: () => {} };
  const document = { addEventListener: (evt, fn) => { docListeners[evt] = fn; }, getElementById: () => null };
  const localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  const btoa = (s) => Buffer.from(s, "binary").toString("base64");
  const atob = (s) => Buffer.from(s, "base64").toString("binary");
  const ctx = { window: win, document, localStorage, console, setTimeout, clearTimeout, confirm: () => true, btoa, atob };
  vm.createContext(ctx);
  vm.runInContext(WIKI_JS, ctx);

  let saveCalled = 0;
  ctx.window.Wiki.wireBeforeUnload(function () { return false; }, function () { saveCalled++; });
  const e = { metaKey: false, ctrlKey: true, key: 's', preventDefault: () => {} };
  docListeners.keydown(e);
  assert.equal(saveCalled, 1);
});

test('wireBeforeUnload: Cmd+S (mac) also calls onSave', () => {
  const win = { addEventListener: () => {}, removeEventListener: () => {} };
  const docListeners = {};
  const document = { addEventListener: (evt, fn) => { docListeners[evt] = fn; }, getElementById: () => null };
  const localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  const btoa = (s) => Buffer.from(s, "binary").toString("base64");
  const atob = (s) => Buffer.from(s, "base64").toString("binary");
  const ctx = { window: win, document, localStorage, console, setTimeout, clearTimeout, confirm: () => true, btoa, atob };
  vm.createContext(ctx);
  vm.runInContext(WIKI_JS, ctx);

  let saveCalled = 0;
  ctx.window.Wiki.wireBeforeUnload(function () { return false; }, function () { saveCalled++; });
  const e = { metaKey: true, ctrlKey: false, key: 's', preventDefault: () => {} };
  docListeners.keydown(e);
  assert.equal(saveCalled, 1);
});

test('wireBeforeUnload: plain "s" key does NOT trigger save', () => {
  const win = { addEventListener: () => {}, removeEventListener: () => {} };
  const docListeners = {};
  const document = { addEventListener: (evt, fn) => { docListeners[evt] = fn; }, getElementById: () => null };
  const localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  const btoa = (s) => Buffer.from(s, "binary").toString("base64");
  const atob = (s) => Buffer.from(s, "base64").toString("binary");
  const ctx = { window: win, document, localStorage, console, setTimeout, clearTimeout, confirm: () => true, btoa, atob };
  vm.createContext(ctx);
  vm.runInContext(WIKI_JS, ctx);

  let saveCalled = 0;
  ctx.window.Wiki.wireBeforeUnload(function () { return false; }, function () { saveCalled++; });
  const e = { metaKey: false, ctrlKey: false, key: 's', preventDefault: () => {} };
  docListeners.keydown(e);
  assert.equal(saveCalled, 0);
});
