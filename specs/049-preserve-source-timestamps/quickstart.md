# 검증 안내

수정 wheel을 먼저 설치하고 `NvidiaEncode(preserve_timestamps=True)` 또는 YAML의 NvidiaEncode 섹션에 `preserve_timestamps: true`를 지정한다. NvidiaDecode는 수정 wheel의 잠금 API로 얻은 pts와 PyAV time_base를 전달한다. 공식 wheel에서는 원본 PTS가 없어 보존 모드 입력이 폐기된다.

`.venv/Scripts/python.exe -m unittest discover -s tests -p test_nvidia_encode.py`로 원본 시간·지연·복구·누락과 기본 모드를 검증한다. test_step_config_defaults.py와 test_rtsp_publish.py도 검증한다.
