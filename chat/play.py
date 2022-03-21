from __future__ import annotations

import json
from abc import abstractmethod, ABC
from functools import partial
from logging import basicConfig, DEBUG
from threading import Thread, Lock
from typing import Dict, Any, List, Optional, Callable, final, Type, Set

from attr import define, field
from benedict import benedict
from cattr import unstructure, structure
from more_itertools import one
from py_cui import PyCUI
from py_cui.keys import KEY_ENTER
from py_cui.widget_set import WidgetSet
from py_cui.widgets import ScrollMenu
from requests import Session
from requests.cookies import RequestsCookieJar
from websocket import WebSocketApp

from support.mixin import LoggableMixin


class OnMessageListener:
    def __init__(self, message_type: str, callback: Callable[[WebSocketApp, benedict], None]):
        self.callback = callback
        self.message_type = message_type

    def accepts(self, message: benedict):
        return self.message_type in message

    def process(self, socket: WebSocketApp, message: benedict):
        self.callback(socket, message)


class ListenerBuilder:
    def __init__(self, listener_list, message_type: str):
        self.listener_list = listener_list
        self.message_type = message_type

    def call(self, callback=Callable[[WebSocketApp, benedict], None]):
        self.listener_list.append(OnMessageListener(self.message_type, callback))


class SpatialWebSocketApp(LoggableMixin, WebSocketApp):
    socket_endpoint = 'wss://spatial.chat/api/SpaceOnline/onlineSpace'

    def __init__(self, space_id: str, secret: AccountSecret):
        LoggableMixin.__init__(self)
        WebSocketApp.__init__(self, f'{self.socket_endpoint}?spaceId={space_id}', on_message=self._on_message,
                              on_open=self._on_open, cookie=f'authorization={secret.auth_code}')
        self.space_id = space_id
        self.socket_thread = Thread(target=self._run_socket)
        self.on_message_listener: List[OnMessageListener] = []
        self.connection = ConnectedListener(self)

    def _run_socket(self):
        self.run_forever()

    def _on_open(self, socket: WebSocketApp):
        self.debug(f'opened socket {socket.url}')

    def _on_message(self, socket: WebSocketApp, message: str):
        self.debug(f'triggered by message {message}')
        if 'ping' == message:
            socket.send('pong')
        else:
            message_json = benedict(json.loads(message))
            for accepting_listener in filter(lambda l: l.accepts(message_json), self.on_message_listener):
                try:
                    accepting_listener.process(socket, message_json)
                except:
                    self._log.exception(f'failed to execute [{accepting_listener}]')

    @property
    def connection_id(self):
        return self.connection.connection_id

    def start(self):
        self.socket_thread.start()

    def end(self):
        self.close()
        self.socket_thread.join(timeout=1)

    def on(self, message_type: str):
        return ListenerBuilder(self.on_message_listener, message_type)

    def send_message(self, message: object):
        self.send(json.dumps(unstructure(message)))


class BlockingListener(ABC):
    def __init__(self, socket: SpatialWebSocketApp, trigger_message: str):
        socket.on(trigger_message).call(self.on_message)
        self.lock = Lock()
        self.lock.acquire()

    @final
    def on_message(self, socket: SpatialWebSocketApp, message: benedict):
        self._on_message(socket, message)
        if self.lock.locked():
            self.lock.release()

    @abstractmethod
    def _on_message(self, socket: SpatialWebSocketApp, message: benedict):
        raise NotImplementedError


class RoomsTreeListener(BlockingListener):
    def __init__(self, socket: SpatialWebSocketApp, sap: SpatialApiConnector):
        super(RoomsTreeListener, self).__init__(socket, 'success.spaceState.roomsTree')
        self.sap = sap
        self.rooms = list()
        self.callbacks: List[Callable[[List[Room]], Any]] = list()

    def _on_message(self, socket: SpatialWebSocketApp, message: benedict):
        self.rooms.clear()
        rooms = [Room(room['id'], room['name'], socket, self.sap) for room in message['success.spaceState.roomsTree']]
        self.rooms.extend(rooms)
        [cb(rooms) for cb in self.callbacks]

    def get_rooms(self) -> List[Room]:
        with self.lock:
            return self.rooms

    def register(self, callback: Callable[[List[Room]], Any]):
        self.callbacks.append(callback)


