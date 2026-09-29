"""人设修订 CAS 与迁移（P2 · 任务 A）。"""

import sqlite3

from app.engine.roles import RoleStore


def test_migration_meta_columns(tmp_path):
    db = tmp_path / "roles"
    roles = RoleStore(db)
    role = roles.create(name="R", system_prompt="hello")
    revs = roles.list_persona_revisions("role", role["id"])
    assert revs[0]["meta"] == {}
    assert revs[0]["rolled_back_by"] is None
    cols = {
        r[1]
        for r in roles.conn.execute("PRAGMA table_info(persona_revisions)").fetchall()
    }
    assert "meta_json" in cols
    assert "rolled_back_by" in cols


def test_revision_order_same_timestamp(tmp_path):
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="R", system_prompt="")
    stamp = "2020-01-01T00:00:00+00:00"
    roles.conn.execute(
        """
        INSERT INTO persona_revisions(
            id, subject_kind, subject_id, body, source, created_at, meta_json
        ) VALUES ('a', 'role', ?, '1', 'manual', ?, '{}'),
                 ('b', 'role', ?, '2', 'manual', ?, '{}')
        """,
        (role["id"], stamp, role["id"], stamp),
    )
    roles.conn.commit()
    revs = roles.list_persona_revisions("role", role["id"], limit=10)
    ids = [r["id"] for r in revs if r["id"] in ("a", "b")]
    assert ids.index("b") < ids.index("a")


def test_cas_evolution_and_rollback(tmp_path):
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="R", system_prompt="v0")
    roles.update(role["id"], system_prompt="v1")
    assert (
        roles.apply_persona_evolution(
            "role",
            role["id"],
            expected_body="v0",
            new_body="v2",
            meta={},
        )
        is None
    )
    evo = roles.apply_persona_evolution(
        "role",
        role["id"],
        expected_body="v1",
        new_body="v2",
        meta={"k": 1},
    )
    assert evo and evo["source"] == "evolution"
    rb = roles.rollback_persona_revision(
        "role",
        role["id"],
        revision_id=evo["id"],
        expected_body="v2",
        new_body="v1",
    )
    assert rb
    target = roles.get_persona_revision(evo["id"])
    assert target["rolled_back_by"] == rb["id"]
    assert (
        roles.rollback_persona_revision(
            "role",
            role["id"],
            revision_id=evo["id"],
            expected_body="v1",
            new_body="v1",
        )
        is None
    )


def test_rollback_even_when_body_unchanged(tmp_path):
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="R", system_prompt="v1")
    roles.update(role["id"], system_prompt="v2")
    evo = roles.apply_persona_evolution(
        "role",
        role["id"],
        expected_body="v2",
        new_body="v3",
        meta={},
    )
    roles.update(role["id"], system_prompt="v2")
    rb = roles.rollback_persona_revision(
        "role",
        role["id"],
        revision_id=evo["id"],
        expected_body="v2",
        new_body="v2",
    )
    assert rb and rb["source"] == "rollback"


def test_get_persona_body_and_neighbors(tmp_path):
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="R", system_prompt="a")
    roles.update(role["id"], system_prompt="b")
    revs = roles.list_persona_revisions("role", role["id"])
    latest = roles.latest_persona_revision("role", role["id"])
    assert latest["body"] == "b"
    prev = roles.previous_persona_revision(latest["id"])
    assert prev["body"] == "a"
    assert roles.get_persona_body("role", role["id"]) == "b"
