# yunleng 摄像头视觉 MCP Server - Docker 镜像
# Glama 部署用：启动 server 并响应 MCP introspection 检查
# 注意：代码基于 mcp 2.0.0 API（MCPServer），必须锁定版本，否则新版 mcp 不兼容
FROM python:3.11-slim

WORKDIR /app

# OpenCV 运行时库 + mediapipe 依赖的 glib
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖（锁定 mcp==2.0.0 与本地开发环境一致）
COPY pyproject.toml README.md ./
COPY camera_mcp/ ./camera_mcp/
RUN pip install --no-cache-dir "mcp==2.0.0" \
    && pip install --no-cache-dir .

# MCP server 默认走 stdio（Glama 检查用）
ENTRYPOINT ["python", "-m", "camera_mcp.server"]
CMD []
