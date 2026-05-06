#!/usr/bin/env python3
"""强力解析器（Powerful Parser）单元测试。

验证 extract_json_from_thinking_model 能处理 Thinking Model 的各种混乱输出格式。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from vision_engine import extract_json_from_thinking_model


# ── 测试用例：input_str → list of (path, expected_value) ─────────────────────

TEST_CASES: list[dict[str, Any]] = [
    # Case 1: 干净纯 JSON
    {
        "name": "Case 1: 干净纯 JSON",
        "input": '{"is_room": true, "is_blurry_or_unusable": false, "reason": "OK"}',
        "assertions": [
            (["is_room"], True),
            (["is_blurry_or_unusable"], False),
            (["reason"], "OK"),
        ],
    },
    # Case 2: XML <result> 标签包裹
    {
        "name": "Case 2: XML <result> 标签包裹",
        "input": "好的，让我分析一下。\n<result>{\"is_room\": true, \"is_blurry_or_unusable\": false, \"reason\": \"清晰\"}</result>\n这是结论。",
        "assertions": [
            (["is_room"], True),
            (["reason"], "清晰"),
        ],
    },
    # Case 3: XML 大写标签
    {
        "name": "Case 3: XML 大写 <RESULT> 标签",
        "input": "<RESULT>{\"is_room\": false, \"is_blurry_or_unusable\": true, \"reason\": \"模糊\"}</RESULT>",
        "assertions": [
            (["is_room"], False),
            (["is_blurry_or_unusable"], True),
        ],
    },
    # Case 4: Markdown ```json 代码块
    {
        "name": "Case 4: Markdown ```json 代码块",
        "input": "```json\n{\"is_room\": true, \"is_blurry_or_unusable\": false, \"reason\": \"OK\"}\n```",
        "assertions": [
            (["is_room"], True),
            (["reason"], "OK"),
        ],
    },
    # Case 5: 普通 ``` 代码块（无语言标记）
    {
        "name": "Case 5: 普通 ``` 代码块",
        "input": "```\n{\"is_room\": true, \"is_blurry_or_unusable\": false, \"reason\": \"test\"}\n```",
        "assertions": [
            (["is_room"], True),
        ],
    },
    # Case 6: 一万字思考过程 + JSON（JSON紧跟在思考之后）
    {
        "name": "Case 6: 超长思考过程 + JSON",
        "input": """好的，让我详细分析这张图片...

（此处省略一万字思考分析过程）

我注意到图片中有明显的房间结构，包括墙壁、地板、家具等元素。
综合以上分析，这是一张清晰的室内房间场景图片，适合后续处理。

{"is_room": true, "is_blurry_or_unusable": false, "reason": "房间场景清晰，家具轮廓明确"}""",
        "assertions": [
            (["is_room"], True),
            (["reason"], "房间场景清晰，家具轮廓明确"),
        ],
    },
    # Case 7: RoomScene 完整嵌套 JSON
    {
        "name": "Case 7: RoomScene 完整嵌套 JSON + XML",
        "input": """让我分析这个房间的布局...

<result>
{
  "room": {
    "boundary": {
      "walls": ["北墙", "南墙"],
      "windows": ["南墙窗户"],
      "doors": ["南墙门"]
    },
    "furniture": [
      {
        "name": "双人沙发",
        "dimensions": {"width": 1.8, "depth": 0.85, "height": 0.9},
        "position": {"x": 0.5, "y": 3.2, "z": 0, "rotation_degrees": 0},
        "material": "布艺"
      },
      {
        "name": "茶几",
        "dimensions": {"width": 0.6, "depth": 0.6, "height": 0.45},
        "position": {"x": 1.5, "y": 3.2, "z": 0, "rotation_degrees": 0},
        "material": "木质"
      }
    ]
  },
  "2d_floor_plan": "┌──────────────┐\\n│ 沙发  窗户  │\\n└──────────────┘"
}
</result>

