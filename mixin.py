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
    def __init__(self,*args,**kwargs):
        self.info = getLogger(self.__class__.__name__).info
        self.debug = getLogger(self.__class__.__name__).debug