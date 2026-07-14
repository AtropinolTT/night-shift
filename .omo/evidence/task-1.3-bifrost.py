#!/usr/bin/env python3
"""Evidence: Bifrost companion config loader (task-1.3)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "bifrost"))

from companion.config import load_config

c = load_config()

assert c.max_context_tokens == 8000
assert c.model_for_classifier == "deepseek-v4-flash"
assert c.model_for_fusion_synthesis == "deepseek-v4-pro"
assert c.max_turns_default == 10
assert c.cost_ceiling_default == 1.00
assert isinstance(c.allowlisted_bash_commands, list)
assert all(isinstance(x, str) for x in c.allowlisted_bash_commands)
assert "ls" in c.allowlisted_bash_commands

print("All assertions passed.")
print(f"  max_context_tokens = {c.max_context_tokens}")
print(f"  model_for_classifier = {c.model_for_classifier}")
print(f"  model_for_fusion_synthesis = {c.model_for_fusion_synthesis}")
print(f"  max_turns_default = {c.max_turns_default}")
print(f"  cost_ceiling_default = {c.cost_ceiling_default}")
print(f"  allowlisted_bash_commands ({len(c.allowlisted_bash_commands)} items)")
