#!/usr/bin/env python3
"""Generate the embedded Fusion resources for Quark framed-glass mosaic CT."""

from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from itertools import product
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
RESOURCES_DIR = PROJECT_DIR / "src" / "main" / "resources"
DEFAULT_QUARK_JAR = PROJECT_DIR.parent / "minecraft" / "mods" / "Quark-4.1-480.jar"
NAMESPACE = "quark_framed_glass_ct"
VARIANTS = (
    "",
    "white",
    "orange",
    "magenta",
    "light_blue",
    "yellow",
    "lime",
    "pink",
    "gray",
    "light_gray",
    "cyan",
    "purple",
    "blue",
    "brown",
    "green",
    "red",
    "black",
)
# Keep translucent quads deterministically separated without visible parallax.
OVERLAY_OFFSET = 0.002
PANE_MODEL_SUFFIXES = (
    "post",
    "noside",
    "noside_alt",
    "side_north",
    "side_east",
    "side_south",
    "side_west",
)
PANE_TEMPLATES = {
    "post": "minecraft:block/template_glass_pane_post",
    "noside": "minecraft:block/template_glass_pane_noside",
    "noside_alt": "minecraft:block/template_glass_pane_noside_alt",
    "side_north": "minecraft:block/template_glass_pane_side",
    "side_east": "minecraft:block/template_glass_pane_side",
    "side_south": "minecraft:block/template_glass_pane_side_alt",
    "side_west": "minecraft:block/template_glass_pane_side_alt",
}

DIRECTION_TILES = {
    "top": {9, 10, 11, 13, 15, 16, 17},
    "right": {3, 4, 6, 9, 10, 15, 16},
    "bottom": {1, 3, 4, 5, 9, 10, 11},
    "left": {4, 5, 8, 10, 11, 16, 17},
}
DIRECTION_BITS = {"top": 0, "right": 2, "bottom": 4, "left": 6}
PIECED_REMOVED_EDGES = {
    0: set(),
    1: {"top", "right", "bottom", "left"},
    2: {"top", "bottom"},
    3: {"right", "left"},
    4: {"top", "right", "bottom", "left"},
}


def name(variant: str) -> str:
    return f"{variant}_framed_glass" if variant else "framed_glass"


def block_id(variant: str) -> str:
    return f"quark:{name(variant)}"


def pane_name(variant: str) -> str:
    return f"{name(variant)}_pane"


def pane_id(variant: str) -> str:
    return f"quark:{pane_name(variant)}"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def match_block(variant: str) -> dict[str, Any]:
    return {"type": "match_block", "block": block_id(variant)}


def match_group() -> dict[str, Any]:
    # Fusion 1.3.2+b only retains the final entry of a `blocks` array.
    return {"type": "or", "predicates": [match_block(variant) for variant in VARIANTS]}


def match_pane(variant: str) -> dict[str, Any]:
    return {"type": "fusion:match_block", "block": pane_id(variant)}


def match_pane_group() -> dict[str, Any]:
    return {"type": "fusion:or", "predicates": [match_pane(variant) for variant in VARIANTS]}


def retarget_pane_connection(value: Any, targets: tuple[str, ...]) -> Any:
    if isinstance(value, list):
        return [retarget_pane_connection(item, targets) for item in value]
    if not isinstance(value, dict):
        return value

    predicate_type = value.get("type", "").removeprefix("fusion:")
    if predicate_type in {"is_same_block", "match_block"}:
        predicates = [match_pane(variant) for variant in targets]
        return predicates[0] if len(predicates) == 1 else {"type": "fusion:or", "predicates": predicates}
    if predicate_type == "match_state":
        predicates = [
            {
                "type": "fusion:match_state",
                "block": pane_id(variant),
                "properties": deepcopy(value.get("properties", {})),
            }
            for variant in targets
        ]
        return predicates[0] if len(predicates) == 1 else {"type": "fusion:or", "predicates": predicates}

    return {
        key: retarget_pane_connection(item, targets)
        for key, item in value.items()
        if key not in {"block", "blocks"}
    }


def connected_component(mask: set[tuple[int, int]], seed: tuple[int, int]) -> set[tuple[int, int]]:
    component = {seed}
    pending = [seed]
    while pending:
        x, y = pending.pop()
        for point in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if point in mask and point not in component:
                component.add(point)
                pending.append(point)
    return component


