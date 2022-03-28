from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Lock
from time import sleep
from typing import Callable, final, Set, Any, List, Dict, Tuple

from attr import define, field
from benedict.dicts import benedict
from websocket import WebSocketApp

from chat.entity.messages import ChatMessage
from support.mixin import LoggableMixin


class ListenerBuilderAware(ABC):
    @abstractmethod
    def on(self, message_type: str) -> ListenerBuilder:
        raise NotImplementedError


@define
class OnMessageListener(LoggableMixin):
    message_type: str = field()
    callback: Callable[[WebSocketApp, benedict], None] = field()

    def accepts(self, message: benedict):
        return self.message_type in message

    def process(self, socket: WebSocketApp, message: benedict):
        self.debug(f'processing {self.message_type}: {message}')
        self.callback(socket, message)


@define
class ListenerBuilder(LoggableMixin):
    listener_list: List[OnMessageListener] = field()
    message_type: str = field()

    def call(self, callback=Callable[[WebSocketApp, benedict], None]):
        listener = OnMessageListener(self.message_type, callback)
        self.debug(f'registering {listener}')
        self.listener_list.append(listener)


class BlockingListener(ABC):
    def __init__(self, socket: ListenerBuilderAware, trigger_message: str, lock=Lock()):
        self.lock = lock
        if not self.lock.locked():
            self.lock.acquire()
        socket.on(trigger_message).call(self.on_message)

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


class ChatListener(LoggableMixin):
    def __init__(self, socket: ListenerBuilderAware):
        LoggableMixin.__init__(self)
        self.chats: Dict[str, Set[ChatMessage]] = dict()
        self.lock = Lock()
        self.new_message_chat_listener = NewMessageChatListener(socket, self.chats)
        self.initial_state_chat_listener = InitialStateChatListener(socket, self.chats)

    def register_on_new_message(self, room_id: str, callback: Callable[[ChatMessage], Any]):
        self.new_message_chat_listener.listener[room_id] = callback

    def room_chats(self, room_id: str):
        while room_id not in self.chats:
            sleep(0.1)
        with self.lock:
            return sorted(self.chats[room_id], key=lambda c: c.created)


def is_active_message(chat: benedict):
    return 'state.active.content' in chat


class NewMessageChatListener(LoggableMixin):
    def __init__(self, socket: ListenerBuilderAware, chats: Dict[str, Set[ChatMessage]]):
        LoggableMixin.__init__(self)
        self.chats = chats
        self.listener: Dict[str, Callable[[ChatMessage], Any]] = dict()
        socket.on('success.room.response.spatial.update.chatMessage').call(self.on_spatial_message)
        socket.on('success.room.response.stage.update.chatMessage').call(self.on_stage_message)

    def on_spatial_message(self, socket: ListenerBuilderAware, message: benedict):
        return self.update_chats(message, 'success.room.response.spatial.update.chatMessage')

    def on_stage_message(self, socket: ListenerBuilderAware, message: benedict):
        return self.update_chats(message, 'success.room.response.stage.update.chatMessage')

    def update_chats(self, message: benedict, chats_key: str):
        room_id = message['success.room.id']
        if is_active_message(message[chats_key]):
            chat_message = ChatMessage.from_json(message[chats_key])
            self.chats[room_id].add(chat_message)
            self.listener[room_id](chat_message)
        else:
            self.debug(f'omitting inactive message [{message[chats_key]}]')


class InitialStateChatListener(LoggableMixin):
    def __init__(self, socket: ListenerBuilderAware, chats: Dict[str, Set[ChatMessage]]):
        LoggableMixin.__init__(self)
        self.chats = chats
        socket.on('success.room.response.spatial.state.chat', ).call(self.on_spatial_message)
        socket.on('success.room.response.stage.state.chat', ).call(self.on_stage_message)

    def on_spatial_message(self, socket: ListenerBuilderAware, message: benedict):
        room_id, chats = self.extract_chats(message, 'success.room.response.spatial.state.chat')
        self.chats[room_id] = chats

    def on_stage_message(self, socket: ListenerBuilderAware, message: benedict):
        room_id, chats = self.extract_chats(message, 'success.room.response.stage.state.chat')
        self.chats[room_id] = chats

    def extract_chats(self, message: benedict, chats_key: str) -> Tuple[Any, Set[Any]]:
        room_id = message['success.room.id']
        self.debug(f'receiving chats for {room_id}')
        room_chats = set()
        for chat in map(lambda c: benedict(c), message[chats_key]):
            if is_active_message(chat):
                chat_message = ChatMessage.from_json(chat)
                self.debug(chat_message)
                room_chats.add(chat_message)
            else:
                self.debug(f'omitting inactive message [{chat}]')
        return room_id, room_chats
