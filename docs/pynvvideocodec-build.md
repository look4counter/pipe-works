# PyNvVideoCodec v141·CUDA 12.0 빌드와 배포

정상 동작이 확인된 MSVC v141·CUDA 12.0 조건으로 `2.2.2+pipeworks.1` 수정 wheel을 만든다. 영구 진입점은 프로젝트 루트의 `build-pynvvideocodec-v141-cuda120.ps1`이다. 기존 일반 빌드 진입점은 제거했다.

## 최초 준비

Windows x64에 다음 도구를 설치한다.

- Visual Studio Installer의 MSVC v141 - VS 2017 C++ x64/x86 빌드 도구(14.16)
- CUDA Toolkit 12.0: 기본 경로 `C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.0`
- Git과 Python 3.11.9, uv

```powershell
uv venv --python 3.11.9 build/pynvvideocodec-env
uv pip install --python build/pynvvideocodec-env/Scripts/python.exe -r requirements-pynvvideocodec-build.txt
```

빌드 의존성은 정상 비교 빌드와 같은 scikit-build 0.18.1 등으로 고정한다. 공식 wheel의 scikit-build 0.19.1과 모든 빌드 옵션까지 일치한다고 보장하지 않는다.

## 빌드

일반 PowerShell에서 프로젝트 루트로 이동한 뒤 실행한다. 개발자 PowerShell을 따로 활성화하지 않아도 스크립트가 v141 환경을 선택한다. 도구가 없거나 버전이 다르면 중단하며 다른 버전으로 대체하지 않는다. 종료 시 호출자의 환경 변수를 복원한다.

```powershell
./build-pynvvideocodec-v141-cuda120.ps1
```

원본 ZIP이 프로젝트 루트에 없으면 NVIDIA NGC의 고정 2.2.2 파일을 자동 다운로드한다. 임시 파일의 SHA-256이 `0ecb47da0bd40dc70e1e684fa95073fd6f3debc607fd4a5056b99b42af5cbeb1`과 일치해야 캐시로 저장한다. 기존 파일은 검증 후 재사용하며, 불일치 파일을 자동으로 덮어쓰지 않는다. 다운로드 실패 시 임시 파일을 정리하고 오류를 출력한다.

- 원본 캐시: `PyNvVideoCodec_2.2.2.zip`
- 패치된 소스·CMake 캐시: `build/pynvvideocodec-patched-v141-cuda120/`
- 수정 wheel: `dist/pynvvideocodec-patched-v141-cuda120/pynvvideocodec-2.2.2+pipeworks.1-cp311-cp311-win_amd64.whl`

패치 적용까지만 확인하거나 다른 원본 캐시·작업 경로를 사용하려면 다음처럼 실행한다.

```powershell
./build-pynvvideocodec-v141-cuda120.ps1 -PrepareOnly
./build-pynvvideocodec-v141-cuda120.ps1 -SourceArchive D:/Downloads/PyNvVideoCodec_2.2.2.zip
./build-pynvvideocodec-v141-cuda120.ps1 -WorkDirectory ./build/pynvvideocodec-v141-cuda120-fresh
```

`-Python`, `-OutputDirectory`, `-VisualStudioDirectory`, `-CudaDirectory`로 설치 경로를 지정할 수 있다. CUDA 경로를 바꿔도 12.0 검증을 통과해야 한다. 패치나 컴파일 조건이 달라졌다면 새 작업 경로를 사용한다.

CMake는 필요한 pybind11 2.10.0과 DLPack 0.8을 다운로드한다. `build/deps/pybind11-2.10.0`과 `build/deps/dlpack-0.8`이 있으면 자동으로 사용한다. 오프라인에서는 패키지를 미리 설치하고 원본 ZIP과 다음 소스 경로를 제공한다.

```powershell
./build-pynvvideocodec-v141-cuda120.ps1 `
  -SourceArchive D:/BuildDeps/PyNvVideoCodec_2.2.2.zip `
  -Pybind11SourceDirectory D:/BuildDeps/pybind11-2.10.0 `
  -DLPackSourceDirectory D:/BuildDeps/dlpack-0.8
```

## 구형 산출물 정리

정리 스크립트는 이전 CUDA 12.6 패치본, 실패 원본 비교본과 관련 작업·로그만 고정 목록으로 처리한다. 정상 v141 패치본·원본 비교본, 공식 원본, 라이선스 묶음, PipeWorks wheel, 빌드 Python·의존성은 유지한다. 연결 경로는 삭제하지 않는다.

```powershell
./cleanup-pynvvideocodec-obsolete.ps1 -WhatIf
./cleanup-pynvvideocodec-obsolete.ps1
```

이 작업 세션에서는 자동 실행 정책이 실제 삭제를 차단하여 구형 산출물이 남아 있다. 위 명령을 로컬에서 실행하면 된다. 새 빌드는 구형 파일이 있는 dist 루트 대신 위 전용 출력 폴더를 사용한다.

## 설치와 검증

빌드에 사용한 Python ABI와 같은 Windows x64·Python 3.11 환경에 설치한다. 실행 PC에는 NVIDIA 드라이버와 필요한 CUDA·VC++ 런타임을 준비한다. 원본 ZIP은 설치·실행에 사용하지 않는다.

```powershell
python -m pip install --force-reinstall --no-deps ./dist/pynvvideocodec-patched-v141-cuda120/pynvvideocodec-2.2.2+pipeworks.1-cp311-cp311-win_amd64.whl
```

앱을 재시작한다. 기본 `uv.lock`은 공식 wheel을 가리키므로 `uv sync --no-install-package pynvvideocodec` 후 수정본을 설치하거나 배포 프로젝트의 소스를 수정 wheel로 고정한다.

```powershell
$env:PYTHONPATH = 'src;tests'
.venv/Scripts/python.exe -m unittest test_pynvvideocodec_build
.venv/Scripts/python.exe -m unittest test_nvidia_decode.NativeDecodeTests.test_native_patched_locked_pts_survive_decode_and_reach_encoder
```

네이티브 검사는 수정 wheel을 설치하고 CUDA가 제공된 환경에서 건너뜀 없이 통과해야 한다. `_121`과 `_130`의 선택은 드라이버가 지원하는 NVENC API 버전에 따른다. 두 모듈의 링커 14.16·PTX 8.0과 GPU PTS 보존 검증 기록은 [검증 결과](../specs/049-preserve-source-timestamps/validation.md)에 있다. 대상 Windows 10·L40-8Q·538.15 환경에서 v141·CUDA 12.0 패치본의 정상 동작은 사용자가 확인했다.

## 배포

wheel과 함께 [라이선스·제3자 고지](../licenses/pynvvideocodec/README.md)를 제공한다. 기존 `pynvvideocodec-2.2.2+pipeworks.1-licenses.zip`은 라이선스·FFmpeg 소스 제공용이며 설치 파일이 아니다. PipeWorks와 수정 wheel을 같은 wheelhouse에 제공할 때는 정확한 버전을 지정한 `requirements-pynvvideocodec.txt`를 사용한다.
