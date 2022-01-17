import json
from logging import getLogger
from pathlib import Path
from typing import List

import websocket
from requests import Session

from hub import Processor, Hub


class RoomElementsProcessor(Processor):
    def __init__(self):
        self.elements = []

    def satisfied(self) -> bool:
        return self.elements != []

    def process(self, message_content):
        self.elements = message_content['elements']


class RoomHub(Hub):
    def __init__(self, connection: websocket):
        self.room_processor = RoomElementsProcessor()
        super().__init__(connection, {'room:elements:listed': self.room_processor})
        self.process_messages()

    @classmethod
    def connect(cls, connection):
        room_hub = cls(connection)
        return room_hub


class Room:
    endpoint = 'https://spatial.chat/api/prod/v1/rooms'

    @classmethod
    def from_json(cls, room_json, space_password):
        return cls(room_json['id'], room_json['name'], space_password)

    def __init__(self, _id, name, space_password):
        self._space_password = space_password
        self.id = _id
        self.name = name
        self.info = getLogger(self.__class__.__name__).info

    def __repr__(self):
        key_values = ','.join(map(lambda item: f'{item[0]}->{item[1]}',
                                  filter(lambda item: not (callable(item[1]) or item[0].startswith('_')),
                                         self.__dict__.items())))
        return f'{self.__class__.__name__}({key_values})'

    def background_image(self, filename):
        with Session() as s:
            upload_request = s.post('https://spatial.chat/api/prod/v1/images/upload-request',
                                    json={'fileName': filename, 'fileType': 'image/png'})
            assert 200 == upload_request.status_code, upload_request.text
            upload_url = upload_request.json()['signedRequest']
            final_url = upload_request.json()['url']
            with open(Path(filename).expanduser(), 'rb') as file:
                file_content = file.read()
                file_options = s.options(upload_url, headers={'origin': 'https://spatial.chat',
                                                              'Access-Control-Request-Headers': 'content-type',
                                                              'Access-Control-Request-Method': 'PUT'})
                assert 200 == file_options.status_code, file_options.text
                file_upload = s.put(upload_url, data=file_content, headers={'Content-Type': 'image/png'})
                assert 200 == file_upload.status_code, file_upload.text

            patched = s.patch(f'{Room.endpoint}/{self.id}', params={'password': self._space_password},
                              json={'bgImageUrl': final_url})
            assert 200 == patched.status_code
            return final_url

    def join(self, connection: websocket) -> RoomHub:
        self.info(f'joining room [{self}]')
        connection.send(json.dumps(['room:join', {'id': self.id}]))
        return RoomHub.connect(connection)

    def to_json(self):
        return {'name': self.name, 'id': self.id}


class RoomListingProcessor(Processor):
    def satisfied(self) -> bool:
        return self.rooms != []

    def __init__(self, space_password):
        self.space_password = space_password
        self.rooms: List[Room] = []
        self.debug = getLogger(self.__class__.__name__).debug

    def process(self, message_content):
        for room_json in message_content['rooms']:
            room = Room.from_json(room_json, self.space_password)
            self.debug(f'got room [{room}]')
            self.rooms.append(room)
