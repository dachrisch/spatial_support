from __future__ import annotations

from chat.spatial.api import SpatialApiConnector


class ChatSender:
    def __init__(self, sap: SpatialApiConnector, space_id: str, connection_id: str):
        self.connection_id = connection_id
        self.space_id = space_id
        self.sap = sap

    def send(self, room_id: str, message_text: str):
        self.sap.send_room_chat(self.space_id, room_id, self.connection_id, message_text)