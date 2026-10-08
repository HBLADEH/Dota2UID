"""Standard-library bootstrap for immutable, plugin-private Dota2UID runtime snapshots.

Copied into the generated plugin root. It never imports project libraries, SDKs,
configuration, or pip; project imports and resource probes happen in a child process.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.machinery as machinery
import importlib.metadata as metadata
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
import zlib
from collections.abc import Buffer, Iterator
from contextlib import contextmanager
from email.parser import BytesParser
from http.client import HTTPMessage
from pathlib import Path, PurePosixPath
from types import CodeType
from typing import IO, cast
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

PACKAGES = {
    "dota2forge-core": "dota2forge_core",
    "dota2forge-renderer": "dota2forge_renderer",
    "dota2forge-assets": "dota2forge_assets",
    "dota2uid": "Dota2UID",
}
MAX_WHEEL_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_RUNTIME_BYTES = 128 * 1024 * 1024
MAX_FILES = 10_000
MINIMUM_PYTHON = (3, 12)
DOWNLOAD_TIMEOUT = 10.0
DOWNLOAD_DEADLINE = 60.0
PROBE_TIMEOUT = 30.0
VERSION_PATTERN = r"[0-9][0-9A-Za-z.!+-]{0,63}"
ERROR_TEXT = {
    "invalid_manifest": "发行清单无效，请重新安装插件。",
    "missing_runtime": "缺少随包运行库，主人可发送 do安装核心。",
    "invalid_wheel": "运行包校验失败，请发送 do安装核心 修复。",
    "dependency_incompatible": "宿主 HTTPX/Pillow 或相关依赖不兼容，请停机维护依赖后重启。",
    "runtime_probe_failed": "运行包导入或字体资源验证失败，请重新安装插件。",
    "module_conflict": "进程已加载其他运行库，请完整关闭并重启 GsCore。",
    "permission_denied": "运行库目录无写入权限，请检查插件数据目录权限。",
    "disk_error": "运行库写入失败，请检查可用磁盘空间。",
    "download_failed": "运行包下载失败，请检查网络后重试。",
    "download_timeout": "运行包下载超时，请稍后重试。",
    "cancelled": "运行库准备已取消。",
    "not_prepared": "运行库尚未准备，请发送 do安装核心。",
    "stopped": "插件已关闭，运行库任务已停止。",
}


class BootstrapError(ValueError):
    """Stable, non-sensitive failure code suitable for a management reply."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(ERROR_TEXT.get(code, "运行库准备失败，请重新安装插件。"))


def _normal_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_parts(name: str) -> tuple[str, ...]:
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        raise BootstrapError("invalid_wheel")
    parts = tuple(name.removesuffix("/").split("/"))
    for part in parts:
        if (
            part in {"", ".", ".."}
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", part)
            or part.endswith((".", " "))
            or re.fullmatch(r"(?i)(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?", part)
        ):
            raise BootstrapError("invalid_wheel")
    return parts


