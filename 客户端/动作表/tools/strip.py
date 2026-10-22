import sys,os,struct
sys.path.insert(0,r'C:\游戏\网金最原始文件\网金最原始文件\客户端\逆向工具\资源解析')
import wjres
from PIL import Image, ImageDraw
root=r'C:\游戏\网金最原始文件\网金最原始文件\客户端\share\role'
out=r'C:\游戏\网金最原始文件\网金最原始文件\客户端\逆向工具\动作表\strips'
os.makedirs(out,exist_ok=True)
mrgname=sys.argv[1]; layers=sys.argv[2].split(','); cps=sys.argv[3].split(',')
m=wjres.Mrg(os.path.join(root,mrgname))
idx={n.upper():i for i,n in enumerate(m.names)}
def frames(layer,cp):
    key=('ROLE\\%s.CP%s'%(layer,cp)).upper()
    if key not in idx: return None
    pal,fr=wjres.parse_cp(m.get(idx[key]))
    return pal,fr
for cp in cps:
    L=[frames(l,cp) for l in layers]
    L=[(l,x) for l,x in zip(layers,L) if x]
    if not L: print('no',cp); continue
    n=len(L[0][1][1]); per=n//8
    CW,CH=110,120; ax,ay=55,95
    sheet=Image.new('RGBA',(CW*per,CH*8),(60,60,70,255))
    d=ImageDraw.Draw(sheet)
    for dr in range(8):
        for f in range(per):
            fi=dr*per+f
            cell=Image.new('RGBA',(CW,CH),(60,60,70,255))
            for (l,(pal,fr)) in L:
                x,y,w,h,data=fr[fi]
                if w==0 or h==0: continue
                idxb=wjres.lzss(data,w*h)
                im=wjres.idx_to_rgba(idxb,w,h,pal)
                cell.alpha_composite(im,(ax+x,ay+y)) if (0<=ax+x and 0<=ay+y and ax+x+w<=CW and ay+y+h<=CH) else cell.paste(im,(ax+x,ay+y),im)
            sheet.paste(cell,(f*CW,dr*CH))
            d.rectangle([f*CW,dr*CH,f*CW+CW-1,dr*CH+CH-1],outline=(90,90,100,255))
            d.text((f*CW+2,dr*CH+2),'d%d f%d'%(dr,f),fill=(255,255,0,255))
    p=os.path.join(out,'%s_CP%s.png'%(mrgname[:-4],cp)); sheet.save(p); print(p,n,per)
