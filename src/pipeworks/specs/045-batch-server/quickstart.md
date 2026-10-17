# 사용 및 검증

```python
pipeline = Pipeline("camera", config=config_path, batch_server="camera-a")
```

검증은 현재 디렉터리에서 프로젝트 가상환경으로 실행한다.

```powershell
& ../../.venv/Scripts/python.exe specs/045-batch-server/verify.py
```

remaining.patch는 저장소 루트에서 git apply로 반영할 수 있는 외부 파일 변경분이다.
현재 세션에서는 외부 파일 쓰기 권한이 없어 적용하지 않는다.
