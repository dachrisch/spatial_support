from __future__ import annotations

import json
from json import loads
from threading import Thread

from benedict.dicts import benedict
from cattr import unstructure
from websocket import WebSocketApp

from chat.spatial.listener import ListenerBuilderAware
from support.mixin import LoggableMixin


class ThreadedWebSocketAppMixin(LoggableMixin):

    def __init__(self, socket: WebSocketApp):
        LoggableMixin.__init__(self)
        self.socket = socket
        self.socket_thread = Thread(target=self._run_socket)

    def start(self):
        self.debug(f'starting socket thread [{self.socket_thread.name}]')
        self.socket_thread.start()

    def end(self):
        self.socket.close()
        self.socket_thread.join(timeout=1)

    def _run_socket(self):
        self.debug(f'running forever in thread {self.socket.url}')
        self.socket.run_forever()


class MessageHandlingWebSocketMixin(ListenerBuilderAware):
    def __init__(self, socket: WebSocketApp):
        ListenerBuilderAware.__init__(self)
        self.socket = socket
        socket.on_open = self._on_open
        socket.on_message = self._on_message

    def _on_open(self, socket: WebSocketApp):
        self.debug(f'opened socket {socket.url}')

    def _on_message(self, socket: WebSocketApp, message: str):
        self.debug(f'triggered by message {message}')
        if 'ping' == message:
            socket.send('pong')
        else:
            self.process_listener(socket, benedict(loads(message)))


class MessageSendingWebSocketMixin:
    def __init__(self, socket: WebSocketApp):
        self.socket = socket

    def send_message(self, message: object):
        self.socket.send(json.dumps(unstructure(message)))