class ConnectedListener(BlockingListener):
    def __init__(self, socket: SpatialWebSocketApp):
        super(ConnectedListener, self).__init__(socket, 'success.connected')
        self._connection_id = None

    def _on_message(self, socket: SpatialWebSocketApp, message: benedict):
        self._connection_id = message['success.connected.connectionId']

    @property
    def connection_id(self):
        with self.lock:
            return self._connection_id


@define(hash=True)
class ChatMessage:
    author_name = field()
    created = field()
    message = field()

    @classmethod
    def from_json(cls: Type[ChatMessage], chat_json: Dict[Any, Any]) -> ChatMessage:
        return ChatMessage(chat_json['created.account.account.name'], chat_json['created.date'], chat_json[
            'state.active.content'])


class ChatListener(BlockingListener, LoggableMixin):
    def __init__(self, socket: SpatialWebSocketApp):
        LoggableMixin.__init__(self)
        BlockingListener.__init__(self, socket, 'success.room.response.spatial.state.chat')
        self._chats: Set[ChatMessage] = set()

    def _on_message(self, socket: SpatialWebSocketApp, message: benedict):
        for chat in message['success.room.response.spatial.state.chat']:
            c = benedict(chat)
            if 'state.active.content' in c:
                self._chats.add(ChatMessage.from_json(c))
            else:
                self.debug(f'omitting inactive message [{c}]')

    @property
    def chats(self):
        with self.lock:
            return self._chats


class ChatSender:
    def __init__(self, sap: SpatialApiConnector, space_id: str, connection_id: str):
        self.connection_id = connection_id
        self.space_id = space_id
        self.sap = sap

    def send(self, room_id: str, message_text: str):
        self.sap.send_room_chat(self.space_id, room_id, self.connection_id, message_text)


@define
class JoinedRoom:
    room_id = field()
    chat_listener: ChatListener = field()
    chat_sender: ChatSender = field()

    def get_chat_messages(self):
        return self.chat_listener.chats

    def send_chat(self, message_text: str):
        with self.chat_listener.lock:
            self.chat_sender.send(self.room_id, message_text)


@define
class Room:
    room_id = field()
    name = field()
    socket: SpatialWebSocketApp = field()
    sap: SpatialApiConnector = field()

    def join(self):
        self.sap.join_room(self.socket.space_id, self.room_id, self.socket.connection_id)
        return JoinedRoom(self.room_id, ChatListener(self.socket),
                          ChatSender(self.sap, self.socket.space_id, self.socket.connection_id))


@define
class LeaveMessage:
    leave = {}


class JoinedSpace:

    def __init__(self, socket: SpatialWebSocketApp, sap: SpatialApiConnector):
        self.rooms_tree = RoomsTreeListener(socket, sap)
        self.sap = sap

    def list_rooms(self) -> List[Room]:
        return self.rooms_tree.get_rooms()

    def on_rooms_updated(self, callback: Callable[[List[Room]], Any]):
        self.rooms_tree.register(callback)


class JoinableSpace:
    def __init__(self, space_id: str, secret: AccountSecret, sap: SpatialApiConnector):
        self.space_id = space_id
        self.socket = SpatialWebSocketApp(space_id, secret)
        self.sap = sap

    def __enter__(self) -> JoinedSpace:
        return self.join()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.leave()

    def join(self) -> JoinedSpace:
        self.socket.start()
        return JoinedSpace(self.socket, self.sap)

    def leave(self):
        self.socket.send_message(LeaveMessage())
        self.socket.end()


