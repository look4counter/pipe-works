# 서드파티 고지

이 문서는 Pipe Works 1.0.0의 현재 의존성 목록과 라이선스 검토 대상을 기록합니다. 실제 배포 파일에 포함된 항목과 고지 의무는 최종 wheelhouse·번들 ZIP을 기준으로 다시 확인해야 합니다.

## 기준

- 기준 파일: `pyproject.toml`, `uv.lock`, `requirements-py311-win-amd64-cuda121.txt`
- 대상 환경: CPython 3.11.9 / Windows x64 / CUDA 12.1
- 아래 내용은 배포 검토용 요약이며 법률 자문이 아닙니다.

## 직접 의존성

| 패키지 | 버전 | 라이선스·검토 사항 |
|---|---:|---|
| av | 18.1.0 | BSD 계열 및 번들 FFmpeg 고지 검토; PyAV 배포 조건 확인 |
| PyYAML | 6.0.3 | MIT |
| PyNvVideoCodec | 2.2.2 | NVIDIA 배포 조건 및 재배포 권한 확인 |
| torch | 2.2.1+cu121 | BSD-3-Clause 및 CUDA 조건 확인 |
| torchvision | 0.17.1+cu121 | BSD-3-Clause |
| numpy | 1.26.4 | BSD-3-Clause |
| ultralytics | 8.4.146 | AGPL-3.0 또는 별도 상용 라이선스 조건 검토 필수 |
| tensorrt | 10.10.0.31 | NVIDIA TensorRT 라이선스 및 재배포 조건 확인 |
| onnx | 1.18.0 | Apache-2.0 |
| onnxslim | 0.1.82 | 배포본의 LICENSE 및 고지 파일 확인 |
| cloudpickle | 3.1.2 | BSD-3-Clause |
| watchdog | 6.0.0 | Apache-2.0 |

## 주요 전이 의존성

| 패키지 | 버전 | 라이선스·검토 사항 |
|---|---:|---|
| matplotlib | 3.11.2 | Matplotlib 라이선스 및 포함 고지 확인 |
| opencv-python | 4.11.0.86 | Apache-2.0 및 OpenCV 고지 확인 |
| pillow | 12.3.0 | HPND 계열 및 번들 라이브러리 고지 확인 |
| requests | 2.34.2 | Apache-2.0 |
| protobuf | 7.36.2 | BSD-3-Clause |
| psutil | 7.2.2 | BSD-3-Clause |
| polars | 1.44.2 | MIT |
| packaging | 26.3 | Apache-2.0 또는 BSD-2-Clause 조건 확인 |
| typing-extensions | 4.16.0 | PSF-2.0 |

## 배포 전 확인 사항

- 최종 wheelhouse에 실제 포함된 파일과 버전이 `uv.lock` 및 핀 파일과 일치하는지 확인합니다.
- NVIDIA, CUDA, TensorRT, PyNvVideoCodec 구성요소의 사내 재배포 조건을 확인합니다.
- Ultralytics의 AGPL-3.0 또는 상용 라이선스 적용 조건을 확인합니다.
- 각 wheel에 포함된 LICENSE·NOTICE 파일이 있으면 번들에 함께 보존합니다.
- 회사명이나 공개 배포 정보를 이 문서에 추가하지 않습니다.
