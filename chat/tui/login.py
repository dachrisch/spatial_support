from __future__ import annotations

from functools import partial
from threading import Thread
from typing import Dict

from py_cui import PyCUI

from chat.entity.account import EmailAccount, UnauthenticatedEmailAccount, FileAccount
from chat.tui.space import SpaceSelectWidgetSet
from support.mixin import LoggableMixin


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
            authenticated_account = unauthenticated_account.validate_by_magic_code(magic_code)
            SpaceSelectWidgetSet(self.cui, authenticated_account).activate()
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
