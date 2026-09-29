# 参与开发

工作约定、目录说明、各组件的检查命令和测试数据库红线都在 [CLAUDE.md](CLAUDE.md)，请先读它。

## 分支与PR

从目标分支创建 `codex/主题`，在PR中描述问题、最终行为、验证结果与上线限制。必需CI检查通过后合并。仓库管理员应启用分支保护，禁止直接推送和绕过检查；本地配置不能代替服务器设置。

开发环境使用Python3.12、Node22和pnpm10.14.0，按哈希锁文件安装。可选安装pre-commit后执行 `pre-commit install`，提交时检查ruff、行尾、大文件与私钥。

## 提交前
1. 跑改动涉及组件的检查（后端：`ruff check` / `mypy` / `python scripts/dev.py test`；前端：`typecheck` / `lint` / `test` / `build`）。
2. `git diff --check` 确认没有多余空白；不要提交 `.env*`、`data/`、日志、前端 `dist/` 和仓库根的一次性脚本。
3. 提交信息用中文，说明动机而不只是改了什么。

## 换行规范化（待办，单独一次提交）
`.gitattributes` 已声明 `* text=auto eol=lf`，但仓库里仍有历史 CRLF / 混合换行的文件。
新建或实际修改的文本使用LF（Windows脚本依.gitattributes例外）。为避免无关diff混进功能改动，不要在工作区有未提交功能修改时执行全仓规范化。
等当前一批功能改动合入 `main` 后，另开一个只做规范化的提交：

```bash
git add --renormalize .
git commit -m "chore: 按 .gitattributes 统一换行为 LF"
```

规范化提交只应包含换行变化（`git diff --cached --ignore-all-space --stat` 应为空）。
