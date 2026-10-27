# Pipe Works 1.0.0

**릴리즈 기준일**: 2026-10-27
**기준 소스**: 현재 main 소스 확정본
**배포 유형**: 사내·비공개 배포

## 개요

Pipe Works 최초 1.0.0 릴리즈입니다. 현재 main 소스의 RTSP, NVIDIA 디코드·인코드, YOLO, TensorRT·TorchScript·Ultralytics 백엔드와 Step 조합 기능을 포함합니다.

## 포함 주요 기능

- 선언형 Python 파이프라인
- RTSP 입력·출력·재연결
- NVIDIA 디코드·인코드
- YOLO 및 PatchCore 백엔드
- CUDA 비동기·배치 처리
- 핫 스왑 및 설정 감시
- 프로세스당 1회 실행을 위한 RunOnce Step
- Python 3.11.9 / Windows x64 / CUDA 12.1 의존성 핀

## 지원 기준

- Python 3.11.9
- Windows x64
- CUDA 12.1
- torch 2.2.1+cu121
- torchvision 0.17.1+cu121
- TensorRT 10.10.0.31
- 의존성 기준 파일: `uv.lock`, `requirements-py311-win-amd64-cuda121.txt`

## 설치 기준

```powershell
python -m pip install -r requirements-py311-win-amd64-cuda121.txt
python -m pip install pipe_works-1.0.0-py3-none-any.whl
```

wheel, wheelhouse, 실행 번들 ZIP, 체크섬 목록은 별도 배포 산출물 생성 단계에서 구성합니다. 이번 변경은 현재 소스와 릴리즈 기준 문서·의존성 파일을 확정합니다.

## 알려진 제한

- GPU, NVIDIA 드라이버, CUDA, TensorRT 환경이 필요합니다.
- 지원 기준은 Windows x64입니다.
- GPU·PyNvVideoCodec·TensorRT가 없는 환경에서는 일부 테스트와 기능을 실행할 수 없습니다.
- 서드파티 라이선스 조건은 `THIRD_PARTY_NOTICES.md`를 확인해야 합니다.
- 문서, 예제, 모델 파일은 wheel에 자동 포함되지 않습니다.

## 독점 배포 고지

본 소프트웨어는 사내·비공개 배포용 독점 소프트웨어입니다. 상세 조건은 `LICENSE`를 따릅니다.
