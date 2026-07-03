#!/usr/bin/env python3
"""
Deterministic SemVer core for the open-semver-advisor skill.

Given the full source of two versions of a Python module (`old_code`, `new_code`), this module
extracts each version's PUBLIC API surface via `ast` and computes the required SemVer bump
(`major` / `minor` / `patch`) by a fixed, documented rule set. Both classify.py (the skill's
in-loop harness) and evaluate.py (the grader-facing scorer) import these helpers, so the rule
is defined in exactly one place — there are no hidden assumptions (spec §共通原則 #5).

PUBLIC SYMBOL SET
-----------------
- module-level functions whose name does not start with "_"
- module-level classes whose name does not start with "_"
- for each public class: its methods whose name does not start with "_", plus "__init__"

SIGNATURE (per function / method)
---------------------------------
- accepted: the set of all parameter names the callable accepts by name
- required: the number of parameters with no default (positional-or-keyword + positional-only +
  required keyword-only), i.e. the args a caller MUST supply
- has_varargs / has_kwargs: whether it declares *args / **kwargs

BUMP RULES (old -> new), first match wins
-----------------------------------------
MAJOR (a previously-valid call could now break):
  - a public symbol present in old is removed in new
  - a public class loses a public method (or its __init__)
  - a function/method signature changes incompatibly:
      * an accepted parameter name in old is no longer accepted in new, or
      * required count increases, or
      * *args or **kwargs present in old is removed in new
MINOR (backward-compatible addition), if no MAJOR change:
  - a new public symbol is added (function / class / method)
  - an existing function/method gains a new optional parameter (accepted grows, required same)
  - *args or **kwargs is newly added
PATCH:
  - none of the above — public API surface unchanged (only bodies / private symbols changed)
"""

from __future__ import annotations

import ast


def _sig(node) -> dict:
    """Build a signature descriptor from a FunctionDef/AsyncFunctionDef ast node."""
    a = node.args
    posonly = list(a.posonlyargs)
    pos = list(a.args)
    kwonly = list(a.kwonlyargs)
    accepted = {p.arg for p in posonly + pos + kwonly}
    # required positional-or-positional-only: those without defaults.
    pos_all = posonly + pos
    n_pos_defaults = len(a.defaults)
    required_pos = len(pos_all) - n_pos_defaults
    # required keyword-only: kw_defaults entries that are None
    required_kw = sum(1 for d in a.kw_defaults if d is None)
    required = max(0, required_pos) + required_kw
    return {
        "accepted": accepted,
        "required": required,
        "has_varargs": a.vararg is not None,
        "has_kwargs": a.kwarg is not None,
    }


def _public_methods(cls: ast.ClassDef) -> dict:
    out = {}
    for n in cls.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not n.name.startswith("_") or n.name == "__init__":
                out[n.name] = _sig(n)
    return out


def _safe_parse(source: str):
    """
    Parse `source`, returning (tree, error_msg). If the raw parse fails, retry on progressively
    repaired copies that undo the ways a weak LLM over-escapes code inside a JSON argv:
      1. over-escaped whitespace: literal '\\n'/'\\t'/'\\r' -> real newline/tab;
      2. over-escaped quotes:     stray '\\"' / "\\'" -> '"' / "'" (e.g. unit=\\"cm\\").
    Each repair is only ATTEMPTED after the raw parse already failed, and is only ACCEPTED if it
    then parses cleanly, so well-formed source is never altered. Observed across models: gemma4
    relays clean `\\n`; some models (e.g. llama3.1) emit `\\n` + `\\"` together — (2) recovers those.
    """
    src = source or ""
    try:
        return ast.parse(src), ""
    except SyntaxError as raw_err:
        ws = src.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\n")
        for repaired in (ws, ws.replace('\\"', '"').replace("\\'", "'")):
            if repaired != src:
                try:
                    return ast.parse(repaired), ""
                except SyntaxError:
                    continue
        return None, f"syntax error: {raw_err}"


def public_api(source: str) -> dict:
    """
    Return {"functions": {name: sig}, "classes": {name: {method: sig}}, "_error": optional}.
    On a syntax error (even after recovery), returns {"_error": msg} so callers can surface it
    deterministically.
    """
    tree, err = _safe_parse(source)
    if tree is None:
        return {"functions": {}, "classes": {}, "_error": err}
    functions, classes = {}, {}
    for node in tree.body:  # module-level only
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                functions[node.name] = _sig(node)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                classes[node.name] = _public_methods(node)
    return {"functions": functions, "classes": classes}


def _sig_change(old: dict, new: dict) -> str:
    """Compare two signatures -> 'breaking' | 'additive' | 'none'."""
    # breaking: an accepted name disappeared, required count grew, or *args/**kwargs removed
    if (old["accepted"] - new["accepted"]) \
            or new["required"] > old["required"] \
            or (old["has_varargs"] and not new["has_varargs"]) \
            or (old["has_kwargs"] and not new["has_kwargs"]):
        return "breaking"
    # additive: new accepted names, or *args/**kwargs newly added
    if (new["accepted"] - old["accepted"]) \
            or (new["has_varargs"] and not old["has_varargs"]) \
            or (new["has_kwargs"] and not old["has_kwargs"]):
        return "additive"
    return "none"


def diff_api(old_api: dict, new_api: dict) -> dict:
    """Return structured change lists: removed/added/changed symbols and per-change severity."""
    changes = {"breaking": [], "additive": []}

    of, nf = old_api.get("functions", {}), new_api.get("functions", {})
    for name in of:
        if name not in nf:
            changes["breaking"].append(f"function removed: {name}")
        else:
            c = _sig_change(of[name], nf[name])
            if c == "breaking":
                changes["breaking"].append(f"function signature breaking: {name}")
            elif c == "additive":
                changes["additive"].append(f"function gained optional param/varargs: {name}")
    for name in nf:
        if name not in of:
            changes["additive"].append(f"function added: {name}")

    oc, nc = old_api.get("classes", {}), new_api.get("classes", {})
    for name in oc:
        if name not in nc:
            changes["breaking"].append(f"class removed: {name}")
        else:
            om, nm = oc[name], nc[name]
            for m in om:
                if m not in nm:
                    changes["breaking"].append(f"method removed: {name}.{m}")
                else:
                    c = _sig_change(om[m], nm[m])
                    if c == "breaking":
                        changes["breaking"].append(f"method signature breaking: {name}.{m}")
                    elif c == "additive":
                        changes["additive"].append(f"method gained optional param/varargs: {name}.{m}")
            for m in nm:
                if m not in om:
                    changes["additive"].append(f"method added: {name}.{m}")
    for name in nc:
        if name not in oc:
            changes["additive"].append(f"class added: {name}")
    return changes


def classify(old_code: str, new_code: str) -> dict:
    """
    Compute the required SemVer bump from two source versions.
    Returns {"bump": "major"|"minor"|"patch", "changes": {...}, "error": ""}.
    A syntax error in either source yields bump="" and a non-empty error.
    """
    old_api = public_api(old_code)
    new_api = public_api(new_code)
    if "_error" in old_api or "_error" in new_api:
        return {"bump": "", "changes": {"breaking": [], "additive": []},
                "error": old_api.get("_error") or new_api.get("_error")}
    changes = diff_api(old_api, new_api)
    if changes["breaking"]:
        bump = "major"
    elif changes["additive"]:
        bump = "minor"
    else:
        bump = "patch"
    return {"bump": bump, "changes": changes, "error": ""}
