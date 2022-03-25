from __future__ import annotations

from attr import define, field
from requests.cookies import RequestsCookieJar


@define
class AccountSecret:
    COOKIE_FIELD = 'authorization'
    email = field()
    auth_code = field()

    def __init__(self, email: str, auth_code: str):
        self.auth_code = auth_code
        self.email = email

    def inject_cookies(self, cookies):
        cookies.set(self.COOKIE_FIELD, self.auth_code)

    @classmethod
    def from_cookies(cls, email: str, cookies: RequestsCookieJar):
        auth_code = cookies.get(cls.COOKIE_FIELD)
        return AccountSecret(email, auth_code)