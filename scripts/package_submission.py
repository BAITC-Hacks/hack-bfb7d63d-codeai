"""Build and verify local allowlisted submission ZIPs; no network or API calls.

Run verify_submission.py first. This script refuses failed or stale acceptance
reports. --wheelhouse adds a separate full Windows x64 / Python 3.14 offline kit.
Only the Python standard library is required; raw case data is never included.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "README.md", "app.py", "requirements.txt", "setup.ps1", "start.ps1", "run.ps1",
    ".env.example", ".gitignore", ".streamlit/config.toml",
)
DIRECTORY_SUFFIXES = {
    "moneymap": {".py", ".html", ".css", ".js", ".json", ".md", ".txt", ".svg"},
    "config": {".json", ".toml", ".yaml", ".yml"},
    "docs": {".md", ".html", ".svg", ".png", ".pdf", ".txt", ".json"},
    "scripts": {".py", ".ps1", ".sh"},
    "tests": {".py"},
}
CSV_FILES = ("nodes_roles.csv", "clusters.csv", "top_nodes.csv")
RESULT_FILES = (*CSV_FILES, "run_report.json", "acceptance_report.json")
RESULT_PREFIX = "results"
OPTIONAL_REPORTS = {
    "output/stage6/offline_ui_report.json": "verification/offline_ui_report.json",
    "output/stage6/verification_report.json": "verification/verification_report.json",
}
FORBIDDEN_PARTS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", "logs", "secrets.toml", "id_rsa", "id_ed25519",
}
FORBIDDEN_SUFFIXES = {
    ".parquet", ".pyc", ".pyo", ".log", ".sqlite", ".sqlite3", ".db",
    ".pem", ".key", ".p12", ".pfx", ".env",
}
MANIFEST_NAME = "MANIFEST.sha256.json"
OFFLINE_README = """# MoneyMap offline kit: Windows x64, Python 3.14

This archive contains the same project and verified results as the submission,
plus every pinned dependency wheel under `wheelhouse/`. It does not include a
Python installer, API keys, or the organizer's raw Parquet data. Install Python
3.14 x64 beforehand. These wheels are not a Linux/macOS or other-Python kit.

Extract the full archive, open PowerShell in its root, and run:

```powershell
py -3.14 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install --no-index --find-links wheelhouse -r requirements.txt
.\\.venv\\Scripts\\python.exe -m streamlit run app.py
```

Open http://127.0.0.1:8501. The first two commands require no package registry;
Python itself must already be installed. Keep real API use disabled for an
offline demonstration. Consult README.md for the complete setup and limitations.

For recomputation, supply the organizer's three raw files in `data/case/`, then:

```powershell
.\\.venv\\Scripts\\python.exe -m moneymap run --data-dir data/case --out output/submission/results
```

