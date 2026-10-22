# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目是什么

《金庸群侠传 Online》（网金）的私服复刻，个人学习自用，不分发、不商用。文档、注释、提交说明都是**中文**，新增内容沿用中文。根目录有一份`武侠开放世界RPG游戏设计总纲_V0.3.pdf`（后续原创玩法的设计与验收（V0.3，2026-10-22）：「渡口失药」约 20–30 分钟的单人手机横屏动作验证包，要求用**独立数据库和独立角色库**，不得写网金复刻的正式角色库，也不得覆盖当前客户端；目前没有代码对应。同目录的 `武侠开放世界RPG游戏设计总纲_V0.3_修订稿.md` 是它的 Markdown 修订稿（附录 A 列出改动与待决策项）；`武侠开放世界 RPG · V0.3 评审意见.pdf` 是外部评审，吸收后整理成 `武侠开放世界RPG游戏设计总纲_V0.4_草稿.md`（首页有逐条处理表，附录 A 参数总表、附录 C 待确认的草稿取值）。可复用与必须新写的部分见 PDF 第 09–10 节）。`原型/` 是这个验证包的网页试玩：`渡口失药试玩.html`（单文件，像素美术全部用代码绘制，本地存档走「副本修改 + 操作号去重」的提交；加 `?debug` 会暴露 `window.__duko` 供脚本逐帧测试）和 `像素样张.html`（美术方向样张）。本地预览用 `.claude/launch.json` 里的 `prototype` 配置（`python -m http.server 8770 --directory 原型`）。

两个子项目，靠**原版 TCP 协议**对接：

- `服务端/` — `jyserver`：Python 3.14 + asyncio 重写的服务端，说原版协议，原版客户端 `loginp.exe` 能直接连。
- `客户端/` — 逆向出来的客户端协议库 `jyclient.py` + WebSocket 网关 `gateway.py` + 浏览器页面 `web/`，即「网页版客户端」。它是服务端的主要测试对象。

没有 git 仓库，没有版本管理（`服务端/.gitignore` 只忽略 `captures/`、`__pycache__`）。改之前自己留意备份；发布靠打 zip（见下）。

## 常用命令

服务端（在 `服务端/` 目录，只用标准库）：

```bash
python -m unittest discover -s tests -t .          # 全部测试
python -m unittest tests.test_codec                # 单个模块
python -m unittest tests.test_codec.TestX.test_y   # 单个用例
python -m jyserver.importer                        # 原版 MySQL → data/chars.sqlite（只读 MySQL）
python -m jyserver.server --port 6732              # 默认 6732，和原服务端并存做对照；原版客户端固定连 6731
python -m jyserver.manage add-account <jyid> <密码> # 建账号
python tools/decode_hex.py c2s "f6 11 01 ..."      # 解一段十六进制帧
```

客户端（在 `客户端/` 目录；网关也只用标准库，`bigmap.py` 才需要 numpy + Pillow，页面 `web/` 里没有构建步骤）：

```bash
python gateway.py [--server 127.0.0.1:6732] [--listen 127.0.0.1:8088]   # 页面 http://127.0.0.1:8088/
python isolated_server.py --port 6734      # 起一个临时库副本的隔离服务端，改数据的测试都用它
python test_gateway.py --port 8088 --jyid 123456     # 需要网关 + 服务端已在运行；--mutate 会改角色数据，只在隔离服务端上用
python client_scenario.py [--scenario map|rekey]     # 多人场景
python client_actions_test.py                        # 自起隔离服务端，装备 / 用药 / 商店
python test_evt.py                                   # NPC 对话引擎离线自测，不需要服务端
python api_map.py                                    # opcode → 方法 / 网关操作 / 页面入口 覆盖表
python build_mac_client.py [--maps none | --update <底包>]   # 打 macOS 部署包到 dist/
python 服务端/tools/build_mac_package.py   # 服务端的同类打包（在服务端目录下运行）
```

客户端的 `test_*.py` 大多是脚本式（各自 `main()` + argparse），不是 unittest；用 `python 文件.py` 跑。测试号 `8617293 / 1234567 / 123456`（密码 = 账号）。

## 架构

### 协议（理解任何代码前先读 `服务端/docs/协议模型.md`）

- 帧：`魔数(F4 44 短帧 / F5 B3 长帧) + 长度 + opcode + 参数`，整帧与一个单字节密钥 XOR。S2C 密钥写在帧头；C2S 线路是 `F6 11 <序号> + XOR(密钥, 明文)`，**C2S 密钥 = `基数 XOR 序号`**，基数默认 `0x7D`（新账号握手后为 `0x34`），服务端发 `0x99 04 <种子>` 时按 `derive_key(种子)` 换基数。密钥不对的帧原版**静默忽略**，序号重复则断开（防重放）。
- 线上中文是 **BIG5 繁体**，库 / CSV 是 **GBK 简体**；下发前走 `state.to_big5` + `data/s2t.json` 简繁表（只有 CP950 里有的字才转，别手改转换规则，见 `docs/事件引擎.md`）。
- 网络实体 ID == 数据库 `jyid`。

### 服务端 `服务端/jyserver/`

