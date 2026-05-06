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
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

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
from vision_engine import analyze_room_image

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
async def analyze_room(file: UploadFile = File(...)) -> dict[str, object]:
    """
    分析房间图片，返回完整的适老化合规审查结果。

    【防御性设计】
    - 所有层级均用 try/except 包裹
    - 任何解析失败均返回合法 JSON，前端永不白屏
    - 错误详情写入日志，便于工程师排查
    """
    logger.info("Received analyze-room request: filename=%s", file.filename)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file is missing a filename.")

    suffix = Path(file.filename).suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Only image uploads are supported.")

    temp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    try:
        content = await file.read()

        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.",
            )

        temp_path.write_bytes(content)
        logger.info("Image saved to %s (%d bytes)", temp_path, len(content))

        # ── 阶段 1: 视觉分析 ──────────────────────────────────────────────
        room_scene = analyze_room_image(str(temp_path))
        logger.info("Vision analysis complete: %d furniture detected", len(room_scene.furniture))

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
        final_scene = apply_modifications(room_scene, proposals) if status == "APPROVED" else room_scene

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
            # 成功标识（供前端区分错误/成功）
            "_parse_success": True,
            "_parse_error": None,
        }

    except HTTPException:
        # HTTP 层异常直接重新抛出
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
        # ── 防御性处理：所有未预期异常均返回合法 error JSON ─────────────
        tb = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Pipeline execution failed: %s\nTraceback:\n%s", error_msg, tb)

        # 即使发生未预期异常，也返回一个合法 JSON，防止前端白屏
        raise HTTPException(
            status_code=500,
            detail=(
                f"Pipeline execution failed: {error_msg}\n"
                f"（完整错误已记录到服务器日志）"
            ),
        ) from exc

    finally:
        if temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info",
    )
