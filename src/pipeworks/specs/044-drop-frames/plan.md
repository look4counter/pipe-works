# 구현 계획: 프레임 선택 및 폐기

## 요약 및 기술 맥락

기존 Python Step 계약을 구현하는 독립적인 `DropFrames`를 추가한다.
의존성 추가와 저장소는 필요하지 않다. Python 3.11 및 unittest로 검증한다.
입력마다 상수 시간에 순번을 판정하며 프레임을 누적하지 않는다.

## 헌장 확인

저장소 헌장은 미작성 템플릿이므로 추가 규범 검사는 생략한다.
모든 Markdown은 한글로 작성하고 명세 → 명확화 → 계획 → 작업 → 분석 → 구현 → 수렴 순서를 따른다.

## 구조와 설계

- `embedded/drop_frames.py`: 생성자 기본값, configure 검증, enumerate 기반 필터.
- `embedded/__init__.py`: 공개 가져오기 및 `__all__` 등록.
- `specs/044-drop-frames/test_drop_frames.py`: 공개 계약과 설정, 입력 선택, 재사용 검증.
- `specs/044-drop-frames/quickstart.md`: 사용 및 검증 안내.

기존 테스트·명세 디렉터리는 허용된 쓰기 범위 밖이므로 새 산출물은 `src/pipeworks/specs/044-drop-frames`에 보관한다.
저장소 `.specify/feature.json`은 쓰기 범위 밖이므로 수정하지 않는다. 경로를 명시하여 수동으로 각 단계를 수행한다.

## 검증 및 완료

새 자동 검증과 기존 EveryNFrames·설정 회귀 검증을 실행한다.
분석에서 모든 요구사항과 작업의 대응을 확인하고, 구현 후 수렴 검토에서 누락 여부를 확인한다.