def find_lobe_masks(first: Image.Image, second: Image.Image) -> dict[str, set[tuple[int, int]]]:
    colored = {
        (x, y)
        for y in range(16)
        for x in range(16)
        if first.getpixel((x, y)) != second.getpixel((x, y))
    }
    return {
        "top": connected_component(colored, (10, 1)),
        "right": connected_component(colored, (14, 10)),
        "bottom": connected_component(colored, (3, 14)),
        "left": connected_component(colored, (1, 3)),
    }


def expand_masks_over_removed_frame(
    masks: dict[str, set[tuple[int, int]]]
) -> dict[str, set[tuple[int, int]]]:
    expanded = {direction: set(points) for direction, points in masks.items()}
    for direction, points in expanded.items():
        for y in range(16):
            for x in range(16):
                if x not in (0, 15) and y not in (0, 15):
                    continue
                source_point = (min(14, max(1, x)), min(14, max(1, y)))
                if source_point in masks[direction]:
                    points.add((x, y))
    return expanded


def make_pieced_tiles(source: Image.Image) -> list[Image.Image]:
    source = source.convert("RGBA")
    if source.size != (16, 16):
        raise ValueError(f"Expected 16x16 Quark texture, got {source.size}")

    full = source.copy()
    no_edges = source.copy()
    for y in range(16):
        for x in range(16):
            if x in (0, 15) or y in (0, 15):
                no_edges.putpixel(
                    (x, y),
                    source.getpixel((min(14, max(1, x)), min(14, max(1, y)))),
                )

    vertical = source.copy()
    for x in range(1, 15):
        vertical.putpixel((x, 0), source.getpixel((x, 1)))
        vertical.putpixel((x, 15), source.getpixel((x, 14)))

    horizontal = source.copy()
    for y in range(1, 15):
        horizontal.putpixel((0, y), source.getpixel((1, y)))
        horizontal.putpixel((15, y), source.getpixel((14, y)))

    corners = no_edges.copy()
    for point in ((0, 0), (15, 0), (0, 15), (15, 15)):
        corners.putpixel(point, source.getpixel(point))
    return [full, no_edges, vertical, horizontal, corners]


def make_base_atlas(
    source: Image.Image,
    original_masks: dict[str, set[tuple[int, int]]],
    expanded_masks: dict[str, set[tuple[int, int]]],
) -> Image.Image:
    tiles = make_pieced_tiles(source)
    original_points = set().union(*original_masks.values())
    additions = {
        direction: expanded_masks[direction] - original_masks[direction]
        for direction in original_masks
    }
    for tile_index, tile in enumerate(tiles):
        clear = set(original_points)
        for direction in PIECED_REMOVED_EDGES[tile_index]:
            clear.update(additions[direction])
        for point in clear:
            tile.putpixel(point, (0, 0, 0, 0))

    atlas = Image.new("RGBA", (80, 16))
    for index, tile in enumerate(tiles):
        atlas.paste(tile, (index * 16, 0))
    return atlas


