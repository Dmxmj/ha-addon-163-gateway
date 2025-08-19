# 使用 Alpine 镜像（支持多架构）
ARG BUILD_FROM=alpine:3.18
FROM ${BUILD_FROM}

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 设置工作目录
WORKDIR /app

# 安装 Python 和编译依赖
# 注意：alpine:3.18 中 py3-pip 是正确的
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    python3-dev \
    musl-dev

# 设置 pip 使用阿里云镜像（更稳定）
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_EXTRA_INDEX_URL=https://pypi.org/simple
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com

# 使用 python -m pip 替代 pip3（更可靠）
# 先测试 pip 是否可用
RUN python3 -m pip --version

# 安装依赖（不升级 pip，避免网络问题）
RUN python3 -m pip install --no-cache-dir \
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
