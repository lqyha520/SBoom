# 参与开发

工作约定、目录说明、各组件的检查命令和测试数据库红线都在 [CLAUDE.md](CLAUDE.md)，请先读它。

## 提交前
1. 跑改动涉及组件的检查（后端：`ruff check` / `mypy` / `python -m pytest -n auto`；前端：`typecheck` / `test` / `build`）。
2. `git diff --check` 确认没有多余空白；不要提交 `.env*`、`data/`、日志、前端 `dist/` 和仓库根的一次性脚本。
3. 提交信息用中文，说明动机而不只是改了什么。

## 换行规范化（待办，单独一次提交）
`.gitattributes` 已声明 `* text=auto eol=lf`，但仓库里仍有历史 CRLF / 混合换行的文件。
为避免和正在进行的功能改动混在一起，**不要**在功能分支上执行规范化。
等当前一批功能改动合入 `main` 后，另开一个只做规范化的提交：

```bash
git add --renormalize .
git commit -m "chore: 按 .gitattributes 统一换行为 LF"
```

规范化提交只应包含换行变化（`git diff --cached --ignore-all-space --stat` 应为空）。
