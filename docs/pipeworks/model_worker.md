# model_worker: 모델 경로와 작업자 재사용

구현: src/pipeworks/model_worker.py. get_model_worker(model_path, workers, paths, lock, create)는 프로세스 내 캐시에서 모델 작업자를 찾거나 create(canonical_path)로 생성합니다. 일반 앱은 직접 캐시를 만들 필요가 없습니다.

workers는 정규화 절대경로 → 작업자, paths는 (입력 Path, 상대경로일 때 현재 작업 디렉터리) → 정규화 경로 사전입니다. lock 아래에서 별칭 조회·resolve·파일 검사·작업자 생성을 수행합니다. 작업자가 없고 실제 모델 파일도 없으면 FileNotFoundError입니다.

이미 연결된 별칭과 작업자가 있으면 resolve와 is_file을 반복하지 않습니다. 같은 정규화 경로의 다른 별칭은 같은 작업자를 공유합니다. 기존 작업자는 모델 파일이 삭제·교체되어도 즉시 폐기되지 않습니다. 심볼릭 링크 변경도 기존 별칭을 자동 갱신하지 않습니다. 같은 상대경로 문자열은 작업 디렉터리가 다르면 별칭을 달리 취급합니다.

생성 콜백의 오류는 전달되며 이 함수에 파일 변경 감시나 공개 캐시 무효화 기능은 없습니다. [공유 추론](local_yolo_inference.md)은 backend별로 별도 캐시를 유지합니다. 배포 앱은 절대 모델 경로를 넘기고 모델 교체 시 실행 프로세스를 재시작합니다.
