# 山寺（垂直切片，Godot 4）

把 `参考资料/` 里《武侠 ARPG 垂直切片功能规格书》、小说《山寺归僧》和《美术说明（AI 生图用）》做成可玩的垂直切片。2026-10-23 决定用 **Godot 4.7** 做，不再沿用网页原型的代码；`原型/V0.4/`《青石渡风波》本身不改。

当前状态：**工程骨架、输入映射和测试入口已就绪，还没有游戏代码**；主场景只是一行「开发中」占位。先由策划按 `UI设计/交换清单_第一里程碑.md` 出图，再按图开发。

## 打开与测试

Godot 4.7.2 用 winget 装（不需要管理员；没有 `godot` 短命令，可执行文件是 `Godot_v4.7.2-stable_win64_console.exe`，安装时已加进用户 PATH，新开终端生效）：

```bash
winget install --id GodotEngine.GodotEngine --exact
```

打开 Godot → 导入 → 选本目录的 `project.godot`；F5 运行。

无界面测试（会先导入一遍资源，再跑 `tests/test_*.gd`，失败时退出码为 1）：

```bash
powershell -ExecutionPolicy Bypass -File 原型/山寺/tools/test.ps1
```

工程设置：内部分辨率 960×540、窗口 1920×1080、整数倍拉伸，贴图默认最近邻、2D 变换吸附整像素（像素风不糊）；渲染器用 Compatibility（网页导出走 WebGL2）。

## 试玩：网页版（手机与电脑浏览器）

试玩发链接、浏览器打开，不发 exe。导出网页版到 `build/web/`（已被 `.gitignore` 排除）：

```bash
powershell -ExecutionPolicy Bypass -File 原型/山寺/tools/export_web.ps1
```

本机预览用 `.claude/launch.json` 的 `shansi-web` 配置（`python -m http.server 8772 --directory 原型/山寺/build/web`，只听 127.0.0.1）。

- 导出用单线程版本（`variant/thread_support=false`），不需要 COOP / COEP 响应头，iPhone Safari 也能跑；开了 PWA，可「添加到主屏幕」横屏全屏。
- 体积：`index.wasm` 约 39.5 MB（引擎本体，未压缩；服务器开 gzip / brotli 后约十分之一到四分之一），`index.pck` 是游戏内容。手机第一次打开要等下载。
- 画面按设备实际像素整数倍放大：iPhone 横屏（DPR 3）放大 2 倍，左右留黑边（手机比 16:9 宽）。要不要改成「两边多露场景」等第一张场景图出来再定。
- 网页里没有系统中文字体可回落，界面字体用工程自带的 Fusion Pixel 12px 简体（`assets/fonts/fusion-pixel/`，SIL OFL 1.1，许可文件同目录），主题在 `scenes/default_theme.tres`，字号按 12 的整数倍用。
- 还没接到公网试玩发布流程（`scripts/update-preview.mjs`），手机目前只能在同一局域网另起服务访问。
- 导出模板 4.7.2 已装在 `%APPDATA%\Godot\export_templates\4.7.2.stable\`（含 Windows，以后要出 exe 也能直接导）。

## 键位

由 `tools/setup_input.gd` 生成进 `project.godot`，改键位改这个脚本再跑一遍（命令见脚本头注释）。

| 动作 | 键鼠 | 手柄 |
|---|---|---|
| 移动 | WASD / 方向键 | 左摇杆 |
| 瞄准 | （鼠标位置，开发时接） | 右摇杆 |
| 普攻 | J / 鼠标左键 | A |
| 主动一 / 二 / 三 | U / I / O | X / Y / B |
| 通用技 | K | RB |
| 合击 | F | RT |
| 闪避 | 空格 | LB |
| 取消蓄力 / 瞄准 | Esc / 鼠标右键 | LT |
| 交谈 / 互动 | E | 十字键上 |
| 物品栏 | Tab | Start |
| 暂停 | P | Back |

和规格书第五节不同的三处：三主动从 Q W E 改为 U I O（W 与移动冲突）；手柄取消从 B 改为 LT（B 是主动三）；规格书没给交谈 / 互动和暂停键，暂定如上。

## 已定取舍（2026-10-23）

- 第一版单人 + AI 净心，但按联机拆结构：战斗规则写在不依赖场景树的纯逻辑层（`scripts/sim/`），每帧吃「各玩家指令」推进；合击的「响应者」做成接口，真人和 AI 走同一个。以后接 Godot 多人联机时由服务端跑这一层（服务端权威，规格书第二节）。
- 少林、邪派两门派都做：各一被动 + 三主动 + 通用技槽（梯云纵 / 运功疗伤 / 截脉三选一）+ 合击键。
- 第一个里程碑：小说任务节点 0–3（茶棚相遇、破山门、叛僧教头两阶段：教闪避、教打断）+ 双人合击与默契值。
- 试玩走网页版，手机和电脑浏览器都要能玩：键鼠与 Xbox / PS 手柄用 Godot 输入映射，**触屏操作（左摇杆 + 右侧按键群）提前到第一个里程碑**（规格书原把手机放第二阶段，2026-10-23 改）。
- 从 V0.4 带过来的只有手感与规则数值（三连普攻、闪避消耗与无敌帧、预警时长、架势 / 打断 / 失衡、命中停顿与震屏），按规格书重新标定后写进数据，不搬代码。

## 目录

```
原型/山寺/
├── project.godot    Godot 工程设置
├── .gitignore       忽略 .godot/ 缓存与导出产物
├── UI设计/          界面效果图与美术↔开发交换清单
├── assets/          美术交付的游戏资产（命名见交换清单）
│   ├── env/  obj/  chr/  npc/  boss/  vfx/  ico/  ui/  por/
│   ├── fonts/       Fusion Pixel 中文像素字体与 OFL 许可
│   └── ref/         母图、定妆图、GPT 原图（不进游戏）
├── scenes/          场景（.tscn）：现在只有 main.tscn 占位；之后是茶棚、山门、角色、界面
├── scripts/
│   ├── sim/         纯逻辑：世界状态、门派招式、合击与默契、Boss、AI 净心
│   └── game/        画面、输入、镜头、界面、对话
├── tests/           无界面测试：run_tests.gd 入口、test_case.gd 基类、test_*.gd 用例
├── tools/           setup_input.gd 生成键位、test.ps1 跑测试、export_web.ps1 导出网页版
└── export_presets.cfg  网页导出预设
```

各目录里的 `.gitkeep` 只是让空目录进 Git，放进文件后可以删。`*.gd.uid` 是 Godot 4.4 起自动生成的脚本 ID，要和脚本一起提交。

还没做的准备：网页版接进公网试玩发布流程。
