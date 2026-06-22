from api import models


def test_session_compact_uses_metadata_without_scanning_full_history(monkeypatch):
    messages = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": str(index), "timestamp": float(index)}
        for index in range(1000)
    ]
    session = models.Session(
        messages=messages,
        last_message_at=999.0,
        message_count=len(messages),
        user_message_count=500,
    )
    timestamp_calls = 0
    role_calls = 0
    original_message_timestamp = models._message_timestamp
    original_message_role = models._message_role

    def counted_message_timestamp(message):
        nonlocal timestamp_calls
        timestamp_calls += 1
        return original_message_timestamp(message)

    def counted_message_role(message):
        nonlocal role_calls
        role_calls += 1
        return original_message_role(message)

    monkeypatch.setattr(models, "_message_timestamp", counted_message_timestamp)
    monkeypatch.setattr(models, "_message_role", counted_message_role)

    compact = session.compact()

    assert compact["last_message_at"] == 999.0
    assert compact["message_count"] == 1000
    assert compact["user_message_count"] == 500
    assert timestamp_calls <= 32
    assert role_calls == 0


def test_session_compact_caches_user_message_count_for_loaded_sessions(monkeypatch):
    messages = [
        {"role": "user" if index % 3 == 0 else "assistant", "content": str(index), "timestamp": float(index)}
        for index in range(900)
    ]
    session = models.Session(messages=messages, last_message_at=899.0)
    role_calls = 0
    original_message_role = models._message_role

    def counted_message_role(message):
        nonlocal role_calls
        role_calls += 1
        return original_message_role(message)

    monkeypatch.setattr(models, "_message_role", counted_message_role)

    first = session.compact()
    second = session.compact()

    assert first["user_message_count"] == 300
    assert second["user_message_count"] == 300
    assert role_calls == 900
