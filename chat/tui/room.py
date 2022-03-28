from __future__ import annotations

from enum import Enum, auto
from functools import partial
from threading import Thread
from typing import Callable, Any, List

from attr import define, field
from more_itertools import one
from py_cui import PyCUI
from py_cui.keys import KEY_ENTER, KEY_ESCAPE
from py_cui.widget_set import WidgetSet
from py_cui.widgets import ScrollMenu, TextBox
from requests import RequestException

from chat.entity.messages import ChatMessage
from chat.entity.room import JoinedRoom, Room
from chat.entity.space import JoinedSpace, JoinableSpace
from support.mixin import LoggableMixin


@define
class AsyncWithResultCallback:
    call: Callable[[], Any] = field()
    callback: Callable[[Any], Any] = field()

    def run(self):
        call_return = self.call()
        self.callback(call_return)


class AsyncWithCallbackBuilder:

    def __init__(self, call: Callable[[Any], Any]):
        self.call = call

    def then_with_result(self, callback: Callable[[Any], Any]):
        return Thread(target=AsyncWithResultCallback(self.call, callback).run).start()

    @classmethod
    def do_async(cls, call: Callable[[Any], Any]):
        return AsyncWithCallbackBuilder(call)


class RoomEvent(Enum):
    PRE_JOIN = auto()
    POST_JOIN = auto()


class RoomsListMenu:
    def __init__(self, rooms_list: ScrollMenu, joined_space: JoinedSpace, cui: PyCUI):
        self.cui = cui
        self.rooms_list = rooms_list
        self.rooms_list.add_item('*** loading rooms ***')
        self.joined_space = joined_space
        self.joined_space.on_rooms_updated(self.on_rooms_updated)

        self.rooms_list.add_key_command(KEY_ENTER, self.command_join_room)

        self.event_listener = dict()
        for event in RoomEvent:
            self.event_listener[event] = list()

    def on_rooms_updated(self, rooms: List[Room]):
        self.rooms_list.clear()
        self.rooms_list.add_item_list(list(map(lambda r: r.name, rooms)))

    def register(self, event: RoomEvent, callback: Callable[[Any], Any]):
        self.event_listener[event].append(callback)

    def command_join_room(self):
        try:
            selected_room = one(filter(lambda r: r.name == self.rooms_list.get(), self.joined_space.list_rooms()))
            self.inform_listener(RoomEvent.PRE_JOIN, selected_room)
            AsyncWithCallbackBuilder.do_async(selected_room.join).then_with_result(
                partial(self.inform_listener, RoomEvent.POST_JOIN))
        except RequestException as re:
            self.cui.show_error_popup(f'Error joining room {self.rooms_list.get()}', f'{re}')

    def inform_listener(self, event: RoomEvent, *args, **kwargs):
        for listener in self.event_listener[event]:
            listener(*args, **kwargs)


class ChatsListMenu:
    def __init__(self, chats_list: ScrollMenu):
        self.chats_list = chats_list
        self.title = chats_list.get_title()

        self.chats_list.add_key_command(KEY_ESCAPE, self.command_delete_chat_message)

    def command_delete_chat_message(self):
        pass

    def pre_room_join(self, selected_room: Room):
        self.chats_list.clear()
        self.chats_list.add_item(f'*** loading chats ***')
        self.chats_list.set_title(f'{self.title} - [{selected_room.name}]')

    def on_room_join(self, joined_room: JoinedRoom):
        self.chats_list.clear()
        chat_messages = list(map(self.chat_message_format, joined_room.get_chat_messages()))
        self.chats_list.add_item_list(chat_messages)
        joined_room.on_new_message(self.on_new_chat_message)

    def on_new_chat_message(self, chat_message: ChatMessage):
        self.chats_list.add_item(self.chat_message_format(chat_message))

    def chat_message_format(self, chat: ChatMessage):
        return f'[{chat.age}]-[{chat.author_name}] {chat.message}'


class ChatSendBox:
    def __init__(self, box: TextBox, cui: PyCUI):
        self.cui = cui
        self.box = box
        self.title = box.get_title()
        self.joined_room: JoinedRoom = JoinedRoom(-1, 'nothing', None, None)
        self.box.add_key_command(KEY_ENTER, self.command_send_chat_message)
        self.box.set_selectable(False)
        self.box.set_title('join room to send message')

    def command_send_chat_message(self):
        message = self.box.get()
        try:
            self.joined_room.send_chat(message)
            self.box.clear()
        except RequestException as re:
            self.cui.show_error_popup('Error while sending chat', f'{re}')

    def pre_room_join(self, selected_room: Room):
        self.box.set_selectable(False)
        self.box.set_title(f'send message to [{selected_room.name}]')

    def on_room_join(self, joined_room: JoinedRoom):
        self.joined_room = joined_room
        self.box.set_selectable(True)


class SpaceChatWidgetSet(WidgetSet, LoggableMixin):
    def __init__(self, cui: PyCUI, joinable_space: JoinableSpace):
        LoggableMixin.__init__(self)
        WidgetSet.__init__(self, 4, 3, logger=self._log, root=cui)
        self.cui = cui

        self.joinable_space = joinable_space
        self.rooms_menu = RoomsListMenu(self.add_scroll_menu('rooms', 0, 0, row_span=4), joinable_space.join(),
                                        self.cui)
        self.chats_menu = ChatsListMenu(self.add_scroll_menu('messages', 0, 1, row_span=3, column_span=2))
        self.chat_send_box = ChatSendBox(self.add_text_box('send message', 3, 1, column_span=2), self.cui)

        self.rooms_menu.register(RoomEvent.PRE_JOIN, self.chats_menu.pre_room_join)
        self.rooms_menu.register(RoomEvent.POST_JOIN, self.chats_menu.on_room_join)
        self.rooms_menu.register(RoomEvent.PRE_JOIN, self.chat_send_box.pre_room_join)
        self.rooms_menu.register(RoomEvent.POST_JOIN, self.chat_send_box.on_room_join)

    def activate(self):
        self.cui.apply_widget_set(self)
        self.cui.run_on_exit(self.terminate_space)

    def terminate_space(self):
        self.info('goodbye')
        self.joinable_space.leave()
