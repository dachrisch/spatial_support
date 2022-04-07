from __future__ import annotations

from websocket import WebSocketApp

from chat.entity.account import AccountProfile, AccountSecret
from chat.spatial.listener import ExistingDirectChatsListener
from chat.spatial.websocket import ThreadedWebSocketAppMixin, MessageHandlingWebSocketMixin


class DirectChatSocketAppWrapper(ThreadedWebSocketAppMixin, MessageHandlingWebSocketMixin):
    socket_endpoint = 'wss://spatial.chat/api/ChatOnline/connectDirectMessageChat'

    def __init__(self, socket: WebSocketApp):
        ThreadedWebSocketAppMixin.__init__(self, socket)
        MessageHandlingWebSocketMixin.__init__(self, socket)
        self.existing_direct_chats = ExistingDirectChatsListener(self)

    @classmethod
    def from_account(cls, account_profile: AccountProfile, secret: AccountSecret):
        socket = WebSocketApp(f'{cls.socket_endpoint}?accountId={account_profile.account_id}',
                              cookie=f'authorization={secret.auth_code}')
        return DirectChatSocketAppWrapper(socket)
