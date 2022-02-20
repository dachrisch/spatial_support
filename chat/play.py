from __future__ import annotations

import inspect
import json
from abc import abstractmethod
from functools import partial
from logging import basicConfig, getLogger, INFO
from threading import Thread, Lock
from typing import Dict, Any, List, Callable

from requests import Session, Response
from websocket import WebSocketApp

from chat.listener import Registrable, Listener, SingleMessageListener, AvailableRoomsLister, JoinRoomListener, \
    KeepAlive
from chat.messages import Message, ChatMessage, JoinRoomMessage, GetChatMessagesMessage
from support.mixin import PrintableMixin, LoggableMixin

basicConfig(level=INFO)


def validated_json(response: Response) -> Dict[Any, Any]:
    assert 200 == response.status_code, f'{response.status_code}, {response.text}'
    json_response = response.json()
    getLogger(inspect.stack()[1][3]).debug(f'{response.url}: {json_response}')
    return json_response


class SpaceHubSocket(LoggableMixin, PrintableMixin):
    def __init__(self, hub_endpoint, token, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hub_endpoint = hub_endpoint
        self._hub_socket = WebSocketApp(f'{hub_endpoint}?apiVer=2&token={token}', on_message=self._on_message,
                                        on_open=self._on_open)
        self._hub_thread = Thread(target=self._run_hub)
        self._hub_thread.daemon = True
        self._listeners: List[Listener] = list()
        self._lock = Lock()
        self.register(KeepAlive())

    def _run_hub(self) -> None:
        self.debug(f'starting up socket thread [{self._hub_thread.name}]')
        self._hub_socket.run_forever()

    def startup(self) -> None:
        self.info(f'startup hub on [{self.hub_endpoint}]')
        self._lock.acquire()
        self._hub_thread.start()

    def teardown(self) -> None:
        self.info(f'tearing down hub [{self.hub_endpoint}]')
        with self._lock:
            self._hub_socket.close()
            self._hub_thread.join()

    def register(self, registrable: Registrable):
        registrable.on_register_listener(self._listeners)
        registrable.on_register_sender(self.send)

    def send(self, message: Message) -> None:
        self.debug(f'sending message {message}')
        with self._lock:
            self._hub_socket.send(json.dumps((message.message_type, message.message_content)))

    def _on_message(self, socket: WebSocketApp, message: str):
        def accepts(listener: Listener, _type: str):
            return listener.accepts(_type)

        message_json = json.loads(message)
        message_type = message_json[0]
        als = list(filter(partial(accepts, _type=message_type), self._listeners))
        self.debug(f'listener accepting [{message_type}]: {[l.__class__.__name__ for l in als]}')
        [al.process(message_json) for al in als]

    def _on_open(self, socket: WebSocketApp):
        self._lock.release()


class Sender:
    def __init__(self):
        self._send_method = lambda m:m

    def register_send(self, send_method: Callable[[Message], None]):
        self._send_method = send_method

    def send(self, message: Message):
        self._send_method(message)


class RoomJoiner(Sender):

    def join(self, room_name: str, room_id: str) -> Room:
        self.send(JoinRoomMessage(room_id))
        return Room(room_name, room_id)


class AvailableRooms(Registrable, LoggableMixin):
    def __init__(self):
        super().__init__()
        self.available_rooms_listener = AvailableRoomsLister()
        self.room_joiner = RoomJoiner()

    def on_register_listener(self, listener: List[Listener]) -> None:
        listener.append(self.available_rooms_listener)

    def on_register_sender(self, send_method: Callable) -> None:
        self.room_joiner.register_send(send_method)

    def join(self, room_name: str) -> Room:
        room_id = self.available_rooms_listener.get_room_id(room_name)
        self.info(f'joining room [{room_name}:({room_id})]')
        return self.room_joiner.join(room_name, room_id)


class RoomChatMessageListener(SingleMessageListener):
    def __init__(self):
        super().__init__('chat:get-messages')
        self.messages = set()

    def _process(self, message_json: Dict[Any, Any]):
        _type, *messages, message_id = message_json
        self.messages.update(map(lambda m: ChatMessage(m), messages[0]['messages']))

    def get_messages(self):
        with self._lock:
            return self.messages


class RoomChatNewMessageListener(SingleMessageListener):
    def __init__(self):
        super().__init__('chat:message-added')
        self.messages = set()

    def _process(self, message_json: Dict[Any, Any]):
        _type, *messages = message_json
        self.messages.add(ChatMessage(messages[0]['message']))

    def get_new_messages(self):
        messages_copy = self.messages.copy()
        self.messages.clear()
        return messages_copy

    def with_wait_for_new(self):
        return self._lock.acquire()


class Room(Registrable, LoggableMixin, Sender):

    def __init__(self, room_name: str, room_id: str):
        Registrable.__init__(self)
        LoggableMixin.__init__(self)
        self.room_name = room_name
        self.room_id = room_id
        self.room_join_listener = JoinRoomListener(room_name, room_id)
        self.chat_listener = RoomChatMessageListener()
        self.new_chat_listener = RoomChatNewMessageListener()

    def on_register_listener(self, listener: List[Listener]) -> None:
        listener.append(self.room_join_listener)
        listener.append(self.chat_listener)
        listener.append(self.new_chat_listener)

    def on_register_sender(self, send_method: Callable) -> None:
        self.register_send(send_method)

    def get_chats(self):
        self.send(GetChatMessagesMessage(self.room_id))
        return self.chat_listener.get_messages()

    def chat_loop(self):
        while True:
            if self.new_chat_listener.with_wait_for_new():
                print(self.new_chat_listener.get_new_messages())


class SpaceHub(PrintableMixin, LoggableMixin):
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


class Space(PrintableMixin, LoggableMixin):
    space_endpoint = 'https://spatial.chat/api/prod/v1/spaces'

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


if __name__ == '__main__':
    debug = getLogger(__name__).debug

    with open('space.json') as space_file:
        sjf = json.load(space_file)

    space = Space.connect(sjf['space_name'], sjf['space_password'])
    debug(space)
    space_hub = space.join_as('c')

    debug(space_hub)
    space_hub.startup()
    room = space_hub.join_room('Warm-Up 🎲')
    print(room.get_chats())
    room.chat_loop()
    space_hub.teardown()
