// 使用真实网页脚本与延迟响应，回归保存竞态、模型设置及失败导入的数据保护。
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");

class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.events = {};
    this.value = "";
  }
  append(...nodes) {
    this.children.push(...nodes);
  }
  addEventListener(name, callback) {
    this.events[name] = callback;
  }
  setAttribute() {}
}
function find(root, tag) {
  if (root.tag === tag) return root;
  for (const child of root.children || []) {
    const result = find(child, tag);
    if (result) return result;
  }
}
const elements = {};
const get = (selector) =>
  (elements[selector] ??= Object.assign(new Element("fixed"), {
    value: "测试原因",
    content: "token",
  }));
const original = JSON.parse(fs.readFileSync("examples/demo.json", "utf8"));
let release;
let savedReply = original;
const context = {
  document: { querySelector: get, createElement: (tag) => new Element(tag) },
  window: { addEventListener() {} },
  structuredClone,
  fetch: async (path) => {
    if (path === "/api/state")
      return {
        ok: true,
        json: async () => ({ version: 1, data: structuredClone(original) }),
      };
    if (path === "/api/validate")
      return { ok: false, json: async () => ({ error: "结构无效" }) };
    return new Promise(
      (resolve) =>
        (release = () =>
          resolve({
            ok: true,
            json: async () => ({
              version: 2,
              data: structuredClone(savedReply),
            }),
          })),
    );
  },
};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync("finance_agent/static/app.js", "utf8"),
  context,
);
vm.runInContext("render=()=>{};", context);

(async () => {
  await new Promise((resolve) => setImmediate(resolve));
  const pending = get("#save").events.click();
  vm.runInContext('working.title="保存期间的新编辑";mark();', context);
  release();
  await pending;
  assert.equal(vm.runInContext("working.title", context), "保存期间的新编辑");
  assert.equal(vm.runInContext("dirty", context), true);
  console.log("PASS: 保存响应保留在途新编辑");

  context.nextWorkspace = structuredClone(original);
  context.nextWorkspace.rules[0].threshold = "9000.00";
  for (const uat of context.nextWorkspace.uats)
    Object.assign(uat, {
      status: "passed",
      actual: uat.expected,
      executor: "旧执行人",
      evidence: "旧证据",
    });
  savedReply = structuredClone(context.nextWorkspace);
  for (const uat of savedReply.uats)
    Object.assign(uat, {
      status: "pending",
      actual: "",
      executor: "",
      evidence: "",
    });
  vm.runInContext("working=nextWorkspace;mark();", context);
  const secondSave = get("#save").events.click();
  vm.runInContext('working.uats[0].executor="保存期间的编辑";mark();', context);
  release();
  await secondSave;
  assert.equal(
    vm.runInContext(
      "working.uats.every(c=>c.status==='pending'&&!c.evidence)",
      context,
    ),
    true,
  );
  console.log("PASS: 在途编辑不能恢复服务端已失效的 UAT");
  vm.runInContext('working.title="保存期间的新编辑";', context);

  vm.runInContext("dirty=false;", context);
  context.aiContainer = new Element("div");
  vm.runInContext("aiPage(aiContainer);", context);
  const modelInput = find(context.aiContainer, "input");
  modelInput.value = "my-installed-model:local";
  modelInput.events.change();
  assert.equal(vm.runInContext("dirty", context), false);
  context.aiContainer = new Element("div");
  vm.runInContext("aiPage(aiContainer);", context);
  assert.equal(
    find(context.aiContainer, "input").value,
    "my-installed-model:local",
  );
  console.log("PASS: 自选模型独立保存且不修改工作区");

  context.importContainer = new Element("div");
  vm.runInContext("advanced(importContainer);", context);
  find(context.importContainer, "textarea").value = '{"title":"无效草案"}';
  await find(context.importContainer, "button").events.click();
  assert.equal(vm.runInContext("working.title", context), "保存期间的新编辑");
  assert.equal(get("#message").textContent, "结构无效");
  console.log("PASS: 无效结构导入保留原草稿");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
