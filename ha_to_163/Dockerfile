# 使用外部传入的基础镜像（支持构建参数）
ARG BUILD_FROM=alpine:3.18
FROM ${BUILD_FROM}

# 设置非交互式安装，避免提示
ENV DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /app

# 复制 requirements.txt（先单独复制，利用 Docker 缓存）
COPY requirements.txt .

# 安装 Python、编译工具和 pip（Alpine 使用 apk）
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    python3-dev \
    musl-dev \
    && \
    # 清理缓存，减小镜像体积
    rm -rf /var/cache/apk/*

# 使用国内镜像源加速 pip 安装，同时保留官方源作为备选
# 优先使用清华源，失败则回退到 PyPI 官方
RUN pip3 install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --extra-index-url https://pypi.org/simple \
    --upgrade pip \
    && \
    pip3 install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --extra-index-url https://pypi.org/simple \
    paho-mqtt>=1.6.1 \
    requests>=2.31.0 \
    pyyaml>=6.0.1 \
    ntplib>=0.3.0

# 验证关键依赖是否安装成功（可选，调试用）
RUN pip3 list | grep -E "(paho-mqtt|requests|pyyaml|ntplib)"

# 复制项目所有文件（放在最后，避免代码变更导致依赖重装）
COPY . .

# 确保 main.py 可执行（如果需要）
RUN chmod +x /app/main.py

# 启动命令：运行主程序
CMD ["python3", "/app/main.py"]
