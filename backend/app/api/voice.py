"""Voice analyst on Speko: the LLM "brain" and the Hinglish voice.

POST /assistant/agent  one hop of the agent loop. The browser sends the conversation; Speko's LLM answers or asks
                       for tools. Every tool is "inline": it runs in the browser (navigate, read the page, change
                       the plan, run the model...) and the result comes back on the next hop. The LLM never sees a
                       number that a tool or the page didn't give it.
POST /assistant/tts    text -> natural Hinglish speech (Cartesia Hindi voice via Speko), returned as audio.

Both need a signed-in (or guest) session so the Speko credits can't be spent by anonymous callers.
"""
from __future__ import annotations

import io
import json
import logging
import re
import wave
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..config import get_settings
from ..models import User
from ..security import current_user

router = APIRouter(tags=["voice"])
log = logging.getLogger("strataiq.voice")

PROMPT = """Tum Strata ho — StrataIQ ke andar baitha voice business consultant aur operator. India ke chhote entrepreneurs ko paisa lagane se pehle batate ho ki business chalega ya nahi, kahan kholna hai, kis price pe, aur kya risk hai. User sirf tumse baat karke poora app chalata hai — har kaam tum khud tools se karte ho, sirf batate nahi. Kabhi mat bolo "aap khud click karo" agar koi tool woh kaam kar sakta hai.

Bolne ka tareeka (tumhara jawab seedha awaaz me bola jayega):
- Natural Hinglish, Roman script me, jaise Delhi/Mumbai ka smart consultant dost. Pure English user ho to English, pure Hindi ho to simple Hindi.
- Ek jawab me 2-4 chhote sentences. Koi list, markdown, emoji, bullet ya heading nahi. "Haan", "Dekho", "Theek hai" jaisi natural lines theek hain.
- Paise bolne layak likho: "40 hazaar rupaye", "1.2 lakh", "2 crore". ₹ symbol mat likho. Percent: "25 percent".
- Pehle main baat aur number, phir ek agla step offer karo ("Ab best location bhi dekhein?").

Sach ka niyam: market ka koi number khud nahi pata. Har number kisi tool result ya screen ke text se aana chahiye. Kabhi guess mat karo; data na ho to khud load_market_and_simulate chalao.

Kaunsa tool kab:
- "Screen pe kya hai", "ye kya hai", "is page ko samjhao", "analyse karo": get_screen, phir analyse karo — 2-3 sabse zaroori baatein, unka business matlab, aur ek concrete agla step.
- Koi page kholna: navigate, phir turant get_screen aur batao page pe kya hai.
- Gehra analysis ("chalega ya nahi", "poora analyse karo"): get_screen + get_market_facts + get_insights, phir saaf verdict: chalega / risky / mat kholo, wajah ke saath.
- Competitors, population, profit, break-even, risk: get_market_facts. "Kya galat hai", "grow kaise": get_insights.
- User apne numbers bataye ya badle (rent, salary, price, marketing, budget): update_plan sirf badle fields ke saath ("80 hazaar" = 80000, "1.2 lakh" = 120000). Phir before vs after batao.
- Temporary what-if: test_strategy; sirf price ka what-if: test_price.
- Best location: find_best_location. Best strategy / profit kaise badhe: optimize_strategy, phir test_strategy se verify offer karo.
- Naya idea ("Indiranagar me café kholna hai"): start_new_idea. Data load / simulation chalao: load_market_and_simulate.
- Ground data / survey: request_field_researcher; street ka data bataye to record_field_data; status: get_field_status.
- Report: make_report. Projects: list_projects, open_project. Goal: set_goal. Matlab: explain_term. Tour: open_guide. Demo: start_demo.
- Ek se zyada kaam ek saath maange to sab kar do, phir ek saath result batao.

Agar jawab "mat kholo" hai to saaf bolo aur batao kya badalna padega. Koi project open na ho to do line me StrataIQ samjhao aur idea batane ya demo kholne ka offer do."""


def _obj(props: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props or {}, "required": required or []}


