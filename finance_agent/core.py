"""财务领域校验、可追溯关联与追加版本；不包含任何联网代码。"""
import copy
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import sqlite3

GROUPS = ("sources", "requirements", "questions", "processes", "rules", "prd", "screens", "uats")
RESULT_FIELDS = ("status", "actual", "executor", "evidence")
TEXT_FIELDS = {
    "sources": ("title", "notes"),
    "requirements": ("title", "description", "owner", "metric"),
    "questions": ("question", "answer"),
    "processes": ("title",),
    "rules": ("title", "basis", "owner", "effective_from", "effective_to", "currency", "amount_basis", "rounding", "segregation", "exception", "operator", "threshold", "when_true", "when_false"),
    "prd": ("title", "description", "acceptance"),
    "screens": ("title",),
    "uats": ("title", "expected", "actual", "status", "executor", "evidence"),
}
REFS = {
    "requirements": {"source_ids": "sources"},
    "questions": {"requirement_id": "requirements"},
    "processes": {"requirement_ids": "requirements", "rule_ids": "rules"},
    "rules": {"requirement_ids": "requirements"},
    "prd": {"requirement_ids": "requirements", "process_ids": "processes", "rule_ids": "rules"},
    "screens": {"prd_ids": "prd"},
    "uats": {"requirement_ids": "requirements", "rule_ids": "rules", "screen_ids": "screens"},
}


class Conflict(ValueError):
    """编辑基于过时版本，拒绝覆盖。"""


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data):
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()


def text(value, label, required=False):
    if not isinstance(value, str) or len(value) > 20000 or (required and not value.strip()):
        raise ValueError(f"{label} 必须为{'非空' if required else ''}文本（最多20000字）")


def money(value):
    # 金额使用十进制字符串；拒绝浮点、科学计数、非有限数和超大输入。
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,16}(?:\.\d{1,8})?", value):
        raise ValueError("金额须为非负十进制字符串，最多16位整数、8位小数")
    try:
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise ValueError("金额无法按分舍入") from error


def evaluate(rule, amount, currency, on_date):
    if currency != rule["currency"]:
        raise ValueError("币种不匹配，转人工处理")
    try:
        current_date = date.fromisoformat(on_date)
        if not date.fromisoformat(rule["effective_from"]) <= current_date <= date.fromisoformat(rule["effective_to"]):
            raise ValueError("日期超出规则适用期间，转人工处理")
    except (TypeError, ValueError) as error:
        raise ValueError("日期无效或超出规则适用期间，转人工处理") from error
    if rule["rounding"] != "ROUND_HALF_UP_2":
        raise ValueError("仅支持四舍五入到分")
    left, right = money(amount), money(rule["threshold"])
    operators = {">": left > right, ">=": left >= right, "<": left < right, "<=": left <= right, "==": left == right}
    if rule["operator"] not in operators:
        raise ValueError("不支持的规则操作符")
    return rule["when_true"] if operators[rule["operator"]] else rule["when_false"]


def index(data):
    return {node["id"]: node for group in GROUPS for node in data[group]}


def edges(data):
    """返回上游 -> 下游边；流程步骤作为所属流程的一部分修订。"""
    result = []
    for group, fields in REFS.items():
        for node in data[group]:
            for key in fields:
                values = [node[key]] if key == "requirement_id" else node[key]
                result.extend((ref, node["id"]) for ref in values)
    return result


def impact(data, changed):
    affected = set(changed)
    while True:
        extended = affected | {target for source, target in edges(data) if source in affected}
        if extended == affected:
            return sorted(affected)
        affected = extended


