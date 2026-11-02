"""공식 소스에 최소 패치를 적용하고 독립된 PyNvVideoCodec wheel을 빌드한다."""

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.error import URLError
from urllib.request import urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA256 = "0ecb47da0bd40dc70e1e684fa95073fd6f3debc607fd4a5056b99b42af5cbeb1"
ARCHIVE_URL = ("https://api.ngc.nvidia.com/v2/resources/nvidia/pynvvideocodec/"
               "versions/2.2.2/files/PyNvVideoCodec_2.2.2.zip")
VERSION = "2.2.2+pipeworks.1"
PATCH = ROOT / "tools/patches/pynvvideocodec-2.2.2-locked-frame-pts.patch"
SOURCE_NAME = "PyNvVideoCodec_2.2.2"
TRACKED = ("src/PyNvVideoCodec/src/PyNvDecoder.cpp", "pyproject.toml",
           "setup.py", "src/PyNvVideoCodec/__init__.py")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ensure_archive(archive):
    """원본 캐시를 검증하고, 없으면 공식 파일을 검증 후 저장한다."""
    archive = archive.resolve()
    if archive.exists():
        if sha256(archive) != ARCHIVE_SHA256:
            raise ValueError("공식 2.2.2 ZIP의 SHA-256이 다릅니다. 파일을 확인하세요.")
        return archive
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=archive.parent, suffix=".download", delete=False) as output:
            temporary = Path(output.name)
            print(f"공식 소스 다운로드: {ARCHIVE_URL}", flush=True)
            with urlopen(ARCHIVE_URL, timeout=120) as response:
                shutil.copyfileobj(response, output)
        if sha256(temporary) != ARCHIVE_SHA256:
            raise ValueError("다운로드한 공식 2.2.2 ZIP의 SHA-256이 다릅니다.")
        temporary.replace(archive)
        return archive
    except (OSError, URLError) as error:
        raise RuntimeError(f"공식 소스 다운로드 실패: {error}. --source-archive로 원본 ZIP을 지정할 수 있습니다.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare(archive, work_dir):
    archive, work_dir = archive.resolve(), work_dir.resolve()
    if sha256(archive) != ARCHIVE_SHA256:
        raise ValueError("공식 2.2.2 ZIP의 SHA-256이 다릅니다. 소스 버전을 확인하세요.")
    source = work_dir / SOURCE_NAME
    stamp = work_dir / "pipeworks-patch.json"
    identity = {"archive_sha256": ARCHIVE_SHA256, "patch_sha256": sha256(PATCH),
                "version": VERSION}
    if stamp.exists():
        manifest = json.loads(stamp.read_text(encoding="utf-8"))
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("기존 작업 디렉터리의 패치 버전이 다릅니다. 새 --work-dir을 지정하세요.")
        if any(not (source / name).is_file() or sha256(source / name) != value
               for name, value in manifest["files"].items()):
            raise ValueError("준비된 소스가 변경되었습니다. 새 --work-dir을 지정하세요.")
        return source
    if work_dir.exists() and any(work_dir.iterdir()):
        raise ValueError("작업 디렉터리가 비어 있지 않습니다. 새 --work-dir을 지정하세요.")
    git = shutil.which("git")
    if not git:
        raise RuntimeError("패치 검증과 적용에 Git이 필요합니다.")
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (work_dir / member.filename).resolve()
            mode = member.external_attr >> 16
            if (not target.is_relative_to(work_dir)
                    or not member.filename.startswith(SOURCE_NAME + "/")
                    or stat.S_ISLNK(mode)):
                raise ValueError(f"안전하지 않은 ZIP 경로: {member.filename}")
        work_dir.mkdir(parents=True, exist_ok=True)
        bundle.extractall(work_dir)
    # 원본 ZIP에 포함된 CRCRLF를 정규화하여 같은 패치를 재현 가능하게 적용한다.
    binding = source / TRACKED[0]
    binding.write_text(binding.read_bytes().decode("utf-8").replace("\r", ""),
                       encoding="utf-8", newline="\n")
    for action in (("--check",), ()):
        subprocess.run([git, "apply", "--no-index", *action, str(PATCH)],
                       cwd=source, check=True)
    for name, old in (("pyproject.toml", 'version = "2.2.2"'),
                      ("setup.py", 'version="2.2.2"'),
                      ("src/PyNvVideoCodec/__init__.py", '__version__ = "2.2.2"')):
        path = source / name
        content = path.read_bytes().decode("utf-8").replace("\r", "")
        if content.count(old) != 1:
            raise ValueError(f"버전 치환 위치가 다릅니다: {name}")
        path.write_text(content.replace(old, old.replace("2.2.2", VERSION)),
                        encoding="utf-8", newline="\n")
    identity["files"] = {name: sha256(source / name) for name in TRACKED}
    stamp.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    return source


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", type=Path, default=ROOT / "PyNvVideoCodec_2.2.2.zip")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "build/pynvvideocodec-patched-v141-cuda120")
    parser.add_argument("--wheel-dir", type=Path, default=ROOT / "dist/pynvvideocodec-patched-v141-cuda120")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--cmake-arg", action="append", default=[])
    parser.add_argument("--pybind11-source-dir", type=Path)
    parser.add_argument("--dlpack-source-dir", type=Path)
    return parser.parse_args(argv)


def build_environment(args, environ=None):
    env = dict(os.environ if environ is None else environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    if sys.platform == "win32":
        compiler = shutil.which("cl", path=env["PATH"])
        if not compiler:
            raise RuntimeError("Visual Studio의 x64 개발자 PowerShell에서 실행하세요. cl.exe를 찾지 못했습니다.")
        env["CC"] = env["CXX"] = compiler
        # 구버전 scikit-build의 VS 자동 탐색 대신 활성 개발자 환경을 사용한다.
        env.setdefault("CMAKE_GENERATOR", "Ninja Multi-Config")
    previous = env.pop("CMAKE_ARGS", "")
    previous = env.get("SKBUILD_CONFIGURE_OPTIONS", previous)
    cmake_args = [*shlex.split(previous),
                  "-DPython_EXECUTABLE=" + Path(sys.executable).as_posix(),
                  f"-DREQUESTED_PYTHON_VERSION={sys.version_info.major}.{sys.version_info.minor}",
                  *args.cmake_arg]
    if args.pybind11_source_dir:
        cmake_args.append("-DFETCHCONTENT_SOURCE_DIR_PYBIND11="
                          + args.pybind11_source_dir.resolve().as_posix())
    if args.dlpack_source_dir:
        env["DLPACK_SOURCE_DIR"] = str(args.dlpack_source_dir.resolve())
    env["SKBUILD_CONFIGURE_OPTIONS"] = shlex.join(cmake_args)
    return env


def main(argv=None):
    args = parse_args(argv)
    try:
        source = prepare(ensure_archive(args.source_archive), args.work_dir)
        print(f"패치 준비 완료: {source}", flush=True)
        if args.prepare_only:
            return 0
        missing = []
        for name in ("build", "scikit-build", "setuptools", "wheel", "numpy", "packaging"):
            try:
                version(name)
            except PackageNotFoundError:
                missing.append(name)
        if missing:
            raise RuntimeError("빌드 패키지가 없습니다: " + ", ".join(missing)
                               + ". requirements-pynvvideocodec-build.txt를 빌드 환경에 설치하세요.")
        env = build_environment(args)
        if not shutil.which("cmake", path=env["PATH"]):
            raise RuntimeError("CMake가 PATH에 없습니다.")
        args.wheel_dir.resolve().mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation",
                        "--outdir", str(args.wheel_dir.resolve()), str(source)],
                       env=env, check=True)
        wheels = list(args.wheel_dir.resolve().glob(f"pynvvideocodec-{VERSION}-*.whl"))
        if not wheels:
            raise RuntimeError("빌드 후 수정 버전 wheel을 찾지 못했습니다.")
        for wheel in wheels:
            print(f"wheel: {wheel}\nSHA-256: {sha256(wheel)}")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"빌드 실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
