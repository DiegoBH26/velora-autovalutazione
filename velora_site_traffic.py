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
from datetime import datetime, timezone, timedelta
from pathlib import Path
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
    # Vaneform returns dated monthly history in scale.monthly_visits.
    # Preserve only legitimate months; do not infer missing months as zero.
    monthly=[]
    raw_history=scale.get("monthly_visits")
    if isinstance(raw_history,list):
        seen=set()
        for item in raw_history[:36]:
            if not isinstance(item,dict):
                continue
            month=str(item.get("month") or "")
            raw_visits=item.get("visits")
            if not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])",month) or month in seen:
                continue
            if isinstance(raw_visits,bool) or not isinstance(raw_visits,(int,float)):
                continue
            estimated=int(raw_visits)
            if estimated<0 or estimated>10**12 or estimated!=raw_visits:
                continue
            monthly.append({"month":month,"visits":estimated})
            seen.add(month)
    monthly.sort(key=lambda row:row["month"])
    # The current snapshot may be newer than the returned series. Only add
    # it when it represents whole-site traffic and has an unambiguous month.
    current_month=str(scale.get("as_of") or "")[:7]
    if (is_site and visits is not None and
        re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])",current_month)
        and current_month not in {row["month"] for row in monthly}):
        monthly.append({"month":current_month,"visits":visits})
        monthly.sort(key=lambda row:row["month"])
    months_by_year={}
    for item in monthly:
        year=item["month"][:4]
        months_by_year.setdefault(year,[]).append(item)
    annual=[]
    for year,entries in sorted(months_by_year.items()):
        # Do not turn the sum of 3 sampled months into a claimed annual total.
        annual.append({
            "year":int(year),
            "sumAvailableMonths":sum(row["visits"] for row in entries),
            "monthsAvailable":len(entries),
            "monthsMissing":[f"{year}-{m:02d}" for m in range(1,13)
                             if f"{year}-{m:02d}" not in {r["month"] for r in entries}],
            "completeYear":len(entries)==12,
        })
    raw_bounce=scale.get("bounce_rate")
    bounce_pct=round(raw_bounce*100,2) if isinstance(raw_bounce,(int,float)) and not isinstance(raw_bounce,bool) and 0<=raw_bounce<=1 else None
    raw_pages=scale.get("pages_per_visit")
    pages_per_visit=round(float(raw_pages),2) if isinstance(raw_pages,(int,float)) and not isinstance(raw_pages,bool) and 0<=raw_pages<1000 else None
    raw_duration=scale.get("time_on_site_seconds")
    duration_seconds=int(raw_duration) if isinstance(raw_duration,(int,float)) and not isinstance(raw_duration,bool) and 0<=raw_duration<86400 else None
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
        "monthlyVisits":monthly if is_site else [],
        "annualSummaries":annual if is_site else [],
        "bounceRatePct":bounce_pct,"pagesPerVisit":pages_per_visit,
        "timeOnSiteSeconds":duration_seconds,
        "retrievedAt":datetime.now(timezone.utc).isoformat(),
        "reportUrl":value.get("report_url") if isinstance(value.get("report_url"),str)
            and value["report_url"].startswith("https://vaneform.com/") else "",
        "note":("Stima dell'intero dominio: NON attribuibile alla singola struttura o pagina."
            if scope=="domain_not_property" else
            "Stima del dominio, non misurazione Analytics né visite verificate.")
    }


def _api_error(exc: HTTPError) -> tuple[str, str]:
    """Translate documented API error codes, without logging secrets."""
    code=""
    try:
        payload=json.loads(exc.read(8192).decode("utf-8"))
        if isinstance(payload,dict):
            details=payload.get("error")
            if isinstance(details,dict):
                code=str(details.get("code") or "")[:80]
    except (OSError,ValueError,TypeError,UnicodeError,AttributeError):
        pass
    if exc.code==401:
        if code=="invalid_api_key":
            return "invalid_key","Chiave API rifiutata da Vaneform: sostituita, errata o non attiva."
        return "unauthorized","Autenticazione Vaneform non autorizzata: verifica chiave e formato Bearer."
    if exc.code==429:
        return "limit_reached","Limite o crediti Vaneform esauriti ("+(code or "HTTP 429")+")."
    if exc.code==403:
        return "access_denied","Accesso Vaneform negato ("+(code or "HTTP 403")+")."
    return "unavailable","Vaneform non disponibile (HTTP "+str(exc.code)+")."