def validate_wheel(path: Path, name: str, version: str, sha256: str) -> dict[str, bytes]:
    """Validate a pure project wheel completely, returning files without any writes."""
    if (
        name not in PACKAGES
        or not re.fullmatch(VERSION_PATTERN, version)
        or not re.fullmatch(r"[0-9a-f]{64}", sha256)
        or path.name != f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_WHEEL_BYTES
    ):
        raise BootstrapError("invalid_wheel")
    payload = path.read_bytes()
    if _hash(payload) != sha256:
        raise BootstrapError("invalid_wheel")
    dist_info = f"{name.replace('-', '_')}-{version}.dist-info"
    result: dict[str, bytes] = {}
    seen: dict[str, bool] = {}
    total = 0
    try:
        with ZipFile(io.BytesIO(payload)) as wheel:
            if len(wheel.infolist()) > MAX_FILES:
                raise BootstrapError("invalid_wheel")
            for entry in wheel.infolist():
                parts = _safe_parts(entry.orig_filename)
                key = "/".join(parts).casefold()
                mode = entry.external_attr >> 16
                if (
                    entry.orig_filename != entry.filename
                    or parts[0] not in {PACKAGES[name], dist_info}
                    or key in seen
                    or entry.flag_bits & 1
                    or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
                    or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR})
                    or (stat.S_ISDIR(mode) and not entry.is_dir())
                    or any(
                        seen.get("/".join(parts[:index]).casefold()) is False
                        for index in range(1, len(parts))
                    )
                    or (not entry.is_dir() and any(old.startswith(key + "/") for old in seen))
                ):
                    raise BootstrapError("invalid_wheel")
                seen[key] = entry.is_dir()
                if entry.is_dir():
                    continue
                suffix = PurePosixPath(entry.filename).suffix.lower()
                if (
                    suffix
                    in {
                        ".dll",
                        ".pyd",
                        ".so",
                        ".dylib",
                        ".exe",
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".webp",
                        ".gif",
                        ".db",
                        ".sqlite",
                        ".sqlite3",
                        ".pyc",
                    }
                    or parts[-1].lower() in {".env", "config.toml", "config.json"}
                    or re.search(r"(?i)\.(?:so|dylib|dll|pyd)(?:\.|$)", parts[-1])
                    or entry.file_size > MAX_WHEEL_BYTES
                ):
                    raise BootstrapError("invalid_wheel")
                total += entry.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise BootstrapError("invalid_wheel")
                data = wheel.read(entry)
                if len(data) != entry.file_size:
                    raise BootstrapError("invalid_wheel")
                result[entry.filename] = data
    except (BadZipFile, KeyError, RuntimeError, UnicodeError, zlib.error) as exc:
        raise BootstrapError("invalid_wheel") from exc
    try:
        info = BytesParser().parsebytes(result[f"{dist_info}/METADATA"])
        tags = BytesParser().parsebytes(result[f"{dist_info}/WHEEL"])
        if (
            info.get_all("Name") != [name]
            or info.get_all("Version") != [version]
            or info.get_all("Requires-Python") != [">=3.12"]
            or tags.get_all("Tag") != ["py3-none-any"]
            or tags.get("Root-Is-Purelib", "").lower() != "true"
            or tags.get("Wheel-Version") != "1.0"
            or f"{PACKAGES[name]}/__init__.py" not in result
            or f"{dist_info}/RECORD" not in result
            or not any(key.startswith(f"{dist_info}/licenses/") for key in result)
        ):
            raise BootstrapError("invalid_wheel")
    except KeyError as exc:
        raise BootstrapError("invalid_wheel") from exc
    return result


def _json_dict(path: Path, code: str = "invalid_manifest") -> dict[str, object]:
    try:
        if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
            raise BootstrapError(code)
        value: object = json.loads(path.read_text("utf-8"))
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise BootstrapError(code)
        return cast(dict[str, object], value)
    except (OSError, ValueError, UnicodeError) as exc:
        raise BootstrapError(code) from exc


def _manifest(root: Path) -> tuple[dict[str, str], dict[str, dict[str, str]], str, str]:
    release = _json_dict(root / "release.json")
    manifest = _json_dict(root / "runtime-wheels.json")
    deployment = _json_dict(root / "deployment.json")
    digest = _hash((root / "runtime-wheels.json").read_bytes())
    if (
        type(release.get("schema_version")) is not int
        or release.get("schema_version") != 1
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
        or type(deployment.get("schema_version")) is not int
        or deployment.get("schema_version") != 1
        or deployment.get("mode") != "bundled"
        or deployment.get("manifest_sha256") != digest
        or release.get("plugin") != "Dota2UID"
        or not isinstance(release.get("versions"), dict)
        or not isinstance(manifest.get("wheels"), dict)
    ):
        raise BootstrapError("invalid_manifest")
    raw_versions = cast(dict[str, object], release["versions"])
    raw_wheels = cast(dict[str, object], manifest["wheels"])
    if set(raw_versions) != set(PACKAGES) or set(raw_wheels) != set(PACKAGES):
        raise BootstrapError("invalid_manifest")
    versions: dict[str, str] = {}
    wheels: dict[str, dict[str, str]] = {}
    for name in PACKAGES:
        version = raw_versions[name]
        entry = raw_wheels[name]
        if (
            not isinstance(version, str)
            or not re.fullmatch(VERSION_PATTERN, version)
            or not isinstance(entry, dict)
        ):
            raise BootstrapError("invalid_manifest")
        filename = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
        sha256 = entry.get("sha256")
        if (
            entry.get("filename") != filename
            or not isinstance(sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", sha256)
        ):
            raise BootstrapError("invalid_manifest")
        versions[name] = version
        wheels[name] = {"filename": filename, "sha256": sha256}
    repo = manifest.get("repository")
    tag = "v" + versions["dota2uid"]
    if (
        not isinstance(repo, str)
        or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_-]+/Dota2UID", repo)
        or manifest.get("release_tag") != tag
    ):
        raise BootstrapError("invalid_manifest")
    return versions, wheels, f"{repo}/releases/download/{tag}/", digest


