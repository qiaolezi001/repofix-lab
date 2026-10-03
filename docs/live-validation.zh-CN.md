# 真实容器与模型验证

容器验收与模型效果分开记录。`scripts/docker_verify.py` 不发模型请求：它使用自建测试夹具，以及明确标注的 Mock 分页演示。10 项容器检查通过，不代表真实模型修复成功率。

在项目根目录复现容器验收：

```powershell
uv sync --locked
docker build -f Dockerfile.sandbox -t repofix-sandbox:0.1 .
uv run python scripts/docker_verify.py --output work/docker-validation.json
```

查看 JSON 中的逐项结果、实际 Docker/image ID、容器 inspect、测试输出与清理检查。所有候选代码在容器中执行；无 Docker 时脚本记录 `unavailable` 并退出 2。GitHub 的 `docker-verification` 工作流运行同一个脚本并保存 artifact。

如果镜像构建期间访问 PyPI 失败，可以按 [Docker 官方代理构建参数说明](https://docs.docker.com/build/building/variables/#proxy-arguments) 设置构建代理。Windows 的 Docker CLI 使用宿主机代理地址；构建容器访问宿主机代理时，地址通常需使用 `host.docker.internal`。构建代理与任务执行分开：候选测试仍然使用 `--network none`，不继承宿主机环境变量或模型密钥。不要将 API Key 作为构建参数。

应用镜像也可单独验收：

```powershell
docker build -t repofix-app:validation .
uv run python scripts/app_container_verify.py --output work/docker-app-validation.json
```

该验收实际启动非 root 应用容器，在随机本地端口验证界面、OpenAPI、提交 Mock 任务和报告下载，然后移除容器与临时数据卷。应用容器没有 Docker socket，所以测试状态为 `unavailable`，任务应为 `completed`。完整验证使用“宿主机应用 + 独立 Docker 测试容器”。

## 真实模型小规模试验

目前真实模型兼容性和修复效果均为 **尚未测量**。先配置你有权限访问的 API 服务、模型和费用预算；不要把密钥发到聊天、提交 GitHub 或放进截图。项目不会自动加载 `.env`。

建议先进行 2 次工具调用兼容性探测，再对开发集 `numeric-01` 做单次基线与完整 Agent 的配对试验。Agent 调用上限设为 8，基线为 1，因此本阶段最多 **11 次模型请求**。探测输出上限为 2×128，任务输出上限为 9×1800，总计 **16456 输出 Token**；每次任务的消息与工具上下文上限为 32000 字符，不能当作精确输入 Token 上限。

一个可用于当前 Chat Completions 适配器的选择是 `gpt-4.1-mini-2025-04-14`。截至 2026-10-03，[官方模型页](https://developers.openai.com/api/docs/models/gpt-4.1-mini)列出支持函数调用，标准价格为每百万输入 Token **$0.40**、缓存输入 **$0.10**、输出 **$1.60**。上述试验的输出部分最多约 **$0.02633**，输入另计；这不是总费用承诺。服务商可用性、余额和实际账单需由你的账号验证。

以下 PowerShell 示例只在当前终端设置密钥，输入不会回显。先批准费用规模，再执行有 `--allow-paid` 的命令：

```powershell
$modelSecret = Read-Host 'API Key (local only)' -AsSecureString
$env:REPOFIX_API_KEY = [System.Net.NetworkCredential]::new('', $modelSecret).Password
$env:REPOFIX_BASE_URL = 'https://api.openai.com/v1'
$env:REPOFIX_MODEL = 'gpt-4.1-mini-2025-04-14'
# 可选：只使用你明确配置的可信 HTTP(S) 代理。
# $env:REPOFIX_PROXY_URL = 'http://127.0.0.1:代理端口'
uv run repofix doctor
uv run repofix model-check --allow-paid
uv run repofix evaluate --mode live --split dev --task-id numeric-01 --max-calls 8 --output work/live-pilot --allow-paid
```

显式代理不读取 `HTTP_PROXY` 等环境设置；代理地址不得含用户名、密码、查询或片段。没有代理的环境无需设置该项。

试验输出目录包含两条逐任务记录、各自补丁、配置及汇总。公开测试通过与独立验收通过分别记录；没有独立测试结果就不能宣称修复成功。基线预算较小，不能把观察到的差异全部归因于检索。API 响应缺少用量或某次请求出错时，总用量与费用可能不完整，应标注未知并与服务商账单核对。

对于上述模型，完整用量中的输入 P、缓存输入 C、输出 O 对应费用为 `((P-C)*0.40 + C*0.10 + O*1.60)/1000000` 美元。逐次 API usage 保存在 `usage.responses`，包括服务商返回的缓存/推理细项；报告的 `cost_usd` 默认仍为 null，需要依据记录的价格计算后才能填入。不要自行假定缺失缓存用量等于零。

在开发试验确认兼容性后，冻结代码和配置，再单独批准最终评测：9 个评测任务，`--max-calls 8`，两种策略最多 **81 请求、145800 输出 Token**，不含探测。该规模的输出费用上限约 **$0.23328**，输入另计。项目没有自动美元硬限；调用次数和 Token 限制不能替代明确的总费用授权。

```powershell
uv run repofix evaluate --mode live --split eval --max-calls 8 --output work/live-eval --allow-paid
```

每次评测使用新的输出目录。不得用 Mock 结果填充真实模型指标，也不得把开发任务当作最终未见评测。
