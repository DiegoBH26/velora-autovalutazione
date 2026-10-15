"""Velora v97: archivio progressivo delle offerte OTA, senza prezzi storici spacciati per attuali."""
from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone

def _identity(o, q):
    return "|".join(str(v or "").strip().casefold() for v in (
        o.get("otaId"), o.get("checkin"), o.get("checkout"), o.get("adults"),
        q.get("roomType") or q.get("roomName"), q.get("ratePlan"), q.get("total"),
        q.get("currency") or "EUR",
    ))

def consolidate(path: Path, result: dict) -> None:
    """Archive observed quotes across runs; never put stale quotes into live observations."""
    pid = str(result.get("propertyId") or "unknown")
    safe_id = "".join(c for c in pid if c.isalnum() or c in "-_")[:90] or "unknown"
    history_path = path.parent / ("velora-quote-history-" + safe_id + ".json")
    entries = {}
    for src in (history_path, path):
        if not src.is_file():
            continue
        try:
            old = json.loads(src.read_text(encoding="utf-8"))
            for item in old.get("quoteHistory", []):
                if isinstance(item, dict) and item.get("key"):
                    entries[item["key"]] = item
            for obs in old.get("observations", []):
                for quote in obs.get("quotes") or []:
                    if not isinstance(quote, dict) or quote.get("total") is None:
                        continue
                    key = _identity(obs, quote)
                    if key not in entries:
                        entries[key] = {
                            "key": key, "otaId": obs.get("otaId"), "checkin": obs.get("checkin"),
                            "checkout": obs.get("checkout"), "adults": obs.get("adults"),
                            "quote": quote, "firstSeen": obs.get("observedAt"),
                            "lastSeen": obs.get("observedAt"), "sourceUrl": obs.get("finalUrl") or obs.get("sourceUrl"),
                        }
        except (OSError, ValueError, TypeError):
            continue

    now = datetime.now(timezone.utc).isoformat()
    current_keys = set()
    for obs in result.get("observations", []):
        for quote in obs.get("quotes") or []:
            if not isinstance(quote, dict) or quote.get("total") is None:
                continue
            key = _identity(obs, quote)
            current_keys.add(key)
            previous = entries.get(key)
            if previous:
                quote["historyStatus"] = "reconfirmed"
                first_seen = previous.get("firstSeen") or now
            else:
                quote["historyStatus"] = "new"
                first_seen = obs.get("observedAt") or now
            entries[key] = {
                "key": key, "otaId": obs.get("otaId"), "checkin": obs.get("checkin"),
                "checkout": obs.get("checkout"), "adults": obs.get("adults"),
                "quote": dict(quote), "firstSeen": first_seen,
                "lastSeen": obs.get("observedAt") or now,
                "sourceUrl": obs.get("finalUrl") or obs.get("sourceUrl"),
            }
    history = []
    for key, item in entries.items():
        row = dict(item)
        row["currentRunConfirmed"] = key in current_keys
        row["historyStatus"] = "reconfirmed" if key in current_keys else "historical_not_reconfirmed"
        history.append(row)
    result["quoteHistory"] = history
    result["quoteHistorySummary"] = {
        "archived": len(history), "confirmedThisRun": len(current_keys),
        "notReconfirmedThisRun": len(history) - len(current_keys),
        "note": "Le offerte storiche non sono disponibilita o prezzi attuali confermati."
    }
    tmp = history_path.with_name(history_path.name + ".tmp")
    try:
        tmp.write_text(json.dumps({"quoteHistory": history}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, history_path)
    except OSError as error:
        print(f"warning: quote history non salvato: {error}", flush=True)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
