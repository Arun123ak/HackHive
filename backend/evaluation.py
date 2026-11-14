"""Evaluate the classifier on a small, separate, fully synthetic labelled test set."""
from backend import analysis

# (title, content, category, expected_sentiment, expected_severity)
TEST_SET = [
 ("Battery recall announced", "The company issued a recall of a fictional device batch after a battery fault.", "Product Safety", "Potentially negative", "High"),
 ("Regulator opens investigation", "A fictional regulator opened an investigation into disclosure practices.", "Regulatory", "Potentially negative", "High"),
 ("Data outage interrupted customers", "A fictional outage interrupted customer workloads for three hours.", "Operational", "Potentially negative", "High"),
 ("Factory shutdown after fire", "A fictional plant faced a shutdown after a small fire; output delayed.", "Operational", "Potentially negative", "High"),
 ("Revenue fell in latest quarter", "Fictional revenue fell nine percent and management announced a cost decline plan.", "Financial Performance", "Potentially negative", "Medium"),
 ("Shipment delay hits sales", "Fictional supply delay reduced quarterly sales; the company cut guidance.", "Financial Performance", "Potentially negative", "Medium"),
 ("Leadership transition causes delay", "A fictional product launch faces delay during a leadership transition.", "Strategic Development", "Potentially negative", "Medium"),
 ("Revenue growth beats plan", "Fictional quarterly revenue growth was stronger than expected.", "Financial Performance", "Potentially positive", "Informational"),
 ("New facility investment", "The company announced investment to expand a fictional production facility.", "Strategic Development", "Potentially positive", "Informational"),
 ("Service resilience improved", "Fictional engineers improve resilience and expand capacity across regions.", "Operational", "Potentially positive", "Informational"),
 ("Demand increased for new line", "Fictional demand increased for the new product line.", "Financial Performance", "Potentially positive", "Informational"),
 ("Annual meeting scheduled", "The fictional company scheduled its annual shareholder meeting for next month.", "Governance", "Neutral / mixed", "Informational"),
 ("New board member appointed", "A fictional board appointed a new independent director.", "Governance", "Neutral / mixed", "Informational"),
 ("Office relocation planned", "The fictional company will relocate its headquarters next year.", "Strategic Development", "Neutral / mixed", "Informational"),
 # harder cases the simple keyword method is expected to struggle with
 ("Safety review closes with no findings", "An independent fictional review found no issue and closed the file.", "Product Safety", "Potentially positive", "Informational"),
 ("Company resolves incident quickly", "A fictional incident was resolved within minutes with no customer impact; resilience improved.", "Operational", "Potentially positive", "Informational"),
 ("Regulatory review concludes without penalty", "A fictional regulatory review concluded and the company will expand services.", "Regulatory", "Potentially positive", "Informational"),
 ("Strong growth but supply issue", "Fictional growth was stronger than planned, though a supply issue and delay remain.", "Financial Performance", "Neutral / mixed", "Informational"),
 ("Product launch slips to spring", "A fictional launch will slip to spring as testing continues.", "Strategic Development", "Potentially negative", "Medium"),
 ("Customer complaints rise", "Fictional customer complaints rose after a software update.", "Operational", "Potentially negative", "High"),
]
SENTIMENT_LABELS = ["Potentially negative", "Neutral / mixed", "Potentially positive"]
SEVERITY_LABELS = ["High", "Medium", "Informational"]


def _prf(y_true, y_pred, labels):
    rows = []
    for lab in labels:
        tp = sum(t == lab and p == lab for t, p in zip(y_true, y_pred))
        fp = sum(t != lab and p == lab for t, p in zip(y_true, y_pred))
        fn = sum(t == lab and p != lab for t, p in zip(y_true, y_pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        rows.append({"Label": lab, "Precision": round(prec, 2), "Recall": round(rec, 2),
                     "F1": round(f1, 2), "Support": sum(t == lab for t in y_true)})
    return rows


def _confusion(y_true, y_pred, labels):
    return [[sum(t == a and p == b for t, p in zip(y_true, y_pred)) for b in labels] for a in labels]


def evaluate(method="Baseline"):
    """method: 'Baseline' or 'OpenAI'. Returns dict with metrics and per-item results."""
    sent_true, sent_pred, sev_true, sev_pred, items = [], [], [], [], []
    for title, content, cat, e_sent, e_sev in TEST_SET:
        art = {"title": title, "content": content, "category": cat, "company": "Test Co"}
        if method == "OpenAI":
            _, sent, sev, _ = analysis.llm_classify(art)
        else:
            _, sent, sev, _ = analysis.classify_development(art)
        sent_true.append(e_sent); sent_pred.append(sent)
        sev_true.append(e_sev); sev_pred.append(sev)
        items.append({"Headline": title, "Expected severity": e_sev, "Predicted severity": sev,
                      "Expected sentiment": e_sent, "Predicted sentiment": sent,
                      "Correct": "✅" if (e_sev == sev and e_sent == sent) else "❌"})
    out = {"n": len(TEST_SET), "items": items}
    for name, t, p, labs in [("sentiment", sent_true, sent_pred, SENTIMENT_LABELS),
                             ("severity", sev_true, sev_pred, SEVERITY_LABELS)]:
        table = _prf(t, p, labs)
        out[name] = {"accuracy": sum(a == b for a, b in zip(t, p)) / len(t),
                     "macro_f1": sum(r["F1"] for r in table) / len(table),
                     "table": table, "labels": labs, "confusion": _confusion(t, p, labs)}
    return out