def _version(value: str) -> tuple[int, tuple[int, ...], int, int, int]:
    match = re.fullmatch(
        r"(?:(\d+)!)?(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?(?:\.post(\d+))?(?:\+[A-Za-z0-9.]+)?",
        value,
        re.IGNORECASE,
    )
    if match is None:
        raise BootstrapError("dependency_incompatible")
    release = tuple(int(part) for part in match[2].split("."))
    release += (0,) * max(0, 8 - len(release))
    return (
        int(match[1] or 0),
        release,
        {"a": 0, "b": 1, "rc": 2, None: 3}[match[3]],
        int(match[4] or 0),
        int(match[5] or 0),
    )


def _satisfies(version: str, specification: str) -> bool:
    current = _version(version)
    for clause in specification.strip().strip("()").split(","):
        if not clause.strip():
            continue
        match = re.fullmatch(r"\s*(===|~=|==|!=|>=|<=|>|<)\s*([0-9][0-9A-Za-z.!+*-]*)\s*", clause)
        if match is None:
            raise BootstrapError("dependency_incompatible")
        operator, target = match.groups()
        if operator == "===":
            valid = version == target
        elif target.endswith(".*") and operator in {"==", "!="}:
            prefix = tuple(int(part) for part in target[:-2].split("."))
            valid = current[1][: len(prefix)] == prefix
            if operator == "!=":
                valid = not valid
        elif operator == "~=":
            wanted = _version(target)
            count = len(target.split(".")) - 1
            valid = current >= wanted and current[1][:count] == wanted[1][:count]
        else:
            wanted = _version(target)
            valid = {
                "==": current == wanted,
                "!=": current != wanted,
                ">=": current >= wanted,
                "<=": current <= wanted,
                ">": current > wanted,
                "<": current < wanted,
            }.get(operator, False)
        if not valid:
            return False
    return True


