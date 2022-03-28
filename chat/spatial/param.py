from __future__ import annotations

from attr import define, field

from chat.spatial.listener import ConnectedListener


@define
class SpaceConnection:
    space_id: str = field()
    connection: ConnectedListener = field(repr=False)

    @property
    def connection_id(self):
        return self.connection.connection_id
