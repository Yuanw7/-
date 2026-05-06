#!/usr/bin/env python3
"""API 真实性验证脚本 — 测试 /analyze-room 接口是否返回动态分析结果。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

API_BASE = "http://localhost:8080"
TEST_IMAGE = Path(__file__).parent / "test_room.jpg"


def wait_for_backend(timeout: float = 15.0) -> bool:
    """等待后端就绪。"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{API_BASE}/health", timeout=3)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def run_test() -> dict:
    """发送真实图片请求，返回完整响应 JSON。"""
    if not TEST_IMAGE.exists():
        raise FileNotFoundError(f"测试图片不存在: {TEST_IMAGE}")

    print(f"📤 发送图片: {TEST_IMAGE} ({TEST_IMAGE.stat().st_size} bytes)")
    print(f"⏳ 等待响应中（首次调用需加载模型，预计 10~30 秒）...\n")

    with open(TEST_IMAGE, "rb") as f:
        files = {"file": (TEST_IMAGE.name, f, "image/jpeg")}
        start = time.time()
        resp = requests.post(
            f"{API_BASE}/analyze-room",
            files=files,
            timeout=120,
        )
        elapsed = time.time() - start

    print(f"✅ 响应状态码: {resp.status_code}  ({elapsed:.1f}s)\n")

    if resp.status_code != 200:
        print(f"❌ 请求失败:")
        try:
            detail = resp.json().get("detail", resp.text)
            print(f"   {detail}")
        except Exception:
            print(f"   {resp.text[:300]}")
        sys.exit(1)

    data = resp.json()
    return data


def check_is_dynamic(data: dict) -> tuple[bool, str]:
    """验证 API 返回的是否为动态分析结果，而非硬编码模板。"""
    findings: list[str] = []
    is_dynamic = True

    # 1. 检查 status 字段是否在预期范围内
    status = data.get("status", "")
    if status not in ("PENDING", "APPROVED", "REJECT", "REJECTED"):
        findings.append(f"  ⚠️  status='{status}' 不在预期值范围")
        is_dynamic = False
    else:
        findings.append(f"  ✅ status='{status}' 在预期范围")

    # 2. 检查 room_scene 中的 furniture 数量（0 可能是模板）
    room_scene = data.get("room_scene", {})
    furniture = room_scene.get("furniture", [])
    findings.append(f"  家具数量: {len(furniture)}")

    if len(furniture) == 0:
        findings.append(f"  ⚠️  家具数量为 0，可能是质量检测被拒或模型未能识别")
    else:
        # 检查家具名称是否来自预定义列表
        all_names = [f.get("name", "") for f in furniture]
        findings.append(f"  家具名称: {all_names}")

        # 3. 检查坐标是否为默认值（0,0）— 动态分析应有实际坐标
        zero_coords = all(
            f.get("position", {}).get("x", 0) == 0
            and f.get("position", {}).get("y", 0) == 0
            for f in furniture
        )
        if zero_coords:
            findings.append(f"  ⚠️  所有家具坐标均为 (0,0)，可能未进行真实坐标估算")
            # 不直接判定为非动态，因为可能是原点恰好重叠
        else:
            sample = furniture[0]
            pos = sample.get("position", {})
            findings.append(
                f"  ✅ 首个家具 ({sample.get('name')}) 坐标: "
                f"x={pos.get('x')}, y={pos.get('y')}, z={pos.get('z')}"
            )

        # 4. 检查尺寸是否为默认值
        default_dims = all(
            f.get("dimensions", {}).get("width", 0) < 0.05
            for f in furniture
        )
        if default_dims:
            findings.append(f"  ⚠️  所有家具宽高均 < 0.05m，可能使用了默认占位值")
        else:
            findings.append(f"  ✅ 家具具有非默认尺寸")

    # 5. 检查 blueprint_2d_markdown 是否包含动态内容
    blueprint = data.get("blueprint_2d_markdown", "")
    static_markers = [
        "N/A",
        "No changes detected",
        "No modifications",
        "no conflict",
        "mock",
        "template",
    ]
    has_static = any(m.lower() in blueprint.lower() for m in static_markers)
    findings.append(f"  blueprint_2d_markdown 长度: {len(blueprint)} 字符")
    if has_static:
        findings.append(f"  ⚠️  blueprint 包含静态标记词，可能为固定模板")
    else:
        findings.append(f"  ✅ blueprint 包含动态生成的俯视图内容")

    # 6. 检查家具坐标是否与 blueprint 中的一致
    if furniture and blueprint:
        first_name = furniture[0].get("name", "")
        if first_name not in blueprint:
            findings.append(
                f"  ⚠️  blueprint 中未找到家具名 '{first_name}'，"
                f"可能 blueprint 使用了不同的硬编码数据"
            )
            is_dynamic = False
        else:
            findings.append(f"  ✅ blueprint 与 room_scene 数据一致")

    # 7. 检查 JSON 中的所有浮点数值是否全为 0
    json_str = json.dumps(data)
    import re

    float_values = re.findall(r':\s*([0-9]+\.[0-9]+)', json_str)
    nonzero = [f for f in float_values if float(f) != 0.0]
    findings.append(f"  JSON 中非零浮点数数量: {len(nonzero)}")
    if len(nonzero) < 3:
        findings.append(f"  ⚠️  数据几乎全为 0 或 0.0，疑似硬编码模板")
        is_dynamic = False

    verdict = "✅ 动态生成" if is_dynamic else "⚠️ 疑似模板"
    return is_dynamic, "\n".join(findings)


