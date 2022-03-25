from __future__ import annotations

from typing import Callable, Any, List

from more_itertools import one
from py_cui import PyCUI
from py_cui.keys import KEY_ENTER
from py_cui.widget_set import WidgetSet
from py_cui.widgets import ScrollMenu, TextBox

from chat.entity.messages import ChatMessage
from chat.entity.room import JoinedRoom, Room
from chat.entity.space import JoinedSpace, JoinableSpace
from support.mixin import LoggableMixin


class RoomsListMenu:
    def __init__(self, rooms_list: ScrollMenu, joined_space: JoinedSpace):
        self.rooms_list = rooms_list
        self.joined_space = joined_space
        self.joined_space.on_rooms_updated(self.on_rooms_updated)

        self.rooms_list.add_key_command(KEY_ENTER, self.callback_on_room_joined)
        self.on_room_joined_listener: List[Callable[[JoinedRoom], Any]] = list()

    def on_rooms_updated(self, rooms: List[Room]):
        self.rooms_list.clear()
        self.rooms_list.add_item_list(list(map(lambda r: r.name, rooms)))

    def register_on_room_joined(self, callback: Callable[[JoinedRoom], Any]):
        self.on_room_joined_listener.append(callback)

    def callback_on_room_joined(self):
        selected_room = one(filter(lambda r: r.name == self.rooms_list.get(), self.joined_space.list_rooms()))
        for callback in self.on_room_joined_listener:
            callback(selected_room.join())


class ChatsListMenu:
    def __init__(self, chats_list: ScrollMenu):
        self.chats_list = chats_list

    def on_room_join(self, joined_room: JoinedRoom):
        self.chats_list.clear()
        self.chats_list.add_item_list(list(map(self.chat_message_format, joined_room.get_chat_messages())))
        joined_room.on_new_message(self.on_new_chat_message)

    def on_new_chat_message(self, chat_message: ChatMessage):
        self.chats_list.add_item(self.chat_message_format(chat_message))

    def chat_message_format(self, chat: ChatMessage):
        return f'[{chat.age}]-[{chat.author_name}] {chat.message}'


class ChatSendBox:
    def __init__(self, box: TextBox):
        self.box = box
        self.title = box.get_title()
        self.joined_room: JoinedRoom = None
        self.box.add_key_command(KEY_ENTER, self.send_chat_message)
        self.box.set_selectable(False)
        self.box.set_title('join room to send message')

    def send_chat_message(self):
        message = self.box.get()
        self.joined_room.send_chat(message)
        self.box.clear()

    def on_room_join(self, joined_room: JoinedRoom):
        self.joined_room = joined_room
        self.box.set_selectable(True)
        self.box.set_title(f'send message to [{joined_room.name}]')


class SpaceChatWidgetSet(WidgetSet, LoggableMixin):
    def __init__(self, cui: PyCUI, joinable_space: JoinableSpace):
        LoggableMixin.__init__(self)
        WidgetSet.__init__(self, 4, 3, logger=self._log, root=cui)
        self.cui = cui

        self.joinable_space = joinable_space
        self.rooms_menu = RoomsListMenu(self.add_scroll_menu('rooms', 0, 0, row_span=4), joinable_space.join())
        self.chats_menu = ChatsListMenu(self.add_scroll_menu('messages', 0, 1, row_span=3, column_span=2))
        self.chat_send_box = ChatSendBox(self.add_text_box('send message', 3, 1, column_span=2))

        self.rooms_menu.register_on_room_joined(self.chats_menu.on_room_join)
        self.rooms_menu.register_on_room_joined(self.chat_send_box.on_room_join)

    def activate(self):
        self.cui.apply_widget_set(self)
        self.cui.run_on_exit(self.terminate_space)

    def terminate_space(self):
        self.info('goodbye')
        self.joinable_space.leave()
