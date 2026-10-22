# Specifai 上游实际代码审计

审计日期：2026-10-21（Asia/Singapore）。只读取公开源码，未安装依赖、未运行上游、未连接模型、未读取真实客户数据。

## 结论与建议

上游适合复用“调研 → BRD → PRD → 用户故事 → 测试用例”的生成组织方式、文档 ID 与关联结构、编辑和流程可视化界面；它不是现成的财务规则引擎，也不能把模型自评当成 UAT 签字。建议先做 Finance Product Agent 的独立财务领域模块，补齐来源证据、澄清状态、规则版本、稳定关联 ID、变更影响、人工基线和 UAT 执行记录。是否整体保留 Electron/Angular，应由目标已有代码库决定，不应为复用而强行重写已有项目。

## 固定来源与复现

- 上游：<https://github.com/presidio-oss/specif-ai>
- 本次 shallow clone 的 HEAD：`a084a227b0d65c009544d8af575a7a4f5c37b4be`，默认分支 main。
- 工作副本：`work/upstream`。复核命令：`git -C work/upstream rev-parse HEAD`；阅读 `LICENSE`、根及 electron/ui 的 `package.json`、下列实现文件。
- 根包版本为 2.8.2，见[根 package.json](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/package.json#L1-L23)。这只是所审计源码声明的版本，不代表依赖当前最新版本。

## 已核实的许可证事实

[根 LICENSE 全文](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/LICENSE#L1-L27)包含 MIT 授权、Presidio 版权、随副本/实质部分保留版权与许可文本的要求和免责条款；末尾另附 Branding 条款：修改或再分发版本的 Presidio logo、商标及其他品牌资产须移除或替换，除非取得书面许可。因此不能仅凭根 package.json 的 `MIT` 标签忽略追加文本。

根 package.json 自报 MIT，[electron/package.json](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/package.json#L1-L45)却自报 ISC，存在元数据不一致。安全实施建议：复制或修改上游实质代码时，原样保留根 LICENSE，新增 THIRD_PARTY_NOTICES/来源与修改说明；替换产品名称、图标、品牌图、安装包元数据及上游更新发布地址；不把新增文件归属说成 Presidio 官方产品。第三方依赖另有许可证，尚未逐一展开包内容核验，不能声称已完成全依赖法律合规或漏洞审计。

## 已核实架构与依赖

| 层次 | 实际实现 | 对落地的影响 |
|---|---|---|
| 桌面主进程 | [electron/app.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/app.ts#L1-L27)，按 handlers 注册 IPC；BrowserWindow 使用 preload、contextIsolation=true、nodeIntegration=false | 保留桌面形态时，财务读写应放主进程，渲染层只经受限接口 |
| 界面 | [ui/package.json](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/ui/package.json)，Angular 16.2、TypeScript ~5.1.3、NGXS 18、RxJS ~7.8、Tiptap 2、Tailwind 3、Mermaid 10 | 可复用编辑器/流程页面；NGXS 与 Angular 声明的版本组合应在实际安装/构建时核验，不能仅凭文件断言兼容 |
| 模型与流程 | [electron/package.json](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/package.json)，Electron ^36.4、TypeScript ^5.8.2、LangGraph ^0.2.63、LangChain 0.3 系列、Zod ^3.24；OpenAI/Azure/Anthropic/Bedrock/Gemini/OpenRouter/Ollama 适配器 | 属于 TS 模型编排，不是 Python 服务；默认本地/Ollama 或禁用外部生成更符合首版隐私边界 |
| 运行与锁定 | electron/ui 均声明 Node >=18.17；两目录均有 package-lock.json | 根目录并非能一次安装所有组件的完整 workspace；不能只跑根 npm install 就声称应用可用 |
| 存储 | [projects.state.ts 的 UpdateFile](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/ui/src/app/store/projects/projects.state.ts#L635-L659)与[文件写入工具](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/file-system.utility.ts#L85-L123)，本地 JSON、.metadata.json；配置用 electron-store | 适合个人离线原型；需求更新直接覆写，须新增不可变 revision/基线/变更事件 |
| 测试现状 | electron/package.json 的 test 脚本是失败占位；UI 有 Karma/Jasmine 脚本和 component spec | 不能把上游“有测试文件”等同于已经通过。财务规则/追踪的行为测试必须新增并执行 |

## 可复用能力及缺口

1. **需求调研与澄清**：实际 [create-solution-workflow/index.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/agentic/create-solution-workflow/index.ts#L1-L53)是 LangGraph：research 后并行 BRD/UIR/NFR，BRD 再到 PRD。[研究总结 prompt](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/agentic/create-solution-workflow/prompts/summarize-research.ts)要求保留信息缺口。可复用组织方式，但 Finance 需额外持久化“问题—负责人—答案—来源—是否确认”，阻止把未确认假设写成财务既定规则。
2. **PRD 与追踪**：[create-prd.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/prompts/solution/create-prd.ts#L1-L92)明确生成 `id/title/requirement/linkedBRDIds`、Screens/Personas，且要求覆盖 BRD。这是提示词要求，并非已被程序验证的全链路引用完整性。可扩展为 `REQ → PROCESS/RULE → PRD → SCREEN → UAT` 图，程序拒绝未知 ID/孤立关键需求。
3. **流程建模**：[business-process/add.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/prompts/requirement/business-process/add.ts#L1-L89)输入 BRD/PRD 与请求，输出单段流程描述；[flowchart API](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/api/visualization/flowchart.ts#L1-L67)调用模型生成 flowChartData。可复用视图，新增流程节点/边及责任角色的结构化校验，而不是仅靠自然语言/Mermaid。
4. **财务规则**：上述流程与 PRD 结构未提供币种、Decimal 精度、适用期间、金额上下界、税率/舍入、职责分离、例外处理等领域 schema。此处是新增核心，使用已确认业务政策和虚构示例；首版不提供税法或会计合规判断。
5. **原型**：上游 PRD prompt 有 Screens/Personas、UIR 文档与富文本编辑能力；本次未发现可直接复用为端到端“可点击业务原型生成器”的实现。因此 Finance 首版应明确交付轻量可点击原型（由结构化 screen 字段生成），不要把 UIR 文档冒充已运行的原型。
6. **UAT**：[test-case-workflow/index.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/agentic/test-case-workflow/index.ts#L1-L47)实现 research → generate → evaluate → 最多反馈循环。[TestCase 结构](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/agentic/test-case-workflow/types.ts#L1-L31)已有前后置条件、步骤、期望、优先级、类型；可复用生成模板。必须新增实际执行人、实际结果、证据、失败原因、版本与签字状态。[nodes.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/agentic/test-case-workflow/nodes.ts#L440-L500)模型文本匹配或迭代到限都能使 isComplete=true，异常也能结束流程；这是生成任务结束，绝非业务验收通过。
7. **变更追踪**：上游 README 的版本管理描述主要依靠用户选择可被 OneDrive/Dropbox 等同步的本地目录；实际 UpdateFile 直接写 JSON，未在该通路发现自动 Git commit/不可变审计。Finance 须自己实现 revision、修改理由、影响下游标记 stale、基线审批失效和重新 UAT；源码 Git PR 与业务文档变更记录是两类机制。

## 数据外传路径与防护边界（已核实）

- **模型**：[OpenAI provider](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/services/llm/providers/openai.ts#L15-L119)将消息发往配置的客户端端点；其他外部 provider 同类。Ollama 默认 `http://localhost:11434`，但 [ollama provider](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/services/llm/langchain-providers/ollama.ts#L13-L52)允许 baseUrl/env 指向其他地址，因此选择 Ollama 本身不保证不外传。
- **Langfuse**：[observability.manager.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/services/observability/observability.manager.ts#L45-L115)由 analyticsEnabled 与 env/custom 配置共同启用。详细 traces 标志存在，但 [create-solution nodes](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/agentic/create-solution-workflow/nodes.ts#L225-L237)仍向 trace span 写入 requirementTypePrompt 与生成结果；仅关闭 detailed traces 不足以作“无业务文本”保证，应禁用整个遥测出口。
- **PostHog**：[posthog-analytics.manager.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/ui/src/app/services/analytics/managers/posthog-analytics.manager.ts#L1-L205)包含用户 ID/用户名、provider、事件、IP，虽有开关仍属外部出口。
- **Sentry**：[ui/src/main.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/ui/src/main.ts#L1-L37)在 ENABLE_SENTRY 时启用 replay，maskAllText=false、blockAllMedia=false、错误回放采样 1.0；仓库提交的 environment 文件当前均为关闭状态。不能在财务分支直接开启这些回放配置。
- **MCP/集成**：[mcp-connection.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/mcp/mcp-connection.ts#L48-L140)可连接 stdio/WebSocket/SSE，工具调用发送 args；Jira/ADO handlers 也能外发。个人 MVP 默认禁用；未来每次外发只允许已脱敏、明确选定的信息。
- **日志**：[flowchart.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/api/visualization/flowchart.ts#L17-L51)会打印 llmConfig 与模型完整回复，[projects.state.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/ui/src/app/store/projects/projects.state.ts#L635-L652)会 debug 完整内容。财务工作流不得继承这种日志；只记内部 ID、状态和校验错误。
- **更新与发布**：[app-update-handler.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/handlers/app-update-handler.ts#L1-L83)支持检查/下载安装更新，electron 包配置仍指向 presidio-oss/specif-ai。派生产品须移除/替换该发布源，不能让个人版被上游安装包覆盖。
- **Guardrails**：[guardrails/index.ts](https://github.com/presidio-oss/specif-ai/blob/a084a227b0d65c009544d8af575a7a4f5c37b4be/electron/guardrails/index.ts)有注入/泄漏/PII/secret 检查，但启发式注入 guard 被注释，且只校验 user message；这不能代替数据分级、无网络默认和出口控制。本次未执行第三方库，未证明所有调用都真正脱敏。

## 推荐的增量验收（工程建议）

首个闭环使用纯虚构“费用报销/付款审批”案例；持久化需求与澄清、可校验流程图、金额/期间/审批规则、关联 PRD 与屏幕、UAT 用例与执行结果。外部模型默认不启用，先提供确定性草稿模板与人工确认；若接入模型，仅允许明确选择的合成/脱敏输入，生成结果保持 draft。

验证应覆盖：未知关联 ID 被拒绝；规则边界金额与精度；存在未答问题时禁止基线；需求或规则变化后下游 stale、已有验收失效；失败/未执行 UAT 禁止通过；重启后数据与版本保持；原型可点击且不加载 CDN；默认路径无外部网络调用。只有实际跑出的命令与结果才能写进最终测试证据。

后续才考虑复用完整 Electron 壳、多模型、MCP、Jira/ADO、自动生成原型和多人审批。模型生成速度和文案质量不能替代财务规则正确性与签字证据。
