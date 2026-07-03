"""任務二進階功能單元測試：privacy、decay、hybrid (bm25_only path)、CLI /recall /forget。

注意：核心 BM25 與 store 的測試在 test_memory.py。這裡只測「進階開關」與「外殼」。
hybrid_search 完整路徑需 sentence-transformers 與模型下載，所以在這裡只測 bm25_only
fallback 與「未安裝 embedding 後端時 retrieve 仍可運作」這兩個保證。
"""
from __future__ import annotations
import json
import os
import tempfile
import time

import pytest


@pytest.fixture
def tmp_store(monkeypatch):
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    from memory import core
    core.set_memory_path(f.name)
    yield f.name
    os.unlink(f.name)


# ── 任務二 B：隱私過濾 ──

def test_privacy_redacts_openai_key():
    from memory.privacy import redact, contains_secret
    s = "my key is sk-abcd1234EFGH56789xyzPOI"
    out = redact(s)
    assert "sk-abcd1234EFGH56789xyzPOI" not in out
    assert "[REDACTED]" in out
    assert contains_secret(s)


def test_privacy_redacts_github_token():
    from memory.privacy import redact
    s = "use ghp_abcdefghij0123456789KLMNOP for auth"
    out = redact(s)
    assert "abcdefghij0123456789" not in out
    assert "ghp_[REDACTED]" in out


def test_privacy_redacts_password_assignment():
    from memory.privacy import redact
    s = "DATABASE_URL=postgres://user:password=hunter2@db/x"
    out = redact(s)
    # 「password=hunter2」應被遮成 password=[REDACTED]
    assert "hunter2" not in out
    assert "[REDACTED]" in out


def test_privacy_redacts_bearer_jwt():
    from memory.privacy import redact
    s = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.PAYLOAD_PAYLOAD.SIGNATURE_X"
    out = redact(s)
    assert "eyJhbGci" not in out
    assert "Bearer [REDACTED]" in out


def test_privacy_leaves_normal_text_untouched():
    from memory.privacy import redact, contains_secret
    s = "this project uses pnpm test"
    assert redact(s) == s
    assert not contains_secret(s)


def test_capture_with_privacy_env(tmp_store, monkeypatch):
    """PI_PRIVACY=1 時，summary 在存檔前被遮蔽（去重 id 也跟著更新）。"""
    monkeypatch.setenv("PI_PRIVACY", "1")
    from memory.core import capture, make_observation, list_all
    obs = make_observation("save this: sk-LIVE0000abcdEFGHabcdEFGH1234")
    capture(obs)
    items = list_all()
    assert len(items) == 1
    assert "sk-LIVE0000abcdEFGHabcdEFGH1234" not in items[0]["summary"]
    assert "[REDACTED]" in items[0]["summary"]


# ── 任務二 C：Decay ──

def test_decay_weight_recent_is_one():
    from memory.decay import decay_weight
    now = 1_000_000_000_000
    assert decay_weight(None, now) == pytest.approx(1.0)
    assert decay_weight(now, now) == pytest.approx(1.0)


def test_decay_weight_halflife_is_one_half():
    """半衰期定義：t = T_half 時，weight 應約 = 0.5。"""
    from memory.decay import decay_weight
    now = 1_000_000_000_000
    half = 10.0
    one_half_ago = now - int(half * 24 * 3600 * 1000)
    w = decay_weight(one_half_ago, now, half_life_days=half, floor=0.0)
    assert w == pytest.approx(0.5, abs=1e-6)


def test_decay_floor_prevents_zero():
    from memory.decay import decay_weight
    now = 1_000_000_000_000
    long_ago = now - int(10_000 * 24 * 3600 * 1000)
    w = decay_weight(long_ago, now, half_life_days=1.0, floor=0.25)
    assert w == pytest.approx(0.25)


def test_retrieve_with_decay_reorders(tmp_store, monkeypatch):
    """同分情況下，常使用的應排在前面。我們用兩筆同 summary 體驗（不可能，
    sha 一樣會去重），改用 BM25 同分的兩筆，再人工灌 last_used_at。"""
    monkeypatch.setenv("PI_DECAY", "1")
    monkeypatch.setenv("PI_DECAY_HALFLIFE_DAYS", "1")
    from memory.core import capture, retrieve, make_observation, _get_store
    capture(make_observation("alpha beta"))
    capture(make_observation("alpha gamma"))
    store = _get_store()
    now_ms = int(time.time() * 1000)
    old = now_ms - 10 * 24 * 3600 * 1000  # 10 天前
    # 把第一筆設為「久未使用」、第二筆「剛用過」
    items = store.all()
    store.update(items[0]["id"], last_used_at=old)
    store.update(items[1]["id"], last_used_at=now_ms)
    hits = retrieve("alpha", 2)
    # 兩筆對 "alpha" BM25 分數相同（單字、同長度）→ decay 後第二筆勝出
    assert len(hits) == 2
    assert hits[0]["summary"] == "alpha gamma"


# ── 任務二 A：Hybrid (bm25_only fallback) ──

def test_hybrid_search_bm25_only_matches_bm25(tmp_store):
    from memory.bm25 import bm25_search
    from memory.hybrid import hybrid_search
    docs = [
        {"id": "d1", "text": "this project uses pnpm test"},
        {"id": "d2", "text": "the project readme is in docs"},
        {"id": "d3", "text": "run pnpm test before commit"},
    ]
    a = bm25_search("pnpm test", docs, 3)
    b = hybrid_search("pnpm test", docs, k=3, bm25_only=True)
    assert [x["id"] for x in a] == [x["id"] for x in b]


def test_hybrid_empty_docs():
    from memory.hybrid import hybrid_search
    assert hybrid_search("x", [], 5) == []


# ── 任務二 D：/recall + /forget CLI 入口 ──

def test_cli_list_and_forget(tmp_store, monkeypatch, capsys):
    from memory import core as core_mod
    core_mod.set_memory_path(tmp_store)
    monkeypatch.setenv("PI_MEMORY_PATH", tmp_store)
    from memory.cli import main as cli_main

    cli_main(["capture", "--summary", "use pnpm not npm"])
    cli_main(["capture", "--summary", "deploy with docker"])
    out = capsys.readouterr().out

    cli_main(["list"])
    out = capsys.readouterr().out
    assert "Total: 2" in out
    assert "pnpm" in out

    cli_main(["list", "--query", "pnpm"])
    out = capsys.readouterr().out
    assert "Total: 1" in out

    cli_main(["forget", "--summary", "use pnpm not npm"])
    out = capsys.readouterr().out
    assert "Forgotten." in out

    cli_main(["list"])
    out = capsys.readouterr().out
    assert "Total: 1" in out
    assert "pnpm" not in out


def test_cli_forget_missing_prints_no_op(tmp_store, capsys, monkeypatch):
    from memory import core as core_mod
    core_mod.set_memory_path(tmp_store)
    monkeypatch.setenv("PI_MEMORY_PATH", tmp_store)
    from memory.cli import main as cli_main
    cli_main(["forget", "--summary", "never seen this"])
    out = capsys.readouterr().out
    assert "查無" in out


def test_cli_retrieve_emits_json(tmp_store, capsys, monkeypatch):
    from memory import core as core_mod
    core_mod.set_memory_path(tmp_store)
    from memory.cli import main as cli_main
    cli_main(["capture", "--summary", "use pnpm not npm"])
    capsys.readouterr()
    cli_main(["retrieve", "--query", "pnpm"])
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert isinstance(data, list) and len(data) == 1
    assert "pnpm" in data[0]["summary"]
