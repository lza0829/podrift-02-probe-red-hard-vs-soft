from __future__ import annotations
from fastapi import APIRouter
from app.db import db
from app.services.common import rows
from app.services import probe_gate

router = APIRouter(tags=["舱体"])


@router.get("/舱体")
def list_pods():
    with db() as conn:
        threshold = probe_gate.load_threshold(conn)
        data = rows(
            conn.execute(
                """
                SELECT p.*, i.name AS image_name, i.tag AS image_tag, i.pull_state,
                       pr.color AS probe_color, pr.fail_streak
                FROM pods p
                LEFT JOIN images i ON i.id = p.image_id
                LEFT JOIN probes pr ON pr.pod_id = p.id
                ORDER BY p.id
                """
            )
        )
        for r in data:
            probe = (
                {"color": r["probe_color"], "fail_streak": r["fail_streak"]}
                if r["probe_color"] is not None
                else None
            )
            v = probe_gate.evaluate(probe, threshold)
            r["开单前可起"] = not v.blocked
            r["开单前门"] = v.label
            r["探针阈值"] = threshold
        return data
