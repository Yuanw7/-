"""
FastAPI application — 建筑合规审查 Agent
启动方式:
  python main.py          (默认 http://0.0.0.0:8080)

【防御性设计】
所有异常均经过 try/except 处理，解析失败时返回合法的 error JSON，
确保前端永不白屏，并记录完整错误日志供调试。
"""

from __future__ import annotations

import logging
import os
import traceback
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from typing import Annotated, Any

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("room_compliance_api")

# Validate required environment variables at startup
_required_vars = ["ZHIPUAI_API_KEY"]
_missing = [v for v in _required_vars if not os.environ.get(v)]
if _missing:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(_missing)}. "
        f"Copy .env.example to .env and fill in your values."
    )

from agent_logic import run_design_agent
from output_engine import (
    apply_modifications,
    generate_2d_blueprint_markdown,
    generate_blender_script,
    generate_elder_redesign_suggestions,
    generate_safety_report,
    generate_strict_change_formula,
    generate_user_friendly_suggestions_text,
)
from vision_engine import analyze_room_image, analyze_room_images

logger.info("Environment validated. API starting...")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="建筑合规审查 Agent API",
    description="基于 GB 标准的适老化房间安全合规审查系统",
    version="1.0.0",
)

# CORS — allow ALL origins for cloudflare tunnel compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve index.html at root
INDEX_HTML = Path(__file__).parent / "index.html"


@app.get("/")
async def serve_index():
    """Serve the glassmorphism frontend at the root URL."""
    return FileResponse(str(INDEX_HTML))


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}


MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


@app.post("/analyze-room")
async def analyze_room(
    files: Annotated[list[UploadFile], File(description="房间照片，支持多张（接龙顺序）")],
    calibration_data: Annotated[str | None, Form(description="参照物校准数据 JSON")] = None,
) -> dict[str, object]:
    """
    分析房间图片，返回完整的适老化合规审查结果。

    【接口升级 — 多图空间链】
    - 接收 files（List[UploadFile]）和 calibration_data（dict）
    - 按上传顺序编号，利用图片 Overlap 构建空间拓扑
    - 将参照物尺寸注入 Prompt 作为唯一比例尺

    【防御性设计】
    - 所有层级均用 try/except 包裹
    - 任何解析失败均返回合法 JSON，前端永不白屏
    - 错误详情写入日志，便于工程师排查
    """
    # ── 解析校准数据 ─────────────────────────────────────────────────
    calibration: dict[str, Any] = {}
    if calibration_data:
        try:
            import json as _json

            calibration = _json.loads(calibration_data)
            if not isinstance(calibration, dict):
                raise ValueError("calibration_data must be a JSON object")
        except Exception as exc:
            logger.warning("calibration_data 解析失败: %s，使用默认空校准", exc)

    # ── 验证文件列表 ────────────────────────────────────────────────
    if not files:
        raise HTTPException(status_code=400, detail="至少需要上传一张房间照片。")

    valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
    temp_paths: list[Path] = []

    try:
        for idx, file in enumerate(files):
            if not file.filename:
                raise HTTPException(
                    status_code=400,
                    detail=f"第 {idx + 1} 个文件缺少文件名。",
                )
            suffix = Path(file.filename).suffix.lower() or ".jpg"
            if suffix not in valid_exts:
                raise HTTPException(
                    status_code=400,
                    detail=f"第 {idx + 1} 个文件格式不支持（{suffix}），仅支持 jpg/jpeg/png/webp。",
                )

            content = await file.read()
            if len(content) > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"第 {idx + 1} 个文件超过 {MAX_FILE_SIZE_MB}MB 限制。",
                )

            temp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
            temp_path.write_bytes(content)
            temp_paths.append(temp_path)

        logger.info(
            "接收到 %d 张图片，校准数据=%s",
            len(temp_paths),
            {"ref_object": calibration.get("ref_object"), "ref_size_m": calibration.get("ref_size_m")},
        )

        # ── 阶段 1: 视觉分析（自动选择单图/多图模式） ───────────────────
        if len(temp_paths) == 1:
            room_scene = analyze_room_image(
                str(temp_paths[0]),
                calibration_data=calibration,
            )
        else:
            room_scene = analyze_room_images(
                [str(p) for p in temp_paths],
                calibration_data=calibration,
            )

        logger.info("视觉分析完成: %d 件家具", len(room_scene.furniture))

        # ── 阶段 2: Agent 推理 ───────────────────────────────────────────
        agent_state = run_design_agent(room_scene)
        proposals = agent_state["proposals"]
        status = agent_state["status"]
        failure_trace = agent_state["failure_trace"]
        safety_results = agent_state["safety_results"]
        logger.info(
            "Agent state: status=%s, proposals=%d, failures=%d",
            status, len(proposals), len(failure_trace),
        )

        # ── 阶段 3: 应用变更（如 APPROVED） ───────────────────────────────
        final_scene = (
            apply_modifications(room_scene, proposals)
            if status == "APPROVED"
            else room_scene
        )

        # ── 阶段 4: 生成所有输出报告 ────────────────────────────────────
        blender_script = generate_blender_script(final_scene)
        blueprint_2d = generate_2d_blueprint_markdown(final_scene)
        strict_change_formula = generate_strict_change_formula(
            final_room_scene=final_scene,
            proposals=proposals,
            safety_results=safety_results,
        )
        elder_redesign_suggestions = generate_elder_redesign_suggestions(
            final_room_scene=final_scene,
            proposals=proposals,
            safety_results=safety_results,
        )
        user_friendly_suggestions = generate_user_friendly_suggestions_text(
            final_room_scene=final_scene,
            proposals=proposals,
        )
        safety_report = generate_safety_report(
            final_room_scene=final_scene,
            proposals=proposals,
            safety_results=safety_results,
            status=status,
            failure_trace=failure_trace,
        )

        return {
            "status": status,
            "room_scene": final_scene.model_dump(),
            "modification_proposals": [proposal.model_dump() for proposal in proposals],
            "failure_trace": failure_trace,
            "blender_script": blender_script,
            "blueprint_2d_markdown": blueprint_2d,
            "strict_change_formula": strict_change_formula,
            "elder_redesign_suggestions_markdown": elder_redesign_suggestions,
            "user_friendly_suggestions_text": user_friendly_suggestions,
            "safety_report_markdown": safety_report,
            "reasoning_trace_file": "reasoning_trace.json",
            # 元数据
            "_parse_success": True,
            "_parse_error": None,
            "_images_count": len(temp_paths),
            "_calibration": {
                "ref_object": calibration.get("ref_object"),
                "ref_size_m": calibration.get("ref_size_m"),
            },
        }

    except HTTPException:
        raise

    except FileNotFoundError as exc:
        logger.error("FileNotFoundError: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except ValueError as exc:
        logger.error("ValueError: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except EnvironmentError as exc:
        logger.error("EnvironmentError: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Pipeline execution failed: %s\nTraceback:\n%s", error_msg, tb)
        raise HTTPException(
            status_code=500,
            detail=(
                f"Pipeline execution failed: {error_msg}\n"
                f"（完整错误已记录到服务器日志）"
            ),
        ) from exc

    finally:
        for p in temp_paths:
            if p.exists():
                p.unlink()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info",
    )
