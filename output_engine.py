"""输出生成器 — 适老化房间安全合规审查报告、2D 俯视图与 Blender 脚本。"""

from __future__ import annotations

import math
from typing import Any, Sequence

from knowledge_base import SafetyConstraintResult
from models import ModificationProposal, RoomScene


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
    """生成详细的适老化改造建议（Markdown）。"""
    lines: list[str] = [
        "# 适老化房间改造详细建议",
        "",
        "## 设计目标",
        "- 保障老年人日常生活的安全性、无障碍性与舒适度。",
        "",
        "## 优先改造项目",
    ]

    if proposals:
        for idx, proposal in enumerate(proposals, start=1):
            rule = _select_best_rule(proposal, safety_results)
            lines.append(f"### 改造项 {idx}：{proposal.original_object_id}")
            lines.append(f"- **操作类型**：`{proposal.action}`，参数：`{proposal.new_parameters}`")
            lines.append(f"- **原因说明**：{proposal.reasoning[:180]}")
            if rule:
                lines.append(
                    f"- **标准依据**：`{rule.source_file}` 第 {rule.page_number} 页；"
                    f"摘要：{rule.snippet[:180].replace(chr(10), ' ')}"
                )
            else:
                lines.append("- **标准依据**：无直接匹配标准，执行保守适老化安全基线。")
            lines.append("")
    else:
        lines.extend(
            [
                "### 改造项 1：优化通道空间",
                "- **操作**：主要通道（床/座椅→门/卫生间）宽度维持在 ≥ 0.9m。",
                "- **原因**：保障轮椅和助行器的顺利通过，降低跌倒风险。",
                "",
                "### 改造项 2：更换地面材质",
                f"- **操作**：{_infer_floor_texture_suggestion(final_room_scene)}",
                "- **原因**：减少老年人常见滑倒事故。",
                "",
                "### 改造项 3：安装夜间感应照明",
                "- **操作**：在床至门/卫生间的路径安装低眩光人体感应灯。",
                "- **原因**：防止老年人夜间如厕时因视线不清而跌倒。",
                "",
            ]
        )

    lines.extend(
        [
            "## 家具适老化评估",
            "| 家具 | 材质 | 适老化评估 | 建议调整 |",
            "|---|---|---|---|",
        ]
    )
    for item in final_room_scene.furniture:
        lines.append(
            f"| {item.name} | {item.material} | "
            f"{_material_elder_friendliness(item.material)} | "
            "圆角化处理，保持周边 0.9m 净空，不阻挡主要通道。 |"
        )

    if not final_room_scene.furniture:
        lines.append("| 暂无数据 | — | — | 请上传房间照片获取分析结果。 |")

    return "\n".join(lines).strip() + "\n"


def generate_user_friendly_suggestions_text(
    final_room_scene: RoomScene,
    proposals: Sequence[ModificationProposal],
) -> str:
    """生成面向普通用户的简洁适老化建议（纯文本）。"""
    lines: list[str] = [
        "适老化房间改造建议",
        "",
        "① 保持通道畅通：",
        "   主要通道（床、座椅 → 门/卫生间）宽度至少保留 0.9 米，方便轮椅或助行器通过。",
        "",
        "② 地面防滑处理：",
        f"   {_infer_floor_texture_suggestion(final_room_scene)}",
        "",
        "③ 夜间照明安全：",
        "   建议在床到门/卫生间的路线上安装低眩光人体感应灯，防止夜间如厕时跌倒。",
        "",
    ]
    if proposals:
        lines.append("本房间检测到的具体改造建议：")
        for idx, proposal in enumerate(proposals[:6], start=1):
            lines.append(
                f"   {idx}. {proposal.original_object_id}："
                f"建议{_action_zh(proposal.action)}。"
                f"理由：{proposal.reasoning[:100]}"
            )
    else:
        lines.extend(
            [
                "本房间检测到的具体改造建议：",
                "   本次分析未发现重大违规项，建议按上述 ① ② ③ 三项执行适老化基线改造。",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _action_zh(action: str) -> str:
    return {"move": "移动位置", "resize": "调整尺寸", "replace": "更换/移除"}.get(
        action, action
    )


def generate_safety_report(
    final_room_scene: RoomScene,
    proposals: Sequence[ModificationProposal],
    safety_results: Sequence[SafetyConstraintResult],
    status: str,
    failure_trace: Sequence[str] | None = None,
) -> str:
    """生成安全审查报告（含评分、依据和失败追踪）。"""
    failures = list(failure_trace or [])
    safety_score = _compute_safety_score(status, proposals, safety_results, len(failures))

    status_zh = {"APPROVED": "通过", "REJECTED": "不通过"}.get(status, status)

    lines: list[str] = [
        "# 建筑合规安全审查报告",
        "",
        "## 最终结论",
        f"- **审查结果**：**{status_zh}**",
        f"- **安全评分**：**{safety_score:.1f}/100**",
        f"- **场景内家具数量**：**{len(final_room_scene.furniture)} 件**",
        "",
        "## 变更审查清单",
        "",
        "| 变更对象 | 操作 | 对应安全规则 | 来源文件 | 页码 | 规则摘要 |",
        "|---|---|---|---|---|---|",
    ]

    for proposal in proposals:
        rule = _select_best_rule(proposal, safety_results)
        if rule is None:
            lines.append(
                f"| {proposal.original_object_id} | {proposal.action} | "
                "无直接匹配规则 | — | — | — |"
            )
            continue

        snippet = rule.snippet.replace("\n", " ").strip()
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        lines.append(
            "| "
            f"{proposal.original_object_id} | {proposal.action} | "
            f"{rule.constraint.rule_id}（{rule.constraint.material_requirement}）| "
            f"{rule.source_file} | {rule.page_number} | "
            f"{snippet} |"
        )

    if not proposals:
        lines.append("| 暂无变更项 | — | 无 | — | — | — |")

    lines.extend(["", "## 审查失败追踪"])
    if failures:
        for item in failures:
            lines.append(f"- ❌ {item}")
    else:
        lines.append("✅ 安全审查官未记录任何失败项。")

    lines.extend(
        [
            "",
            "## 报告说明",
            "本报告基于 ChromaDB RAG 知识库检索结果，引用 GB 标准原文并标注来源页码，",
            "以确保每项安全结论均可追溯、可查证。",
        ]
    )
    return "\n".join(lines).strip() + "\n"
