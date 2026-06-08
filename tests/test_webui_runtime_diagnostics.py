from api.config import STREAMS, STREAMS_LOCK, create_stream_channel
from api.routes import _stream_runtime_diagnostics


def test_stream_channel_exposes_buffer_and_subscriber_counts():
    channel = create_stream_channel()
    channel.put_nowait(("token", {"text": "offline"}))

    snapshot = channel.diagnostic_snapshot()
    assert snapshot["subscriber_count"] == 0
    assert snapshot["offline_buffered_events"] == 1
    assert snapshot["offline_dropped_events"] == 0
    assert snapshot["offline_buffer_max"] >= 1

    subscriber = channel.subscribe()
    try:
        snapshot = channel.diagnostic_snapshot()
        assert snapshot["subscriber_count"] == 1
        assert snapshot["offline_buffered_events"] == 1
        assert subscriber.get_nowait()[0] == "token"
    finally:
        channel.unsubscribe(subscriber)


def test_stream_channel_bounds_offline_buffer_and_replays_tail():
    channel = create_stream_channel(offline_buffer_max=2)
    channel.put_nowait(("token", {"text": "one"}))
    channel.put_nowait(("token", {"text": "two"}))
    channel.put_nowait(("token", {"text": "three"}))

    snapshot = channel.diagnostic_snapshot()
    assert snapshot["offline_buffered_events"] == 2
    assert snapshot["offline_dropped_events"] == 1
    assert snapshot["offline_buffer_max"] == 2

    subscriber = channel.subscribe()
    try:
        assert subscriber.get_nowait() == ("token", {"text": "two"})
        assert subscriber.get_nowait() == ("token", {"text": "three"})
    finally:
        channel.unsubscribe(subscriber)


def test_stream_runtime_diagnostics_summarizes_active_stream_channels():
    channel = create_stream_channel(offline_buffer_max=1)
    channel.put_nowait(("token", {"text": "older"}))
    channel.put_nowait(("token", {"text": "offline"}))
    subscriber = channel.subscribe()
    try:
        with STREAMS_LOCK:
            previous = dict(STREAMS)
            STREAMS.clear()
            STREAMS["stream-one"] = channel
        try:
            payload = _stream_runtime_diagnostics()
        finally:
            with STREAMS_LOCK:
                STREAMS.clear()
                STREAMS.update(previous)

        assert payload["active_streams"] == 1
        assert payload["total_subscribers"] == 1
        assert payload["total_offline_buffered_events"] == 1
        assert payload["total_offline_dropped_events"] == 1
        assert payload["streams"] == [
            {
                "stream_id": "stream-one",
                "subscriber_count": 1,
                "offline_buffered_events": 1,
                "offline_dropped_events": 1,
                "offline_buffer_max": 1,
            }
        ]
    finally:
        channel.unsubscribe(subscriber)
