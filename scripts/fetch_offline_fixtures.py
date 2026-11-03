#!/usr/bin/env python3
"""Baja fixtures offline desde archivos de una rama, no desde un Release.

Lee ``datos/offline/`` en ``RRM_OFFLINE_REPO`` (default
FrankEBaru/research-microscope-compass) y ``RRM_OFFLINE_BRANCH`` (default
``claude/rrm-50-plan-b1``). v2 son dos partes: se unen y el sha256 tiene que
coincidir con el del archivo unido. v3 es un tar (o partes, si las hay).
La caché local evita volver a bajar los blobs si el sha ya está en disco.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from urllib.parse import quote

ROOT_PREFIX = "datos/offline"
_HEX = re.compile(r"\b([a-fA-F0-9]{64})\b")
_PART = re.compile(r"\.part[-_.]?[a-z0-9]+$", re.I)


def _die(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def _endpoint(repo: str, branch: str, path: str) -> str:
    safe = "/".join(quote(seg) for seg in path.split("/") if seg != "")
    return f"repos/{repo}/contents/{safe}?ref={quote(branch, safe='')}"


def _gh_json(endpoint: str):
    proc = subprocess.run(
        ["gh", "api", endpoint],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()
        _die(err or f"gh api falló: {endpoint}")
    try:
        return json.loads(proc.stdout.decode("utf-8"))
    except json.JSONDecodeError:
        _die(f"gh api no devolvió JSON: {endpoint}")


def _gh_raw(endpoint: str) -> bytes:
    proc = subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw", endpoint],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        _die(err or f"gh api no pudo bajar {endpoint}")
    return proc.stdout


def _walk(repo: str, branch: str, path: str) -> list[dict]:
    data = _gh_json(_endpoint(repo, branch, path))
    if isinstance(data, dict):
        if data.get("type") == "file":
            return [data]
        msg = data.get("message") or "respuesta inesperada"
        _die(f"No pude listar {path} en {repo} (rama {branch}): {msg}")
    out: list[dict] = []
    for item in data:
        if item.get("type") == "dir":
            out.extend(_walk(repo, branch, item["path"]))
        elif item.get("type") == "file":
            out.append(item)
    return out


def _rel(path: str) -> str:
    prefix = ROOT_PREFIX + "/"
    if path.startswith(prefix):
        return path[len(prefix):]
    return path


def _belongs(rel: str, version: str) -> bool:
    parts = rel.split("/")
    dirs = parts[:-1]
    name = parts[-1].lower()
    tokens = {version, f"offline-fixtures-{version}", f"fixtures-{version}"}
    if any(d.lower() in tokens for d in dirs):
        return True
    return version in name or f"fixtures-{version}" in name


def _pack_entry(pack: dict, version: str):
    num = version[1:] if version.startswith("v") else version
    block = None
    if isinstance(pack.get(version), dict):
        block = pack[version]
    elif isinstance(pack.get(num), dict):
        block = pack[num]
    elif isinstance(pack.get("versions"), dict):
        versions = pack["versions"]
        block = versions.get(version) if isinstance(versions.get(version), dict) else versions.get(num)
    if not isinstance(block, dict):
        return None
    parts = []
    if isinstance(block.get("parts"), list):
        parts = [str(p) for p in block["parts"]]
    elif isinstance(block.get("files"), list):
        parts = [str(p) for p in block["files"]]
    elif isinstance(block.get("file"), str):
        parts = [block["file"]]
    sha = str(block.get("sha256") or block.get("sha") or "").strip().lower()
    if not parts or not re.fullmatch(r"[a-f0-9]{64}", sha):
        return None
    return {"parts": parts, "sha256": sha}


def _parse_sha_text(text: str) -> list[tuple[str, str]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-fA-F0-9]{64})(?:\s+\*?(\S+))?$", line)
        if match:
            rows.append((match.group(1).lower(), match.group(2) or ""))
    return rows


def _joined_name(names: list[str]) -> str:
    return _PART.sub("", names[0])


def _expected_sha(sha_blobs: list[tuple[str, str]], joined_name: str, readme: str, full_readme: str = "") -> str:
    base = Path(joined_name).name
    parsed: list[tuple[str, str, str]] = []
    for filename, text in sha_blobs:
        for digest, named in _parse_sha_text(text):
            parsed.append((digest, named, filename))
    for digest, named, _filename in parsed:
        if named and Path(named).name == base:
            return digest
    bare = [digest for digest, named, filename in parsed if not named and ".part-" not in filename.lower()]
    if len(bare) == 1:
        return bare[0]
    singles = [digest for digest, named, filename in parsed if ".part-" not in filename.lower() and ".part-" not in named]
    if len(singles) == 1:
        return singles[0]
    # README de compass: tabla markdown con una fila por archivo; la del archivo
    # unido nombra `offline-fixtures-vN.tar.gz` exacto (las partes llevan .part-).
    named_rows = {
        digest.lower()
        for line in f"{readme or ''}\n{full_readme or ''}".splitlines()
        if f"`{base}`" in line
        for digest in _HEX.findall(line)
    }
    if len(named_rows) == 1:
        return named_rows.pop()
    found = {digest.lower() for digest in _HEX.findall(readme or "")}
    if len(found) == 1:
        return found.pop()
    return ""


def _readme_for(version: str, readme: str) -> str:
    if not readme:
        return ""
    lines = readme.splitlines()
    heads = []
    for i, line in enumerate(lines):
        if re.match(r"^#{1,3}\s+", line) and version in line.lower():
            heads.append(i)
    if not heads:
        return readme
    start = heads[0]
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^#{1,3}\s+", lines[j]) and version not in lines[j].lower():
            end = j
            break
    return "\n".join(lines[start:end])


def _is_sha_name(name: str) -> bool:
    low = name.lower()
    return low.endswith(".sha256") or low.endswith(".sha256sum") or low in {
        "sha256", "sha256.txt", "sha256sums", "sha256sum",
    }


def _is_part(name: str) -> bool:
    return ".part-" in name.lower() or bool(re.search(r"\.part\d+$", name.lower()))


def _is_archive(name: str) -> bool:
    low = name.lower()
    return low.endswith(".tar.gz") or low.endswith(".tgz") or low.endswith(".tar")


def _extract(blob: bytes, dest: Path) -> None:
    tmp = Path(f"{dest}.tmp.extract")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tar:
            for member in tar.getmembers():
                name = member.name
                if name.startswith("/") or ".." in Path(name).parts:
                    _die(f"ruta insegura en el tar: {name}")
            tar.extractall(tmp)
        src = ""
        if (tmp / "manifest.json").is_file():
            src = tmp
        elif (tmp / "offline-fixtures" / "manifest.json").is_file():
            src = tmp / "offline-fixtures"
        else:
            for sub in tmp.iterdir():
                if sub.is_dir() and (sub / "manifest.json").is_file():
                    src = sub
                    break
        if not src:
            _die("El archivo no trae manifest.json.")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(src), dest)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def _cache_paths(cache: Path, branch: str, version: str) -> tuple[Path, Path]:
    slug = branch.replace("/", "__")
    folder = cache / slug / version
    return folder / "joined.tar.gz", folder / "sha256"


def _install(blob: bytes, expected: str, dest: Path, cache: Path, branch: str, version: str) -> None:
    if blob.startswith(b"version https://git-lfs.github.com/spec/v1"):
        _die(f"{version} bajó un puntero de Git LFS, no el tar (rama {branch}).")
    got = hashlib.sha256(blob).hexdigest()
    if got != expected:
        _die(
            f"sha256 no coincide para {version} (rama {branch}). "
            f"Esperado {expected}, salió {got}."
        )
    tar_path, sha_path = _cache_paths(cache, branch, version)
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_tar = tar_path.with_suffix(".tar.gz.partial")
    tmp_tar.write_bytes(blob)
    tmp_tar.replace(tar_path)
    sha_path.write_text(expected + "\n", encoding="utf-8")
    _extract(blob, dest)
    (dest / ".rrm-release").write_text(
        f"branch={branch} version={version} sha256={expected}\n",
        encoding="utf-8",
    )
    print(f"Fixtures {version} (sha256 {expected[:12]}, rama {branch}): {dest}")


def _download_rel(repo: str, branch: str, rel: str, by_rel: dict[str, dict]) -> bytes:
    item = by_rel.get(rel)
    path = item["path"] if item else f"{ROOT_PREFIX}/{rel}"
    return _gh_raw(_endpoint(repo, branch, path))


def fetch(repo: str, branch: str, version: str, dest: Path, cache: Path) -> None:
    try:
        files = _walk(repo, branch, ROOT_PREFIX)
    except SystemExit:
        raise
    except OSError as exc:
        _die(f"No pude leer {ROOT_PREFIX} en {repo} (rama {branch}): {exc}")
    if not files:
        _die(f"{ROOT_PREFIX} está vacío en {repo} (rama {branch}).")
    by_rel = {_rel(item["path"]): item for item in files}
    readme = ""
    if "README.md" in by_rel:
        readme = _gh_raw(_endpoint(repo, branch, by_rel["README.md"]["path"])).decode("utf-8", "replace")
    pack = None
    if "manifest.json" in by_rel:
        raw = _gh_raw(_endpoint(repo, branch, by_rel["manifest.json"]["path"]))
        try:
            obj = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and "queries" not in obj:
            pack = obj
    entry = _pack_entry(pack, version) if pack else None
    chosen = [item for rel, item in by_rel.items() if rel and _belongs(rel, version)]
    names = sorted(by_rel)
    if entry:
        expected = entry["sha256"]
        cached, cached_sha = _cache_paths(cache, branch, version)
        if cached.is_file() and cached_sha.is_file() and cached_sha.read_text(encoding="utf-8").strip() == expected:
            blob = cached.read_bytes()
        else:
            blob = b"".join(_download_rel(repo, branch, rel, by_rel) for rel in entry["parts"])
    else:
        parts = sorted((item for item in chosen if _is_part(item["name"])), key=lambda item: item["name"])
        archives = sorted((item for item in chosen if _is_archive(item["name"])), key=lambda item: item["name"])
        sha_items = [item for item in chosen if _is_sha_name(item["name"])]
        version_readme = _readme_for(version, readme)
        for item in chosen:
            if item["name"].lower() == "readme.md":
                version_readme += "\n" + _gh_raw(_endpoint(repo, branch, item["path"])).decode("utf-8", "replace")
        sha_blobs = [
            (item["name"], _gh_raw(_endpoint(repo, branch, item["path"])).decode("utf-8", "replace"))
            for item in sha_items
        ]
        if parts:
            joined = _joined_name([item["name"] for item in parts])
            expected = _expected_sha(sha_blobs, joined, version_readme, readme)
            if not expected:
                _die(
                    f"{version} no trae el sha256 del archivo unido en {ROOT_PREFIX} "
                    f"(rama {branch}). Archivos: {', '.join(names)}"
                )
            cached, cached_sha = _cache_paths(cache, branch, version)
            if cached.is_file() and cached_sha.is_file() and cached_sha.read_text(encoding="utf-8").strip() == expected:
                blob = cached.read_bytes()
            else:
                blob = b"".join(_gh_raw(_endpoint(repo, branch, item["path"])) for item in parts)
        elif len(archives) == 1:
            archive = archives[0]
            expected = _expected_sha(sha_blobs, archive["name"], version_readme, readme)
            if not expected:
                _die(
                    f"{version} no trae sha256 en {ROOT_PREFIX} (rama {branch}). "
                    f"Archivos: {', '.join(names)}"
                )
            cached, cached_sha = _cache_paths(cache, branch, version)
            if cached.is_file() and cached_sha.is_file() and cached_sha.read_text(encoding="utf-8").strip() == expected:
                blob = cached.read_bytes()
            else:
                blob = _gh_raw(_endpoint(repo, branch, archive["path"]))
        else:
            _die(
                f"No encontré el tar de {version} en {ROOT_PREFIX} (rama {branch}). "
                f"Archivos: {', '.join(names)}"
            )
    _install(blob, expected, dest, cache, branch, version)
    _install_licenses(repo, branch, version, dest, by_rel)


def _install_licenses(repo: str, branch: str, version: str, dest: Path, by_rel: dict[str, dict]) -> None:
    # RRM-73: sin licenses.json el gate trata todo como cerrado y no hay artefactos.
    # Compass guarda el mapa como datos/offline/licenses-vN.json junto al tar.
    target = dest / "licenses.json"
    rel = f"licenses-{version}.json"
    if target.exists() or rel not in by_rel:
        return
    raw = _gh_raw(_endpoint(repo, branch, by_rel[rel]["path"]))
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        print(f"{rel} no es JSON; no lo copio.", file=sys.stderr)
        return
    if not isinstance(obj, dict):
        return
    target.write_bytes(raw)
    print(f"Mapa de licencias {rel} ({len(obj)} ids): {target}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baja fixtures offline desde una rama de compass.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args(argv)
    version = args.version.strip().lower()
    if not re.fullmatch(r"v[0-9]+", version):
        _die("La versión tiene que ser v2 o v3.")
    os.environ.setdefault("GH_PROMPT_DISABLED", "1")
    fetch(args.repo, args.branch, version, args.dest, args.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
