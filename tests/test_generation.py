"""Grounded prompts, semantic cliches, narration provenance and opt-in tracing."""

import builtins
import json
import os
import random
from unittest.mock import patch

import push_shit as ps
from tests.support import RepoCase


class GenerationTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.cfg = {"lang": "zh", "haunt_count": 0, "lifetime_hauntings": 0,
                    "probability": 1, "diary_path": None}
        self.committed = ("def parse_limit(raw):\n"
                          "    # TODO: reject NEGATIVE_LIMIT_INPUT\n"
                          "    return int(raw)\n")
        (self.repo / "src/app.py").write_text(self.committed, encoding="utf-8")
        self.git("add", "src/app.py")
        self.git("commit", "-m", "add limit parser")
        self.sha = self.git("rev-parse", "HEAD")
        ps.save_config(str(self.repo), self.cfg)

    def sins(self):
        return ps.collect_sins(str(self.repo), self.sha, ps.ZERO_SHA)

    def test_prompt_contains_committed_code_and_real_todo_not_dirty_text(self):
        (self.repo / "src/app.py").write_text(
            "# TODO: DIRTY_PRIVATE_TRIPWIRE\n", encoding="utf-8")
        with patch.object(ps, "llm_chat", return_value="parse_limit连负数都照单全收，门口的检查还没上班？") as chat:
            ps.gen_whisper(self.cfg, self.sins())
        prompt = chat.call_args.args[1]
        self.assertIn("NEGATIVE_LIMIT_INPUT", prompt)
        self.assertIn("return int(raw)", prompt)
        self.assertIn(self.sha, prompt)
        self.assertNotIn("DIRTY_PRIVATE_TRIPWIRE", prompt)

    def test_prompt_shows_real_newlines_and_a_clear_subject(self):
        with patch.object(ps, "llm_chat", return_value="parse_limit没有给负数设门槛，转换倒是很勤快。") as chat:
            ps.gen_whisper(self.cfg, self.sins())
        prompt = chat.call_args.args[1]
        self.assertIn("def parse_limit(raw):\n", prompt)
        self.assertIn("```python", prompt)
        self.assertIn("当前审阅对象：parse_limit", prompt)
        self.assertIn("reference", prompt)
        self.assertIn("observation", prompt)

    def test_vacuous_questions_and_invented_replacement_api_are_not_grounded(self):
        sins = self.sins()
        fact = ps._voice_plan(self.cfg, sins, [])[1]
        self.assertFalse(ps._grounded_voice("parse_limit究竟返回什么值？", fact, sins))
        self.assertFalse(ps._grounded_voice("`parse_limit`应该用`get_or_create`替换。", fact, sins))
        self.assertTrue(ps._grounded_voice("parse_limit把负数也照单全收，检查倒是省下了。", fact, sins))

    def test_generic_praise_is_not_grounded_by_a_code_reference_alone(self):
        sins = self.sins()
        fact = ps._voice_plan(self.cfg, sins, [])[1]
        self.assertFalse(ps._grounded_voice("代码竟然简单到让你怀疑人生。", fact, sins, reference="return int(raw)"))

    def test_inline_markdown_identifier_does_not_lose_one_backtick(self):
        raw = "`parse_limit`把负数也照单全收。"
        with patch.object(ps, "model_request", return_value={"choices": [{"message": {"content": raw}}]}):
            self.assertEqual(ps.llm_chat("system", "user"), raw)

    def test_structured_reference_grounds_a_real_operation_without_forcing_a_name(self):
        sins = self.sins()
        fact = ps._voice_plan(self.cfg, sins, [])[1]
        body = "负数也被这一轮转换照单全收，检查倒是省下了。"
        raw = json.dumps({"reference": "return int(raw)", "text": body}, ensure_ascii=False)
        self.assertEqual(ps._decode_review(raw), (body, "return int(raw)"))
        self.assertTrue(ps._grounded_voice(body, fact, sins, reference="return int(raw)"))
        self.assertFalse(ps._grounded_voice(body, fact, sins, reference="open('/secret')"))
        self.assertEqual(ps._decode_review('{"text": "body", "reference": 42}'), (None, None))

    def test_reference_is_verified_even_for_top_level_code_without_a_symbol(self):
        sins = {"contexts": [{"id": "top", "symbol": None, "file": "src/app.py",
                              "code": "VALUE = 42\nprint(VALUE)", "sha": self.sha, "start_line": 1}]}
        fact = ("code_top", "top-level code")
        self.assertFalse(ps._grounded_voice("读取了秘密。", fact, sins, reference="open('/secret')"))
        self.assertTrue(ps._grounded_voice("输出的是这个已定义的值。", fact, sins, reference="print(VALUE)"))
        sins["contexts"][0]["code"] = "def empty():\n    return None"
        self.assertTrue(ps._grounded_voice("这个返回值没有携带结果。", fact, sins, reference="return None"))

    def test_reference_verification_preserves_whitespace_inside_string_literals(self):
        sins = {"contexts": [{"id": "spaces", "symbol": "tokens", "file": "src/app.py",
                              "code": 'def tokens(line):\n    return line.split(" ")',
                              "sha": self.sha, "start_line": 1}]}
        fact = ("code_spaces", "space tokenizer")
        self.assertFalse(ps._grounded_voice("空格切分。", fact, sins, reference='line.split("")'))
        self.assertTrue(ps._grounded_voice("空格切分。", fact, sins, reference="line.split( ' ' )"))

    def test_reference_cannot_join_two_distinct_python_statements(self):
        context = {"file": "x.py", "code": "def f(a, b):\n    return a\n    + b\n"}
        self.assertFalse(ps._reference_in_code("return a + b", context))
        context["code"] = "def f(a, b):\n    return (a\n            + b)\n"
        self.assertTrue(ps._reference_in_code("return (a + b)", context))

    def test_common_quoted_and_annotated_secret_values_never_become_context(self):
        blobs = ['CONFIG = {"password": "synthetic-secret-123"}\n# TODO private\n',
                 'api_key: str = "synthetic-secret-123"\n# TODO private\n']
        for blob in blobs:
            def fake_git(args, _root, blob=blob):
                if args[0] == "ls-tree":
                    return 0, "100644 blob " + "a" * 40 + " 100\tsrc/settings.py\0", ""
                if args[0] == "show":
                    return 0, blob, ""
                return 0, "", ""
            with self.subTest(blob=blob), patch.object(ps, "run_git", side_effect=fake_git):
                material = ps._committed_material(str(self.repo), self.sha)
            self.assertEqual(material["contexts"], [])
            self.assertIsNone(material["todo"])
            self.assertNotIn("synthetic-secret-123", str(material))

    def test_reference_menu_uses_real_expressions_not_flattened_try_blocks(self):
        context = {"file": "x.py", "code": "def retry_once(work):\n    try:\n        return work()\n    except ValueError:\n        return work()\n"}
        choices = ps._reference_choices(context)
        self.assertIn("work()", choices)
        self.assertFalse(any("try:" in value or "except" in value for value in choices))
        self.assertTrue(all(ps._reference_in_code(value, context) for value in choices))

    def test_membership_comparison_is_a_valid_grounded_reference(self):
        context = {"id": "cache", "file": "x.py", "symbol": "cached", "sha": self.sha, "start_line": 1,
                   "code": "def cached(cache, key, loader):\n    if key not in cache:\n        cache[key] = loader()\n    return cache[key]"}
        sins = {"contexts": [context]}
        self.assertTrue(ps._grounded_voice("缓存没有这个键时，才加载并存下结果。", ("code_cache", "code"),
                                           sins, reference="key not in cache"))

    def test_reference_cannot_move_a_return_into_another_indentation_block(self):
        context = {"file": "x.py", "code": "def f(x):\n    if x:\n        return 1\n    return 2\n"}
        self.assertFalse(ps._reference_in_code("if x:\n    return 1\n    return 2", context))
        self.assertTrue(ps._reference_in_code("return 2", context))

    def test_exception_flow_annotations_must_distinguish_retry_from_swallowing(self):
        retry = {"id": "retry", "file": "x.py", "symbol": "f", "sha": self.sha, "start_line": 1,
                 "code": "def f(work):\n    try:\n        return work()\n    except ValueError:\n        return work()"}
        swallow = {**retry, "id": "swallow", "code": "def f(work):\n    try:\n        return work()\n    except Exception:\n        return None"}
        self.assertFalse(ps._grounded_voice("函数会立即执行传入的工作。", ("code_retry", "code"),
                                            {"contexts": [retry]}, reference="work()"))
        self.assertFalse(ps._grounded_voice("调用者会立刻执行传入的函数。", ("code_swallow", "code"),
                                            {"contexts": [swallow]}, reference="work()"))
        self.assertTrue(ps._grounded_voice("ValueError后再调用一次，第二次失败就抛出。", ("code_retry", "code"),
                                           {"contexts": [retry]}, reference="work()"))
        self.assertTrue(ps._grounded_voice("调用失败时返回None，没出错就原样还回去。", ("code_swallow", "code"),
                                           {"contexts": [swallow]}, reference="return None"))
        self.assertTrue(ps._grounded_voice("第一次失败后，又重新播种一遍，但不会无限循环。", ("code_retry", "code"),
                                           {"contexts": [retry]}, reference="return work()"))
        self.assertTrue(ps._grounded_voice("遇到难题就立马重启调查一遍，只差没喊重新开始。", ("code_retry", "code"),
                                           {"contexts": [retry]}, reference="return work()"))

    def test_mixed_accepts_real_imperative_and_article_free_english_clauses(self):
        for english in ("Avoid float clock values, cast immediately to integer.",
                        "Key replacement occurs; original keys remain unchanged.",
                        "Key replacement preserves original data structure."):
            with self.subTest(english=english):
                self.assertTrue(ps._voice_language_ok("我记下这条旁注；" + english, "mixed", {}))
        self.assertFalse(ps._voice_language_ok("这些标记还在；TODO FIXME HACK XXX", "mixed", {}))
        self.assertFalse(ps._voice_language_ok("这些是代码关键字；return static public class", "mixed", {}))

    def test_finally_override_does_not_get_a_false_swallowing_hint(self):
        context = {"id": "finally", "file": "x.py", "symbol": "f", "sha": self.sha, "start_line": 1,
                   "code": "def f(work):\n    try:\n        return work()\n    except Exception:\n        return None\n    finally:\n        return 7"}
        self.assertIsNone(ps._exception_behavior(context))
        self.assertNotIn("正常调用的结果原样返回", ps._python_notes(context, "zh"))
        self.assertTrue(ps._grounded_voice("无论工作成功失败，最终都返回7。", ("code_finally", "code"),
                                           {"contexts": [context]}, reference="return 7"))

    def test_generic_time_poetry_is_not_a_concrete_integer_conversion_observation(self):
        context = {"id": "clock", "file": "x.py", "symbol": "f", "sha": self.sha, "start_line": 1,
                   "code": "def f(clock):\n    return int(clock())"}
        sins = {"contexts": [context]}
        self.assertFalse(ps._grounded_voice("时间就像沙漏，流逝不复返。", ("code_clock", "code"), sins,
                                            reference="int(clock())"))
        self.assertTrue(ps._grounded_voice("时间如水，只留整数的痕迹。", ("code_clock", "code"), sins,
                                           reference="int(clock())"))

    def test_unbounded_read_is_not_accepted_as_next_character_consumption(self):
        context = {"id": "reader", "file": "x.py", "symbol": "read_everything", "sha": self.sha, "start_line": 1,
                   "code": "def read_everything(reader):\n    return reader.read()"}
        sins = {"contexts": [context]}
        self.assertFalse(ps._grounded_voice("直接读取字符，像吞噬者一口吞下下一个。", ("code_reader", "code"),
                                            sins, reference="reader.read()"))
        self.assertTrue(ps._grounded_voice("把读取器剩下的所有内容读回来。", ("code_reader", "code"),
                                           sins, reference="reader.read()"))

    def test_similar_call_sites_need_their_distinct_state_or_evaluation_detail(self):
        cache = {"id": "cache", "file": "x.py", "symbol": "cached", "sha": self.sha, "start_line": 1,
                 "code": "def cached(cache, key, loader):\n    if key not in cache:\n        cache[key] = loader()\n    return cache[key]"}
        default = {**cache, "id": "default", "symbol": "get_or_build",
                   "code": "def get_or_build(mapping, key, fallback):\n    return mapping.get(key, fallback())"}
        self.assertFalse(ps._grounded_voice("键不存在时，加载器会被调用一次。", ("code_cache", "code"),
                                            {"contexts": [cache]}, reference="key not in cache"))
        self.assertTrue(ps._grounded_voice("缺键时把加载结果写入缓存，后续复用。", ("code_cache", "code"),
                                           {"contexts": [cache]}, reference="key not in cache"))
        self.assertFalse(ps._grounded_voice("键不存在，就调用fallback得到新值。", ("code_default", "code"),
                                            {"contexts": [default]}, reference="mapping.get(key, fallback())"))
        self.assertTrue(ps._grounded_voice("fallback先求值，即使字典里已经有键。", ("code_default", "code"),
                                           {"contexts": [default]}, reference="mapping.get(key, fallback())"))

    def test_deduplication_is_not_an_unrelated_front_row_metaphor(self):
        context = {"id": "set", "file": "x.py", "symbol": "unique_labels", "sha": self.sha, "start_line": 1,
                   "code": "def unique_labels(labels):\n    return list(set(labels))"}
        self.assertFalse(ps._grounded_voice("标签像排队的人，只留下最前排。", ("code_set", "code"),
                                            {"contexts": [context]}, reference="list(set(labels))"))
        self.assertTrue(ps._grounded_voice("重复标签只留一份，不保证原序。", ("code_set", "code"),
                                           {"contexts": [context]}, reference="list(set(labels))"))

    def test_diary_can_review_another_detail_without_copying_primary_focus(self):
        context = {"id": "cache", "file": "x.py", "symbol": "cached", "sha": self.sha, "start_line": 1,
                   "scope": "committed snapshot",
                   "code": "def cached(cache, key, loader):\n    if key not in cache:\n        cache[key] = loader()\n    return cache[key]"}
        sins = {**self.sins(), "contexts": [context]}
        text = "建议增加键类型校验，避免未命中时输入类型不合预期。"
        self.assertFalse(ps._grounded_voice(text, ("code_cache", "code"), sins, reference="key not in cache"))
        reply = json.dumps({"reference": "key not in cache", "observation": "键参与字典成员检查", "text": text})
        info = {}
        with patch.object(ps, "llm_chat", return_value=reply):
            ps.gen_diary_entry(self.cfg, sins, "加了旁注", meta=info)
        self.assertEqual(info["source"], "model")
        self.assertEqual(info["attempts"], 1)

    def test_diary_focus_opt_out_preserves_reader_and_reference_boundaries(self):
        context = {"id": "reader", "file": "x.py", "symbol": "read_all",
                   "code": "def read_all(reader):\n    return reader.read()"}
        sins, fact = {"contexts": [context]}, ("code_reader", "code")
        for focus in (True, False):
            with self.subTest(primary_focus=focus):
                self.assertFalse(ps._grounded_voice("只吞下下一个字符。", fact, sins,
                                                   reference="reader.read()", primary_focus=focus))
                self.assertFalse(ps._grounded_voice("读取所有内容。", fact, sins,
                                                   reference="reader.read(1)", primary_focus=focus))
        context["code"] = 'def f():\n    return "a b"'
        self.assertFalse(ps._grounded_voice("返回字符串。", fact, sins,
                                           reference='return "ab"', primary_focus=False))
        context["code"] = "def f(work):\n    try:\n        return work()\n    except Exception:\n        return None"
        self.assertFalse(ps._grounded_voice("异常转为空值。", fact, sins,
                                           reference="work()\nreturn None", primary_focus=False))

    def test_only_primary_messages_require_the_selected_data_behavior(self):
        examples = [
            ("def f(cache, key, loader):\n    if key not in cache:\n        cache[key] = loader()\n    return cache[key]",
             "key not in cache", "建议增加键类型校验。"),
            ("def f(mapping, key, fallback):\n    return mapping.get(key, fallback())",
             "mapping.get(key, fallback())", "建议说明缺键返回值的类型。"),
            ("def f(labels):\n    return list(set(labels))", "list(set(labels))", "空列表仍返回空列表。"),
        ]
        for code, reference, text in examples:
            with self.subTest(reference=reference):
                sins = {"contexts": [{"id": "one", "file": "x.py", "symbol": "f", "code": code}]}
                self.assertFalse(ps._grounded_voice(text, ("code_one", "code"), sins, reference=reference))
                self.assertTrue(ps._grounded_voice(text, ("code_one", "code"), sins,
                                                  reference=reference, primary_focus=False))

    def test_plain_and_mixed_whispers_do_not_opt_out_of_primary_focus(self):
        for lang, text in (("zh", "输入转换为整数，负数仍需检查。"),
                           ("mixed", "输入转换为整数，负数仍需检查；The integer conversion still needs a boundary guard.")):
            with self.subTest(lang=lang):
                reply = json.dumps({"reference": "int(raw)", "observation": "整数转换", "text": text})
                with patch.object(ps, "llm_chat", return_value=reply), \
                        patch.object(ps, "_grounded_voice", wraps=ps._grounded_voice) as guard:
                    result = ps.gen_whisper({**self.cfg, "lang": lang}, self.sins())
                self.assertIsNotNone(result)
                self.assertTrue(guard.called)
                self.assertTrue(all(call.kwargs.get("primary_focus", True) for call in guard.call_args_list))

    def test_shared_evaluation_facts_and_concrete_action_survive_diary_role(self):
        context = {"id": "get", "file": "x.py", "symbol": "f",
                   "code": "def f(mapping, key, fallback):\n    return mapping.get(key, fallback())"}
        for lang, role_marker, action_marker in (("zh", "无论主留言还是日记", "比喻不能替代"),
                                                 ("en", "both annotations and diaries", "metaphor cannot replace")):
            with self.subTest(lang=lang):
                self.assertIn(role_marker, ps._python_notes(context, lang))
                prompt, _ = ps._review_format("", ("code_get", "code"), {"contexts": [context]}, lang)
                self.assertIn(action_marker, prompt)

    def test_eager_default_accepts_real_call_order_without_a_magic_timing_word(self):
        context = {"id": "get", "file": "x.py", "symbol": "get_or_build",
                   "code": "def get_or_build(mapping, key, fallback):\n    return mapping.get(key, fallback())"}
        sins, fact = {"contexts": [context]}, ("code_get", "code")
        self.assertTrue(ps._grounded_voice("fallback() 调用了，get 尝试在映射中查找 key。", fact, sins,
                                           reference="mapping.get(key, fallback())"))
        for text in ("如果键不在映射里，就执行fallback。", "get查找，fallback生成默认值。",
                     "fallback()只有缺键才执行，get查找。", "fallback() runs only when missing; get selects a value.",
                     "如果键不存在，fallback() 调用了，get 查找 key。",
                     "fallback() 没有调用，get 查找 key。", "fallback()，get。",
                     "fallback() 调用了，get 没有查找。",
                     "On a cache miss, fallback() runs; get selects a value."):
            with self.subTest(text=text):
                self.assertFalse(ps._grounded_voice(text, fact, sins, reference="mapping.get(key, fallback())"))
        context["code"] = "def get_or_build(mapping, key, resolve):\n    return mapping.get(key, resolve())"
        self.assertTrue(ps._grounded_voice("resolve() runs; get selects the returned value.", fact, sins,
                                           reference="mapping.get(key, resolve())"))
        self.assertFalse(ps._grounded_voice("fallback() runs; get selects a value.", fact, sins,
                                            reference="mapping.get(key, resolve())"))
        for text in ("RESOLVE() runs; get selects a value.", "resolve() runs; GET selects a value."):
            self.assertFalse(ps._grounded_voice(text, fact, sins, reference="mapping.get(key, resolve())"))
        self.assertTrue(ps._grounded_voice("resolve() RUNS; get SELECTS a value.", fact, sins,
                                           reference="mapping.get(key, resolve())"))

    def test_lazy_default_claims_are_rejected_for_diaries_without_forcing_a_focus(self):
        context = {"id": "get", "file": "x.py", "symbol": "f",
                   "code": "def f(mapping, key, fallback):\n    return mapping.get(key, fallback())"}
        sins, fact = {"contexts": [context]}, ("code_get", "code")
        for text in ("先尝试从字典找到目标，找不到再调用备用方法生成替代方案。",
                     "键存在直接返回键值，否则立即执行fallback函数。",
                     "First look up the key; otherwise call fallback()."):
            for focus in (True, False):
                with self.subTest(text=text, primary_focus=focus):
                    self.assertFalse(ps._grounded_voice(text, fact, sins,
                                                       reference="mapping.get(key, fallback())", primary_focus=focus))
        for text in ("建议说明缺键返回值的类型。", "fallback先执行，即使键存在。",
                     "fallback先执行，不是缺键才调用。"):
            self.assertTrue(ps._grounded_voice(text, fact, sins,
                                              reference="mapping.get(key, fallback())", primary_focus=False))

    def test_evaluation_steps_use_actual_source_names_and_follow_the_style_task(self):
        context = {"id": "get", "file": "x.py", "symbol": "f",
                   "code": "def f(mapping, key, resolve):\n    return mapping.get(key, resolve())"}
        for lang in ("zh", "en"):
            with self.subTest(lang=lang):
                notes = ps._python_notes(context, lang)
                self.assertIn("resolve()", notes)
                self.assertNotIn("fallback()", notes)
                prompt, _ = ps._review_format("STYLE TASK", ("code_get", "code"), {"contexts": [context]}, lang)
                self.assertTrue(prompt.endswith(notes))

    def test_annotation_system_prioritizes_facts_and_obeys_structured_output(self):
        for lang, facts, optional in (("zh", "事实优先", "幽默可选"),
                                      ("en", "Facts first", "humor is optional")):
            with self.subTest(lang=lang):
                system = ps._voice_system(lang)
                self.assertIn(facts, system)
                self.assertIn(optional, system)
                self.assertNotIn("不是函数说明书", system)
                self.assertNotIn("Only the final annotation", system)

    def test_diary_retries_unclosed_inline_code_instead_of_planting_half_a_sentence(self):
        context = {"id": "tokens", "file": "x.py", "symbol": "tokens", "sha": self.sha,
                   "start_line": 1, "scope": "committed snapshot",
                   "code": 'def tokens(line):\n    return line.split(" ")'}
        sins = {**self.sins(), "contexts": [context]}
        def reply(text):
            return json.dumps({"reference": 'line.split(" ")', "observation": "空格分割", "text": text})
        broken = reply("建议将 `line.split(")
        good = reply('`line.split(" ")`会保留连续空格间的空字符串。')
        info = {}
        with patch.object(ps, "llm_chat", side_effect=[broken, good]):
            entry = ps.gen_diary_entry(self.cfg, sins, "旁注", meta=info)
        self.assertEqual(info["source"], "model")
        self.assertEqual(info["attempts"], 2)
        self.assertEqual(info["rejections"], ["incomplete-inline-code"])
        self.assertIn("连续空格", entry)
        with patch.object(ps, "llm_chat", return_value=broken) as chat:
            info = {}
            ps.gen_diary_entry(self.cfg, sins, "旁注", meta=info)
        self.assertNotEqual(info["source"], "model")
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(info["rejections"], ["incomplete-inline-code"] * 2)

    def test_retry_accepts_the_actual_continue_execution_paraphrase(self):
        context = {"id": "retry", "file": "x.py", "symbol": "retry_once",
                   "code": "def retry_once(work):\n    try:\n        return work()\n    except ValueError:\n        return work()"}
        self.assertTrue(ps._grounded_voice("work()被立刻调用，如果出现ValueError，函数会继续执行work()。",
                                           ("code_retry", "code"), {"contexts": [context]}, reference="work()"))
        self.assertFalse(ps._grounded_voice("函数调用了工作函数，并返回工作函数的结果。",
                                            ("code_retry", "code"), {"contexts": [context]}, reference="work()"))

    def test_retry_diary_must_keep_failure_or_operation_not_only_a_spring_metaphor(self):
        context = {"id": "retry", "file": "x.py", "symbol": "retry_once", "sha": self.sha,
                   "start_line": 1, "scope": "committed snapshot",
                   "code": "def retry_once(work):\n    try:\n        return work()\n    except ValueError:\n        return work()"}
        sins, fact = {**self.sins(), "contexts": [context]}, ("code_retry", "code")
        text = "就像一根弹簧，被压了一下就立刻又弹了回去，即便弹回去的压力和之前一样。"
        self.assertFalse(ps._grounded_voice(text, fact, sins, reference="work()", primary_focus=False))
        for good in ("work()又执行了一次。", "失败以后重新做一次，而不是无止境重来。"):
            self.assertTrue(ps._grounded_voice(good, fact, sins, reference="work()", primary_focus=False))
        reply = json.dumps({"reference": "work()", "observation": "失败重试", "text": "work()又执行了一次。"})
        with patch.object(ps, "llm_chat", return_value=reply) as chat:
            ps.gen_diary_entry(self.cfg, sins, "旁注")
        self.assertIn("事实优先", chat.call_args.args[0])

    def test_structured_output_format_reaches_the_actual_model_request(self):
        reply = '{"reference": "return 1", "text": "A concrete note."}'
        with patch.object(ps, "model_request", return_value={"choices": [{"message": {"content": reply}}]}) as request:
            self.assertEqual(ps.llm_chat("system", "user", response_format={"type": "json_object"}), reply)
        self.assertEqual(request.call_args.args[2]["response_format"], {"type": "json_object"})

    def test_todo_facts_are_from_the_selected_commit(self):
        (self.repo / "src/app.py").write_text("# TODO: DIRTY_PRIVATE_TRIPWIRE\n", encoding="utf-8")
        sins = self.sins()
        self.assertIn("NEGATIVE_LIMIT_INPUT", sins["todo"]["text"])
        self.assertNotIn("DIRTY_PRIVATE_TRIPWIRE", str(sins))

    def test_code_context_ignores_secrets_and_owned_outputs_and_is_bounded(self):
        (self.repo / ".env").write_text("TOKEN=ENV_SECRET_TRIPWIRE\n", encoding="utf-8")
        (self.repo / "src/keys.py").write_text('API_KEY = "SECRET_VALUE_TRIPWIRE"\n', encoding="utf-8")
        (self.repo / "src/generated.py").write_text("# OLD_GHOST_TRIPWIRE\nprint('boo')\n", encoding="utf-8")
        (self.repo / "src/diary.md").write_text("# OLD_DIARY_TRIPWIRE\n", encoding="utf-8")
        original = self.committed.replace("    return", "    # FORMER_AUTHOR_TRIPWIRE\n    return")
        (self.repo / "src/app.py").write_text(original + "# 💩 OLD_VOICE_TRIPWIRE\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "context exclusions")
        self.sha = self.git("rev-parse", "HEAD")
        ps.ledger_append(str(self.repo), {"type": "ghost_code", "file": "src\\generated.py"})
        ps.ledger_append(str(self.repo), {"type": "diary", "file": "src/diary.md"})
        ps.ledger_append(str(self.repo), {"type": "predecessor", "file": "src/app.py", "line": "# FORMER_AUTHOR_TRIPWIRE"})
        contexts = self.sins()["contexts"]
        self.assertTrue(contexts)
        self.assertLessEqual(len(contexts), 48)
        rendered = json.dumps(contexts, ensure_ascii=False)
        for marker in ("ENV_SECRET_TRIPWIRE", "SECRET_VALUE_TRIPWIRE", "OLD_GHOST_TRIPWIRE",
                       "OLD_DIARY_TRIPWIRE", "OLD_VOICE_TRIPWIRE", "FORMER_AUTHOR_TRIPWIRE"):
            self.assertNotIn(marker, rendered)
        for item in contexts:
            self.assertLessEqual(len(item["code"]), 2000)
            self.assertLessEqual(len(item["code"].splitlines()), 16)
            self.assertEqual(item["sha"], self.sha)

    def test_mixed_english_completion_sees_its_chinese_partner(self):
        chinese = "parse_limit把负数也收进来了，检查去哪了？"
        english = "The conversion still needs a boundary guard."
        with patch.object(ps, "llm_chat", side_effect=[chinese, english]) as chat:
            result = ps.gen_whisper({**self.cfg, "lang": "mixed"}, self.sins())
        self.assertIsNotNone(result)
        self.assertIn(chinese, chat.call_args_list[1].args[1])

    def test_committed_context_determines_the_comment_destination(self):
        other = self.repo / "src/other.py"
        other.write_text("def keep_first(values):\n    return values[0]\n", encoding="utf-8")
        self.git("add", "src/other.py")
        self.git("commit", "-m", "add other behavior")
        with (self.repo / "src/app.py").open("a", encoding="utf-8") as handle:
            handle.write("# Fresh diff is here, while selected review context is in the other file.\n")
        self.git("add", "src/app.py")
        self.git("commit", "-m", "review parser metadata")
        self.sha = self.git("rev-parse", "HEAD")
        sins = self.sins()
        self.cfg["haunt_count"] = 1
        fact = ps._voice_plan(self.cfg, sins, [])[1]
        context = ps._fact_context(fact[0], sins)
        assert context is not None
        response = context["symbol"] + "把空列表的第一个位置也当成了已有人占座。"
        with patch.object(ps, "server_alive", return_value=True), patch.object(ps, "llm_chat", return_value=response):
            result = ps.plant_whisper(str(self.repo), self.cfg, sins, random.Random(1))
        assert result is not None
        self.assertEqual(result["file"], context["file"])

    def test_unseen_committed_behaviors_are_used_before_revisiting_old_ones(self):
        contexts = [{"id": key, "file": "src/app.py", "code": "return 1", "sha": self.sha,
                     "symbol": key, "start_line": 1} for key in ("a", "b", "c", "d")]
        recent = [{"text": key, "fact": "code_" + key} for key in ("a", "b", "c")]
        fact = ps._voice_plan({**self.cfg, "haunt_count": 4}, {"contexts": contexts}, recent)[1]
        self.assertEqual(fact[0], "code_d")

    def test_owned_comment_growth_does_not_change_the_user_context_identity(self):
        before = self.sins()["contexts"][0]
        lines = self.committed.splitlines(keepends=True)
        lines[1:1] = ["    # 💩 old generated annotation\n"] * 20
        (self.repo / "src/app.py").write_text("".join(lines), encoding="utf-8")
        self.git("add", "src/app.py")
        self.git("commit", "-m", "simulate owned comment growth")
        self.sha = self.git("rev-parse", "HEAD")
        after = self.sins()["contexts"][0]
        self.assertEqual(after["code"], before["code"])
        self.assertEqual(after["id"], before["id"])

    def test_persona_does_not_force_repeated_surveillance_and_aggression(self):
        for phrase in ("一举一动", "永远删不掉", "语气攻击性强"):
            self.assertNotIn(phrase, ps.PERSONA["zh"])
        self.assertNotIn("aggressive, contemptuous", ps.PERSONA["en"])

    def test_synonymous_debt_cliches_are_rejected_even_without_text_similarity(self):
        previous = "我把这份代码记为一笔技术债，后来的人总要替你还。"
        candidate = "欠款清单又添了新账单，偿还日期并不由你决定。"
        self.assertTrue(ps._recent_repeat(candidate, [{"text": previous}]))
        self.assertFalse(ps._recent_repeat(
            "列表排序会原地修改调用者传来的对象。", [{"text": "异常被这段分支吞掉，日志里没有留下线索。"}]))

    def test_chinese_diary_prompt_uses_an_explicit_chinese_instruction(self):
        with patch.object(ps, "llm_chat", return_value="parse_limit把负数也照单全收，我先记下这个边界。") as chat:
            ps.gen_diary_entry(self.cfg, self.sins(), "whisper annotation in src/app.py")
        self.assertIn("只用自然中文", chat.call_args.args[1])
        self.assertNotIn("Write a personal field note", chat.call_args.args[1])

    def test_python_argument_evaluation_note_is_derived_from_nested_calls(self):
        context = {"id": "evaluation", "file": "src/app.py", "sha": self.sha, "start_line": 1,
                   "scope": "committed snapshot", "symbol": "get_or_build",
                   "code": "def get_or_build(mapping, key, fallback):\n    return mapping.get(key, fallback())"}
        prompt = ps._material_prompt(("code_evaluation", "code"), {"contexts": [context]}, "zh")
        self.assertIn("实参", prompt)
        self.assertIn("先求值", prompt)

    def test_diary_fallbacks_have_history_and_honest_provenance(self):
        recent = []
        values = []
        with patch.object(ps, "llm_chat", return_value=None):
            for _ in range(4):
                meta = {}
                entry = ps.gen_diary_entry(self.cfg, self.sins(), "whisper in src/app.py",
                                          recent=recent, meta=meta)
                self.assertEqual(meta["source"], "template")
                assert entry is not None
                body = entry.split("\n\n", 1)[1].strip()
                values.append(body)
                recent.append({"text": body})
        self.assertEqual(len(set(values)), 4)

    def test_diary_preface_is_not_counted_as_model(self):
        meta = {}
        with patch.object(ps, "llm_chat", return_value="Okay, here's a creepy diary entry:"):
            entry = ps.gen_diary_entry(self.cfg, self.sins(), "whisper in src/app.py", meta=meta)
        self.assertNotEqual(meta["source"], "model")
        assert entry is not None
        self.assertNotIn("Okay", entry)

    def test_auxiliary_narrations_have_multiple_honest_fallbacks(self):
        for kind in ("seed", "epitaph"):
            recent = []
            values = []
            with patch.object(ps, "llm_chat", return_value=None):
                for _ in range(3):
                    meta = {}
                    if kind == "seed":
                        value = ps.gen_seed_whisper(self.cfg, recent=recent, meta=meta)
                    else:
                        value = ps.gen_epitaph(self.cfg, "one annotation removed", recent=recent, meta=meta)
                    self.assertEqual(meta["source"], "template")
                    values.append(value)
                    recent.append({"text": value})
            self.assertEqual(len(set(values)), 3)

    def test_llm_does_not_throw_away_every_line_after_the_first(self):
        raw = "我记下了转型之后漏掉的边界。\n再看负数，它没有被门槛拦住。"
        with patch.object(ps, "model_request", return_value={"choices": [{"message": {"content": raw}}]}):
            self.assertEqual(ps.llm_chat("system", "user"), raw)

    def test_trace_disabled_by_default(self):
        with patch.dict(os.environ, {"PUSH_SHIT_TRACE": "0"}), \
                patch.object(ps, "model_request", return_value={"choices": [{"message": {"content": "valid reply"}}]}), \
                ps.generation_scope(str(self.repo), "manual", 1):
            self.assertEqual(ps.llm_chat("system", "user"), "valid reply")
        self.assertFalse((self.repo / ".git/push-shit/model-trace.jsonl").exists())

    def test_trace_records_actual_request_and_full_response_under_target(self):
        raw = "first line\nsecond line"
        with patch.dict(os.environ, {"PUSH_SHIT_TRACE": "1"}), \
                patch.object(ps, "model_request", return_value={"choices": [{"message": {"content": raw}}]}), \
                ps.generation_scope(str(self.repo), "push", 7):
            ps.llm_chat("actual system", "actual user", temperature=0.8)
        path = self.repo / ".git/push-shit/model-trace.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["raw"], raw)
        self.assertEqual(rows[0]["system"], "actual system")
        self.assertEqual(rows[0]["user"], "actual user")
        self.assertEqual(rows[0]["trigger"], "push")
        self.assertEqual(rows[0]["haunting"], 7)

    def test_trace_write_error_does_not_turn_a_real_reply_into_failure(self):
        original_open = builtins.open

        def guarded(path, *args, **kwargs):
            if str(path).endswith("model-trace.jsonl"):
                raise OSError("trace is read-only")
            return original_open(path, *args, **kwargs)

        with patch.dict(os.environ, {"PUSH_SHIT_TRACE": "1"}), \
                patch.object(ps, "model_request", return_value={"choices": [{"message": {"content": "real reply"}}]}), \
                ps.generation_scope(str(self.repo), "manual", 1), patch("builtins.open", side_effect=guarded):
            self.assertEqual(ps.llm_chat("system", "user"), "real reply")
