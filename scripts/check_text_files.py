"""检查待提交文本及既有索引，不改未涉及文件；两个历史 CRLF 索引留待独立规范化。"""

import subprocess
from pathlib import Path

LEGACY_CRLF = {"app/services/knowledge_scope.py", "app/data/knowledge_scope.json"}


def main() -> None:
    entries = subprocess.check_output(["git", "ls-files", "--eol", "-z"]).decode("utf-8").split("\0")
    indexed = {name: info.split()[0] for entry in filter(None, entries) for info, name in [entry.split("\t", 1)]}
    changed = set(subprocess.check_output(["git", "diff", "--name-only", "HEAD", "-z"]).decode("utf-8").split("\0"))
    added = set(subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"]).decode("utf-8").split("\0"))
    paths = (set(indexed) | added) - {""}
    errors = []
    for name in sorted(paths):
        path = Path(name)
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        # 未修改文件检查 Git 索引，兼容旧 Windows 检出的 CRLF，避免夹带全仓格式化。
        bad_eol = b"\r\n" in data if name in changed | added else indexed[name] in {"i/crlf", "i/mixed"}
        if name not in LEGACY_CRLF and path.suffix not in {".ps1", ".cmd", ".bat"} and bad_eol:
            errors.append(name + ": expected LF")
        if any(line.startswith(("<<<<<<< ", ">>>>>>> ")) for line in text.splitlines()):
            errors.append(name + ": unresolved conflict")
    if errors:
        raise SystemExit("\n".join(errors))
    print("Text checks passed")


if __name__ == "__main__":
    main()
