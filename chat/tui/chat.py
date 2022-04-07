from __future__ import annotations

from typing import List

from py_cui import PyCUI
from py_cui.keys import KEY_DELETE, KEY_ENTER
from py_cui.widgets import ScrollMenu, TextBox
from requests import RequestException

from chat.entity.messages import ChatMessage
from chat.entity.room import JoinedRoom, Room


class ChatsListMenu:
    def __init__(self, chats_list: ScrollMenu, cui: PyCUI):
        self.cui = cui
        self.joined_room: JoinedRoom = JoinedRoom(None, None)
        self.chats_list = chats_list
        self.title = chats_list.get_title()

        self.chat_messages: List[ChatMessage] = list()

        self.chats_list.add_key_command(KEY_DELETE, self.command_delete_chat_message)
        self.chats_list.add_key_command(KEY_ENTER, self.command_show_message_details)

    def command_show_message_details(self):
        selected_index = self.chats_list.get_selected_item_index()
        chat_index = len(self.chat_messages) - selected_index - 1

        if 0 <= chat_index < len(self.chat_messages):
            chat = self.chat_messages[chat_index]
            ascii_author = chat.author_name.encode("ascii", "ignore").decode().strip()
            _, root_width = self.cui.get_absolute_size()
            total_width = (int(3 * root_width / 4)) - int(root_width / 4) - 7
            words = chat.message.split(' ')
            display_lines = ['', '']
            current_line = 1
            for word in words:
                if len(display_lines[current_line]) + len(word) > total_width:
                    display_lines.append('')
                    current_line += 1
                display_lines[current_line] = ' '.join((display_lines[current_line], word))

            self.cui.show_menu_popup(f'[{ascii_author}] @ [{chat.created.strftime("%Y/%m/%d %H:%M:%S")}]',
                                     display_lines, lambda x: x)

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