def check_vaneform_connection(*, api_key: str|None=None, fetch=None) -> dict:
    """Free GET /account; never returns the API key or makes a paid lookup."""
    key=(api_key if api_key is not None else os.environ.get("VANEFORM_API_KEY","")).strip()
    if not key:
        return {"provider":"Vaneform","status":"not_configured",
                "note":"Chiave VANEFORM_API_KEY non presente nell'agente Windows."}
    if not key.startswith("vf_live_") or len(key)<20 or any(c.isspace() for c in key):
        return {"provider":"Vaneform","status":"invalid_format",
                "note":"Il valore salvato in Windows non ha il formato vf_live_... della chiave API."}
    try:
        data=(fetch or _request)(API_ROOT+"/account",key)
        credits=data.get("credits")
        credits=credits if isinstance(credits,dict) else {}
        remaining=credits.get("remaining")
        if not isinstance(remaining,int) or isinstance(remaining,bool):
            remaining=None
        return {
            "provider":"Vaneform","status":"connected",
            "plan":str(data.get("plan") or "non indicato")[:25],
            "creditsRemaining":remaining,
            "note":"Chiave API verificata sull'endpoint account; controllo gratuito, nessun credito consumato.",
        }
    except HTTPError as exc:
        status,note=_api_error(exc)
        return {"provider":"Vaneform","status":status,"note":note}
    except (URLError,TimeoutError,OSError,ValueError,TypeError) as exc:
        return {"provider":"Vaneform","status":"unavailable",
                "note":"Controllo Vaneform non concluso ("+type(exc).__name__+")."}


def collect_site_traffic(website: str, *, api_key: str|None=None, fetch=None,
                         cache_dir: str|Path|None=None) -> dict:
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
    # Avoid spending a free credit every day when Leonardo is rerun on the
    # same domain. One successful reading per UTC month is enough for audits;
    # missing data is retried after 24 hours.
    cache_file=None
    now=datetime.now(timezone.utc)
    if cache_dir is not None:
        try:
            cache_base=Path(cache_dir).resolve()
            cache_base.mkdir(parents=True,exist_ok=True)
            cache_file=cache_base/("traffic_"+domain.replace(".","_")+".json")
            prior=json.loads(cache_file.read_text(encoding="utf-8"))
            stored_at=datetime.fromisoformat(str(prior.get("retrievedAt") or "").replace("Z","+00:00"))
            stored_at=stored_at.replace(tzinfo=stored_at.tzinfo or timezone.utc)
            if (prior.get("provider")=="Vaneform" and prior.get("domain")==domain
                    and prior.get("schemaVersion")==2
                    and prior.get("status") in {"estimated","not_available"}
                    and (stored_at.strftime("%Y-%m")==now.strftime("%Y-%m")
                         if prior.get("status")=="estimated"
                         else now-stored_at < timedelta(hours=24))):
                return {**prior,"cached":True}
        except (OSError,ValueError,TypeError,AttributeError):
            pass
    def save(value):
        value={**value,"schemaVersion":2}
        if cache_file is not None and value.get("status") in {"estimated","not_available"}:
            try:
                cache_file.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
            except OSError:
                pass
        return value
    call=fetch or _request
    try:
        value=call(API_ROOT+"/domains/"+quote(domain,safe="")+"?include=scale",key)
        parsed=_parse(domain,source["scope"],value)
        if parsed["status"]=="estimated":return save(parsed)
        # Single domain read is cache_only; a bulk read can fetch an uncached
        # traffic estimate. This still uses the vendor's documented API.
        bulk=call(API_ROOT+"/bulk?q="+quote(domain,safe=""),key)
        items=bulk.get("items") if isinstance(bulk,dict) else None
        if isinstance(items,list):
            chosen=next((item for item in items
                if isinstance(item,dict) and item.get("domain")==domain),None)
            if chosen:
                result=_parse(domain,source["scope"],chosen)
                if result["status"]=="estimated":return save(result)
        return save({**parsed,"note":"Nessuna stima disponibile dal provider per questo dominio; non equivale a zero visite."})
    except HTTPError as exc:
        status,note=_api_error(exc)
        return {**base,"status":status,"note":note}
    except (URLError,TimeoutError,OSError,ValueError,TypeError,KeyError) as exc:
        return {**base,"status":"unavailable",
                "note":"Fonte temporaneamente non accessibile ("+type(exc).__name__+"). Nessuna visita inventata."}
