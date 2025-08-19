# 使用 Alpine 作为基础镜像（支持多架构）
ARG BUILD_FROM=alpine:3.18
FROM ${BUILD_FROM}

# 设置环境变量，避免交互式提示
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_EXTRA_INDEX_URL=https://pypi.org/simple

# 设置工作目录
WORKDIR /app

# 安装 Python 和必要编译工具
# 注意：Alpine 3.18 中 pip 包名为 py3-pip
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    python3-dev \
    musl-dev \
    && \
    # 验证 pip 安装成功
    pip3 --version \
    && \
    # 升级 pip（使用国内源）
    pip3 install --upgrade pip \
    && \
    # 安装 Python 依赖（优先使用清华源）
    pip3 install --no-cache-dir \
        paho-mqtt>=1.6.1 \
        requests>=2.31.0 \
        pyyaml>=6.0.1 \
        ntplib>=0.3.0

# 验证依赖安装
RUN pip3 list | grep -E "(paho-mqtt|requests|pyyaml|ntplib)"

# 复制应用文件
COPY . .

# 确保主程序可执行
RUN chmod +x /app/main.py || true

# 启动命令
CMD ["python3", "/app/main.py"]