def make_overlay_atlas(
    source: Image.Image, masks: dict[str, set[tuple[int, int]]]
) -> Image.Image:
    atlas = Image.new("RGBA", (96, 48))
    for tile in range(18):
        for direction, direction_tiles in DIRECTION_TILES.items():
            if tile not in direction_tiles:
                continue
            for x, y in masks[direction]:
                atlas.putpixel(
                    (tile % 6 * 16 + x, tile // 6 * 16 + y),
                    source.getpixel((x, y)),
                )
    return atlas


def emitted_overlay_tiles(connections: tuple[bool, ...]) -> list[int]:
    top, top_right, right, bottom_right, bottom, bottom_left, left, top_left = connections
    if top and right and bottom and left:
        return [10]
    if not any(connections):
        return []

    tiles: list[int] = []
    if not left:
        if not top:
            if top_left:
                tiles.append(14)
        elif not right:
            tiles.append(13)
        elif not bottom:
            tiles.append(15)
        else:
            tiles.append(9)
    if not top:
        if not right:
            if top_right:
                tiles.append(12)
        elif not bottom:
            tiles.append(6)
        elif not left:
            tiles.append(3)
        else:
            tiles.append(4)
    if not right:
        if not bottom:
            if bottom_right:
                tiles.append(0)
        elif not left:
            tiles.append(1)
        elif not top:
            tiles.append(5)
        else:
            tiles.append(11)
    if not bottom:
        if not left:
            if bottom_left:
                tiles.append(2)
        elif not top:
            tiles.append(8)
        elif not right:
            tiles.append(17)
        else:
            tiles.append(16)
    return tiles


def overlay_elements() -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    axes = {
        "down": (1, False),
        "up": (1, True),
        "north": (2, False),
        "south": (2, True),
        "west": (0, False),
        "east": (0, True),
    }
    for direction, (axis, positive) in axes.items():
        start = [0, 0, 0]
        end = [16, 16, 16]
        if positive:
            end[axis] += OVERLAY_OFFSET
        else:
            start[axis] -= OVERLAY_OFFSET
        elements.append(
            {
                "from": start,
                "to": end,
                "faces": {direction: {"texture": "#all", "cullface": direction}},
            }
        )
    return elements


def make_base_model(variant: str) -> dict[str, Any]:
    return {
        "loader": "fusion:model",
        "type": "connecting",
        "parent": "minecraft:block/cube_all",
        "textures": {"all": f"{NAMESPACE}:block/{name(variant)}_base"},
        "connections": match_group(),
    }


def make_overlay_model(variant: str, fallback: bool) -> dict[str, Any]:
    connection = (
        {"type": "not", "predicate": match_group()}
        if fallback
        else match_block(variant)
    )
    suffix = "fallback" if fallback else "group"
    return {
        "loader": "fusion:model",
        "type": "connecting",
        "textures": {
            "all": f"{NAMESPACE}:block/{name(variant)}_{suffix}_overlay",
            "particle": "#all",
        },
        "connections": connection,
        "elements": overlay_elements(),
    }


def make_pane_blockstate(variant: str) -> dict[str, Any]:
    model = f"{NAMESPACE}:block/panes/{pane_name(variant)}"
    return {
        "multipart": [
            {"apply": {"model": f"{model}_post"}},
            {"when": {"north": "true"}, "apply": {"model": f"{model}_side_north"}},
            {"when": {"east": "true"}, "apply": {"model": f"{model}_side_east", "y": 90}},
            {"when": {"south": "true"}, "apply": {"model": f"{model}_side_south"}},
            {"when": {"west": "true"}, "apply": {"model": f"{model}_side_west", "y": 90}},
            {"when": {"north": "false"}, "apply": {"model": f"{model}_noside"}},
            {"when": {"east": "false"}, "apply": {"model": f"{model}_noside_alt"}},
            {"when": {"south": "false"}, "apply": {"model": f"{model}_noside_alt", "y": 90}},
            {"when": {"west": "false"}, "apply": {"model": f"{model}_noside", "y": 270}},
        ]
    }


def make_pane_model(variant: str, suffix: str) -> dict[str, Any]:
    if suffix.startswith("side_"):
        side = suffix.removeprefix("side_")
        connections = {
            "type": "fusion:or",
            "predicates": [
                {
                    "type": "fusion:and",
                    "predicates": [
                        {
                            "type": "fusion:match_state",
                            "block": pane_id(variant),
                            "properties": {side: ["true"]},
                        },
                        {"type": "fusion:is_direction", "directions": ["bottom", "top"]},
                    ],
                },
                {
                    "type": "fusion:and",
                    "predicates": [
                        match_pane(variant),
                        {
                            "type": "fusion:is_direction",
                            "directions": [
                                "bottom_left",
                                "bottom_right",
                                "left",
                                "right",
                                "top_left",
                                "top_right",
                            ],
                        },
                    ],
                },
            ],
        }
    else:
        connections = match_pane(variant)

    # Fusion 1.3.2 applies model rotations correctly only when pane predicates
    # retain the outer single-entry `or` used by its connecting-pane format.
    connections = {"type": "fusion:or", "predicates": [connections]}

    return {
        "loader": "fusion:model",
        "type": "fusion:connecting",
        "parent": PANE_TEMPLATES[suffix],
        "connections": connections,
        "textures": {
            "edge": "quark:block/framed_glass_pane_top",
            "pane": f"{NAMESPACE}:block/{name(variant)}_base",
        },
    }


def pane_overlay_elements(suffix: str) -> list[dict[str, Any]]:
    if suffix == "post":
        return []
    if suffix == "noside":
        elements = [
            {"from": [7, 0, 7], "to": [9, 16, 9], "faces": {"north": {"texture": "#pane"}}}
        ]
    elif suffix == "noside_alt":
        elements = [
            {"from": [7, 0, 7], "to": [9, 16, 9], "faces": {"east": {"texture": "#pane"}}}
        ]
    elif suffix in {"side_north", "side_east"}:
        elements = [
            {
                "from": [7, 0, 0],
                "to": [9, 16, 7],
                "faces": {"west": {"texture": "#pane"}, "east": {"texture": "#pane"}},
            }
        ]
    else:
        elements = [
            {
                "from": [7, 0, 9],
                "to": [9, 16, 16],
                "faces": {"west": {"texture": "#pane"}, "east": {"texture": "#pane"}},
            }
        ]

    overlays: list[dict[str, Any]] = []
    for source_element in elements:
        for direction, source_face in source_element.get("faces", {}).items():
            if source_face.get("texture") != "#pane":
                continue
            element = {key: deepcopy(value) for key, value in source_element.items() if key != "faces"}
            element["from"] = list(element["from"])
            element["to"] = list(element["to"])
            axis, positive = {
                "down": (1, False),
                "up": (1, True),
                "north": (2, False),
                "south": (2, True),
                "west": (0, False),
                "east": (0, True),
            }[direction]
            if positive:
                element["to"][axis] += OVERLAY_OFFSET
            else:
                element["from"][axis] -= OVERLAY_OFFSET
            face = deepcopy(source_face)
            face["texture"] = "#all"
            element["faces"] = {direction: face}
            overlays.append(element)
    return overlays


def make_pane_overlay_component(
    variant: str,
    connections: dict[str, Any],
    suffix: str,
    fallback: bool,
) -> dict[str, Any]:
    texture_suffix = "fallback" if fallback else "group"
    return {
        "loader": "fusion:model",
        "type": "fusion:connecting",
        "ambientocclusion": False,
        "textures": {
            "all": f"{NAMESPACE}:block/{name(variant)}_{texture_suffix}_overlay",
            "particle": "#all",
        },
        "connections": connections,
        "elements": pane_overlay_elements(suffix),
    }


def make_pane_composite_model(
    variant: str,
    base_model: dict[str, Any],
    suffix: str,
) -> dict[str, Any]:
    original_connections = base_model["connections"]
    group_connections = retarget_pane_connection(original_connections, VARIANTS)
    base_model = deepcopy(base_model)
    base_model["connections"] = group_connections

    if not pane_overlay_elements(suffix):
        return base_model

    components: list[dict[str, Any]] = [{"model": base_model}]
    for donor in VARIANTS:
        components.append(
            {
                "model": make_pane_overlay_component(
                    donor,
                    retarget_pane_connection(original_connections, (donor,)),
                    suffix,
                    False,
                )
            }
        )
    components.append(
        {
            "model": make_pane_overlay_component(
                variant,
                {"type": "fusion:not", "predicate": group_connections},
                suffix,
                True,
            )
        }
    )
    return {"loader": "fusion:model", "type": "fusion:composite", "models": components}


def validate(
    sources: dict[str, Image.Image],
    original_masks: dict[str, set[tuple[int, int]]],
    expanded_masks: dict[str, set[tuple[int, int]]],
) -> None:
    errors: list[str] = []
    if any(len(points) != 9 for points in original_masks.values()):
        errors.append("Every original lobe must contain 9 pixels")
    if any(len(points) != 14 for points in expanded_masks.values()):
        errors.append("Every expanded lobe must contain 14 pixels")
    if len(set().union(*expanded_masks.values())) != 56:
        errors.append("Expanded directional lobes must not overlap")

    for variant in VARIANTS:
        base_path = RESOURCES_DIR / "assets" / NAMESPACE / "textures" / "block" / f"{name(variant)}_base.png"
        base = Image.open(base_path).convert("RGBA")
        if base.size != (80, 16):
            errors.append(f"Wrong base atlas size for {variant or 'plain'}: {base.size}")
            continue

        original_points = set().union(*original_masks.values())
        expanded_points = set().union(*expanded_masks.values())
        for tile in range(5):
            for x, y in original_points:
                if base.getpixel((tile * 16 + x, y))[3] != 0:
                    errors.append(f"Base lobe is not reserved for {variant or 'plain'}, tile {tile}")
                    break

        fallback_atlas = Image.open(
            RESOURCES_DIR / "assets" / NAMESPACE / "textures" / "block" / f"{name(variant)}_fallback_overlay.png"
        ).convert("RGBA")
        group_atlas = Image.open(
            RESOURCES_DIR / "assets" / NAMESPACE / "textures" / "block" / f"{name(variant)}_group_overlay.png"
        ).convert("RGBA")
        no_edges = make_pieced_tiles(sources[variant])[1]
        for y in range(16):
            for x in range(16):
                isolated = (
                    fallback_atlas.getpixel((4 * 16 + x, 1 * 16 + y))
                    if (x, y) in original_points
                    else base.getpixel((x, y))
                )
                if isolated != sources[variant].getpixel((x, y)):
                    errors.append(f"Isolated texture does not reconstruct exactly for {variant or 'plain'}")
                    break
                fully_connected = (
                    group_atlas.getpixel((4 * 16 + x, 1 * 16 + y))
                    if (x, y) in expanded_points
                    else base.getpixel((16 + x, y))
                )
                if fully_connected != no_edges.getpixel((x, y)):
                    errors.append(f"Connected texture does not reconstruct exactly for {variant or 'plain'}")
                    break

        overlay_sources = {
            "group": make_pieced_tiles(sources[variant])[1],
            "fallback": sources[variant],
        }
        for suffix, masks in (("group", expanded_masks), ("fallback", original_masks)):
            atlas_path = RESOURCES_DIR / "assets" / NAMESPACE / "textures" / "block" / f"{name(variant)}_{suffix}_overlay.png"
            atlas = Image.open(atlas_path).convert("RGBA")
            if atlas.size != (96, 48):
                errors.append(f"Wrong {suffix} overlay size for {variant or 'plain'}: {atlas.size}")
                continue
            for connections in product((False, True), repeat=8):
                actual = {(x, y): (0, 0, 0, 0) for y in range(16) for x in range(16)}
                for tile in emitted_overlay_tiles(connections):
                    for y in range(16):
                        for x in range(16):
                            pixel = atlas.getpixel((tile % 6 * 16 + x, tile // 6 * 16 + y))
                            if pixel != (0, 0, 0, 0):
                                actual[(x, y)] = pixel
                expected_points: set[tuple[int, int]] = set()
                for direction, bit in DIRECTION_BITS.items():
                    if connections[bit]:
                        expected_points.update(masks[direction])
                expected = {
                    (x, y): (
                        overlay_sources[suffix].getpixel((x, y))
                        if (x, y) in expected_points
                        else (0, 0, 0, 0)
                    )
                    for y in range(16)
                    for x in range(16)
                }
                if actual != expected:
                    errors.append(f"{suffix} overlay mapping mismatch for {variant or 'plain'}: {connections}")
                    break

    json_paths = [
        path
        for path in RESOURCES_DIR.rglob("*")
        if path.is_file() and (path.suffix == ".json" or path.name.endswith(".mcmeta"))
    ]
    for path in json_paths:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exception:
            errors.append(f"Invalid JSON {path.relative_to(RESOURCES_DIR)}: {exception}")

    modifier_dir = RESOURCES_DIR / "assets" / NAMESPACE / "fusion" / "model_modifiers" / "blocks"
    modifiers = list(modifier_dir.glob("*.json"))
    if len(modifiers) != 18:
        errors.append(f"Expected 18 model modifiers, found {len(modifiers)}")
    expected_append_count = len(VARIANTS) + 1
    for path in modifiers:
        modifier = json.loads(path.read_text(encoding="utf-8"))
        if path.name == "pane_culling_fix.json":
            if modifier.get("pane_culling_fix") is not True or set(modifier.get("targets", [])) != {
                pane_id(variant) for variant in VARIANTS
            }:
                errors.append("Pane culling modifier must target all 17 pane materials")
            continue
        append = modifier.get("append", [])
        if len(append) != expected_append_count or not all(isinstance(model, str) for model in append):
            errors.append(f"Wrong Fusion 1.3.2 append list in {path.name}")

    for variant in VARIANTS:
        blockstate_path = RESOURCES_DIR / "assets" / "quark" / "blockstates" / f"{pane_name(variant)}.json"
        blockstate = json.loads(blockstate_path.read_text(encoding="utf-8"))
        multipart = blockstate.get("multipart", [])
        if len(multipart) != 9:
            errors.append(f"Expected 9 multipart entries for {pane_name(variant)}")
        for values in product((False, True), repeat=4):
            state = dict(zip(("north", "east", "south", "west"), values))
            applied = 0
            for entry in multipart:
                conditions = entry.get("when", {})
                if all(str(state[key]).lower() == expected for key, expected in conditions.items()):
                    applied += 1
            if applied != 5:
                errors.append(f"Pane state must select post plus exactly four shaped parts: {pane_name(variant)} {state}")
                break

        referenced_models = {
            entry.get("apply", {}).get("model")
            for entry in multipart
        }
        expected_prefix = f"{NAMESPACE}:block/panes/{pane_name(variant)}_"
        if not all(model and model.startswith(expected_prefix) for model in referenced_models):
            errors.append(f"Unexpected pane model reference for {pane_name(variant)}")

        for suffix in PANE_MODEL_SUFFIXES:
            model_path = (
                RESOURCES_DIR
                / "assets"
                / NAMESPACE
                / "models"
                / "block"
                / "panes"
                / f"{pane_name(variant)}_{suffix}.json"
            )
            composite = json.loads(model_path.read_text(encoding="utf-8"))
            if suffix == "post":
                if composite.get("type") != "fusion:connecting" or "models" in composite:
                    errors.append(f"Pane post must remain a single edge-only model: {model_path.name}")
                post_connections = composite.get("connections", {})
                if (
                    post_connections.get("type") != "fusion:or"
                    or len(post_connections.get("predicates", [])) != 1
                ):
                    errors.append(f"Pane post lost the Fusion 1.3.2 predicate wrapper: {model_path.name}")
                continue
            components = composite.get("models", [])
            if composite.get("type") != "fusion:composite" or len(components) != 19:
                errors.append(f"Wrong pane composite structure: {model_path.name}")
                continue
            base = components[0].get("model", {})
            if base.get("parent") != PANE_TEMPLATES[suffix]:
                errors.append(f"Wrong pane template orientation: {model_path.name}")
            base_connections = base.get("connections", {})
            if (
                base_connections.get("type") != "fusion:or"
                or len(base_connections.get("predicates", [])) != 1
            ):
                errors.append(f"Pane model lost the Fusion 1.3.2 predicate wrapper: {model_path.name}")
            base_text = json.dumps(base.get("connections", {}))
            if not all(pane_id(target) in base_text for target in VARIANTS) or '"blocks"' in base_text:
                errors.append(f"Pane base must use 17 singular predicates: {model_path.name}")
            expected_elements = pane_overlay_elements(suffix)
            for donor_index, donor in enumerate(VARIANTS, start=1):
                overlay = components[donor_index].get("model", {})
                connection_text = json.dumps(overlay.get("connections", {}))
                if pane_id(donor) not in connection_text or '"blocks"' in connection_text:
                    errors.append(f"Wrong donor predicate in {model_path.name}: {donor or 'plain'}")
                if overlay.get("elements") != expected_elements:
                    errors.append(
                        f"Wrong {suffix} pane overlay coordinates or faces in {model_path.name}: {donor or 'plain'}"
                    )
            fallback = components[-1].get("model", {})
            if fallback.get("connections", {}).get("type") != "fusion:not":
                errors.append(f"Missing pane fallback predicate: {model_path.name}")
            if fallback.get("textures", {}).get("all") != f"{NAMESPACE}:block/{name(variant)}_fallback_overlay":
                errors.append(f"Pane fallback uses wrong material: {model_path.name}")
            if fallback.get("elements") != expected_elements:
                errors.append(f"Wrong fallback pane overlay geometry: {model_path.name}")

        if (RESOURCES_DIR / "assets" / "quark" / "models" / "item" / f"{pane_name(variant)}.json").exists():
            errors.append(f"Pane item model must remain owned by Quark: {pane_name(variant)}")

    if errors:
        raise RuntimeError("Generated resource validation failed:\n- " + "\n- ".join(errors))
    file_count = sum(path.is_file() for path in RESOURCES_DIR.rglob("*"))
    print(
        f"Validation passed: 17 block and pane materials, all 256 masks per overlay, "
        f"{len(json_paths)} JSON metadata files, {file_count} resource files"
    )


def generate(quark_jar: Path) -> None:
    if not quark_jar.is_file():
        raise FileNotFoundError(quark_jar)
    for generated in (
        RESOURCES_DIR / "assets" / "quark",
        RESOURCES_DIR / "assets" / NAMESPACE,
    ):
        if generated.exists():
            shutil.rmtree(generated)

    with ZipFile(quark_jar) as archive:
        sources = {
            variant: Image.open(
                archive.open(f"assets/quark/textures/block/{name(variant)}.png")
            ).convert("RGBA")
            for variant in VARIANTS
        }

    original_masks = find_lobe_masks(sources["pink"], sources["purple"])
    expanded_masks = expand_masks_over_removed_frame(original_masks)
    texture_dir = RESOURCES_DIR / "assets" / NAMESPACE / "textures" / "block"
    model_dir = RESOURCES_DIR / "assets" / NAMESPACE / "models" / "block"

    for variant in VARIANTS:
        current_name = name(variant)
        source = sources[variant]
        pieced_tiles = make_pieced_tiles(source)

        base_path = texture_dir / f"{current_name}_base.png"
        base_path.parent.mkdir(parents=True, exist_ok=True)
        make_base_atlas(source, original_masks, expanded_masks).save(base_path)
        write_json(
            base_path.with_suffix(".png.mcmeta"),
            {"fusion": {"type": "connecting", "layout": "pieced"}},
        )

        group_path = texture_dir / f"{current_name}_group_overlay.png"
        make_overlay_atlas(pieced_tiles[1], expanded_masks).save(group_path)
        write_json(
            group_path.with_suffix(".png.mcmeta"),
            {"fusion": {"type": "connecting", "layout": "overlay", "render_type": "translucent"}},
        )

        fallback_path = texture_dir / f"{current_name}_fallback_overlay.png"
        make_overlay_atlas(source, original_masks).save(fallback_path)
        write_json(
            fallback_path.with_suffix(".png.mcmeta"),
            {"fusion": {"type": "connecting", "layout": "overlay", "render_type": "translucent"}},
        )

        write_json(
            RESOURCES_DIR / "assets" / "quark" / "models" / "block" / f"{current_name}.json",
            make_base_model(variant),
        )
        write_json(
            RESOURCES_DIR / "assets" / "quark" / "models" / "item" / f"{current_name}.json",
            {
                "parent": "minecraft:block/cube_all",
                "textures": {"all": f"quark:block/{current_name}"},
            },
        )
        write_json(model_dir / f"{current_name}_group_overlay.json", make_overlay_model(variant, False))
        write_json(model_dir / f"{current_name}_fallback_overlay.json", make_overlay_model(variant, True))

        group_models = [
            f"{NAMESPACE}:block/{name(donor)}_group_overlay"
            for donor in VARIANTS
        ]
        write_json(
            RESOURCES_DIR
            / "assets"
            / NAMESPACE
            / "fusion"
            / "model_modifiers"
            / "blocks"
            / f"{current_name}.json",
            {
                "targets": [block_id(variant)],
                "append": group_models + [f"{NAMESPACE}:block/{current_name}_fallback_overlay"],
                "show_breaking_overlay": False,
            },
        )

    for variant in VARIANTS:
        for suffix in PANE_MODEL_SUFFIXES:
            pane_model = make_pane_model(variant, suffix)
            write_json(
                RESOURCES_DIR
                / "assets"
                / NAMESPACE
                / "models"
                / "block"
                / "panes"
                / f"{pane_name(variant)}_{suffix}.json",
                make_pane_composite_model(variant, pane_model, suffix),
            )
        write_json(
            RESOURCES_DIR / "assets" / "quark" / "blockstates" / f"{pane_name(variant)}.json",
            make_pane_blockstate(variant),
        )

    write_json(
        RESOURCES_DIR
        / "assets"
        / NAMESPACE
        / "fusion"
        / "model_modifiers"
        / "blocks"
        / "pane_culling_fix.json",
        {"pane_culling_fix": True, "targets": [pane_id(variant) for variant in VARIANTS]},
    )

    write_json(
        RESOURCES_DIR / "assets" / NAMESPACE / "lang" / "en_us.json",
        {"modmenu.nameTranslation.quark_framed_glass_ct": "Quark Framed Glass CT"},
    )
    validate(sources, original_masks, expanded_masks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quark-jar", type=Path, default=DEFAULT_QUARK_JAR)
    arguments = parser.parse_args()
    generate(arguments.quark_jar.resolve())


if __name__ == "__main__":
    main()
