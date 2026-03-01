from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import COAMapping, Engagement
from .common import add_exception
from .parser_service import parse_mapping


def import_mapping_file(db: Session, engagement: Engagement, mapping_path: Path) -> dict[str, int]:
    parsed = parse_mapping(mapping_path)

    entities = {entity.id: entity for entity in engagement.entities}
    entity_by_name = {entity.name.strip().lower(): entity for entity in engagement.entities}

    db.execute(delete(COAMapping).where(COAMapping.engagement_id == engagement.id))

    seen: dict[tuple[str | None, str], str] = {}
    duplicate_count = 0
    conflict_count = 0

    for row in parsed:
        entity_id = None
        if row["entity_ref"]:
            ref = row["entity_ref"].strip()
            if ref in entities:
                entity_id = ref
            else:
                lookup = entity_by_name.get(ref.lower())
                if not lookup:
                    add_exception(
                        db,
                        engagement.id,
                        "MAPPING_ENTITY_UNKNOWN",
                        f"Mapping row references unknown entity '{ref}'",
                        blocking=True,
                        context={"entity_ref": ref},
                    )
                    conflict_count += 1
                    continue
                entity_id = lookup.id

        key = (entity_id, row["local_account_code"])
        mapped_to = seen.get(key)
        if mapped_to:
            duplicate_count += 1
            if mapped_to != row["group_account_code"]:
                conflict_count += 1
                add_exception(
                    db,
                    engagement.id,
                    "MAPPING_CONFLICT",
                    (
                        f"Local account {row['local_account_code']} is mapped to multiple group accounts "
                        f"({mapped_to}, {row['group_account_code']})"
                    ),
                    blocking=True,
                    entity_id=entity_id,
                    account_code=row["local_account_code"],
                )
                continue
        else:
            seen[key] = row["group_account_code"]

        db.add(
            COAMapping(
                engagement_id=engagement.id,
                entity_id=entity_id,
                local_account_code=row["local_account_code"],
                local_account_name=row["local_account_name"],
                group_account_code=row["group_account_code"],
                group_account_name=row["group_account_name"],
                account_class=row["account_class"],
                translation_policy=row["translation_policy"],
                historical_rate_date=row["historical_rate_date"],
                is_intercompany=row["is_intercompany"],
            )
        )

    db.flush()

    by_entity: defaultdict[str, int] = defaultdict(int)
    rows = db.execute(select(COAMapping.entity_id).where(COAMapping.engagement_id == engagement.id)).scalars().all()
    for entity_id in rows:
        by_entity[entity_id or "GLOBAL"] += 1

    return {
        "rows_loaded": len(rows),
        "duplicate_rows": duplicate_count,
        "conflict_rows": conflict_count,
        "global_rows": by_entity["GLOBAL"],
    }
