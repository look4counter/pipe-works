from pipeworks import BatchCollector, BatchPolicy, DropPolicy, Frame, FrameQueue


def test_frame_queue_drop_oldest_keeps_freshest_frames() -> None:
    queue = FrameQueue(max_frames=2, drop_policy=DropPolicy.DROP_OLDEST)

    assert queue.put(Frame("cam01", sequence=1)) is True
    assert queue.put(Frame("cam01", sequence=2)) is True
    assert queue.put(Frame("cam01", sequence=3)) is True

    assert queue.metrics.depth == 2
    assert queue.metrics.dropped_count == 1
    assert queue.get().sequence == 2
    assert queue.get().sequence == 3


def test_frame_queue_drop_newest_rejects_incoming_frame() -> None:
    queue = FrameQueue(max_frames=2, drop_policy=DropPolicy.DROP_NEWEST)

    assert queue.put(Frame("cam01", sequence=1)) is True
    assert queue.put(Frame("cam01", sequence=2)) is True
    assert queue.put(Frame("cam01", sequence=3)) is False

    assert queue.metrics.depth == 2
    assert queue.metrics.dropped_count == 1
    assert queue.get().sequence == 1
    assert queue.get().sequence == 2


def test_frame_queue_block_refuses_immediate_insert_when_full() -> None:
    queue = FrameQueue(max_frames=1, drop_policy=DropPolicy.BLOCK)

    assert queue.put(Frame("cam01", sequence=1)) is True
    assert queue.put(Frame("cam01", sequence=2)) is False

    assert queue.metrics.depth == 1
    assert queue.metrics.dropped_count == 0
    assert queue.get().sequence == 1


def test_batch_collector_uses_latest_frame_per_stream_and_preserves_identity() -> None:
    cam01 = FrameQueue(max_frames=4)
    cam02 = FrameQueue(max_frames=4)
    cam03 = FrameQueue(max_frames=4)
    cam01.put(Frame("cam01", sequence=1))
    cam01.put(Frame("cam01", sequence=2))
    cam02.put(Frame("cam02", sequence=7))
    cam03.put(Frame("cam03", sequence=4))

    collector = BatchCollector(
        {"cam03": cam03, "cam01": cam01, "cam02": cam02},
        BatchPolicy(max_batch_size=2, max_wait_ms=0),
    )

    contexts = collector.collect()

    assert [context.stream_id for context in contexts] == ["cam01", "cam02"]
    assert [context.frame.sequence for context in contexts] == [2, 7]
