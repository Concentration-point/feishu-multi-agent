from __future__ import annotations

from config import WIKI_SPACE_ID
from sync.wiki_sync import WikiSyncService


def main() -> int:
    sync = WikiSyncService(WIKI_SPACE_ID or "preview-only")
    previews = sync.preview_dirty_files()
    if not previews:
        print("No dirty wiki files.")
        return 0

    for item in previews:
        print("=" * 72)
        print(f"FILE: {item['rel_path']}")
        print(f"PARENT: {item['parent_title']}")
        print(f"TITLE: {item['doc_title']}")
        print(f"RAW_LEN: {item['raw_length']} -> CLEANED_LEN: {item['cleaned_length']}")
        print("--- CLEANED MARKDOWN PREVIEW ---")
        print(item['cleaned_markdown'][:1200])
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
