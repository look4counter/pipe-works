# PTS 바인딩 wheel 빌드와 배포

GitHub 배포 시 [라이선스와 제3자 고지](../licenses/pynvvideocodec/README.md)를 명시하고, wheel과 라이선스·FFmpeg 소스 ZIP을 함께 첨부한다.

공식 PyNvVideoCodec 2.2.2 소스에 최소 바인딩 패치를 적용하여 `2.2.2+pipeworks.1` wheel을 만든다. 원본 ZIP과 설치된 패키지는 변경하지 않는다. 현재 지원 안내는 Windows x64·Python 3.11 기준이다. 실제 빌드에는 C++ 컴파일러와 CUDA Toolkit이 필요하다.

## 준비

공식 `PyNvVideoCodec_2.2.2.zip`을 프로젝트 루트에 둔다. 빌드 도구는 SHA-256이 `0ecb47da0bd40dc70e1e684fa95073fd6f3debc607fd4a5056b99b42af5cbeb1`인 원본만 받는다. 다른 버전은 소스를 검토하여 새 패치와 해시를 추가해야 한다.

Visual Studio의 C++ 빌드 도구와 CUDA Toolkit, Git을 준비하고 x64 개발자 PowerShell에서 실행한다. 빌드 전용 Python 환경을 만들어 개발 패키지를 설치한다.

```powershell
uv venv --python 3.11.9 build/pynvvideocodec-env
uv pip install --python build/pynvvideocodec-env/Scripts/python.exe -r requirements-pynvvideocodec-build.txt
```

이 단계에는 패키지 저장소 접근이 필요하다. CMake는 기본적으로 공식 소스에 지정된 pybind11 2.10.0과 DLPack 0.8을 다운로드한다. FFmpeg 헤더와 라이브러리는 원본 ZIP에 포함되어 있다. 사용한 CUDA Toolkit과 컴파일러 버전은 배포 시 함께 기록한다.

## 패치 검토와 빌드

```powershell
./build-pynvvideocodec.ps1 -PrepareOnly
./build-pynvvideocodec.ps1 -Python ./build/pynvvideocodec-env/Scripts/python.exe
```

준비 단계는 `build/pynvvideocodec/PyNvVideoCodec_2.2.2`에 원본을 추출하고 `tools/patches/pynvvideocodec-2.2.2-locked-frame-pts.patch`를 적용한다. 새 메서드만 추가하며 기존 `GetLockedFrame()`과 `UnlockFrame()`은 유지한다. 메타데이터와 모듈 버전도 함께 변경한다. 재실행 시 입력 해시와 준비된 수정 파일들을 확인하고, 로컬 변경이 있으면 덮어쓰지 않고 실패한다. 패치를 변경한 뒤 다시 빌드할 때는 새 `-WorkDirectory`를 지정한다.

빌드 결과는 `dist/pynvvideocodec-2.2.2+pipeworks.1-*.whl`이다. 빌드 도구가 출력하는 wheel SHA-256을 배포 기록에 남긴다. Python ABI·운영체제·아키텍처가 다른 환경에는 해당 환경용 wheel을 따로 빌드하고 검증해야 한다.

Windows에서는 활성화한 MSVC 개발자 환경과 Ninja Multi-Config를 사용한다. Visual Studio 2026에서도 CUDA가 지원하는 14.44 도구 집합을 선택할 수 있다. MSVC 14.44·CUDA 12.6·Python 3.11과 로컬 pybind11 2.10.0·DLPack 0.8 소스로 실제 wheel 빌드와 GPU 통합 검증을 완료했다. 공백이 있는 CMake 경로는 빌드 도구가 SKBUILD_CONFIGURE_OPTIONS로 한 번만 전달한다.

현재 PC의 도구 집합을 명시하는 재개 예시는 다음과 같다. 먼저 Visual Studio 개발자 환경에서 MSVC 14.44를 선택하고 실행한다.

```powershell
./build-pynvvideocodec.ps1 `
  -Python ./build/pynvvideocodec-env/Scripts/python.exe `
  -CMakeArgument @(
    '-DCUDAToolkit_ROOT=C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6',
    '-DCMAKE_CUDA_COMPILER=C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6/bin/nvcc.exe',
    '-DCMAKE_CXX_FLAGS=/utf-8 /EHsc',
    '-DCMAKE_CUDA_FLAGS=-Xcompiler=/utf-8'
  )
```

네트워크가 없는 빌드 환경에서는 개발 패키지를 로컬 wheelhouse에서 설치하고, 미리 확보한 pybind11·DLPack 소스 경로를 지정한다.

