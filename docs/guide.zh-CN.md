# RepoFix-Lab 中文使用指南

RepoFix-Lab 接收小型 Python 代码库与 Issue，在独立工作副本中检索代码、提出补丁，再使用 Docker 运行公开测试。你可以通过 CLI 或浏览器查看证据和执行记录。

2026-10-03 已实际完成本机和 GitHub Linux 环境的 10 项容器验收，Mock 分页任务的公开测试 3/3 通过；真实模型效果仍为尚未测量。验收复现、密钥配置和小规模调用预算见 [真实容器与模型验证](live-validation.zh-CN.md)。

默认 Mock 模式是人为编排的分页 Bug 演示，用于体验工程流程。它不能证明模型理解代码或具备修复能力。当前真实模型修复效果**尚未测量**；实际验证状态以 [STATUS.md](../STATUS.md) 为准。

## 第一次运行

先安装 Python 3.11+ 与 uv，在仓库根目录运行：

```powershell
uv sync --locked
uv run repofix doctor
uv run repofix demo
uv run repofix serve
```

打开 <http://127.0.0.1:8765>。依次点击「载入示例」「启动修复」，查看结果报告、代码证据、修复补丁、测试结果和执行轨迹。界面默认使用 Mock；没有 API Key 也能体验。

示例位于 `examples/demo`，缺陷是分页起点多加了 1。修复工作副本中的 `pagination.py`，原始示例保持缺陷，便于重复演示。最终 diff 可以下载为 patch；JSON/Markdown 报告保留代码引用、工具结果、预算和验证状态。

数据默认写入当前目录的 `.repofix/`，其中 `tasks.sqlite3` 存储状态，`tasks/<id>/repo` 为工作副本，`baseline` 为不可变基线；内部 manifest 与 patch receipt 位于模型不可访问的任务根目录。若需要保留运行记录，请备份整个数据目录，不能只复制数据库。

## 打开真实测试环境

Docker 需要切换为 Linux containers。在仓库根目录构建镜像：

```powershell
docker build -f Dockerfile.sandbox -t repofix-sandbox:0.1 .
uv run repofix doctor
uv run repofix demo
```

镜像构建会联网安装固定版本 pytest；具体候选代码测试使用 `--pull never` 与 `--network none`，不会安装依赖。默认测试超时 30 秒，限制 1 CPU、256 MiB 内存、64 个进程、64 MiB 临时目录，以非 root 用户运行。宿主机源码只读挂载到容器，再复制到容器临时目录中测试。

没有 Docker CLI、daemon 不可达、不是 Linux containers 或镜像未构建时，报告会显示 `unavailable`。仍能检索和导出候选补丁，但没有公开测试通过的证据。默认不会回退到宿主机执行待修复代码。

## 输入你自己的代码库

本地目录必须是服务器进程可访问的绝对或相对路径。v0.1 接受 UTF-8 `.py` 与 `.md`，最多 500 个文件、单文件 256 KiB、总量 8 MiB。文件名包含 secret、credential、api_key 等的路径，隐藏目录、参考答案目录和基础设施文件会被排除；符号链接会被拒绝。

只修改原始快照中已有的非测试 `.py` 文件，不能改测试、添加文件或修改配置。`conftest.py`、自定义 pytest 配置、外部依赖、编译扩展、数据资产和网络服务尚不支持。先使用依赖 Python 标准库的纯函数项目。

```powershell
uv run repofix run ./examples/demo --issue "The paginate function skips the first item. Page 1 must include the first element." --mode mock
```

Mock 只识别这个专用演示；它对其他代码库没有通用修复策略。

## 真实模型接入

设置环境变量，密钥只留在本机。下面用 PowerShell 的交互式安全输入避免在命令历史里出现明文：

```powershell
$repoFixSecureKey = Read-Host 'API key' -AsSecureString
$env:REPOFIX_API_KEY = [System.Net.NetworkCredential]::new('', $repoFixSecureKey).Password
$env:REPOFIX_BASE_URL = 'https://api.openai.com/v1'
$env:REPOFIX_MODEL = '你的支持工具调用的模型名称'
```

`.env.example` 是配置说明，程序不自动读取 `.env`。也支持 `OPENAI_API_KEY` 作为密钥后备；明确设置 `REPOFIX_API_KEY` 可覆盖它。模型地址默认要求 HTTPS，仅本机开发服务允许 HTTP。

先查阅提供商当前价格，批准一个两次调用的探针。每次输出上限 128 Token，输入包括简短消息和 echo 工具 schema；金额依模型价格，当前预算金额**未知**。程序不提供自动美元金额封顶，资源上限不能代替账户费用上限。

```powershell
uv run repofix model-check --allow-paid
```

