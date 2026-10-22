# 网金图集查看器 (viewer/index.html)

纯前端单文件，无外部依赖，用来验证 `wjres.py` 输出的 "PNG 图集 + atlas.json" 够不够网页端用。

## 在另一台电脑上运行（拷过去就跑）

**要拷的文件夹**（整个 `资源解析` 目录即可，保持相对位置不变）：

```
资源解析\
  viewer\      index.html、serve.bat、README.md      （必须）
  out\         已转换好的样例：boy05、boy01、npc101、ahsin、menu5 …   （要看哪个拷哪个；boy01 约 130MB，可不拷）
  wjres.py     转换器（只有要重新生成图集时才需要）
```

页面和脚本里全是相对路径（页面用 `../out/`），没有任何 `C:\...` 绝对路径。

**环境要求**
* 只看样例：任意装有 **Python 3**（`python -m http.server` 自带，3.6+ 即可）和现代浏览器（Chrome/Edge/Firefox 最新版）。不需要装 Pillow。
* 要运行 `wjres.py`：**Python 3.8+ 与 Pillow**（`pip install pillow`，本机用的是 Pillow 12.3 / Python 3.14，旧版 Pillow 也应可用）。

**启动**（在 `资源解析` 目录里执行；Windows 也可直接双击 `viewer\serve.bat`）：
```
cd 资源解析
python -m http.server 8765 --bind 127.0.0.1
```
浏览器访问 <http://localhost:8765/viewer/>（顶部下拉选 `../out/` 下的目录），或 <http://localhost:8765/viewer/?dir=boy05> 直接打开。想让局域网内别的机器访问，把 `--bind 127.0.0.1` 换成 `--bind 0.0.0.0`，再用 `http://<主机IP>:8765/viewer/`。端口被占用就换个数字。

**用 wjres.py 重新生成别的 mrg**（原始资源在 `客户端\share\role`、`客户端\share\pic`，只读；下面路径假设 `资源解析` 位于 `客户端\逆向工具\` 下，其它位置请自行改相对路径）：
```
python wjres.py ..\..\share\role\boy01.mrg -o out --variants 5     # 角色, 带 5 套换色, 约 4~5 分钟
python wjres.py ..\..\share\role\boy05.mrg ..\..\share\role\boy02.mrg -o out --variants 3
python wjres.py ..\..\share\pic\menu5.mrg -o out                    # 界面图, 无换色
```
输出在 `out\<mrg 名>\`，刷新查看器页面即可看到新目录（下拉框是读 `../out/` 的目录列表）。速度约 150KB/s，`npc*.mrg` 这类百 MB 级的文件会很久，可加 `--limit-records N` 先试。

**不起服务的备选**：直接双击 `viewer\index.html`，把 `out\boy05` 目录拖进页面（file:// 下 fetch 被禁，但拖拽/“选择目录…”走本地文件，可用）。

## 启动

`file://` 下浏览器禁止 fetch，二选一：

1. **http 服务（推荐）**：双击 `viewer\serve.bat`，或在 `资源解析` 目录运行
   ```
   python -m http.server 8765 --bind 127.0.0.1
   ```
   打开 <http://localhost:8765/viewer/>，顶部下拉框会自动列出 `../out/` 下的目录；`?dir=boy05` 可直接打开某目录。
2. **不起服务**：直接双击打开 index.html，把 `out\boy05` 之类的目录**拖进页面**或点“选择目录…”。（用 blob URL 读本地文件。）

## 功能

| 标签 | 内容 |
|---|---|
| 缩略网格 | 全部 images，按名称/类型过滤，可选换色套；每格 name、frame、w×h、ox/oy 或 cw×ch；200 个一页（用 CSS 精灵图渲染，不建 canvas，9520 项的 boy01 也不卡） |
| Role 叠加 | 按 `.CPn` 后缀分 canvas（CP1/2/4/7 并排同步），每个 stem 一层；默认层序 阴影(`X##S`) → 身体(`X#0000`) → 头发(`X#M*`) → 衣服(`X#P*`) → 武器(`X#W*`)，每类默认只开第一个；可勾选/上下移层、**每层独立选换色套**、锚点十字、每层包围框；逐帧/播放/“每组帧数×组号”循环；“帧总览”把某 CPn 的全部帧排成一张图 |
| 精灵表 | rle6 / raw565 图可按手填列×行切格播放，也可点“按 cw,ch 切分” |

## 验证结论（boy05 / boy01）

**叠加正确**：`draw(锚点x+ox, 锚点y+oy)` + 上述层序，boy05 与 boy01 的人物（身体、头发、衣服、武器、阴影）在 64 帧里都对齐、无错位，换色（boy01 的 1..5）也正确。几条由此确认的事实：

* **64 帧 = 8 方向 × 8 帧**：帧总览中每 8 帧一行是同一朝向（行 0..7=8 个方向），每行第 0 帧是起势/待机姿势、1..7 是动作过程。方向顺序（哪行朝哪）仍待确认，可用查看器对照动作表。
* **CP1/CP2/CP4/CP7 是不同动作**（boy05 里 CP2 是挥剑攻击；boy01 有 CP1..CP7 共 7 个）。
* **武器 WA..WE 是互斥的不同武器**（WA=剑，WB=另一种刀，WC=枪…），不是叠加层，同时只开一个。
* **武器精灵里已经烘焙了被身体遮挡的缺口**（朝背面时剑身被身体挡住的那一段在武器图里就是缺的），所以武器永远画在最上层即可，不需要按朝向换层序。
* **锚点在身体中心(约腰部)**，不是脚底：阴影 oy≈+31..+39（在锚点下方），头发 oy≈-62。
* `oy` 向下为正，`ox,oy` 是图左上角相对锚点的偏移（与 json 说明一致）。
* 层序猜测目前**没发现不对**，但“头发 vs 衣服领口”“武器 vs 手”在个别帧是否应换序，需对照原版截图再确认。

