# 源码导读、面试准备与亲手练习

这个项目由 Codex 辅助完成。把它作为学习和持续维护的起点：只有你能独立讲清调用链、验证关键行为并完成自己的改动，才适合在简历中写成你的项目经历。下面的回答是源码阅读提示，需要你结合实际运行重新表达。

## 推荐阅读路线

| 顺序 | 文件 | 阅读时回答的问题 |
| --- | --- | --- |
| 1 | `examples/demo/pagination.py` 与公开测试 | 人工缺陷为什么会跳过元素？测试为什么能发现它？ |
| 2 | `src/repofix/models.py` | TaskRequest、Limits 如何拒绝非法输入？ |
| 3 | `src/repofix/config.py` | 密钥、数据目录、镜像配置来自哪里？ |
| 4 | `src/repofix/workspace.py` | 原始目录如何变成两份隔离快照？哪些文件被排除？ |
| 5 | `src/repofix/index.py` | AST 如何产生符号片段？BM25 每个变量代表什么？ |
| 6 | `src/repofix/tools.py` | schema 与 Python 参数验证怎么对应？统一错误如何进入下一轮？ |
| 7 | `src/repofix/providers.py` | Reply 如何包装 content、actions、usage？Mock 为什么只是一份脚本？ |
| 8 | `src/repofix/store.py` | 状态 JSON、取消列与 lease 分别解决什么问题？ |
| 9 | `src/repofix/engine.py` | pending 意图、工具结果和最终验证分别在哪保存？ |
| 10 | `src/repofix/sandbox.py` | 运行命令如何限制执行环境？怎样清理超时容器？ |
| 11 | `src/repofix/api.py`、`cli.py`、`reports.py` | 一个用户动作怎样进入 Engine、再导出结果？ |
| 12 | `src/repofix/evaluation.py` 与 `benchmarks/manifest.json` | 独立测试什么时候注入？如何保证不泄露给 Agent？ |
| 13 | `tests/` | 哪些测试验证真实行为？哪些使用模拟传输或沙箱？ |

第一次阅读不要试图记住全部细节。运行 demo，把一个 `tool_request` 的操作 ID 在 SQLite 状态、events 和 receipts 中对应起来，再回到 `Engine.run` 追踪它。

## 一次实际任务的调用链

1. 浏览器向 `POST /api/tasks` 发送目录、Issue、模式、策略和限制。FastAPI 使用 `TaskRequest` 严格验证。
2. `Engine.create` 创建 ID；`Workspace` 按策略读取允许的文件，生成 `baseline`、`repo`、manifest 与版本哈希；初始状态写入 `Store`。
3. API 启动后台工作，`Engine.run` 领取 lease，将任务标为 `running`。它检查取消标志、剩余时间、模型调用预算，并构建有界上下文。
4. Mock 第一次回复提出 `search_code`。真实模型通过 tool schema 选择动作。引擎先写入 `pending` 和 `tool_request`，再交给 `ToolRegistry.execute`。
5. `search_code` 实例化 `Index`，AST 切分后计算 BM25；结果包含真实路径、符号、行号、文本和版本。证据写入状态，结构化工具结果作为 `role=tool` 的消息进入下一轮。
6. Demo 继续读取 `pagination.py`，随后 `apply_patch` 将 `start = (page - 1) * page_size + 1` 替换为少了 `+ 1` 的语句。工具检查唯一匹配、写权限与文件限制，保存 patch intent/result 回执；语法或行为错误通过后续测试暴露。
7. `run_tests` 调用 `Sandbox.run`。没有 Docker 时返回 `unavailable`；有环境时运行完整公开测试，保存输出、退出码和完整性标志。新的补丁会清除上一轮测试结论。
8. 模型结束后 `_verify_and_finish` 必要时补做完整公开验证；`_finish` 生成 baseline 对比 diff 并保存终态。仅完整公开测试通过且有候选 diff 才为 `succeeded`。
9. UI 通过 `GET /api/tasks/{id}` 轮询公开状态；`reports.public_state` 排除内部消息/pending 等细节，Markdown/JSON 报告解释候选、公开测试与独立验收。普通 demo 未运行 hidden tests，因此独立验收保持 `not_run`。

可以直接在运行时对照工具轨迹验证这条链。Mock 使用真实工具与存储，但动作选择是人为脚本；Live 的选择才来自模型。

## 面试问题与参考回答

**1. 这是怎样的 Agent？哪里由模型决定？**

