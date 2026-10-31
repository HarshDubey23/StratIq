/**
 * Offline command router for Strata (used when the realtime ElevenLabs agent is not connected).
 * It understands Hinglish / English commands, runs the SAME client tools the realtime agent uses and speaks the
 * result in Hinglish. Every number in a reply comes from a tool result (simulation, live data, the page itself).
 * Returns null when it doesn't recognise the request, so the caller can fall back to the backend fact router.
 */
import { readPage } from "@/lib/screen";

type Tool = (args?: never) => Promise<string>;
export type Tools = Record<string, Tool>;

// ---------------------------------------------------------------- numbers
const UNIT: [RegExp, number][] = [
  [/^(crore|cr)$/i, 1e7],
  [/^(lakh|lac|lakhs|l)$/i, 1e5],
  [/^(k|thousand|hazaar|hazar|hajar|hazaar)$/i, 1e3],
];
const AMOUNT = /(?:₹|rs\.?|inr|rupees?)?\s*(\d+(?:,\d{2,3})*(?:\.\d+)?)\s*(crore|cr|lakhs?|lac|l|k|thousand|hazaar|hazar|hajar)?\b/gi;

/** Every amount in the text with its position: "80 hazaar" → 80000, "1.2 lakh" → 120000, "₹2,500" → 2500. */
export function amounts(q: string): { v: number; at: number }[] {
  const out: { v: number; at: number }[] = [];
  for (const m of q.matchAll(AMOUNT)) {
    let v = Number(m[1].replace(/,/g, ""));
    const u = m[2] && UNIT.find(([re]) => re.test(m[2]!));
    if (u) v *= u[1];
    if (Number.isFinite(v)) out.push({ v, at: m.index ?? 0 });
  }
  return out;
}

const FIELDS: [string, RegExp, string][] = [
  ["rent", /\b(rent|kiraya|kiraaya|bhada|bhaada)\b/i, "rent"],
  ["payroll", /\b(salary|salaries|payroll|tankhwah|tankha|wages|staff (cost|kharcha))\b/i, "salary"],
  ["marketing_spend", /\b(marketing|ads?|advertis\w*|promotion|prachar)\b/i, "marketing"],
  ["utilities", /\b(bijli|electricity|utilities|utility|light bill)\b/i, "bijli-paani"],
  ["startup_cost", /\b(startup|start-up|setup|investment|budget|lagat)\b/i, "startup cost"],
  ["variable_cost_per_unit", /\b(variable cost|cost per (unit|cup|plate|order|item)|raw material)\b/i, "per-unit cost"],
  ["price", /\b(price|fees?|daam|dam|keemat|kimat|charge|rate|mrp)\b/i, "price"],
];

/** Plan fields mentioned with an amount next to them: "rent 80 hazaar aur price 300" → {rent: 80000, price: 300}. */
export function planChanges(q: string): Record<string, number> {
  const nums = amounts(q);
  const out: Record<string, number> = {};
  const used = new Set<number>();
  for (const [key, re] of FIELDS) {
    const m = re.exec(q);
    if (!m) continue;
    const end = m.index + m[0].length;
    // prefer the first amount after the word, else the closest one before it
    const after = nums.find((n) => n.at >= end && n.at - end < 40 && !used.has(n.at));
    const before = [...nums].reverse().find((n) => n.at < m.index && m.index - n.at < 25 && !used.has(n.at));
    const hit = after || before;
    if (hit && hit.v > 0) {
      out[key] = hit.v;
      used.add(hit.at);
    }
  }
  return out;
}

// ---------------------------------------------------------------- formatting (Indian style)
export function inr(x: unknown): string {
  const v = Number(x);
  if (x === null || x === undefined || !Number.isFinite(v)) return "pata nahi";
  const a = Math.abs(v);
  const s = a >= 1e7 ? `₹${(a / 1e7).toFixed(a >= 1e8 ? 0 : 1)} crore` : a >= 1e5 ? `₹${(a / 1e5).toFixed(a >= 1e6 ? 0 : 1)} lakh` : `₹${Math.round(a).toLocaleString("en-IN")}`;
  return v < 0 ? `${s} ka loss` : s;
}
const num = (x: unknown) => (Number.isFinite(Number(x)) ? Math.round(Number(x)).toLocaleString("en-IN") : "?");
const pct = (x: unknown) => (Number.isFinite(Number(x)) ? `${Math.round(Number(x) * 100)}%` : "?");
const parse = (s: string) => {
  try {
    return JSON.parse(s);
  } catch {
    return { text: s };
  }
};
const label = (k: string) => FIELDS.find(([f]) => f === k)?.[2] || k;

