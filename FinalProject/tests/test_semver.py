"""Tests for skills/open-semver-Azure0413/scripts/_semver.py — the deterministic bump classifier."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SV_PATH = REPO_ROOT / "skills" / "open-semver-Azure0413" / "scripts" / "_semver.py"


def _load():
    spec = importlib.util.spec_from_file_location("_semver", SV_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sv = _load()


def b(old, new):
    return sv.classify(old, new)["bump"]


def test_patch_body_only():
    assert b("def add(a, b):\n    return a+b\n",
             "def add(a, b):\n    s=a+b\n    return s\n") == "patch"


def test_patch_private_only():
    assert b("def _h():\n    return 1\ndef pub():\n    return _h()\n",
             "def _h():\n    return 2\ndef pub():\n    return _h()\n") == "patch"


def test_minor_new_function():
    assert b("def add(a, b):\n    return a+b\n",
             "def add(a, b):\n    return a+b\ndef sub(a, b):\n    return a-b\n") == "minor"


def test_minor_optional_param():
    assert b("def add(a, b):\n    return a+b\n",
             "def add(a, b, c=0):\n    return a+b+c\n") == "minor"


def test_minor_new_varargs():
    assert b("def log(msg):\n    pass\n", "def log(msg, *args):\n    pass\n") == "minor"


def test_minor_new_public_method():
    old = "class A:\n    def f(self):\n        return 1\n"
    new = "class A:\n    def f(self):\n        return 1\n    def g(self):\n        return 2\n"
    assert b(old, new) == "minor"


def test_major_removed_function():
    assert b("def a():\n    pass\ndef bb():\n    pass\n", "def a():\n    pass\n") == "major"


def test_major_new_required_param():
    assert b("def add(a, b):\n    return a+b\n",
             "def add(a, b, c):\n    return a+b+c\n") == "major"


def test_major_renamed_param():
    assert b("def greet(name):\n    return name\n",
             "def greet(username):\n    return username\n") == "major"


def test_major_init_new_required():
    assert b("class A:\n    def __init__(self):\n        pass\n",
             "class A:\n    def __init__(self, x):\n        self.x=x\n") == "major"


def test_major_removed_kwargs():
    assert b("def cfg(**kw):\n    return kw\n", "def cfg():\n    return {}\n") == "major"


def test_syntax_error_reports_error():
    res = sv.classify("def f(:\n  pass\n", "def f():\n  pass\n")
    assert res["bump"] == "" and res["error"]


def test_identical_is_patch():
    src = "def f(a, b=1):\n    return a + b\n"
    assert b(src, src) == "patch"


def test_recovers_over_escaped_newlines():
    # An LLM double-escapes newlines inside the JSON argv: real source newlines arrive as the
    # two-character sequence backslash-n. The harness must recover and classify correctly.
    old = "class Client:\\n    def __init__(self, host, port):\\n        pass\\n\\ndef ping(h):\\n    return True\\n"
    new = "class Client:\\n    def __init__(self, host, address):\\n        pass\\n"
    assert b(old, new) == "major"  # ping removed + __init__ param renamed


def test_recovers_over_escaped_quotes():
    # Some models (observed: llama3.1) over-escape BOTH newlines (backslash-n) and quotes
    # (backslash-quote, e.g. unit=\"cm\") when hand-writing the JSON argv. The harness must
    # recover the over-escaped quotes too, not just newlines, and still classify correctly.
    old = "def area(r):\\n    return 3.14*r*r\\n"
    new = "def area(r, unit=\\\"cm\\\"):\\n    return 3.14*r*r\\ndef perimeter(r):\\n    return 6.28*r\\n"
    assert b(old, new) == "minor"  # optional param added + new public perimeter()


def test_genuinely_broken_still_errors():
    res = sv.classify("def f(:\n  pass\n", "def g():\n  pass\n")
    assert res["bump"] == "" and res["error"]


# --- one-shot advise.py: bump + changelog + contract, all deterministic ---------------------
# advise.py is FILE-BASED (course 2026-06 update): it WRITES the final contract to
# $AIASE_RESULT_PATH instead of printing a fenced JSON block. Tests read that file.
import json as _json
import os as _os
import subprocess as _sub
import sys as _sys
import tempfile as _tempfile

ADVISE = REPO_ROOT / "skills" / "open-semver-Azure0413" / "scripts" / "advise.py"


def _advise_raw(argv1: str) -> dict:
    """Run advise.py with a raw argv string and return the JSON it wrote to the result file."""
    fd, path = _tempfile.mkstemp(suffix=".json", prefix="aiase_semver_")
    _os.close(fd)
    _os.remove(path)
    env = dict(_os.environ)
    env["AIASE_RESULT_PATH"] = path
    p = _sub.run([_sys.executable, str(ADVISE), argv1], env=env,
                 capture_output=True, text=True, encoding="utf-8")
    assert _os.path.exists(path), f"advise.py wrote no result file\nstdout:{p.stdout}\nstderr:{p.stderr}"
    try:
        with open(path, encoding="utf-8") as f:
            return _json.load(f)
    finally:
        _os.remove(path)


def _advise(payload: dict) -> dict:
    return _advise_raw(_json.dumps(payload))


def test_advise_minor_with_changelog():
    out = _advise({"task_id": "x", "old_code": "def f(a):\n    return a\n",
                   "new_code": "def f(a, b=0):\n    return a+b\ndef g():\n    return 1\n"})
    assert out["task_id"] == "x" and out["bump"] == "minor"
    assert "f" in out["changelog"] and "g" in out["changelog"]  # symbol-complete changelog
    assert out["confidence"] == 1.0


def test_advise_patch():
    out = _advise({"task_id": "x", "old_code": "def t(n):\n    return sum(n)\n",
                   "new_code": "def _h(n):\n    return sum(n)\ndef t(n):\n    return _h(n)\n"})
    assert out["bump"] == "patch"


def test_advise_recovers_double_encoded_payload():
    # Some models escape the whole payload as if it were a JSON string (\" and \\n). Recover it.
    inner = {"task_id": "x",
             "old_code": "def f(a):\n    return a\ndef g():\n    return 1\n",
             "new_code": "def f(a):\n    return a\n"}  # g() removed -> major
    double = _json.dumps(inner).replace("\\", "\\\\").replace('"', '\\"')
    out = _advise_raw(double)
    assert out["bump"] == "major" and out["task_id"] == "x"


def test_advise_recovers_over_escaped_and_is_valid_json():
    out = _advise({"task_id": "x",
                   "old_code": "def f(a, b):\\n    return a\\ndef ping():\\n    return 1\\n",
                   "new_code": "def f(a, b):\\n    return a\\n"})
    assert out["bump"] == "major"
    # contract must be strict JSON (no NaN/Infinity)
    _json.dumps(out, allow_nan=False)
