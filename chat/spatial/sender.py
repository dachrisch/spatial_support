from __future__ import annotations

from attr import define, field

from chat.spatial.api import SpatialApiConnector
from chat.spatial.param import SpaceConnection


@define
class ChatSender:
    sap: SpatialApiConnector = field(repr=False)
    space_connection: SpaceConnection = field()

    def send(self, room_id: str, message_text: str):
        self.sap.send_room_chat(self.space_connection, room_id, message_text)


@define
class ChatDeleter:
    sap: SpatialApiConnector = field(repr=False)
    space_connection: SpaceConnection = field()

    def delete(self, room_id: str, message_id: str):
        self.sap.delete_chat_message(self.space_connection, room_id, message_id)
