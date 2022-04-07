from __future__ import annotations

from typing import List, Callable, Any, Dict

from attr import define, field
from benedict.dicts import benedict

from chat.entity.messages import ChatMessage
from chat.spatial.api import SpatialApiConnector
from chat.spatial.listener import BlockingListener, ChatListener
from chat.spatial.param import SpaceConnection
from chat.spatial.sender import ChatSender, ChatDeleter
from chat.spatial.ws_space import SpatialWebSocketAppWrapper
from support.mixin import LoggableMixin


@define
class RoomsTreeListener(BlockingListener, LoggableMixin):
    room_joiner: RoomJoiner = field(repr=False)
    socket: SpatialWebSocketAppWrapper = field(repr=False)
    rooms: List[Room] = field(default=list())
    callbacks: List[Callable[[List[Room]], Any]] = field(repr=False, default=list())

    def __attrs_post_init__(self):
        BlockingListener.__init__(self, self.socket, 'success.spaceState.roomsTree')

    def _on_message(self, socket: SpatialWebSocketAppWrapper, message: benedict):
        self.rooms.clear()
        rooms = [Room.from_json(room_json, self.room_joiner) for room_json in message['success.spaceState.roomsTree']]
        self.rooms.extend(rooms)
        self.info(f'available rooms: {rooms}')
        [cb(rooms) for cb in self.callbacks]

    def get_rooms(self) -> List[Room]:
        with self.lock:
            return self.rooms

    def register(self, callback: Callable[[List[Room]], Any]):
        self.callbacks.append(callback)


@define
class RoomOperations:
    chat_listener: ChatListener = field(repr=False)
    chat_sender: ChatSender = field(repr=False)
    chat_deleter: ChatDeleter = field(repr=False)

    @classmethod
    def build(cls, sap: SpatialApiConnector, socket: SpatialWebSocketAppWrapper) -> RoomOperations:
        return RoomOperations(ChatListener(socket), ChatSender(sap, socket.space_connection),
                              ChatDeleter(sap, socket.space_connection))


@define
class RoomJoiner:
    sap: SpatialApiConnector = field(repr=False)
    space_connection: SpaceConnection = field()
    room_operations: RoomOperations = field(repr=False)

    def join_room(self, room: Room):
        self.sap.join_room(self.space_connection, room.room_id)
        return JoinedRoom(room, self.room_operations)


@define
class Room(LoggableMixin):
    room_id = field()
    name = field()
    room_joiner: RoomJoiner = field(repr=False)

    def join(self) -> JoinedRoom:
        self.info(f'joining room {self}')
        return self.room_joiner.join_room(self)

    @classmethod
    def from_json(cls, room_json: Dict[str, Any], room_joiner: RoomJoiner):
        return Room(room_json['id'], room_json['name'], room_joiner)


@define
class JoinedRoom(LoggableMixin):
    room: Room = field()
    room_operations: RoomOperations = field(repr=False)

    def get_chat_messages(self) -> List[ChatMessage]:
        self.info(f'retrieved chats in {self}')
        return self.room_operations.chat_listener.room_chats(self.room.room_id)

    def on_new_message(self, callback: Callable[[ChatMessage], Any]):
        self.room_operations.chat_listener.register_on_new_message(self.room.room_id, callback)

    def send_chat(self, message_text: str):
        self.info(f'sending [{message_text}] to {self}')
        self.room_operations.chat_sender.send(self.room.room_id, message_text)

    def delete_chat(self, chat: ChatMessage):
        self.info(f'deleting {chat} in  {self.room}')
        self.room_operations.chat_deleter.delete(self.room.room_id, chat.message_id)