@define
class Space:
    space_id: str = field()
    name: str = field()
    slug: str = field()
    sap: SpatialApiConnector = field()

    @classmethod
    def from_dict(cls, space_dict: Dict[str, Any], sap: SpatialApiConnector) -> Space:
        assert 'space' in space_dict
        return cls(space_id=space_dict['space']['id'], name=space_dict['space']['name'],
                   slug=space_dict['space']['slug'], sap=sap)

    def __init__(self, space_id: str, name: str, slug: str, sap: SpatialApiConnector):
        self.sap = sap
        self.space_id = space_id
        self.name = name
        self.slug = slug

    def connect(self, secret: AccountSecret) -> JoinableSpace:
        return JoinableSpace(self.space_id, secret, self.sap)


@define
class AccountSecret:
    COOKIE_FIELD = 'authorization'
    email = field()
    auth_code = field()

    def __init__(self, email: str, auth_code: str):
        self.auth_code = auth_code
        self.email = email

    def inject_cookies(self, cookies):
        cookies.set(self.COOKIE_FIELD, self.auth_code)

    @classmethod
    def from_cookies(cls, email: str, cookies: RequestsCookieJar):
        auth_code = cookies.get(cls.COOKIE_FIELD)
        return AccountSecret(email, auth_code)


class SpatialApiConnector(LoggableMixin):
    headers = {'x-client-version': '1', 'content-type': 'application/json'}

    def __init__(self, session: Session):
        super().__init__()
        self._session = session

    def list_space_visited(self) -> List[Dict[Any, Any]]:
        spaces_json = self._validated_put('https://spatial.chat/api/SpaceVisited/listSpaceVisited')
        assert 'spaces' in spaces_json, spaces_json
        return spaces_json['spaces']

    def register_account(self, email: str) -> str:
        account_json = self._validated_put('https://spatial.chat/api/Account/registerAccount',
                                           json_payload={'email': email})
        assert 'authKey' in account_json
        return account_json['authKey']

    def auth_account_by_magic_link(self, auth_key: str, magic_code: str) -> str:
        self._validated_put('https://spatial.chat/api/Account/authAccountByMagicLink', json_payload={
            'code': magic_code,
            'authKey': auth_key
        })
        assert AccountSecret.COOKIE_FIELD in self._session.cookies
        return self._session.cookies.get(AccountSecret.COOKIE_FIELD)

    def join_room(self, space_id: str, room_id: str, connection_id: str):
        self._validated_put('https://spatial.chat/api/SpaceOnline/joinRoom',
                            json_payload={'connectionId': connection_id, 'spaceId': space_id, 'roomId': room_id})

    def send_room_chat(self, space_id: str, room_id: str, connection_id: str, message_text: str):
        self._validated_put('https://spatial.chat/api/SpaceOnlineRoomChat/postRoomChatMessage',
                            json_payload={'connectionId': connection_id, 'spaceId': space_id, 'roomId': room_id,
                                          'content': message_text})

    def _validated_put(self, uri: str, json_payload: Optional[Dict[Any, Any]] = None) -> Dict[Any, Any]:
        if json_payload:
            # XXX: that bug cost me hours of lifetime - the api hangs if there are whitespaces in the json string. what the f*ck
            put_data = json.dumps(json_payload).replace(' ', '')
        else:
            put_data = ''
        self.debug(f'-X PUT {uri} -d\'{put_data}\'')
        json_response = self._session.put(uri, data=put_data, headers=self.headers, timeout=1).json()
        self.debug(json_response)
        assert 'success' in json_response, json_response
        return json_response['success']

    def authenticate(self, secret: AccountSecret):
        secret.inject_cookies(self._session.cookies)

    def terminate(self):
        self._session.close()