def main() -> None:
    print("=" * 60)
    print("  API 真实性验证 — 适老化建筑合规审查系统")
    print("=" * 60)
    print()

    if not wait_for_backend():
        print("❌ 后端服务未启动，请先运行: python main.py")
        sys.exit(1)

    print("✅ 后端服务已就绪\n")

    data = run_test()

    print("=" * 60)
    print("  验证分析")
    print("=" * 60)
    is_dynamic, findings = check_is_dynamic(data)
    print(findings)
    print()

    # 打印关键字段摘要
    print("=" * 60)
    print("  关键字段摘要")
    print("=" * 60)
    print(f"  status: {data.get('status')}")
    print(f"  furniture count: {len(data.get('room_scene', {}).get('furniture', []))}")
    print(f"  proposals count: {len(data.get('modification_proposals', []))}")
    print(f"  blueprint length: {len(data.get('blueprint_2d_markdown', ''))} chars")
    print(f"  strict_change_formula keys: {list(data.get('strict_change_formula', {}).keys())}")
    print()

    # 打印首条 proposal（如果存在）
    proposals = data.get("modification_proposals", [])
    if proposals:
        p = proposals[0]
        print(f"  首条 proposal:")
        print(f"    target: {p.get('original_object_id')}")
        print(f"    action: {p.get('action')}")
        print(f"    reasoning: {str(p.get('reasoning', ''))[:80]}...")
    print()

    # 打印 room_scene 中的前两条 furniture
    furniture = data.get("room_scene", {}).get("furniture", [])
    if furniture:
        print(f"  家具详情（前 2 条）:")
        for item in furniture[:2]:
            pos = item.get("position", {})
            dims = item.get("dimensions", {})
            print(
                f"    {item.get('name')} | "
                f"pos=({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f}, {pos.get('z', 0):.2f}) | "
                f"dims={dims.get('width', 0):.2f}×{dims.get('depth', 0):.2f}×{dims.get('height', 0):.2f}m"
            )
    print()

    print("=" * 60)
    print(f"  最终判定: {findings.split(chr(10))[0]}")
    print("=" * 60)

    # 保存完整响应到文件
    out_path = Path(__file__).parent / "api_response_full.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n📄 完整响应已保存到: {out_path}")
    print()

    if is_dynamic:
        print("🎉 API 验证成功：输出为实时分析结果而非范例。")
    else:
        print("⚠️  需要人工复查 — 部分指标显示可能存在硬编码数据。")


if __name__ == "__main__":
    main()
