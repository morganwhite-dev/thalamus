"""Grounding checks for prep drafts (Phase 13). Plain code, no model.

The draft may only choose and order facts by id; free text (summary, letter) is checked here.
"""
import json, re

DASH = re.compile(r"[—–]|\s-\s|\s--\s")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
IN_PROGRESS_TERMS = ("network+", "c|oasp", "coasp")


def load_facts(path):
    return json.loads(open(path, encoding="utf-8").read())


def _corpus(facts):
    parts = []
    def walk(o):
        if isinstance(o, str): parts.append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                if k not in ("banned_terms", "note"): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(facts)
    return "\n".join(parts)


def allowed_numbers(facts):
    nums = {n.strip(",").rstrip(".") for n in NUM.findall(_corpus(facts))}
    nums |= {"2026", "2027", "1", "2", "3"}  # years and tiny counts that appear in plain speech
    return nums


def check_text(label, text, facts):
    """Problems in one free-text field."""
    out = []
    if not text:
        return out
    if DASH.search(text):
        out.append(f"{label}: remove em dashes, en dashes and spaced hyphens (use a comma or a new sentence)")
    low = text.lower()
    for term in facts.get("banned_terms", []):
        if re.search(r"\b" + re.escape(term.lower()) + r"\b", low):
            out.append(f"{label}: remove the claim about '{term}' (not something Morgan can claim)")
    ok = allowed_numbers(facts)
    for n in NUM.findall(text):
        n2 = n.strip(",").rstrip(".")
        if n2 and n2 not in ok:
            out.append(f"{label}: the number {n2} is not in Morgan's verified facts, remove it")
    for t in IN_PROGRESS_TERMS:
        for m in re.finditer(re.escape(t), low):
            tail = low[m.end(): m.end() + 40]
            if "in progress" not in tail and "in-progress" not in tail:
                out.append(f"{label}: '{t}' is still in progress; say so right after the name")
                break
    return out


def check_draft(draft, facts, need_letter):
    """Validate the structured draft. Returns a list of problems (empty = fine)."""
    out = []
    if not isinstance(draft, dict):
        return ["the draft was not a JSON object"]
    exp = {e["id"]: e for e in facts["experience"]}
    proj = {p["id"]: p for p in facts["projects"]}
    skills = {s.lower() for s in facts["skills"]}
    if not isinstance(draft.get("summary"), str) or not draft["summary"].strip():
        out.append("summary: missing")
    out += check_text("summary", draft.get("summary", ""), facts)
    if len(draft.get("summary", "")) > 700:
        out.append("summary: keep it under 700 characters so the resume stays on one page")
    for g in draft.get("skills") or []:
        if not isinstance(g, dict) or not g.get("label") or not isinstance(g.get("items"), list):
            out.append("skills: each group needs a label and an items list"); continue
        for it in g["items"]:
            if str(it).lower() not in skills:
                out.append(f"skills: '{it}' is not in Morgan's verified skills list")
    if not draft.get("skills"):
        out.append("skills: missing")
    pids = draft.get("projects") or []
    if not pids or len(pids) > 4:
        out.append("projects: choose 1 to 4 project ids")
    for p in pids:
        if p not in proj: out.append(f"projects: unknown id '{p}'")
    eids = draft.get("experience") or []
    for e in eids:
        if e not in exp: out.append(f"experience: unknown id '{e}'")
    sel = draft.get("bullets") or {}
    if not isinstance(sel, dict):
        out.append("bullets: must be an object of id -> list of bullet ids"); sel = {}
    for owner, bl in sel.items():
        item = exp.get(owner) or proj.get(owner)
        if not item: out.append(f"bullets: unknown owner '{owner}'"); continue
        valid = {b["id"] for b in item["bullets"]}
        for b in bl:
            if b not in valid: out.append(f"bullets: '{b}' does not belong to '{owner}'")
    letter = draft.get("letter")
    if need_letter:
        if not isinstance(letter, str) or len(letter.split()) < 120:
            out.append("letter: missing or too short (aim for 200 to 280 words)")
        elif len(letter.split()) > 340:
            out.append("letter: too long, it must fit on one page (under 300 words)")
        out += check_text("letter", letter or "", facts)
    return out
