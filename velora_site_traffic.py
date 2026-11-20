"""Optional free-tier site-traffic estimates for Leonardo (Vaneform API).

The public homepage NEVER exposes a reliable visit counter. This module reads
third-party ESTIMATES only when the local operator has explicitly configured
VANEFORM_API_KEY. There is no screen scraping, CAPTCHA bypass or paid fallback.
"""
from __future__ import annotations

import json
import os
import ipaddress
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_ROOT = "https://vaneform.com/api/v1"
MAX_BODY_BYTES = 500_000


def _source_domain(website: str) -> dict:
    """Return site host and whether a shared-host path prevents attribution."""
    try:
        parsed=urlsplit(str(website or "").strip())
        hostname=(parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in ("https","http") or not hostname or len(hostname)>253:
            raise ValueError("missing or invalid public site")
        if hostname.startswith("www."):
            hostname=hostname[4:]
        if not re.fullmatch(r"[a-z0-9.-]+",hostname) or "." not in hostname:
            raise ValueError("not a public DNS hostname")
        if any(part.startswith("-") or part.endswith("-") or not part
               for part in hostname.split(".")):
            raise ValueError("invalid domain")
        if hostname.endswith((".local",".internal",".localhost",".test",".invalid",".example")):
            raise ValueError("reserved domain")
        try:
            ipaddress.ip_address(hostname)
            raise ValueError("IP literals not supported")
        except ValueError as exc:
            if "not supported" in str(exc):raise
        path=(parsed.path or "").strip("/")
        # Directories or property pages on a shared domain are never property
        # specific analytics. Likewise multi-property hosts need an explicit
        # property-scoped measurement, not a domain-wide estimate.
        return {"domain":hostname,"scope":"domain_not_property" if path else "domain",
                "sitePath":bool(path)}
    except (ValueError,TypeError):
        return {"domain":"","scope":"invalid_site","sitePath":False}


def _request(url: str,key: str) -> dict:
    req=Request(url,headers={
        "Authorization":"Bearer "+key,
        "Accept":"application/json",
        "User-Agent":"Velora-Leonardo/1.0 (site-traffic estimate API)",
    })
    with urlopen(req,timeout=12) as response:
        body=response.read(MAX_BODY_BYTES+1)
    if len(body)>MAX_BODY_BYTES:
        raise ValueError("API response too large")
    value=json.loads(body.decode("utf-8"))
    if not isinstance(value,dict):
        raise ValueError("API response is not an object")
    return value


def _parse(domain: str,scope: str,value: dict) -> dict:
    scale=value.get("scale") if isinstance(value.get("scale"),dict) else {}
    raw=scale.get("visits")
    try:
        visits=int(float(raw)) if raw is not None and not isinstance(raw,bool) else None
    except (ValueError,TypeError,OverflowError):
        visits=None
    if visits is not None and not (0<visits<10**13):
        visits=None
    estimate_type=scale.get("estimate")
    is_site=estimate_type=="site"
    # A search-only estimate is NOT equivalent to visits from all channels.
    estimate_type=estimate_type if estimate_type in {"site","search"} else "unknown"
    confidence=scale.get("confidence")
    confidence=confidence if confidence in {"low","medium","high"} else "unknown"
    raw_sources=scale.get("sources") if isinstance(scale.get("sources"),dict) else {}
    sources={}
    for name in ("direct","search","social","referrals","mail","display_ads","search_paid","affiliate","gen_ai","other"):
        val=raw_sources.get(name)
        if isinstance(val,(int,float)) and not isinstance(val,bool) and 0<=val<=1:
            sources[name]=round(float(val)*100,2)
    raw_regions=scale.get("top_regions") if isinstance(scale.get("top_regions"),list) else []
    regions=[]
    for row in raw_regions[:5]:
        if not isinstance(row,dict):continue
        country=str(row.get("country") or "")[:60]
        share=row.get("share")
        if country and isinstance(share,(int,float)) and 0<=share<=1:
            regions.append({"country":country,"sharePct":round(share*100,2)})
    return {
        "provider":"Vaneform","status":"estimated" if visits is not None else "not_available",
        "domain":domain,"scope":scope,"measurement":"third_party_estimate",
        "visitsMonthlyEstimate":visits,"estimateType":estimate_type,
        "wholeSiteVisits":visits if is_site else None,
        "month":str(scale.get("as_of") or "")[:10],"confidence":confidence,
        "momChangePct":scale.get("visits_mom_change_pct")
            if isinstance(scale.get("visits_mom_change_pct"),(int,float)) else None,
        "sourcesPct":sources,"topRegions":regions,
        "retrievedAt":datetime.now(timezone.utc).isoformat(),
        "reportUrl":value.get("report_url") if isinstance(value.get("report_url"),str)
            and value["report_url"].startswith("https://vaneform.com/") else "",
        "note":("Stima dell'intero dominio: NON attribuibile alla singola struttura o pagina."
            if scope=="domain_not_property" else
            "Stima del dominio, non misurazione Analytics né visite verificate.")
    }


def collect_site_traffic(website: str, *, api_key: str|None=None, fetch=None) -> dict:
    """One best-effort lookup; never block or invalidate Leonardo's booking audit.

    Vaneform's individual domain GET is cache_only. A no-data response can be
    followed by a one-domain bulk query to request a stored traffic snapshot.
    Two requests maximum; no automatic retry after rate limit/denial.
    """
    source=_source_domain(website)
    domain=source["domain"]
    base={"provider":"Vaneform","domain":domain,"scope":source["scope"],
          "measurement":"third_party_estimate","wholeSiteVisits":None,
          "visitsMonthlyEstimate":None}
    if not domain:
        return {**base,"status":"invalid_site","note":"Sito pubblico non configurato o dominio non valido."}
    key=(api_key if api_key is not None else os.environ.get("VANEFORM_API_KEY","")).strip()
    if not key:
        return {**base,"status":"not_configured",
                "note":"Configura la chiave gratuita VANEFORM_API_KEY sull'agente Windows."}
    call=fetch or _request
    try:
        value=call(API_ROOT+"/domains/"+quote(domain,safe="")+"?include=scale",key)
        parsed=_parse(domain,source["scope"],value)
        if parsed["status"]=="estimated":return parsed
        # Single domain read is cache_only; a bulk read can fetch an uncached
        # traffic estimate. This still uses the vendor's documented API.
        bulk=call(API_ROOT+"/bulk?q="+quote(domain,safe=""),key)
        items=bulk.get("items") if isinstance(bulk,dict) else None
        if isinstance(items,list):
            chosen=next((item for item in items
                if isinstance(item,dict) and item.get("domain")==domain),None)
            if chosen:
                result=_parse(domain,source["scope"],chosen)
                if result["status"]=="estimated":return result
        return {**parsed,"note":"Nessuna stima disponibile dal provider per questo dominio; non equivale a zero visite."}
    except HTTPError as exc:
        status={401:"invalid_key",403:"access_denied",429:"limit_reached"}.get(exc.code,"unavailable")
        return {**base,"status":status,"note":(
            "Limite del piano gratuito o frequenza superata; nessun acquisto automatico."
            if status=="limit_reached" else
            "Vaneform ha rifiutato la richiesta; verifica chiave o disponibilità."
        )}
    except (URLError,TimeoutError,OSError,ValueError,TypeError,KeyError) as exc:
        return {**base,"status":"unavailable",
                "note":"Fonte temporaneamente non accessibile ("+type(exc).__name__+"). Nessuna visita inventata."}
