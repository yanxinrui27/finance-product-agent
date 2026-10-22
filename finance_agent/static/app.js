"use strict";
const $ = (s) => document.querySelector(s);
const csrf = $('meta[name="csrf"]').content;
const sections = [
  ["overview", "项目概览", "掌握需求、规则与验收的整体状态。"],
  ["sources", "调研来源", "保留财务原始诉求和来源；真实材料只在本机编辑。"],
  ["requirements", "需求与目标", "写清问题、责任人与可衡量的成功标准。"],
  [
    "questions",
    "需求澄清",
    "没有确认的答案会阻止签署；请勿用猜测填补财务政策。",
  ],
  ["processes", "业务流程", "明确角色、输入、动作、输出及异常分支。"],
  ["rules", "财务规则", "记录规则依据、金额口径、适用期间与职责分离。"],
  ["prd", "PRD 产品需求", "将业务需求关联到流程、规则和验收标准。"],
  ["screens", "页面与原型", "用结构化页面生成可点击原型，供需求评审。"],
  ["uats", "UAT 验收", "配置试算与实际系统验收分开记录；通过必须填写证据。"],
  ["changes", "变更与追踪", "查看来源、影响范围、版本差异和人工签署。"],
  [
    "ai",
    "AI 草案助手",
    "使用本地模型辅助澄清、PRD 与 UAT；输出仅作待复核建议。",
  ],
];
const labels = {
  title: "标题",
  notes: "访谈记录 / 来源材料",
  description: "需求说明",
  owner: "责任人",
  metric: "成功指标",
  source_ids: "来源 ID",
  question: "澄清问题",
  answer: "已确认答案",
  requirement_id: "所属需求",
  requirement_ids: "关联需求",
  rule_ids: "关联规则",
  process_ids: "关联流程",
  prd_ids: "关联 PRD",
  screen_ids: "关联页面",
  basis: "制度依据 / 来源",
  effective_from: "生效日期",
  effective_to: "失效日期",
  currency: "币种",
  amount_basis: "金额口径",
  rounding: "舍入规则",
  segregation: "职责分离",
  exception: "异常处理",
  operator: "比较符",
  threshold: "金额阈值",
  when_true: "条件成立时",
  when_false: "条件不成立时",
  acceptance: "验收标准",
  expected: "预期结果",
  actual: "实际结果",
  status: "执行状态",
  executor: "执行人",
  evidence: "验收证据 / 本地记录位置",
};
const refGroups = {
  source_ids: "sources",
  requirement_id: "requirements",
  requirement_ids: "requirements",
  rule_ids: "rules",
  process_ids: "processes",
  prd_ids: "prd",
  screen_ids: "screens",
};
let state = { version: 0, data: null },
  working = null,
  tab = "overview",
  dirty = false,
  editSequence = 0,
  saving = false,
  localModel = "qwen3:8b";
