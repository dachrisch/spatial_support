from typing import List, Dict, Any
from unittest import TestCase

from chat.spatial.api import SpatialApiConnector
from chat.entity.account import AuthenticatedAccount, EmailAccount
from chat.entity.secret import AccountSecret
from chat.entity.space import Space


class SpatialApiConnectorMock(SpatialApiConnector):
    def __init__(self):
        super().__init__(None)

    def register_account(self, email: str) -> str:
        return 'authKey-1234'

    def auth_account_by_magic_link(self, auth_key: str, magic_code: str) -> str:
        assert 'authKey-1234' == auth_key
        assert 'magicCode-1234' == magic_code
        return 'authCode-1234'

    def list_space_visited(self) -> List[Dict[Any, Any]]:
        return [{'space': {'id': '1234', 'name': 'Test Space', 'slug': 'test-space'}}, ]

    def authenticate(self, secret: AccountSecret):
        assert 'authCode-4567' == secret.auth_code


class TestRegisterAccount(TestCase):
    def setUp(self) -> None:
        self.sap=SpatialApiConnectorMock()

    def test_register_account_by_email(self):
        account = EmailAccount('test@t.d', self.sap)
        registered_account = account.register()
        authenticated_account = registered_account.validate_by_magic_code('magicCode-1234')
        self.assertIn(Space.from_dict({'space': {'id': '1234', 'name': 'Test Space', 'slug': 'test-space'}},self.sap),
                      authenticated_account.list_spaces())

    def test_authenticate_session_from_secret(self):
        secret = AccountSecret('test@t.d', 'authCode-4567')
        self.sap.authenticate(secret)
        self.assertIn(Space.from_dict({'space': {'id': '1234', 'name': 'Test Space', 'slug': 'test-space'}}, self.sap),
                      AuthenticatedAccount(self.sap, secret).list_spaces())
