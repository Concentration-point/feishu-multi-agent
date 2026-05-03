"""快速查看 Chroma 经验向量库内容。

用法：
  python scripts/inspect_chroma.py              # 列出所有记录
  python scripts/inspect_chroma.py --query 小红书  # 语义检索
  python scripts/inspect_chroma.py --role copywriter  # 按角色过滤
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from memory.experience_store import ExperienceVectorStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", "-q", default=None, help="语义检索关键词")
    parser.add_argument("--role", "-r", default=None, help="按 role_id 过滤")
    parser.add_argument("--top", "-n", type=int, default=20, help="最多显示条数")
    parser.add_argument("--path", default=None, help="Chroma 路径（默认读 config）")
    args = parser.parse_args()

    store = ExperienceVectorStore(path=args.path)
    total = store._col.count()
    print(f"\nChroma 路径: {args.path or config.CHROMA_DB_PATH}")
    print(f"总记录数: {total}\n")

    if total == 0:
        print("（空库）")
        return

    if args.query:
        # 语义检索模式
        results = store.query(args.query, role_id=args.role, k=args.top)
        print(f"[语义检索] '{args.query}'  role={args.role or '全部'}\n")
        print(f"{'#':<3} {'相似度':<8} {'role_id':<20} {'category':<15} {'conf':<6}  lesson")
        print("-" * 100)
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            sim = 1.0 - r["distance"]
            lesson = r["document"][:60].replace("\n", " ")
            print(f"{i:<3} {sim:<8.4f} {meta.get('role_id',''):<20} {meta.get('category',''):<15} {meta.get('confidence',0):<6.2f}  {lesson}")
    else:
        # 列出所有记录
        where = {"role_id": {"$eq": args.role}} if args.role else None
        kwargs = {"include": ["documents", "metadatas"], "limit": args.top}
        if where:
            kwargs["where"] = where
        result = store._col.get(**kwargs)

        ids = result.get("ids", [])
        docs = result.get("documents", [])
        metas = result.get("metadatas", [])

        print(f"{'#':<3} {'id':<30} {'role_id':<20} {'category':<15} {'conf':<6} {'use':<4}  lesson")
        print("-" * 110)
        for i, (id_, doc, meta) in enumerate(zip(ids, docs, metas), 1):
            lesson = doc[:55].replace("\n", " ")
            print(
                f"{i:<3} {id_[:28]:<30} {meta.get('role_id',''):<20} "
                f"{meta.get('category',''):<15} {meta.get('confidence',0):<6.2f} "
                f"{meta.get('use_count',0):<4}  {lesson}"
            )

        if total > args.top:
            print(f"\n... 共 {total} 条，当前显示前 {args.top} 条。用 --top N 调整。")

    print()


if __name__ == "__main__":
    main()
