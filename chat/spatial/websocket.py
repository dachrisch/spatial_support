from __future__ import annotations

import json
from threading import Thread
from typing import List

from benedict.dicts import benedict
from cattr import unstructure
from websocket import WebSocketApp

from chat.entity.secret import AccountSecret
from chat.spatial.listener import OnMessageListener, ListenerBuilder, ConnectedListener, ListenerBuilderAware
from chat.spatial.param import SpaceConnection
from support.mixin import LoggableMixin


class SpatialWebSocketApp(LoggableMixin, WebSocketApp, ListenerBuilderAware):
    socket_endpoint = 'wss://spatial.chat/api/SpaceOnline/onlineSpace'

    def __init__(self, space_id: str, secret: AccountSecret):
        LoggableMixin.__init__(self)
        WebSocketApp.__init__(self, f'{self.socket_endpoint}?spaceId={space_id}', on_message=self._on_message,
                              on_open=self._on_open, cookie=f'authorization={secret.auth_code}')
        ListenerBuilderAware.__init__(self)
        self.socket_thread = Thread(target=self._run_socket)
        self.on_message_listener: List[OnMessageListener] = []
        self.connection = ConnectedListener(self)
        self.space_connection = SpaceConnection(space_id, self.connection)

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

    def start(self):
        self.socket_thread.start()

    def end(self):
        self.close()
        self.socket_thread.join(timeout=1)

    def on(self, message_type: str):
        return ListenerBuilder(self.on_message_listener, message_type)

    def send_message(self, message: object):
        self.send(json.dumps(unstructure(message)))