const PAGE_WORDS: [string, RegExp, string][] = [
  ["market", /\b(market map|map|naksha|competitors? map|3d)\b/i, "Market map"],
  ["field", /\b(field( data| research| page)?|ground data|researcher page)\b/i, "Field data"],
  ["live", /\b(live( market)?|agents?|log kaise chun)\b/i, "Live market"],
  ["simulation", /\b(simulation( lab)?|lab|scenario|what.?if page)\b/i, "Simulation lab"],
  ["decisions", /\b(decisions?|verdict|faisla|go.?no.?go)\b/i, "Decisions"],
  ["report", /\b(report|pdf)\b/i, "Report"],
  ["genome", /\b(dna|genome)\b/i, "Market DNA"],
  ["factors", /\b(factors?|615)\b/i, "615 factors"],
  ["monitor", /\b(monitor\w*|actuals)\b/i, "Monitoring"],
  ["overview", /\b(overview|project (home|page)|summary page)\b/i, "Overview"],
  ["dashboard", /\b(dashboard|all projects|projects page)\b/i, "Dashboard"],
  ["new_project", /\b(new (project|analysis)|naya project)\b/i, "New analysis"],
  ["methodology", /\b(methodology|method)\b/i, "Methodology"],
  ["settings", /\b(settings?)\b/i, "Settings"],
  ["home", /\b(home ?page|landing)\b/i, "Home"],
];
const PAGE_NAME: Record<string, string> = { market: "Market map", field: "Field data", live: "Live market", simulation: "Simulation lab", decisions: "Decisions", report: "Report",
  genome: "Market DNA", factors: "615 factors", monitor: "Monitoring" };

const OPEN = /\b(open|kholo|khol do|khol|dikhao|dikha do|le chalo|chalo|jao|go to|show|take me)\b/i;
const TRY = /\b(try|test|dekho|dekh|check|what if|kya hoga|simulate karke|karke dekho)\b/i;

function pageNameFromPath(p: string) {
  const seg = p.split("/").filter(Boolean);
  if (seg[0] !== "app") return p === "/" ? "home page" : p.replace("/", "");
  if (seg.length === 1) return "dashboard (aapke projects)";
  if (seg[1] === "projects" && seg[2] === "new") return "new analysis form";
  if (seg[1] === "projects") return PAGE_NAME[seg[3] || ""] || "project overview";
  return seg[1];
}

/** What is on the page, in two or three spoken sentences. */
function describePage(): string {
  const pg = readPage();
  if (!pg) return "Screen padh nahi paaya.";
  const name = pageNameFromPath(pg.path);
  const heads = pg.headings.filter((h) => h.length < 80).slice(0, 4);
  const n = (pg.numbers || {}) as Record<string, unknown>;
  const facts: string[] = [];
  if (n.day !== undefined) facts.push(`simulation day ${num(n.day)}`);
  if (n.orders_today !== undefined) facts.push(`aaj ${num(n.orders_today)} orders`);
  if (n.competitors !== undefined) facts.push(`${num(n.competitors)} competitors map pe`);
  if (n.profit_per_month !== undefined) facts.push(`profit ${inr(n.profit_per_month)} mahina`);
  let s = `Aap ${name} pe ho.`;
  if (heads.length) s += ` Yahan dikh raha hai: ${heads.join("; ")}.`;
  if (facts.length) s += ` Numbers: ${facts.join(", ")}.`;
  return s;
}

