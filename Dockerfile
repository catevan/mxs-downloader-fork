FROM python:3.11-slim

WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

# 安装必要依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 库
RUN pip install --no-cache-dir streamlit requests beautifulsoup4 lxml

# 复制当前目录代码
COPY . .

# 创建 downloads 挂载目录
RUN mkdir -p downloads

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "web_app.py", "--server.port=8501", "--server.address=0.0.0.0"]