"""Agent tools. Each function performs a real SQLite/file operation."""
from .db import (
    get_holdings, get_news_for_symbol, get_filings_for_symbol,
    save_alert, log_step
)

def portfolio_lookup_tool(portfolio_id: str):
    """External database tool: fetch synthetic portfolio holdings."""
    return get_holdings(portfolio_id)

def financial_news_search_tool(symbol: str):
    """External database search tool: search the synthetic news corpus."""
    return get_news_for_symbol(symbol)

def filing_retrieval_tool(symbol: str):
    """External document-evidence tool: retrieve synthetic filing excerpts."""
    return get_filings_for_symbol(symbol)

def alert_write_tool(alert: dict):
    """Action tool: persist a verified or review-required alert."""
    return save_alert(alert)

def activity_log_tool(run_id: str, step: str, detail: str, status="completed"):
    """Persist the agent's tool-use trace."""
    log_step(run_id, step, detail, status)
