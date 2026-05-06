#!/usr/bin/env python3
"""内网穿透启动脚本 - 一键获取公网访问链接"""

import subprocess
import re
import sys
import os


def start_tunnel():
    print("🚀 正在启动内网穿透...")
    print("   提示：如果启动失败，请确保已安装 cloudflared")
    print()

    # 检查 cloudflared 是否安装
    try:
        subprocess.run(
            ["cloudflared", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ 错误：未找到 cloudflared 命令")
        print("   请先安装 cloudflared：")
        print("   macOS: brew install cloudflared")
        print("   Linux: curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared")
        sys.exit(1)

    # 启动命令
    cmd = ["cloudflared", "tunnel", "--url", "http://localhost:8080"]

    # 开启子进程并监听输出
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

    tunnel_url = None

    for line in iter(process.stdout.readline, ""):
        # 实时打印原始日志（调试用，取消注释可以看到）
        # print(line, end="")

        # 使用正则匹配链接
        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if match:
            tunnel_url = match.group(0)
            print()
            print("=" * 50)
            print("🎉 网站已上线！演示链接如下：")
            print()
            print(f"   \033[1;32;40m {tunnel_url} \033[0m")  # 绿色加粗显示
            print()
            print("=" * 50)
            print()
            print("按 Ctrl+C 可以停止分享。")
            print()
            break

    if not tunnel_url:
        # 如果没找到链接，继续监听
        for line in iter(process.stdout.readline, ""):
            match = re.search(
                r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line
            )
            if match:
                tunnel_url = match.group(0)
                print()
                print("=" * 50)
                print("🎉 网站已上线！演示链接如下：")
                print()
                print(f"   \033[1;32;40m {tunnel_url} \033[0m")
                print()
                print("=" * 50)
                print()
                print("按 Ctrl+C 可以停止分享。")
                print()
                break

    # 保持进程运行
    if tunnel_url:
        process.wait()


if __name__ == "__main__":
    try:
        start_tunnel()
    except KeyboardInterrupt:
        print()
        print("🛑 隧道已关闭")
        print("感谢使用！")
