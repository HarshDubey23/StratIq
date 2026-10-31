// End-to-end judge journey in a real browser. Writes screenshots + a log to ./out.
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE_URL || "http://localhost:3000";
const OUT = "out";
fs.mkdirSync(OUT, { recursive: true });
const log = [];
const L = (...a) => { const s = a.join(" "); console.log(s); log.push(s); };
let failures = 0;

const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
// The first-visit product tour is a modal; the journey tests the app behind it, so mark it seen.
await ctx.addInitScript(() => { try { localStorage.setItem("siq-tour-seen", "1"); } catch { /* ignore */ } });
const page = await ctx.newPage();
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) L(`[console.${m.type()}] ${m.text().slice(0, 300)}`); });
page.on("pageerror", (e) => { failures++; L(`[pageerror] ${e.message.slice(0, 500)}`); });
page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) L(`[http ${r.status()}] ${r.request().method()} ${r.url().replace(BASE, "")}`); });

async function shot(name) {
  await page.waitForTimeout(1200);
  const diag = await page.evaluate(() => {
    const maps = [...document.querySelectorAll('[data-testid="map"]')].map((m) => {
      const r = m.getBoundingClientRect();
      const c = m.querySelector("canvas");
      return `map ${Math.round(r.width)}x${Math.round(r.height)} canvas=${c ? `${c.width}x${c.height}` : "none"} markers=${m.querySelectorAll(".maplibregl-marker").length} text=${(m.textContent || "").slice(0, 60)}`;
    });
    let gl = "n/a";
    try { const cv = document.createElement("canvas"); gl = cv.getContext("webgl2") ? "webgl2" : cv.getContext("webgl") ? "webgl1" : "none"; } catch { gl = "err"; }
    return `${gl} | ${maps.join(" ; ")}`;
  }).catch(() => "");
  if (diag.includes("map")) L(`  diag ${name}: ${diag}`);
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

await step("landing", async () => { await page.goto(BASE); await page.getByText("before the lease.").first().waitFor(); await page.waitForTimeout(6000); await shot("01-landing"); });
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
  await page.waitForURL(/live/);
  await page.getByText("Live market simulation").waitFor({ timeout: 60000 });
  await page.waitForTimeout(4000);
  await shot("04a-demo-live");
  // Agent X-ray via deep link: an in-market agent close to the site that chose a competitor
  const pid = page.url().split("/projects/")[1].split("/")[0];
  const proj = await api(`/projects/${pid}`);
  const base = proj.body.scenarios.find((s) => s.is_baseline);
  const res = await api(`/simulation-runs/${base.latest_run.id}/results`);
  const abm = res.body.results.abm;
  const C = Object.fromEntries(abm.agents.columns.map((c, i) => [c, i]));
  const rows = abm.agents.rows.map((r, i) => [i, r]).filter(([, r]) => r[C.in_market]);
  rows.sort((a, b) => a[1][C.dist_km] - b[1][C.dist_km]);
  const lost = rows.find(([, r]) => r[C.last_choice] > 0) || rows[0];
  L(`genome per agent=${abm.genome?.per_agent} agents=${abm.n_agents} total=${abm.genome?.total_parameters} calib=${JSON.stringify(abm.calibration)}`);
  L(`decomposition lost-to-competitor: ${JSON.stringify(abm.decomposition?.chose_competitor?.channels)}`);
  L(`top drivers against you: ${(abm.top_drivers_against_you || []).slice(0, 5).map((d) => d.label + " " + d.mean_effect).join(" | ")}`);
  await page.goto(`${BASE}/app/projects/${pid}/live?agent=${lost[0]}`);
  await page.getByText("decision X-ray").waitFor({ timeout: 60000 });
  await page.getByText("Full genome · 615 parameters").waitFor({ timeout: 60000 });
  await page.waitForTimeout(2500);
  await shot("04b-demo-agent-xray");
  await page.goto(`${BASE}/app/projects/${pid}/genome`);
  await page.getByText("Every synthetic customer, every parameter").waitFor({ timeout: 30000 });
  await page.locator("canvas").first().waitFor({ timeout: 90000 });
  await page.waitForTimeout(1500);
  await shot("04c-demo-market-dna");
  const cv = await page.locator("canvas").first().boundingBox();
  await page.mouse.click(cv.x + cv.width * 0.4, cv.y + cv.height * 0.15);
  await page.getByText("decision X-ray").waitFor({ timeout: 60000 });
  await page.waitForTimeout(2000);
  await shot("04d-demo-dna-xray");
  await page.getByRole("button", { name: /Generate survey/ }).click();
  await page.getByText("Van Westendorp").first().waitFor({ timeout: 30000 });
  await page.getByText("Get real feedback").scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
  await shot("04e-demo-survey-kit");
  await page.goto(`${BASE}/app/projects/${pid}/live`);
  await page.getByText("Live market simulation").waitFor({ timeout: 60000 });
  await page.getByLabel("Project").getByRole("link", { name: "Simulation lab" }).click();
  await page.getByText("Operating profit / mo").first().waitFor({ timeout: 60000 });
  await shot("04-demo-lab-baseline");
  await page.getByRole("tab", { name: /Lower price/ }).click();
  await page.getByRole("button", { name: /Run simulation|Recalculate/ }).first().click();
  await page.getByText("vs baseline").first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(1500);
  await shot("05-demo-lab-lower-price");
  await page.getByRole("radio", { name: "Assumptions" }).click();
  await shot("06-demo-tornado");
  await page.getByLabel("Project").getByRole("link", { name: "Decisions" }).click();
  await page.getByText("What could make this result wrong?").waitFor({ timeout: 30000 });
  await shot("07-demo-decisions");
  await page.getByLabel("Project").getByRole("link", { name: "Market map" }).click();
  await page.waitForTimeout(3000);
  await shot("08-demo-market");
});

