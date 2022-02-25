from __future__ import annotations

from abc import abstractmethod, ABC
from threading import Lock
from typing import Callable, Dict, Any, Set, List

from attr import define, field

from chat.messages import PongMessage, Message, ChatMessage
from support.mixin import LoggableMixin


class Registrable:
    @abstractmethod
    def on_register_listener(self, listener: Set[Listener]) -> None:
        raise NotImplementedError

    @abstractmethod
    def on_register_sender(self, send_method: Callable) -> None:
        raise NotImplementedError


class Listener:
    def __init__(self):
        self._lock = Lock()
        self._lock.acquire()

    @abstractmethod
    def accepts(self, _type: str) -> bool:
        raise NotImplementedError

    def process(self, message_json: Dict[Any, Any]) -> None:
        self._process(message_json)
        if self._lock.locked():
            self._lock.release()

    @abstractmethod
    def _process(self, message_json: Dict[Any, Any]):
        raise NotImplementedError


@define(hash=True)
class SingleMessageListener(Listener, ABC):
    message = field()

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def accepts(self, _type: str) -> bool:
        return _type == self.message


class AvailableRoomsLister(SingleMessageListener, LoggableMixin):
    def __init__(self):
        LoggableMixin.__init__(self)
        SingleMessageListener.__init__(self, 'rooms:listed')
        self._room_names_id_map = {}

    def _process(self, message_json: Dict[Any, Any]) -> None:
        _type, *rooms = message_json
        for room in rooms[0]['rooms']:
            self._room_names_id_map[room['name']] = room['id']

        self.debug(f'got new rooms: {self._room_names_id_map}')

    def get_room_id(self, room_name: str):
        with self._lock:
            return self._room_names_id_map[room_name]


@define(hash=True)
class JoinRoomListener(SingleMessageListener, LoggableMixin):
    room_id: field()

    def __init__(self, room_name, room_id):
        SingleMessageListener.__init__(self, 'room:join')
        LoggableMixin.__init__(self)
        self.room_id = room_id
        self.room_name = room_name
        self._joined_room = False

    def _process(self, message_content: Dict[Any, Any]):
        _type, *room, message_id = message_content
        joined_room_id = room[0]['roomId']
        self._joined_room = self.room_id == joined_room_id
        if self._joined_room:
            self.info(f'joined room [{self.room_name}:({self.room_id})]')
        else:
            self.debug(f'listening for [{self.room_id}], but joined room was [{joined_room_id}]')


class KeepAlive(Registrable, SingleMessageListener):

    def _process(self, message_json: Dict[Any, Any]):
        self.send_method(PongMessage())

    def __init__(self):
        super().__init__('ping')
        self.send_method: Callable[[Message], Any] = lambda m: m

    def on_register_listener(self, listener: Set[Listener]) -> None:
        listener.add(self)

    def on_register_sender(self, send_method: Callable[[Message], Any]) -> None:
        self.send_method = send_method


@define(hash=True)
class RoomChatMessageListener(SingleMessageListener, LoggableMixin):
    room_id: field()

    def __init__(self, room_id):
        SingleMessageListener.__init__(self, 'chat:get-messages')
        LoggableMixin.__init__(self)
        self.room_id = room_id
        self.messages = set()

    def _process(self, message_json: Dict[Any, Any]):
        _type, *messages, message_id = message_json
        for message in self.channel_messages(messages[0]['messages']):
            self.messages.add(ChatMessage(message))
        self.debug(f'existing chats: {self.messages}')

    def channel_messages(self, ms: List[Dict[str, Any]]):
        channel_messages = list(filter(lambda message: message['channel'] == self.channel, ms))
        self.debug(f'obtained existing chats for [{self.room_id}]: {channel_messages}')
        return channel_messages

    def get_messages(self):
        with self._lock:
            return self.messages

    @property
    def channel(self):
        return f'R{self.room_id}'


@define(hash=True)
class RoomChatNewMessageListener(SingleMessageListener):
    room_id = field()

    def no_callback(self, message: ChatMessage) -> None:
        pass

    def __init__(self, room_id: str):
        super().__init__('chat:message-added')
        self.callback: Callable[[ChatMessage], Any] = self.no_callback
        self.room_id = room_id
        self.messages = set()

    def with_callback(self, callback: Callable[[ChatMessage], Any] = None):
        self.callback = callback

    def _process(self, message_json: Dict[Any, Any]):
        _type, *messages = message_json
        chat_message = ChatMessage(messages[0]['message'])
        self.messages.add(chat_message)
        self.callback(chat_message)

    def get_new_messages(self):
        messages_copy = self.messages.copy()
        self.messages.clear()
        return messages_copy

    def with_wait_for_new(self):
        return self._lock.acquire()


@define(hash=True)
class OnRoomsCallbackListener(SingleMessageListener, LoggableMixin, Registrable):
    def on_register_listener(self, listener: Set[Listener]) -> None:
        listener.add(self)

    def on_register_sender(self, send_method: Callable) -> None:
        pass

    def __init__(self, callback: Callable[[Dict[Any, Any]], None]):
        LoggableMixin.__init__(self)
        Registrable.__init__(self)
        SingleMessageListener.__init__(self, 'rooms:listed')
        self.callback = callback

    def _process(self, message_json: Dict[Any, Any]) -> None:
        _type, *rooms = message_json
        self.debug(f'calling [{self.callback}] with {rooms[0]["rooms"]}')
        self.callback(rooms[0]['rooms'])
