from __future__ import annotations

from collections import Counter, defaultdict
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
    return evaluate_payload(scene.to_dict(), expected)


def evaluate_payload(payload: dict[str, Any], expected: dict[str, Any] | None) -> EvaluationResult | None:
    if not expected:
        return None

    checks: list[dict[str, Any]] = []
    primitive_counts = Counter(item.get("kind", "") for item in payload.get("primitives", []))
    relation_counts = Counter(item.get("kind", "") for item in payload.get("relations", []))
    text_values = [str(item.get("text", "")) for item in payload.get("texts", [])]
    relation_context = _build_relation_context(payload)

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
        actual = len(payload.get("primitives", []))
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
        actual = len(payload.get("texts", []))
        checks.append(
            {
                "name": "min_texts",
                "passed": actual >= int(min_texts),
                "expected": int(min_texts),
                "actual": actual,
            }
        )

    for item in expected.get("required_labels", []):
        checks.append(_check_required_label(item, relation_context))

    for item in expected.get("required_object_relations", []):
        checks.append(_check_required_object_relation(item, relation_context))

    for item in expected.get("required_group_members", []):
        checks.append(_check_required_group_member(item, relation_context))

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


def _build_relation_context(payload: dict[str, Any]) -> dict[str, Any]:
    primitives_by_id: dict[str, dict[str, Any]] = {}
    labels_by_primitive: dict[str, list[str]] = defaultdict(list)

    for primitive in payload.get("primitives", []):
        metadata = primitive.get("metadata", {})
        primitive_id = str(metadata.get("id", "")).strip()
        if primitive_id:
            primitives_by_id[primitive_id] = primitive

    for text_block in payload.get("texts", []):
        text = str(text_block.get("text", "")).strip()
        if not text:
            continue
        metadata = text_block.get("metadata", {})
        label_for = str(metadata.get("label_for", "")).strip()
        if label_for:
            labels_by_primitive[label_for].append(text)

    return {
        "primitives_by_id": primitives_by_id,
        "labels_by_primitive": {key: list(dict.fromkeys(values)) for key, values in labels_by_primitive.items()},
        "relations": payload.get("relations", []),
    }


def _check_required_label(item: dict[str, Any], relation_context: dict[str, Any]) -> dict[str, Any]:
    text = str(item.get("text", "")).strip()
    target_kind = str(item.get("target_kind", "")).strip()
    primitives_by_id = relation_context["primitives_by_id"]
    labels_by_primitive = relation_context["labels_by_primitive"]
    actual_targets: list[str] = []
    passed = False

    for primitive_id, labels in labels_by_primitive.items():
        if text not in labels:
            continue
        primitive = primitives_by_id.get(primitive_id)
        if primitive is None:
            continue
        actual_kind = str(primitive.get("kind", ""))
        actual_targets.append(f"{actual_kind}:{primitive_id}")
        if not target_kind or actual_kind == target_kind:
            passed = True

    expected_parts = [f"text={text}"]
    if target_kind:
        expected_parts.append(f"target_kind={target_kind}")
    return {
        "name": f"required_labels.{text or 'unknown'}",
        "passed": passed,
        "expected": ", ".join(expected_parts),
        "actual": actual_targets or [],
    }