## 发现的 atlas.json / 转换器问题（★=已在 wjres.py 里修，向后兼容）

1. ★ **`boy05.pal` 的换色套 1..5 基本是空的**（全 0 → 色键全透明）：M5PA01/M5W* 只有第 0 套有色，M5MA01 第 0=第 1 套，其余 0。旧版转换器照样输出整页全透明的 `atlas_v1..` 图集（所以之前 boy05 的 v1/v2 图集只有 35~165KB，而且换色后人物“衣服消失”）。现在**全 0 的套会被跳过**；boy01..04、06 的 `.pal` 才是 6 套全满，建议换色测试用 boy01（`--variants 5`）。
2. ★ **独立大图项格式不一致**：超过页尺寸的图（如 menu5 的 `GenSAni1` 5440×260）原来只有 `file`+`standalone`，没有 `page/x/y`。现在补上 `page=<file>, x=0, y=0`（`file/standalone` 保留）。查看器对旧文件也做了兜底。
3. ★ **缺页面尺寸**：用 CSS/WebGL 贴图需要先知道每张 PNG 的宽高，原来只能先加载图。现在顶层多了 `"pages": {"atlas_0.png":[w,h], "atlas_v1_0.png":[w,h], …}`。
4. ★ **缺记录级信息**：网页端要自己用正则从 `name` 解析 stem / CPn / 是不是阴影 / 用哪块调色板。现在顶层多了 `"records":[{"name","index","kind":"cp","stem":"m5ma01","cpn":1,"nframes":64,"pal":"m5ma01"|null,"shadow":false,"alpha":255}]`（只含 cp 类）。`pal` 就是 `palettes`/`variants` 的键。`nframes` 是含空帧的总帧数（frame 号是稀疏的：w=0 的帧不输出，叠加时该层该帧直接不画）。
5. **cw/ch 的含义不明，很可能不是动画单元尺寸**（未改，仅说明）：ahsin 的 `lantern1`（240×192，cw=30,ch=24）按 8×8 切开是乱的——它是一张完整的立绘（孙悟空站在八角台上）；`carpet1` 121×57 cw=15 ch=7；`1L` 11×26 cw=1 ch=3 都是 `cw=floor(w/8), ch=floor(h/8)`。Aspect/add101 里又是 `cw=w, ch=h`（type 6 的也是）。所以 cw/ch 看起来像“8×8 分块计数”之类的头字段，**不要拿它当精灵表单元尺寸**；查看器默认整图 1×1，提供手动切分。真正的帧动画（火焰 `cfire*`、`attack/defend`）的帧布局还需要从客户端代码里找。
6. **raw565 精灵条没有帧尺寸信息**：menu5 的 `GenSAni1` 5440×260、`GenF*` 等只给整图 w,h，没有 cw/ch/帧数。动画条要么在 json 里补帧数，要么从客户端找（逆向另一会话的动作表可能涉及）。
7. **阴影的半透明被烘焙进 PNG**（`--shadow-alpha 128`），网页端无法调整阴影浓度。`records[].shadow/alpha` 现在能标识，但图本身是烘焙的；如要在网页里调，应输出不透明阴影 + 在 JS 里设 globalAlpha。
8. **体积/加载**（最大的实际问题，未改）：boy01（98 个 cp、9520 帧）`atlas.json` **8.6 MB**，主图集 4 张 4094×~4000 的 RGBA PNG 共 ~26 MB，每套换色再 ~20 MB，全套 5 色 ≈ 130 MB；转换耗时 274 s。网页端建议：
   * cp 类改输出 **8 位索引色 PNG（P 模式）+ 在 json 里给 256 色调色板**，换色靠“改调色板”（Canvas 2D 需逐像素换色，WebGL 用调色板纹理 shader），而不是为每套输出整套 RGBA 图集 —— 体积能降一个数量级，而且 `.pal` 的 6 套任意组合/新增套都不用重新生成图集；
   * json 改紧凑格式：现在每帧都重复整个 `name`/`index`/`type`/`kind`，建议 `records[]` 内放 `frames:[[ox,oy,page,x,y,w,h],…]`（空帧用 null，下标=frame 号）；
   * 4096² 的页对部分手机 GPU 偏大（单页 64MB 显存），可加 `--page 2048`。
9. 图集 1px 间隔且无 extrude，整数缩放没问题；非整数缩放/WebGL 线性过滤会出现边缘渗色，要么用 nearest，要么 pad 时复制边缘像素。
10. 名字大小写/命名：`name` 在 role 里是 `ROLE\M5MA01.CP1`，npc 里是 `role\41174.cp`（小写、无 CPn 后缀）；`palettes` 键全小写。网页端匹配时要统一 lower-case。`.pal` 里还有 mrg 中并不存在的 stem（boy05 的 M5MB01/M5MC01、M5PB..D01、M5WF01），对应的 .cp 不在 boy05.mrg 里，应该在别的 mrg（待查）。

## 已知局限（viewer）

* 目前只猜了 `.CPn` 分组，没有任何“动作名/方向名”（等动作表逆向结果，可以加在 `records` 或另一份 json 里）。
* 方向顺序、播放顺序（每组 8 帧里第 0 帧是起势还是循环的一部分）未确认，所以播放默认只在“组内”循环。
* 层序只实现了固定顺序（带上下移动调整），没有按方向动态换序。
