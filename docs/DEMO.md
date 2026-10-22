# Hackathon demo script (≈6 minutes)

Before going on stage: open `https://<api>/api/health` (wakes a sleeping free instance), sign in once, and pre-load one live
project so its snapshot is cached. Keep the labelled offline demo (`Open labelled demo` on the dashboard) as a fallback.

1. **Problem (30 s)** — a map shows some competitors, a spreadsheet calculates margins; neither explains how location,
   affordability, competition and price interact.
2. **Create (60 s)** — New analysis → *Start a new business* → type **“gym”** (show it also works for “pizza shop”,
   “dental clinic”) → price ₹1,800 → capacity, rent, payroll → positioning → search a real locality → 3 km radius → Create.
3. **Explore (60 s)** — Market map: candidate, OSM competitors (amber), population zones, 3D buildings. Click a competitor:
   *Observed* vs *Unknown* (price) vs *Model-derived*. Evidence tab: retrieval vs source time, coverage signals.
3b. **Live market (60 s)** — Live market tab → 10,000 red dots at real density, each with 615 parameters (HUD shows
   “10,000 × 615 = 6,150,000 params”). Press play: awareness spreads, agents travel to you (cyan) or competitors (amber).
   **Click one dot** → Agent X-ray: genome heatmap, utility by channel vs the competitor it chose, the exact parameters
   (e.g. “relies on online reviews”) that cost you this customer.
3c. **Market DNA (45 s)** — the full matrix; “What makes your customers different”; “Where you win and lose”; then
   *Generate survey* → this is how the founder gets REAL feedback to replace assumptions.
4. **Baseline (45 s)** — Simulation Lab → Run. Units, revenue, operating profit, break-even, P(loss), histogram, synthetic
   agents coloured by choice.
5. **Change an assumption (45 s)** — Duplicate → price ₹1,500 → Run. Deltas vs baseline; price curve shows the trade-off
   (lower price is not automatically better).
6. **Missing evidence (45 s)** — Market map → Add competitor next door (user-observed, ₹1,400) → Rerun baseline → before/after.
7. **Compare and decide (45 s)** — Decisions: switch goal *Expected profit* ↔ *Low risk*; read recommendations, *What could
   make this result wrong?*, next actions.
8. **Science (30 s)** — /methodology: logit with outside option, affordability, Monte Carlo; validation status is honest.

Closing line: *StrataIQ does not claim to know every customer or every business. It makes assumptions visible, quantifies
uncertainty, and tells you what to verify before you invest.*
