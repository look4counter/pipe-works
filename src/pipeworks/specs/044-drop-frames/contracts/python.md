# 공개 계약

`from pipeworks.embedded import DropFrames`

`DropFrames(*, keep_every: int = 1)`은 Step 인스턴스를 만든다.
`configure(SimpleNamespace(keep_every=2))`로 설정을 덮어쓸 수 있다.
빈 설정은 생성자 기본값을 복원한다.
`process(inputs)`는 순번 0, N, 2N만 출력한다. 시간과 FPS는 바꾸지 않는다.