def validate(data):
    if not isinstance(data, dict) or set(data) != {"schema_version", "title", "classification", *GROUPS}:
        raise ValueError("工作区必须符合 schema_version=1；不接受未知字段")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("不支持的数据版本")
    text(data["title"], "项目名称", True)
    if data["classification"] not in ("synthetic", "sanitized", "local_sensitive"):
        raise ValueError("数据分类无效")
    seen, by_group = set(), {}
    for group in GROUPS:
        nodes = data[group]
        if not isinstance(nodes, list) or len(nodes) > 1000:
            raise ValueError(f"{group} 必须为列表且最多1000项")
        by_group[group] = set()
        for node in nodes:
            if not isinstance(node, dict):
                raise ValueError(f"{group} 的条目必须为对象")
            node_id = node.get("id")
            if not isinstance(node_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9_-]{0,63}", node_id) or node_id in seen:
                raise ValueError(f"非法或重复 ID：{node_id}")
            seen.add(node_id)
            by_group[group].add(node_id)
            extra = {"steps"} if group == "processes" else {"fields", "actions"} if group == "screens" else {"input"} if group == "uats" else set()
            expected = {"id", *TEXT_FIELDS[group], *REFS.get(group, {}), *extra}
            if set(node) != expected:
                raise ValueError(f"{node_id} 字段不匹配：应为 {sorted(expected)}")
            for field in TEXT_FIELDS[group]:
                text(node[field], f"{node_id}.{field}")
    for group, fields in REFS.items():
        for node in data[group]:
            for key, target in fields.items():
                values = [node[key]] if key == "requirement_id" else node[key]
                if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values) or len(set(values)) != len(values) or any(v not in by_group[target] for v in values):
                    raise ValueError(f"{node['id']}.{key} 引用为空、重复或不存在")
    for node in data["rules"]:
        money(node["threshold"])
        if node["operator"] not in (">", ">=", "<", "<=", "==") or node["rounding"] != "ROUND_HALF_UP_2" or not re.fullmatch(r"[A-Z]{3}", node["currency"]):
            raise ValueError(f"{node['id']} 金额规则格式无效")
        try:
            if date.fromisoformat(node["effective_from"]) > date.fromisoformat(node["effective_to"]):
                raise ValueError()
        except ValueError as error:
            raise ValueError(f"{node['id']} 适用期间无效") from error
    for node in data["processes"]:
        steps = node["steps"]
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"{node['id']} 流程必须包含步骤")
        step_ids = set()
        for step in steps:
            if not isinstance(step, dict) or set(step) != {"id", "role", "input", "action", "output", "next"}:
                raise ValueError("流程步骤字段不匹配")
            sid = step["id"]
            if not isinstance(sid, str) or not re.fullmatch(r"[A-Z][A-Z0-9_-]{0,63}", sid) or sid in seen:
                raise ValueError("步骤 ID 非法或重复")
            seen.add(sid)
            step_ids.add(sid)
            for field in ("role", "input", "action", "output"):
                text(step[field], f"{sid}.{field}", True)
        for step in steps:
            if not isinstance(step["next"], list) or any(not isinstance(v, str) or v not in step_ids for v in step["next"]):
                raise ValueError("流程后续步骤不存在")
    for node in data["screens"]:
        if not isinstance(node["fields"], list) or not isinstance(node["actions"], list):
            raise ValueError("页面字段与动作必须为列表")
        for field in node["fields"]:
            text(field, "页面字段", True)
        for action in node["actions"]:
            if not isinstance(action, dict) or set(action) != {"label", "target"}:
                raise ValueError("页面动作格式无效")
            text(action["label"], "动作标签", True)
            if not isinstance(action["target"], str) or action["target"] not in by_group["screens"]:
                raise ValueError("页面跳转目标不存在")
    for node in data["uats"]:
        if node["status"] not in ("pending", "passed", "failed", "blocked"):
            raise ValueError("UAT 状态无效")
        values = node["input"]
        if not isinstance(values, dict) or set(values) != {"amount", "currency", "date"}:
            raise ValueError("UAT 输入必须包含 amount/currency/date 字符串")
        for key, value in values.items():
            text(value, f"UAT 输入 {key}", True)
    nodes = index(data)
    # 防止需求 A 的验收借用需求 B 的规则/页面，制造虚假的完整覆盖。
    for group in ("processes", "prd", "uats"):
        for node in data[group]:
            scope = set(node["requirement_ids"])
            for key in ("rule_ids", "process_ids"):
                for ref in node.get(key, []):
                    if not set(nodes[ref]["requirement_ids"]) <= scope:
                        raise ValueError(f"{node['id']} 与 {ref} 的需求范围不一致")
            for screen_id in node.get("screen_ids", []):
                screen_scope = {r for p in nodes[screen_id]["prd_ids"] for r in nodes[p]["requirement_ids"]}
                if not screen_scope & scope:
                    raise ValueError(f"{node['id']} 与 {screen_id} 的需求范围不一致")
    return data


def assess(data):
    """业务门禁单独于结构校验，允许保存尚未完成的澄清。"""
    validate(data)
    blockers = []
    for group in GROUPS:
        if not data[group]:
            blockers.append(f"{group} 尚无条目（UAT/来源/澄清/建模均须建立）")
        for node in data[group]:
            for field in TEXT_FIELDS[group]:
                if field in ("actual", "status", "executor", "evidence"):
                    continue
                if not node[field].strip():
                    blockers.append(f"{node['id']} {'澄清未完成' if field == 'answer' else field + ' 未填写'}")
    for req in data["requirements"]:
        if not any(q["requirement_id"] == req["id"] for q in data["questions"]):
            blockers.append(f"{req['id']} 缺少需求澄清")
        downstream = set(impact(data, [req["id"]]))
        for group in ("processes", "rules", "prd", "screens", "uats"):
            if not any(n["id"] in downstream for n in data[group]):
                blockers.append(f"{req['id']} 缺少 {group}/UAT 可追溯覆盖")
    for group in ("rules", "screens"):
        for node in data[group]:
            if not any(node["id"] in c["rule_ids" if group == "rules" else "screen_ids"] for c in data["uats"]):
                blockers.append(f"{node['id']} 缺少 UAT 覆盖")
    for case in data["uats"]:
        if case["status"] != "passed":
            blockers.append(f"{case['id']} UAT 尚未通过")
        elif not all(case[field].strip() for field in ("executor", "evidence", "actual")):
            blockers.append(f"{case['id']} 缺少执行人、实际结果或证据")
        elif case["actual"].strip() != case["expected"].strip():
            blockers.append(f"{case['id']} 实际结果与预期不一致")
    return blockers


