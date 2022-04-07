from __future__ import annotations

import json
from logging import getLogger
from typing import Optional, List

from attr import define, field
from cattr import unstructure, structure
from requests import Session

from chat.entity.account import AccountSecret
from chat.entity.space import Space
from chat.spatial.api import SpatialApiConnector
from support.mixin import LoggableMixin


@define
class AuthenticatedAccount(LoggableMixin):
    sap: SpatialApiConnector = field(repr=False)
    account_secret: AccountSecret = field()

    def __attrs_post_init__(self):
        self.info(f'authenticated account [{self.account_secret.email}]')

    def list_spaces(self) -> List[Space]:
        spaces_json = self.sap.list_space_visited()
        visited_spaces = [Space.from_dict(space_json, self.sap) for space_json in spaces_json]
        self.info(f'list visited spaces: {visited_spaces}')
        return visited_spaces

    def to_file(self, filename: str):
        with open(filename, 'w') as file:
            json.dump(unstructure(self.account_secret), file)


@define
class FileAccount(LoggableMixin):
    account_secret: AccountSecret = field()
    sap: Optional[SpatialApiConnector] = field(repr=False, default=None)

    def __enter__(self):
        return self.authenticate()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.sap.terminate()

    def authenticate(self):
        if not self.sap:
            self.sap = SpatialApiConnector(Session())
        self.sap.authenticate(self.account_secret)
        return AuthenticatedAccount(self.sap, self.account_secret)

    @classmethod
    def from_file(cls, filename: str) -> FileAccount:
        with open(filename, 'r') as file:
            secret = structure(json.load(file), AccountSecret)
            getLogger(cls.__name__).info(f'creating account from file [{filename}]: {secret.email}')
            return FileAccount(secret)


@define
class UnauthenticatedEmailAccount:
    email: str = field()
    sap: SpatialApiConnector = field(repr=False)
    auth_key: str = field(repr=False)
    remaining_tries: int = field(default=3)

    def validate_by_magic_code(self, magic_code: str) -> AuthenticatedAccount:
        self.remaining_tries -= 1
        auth = self.sap.auth_account_by_magic_link(self.auth_key, magic_code)
        return AuthenticatedAccount(self.sap, AccountSecret(self.email, auth))


@define
class EmailAccount:
    email: str = field()
    sap: Optional[SpatialApiConnector] = field(repr=False, default=None)

    headers = {'x-client-version': '-1'}

    def __enter__(self) -> UnauthenticatedEmailAccount:
        return self.register()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.sap.terminate()

    def register(self) -> UnauthenticatedEmailAccount:
        if not self.sap:
            self.sap = SpatialApiConnector(Session())
        auth_key = self.sap.register_account(self.email)
        return UnauthenticatedEmailAccount(self.email, self.sap, auth_key)
