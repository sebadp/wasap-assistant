from app.conversation.manager import ConversationManager
from app.models import ChatMessage


def test_add_and_get_history():
    mgr = ConversationManager(max_messages=5)
    mgr.add_message("123", ChatMessage(role="user", content="hello"))
    mgr.add_message("123", ChatMessage(role="assistant", content="hi"))

    history = mgr.get_history("123")
    assert len(history) == 2
    assert history[0].content == "hello"
    assert history[1].content == "hi"


def test_trimming():
    mgr = ConversationManager(max_messages=3)
    for i in range(5):
        mgr.add_message("123", ChatMessage(role="user", content=f"msg{i}"))

    history = mgr.get_history("123")
    assert len(history) == 3
    assert history[0].content == "msg2"
    assert history[2].content == "msg4"


def test_separate_conversations():
    mgr = ConversationManager()
    mgr.add_message("111", ChatMessage(role="user", content="a"))
    mgr.add_message("222", ChatMessage(role="user", content="b"))

    assert len(mgr.get_history("111")) == 1
    assert len(mgr.get_history("222")) == 1
    assert mgr.get_history("111")[0].content == "a"


def test_clear():
    mgr = ConversationManager()
    mgr.add_message("123", ChatMessage(role="user", content="hello"))
    mgr.clear("123")
    assert mgr.get_history("123") == []


def test_empty_history():
    mgr = ConversationManager()
    assert mgr.get_history("nonexistent") == []


def test_duplicate_detection():
    mgr = ConversationManager()
    assert mgr.is_duplicate("wamid.1") is False
    assert mgr.is_duplicate("wamid.1") is True
    assert mgr.is_duplicate("wamid.2") is False


def test_history_is_a_copy():
    mgr = ConversationManager()
    mgr.add_message("123", ChatMessage(role="user", content="hello"))
    history = mgr.get_history("123")
    history.append(ChatMessage(role="user", content="extra"))
    assert len(mgr.get_history("123")) == 1
