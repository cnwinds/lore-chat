import re

from app.config import EDITABLE_SETTING_KEYS, get_settings
from app.engine.background.catalog import ALL_PURPOSE_KEYS, build_catalog_static, setting_meta

_SNAKE_CASE = re.compile(r"[a-z]+_[a-z_]+")
_API_PATH = re.compile(r"/api/")
_CODE_EXT = re.compile(r"\.(py|db|json)\b")


def test_catalog_lane_nodes_exist():
    static = build_catalog_static()
    nodes = static["nodes"]
    for lane in static["lanes"]:
        for step in lane["steps"]:
            for nid in step["nodes"]:
                assert nid in nodes, f"missing node {nid} for lane {lane['id']}"


def test_llm_nodes_have_purpose_and_prompts():
    static = build_catalog_static()
    for nid, node in static["nodes"].items():
        if node["type"] in ("llm", "embed"):
            assert node.get("purpose"), nid
        if node["type"] == "llm":
            assert node["prompts"], nid


def test_settings_keys_editable():
    for key in setting_meta(get_settings()):
        assert key in EDITABLE_SETTING_KEYS


def test_all_purpose_keys_in_stats_list():
    static = build_catalog_static()
    llm_purposes = {
        n["purpose"]
        for n in static["nodes"].values()
        if n.get("purpose") and n["type"] in ("llm", "embed")
    }
    assert set(ALL_PURPOSE_KEYS) == llm_purposes


def test_lane_step_kind_rules():
    static = build_catalog_static()
    nodes = static["nodes"]
    for lane in static["lanes"]:
        steps = lane["steps"]
        assert steps, lane["id"]
        assert steps[0]["kind"] == "trigger", lane["id"]
        for nid in steps[0]["nodes"]:
            assert nodes[nid]["type"] == "trigger", (lane["id"], nid)
        for step in steps[1:]:
            if step["kind"] == "stage":
                for nid in step["nodes"]:
                    assert nodes[nid]["type"] in (
                        "llm",
                        "embed",
                        "code",
                        "turn",
                    ), (lane["id"], nid)
            elif step["kind"] == "output":
                for nid in step["nodes"]:
                    assert nodes[nid]["type"] == "store", (lane["id"], nid)


def _iter_catalog_user_facing_strings(static: dict) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for group in static["groups"]:
        rows.append(("group", group["id"], "hint", group["hint"]))
    for lane in static["lanes"]:
        for field in ("summary", "cadence", "title"):
            rows.append(("lane", lane["id"], field, lane[field]))
    for item in static["pausable"]:
        rows.append(("pausable", item["key"], "label", item["label"]))
        rows.append(("pausable", item["key"], "hint", item["hint"]))
    for nid, node in static["nodes"].items():
        for field in ("title", "subtitle", "description"):
            text = node.get(field)
            if text:
                rows.append(("node", nid, field, text))
        for list_field in ("conditions", "limits", "guards", "outputs"):
            for idx, text in enumerate(node.get(list_field) or []):
                rows.append(("node", nid, f"{list_field}[{idx}]", text))
    for key, meta in setting_meta(get_settings()).items():
        rows.append(("setting", key, "label", meta["label"]))
        rows.append(("setting", key, "hint", meta["hint"]))
    return rows


def test_catalog_user_facing_strings_avoid_code_identifiers():
    static = build_catalog_static()
    for kind, item_id, field, text in _iter_catalog_user_facing_strings(static):
        assert not _SNAKE_CASE.search(text), (kind, item_id, field, text)
        assert not _API_PATH.search(text), (kind, item_id, field, text)
        assert not _CODE_EXT.search(text), (kind, item_id, field, text)
