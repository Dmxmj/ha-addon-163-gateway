FROM alpine:3.18

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 设置工作目录
WORKDIR /app

# 安装 Python 和构建依赖
RUN apk add --no-cache \
    python3 \
    py3-pip \
    ca-certificates \
    curl \
    gcc \
    python3-dev \
    musl-dev

# 使用阿里云源安装依赖（HTTP + trusted-host）
RUN python3 -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --extra-index-url https://pypi.org/simple \
    paho-mqtt>=1.6.1 \
    requests>=2.31.0 \
    pyyaml>=6.0.1 \
    ntplib>=0.3.0

# 复制代码
COPY . .

# 可执行权限
RUN chmod +x /app/main.py || true

# 启动
CMD ["python3", "/app/main.py"]
