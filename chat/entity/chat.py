from typing import Dict, Any, List

from attr import define, field
from benedict.dicts import benedict
from websocket import WebSocketApp

from chat.entity.account import ChatAccount
from chat.entity.messages import ChatMessage
from chat.spatial.api import SpatialApiConnector
from chat.spatial.listener import BlockingListener, ListenerBuilderAware


class ExistingDirectChatsListener(BlockingListener):
    def __init__(self, sap: SpatialApiConnector, socket: ListenerBuilderAware):
        BlockingListener.__init__(self, socket, 'success.state.chats')
        self.sap = sap
        self.chats: List[DirectChat] = list()

    def _on_message(self, socket: WebSocketApp, message: benedict):
        for chat in message['success.state.chats']:
            self.chats.append(DirectChat.from_json(chat['account'], self.sap))

    def get_chats(self):
        with self.lock:
            return self.chats


@define
class DirectChat:
    chat_account: ChatAccount = field()
    sap: SpatialApiConnector = field(repr=False)

    def get_all_message(self) -> List[ChatMessage]:
        direct_message_chats = self.sap.get_direct_message_chat_page(self.chat_account.account_id)

        return [ChatMessage.from_json(benedict(dm)) for dm in direct_message_chats]

    @classmethod
    def from_json(cls, chat_json: Dict[Any, Any], sap: SpatialApiConnector):
        return DirectChat(ChatAccount.from_json(chat_json['account']), sap)
