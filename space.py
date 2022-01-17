from logging import getLogger
from typing import List

from more_itertools import one
from requests import Session
from websocket import create_connection

from hub import Hub, DoNothingProcessor
from room import Room, RoomListingProcessor, RoomHub


class SpaceHub(Hub):
    @classmethod
    def connect(cls, json_hub, space_password):
        return cls(json_hub['hubEndpoint'], json_hub['token'], space_password)

    def __init__(self, endpoint, token, space_password):
        self.room_listing_processor = RoomListingProcessor(space_password)
        self.space_password = space_password
        self.token = token
        self.endpoint = endpoint
        ws = create_connection(f"{self.endpoint}?apiVer=2&token={self.token}")
        super().__init__(ws, {'space:updated': DoNothingProcessor(),
                              'rooms:listed': self.room_listing_processor,
                              'users:listed': DoNothingProcessor(),
                              'groups:listed': DoNothingProcessor(),
                              'broadcast:updated': DoNothingProcessor(), })

        self.connection.send('rooms:listed')
        self.process_messages()

    def join_room(self, name) -> RoomHub:
        return one(filter(lambda room: name == room.name, self.room_listing_processor.rooms)).join(self.connection)

    @property
    def rooms(self) -> List[Room]:
        return self.room_listing_processor.rooms


class Space:
    endpoint = 'https://spatial.chat/api/prod/v1/spaces'

    @classmethod
    def login(cls, space_name, space_password):
        getLogger(cls.__name__).info(f'logging into space [{space_name}]')
        with Session() as s:
            response = s.get(Space.endpoint, params={'name': space_name, 'password': space_password})
            assert 200 == response.status_code
            return cls(space_name, response.json(), space_password)

    def __init__(self, space_name, json, space_password):
        self.name = space_name
        self.debug = getLogger(self.__class__.__name__).debug
        self.info = getLogger(self.__class__.__name__).info
        self.space_password = space_password
        self.space_title = json['title']
        self.space_id = json['id']
        self.debug(json.keys())

    def join(self, username) -> SpaceHub:
        join_url = '/'.join((Space.endpoint, self.space_id, 'join'))
        self.info(f'joining [{self.space_title}] as [{username}]')
        with Session() as s:
            response = s.post(join_url, json={'userId': '123', 'name': username, 'password': self.space_password})
            assert 200 == response.status_code, response.status_code
            json_response = response.json()
            self.debug(json_response)
            return SpaceHub.connect(json_response, self.space_password)

    def to_json(self):
        return {'name': self.name, 'id': self.space_id}
