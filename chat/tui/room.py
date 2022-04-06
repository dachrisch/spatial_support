from __future__ import annotations

from enum import Enum, auto
from functools import partial
from threading import Thread
from typing import Callable, Any, List

from attr import define, field
from more_itertools import one
from py_cui import PyCUI
from py_cui.keys import KEY_ENTER, KEY_DELETE
from py_cui.widgets import ScrollMenu, TextBox
from requests import RequestException

from chat.entity.messages import ChatMessage
from chat.entity.room import JoinedRoom, Room
from chat.entity.space import JoinedSpace


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
        self.joined_room: JoinedRoom = JoinedRoom(None, None)
        self.chats_list = chats_list
        self.title = chats_list.get_title()

        self.chat_messages: List[ChatMessage] = list()

        self.chats_list.add_key_command(KEY_DELETE, self.command_delete_chat_message)

    def command_delete_chat_message(self):
        selected_index = self.chats_list.get_selected_item_index()
        chat_index = len(self.chat_messages) - selected_index - 1
        if 0 <= chat_index < len(self.chat_messages):
            chat = self.chat_messages[chat_index]
            self.joined_room.delete_chat(chat)
            self.chat_messages.remove(chat)
            self.display_chats()
            self.chats_list.set_selected_item_index(min(selected_index, len(self.chats_list.get_item_list()) - 1))

    def pre_room_join(self, selected_room: Room):
        self.chats_list.clear()
        self.chats_list.add_item(f'*** loading chats ***')
        self.chats_list.set_title(f'{self.title} - [{selected_room.name}]')

    def on_room_join(self, joined_room: JoinedRoom):
        self.joined_room = joined_room
        self.chat_messages = joined_room.get_chat_messages()
        self.display_chats()
        joined_room.on_new_message(self.on_new_chat_message)

    def on_new_chat_message(self, chat_message: ChatMessage):
        self.chat_messages.append(chat_message)
        self.display_chats()

    def display_chats(self):
        self.chats_list.clear()
        self.chats_list.add_item_list(list(map(self.chat_message_format, reversed(self.chat_messages))))

    def chat_message_format(self, chat: ChatMessage):
        return f'[{chat.age}]-[{chat.author_name}] {chat.message}'


class ChatSendBox:
    def __init__(self, box: TextBox, cui: PyCUI):
        self.cui = cui
        self.box = box
        self.title = box.get_title()
        self.joined_room: JoinedRoom = JoinedRoom(None, None)
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


