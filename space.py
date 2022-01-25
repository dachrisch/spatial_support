import json
from logging import getLogger
from pathlib import Path
from typing import List

from more_itertools import first, one
from websocket import create_connection

from hub import Hub, SpatialSpaceConnector
from mixin import PrintableMixin, LoggableMixin
from room import Room, RoomHub, ConnectedRoom


class SpaceFactory:
    @classmethod
    def connect(cls, space_name, space_password):
        space_connector = SpatialSpaceConnector(space_name, space_password)
        return ConnectedSpace(space_connector)


class Space(PrintableMixin):

    def __init__(self, id, title, name, maxRooms, **kwargs):
        self.max_rooms = maxRooms
        self.name = name
        self.debug = getLogger(self.__class__.__name__).debug
        self.info = getLogger(self.__class__.__name__).info
        self.space_title = title
        self.space_id = id
        self.debug(kwargs)

    def to_json(self):
        return {'title': self.space_title, 'id': self.space_id}


class SpaceHub(Hub, LoggableMixin):

    def __init__(self, space_connector: SpatialSpaceConnector, hubEndpoint, token, user, chatEndpoint):
        self.space_connector = space_connector
        self.hubEndpoint = hubEndpoint
        self.token = token
        super().__init__(create_connection(f"{self.hubEndpoint}?apiVer=2&token={self.token}"))
        self.room_hub = RoomHub(space_connector, self.connection)

    def list_rooms(self):
        return self.room_hub.list_rooms()


class JoinedSpace(PrintableMixin, LoggableMixin):
    def __init__(self, space: Space, space_hub: SpaceHub):
        super().__init__()
        self.space = space
        self.space_hub = space_hub

    @property
    def rooms(self) -> List[ConnectedRoom]:
        return self.space_hub.list_rooms()

    def hibernate(self, hibernate_path: Path):
        with open(hibernate_path.joinpath(f'{self.space.name}.space'), 'w') as space_file:
            space_json = {
                'space': self.space.to_json(),
            }
            space_json['space']['rooms'] = list(map(lambda room: room.to_json(), self.rooms))
            self.info(f'hibernating space to [{space_file.name}]')
            self.debug(f'space content: {space_json}')
            json.dump(space_json, space_file)

        for room in self.rooms:
            room.hibernate(hibernate_path)

    def resume(self, hibernate_path: Path):
        with open(one(hibernate_path.glob('*.space')), 'r') as space_file:
            self.info(f'resuming space [{self.space.name}] from [{space_file.name}]')
            space_json = json.load(space_file)['space']
        self.space_hub.space_connector.update_space_from_json(self.space.space_id, space_json)
        self.eat_excessive_room_messages()
        resume_rooms = list(map(lambda room_json: Room.from_json(room_json), space_json['rooms']))

        self._restore_rooms(resume_rooms)

        for resume_room in resume_rooms:
            connected_room: ConnectedRoom = first(filter(lambda room: room.name == resume_room.name, self.rooms), ())
            if not connected_room:
                self.log.error(f'skipping not existing room [{resume_room.name}]')
            else:
                connected_room.resume(hibernate_path)

    def eat_excessive_room_messages(self):
        self.set_refresh_rooms()
        self.space_hub.room_hub.list_rooms()
        self.set_refresh_rooms()

    def _restore_rooms(self, resume_rooms: List[Room]):
        new_rooms = list(
            filter(lambda r: r.name not in self._existing_rooms_names(), resume_rooms))
        required_rooms_new = len(new_rooms)
        self.debug(f'about to create [{required_rooms_new}] rooms')
        current_rooms = len(self.rooms)
        remaining_rooms_space = self.space.max_rooms - current_rooms
        if required_rooms_new > remaining_rooms_space:
            self.log.error(f'only [{remaining_rooms_space}] rooms available but need to create [{required_rooms_new}]')
            new_rooms = new_rooms[:remaining_rooms_space]
            self.info(f'only creating rooms {list(map(lambda r: r.name, new_rooms))}')
        for new_room in new_rooms:
            self.space_hub.space_connector.create_room(self.space.space_id, new_room)
            self.set_refresh_rooms()

    def _existing_rooms_names(self):
        return map(lambda existing_room: existing_room.name, self.rooms)

    def set_refresh_rooms(self):
        self.space_hub.room_hub.processor.reset()


class ConnectedSpace(PrintableMixin):
    def __init__(self, space_connector: SpatialSpaceConnector):
        self.space = Space(**space_connector.connect())
        self.space_connector = space_connector

    def join(self, username) -> JoinedSpace:
        hub_json = self.space_connector.join(self.space.space_id, username)
        return JoinedSpace(self.space, SpaceHub(self.space_connector, **hub_json))
