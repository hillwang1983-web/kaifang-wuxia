import math
t=math.sqrt(2)-1
def sg(v): return 1 if v>0 else (0 if v==0 else -1)
def sector(X,Y):
    i1=sg(t*X-Y); i2=sg(X-t*Y); i3=sg(X+t*Y); i5=sg(Y+t*X)
    u=0
    if i5>=0 and i3<0: u=1
    if i1<1 and i5<0: u=2
    if i2<1 and i1>0: u=3
    if i3<1 and i2>0: u=4
    if i5<1 and i3>0: u=5
    if i1>=0 and i5>0: u=6
    if i2>=0 and i1<0: u=7
    return u
m={0:4,1:5,2:6,3:7,4:0,5:1,6:2,7:3}
names={(0,-1):'N(up)',(1,-1):'NE(up-right)',(1,0):'E',(1,1):'SE(down-right)',(0,1):'S(down)',(-1,1):'SW',(-1,0):'W',(-1,-1):'NW'}
for (mx,my),n in names.items():
    X,Y=-mx,my
    s=sector(X,Y); print(n,'move',(mx,my),'sector',s,'dir',m[s])