`Engine.run` 提供状态与工具 schema，调用 provider，再执行 Reply 中的 Action；后续消息包含工具观察。Live 模型决定检索词、读取范围、补丁与继续动作。MockProvider 是固定脚本，仅演示这条闭环。不能用 Mock 截图证明模型规划能力。

**2. 为什么没用 LangGraph？**

目前只有一个模型和一个依次执行的工具动作，直接状态机足够。代码里的 pending 意图、SQLite checkpoint 和 patch receipts 更容易审查。将来出现并行检索、分支审核或多 Agent 任务，再引入图编排会更有价值。

**3. AST 切分相比固定长度分块有什么作用？**

`Index` 用函数、类及嵌套名称定位语义边界，引用可以指向实际符号和行号。长符号再拆为最多 100 行的小片段。代价是 class 与 method 可能重叠；语法错误用文本回退并留下 warnings，避免索引静默失败。

**4. 为什么先用 BM25？有什么缺点？**

实现可复现，不需要 embedding API；代码标识符与 Issue 中的名字常有词面重合。`tokenize` 拆 snake_case/CamelCase。BM25 难以识别语义同义词和跨语言描述，下一步可增加检索消融比较，而不能直接假定混合检索效果更好。

**5. 如何防止模型调用任意命令或越界读取？**

只有 `TOOL_MODELS` 中六个工具可调用，参数通过严格 Pydantic 模型。`Workspace.resolve` 拒绝绝对路径、盘符、`..`、未知快照文件与符号链接；写入只允许既有非测试 Python 源码。没有通用 shell 工具。这是工具层的约束，仍需关注文件系统竞争与生产攻击面。

**6. 修复不能靠删除测试过关是怎样保证的？**

编辑工具不能写测试，`Workspace.validate` 通过原始 manifest 检查测试哈希；容器执行后再检查测试内容。公开成功还要求完整测试集合，运行一部分测试不能达到 `succeeded`。同解释器中的恶意代码仍可能干预测试过程，这是文档承认的限制。

**7. 进程在补丁写入后崩溃，恢复为什么不会重复替换？**

执行前 `pending` 先持久化，补丁工具保存按 action ID 标记的参数指纹与前后内容回执。恢复时，同一操作可以返回原结果或识别已写入状态；同 ID 不同参数被拒绝。`tests/test_engine.py` 和 `test_tools.py` 中的故障注入验证这一边界。不要把它描述成跨系统的分布式 exactly-once。

**8. 取消为什么单独用数据库列？**

Engine 可能持有旧的 state JSON。若取消仅修改这个 JSON，旧 worker 的下一次 save 会覆盖取消请求。`Store.cancel` 更新独立 `cancelled` 列，循环边界读取它；容器轮询也检查 token。HTTP 调用要等待请求超时或返回，所以取消是协作式。

恢复也不能把「待模型决策」和「待最终验证」混为一谈：`verification_pending` 记录测试结果是否已持久化。后者恢复时不再调用模型；未记录结果的测试重试仍扣工具次数，已记录结果则直接用于收尾。`tests/test_engine.py` 同时验证默认预算和只有一次模型调用的 baseline。

**9. 如何控制 Agent 死循环和成本？**

`Limits` 有模型次数、工具次数、修复轮数、任务超时、上下文字符和单次输出上限，计数保存在状态中，恢复也沿用预算。它们限制资源，不能保证某个美元金额；真实成本需价格、完整 Token usage 和账户配额。批量调用要求 `--allow-paid`。

**10. 上下文裁剪为什么不能直接取最后 N 条消息？**

函数调用的 assistant 消息与对应 tool result 是一组，直接截取可能留下没有调用 ID 的结果。`Engine._context` 保留 system/Issue 和最近完整轮次，按字符预算选择。字符不是 Token，因此仍有近似误差，需要模型端输入限制与更精确的后续改进。

**11. Docker 不可用时怎么保证报告诚实？**

`Sandbox.available` 返回原因，`run_tests` 标 `unavailable`，不执行 host fallback。候选仍能生成，但终态是 `completed`，公开验证不算通过。报告和 UI 用三个独立结论显示候选、公开验证、独立验收。

**12. 成功率怎样评测，怎样避免答案泄露？**

15 个人工任务分为 6 dev / 9 eval。Agent 只接收每项的 `repo/` 和 Issue，hidden、meta、reference 在外部。完成后，评测器在另一份 candidate 中注入 hidden tests 并运行 Docker。公平性需记录同模型、任务和预算；baseline 与 agent 调用预算不同，是系统比较而非严格等算力消融。当前没有真实模型成绩。

