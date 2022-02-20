import json
from base64 import urlsafe_b64encode
from json import JSONDecodeError
from logging import getLogger
from pathlib import Path
from typing import List, Any, Dict

import websocket
from more_itertools import one
from requests import Session

from hibernate.hub import Processor, Hub, SpatialSpaceConnector
from support.mixin import PrintableMixin, LoggableMixin


class RoomElementAddedProcessor(Processor, LoggableMixin):

    def __init__(self):
        super().__init__()
        self._processed = False

    def process(self, message_content, *args):
        self._processed = True
        self.debug(f'element added: {message_content}')

    def satisfied(self) -> bool:
        return self._processed

    def processed(self) -> Any:
        pass

    def _accept_message_type(self):
        return 'room:elements:add'


class RoomJoinedProcessor(Processor, LoggableMixin):
    def __init__(self, room_id):
        super().__init__()
        self.room_id = room_id
        self.joined_room = None

    def process(self, message_content, *args):
        self.joined_room = message_content
        self.debug(f'joined room: {message_content}')

    def satisfied(self) -> bool:
        return self.joined_room and self.room_id == self.joined_room['roomId']

    def processed(self) -> Any:
        return self.joined_room

    def _accept_message_type(self):
        return 'room:join'


class RoomElementsProcessor(Processor):
    def processed(self) -> Any:
        return self.elements

    def __init__(self):
        self.elements = None

    def satisfied(self) -> bool:
        return self.elements is not None

    def process(self, message_content):
        self.elements = message_content['elements']

    def _accept_message_type(self):
        return 'room:elements:listed'


class RoomListingProcessor(Processor):

    def _accept_message_type(self):
        return 'rooms:listed'

    def __init__(self):
        self.rooms: List[Room] = []
        self.debug = getLogger(self.__class__.__name__).debug

    def satisfied(self) -> bool:
        return self.rooms != []

    def process(self, *message_content):
        for room_json in one(message_content)['rooms']:
            room = Room.from_json(room_json)
            self.debug(f'got room [{room}]')
            self.rooms.append(room)

    def processed(self):
        return self.rooms

    def reset(self):
        return self.rooms.clear()


class Room:

    @classmethod
    def from_json(cls, room_json):
        _id = room_json['id']
        name = room_json['name']
        del room_json['id']
        del room_json['name']
        return cls(_id, name, **room_json)

    def __init__(self, _id, name, **kwargs):
        self.id = _id
        self.name = name
        for item in kwargs.items():
            setattr(self, item[0], item[1])
        self.info = getLogger(self.__class__.__name__).info

    def __repr__(self):
        key_values = ','.join(map(lambda item: f'{item[0]}->{item[1]}', self._public_member))
        return f'{self.__class__.__name__}({key_values})'

    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return False

    @property
    def _public_member(self):
        return filter(lambda item: not (callable(item[1]) or item[0].startswith('_')),
                      self.__dict__.items())

    def to_json(self):
        return dict(map(lambda item: (item[0], item[1]), self._public_member))


