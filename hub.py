import json
from abc import abstractmethod
from logging import getLogger
from typing import Dict

import websocket
from more_itertools import one


class Processor:
    @abstractmethod
    def process(self, message_content):
        raise NotImplementedError

    @abstractmethod
    def satisfied(self) -> bool:
        raise NotImplementedError


class DoNothingProcessor(Processor):
    def satisfied(self) -> bool:
        return True

    def process(self, message_content):
        pass


class Hub:
    def __init__(self, connection: websocket, processors: Dict[str, Processor]):
        self.connection = connection
        self.processors = processors
        self.debug = getLogger(self.__class__.__name__).debug

    def process_messages(self):
        while not all(map(lambda processor: processor.satisfied(), self.processors.values())):
            json_message = json.loads(self.connection.recv())
            if not json_message[0]:
                continue
            if 'ping' == json_message[0]:
                break
            self._process(json_message)

    def _process(self, message):
        self.debug(f'processing message {message}')
        message_type, *message_content = message
        if message_type in self.processors:
            self.debug(
                f'processing message of type [{message_type}] with processor [{self.processors[message_type]}]: {message_content}')
            self.processors[message_type].process(one(message_content))
        else:
            self.debug(f'ignoring message {message}')
