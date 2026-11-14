"""Inspect archive schema without private key, print anonymized field descriptions."""
import requests,zstandard,io,json,collections
from pathlib import Path
out=Path("pumpfun/boost_features");out.mkdir(exist_ok=True,parents=True)
hours=requests.get("https://replay.shrine.trade/pump/index.json",timeout=20).json()["hours"]
hour=hours[-8]
samples={}
with requests.get("https://replay.shrine.trade/pump/"+hour+".jsonl.zst",stream=True,timeout=40) as r:
 r.raise_for_status()
 stream=zstandard.ZstdDecompressor().stream_reader(r.raw)
 for line in io.TextIOWrapper(stream,encoding="utf-8"):
  try:x=json.loads(line)
  except ValueError:continue
  a=x.get("action")
  if a not in samples and a in ("migrate","buy","sell","createPool"):
   samples[a]={"keys":list(x.keys()),"types":{k:type(v).__name__ for k,v in x.items()},
               "safe_values":{k:v for k,v in x.items() if k in ("action","protocol","quoteMint","baseMint")}}
  if len(samples)>=4:break
result={"hour":hour,"samples":samples}
(out/"schema.json").write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