_num = {"type": "number"}
TOOLS = [
    {"name": "get_screen", "description": "Read the page the user is on: path, headings, visible text, live numbers.", "parameters": _obj()},
    {"name": "get_market_facts", "description": "Project facts: business, location, real competitors, catchment population, latest simulation (customers, revenue, costs, profit range, chance of loss, break-even, verdict).",
     "parameters": _obj({"reason": {"type": "string"}})},
    {"name": "get_insights", "description": "Diagnosis of the run on screen: what holds the business back and a concrete suggested change.", "parameters": _obj()},
    {"name": "navigate", "description": "Open a page.", "parameters": _obj({"page": {"type": "string", "enum": [
        "overview", "market", "field", "live", "simulation", "decisions", "report", "genome", "factors", "monitor",
        "dashboard", "new_project", "methodology", "settings", "home"]}}, ["page"])},
    {"name": "update_plan", "description": "Permanently change the baseline plan (rupees per month; startup_cost one-time) and re-run the simulation. Pass only changed fields.",
     "parameters": _obj({k: _num for k in ("price", "rent", "payroll", "utilities", "other_fixed", "marketing_spend", "startup_cost", "variable_cost_per_unit", "quality")})},
    {"name": "test_strategy", "description": "Temporary what-if through the 10,000-agent simulation, replayed on the live map. Pass only changed fields.",
     "parameters": _obj({k: _num for k in ("price", "marketing_spend", "quality", "capacity_scale", "open_hour", "close_hour")})},
    {"name": "test_price", "description": "What-if at a new price vs the baseline.", "parameters": _obj({"price": _num}, ["price"])},
    {"name": "find_best_location", "description": "Test the plan at every populated spot in the catchment; returns current site and best 3 sites.", "parameters": _obj()},
    {"name": "optimize_strategy", "description": "Search price, marketing and capacity combinations for the most profitable plan.", "parameters": _obj()},
    {"name": "start_new_idea", "description": "Create a new analysis from the user's idea (business type + place, optional price/budget).",
     "parameters": _obj({"description": {"type": "string"}}, ["description"])},
    {"name": "load_market_and_simulate", "description": "Load live market data for the open project and run the baseline simulation (up to 2 minutes).", "parameters": _obj()},
    {"name": "request_field_researcher", "description": "Request an industry-matched field researcher to collect ground data.",
     "parameters": _obj({"brief": {"type": "string"}, "researcher_name": {"type": "string"}})},
    {"name": "record_field_data", "description": "Save one ground observation: interview, competitor, footfall or rent.",
     "parameters": _obj({"kind": {"type": "string", "enum": ["interview", "competitor", "footfall", "rent"]}, "uses_category": {"type": "boolean"},
                         "visits_per_month": _num, "max_price": _num, "travel_km": _num, "name": {"type": "string"}, "price": _num, "rating": _num,
                         "count": _num, "minutes": _num, "time_of_day": {"type": "string"}, "monthly_rent": _num, "deposit": _num}, ["kind"])},
    {"name": "get_field_status", "description": "Field research progress and which agent parameters now use street data.", "parameters": _obj()},
    {"name": "make_report", "description": "Generate and open the feasibility report.", "parameters": _obj()},
    {"name": "list_projects", "description": "List the user's saved analyses.", "parameters": _obj()},
    {"name": "open_project", "description": "Open a saved analysis by (part of) its name.", "parameters": _obj({"name": {"type": "string"}}, ["name"])},
    {"name": "set_goal", "description": "What recommendations optimise for.", "parameters": _obj({"goal": {"type": "string", "enum": ["profit", "low_risk", "break_even", "growth"]}}, ["goal"])},
    {"name": "explain_term", "description": "Plain-language meaning of a term.", "parameters": _obj({"term": {"type": "string"}}, ["term"])},
    {"name": "open_guide", "description": "Open the 'How it works' guide.", "parameters": _obj()},
    {"name": "start_demo", "description": "Open the live demo project.", "parameters": _obj()},
]
TOOL_NAMES = {t["name"] for t in TOOLS}