const el = (tag, content, cls) => {
  const e = document.createElement(tag);
  if (content !== undefined) e.textContent = content;
  if (cls) e.className = cls;
  return e;
};
function message(value, error = false) {
  const box = $("#message");
  box.textContent = value;
  box.className = error ? "error" : "";
  box.hidden = false;
}
async function api(path, body) {
  const options =
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-FPA-CSRF": csrf },
          body: JSON.stringify(body),
        };
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "操作失败");
  return value;
}
function button(label, action, cls = "") {
  const b = el("button", label, cls);
  b.type = "button";
  b.addEventListener("click", () =>
    Promise.resolve()
      .then(action)
      .catch((e) => message(e.message, true)),
  );
  return b;
}
function mark() {
  editSequence++;
  dirty = true;
  $("#version").textContent = `v${state.version} · 有未保存修改`;
}
function field(
  parent,
  label,
  value,
  onchange,
  {
    area = false,
    options = null,
    multiple = false,
    wide = false,
    type = "text",
    workspace = true,
  } = {},
) {
  const wrap = el("label", label, wide ? "wide" : "");
  let input;
  if (options) {
    input = el("select");
    input.multiple = multiple;
    if (multiple) input.className = "select-many";
    for (const option of options) {
      const [v, t] = Array.isArray(option) ? option : [option, option];
      const o = el("option", t);
      o.value = v;
      o.selected = multiple ? value.includes(v) : value === v;
      input.append(o);
    }
  } else {
    input = el(area ? "textarea" : "input");
    if (!area) input.type = type;
    input.value = value ?? "";
  }
  input.addEventListener("change", () => {
    onchange(
      options && multiple
        ? [...input.selectedOptions].map((o) => o.value)
        : input.value,
    );
    if (workspace) mark();
  });
  wrap.append(input);
  parent.append(wrap);
  return input;
}
function card(title) {
  const c = el("section", undefined, "card");
  if (title) c.append(el("h2", title));
  return c;
}
function link(label, url) {
  const a = el("a", label, "button");
  a.href = url;
  return a;
}
function first(group) {
  return working[group][0]?.id;
}
function freshId(prefix) {
  let n = 1;
  const ids = new Set(
    Object.values(working)
      .filter(Array.isArray)
      .flat()
      .map((x) => x.id),
  );
  for (const p of working.processes) for (const s of p.steps) ids.add(s.id);
  while (ids.has(`${prefix}-${n}`)) n++;
  return `${prefix}-${n}`;
}
function newItem(group) {
  const req = first("requirements"),
    rule = first("rules"),
    prd = first("prd"),
    screen = first("screens"),
    flow = first("processes"),
    source = first("sources");
  const ids = (x) => (x ? [x] : []);
  const samples = {
    sources: () => ({ id: freshId("SRC"), title: "新调研来源", notes: "" }),
    requirements: () => ({
      id: freshId("REQ"),
      title: "新需求",
      description: "",
      source_ids: ids(source),
      owner: "",
      metric: "",
    }),
    questions: () => ({
      id: freshId("Q"),
      requirement_id: req || "",
      question: "待确认的问题",
      answer: "",
    }),
    processes: () => ({
      id: freshId("FLOW"),
      title: "新业务流程",
      requirement_ids: ids(req),
      rule_ids: ids(rule),
      steps: [
        {
          id: freshId("STEP"),
          role: "",
          input: "",
          action: "",
          output: "",
          next: [],
        },
      ],
    }),
    rules: () => ({
      id: freshId("RULE"),
      title: "待确认财务规则",
      requirement_ids: ids(req),
      basis: "",
      owner: "",
      effective_from: "",
      effective_to: "",
      currency: "CNY",
      amount_basis: "",
      rounding: "ROUND_HALF_UP_2",
      segregation: "",
      exception: "",
      operator: ">",
      threshold: "0.00",
      when_true: "",
      when_false: "",
    }),
    prd: () => ({
      id: freshId("PRD"),
      title: "新产品需求",
      requirement_ids: ids(req),
      process_ids: ids(flow),
      rule_ids: ids(rule),
      description: "",
      acceptance: "",
    }),
    screens: () => ({
      id: freshId("UI"),
      title: "新页面",
      prd_ids: ids(prd),
      fields: [],
      actions: [],
    }),
    uats: () => ({
      id: freshId("UAT"),
      title: "新验收场景",
      requirement_ids: ids(req),
      rule_ids: ids(rule),
      screen_ids: ids(screen),
      input: {
        amount: "",
        currency: "CNY",
        date: new Date().toISOString().slice(0, 10),
      },
      expected: "",
      actual: "",
      status: "pending",
      executor: "",
      evidence: "",
    }),
  };
  working[group].push(samples[group]());
  mark();
  render();
}
function editNode(group, node) {
  const c = card();
  const head = el("div", undefined, "card-title");
  const name = el("div");
  name.append(el("small", node.id), el("h2", node.title || node.question));
  head.append(
    name,
    button(
      "移除条目",
      () => {
        if (confirm("移除将保留在历史版本中。关联条目需同时调整，才可保存。")) {
          working[group] = working[group].filter((n) => n !== node);
          mark();
          render();
        }
      },
      "small danger",
    ),
  );
  c.append(head);
  const fields = el("div", undefined, "fields");
  c.append(fields);
  for (const [key, value] of Object.entries(node)) {
    if (["id", "steps", "fields", "actions", "input"].includes(key)) continue;
    let options = null;
    const reference = refGroups[key];
    if (reference)
      options = working[reference].map((n) => [
        n.id,
        `${n.id} · ${n.title || n.question}`,
      ]);
    else if (key === "operator") options = [">", ">=", "<", "<=", "=="];
    else if (key === "rounding") options = ["ROUND_HALF_UP_2"];
    else if (key === "status")
      options = [
        ["pending", "未执行"],
        ["passed", "通过"],
        ["failed", "失败"],
        ["blocked", "受阻"],
      ];
    field(fields, labels[key] || key, value, (v) => (node[key] = v), {
      options,
      multiple: Array.isArray(value),
      area: [
        "notes",
        "description",
        "question",
        "answer",
        "basis",
        "segregation",
        "exception",
        "acceptance",
        "expected",
        "actual",
        "evidence",
      ].includes(key),
      wide: [
        "notes",
        "description",
        "question",
        "answer",
        "acceptance",
      ].includes(key),
      type: key.startsWith("effective_") ? "date" : "text",
    });
  }
  if (group === "processes") {
    c.append(el("h3", "流程步骤"));
    for (const step of node.steps) {
      const box = el("div", undefined, "subcard");
      box.append(el("small", step.id));
      const fs = el("div", undefined, "fields");
      box.append(fs);
      for (const [key, label] of [
        ["role", "执行角色"],
        ["input", "输入"],
        ["action", "动作 / 分支条件"],
        ["output", "输出"],
      ])
        field(fs, label, step[key], (v) => (step[key] = v));
      field(
        fs,
        "后续步骤（可多选；无后续代表结束）",
        step.next,
        (v) => (step.next = v),
        {
          options: node.steps.map((s) => [s.id, s.id + " · " + s.action]),
          multiple: true,
          wide: true,
        },
      );
      c.append(box);
    }
    c.append(
      button(
        "添加步骤",
        () => {
          node.steps.push({
            id: freshId("STEP"),
            role: "",
            input: "",
            action: "",
            output: "",
            next: [],
          });
          mark();
          render();
        },
        "small",
      ),
    );
  }
  if (group === "screens") {
    field(
      fields,
      "页面字段（每行一个）",
      node.fields.join("\n"),
      (v) => (node.fields = v.split("\n").filter((x) => x.trim())),
      { area: true, wide: true },
    );
    for (const a of node.actions) {
      const row = el("div", undefined, "row");
      field(row, "按钮文字", a.label, (v) => (a.label = v));
      field(row, "跳转页面", a.target, (v) => (a.target = v), {
        options: working.screens.map((s) => [s.id, s.id + " · " + s.title]),
      });
      c.append(row);
    }
    c.append(
      button(
        "添加页面跳转",
        () => {
          node.actions.push({ label: "下一步", target: node.id });
          mark();
          render();
        },
        "small",
      ),
    );
  }
  if (group === "uats") {
    const box = el("div", undefined, "subcard");
    box.append(el("h3", "规则试算输入"));
    const fs = el("div", undefined, "fields");
    for (const [key, label] of [
      ["amount", "金额（十进制文本）"],
      ["currency", "币种"],
      ["date", "业务日期"],
    ])
      field(fs, label, node.input[key], (v) => (node.input[key] = v), {
        type: key === "date" ? "date" : "text",
      });
    box.append(fs);
    box.append(
      button(
        "使用已保存规则试算",
        async () => {
          if (dirty) throw new Error("请先保存新版本，再试算规则");
          const results = [];
          for (const id of node.rule_ids) {
            const r = await api("/api/evaluate", {
              version: state.version,
              rule_id: id,
              ...node.input,
            });
            results.push(`${id}：${r.result}`);
          }
          message(
            results.join("；") +
              "。试算不自动将 UAT 标为通过；请在实际系统执行并登记证据。",
          );
        },
        "small",
      ),
    );
    c.append(box);
  }
  return c;
}
function overview(container) {
  if (!working) {
    const hero = card();
    hero.classList.add("hero");
    const body = el("div");
    body.append(
      el("span", "从一条财务需求开始", "eyebrow"),
      el("h2", "把需求说明，变成可交付的闭环"),
      el(
        "p",
        "先澄清业务口径，再连接流程、规则、页面和验收。你确认事实，工作台维护关联与版本。",
      ),
    );
    body.append(
      button(
        "载入合成演示",
        async () => {
          working = await api("/api/example");
          mark();
          render();
        },
        "primary",
      ),
    );
    hero.append(body, el("div", "01", "number"));
    container.append(hero);
    const c = card("新建自己的工作区");
    const form = { title: "", brief: "", owner: "产品经理" };
    const fs = el("div", undefined, "fields");
    field(fs, "项目名称", "", (v) => (form.title = v));
    field(fs, "业务负责人", form.owner, (v) => (form.owner = v));
    field(fs, "财务原始诉求", "", (v) => (form.brief = v), {
      area: true,
      wide: true,
    });
    c.append(
      fs,
      el("p", "新项目默认标记为敏感本地内容。未确认规则保持空白。", "hint"),
      button(
        "建立需求澄清草案",
        async () => {
          working = await api("/api/new", form);
          mark();
          render();
        },
        "primary",
      ),
    );
    container.append(c);
    return;
  }
  const hero = card();
  hero.classList.add("hero");
  const b = el("div");
  b.append(
    el("span", "REQUIREMENTS → ACCEPTANCE", "eyebrow"),
    el("h2", working.title),
    el(
      "p",
      "需求的价值，落在每一个能被验证的细节。所有交付物来自同一份结构化工作区，每次修改都有原因和影响记录。",
    ),
  );
  hero.append(
    b,
    el("div", String(working.requirements.length).padStart(2, "0"), "number"),
  );
  container.append(hero);
  const stats = el("div", undefined, "stats");
  for (const [label, value, note] of [
    ["需求", working.requirements.length, "保留调研来源"],
    [
      "待澄清",
      working.questions.filter((q) => !q.answer.trim()).length,
      "签署前必须解决",
    ],
    ["财务规则", working.rules.length, "口径、依据与期间"],
    [
      "UAT 通过",
      `${working.uats.filter((c) => c.status === "passed").length}/${working.uats.length}`,
      "必须有实际执行证据",
    ],
  ]) {
    const c = el("div", undefined, "stat");
    c.append(el("span", label), el("strong", String(value)), el("small", note));
    stats.append(c);
  }
  container.append(stats);
  const grid = el("div", undefined, "grid"),
    settings = card("工作区设置"),
    fs = el("div", undefined, "fields");
  field(fs, "项目名称", working.title, (v) => (working.title = v), {
    wide: true,
  });
  field(
    fs,
    "数据分类",
    working.classification,
    (v) => (working.classification = v),
    {
      options: [
        ["local_sensitive", "敏感内容，仅本机"],
        ["synthetic", "完全合成数据"],
        ["sanitized", "已人工脱敏数据"],
      ],
      wide: true,
    },
  );
  settings.append(
    fs,
    el(
      "p",
      "分类是你的人工声明；程序不能识别所有敏感信息。只有合成或已脱敏内容可进入本地模型。",
      "hint",
    ),
  );
  const gate = card("当前已保存版本的验收门禁");
  if (state.data) {
    gate.append(
      el(
        "p",
        state.ready
          ? "当前版本已完成记录与签署，可供上线评审。"
          : "尚未完成签署，不可作为验收完成依据。",
        state.ready ? "ok" : "pending",
      ),
    );
    const list = el("ul", undefined, "blockers");
    for (const blocker of state.blockers) list.append(el("li", blocker));
    gate.append(list);
  } else gate.append(el("p", "尚无保存版本。请填写修改原因并保存。", "hint"));
  grid.append(settings, gate);
  container.append(grid);
}
async function changes(container) {
  const gate = card("人工基线签署");
  gate.append(
    el(
      "p",
      "签署只对当前版本有效。任何新版本都会使签署失效；业务内容变化还会重置全部 UAT 记录。签署不执行合并或部署。",
      "hint",
    ),
  );
  gate.append(
    button(
      "签署当前保存版本",
      async () => {
        if (dirty) throw new Error("请先保存未提交修改");
        state = {
          ...(await api("/api/approve", {
            version: state.version,
            actor: $("#actor").value,
          })),
          local_ai_enabled: state.local_ai_enabled,
        };
        render();
        message("当前版本已签署；请独立组织上线评审。");
      },
      "primary",
    ),
  );
  for (const s of state.signers || [])
    gate.append(el("p", `${s.actor} · ${s.created}`, "ok"));
  container.append(gate);
  const history = await api("/api/history");
  if (tab !== "changes") return;
  for (const revision of history) {
    const c = card(`v${revision.version} · ${revision.reason}`);
    c.append(
      el("p", `${revision.actor} · ${revision.created}`, "hint"),
      el(
        "pre",
        `SHA-256 ${revision.digest}\n影响范围：${revision.impact.join("、")}`,
      ),
    );
    const details = el("details");
    details.append(
      el("summary", `查看 ${revision.changes.length} 项变更前后差异`),
      el("pre", JSON.stringify(revision.changes, null, 2)),
    );
    c.append(details);
    container.append(c);
  }
  if (working) {
    const c = card("当前编辑内容的追踪关联"),
      table = el("table");
    const header = el("tr");
    header.append(el("th", "上游"), el("th", "下游"));
    table.append(header);
    for (const [group, ref] of [
      ["requirements", "source_ids"],
      ["questions", "requirement_id"],
      ["processes", "requirement_ids"],
      ["processes", "rule_ids"],
      ["rules", "requirement_ids"],
      ["prd", "requirement_ids"],
      ["prd", "process_ids"],
      ["prd", "rule_ids"],
      ["screens", "prd_ids"],
      ["uats", "requirement_ids"],
      ["uats", "rule_ids"],
      ["uats", "screen_ids"],
    ])
      for (const node of working[group])
        for (const source of Array.isArray(node[ref])
          ? node[ref]
          : [node[ref]]) {
          const row = el("tr");
          row.append(el("td", source), el("td", node.id));
          table.append(row);
        }
    c.append(table);
    container.append(c);
  }
}
function aiPage(container) {
  const c = card("本地 AI · 只生成待复核建议");
  c.append(
    el(
      "p",
      state.local_ai_enabled
        ? "服务允许本地模型调用。请确认当前保存版本完全合成或已经脱敏。"
        : "当前未启用模型调用。可继续使用全部编辑、导出、规则和版本功能。需要 AI 时，停止服务并加 --enable-local-ai 重新启动。",
      "hint",
    ),
  );
  field(
    c,
    "已安装的 Ollama 模型名称（示例名称不保证已安装）",
    localModel,
    (v) => (localModel = v),
    { workspace: false },
  );
  const output = el("pre", "草案将显示在这里，正式条目不会被自动修改。");
  c.append(
    button(
      "请求本地模型生成草案",
      async () => {
        if (dirty) throw new Error("请先保存当前内容");
        message("本地模型正在生成，最长等待45秒。");
        const result = await api("/api/draft", {
          version: state.version,
          model: localModel,
        });
        output.textContent = JSON.stringify(result, null, 2);
        message("草案已返回，需人工核实后逐项录入；未改动正式条目。");
      },
      "primary",
    ),
    output,
  );
  container.append(c);
}
function advanced(container) {
  if (!working) return;
  const d = el("details");
  d.append(el("summary", "高级：查看 / 导入完整工作区 JSON"));
  const edit = el("textarea", undefined, "json-editor");
  edit.value = JSON.stringify(working, null, 2);
  edit.setAttribute("aria-label", "工作区 JSON");
  d.append(
    edit,
    button(
      "将 JSON 载入编辑区",
      async () => {
        const imported = JSON.parse(edit.value);
        await api("/api/validate", { data: imported });
        working = imported;
        mark();
        render();
        message("已载入编辑区；保存时会校验结构和关联。");
      },
      "small",
    ),
  );
  container.append(d);
}
function render() {
  const selected = sections.find((x) => x[0] === tab);
  $("#page-title").textContent = selected[1];
  $("#subtitle").textContent = selected[2];
  $("#step-label").textContent =
    `WORKSPACE / ${String(sections.indexOf(selected) + 1).padStart(2, "0")}`;
  $("#project-name").textContent =
    working?.title || "从财务问题，到可验收的产品";
  $("#version").textContent =
    `v${state.version}${dirty ? " · 有未保存修改" : state.signed ? " · 已签署" : " · 待复核"}`;
  $("#nav").replaceChildren(
    ...sections.map(([key, label], i) => {
      const b = button("", () => {
        tab = key;
        render();
      });
      b.append(
        el("span", String(i + 1).padStart(2, "0")),
        document.createTextNode(label),
      );
      b.classList.toggle("active", key === tab);
      return b;
    }),
  );
  const add = $("#add-item");
  add.hidden =
    !working ||
    ![
      "sources",
      "requirements",
      "questions",
      "processes",
      "rules",
      "prd",
      "screens",
      "uats",
    ].includes(tab);
  add.onclick = () => newItem(tab);
  const container = $("#content");
  container.replaceChildren();
  if (tab === "overview") overview(container);
  else if (!working) {
    container.append(
      el("div", "请先在项目概览建立工作区或载入合成演示。", "empty"),
    );
  } else if (tab === "changes")
    changes(container).catch((e) => message(e.message, true));
  else if (tab === "ai") aiPage(container);
  else {
    if (tab === "screens") {
      const bar = el("div", undefined, "toolbar");
      const a = link("打开已保存版本的可点击原型", "/prototype");
      a.target = "_blank";
      a.rel = "noopener";
      bar.append(a);
      container.append(bar);
    }
    if (!working[tab].length)
      container.append(
        el("p", "还没有条目。点击“添加条目”开始建模。", "empty"),
      );
    for (const node of working[tab]) container.append(editNode(tab, node));
  }
  advanced(container);
}
$("#reload").addEventListener("click", async () => {
  if (saving) return message("正在保存，请等待完成后重新载入。", true);
  if (dirty && !confirm("重新载入会放弃当前未保存编辑，是否继续？")) return;
  try {
    state = await api("/api/state");
    working = structuredClone(state.data);
    dirty = false;
    render();
    message("已载入当前保存版本。");
  } catch (e) {
    message(e.message, true);
  }
});
$("#save").addEventListener("click", async () => {
  if (saving) return;
  const sequence = editSequence;
  try {
    if (!working) throw new Error("请先建立工作区");
    saving = true;
    $("#save").disabled = true;
    const sent = structuredClone(working);
    const result = await api("/api/save", {
      data: sent,
      version: state.version,
      actor: $("#actor").value,
      reason: $("#reason").value,
    });
    state = { ...result, local_ai_enabled: state.local_ai_enabled };
    // 请求期间的新编辑保留为草案，不能被较早的保存响应覆盖。
    if (sequence === editSequence) {
      working = structuredClone(state.data);
      dirty = false;
      $("#reason").value = "";
    } else {
      // 保留新业务编辑，但服务端失效的验收证据必须同步清除，防止旧 passed 被再次保存。
      const resultFields = ["status", "actual", "executor", "evidence"];
      for (const saved of state.data.uats) {
        const submitted = sent.uats.find((item) => item.id === saved.id);
        const edited = working.uats.find((item) => item.id === saved.id);
        if (
          submitted &&
          edited &&
          resultFields.some((key) => submitted[key] !== saved[key])
        ) {
          for (const key of resultFields) edited[key] = saved[key];
        }
      }
    }
    render();
    message(
      dirty
        ? `已保存 v${state.version}；新业务编辑已保留，仍需再次保存。失效的 UAT 证据已同步清除，请重新执行。`
        : `已保存 v${state.version}。业务内容变化时，旧 UAT 结果会重置，请重新执行。`,
    );
  } catch (e) {
    message(e.message, true);
  } finally {
    saving = false;
    $("#save").disabled = false;
  }
});
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
api("/api/state")
  .then((value) => {
    state = value;
    working = structuredClone(state.data);
    render();
  })
  .catch((e) => message(e.message, true));
