from logging import getLogger


class PrintableMixin:
    def __repr__(self):
        key_values = ','.join(map(lambda item: f'{item[0]}->{item[1]}', self._public_member))
        return f'{self.__class__.__name__}({key_values})'

    @property
    def _public_member(self):
        return filter(lambda item: not (callable(item[1]) or item[0].startswith('_')),
                      self.__dict__.items())


class LoggableMixin:
    def __init__(self, *args, **kwargs):
        self._log = getLogger(self.__class__.__name__)
        self.info = self._log.info
        self.debug = self._log.debug
