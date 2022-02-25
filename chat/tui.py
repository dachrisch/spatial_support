from __future__ import annotations

import getpass
import json
from functools import partial
from logging import DEBUG, basicConfig
from threading import Thread
from typing import Dict, Any

from py_cui import PyCUI
from py_cui.keys import KEY_ENTER
from py_cui.widget_set import WidgetSet

from chat.entity import Space, SpaceHub, Room
from chat.messages import SendChatMessage, ChatMessage
from support.mixin import LoggableMixin


class ChatWidgetWrapper(LoggableMixin):

    def __init__(self, chat_widget: WidgetSet):
        super().__init__()
        self.space_hub = SpaceHub('', '')
        self.chat_widget = chat_widget
        self.room_chats = self.chat_widget.add_scroll_menu('messages', 0, 1, row_span=3, column_span=2)

        self.rooms_list = self.chat_widget.add_scroll_menu('rooms', 0, 0, row_span=4)
        self.rooms_list.add_key_command(KEY_ENTER, self._on_room_select)

        self.chat_message = self.chat_widget.add_text_box('send', 3, 1, column_span=2)
        self.chat_message.add_key_command(KEY_ENTER, self._on_send_chat)

        self.joined_room = Room('None', 'None')

    def apply_widget(self, cui: PyCUI):
        cui.apply_widget_set(self.chat_widget)

    def register_space_hub(self, space_hub: SpaceHub):
        self.space_hub = space_hub
        self.space_hub.on_rooms_listed(self._update_rooms_list)

    @property
    def selected_room(self):
        return self.rooms_list.get()

    def _update_rooms_list(self, rooms: Dict[Any, Any]):
        self.rooms_list.clear()
        self.rooms_list.add_item_list(list(map(lambda r: r['name'], rooms)))

    def _on_room_select(self):
        self.debug(f'starting chat for [{self.selected_room}]')
        self.joined_room = self.space_hub.join_room(self.selected_room)
        self.joined_room.on_new_chat(self._update_chats)
        self._init_chats()

    def _format_chat_message(self, cm: ChatMessage):
        return f'[{cm.author}]: {cm.text}'

    def _init_chats(self):
        chats = self.joined_room.get_chats()
        self.debug(f'received chats: {chats}')
        self.room_chats.clear()
        self.room_chats.add_item_list(list(map(self._format_chat_message, chats)))

    def _update_chats(self, cm: ChatMessage):
        self.room_chats.add_item(self._format_chat_message(cm))

    def _on_send_chat(self):
        message = self.chat_message.get()
        self.debug(f'posting message to chat [{self.selected_room}]: {message}')
        self.joined_room.send(SendChatMessage.create(self.joined_room.room_id, message))
        self.chat_message.clear()


class SpatialChatCui(LoggableMixin):
    def __init__(self, auto_join=False):
        super(SpatialChatCui, self).__init__()
        self.auto_join = auto_join
        self.cui = PyCUI(4, 3)
        self.cui.set_title('Spatial Omnichat')
        self.cui.enable_logging(logging_level=DEBUG)
        self.cui.set_refresh_timeout(1)  # in order to update async events (like room refresh)

        self.rooms_menu = ChatWidgetWrapper(self.cui.create_new_widget_set(4, 3))

        if self.auto_join:
            with open('chat/space.json') as space_file:
                sjf = json.load(space_file)
                self.connect_with_loading_popup(
                    {'Space Name': sjf['space_name'], 'Admin Password': sjf['space_password'],
                     'Username': getpass.getuser()})
        else:
            self.cui.add_label('Connect to a space', 0, 0, column_span=3)
            self.cui.add_button('connect', 1, 1, command=self.show_space_popup)

    def start(self):
        self.cui.start()

    def show_space_popup(self):
        fields = ['Space Name', 'Admin Password', 'Username']
        self.cui.show_form_popup('Connect to Space',
                                 fields,
                                 passwd_fields=['Admin Password'],
                                 required=fields,
                                 callback=self.connect_with_loading_popup)

    def connect_with_loading_popup(self, form_output):
        self.cui.show_loading_icon_popup(f'Connecting to [{form_output["Space Name"]}]', 'Loading')
        Thread(target=partial(self.connect_to_space, form_output)).start()

    def connect_to_space(self, form_output):
        try:
            space = Space.connect(form_output['Space Name'], form_output['Admin Password'])
            space_hub = space.join_as(form_output['Username'])
            self.init_space(space_hub)
            self.cui.stop_loading_popup()
        except AssertionError as e:
            self.cui.stop_loading_popup()
            self.cui.show_error_popup('Error connecting to Space', str(e))

    def init_space(self, space_hub: SpaceHub):
        self.rooms_menu.apply_widget(self.cui)
        space_hub.startup()
        self.rooms_menu.register_space_hub(space_hub)


if __name__ == "__main__":
    basicConfig(filename='cui.log', filemode='w', level=DEBUG)

    # Create the CUI, pass it to the wrapper object, and start it
    SpatialChatCui(auto_join=True).start()
