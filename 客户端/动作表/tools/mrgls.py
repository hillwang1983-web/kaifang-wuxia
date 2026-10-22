import struct,sys
def names(path):
    d=open(path,'rb').read(1<<20) if False else None
    f=open(path,'rb'); h=f.read(8); cnt,nl=struct.unpack('<II',h)
    tab=f.read(13*cnt); nm=f.read(nl).decode('gbk','replace').split('\r\n')
    base=8+13*cnt+nl
    out=[]
    for i in range(cnt):
        sz,off,_,t=struct.unpack_from('<IIIB',tab,13*i)
        n=None
        if sz>=4:
            f.seek(base+off); n=struct.unpack('<I',f.read(4))[0]
        out.append((i,nm[i] if i<len(nm) else '',sz,n))
    return out
if __name__=='__main__':
    for r in names(sys.argv[1]): print(*r)
