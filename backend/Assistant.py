"""'Ask Sentinel': answers questions grounded ONLY in saved alerts."""
import os
import re

from backend.analysis import llm_available, _get_client

SEV_RANK = {"High": 0, "Medium": 1, "Informational": 2}


def _rule_based(q: str, alerts: list[dict], holdings: list[dict]) -> str:
    ql = q.lower()
    hits = alerts
    named = [h for h in holdings if h["company"].lower() in ql or h["symbol"].lower() in re.findall(r"\w+", ql)]
    if named:
        syms = {h["symbol"] for h in named}
        hits = [a for a in hits if a["symbol"] in syms]
    for sev in SEV_RANK:
        if sev.lower() in ql or (sev == "Informational" and "info" in ql):
            hits = [a for a in hits if a["severity"] == sev]
    for cat in {a["category"] for a in alerts}:
        if cat.lower() in ql:
            hits = [a for a in hits if a["category"] == cat]
    if not hits:
        return "I couldn't find saved alerts matching that. Try a company name, a severity (High/Medium) or a topic like Product Safety."
    hits = sorted(hits, key=lambda a: SEV_RANK.get(a["severity"], 9))
    if any(w in ql for w in ("how many", "count", "number of")):
        return f"There are **{len(hits)}** matching alerts."
    lines = [f"Found **{len(hits)}** matching alert(s):"]
    for a in hits[:8]:
        lines.append(f"- **{a['severity']}** · {a['company']} — {a['title']} ({a['category']}, {a['evidence_status']})")
    return "\n".join(lines)


def ask(q: str, alerts: list[dict], holdings: list[dict]) -> tuple[str, str]:
    """Returns (answer, method)."""
    if not alerts:
        return "There are no saved alerts yet. Run a health check first.", "Rules"
    if llm_available():
        try:
            ctx = "\n".join(
                f"[{a['alert_id']}] {a['severity']} | {a['company']} ({a['symbol']}) | {a['title']} | "
                f"{a['category']} | {a['sentiment']} | {a['evidence_status']} | evidence: {a['evidence'][:200]}"
                for a in alerts)
            r = _get_client().chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0, timeout=30,
                messages=[{"role": "system", "content":
                           "Answer using ONLY the alerts provided. Be brief, cite alert IDs in brackets. "
                           "If the answer isn't in the alerts, say so. Never give buy/sell/hold advice or predictions."},
                          {"role": "user", "content": f"Alerts:\n{ctx}\n\nQuestion: {q}"}])
            return r.choices[0].message.content.strip(), "OpenAI"
        except Exception:
            pass
    return _rule_based(q, alerts, holdings), "Rules"