# 基础镜像：使用Home Assistant官方多架构基础镜像（正确名称）
# 设置有效默认值，避免"invalid base image"警告
ARG BUILD_FROM=homeassistant/container-base:latest
FROM ${BUILD_FROM}

# 架构变量（适配多架构构建，无需修改）
ARG TARGETARCH
ARG TARGETVARIANT

# 设置工作目录
WORKDIR /app

# 安装系统依赖（Alpine系统通用，无需修改）
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-setuptools \
    py3-wheel \
    --virtual .build-deps \
    gcc \
    python3-dev \
    musl-dev \
    linux-headers

# 复制依赖清单并安装（国内源加速）
COPY requirements.txt .
RUN pip3 install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制插件所有文件
COPY . .

# 给启动脚本添加可执行权限
RUN chmod +x /app/run.sh

# 清理构建依赖（减小镜像体积）
RUN apk del .build-deps

# 开启Python无缓冲输出（日志实时刷新）
ENV PYTHONUNBUFFERED=1

# 启动命令
CMD ["/app/run.sh"]
