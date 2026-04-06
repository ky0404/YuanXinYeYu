#!/usr/bin/env python3
"""scripts/validate_kb.py
知识库质量巡检脚本，检查：
  - 重复 id
  - 缺少必要字段（id / category / topic / keywords / content）
  - keywords 为空
  - content 过短（< 50 字）
  - advice 缺失
  - dialogue_example 缺失
  - 新字段覆盖率统计（scene_tags / do / dont / taboo）

运行：cd /root/emotion_analysis_service && python scripts/validate_kb.py
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from knowledge.emotion_knowledge import KNOWLEDGE_BASE

REQUIRED_FIELDS = ["id", "category", "topic", "keywords", "content"]
NEW_FIELDS      = ["scene_tags", "do", "dont", "taboo", "risk_level", "audience"]

errors:   list = []
warnings: list = []
seen_ids: set  = set()

for i, entry in enumerate(KNOWLEDGE_BASE, 1):
    eid = entry.get("id", f"<idx={i}>")

    # 重复 id
    if eid in seen_ids:
        errors.append(f"  [重复ID] id={eid}")
    seen_ids.add(eid)

    # 必要字段缺失
    for field in REQUIRED_FIELDS:
        if not entry.get(field):
            errors.append(f"  [缺少字段] id={eid} field={field}")

    # keywords 为空列表
    kws = entry.get("keywords", [])
    if isinstance(kws, list) and len(kws) == 0:
        errors.append(f"  [keywords空] id={eid}")

    # content 过短
    content = entry.get("content", "")
    if len(content.strip()) < 50:
        warnings.append(f"  [content过短] id={eid} len={len(content.strip())}")

    # advice 缺失
    if not entry.get("advice"):
        warnings.append(f"  [缺少advice] id={eid}")

    # dialogue_example 缺失
    if not entry.get("dialogue_example"):
        warnings.append(f"  [缺少dialogue_example] id={eid}")

# 统计
total        = len(KNOWLEDGE_BASE)
new_coverage = {
    field: sum(1 for e in KNOWLEDGE_BASE if e.get(field)) / max(total, 1) * 100
    for field in NEW_FIELDS
}

print(f"\n{'='*60}")
print(f"知识库巡检报告 — 共 {total} 条")
print(f"{'='*60}")

if errors:
    print(f"\n❌ 错误（{len(errors)} 条，必须修复）：")
    for e in errors:
        print(e)
else:
    print("\n✅ 无错误")

if warnings:
    print(f"\n⚠️  警告（{len(warnings)} 条，建议优化）：")
    for w in warnings[:30]:
        print(w)
    if len(warnings) > 30:
        print(f"  ... 共 {len(warnings)} 条警告")
else:
    print("✅ 无警告")

print("\n📊 新字段覆盖率：")
for field, pct in new_coverage.items():
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    print(f"  {field:20s} {bar} {pct:5.1f}%")

print(f"\n{'='*60}")
if errors:
    print("❌ 存在错误，请修复后重新运行")
    sys.exit(1)
else:
    print("✅ 知识库结构检查通过")
    sys.exit(0)