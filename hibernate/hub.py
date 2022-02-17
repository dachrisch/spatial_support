from abc import abstractmethod
from logging import getLogger
from pathlib import Path
from typing import Any, Dict

from requests import Session
from websocket import WebSocket

from support.mixin import PrintableMixin, LoggableMixin


class Processor:
    @abstractmethod
    def process(self, message_content):
        raise NotImplementedError

    @abstractmethod
    def satisfied(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def processed(self) -> Any:
        raise NotImplementedError

    def accepts(self, message_type):
        return self._accept_message_type() == message_type

    @abstractmethod
    def _accept_message_type(self):
        raise NotImplementedError


class Hub:
    def __init__(self, connection: WebSocket):
        super(Hub, self).__init__()
        self.connection = connection
        self.debug = getLogger(self.__class__.__name__).debug


class SpatialSpaceConnector(PrintableMixin, LoggableMixin):
    space_endpoint = 'https://spatial.chat/api/prod/v1/spaces'
    room_endpoint = 'https://spatial.chat/api/prod/v1/rooms'

    def __init__(self, space_name, space_password):
        super().__init__()
        self.space_name = space_name
        self._space_password = space_password

    def connect(self) -> Dict[Any, Any]:
        self.info(f'connecting to space [{self.space_name}]')
        with Session() as s:
            response = s.get(self.space_endpoint, params={'name': self.space_name, 'password': self._space_password})
            _json = self._validated_json(response)
            return _json

    def join(self, space_id, username):
        join_url = '/'.join((self.space_endpoint, space_id, 'join'))
        self.info(f'joining [{self.space_name}] as [{username}]')
        with Session() as s:
            response = s.post(join_url,
                              json={'userId': f'{hash(username)}', 'name': username, 'password': self._space_password})
            return self._validated_json(response)

    def update_space_from_json(self, space_id, space_json: Dict[str, Any]):
        update_url = '/'.join((self.space_endpoint, space_id))
        self.info(f'updating [{self.space_name}] title to [{space_json["title"]}]')
        with Session() as s:
            response = s.patch(update_url, params={'password': self._space_password},
                               json={'title': space_json['title']})
            return self._validated_json(response)

    def update_room_from_json(self, room_id, room_json: Dict[str, Any]):
        with Session() as s:
            permissions = room_json['permissions'].copy()
            del permissions['stageReactions']
            patched = s.patch('/'.join((self.room_endpoint, room_id)), params={'password': self._space_password},
                              json={'permissions': permissions,
                                    'bgBrightness': room_json['bgBrightness'],
                                    'defaultZoomLevel': room_json['defaultZoomLevel']})
            return self._validated_json(patched)

    def create_room(self, space_id, room):
        create_room_url = '/'.join((self.space_endpoint, space_id, 'rooms'))
        self.info(f'creating room [{room.name}] in [{self.space_name}]')
        with Session() as s:
            response = s.post(create_room_url, params={'password': self._space_password},
                              json={'name': room.name, 'type': room.type})
            return self._validated_json(response)

    def _validated_json(self, response):
        assert 200 == response.status_code, f'{response.status_code}, {response.text}'
        json_response = response.json()
        self.debug(f'{response.url}: {json_response}')
        return json_response

    def background_image(self, room_id, filepath: Path):
        with Session() as s:
            upload_request = s.post('https://spatial.chat/api/prod/v1/images/upload-request',
                                    json={'fileName': filepath.name, 'fileType': 'image/png'})
            assert 200 == upload_request.status_code, upload_request.text
            upload_url = upload_request.json()['signedRequest']
            final_url = upload_request.json()['url']
            with open(filepath, 'rb') as file:
                file_content = file.read()
                file_options = s.options(upload_url, headers={'origin': 'https://spatial.chat',
                                                              'Access-Control-Request-Headers': 'content-type',
                                                              'Access-Control-Request-Method': 'PUT'})
                assert 200 == file_options.status_code, file_options.text
                file_upload = s.put(upload_url, data=file_content, headers={'Content-Type': 'image/png'})
                assert 200 == file_upload.status_code, file_upload.text

            patched = s.patch('/'.join((self.room_endpoint, room_id)), params={'password': self._space_password},
                              json={'bgImageUrl': final_url})
            assert 200 == patched.status_code, patched.text
            return final_url
