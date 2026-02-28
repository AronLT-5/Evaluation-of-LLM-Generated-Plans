from __future__ import annotations

DATASET_HUMANEVAL = "humaneval"
DATASET_SWEBENCH_VERIFIED = "swebench_verified"
DATASET_REFACTORBENCH_PY = "refactorbench_py"

DATASET_NAMES = (
    DATASET_HUMANEVAL,
    DATASET_SWEBENCH_VERIFIED,
    DATASET_REFACTORBENCH_PY,
)

BATCH_NUMBERS = (1, 2, 3)
PLANS_PER_BATCH = 4
TOTAL_PLANS_PER_TASK = 12

DEFAULT_LABEL_SETS: dict[str, list[str]] = {
    DATASET_HUMANEVAL: [
        "Spec-First",
        "Examples-First",
        "Edge-Cases-First",
        "Invariants-First",
        "Pseudocode-First",
        "Decompose-Then-Solve",
        "Brute-Force-Then-Optimize",
        "Type-Driven",
        "Complexity-Guardrails",
        "Test-Design-Mental",
        "Failure-Modes-First",
        "Minimal-Solution-First",
    ],
    DATASET_SWEBENCH_VERIFIED: [
        "Reproduce-First",
        "Minimal-Failing-Test",
        "Stacktrace-Guided",
        "Search-And-Trace",
        "Config-Dependency-Check",
        "Docs-Spec-First",
        "Logging-Instrumentation",
        "Git-Blame-Regression",
        "Patch-Minimization",
        "Refactor-Then-Fix",
        "Add-Regression-Test",
        "Risk-Assessment-First",
    ],
    DATASET_REFACTORBENCH_PY: [
        "Behavior-Preservation-First",
        "Characterization-Tests-First",
        "Small-Commits-Plan",
        "Extract-Function-Focus",
        "Simplify-Control-Flow",
        "Remove-Duplication",
        "Clarify-Names-Interfaces",
        "Data-Structure-Cleanup",
        "Reduce-Coupling",
        "Incremental-Refactor-Loop",
        "Lint-Format-First",
        "Performance-Safe-Refactor",
    ],
}

HUMANEVAL_EXCLUDED_TASK_TEXT_KEYS = {"canonical_solution", "test"}
SWEBENCH_EXCLUDED_TASK_TEXT_KEYS = {"patch", "test_patch"}
REFACTORBENCH_EXCLUDED_PATTERNS = ("refactored", "target", "after", "gold", "solution")

PLACEHOLDER_TERMS = ("tbd", "todo", "fill in", "unknown")
TRUNCATION_MARKER = "\n...[TRUNCATED]...\n"
