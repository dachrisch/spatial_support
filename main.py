import json
import os
from logging import basicConfig, INFO
from logging import getLogger
from pathlib import Path

from space import Space


class SpaceProcessor:
    def __init__(self, space_name, space_password):
        self.space: Space = Space.login(space_name, space_password)
        self.debug = getLogger(self.__class__.__name__).debug
        self.info = getLogger(self.__class__.__name__).info

    def hibernate(self, directory, user='hibernate'):
        space_hub = self.space.join(user)
        hibernate_path = Path(directory).joinpath(self.space.name).expanduser()
        hibernate_path.mkdir(parents=True, exist_ok=True)
        with open(hibernate_path.joinpath(f'{self.space.name}.space'), 'w') as space_file:
            space_json = {'space': self.space.to_json()}
            space_json['space']['rooms'] = []
            for room in space_hub.rooms:
                room_json = {'room': room.to_json()}
                space_json['space']['rooms'].append(room.to_json())
                room_hub = space_hub.join_room(room.name)
                room_json['room']['elements'] = room_hub.room_processor.elements
                with open(hibernate_path.joinpath(f'{room.name}.room'), 'w') as room_file:
                    self.info(f'hibernating room to [{room_file.name}]')
                    self.debug(f'room content: {room_json}')
                    json.dump(room_json, room_file)
            self.info(f'hibernating space to [{space_file.name}]')
            self.debug(f'space content: {space_json}')
            json.dump(space_json, space_file)


def main():
    basicConfig(level=INFO)

    sp = SpaceProcessor(os.getenv('space_name'), os.getenv('space_password'))

    sp.hibernate('~/Downloads/spatial_test')


if __name__ == '__main__':
    main()
