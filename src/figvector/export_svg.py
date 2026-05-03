from __future__ import annotations

from xml.sax.saxutils import escape

from .models import Primitive, SceneGraph, TextBlock


def export_svg(scene: SceneGraph) -> str:
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{scene.width}" height="{scene.height}" viewBox="0 0 {scene.width} {scene.height}" fill="none">',
        "  <defs>",
        '    <marker id="arrowhead" markerWidth="12" markerHeight="8" refX="10" refY="4" orient="auto">',
        '      <path d="M0,0 L12,4 L0,8 Z" fill="currentColor" />',
        "    </marker>",
        "  </defs>",
        f'  <rect width="{scene.width}" height="{scene.height}" fill="{_css_color(scene.background)}" />',
    ]

    for index, primitive in enumerate(scene.primitives, start=1):
        lines.extend(_primitive_to_svg(index, primitive))
    for index, text_block in enumerate(scene.texts, start=1):
        lines.extend(_text_to_svg(index, text_block))

    lines.append("</svg>")
    return "\n".join(lines)


def _primitive_to_svg(index: int, primitive: Primitive) -> list[str]:
    bbox = primitive.bbox
    stroke = _css_color(_darken(primitive.color, 0.28))
    fill = _css_color(primitive.color)
    alpha = primitive.color[3] / 255 if primitive.color[3] else 1.0
    primitive_id = str(primitive.metadata.get("id", f"primitive-{index}"))
    relation_attrs = []
    if "connects_from" in primitive.metadata:
        relation_attrs.append(f'data-figvector-from="{escape(str(primitive.metadata["connects_from"]))}"')
    if "connects_to" in primitive.metadata:
        relation_attrs.append(f'data-figvector-to="{escape(str(primitive.metadata["connects_to"]))}"')
    if "group_with" in primitive.metadata:
        relation_attrs.append(f'data-figvector-group-with="{escape(str(primitive.metadata["group_with"]))}"')
    common = (
        f'data-figvector-kind="{escape(primitive.kind)}" '
        f'data-figvector-confidence="{primitive.confidence:.2f}" '
        f'id="{primitive_id}"'
    )
    if relation_attrs:
        common = f"{common} {' '.join(relation_attrs)}"

    if primitive.kind == "rectangle":
        return [
            f'  <rect {common} x="{bbox.x}" y="{bbox.y}" width="{bbox.width}" height="{bbox.height}" rx="10" fill="{fill}" fill-opacity="{alpha:.3f}" stroke="{stroke}" stroke-width="2" />'
        ]
    if primitive.kind == "ellipse":
        cx, cy = bbox.center
        return [
            f'  <ellipse {common} cx="{cx:.1f}" cy="{cy:.1f}" rx="{bbox.width / 2:.1f}" ry="{bbox.height / 2:.1f}" fill="{fill}" fill-opacity="{alpha:.3f}" stroke="{stroke}" stroke-width="2" />'
        ]
    if primitive.kind == "line":
        x1, y1, x2, y2 = _line_endpoints(primitive)
        stroke_width = max(2, min(bbox.width, bbox.height))
        return [
            f'  <line {common} x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{stroke_width}" stroke-linecap="round" />'
        ]
    if primitive.kind == "arrow":
        x1, y1, x2, y2 = _arrow_endpoints(primitive)
        stroke_width = max(2, min(bbox.width, bbox.height) // 2)
        return [
            f'  <line {common} x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{stroke_width}" stroke-linecap="round" marker-end="url(#arrowhead)" />'
        ]
    if primitive.kind == "polyline":
        points = primitive.metadata.get("points", [])
        if isinstance(points, list) and len(points) >= 2:
            stroke_width = max(2, min(bbox.width, bbox.height) // 3)
            encoded = " ".join(f"{point[0]},{point[1]}" for point in points)
            return [
                f'  <polyline {common} points="{encoded}" stroke="{stroke}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" fill="none" />'
            ]
    return [
        f'  <rect {common} x="{bbox.x}" y="{bbox.y}" width="{bbox.width}" height="{bbox.height}" fill="none" stroke="{stroke}" stroke-width="2" stroke-dasharray="8 6" />'
    ]


def _text_to_svg(index: int, text_block: TextBlock) -> list[str]:
    bbox = text_block.bbox
    text_id = str(text_block.metadata.get("id", f"text-{index}"))
    attrs = [
        f'id="{text_id}"',
        'data-figvector-kind="text"',
        f'data-figvector-confidence="{text_block.confidence:.2f}"',
        f'data-figvector-source="{escape(text_block.source)}"',
    ]
    if "label_for" in text_block.metadata:
        attrs.append(f'data-figvector-label-for="{escape(str(text_block.metadata["label_for"]))}"')
    font_size = max(12, min(24, bbox.height))
    baseline = bbox.y + max(font_size, bbox.height - 2)
    return [
        f'  <text {" ".join(attrs)} x="{bbox.x}" y="{baseline}" fill="rgb(46, 50, 71)" font-size="{font_size}" font-family="Helvetica, Arial, sans-serif">{escape(text_block.text)}</text>'
    ]


def _line_endpoints(primitive: Primitive) -> tuple[float, float, float, float]:
    bbox = primitive.bbox
    if bbox.width >= bbox.height:
        y = bbox.y + bbox.height / 2.0
        return bbox.x, y, bbox.x2, y
    x = bbox.x + bbox.width / 2.0
    return x, bbox.y, x, bbox.y2


def _arrow_endpoints(primitive: Primitive) -> tuple[float, float, float, float]:
    bbox = primitive.bbox
    direction = str(primitive.metadata.get("direction", "right"))
    if direction == "left":
        y = bbox.y + bbox.height / 2.0
        return bbox.x2, y, bbox.x, y
    if direction == "up":
        x = bbox.x + bbox.width / 2.0
        return x, bbox.y2, x, bbox.y
    if direction == "down":
        x = bbox.x + bbox.width / 2.0
        return x, bbox.y, x, bbox.y2
    y = bbox.y + bbox.height / 2.0
    return bbox.x, y, bbox.x2, y


def _darken(color: tuple[int, int, int, int], amount: float) -> tuple[int, int, int, int]:
    factor = max(0.0, min(1.0, 1.0 - amount))
    return (
        int(color[0] * factor),
        int(color[1] * factor),
        int(color[2] * factor),
        color[3],
    )


def _css_color(color: tuple[int, int, int, int]) -> str:
    return f"rgb({color[0]}, {color[1]}, {color[2]})"
