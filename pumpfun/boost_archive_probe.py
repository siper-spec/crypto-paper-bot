"""Audit one historical replay hour for directly identifiable BOOST start/end events.
Streaming source; at most 25MB decompressed or 250k rows, for bounded GitHub execution.
No inference of BOOST from ordinary buys.
"""
import requests,json,collections,time
from pathlib import Path
out=Path("pumpfun/boost_probe_results");out.mkdir(parents=True,exist_ok=True)
result={"source":"shrine historical archive","status":"starting","records":0,
        "boost_marked":0,"examples":[],"actions":{},"protocols":{},"errors":[]}
try:
    r=requests.get("https://replay.shrine.trade/pump/index.json",timeout=18)
    r.raise_for_status()
    index=r.json()
    hours=index.get("hours") or []
    result["hours_available"]=len(hours)
    if not hours:raise RuntimeError("archive index has no hours")
    # Choose a UTC hour safely behind the newest rolling archive.
    hour=hours[-min(3,len(hours))]
    url=f"https://replay.shrine.trade/pump/{hour}.jsonl.zst"
    result["hour"]=hour;result["archive_url"]=url
    import zstandard
    actions=collections.Counter();protocols=collections.Counter()
    with requests.get(url,stream=True,timeout=40) as response:
        response.raise_for_status()
        stream=zstandard.ZstdDecompressor().stream_reader(response.raw)
        import io
        for line in io.TextIOWrapper(stream,encoding="utf-8"):
            if not line.strip():continue
            try:e=json.loads(line)
            except ValueError:continue
            result["records"]+=1
            actions[e.get("action","?")]+=1;protocols[e.get("protocol","?")]+=1
            t=json.dumps(e).lower()
            if "boost" in t or "buy_and_burn" in t:
                result["boost_marked"]+=1
                if len(result["examples"])<3:result["examples"].append({k:e.get(k) for k in ("action","protocol","mint","timestamp","signature","method","instruction")})
            if result["records"]>=250000:break
    result["actions"]=dict(actions)
    result["protocols"]=dict(protocols)
    result["status"]="boost_events_present" if result["boost_marked"] else "no_explicit_boost_marker_in_sample"
except Exception as exc:
    result["status"]="source_unavailable"
    result["errors"].append(str(exc)[:450])
(out/"summary.json").write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
