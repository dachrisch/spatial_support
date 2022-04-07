from __future__ import annotations

from websocket import WebSocketApp

from chat.entity.account import AccountSecret
from chat.spatial.listener import ConnectionListener
from chat.spatial.param import SpaceConnection
from chat.spatial.websocket.base import ThreadedWebSocketAppMixin, MessageHandlingWebSocketMixin, \
    MessageSendingWebSocketMixin


class SpatialWebSocketAppWrapper(ThreadedWebSocketAppMixin, MessageHandlingWebSocketMixin,
                                 MessageSendingWebSocketMixin):
    socket_endpoint = 'wss://spatial.chat/api/SpaceOnline/onlineSpace'

    def __init__(self, space_id: str, socket: WebSocketApp):
        ThreadedWebSocketAppMixin.__init__(self, socket)
        MessageHandlingWebSocketMixin.__init__(self, socket)
        MessageSendingWebSocketMixin.__init__(self, socket)

        self.connection = ConnectionListener(self)
        self.space_connection = SpaceConnection(space_id, self.connection.connected)

    @classmethod
    def from_account(cls, space_id: str, secret: AccountSecret):
        socket = WebSocketApp(f'{cls.socket_endpoint}?spaceId={space_id}', cookie=f'authorization={secret.auth_code}')
        return SpatialWebSocketAppWrapper(space_id, socket)
