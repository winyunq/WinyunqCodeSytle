# Maintenance contract for this tool

Use `.agents/skills/ue-maintenance/SKILL.md` when maintaining a user's project.
Do not interpret a content import as permission to change runtime systems. Do not bypass profile, locks, or approvals using shell or direct database edits.

When modifying this tool: preserve the four public tools and their tests. Prefer existing `doxygenue` mechanisms for source ranges, document parsing, transactions and function diff. Do not replace them with another parser to fix a facade issue. New data adapters must preserve omitted values, expose real failures and include destructive negative tests. No test double may be reachable from the shipping MCP.

Tests: `python tools/run_tests.py`. Code tests require real Doxygen and g++/clang++; report skips. `tools/replay.py` runs the real stdio tasks and saves evidence. An Unreal API contract test is not evidence of execution in Unreal.
