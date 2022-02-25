from __future__ import annotations

from typing import Dict, Any

from support.mixin import PrintableMixin


class ChatMessage(PrintableMixin):
    def __init__(self, message_json: Dict[str, Any], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._id = message_json['id']
        self.date = message_json['date']
        self.author = message_json['author']['name']
        self.text = message_json['text']
        self.channel = message_json['channel']


class Message(PrintableMixin):
    def __init__(self, message_type: str, message_content: Dict[Any, Any]):
        self.message_content = message_content
        self.message_type = message_type


class JoinRoomMessage(Message):
    def __init__(self, room_id):
        super().__init__('room:join', {'id': room_id})


class GetChatMessagesMessage(Message):
    def __init__(self, room_id):
        super().__init__('chat:get-messages', {'channel': f'R{room_id}'})


class PongMessage(Message):
    def __init__(self):
        super().__init__('pong', {})


class SendChatMessage(Message):
    def __init__(self, channel: str, text: str):
        super().__init__('chat:send-message', {'channel': channel, 'text': text})

    @classmethod
    def create(cls, room_id: str, message: str) -> SendChatMessage:
        return cls(f'R{room_id}', message)
