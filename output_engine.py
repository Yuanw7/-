"""输出生成器 — 适老化房间安全合规审查报告、2D 俯视图与 Blender 脚本。

【设计原则 — 去技术化】
- 所有坐标、旋转角度等数值必须翻译成口语化描述
- 每条建议都要解释"对老人有什么具体好处"
- 禁止出现 x/y/z、move/rotate、JSON 参数等技术术语
- 规范引用必须使用全称，禁止显示 .pdf 或 chunk_index 等后台字样
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from knowledge_base import SafetyConstraintResult
from models import ModificationProposal, RoomScene


# ════════════════════════════════════════════════════════════════════════════════
# 口语化距离转换表
# ════════════════════════════════════════════════════════════════════════════════

def _meters_to_words(meters: float) -> str:
    """将米制距离转换为口语化描述。"""
    if meters < 0.1:
        return "一拳头宽"
    elif meters < 0.2:
        return "一个手机宽"
    elif meters < 0.3:
        return "一拃长"
    elif meters < 0.5:
        return "约半米"
    elif meters < 0.8:
        return "约一大步"
    elif meters < 1.0:
        return "约一步"
    elif meters < 1.2:
        return "够一个人侧身走"
    elif meters < 1.5:
        return "够一个人正常走"
    elif meters < 1.8:
        return "够两个人并排走"
    else:
        return f"约 {meters:.1f} 米宽"


def _size_to_words(width: float, depth: float, height: float | None = None) -> str:
    """将尺寸转换为口语化描述。"""
    size_desc = f"{_meters_to_words(width)}、{_meters_to_words(depth)}"
    if height is not None:
        if height < 0.4:
            size_desc += f"，矮矮的（约到小腿）"
        elif height < 0.6:
            size_desc += f"，约到膝盖高"
        elif height < 0.8:
            size_desc += f"，约到大腿高"
        elif height < 1.0:
            size_desc += f"，约到腰部高"
        elif height < 1.2:
            size_desc += f"，约到胸口高"
        else:
            size_desc += f"，高高的"
    return size_desc


def _direction_to_words(x_from: float, y_from: float, x_to: float, y_to: float) -> str:
    """将坐标移动转换为口语化方向描述。"""
    dx = x_to - x_from
    dy = y_to - y_from

    # 判断水平方向
    if abs(dx) < 0.15:
        horizontal = ""
    elif dx > 0:
        horizontal = "往右"
    else:
        horizontal = "往左"

    # 判断垂直方向
    if abs(dy) < 0.15:
        vertical = ""
    elif dy > 0:
        vertical = "往里"
    else:
        vertical = "往外"

    distance = math.sqrt(dx * dx + dy * dy)
    
    # 构建描述
    if horizontal or vertical:
        direction_desc = horizontal + vertical
        if distance > 0.1:
            distance_str = _meters_to_words(distance)
            return f"{direction_desc}移动{distance_str}"
        else:
            return f"{direction_desc}挪一下"
    else:
        distance_str = _meters_to_words(distance)
        return f"调整位置（移动{distance_str}）"


def _position_to_words(x: float, y: float, room_width: float = 5.0) -> str:
    """将位置坐标转换为口语化描述。"""
    # 以房间中点为参考
    room_center_x = room_width / 2
    dx = x - room_center_x

    if abs(dx) < 0.5:
        return "房间中间"
    elif dx < -1.0:
        return "房间左边"
    elif dx > 1.0:
        return "房间右边"
    elif dx < 0:
        return "偏房间左边"
    else:
        return "偏房间右边"


def _action_to_human(action: str) -> str:
    """将技术动作转换为口语化描述。"""
    mapping = {
        "move": "换个位置",
        "resize": "改改大小",
        "replace": "换成别的",
        "remove": "挪走",
        "add": "添一个",
    }
    return mapping.get(action, action)


# ════════════════════════════════════════════════════════════════════════════════
# 修改应用逻辑（保留核心功能）
# ════════════════════════════════════════════════════════════════════════════════


def apply_modifications(
    room_scene: RoomScene, proposals: Sequence[ModificationProposal]
) -> RoomScene:
    """将 ModificationProposal 应用到 RoomScene，生成最终场景。"""
    updated = room_scene.model_copy(deep=True)
    furniture_by_name = {item.name: item for item in updated.furniture}

    for proposal in proposals:
        target = furniture_by_name.get(proposal.original_object_id)
        if target is None:
            continue

        if proposal.action == "move":
            target.position.x = float(proposal.new_parameters.get("x", target.position.x))
            target.position.y = float(proposal.new_parameters.get("y", target.position.y))
            target.position.z = float(proposal.new_parameters.get("z", target.position.z))
            target.position.rotation_degrees = float(
                proposal.new_parameters.get("rotation_degrees", target.position.rotation_degrees)
            )
        elif proposal.action == "resize":
            target.dimensions.width = float(
                proposal.new_parameters.get("width", target.dimensions.width)
            )
            target.dimensions.depth = float(
                proposal.new_parameters.get("depth", target.dimensions.depth)
            )
            target.dimensions.height = float(
                proposal.new_parameters.get("height", target.dimensions.height)
            )
        elif proposal.action == "replace":
            target.name = str(proposal.new_parameters.get("name", target.name))
            target.material = str(proposal.new_parameters.get("material", target.material))

    return updated


def _safe_obj_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip()) or "object"


def generate_blender_script(final_room_scene: RoomScene) -> str:
    """生成 Blender Python 脚本，重建最终 3D 房间场景。"""
    lines: list[str] = [
        "import bpy",
        "",
        "# 重置场景",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete(use_global=False)",
        "",
        "# 重建房间家具",
    ]

    for idx, obj in enumerate(final_room_scene.furniture):
        obj_var = f"{_safe_obj_name(obj.name)}_{idx}"
        lines.extend(
            [
                f"# {obj.name} ({obj.material})",
                "bpy.ops.mesh.primitive_cube_add(size=1)",
                f"{obj_var} = bpy.context.active_object",
                f"{obj_var}.name = '{_safe_obj_name(obj.name)}'",
                (
                    f"{obj_var}.scale = ("
                    f"{obj.dimensions.width / 2.0:.4f}, "
                    f"{obj.dimensions.depth / 2.0:.4f}, "
                    f"{obj.dimensions.height / 2.0:.4f})"
                ),
                (
                    f"{obj_var}.location = ("
                    f"{obj.position.x:.4f}, {obj.position.y:.4f}, "
                    f"{obj.position.z + (obj.dimensions.height / 2.0):.4f})"
                ),
                f"{obj_var}.rotation_euler[2] = {obj.position.rotation_degrees:.4f} * 3.141592653589793 / 180.0",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def _select_best_rule(
    proposal: ModificationProposal, safety_results: Sequence[SafetyConstraintResult]
) -> SafetyConstraintResult | None:
    if not safety_results:
        return None

    target = proposal.original_object_id.lower()
    proposal_text = f"{proposal.reasoning} {proposal.new_parameters}".lower()

    best: SafetyConstraintResult | None = None
    best_score = -1.0
    for item in safety_results:
        snippet = item.snippet.lower()
        score = item.score
        if target in snippet:
            score += 1.0
        if (
            "flammable" in proposal_text
            and any(term in snippet for term in ("fire", "heat", "ignition"))
            or "可燃" in proposal_text
            and any(term in snippet for term in ("火灾", "高温", "热源"))
        ):
            score += 0.5
        if score > best_score:
            best_score = score
            best = item
    return best


def _compute_safety_score(
    status: str,
    proposals: Sequence[ModificationProposal],
    safety_results: Sequence[SafetyConstraintResult],
    failures: int,
) -> float:
    baseline = 85.0 if status == "APPROVED" else 60.0
    reward = min(10.0, len(proposals) * 2.0)
    grounding = 0.0
    if safety_results:
        avg = sum(item.score for item in safety_results[:5]) / min(5, len(safety_results))
        grounding = min(10.0, avg * 10.0)
    penalty = min(40.0, failures * 8.0)
    return max(0.0, min(100.0, baseline + reward + grounding - penalty))


def _material_elder_friendliness(material: str) -> str:
    lowered = material.lower()
    if any(term in lowered for term in ("marble", "tile", "glossy", "glass", "大理石", "瓷砖", "光滑", "玻璃")):
        return "不适合老年人（表面光滑，易滑倒）"
    if any(
        term in lowered
        for term in ("fabric", "foam", "wood", "matte", "vinyl", "布料", "泡沫", "木头", "哑光", "乙烯")
    ):
        return "适合老年人（保持防滑处理的前提下）"
    return "材质不明，需实地确认防滑性能"


def _infer_floor_texture_suggestion(room_scene: RoomScene) -> str:
    materials = " ".join(item.material.lower() for item in room_scene.furniture)
    if any(
        term in materials
        for term in ("glass", "marble", "polished", "tile", "大理石", "抛光", "瓷砖", "光滑")
    ):
        return "建议更换为 R10+ 防滑哑光地面材料，避免使用高光抛光地砖，降低滑倒风险。"
    return "建议使用哑光防滑地面材料，低反光度、高视觉对比度，特别在通道区域优先处理。"


# ── ASCII 2D Floor Plan Generator ──────────────────────────────────────────────

def _generate_ascii_floor_plan(final_room_scene: RoomScene) -> str:
    """基于家具坐标和尺寸，生成 ASCII 字符俯视图。"""

    if not final_room_scene.furniture:
        return "┌─────────────────────┐\n│ （无家具数据）        │\n└─────────────────────┘"

    # 计算房间边界
    all_x, all_y = [], []
    for item in final_room_scene.furniture:
        all_x.append(item.position.x)
        all_x.append(item.position.x + item.dimensions.width)
        all_y.append(item.position.y)
        all_y.append(item.position.y + item.dimensions.depth)

    if not all_x or not all_y:
        return "┌─────────────────────┐\n│ （坐标数据不足）      │\n└─────────────────────┘"

    room_min_x = max(0.0, min(all_x) - 0.5)
    room_max_x = max(all_x) + 0.5
    room_min_y = max(0.0, min(all_y) - 0.5)
    room_max_y = max(all_y) + 0.5

    room_w = room_max_x - room_min_x
    room_h = room_max_y - room_min_y

    # 最小格子尺寸：1格 = CELL_SIZE 米，向上取整
    CELL_SIZE = 0.8  # 每格 0.8 米
    cols = max(10, min(60, math.ceil(room_w / CELL_SIZE)))
    rows = max(8, min(30, math.ceil(room_h / CELL_SIZE)))

    cell_w = room_w / cols
    cell_h = room_h / rows

    # 初始化网格
    grid: list[list[str]] = [["  " for _ in range(cols)] for _ in range(rows)]

    def to_grid(x: float, y: float) -> tuple[int, int]:
        col = int((x - room_min_x) / cell_w)
        row = int((room_max_y - y) / cell_h)
        col = max(0, min(cols - 1, col))
        row = max(0, min(rows - 1, row))
        return col, row

    # 绘制墙壁边框
    for c in range(cols):
        grid[0][c] = "──"
        grid[rows - 1][c] = "──"
    for r in range(rows):
        grid[r][0] = "│ "
        grid[r][cols - 1] = " │"

    # 角落
    grid[0][0] = "┌─"
    grid[0][cols - 1] = "─┐"
    grid[rows - 1][0] = "└─"
    grid[rows - 1][cols - 1] = "─┘"

    # 绘制门窗（用符号标记边界开口）
    for door in final_room_scene.boundary.doors:
        # 简化处理：取第一个字符放在中间
        mark = "🚪"
        c, r = cols // 2, rows - 1
        grid[r][max(1, min(cols - 2, c))] = mark[:2]

    for window in final_room_scene.boundary.windows:
        mark = "□ "
        c, r = cols // 2, 0
        grid[r][max(1, min(cols - 2, c))] = mark

    # 绘制家具（按位置投影到俯视图）
    FURNITURE_SYMBOLS = [
        "🛋️", "🛏️", "🍽️", "📺", "🪑", "🗄️", "🚿", "🚽", "🧺", "🪴",
    ]

    for idx, item in enumerate(final_room_scene.furniture):
        # 俯视图只考虑 width(x) 和 depth(y)
        fx, fy = item.position.x, item.position.y
        fw, fd = item.dimensions.width, item.dimensions.depth

        # 计算占据的格子范围
        fx2 = fx + fw
        fy2 = fy + fd

        c1, r1 = to_grid(fx, fy)
        c2, r2 = to_grid(fx2, fy2)

        c1, c2 = min(c1, c2), max(c1, c2)
        r1, r2 = min(r1, r2), max(r1, r2)

        # 取符号
        symbol = FURNITURE_SYMBOLS[idx % len(FURNITURE_SYMBOLS)]
        sym = symbol[:2] if len(symbol) > 1 else symbol + " "

        # 绘制填充
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                if 0 < rr < rows - 1 and 0 < cc < cols - 1:
                    grid[rr][cc] = sym

        # 左上角标记物品名称缩写
        if r1 + 1 < rows and c1 + 1 < cols:
            abbr = _abbrev_name(item.name)
            for i, ch in enumerate(abbr[:2]):
                if c1 + 1 + i < cols - 1:
                    grid[r1 + 1][c1 + 1 + i] = ch + " "

    # 组装输出
    line_sep = "  " + "──" * cols
    lines_out = [f"  ┌{'──' * cols}┐"]
    for r, row in enumerate(grid):
        if r == 0 or r == rows - 1:
            continue
        lines_out.append("  │" + "".join(row) + "│")
    lines_out.append(f"  └{'──' * cols}┘")

    # 添加比例尺
    scale_bar = f"  比例尺：1格 = {CELL_SIZE:.1f}m  │  房间约 {room_w:.1f}m × {room_h:.1f}m"
    lines_out.append("")
    lines_out.append(scale_bar)

    # 添加图例
    legend_lines = ["  图例："]
    for idx, item in enumerate(final_room_scene.furniture[:5]):
        sym = FURNITURE_SYMBOLS[idx % len(FURNITURE_SYMBOLS)]
        legend_lines.append(f"    {sym} = {item.name}（{item.dimensions.width:.1f}×{item.dimensions.depth:.1f}m）")
    if final_room_scene.boundary.doors:
        legend_lines.append("    🚪 = 门")
    if final_room_scene.boundary.windows:
        legend_lines.append("    □  = 窗户")
    lines_out.extend(legend_lines)

    return "\n".join(lines_out)


def _abbrev_name(name: str) -> str:
    """将中文家具名称缩至2字符。"""
    # 常见家具映射
    KNOWN = {
        "沙发": "沙", "茶几": "茶", "餐桌": "桌", "椅子": "椅", "床": "床",
        "衣柜": "衣", "电视柜": "视", "书桌": "书", "床头柜": "头",
        "冰箱": "冰", "洗衣机": "洗", "马桶": "马", "洗手台": "台",
        "淋浴间": "淋", "浴缸": "浴", "储物柜": "存", "跑步机": "跑",
    }
    for k, v in KNOWN.items():
        if k in name:
            return v
    # 备用：取前2个字符
    return name[:2]


# ── Public Output Functions ────────────────────────────────────────────────────

def generate_2d_blueprint_markdown(final_room_scene: RoomScene) -> str:
    """生成 2D 俯视图 Blueprint Markdown（含 ASCII 字符画 + 坐标表）。"""

    ascii_plan = _generate_ascii_floor_plan(final_room_scene)

    lines: list[str] = [
        "# 2D 房间俯视图（平面蓝图）",
        "",
        "## 字符画俯视图",
        "```",
        ascii_plan,
        "```",
        "",
        "## 房间边界信息",
        f"- **墙面**：{', '.join(final_room_scene.boundary.walls) if final_room_scene.boundary.walls else '未标注'}",
        f"- **窗户**：{', '.join(final_room_scene.boundary.windows) if final_room_scene.boundary.windows else '未标注'}",
        f"- **门**：{', '.join(final_room_scene.boundary.doors) if final_room_scene.boundary.doors else '未标注'}",
        "",
        "## 家具坐标清单（单位：米）",
        "| 家具 | 名称 | X坐标 | Y坐标 | 宽(m) | 深(m) | 高(m) | 材质 | 旋转角度 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for item in final_room_scene.furniture:
        lines.append(
            f"| {item.name} | "
            f"{item.position.x:.2f} | {item.position.y:.2f} | "
            f"{item.dimensions.width:.2f} | {item.dimensions.depth:.2f} | "
            f"{item.dimensions.height:.2f} | {item.material} | "
            f"{item.position.rotation_degrees:.1f}° |"
        )

    lines.extend(
        [
            "",
            "## 适老化布置建议",
            "- 主要通道宽度应 ≥ 0.9m，确保轮椅/助行器顺利通过",
            "- 家具尖角应做圆角处理，降低碰撞伤害风险",
            "- 通道区域避免放置小件杂物，防止绊倒",
            "- 夜间动线（床→门/卫生间）建议安装低眩光感应灯",
            "",
            "## 地面材质建议",
            f"- {_infer_floor_texture_suggestion(final_room_scene)}",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def generate_strict_change_formula(
    final_room_scene: RoomScene,
    proposals: Sequence[ModificationProposal],
    safety_results: Sequence[SafetyConstraintResult],
) -> dict[str, Any]:
    """生成结构化变更清单（含 RAG 依据）。"""
    formula: dict[str, Any] = {
        "program_goal": "适老化房间改造设计",
        "furniture": {},
        "changes_required": [],
        "elder_redesign_plan": [],
        "floor_texture": {
            "suggestion": _infer_floor_texture_suggestion(final_room_scene),
            "short_reason": "降低老年人滑倒风险，提升行走安全。",
        },
        "rag_strict_grounding": [],
    }

    for item in final_room_scene.furniture:
        formula["furniture"][item.name] = {
            "material": item.material,
            "elder_friendliness": _material_elder_friendliness(item.material),
            "placement": {
                "x": round(item.position.x, 3),
                "y": round(item.position.y, 3),
                "z": round(item.position.z, 3),
                "rotation_degrees": round(item.position.rotation_degrees, 3),
            },
            "dimensions_m": {
                "width": round(item.dimensions.width, 3),
                "depth": round(item.dimensions.depth, 3),
                "height": round(item.dimensions.height, 3),
            },
        }
        formula["elder_redesign_plan"].append(
            {
                "zone": item.name,
                "what_to_change": (
                    "建议圆角化处理；周边保留至少 0.9m 通行空间，"
                    "避免遮挡主要动线。"
                ),
                "short_reason": "减少碰撞伤害风险，保障轮椅/助行器通过性。",
            }
        )

    for proposal in proposals:
        rule = _select_best_rule(proposal, safety_results)
        if rule is None:
            formula["changes_required"].append(
                {
                    "target": proposal.original_object_id,
                    "action": proposal.action,
                    "what_to_change": proposal.new_parameters,
                    "short_reason": proposal.reasoning[:160],
                    "grounding": {
                        "source_file": None,
                        "page_number": None,
                        "snippet": None,
                    },
                }
            )
            continue

        formula["changes_required"].append(
            {
                "target": proposal.original_object_id,
                "action": proposal.action,
                "what_to_change": proposal.new_parameters,
                "short_reason": proposal.reasoning[:160],
                "grounding": {
                    "rule_id": rule.constraint.rule_id,
                    "source_file": rule.source_file,
                    "page_number": rule.page_number,
                    "snippet": rule.snippet[:240],
                },
            }
        )

    for rule in safety_results:
        formula["rag_strict_grounding"].append(
            {
                "rule_id": rule.constraint.rule_id,
                "source_file": rule.source_file,
                "page_number": rule.page_number,
                "snippet": rule.snippet[:240],
                "score": round(rule.score, 4),
            }
        )

    if not formula["changes_required"]:
        formula["changes_required"].append(
            {
                "target": "global_layout",
                "action": "move",
                "what_to_change": {
                    "clear_path_min_width_m": 0.9,
                    "remove_trip_hazards": True,
                    "night_path_lighting": "在床到门/卫生间的路径安装低眩光感应灯",
                },
                "short_reason": "未发现单一物品违规，但适老化基线改造建议：清除绊倒隐患，保持通道宽度 ≥ 0.9m。",
                "grounding": {
                    "source_file": "GB 50763 无障碍设计规范",
                    "page_number": None,
                    "snippet": "老年人居住建筑的主要通道净宽不应小于 0.9m。",
                },
            }
        )

    return formula


def generate_elder_redesign_suggestions(
    final_room_scene: RoomScene,
    proposals: Sequence[ModificationProposal],
    safety_results: Sequence[SafetyConstraintResult],
) -> str:
    """生成详细的适老化改造建议（通俗易懂版）。
    
    【设计原则】
    - 按【家具布局】和【环境改进】分类
    - 每项建议解释对老人的具体好处
    - 用口语化描述替代技术术语
    """
    # 计算房间尺寸
    room_width = room_depth = 5.0
    if final_room_scene.furniture:
        all_x = [item.position.x for item in final_room_scene.furniture]
        all_y = [item.position.y for item in final_room_scene.furniture]
        if all_x:
            room_width = max(all_x) - min(all_x) + 1.0
        if all_y:
            room_depth = max(all_y) - min(all_y) + 1.0

    lines: list[str] = [
        "适老化房间改造详细建议",
        "=" * 50,
        "",
        "【改造目标】",
        "让您的家更适合老人居住：",
        "  - 走路不容易绊倒",
        "  - 坐下去、站起来不费劲",
        "  - 晚上起来不用摸黑",
        "  - 万一滑倒了也能及时被发现",
        "",
    ]

    # ── 家具布局调整 ─────────────────────────────────────────
    lines.append("【家具布局调整】")
    lines.append("")

    if proposals:
        for idx, proposal in enumerate(proposals, start=1):
            target = proposal.original_object_id
            
            if proposal.action == "move":
                old_x = proposal.new_parameters.get("_old_x", 0.0)
                old_y = proposal.new_parameters.get("_old_y", 0.0)
                new_x = proposal.new_parameters.get("x", old_x + 0.5)
                new_y = proposal.new_parameters.get("y", old_y)
                change = _direction_to_words(old_x, old_y, new_x, new_y)
                what_action = f"把{target}{change}"
            elif proposal.action == "resize":
                what_action = f"把{target}改小一点或换掉"
            elif proposal.action == "replace":
                what_action = f"把{target}换成更适合老人用的"
            else:
                what_action = f"调整{target}"
            
            # 口语化解释好处
            reason = proposal.reasoning
            if "heat" in reason.lower() or "火" in reason:
                benefit = "老人反应慢，离热源太近容易出事"
            elif "clearance" in reason.lower() or "通道" in reason or "空间" in reason:
                benefit = "老人走路不稳需要更多空间，这样轮椅、助行器才能过"
            elif "flammable" in reason.lower() or "可燃" in reason:
                benefit = "老人防火意识弱，用不容易烧着的更安全"
            elif "height" in reason.lower() or "高" in reason:
                benefit = "老人膝盖不好，太高太低都费劲"
            else:
                benefit = "这样老人住着更安全、更方便"
            
            # 获取规范依据（口语化）
            rule = _select_best_rule(proposal, safety_results)
            if rule:
                grounding = f"依据：{_strip_technical_reference(rule.source_file)}"
            else:
                grounding = "依据：《中国建筑无障碍设计规范》适老化通用要求"
            
            lines.extend([
                f"  改造项 {idx}：{target}",
                f"    怎么改：{what_action}",
                f"    为什么要改：{reason[:120]}",
                f"    对老人的好处：{benefit}",
                f"    {grounding}",
                "",
            ])
    else:
        lines.extend([
            "  （本次检查未发现需要调整的家具）",
            "  建议：保持现有布局，重点关注下面的【环境改进】部分。",
            "",
        ])

    # ── 环境改进建议 ─────────────────────────────────────────
    lines.extend([
        "",
        "【环境改进建议】",
        "",
    ])

    # 根据房间情况生成个性化建议
    floor_suggestion = _infer_floor_texture_suggestion(final_room_scene)
    
    # 检测是否有可燃材料
    has_flammable = any(
        "fabric" in item.material.lower() or "wood" in item.material.lower() or
        "布" in item.material or "木" in item.material
        for item in final_room_scene.furniture
    )

    suggestions = [
        {
            "title": "地面防滑处理",
            "what": floor_suggestion,
            "benefit": "老人容易滑倒，地面防滑做得好，能减少一半的摔伤风险。"
        },
        {
            "title": "夜间感应照明",
            "what": "在床到卫生间的必经路线上安装低眩光人体感应灯",
            "benefit": "老人起夜多，有灯照着不容易摔；而且灯光柔和不刺眼，不影响老伴睡觉。"
        },
        {
            "title": "门槛和台阶处理",
            "what": "如果家里有门槛，建议做成斜坡或贴上醒目的警示条",
            "benefit": "老人抬脚不高，门槛最容易绊倒；轮椅更是根本过不去。"
        },
        {
            "title": "插座和开关位置",
            "what": "把常用插座和开关调到腰部高度（离地约1米）",
            "benefit": "老人弯腰不方便，高处够不着、低处要蹲下，都很费劲。"
        },
    ]

    if has_flammable:
        suggestions.insert(0, {
            "title": "易燃物品远离热源",
            "what": "检查沙发垫、窗帘、纸箱这些易燃物品，确保离灶台、暖气片至少一大步的距离",
            "benefit": "老人防火意识弱，发现火情反应慢，远离热源能减少火灾风险。"
        })

    for idx, s in enumerate(suggestions, start=1):
        lines.extend([
            f"  {idx}. {s['title']}",
            f"     怎么做：{s['what']}",
            f"     对老人的好处：{s['benefit']}",
            "",
        ])

    # ── 家具适老化评估表 ──────────────────────────────────────
    lines.extend([
        "",
        "【家具适老化评估】",
        "",
        "  下面列出您家各件家具的适老化情况：",
        "",
    ])

    if final_room_scene.furniture:
        for item in final_room_scene.furniture:
            elder_friendly = _material_elder_friendliness(item.material)
            size_desc = _size_to_words(
                item.dimensions.width, 
                item.dimensions.depth, 
                item.dimensions.height
            )
            position_desc = _position_to_words(
                item.position.x, 
                item.position.y, 
                room_width
            )
            
            # 判断是否需要特别关注
            if "不适合" in elder_friendly:
                attention = "⚠️ 需关注"
            else:
                attention = "✓ 基本OK"
            
            lines.extend([
                f"  {item.name}（{position_desc}）",
                f"    大小：{size_desc}",
                f"    材质：{item.material}",
                f"    适老化评估：{elder_friendly}",
                f"    {attention}",
                "",
            ])
    else:
        lines.append("  暂无家具数据，请上传房间照片获取详细评估。")

    lines.extend([
        "",
        "=" * 50,
        "温馨提示",
        "=" * 50,
        "",
        "适老化改造不用一步到位，可以按优先级慢慢来：",
        "",
        "  第一优先（最危险）：地面防滑、门槛处理",
        "  第二优先（最实用）：夜间照明、通道清理",
        "  第三优先（更舒适）：家具调整、插座高度",
        "",
        "有条件的话，建议请专业适老化改造团队上门评估，",
        "他们会根据您的具体情况给出最合适的方案。",
    ])

    return "\n".join(lines).strip() + "\n"


def generate_user_friendly_suggestions_text(
    final_room_scene: RoomScene,
    proposals: Sequence[ModificationProposal],
) -> str:
    """生成面向普通用户的简洁适老化建议（纯人话版本）。
    
    【设计原则】
    - 像邻居老师傅说话一样通俗易懂
    - 每条建议都解释对老人的具体好处
    - 不出现技术术语和坐标
    """
    # 计算房间大致尺寸
    room_width = room_depth = 5.0
    if final_room_scene.furniture:
        all_x = [item.position.x for item in final_room_scene.furniture]
        all_y = [item.position.y for item in final_room_scene.furniture]
        if all_x:
            room_width = max(all_x) - min(all_x) + 1.0
        if all_y:
            room_depth = max(all_y) - min(all_y) + 1.0

    lines: list[str] = [
        "适老化改造建议（通俗版）",
        "=" * 40,
        "",
    ]

    # ── 基线建议 ──────────────────────────────────────────────
    lines.extend([
        "【通用建议 — 适合所有家庭】",
        "",
        "① 保持过道畅通",
        "   把沙发、茶几、矮凳这些容易绊脚的东西收一收。",
        f"   主要通道（从沙发/床到门/卫生间这段）最好能{_meters_to_words(0.9)}以上。",
        "   对老人的好处：走路扶不稳的时候，旁边有人能搭把手；坐轮椅或用助行器也能顺利过去。",
        "",
        "② 地面要防滑",
        f"   {_infer_floor_texture_suggestion(final_room_scene)}",
        "   对老人的好处：老人有时候不穿拖鞋就走路，地面滑的话很容易摔。",
        "",
        "③ 夜间要有感应灯",
        "   建议在床到卫生间的路线上装个感应灯，夜里起来自动亮。",
        "   对老人的好处：老人起夜多，迷迷糊糊的，有灯照着不容易摔。",
        "",
    ])

    # ── 针对本房间的具体建议 ─────────────────────────────────
    if proposals:
        lines.extend([
            "【针对您家的具体问题】",
            "",
        ])
        for idx, proposal in enumerate(proposals[:6], start=1):
            target = proposal.original_object_id
            
            if proposal.action == "move":
                old_x = proposal.new_parameters.get("_old_x", 0.0)
                old_y = proposal.new_parameters.get("_old_y", 0.0)
                new_x = proposal.new_parameters.get("x", old_x + 0.5)
                new_y = proposal.new_parameters.get("y", old_y)
                change = _direction_to_words(old_x, old_y, new_x, new_y)
            else:
                change = _action_to_human(proposal.action)
            
            # 口语化解释原因
            reason = proposal.reasoning
            if "heat" in reason.lower() or "fire" in reason.lower() or "热" in reason:
                benefit = "离热源太近容易着火，老人反应慢，发现时可能已经晚了"
            elif "clearance" in reason.lower() or "通道" in reason:
                benefit = "空间太挤，老人走路容易碰到；轮椅和助行器也过不去"
            elif "flammable" in reason.lower() or "可燃" in reason:
                benefit = "这种材质容易烧着，老人用的东西要选安全的"
            else:
                benefit = "老人住着不方便，改改更安全"
            
            lines.extend([
                f"  {idx}. {target}",
                f"     怎么办：{change}",
                f"     为什么：{reason[:80]}",
                f"     对老人好处：{benefit}",
                "",
            ])
    else:
        lines.extend([
            "【针对您家的具体问题】",
            "  从这次照片来看，您的房间整体还不错！",
            "  按照上面①②③三条做就更好了。",
            "",
        ])

    lines.extend([
        "",
        "=" * 40,
        "小贴士",
        "=" * 40,
        "",
        "适老化改造不用一次到位，可以先从最危险的地方改起。",
        "比如：先把最容易滑倒的地方处理了，再装几个感应灯，最后再慢慢调整家具位置。",
        "有条件的话，可以请社区的适老化改造专员上门看看，给的建议更准确。",
    ])

    return "\n".join(lines).strip() + "\n"




def generate_safety_report(
    final_room_scene: RoomScene,
    proposals: Sequence[ModificationProposal],
    safety_results: Sequence[SafetyConstraintResult],
    status: str,
    failure_trace: Sequence[str] | None = None,
) -> str:
    """生成面向普通用户的易懂安全审查报告。
    
    【设计原则】
    - 不出现坐标、JSON、move/rotate 等技术术语
    - 用口语化描述定位隐患位置
    - 明确标注隐患对应的照片位置
    - 每条建议都要解释对老人的具体好处
    """
    failures = list(failure_trace or [])
    safety_score = _compute_safety_score(status, proposals, safety_results, len(failures))

    status_zh = {"APPROVED": "通过", "REJECTED": "需改进"}.get(status, status)

    # 计算房间大致尺寸用于口语化定位
    room_width = room_depth = 5.0  # 默认值
    if final_room_scene.furniture:
        all_x = [item.position.x for item in final_room_scene.furniture]
        all_y = [item.position.y for item in final_room_scene.furniture]
        if all_x:
            room_width = max(all_x) - min(all_x) + 1.0
        if all_y:
            room_depth = max(all_y) - min(all_y) + 1.0

    lines: list[str] = [
        "=" * 50,
        "适老化安全审查报告",
        "=" * 50,
        "",
        "【审查结论】",
        f"  本次审查结果：{status_zh}",
        f"  安全评分：{safety_score:.0f}/100",
        f"  本次共检查了 {len(final_room_scene.furniture)} 件家具和用品",
        "",
    ]

    # ── 风险分类描述 ──────────────────────────────────────────────
    if proposals:
        lines.extend([
            "【需要关注的问题】",
            "",
        ])
        for idx, proposal in enumerate(proposals, start=1):
            rule = _select_best_rule(proposal, safety_results)
            target_name = proposal.original_object_id
            
            # 口语化描述变更
            if proposal.action == "move":
                old_x = proposal.new_parameters.get("_old_x", 0.0)
                old_y = proposal.new_parameters.get("_old_y", 0.0)
                new_x = proposal.new_parameters.get("x", old_x + 0.5)
                new_y = proposal.new_parameters.get("y", old_y)
                change_desc = _direction_to_words(old_x, old_y, new_x, new_y)
            else:
                change_desc = _action_to_human(proposal.action)
            
            lines.append(f"  问题 {idx}：{target_name}")
            lines.append(f"         建议：{change_desc}")
            lines.append(f"         原因：{proposal.reasoning[:80]}")
            
            if rule:
                # 口语化规范引用
                doc_name = _strip_technical_reference(rule.source_file)
                lines.append(f"         依据：{doc_name}")
            
            lines.append("")

    if not proposals:
        lines.extend([
            "【审查结果】",
            "  ✅ 本次审查未发现重大安全隐患",
            "  ✅ 您的房间整体布局基本合理",
            "",
        ])

    # ── 适老化基线建议（始终提供） ────────────────────────────────
    lines.extend([
        "【适老化改造建议】",
        "",
        "  根据《中国建筑无障碍设计规范》，我们建议您关注以下方面：",
        "",
        "  1. 通道空间",
        "     建议：主要通道（床或沙发 → 门/卫生间）保持足够宽敞",
        "     对老人的好处：老人走路不稳时，身边有人能搭把手；轮椅、助行器能顺利通过",
        "",
        "  2. 地面防滑",
        "     建议：选用防滑性能好的地面材料，特别是卫生间门口和厨房",
        "     对老人的好处：大大降低滑倒风险，老人赤脚走路也不怕",
        "",
        "  3. 夜间照明",
        "     建议：在床到卫生间的路线安装感应灯，夜间起身自动亮起",
        "     对老人的好处：老人起夜不用摸黑找开关，避免摔倒在黑暗的走廊",
        "",
    ])

    # ── 审查过程记录 ──────────────────────────────────────────────
    if failures:
        lines.extend([
            "",
            "【审查过程记录】",
        ])
        for item in failures:
            lines.append(f"  ⚠️  {item}")
    else:
        lines.extend([
            "",
            "【审查过程记录】",
            "  ✅ 安全审查官未发现违规项",
        ])

    lines.extend([
        "",
        "=" * 50,
        "报告说明",
        "=" * 50,
        "",
        "本报告依据国家相关建筑规范，结合您的房间实际情况生成。",
        "如有任何疑问，建议咨询专业适老化改造团队进行现场评估。",
    ])

    return "\n".join(lines).strip() + "\n"


def _strip_technical_reference(filename: str) -> str:
    """将技术文件名转换为规范全称。"""
    if not filename:
        return "相关国家标准"
    
    # 去除 .pdf、_processed 等后缀
    name = filename.split(".")[0] if "." in filename else filename
    name = name.replace("_processed", "").replace("_chunks", "").replace("_", " ")
    
    # 常见规范名称映射（不区分大小写）
    norm_names = {
        "gb50016": "《建筑设计防火规范》",
        "gb50222": "《建筑内部装修设计防火规范》",
        "gb50352": "《民用建筑设计统一标准》",
        "gb50763": "《中国建筑无障碍设计规范》",
    }
    
    name_lower = name.lower()
    for code, full_name in norm_names.items():
        if code in name_lower:
            return full_name
    
    # 如果是其他文件，返回清洗后的名称
    # 将下划线转为空格，首字母大写
    readable_name = " ".join(word.capitalize() for word in name.split())
    return f"《{readable_name}》"
