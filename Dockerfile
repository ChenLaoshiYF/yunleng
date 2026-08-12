# yunleng 摄像头视觉 MCP Server - Docker 镜像
# Glama 部署用：启动 server 并响应 MCP introspection 检查
FROM python:3.11-slim

WORKDIR /app

# OpenCV 运行时库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖（mediapipe 在 linux 有 wheel）
COPY pyproject.toml README.md ./
COPY camera_mcp/ ./camera_mcp/
RUN pip install --no-cache-dir .

# MCP server 默认走 stdio（Glama 检查用）
ENTRYPOINT ["python", "-m", "camera_mcp.server"]
CMD []
