# 공통 HTML 문서 데이터 관리

설정·Input·Output 설명을 변경하려면 docs/reference/reference.js의 STEP_REFERENCE를 수정한다. 모든 HTML은 같은 스크립트를 사용한다. docs/reference/index.html을 직접 열어 목록과 상세 문서를 확인한다.

검증 결과: 17개 HTML의 스크립트·CSS 연결과 16개 Step의 실제 렌더링을 확인했다. 기존 설정·입출력 표 및 빈 영역 설명이 모두 보존됐고 상세 링크가 유효했다. header와 note 문단은 추가하지 않았다.

설정 및 생성자 파라미터는 각 클래스명.html의 section.parameters에서 편집한다. Input·Output은 reference.js에서 편집한다. 16개 상세 페이지의 표 내용 보존과 렌더링 시 기존 위치 배치를 검증했다.

Input 변수명을 클릭하면 생성 Step의 Output 행으로 이동한다. 중첩 속성은 상위 변수로 연결하며 검출 결과는 YOLO·TensorRT 경로를 함께 표시한다. 전체 생성 링크 39개의 대상 파일·Output 앵커를 검증했다.

변수 관리: reference.js의 VARIABLES에서 변수명·설명 변형·생성 위치를 편집한다. STEP_REFERENCE는 변수 ID와 설명 ID를 참조한다. 17개 페이지의 변경 전후 렌더링 텍스트·링크·앵커가 모두 동일함을 검증했다.

변수마다 description 하나만 관리한다. Step별 설명 ID는 제거했다. 모든 상세 페이지에서 공통 설명이 표시되고 입력 링크 39개의 Output 앵커가 유지됨을 확인했다.

VARIABLES는 실제 변수명을 키로 사용한다. 예: VARIABLES.frame, VARIABLES["video_stream.codec_context.width"]. Step의 variable과 생성 위치 참조에도 같은 변수명을 쓴다. 번호 재지정은 필요 없다. 누락된 정의는 설명 누락 표시를 제공하고 유효하지 않은 생성 링크는 제외한다. 전체 페이지의 기존 렌더링 동일성과 변수 21개 각각의 삭제 시 오류 없는 렌더링을 검증했다.
