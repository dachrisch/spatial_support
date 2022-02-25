from __future__ import annotations

import json
from functools import partial
from threading import Thread, Lock
from typing import List, Set

from websocket import WebSocketApp

from chat.listener import Listener, KeepAlive, Registrable
from chat.messages import Message
from support.mixin import LoggableMixin, PrintableMixin


class SpaceHubSocket(LoggableMixin, PrintableMixin):
    def __init__(self, hub_endpoint, token, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hub_endpoint = hub_endpoint
        self._hub_socket = WebSocketApp(f'{hub_endpoint}?apiVer=2&token={token}', on_message=self._on_message,
                                        on_open=self._on_open)
        self._hub_thread = Thread(target=self._run_hub)
        self._hub_thread.daemon = True
        self._listeners: Set[Listener] = set()
        self._lock = Lock()
        self.register(KeepAlive())

    def _run_hub(self) -> None:
        self.debug(f'starting up socket thread [{self._hub_thread.name}]')
        self._hub_socket.run_forever()

    def startup(self) -> None:
        self.info(f'startup hub on [{self.hub_endpoint}]')
        self._lock.acquire()
        self._hub_thread.start()

    def teardown(self) -> None:
        self.info(f'tearing down hub [{self.hub_endpoint}]')
        with self._lock:
            self._hub_socket.close()
            self._hub_thread.join()

    def register(self, registrable: Registrable):
        registrable.on_register_listener(self._listeners)
        registrable.on_register_sender(self.send)

    def send(self, message: Message) -> None:
        self.debug(f'sending message {message}')
        with self._lock:
            self._hub_socket.send(json.dumps((message.message_type, message.message_content)))

    def _on_message(self, socket: WebSocketApp, message: str):
        def accepts(listener: Listener, _type: str):
            return listener.accepts(_type)

        message_json = json.loads(message)
        message_type = message_json[0]
        als = list(filter(partial(accepts, _type=message_type), self._listeners))
        self.debug(f'listener accepting [{message_type}]: {[l.__class__.__name__ for l in als]}')
        for al in als:
            try:
                al.process(message_json)
                self.debug(f'successfully processed {message_type} with {al}')
            except:
                self._log.exception(f'error processing message [{message_json}] with processor [{al}]')

    def _on_open(self, socket: WebSocketApp):
        self._lock.release()