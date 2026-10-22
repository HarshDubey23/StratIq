// End-to-end judge journey in a real browser. Writes screenshots + a log to ./out.
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE_URL || "http://localhost:3000";
const OUT = "out";
fs.mkdirSync(OUT, { recursive: true });
const log = [];
const L = (...a) => { const s = a.join(" "); console.log(s); log.push(s); };
let failures = 0;

const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) L(`[console.${m.type()}] ${m.text().slice(0, 300)}`); });
page.on("pageerror", (e) => { failures++; L(`[pageerror] ${e.message.slice(0, 500)}`); });
page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) L(`[http ${r.status()}] ${r.request().method()} ${r.url().replace(BASE, "")}`); });

async function shot(name) {
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
  L(`shot ${name} @ ${page.url().replace(BASE, "")}`);
}
async function step(name, fn) {
  try { await fn(); L(`OK   ${name}`); }
  catch (e) { failures++; L(`FAIL ${name}: ${String(e).slice(0, 400)}`); await page.screenshot({ path: `${OUT}/FAIL-${name.replace(/\W+/g, "_")}.png` }).catch(() => {}); }
}
const api = (path, method = "GET", body) => page.evaluate(async ([p, m, b]) => {
  const r = await fetch(`/api/v1${p}`, { method: m, headers: b ? { "Content-Type": "application/json" } : {}, body: b ? JSON.stringify(b) : undefined, credentials: "include" });
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch { j = t; }
  return { status: r.status, body: j };
}, [path, method, body]);

