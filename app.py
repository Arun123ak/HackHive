from pathlib import Path
import sys
import sqlite3
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from backend.db import (
    init_db, get_portfolios, get_holdings, get_alerts,
    get_run_logs, clear_demo_alerts
)
from backend.agent import run_health_check
from backend.db import save_alert, retrieve_filings
from backend import analysis as ai
from backend.evaluation import evaluate
from backend.Assistant import ask as ask_sentinel
from backend import auth

DB_PATH = ROOT / "portfolio_sentinel.db"
SEV_ORDER = {"High": 0, "Medium": 1, "Informational": 2}
SEV_COLOR = {"High": "#ef4444", "Medium": "#f59e0b", "Informational": "#38bdf8"}
SEV_ICON = {"High": "🔴", "Medium": "🟠", "Informational": "🔵"}

st.set_page_config(page_title="Portfolio Sentinel", page_icon="🛡️",
                   layout="wide", initial_sidebar_state="expanded")
init_db()

# ---------------------------------------------------------------- style
st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
[data-testid="stMetric"] {background:#111827; padding:16px; border-radius:12px; border:1px solid #263449;}
div[data-testid="stDataFrame"] {border:1px solid #263449; border-radius:10px;}
.hero {padding:22px 24px; border-radius:16px; background:linear-gradient(120deg,#111827,#1e3a5f);
       border:1px solid #334155; margin-bottom:18px;}
.hero h1 {margin:0; color:#f8fafc; font-size:2rem;}
.hero p {color:#cbd5e1; margin:8px 0 0 0;}
.small-note {color:#94a3b8; font-size:0.85rem;}
.alert-card {border:1px solid #334155; border-radius:12px; padding:14px 16px; margin:8px 0; background:#111827; color:#e2e8f0;}
.badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:.75rem; font-weight:600; color:#0b1220;}
.step {border:1px dashed #475569; border-radius:12px; padding:14px; background:#0f172a; color:#e2e8f0; height:100%;}
.step b {color:#7dd3fc;}
.summary-box {border-left:4px solid #38bdf8; background:#0f172a; color:#e2e8f0; padding:14px 18px; border-radius:8px;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- login gate
auth.init_users()
if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.markdown("""
    <div class="hero"><h1>🛡️ Portfolio Sentinel</h1>
    <p>Please sign in to continue.</p></div>""", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        tab_in, tab_up = st.tabs(["🔑 Sign in", "📝 Create account"])
        with tab_in:
            with st.form("login_form"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                ok_btn = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if ok_btn:
                user, msg = auth.login(u, p)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error(msg)
        with tab_up:
            with st.form("signup_form"):
                n = st.text_input("Full name")
                u2 = st.text_input("Choose a username")
                p1 = st.text_input("Password", type="password", help="At least 8 characters, with a letter and a number.")
                p2 = st.text_input("Confirm password", type="password")
                up_btn = st.form_submit_button("Create account", use_container_width=True)
            if up_btn:
                done, msg = auth.register(u2, n, p1, p2)
                (st.success if done else st.error)(msg)
            st.caption("The first account created becomes the administrator.")
        st.caption("Demo app with synthetic data only. Not investment advice.")
    st.stop()

user = st.session_state.user
is_admin = user["role"] == "admin"
can_edit = user["role"] in ("admin", "analyst")


# ---------------------------------------------------------------- helpers
def badge(sev: str) -> str:
    return f'<span class="badge" style="background:{SEV_COLOR.get(sev, "#94a3b8")}">{sev}</span>'


def query_db(sql: str, params=()) -> pd.DataFrame:
    try:
        with sqlite3.connect(DB_PATH) as con:
            return pd.read_sql_query(sql, con, params=params)
    except Exception:
        return pd.DataFrame()


def exposure_score(holdings_df: pd.DataFrame, alerts_df: pd.DataFrame):
    """% of portfolio sitting in companies that have at least one High alert."""
    if holdings_df.empty or alerts_df.empty:
        return 0.0, []
    high = set(alerts_df.loc[alerts_df["severity"] == "High", "symbol"])
    flagged = holdings_df[holdings_df["symbol"].isin(high)]
    return float(flagged["allocation_pct"].sum()), flagged["company"].tolist()


def plain_summary(portfolio, holdings_df, alerts_df) -> str:
    if alerts_df.empty:
        return "No alerts yet. Click **Run portfolio health check** in the sidebar to start."
    n_high = int((alerts_df["severity"] == "High").sum())
    pct, names = exposure_score(holdings_df, alerts_df)
    top = alerts_df["company"].value_counts().idxmax()
    top_cat = alerts_df["category"].value_counts().idxmax()
    txt = (f"**{portfolio}** has **{len(alerts_df)} alerts**, of which **{n_high} are high severity**. "
           f"The company with the most alerts is **{top}**, and the most common topic is **{top_cat}**. ")
    if names:
        txt += (f"About **{pct:.0f}%** of the portfolio is in companies with a high-severity alert "
                f"({', '.join(names)}). ")
    txt += "This is an informational summary, not investment advice."
    return txt


def build_report(portfolio, holdings_df, alerts_df) -> str:
    lines = [f"# Portfolio Sentinel report — {portfolio}",
             f"Generated: {datetime.now():%Y-%m-%d %H:%M}", "",
             "## Summary", plain_summary(portfolio, holdings_df, alerts_df).replace("**", ""), ""]
    if not alerts_df.empty:
        lines.append("## Alerts")
        for _, a in alerts_df.sort_values("severity", key=lambda s: s.map(SEV_ORDER)).iterrows():
            lines += [f"### [{a['severity']}] {a['company']} ({a['symbol']}) — {a['title']}",
                      f"- Category: {a['category']}",
                      f"- Assessment: {a['sentiment']}",
                      f"- Evidence status: {a['evidence_status']}",
                      f"- Source: {a['evidence_source']}",
                      f"> {a['evidence']}", ""]
    lines.append("_Synthetic demo data. Not investment advice._")
    return "\n".join(lines)


# ---------------------------------------------------------------- session state
st.session_state.setdefault("last_result", None)
st.session_state.setdefault("reviewed", set())

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## 🛡️ Portfolio Sentinel")
    st.caption("Evidence-based company monitoring agent")
    st.markdown(f"👤 **{user['full_name']}**  \n`{user['username']}` · {user['role']}")
    if st.button("Sign out", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    st.divider()
    portfolios = get_portfolios()
    selected = st.selectbox("Select demo portfolio", portfolios)
    run_button = st.button("▶ Run portfolio health check", use_container_width=True, type="primary",
                           disabled=not can_edit, help=None if can_edit else "Viewers cannot run the agent.")
    st.divider()
    st.markdown("**Navigation**")
    page = st.radio("Go to",
                    ["Overview", "Holdings", "Alerts & Evidence", "Company Deep-Dive",
                     "Ask Sentinel", "Try It Yourself", "Compare Portfolios",
                     "Model Evaluation", "Agent Execution", "Run History", "Help & Glossary"]
                    + (["User Management"] if is_admin else []) + ["My Account"],
                    label_visibility="collapsed")
    st.divider()
    if ai.llm_available():
        st.success("🤖 AI mode: OpenAI connected")
    else:
        st.info("🧮 AI mode: built-in rules\n\nAdd OPENAI_API_KEY to .env for LLM analysis.")
    if is_admin:
        with st.expander("⚠️ Danger zone"):
            confirm = st.checkbox("I understand this deletes saved alerts")
            if st.button("Reset demo alerts", use_container_width=True, disabled=not confirm):
                clear_demo_alerts()
                st.session_state.last_result = None
                st.session_state.reviewed = set()
                st.rerun()
    st.caption("Demo data is entirely synthetic. This app does not provide investment advice.")

if run_button:
    with st.status("Agent is working…", expanded=True) as status:
        try:
            st.write("🧭 Planning monitoring steps")
            st.write("🗄️ Retrieving holdings, news and filings")
            st.write("🔎 Analysing and verifying evidence")
            st.session_state.last_result = run_health_check(selected)
            status.update(label="Health check complete", state="complete", expanded=False)
            st.toast("Portfolio monitoring run completed", icon="✅")
        except Exception as exc:
            status.update(label="Run failed", state="error")
            st.error(f"Agent run failed: {exc}")

holdings = get_holdings(selected)
alerts = get_alerts(selected)
holdings_df = pd.DataFrame(holdings)
alerts_df = pd.DataFrame(alerts)

st.markdown("""
<div class="hero">
  <h1>Portfolio Sentinel</h1>
  <p>AI-assisted monitoring of fictional portfolio holdings against mock news and mock company disclosures.</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- top stats
n_high = int((alerts_df["severity"] == "High").sum()) if not alerts_df.empty else 0
n_verified = int(alerts_df["evidence_status"].str.contains("Verified", na=False).sum()) if not alerts_df.empty else 0
exp_pct, _ = exposure_score(holdings_df, alerts_df)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Holdings monitored", len(holdings))
c2.metric("Saved alerts", len(alerts))
c3.metric("High severity", n_high)
c4.metric("Evidence verified", f"{n_verified}/{len(alerts)}" if alerts else "0")
c5.metric("High-alert exposure", f"{exp_pct:.0f}%", help="Share of the portfolio held in companies with at least one High alert.")

# ================================================================ PAGES
if page == "Overview":
    if alerts_df.empty:
        st.markdown("### 👋 Getting started")
        s1, s2, s3 = st.columns(3)
        s1.markdown('<div class="step"><b>1 · Pick a portfolio</b><br>Use the dropdown in the sidebar.</div>', unsafe_allow_html=True)
        s2.markdown('<div class="step"><b>2 · Run the check</b><br>Click the blue button. The agent plans, retrieves evidence and saves alerts.</div>', unsafe_allow_html=True)
        s3.markdown('<div class="step"><b>3 · Review evidence</b><br>Open <i>Alerts &amp; Evidence</i> to see the source behind every alert.</div>', unsafe_allow_html=True)
        st.write("")
    else:
        st.markdown(f'<div class="summary-box">{plain_summary(selected, holdings_df, alerts_df)}</div>', unsafe_allow_html=True)
        st.write("")

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Portfolio composition")
        if not holdings_df.empty:
            fig = px.pie(holdings_df, names="company", values="allocation_pct", hole=0.58,
                         title="Illustrative allocation")
            fig.update_layout(margin=dict(t=50, b=10, l=10, r=10), legend_title_text="Company")
            st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Recent monitoring alerts")
        if alerts:
            for a in alerts[:5]:
                st.markdown(
                    f"""<div class="alert-card">{badge(a['severity'])} <b>{a['company']}</b><br>
                    {a['title']}<br>
                    <span class="small-note">{a['category']} · {a['evidence_status']}</span></div>""",
                    unsafe_allow_html=True)
            st.caption("See all alerts under **Alerts & Evidence**.")
        else:
            st.info("No alerts yet. Run a portfolio health check to start the agent.")

    if not alerts_df.empty:
        st.subheader("Insights")
        i1, i2, i3 = st.columns(3)
        sev = alerts_df["severity"].value_counts().reindex(list(SEV_ORDER), fill_value=0).reset_index()
        sev.columns = ["Severity", "Alerts"]
        f1 = px.bar(sev, x="Severity", y="Alerts", color="Severity", color_discrete_map=SEV_COLOR, title="Alerts by severity")
        f1.update_layout(showlegend=False, margin=dict(t=50, b=10, l=10, r=10))
        i1.plotly_chart(f1, use_container_width=True)

        cat = alerts_df["category"].value_counts().reset_index()
        cat.columns = ["Category", "Alerts"]
        f2 = px.bar(cat, x="Alerts", y="Category", orientation="h", title="Alerts by topic")
        f2.update_layout(margin=dict(t=50, b=10, l=10, r=10), yaxis=dict(autorange="reversed"))
        i2.plotly_chart(f2, use_container_width=True)

        comp = alerts_df.groupby(["company", "severity"]).size().reset_index(name="Alerts")
        f3 = px.bar(comp, x="company", y="Alerts", color="severity", color_discrete_map=SEV_COLOR,
                    title="Alerts per company", labels={"company": "Company"})
        f3.update_layout(margin=dict(t=50, b=10, l=10, r=10), legend_title_text="")
        i3.plotly_chart(f3, use_container_width=True)

        st.subheader("Risk heatmap")
        st.caption("Each cell adds up alert weight for a company and topic (High = 3, Medium = 2, Informational = 1).")
        w = alerts_df.assign(weight=alerts_df["severity"].map({"High": 3, "Medium": 2, "Informational": 1}))
        heat = w.pivot_table(index="company", columns="category", values="weight", aggfunc="sum", fill_value=0)
        fh = px.imshow(heat, text_auto=True, aspect="auto", color_continuous_scale="OrRd",
                       labels=dict(color="Weight", x="Topic", y="Company"))
        fh.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fh, use_container_width=True)

        st.download_button("⬇️ Download full report (Markdown)",
                           build_report(selected, holdings_df, alerts_df),
                           file_name=f"sentinel_report_{selected}.md", mime="text/markdown")
    st.caption("Severity is an informational triage label, not a prediction of market impact.")

elif page == "Holdings":
    st.subheader(f"Holdings · {selected}")
    if not holdings_df.empty:
        view = holdings_df.copy()
        counts = alerts_df.groupby("symbol").size() if not alerts_df.empty else pd.Series(dtype=int)
        view["alerts"] = view["symbol"].map(counts).fillna(0).astype(int)
        view = view.rename(columns={"portfolio_id": "Portfolio", "company": "Company", "symbol": "Symbol",
                                    "shares": "Mock shares", "allocation_pct": "Illustrative allocation (%)",
                                    "alerts": "Open alerts"})
        st.dataframe(view, use_container_width=True, hide_index=True,
                     column_config={"Illustrative allocation (%)": st.column_config.ProgressColumn(
                         "Illustrative allocation (%)", min_value=0, max_value=100, format="%.0f%%")})
        st.download_button("⬇️ Download holdings (CSV)", view.to_csv(index=False),
                           file_name=f"holdings_{selected}.csv", mime="text/csv")
    st.info("All portfolio names, holdings and allocation percentages are synthetic demo records.")

elif page == "Alerts & Evidence":
    st.subheader("Alerts and supporting evidence")
    if alerts_df.empty:
        st.info("No saved alerts. Run the monitoring agent first.")
    else:
        f1, f2, f3, f4 = st.columns([1.4, 1, 1, 1])
        q = f1.text_input("🔍 Search", placeholder="company, keyword, topic…")
        sev_f = f2.multiselect("Severity", list(SEV_ORDER), default=list(SEV_ORDER))
        cat_f = f3.multiselect("Topic", sorted(alerts_df["category"].unique()))
        sort_f = f4.selectbox("Sort by", ["Severity", "Newest", "Company"])
        hide_rev = st.toggle("Hide reviewed alerts", value=False)

        df = alerts_df[alerts_df["severity"].isin(sev_f)]
        if cat_f:
            df = df[df["category"].isin(cat_f)]
        if q:
            mask = df.apply(lambda r: q.lower() in " ".join(map(str, r.values)).lower(), axis=1)
            df = df[mask]
        if hide_rev:
            df = df[~df["alert_id"].isin(st.session_state.reviewed)]
        if sort_f == "Severity":
            df = df.sort_values("severity", key=lambda s: s.map(SEV_ORDER))
        elif sort_f == "Newest":
            df = df.sort_values("created_at", ascending=False)
        else:
            df = df.sort_values("company")

        top, dl = st.columns([3, 1])
        top.caption(f"Showing {len(df)} of {len(alerts_df)} alerts · reviewed: {len(st.session_state.reviewed)}")
        dl.download_button("⬇️ Export CSV", df.to_csv(index=False), file_name=f"alerts_{selected}.csv",
                           mime="text/csv", use_container_width=True)

        if df.empty:
            st.warning("No alerts match these filters.")
        for _, a in df.iterrows():
            done = a["alert_id"] in st.session_state.reviewed
            label = f"{'✅' if done else SEV_ICON.get(a['severity'], '⚪')} {a['severity']} · {a['company']} ({a['symbol']}) · {a['title']}"
            with st.expander(label):
                m1, m2, m3 = st.columns(3)
                m1.write(f"**Topic:** {a['category']}")
                m2.write(f"**Assessment:** {a['sentiment']}")
                m3.write(f"**Evidence:** {a['evidence_status']}")
                st.write("**Why this may matter:**", a["explanation"])
                st.write("**Evidence source:**", a["evidence_source"])
                st.info(a["evidence"])
                st.caption(f"Alert ID {a['alert_id']} · News ID {a['news_id']} · Created {a['created_at']}")
                if st.checkbox("Mark as reviewed", value=done, key=f"rev_{a['alert_id']}"):
                    st.session_state.reviewed.add(a["alert_id"])
                else:
                    st.session_state.reviewed.discard(a["alert_id"])

elif page == "Company Deep-Dive":
    st.subheader("Company deep-dive")
    if holdings_df.empty:
        st.info("No holdings in this portfolio.")
    else:
        name = st.selectbox("Choose a company", holdings_df["company"].tolist())
        row = holdings_df[holdings_df["company"] == name].iloc[0]
        sym = row["symbol"]
        k1, k2, k3 = st.columns(3)
        k1.metric("Symbol", sym)
        k2.metric("Mock shares", int(row["shares"]))
        k3.metric("Allocation", f"{row['allocation_pct']:.0f}%")

        t1, t2, t3 = st.tabs(["📰 News timeline", "📄 Filing excerpts", "🚨 Alerts"])
        news = query_db("SELECT published_at, title, category, source, content FROM news "
                        "WHERE symbol=? ORDER BY published_at DESC", (sym,))
        with t1:
            if news.empty:
                st.info("No news found for this company.")
            for _, n in news.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{n['title']}**")
                    st.caption(f"{n['published_at']} · {n['category']} · {n['source']}")
                    st.write(n["content"])
        with t2:
            fil = query_db("SELECT document_title, section, page, excerpt, document_ref FROM filings WHERE symbol=?", (sym,))
            if fil.empty:
                st.info("No filing excerpts found.")
            for _, f in fil.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{f['document_title']}** — {f['section']} (p. {f['page']})")
                    st.write(f["excerpt"])
                    st.caption(f"Reference: {f['document_ref']}")
        with t3:
            sub = alerts_df[alerts_df["symbol"] == sym] if not alerts_df.empty else pd.DataFrame()
            if sub.empty:
                st.info("No alerts for this company yet.")
            else:
                for _, a in sub.iterrows():
                    st.markdown(f"{badge(a['severity'])} **{a['title']}**<br><span class='small-note'>{a['category']} · {a['evidence_status']}</span>",
                                unsafe_allow_html=True)
                    st.write("")

elif page == "Agent Execution":
    st.subheader("Agent execution trace")
    result = st.session_state.last_result
    if result:
        st.success(result.get("final_report", "Run completed."))
        st.markdown("**Plan created by the planner node**")
        for i, task in enumerate(result.get("plan", []), 1):
            st.write(f"{i}. {task}")
        st.markdown("**Tool-use and action log**")
        trace_df = pd.DataFrame(result.get("trace", []))
        if not trace_df.empty:
            st.dataframe(trace_df, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Download trace (CSV)", trace_df.to_csv(index=False),
                               file_name="agent_trace.csv", mime="text/csv")
        st.caption(f"Run ID: {result.get('run_id')}")
    else:
        st.info("Run the health check to see the live planning → tool-use → action trace.")
    st.markdown("**Why this satisfies the agent workflow**")
    st.write("- Planner node creates a multi-step plan.")
    st.write("- SQLite-backed tools retrieve holdings, news and filing excerpts.")
    st.write("- Conditional verification route can retry evidence retrieval.")
    st.write("- Alert-write tool persists results and prevents duplicate alerts.")

elif page == "Run History":
    st.subheader("Run history")
    st.caption("Every agent run is logged, so results can be audited later.")
    logs = query_db("SELECT run_id, step, detail, status, created_at FROM run_logs ORDER BY log_id DESC")
    if logs.empty:
        try:
            logs = pd.DataFrame(get_run_logs())
        except Exception:
            logs = pd.DataFrame()
    if logs.empty:
        st.info("No runs recorded yet.")
    else:
        runs = logs.groupby("run_id").agg(started=("created_at", "min"), steps=("step", "count")).reset_index()
        runs = runs.sort_values("started", ascending=False)
        h1, h2 = st.columns([1, 2])
        h1.metric("Total runs", len(runs))
        pick = h2.selectbox("Inspect a run", ["All runs"] + runs["run_id"].tolist())
        shown = logs if pick == "All runs" else logs[logs["run_id"] == pick].iloc[::-1]
        st.dataframe(shown, use_container_width=True, hide_index=True)

elif page == "Ask Sentinel":
    st.subheader("Ask Sentinel")
    st.caption("Ask questions about your saved alerts. Answers use only the alerts in this portfolio.")
    st.session_state.setdefault("chat", [])
    ex1, ex2, ex3 = st.columns(3)
    quick = None
    if ex1.button("Which alerts are high severity?", use_container_width=True):
        quick = "Which alerts are high severity?"
    if ex2.button("Any product safety alerts?", use_container_width=True):
        quick = "Any product safety alerts?"
    if ex3.button("How many alerts are there?", use_container_width=True):
        quick = "How many alerts are there?"
    question = st.chat_input("e.g. What is the biggest issue for Aster Devices?") or quick
    if question:
        answer, how = ask_sentinel(question, alerts, holdings)
        st.session_state.chat.append(("user", question))
        st.session_state.chat.append(("assistant", f"{answer}\n\n*Answered by: {how}*"))
    for role, msg in st.session_state.chat[-12:]:
        with st.chat_message(role):
            st.markdown(msg)
    if st.session_state.chat and st.button("Clear conversation"):
        st.session_state.chat = []
        st.rerun()

elif page == "Try It Yourself":
    st.subheader("Try it yourself")
    st.caption("Write a fictional news item and see how the agent would triage it, with matching filing evidence.")
    symbol_names = {}
    for p in portfolios:
        for h in get_holdings(p):
            symbol_names[h["symbol"]] = h["company"]
    CATS = ["Financial Performance", "Product Safety", "Operational", "Regulatory",
            "Strategic Development", "Governance"]
    with st.form("tryit"):
        t1, t2 = st.columns(2)
        sym = t1.selectbox("Company", list(symbol_names), format_func=lambda x: f"{symbol_names[x]} ({x})")
        cat = t2.selectbox("Topic", CATS)
        title = st.text_input("Headline", value="Production line paused after quality incident")
        body = st.text_area("News text (fictional)", height=120,
                            value="The company paused a fictional production line after an incident and said a review is under way.")
        go = st.form_submit_button("Analyse this news", type="primary")
    if go and title.strip() and body.strip():
        art = {"title": title.strip(), "content": body.strip(), "category": cat,
               "company": symbol_names[sym], "symbol": sym, "source": "User input"}
        with st.spinner("Analysing…"):
            category, sentiment, severity, expl, method = ai.analyze(art)
        terms = set((art["title"] + " " + art["content"]).lower().split())
        best, best_f, best_sc = "", None, 0
        for f in retrieve_filings(sym):
            sc = len(terms & set(f["excerpt"].lower().split()))
            if sc > best_sc:
                best, best_f, best_sc = f["excerpt"], f, sc
        st.session_state.tryit = {**art, "sentiment": sentiment, "severity": severity, "explanation": expl,
                                  "method": method, "evidence": best, "filing": best_f}
    elif go:
        st.warning("Please enter a headline and some text.")
    r = st.session_state.get("tryit")
    if r:
        st.markdown(f"{badge(r['severity'])} &nbsp; **{r['company']}** · {r['sentiment']}", unsafe_allow_html=True)
        st.write(r["explanation"])
        if r["filing"]:
            f = r["filing"]
            st.success(f"Filing evidence found: {f['document_title']} · {f['section']} · page {f['page']}")
            st.info(r["evidence"])
        else:
            st.warning("No supporting filing excerpt found. This would be flagged as news source only.")
        st.caption(f"Analysed by: {r['method']}")
        if can_edit and st.button(f"💾 Save as alert in {selected}"):
            holds = {h["symbol"] for h in holdings}
            if r["symbol"] not in holds:
                st.error(f"{r['company']} is not held in {selected}. Pick a portfolio that holds it.")
            else:
                save_alert({
                    "portfolio_id": selected, "news_id": f"CUSTOM-{datetime.now():%m%d%H%M%S}",
                    "symbol": r["symbol"], "company": r["company"], "title": r["title"],
                    "category": r["category"], "sentiment": r["sentiment"], "severity": r["severity"],
                    "explanation": r["explanation"], "evidence": r["evidence"] or r["content"][:500],
                    "evidence_source": (f"{r['filing']['document_title']} · {r['filing']['section']} · page {r['filing']['page']}"
                                        if r["filing"] else "User-entered news"),
                    "evidence_status": "Verified against mock filing" if r["filing"] else "News source only — review recommended"})
                st.toast("Alert saved", icon="✅")
                st.rerun()

elif page == "Compare Portfolios":
    st.subheader("Compare portfolios")
    rows, per_company = [], []
    for p in portfolios:
        h, a = pd.DataFrame(get_holdings(p)), pd.DataFrame(get_alerts(p))
        pct, names = exposure_score(h, a)
        rows.append({"Portfolio": p, "Holdings": len(h), "Alerts": len(a),
                     "High severity": int((a["severity"] == "High").sum()) if not a.empty else 0,
                     "High-alert exposure (%)": round(pct, 1),
                     "Most exposed": ", ".join(names) or "—"})
        if not h.empty:
            per_company.append(h.assign(Portfolio=p))
    cmp_df = pd.DataFrame(rows)
    st.dataframe(cmp_df, use_container_width=True, hide_index=True)
    if cmp_df["Alerts"].sum() == 0:
        st.info("Run a health check on each portfolio to compare their alerts.")
    fx = px.bar(cmp_df, x="Portfolio", y="High-alert exposure (%)", color="Portfolio",
                title="High-alert exposure by portfolio", range_y=[0, 100])
    fx.update_layout(showlegend=False, margin=dict(t=50, b=10, l=10, r=10))
    st.plotly_chart(fx, use_container_width=True)
    if per_company:
        allh = pd.concat(per_company)
        shared = allh.pivot_table(index="company", columns="Portfolio", values="allocation_pct", aggfunc="sum")
        shared = shared.dropna(thresh=2) if len(portfolios) > 1 else shared
        st.markdown("**Companies held in more than one portfolio (allocation %)**")
        st.dataframe(shared.fillna(0), use_container_width=True)

elif page == "Model Evaluation":
    st.subheader("Model evaluation")
    st.caption("Scores the classifier on a small, separate, synthetic labelled test set (20 items) "
               "so accuracy is measured rather than assumed.")
    methods = ["Baseline (built-in rules)"] + (["OpenAI"] if ai.llm_available() else [])
    choice = st.radio("Method to evaluate", methods, horizontal=True)
    if st.button("▶ Run evaluation", type="primary"):
        with st.spinner("Scoring test set…"):
            try:
                st.session_state.eval_res = (choice, evaluate("OpenAI" if choice == "OpenAI" else "Baseline"))
            except Exception as exc:
                st.error(f"Evaluation failed: {exc}")
    if st.session_state.get("eval_res"):
        name, res = st.session_state.eval_res
        st.markdown(f"**Results for: {name}** · {res['n']} test items")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Severity accuracy", f"{res['severity']['accuracy']:.0%}")
        m2.metric("Severity macro-F1", f"{res['severity']['macro_f1']:.2f}")
        m3.metric("Sentiment accuracy", f"{res['sentiment']['accuracy']:.0%}")
        m4.metric("Sentiment macro-F1", f"{res['sentiment']['macro_f1']:.2f}")
        tab_a, tab_b, tab_c = st.tabs(["Severity", "Sentiment", "Item-by-item"])
        for tab, key in [(tab_a, "severity"), (tab_b, "sentiment")]:
            with tab:
                st.dataframe(pd.DataFrame(res[key]["table"]), use_container_width=True, hide_index=True)
                labs = res[key]["labels"]
                cm = pd.DataFrame(res[key]["confusion"], index=labs, columns=labs)
                fc = px.imshow(cm, text_auto=True, color_continuous_scale="Blues",
                               labels=dict(x="Predicted", y="Actual", color="Items"), title="Confusion matrix")
                fc.update_layout(margin=dict(t=50, b=10, l=10, r=10))
                st.plotly_chart(fc, use_container_width=True)
        with tab_c:
            st.dataframe(pd.DataFrame(res["items"]), use_container_width=True, hide_index=True)
            st.caption("The test set deliberately includes tricky cases, such as 'review closes with no findings', "
                       "where simple keyword rules are expected to make mistakes.")
    st.caption("Test items are invented and separate from the demo news used by the agent.")

elif page == "User Management":
    st.subheader("User management")
    if not is_admin:
        st.error("Administrators only.")
    else:
        users = auth.list_users()
        st.dataframe(pd.DataFrame(users).drop(columns=["user_id"]), use_container_width=True, hide_index=True)
        st.markdown("**Change a role or remove a user**")
        labels = {u["user_id"]: f"{u['username']} ({u['role']})" for u in users}
        uid = st.selectbox("User", list(labels), format_func=lambda x: labels[x])
        c_a, c_b = st.columns(2)
        new_role = c_a.selectbox("New role", auth.ROLES)
        if c_a.button("Update role"):
            ok, msg = auth.set_role(uid, new_role)
            (st.success if ok else st.error)(msg)
            if ok and uid == user["user_id"]:
                st.session_state.user["role"] = new_role
            if ok:
                st.rerun()
        if uid == user["user_id"]:
            c_b.caption("You cannot delete your own account.")
        elif c_b.button("Delete user"):
            ok, msg = auth.delete_user(uid)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
        st.caption("Roles: **admin** manages users and resets data · **analyst** runs checks and saves alerts · **viewer** is read-only.")

elif page == "My Account":
    st.subheader("My account")
    st.write(f"**Name:** {user['full_name']}  \n**Username:** {user['username']}  \n**Role:** {user['role']}")
    with st.form("pw_form"):
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        new2 = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Change password"):
            if new != new2:
                st.error("New passwords do not match.")
            else:
                ok, msg = auth.change_password(user["user_id"], old, new)
                (st.success if ok else st.error)(msg)

elif page == "Help & Glossary":
    st.subheader("Help & glossary")
    with st.expander("How do I use this app?", expanded=True):
        st.markdown("1. Choose a portfolio in the sidebar.\n2. Click **Run portfolio health check**.\n"
                    "3. Explore **Overview**, **Alerts & Evidence** and **Company Deep-Dive**.\n"
                    "4. Download a report from the Overview page.")
    with st.expander("What do the severity levels mean?"):
        st.markdown("- 🔴 **High** – potentially significant development worth reviewing first.\n"
                    "- 🟠 **Medium** – noteworthy, lower urgency.\n"
                    "- 🔵 **Informational** – context only.\n\n"
                    "These are triage labels, **not** predictions of market impact.")
    with st.expander("What does 'Verified' evidence mean?"):
        st.write("The news item was matched to an excerpt from a (mock) company filing that supports it.")
    with st.expander("What is High-alert exposure?"):
        st.write("The share of the illustrative portfolio held in companies with at least one High alert.")
    with st.expander("Is this investment advice?"):
        st.write("No. All data is synthetic and the app never recommends buying, selling or holding.")

st.divider()
st.caption(f"Demo environment · Portfolio {selected} · Updated {datetime.now():%Y-%m-%d %H:%M:%S} · "
           "Synthetic data only · Not investment advice")