探针验证模型能返回 echo 工具调用并接受对应 tool result。通过后才运行真实任务：

```powershell
uv run repofix run ./examples/demo --issue "Fix the pagination offset and run all public tests." --mode live --allow-paid
```

CLI 的默认限制为 16 次模型调用、12 次工具调用、3 次成功修复、180 秒任务耗时、32000 字符上下文和每次 1800 输出 Token。Web 界面选择 Live 后需要确认本次调用，Web 使用 8 次模型调用上限；baseline 固定为单次生成。具体有效参数保存在任务 `limits` 中。

适配器使用 Chat Completions `/chat/completions`、function calling、`max_completion_tokens` 和 `parallel_tool_calls=false`。不同“兼容”提供商仍可能不支持这些字段，需以 `model-check` 和实际任务验证为准。HTTP 模拟测试验证了协议解析与异常处理，不能代替在线验证。API Key 缺失不妨碍离线工程验收。

清除当前终端凭证可执行：

```powershell
Remove-Item Env:REPOFIX_API_KEY -ErrorAction SilentlyContinue
```

## 看懂结果状态

| 状态 | 含义 |
| --- | --- |
| `queued` | 已建立快照，等待执行 |
| `running` | 正在请求模型或执行工具 |
| `interrupted` | 上一次工作进程停止，等待显式恢复 |
| `succeeded` | 有候选 diff，并且最后一次补丁后的完整公开测试通过 |
| `completed` | 已完成诊断或生成候选，但尚未获得上述公开验证 |
| `failed` | 模型错误、预算耗尽、工具异常或测试失败等 |
| `timed_out` | 任务时间预算用尽 |
| `cancelled` | 用户请求取消 |

`succeeded` 不表示独立评测通过。普通任务的 `independent_tests.status` 保持 `not_run`；只有外部评测器运行独立测试，才能得出该结论。Mock 即使实际 Docker 测试通过，也仅证明人为编排的演示补丁可通过这些测试。

## 取消与恢复

Web 运行中可以点击取消。取消是协作式的：检查点边界会读取独立取消标志，容器测试会清理具名容器；正在进行的 HTTP 调用受请求超时限制，不能保证立即结束。

服务重启后，遗留 `running` 任务会标为 `interrupted`。点击恢复会从持久状态继续；Live 任务恢复可能消耗剩余调用预算。补丁工具有操作回执，能识别已应用的同一次操作，避免重复替换。恢复依赖原有数据目录中的数据库、快照和 receipts，不能随意编辑其中的文件。

## API 与报告

运行后可查看机器可读的接口定义 <http://127.0.0.1:8765/openapi.json>。界面使用本地静态资源；默认依赖 CDN 的 Swagger/Redoc 页面已关闭，以兼容离线运行和浏览器安全策略。主要接口：

| 方法 / 路径 | 用途 |
| --- | --- |
| `GET /api/health` | 模式、模型与 Docker 状态 |
| `GET /api/demo` | 演示代码库位置与 Issue |
| `GET /api/tasks` | 最近任务列表 |
| `POST /api/tasks` | 创建并启动任务 |
| `GET /api/tasks/{id}` | 完整持久状态和事件 |
| `POST /api/tasks/{id}/cancel` | 取消 |
| `POST /api/tasks/{id}/resume` | 恢复中断任务 |
| `GET /api/tasks/{id}/report?format=md\|json` | 导出报告 |

单用户接口不提供登录或多租户授权。默认只绑定本地地址；请保持 localhost 使用，不要直接公开监听到互联网。

## 运行检查与评测

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repofix
uv run pytest
uv run repofix evaluate --mode mock --split eval --output work/mock-eval
```

离线评测结果能证明框架对任务的接入、策略运行和输出记录。Mock 未解决某个任务不是模型失败率；缺少 Docker 则测试与独立验收仍未测量。真实评测需先阅读 [评测设计](evaluation.md)，核对成本并使用 `--allow-paid`。

## 容器运行应用

```powershell
docker compose up --build
```

Compose 只把端口发布到 `127.0.0.1:8765`，不挂 Docker socket 或宿主机凭证，任务保存在 named volume。应用容器提供诊断/API/UI；Docker 测试不可用，这是预期限制。镜像内已有示例，额外挂载示例到 `/input/demo`；输入本机其他仓库时需主动加只读挂载，并填写容器内路径。

## 从哪里开始学习

先按 [源码导读与练习](learning.zh-CN.md) 运行一次 demo，再从 `TaskRequest`、`Engine.run` 和 `ToolRegistry.execute` 追踪一次工具调用。独立完成三个小改动并做 Live 验证后，再根据实际参与程度修改简历描述。公开发布步骤见 [publishing.md](publishing.md)。
