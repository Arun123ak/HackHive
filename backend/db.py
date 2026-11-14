"""SQLite layer for Portfolio Sentinel. Invented demo data only."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "portfolio_sentinel.db"

DEMO_HOLDINGS = [
    ("DEMO-01", "Aster Devices", "ASTR", 20, 25.0),
    ("DEMO-01", "Northstar Cloud", "NSCL", 15, 25.0),
    ("DEMO-01", "VoltForge Mobility", "VFM", 12, 25.0),
    ("DEMO-01", "QuantaSilica", "QTSL", 10, 25.0),
    ("DEMO-02", "Aster Devices", "ASTR", 10, 40.0),
    ("DEMO-02", "HarborCart", "HBCT", 18, 35.0),
    ("DEMO-02", "Northstar Cloud", "NSCL", 8, 25.0),
]

DEMO_NEWS = [
    ("N-001", "ASTR", "Aster Devices", "Quarterly revenue falls 11 percent",
     "Aster Devices reported an 11 percent year-over-year revenue decline in its fictional quarterly update. The company attributed the change to slower demand in two product lines and said it is reviewing operating costs.",
     "Financial Performance", "2026-11-08", "DemoWire", "Mock news"),
    ("N-002", "ASTR", "Aster Devices", "New repair program announced",
     "Aster Devices announced a voluntary repair program for a limited batch of fictional portable devices after identifying a battery performance issue. The company said affected customers will receive a no-cost repair.",
     "Product Safety", "2026-11-10", "DemoWire", "Mock news"),
    ("N-003", "NSCL", "Northstar Cloud", "Cloud service availability incident",
     "Northstar Cloud disclosed a service availability incident that interrupted a subset of customer workloads for approximately two hours. The company said service has been restored and a post-incident report is being prepared.",
     "Operational", "2026-11-09", "Mock Business Journal", "Mock news"),
    ("N-004", "NSCL", "Northstar Cloud", "New data center investment",
     "Northstar Cloud announced a fictional investment in a new energy-efficient data center intended to expand capacity and improve service resilience.",
     "Strategic Development", "2026-11-11", "Mock Business Journal", "Mock news"),
    ("N-005", "VFM", "VoltForge Mobility", "Vehicle battery inspection campaign",
     "VoltForge Mobility initiated an inspection campaign for a defined batch of fictional electric vehicles after detecting a battery-management software issue. The company has not reported injuries in the mock announcement.",
     "Product Safety", "2026-11-07", "DemoWire", "Mock news"),
    ("N-006", "VFM", "VoltForge Mobility", "Production temporarily paused",
     "VoltForge Mobility temporarily paused one assembly line while it updates quality-control procedures. The fictional notice says other production lines continue operating.",
     "Operational", "2026-11-10", "Mock Business Journal", "Mock news"),
    ("N-007", "QTSL", "QuantaSilica", "Quarterly earnings exceed internal plan",
     "QuantaSilica reported fictional quarterly revenue growth of 18 percent and stronger-than-anticipated demand for semiconductor components.",
     "Financial Performance", "2026-11-06", "DemoWire", "Mock news"),
    ("N-008", "QTSL", "QuantaSilica", "New chip packaging facility planned",
     "QuantaSilica announced plans for a new advanced packaging facility, subject to permits and final board approval.",
     "Strategic Development", "2026-11-11", "Mock Business Journal", "Mock news"),
    ("N-009", "HBCT", "HarborCart", "Regulatory review opened",
     "A fictional consumer regulator opened a review of HarborCart's marketplace seller-disclosure practices. The company said it will cooperate and has not received a formal penalty.",
     "Regulatory", "2026-11-05", "DemoWire", "Mock news"),
]

DEMO_FILINGS = [
    ("F-001", "ASTR", "Aster Devices", "Quarterly Operations Brief", "Revenue and Demand", 4,
     "The fictional quarterly update records an 11 percent year-over-year revenue decline, concentrated in two product lines. Management states that operating costs are under review.",
     "aster_devices_quarterly_brief.pdf"),
    ("F-002", "ASTR", "Aster Devices", "Product Safety Notice", "Battery Performance", 2,
     "Aster Devices identified a battery performance issue in a limited batch and announced a voluntary no-cost repair program. An independent review has been commissioned.",
     "aster_devices_safety_notice.pdf"),
    ("F-003", "NSCL", "Northstar Cloud", "Service Incident Report", "Service Availability", 3,
     "A service availability incident interrupted a subset of workloads for approximately two hours. Service was restored and a post-incident review is in progress.",
     "northstar_cloud_incident_report.pdf"),
    ("F-004", "VFM", "VoltForge Mobility", "Quality Update", "Battery Inspection", 5,
     "VoltForge Mobility initiated an inspection campaign after identifying a battery-management software issue. Updated inspection and supplier-control steps are being introduced.",
     "voltforge_quality_update.pdf"),
    ("F-005", "QTSL", "QuantaSilica", "Quarterly Results Summary", "Revenue", 4,
     "QuantaSilica reported fictional quarterly revenue growth of 18 percent and stronger-than-anticipated demand for semiconductor components.",
     "quantasilica_results.pdf"),
    ("F-006", "HBCT", "HarborCart", "Regulatory Disclosure", "Marketplace Practices", 6,
     "A regulator opened a review of seller-disclosure practices. The company states that it will cooperate and that no formal penalty has been issued in this fictional scenario.",
     "harborcart_regulatory_disclosure.pdf"),
]


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables and seed invented demo data (only if tables are empty)."""
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS holdings (
            portfolio_id TEXT NOT NULL, company TEXT NOT NULL, symbol TEXT NOT NULL,
            shares INTEGER NOT NULL, allocation_pct REAL NOT NULL,
            PRIMARY KEY (portfolio_id, symbol));
        CREATE TABLE IF NOT EXISTS news (
            news_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, company TEXT NOT NULL,
            title TEXT NOT NULL, content TEXT NOT NULL, category TEXT NOT NULL,
            published_at TEXT NOT NULL, source TEXT NOT NULL, source_type TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS filings (
            filing_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, company TEXT NOT NULL,
            document_title TEXT NOT NULL, section TEXT NOT NULL, page INTEGER NOT NULL,
            excerpt TEXT NOT NULL, document_ref TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id TEXT NOT NULL, news_id TEXT NOT NULL, symbol TEXT NOT NULL,
            company TEXT NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL,
            sentiment TEXT NOT NULL, severity TEXT NOT NULL, explanation TEXT NOT NULL,
            evidence TEXT NOT NULL, evidence_source TEXT NOT NULL, evidence_status TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(portfolio_id, news_id));
        CREATE TABLE IF NOT EXISTS run_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL, step TEXT NOT NULL, detail TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        if conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0] == 0:
            conn.executemany("INSERT INTO holdings VALUES (?,?,?,?,?)", DEMO_HOLDINGS)
        if conn.execute("SELECT COUNT(*) FROM news").fetchone()[0] == 0:
            conn.executemany("INSERT INTO news VALUES (?,?,?,?,?,?,?,?,?)", DEMO_NEWS)
        if conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 0:
            conn.executemany("INSERT INTO filings VALUES (?,?,?,?,?,?,?,?)", DEMO_FILINGS)


