from __future__ import annotations

from more_itertools import one
from py_cui import PyCUI
from py_cui.keys import KEY_ENTER
from py_cui.widget_set import WidgetSet

from chat.entity.account import AuthenticatedAccount
from chat.tui.room import SpaceChatWidgetSet
from support.mixin import LoggableMixin


class SpaceSelectWidgetSet(WidgetSet, LoggableMixin):
    def __init__(self, cui: PyCUI, account: AuthenticatedAccount):
        LoggableMixin.__init__(self)
        WidgetSet.__init__(self, 6, 6, logger=self._log, root=cui)
        self.account = account
        self.cui = cui
        self.spaces_list = self.add_scroll_menu('spaces', 1, 1, row_span=4, column_span=4)
        self.spaces_list.add_key_command(KEY_ENTER, self.select_space)

    def activate(self):
        self.cui.apply_widget_set(self)
        self.spaces_list.add_item_list(list(map(lambda s: s.name, self.account.list_spaces())))

    def select_space(self):
        selected_space_name = self.spaces_list.get()
        selected_space = one(filter(lambda s: s.name == selected_space_name, self.account.list_spaces()))
        joinable_space = selected_space.connect(self.account.secret)
        SpaceChatWidgetSet(self.cui, joinable_space).activate()