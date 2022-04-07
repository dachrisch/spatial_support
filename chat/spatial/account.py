from __future__ import annotations

import json
from logging import getLogger
from typing import Optional

from cattr import unstructure, structure
from requests import Session

from chat.entity.account import AccountSecret
from chat.entity.space import Space
from chat.spatial.api import SpatialApiConnector
from support.mixin import LoggableMixin


class AuthenticatedAccount(LoggableMixin):

    def __init__(self, sap: SpatialApiConnector, account_secret: AccountSecret, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sap = sap
        self.secret = account_secret
        self.info(f'authenticated account [{self.secret.email}]')

    def list_spaces(self):
        spaces_json = self.sap.list_space_visited()
        visited_spaces = [Space.from_dict(space_json, self.sap) for space_json in spaces_json]
        self.info(f'list visited spaces: {visited_spaces}')
        return visited_spaces

    def to_file(self, filename: str):
        with open(filename, 'w') as file:
            json.dump(unstructure(self.secret), file)


class FileAccount(LoggableMixin):
    def __init__(self, secret: AccountSecret, sap: Optional[SpatialApiConnector] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
            getLogger(cls.__name__).info(f'creating account from file [{filename}]: {secret.email}')
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