function runSentence(o: Record<string, unknown>): string {
  const a = o.after as Record<string, number> | null;
  const b = o.before as Record<string, number> | null;
  if (!a) return "";
  const unit = (a as unknown as { unit?: string }).unit || "customers";
  let s = ` Ab profit ${inr(a.profit_per_month)} mahina`;
  if (b && b.profit_per_month !== undefined) s += ` (pehle ${inr(b.profit_per_month)})`;
  s += `, lagbhag ${num(a.units_per_month)} ${unit} mahine me`;
  if (a.break_even_units) s += `, break-even ${num(a.break_even_units)} ${unit} pe`;
  if (a.chance_of_loss !== undefined && a.chance_of_loss !== null) s += `, aur loss wale mahine ka chance ${pct(a.chance_of_loss)}`;
  return s + ".";
}

/** Try to handle the request locally. `say` speaks an interim line for slow tools. */
export async function route(qRaw: string, t: Tools, ctx: { projectOpen: boolean; say: (s: string) => void }): Promise<string | null> {
  const q = qRaw.trim();
  const call = async (name: string, args?: Record<string, unknown>) => parse(await (t[name] as (a?: Record<string, unknown>) => Promise<string>)(args));
  const needProject = "Iske liye pehle ek project kholo — bolo 'mere projects dikhao' ya apna idea batao, jaise 'Indiranagar me café kholna hai'.";

  // 1. a new business idea
  if (/\b(kholna|kholni|kholunga|start karna|shuru karna|open karna|i want to (open|start)|want to start|planning to open)\b/i.test(q) && !/\bproject\b/i.test(q)) {
    ctx.say("Theek hai, project bana raha hoon aur live market dhoondh raha hoon.");
    const o = await call("start_new_idea", { description: q });
    return o.created
      ? `Project ban gaya: ${o.business}${o.place ? `, ${String(o.place).split(",").slice(0, 2).join(",")}` : ""}. Market map pe live competitors aur population load ho rahe hain, ek minute me baseline simulation apne aap chalega.`
      : "Place samajh nahi aaya, isliye form khol diya hai — bas jagah select kar do.";
  }

  // 2. change the plan (permanent) or test a what-if
  const changes = planChanges(q);
  if (Object.keys(changes).length) {
    if (!ctx.projectOpen) return needProject;
    const what = Object.entries(changes).map(([k, v]) => `${label(k)} ${inr(v)}`).join(", ");
    if (TRY.test(q) && !/\b(kar do|kardo|set|save|update)\b/i.test(q)) {
      ctx.say(`${what} pe simulation chala raha hoon.`);
      if (Object.keys(changes).length === 1 && changes.price) {
        const o = await call("test_price", { price: changes.price });
        if (o.error) return `Simulation nahi chal payi: ${o.error}`;
        const w = (o.what_if || {}) as Record<string, number>;
        const b = (o.baseline || {}) as Record<string, number>;
        return `Price ${inr(changes.price)} pe: profit ${inr(w.operating_profit_per_month)} mahina, abhi ke ${inr(b.operating_profit_per_month)} ke muqable. ` +
          `Customers ${num(w.customers_or_units_per_month)} vs ${num(b.customers_or_units_per_month)}` +
          (w.probability_of_loss != null ? `, loss ka chance ${pct(w.probability_of_loss)}` : "") +
          `. Ye sirf what-if hai, plan nahi badla — save karna ho to bolo 'price ${num(changes.price)} kar do'.`;
      }
      const o = await call("test_strategy", changes);
      if (o.error) return `Simulation nahi chal payi: ${o.error}`;
      return `${what} wala strategy live map pe chala diya. ${o.spoken || ""}`.trim();
    }
    ctx.say(`${what} set kar raha hoon aur dobara simulate kar raha hoon.`);
    const o = await call("update_plan", changes);
    if (o.error) return `Plan update nahi hua: ${o.error}`;
    return `${what} kar diya aur dobara simulate kiya.${runSentence(o)}`;
  }

  // 3. report
  if (/\b(report|pdf)\b/i.test(q) && /\b(bana|banao|bana do|make|create|generate|naya|nayi|chahiye)\b/i.test(q)) {
    if (!ctx.projectOpen) return needProject;
    ctx.say("Report bana raha hoon.");
    const o = await call("make_report");
    return o.error ? `Report nahi ban payi: ${o.error}` : "Feasibility report bana di aur khol di. Wahin se print ya share kar sakte ho.";
  }

  // 4. best location
  if (/\b(best|sabse (acchi|achhi|badhiya)|better|ideal|top|right)\s+(location|locatin|locaton|site|jagah|spot|area|place)\b|kahan khol|konsi jagah|kaun si jagah|where should i open|location (batao|dikhao|suggest)/i.test(q)) {
    if (!ctx.projectOpen) return needProject;
    ctx.say("Aapka plan har populated jagah pe test kar raha hoon.");
    const o = await call("find_best_location");
    if (o.error) return `Location scan nahi ho paya: ${o.error}`;
    const cur = o.current_site || {};
    const best = (o.best_sites || [])[0];
    if (!best) return "Is catchment me compare karne layak dusri jagah nahi mili.";
    if (Number(best.profit_per_month) <= Number(cur.profit_per_month))
      return `Aapki current site hi is area me best hai: ${inr(cur.profit_per_month)} mahina profit. Agli best jagah ${inr(best.profit_per_month)} deti hai.`;
    return `Sabse acchi jagah aapki site se ${best.from_current_km} km door hai — wahan same plan se ${inr(best.profit_per_month)} mahina profit, abhi ke ${inr(cur.profit_per_month)} ke muqable. ` +
      `Ek km me ${num(best.people_within_1km)} log aur 500 m me ${num(best.competitors_within_500m)} competitors. Map pe green pillars me dikha diya. Rent wahan same maana hai, isliye local rent check kar lena.`;
  }

  // 5. best strategy / how to increase profit
  if (/\b(best|optimal|sabse (zyada|jyada|accha))\s+(strategy|price|plan|pricing)|optimi[sz]e|maximi[sz]e|profit (kaise|kese) badh|zyada profit|munafa (kaise|badh)/i.test(q)) {
    if (!ctx.projectOpen) return needProject;
    ctx.say("Price, marketing aur capacity ke sainkdon combinations test kar raha hoon.");
    const o = await call("optimize_strategy");
    if (o.error) return `Optimizer nahi chal paya: ${o.error}`;
    const b = o.best || {};
    const c = o.current || {};
    return `${num(o.combinations_tested)} combinations me sabse zyada profit: price ${inr(b.price)}, marketing ${inr(b.marketing_spend)} mahina` +
      (b.capacity_scale && b.capacity_scale !== 1 ? `, capacity ${Math.round((b.capacity_scale - 1) * 100)}% zyada` : "") +
      ` — profit ${inr(b.profit_per_month)} mahina, abhi ke ${inr(c.profit_per_month)} ke muqable. Bolo 'ye test karo' to main isse live map pe chala dunga.`;
  }

  // 6. analysis / insights
  if (/\b(analy[sz]\w*|insight|suggest\w*|advice|sujhav|kya galat|problem|improve|kaise badhe|kya karu|what should i (do|change))\b/i.test(q)) {
    if (!ctx.projectOpen) return needProject;
    const o = await call("get_insights");
    if (o.error) return `Analysis abhi nahi ho paya: ${o.error}. Pehle simulation chalao — bolo 'data load karo'.`;
    return String(o.spoken || o.summary || o.text || "Is run ke liye insights nahi mile.");
  }

  // 7. what is on screen
  if (/\b(screen|is page|ye page|yeh page|yahan|yaha)\b|kya dikh|what (am i|are we|is) (looking|seeing|on)|what do you see|explain (this|the page)|samjhao ye/i.test(q)) {
    return describePage();
  }

  // 8. field research
  if (/\b(researcher|field (research|visit|data)|ground (data|reality)|survey|banda bhejo|koi bhejo)\b/i.test(q)) {
    if (!ctx.projectOpen) return needProject;
    if (/\b(status|kitne|kya hua|progress|update)\b/i.test(q)) {
      const o = await call("get_field_status");
      const c = (o.summary?.counts || {}) as Record<string, number>;
      return o.request ? `Field research chal raha hai: ${num(c.interview || 0)} interviews, ${num(c.competitor || 0)} competitor visits, ${num(c.footfall || 0)} footfall counts aur ${num(c.rent || 0)} rent quotes save hue hain.`
        : "Abhi tak koi field researcher request nahi hua. Bolo 'researcher bhejo'.";
    }
    const o = await call("request_field_researcher", { brief: q });
    return o.error ? `Request nahi ho paya: ${o.error}` : `${o.specialty} request ho gaya. Field data page khol diya — wahan ka link WhatsApp pe researcher ko bhej do; wo phone se interviews, rivals ke daam, footfall aur rent bharega.`;
  }

  // 9. load live data and run
  if (/\b(load|refresh|reload|update)\b.*\b(data|market)\b|\bdata load\b|simulation chalao|run (the )?simulation|baseline chalao/i.test(q)) {
    if (!ctx.projectOpen) return needProject;
    ctx.say("Live market data load kar raha hoon, isme ek-do minute lag sakte hain.");
    const o = await call("load_market_and_simulate");
    if (o.error) return `Load nahi ho paya: ${o.error}`;
    if (o.status === "still_loading") return "Data abhi bhi load ho raha hai, background me chalta rahega. Thodi der me poochna.";
    if (o.status === "failed") return "Live data abhi load nahi ho paya — OpenStreetMap busy ho sakta hai. Thodi der baad try karo.";
    const s = o.simulation || {};
    return `Live data aa gaya aur simulation chal gayi: lagbhag ${num(s.units_per_month)} ${s.unit || "customers"} mahina, profit ${inr(s.profit_per_month)}${s.chance_of_loss !== undefined ? `, loss ka chance ${pct(s.chance_of_loss)}` : ""}.`;
  }

  // 10. projects
  if (/\b(mere|my|saare|all)\s+projects?\b|projects? (dikhao|list|batao)/i.test(q)) {
    const o = await call("list_projects");
    if (!Array.isArray(o)) return "Projects dekhne ke liye sign in karna hoga.";
    if (!o.length) return "Abhi koi project nahi hai. Apna idea batao, main bana deta hoon.";
    await call("navigate", { page: "dashboard" });
    return `Aapke ${o.length} projects hain: ${o.slice(0, 5).map((p: { name: string }) => p.name).join(", ")}. Kaunsa kholu?`;
  }
  const projName = q.match(/^(.+?)\s+(wala\s+)?project\s+(kholo|khol do|open)/i) || q.match(/\bopen\s+(the\s+)?(.+?)\s+project\b/i);
  if (projName) {
    const name = (projName[2] && projName[2] !== "the " ? projName[2] : projName[1]).trim();
    const o = await call("open_project", { name });
    return o.opened ? `${o.opened} khol diya.` : `"${name}" naam ka project nahi mila. Aapke projects: ${(o.projects || []).slice(0, 5).join(", ")}.`;
  }

  // 11. demo, guide, goal
  if (/\bdemo\b/i.test(q)) {
    ctx.say("Live demo khol raha hoon.");
    return String((await (t.start_demo as () => Promise<string>)()) || "Demo khol diya.");
  }
  if (/\b(guide|tour|how it works|kaise (use|chalaye|chalate)|walk me through)\b/i.test(q)) {
    await call("open_guide");
    return "Screen pe 'How it works' guide khol diya — paanch steps me poora app samjha deta hai.";
  }
  if (/\b(risk kam|low risk|safe (rehna|chahiye))\b/i.test(q)) {
    await call("set_goal", { goal: "low_risk" });
    return "Theek hai, ab recommendations sabse kam risk ke hisaab se aayengi.";
  }

  // 12. navigation
  if (OPEN.test(q)) {
    const hit = PAGE_WORDS.find(([, re]) => re.test(q));
    if (hit) {
      const [page, , name] = hit;
      const projectPage = !["dashboard", "new_project", "methodology", "settings", "home"].includes(page);
      if (projectPage && !ctx.projectOpen) return needProject;
      await call("navigate", { page });
      return `${name} khol diya. Is page ke baare me jaanna ho to bolo 'is page pe kya hai'.`;
    }
  }

  // 13. a word's meaning
  const term = q.match(/^(?:what is|what's|explain)\s+(.+?)\??$/i) || q.match(/^(.+?)\s+(?:kya hota hai|kya hai|ka matlab|means|meaning)\??$/i);
  if (term && term[1].split(" ").length <= 4) {
    const o = await call("explain_term", { term: term[1] });
    if (o.meaning) return `${o.term}: ${o.meaning}`;
  }

  return null;
}
