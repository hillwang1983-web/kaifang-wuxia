import json,re,sys,collections,csv
scr=sys.argv[1]
pe=open(r'C:\游戏\网金最原始文件\网金最原始文件\客户端\maina\loginp.exe','rb').read()
items=json.load(open(scr+r'\batch1.json',encoding='utf8'))+json.load(open(scr+r'\batch2.json',encoding='utf8'))
def addr_of(n): return int(re.search(r'([0-9a-f]{8})$',n).group(1),16)
def lstr(va):
    o=va-0x400000; n=int.from_bytes(pe[o-4:o],'little')
    return pe[o:o+n] if 1<=n<=2000 else None
def sstr(va):
    o=va-0x400000; n=pe[o]
    return pe[o+1:o+1+n] if 1<=n<=40 else None
rows=[]; uncl=[]
for x in items:
    c=x['pseudocode'] or ''
    sends=list(re.finditer(r'FUN_009db454\(([^;]*?),\s*([^;]*?)\);',c))
    if not sends: continue
    info=dict(func=x['address'],sends=len(sends),type=None,how='',sub='',extra='')
    # 1) literal / concat-with-literal (long string)
    types=[]
    for m in sends:
        arg=m.group(2).strip()
        mm=re.fullmatch(r'&?((?:DAT_|s_)[A-Za-z0-9_]*?[0-9a-f]{8})',arg)
        va=None
        if mm: va=addr_of(mm.group(1)); how='lit'
        else:
            var=re.sub(r'^\(.*?\)\s*','',arg).lstrip('&'); best=None
            for mv in re.finditer(r'FUN_004053[0-9a-f]{2}\(&?%s,\s*&?((?:DAT_|s_)[A-Za-z0-9_]*?[0-9a-f]{8})'%re.escape(var),c[:m.start()]): best=mv
            if best: va=addr_of(best.group(1)); how='cat'
        if va:
            b=lstr(va)
            if b: types.append((b[0],b[:8].hex(),how))
    # 2) ShortString stub pattern
    if not types:
        ss=re.search(r'FUN_004032a4\(\w+,\s*&?((?:DAT_|s_)[A-Za-z0-9_]*?[0-9a-f]{8})\)',c)
        if ss:
            b=sstr(addr_of(ss.group(1)))
            if b:
                rg=re.search(r'\(byte\)\((\w+) - 1U\) < (0x[0-9a-f]+|\d+)',c)
                types.append((b[0],b.hex(),'stub'))
                if rg: info['sub']='1..%d'%int(rg.group(2),0)
    if types:
        t=types[0]; info.update(type=t[0],extra=t[1],how=t[2])
        info['alltypes']=sorted({tt[0] for tt in types})
        rows.append(info)
    else: uncl.append(info)
print('functions with send:',len(rows)+len(uncl),' typed:',len(rows),' untyped:',len(uncl))
by=collections.defaultdict(list)
for r in rows: by[r['type']].append(r)
print('distinct types:',len(by))
for t in sorted(by,key=lambda k:-len(by[k]))[:25]:
    print('type 0x%02x'%t, len(by[t]),'functions; hows',collections.Counter(r['how'] for r in by[t]), 'subs',[r['sub'] for r in by[t] if r['sub']][:4])
with open(scr+r'\outbound_types.csv','w',newline='',encoding='utf-8-sig') as f:
    w=csv.writer(f); w.writerow(['函数地址','类型字节(hex)','来源','子类型范围','发送点数','常量前8字节(hex)','该函数涉及的全部类型'])
    for r in sorted(rows,key=lambda r:(r['type'],int(r['func'],16))):
        w.writerow([r['func'],'0x%02x'%r['type'],r['how'],r['sub'],r['sends'],r['extra'],' '.join('0x%02x'%t for t in r['alltypes'])])
    for r in sorted(uncl,key=lambda r:int(r['func'],16)):
        w.writerow([r['func'],'?','未识别','',r['sends'],'',''])