- `server.py`：`GameServer` 持有 `Conn` 状态机；`dispatch()` 按 opcode 分到 `on_*` 方法，再转给按功能拆的模块（`account bank battle commands craft creation events items kungfu life org shop study team trade`）。新增处理函数 = 在 `dispatch` 里挂 opcode + 新模块里写纯逻辑函数（返回要发的帧），`server.py` 只负责把帧发给对的人。
- `codec.py` 帧编解码 / 流式拆帧 / 密钥推导（解码无状态，**编码必须用客户端当前期望的密钥**）；`opcodes.py` 只收有证据的 opcode，并标证据等级；`state.py` 由角色数据**生成**登录序列（`0x1E` 角色状态包等）；`store.py` SQLite 角色库（`data/chars.sqlite`，`importer.py` 从原版 MySQL 导入）。
- 数据表（物品、商店、事件、武功…）**运行时直接读原版服务端的 `data/` `config/` CSV**：部署包里在 `原版数据/`，开发机读 `C:\游戏\网金最原始文件\网金最原始文件\服务端\`（只读，不要改）。`recipes.json`、`life_items.json` 是从反编译抠出的表，由 `tools/extract_*.py` 生成。
- **核心方法论：原版行为逐包复刻**。功能的「正确」标准是和原版 `服务端.exe` 回包 / 落库逐字节一致，连原版的怪行为（如丢弃只扣 1 件、商店单价恒为 1）也照搬，每个 `docs/*.md` 记录对应功能的实测规则和已知怪行为。验证靠对拍工具：`tools/*_compare.py` / `*_probe.py` 对原版（MySQL 3306，端口 6731）和新服务端跑同一脚本再比较回包与库（`jyproxy.py` 夹在客户端与原版之间录 JSONL；`sim_client.py` 模拟客户端）。反编译用 REA（见 `docs/服务端逆向笔记.md` 的函数地址）。
- 战斗（`battle.py`）只做了单人打怪，进战后的帧序列按客户端侧反编译，伤害 / 掉落数值是**自定**的，不是原版公式；NPC 摆放、师徒 / 门派、修炼、镖局等没做，清单见 `docs/服务端功能盘点.md`。
- 改 `0x1E` 登录包相关代码时看 `docs/0x1E字段表.md`、`docs/登录序列布局.md`；`tools/verify_state.py` 把生成器与 `data/fixtures/char-*.json` 真实快照逐字节比。已知偏差：`state.py` 把 kf 行写成 11 字节而原版实测 9 字节（见 `客户端/遗留问题.md` F 节）。

### 客户端 `客户端/`

- 链路：浏览器 `web/index.html` ⟷ WebSocket/JSON ⟷ `gateway.py`（自带最小 HTTP + RFC6455，页面与 `/ws` 同端口）⟷ `jyclient.py`（asyncio 协议库）⟷ TCP ⟷ 服务端。网关 JSON 指令表在 `gateway.py` 文件头注释。**网关没有鉴权、协议登录只认 jyid，别监听 0.0.0.0。**
- 游戏逻辑在客户端侧的部分（因为原版就是客户端主导）：`evtengine.py` + `evtdata.py` 解释原版 `EvtMrg*/TextMrg*` 事件脚本做 NPC 对话；`jyfight.py` 战斗；`bigmap.py` 野外大地图；`npcdata.py/npcdat.py` NPC 摆放与精灵；`parse_0x1e.py` 解登录状态包；`packet_proxy.py` 帧编解码 / 抓包代理（`jyclient` 也依赖它）。
- `web/sprites/`、`web/objects/` 是 `build_sprites.py / build_npc_sprites.py / build_objects.py / build_fx.py` 预生成的缓存；`客户端/资源解析/wjres.py` 把原版 `.mrg` 转成 PNG 图集（需要 Pillow），`viewer/` 是它的查看器（`python -m http.server 8765` 后访问 `/viewer/`），`动作表/` 是动作 / 方向 / 帧序的逆向结果（CPn = 动作号，每个 `.cp` = 8 方向块）。
- 逆向笔记在 `客户端/*.md`：`客户端库说明.md`、`战斗协议_客户端侧.md`、`C2S_0x31命令表.md`、`资源格式说明.md`、`遗留问题.md`（卡点与已搁置功能）、`交接*.md`。

## 注意事项

- **路径依赖本机旧布局**：代码里硬编码了 `C:\游戏\网金最原始文件\...`（原版数据）和 `C:\游戏\网金复刻\data\s2t.json` 等旧位置作为开发机默认值；`客户端/` 需要的 `share/`（地图、`dat/*.dat`、`pic/*.mrg`）、`maina/` 并不在本目录里，缺了网关会提示资源没读到。部署包会把这些路径换成包内相对路径。
- 原版服务端强制单点登录且会写库；对原版跑对拍前先看对应 `tools/` 脚本是否会改库（`exp_compare.py --cleanup` 还原 `事件.csv`）。`登录器(双).exe` 是第三方程序，只在隔离环境运行。
- `captures/` 抓包含账号 ID，别外传。
- 服务端 `README.md` 是持续更新的功能进度表（M0/M1 里程碑与「还没做」清单）；做完一个功能后同步 README 与对应 `docs/*.md`，并补 `tests/test_*.py`。
