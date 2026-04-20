from __future__ import annotations

from xml.sax.saxutils import escape

from .models import Primitive, Relation, SceneGraph, TextBlock


DRAWIO_HEADER = (
    '<mxfile host="app.diagrams.net" agent="FigVector" version="1.0">'
    '<diagram id="figvector" name="FigVector">'
    '<mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1600" pageHeight="1200" math="0" shadow="0">'
    '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
)
DRAWIO_FOOTER = '</root></mxGraphModel></diagram></mxfile>'


def export_drawio(scene: SceneGraph) -> str:
    cells: list[str] = []
    for primitive in scene.primitives:
        if primitive.kind in {"arrow", "line", "polyline"} and "connects_from" in primitive.metadata and "connects_to" in primitive.metadata:
            continue
        cells.append(_vertex_cell(primitive))
    for text_block in scene.texts:
        cells.append(_text_cell(text_block))
    for index, relation in enumerate(scene.relations, start=1):
        cells.append(_edge_cell(index, scene, relation))
    return DRAWIO_HEADER + "".join(cells) + DRAWIO_FOOTER


def _vertex_cell(primitive: Primitive) -> str:
    primitive_id = str(primitive.metadata.get("id", "primitive"))
    bbox = primitive.bbox
    fill = _hex_color(primitive.color)
    stroke = _hex_color(_darken(primitive.color, 0.28))
    style = 'rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};'.format(fill=fill, stroke=stroke)
    if primitive.kind == "ellipse":
        style += 'ellipse;'
    elif primitive.kind == "region":
        style += 'dashed=1;fillColor=none;'
    value = escape(str(primitive.metadata.get("label", primitive.kind)))
    return (
        f'<mxCell id="{escape(primitive_id)}" value="{value}" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{bbox.x}" y="{bbox.y}" width="{bbox.width}" height="{bbox.height}" as="geometry"/>'
        '</mxCell>'
    )


def _text_cell(text_block: TextBlock) -> str:
    text_id = str(text_block.metadata.get("id", "text"))
    bbox = text_block.bbox
    style = 'text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;whiteSpace=wrap;'
    return (
        f'<mxCell id="{escape(text_id)}" value="{escape(text_block.text)}" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{bbox.x}" y="{bbox.y}" width="{bbox.width}" height="{bbox.height}" as="geometry"/>'
        '</mxCell>'
    )


def _edge_cell(index: int, scene: SceneGraph, relation: Relation) -> str:
    style = 'edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#2E3247;'
    if relation.kind == 'flows_to':
        style += 'endArrow=block;endFill=1;'
    elif relation.kind == 'labels':
        style += 'dashed=1;endArrow=none;strokeColor=#66728F;'
    else:
        style += 'endArrow=none;'

    points = _edge_points_for_relation(scene, relation)
    geometry = '<mxGeometry relative="1" as="geometry">'
    if points:
        geometry += '<Array as="points">'
        for x, y in points:
            geometry += f'<mxPoint x="{x}" y="{y}"/>'
        geometry += '</Array>'
    geometry += '</mxGeometry>'

    return (
        f'<mxCell id="edge-{index}" value="" style="{style}" edge="1" parent="1" '
        f'source="{escape(relation.source_id)}" target="{escape(relation.target_id)}">'
        f'{geometry}'
        '</mxCell>'
    )


def _edge_points_for_relation(scene: SceneGraph, relation: Relation) -> list[tuple[int, int]]:
    for primitive in scene.primitives:
        if primitive.metadata.get('connects_from') != relation.source_id:
            continue
        if primitive.metadata.get('connects_to') != relation.target_id:
            continue
        if primitive.kind != 'polyline':
            return []
        points = primitive.metadata.get('points', [])
        if not isinstance(points, list) or len(points) <= 2:
            return []
        return [(int(point[0]), int(point[1])) for point in points[1:-1]]
    return []


def _darken(color: tuple[int, int, int, int], amount: float) -> tuple[int, int, int, int]:
    factor = max(0.0, min(1.0, 1.0 - amount))
    return (
        int(color[0] * factor),
        int(color[1] * factor),
        int(color[2] * factor),
        color[3],
    )


def _hex_color(color: tuple[int, int, int, int]) -> str:
    return '#{0:02X}{1:02X}{2:02X}'.format(color[0], color[1], color[2])
