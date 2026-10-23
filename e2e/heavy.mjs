// Dense-market check: a café in Koramangala (hundreds of rivals) end to end through the public API.
const API = process.env.API_URL || "https://strataiq-api.vercel.app/api/v1";
let cookie = "";
async function call(path, method = "GET", body) {
  const t = Date.now();
  const r = await fetch(API + path, { method, headers: { "Content-Type": "application/json", cookie }, body: body ? JSON.stringify(body) : undefined });
  const sc = r.headers.get("set-cookie");
  if (sc) cookie = sc.split(";")[0];
  const text = await r.text();
  let j; try { j = JSON.parse(text); } catch { j = text.slice(0, 300); }
  console.log(`${method} ${path} -> ${r.status} in ${((Date.now() - t) / 1000).toFixed(1)}s`);
  return { status: r.status, body: j };
}
const idea = process.env.IDEA || "A café in Koramangala, Bengaluru, coffee at ₹250";
await call("/auth/guest", "POST");
const plan = (await call("/quickstart/plan", "POST", { text: idea })).body;
console.log("plan:", plan.category?.label, "|", plan.place?.display_name, "| ready", plan.ready);
const p = (await call("/quickstart/create", "POST", { plan })).body;
const loc = p.locations[0].id;
const snap = (await call(`/projects/${p.id}/locations/${loc}/refresh`, "POST")).body;
console.log("snapshot:", snap.status, "errors", JSON.stringify(snap.errors || []).slice(0, 300));
const proj = (await call(`/projects/${p.id}`)).body;
const sc = proj.scenarios[0];
const run = await call(`/scenarios/${sc.id}/runs`, "POST");
const res = run.body.results || {};
console.log("run:", run.status, "competitors in model", res.competitors?.length, "| agents weigh", res.abm?.competitors_simulated, "of", res.abm?.competitors_total,
  "| units", res.summary?.units_sold, "| abm months", JSON.stringify(res.abm?.monthly_units), "| duration ms", run.body.duration_ms);
const opt = await call(`/projects/${p.id}/optimize`);
console.log("optimize:", opt.status, opt.body.evaluated, "best profit", opt.body.best?.profit);
const sites = await call(`/projects/${p.id}/sites`);
console.log("sites:", sites.status, "scanned", sites.body.candidates?.length, "top", sites.body.top?.[0]?.profit);
const strat = await call(`/projects/${p.id}/strategy`, "POST", { marketing_spend: 40000, from_scenario_id: sc.id });
console.log("strategy:", strat.status, strat.body.comparison?.verdict);
if (run.status !== 201 || opt.status !== 200 || sites.status !== 200 || strat.status !== 200) process.exit(1);