def _rows(sql, params=()):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---- read helpers used by the UI ----
def get_portfolios():
    return [r["portfolio_id"] for r in _rows(
        "SELECT DISTINCT portfolio_id FROM holdings ORDER BY portfolio_id")]


def get_holdings(portfolio_id):
    return _rows("SELECT * FROM holdings WHERE portfolio_id=? ORDER BY allocation_pct DESC, company",
                 (portfolio_id,))


def get_alerts(portfolio_id):
    return _rows("SELECT * FROM alerts WHERE portfolio_id=? ORDER BY created_at DESC, alert_id DESC",
                 (portfolio_id,))


def get_run_logs(run_id=None):
    if run_id:
        return _rows("SELECT run_id, step, detail, status, created_at FROM run_logs "
                     "WHERE run_id=? ORDER BY log_id", (run_id,))
    return _rows("SELECT run_id, step, detail, status, created_at FROM run_logs ORDER BY log_id DESC")


# ---- tools used by the agent ----
def search_news(symbol):
    return _rows("SELECT * FROM news WHERE symbol=? ORDER BY published_at DESC", (symbol,))


def retrieve_filings(symbol):
    return _rows("SELECT * FROM filings WHERE symbol=? ORDER BY page", (symbol,))


def save_alert(a: dict):
    """Insert an alert; duplicate (portfolio, news) pairs are ignored."""
    with get_connection() as conn:
        conn.execute("""INSERT OR IGNORE INTO alerts
            (portfolio_id, news_id, symbol, company, title, category, sentiment, severity,
             explanation, evidence, evidence_source, evidence_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a["portfolio_id"], a["news_id"], a["symbol"], a["company"], a["title"],
             a["category"], a["sentiment"], a["severity"], a["explanation"],
             a["evidence"], a["evidence_source"], a["evidence_status"]))
        row = conn.execute("SELECT * FROM alerts WHERE portfolio_id=? AND news_id=?",
                           (a["portfolio_id"], a["news_id"])).fetchone()
    return dict(row)


def write_log(run_id, step, detail, status="completed"):
    with get_connection() as conn:
        conn.execute("INSERT INTO run_logs (run_id, step, detail, status) VALUES (?,?,?,?)",
                     (run_id, step, detail, status))


def clear_demo_alerts():
    with get_connection() as conn:
        conn.execute("DELETE FROM alerts")
        conn.execute("DELETE FROM run_logs")