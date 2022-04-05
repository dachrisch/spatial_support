from abc import abstractmethod
from typing import final

from py_cui import PyCUI
from py_cui.widget_set import WidgetSet


class WidgetSetActivator(WidgetSet):
    def __init__(self, cui: PyCUI, *args, **kwargs):
        WidgetSet.__init__(self, *args, root=cui, **kwargs)
        self.cui = cui

    @final
    def activate(self):
        self.cui.apply_widget_set(self)
        self.on_activate()

    @abstractmethod
    def on_activate(self):
        raise NotImplementedError
