"""RRM-100, candidato E3 (perdió): agente con herramientas sobre Muse.

Se queda aquí para repetir la comparación (scripts/explain_eval.py --cands E3);
la app no lo usa. Ver notas/RRM-100-resultados.md en compass.
"""

import json

from rrm.reader.explain import llm
from rrm.reader.explain.retrieve import _encode, passage_text, rank_units
from rrm.reader.explain.review import _MISSED_FREE, _OTHERS, _RULES, _TOKENS, PARTS, _claim_schema, _said, assemble, sentences
from rrm.reader.explain.section import numbered



def _tool(name, desc, props, required):
    return {"type": "function", "name": name, "description": desc, "strict": True,
            "parameters": {"type": "object", "properties": props, "required": required, "additionalProperties": False}}


def _agent_tools():
    q = {"query": {"type": "string"}}
    final = _claim_schema()
    return [
        _tool("read_section", "Read every sentence of the section the reader explained, with ids.", {}, []),
        _tool("search_paper", "Search the whole open paper; returns the 6 closest sentences with ids.", q, ["query"]),
        _tool("search_other_papers", "Search passages of other papers (ids o1, o2…) that may explain an idea.", q, ["query"]),
        _tool("submit_review", "Submit the final review. Call it exactly once, at the end.", final["properties"], final["required"]),
    ]


_AGENT = (
    "You review a reader's explanation of a paper section. Use the tools to find what the paper says before judging: "
    "read the section, and search the paper for any claim the section does not cover. Search other papers only if it would help the reader. "
    "Then call submit_review once. " + _RULES + _OTHERS.replace("passages from other papers", "o ids returned by search_other_papers") + _MISSED_FREE
)


def review_e3(ctx, text, *, model=None, effort="minimal", salt="", max_turns=5):
    sents = sentences(text)
    if not sents:
        return {part: [] for part in PARTS}, llm.add(None, None), {}
    tools = _agent_tools()
    convo = [{"role": "developer", "content": _AGENT},
             {"role": "user", "content": f"Section: «{ctx.title}».\n\nReader's explanation:\n{_said(sents)}"}]
    cost, seconds, found, calls = llm.add(None, None), 0.0, [], 0
    data = None
    for turn in range(max_turns):
        payload = {"model": model or llm.CONTRIBUTOR, "store": False, "max_output_tokens": _TOKENS, "input": convo, "tools": tools}
        if effort:
            payload["reasoning"] = {"effort": effort}
        if turn == max_turns - 1:
            payload["tool_choice"] = {"type": "function", "name": "submit_review"}
        response, c, s, _hit = llm.call(payload, salt=salt)
        cost, seconds = llm.add(cost, c), seconds + s
        out = (response or {}).get("output") or []
        convo = convo + out
        fcs = [o for o in out if isinstance(o, dict) and o.get("type") == "function_call"]
        if not fcs:
            break
        done = False
        for fc in fcs:
            calls += 1
            try:
                args = json.loads(fc.get("arguments") or "{}")
            except ValueError:
                args = {}
            name = fc.get("name")
            if name == "submit_review":
                data, done = args, True
                result = "ok"
            elif name == "read_section":
                result = numbered(ctx.section)
            elif name == "search_paper":
                row = rank_units(_encode([args.get("query") or ctx.title], ctx.encode), ctx.units, ctx.vecs, k=6)[0]
                result = "\n".join(f"[{u['id']}] ({u['section']}) {u['text']}" for u, _s in row)
            elif name == "search_other_papers" and ctx.base is not None:
                hits = ctx.base.search(_encode([args.get("query") or ctx.title], ctx.encode), k=4, exclude=ctx.paper.get("corpusid"))
                lines = []
                for row, _score in hits[:4]:
                    oid = f"o{len(found) + 1}"
                    found.append({"id": oid, "text": passage_text(row), "title": str(row.get("title") or ""),
                                  "paper_id": str(row.get("corpusid")), "section": str(row.get("section") or ""), "why": "", "url": str(row.get("url") or "")})
                    lines.append(f"[{oid}] ({row.get('title')}) {passage_text(row)}")
                result = "\n".join(lines) or "nothing found"
            else:
                result = "unavailable"
            convo = convo + [{"type": "function_call_output", "call_id": fc.get("call_id"), "output": result}]
        if done:
            break
    if data is None:
        data = llm.json_of(response) if response else None
    return assemble(ctx, sents, data, passages=found), cost, {"llm_s": seconds, "tool_calls": calls, "parsed": data is not None}
