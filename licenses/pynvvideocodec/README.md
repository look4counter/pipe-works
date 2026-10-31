# 수정 PyNvVideoCodec 배포본의 라이선스와 제3자 고지

대상 파일은 `pynvvideocodec-2.2.2+pipeworks.1-cp311-cp311-win_amd64.whl`입니다. Windows x64·Python 3.11용으로 빌드한 수정본이며, NVIDIA 공식 배포본과 구분하기 위해 `+pipeworks.1` 버전을 사용합니다.

## 라이선스 표기

**PyNvVideoCodec 본체와 이 배포본의 추가 바인딩은 MIT 라이선스로 배포합니다.** NVIDIA의 원저작권 표시와 MIT 라이선스 원문을 유지합니다. 추가된 기능은 잠긴 GPU 버퍼와 해당 프레임의 PTS를 함께 반환하는 `GetLockedFrameWithPTS()`이며, 기존 공개 메서드는 유지합니다. 이 수정본은 NVIDIA의 공식 릴리스가 아닙니다.

포함되거나 빌드에 사용된 구성요소에는 다음 조건이 각각 적용됩니다.

| 구성요소 | 확인한 버전과 범위 | 라이선스·고지 |
| --- | --- | --- |
| PyNvVideoCodec | 2.2.2 기반 수정 바인딩 | [MIT 원문](NVIDIA-MIT.txt), [원본 제3자 고지](NVIDIA-NOTICES.txt) |
| NVIDIA Video Codec SDK 유틸리티·헤더 | 소스 배포본에 포함된 코드 | [원저작권·MIT 고지](NVIDIA-VideoCodecSDK-MIT.txt) |
| FFmpeg | 번들 `avformat-62.dll`, `avutil-60.dll` 및 avformat에 포함된 avcodec 코드 | [LGPL 2.1 원문](FFmpeg-LGPL-2.1.txt) 또는 이후 버전. [FFmpeg 라이선스 설명](FFmpeg-LICENSE.txt)도 참고 |
| pybind11 | 2.10.0, 네이티브 Python 바인딩 빌드 | [BSD 3-Clause 원문](pybind11-BSD-3-Clause.txt) |
| DLPack | 0.8, 텐서 교환 인터페이스 | [Apache License 2.0 원문](DLPack-Apache-2.0.txt) |

FFmpeg DLL의 라이선스 조회 함수는 두 파일 모두 `LGPL version 2.1 or later`를 반환했습니다. NVIDIA 원본 `NOTICES.txt`에는 LGPL 3.0 전문이 포함되어 있어 원문을 그대로 보존했으며, [LGPL 3.0](FFmpeg-LGPL-3.0.txt)과 해당 문서가 참조하는 [GPL 3.0](FFmpeg-GPL-3.0.txt)도 함께 제공합니다. 구성요소별 라이선스를 MIT로 대체하지 않습니다.

CUDA Toolkit과 NVIDIA 드라이버 등 별도 설치 구성요소는 해당 배포자의 약관을 따릅니다. 이번 라이선스 묶음은 이들 설치 파일을 재배포하지 않습니다.

## FFmpeg 소스와 빌드 정보

라이선스·소스 묶음 `pynvvideocodec-2.2.2+pipeworks.1-licenses.zip`에는 NVIDIA 소스 배포본이 함께 제공한 `sources/ffmpeg-8.1.2.tar.xz`를 포함합니다. 번들 FFmpeg DLL은 NVIDIA 제공 파일을 수정하지 않고 wheel에 포함했습니다. wheel의 DLL과 원본 소스 배포 디렉터리의 DLL이 바이트 단위로 일치함을 확인했습니다.

[FFmpeg 빌드 안내](FFmpeg-BUILD.txt)에는 NVIDIA가 제공한 구성 옵션과 DLL 생성 방식이 있습니다. [식별 정보](manifest.json)에 wheel, DLL과 소스 압축본의 SHA-256을 기록했습니다. FFmpeg DLL 자체를 소스에서 다시 빌드하여 재현성을 검증한 것은 아닙니다.

FFmpeg의 재배포에서는 저작권·라이선스 고지와 대응 소스 제공, 라이브러리 교체·재링크 등 적용되는 LGPL 조건을 함께 충족해야 합니다. GitHub Release에는 wheel과 라이선스·소스 묶음을 같은 릴리스의 다운로드 자산으로 제공하고 아래 고지에 해당 자산으로 가는 링크를 연결합니다. [FFmpeg 공식 배포 안내](https://ffmpeg.org/legal.html)를 참고합니다.

## GitHub Release에 사용할 고지

다음 문구와 함께 wheel 및 `pynvvideocodec-2.2.2+pipeworks.1-licenses.zip`을 첨부합니다.

> 이 파일은 NVIDIA PyNvVideoCodec 2.2.2에 잠긴 GPU 버퍼와 PTS를 함께 반환하는 바인딩을 추가한 비공식 수정본입니다. PyNvVideoCodec 본체와 추가 바인딩은 MIT 라이선스를 따릅니다. 번들 FFmpeg에는 LGPL 2.1 또는 이후 버전이, pybind11에는 BSD 3-Clause가, DLPack에는 Apache License 2.0이 적용됩니다. 원저작권 고지, 라이선스 원문 및 번들 FFmpeg에 대해 NVIDIA가 제공한 소스는 함께 첨부한 라이선스·소스 ZIP에 있습니다. 수정 패치와 빌드 방법은 저장소에 공개합니다.

원저작권은 각 구성요소의 라이선스 파일에 명시된 저작권자에게 있습니다. 라이선스별 보증 부인 조항이 적용됩니다. 이 한국어 설명은 각 라이선스 원문을 대체하지 않습니다.

## 식별 정보

- wheel SHA-256: `4ea783158cd2143cfa09ed312f493270ef0a2703a5e06dc78e5d1f90fac2edac`
- FFmpeg 소스 SHA-256: `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c`
- [최소 수정 패치](../../tools/patches/pynvvideocodec-2.2.2-locked-frame-pts.patch)
- [빌드·설치 안내](../../docs/pynvvideocodec-build.md)
- [공식 PyNvVideoCodec 소스 배포처](https://catalog.ngc.nvidia.com/orgs/nvidia/-/resources/pynvvideocodec/2.2.2/file-browser)
