# syntax=docker/dockerfile:1.7
# learn-coach 生产镜像
# 构建：docker build -t learncoach .
# 运行：见 deploy/docker-compose.yml
# 需要 BuildKit（Docker 23+ / docker compose v2 默认启用）：RUN --mount=type=cache
# 只在构建期挂载 pip / pnpm 的下载缓存，不进镜像层；锁文件不变时二次构建几乎不再下载。

# ─── 阶段一：构建两个前端（web 用户端 + admin 后台） ───
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS frontend
WORKDIR /src
# pnpm 版本与 CI（.github/workflows/ci.yml 的 pnpm/action-setup）保持一致；corepack 随 Node 22 自带。
# npm_config_store_dir 把 pnpm 内容寻址仓库固定到 /pnpm/store，供下面的缓存卷复用。
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    npm_config_store_dir=/pnpm/store
ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org
RUN corepack enable && corepack prepare pnpm@10.14.0 --activate

# 先只拷贝清单，利用层缓存装依赖
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./web/
COPY admin/package.json admin/pnpm-lock.yaml admin/pnpm-workspace.yaml ./admin/
# 两个前端构建都会 import 仓库根的 ../ui/config.mts 与 shared/mini-profile
# store 在缓存卷、node_modules 在镜像层，跨文件系统时 pnpm 会退化为复制（有提示，属正常）
RUN --mount=type=cache,id=learncoach-pnpm-store,target=/pnpm/store \
    cd web && pnpm install --frozen-lockfile \
 && cd ../admin && pnpm install --frozen-lockfile

COPY ui ./ui
COPY shared ./shared

COPY web ./web
COPY admin ./admin
RUN cd web && pnpm build \
 && cd ../admin && pnpm build

# ─── 阶段二：Python 运行时 ───
FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    TZ=Asia/Shanghai

COPY requirements.lock ./
# 构建期可换 pip 源，默认仍是官方 PyPI（CI、本地构建行为完全不变）。
# 国内服务器重建时用 --build-arg PIP_INDEX_URL=<镜像源> 提速：实测该机到
# files.pythonhosted.org 只有 ~14 kB/s，整层依赖要爬 30-40 分钟；换成国内镜像
# 可到 ~1 MB/s，一两分钟装完。
# pip 下载缓存放 BuildKit 缓存卷（/root/.cache/pip），镜像层里不残留 wheel。
# requirements.txt 只含运行时依赖；mypy / pip-audit / pytest 在 requirements-dev.txt，不进镜像。
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN --mount=type=cache,id=learncoach-pip-cache,target=/root/.cache/pip \
    pip install --require-hashes --index-url="${PIP_INDEX_URL}" -r requirements.lock \
 && python -m pip uninstall -y pip

# 非 root 运行：固定 uid/gid 10001。/app/data 是 compose 里 appdata 卷的挂载点，
# 运行期写入（secret_key.txt、paper-files、微信支付密钥）全部落在这里，须归该用户所有。
# 代码目录保持 root 只读；用 compileall 预生成 .pyc，避免运行用户无权写字节码拖慢启动。
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /app/data && chown app:app /app/data

COPY app ./app
COPY run.py .
COPY --from=frontend /src/web/dist ./web/dist
COPY --from=frontend /src/admin/dist ./admin/dist
RUN python -m compileall -q app run.py \
 && test -s web/dist/index.html && test -s admin/dist/index.html \
 && test -n "$(find web/dist/assets -type f -name '*.js' -print -quit)" \
 && test -n "$(find admin/dist/assets -type f -name '*.js' -print -quit)"

# 运行期数据（本地试卷文件 / secret_key）全部落这个卷。
# 注意：已存在的旧 appdata 卷是 root 所有，切到本镜像前需一次性 chown，见 docs/deploy.md。
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/readyz',timeout=3)"

USER app
CMD ["python", "run.py"]

# 运维镜像与应用共享 Python 依赖；PG 客户端来自 PostgreSQL 16 镜像。
FROM postgres:16-bookworm@sha256:0ea6700a3b4f0ae6ce746519073558aed4d88a79d8d07622a9a644946c7319c4 AS pgtools
FROM runtime AS ops
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 liblz4-1 libzstd1 restic && rm -rf /var/lib/apt/lists/*
COPY --from=pgtools /usr/lib/postgresql/16/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=pgtools /usr/lib/postgresql/16/bin/pg_restore /usr/local/bin/pg_restore
COPY scripts ./scripts
HEALTHCHECK NONE
USER app
ENTRYPOINT ["python", "scripts/ops_backup.py"]
CMD ["backup"]

# 默认构建仍是应用镜像；运维镜像必须显式指定 --target ops。
FROM runtime AS application
