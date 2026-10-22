import json,os
base=r'C:\游戏\网金最原始文件\网金最原始文件\客户端\逆向工具\动作表'
full=json.load(open(os.path.join(base,'action_table.json'),encoding='utf-8'))
avail=full['availability']
models=[]
def add(mid,mrg,body,shadow,series):
    a=avail.get(mrg,{})
    models.append({"model":mid,"mrg":mrg,"series":series,"bodyLayer":body,"shadowLayer":shadow,
      "atlas":"../资源解析/out/%s/atlas.json"%mrg[:-4],
      "cps":{k[2:]:v['framesPerDir'] for k,v in a.items()}})
for n,m in enumerate(['boy01','boy02','boy03','boy04','boy05','boy06','boy07','boy08'],1):
    add(n,m+'.mrg','M%d0000'%n,'B%d0S'%n,'M')
for i,m in enumerate(['boy10','boy11','boy12','boy13','boy14','boy15']):
    add(0x14+i,m+'.mrg','B%d0000'%(i+1),None,'B')
for i,m in enumerate(['girl','girl02','girl03','girl04','girl05','girl06','girl07']):
    add(0x80+i,m+'.mrg','G%d0000'%(i+1),'G%d0S'%(i+1),'G')
for i,(m,f) in enumerate(zip(['girl09','girl10','girl11','girl12','girl13','girl14'],[1,2,3,4,5,7])):
    add(0x92+i,m+'.mrg','F%d0000'%f,None,'F')
web={
 "version":1,
 "_doc":"网页端直接 import 的动作表。所有路径相对本 JSON 所在目录。字段说明见 动作表说明.md 第 9 节。",
 "directionCount":8,
 "directions":["N","NW","W","SW","S","SE","E","NE"],
 "directionNote":"0=上(背对镜头) 逆时针 ... 4=下(面向镜头) ... 7=右上; 无镜像",
 "tickMs":1,
 "actions":{
   "idle":{"cp":7,"loopFrames":8,"intervalMs":150},
   "walk":{"cp":1,"loopFrames":8,"intervalMs":100},
   "attack":{"cp":4,"loopFrames":8,"intervalMs":100,"once":True,"note":"世界场景只播0..7后回到站立; 文件里可能有 15 帧/方向"},
   "ride_move":{"cp":8,"loopFrames":8,"intervalMs":100},
   "ride_idle":{"cp":9,"loopFrames":8,"intervalMs":150},
   "skillA":{"cp":2,"loopFrames":8,"fileFramesBySeries":"12(boy01,02,girl)/8","battleOnly":True},
   "skillC":{"cp":3,"loopFrames":8,"fileFramesBySeries":"12(boy01,02,girl)/8","battleOnly":True},
   "battle5":{"cp":5,"loopFrames":8,"battleOnly":True,"confidence":"low"},
   "battle6":{"cp":6,"loopFrames":8,"battleOnly":True,"confidence":"low"},
   "special10":{"cp":10,"loopFrames":8,"confidence":"low"}
 },
 "cpFallbackRules":[
   {"if":{"modelNotIn":[1,2,128],"seriesNotIn":["B","F"]},"map":{"5":4,"6":4}},
   {"if":{"modelIn":[6,7,8,132,133,134]},"map":{"3":2}},
   {"if":{"seriesIn":["B","F"]},"map":{"2":4,"3":4,"5":4,"6":4}}
 ],
 "cpFallbackNote":"依次套用 0x5253c8 的折叠规则; 套完若该模型仍没有这个 cp 就不画(原版行为)",
 "worldState":{
   "stateToAction":{"0":"idle","1":"walk","2":"idle","4":"walk_or_idle_by_timer"},
   "mountedMap":{"walk":"ride_move","idle":"ride_idle"},
   "attackOverridesWhenNotMounted":"attack"
 },
 "stepRule":"interval = (state==walk) ? actions.walk.intervalMs : actions[action].intervalMs; 当 now-last>interval 则 frame=(frame+1)%loopFrames",
 "framePicking":"fileFrame = dir*framesPerDir + f; 从 atlas.images 里找 name==ROLE\\<层>.CP<cp> 且 frame==fileFrame 的项",
 "layerOrder":{"default":[0,1,2,3],"models3to9":[0,2,1,3],"note":"0=身体,k>0=装备槽k; 先画阴影"},
 "layers":{"shadow":"阴影,半透明","bodyThenEquip":"装备层名如 M5MA01(发)/M5PA01(衣)/M5WA01(武器), 同一 CP 同一帧号叠在同一锚点"},
 "drawOffsetY":{"model3":6,"model4":9,"model129":9,"model130":10,"default":0,"base":-56,"note":"y_draw=y+offset-56, 再加各帧 oy"},
 "frameDraw":"drawImage(page, x,y,w,h -> (px+ox, py+oy))，ox,oy 来自 atlas.json 每帧",
 "atlasPattern":"../资源解析/out/{mrg不含扩展名}/atlas.json",
 "models":models,
 "mountedRiders":{"mrg":"Horse.mrg","atlas":"../资源解析/out/Horse/atlas.json","note":"模型 1-4/G1-3 骑乘(cp8/9)用 Horse.mrg 内同名层; 其它模型 cp8/9 在自己 mrg"}
}
json.dump(web,open(os.path.join(base,'action_table.web.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
print(len(models))