def _check_required_object_relation(item: dict[str, Any], relation_context: dict[str, Any]) -> dict[str, Any]:
    kind = str(item.get("kind", "")).strip()
    source_text = str(item.get("source_text", "")).strip()
    target_text = str(item.get("target_text", "")).strip()
    source_kind = str(item.get("source_kind", "")).strip()
    target_kind = str(item.get("target_kind", "")).strip()
    primitives_by_id = relation_context["primitives_by_id"]
    labels_by_primitive = relation_context["labels_by_primitive"]

    passed = False
    actual_relations: list[str] = []
    for relation in relation_context["relations"]:
        actual_kind = str(relation.get("kind", "")).strip()
        if actual_kind != kind:
            continue
        source_id = str(relation.get("source_id", "")).strip()
        target_id = str(relation.get("target_id", "")).strip()
        source_primitive = primitives_by_id.get(source_id)
        target_primitive = primitives_by_id.get(target_id)
        if source_primitive is None or target_primitive is None:
            continue

        actual_source_kind = str(source_primitive.get("kind", "")).strip()
        actual_target_kind = str(target_primitive.get("kind", "")).strip()
        source_labels = labels_by_primitive.get(source_id, [])
        target_labels = labels_by_primitive.get(target_id, [])
        actual_relations.append(_semantic_relation_summary(actual_kind, source_labels, actual_source_kind, target_labels, actual_target_kind))

        if source_text and source_text not in source_labels:
            continue
        if target_text and target_text not in target_labels:
            continue
        if source_kind and source_kind != actual_source_kind:
            continue
        if target_kind and target_kind != actual_target_kind:
            continue
        passed = True

    expected_parts = [f"kind={kind}"]
    if source_text:
        expected_parts.append(f"source_text={source_text}")
    if target_text:
        expected_parts.append(f"target_text={target_text}")
    if source_kind:
        expected_parts.append(f"source_kind={source_kind}")
    if target_kind:
        expected_parts.append(f"target_kind={target_kind}")
    return {
        "name": f"required_object_relations.{kind or 'unknown'}",
        "passed": passed,
        "expected": ", ".join(expected_parts),
        "actual": actual_relations or [],
    }


def _check_required_group_member(item: dict[str, Any], relation_context: dict[str, Any]) -> dict[str, Any]:
    container_text = str(item.get("container_text", "")).strip()
    member_text = str(item.get("member_text", "")).strip()
    member_kind = str(item.get("member_kind", "")).strip()
    container_kind = str(item.get("container_kind", "")).strip()
    primitives_by_id = relation_context["primitives_by_id"]
    labels_by_primitive = relation_context["labels_by_primitive"]

    container_matches: list[str] = []
    member_matches: list[str] = []
    passed = False

    for relation in relation_context["relations"]:
        if str(relation.get("kind", "")).strip() != "group_with":
            continue
        container_id = str(relation.get("source_id", "")).strip()
        member_id = str(relation.get("target_id", "")).strip()
        container = primitives_by_id.get(container_id)
        member = primitives_by_id.get(member_id)
        if container is None or member is None:
            continue

        actual_container_kind = str(container.get("kind", "")).strip()
        actual_member_kind = str(member.get("kind", "")).strip()
        container_labels = labels_by_primitive.get(container_id, [])
        member_labels = labels_by_primitive.get(member_id, [])
        container_matches.append(
            _semantic_relation_summary(
                "group_with",
                container_labels,
                actual_container_kind,
                member_labels,
                actual_member_kind,
            )
        )

        if container_text and container_text not in container_labels:
            continue
        if member_text and member_text not in member_labels:
            continue
        if container_kind and container_kind != actual_container_kind:
            continue
        if member_kind and member_kind != actual_member_kind:
            continue
        passed = True
        member_matches.append(member_id)

    expected_parts = ["kind=group_with"]
    if container_text:
        expected_parts.append(f"container_text={container_text}")
    if member_text:
        expected_parts.append(f"member_text={member_text}")
    if container_kind:
        expected_parts.append(f"container_kind={container_kind}")
    if member_kind:
        expected_parts.append(f"member_kind={member_kind}")
    return {
        "name": f"required_group_members.{member_text or 'unknown'}",
        "passed": passed,
        "expected": ", ".join(expected_parts),
        "actual": member_matches or container_matches or [],
    }


def _semantic_relation_summary(
    kind: str,
    source_labels: list[str],
    source_kind: str,
    target_labels: list[str],
    target_kind: str,
) -> str:
    source_name = "|".join(source_labels) if source_labels else source_kind
    target_name = "|".join(target_labels) if target_labels else target_kind
    return f"{kind}({source_name}->{target_name})"
