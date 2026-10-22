import sys,os,re,json,collections
sys.path.insert(0,os.path.dirname(__file__))
from mrgls import names
root=r'C:\游戏\网金最原始文件\网金最原始文件\客户端\share\role'
res={}
for fn in sorted(os.listdir(root)):
    if not fn.lower().endswith('.mrg'): continue
    if os.path.getsize(os.path.join(root,fn))<100: continue
    # npc mrgs are huge but only header + 4 bytes per record are read
    d=collections.defaultdict(dict)
    for i,nm,sz,n in names(os.path.join(root,fn)):
        m=re.match(r'(?i)role\\(.+)\.cp(\d*)$',nm)
        if not m: d['_other'][nm]=n; continue
        d[m.group(1).upper()][m.group(2) or '-']=n
    res[fn]=d
json.dump(res,open(os.path.join(os.path.dirname(__file__),'counts.json'),'w'),indent=0)
# summary: per mrg, set of CP numbers and distinct frame counts per cp for body layer
for fn,d in res.items():
    cps=collections.Counter(); cnt=collections.defaultdict(collections.Counter)
    for layer,cd in d.items():
        if layer=='_other': continue
        for c,n in cd.items():
            cps[c]+=1; cnt[c][n]+=1
    print(fn, {c:dict(cnt[c]) for c in sorted(cnt)})
