"""从同一个版本生成 PRD、UAT、流程和离线原型，避免文档之间失去关联。"""
import csv
import html
import io
import json
import re
from zipfile import ZipFile, ZIP_DEFLATED

from .core import GROUPS, edges, validate


def prd_markdown(state):
    data = state["data"]
    lines = [f"# {data['title']}", "", f"版本：{state['version']} · SHA-256：{state['digest']}", "", "状态：" + ("当前版本已人工签署" if state.get("signed") else "待复核草案，未签署"), "", "本文由已录入的结构化信息编译；不补写未确认的财务政策。", ""]
    labels = {"sources": "调研来源", "requirements": "需求与目标", "questions": "需求澄清", "processes": "业务流程", "rules": "财务规则", "prd": "产品需求", "screens": "页面与交互", "uats": "UAT 验收"}
    for group in GROUPS:
        lines += [f"## {labels[group]}", ""]
        for node in data[group]:
            lines += [f"### {node['id']} · {node.get('title', node.get('question', ''))}", ""]
            # JSON 代码块明确呈现原始口径和 ID，避免 Markdown 被误认为已审核结论。
            body = json.dumps(node, ensure_ascii=False, indent=2)
            fence = "`" * max(3, max((len(part) for part in re.findall(r'`+', body)), default=0) + 1)
            lines += [fence + "json", body, fence, ""]
    return "\n".join(lines)


def csv_text(rows):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    for row in rows:
        # 防止导出文本被 Excel 解释成公式。
        writer.writerow(["'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) or str(v).startswith(("\t", "\r", "\n")) else str(v) for v in row])
    return "\ufeff" + out.getvalue()


def trace_rows(data):
    kinds = {node["id"]: group for group in GROUPS for node in data[group]}
    return [["来源ID", "来源类型", "目标ID", "目标类型"], *[[source, kinds[source], target, kinds[target]] for source, target in edges(data)]]


def flowchart(data):
    lines = ["flowchart TD"]
    for flow in data["processes"]:
        lines.append(f"  subgraph {flow['id']}[\"{html.escape(flow['title'], quote=True)}\"]")
        for step in flow["steps"]:
            label = html.escape(step["role"] + "：" + step["action"], quote=True).replace("\n", " ").replace("\r", " ")
            lines.append(f"    {step['id']}[\"{label}\"]")
            lines.extend(f"    {step['id']} --> {target}" for target in step["next"])
        lines.append("  end")
    return "\n".join(lines) + "\n"


def prototype(state):
    data = state["data"]
    escape = html.escape
    nav = " ".join(f'<a href="#{s["id"]}">{escape(s["title"])}</a>' for s in data["screens"])
    pages = []
    for screen in data["screens"]:
        fields = "".join(f'<label>{escape(f)}<input placeholder="合成示例，仅用于交互评审"></label>' for f in screen["fields"])
        actions = "".join(f'<a class="button" href="#{a["target"]}">{escape(a["label"])}</a>' for a in screen["actions"])
        pages.append(f'<section class="screen" id="{screen["id"]}"><small>{screen["id"]} · {escape(", ".join(screen["prd_ids"]))}</small><h2>{escape(screen["title"])}</h2>{fields}<div>{actions}</div></section>')
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; form-action 'none'; base-uri 'none'">
<title>{escape(data['title'])} · 可点击原型</title><style>
body{{background:#f3f5f8;color:#202b3c;font:16px system-ui;margin:0;padding:32px}}header,main{{max-width:820px;margin:auto}}nav{{padding:20px 0}}a{{color:#174e77;margin-right:16px}}.screen{{display:none;background:white;padding:30px;border:1px solid #dae2e9;border-radius:16px}}.screen:target{{display:block}}body:not(:has(.screen:target)) .screen:first-child{{display:block}}label{{display:block;margin:18px 0}}input{{display:block;padding:12px;width:90%;border:1px solid #bac8d3;border-radius:6px;margin-top:8px}}.button{{display:inline-block;padding:12px 18px;border-radius:8px;background:#174e77;color:white;text-decoration:none;margin-top:20px}}small{{color:#5f7185}}
</style></head><body><header><small>FINANCE PRODUCT AGENT · v{state['version']}</small><h1>{escape(data['title'])}</h1><p>交互原型 · 仅展示页面跳转，金额路由与职责分离尚需研发实现和真实 UAT。输入留在当前浏览器，不提交。</p><nav>{nav}</nav></header><main>{''.join(pages)}</main></body></html>'''


def export_bundle(state, history):
    validate(state["data"])
    data = state["data"]
    # 历史只追加；截断到导出版本，防止并发保存的新内容混入旧版本交付包。
    history = [revision for revision in history if revision["version"] <= state["version"]]
    rows = [["UAT_ID", "标题", "需求ID", "规则ID", "页面ID", "输入", "预期", "实际", "状态", "执行人", "证据", "版本"]]
    rows.extend([c["id"], c["title"], ",".join(c["requirement_ids"]), ",".join(c["rule_ids"]), ",".join(c["screen_ids"]), json.dumps(c["input"], ensure_ascii=False), c["expected"], c["actual"], c["status"], c["executor"], c["evidence"], state["version"]] for c in data["uats"])
    files = {
        "PRD.md": prd_markdown(state), "process.mmd": flowchart(data),
        "UAT.csv": csv_text(rows), "traceability.csv": csv_text(trace_rows(data)),
        "prototype.html": prototype(state), "workspace.json": json.dumps(data, ensure_ascii=False, indent=2),
        "revision-evidence.json": json.dumps({"version": state["version"], "digest": state["digest"], "signers": state.get("signers", []), "blockers": state["blockers"], "history": history}, ensure_ascii=False, indent=2),
    }
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content.encode("utf-8"))
    return buffer.getvalue()
