# 使用 Alpine 镜像
FROM alpine:3.18

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 设置工作目录
WORKDIR /app

# 安装 Python 和依赖
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    python3-dev \
    musl-dev \
    ca-certificates \
    curl

# 使用阿里云源安装 Python 包
RUN python3 -m pip install --no-cache-dir \
    --index-url http://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
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
