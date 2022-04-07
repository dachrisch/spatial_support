from __future__ import annotations

from typing import Optional

from more_itertools import one
from py_cui import PyCUI
from py_cui.keys import KEY_ENTER, KEY_ESCAPE
from py_cui.widgets import ScrollMenu
from websocket import WebSocketConnectionClosedException

from chat.entity.space import JoinableSpace
from chat.spatial.account import AuthenticatedAccount
from chat.tui.chat import ChatsListMenu, ChatSendBox
from chat.tui.room import RoomsListMenu, RoomEvent
from chat.tui.widget_set import WidgetSetActivator
from support.mixin import LoggableMixin


class SpaceSelectWidgetSet(WidgetSetActivator, LoggableMixin):
    def __init__(self, cui: PyCUI, account: AuthenticatedAccount):
        LoggableMixin.__init__(self)
        WidgetSetActivator.__init__(self, cui, 6, 6, logger=self._log)
        self.account = account
        self.spaces_list = self.add_scroll_menu('spaces', 1, 1, row_span=4, column_span=4)
        self.spaces_list.add_key_command(KEY_ENTER, self.select_space)

    def on_activate(self):
        self.cui.move_focus(self.spaces_list)
        self.spaces_list.clear()
        self.spaces_list.add_item_list(list(map(lambda s: s.name, self.account.list_spaces())))

    def select_space(self):
        selected_space_name = self.spaces_list.get()
        selected_space = one(filter(lambda s: s.name == selected_space_name, self.account.list_spaces()))
        joinable_space = selected_space.connect(self.account.account_secret)
        SpaceChatWidgetSet(self.cui, joinable_space, self).activate()


class DirectChatListMenu:
    def __init__(self, direct_list: ScrollMenu, cui: PyCUI):
        self.cui = cui
        self.direct_list = direct_list


class SpaceChatWidgetSet(WidgetSetActivator, LoggableMixin):
    def __init__(self, cui: PyCUI, joinable_space: JoinableSpace, previous_widget: Optional[WidgetSetActivator]):
        LoggableMixin.__init__(self)
        WidgetSetActivator.__init__(self, cui, 4, 3, logger=self._log)
        self.joinable_space = joinable_space
        self.previous_widget = previous_widget

        self.add_key_command(KEY_ESCAPE, self.return_to_select_space)

        self.rooms_menu = RoomsListMenu(self.add_scroll_menu('rooms', 0, 0, row_span=2), joinable_space.join(),
                                        self.cui)
        self.chats_menu = ChatsListMenu(self.add_scroll_menu('messages', 0, 1, row_span=3, column_span=2), self.cui)
        self.chat_send_box = ChatSendBox(self.add_text_box('send message', 3, 1, column_span=2), self.cui)
        self.direct_chat_menu = DirectChatListMenu(self.add_scroll_menu('direct', 2, 0, row_span=2), self.cui)

        self.rooms_menu.register(RoomEvent.PRE_JOIN, self.chats_menu.pre_room_join)
        self.rooms_menu.register(RoomEvent.POST_JOIN, self.chats_menu.on_room_join)
        self.rooms_menu.register(RoomEvent.PRE_JOIN, self.chat_send_box.pre_room_join)
        self.rooms_menu.register(RoomEvent.POST_JOIN, self.chat_send_box.on_room_join)

    def on_activate(self):
        self.cui.move_focus(self.rooms_menu.rooms_list)
        self.cui.run_on_exit(self.terminate_space)

    def terminate_space(self):
        self.info('goodbye')
        try:
            self.joinable_space.leave()
        except WebSocketConnectionClosedException:
            self.debug('connection already closed')

    def return_to_select_space(self):
        self.terminate_space()
        self.previous_widget.activate()
