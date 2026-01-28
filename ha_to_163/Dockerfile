FROM alpine:3.18

# 安装Python、构建依赖及SSL证书
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    python3-dev \
    musl-dev \
    ca-certificates \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip3 install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --extra-index-url https://pypi.org/simple \
    -r requirements.txt

COPY . .

CMD ["python3", "/app/main.py"]
