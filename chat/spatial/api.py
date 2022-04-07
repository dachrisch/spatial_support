from __future__ import annotations

import json
from functools import lru_cache
from typing import List, Dict, Any, Optional

from requests import Session

from chat.entity.account import AccountSecret, AccountProfile
from chat.spatial.param import SpaceConnection
from support.mixin import LoggableMixin


class SpatialApiConnector(LoggableMixin):
    headers = {'x-client-version': '1', 'content-type': 'application/json'}

    def __init__(self, session: Session):
        super().__init__()
        self._session = session

    @lru_cache
    def list_space_visited(self) -> List[Dict[Any, Any]]:
        spaces_json = self._validated_put('https://spatial.chat/api/SpaceVisited/listSpaceVisited')
        assert 'spaces' in spaces_json, spaces_json
        return spaces_json['spaces']

    def register_account(self, email: str) -> str:
        account_json = self._validated_put('https://spatial.chat/api/Account/registerAccount',
                                           json_payload={'email': email})
        assert 'authKey' in account_json
        return account_json['authKey']

    def get_account_profile(self) -> AccountProfile:
        account_json = self._validated_put('https://spatial.chat/api/Account/getAccountProfile')
        assert 'accountId' in account_json
        return AccountProfile.from_json(account_json)

    def auth_account_by_magic_link(self, auth_key: str, magic_code: str) -> str:
        self._validated_put('https://spatial.chat/api/Account/authAccountByMagicLink', json_payload={
            'code': magic_code,
            'authKey': auth_key
        })
        assert AccountSecret.COOKIE_FIELD in self._session.cookies
        return self._session.cookies.get(AccountSecret.COOKIE_FIELD)

    def join_room(self, space_connection: SpaceConnection, room_id: str):
        self._validated_put('https://spatial.chat/api/SpaceOnline/joinRoom',
                            json_payload={'connectionId': space_connection.connection_id,
                                          'spaceId': space_connection.space_id, 'roomId': room_id})

    def send_room_chat(self, space_connection: SpaceConnection, room_id: str, message_text: str):
        self._validated_put('https://spatial.chat/api/SpaceOnlineRoomChat/postRoomChatMessage',
                            json_payload={'connectionId': space_connection.connection_id,
                                          'spaceId': space_connection.space_id, 'roomId': room_id,
                                          'content': message_text})

    def delete_chat_message(self, space_connection: SpaceConnection, room_id: str, message_id: str):
        self._validated_put('https://spatial.chat/api/SpaceOnlineRoomChat/deleteRoomChatMessage',
                            json_payload={'connectionId': space_connection.connection_id,
                                          'spaceId': space_connection.space_id, 'roomId': room_id,
                                          'messageId': message_id})

    def _validated_put(self, uri: str, json_payload: Optional[Dict[Any, Any]] = None) -> Dict[Any, Any]:
        if json_payload:
            # XXX: that bug cost me hours of lifetime - the api hangs if there are whitespaces in the json string. what the f*ck
            put_data = json.dumps(json_payload).replace(', "', ',"').replace(': "', ':"')
        else:
            put_data = ''
        self.debug(f'-X PUT {uri} -d\'{put_data}\'')
        json_response = self._session.put(uri, data=put_data, headers=self.headers, timeout=3).json()
        self.debug(json_response)
        assert 'success' in json_response, json_response
        return json_response['success']

    def authenticate(self, secret: AccountSecret):
        secret.inject_cookies(self._session.cookies)

    def terminate(self):
        self._session.close()
