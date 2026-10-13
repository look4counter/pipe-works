# 실행 모델

새로운 데이터 형식은 없다. Pipeline.steps는 루트 단계 목록이고 YoloInference.batch는 공유 실행 여부다. Hotswap.wrapped_step, TapSkipIfBusy.step, CudaAsync._hot_steps 및 EveryNFrames._hot_steps가 실행 단계 트리를 구성한다. 방문 집합은 객체 식별자로 순환과 중복을 방지한다.
