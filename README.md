# 开放武侠

本仓库同时保存网金复刻源码和原创武侠原型。协作代码以本仓库的 `main` 为共同基线，每个任务使用独立分支，通过 PR 审阅合入。

| 目录 | 内容与边界 |
|---|---|
| `服务端/` | 网金复刻 Python TCP 服务端，进度与命令见其 README |
| `客户端/` | 原版协议库、WebSocket 网关、网页客户端及逆向工具 |
| `原型/渡口失药试玩.html` | 单文件《渡口失药》，保留其他终端的素材、画面和规则迭代 |
| `原型/V0.4/` | 独立《青石渡风波》：取药→查账→渡口冲突，三结局、三招选二；说明见该目录 README |
| `武侠开放世界RPG游戏设计总纲_V0.4_草稿.md` | 20–30 分钟验证包的设计草稿，不能据此推定独立章节的完成状态 |
| `tests/` | 独立 V0.4 章节、试玩记录、浏览器与手机模拟回归 |
| `portal-integration/` | V0.4 白名单静态服务与 HTTP 测试；不包含线上账号、配置或部署状态 |

两套原型入口并存，V0.4 使用 `qingshi-chapter-v04` 存档键，与旧版 `duko-save-v3` 独立。版本号相同不表示内容相同；同步时按路径和提交号判断。网金复刻所需的原版资源与角色库不随 Git 提供，克隆仓库不代表网金客户端已具备完整运行数据。

## 本地试玩

需要 Node.js 22 或更新版本。V0.4 页面与静态服务只依赖 Node 标准库：

```sh
npm run serve
```

打开 http://127.0.0.1:8793/qingshi-v04/ 。此服务只发布四个游戏资源，不发布仓库、测试和记录。旧版原型可以在仓库根目录另运行：

```sh
python3 -m http.server 8770 --bind 127.0.0.1 --directory 原型
```

打开 http://127.0.0.1:8770/渡口失药试玩.html ，需连同 `原型/assets/na/` 素材一起使用。

## 统一测试入口

在仓库根目录运行；Windows 可将下方服务端命令中的 `python3` 换为 `python`。

```sh
npm test                  # 章节规则、试玩记录采样、HTTP 资源边界，无浏览器依赖
npm ci
npx playwright install chromium
npm run test:browser      # 六组剧情/恢复/存档失败/正常输入/触控检查 + 九项手机模拟
npm run test:all          # 上述 V0.4 测试的完整入口
npm run test:server       # 网金服务端 unittest，环境与资源要求见 服务端/README.md
```

Linux 首次安装浏览器时可用 `npx playwright install --with-deps chromium`。浏览器检查自动创建临时本机端口和隔离浏览器存档，无需先启动服务，不访问已部署游戏。`tests/browser-*.js` 是由测试入口调用的用例函数，不是独立 CLI。

GitHub Actions 对相关 PR 和 main 的变更运行同一个 `npm run test:all`。外部贡献者的工作流可能需要仓库维护者批准运行。

浏览器缺失、依赖缺失或用例失败均使命令非零退出，不自动跳过。调试推进、浏览器模拟及正常自动输入分别提供相应证据；这些结果不等于真人手机手感、自然通关时长或完整网金回归。历史验收记录里的本机路径只用于追溯，当前复测以这里的命令为准。

## 一条命令更新公网青石渡试玩

发布主机首次将 `preview-deploy.example.json` 复制为 `.preview-deploy.local.json`，填写已存在的青石渡服务目录、LaunchAgent 标签与公网看板地址。此本机配置被 Git 忽略。本机已完成配置，直接运行：

```sh
npm run update:preview
```

默认抓取 `origin/main` 的最新提交，不切换或覆盖当前工作分支。在临时目录按该提交安装锁定依赖、准备 Chromium、运行 `npm run test:all`；只有成功后才备份旧版、发布四个资源与服务代码、重启青石渡服务并检查提交号和资源哈希。测试失败不发布，发布检查失败自动恢复旧版并以非零状态报错。公网检查覆盖看板健康、登录入口与未登录拦截；不会将这些结果冒充登录后的公网试玩。

```sh
npm run update:preview -- --check-only   # 只抓取、测试，不发布
# 只有明确需要发布尚未合入 main 的分支时才指定来源：
npm run update:preview -- --remote fork --branch codex/preview-update-script
```

脚本当前仅支持本机既有的 macOS launchd 部署。它不改网关或其他游戏，不操作账号库、浏览器存档，也不自动合并 PR。远端分支缺少 V0.4 或提交号健康检查支持时明确失败，无备用模板或旧文件替代。依赖安装或下载失败也会停止。

旧版备份存于服务目录的 `backups/`，不会自动删除；`runtime-manifest.json` 记录当前运行版本，`last-update.json` 记录最近成功发布的 Git 来源、哈希与备份。更新锁遗留时，确认没有更新进程后才可移除 `.update-lock`。脚本不提供定时执行；有新代码时运行同一命令即可。

## 多终端协作

1. 开始前运行 `git status --short --branch` 和 `git fetch origin`，检查任务是否已有 PR。先保留本端未提交工作，再基于最新 `origin/main` 建立任务分支，如 `git switch -c device/任务名 origin/main`。
2. 一个任务一个分支；同时修改同一个文件前先在 PR 中说明范围。独立 V0.4、单文件原型、网金服务端分别按目录安排任务，跨目录修改须在 PR 解释原因。
3. 提交前检查 `git diff --check`、`git diff --stat` 和实际差异，运行对应测试。PR 写清基线提交、修改入口、测试命令与结果、尚未完成的实机验证。
4. 推送前再次 fetch；若 main 有更新，把最新 main 合入自己的任务分支并处理冲突、复测。共享分支不强推，不用整目录覆盖解决冲突。仅有读取权限时推到自己的 fork，再向本仓库 main 提 PR。
5. PR 审阅后再合入 main。其他终端随后 fetch 并同步 main；干净的本地主分支可用 `git pull --ff-only`。运行中的部署由独立发布步骤更新，push 不等于上线。
6. `.remember/`、浏览器存档、账号库、抓包、运行日志、备份和部署包留在各终端。依赖用 `package-lock.json` 与 `npm ci` 还原；原版数据资源按现有文档单独配置，不提交凭证和真实角色数据。

新增或修改任务请先读 `AGENTS.md` 与 `CLAUDE.md`。独立章节的导入基线和文件快照见 `docs/本地V0.4同步清单.json`；其中测试/文档/静态服务为跨终端适配而有后续改动，四个游戏资源保留快照原样。
