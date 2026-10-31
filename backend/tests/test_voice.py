"""Speko voice agent: event-stream folding (no network)."""
import pytest
from fastapi import HTTPException

from app.api.voice import parse_sse


def test_parse_sse_text_and_tools():
    raw = (
        'event: meta\ndata: {"provider":"x","model":"y"}\n\n'
        'event: delta\ndata: {"text":"Haan, "}\n\n'
        'event: tool_call\ndata: {"id":"c1","name":"navigate","args":"{\\"page\\":\\"market\\"}"}\n\n'
        'event: tool_call\ndata: {"id":"c2","name":"rm_rf","args":"{}"}\n\n'
        'event: done\ndata: {"text":"Haan, map khol raha hoon.","provider":"x","model":"y","usage":{"promptTokens":1,"completionTokens":1},'
        '"toolCalls":[{"id":"c1","name":"navigate","args":"{\\"page\\":\\"market\\"}"}]}\n\n'
    )
    out = parse_sse(raw)
    assert out["text"] == "Haan, map khol raha hoon."
    assert [c["name"] for c in out["tool_calls"]] == ["navigate"]


def test_parse_sse_drops_unknown_tools_without_done():
    raw = 'data: {"type":"delta","text":"ok"}\n\ndata: {"type":"tool_call","id":"a","name":"evil","args":"{}"}\n\n'
    assert parse_sse(raw) == {"text": "ok", "tool_calls": []}


def test_parse_sse_error_only_raises():
    with pytest.raises(HTTPException):
        parse_sse('event: error\ndata: {"error":"no credits","code":"X"}\n\n')
