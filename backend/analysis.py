"""Transparent baseline classifier (no API key needed)."""

NEGATIVE = ["decline", "fell", "recall", "incident", "interrupted", "paused",
            "investigation", "review", "issue", "shutdown", "delay"]
POSITIVE = ["growth", "increased", "exceed", "stronger", "investment", "expand",
            "improve", "new facility"]


def classify_development(article: dict):
    text = (article["title"] + " " + article["content"]).lower()
    neg = sum(w in text for w in NEGATIVE)
    pos = sum(w in text for w in POSITIVE)
    sentiment = ("Potentially negative" if neg > pos
                 else "Potentially positive" if pos > neg else "Neutral / mixed")
    category = article["category"]
    if sentiment == "Potentially negative" and category in ("Product Safety", "Regulatory", "Operational"):
        severity = "High"
    elif sentiment == "Potentially negative":
        severity = "Medium"
    else:
        severity = "Informational"
    explanation = (
        f"{article['company']} disclosed a development classified as '{category}'. "
        f"The text indicates a {sentiment.lower()} development. This may be relevant to "
        "portfolio monitoring because it relates to the company's operations, financial "
        "performance, strategy or governance. This is an information alert, not an "
        "investment recommendation.")
    return category, sentiment, severity, explanation


# ---------------------------------------------------------------- optional LLM
import json
import os

SENTIMENTS = {"Potentially negative", "Potentially positive", "Neutral / mixed"}
SEVERITIES = {"High", "Medium", "Informational"}
_client = None
_llm_disabled_reason = None


def llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip()) and _llm_disabled_reason is None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"].strip())
    return _client


def llm_classify(article: dict):
    """Ask the OpenAI model to triage one (fictional) news item. Raises on any problem."""
    prompt = (
        "You triage news about companies held in a FICTIONAL demo portfolio. "
        "Return JSON with keys: sentiment (one of 'Potentially negative', 'Potentially positive', "
        "'Neutral / mixed'), severity (one of 'High', 'Medium', 'Informational'), and explanation "
        "(2 sentences on why this may matter for monitoring). Use High only for potentially "
        "negative safety, regulatory or operational events. Never give buy/sell/hold advice or "
        "predict prices.\n\n"
        f"Company: {article['company']}\nCategory: {article['category']}\n"
        f"Headline: {article['title']}\nText: {article['content']}"
    )
    resp = _get_client().chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        timeout=30,
    )
    data = json.loads(resp.choices[0].message.content)
    sentiment, severity = data["sentiment"], data["severity"]
    if sentiment not in SENTIMENTS or severity not in SEVERITIES:
        raise ValueError("unexpected model output")
    explanation = str(data["explanation"]).strip() + " This is an information alert, not an investment recommendation."
    return article["category"], sentiment, severity, explanation


def analyze(article: dict):
    """Returns (category, sentiment, severity, explanation, method). Falls back safely."""
    global _llm_disabled_reason
    if llm_available():
        try:
            return (*llm_classify(article), "OpenAI")
        except Exception as exc:  # no key rights, no credit, offline, bad output...
            msg = str(exc).lower()
            if any(k in msg for k in ("api key", "401", "quota", "insufficient", "429", "no module")):
                _llm_disabled_reason = str(exc)[:120]  # stop retrying every article
    return (*classify_development(article), "Baseline")