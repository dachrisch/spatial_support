from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Lock
from time import sleep
from typing import Callable, final, Set, Any, List, Dict

from attr import define, field
from benedict.dicts import benedict
from websocket import WebSocketApp

from chat.entity.messages import ChatMessage
from support.mixin import LoggableMixin


@define
class OnMessageListener(LoggableMixin):
    message_type: str = field()
    callback: Callable[[WebSocketApp, benedict], None] = field()

    def accepts(self, message: benedict):
        return self.message_type in message

    def process(self, socket: WebSocketApp, message: benedict):
        self.debug(f'processing {self.message_type}: {message}')
        self.callback(socket, message)


class ListenerBuilderAware(ABC):
    @abstractmethod
    def on(self, message_type: str) -> ListenerBuilder:
        raise NotImplementedError


@define
class ListenerBuilder(LoggableMixin):
    listener_list: List[OnMessageListener] = field()
    message_type: str = field()

    def call(self, callback=Callable[[WebSocketApp, benedict], None]):
        listener = OnMessageListener(self.message_type, callback)
        self.debug(f'registering {listener}')
        self.listener_list.append(listener)


class BlockingListener(ABC):
    def __init__(self, socket: ListenerBuilderAware, trigger_message: str):
        socket.on(trigger_message).call(self.on_message)
        self.lock = Lock()
        self.lock.acquire()

    @final
    def on_message(self, socket: WebSocketApp, message: benedict):
        if self.lock.locked():
            self.lock.release()
        with self.lock:
            self._on_message(socket, message)

    @abstractmethod
    def _on_message(self, socket: WebSocketApp, message: benedict):
        raise NotImplementedError


class ConnectedListener(BlockingListener):
    def __init__(self, socket: ListenerBuilderAware):
        super(ConnectedListener, self).__init__(socket, 'success.connected')
        self._connection_id = None

    def _on_message(self, socket: WebSocketApp, message: benedict):
        self._connection_id = message['success.connected.connectionId']

    @property
    def connection_id(self):
        with self.lock:
            return self._connection_id


class InitialStateChatListener(BlockingListener, LoggableMixin):
    def __init__(self, socket: ListenerBuilderAware):
        LoggableMixin.__init__(self)
        BlockingListener.__init__(self, socket, 'success.room.response.spatial.state.chat')
        socket.on('success.room.response.spatial.update.chatMessage').call(self._on_new_message)
        self._chats: Dict[str, Set[ChatMessage]] = dict()
        self.listener: Dict[str, Callable[[ChatMessage], Any]] = dict()

    def _on_message(self, socket: ListenerBuilderAware, message: benedict):
        room_id = message['success.room.id']
        room_chats = set()
        self._chats[room_id] = room_chats
        self.debug(f'receiving chats for {room_id}')
        for chat in message['success.room.response.spatial.state.chat']:
            c = benedict(chat)
            if 'state.active.content' in c:
                chat_message = ChatMessage.from_json(c)
                self.debug(chat_message)
                room_chats.add(chat_message)
            else:
                self.debug(f'omitting inactive message [{c}]')

    def _on_new_message(self, socket: ListenerBuilderAware, message: benedict):
        room_id = message['success.room.id']
        chat_message = ChatMessage.from_json(message['success.room.response.spatial.update.chatMessage'])
        self._chats[room_id].add(chat_message)
        self.listener[room_id](chat_message)

    def room_chats(self, room_id: str):
        while room_id not in self._chats:
            sleep(0.1)
        with self.lock:
            return sorted(self._chats[room_id], key=lambda c: c.created)

    def register_on_new_message(self, room_id: str, callback: Callable[[ChatMessage], Any]):
        self.listener[room_id] = callback
