#!/usr/bin/env python3
"""Evidence: path-scoped rule injection for Bifrost (task-4.2)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "bifrost"))

from companion.context.rules import load_rules, get_matching_rules


# ── load_rules: returns all rules ────────────────────────────────────────

all_rules = load_rules()
assert len(all_rules) == 3, f"Expected 3 valid rules, got {len(all_rules)}: {[r['file'] for r in all_rules]}"

rule_files = {r["file"] for r in all_rules}
assert "python-rules.md" in rule_files, repr(rule_files)
assert "global-rules.md" in rule_files, repr(rule_files)
assert "frontend-rules.md" in rule_files, repr(rule_files)
# Malformed rule is skipped (warning logged)
assert "malformed.md" not in rule_files, repr(rule_files)

# ── get_matching_rules: path-scoped matching ────────────────────────────

# Python file should match python-rules.md (paths: ["**/*.py"])
# and global-rules.md (no paths → always matches)
py_matches = get_matching_rules("src/foo/bar.py")
py_filenames = {r["file"] for r in py_matches}
assert "python-rules.md" in py_filenames, f"Missing python-rules: {py_filenames}"
assert "global-rules.md" in py_filenames, f"Missing global: {py_filenames}"
assert "frontend-rules.md" not in py_filenames, f"Unexpected frontend: {py_filenames}"

# JSX file should match frontend-rules.md and global-rules.md
jsx_matches = get_matching_rules("src/components/Button.tsx")
jsx_filenames = {r["file"] for r in jsx_matches}
assert "frontend-rules.md" in jsx_filenames, f"Missing frontend: {jsx_filenames}"
assert "global-rules.md" in jsx_filenames, f"Missing global: {jsx_filenames}"

# CSS file should match frontend-rules.md
css_matches = get_matching_rules("src/styles/app.css")
css_filenames = {r["file"] for r in css_matches}
assert "frontend-rules.md" in css_filenames, f"Missing frontend: {css_filenames}"

# Unrelated file should match only global rules
txt_matches = get_matching_rules("README.md")
txt_filenames = {r["file"] for r in txt_matches}
assert txt_filenames == {"global-rules.md"}, f"Expected only global, got: {txt_filenames}"

# ── edge cases ──────────────────────────────────────────────────────────

# Non-existent rules dir → empty list via load_rules
# This can't be tested easily without removing the dir, but the code handles
# it by walking up from CWD.

# Verify rule content is preserved
global_rule = next(r for r in all_rules if r["file"] == "global-rules.md")
assert "Always write tests" in global_rule["content"]
assert global_rule["paths"] == []

py_rule = next(r for r in all_rules if r["file"] == "python-rules.md")
assert "Always use type hints" in py_rule["content"]
assert py_rule["paths"] == ["**/*.py"]

print("All assertions passed.")
print(f"  total rules loaded: {len(all_rules)}")
print(f"  python file matches: {len(py_matches)} rules")
print(f"  jsx file matches: {len(jsx_matches)} rules")
print(f"  css file matches: {len(css_matches)} rules")
print(f"  txt file matches: {len(txt_matches)} rules")
print(f"  malformed.md correctly skipped")
