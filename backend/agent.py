"""LangGraph workflow: plan -> tools -> analysis -> verify -> (retry) -> save -> report."""
from __future__ import annotations

from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from backend import analysis
from backend.db import (get_holdings, init_db, retrieve_filings, save_alert,
                        search_news, write_log)

VERIFIED = "Verified against mock filing"
NEWS_ONLY = "News source only — review recommended"


class AgentState(TypedDict, total=False):
    portfolio_id: str
    run_id: str
    plan: list[str]
    holdings: list[dict[str, Any]]
    news: list[dict[str, Any]]
    filings: dict[str, list[dict[str, Any]]]
    findings: list[dict[str, Any]]
    verified: list[dict[str, Any]]
    saved_alerts: list[dict[str, Any]]
    trace: list[dict[str, str]]
    final_report: str
    retry_count: int


def _trace(state, step, detail):
    write_log(state["run_id"], step, detail)
    return state.get("trace", []) + [{"step": step, "detail": detail, "status": "Completed"}]


def planner_node(state):
    plan = ["Read the selected fictional portfolio.",
            "Search the news database for each holding.",
            "Retrieve relevant mock filing excerpts.",
            "Classify developments and explain their relevance.",
            "Check whether every finding has traceable source evidence.",
            "Save alerts and prepare the monitoring summary."]
    return {"plan": plan, "trace": _trace(state, "Planner", "Created a six-step monitoring plan.")}


def portfolio_node(state):
    h = get_holdings(state["portfolio_id"])
    return {"holdings": h, "trace": _trace(
        state, "Portfolio database tool",
        f"SQLite returned {len(h)} holdings for {state['portfolio_id']}.")}


def news_node(state):
    news = []
    for h in state["holdings"]:
        news.extend(search_news(h["symbol"]))
    return {"news": news, "trace": _trace(
        state, "News search tool",
        f"Searched {len(state['holdings'])} symbols and found {len(news)} mock news items.")}


def filing_node(state):
    filings = {h["symbol"]: retrieve_filings(h["symbol"]) for h in state["holdings"]}
    n = sum(len(v) for v in filings.values())
    return {"filings": filings, "trace": _trace(
        state, "Filing retrieval tool", f"Retrieved {n} supporting filing excerpts.")}


def analysis_node(state):
    findings, methods = [], {}
    for art in state["news"]:
        terms = set((art["title"] + " " + art["content"]).lower().split())
        best, best_f, best_score = "", None, 0
        for f in state.get("filings", {}).get(art["symbol"], []):
            score = len(terms & set(f["excerpt"].lower().split()))
            if score > best_score:
                best_score, best, best_f = score, f["excerpt"], f
        category, sentiment, severity, expl, method = analysis.analyze(art)
        methods[method] = methods.get(method, 0) + 1
        findings.append({
            **art, "category": category, "sentiment": sentiment,
            "severity": severity, "explanation": expl, "evidence": best,
            "evidence_source": (f"{best_f['document_title']} · {best_f['section']} · page {best_f['page']}"
                                if best_f else f"News source · {art['source']} · {art['news_id']}"),
            "evidence_status": VERIFIED if best_f else NEWS_ONLY})
    return {"findings": findings, "trace": _trace(
        state, "Analysis",
        f"Classified {len(findings)} developments ("
        + ", ".join(f"{n} by {m}" for m, n in methods.items()) + ").")}


def verify_node(state):
    verified = [{**f, "evidence_status": VERIFIED if f.get("evidence") else NEWS_ONLY}
                for f in state["findings"]]
    return {"verified": verified, "trace": _trace(
        state, "Evidence verification", f"Checked source traceability for {len(verified)} findings.")}


def route_after_verify(state):
    needs = any(x["evidence_status"] == NEWS_ONLY for x in state.get("verified", []))
    return "retry" if needs and state.get("retry_count", 0) < 1 else "save"


def retry_node(state):
    return {"filings": {h["symbol"]: retrieve_filings(h["symbol"]) for h in state["holdings"]},
            "retry_count": state.get("retry_count", 0) + 1,
            "trace": _trace(state, "Conditional retry",
                            "Repeated filing retrieval because some items lacked filing evidence.")}


def save_node(state):
    saved = []
    for it in state.get("verified", []):
        saved.append(save_alert({
            "portfolio_id": state["portfolio_id"], "news_id": it["news_id"],
            "symbol": it["symbol"], "company": it["company"], "title": it["title"],
            "category": it["category"], "sentiment": it["sentiment"],
            "severity": it["severity"], "explanation": it["explanation"],
            "evidence": it["evidence"] or it["content"][:500],
            "evidence_source": it["evidence_source"], "evidence_status": it["evidence_status"]}))
    return {"saved_alerts": saved, "trace": _trace(
        state, "Alert write tool",
        f"Saved or matched {len(saved)} alerts; duplicates are suppressed.")}


def report_node(state):
    v = state.get("verified", [])
    ok = sum(x["evidence_status"] == VERIFIED for x in v)
    high = sum(x["severity"] == "High" for x in v)
    report = (f"Monitoring finished for {len(state.get('holdings', []))} holdings. "
              f"{len(v)} developments found; {ok} verified against filings; "
              f"{high} marked high severity. No trading advice was generated.")
    return {"final_report": report, "trace": _trace(state, "Final report", "Prepared the run summary.")}


def build_agent():
    g = StateGraph(AgentState)
    for name, fn in [("planner", planner_node), ("portfolio", portfolio_node), ("news", news_node),
                     ("filings", filing_node), ("analysis", analysis_node), ("verify", verify_node),
                     ("retry", retry_node), ("save", save_node), ("report", report_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "planner")
    g.add_edge("planner", "portfolio")
    g.add_edge("portfolio", "news")
    g.add_edge("news", "filings")
    g.add_edge("filings", "analysis")
    g.add_edge("analysis", "verify")
    g.add_conditional_edges("verify", route_after_verify, {"retry": "retry", "save": "save"})
    g.add_edge("retry", "analysis")
    g.add_edge("save", "report")
    g.add_edge("report", END)
    return g.compile()


def run_health_check(portfolio_id: str):
    init_db()
    run_id = str(uuid4())[:8]
    result = build_agent().invoke({"portfolio_id": portfolio_id, "run_id": run_id,
                                   "retry_count": 0, "trace": []})
    result["run_id"] = run_id
    return result