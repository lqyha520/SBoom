# learn-coach 生产镜像
# 构建：docker build -t learncoach .
# 运行：见 deploy/docker-compose.yml

# ─── 阶段一：构建两个前端（web 用户端 + admin 后台） ───
FROM node:22-alpine AS frontend
WORKDIR /src
RUN npm install -g pnpm@10

# 先只拷贝清单，利用层缓存装依赖
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./web/
COPY admin/package.json admin/pnpm-lock.yaml admin/pnpm-workspace.yaml ./admin/
# 两个前端构建都会 import 仓库根的 ../ui/config.mts 与 shared/mini-profile
COPY ui ./ui
COPY shared ./shared
RUN cd web && pnpm install --frozen-lockfile \
 && cd ../admin && pnpm install --frozen-lockfile

COPY web ./web
COPY admin ./admin
RUN cd web && pnpm build \
 && cd ../admin && pnpm build

# ─── 阶段二：Python 运行时 ───
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000

COPY requirements.txt ./
# 构建期可换 pip 源，默认仍是官方 PyPI（CI、本地构建行为完全不变）。
# 国内服务器重建时用 --build-arg PIP_INDEX_URL=<镜像源> 提速：实测该机到
# files.pythonhosted.org 只有 ~14 kB/s，整层依赖要爬 30-40 分钟；换成国内镜像
# 可到 ~1 MB/s，一两分钟装完。
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --index-url="${PIP_INDEX_URL}" -r requirements.txt

COPY app ./app
COPY run.py .
COPY --from=frontend /src/web/dist ./web/dist
COPY --from=frontend /src/admin/dist ./admin/dist

# 运行期数据（本地试卷文件 / secret_key）全部落这个卷
VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health/detail',timeout=3)"

CMD ["python", "run.py"]