class RoomHub(Hub, LoggableMixin):
    def __init__(self, space_connector: SpatialSpaceConnector, connection: websocket):
        super(RoomHub, self).__init__(connection)
        self.space_connector = space_connector
        self.processor = RoomListingProcessor()

    def update_from_json(self, room: Room, room_json):
        self.debug(f'updating room [{room.id}] with {room_json}')
        self.space_connector.update_room_from_json(room.id, room_json)
        self._send_join(room.id)
        room_elements = self.list_elements(room)
        for element in room_json['elements']:
            if self._element_already_present(element, room_elements):
                self.debug(f'element [{element["elementType"]}] already present: {element}')
            else:
                self.debug(f'adding element [{element["elementType"]}]: {element}')
                self._send_element(room.id, element)

    def list_rooms(self):
        rooms = self.satisfy(self.processor)
        return list(map(lambda room: ConnectedRoom(room, self), rooms))

    def list_elements(self, room: Room):
        if not room.type == 'spatial':
            return ()
        self._send_join(room.id)
        return self.satisfy(RoomElementsProcessor())

    def satisfy(self, processor: Processor):
        while not processor.satisfied():
            message = self.connection.recv()
            if not message:
                continue
            try:
                json_message = json.loads(message)
            except JSONDecodeError as e:
                self._log.exception(f'failed to decode [${message}]', e)
                raise

            self.debug(f'processing message {json_message}')
            if not json_message[0]:
                self.debug(f'ignoring unknown message {json_message}')
                continue
            if 'ping' == json_message[0]:
                self.connection.pong()

            message_type, *message_content = json_message
            if processor.accepts(message_type):
                processor.process(*message_content)
        return processor.processed()

    def _send_join(self, room_id):
        self._send_message('room:join', {'id': room_id}, RoomJoinedProcessor(room_id))

    def _send_element(self, room_id, element: Dict[str, Any]):
        element_json = element.copy()
        element_json['roomId'] = room_id
        self._send_message('room:elements:add', element_json, RoomElementAddedProcessor())

    def _send_message(self, message_key: str, message_values: Dict[str, Any], processor):
        self.debug(f'sending message [{message_key}]: {message_values}')
        self.connection.send(json.dumps([message_key, message_values]))
        return self.satisfy(processor)

    def _element_already_present(self, element: Dict[str, Any], room_elements: List[Dict[str, Any]]):
        element_match_map = list(map(lambda el: (el['type'], el['pos'], el['width'], el['height']), room_elements))

        return (element['type'], element['pos'], element['width'], element['height']) in element_match_map


class ConnectedRoom(PrintableMixin, LoggableMixin):
    def __init__(self, room: Room, room_hub: RoomHub):
        super().__init__()
        self.room = room
        self.room_hub = room_hub
        self.debug = getLogger(self.__class__.__name__).debug

    @property
    def name(self):
        return self.room.name

    @property
    def elements(self):
        return self.room_hub.list_elements(self.room)

    def to_json(self):
        return self.room.to_json()

    def hibernate(self, hibernate_path: Path):
        self.debug(f'hibernating [{self.room}]')
        self._hibernate_room(hibernate_path)
        self._hibernate_background_image(hibernate_path)

    def _hibernate_background_image(self, hibernate_path):
        room_bg_filename = f'{str(urlsafe_b64encode(self.name.encode("UTF-8")), "utf-8")}.room.jpg'
        with Session() as s:
            response = s.get(self.room.bgImageUrl)
            with open(hibernate_path.joinpath(room_bg_filename), 'wb') as room_bg_file:
                room_bg_file.write(response.content)

    def _hibernate_room(self, hibernate_path):
        room_filename = f'{str(urlsafe_b64encode(self.name.encode("UTF-8")), "utf-8")}.room'
        room_json = {'room': self.to_json(),
                     }
        room_json['room']['elements'] = self.elements
        with open(hibernate_path.joinpath(room_filename), 'w') as room_file:
            self.info(f'hibernating [{self.name}] to [{room_file.name}]')
            self.debug(f'room content: {room_json}')
            json.dump(room_json, room_file)

    def resume(self, hibernate_path):
        room_bg_filename = hibernate_path.joinpath(
            f'{str(urlsafe_b64encode(self.name.encode("UTF-8")), "utf-8")}.room.jpg')
        self.debug(f'restoring background image [{room_bg_filename.name}]')
        self.room_hub.space_connector.background_image(self.room.id, room_bg_filename)
        room_filename = f'{str(urlsafe_b64encode(self.name.encode("UTF-8")), "utf-8")}.room'
        with open(hibernate_path.joinpath(room_filename), 'r') as room_file:
            self.info(f'resuming room [{self.name}] from [{room_file.name}]')
            room_json = json.load(room_file)['room']
            self.room_hub.update_from_json(self.room, room_json)
