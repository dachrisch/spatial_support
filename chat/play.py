from __future__ import annotations

import json
from logging import basicConfig, DEBUG

from chat.entity import Space

basicConfig(level=DEBUG)

if __name__ == '__main__':
    with open('space.json') as space_file:
        sjf = json.load(space_file)

    space = Space.connect(sjf['space_name'], sjf['space_password'])
    space_hub = space.join_as('c')
    space_hub.startup()
    room = space_hub.join_room('Warm-Up 🎲')
    print(room.get_chats())
    room.chat_loop()
    space_hub.teardown()
