# 使用 Alpine 镜像
ARG BUILD_FROM=alpine:3.18
FROM ${BUILD_FROM}

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 设置工作目录
WORKDIR /app

# 安装必要工具
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    python3-dev \
    musl-dev \
    ca-certificates \
    openssl \
    curl \
    bind-tools  # 提供 dig 命令

# 更新 CA 证书
RUN update-ca-certificates --fresh

# 诊断 1: 测试 DNS 是否正常
RUN echo "=== Testing DNS ===" && \
    nslookup mirrors.aliyun.com

# 诊断 2: 测试网络连通性
RUN echo "=== Testing HTTP Access ===" && \
    curl -I -s --connect-timeout 10 https://mirrors.aliyun.com/pypi/simple/paho-mqtt/ || \
    echo "Warning: HTTPS failed, trying HTTP" && \
    curl -I -s http://mirrors.aliyun.com/pypi/simple/paho-mqtt/

# 安装依赖：使用 HTTP + trusted-host（绕过 HTTPS 问题）
RUN python3 -m pip install --no-cache-dir \
    --index-url http://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --extra-index-url http://pypi.org/simple/ \
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