以上就是分析结果。""",
        "assertions": [
            (["room", "furniture", 0, "name"], "双人沙发"),
            (["room", "furniture", 1, "material"], "木质"),
            (["room", "boundary", "windows", 0], "南墙窗户"),
            (["room", "boundary", "doors", 0], "南墙门"),
            (["2d_floor_plan"], "┌──────────────┐\n│ 沙发  窗户  │\n└──────────────┘"),
        ],
    },
    # Case 8: 多行 JSON，模型正常输出
    {
        "name": "Case 8: 多行格式化的 JSON",
        "input": """{
  "is_room": true,
  "is_blurry_or_unusable": false,
  "reason": "测试"
}""",
        "assertions": [
            (["is_room"], True),
            (["reason"], "测试"),
        ],
    },
    # Case 9: 仅 XML 标签，无任何干扰
    {
        "name": "Case 9: 仅有 XML 标签",
        "input": "<result>{\"is_room\": true, \"is_blurry_or_unusable\": false, \"reason\": \"OK\"}</result>",
        "assertions": [
            (["is_room"], True),
            (["is_blurry_or_unusable"], False),
        ],
    },
    # Case 10: JSON 内有换行和多余逗号
    {
        "name": "Case 10: JSON 内有换行",
        "input": '{"is_room": true, "is_blurry_or_unusable": false,\n"reason": "OK"}',
        "assertions": [
            (["is_room"], True),
            (["reason"], "OK"),
        ],
    },
    # Case 11: 家具数组深度嵌套
    {
        "name": "Case 11: 家具数组深度嵌套",
        "input": '{"room": {"boundary": {"walls": [], "windows": ["窗"], "doors": []}, "furniture": [{"name": "床", "dimensions": {"width": 2.0, "depth": 1.5, "height": 0.5}, "position": {"x": 1.0, "y": 1.0, "z": 0, "rotation_degrees": 0}, "material": "木质"}]}}',
        "assertions": [
            (["room", "furniture", 0, "name"], "床"),
            (["room", "furniture", 0, "dimensions", "width"], 2.0),
            (["room", "boundary", "windows", 0], "窗"),
        ],
    },
    # Case 12: 仅有代码块，无其他内容
    {
        "name": "Case 12: 仅 ```json 代码块",
        "input": "```json\n{\"is_room\": true, \"is_blurry_or_unusable\": false, \"reason\": \"OK\"}\n```",
        "assertions": [
            (["is_room"], True),
            (["reason"], "OK"),
        ],
    },
]


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _get_by_path(data: Any, path: list) -> Any:
    """根据路径列表从字典/列表中取值。"""
    for key in path:
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and isinstance(key, int):
            data = data[key] if 0 <= key < len(data) else None
        else:
            return None
    return data


# ── 测试执行 ─────────────────────────────────────────────────────────────────

def run_tests() -> bool:
    print("=" * 70)
    print("  Powerful Parser 单元测试 — extract_json_from_thinking_model")
    print("=" * 70)
    print()

    passed = 0
    failed = 0

    for tc in TEST_CASES:
        name: str = tc["name"]
        inp: str = tc["input"]
        assertions: list = tc["assertions"]

        try:
            result = extract_json_from_thinking_model(inp)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ FAIL | {name}")
            print(f"     异常: {type(exc).__name__}: {exc}")
            failed += 1
            print()
            continue

        # 执行所有断言
        all_ok = True
        for path, expected in assertions:
            actual = _get_by_path(result, path)
            if actual == expected:
                print(f"✅  {name} | {'.'.join(str(k) for k in path)} == {expected!r}")
            else:
                print(f"❌  {name} | {'.'.join(str(k) for k in path)}")
                print(f"      期望: {expected!r}  实际: {actual!r}")
                all_ok = False

        if all_ok:
            passed += 1
            print(f"✅ PASS | {name}")
        else:
            failed += 1
            print(f"⚠️  FAIL | {name}")

        print()

    # ── 总结 ────────────────────────────────────────────────────────────────
    total = passed + failed
    print("=" * 70)
    if failed == 0:
        print(f"  🎉 全部通过！{passed}/{total}")
    else:
        print(f"  ⚠️  通过 {passed}/{total}，失败 {failed} 个")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
