from app.models import ChatMessage

_SEEN_IDS_MAX = 1000


class ConversationManager:
    def __init__(self, max_messages: int = 20):
        self._max_messages = max_messages
        self._histories: dict[str, list[ChatMessage]] = {}
        self._seen_ids: set[str] = set()

    def is_duplicate(self, wa_message_id: str) -> bool:
        if wa_message_id in self._seen_ids:
            return True
        self._seen_ids.add(wa_message_id)
        if len(self._seen_ids) > _SEEN_IDS_MAX:
            # Evict oldest entries (set is unordered, but good enough)
            to_remove = len(self._seen_ids) - _SEEN_IDS_MAX
            it = iter(self._seen_ids)
            for _ in range(to_remove):
                self._seen_ids.discard(next(it))
        return False

    def get_history(self, phone_number: str) -> list[ChatMessage]:
        return list(self._histories.get(phone_number, []))

    def add_message(self, phone_number: str, message: ChatMessage) -> None:
        history = self._histories.setdefault(phone_number, [])
        history.append(message)
        if len(history) > self._max_messages:
            self._histories[phone_number] = history[-self._max_messages :]

    def clear(self, phone_number: str) -> None:
        self._histories.pop(phone_number, None)
