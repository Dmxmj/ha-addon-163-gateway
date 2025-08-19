# 使用 Alpine 镜像
ARG BUILD_FROM=alpine:3.18
FROM ${BUILD_FROM}

# 设置环境变量（确保 pip 使用国内源）
ENV PYTHONUNBUFFERED=1
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_EXTRA_INDEX_URL=https://pypi.org/simple
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# 设置工作目录
WORKDIR /app

# 安装 Python 和编译工具
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    python3-dev \
    musl-dev \
    ca-certificates \
    openssl \
    && \
    # 强制更新 CA 证书（关键！解决 HTTPS 问题）
    update-ca-certificates --fresh

# 验证 pip 可用
RUN python3 -m pip --version

# 手动指定源安装依赖（最可靠方式）
RUN python3 -m pip install --no-cache-dir \
    --index-url https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --extra-index-url https://pypi.org/simple \
    --trusted-host pypi.org \
    paho-mqtt>=1.6.1 \
    requests>=2.31.0 \
    pyyaml>=6.0.1 \
    ntplib>=0.3.0

# 验证安装
RUN python3 -m pip list | grep -E "(paho-mqtt|requests|pyyaml|ntplib)"

# 复制应用文件
COPY . .

# 确保 main.py 可执行
RUN chmod +x /app/main.py || true

# 启动命令
CMD ["python3", "/app/main.py"]