// ---------- Field research (ground truth) ----------
await step("field research", async () => {
  const projs = (await api("/projects")).body;
  const pid = projs[0].id;
  await page.goto(`${BASE}/app/projects/${pid}/field`);
  await page.getByText("Field research").first().waitFor({ timeout: 30000 });
  await shot("08b-field-request");
  await page.getByRole("button", { name: /Request field researcher/ }).click();
  await page.getByText("ASSIGNMENT").waitFor({ timeout: 30000 });
  const f = (await api(`/projects/${pid}/field`)).body;
  for (let i = 0; i < 9; i++) await api(`/field/${f.request.token}/records`, "POST", { kind: "interview", data: { uses_category: i % 3 === 0, max_price: 200 + 25 * i, visits_per_month: 4, travel_km: 1 + i * 0.3 } });
  await page.reload();
  await page.getByText("What the agents now use from the street").waitFor({ timeout: 30000 });
  await shot("08c-field-progress");
  const mob = await ctx.newPage();
  await mob.setViewportSize({ width: 390, height: 844 });
  await mob.goto(`${BASE}/field/${f.request.token}`);
  await mob.getByText("StrataIQ Field").waitFor({ timeout: 30000 });
  await mob.waitForTimeout(800);
  await mob.screenshot({ path: `${OUT}/08d-field-app-mobile.png` });
  L("shot 08d-field-app-mobile");
  await mob.close();
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
  await page.getByText("Data coverage").waitFor({ timeout: 280000 });
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
  for (let i = 0; i < 115 && st.status === "loading"; i++) { await page.waitForTimeout(2500); st = (await api(`/projects/${pid}/snapshots/${start.body.id}`)).body; }
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
  await page.goto(`${BASE}/app/projects/${pid}/live`);
  await page.getByText("Live market simulation").waitFor({ timeout: 60000 });
  await page.waitForTimeout(6000);
  await shot("16c-live-gym-agents");
  await page.getByLabel("Colour agents by").selectOption("segment");
  await page.waitForTimeout(2500);
  await shot("16d-live-gym-agents-segment");
  await page.mouse.click(700, 500);
  await page.waitForTimeout(1500);
  await shot("16e-live-gym-agent-click");
  await page.goto(`${BASE}/app/projects/${pid}/genome`);
  await page.getByText("Every synthetic customer, every parameter").waitFor({ timeout: 30000 });
  await page.locator("canvas").first().waitFor({ timeout: 90000 });
  await page.waitForTimeout(1500);
  await shot("16g-live-gym-dna");
  await page.goto(`${BASE}/app/projects/${pid}/factors`);
  await page.getByText("Factor Intelligence Engine").waitFor({ timeout: 30000 });
  await page.waitForTimeout(1500);
  await shot("16f-factors");
  const fac = await api(`/projects/${pid}/factors`);
  L(`factors: total=${fac.body.counts?.total} summary=${JSON.stringify(fac.body.summary)}`);
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
