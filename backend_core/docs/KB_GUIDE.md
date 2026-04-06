# 暖心树洞知识库编写规范 (KB_GUIDE)

## 1. 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 唯一标识，格式：`{prefix}_{三位数字}`，如 `stu_001`、`dorm_003` |
| `category` | ✅ | 一级分类，见下方分类表 |
| `topic` | ✅ | 细分主题，20字以内 |
| `keywords` | ✅ | 至少5个触发关键词，与实际用户表达对齐 |
| `content` | ✅ | 心理学背景知识，50-300字，AI内化参考，不直接展示 |
| `advice` | ✅ | 循证干预建议，100-400字，分点描述 |
| `dialogue_example` | ✅ | 用户输入 + 高质量回复示例，用于 Prompt 语气学习 |
| `scene_tags` | 推荐 | 高频场景标签列表，如 `["exam_anxiety","insomnia"]` |
| `audience` | 推荐 | `大学生`/`高中生`/`初中生`/`通用` |
| `emotion_type` | 推荐 | `academic_stress`/`romantic_emotion`/`depression_anxiety`/... |
| `risk_level` | 推荐 | `low`/`medium`/`high`/`urgent` |
| `do` | 推荐 | 推荐的引导方式，最多3条，简洁动词短句 |
| `dont` | 推荐 | 禁忌话术或操作，最多3条 |
| `taboo` | 推荐 | 高危/误导性表达，如涉及自杀方式的词汇 |
| `references` | 可选 | 内部溯源参考，如 `{"来源": "CBT治疗手册"}` |

## 2. 分类表

| category | 典型 scene_tag |
|----------|---------------|
| 学业压力 | exam_anxiety / academic_failure / procrastination |
| 宿舍与人际 | dorm_conflict / social_exclusion / bullying |
| 恋爱与情感 | breakup / romantic_rejection / long_distance |
| 就业与未来 | career_anxiety / job_search / major_confusion |
| 心理健康 | depression_possible / social_anxiety / crisis_intervention |
| 家庭关系 | family_conflict / parental_pressure / divorce |
| 自我成长 | identity_confusion / low_confidence / addiction |
| 生活压力 | financial_stress / sleep_problem |
| 积极心理 | positive_emotion / achievement |

## 3. 风险等级标准

| risk_level | 判断标准 | 干预要求 |
|------------|----------|----------|
| `urgent` | 含自杀/自伤/立即危险意图 | **必须**给出热线号码 |
| `high` | 持续绝望/抑郁/"想消失" | 优先共情，自然引导热线 |
| `medium` | 明显焦虑/冲突/压力 | 共情 + 1-2条微建议 |
| `low` | 一般情绪波动/积极 | 正常共情回应 |

## 4. 禁忌（dont/taboo）填写示例
```python
"dont": [
    "不要说'你要坚强'或'想开点'",
    "不要立刻给出大量建议",
    "不要否定用户的感受",
],
"taboo": [
    "方法/手段",      # 自伤手段的具体描述
    "跳楼几层以上",   # 具体危险信息
    "你太脆弱了",     # 评价性词汇
],
```

## 5. 条目示例（完整格式）
```python
{
    "id": "mental_005",
    "category": "心理健康",
    "topic": "拖延与自我批评循环",
    "keywords": ["拖延", "总是拖", "截止日期", "自责", "明天再说", "做不到"],
    "content": (
        "拖延不是意志力缺失，而是对负面情绪的回避策略。"
        "当任务与焦虑/完美主义/无聊绑定时，大脑选择暂时逃避来降低情绪张力。"
        "事后的自责会形成'拖延→自责→更焦虑→更逃避'的恶性循环。"
    ),
    "advice": (
        "干预建议：\n"
        "1. 【2分钟启动法】：告诉自己只做2分钟，大多数时候开始了就停不下来\n"
        "2. 【区分完美主义】：80分的完成比100分的幻想更有价值\n"
        "3. 【自我同情优先于自责】：先接纳'我今天状态不好'，再讨论任务"
    ),
    "dialogue_example": (
        "用户：我又拖到截止日期前一天，自己都看不起自己\n"
        "回复示例：'看不起自己'这种感觉比拖延本身更难受吧。\n"
        "其实你能意识到、愿意说出来，说明你还是很在意这件事的——\n"
        "只是今天的状态没跟上你的期待。现在还剩多少时间？我们一起看看能做什么。"
    ),
    "scene_tags":  ["procrastination", "self_criticism", "perfectionism"],
    "audience":    "大学生",
    "emotion_type": "academic_stress",
    "risk_level":  "low",
    "do": [
        "先承认拖延背后的情绪（焦虑/无聊/害怕失败）",
        "给一个极小的起步动作",
        "把自我批评与任务分开处理",
    ],
    "dont": [
        "不要说'你应该早点开始'",
        "不要强调截止日期的严重性（会加重焦虑）",
    ],
    "taboo": [],
    "references": {"来源": "CBT procrastination protocol"},
}
```

## 6. 验证方式
```bash
cd /root/emotion_analysis_service
python scripts/validate_kb.py
```