await step("landing", async () => { await page.goto(BASE); await page.getByText("Test your business before you risk your money.").waitFor(); await shot("01-landing"); });
await step("methodology", async () => { await page.goto(`${BASE}/methodology`); await page.getByText("Customer-choice model").waitFor(); });
await step("sign up", async () => {
  await page.goto(`${BASE}/sign-up`);
  await page.fill("#email", `judge${Date.now()}@example.com`);
  await page.fill("#password", "judge-password-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL(/onboarding/);
  await shot("02-onboarding");
  await page.getByRole("button", { name: "Skip for now" }).click();
  await page.waitForURL(/\/app$/);
  await shot("03-dashboard");
});

// ---------- Offline demo ----------
await step("demo project", async () => {
  await page.getByRole("button", { name: /Open labelled demo/ }).click();
  await page.waitForURL(/simulation/);
  await page.getByRole("button", { name: /Run simulation/ }).first().click();
  await page.getByText("Operating profit / mo").first().waitFor({ timeout: 60000 });
  await shot("04-demo-lab-baseline");
  await page.getByRole("tab", { name: /Lower price/ }).click();
  await page.getByRole("button", { name: /Run simulation|Recalculate/ }).first().click();
  await page.getByText("vs baseline").first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(1500);
  await shot("05-demo-lab-lower-price");
  await page.getByRole("radio", { name: "Assumptions" }).click();
  await shot("06-demo-tornado");
  await page.getByRole("link", { name: "Decisions" }).click();
  await page.getByText("What could make this result wrong?").waitFor({ timeout: 30000 });
  await shot("07-demo-decisions");
  await page.getByRole("link", { name: "Market map" }).click();
  await page.waitForTimeout(3000);
  await shot("08-demo-market");
});

// ---------- Wizard UI ----------
await step("wizard ui", async () => {
  await page.goto(`${BASE}/app/projects/new?objective=start_new`);
  await page.getByRole("button", { name: /Next/ }).click();
  await page.getByPlaceholder("e.g. pizza shop").fill("pizza shop");
  await page.getByRole("button", { name: /Match/ }).click();
  await page.getByText("Pizza outlet").first().waitFor({ timeout: 20000 });
  await shot("09-wizard-category");
  await page.getByRole("button", { name: /Next/ }).click();
  await page.getByPlaceholder("e.g. 1800").fill("450");
  await shot("10-wizard-profile");
  await page.getByRole("button", { name: /Next/ }).click();
  await page.getByRole("button", { name: /Next/ }).click();
  await page.getByRole("button", { name: /Next/ }).click();
  await page.getByLabel("Search place").fill("Connaught Place, New Delhi");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator("ul button").first().click({ timeout: 30000 });
  await page.waitForTimeout(2500);
  await shot("11-wizard-location");
  await page.getByRole("button", { name: /Next/ }).click();
  await shot("12-wizard-review");
  await page.getByRole("button", { name: "Create market simulation" }).click();
  await page.waitForURL(/market/, { timeout: 60000 });
  await page.waitForTimeout(3000);
  await shot("13a-live-market-loading");
  await page.getByText("Data coverage").waitFor({ timeout: 200000 });
  await page.waitForTimeout(4000);
  await shot("13-live-market-pizza");
  await page.getByRole("button", { name: /Competitors/ }).click();
  await shot("13b-live-pizza-competitors");
});

// ---------- Live gym project via API (Connaught Place) ----------
await step("live gym journey", async () => {
  const cat = await api("/categories/resolve", "POST", { query: "gym", use_ai: false });
  const p = await api("/projects", "POST", {
    name: "Live gym — Connaught Place", objective: "start_new", decision_goal: "profit", category: cat.body, profile: {},
    location: { label: "Location A", address: "Connaught Place, New Delhi", lat: 28.6315, lng: 77.2167, catchment: { mode: "radius", radius_km: 2.5 } },
    baseline: { price: 1800, quality: 0.6, marketing_spend: 15000, capacity: { max_members: 350 }, rent: 90000, payroll: 90000, utilities: 18000, other_fixed: 12000, startup_cost: 2000000 },
  });
  L(`project create ${p.status}`);
  const pid = p.body.id, lid = p.body.locations[0].id;
  const start = await api(`/projects/${pid}/locations/${lid}/refresh`, "POST");
  L(`refresh start ${start.status} ${start.body.status}`);
  let st = start.body;
  for (let i = 0; i < 90 && st.status === "loading"; i++) { await page.waitForTimeout(2500); st = (await api(`/projects/${pid}/snapshots/${start.body.id}`)).body; }
  const snapFull = await api(`/projects/${pid}/market?location_id=${lid}`);
  const snap = { body: snapFull.body.snapshot || {} };
  L(`snapshot status=${snap.body.status} pop=${JSON.stringify(snap.body.population)} errors=${JSON.stringify(snap.body.errors)} sources=${(snap.body.sources || []).map((s) => s.layer + ":" + (s.from_cache ? "cache" : "live")).join(",")}`);
  L(`coverage=${JSON.stringify(snap.body.coverage)}`);
  const mk = await api(`/projects/${pid}/market?location_id=${lid}`);
  L(`competitors found: ${mk.body.competitors?.length}; first: ${mk.body.competitors?.slice(0, 3).map((c) => c.name).join(" | ")}`);
  await page.goto(`${BASE}/app/projects/${pid}/market`);
  await page.waitForTimeout(6000);
  await shot("14-live-gym-market");
  const firstComp = page.locator("aside ul button").first();
  await page.getByRole("button", { name: /Competitors/ }).click();
  if (await firstComp.count()) { await firstComp.click(); await shot("15-live-competitor-detail"); }
  await page.goto(`${BASE}/app/projects/${pid}/simulation`);
  await page.getByRole("button", { name: /Run simulation/ }).first().click();
  await page.getByText("Profit distribution").waitFor({ timeout: 90000 });
  await page.waitForTimeout(3000);
  await shot("16-live-gym-lab");
  await page.mouse.wheel(0, 900);
  await shot("16b-live-gym-lab-scrolled");
  const runs = await api(`/projects/${pid}/compare`);
  const m = runs.body.rows[0].metrics;
  L(`live gym baseline: units=${m.units_sold} profit=${m.operating_profit} p_loss=${m.prob_loss} in_market=${m.in_market_units}`);
  const dec = await api(`/projects/${pid}/decisions`);
  L(`decision: ${dec.body.verdict} — ${dec.body.headline}`);
  await page.goto(`${BASE}/app/projects/${pid}/decisions`);
  await page.getByText("Recommended next actions").waitFor({ timeout: 30000 });
  await shot("17-live-decisions");
  await page.goto(`${BASE}/app/projects/${pid}/report`);
  await page.getByRole("button", { name: /Generate from latest/ }).click();
  await page.getByText("Business concept").waitFor({ timeout: 30000 });
  await shot("18-live-report");
});

fs.writeFileSync(`${OUT}/journey.log`, log.join("\n"));
await browser.close();
L(`failures=${failures}`);
process.exit(failures ? 1 : 0);