def semantic(data):
    result = copy.deepcopy(data)
    for node in result["uats"]:
        for field in RESULT_FIELDS:
            node.pop(field)
    return result


def diff(before, after):
    old, new = index(before) if before else {}, index(after)
    changes = []
    for key in sorted(old.keys() | new.keys()):
        if old.get(key) != new.get(key):
            changes.append({"id": key, "kind": "added" if key not in old else "removed" if key not in new else "updated", "before": old.get(key), "after": new.get(key)})
    if before and any(before[k] != after[k] for k in ("title", "classification")):
        changes.append({"id": "WORKSPACE", "kind": "updated", "before": {k: before[k] for k in ("title", "classification")}, "after": {k: after[k] for k in ("title", "classification")}})
    return changes


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS revisions (
                    version INTEGER PRIMARY KEY, created TEXT NOT NULL, actor TEXT NOT NULL,
                    reason TEXT NOT NULL, digest TEXT NOT NULL, previous_digest TEXT,
                    data TEXT NOT NULL, changes TEXT NOT NULL, affected TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS approvals (
                    version INTEGER NOT NULL, actor TEXT NOT NULL, created TEXT NOT NULL,
                    PRIMARY KEY (version, actor));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def current(self, db=None):
        if db is None:
            with self.connect() as connection:
                return self.current(connection)
        row = db.execute("SELECT * FROM revisions ORDER BY version DESC LIMIT 1").fetchone()
        if row is None:
            return {"version": 0, "data": None, "signed": False, "blockers": ["请先载入合成演示或新建工作区"]}
        data = json.loads(row["data"])
        signers = [dict(item) for item in db.execute("SELECT actor, created FROM approvals WHERE version=?", (row["version"],))]
        blockers = assess(data)
        return {"version": row["version"], "digest": row["digest"], "data": data, "signed": bool(signers), "signers": signers, "blockers": blockers, "ready": bool(signers) and not blockers}

    def save(self, data, expected_version, actor, reason):
        validate(data)
        text(actor, "操作者", True)
        text(reason, "修改原因", True)
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("版本必须是非负整数")
        data = copy.deepcopy(data)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.current(db)
            if current["version"] != expected_version:
                raise Conflict("已有新版本，请重新载入并人工合并；本次未覆盖")
            before = current["data"]
            # 任何业务内容变化均使已有验收记录失效，禁止同时改规则并沿用通过状态。
            if before and semantic(before) != semantic(data):
                for case in data["uats"]:
                    case.update(status="pending", actual="", executor="", evidence="")
            changes = diff(before, data)
            changed_ids = [item["id"] for item in changes]
            affected = set(impact(data, changed_ids))
            if before:
                affected.update(impact(before, changed_ids))
            if "WORKSPACE" in changed_ids:
                affected.update(index(data))
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?,?)", (expected_version + 1, datetime.now(timezone.utc).isoformat(), actor, reason, digest(data), current.get("digest"), canonical(data), canonical(changes), canonical(sorted(affected))))
            return self.current(db)

    def approve(self, expected_version, actor):
        text(actor, "签署人", True)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.current(db)
            if type(expected_version) is not int or current["version"] != expected_version:
                raise Conflict("签署目标版本已变化")
            if current["blockers"]:
                raise ValueError("无法签署：" + "；".join(current["blockers"][:8]))
            db.execute("INSERT OR IGNORE INTO approvals VALUES (?,?,?)", (expected_version, actor, datetime.now(timezone.utc).isoformat()))
            return self.current(db)

    def history(self):
        with self.connect() as db:
            rows = db.execute("SELECT version,created,actor,reason,digest,previous_digest,changes,affected FROM revisions ORDER BY version DESC").fetchall()
            return [{**{key: row[key] for key in ("version", "created", "actor", "reason", "digest", "previous_digest")}, "changes": json.loads(row["changes"]), "impact": json.loads(row["affected"])} for row in rows]
