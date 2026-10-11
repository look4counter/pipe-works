# 실행 확인

1. `examples/01_single_stream_rtsp_style.py`의 `TapSkipIfBusy(PostProcess())` 구성을 확인한다.
2. 지연을 이벤트로 제어하는 간단한 Step을 `TapSkipIfBusy`로 감싸 여러 컨텍스트를 연속 전달한다.
3. 주 스트림 출력이 지연 없이 모두 전달되고, 작업 중 입력은 감싼 Step에 도달하지 않는지 확인한다.
4. 작업 완료 후 새 컨텍스트가 감싼 Step에 도달하는지 확인한다.
# TapSkipIfBusy 이름 변경 검증

2026-10-09에 전체 160개 테스트를 실행했다. 이름 변경과 관련된 설정 갱신·핫스왑·중앙 실행 출력 전달 테스트는 통과했다. 건너뜀은 3개이며, 기존 BoxOverlay 예제 검사에서 `YoloDetectBatch`를 찾지 못하는 오류 1개가 남았다. 이번 이름 변경으로 새로 발생한 오류는 없다.

FR-010·011, SC-006·007 및 기존 동작 요구사항을 코드·예제·문서·테스트와 대조했다. 공개 import와 설정 섹션은 `TapSkipIfBusy`으로 통일되었으며 최종 출력 분류인 Sink와 테스트용 사용자 Sink 클래스는 유지한다. 수렴 점검에서 추가 작업은 발견하지 않았다.

## TapSkipIfBusy 이름 변경 검증

모듈은 src/pipeworks/embedded/tap_skip_if_busy.py이며 공개 클래스와 설정 섹션은 TapSkipIfBusy다. HTML 문서는 docs/reference/TapSkipIfBusy.html, Markdown 설명은 docs/pipeworks/embedded/tap_skip_if_busy.md로 이동했다. 기존 입력·단일 작업자·건너뛰기 동작은 유지한다. 비동기·보고·설정·핫스왑·중앙 실행 132개와 디코딩 22개 회귀 테스트가 모두 통과했다. 저장소의 이전 모듈·공개 클래스 참조가 없고 git diff --check가 통과했다.
