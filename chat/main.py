from __future__ import annotations

from logging import ERROR, basicConfig, DEBUG

from py_cui import PyCUI

from chat.spatial.account import FileAccount
from chat.spatial.ws_direct import DirectChatSocketAppWrapper
from chat.tui.space import SpaceSelectWidgetSet


class SpatialChatTui:
    def __init__(self):
        self.cui = PyCUI(4, 3)
        self.cui.set_title('Spatial Omnichat')
        self.cui.enable_logging(logging_level=ERROR)
        self.cui.set_refresh_timeout(1)  # in order to update async events (like room refresh)

        # self.cui.add_label('Login to Account', 0, 0, column_span=3)
        # self.cui.add_button('login via email', 1, 1, command=EmailLoginFlow(self.cui).show_login_popup)
        # self.cui.add_button('re-login via file', 2, 1, command=FileLoginFlow(self.cui).show_file_selector)
        with FileAccount.from_file('chat/account.secret') as account:
            SpaceSelectWidgetSet(self.cui, account).activate()

    def start(self):
        self.cui.start()


if __name__ == '1__main__':
    basicConfig(filename='cui.log', filemode='w', level=DEBUG)
    SpatialChatTui().start()

if __name__ == '__main__':
    basicConfig(level=DEBUG)
    with FileAccount.from_file('chat/account.secret') as account:
        account_profile = account.sap.get_account_profile()

        direct_chat = DirectChatSocketAppWrapper.from_account(account_profile, account.secret)
        direct_chat.start()
        chats = direct_chat.existing_direct_chats.get_chats()
        print(chats)
        direct_chat.end()