**13. “OpenAI-compatible” 接口为什么还要探针？**

兼容提供商可能不支持 strict schema、`max_completion_tokens` 或 `parallel_tool_calls=false`。`LiveProvider.check` 检查一次函数调用和一次 tool result 回合；离线 HTTP contract tests 只证明程序编码/解析正确，不证明在线模型支持。完成探针和真实任务后才可声称实测兼容。

**14. 怎么知道一次代码证据还对应当前文件？**

引用有 baseline 版本与当时文件的 `content_sha256`。同一任务修改之后 baseline version 不变，但 content hash 可以不同。不能仅看版本号假定引用仍是最新代码；需要结合事件顺序和后续读取。这也说明报告中保存证据原文的价值。

## 你亲自完成的三个小改动

先创建自己的分支，每个改动保留提交、测试输出和一段解释。

**练习 A：增加一种检索查询预处理。** 在 `index.tokenize` 或查询入口尝试保留点分模块名等信息；设计至少三组会受影响的查询与候选排序，比较改前/改后前几项。使用 `uv run pytest tests/test_index.py` 验证现有行为，再跑 Ruff。不要把简单测试上的变化写成整体召回提升。

**练习 B：让 Web 用户配置修复轮数。** 添加一个有界数字输入，将值放到 POST 的 `limits.max_repairs`；展示任务实际有效限制。分别验证 1、3、非法 0/11，确认服务端 Pydantic 拒绝非法请求，并验证 Mock 的报告仍显示真实预算。可用浏览器 Network 面板与 `uv run pytest tests/test_api.py` 检查接口。

**练习 C：新增第 16 个开发任务。** 先不改变 frozen eval。为新版本 fixture 添加一个你自己的跨文件 Bug、公开测试、hidden test 和参考替换，更新独立 manifest/生成脚本。验证初始公开测试失败、参考修复的公开与隐藏测试在 Docker 内通过、Agent 工作副本中没有答案目录。用 `tests/test_benchmarks.py` 的完整性检查作为起点，保留失败与通过日志。

## 简历描述草稿

以下是待你完成阅读、验证和维护后的写法，应注明你实际做过的部分，不把 AI 输出自动变成个人贡献。不要填入未经真实模型测量的成功率或提升百分比。

1. **RepoFix-Lab · Python Issue 修复 Agent**：基于 FastAPI、Pydantic 与 SQLite 构建本地修复实验台，使用 AST 符号分块和 BM25 返回带路径、行号与版本的代码证据，提供 6 个参数校验工具及 CLI/Web 报告。
2. 为 Agent 实现模型/工具调用、修复轮次、时间和上下文预算，使用持久化 pending 状态与补丁回执支持中断恢复，区分候选补丁、完整公开测试与独立验收结果；通过故障注入验证重复补丁、取消和超限行为。
3. 建立 3 个小型 Python 项目、15 项人工 Bug 的可复现评测集，冻结 6 dev / 9 eval 划分并隔离参考答案与隐藏测试，提供单次生成与检索迭代两种策略比较；真实模型效果与 API 成本尚待实测。

如果你尚未亲自实现第二条的内容，可改为“在 Codex 辅助生成的实现上阅读、验证并维护……”并补充自己的练习和提交。测试数量应从你发布前的实际运行结果填写，不能把未来预期写成完成数据。

## 交付与个人责任

| 内容 | Codex 已承担的工作 | 你需要亲自完成 |
| --- | --- | --- |
| 源码与架构 | 生成核心模块、接口、工具和初版设计说明 | 阅读调用链，判断设计，完成自己的改动与提交 |
| 离线检查 | 运行本地 lint/type/tests 与 Mock 演示，记录证据 | 在自己的机器复现；理解模拟测试的证明范围 |
| Docker | 提供镜像与执行限制、相关离线测试 | 在有 Docker 的机器实际构建和跑 demo；检查输出 |
| 模型效果 | 提供适配器、兼容探针与评测器 | 本地配置 Key，明确预算后授权并运行；审核误修复 |
| 开源发布 | 提供 README、License、CI 和发布步骤 | 账号归属、许可证确认、审查公开内容、批准推送 |
| 简历与面试 | 提供基于代码的草稿与问答 | 按真实参与修改，能现场解释、定位问题并改代码 |

面试前可以做一次不看参考答案的 20 分钟演练：从 UI 点一次任务，画出调用链，解释一个失败 case，再现场改一个工具参数。能完成这些，比记住项目介绍更有说服力。