class AuthenticatedAccount:

    def __init__(self, sap: SpatialApiConnector, account_secret: AccountSecret):
        self.sap = sap
        self.secret = account_secret

    def list_spaces(self):
        spaces_json = self.sap.list_space_visited()
        return [Space.from_dict(space_json, self.sap) for space_json in spaces_json]

    def to_file(self, filename: str):
        with open(filename, 'w') as file:
            json.dump(unstructure(self.secret), file)


class FileAccount:
    def __init__(self, secret: AccountSecret, sap: Optional[SpatialApiConnector] = None):
        self.secret = secret
        self.sap = sap

    def __enter__(self):
        return self.authenticate()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.sap.terminate()

    def authenticate(self):
        if not self.sap:
            self.sap = SpatialApiConnector(Session())
        self.sap.authenticate(self.secret)
        return AuthenticatedAccount(self.sap, self.secret)

    @classmethod
    def from_file(cls, filename: str) -> FileAccount:
        with open(filename, 'r') as file:
            secret = structure(json.load(file), AccountSecret)
            return FileAccount(secret)


class UnauthenticatedEmailAccount:

    def __init__(self, email: str, sap: SpatialApiConnector, auth_key: str):
        self.auth_key = auth_key
        self.sap = sap
        self.email = email
        self.__tries = 0

    def validate_by_magic_code(self, magic_code: str) -> AuthenticatedAccount:
        self.__tries += 1
        auth = self.sap.auth_account_by_magic_link(self.auth_key, magic_code)
        return AuthenticatedAccount(self.sap, AccountSecret(self.email, auth))

    @property
    def tries(self):
        return self.__tries


class EmailAccount:
    headers = {'x-client-version': '-1'}

    def __init__(self, email: str, sap: Optional[SpatialApiConnector] = None):
        self.email = email
        self.sap = sap

    def __enter__(self) -> UnauthenticatedEmailAccount:
        return self.register()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.sap.terminate()

    def register(self) -> UnauthenticatedEmailAccount:
        if not self.sap:
            self.sap = SpatialApiConnector(Session())
        auth_key = self.sap.register_account(self.email)
        return UnauthenticatedEmailAccount(self.email, self.sap, auth_key)


class EmailLoginFlow(LoggableMixin):

    def __init__(self, cui: PyCUI):
        super().__init__()
        self.authenticated_account = None
        self.cui = cui

    def show_login_popup(self):
        fields = ['Email']
        self.cui.show_form_popup('Login to Account',
                                 fields,
                                 required=fields,
                                 callback=self.register_account_with_loading_popup)

    def register_account_with_loading_popup(self, form_output: Dict[str, str]):
        email = form_output['Email']
        self.cui.show_loading_icon_popup(f'Registering Account', f'{email}')
        Thread(target=partial(self.register_account, email)).start()

    def register_account(self, email: str):
        try:
            registered_account = EmailAccount(email).register()
            self.cui.stop_loading_popup()
            self.show_magic_code_popup(registered_account)
        except AssertionError as ae:
            self.cui.stop_loading_popup()
            self._log.exception('error registering account')
            self.cui.show_error_popup('Error while registering Account', f'while registering [{email}]: {ae}')
        except OSError as oe:
            self.cui.stop_loading_popup()
            self._log.exception('error registering account')
            self.cui.show_error_popup('Error connecting to Spatial', oe.strerror)

    def show_magic_code_popup(self, registered_account: UnauthenticatedEmailAccount):
        fields = ['Magic Code']
        self.cui.show_form_popup(f'[{registered_account.tries}] Enter Magic Code for {registered_account.email}',
                                 fields,
                                 required=fields,
                                 callback=partial(self.login_to_account, registered_account))

    def login_to_account(self, unauthenticated_account: UnauthenticatedEmailAccount, magic_code_form: Dict[str, str]):
        magic_code = magic_code_form['Magic Code']
        try:
            self.authenticated_account = unauthenticated_account.validate_by_magic_code(magic_code)
        except AssertionError as ae:
            if unauthenticated_account.tries < 3:
                self.show_magic_code_popup(unauthenticated_account)
            else:
                self.cui.show_error_popup(f'Error while validating code. Tried [{unauthenticated_account.tries}] times',
                                          f'{ae}')