```powershell
./build-pynvvideocodec.ps1 `
  -Python ./build/pynvvideocodec-env/Scripts/python.exe `
  -Pybind11SourceDirectory D:/BuildDeps/pybind11-2.10.0 `
  -DLPackSourceDirectory D:/BuildDeps/dlpack-0.8
```

추가 CMake 설정은 `-CMakeArgument`로 전달한다. 예를 들어 설치한 CUDA Toolkit을 고정하려면 `'-DCUDAToolkit_ROOT=C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6'`를 사용한다. 설치된 Python과 빌드에 선택한 Python이 일치해야 한다.

`CMAKE_CXX_FLAGS`를 직접 지정할 때는 Windows의 예외 처리 옵션 `/EHsc`를 함께 유지한다. 기존 빌드 디렉터리는 scikit-build의 CMake 캐시를 재사용하므로 컴파일 옵션을 변경할 때는 새 `-WorkDirectory`를 지정한다. 예를 들어 `-WorkDirectory ./build/pynvvideocodec-rebuild`를 사용한다. 위 CUDA 옵션과 로컬 의존성 경로 옵션은 한 번의 명령에서 함께 지정할 수 있다.

## 생성한 배포 파일

2026-10-31에 `dist/pynvvideocodec-2.2.2+pipeworks.1-cp311-cp311-win_amd64.whl`을 생성했다. 크기는 20,502,189바이트이며 SHA-256은 `4ea783158cd2143cfa09ed312f493270ef0a2703a5e06dc78e5d1f90fac2edac`다. 이 해시는 해당 빌드 결과의 값이며, 다른 환경에서 재빌드한 wheel과 바이트 단위로 같음을 보장하지 않는다.

기본 가상환경에 수정 wheel을 설치한 후 관련 회귀 검사 186개가 모두 통과했다. 별도 설치 디렉터리에서도 네이티브 GPU 통합 검사 1개가 통과했다. 드라이버·운영체제·Python이 다른 배포 환경과 실제 RTSP 서버 검증은 별도로 수행한다.

## 설치와 배포

수정 wheel은 기존 PyNvVideoCodec을 대체한다. 운영 환경에 컴파일러를 배포할 필요는 없지만 NVIDIA 드라이버 등 실행 의존성은 필요하다.

```powershell
uv pip install --python .venv/Scripts/python.exe --no-index --find-links dist -r requirements-pynvvideocodec.txt
```

PipeWorks wheel과 수정 PyNvVideoCodec wheel을 같은 wheelhouse 또는 사내 패키지 저장소에 배포한다. 다른 의존성이 준비된 환경에서 다음처럼 정확한 수정 버전을 함께 지정한다.

```powershell
python -m pip install --find-links wheelhouse -r requirements-pynvvideocodec.txt pipe-works
```

기본 `uv.lock`은 공식 wheel을 가리킨다. 수정 환경에서 일반 `uv sync`를 실행하면 공식 버전으로 되돌아갈 수 있다. 동기화가 필요하면 `uv sync --no-install-package pynvvideocodec` 후 위 수정 wheel 설치 명령을 실행한다. 수정본을 기본으로 사용하는 별도 배포 프로젝트에서는 wheel 경로나 사내 인덱스를 소스로 고정하고 잠금 파일도 갱신한다. 원본 라이선스 파일은 wheel과 함께 유지한다.

## 사용과 검증

```python
pipeline.step(NvidiaDecode())
pipeline.step(NvidiaEncode(preserve_timestamps=True))
```

`GetLockedFrameWithPTS()`는 잠긴 GPU 포인터와 해당 프레임의 부호 있는 PTS를 한 번에 반환한다. `NvidiaDecode`는 PTS와 PyAV의 시간 기준을 출력 컨텍스트에 함께 넣는다. 영상 복사와 추론 완료 대기는 추가하지 않는다. 공식 wheel로 실행하면 디코딩의 기존 동작은 유지하지만 `pts=None`이므로 인코더 보존 모드는 해당 입력을 폐기한다.

```powershell
$env:PYTHONPATH = 'src;tests'
.venv/Scripts/python.exe -m unittest test_pynvvideocodec_build test_nvidia_decode test_nvidia_encode
```

수정 wheel과 GPU가 설치된 환경에서 `test_native_patched_locked_pts_survive_decode_and_reach_encoder`가 건너뛰어지지 않고 통과해야 한다. 이 검사는 동일 GPU 주소의 잠긴 프레임과 원본 시각 간격이 인코더까지 유지되는지 확인한다. 실제 RTSP 서버에서 재정렬·재연결 및 출력 재생 상태도 운영 배포 전에 검증한다.