def _marker(expression: str, extra: str = "") -> bool:
    values = {
        "extra": extra,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "python_full_version": platform.python_version(),
        "sys_platform": sys.platform,
        "os_name": os.name,
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "platform_python_implementation": platform.python_implementation(),
        "implementation_name": sys.implementation.name,
        "implementation_version": platform.python_version(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
    }

    def operand(node: ast.expr) -> str:
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        raise BootstrapError("dependency_incompatible")

    def evaluate(node: ast.expr) -> bool:
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            results = [evaluate(child) for child in node.values]
            return all(results) if isinstance(node.op, ast.And) else any(results)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = operand(node.left), operand(node.comparators[0])
            operator = node.ops[0]
            if isinstance(operator, (ast.In, ast.NotIn)):
                return (left in right) if isinstance(operator, ast.In) else (left not in right)
            symbol = {
                ast.Eq: "==",
                ast.NotEq: "!=",
                ast.Lt: "<",
                ast.LtE: "<=",
                ast.Gt: ">",
                ast.GtE: ">=",
            }.get(type(operator))
            if symbol is None:
                raise BootstrapError("dependency_incompatible")
            if re.fullmatch(r"\d+(?:\.\d+)*", left) and re.fullmatch(r"\d+(?:\.\d+)*", right):
                return _satisfies(left, symbol + right)
            return {
                "==": left == right,
                "!=": left != right,
                "<": left < right,
                "<=": left <= right,
                ">": left > right,
                ">=": left >= right,
            }[symbol]
        raise BootstrapError("dependency_incompatible")

    try:
        return evaluate(ast.parse(expression.strip(), mode="eval").body)
    except SyntaxError as exc:
        raise BootstrapError("dependency_incompatible") from exc


def _requirement(value: str, extras: tuple[str, ...] = ("",)) -> tuple[str, str] | None:
    dependency, separator, expression = value.partition(";")
    if separator and not any(_marker(expression, extra) for extra in extras):
        return None
    match = re.fullmatch(r"\s*([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?\s*([^;]*)", dependency)
    if match is None or "@" in match[2]:
        raise BootstrapError("dependency_incompatible")
    return _normal_name(match[1]), match[2].strip()


def _dependencies(project: dict[str, str], requirements: list[str]) -> None:
    """Check actual host dependencies and their applicable transitive requirements."""
    pending = ["httpx>=0.28.1,<1", "pillow>=11.3,<13", *requirements]
    checked: set[str] = set()
    while pending:
        requirement = _requirement(pending.pop(), ("", "stratz"))
        if requirement is None:
            continue
        name, specification = requirement
        if name in project:
            installed = project[name]
            dist = None
        else:
            try:
                dist = metadata.distribution(name)
                installed = dist.version
            except metadata.PackageNotFoundError as exc:
                raise BootstrapError("dependency_incompatible") from exc
        if not _satisfies(installed, specification):
            raise BootstrapError("dependency_incompatible")
        if name in checked or dist is None:
            continue
        checked.add(name)
        root = "PIL" if name == "pillow" else name.replace("-", "_")
        loaded = sys.modules.get(root)
        if loaded is not None:
            origin = getattr(loaded, "__file__", None)
            loaded_version = getattr(loaded, "__version__", installed)
            if (
                not isinstance(origin, str)
                or not Path(origin)
                .resolve()
                .is_relative_to(Path(str(dist.locate_file(""))).resolve())
                or not isinstance(loaded_version, str)
                or _version(loaded_version) != _version(installed)
            ):
                raise BootstrapError("dependency_incompatible")
        python = dist.metadata.get("Requires-Python", "")
        if python and not _satisfies(platform.python_version(), python):
            raise BootstrapError("dependency_incompatible")
        pending.extend(value for value in dist.requires or () if _requirement(value) is not None)
    # Preserve constraints of installed host packages that consume these shared libraries.
    for dist in metadata.distributions():
        if _normal_name(dist.metadata.get("Name", "")) in PACKAGES:
            continue
        for value in dist.requires or ():
            if not re.match(r"(?i)^\s*(?:httpx|pillow)(?:\s|[<>=!~;\[]|$)", value):
                continue
            requirement = _requirement(value)
            if requirement is not None:
                name, specification = requirement
                if not _satisfies(metadata.version(name), specification):
                    raise BootstrapError("dependency_incompatible")


def _requirements(generation: Path, versions: dict[str, str]) -> list[str]:
    result: list[str] = []
    for name, version in versions.items():
        path = generation / f"{name.replace('-', '_')}-{version}.dist-info/METADATA"
        info = BytesParser().parsebytes(path.read_bytes())
        if (
            info.get_all("Name") != [name]
            or info.get_all("Version") != [version]
            or info.get_all("Requires-Python") != [">=3.12"]
        ):
            raise BootstrapError("invalid_wheel")
        result.extend(info.get_all("Requires-Dist", []))
    return result


def _check_stop(stop: threading.Event) -> None:
    if stop.is_set():
        raise BootstrapError("cancelled")


def _safe_directory(path: Path) -> None:
    """Reject links at every existing ancestor, including Windows junctions."""
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or (hasattr(ancestor, "is_junction") and ancestor.is_junction()):
            raise BootstrapError("permission_denied")


@contextmanager
def _process_lock(path: Path, stop: threading.Event) -> Iterator[None]:
    _safe_directory(path)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        acquired = False
        try:
            while not acquired:
                _check_stop(stop)
                try:
                    if sys.platform == "win32":
                        import msvcrt

                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError:
                    stop.wait(0.05)
            yield
        finally:
            if acquired:
                if sys.platform == "win32":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class _SecureRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage, newurl: str
    ) -> Request | None:
        try:
            parsed = urlsplit(newurl)
            port = parsed.port
        except ValueError as exc:
            raise BootstrapError("download_failed") from exc
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or port not in {None, 443}
            or parsed.hostname
            not in {
                "github.com",
                "release-assets.githubusercontent.com",
                "objects.githubusercontent.com",
            }
        ):
            raise BootstrapError("download_failed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str, destination: Path, stop: threading.Event) -> None:
    """Only called with a validated manifest URL, with bounded socket and total time."""
    deadline = time.monotonic() + DOWNLOAD_DEADLINE
    try:
        with (
            build_opener(_SecureRedirect()).open(url, timeout=DOWNLOAD_TIMEOUT) as response,
            destination.open("xb") as output,
        ):
            total = 0
            while True:
                _check_stop(stop)
                if time.monotonic() > deadline:
                    raise BootstrapError("download_timeout")
                data = response.read(64 * 1024)
                if not data:
                    break
                total += len(data)
                if total > MAX_WHEEL_BYTES:
                    raise BootstrapError("invalid_wheel")
                output.write(data)
    except TimeoutError as exc:
        raise BootstrapError("download_timeout") from exc
    except URLError as exc:
        code = "download_timeout" if isinstance(exc.reason, TimeoutError) else "download_failed"
        raise BootstrapError(code) from exc


PROBE = """import importlib, importlib.metadata as metadata, importlib.resources as resources
import json, pathlib, socket, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
def denied(event, args):
    if event.startswith("socket."):
        raise RuntimeError("network disabled")
sys.addaudithook(denied)
expected = json.loads(sys.argv[2])
packages = json.loads(sys.argv[3])
for name, version in expected.items():
    assert metadata.version(name) == version
for module in packages.values():
    imported = importlib.import_module(module)
    assert pathlib.Path(imported.__file__).resolve().is_relative_to(root)
import httpx, PIL, httpcore, anyio, certifi, idna, h11
from dota2forge_renderer import MenuCard, PillowRenderer
assets = resources.files("dota2forge_renderer").joinpath("assets", "v1")
assert assets.joinpath("OFL.txt").read_bytes()
renderer = PillowRenderer()
try:
    artifact = renderer.render(MenuCard())
    assert artifact.data and artifact.width > 0
finally:
    renderer.close()
"""


def _probe(generation: Path, versions: dict[str, str], stop: threading.Event) -> None:
    environment = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LANG")
        if key in os.environ
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            PROBE,
            str(generation),
            json.dumps(versions),
            json.dumps(PACKAGES),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    deadline = time.monotonic() + PROBE_TIMEOUT
    try:
        while process.poll() is None:
            _check_stop(stop)
            if time.monotonic() > deadline:
                raise BootstrapError("runtime_probe_failed")
            stop.wait(0.05)
        _check_stop(stop)
        if process.returncode != 0:
            raise BootstrapError("runtime_probe_failed")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _complete(generation: Path, digest: str, stop: threading.Event) -> bool:
    try:
        _safe_directory(generation)
        marker = _json_dict(generation / ".complete.json", "invalid_wheel")
        files = marker.get("files")
        if marker.get("manifest_sha256") != digest or not isinstance(files, dict) or not files:
            return False
        present = {
            path.relative_to(generation).as_posix()
            for path in generation.rglob("*")
            if path.is_file()
        }
        if present != set(files) | {".complete.json"}:
            return False
        for filename, sha256 in files.items():
            _check_stop(stop)
            if not isinstance(filename, str) or not isinstance(sha256, str):
                return False
            _safe_parts(filename)
            path = generation.joinpath(*PurePosixPath(filename).parts)
            _safe_directory(path)
            if _hash(path.read_bytes()) != sha256:
                return False
        return True
    except BootstrapError as exc:
        if exc.code == "cancelled":
            raise
        return False
    except OSError:
        return False


class _ImmutableSourceLoader(machinery.SourceFileLoader):
    """Use verified project source exclusively; neither read nor write bytecode caches."""

    def get_code(self, fullname: str) -> CodeType:
        source = self.get_filename(fullname)
        _safe_directory(Path(source))
        return compile(self.get_data(source), source, "exec", dont_inherit=True)

    def set_data(self, path: str, data: Buffer, *, _mode: int = 0o666) -> None:
        pass


class _PrivateSourceHook:
    """A normal FileFinder restricted to one immutable project's directory tree."""

    def __init__(self, generation: Path) -> None:
        self.generation = generation.resolve()
        self._dota2forge_generation = str(self.generation)

    def __call__(self, value: str) -> machinery.FileFinder:
        path = Path(value).absolute()
        if not path.is_relative_to(self.generation) or not path.is_dir():
            raise ImportError
        return machinery.FileFinder(str(path), (_ImmutableSourceLoader, machinery.SOURCE_SUFFIXES))


def _install_source_hook(generation: Path) -> None:
    """Preserve the host's import behavior and cache policy outside the private tree."""
    resolved = generation.resolve()
    private = str(resolved)
    if not any(getattr(hook, "_dota2forge_generation", None) == private for hook in sys.path_hooks):
        sys.path_hooks.insert(0, _PrivateSourceHook(resolved))
    for value in tuple(sys.path_importer_cache):
        if Path(value).absolute().is_relative_to(resolved):
            del sys.path_importer_cache[value]


class BundledRuntime:
    """One cancellable preparation job, plus explicit process-local first activation."""

    def __init__(self, plugin_root: Path, data_root: Path) -> None:
        self.plugin_root = plugin_root.absolute()
        self.data_root = data_root.absolute()
        self.state = "missing_runtime"
        self.error: str | None = None
        self.generation: Path | None = None
        self._versions: dict[str, str] = {}
        self._digest = ""
        self._stop = threading.Event()
        self._task: asyncio.Task[Path | None] | None = None
        self._closed = False

    async def prepare(self, *, allow_download: bool = False) -> Path | None:
        if self._closed:
            self.state, self.error = "stopped", "stopped"
            return None
        if self._task is not None and not self._task.done():
            return None
        self.state, self.error = "preparing", None
        self._stop.clear()
        self._task = asyncio.create_task(asyncio.to_thread(self._prepare_sync, allow_download))
        try:
            return await asyncio.shield(self._task)
        except asyncio.CancelledError:
            self._stop.set()
            await self._wait_worker()
            raise

    async def _wait_worker(self) -> bool:
        """Repeated caller cancellation must not detach the owned I/O thread."""
        cancelled = False
        while self._task is not None and not self._task.done():
            try:
                await asyncio.shield(self._task)
            except asyncio.CancelledError:
                cancelled = True
                self._stop.set()
        return cancelled

    def _prepare_sync(self, allow_download: bool) -> Path | None:
        staging: Path | None = None
        try:
            if sys.version_info < MINIMUM_PYTHON:
                raise BootstrapError("dependency_incompatible")
            _safe_directory(self.plugin_root)
            versions, wheels, url, digest = _manifest(self.plugin_root)
            runtime = self.data_root / "runtime"
            _safe_directory(runtime)
            runtime.mkdir(parents=True, exist_ok=True)
            with _process_lock(runtime / ".prepare.lock", self._stop):
                _check_stop(self._stop)
                base = runtime / digest
                _safe_directory(base)
                base.mkdir(exist_ok=True)
                for abandoned in base.iterdir():
                    if re.fullmatch(r"\.staging-[0-9a-f]{32}", abandoned.name):
                        _safe_directory(abandoned)
                        if abandoned.is_dir():
                            shutil.rmtree(abandoned)
                current: Path | None = None
                try:
                    pointer = _json_dict(runtime / "current.json", "invalid_wheel")
                    identifier = pointer.get("generation")
                    if (
                        pointer.get("manifest_sha256") == digest
                        and isinstance(identifier, str)
                        and re.fullmatch(r"[0-9a-f]{32}", identifier)
                    ):
                        current = base / identifier
                except BootstrapError:
                    pass
                candidates = ([current] if current is not None else []) + sorted(
                    (
                        path
                        for path in base.iterdir()
                        if re.fullmatch(r"[0-9a-f]{32}", path.name) and path != current
                    ),
                    key=lambda path: path.name,
                )
                for candidate in candidates:
                    if _complete(candidate, digest, self._stop):
                        _dependencies(versions, _requirements(candidate, versions))
                        _probe(candidate, versions, self._stop)
                        self._publish(runtime, candidate, versions, digest)
                        return candidate
                staging = base / (".staging-" + uuid.uuid4().hex)
                staging.mkdir()
                downloads = staging / ".downloads"
                entries: dict[str, bytes] = {}
                for name, info in wheels.items():
                    _check_stop(self._stop)
                    local = self.plugin_root / "runtime-wheels" / info["filename"]
                    try:
                        _safe_directory(local)
                        files = validate_wheel(local, name, versions[name], info["sha256"])
                    except (BootstrapError, OSError):
                        if not allow_download:
                            code = "invalid_wheel" if local.exists() else "missing_runtime"
                            raise BootstrapError(code) from None
                        downloads.mkdir(exist_ok=True)
                        downloaded = downloads / info["filename"]
                        _download(url + info["filename"], downloaded, self._stop)
                        files = validate_wheel(downloaded, name, versions[name], info["sha256"])
                    folded = {filename.casefold() for filename in entries}
                    if any(filename.casefold() in folded for filename in files):
                        raise BootstrapError("invalid_wheel")
                    entries.update(files)
                    if sum(len(value) for value in entries.values()) > MAX_RUNTIME_BYTES:
                        raise BootstrapError("invalid_wheel")
                if downloads.exists():
                    shutil.rmtree(downloads)
                for filename, data in entries.items():
                    _check_stop(self._stop)
                    target = staging.joinpath(*PurePosixPath(filename).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as stream:
                        stream.write(data)
                _dependencies(versions, _requirements(staging, versions))
                _probe(staging, versions, self._stop)
                _atomic_json(
                    staging / ".complete.json",
                    {
                        "manifest_sha256": digest,
                        "files": {name: _hash(data) for name, data in entries.items()},
                    },
                )
                _check_stop(self._stop)
                destination = base / uuid.uuid4().hex
                staging.rename(destination)
                staging = None
                self._publish(runtime, destination, versions, digest)
                return destination
        except BootstrapError as exc:
            self.error = exc.code
            self.state = (
                exc.code if exc.code in {"missing_runtime", "dependency_incompatible"} else "failed"
            )
            return None
        except PermissionError:
            self.state, self.error = "failed", "permission_denied"
            return None
        except OSError:
            self.state, self.error = "failed", "disk_error"
            return None
        finally:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)

    def _publish(
        self, runtime: Path, generation: Path, versions: dict[str, str], digest: str
    ) -> None:
        _check_stop(self._stop)
        _atomic_json(
            runtime / "current.json",
            {"schema_version": 1, "manifest_sha256": digest, "generation": generation.name},
        )
        self.generation, self._versions, self._digest = generation, versions, digest
        self.state, self.error = "prepared", None

    def activate(self) -> None:
        if self._closed:
            raise BootstrapError("stopped")
        generation = self.generation
        if generation is None or self.state not in {"prepared", "runtime_available"}:
            raise BootstrapError("not_prepared")
        try:
            if not _complete(generation, self._digest, self._stop):
                raise BootstrapError("invalid_wheel")
            _dependencies(self._versions, _requirements(generation, self._versions))
            for name, module in list(sys.modules.items()):
                if not any(
                    name == root or name.startswith(root + ".") for root in PACKAGES.values()
                ):
                    continue
                origin = getattr(module, "__file__", None)
                if not isinstance(origin, str) or not Path(origin).resolve().is_relative_to(
                    generation.resolve()
                ):
                    raise BootstrapError("module_conflict")
            private = str(generation)
            _install_source_hook(generation)
            if private in sys.path:
                sys.path.remove(private)
            sys.path.insert(0, private)
            self.state, self.error = "runtime_available", None
        except BootstrapError as exc:
            self.state, self.error = "failed", exc.code
            raise

    async def close(self) -> None:
        self._closed = True
        self._stop.set()
        cancelled = await self._wait_worker()
        self.state = "stopped"
        if cancelled:
            raise asyncio.CancelledError

    def status(self) -> dict[str, str | bool]:
        return {
            "state": self.state,
            "error": self.error or "",
            "prepared": self.generation is not None,
            "runtime_available": self.state == "runtime_available",
            "busy": self._task is not None and not self._task.done(),
        }

    def status_text(self) -> str:
        if self.error is not None:
            return ERROR_TEXT.get(self.error, "运行库准备失败，请重新安装插件。")
        return {
            "missing_runtime": ERROR_TEXT["missing_runtime"],
            "preparing": "正在校验和准备运行库，请稍候。",
            "prepared": "运行库已准备，请完整关闭并重启 GsCore 后启用。",
            "runtime_available": "运行库可用。",
            "stopped": ERROR_TEXT["stopped"],
        }.get(self.state, "运行库尚未准备。")
