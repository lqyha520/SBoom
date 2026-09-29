"""将审查点名的备份移出仓库：DPAPI封装密钥、AES-GCM分块加密、解密验哈希后才删除源。"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import hmac
import json
import os
import secrets
import struct
import subprocess
import time
from ctypes import wintypes
from pathlib import Path
from typing import BinaryIO

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b"LCARCH1\n"
CHUNK = 1024 * 1024


def sources(root: Path) -> list[Path]:
    root = root.resolve(strict=True)
    selected = [root / "artifacts/deploy/image-publication-20260920-113100" / name
                for name in ("database.dump", "appdata.tar.gz")]
    selected.extend((root / ".review/backups").glob("*.dump"))
    backup_root = root / "data/backups"
    if backup_root.exists():
        for directory, directories, files in os.walk(backup_root, followlinks=False):
            directories[:] = [name for name in directories if not (Path(directory) / name).is_symlink()]
            selected.extend(Path(directory) / name for name in files)
    result = []
    for path in selected:
        if not path.exists():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError("备份清单包含符号链接、外部路径或非文件")
        if any(parent.is_symlink() for parent in path.parents if parent != root and parent.is_relative_to(root)):
            raise ValueError("备份父目录包含符号链接")
        result.append(path)
    return sorted(set(result))


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def dpapi(data: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("当前平台不支持Windows当前用户DPAPI；未迁移任何源文件")
    windows_library = getattr(ctypes, "WinDLL", None)
    if windows_library is None:
        raise RuntimeError("当前Python不支持Windows动态库；未迁移任何源文件")
    crypt32 = windows_library("crypt32", use_last_error=True)
    kernel32 = windows_library("kernel32", use_last_error=True)
    buffer = ctypes.create_string_buffer(data)
    source = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = DataBlob()
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.restype = wintypes.BOOL
    operation.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError("DPAPI操作失败")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        # 只输出SID给进程内处理，不把账号或密钥写入清单。
        import csv
        account = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], check=True, capture_output=True, text=True)
        sid = next(csv.reader(account.stdout.splitlines()))[1]
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
                       check=True, capture_output=True, creationflags=0x08000000)
    else:
        path.chmod(0o700)


def load_key(path: Path, *, create: bool = False) -> bytes:
    if path.exists():
        key = dpapi(path.read_bytes(), decrypt=True)
        if len(key) != 32:
            raise ValueError("受保护密钥长度无效")
        return key
    if not create:
        raise FileNotFoundError("当前用户的DPAPI密钥文件不存在")
    key = secrets.token_bytes(32)
    protected = dpapi(key)
    # 先验证保护/解保护，再持久保存；密钥不进入命令行或日志。
    if dpapi(protected, decrypt=True) != key:
        raise ValueError("DPAPI密钥自检失败")
    private_directory(path.parent)
    with path.open("xb") as output:
        output.write(protected)
        output.flush()
        os.fsync(output.fileno())
    return key


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def encrypt_file(source: Path, target: Path, relative: str, key: bytes) -> str:
    size = source.stat().st_size
    salt = secrets.token_bytes(32)
    header = json.dumps({"source": relative, "size": size, "salt": base64.b64encode(salt).decode()},
                        ensure_ascii=False, separators=(",", ":")).encode()
    cipher = AESGCM(hmac.digest(key, salt, "sha256"))
    digest = hashlib.sha256()
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        outgoing.write(MAGIC + struct.pack(">I", len(header)) + header)
        index = 0
        for block in iter(lambda: incoming.read(CHUNK), b""):
            digest.update(block)
            encoded = cipher.encrypt(index.to_bytes(12, "big"), block, header)
            outgoing.write(struct.pack(">I", len(encoded)) + encoded)
            index += 1
        # 独立认证终止块，拒绝截断和拼接。
        end = cipher.encrypt(index.to_bytes(12, "big"), b"", header)
        outgoing.write(struct.pack(">I", len(end)) + end)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    return digest.hexdigest()


def exact(source: BinaryIO, size: int) -> bytes:
    value = source.read(size)
    if len(value) != size:
        raise ValueError("密文被截断")
    return value


def decrypt_file(source: Path, key: bytes, *, expected_source: str, output: BinaryIO | None = None) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as incoming:
        if exact(incoming, len(MAGIC)) != MAGIC:
            raise ValueError("备份格式不匹配")
        header_size = struct.unpack(">I", exact(incoming, 4))[0]
        if not 0 < header_size < 65536:
            raise ValueError("密文头长度无效")
        header = exact(incoming, header_size)
        metadata = json.loads(header)
        size = metadata["size"]
        if metadata["source"] != expected_source or not isinstance(size, int) or size < 0:
            raise ValueError("密文源路径或大小不匹配")
        salt = base64.b64decode(metadata["salt"], validate=True)
        if len(salt) != 32:
            raise ValueError("密文盐长度无效")
        cipher = AESGCM(hmac.digest(key, salt, "sha256"))
        index = 0
        remaining = size
        while remaining:
            expected = min(CHUNK, remaining)
            length = struct.unpack(">I", exact(incoming, 4))[0]
            if length != expected + 16:
                raise ValueError("密文分块长度无效")
            plain = cipher.decrypt(index.to_bytes(12, "big"), exact(incoming, length), header)
            digest.update(plain)
            if output is not None:
                output.write(plain)
            remaining -= len(plain)
            index += 1
        if struct.unpack(">I", exact(incoming, 4))[0] != 16:
            raise ValueError("密文终止块无效")
        if cipher.decrypt(index.to_bytes(12, "big"), exact(incoming, 16), header) != b"" or incoming.read(1):
            raise ValueError("密文包含多余内容")
    return digest.hexdigest()


def migrate(root: Path, target: Path, key: bytes) -> Path:
    root, target = root.resolve(strict=True), target.resolve(strict=True)
    if target.is_relative_to(root):
        raise ValueError("加密目标必须在仓库外")
    selected = sources(root)
    manifest = target / "manifest.json"
    if manifest.exists():
        raise ValueError("清单已存在，拒绝覆盖")
    records: list[dict[str, str]] = []
    # 全部加密验证完成前，不移除任何源文件。
    for source in selected:
        relative = source.relative_to(root).as_posix()
        before = source.stat()
        encrypted = target / f"{len(records):05d}.lcenc"
        digest = encrypt_file(source, encrypted, relative, key)
        if decrypt_file(encrypted, key, expected_source=relative) != digest:
            raise ValueError("完整解密哈希验证失败，源文件保留")
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("备份源在加密期间变化，源文件保留")
        records.append({"source": relative, "encrypted": str(encrypted), "sha256": digest})
    with manifest.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(records, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    for record in records:
        source = root / record["source"]
        # 删前再重读源文件和密文；密钥必须能够重新解保护后才进入migrate。
        if not source.resolve().is_relative_to(root) or source.is_symlink() or digest_file(source) != record["sha256"]:
            raise ValueError("源备份已变化，停止移除")
        if decrypt_file(Path(record["encrypted"]), key, expected_source=record["source"]) != record["sha256"]:
            raise ValueError("移除前密文复验失败")
        source.unlink()
    return manifest


def restore(manifest: Path, destination: Path, key: bytes) -> int:
    destination = destination.resolve()
    if destination == ROOT or destination.is_relative_to(ROOT):
        raise ValueError("恢复目标必须在仓库外，避免覆盖业务数据")
    private_directory(destination)
    records = json.loads(manifest.read_text(encoding="utf-8"))
    count = 0
    for record in records:
        target = destination / record["source"]
        if not target.resolve().is_relative_to(destination) or target.exists() or target.is_symlink():
            raise ValueError("恢复路径越界或目标已存在")
        encrypted = Path(record["encrypted"]).resolve(strict=True)
        if not encrypted.is_relative_to(manifest.resolve().parent):
            raise ValueError("密文路径不在清单目录内")
        # 先认证完整文件，然后才输出；临时文件也放在受限目录。
        if decrypt_file(encrypted, key, expected_source=record["source"]) != record["sha256"]:
            raise ValueError("恢复前完整性检查失败")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + "." + secrets.token_hex(8) + ".partial")
        try:
            with temporary.open("xb") as output:
                digest = decrypt_file(encrypted, key, expected_source=record["source"], output=output)
                output.flush()
                os.fsync(output.fileno())
            if digest != record["sha256"] or digest_file(temporary) != record["sha256"]:
                raise ValueError("恢复输出哈希不匹配")
            if target.exists():
                raise ValueError("恢复期间目标出现，拒绝覆盖")
            temporary.rename(target)
        finally:
            temporary.unlink(missing_ok=True)
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", type=Path, help="已有manifest.json")
    parser.add_argument("--restore-dir", type=Path, help="仓库外全新恢复目录；不覆盖已有文件")
    args = parser.parse_args()
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "LearnCoach"
    key_path = base / "keys" / "archive-key.dpapi"
    if args.restore:
        if not args.restore_dir or args.apply:
            parser.error("恢复需要--restore-dir，不能同时--apply")
        count = restore(args.restore, args.restore_dir, load_key(key_path))
        print(json.dumps({"restored": count, "destination": str(args.restore_dir)}, ensure_ascii=False))
        return 0
    selected = sources(ROOT)
    if not args.apply:
        print(json.dumps({"dry_run": True, "files": [{"source": str(path.relative_to(ROOT)), "bytes": path.stat().st_size}
                                                       for path in selected]}, ensure_ascii=False))
        return 0
    if os.name != "nt" or not os.environ.get("LOCALAPPDATA"):
        raise RuntimeError("需要Windows当前用户DPAPI和LOCALAPPDATA")
    key = load_key(key_path, create=True)
    # 磁盘中的密钥必须可恢复，而不仅仅是当前进程持有明文。
    if load_key(key_path) != key:
        raise ValueError("持久密钥回读验证失败")
    target = base / "secure-archives" / (time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4))
    private_directory(target)
    manifest = migrate(ROOT, target, key)
    print(json.dumps({"migrated": len(selected), "manifest": str(manifest)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
