from __future__ import annotations

from typing import List, Callable, Any

from attr import define, field
from benedict.dicts import benedict

from chat.entity.messages import ChatMessage
from chat.spatial.api import SpatialApiConnector
from chat.spatial.listener import BlockingListener, ChatListener
from chat.spatial.sender import ChatSender
from chat.spatial.websocket import SpatialWebSocketApp
from support.mixin import LoggableMixin


class RoomsTreeListener(BlockingListener, LoggableMixin):
    def __init__(self, socket: SpatialWebSocketApp, sap: SpatialApiConnector):
        LoggableMixin.__init__(self)
        self.sap = sap
        self.rooms = list()
        self.callbacks: List[Callable[[List[Room]], Any]] = list()
        self.chat_listener = ChatListener(socket)
        BlockingListener.__init__(self, socket, 'success.spaceState.roomsTree')

    def _on_message(self, socket: SpatialWebSocketApp, message: benedict):
        self.rooms.clear()
        rooms = [Room(room['id'], room['name'], socket, self.sap, self.chat_listener) for room in
                 message['success.spaceState.roomsTree']]
        self.rooms.extend(rooms)
        self.info(f'available rooms: {rooms}')
        [cb(rooms) for cb in self.callbacks]

    def get_rooms(self) -> List[Room]:
        with self.lock:
            return self.rooms

    def register(self, callback: Callable[[List[Room]], Any]):
        self.callbacks.append(callback)


@define
class Room(LoggableMixin):
    room_id = field()
    name = field()
    socket: SpatialWebSocketApp = field(repr=False)
    sap: SpatialApiConnector = field(repr=False)
    chat_listener: ChatListener = field(repr=False)

    def join(self):
        self.info(f'joining room {self}')
        self.sap.join_room(self.socket.space_id, self.room_id, self.socket.connection_id)
        return JoinedRoom(self.room_id, self.name,
                          self.chat_listener,
                          ChatSender(self.sap, self.socket.space_id, self.socket.connection_id))


@define
class JoinedRoom(LoggableMixin):
    room_id = field()
    name = field()
    chat_listener: ChatListener = field(repr=False)
    chat_sender: ChatSender = field(repr=False)

    def get_chat_messages(self) -> List[ChatMessage]:
        self.info(f'retrieved chats in {self}')
        return self.chat_listener.room_chats(self.room_id)

    def on_new_message(self, callback: Callable[[ChatMessage], Any]):
        self.chat_listener.register_on_new_message(self.room_id, callback)

    def send_chat(self, message_text: str):
        self.info(f'sending [{message_text}] to {self}')
        self.chat_sender.send(self.room_id, message_text)
