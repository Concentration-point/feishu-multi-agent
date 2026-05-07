from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_sync_new_doc_waits_for_docx_ready(tmp_path, monkeypatch):
    from sync import wiki_sync as mod

    monkeypatch.setattr(mod, "KNOWLEDGE_BASE_PATH", str(tmp_path))
    service = mod.WikiSyncService(space_id="space_001")
    service._ensure_parent_node = AsyncMock(return_value={"node_token": "parent_tok"})

    rel_path = "03_经验沉淀/新品发布/test.md"
    full_path = Path(tmp_path) / "03_经验沉淀" / "新品发布" / "test.md"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text("# Test\n\nbody", encoding="utf-8")

    events: list[str] = []

    async def _find_node(*_args, **_kwargs):
        events.append("find")
        return None

    async def _create_node(*_args, **_kwargs):
        events.append("create")
        return {"node_token": "doc_node_tok", "obj_token": "doc_obj_tok"}

    async def _wait_ready(document_id: str):
        events.append(f"wait:{document_id}")

    async def _write_content(obj_token: str, _content: str, _sync_mode: str):
        events.append(f"write:{obj_token}")

    service._wiki.find_node_by_title = AsyncMock(side_effect=_find_node)
    service._wiki.create_node = AsyncMock(side_effect=_create_node)
    service._wiki.wait_for_new_doc_ready = AsyncMock(side_effect=_wait_ready)
    service._write_content = AsyncMock(side_effect=_write_content)

    mode = await service._sync_file(rel_path, full_path)

    assert mode == "markdown"
    assert events == [
        "find",
        "create",
        "wait:doc_obj_tok",
        "write:doc_obj_tok",
    ]
    service._wiki.wait_for_new_doc_ready.assert_awaited_once_with("doc_obj_tok")
