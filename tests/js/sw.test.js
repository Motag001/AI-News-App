const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../../web/sw.js"), "utf8");

class FakeResponse {
  constructor(body, ok = true) { this.body = body; this.ok = ok; }
  clone() { return new FakeResponse(this.body, this.ok); }
}

/** Run sw.js against an in-memory Cache Storage and a controllable network. */
function load() {
  const listeners = {};
  const stores = new Map();
  const state = { online: true, network: {}, fetched: [] };
  const keyOf = (request) => (typeof request === "string" ? request : request.url);
  const makeCache = (name) => {
    if (!stores.has(name)) stores.set(name, new Map());
    const store = stores.get(name);
    return {
      addAll: async (urls) => urls.forEach((url) => store.set(new URL(url, "https://app.test").href, new FakeResponse(`shell:${url}`))),
      put: async (request, response) => { store.set(keyOf(request), response); },
      match: async (request) => store.get(new URL(keyOf(request), "https://app.test").href),
      keys: async () => [...store.keys()].map((url) => ({ url })),
      delete: async (request) => store.delete(keyOf(request)),
    };
  };
  const caches = {
    open: async (name) => makeCache(name),
    keys: async () => [...stores.keys()],
    delete: async (name) => stores.delete(name),
    match: async (request) => {
      for (const name of stores.keys()) {
        const hit = await makeCache(name).match(request);
        if (hit) return hit;
      }
      return undefined;
    },
  };
  const self = {
    location: { origin: "https://app.test" },
    clients: { claim: async () => {} },
    skipWaiting: async () => {},
    addEventListener: (type, handler) => { listeners[type] = handler; },
  };
  const context = {
    self, caches, URL,
    fetch: async (request) => {
      const url = keyOf(request);
      state.fetched.push(url);
      if (!state.online) throw new TypeError("offline");
      return new FakeResponse(state.network[new URL(url).pathname] ?? `net:${url}`);
    },
    Promise, Object, console,
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  const dispatch = async (type, extra = {}) => {
    let pending;
    listeners[type]({ waitUntil: (p) => { pending = p; }, respondWith: (p) => { pending = p; }, ...extra });
    return pending;
  };
  const request = (url, init = {}) => ({ url: `https://app.test${url}`, method: "GET", mode: "cors", ...init });
  return { dispatch, request, state, stores, listeners };
}

test("install precaches the app shell", async () => {
  const sw = load();
  await sw.dispatch("install");
  const shell = [...sw.stores.get("shell-v1").keys()];
  assert.ok(shell.includes("https://app.test/"));
  assert.ok(shell.includes("https://app.test/assets/app.js"));
});

test("activate removes caches from older versions and keeps current ones", async () => {
  const sw = load();
  await sw.dispatch("install");
  sw.stores.set("shell-v0", new Map());
  await sw.dispatch("activate");
  assert.ok(!sw.stores.has("shell-v0"));
  assert.ok(sw.stores.has("shell-v1"));
});

test("pages load from the network when online and fall back to the cached shell offline", async () => {
  const sw = load();
  await sw.dispatch("install");
  const online = await sw.dispatch("fetch", { request: sw.request("/pulse", { mode: "navigate" }) });
  assert.match(online.body, /^net:/);
  sw.state.online = false;
  const offline = await sw.dispatch("fetch", { request: sw.request("/story/abc", { mode: "navigate" }) });
  assert.equal(offline.body, "shell:/");
});

test("story data is served from the last copy when the network is down", async () => {
  const sw = load();
  await sw.dispatch("install");
  sw.state.network["/api/v1/stories"] = "fresh-stories";
  const request = sw.request("/api/v1/stories");
  assert.equal((await sw.dispatch("fetch", { request })).body, "fresh-stories");
  sw.state.online = false;
  assert.equal((await sw.dispatch("fetch", { request })).body, "fresh-stories");
});

test("an offline request with nothing saved fails instead of inventing a response", async () => {
  const sw = load();
  await sw.dispatch("install");
  sw.state.online = false;
  await assert.rejects(sw.dispatch("fetch", { request: sw.request("/api/v1/stories?q=never-seen") }));
});

test("writes and other origins are never intercepted", async () => {
  const sw = load();
  let handled = false;
  const respondWith = () => { handled = true; };
  sw.listeners.fetch({ request: sw.request("/api/v1/pulse/2026-10-31/challenge/answer", { method: "POST" }), respondWith });
  sw.listeners.fetch({ request: { url: "https://images.example/photo.jpg", method: "GET", mode: "no-cors" }, respondWith });
  assert.equal(handled, false);
});

test("the health check is never cached", async () => {
  const sw = load();
  let handled = false;
  sw.listeners.fetch({ request: sw.request("/api/v1/health"), respondWith: () => { handled = true; } });
  assert.equal(handled, false);
});
