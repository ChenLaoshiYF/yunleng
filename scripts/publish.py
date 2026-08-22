"""一键发布：创建 GitHub 仓库（yunleng / chening）+ 配 remote + push。

用法（在项目根执行）：
    python scripts/publish.py
或：
    python C:\\Users\\yifan chen\\Desktop\\QingOH-WorkSpace\\projects\\camera-mcp-server\\scripts\\publish.py

凭据：从 C:\\Users\\yifan chen\\.git-credentials 读取 token。
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
import urllib.error

USER = "ChenLaoshiYF"
ROOT = r"C:\Users\yifan chen\Desktop\QingOH-WorkSpace\projects"

# (本地目录, 仓库名, 描述)
PROJECTS = [
    ("camera-mcp-server", "yunleng",
     "摄像头视觉 MCP Server，给 AI Agent 装上眼睛 —— 来自西工大电子信息Mr.chen"),
    ("cumcm-skills", "chening",
     "国赛数模方法论 Skill 包，18 题三年血泪浓缩 —— 来自西工大电子信息Mr.chen"),
]


def get_token() -> str:
    with open(r"C:\Users\yifan chen\.git-credentials", encoding="utf-8") as f:
        return f.read().strip().splitlines()[0].split("@")[0].split(":")[-1]


def create_repo(token: str, name: str, desc: str) -> str:
    """创建公开仓库，返回 html_url；已存在则返回已有 URL。"""
    req = urllib.request.Request(
        "https://api.github.com/user/repos",
        data=json.dumps({"name": name, "description": desc, "private": False}).encode(),
        headers={"Authorization": f"token {token}", "Content-Type": "application/json",
                 "User-Agent": "hanako", "Accept": "application/vnd.github+json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())["html_url"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 422 and "already exists" in body:
            return f"https://github.com/{USER}/{name}"  # 已存在，直接复用
        raise RuntimeError(f"创建 {name} 失败 HTTP {e.code}: {body[:200]}")


def push(project_dir: str, url: str):
    """配 remote（幂等）并 push master 分支。"""
    git = lambda *a: subprocess.run(["git", "-C", project_dir, *a], check=True)
    git("remote", "remove", "origin") if "origin" in subprocess.run(
        ["git", "-C", project_dir, "remote"], capture_output=True, text=True
    ).stdout.split() else None
    git("remote", "add", "origin", url)
    git("push", "-u", "origin", "master")


def main():
    token = get_token()
    for project_dir, repo, desc in PROJECTS:
        path = os.path.join(ROOT, project_dir)
        print(f"== {project_dir} -> {repo} ==")
        url = create_repo(token, repo, desc)
        print(f"  repo: {url}")
        push(path, url)
        print(f"  pushed OK")
    print("\n全部完成")


if __name__ == "__main__":
    main()