Existing result files at that destination are updated. Re-run
`scripts/verify_submission.py` before packaging changed results. The manifest
records each archived file's SHA-256; it is an integrity inventory, not a digital
signature or a statement of vendor authenticity for wheels.
"""


class PackagingError(ValueError):
    """Reject unsafe paths, incomplete input, or stale verification evidence."""


def require(condition, message):
    if not condition:
        raise PackagingError(message)


def is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def local_path(value: Path | str, *, must_exist: bool = True) -> Path:
    """Only project-local, non-symlink paths; retain checks before resolution."""
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = Path(os.path.abspath(candidate))
    require(candidate.is_relative_to(ROOT), "Path must stay inside the project")
    for item in (candidate, *candidate.parents):
        if item == ROOT:
            break
        require(not is_link(item), f"Symbolic link or junction is not allowed: {item.name}")
    resolved = candidate.resolve(strict=must_exist)
    require(resolved.is_relative_to(ROOT), "Resolved path leaves the project")
    return resolved


def forbidden_name(name: str) -> bool:
    path = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or path.is_absolute():
        return True
    if any(part in {"", ".", ".."} for part in name.split("/")):
        return True
    parts = [part.lower() for part in path.parts]
    if any(part in FORBIDDEN_PARTS for part in parts):
        return True
    if any(part.startswith(".env") and part != ".env.example" for part in parts):
        return True
    return path.suffix.lower() in FORBIDDEN_SUFFIXES


def allowed_name(name: str, *, offline: bool) -> bool:
    if forbidden_name(name):
        return False
    if name in ROOT_FILES or name == MANIFEST_NAME:
        return True
    if name in {f"{RESULT_PREFIX}/{part}" for part in RESULT_FILES}:
        return True
    if name in OPTIONAL_REPORTS.values():
        return True
    if offline and name == "OFFLINE_README.md":
        return True
    path = PurePosixPath(name)
    if offline and len(path.parts) == 2 and path.parts[0] == "wheelhouse":
        return path.suffix == ".whl"
    return (
        len(path.parts) >= 2
        and path.parts[0] in DIRECTORY_SUFFIXES
        and (path.suffix.lower() in DIRECTORY_SUFFIXES[path.parts[0]]
             or path.name in {"LICENSE", "NOTICE", "COPYING"})
    )


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_file(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    require(isinstance(value, dict), f"{path.name}: expected a JSON object")
    return value


def valid_hashes(value, names) -> bool:
    return (
        isinstance(value, dict) and set(value) == set(names)
        and all(isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) for item in value.values())
    )


def acceptance(results: Path) -> dict:
    paths = {name: local_path(results / name) for name in RESULT_FILES}
    require(all(path.is_file() for path in paths.values()), "All five result files are required")
    report = json_file(paths["acceptance_report.json"])
    require(report.get("status") == "PASS", "Acceptance report is not PASS; run verify_submission.py")
    for flag in ("csv_byte_identical", "input_unchanged"):
        require(report.get(flag) is True, f"Acceptance check is not passed: {flag}")
    require(report.get("ai_enabled") is False, "Acceptance must have AI disabled")
    hashes = report.get("csv_sha256")
    require(valid_hashes(hashes, CSV_FILES), "Acceptance CSV SHA-256 fields are invalid")
    require(hashes == {name: sha256_file(paths[name]) for name in CSV_FILES},
            "Stale acceptance report: current CSV bytes differ; rerun verify_submission.py")
    inputs = report.get("input_sha256_before")
    require(valid_hashes(inputs, ("nodes.parquet", "edges.parquet", "transactions.parquet")),
            "Acceptance input SHA-256 fields are invalid")
    require(inputs == report.get("input_sha256_after"), "Input immutability check differs")
    runs = report.get("runs")
    require(isinstance(runs, list) and len(runs) == 2, "Acceptance must contain two successful runs")
    for run in runs:
        require(isinstance(run, dict), "Invalid acceptance run")
        require(run.get("network_guard") == {"installed": True, "attempts": []},
                "Acceptance run did not pass its socket/DNS guard")
        for name in ("raw_to_csv_seconds", "subprocess_wall_seconds"):
            value = run.get(name)
            require(isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) and 0 < value < 300, f"Invalid acceptance runtime: {name}")
        counts = run.get("validation")
        require(isinstance(counts, dict), "Missing acceptance output validation")
        for name in ("nodes", "clusters", "top_nodes", "evidence_max_characters"):
            require(type(counts.get(name)) is int and counts[name] > 0, f"Invalid acceptance count: {name}")
        require(counts["clusters"] <= counts["nodes"]
                and min(20, counts["nodes"]) <= counts["top_nodes"] <= counts["nodes"]
                and counts["evidence_max_characters"] <= 200, "Acceptance counts violate output contract")
    require(runs[0]["validation"] == runs[1]["validation"], "Repeated validation counts differ")
    run_report = json_file(paths["run_report.json"])
    metadata = run_report.get("run", {})
    require(metadata.get("input_sha256") == inputs, "run_report.json input hashes differ from acceptance")
    require(metadata.get("raw_to_csv_seconds") == runs[0]["raw_to_csv_seconds"],
            "run_report.json does not match the accepted first run")
    return report


@dataclass(frozen=True)
class Source:
    name: str
    path: Path | None
    content: bytes | None
    size: int
    sha256: str


def source_file(name: str, path: Path) -> Source:
    path = local_path(path)
    require(path.is_file(), f"Required file missing: {name}")
    return Source(name, path, None, path.stat().st_size, sha256_file(path))


def source_bytes(name: str, content: bytes) -> Source:
    return Source(name, None, content, len(content), hashlib.sha256(content).hexdigest())


def project_sources(results: Path) -> list[Source]:
    sources = [source_file(name, ROOT / name) for name in ROOT_FILES]
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8-sig")
    for line in env_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = (part.strip() for part in stripped.split("=", 1))
        if key.endswith("API_KEY"):
            require(not value, ".env.example contains a nonempty API key")
        if key == "MONEYMAP_AI_ENABLED":
            require(value.lower() == "false", ".env.example must keep real AI disabled")
    for directory in DIRECTORY_SUFFIXES:
        base = local_path(ROOT / directory)
        require(base.is_dir(), f"Required directory missing: {directory}")
        for current, directories, filenames in os.walk(base, followlinks=False):
            current_path = Path(current)
            directories[:] = sorted(
                part for part in directories
                if part.lower() not in FORBIDDEN_PARTS
                and not part.lower().startswith(".env")
                and not is_link(current_path / part)
            )
            for filename in sorted(filenames):
                path = current_path / filename
                name = path.relative_to(ROOT).as_posix()
                if not is_link(path) and allowed_name(name, offline=False):
                    sources.append(source_file(name, path))
    for name in RESULT_FILES:
        sources.append(source_file(f"{RESULT_PREFIX}/{name}", results / name))
    for relative, name in OPTIONAL_REPORTS.items():
        path = ROOT / relative
        if path.exists():
            json_file(local_path(path))  # Include the actual report, without claiming its status.
            sources.append(source_file(name, path))
    return sources


def normalized_package(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def wheel_sources(wheelhouse: Path) -> list[Source]:
    require(wheelhouse.is_dir(), "Wheelhouse must be a directory")
    expected = {}
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", text)
        require(match is not None, "Offline packaging requires plain name==version requirements")
        name, version = match.groups()
        name = normalized_package(name)
        require(name not in expected, "Duplicate pinned requirement")
        expected[name] = version
    found, sources = {}, []
    for path in sorted(wheelhouse.iterdir()):
        if path.suffix.lower() != ".whl":
            continue
        path = local_path(path)
        pieces = path.stem.split("-")
        require(len(pieces) in {5, 6}, f"Invalid wheel filename: {path.name}")
        name, version = normalized_package(pieces[0]), pieces[1]
        py_tag, abi_tag, platform_tag = pieces[-3:]
        require(name in expected and version == expected[name], f"Unpinned wheel: {path.name}")
        require(name not in found, f"Multiple wheels for pinned requirement: {name}")
        platforms = set(platform_tag.split("."))
        require(platforms <= {"any", "win_amd64"}, f"Wheel is not for Windows x64: {path.name}")
        python_tags = set(py_tag.split("."))
        compatible = bool(python_tags & {"py3", "cp314"})
        if abi_tag == "abi3":
            compatible = compatible or any(
                re.fullmatch(r"cp3\d+", tag) and 2 <= int(tag[3:]) <= 14
                for tag in python_tags
            )
        require(compatible, f"Wheel is not compatible with Python 3.14: {path.name}")
        found[name] = version
        sources.append(source_file(f"wheelhouse/{path.name}", path))
    require(found == expected, "Wheelhouse does not contain exactly one wheel for every pinned requirement")
    return sources


def verify_archive(path: Path, expected_manifest: dict) -> None:
    offline = expected_manifest["kind"] == "offline-win-py314"
    with ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        require(len({name.casefold() for name in names}) == len(names), "Duplicate archive paths")
        require(set(names) == set(expected_manifest["files"]) | {MANIFEST_NAME}, "Archive inventory differs")
        require(all(allowed_name(name, offline=offline) for name in names), "Forbidden archive path")
        manifest = json.loads(archive.read(MANIFEST_NAME))
        require(manifest == expected_manifest, "Archive manifest differs")
        for entry in entries:
            require(not entry.is_dir() and not stat.S_ISLNK(entry.external_attr >> 16), "Archive contains a link or directory entry")
            if entry.filename == MANIFEST_NAME:
                continue
            with archive.open(entry) as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            declared = manifest["files"][entry.filename]
            require(entry.file_size == declared["bytes"] and digest == declared["sha256"],
                    f"Archive checksum mismatch: {entry.filename}")


def write_archive(destination: Path, sources: list[Source], report: dict, *, offline: bool) -> dict:
    destination = local_path(destination, must_exist=False)
    require(destination.is_relative_to(ROOT / "output") and destination.suffix.lower() == ".zip",
            "Archive destination must be a .zip under the project output directory")
    names = [source.name for source in sources]
    require(len({name.casefold() for name in names}) == len(names), "Duplicate source archive paths")
    require(all(allowed_name(name, offline=offline) for name in names), "Source is outside the archive allowlist")
    manifest = {
        "schema_version": 1,
        "kind": "offline-win-py314" if offline else "submission",
        "hash_algorithm": "sha256",
        "notes": "Manifest excludes itself. Raw Parquet, API keys, caches and SQLite are not included. Integrity inventory, not a signature.",
        "acceptance": {"status": report["status"], "csv_sha256": report["csv_sha256"]},
        "files": {source.name: {"sha256": source.sha256, "bytes": source.size} for source in sorted(sources, key=lambda item: item.name)},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=".moneymap-package-", suffix=".tmp", dir=destination.parent, delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        with ZipFile(temporary, "w", allowZip64=True) as archive:
            for source in sorted(sources, key=lambda item: item.name):
                entry = ZipInfo(source.name, date_time=(2000, 1, 1, 0, 0, 0))
                entry.compress_type = ZIP_STORED if source.name.endswith(".whl") else ZIP_DEFLATED
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                digest, size = hashlib.sha256(), 0
                with archive.open(entry, "w", force_zip64=True) as target:
                    if source.path is None:
                        data = source.content or b""
                        target.write(data)
                        digest.update(data)
                        size = len(data)
                    else:
                        with local_path(source.path).open("rb") as stream:
                            while chunk := stream.read(1024 * 1024):
                                target.write(chunk)
                                digest.update(chunk)
                                size += len(chunk)
                require(size == source.size and digest.hexdigest() == source.sha256,
                        f"Source changed during packaging: {source.name}; retry after edits finish")
            entry = ZipInfo(MANIFEST_NAME, date_time=(2000, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        verify_archive(temporary, manifest)
        # Atomic replacement happens only after every content hash is verified.
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"path": str(destination), "files": len(sources) + 1, "bytes": destination.stat().st_size, "sha256": sha256_file(destination)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("output/submission/results"))
    parser.add_argument("--out", type=Path, default=Path("output/submission/moneymap-submission.zip"))
    parser.add_argument("--wheelhouse", type=Path, help="Also build full offline kit from all pinned Windows/Python 3.14 wheels")
    args = parser.parse_args(argv)
    try:
        results = local_path(args.results)
        report = acceptance(results)
        sources = project_sources(results)
        output = local_path(args.out, must_exist=False)
        wheels = wheel_sources(local_path(args.wheelhouse)) if args.wheelhouse else None
        offline_output = output.with_name("moneymap-offline-win-py314.zip")
        require(wheels is None or offline_output != output, "Standard and offline archives must have different names")
        # Recheck the exact CSV snapshot which will be packaged, not just earlier file contents.
        snapshot = {PurePosixPath(source.name).name: source.sha256 for source in sources
                    if source.name.startswith(RESULT_PREFIX + "/") and PurePosixPath(source.name).name in CSV_FILES}
        require(snapshot == report["csv_sha256"], "CSV files changed after acceptance was checked")
        built = [write_archive(output, sources, report, offline=False)]
        if wheels is not None:
            offline_sources = [*sources, *wheels, source_bytes("OFFLINE_README.md", OFFLINE_README.encode("utf-8"))]
            built.append(write_archive(offline_output, offline_sources, report, offline=True))
        for archive in built:
            print(f"PASS: {archive['path']} ({archive['files']} files, {archive['bytes']} bytes)")
            print(f"SHA256: {archive['sha256']}")
        if wheels is not None:
            print(f"Offline kit: {len(wheels)} pinned wheels; Windows x64 / Python 3.14 only")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
