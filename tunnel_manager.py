#!/usr/bin/env python3
"""
Cloudflare Tunnel Manager
=========================
使用 cloudflared 异步启动隧道，实时解析并醒目展示公网 URL。

依赖:
    pip install colorama

安装 cloudflared (macOS):
    brew install cloudflared

安装 cloudflared (Linux):
    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
    chmod +x /usr/local/bin/cloudflared
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from colorama import init as colorama_init, Fore, Style

    colorama_init(autoreset=True)
    _HAS_COLORAMA = True
except ImportError:
    _HAS_COLORAMA = False

    class _DummyFore:
        CYAN = RED = GREEN = YELLOW = MAGENTA = WHITE = BLUE = BRIGHT = RESET_ALL = ""

    class _DummyStyle:
        BRIGHT = RESET_ALL = ""

    Fore = _DummyFore()
    Style = _DummyStyle()


# ── Config ──────────────────────────────────────────────────────────────────────

LOCAL_PORT = 8080
TUNNEL_CMD = ["cloudflared", "tunnel", "--url", f"http://localhost:{LOCAL_PORT}"]
CFD_ARROW_RE = re.compile(
    r"https://[a-z0-9\-]+\.trycloudflare\.com",
    re.IGNORECASE,
)


def _has_cloudflared() -> bool:
    return shutil.which("cloudflared") is not None


def _print_banner():
    print()
    print(
        f"{Fore.CYAN}{Style.BRIGHT}"
        + "═" * 62
    )
    print(
        f"  🛡️  Cloudflare Tunnel Manager"
        f"  {Fore.WHITE}|{Fore.CYAN}  Local: http://localhost:{LOCAL_PORT}"
    )
    print(
        f"{Fore.CYAN}{Style.BRIGHT}" + "═" * 62
        + f"{Style.RESET_ALL}"
    )
    print()


def _print_url(url: str):
    print()
    print(
        f"{Fore.GREEN}{Style.BRIGHT}"
        + "★" * 62
    )
    print(f"{Fore.GREEN}{Style.BRIGHT}   🌐  公网访问链接 (可分享给任何人):")
    print()
    print(
        f"   {Fore.YELLOW}{Style.BRIGHT}{url}"
    )
    print()
    print(
        f"{Fore.GREEN}{Style.BRIGHT}"
        + "★" * 62
        + f"{Style.RESET_ALL}"
    )
    print()
    print(f"{Fore.WHITE}   按 {Fore.YELLOW}Ctrl+C {Fore.WHITE}停止隧道")
    print()


def _print_status(msg: str, color=Fore.WHITE):
    ts = time.strftime("%H:%M:%S")
    print(f"{Fore.BLUE}[{ts}]{color} {msg}{Style.RESET_ALL}")


def _monitor_stream(stream, prefix: str = ""):
    """实时打印 cloudflared 的 stdout/stderr，提取 URL 并触发回调。"""
    url_found = False
    buf = ""

    try:
        for chunk in stream:
            if chunk:
                decoded = chunk.decode("utf-8", errors="replace")
                sys.stdout.write(decoded)
                sys.stdout.flush()
                buf += decoded

                if not url_found:
                    for line in buf.splitlines(keepends=True):
                        match = CFD_ARROW_RE.search(line)
                        if match:
                            url_found = True
                            _print_url(match.group(0))
                            buf = buf[buf.index(match.group(0)) + len(match.group(0)) :]
    except Exception:
        pass


def run_tunnel():
    """启动 cloudflared tunnel，异步监听输出并提取公网 URL。"""
    _print_banner()

    if not _has_cloudflared():
        print(
            f"{Fore.RED}{Style.BRIGHT}✖ cloudflared 未安装！{Style.RESET_ALL}"
        )
        print()
        print(f"  请先安装:")
        print(f"  {Fore.CYAN}macOS:  brew install cloudflared{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}Linux:  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared{Style.RESET_ALL}")
        print()
        sys.exit(1)

    _print_status("正在连接 Cloudflare 全球网络...")
    _print_status("启动 cloudflared tunnel → http://localhost:8080")

    try:
        proc = subprocess.Popen(
            TUNNEL_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError:
        print(f"{Fore.RED}✖ 找不到 cloudflared，请确认已安装并加入 PATH{Style.RESET_ALL}")
        sys.exit(1)

    _print_status("cloudflared 进程已启动 (PID: " + str(proc.pid) + ")", Fore.GREEN)

    thread = threading.Thread(target=_monitor_stream, args=(proc.stdout,), daemon=True)
    thread.start()

    try:
        while True:
            time.sleep(0.5)
            if proc.poll() is not None:
                print(f"{Fore.RED}✖ cloudflared 意外退出，退出码: {proc.returncode}{Style.RESET_ALL}")
                break
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}收到停止信号，正在关闭隧道...{Style.RESET_ALL}")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(f"{Fore.GREEN}✓ 隧道已关闭{Style.RESET_ALL}")
        sys.exit(0)


if __name__ == "__main__":
    run_tunnel()
