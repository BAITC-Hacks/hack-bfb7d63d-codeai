"""Install an optional, pinned local CPU LLM under the project's ignored .local directory.

Downloads only official llama.cpp and Qwen artifacts; verifies published SHA256.
It never uploads analysis data and never writes a system-wide installation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "b10964"
REPO = "Qwen/Qwen3-1.7B-GGUF"
MODEL_FILE = "Qwen3-1.7B-Q8_0.gguf"
MODEL_REVISION = "90862c4b9d2787eaed51d12237eafdfe7c5f6077"
MODEL_SHA256 = "061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a"
RUNTIME_SHA256 = "917f39c076402c421224824607397af20f53625a60defc20e8dd22446bf4c5d7"


def read_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "AQSHA-TRACE-local-setup"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, path, expected_hash):
    if path.exists() and sha256(path) == expected_hash:
        print("Verified existing", path.name, flush=True)
        return
    temporary = path.with_suffix(path.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "AQSHA-TRACE-local-setup"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
        total = int(response.headers.get("Content-Length", "0"))
        seen = 0
        checkpoint = 0
        for chunk in iter(lambda: response.read(4 * 1024 * 1024), b""):
            output.write(chunk)
            digest.update(chunk)
            seen += len(chunk)
            if seen - checkpoint >= 128 * 1024 * 1024:
                print(f"{path.name}: {seen // 1024**2} MiB / {total // 1024**2 if total else '?'}", flush=True)
                checkpoint = seen
    if digest.hexdigest() != expected_hash:
        raise ValueError(f"SHA256 mismatch for {path.name}; artifact was not installed")
    temporary.replace(path)
    print("SHA256 verified:", path.name, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    release = read_json(f"https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{RELEASE}")
    archive_name = f"llama-{RELEASE}-bin-win-cpu-x64.zip"
    asset = next(item for item in release["assets"] if item["name"] == archive_name)
    digest = asset.get("digest", "")
    if not digest.startswith("sha256:"):
        raise ValueError("The official release does not publish an archive SHA256")
    if digest != "sha256:" + RUNTIME_SHA256:
        raise ValueError("Published runtime digest differs from the pinned release")
    revision = MODEL_REVISION
    tree = read_json(f"https://huggingface.co/api/models/{REPO}/tree/{revision}")
    model = next(item for item in tree if item["path"] == MODEL_FILE)
    model_hash = model["lfs"]["oid"]
    if model_hash != MODEL_SHA256:
        raise ValueError("Published model digest differs from the pinned model")
    manifest = {"release": RELEASE, "archive_url": asset["browser_download_url"],
                "archive_sha256": digest.split(":", 1)[1], "archive_bytes": asset["size"],
                "model_repository": REPO, "model_revision": revision,
                "model_url": f"https://huggingface.co/{REPO}/resolve/{revision}/{MODEL_FILE}",
                "model_sha256": model_hash, "model_bytes": model["size"],
                "runtime_source": "https://github.com/ggml-org/llama.cpp",
                "model_source": f"https://huggingface.co/{REPO}"}
    print(json.dumps(manifest, indent=2), flush=True)
    if args.inspect:
        return
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    if shutil.disk_usage(local).free < model["size"] + 4 * asset["size"] + 512 * 1024**2:
        raise ValueError("Insufficient free space on the project drive")
    archive = local / archive_name
    model_path = local / MODEL_FILE
    download(manifest["archive_url"], archive, manifest["archive_sha256"])
    download(manifest["model_url"], model_path, model_hash)
    runtime = local / "llama"
    runtime.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = (runtime / member.filename).resolve()
            if not target.is_relative_to(runtime.resolve()):
                raise ValueError("Unexpected archive path")
        package.extractall(runtime)
    server = next(runtime.rglob("llama-server.exe"))
    manifest.update({"server_path": str(server.relative_to(ROOT)), "model_path": str(model_path.relative_to(ROOT))})
    (local / "model-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Local CPU model installed. Start using start-local-model.ps1", flush=True)


if __name__ == "__main__":
    main()