class FileLoginFlow:
    def __init__(self, cui: PyCUI):
        self.cui = cui

    def show_file_selector(self):
        self.cui.show_filedialog_popup(callback=self.login_from_file, limit_extensions=['secret'])

    def login_from_file(self, selected_file: str):
        account = FileAccount.from_file(selected_file).authenticate()
        self.cui.stop_loading_popup()
        SpaceSelectWidgetSet(self.cui, account).activate()


class RoomsListMenu:
    def __init__(self, rooms_list: ScrollMenu, joined_space: JoinedSpace):
        self.rooms_list = rooms_list
        self.joined_space = joined_space
        self.joined_space.on_rooms_updated(self.on_rooms_updated)

        self.rooms_list.add_key_command(KEY_ENTER, self.callback_on_room_joined)
        self.on_room_joined_callback: Callable[[JoinedRoom], Any] = lambda x: None

    def on_rooms_updated(self, rooms: List[Room]):
        self.rooms_list.clear()
        self.rooms_list.add_item_list(list(map(lambda r: r.name, rooms)))

    def register_on_room_joined(self, callback: Callable[[JoinedRoom], Any]):
        self.on_room_joined_callback = callback

    def callback_on_room_joined(self):
        selected_room = one(filter(lambda r: r.name == self.rooms_list.get(), self.joined_space.list_rooms()))
        self.on_room_joined_callback(selected_room.join())


class ChatsListMenu:
    def __init__(self, chats_list: ScrollMenu):
        self.chats_list = chats_list

    def on_room_join(self, joined_room: JoinedRoom):
        self.chats_list.clear()
        self.chats_list.add_item_list(list(map(self.chat_message_format, joined_room.get_chat_messages())))

    def chat_message_format(self, chat: ChatMessage):
        return f'[{chat.author_name}] {chat.message}'


class SpaceChatWidgetSet(WidgetSet, LoggableMixin):
    def __init__(self, cui: PyCUI, joinable_space: JoinableSpace):
        LoggableMixin.__init__(self)
        WidgetSet.__init__(self, 4, 3, logger=self._log, root=cui)
        self.cui = cui

        self.joinable_space = joinable_space
        self.rooms_menu = RoomsListMenu(self.add_scroll_menu('rooms', 0, 0, row_span=4), joinable_space.join())
        self.chats_menu = ChatsListMenu(self.add_scroll_menu('messages', 0, 1, row_span=3, column_span=2))

        self.rooms_menu.register_on_room_joined(self.chats_menu.on_room_join)

    def activate(self):
        self.cui.apply_widget_set(self)
        self.cui.run_on_exit(self.terminate_space)

    def terminate_space(self):
        self.joinable_space.leave()


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


class SpatialChatTui:
    def __init__(self):
        self.cui = PyCUI(4, 3)
        self.cui.set_title('Spatial Omnichat')
        self.cui.enable_logging(logging_level=DEBUG)
        self.cui.set_refresh_timeout(1)  # in order to update async events (like room refresh)

        # self.cui.add_label('Login to Account', 0, 0, column_span=3)
        # self.cui.add_button('login via email', 1, 1, command=EmailLoginFlow(self.cui).show_login_popup)
        # self.cui.add_button('re-login via file', 2, 1, command=FileLoginFlow(self.cui).show_file_selector)
        with FileAccount.from_file('chat/account.secret') as account:
            SpaceSelectWidgetSet(self.cui, account).activate()

    def start(self):
        self.cui.start()


if __name__ == '__main__':
    basicConfig(filename='cui.log', filemode='w', level=DEBUG)
    SpatialChatTui().start()
