# 上游来源与第三方声明

Finance Product Agent 是独立下游衍生项目，不属于 Presidio 官方产品。

## 实际复制与复用

- 来源仓库：https://github.com/presidio-oss/specif-ai
- 固定 commit：`a084a227b0d65c009544d8af575a7a4f5c37b4be`。
- 版权所有：`Copyright (c) Presidio, Inc. and affiliates.`
- 根 LICENSE 全文原样保留在 [vendor/specif-ai/LICENSE](vendor/specif-ai/LICENSE)。其中含 MIT 授权正文及品牌替换条款。
- `vendor/specif-ai/brd-definition.txt`：从 `electron/prompts/context/brd.ts` 的 `BRD_DEFINITION_CONTEXT` 提取，内容不变，仅去除 TS 导出包装并追加换行。
- `vendor/specif-ai/bp-definition.txt`：同上，来自 `bp.ts` 的 `BP_DEFINITION_CONTEXT`。
- `vendor/specif-ai/prd-definition.txt`：同上，来自 `prd.ts` 的 `PRD_DEFINITION_CONTEXT`。
- `finance_agent/drafts.py::build_prompt` 在每次本地 AI 草案请求中加载三份定义。其余 Python/网页/测试是本项目新增实现，未移植上游 Electron/Angular/LangGraph 运行时。

## 品牌与许可证边界

没有复制上游图标、logo、品牌图、安装包配置或自动更新地址。上游名称仅用于来源声明。上游 electron/package.json 的 ISC 标签与根 LICENSE 不一致，本次未依赖该标签重许可材料。新增代码用根 LICENSE；vendor 文件保留上游许可。这里是基于实际文件的实施记录，不是全依赖法律合规或漏洞审计。
