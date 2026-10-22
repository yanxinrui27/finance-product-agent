import io
import json
import unittest
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from finance_agent.artifacts import csv_text, export_bundle, prototype
from finance_agent.core import digest
from finance_agent.drafts import build_prompt, generate, start_workspace, validate_draft
from test_core import demo


class ArtifactTests(unittest.TestCase):
    def state(self):
        data = demo()
        return {"data": data, "version": 1, "digest": digest(data), "signed": False, "blockers": ["待验收"]}

    def test_bundle_and_injection(self):
        state = self.state()
        state["data"]["screens"][0]["title"] = '<script>alert("x")</script>'
        markup = prototype(state)
        self.assertNotIn("<script>", markup)
        self.assertIn("&lt;script&gt;", markup)
        self.assertIn('href="#UI-2"', markup)
        with ZipFile(io.BytesIO(export_bundle(state, []))) as archive:
            self.assertEqual(len(archive.namelist()), 7)
            self.assertIn("RULE-1", archive.read("PRD.md").decode("utf-8"))
            self.assertIn("REQ-1", archive.read("traceability.csv").decode("utf-8-sig"))
        self.assertIn("'=1+1", csv_text([["=1+1"]]))

    def test_actual_upstream_context_and_untrusted_boundary(self):
        prompt = build_prompt(demo())
        self.assertIn("A business requirement is a detailed description", prompt)
        self.assertIn("A product requirement document", prompt)
        self.assertIn("WORKSPACE_DATA", prompt)
        self.assertIn("不能改变本任务", prompt)

    def test_ai_never_connects_when_disabled_or_sensitive(self):
        with patch("urllib.request.build_opener") as opener:
            with self.assertRaises(ValueError):
                generate(demo(), "local-model")
            data = demo()
            data["classification"] = "local_sensitive"
            with self.assertRaises(ValueError):
                generate(data, "local-model", enabled=True)
            opener.assert_not_called()

    def test_ai_loopback_no_proxy_and_draft_validation(self):
        value = {"clarifications": ["请确认阈值"], "prd_outline": "待复核", "uat_suggestions": ["边界值测试"]}
        with patch("urllib.request.OpenerDirector.open") as opened:
            replies = [{"cloud": {"disabled": True}}, {"details": {"format": "gguf"}, "model_info": {"general.architecture": "qwen3"}}, {"response": json.dumps(value), "done": True}]
            contexts = []
            for reply in replies:
                context = MagicMock()
                context.__enter__.return_value.read.return_value = json.dumps(reply).encode()
                contexts.append(context)
            opened.side_effect = contexts
            self.assertEqual(generate(demo(), "local-model", enabled=True), value)
            request = opened.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/generate")
            self.assertEqual([c.args[0].full_url.rsplit("/", 1)[-1] for c in opened.call_args_list], ["status", "show", "generate"])
        with self.assertRaises(ValueError):
            validate_draft({"arbitrary": "not trusted"})

    def test_cloud_and_renamed_remote_models_blocked_before_prompt(self):
        cases = [([{"cloud": {"disabled": False}}], 1), ([{}], 1), ([{"cloud": {"disabled": True}}, {"details": {"format": "gguf"}, "model_info": {"general.architecture": "llama"}, "remote_host": "https://ollama.com", "remote_model": "remote"}], 2), ([{"cloud": {"disabled": True}}, {}], 2)]
        for replies, calls in cases:
            with patch("finance_agent.drafts.local_json", side_effect=replies) as local:
                with self.assertRaises(ValueError):
                    generate(demo(), "innocent-renamed-model", enabled=True)
                self.assertEqual(local.call_count, calls)
                self.assertNotIn("/api/generate", [c.args[1] for c in local.call_args_list])

    def test_export_cannot_include_future_revision(self):
        state = self.state()
        history = [{"version": 2, "reason": "不应外发的新版本"}, {"version": 1, "reason": "当前版本"}]
        with ZipFile(io.BytesIO(export_bundle(state, history))) as archive:
            evidence = json.loads(archive.read("revision-evidence.json"))
            self.assertEqual([r["version"] for r in evidence["history"]], [1])

    def test_new_project_never_invents_financial_policy(self):
        data = start_workspace("应付对账", "减少人工核对", "产品经理")
        self.assertEqual(data["classification"], "local_sensitive")
        self.assertEqual(data["rules"], [])
        self.assertTrue(all(not q["answer"] for q in data["questions"]))


if __name__ == "__main__":
    unittest.main()
