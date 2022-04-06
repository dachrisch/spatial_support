from __future__ import annotations

from typing import List, Callable, Any, Dict

from attr import define, field

from chat.entity.messages import LeaveMessage
from chat.entity.room import RoomsTreeListener, Room
from chat.entity.secret import AccountSecret
from chat.spatial.api import SpatialApiConnector
from chat.spatial.websocket import SpatialWebSocketApp
from support.mixin import LoggableMixin


class JoinedSpace:

    def __init__(self, socket: SpatialWebSocketApp, sap: SpatialApiConnector):
        self.rooms_tree = RoomsTreeListener(socket, sap)
        self.sap = sap

    def list_rooms(self) -> List[Room]:
        return self.rooms_tree.get_rooms()

    def on_rooms_updated(self, callback: Callable[[List[Room]], Any]):
        self.rooms_tree.register(callback)


class JoinableSpace(LoggableMixin):
    def __init__(self, space_id: str, secret: AccountSecret, sap: SpatialApiConnector):
        super().__init__()
        self.space_id = space_id
        self.socket = SpatialWebSocketApp(space_id, secret)
        self.sap = sap

    def join(self) -> JoinedSpace:
        self.info(f'joining space [{self.space_id}]')
        self.socket.start()
        return JoinedSpace(self.socket, self.sap)

    def leave(self):
        self.socket.send_message(LeaveMessage())
        self.info(f'leaving space [{self.space_id}]')
        self.socket.end()


@define
class Space:
    space_id: str = field()
    name: str = field()
    slug: str = field()
    sap: SpatialApiConnector = field(repr=False)

    @classmethod
    def from_dict(cls, space_dict: Dict[str, Any], sap: SpatialApiConnector) -> Space:
        assert 'space' in space_dict
        return cls(space_id=space_dict['space']['id'], name=space_dict['space']['name'],
                   slug=space_dict['space']['slug'], sap=sap)

    def __init__(self, space_id: str, name: str, slug: str, sap: SpatialApiConnector):
        self.sap = sap
        self.space_id = space_id
        self.name = name
        self.slug = slug

    def connect(self, secret: AccountSecret) -> JoinableSpace:
        return JoinableSpace(self.space_id, secret, self.sap)