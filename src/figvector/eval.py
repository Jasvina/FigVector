from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .models import SceneGraph


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    score: float
    checks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "checks": self.checks,
        }


def evaluate_scene(scene: SceneGraph, expected: dict[str, Any] | None) -> EvaluationResult | None:
    if not expected:
        return None

    checks: list[dict[str, Any]] = []
    primitive_counts = Counter(primitive.kind for primitive in scene.primitives)
    relation_counts = Counter(relation.kind for relation in scene.relations)
    text_values = [text_block.text for text_block in scene.texts]

    for kind, expected_count in expected.get("primitive_counts", {}).items():
        actual_count = primitive_counts.get(kind, 0)
        checks.append(_check_equals(f"primitive_counts.{kind}", expected_count, actual_count))

    for kind, expected_count in expected.get("relation_counts", {}).items():
        actual_count = relation_counts.get(kind, 0)
        checks.append(_check_equals(f"relation_counts.{kind}", expected_count, actual_count))

    for text in expected.get("required_texts", []):
        checks.append(
            {
                "name": f"required_texts.{text}",
                "passed": text in text_values,
                "expected": text,
                "actual": text_values,
            }
        )

    minimum = expected.get("min_primitives")
    if minimum is not None:
        actual = len(scene.primitives)
        checks.append(
            {
                "name": "min_primitives",
                "passed": actual >= int(minimum),
                "expected": int(minimum),
                "actual": actual,
            }
        )

    min_texts = expected.get("min_texts")
    if min_texts is not None:
        actual = len(scene.texts)
        checks.append(
            {
                "name": "min_texts",
                "passed": actual >= int(min_texts),
                "expected": int(min_texts),
                "actual": actual,
            }
        )

    if not checks:
        return EvaluationResult(passed=True, score=1.0, checks=[])

    passed_count = sum(1 for check in checks if check["passed"])
    return EvaluationResult(
        passed=passed_count == len(checks),
        score=round(passed_count / len(checks), 3),
        checks=checks,
    )


def _check_equals(name: str, expected: int, actual: int) -> dict[str, Any]:
    return {
        "name": name,
        "passed": int(expected) == int(actual),
        "expected": int(expected),
        "actual": int(actual),
    }
