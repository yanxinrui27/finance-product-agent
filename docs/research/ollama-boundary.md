# 本地模型的云转发边界

核验日期：2026-10-21。固定回环地址只能限制工作台的直接目的地，不能单独证明本地推理。[Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx#L142-L162)明确区分本地与云模型，并提供 `disable_ollama_cloud` / `OLLAMA_NO_CLOUD=1`。

[实际服务路由](https://github.com/ollama/ollama/blob/main/server/routes.go#L2483-L2491)提供 `/api/status`，返回 cloud.disabled；[API 类型](https://github.com/ollama/ollama/blob/main/api/types.go#L743-L765)的 ShowResponse 包含 remote_host/remote_model、details 和 model_info。

本项目策略：先查询不含业务内容的状态与模型信息；仅接受云功能已禁用、无 remote 元数据的本地 GGUF 权重，再发送 prompt。未知/失败一律关闭调用。不以模型名称是否带 cloud 判断，因为远程模型可以改名。服务配置须由用户作用到 Ollama 进程并重启；本工作台不改其配置。元数据检查依赖可信本机 Ollama；恶意本地代理和有权限修改该服务的本机进程不在首版威胁边界内。未验证真实 Ollama 安装或实际模型生成。
