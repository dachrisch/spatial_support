from __future__ import annotations

from enum import Enum, auto
from functools import partial
from threading import Thread
from typing import Callable, Any, List

from attr import define, field
from more_itertools import one
from py_cui import PyCUI
from py_cui.keys import KEY_ENTER
from py_cui.widgets import ScrollMenu
from requests import RequestException

from chat.entity.room import Room
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
