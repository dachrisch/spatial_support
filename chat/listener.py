from __future__ import annotations

from abc import abstractmethod, ABC
from threading import Lock
from typing import List, Callable, Dict, Any, Iterable

from chat.messages import PongMessage, Message
from support.mixin import LoggableMixin


class Registrable:
    @abstractmethod
    def on_register_listener(self, listener: List[Listener]) -> None:
        raise NotImplementedError

    @abstractmethod
    def on_register_sender(self, send_method: Callable) -> None:
        raise NotImplementedError


class Listener:
    def __init__(self):
        self._lock = Lock()
        self._lock.acquire()

    @abstractmethod
    def accepts(self, _type: str):
        raise NotImplementedError

    def process(self, message_json: Dict[Any, Any]):
        self._process(message_json)
        if self._lock.locked():
            self._lock.release()

    @abstractmethod
    def _process(self, message_json: Dict[Any, Any]):
        raise NotImplementedError


class SingleMessageListener(Listener, ABC):
    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def accepts(self, _type: str):
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


class MultiMessageListener(Listener):

    def __init__(self, listeners: Iterable[SingleMessageListener]):
        super().__init__()
        self._listeners = listeners

    def accepts(self, _type: str):
        return any(self._accepting_listener(_type))

    def _process(self, message_json: Dict[Any, Any]):
        _type, *message_content = message_json
        [l.process(message_content) for l in self._listeners]

    def _accepting_listener(self, _type: str):
        return filter(lambda l: l.accepts(_type), self._listeners)


class JoinRoomListener(SingleMessageListener, LoggableMixin):
    def __init__(self, room_name, room_id):
        SingleMessageListener.__init__(self, 'room:join')
        LoggableMixin.__init__(self)
        self.room_id = room_id
        self.room_name = room_name

    def _process(self, message_content: Dict[Any, Any]):
        _type, *room, message_id = message_content
        assert self.room_id == room[0]['roomId']
        self.info(f'joined room [{self.room_name}:({self.room_id})]')


class KeepAlive(Registrable, SingleMessageListener):

    def _process(self, message_json: Dict[Any, Any]):
        self.send_method(PongMessage())

    def __init__(self):
        super().__init__('ping')
        self.send_method: Callable[[Message], Any] = lambda m: m

    def on_register_listener(self, listener: List[Listener]) -> None:
        listener.append(self)

    def on_register_sender(self, send_method: Callable[[Message], Any]) -> None:
        self.send_method = send_method