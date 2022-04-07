from __future__ import annotations

from websocket import WebSocketApp

from chat.entity.account import AccountProfile
from chat.entity.chat import ExistingDirectChatsListener
from chat.spatial.account import AuthenticatedAccount
from chat.spatial.api import SpatialApiConnector
from chat.spatial.websocket.base import ThreadedWebSocketAppMixin, MessageHandlingWebSocketMixin


class DirectChatSocketAppWrapper(ThreadedWebSocketAppMixin, MessageHandlingWebSocketMixin):
    socket_endpoint = 'wss://spatial.chat/api/ChatOnline/connectDirectMessageChat'

    def __init__(self, sap: SpatialApiConnector, socket: WebSocketApp):
        ThreadedWebSocketAppMixin.__init__(self, socket)
        MessageHandlingWebSocketMixin.__init__(self, socket)
        self.existing_direct_chats = ExistingDirectChatsListener(sap, self)

    @classmethod
    def from_account(cls, account_profile: AccountProfile, account: AuthenticatedAccount):
        socket = WebSocketApp(f'{cls.socket_endpoint}?accountId={account_profile.account_id}',
                              cookie=f'authorization={account.account_secret.auth_code}')
        return DirectChatSocketAppWrapper(account.sap, socket)
