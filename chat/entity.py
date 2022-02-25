from __future__ import annotations

import inspect
from logging import getLogger
from typing import Callable, Dict, Any, Set

from attr import define, field
from requests import Session, Response

from chat.hub import SpaceHubSocket
from chat.listener import Registrable, AvailableRoomsLister, Listener, JoinRoomListener, RoomChatMessageListener, \
    RoomChatNewMessageListener, OnRoomsCallbackListener
from chat.messages import GetChatMessagesMessage, Message, JoinRoomMessage, ChatMessage
from support.mixin import LoggableMixin


class AvailableRooms(Registrable, LoggableMixin):
    def __init__(self):
        super().__init__()
        self.available_rooms_listener = AvailableRoomsLister()
        self.room_joiner = RoomJoiner()

    def on_register_listener(self, listener: Set[Listener]) -> None:
        listener.add(self.available_rooms_listener)

    def on_register_sender(self, send_method: Callable) -> None:
        self.room_joiner.register_send(send_method)

    def join(self, room_name: str) -> Room:
        room_id = self.available_rooms_listener.get_room_id(room_name)
        self.info(f'joining room [{room_name}:({room_id})]')
        return self.room_joiner.join(room_name, room_id)


class Sender:
    def __init__(self):
        self._send_method = lambda m: m

    def register_send(self, send_method: Callable[[Message], None]):
        self._send_method = send_method

    def send(self, message: Message):
        self._send_method(message)


@define
class Room(Registrable, LoggableMixin, Sender):
    room_id = field()
    room_name = field()

    def __init__(self, room_name: str, room_id: str):
        Registrable.__init__(self)
        LoggableMixin.__init__(self)
        self.room_name = room_name
        self.room_id = room_id
        self.room_join_listener = JoinRoomListener(room_name, room_id)
        self.chat_listener = RoomChatMessageListener(room_id)
        self.new_chat_listener = RoomChatNewMessageListener(room_id)

    def on_register_listener(self, listener: Set[Listener]) -> None:
        self._register(listener, self.room_join_listener)
        self._register(listener, self.chat_listener)
        self._register(listener, self.new_chat_listener)

    def on_register_sender(self, send_method: Callable[[Message], None]) -> None:
        self.register_send(send_method)

    def on_new_chat(self, callback:Callable[[ChatMessage], Any]):
        self.new_chat_listener.with_callback(callback)

    def get_chats(self):
        self.send(GetChatMessagesMessage(self.room_id))
        return self.chat_listener.get_messages()

    def chat_loop(self):
        while True:
            if self.new_chat_listener.with_wait_for_new():
                print(self.new_chat_listener.get_new_messages())

    def _register(self, listener_set: Set[Listener], listener: Listener):
        listener_set.discard(listener)
        listener_set.add(listener)


class SpaceHub(LoggableMixin):
    def __init__(self, hub_endpoint: str, token: str):
        super().__init__()
        self.space_hub_socket = SpaceHubSocket(hub_endpoint, token)
        self._available_rooms = AvailableRooms()

    def startup(self) -> None:
        self.space_hub_socket.register(self._available_rooms)
        self.space_hub_socket.startup()

    def teardown(self) -> None:
        self.space_hub_socket.teardown()

    def join_room(self, room_name: str) -> Room:
        joined_room = self._available_rooms.join(room_name)
        self.space_hub_socket.register(joined_room)
        return joined_room

    def on_rooms_listed(self, callback: Callable[[Dict[Any, Any]], None]):
        self.space_hub_socket.register(OnRoomsCallbackListener(callback))


@define
class Space(LoggableMixin):
    space_endpoint = 'https://spatial.chat/api/prod/v1/spaces'
    space_id = field()
    space_name = field()

    @classmethod
    def connect(cls, space_name: str, space_password: str) -> Space:
        with Session() as s:
            getLogger(cls.__name__).info(f'connecting to space [{space_name}]')
            response = s.get(Space.space_endpoint, params={'name': space_name, 'password': space_password})
            sj = validated_json(response)

        assert space_name == sj['name']
        return cls(sj['id'], sj['title'], sj['name'], space_password)

    def __init__(self, space_id: str, space_title: str, space_name: str, space_password: str):
        super().__init__()
        self._space_password = space_password
        self.space_id = space_id
        self.space_title = space_title
        self.space_name = space_name

    def join_as(self, username: str) -> SpaceHub:
        join_url = '/'.join((self.space_endpoint, self.space_id, 'join'))
        self.info(f'joining [{self.space_name}] as [{username}]')
        with Session() as s:
            response = s.post(join_url,
                              json={'userId': f'{hash(username)}', 'name': username, 'password': self._space_password})
            hub_json = validated_json(response)
            return SpaceHub(hub_json['hubEndpoint'], hub_json['token'])


def validated_json(response: Response) -> Dict[Any, Any]:
    assert 200 == response.status_code, f'{response.status_code}, {response.text}'
    json_response = response.json()
    getLogger(inspect.stack()[1][3]).debug(f'{response.url}: {json_response}')
    return json_response


class RoomJoiner(Sender):

    def join(self, room_name: str, room_id: str) -> Room:
        self.send(JoinRoomMessage(room_id))
        return Room(room_name, room_id)
