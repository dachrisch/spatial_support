from __future__ import annotations

from more_itertools import one
from py_cui import PyCUI
from py_cui.keys import KEY_ENTER

from chat.entity.account import AuthenticatedAccount
from chat.tui.room import SpaceChatWidgetSet
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
        joinable_space = selected_space.connect(self.account.secret)
        SpaceChatWidgetSet(self.cui, joinable_space, self).activate()
