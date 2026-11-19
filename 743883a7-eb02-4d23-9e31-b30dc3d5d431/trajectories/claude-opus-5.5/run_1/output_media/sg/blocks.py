import json,sys,urllib.request,os
NT=open('/tmp/nt').read().strip(); B=os.environ['NOTION_API_URL']
def get(path):
    r=urllib.request.Request(B+path,headers={'Authorization':'Bearer '+NT}); return json.load(urllib.request.urlopen(r))
def txt(rt): return "".join(x.get("plain_text","") for x in rt)
def dump(bid,ind=0):
    cur=None
    while True:
        d=get(f"/v1/blocks/{bid}/children?page_size=100"+(f"&start_cursor={cur}" if cur else ""))
        for b in d["results"]:
            t=b["type"]; c=b.get(t,{})
            print("  "*ind+f"[{t}] {b['id'][:8]} "+txt(c.get("rich_text",[])) + (" checked="+str(c.get('checked')) if t=='to_do' else ""))
            if b.get("has_children"): dump(b["id"],ind+1)
        if not d.get("has_more"): break
        cur=d["next_cursor"]
for pid in sys.argv[1:]:
    print("#####",pid); dump(pid)