class ToolCall(BaseModel):
    id: str = Field(max_length=200)
    name: str = Field(max_length=64)
    args: str = Field(default="{}", max_length=4000)


class Msg(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str = Field(default="", max_length=12000)
    toolCalls: list[ToolCall] | None = Field(default=None, max_length=8)
    toolCallId: str | None = Field(default=None, max_length=200)
    isError: bool | None = None


class AgentIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=40)
    page: str = Field(default="/", max_length=300)
    project_open: bool = False


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=1500)


def _key() -> str:
    k = get_settings().speko_api_key
    if not k:
        raise HTTPException(503, "Voice brain is not configured (SPEKO_API_KEY missing).")
    return k


def parse_sse(raw: str) -> dict:
    """Fold Speko's /v1/complete event stream into {text, tool_calls}."""
    text, calls, done, err = "", [], None, None
    for block in re.split(r"\r?\n\r?\n", raw):
        ev, data = None, []
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if not data:
            continue
        try:
            obj = json.loads("\n".join(data))
        except ValueError:
            continue
        ev = ev or (obj.get("type") if isinstance(obj, dict) else None)
        if ev == "delta":
            text += obj.get("text", "")
        elif ev == "tool_call":
            calls.append({"id": obj.get("id"), "name": obj.get("name"), "args": obj.get("args") or "{}"})
        elif ev == "done":
            done = obj
        elif ev == "error":
            err = obj
    if done:
        text = done.get("text") or text
        calls = done.get("toolCalls") or calls
    if err and not text and not calls:
        raise HTTPException(502, f"Voice brain error: {err.get('error') or err.get('message') or 'unknown'}")
    return {"text": text.strip(), "tool_calls": [c for c in calls if c.get("name") in TOOL_NAMES]}


@router.post("/assistant/agent")
async def agent(body: AgentIn, user: User = Depends(current_user)):
    s = get_settings()
    context = f"\n\nAbhi user is page pe hai: {body.page}. Project open: {'haan' if body.project_open else 'nahi'}."
    req = {
        "messages": [m.model_dump(exclude_none=True) for m in body.messages],
        "intent": {"language": "en", "optimizeFor": "balanced"},
        "systemPrompt": PROMPT + context,
        "tools": TOOLS,
        "temperature": 0.4,
        "maxTokens": 500,
    }
    try:
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post(f"{s.speko_url}/v1/complete", json=req, headers={"Authorization": f"Bearer {_key()}", "Accept": "text/event-stream"})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Voice brain unreachable: {type(e).__name__}") from e
    if r.status_code >= 400:
        log.warning("speko complete %s: %s", r.status_code, r.text[:300])
        raise HTTPException(502, f"Voice brain error {r.status_code}")
    return parse_sse(r.text)


def _wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


@router.post("/assistant/tts")
async def tts(body: TtsIn, user: User = Depends(current_user)):
    s = get_settings()
    req = {"text": body.text, "intent": {"language": "hi", "optimizeFor": "latency"}, "voice": s.speko_voice,
           "constraints": {"allowedProviders": {"tts": ["cartesia"]}}}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{s.speko_url}/v1/synthesize", json=req, headers={"Authorization": f"Bearer {_key()}"})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Voice unreachable: {type(e).__name__}") from e
    if r.status_code >= 400:
        log.warning("speko synthesize %s: %s", r.status_code, r.text[:300])
        raise HTTPException(502, f"Voice error {r.status_code}")
    ctype = r.headers.get("content-type", "application/octet-stream")
    audio = r.content
    # raw PCM (Cartesia) needs a WAV header before a browser can play it
    if ctype.startswith("audio/pcm") or ctype.startswith("audio/l16"):
        m = re.search(r"rate=(\d+)", ctype)
        audio, ctype = _wav(audio, int(m.group(1)) if m else 24000), "audio/wav"
    return Response(content=audio, media_type=ctype, headers={"Cache-Control": "no-store"})
