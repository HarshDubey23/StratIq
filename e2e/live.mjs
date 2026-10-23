// Smoke test of the PUBLIC deployment: the judge journey on live data. Screenshots + log in ./out-live.
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE_URL || "https://strataiq-rho.vercel.app";
const OUT = "out-live";
fs.mkdirSync(OUT, { recursive: true });
const log = [];
const L = (...a) => { const s = a.join(" "); console.log(s); log.push(s); };
let failures = 0;

const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") L(`[console.error] ${m.text().slice(0, 300)}`); });
page.on("pageerror", (e) => { failures++; L(`[pageerror] ${e.message.slice(0, 500)}`); });
page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) L(`[http ${r.status()}] ${r.request().method()} ${r.url().replace(BASE, "")}`); });

const shot = async (name, ms = 1500) => { await page.waitForTimeout(ms); await page.screenshot({ path: `${OUT}/${name}.png` }); L(`shot ${name} @ ${page.url().replace(BASE, "")}`); };
async function step(name, fn) {
  const t = Date.now();
  try { await fn(); L(`OK   ${name} (${Math.round((Date.now() - t) / 1000)}s)`); }
  catch (e) { failures++; L(`FAIL ${name}: ${String(e).slice(0, 400)}`); await page.screenshot({ path: `${OUT}/FAIL-${name.replace(/\W+/g, "_")}.png` }).catch(() => {}); }
}
const api = (path, method = "GET", body) => page.evaluate(async ([p, m, b]) => {
  const r = await fetch(`/api/v1${p}`, { method: m, headers: b ? { "Content-Type": "application/json" } : {}, body: b ? JSON.stringify(b) : undefined, credentials: "include" });
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch { j = t; }
  return { status: r.status, body: j };
}, [path, method, body]);

let pid = null;
await step("landing", async () => {
  await page.goto(BASE);
  await page.getByText("is a market.").first().waitFor({ timeout: 60000 });
  await shot("01-hero", 12000);
  for (const [i, id] of [[2, "real"], [3, "agents"], [5, "voice"]]) {
    await page.evaluate((x) => document.getElementById(x)?.scrollIntoView(), id);
    await shot(`0${i}-chapter-${id}`, 5000);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
});

await step("open live demo (guest)", async () => {
  await page.getByRole("button", { name: "Pizza", exact: true }).click();
  await page.waitForTimeout(15000);
  await shot("06-hero-pizza", 1000);
  await page.getByRole("button", { name: /Open the live demo/ }).first().click();
  await page.waitForURL(/\/app\/projects\/.+\/market/, { timeout: 280000 });
  pid = page.url().split("/projects/")[1].split("/")[0];
  await shot("10-market", 10000);
  const mk = await api(`/projects/${pid}/market?location_id=${(await api(`/projects/${pid}`)).body.locations[0].id}`);
  L(`snapshot status=${mk.body.snapshot?.status} pop=${mk.body.snapshot?.population?.total} competitors=${mk.body.competitors?.length} sources=${(mk.body.snapshot?.sources || []).map((s) => `${s.layer}:${s.name}`).join(" | ")}`);
  L(`errors=${JSON.stringify(mk.body.snapshot?.errors || [])}`);
  L(`first competitors: ${mk.body.competitors?.slice(0, 6).map((c) => c.name).join(" | ")}`);
});

await step("competitor list", async () => {
  await page.getByRole("button", { name: /Competitors/ }).first().click();
  await shot("10b-competitors", 2500);
});

await step("overview", async () => {
  await page.goto(`${BASE}/app/projects/${pid}`);
  await shot("11-overview", 9000);
});

await step("simulation", async () => {
  const proj = (await api(`/projects/${pid}`)).body;
  for (const s of proj.scenarios) {
    if (!s.latest_run) { const r = await api(`/scenarios/${s.id}/runs`, "POST"); L(`run ${s.name}: ${r.status}`); }
  }
  await page.goto(`${BASE}/app/projects/${pid}/simulation`);
  await page.getByText("Operating profit / mo").first().waitFor({ timeout: 90000 });
  await shot("12-lab", 3000);
  const cmp = await api(`/projects/${pid}/compare`);
  cmp.body.rows.forEach((r) => L(`scenario ${r.scenario.name}: units=${r.metrics?.units_sold} profit=${r.metrics?.operating_profit} p_loss=${r.metrics?.prob_loss}`));
});

await step("live agents", async () => {
  await page.goto(`${BASE}/app/projects/${pid}/live`);
  await page.getByText("Live market simulation").waitFor({ timeout: 90000 });
  await shot("13-live", 9000);
});

await step("live: smooth daily orders + strategy lab", async () => {
  const proj = (await api(`/projects/${pid}`)).body;
  const base = proj.scenarios.find((s) => s.is_baseline);
  const run = (await api(`/simulation-runs/${base.latest_run.id}/results`)).body.results.abm;
  const later = run.daily.units_you.slice(14);
  L(`daily orders (wk3+): min=${Math.min(...later)} max=${Math.max(...later)} distinct=${new Set(later.map((x) => Math.round(x))).size} zeros=${later.filter((x) => x === 0).length} scale=${run.scale} cap/day=${run.capacity_per_day}`);
  const ins = await api(`/projects/${pid}/insights?scenario_id=${base.id}`);
  L(`insights [${ins.status}]: ${(ins.body.insights || []).map((i) => i.title).join(" | ")}`);
  L(`suggested: ${JSON.stringify(ins.body.suggested)}`);
  await page.goto(`${BASE}/app/projects/${pid}/live`);
  await page.getByText("Change your strategy").waitFor({ timeout: 90000 });
  await page.getByRole("radio", { name: "+50%" }).first().click();
  const mk = page.getByRole("slider", { name: "Marketing spend per month" });
  await mk.focus();
  for (let i = 0; i < 20; i++) await page.keyboard.press("ArrowRight");
  await shot("13b-strategy-lab", 800);
  await page.getByRole("button", { name: /Run \d change/ }).click();
  await page.getByText(/Growing — this strategy works|More profit, similar volume|More sales, less profit|Not better/).first().waitFor({ timeout: 180000 });
  await shot("13c-strategy-compare", 6000);
});

await step("decisions", async () => {
  await page.goto(`${BASE}/app/projects/${pid}/decisions`);
  await page.getByText("What could make this result wrong?").waitFor({ timeout: 60000 });
  await shot("14-decisions", 2000);
});

await step("voice analyst (grounded answers)", async () => {
  for (const q of ["kitne competitors hain?", "what is my profit", "what is the break even", "try price 300", "how do agents decide whom to choose?", "what insights do you see on this map?", "double the marketing"]) {
    const r = await api(`/projects/${pid}/assistant/ask`, "POST", { question: q, screen: await page.evaluate(() => window.__strataScreen || null) });
    L(`Q: ${q} -> [${r.status}] ${typeof r.body === "object" ? r.body.answer : r.body}`);
  }
  const f = await api(`/projects/${pid}/assistant/facts`);
  L(`facts: competitors=${f.body.market?.competitors_found} pop=${f.body.market?.population_in_catchment} baseline_profit=${f.body.baseline?.operating_profit_per_month}`);
  await page.goto(`${BASE}/app/projects/${pid}/market`);
  await page.waitForTimeout(4000);
  await page.getByRole("button", { name: /Talk to Strata/ }).click();
  await shot("15-voice-dock", 4000);
});

fs.writeFileSync(`${OUT}/journey.log`, log.join("\n"));
await browser.close();
L(`failures=${failures}`);
process.exit(failures ? 1 : 0);
