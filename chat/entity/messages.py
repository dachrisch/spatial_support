from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Any

import pytz as pytz
from attr import define, field

from chat.entity.account import ChatAccount


@define
class LeaveMessage:
    leave = {}


def to_relative_duration(delta: timedelta):
    if delta.total_seconds() >= 60 * 60 * 24 * 356:
        return '>1y'
    elif delta.total_seconds() >= 60 * 60 * 24:
        return f'-{delta.total_seconds() / (60 * 60 * 24):.0f}d'
    elif delta.total_seconds() >= 60 * 60:
        return f'-{delta.seconds / (60 * 60):.0f}h'
    elif delta.total_seconds() >= 60:
        return f'-{delta.seconds / 60:.0f}m'
    else:
        return 'now'


def to_datetime(datetime_str: str, local_tz) -> datetime:
    utc_tz = pytz.timezone('UTC')
    utc_time = datetime.fromisoformat(datetime_str[:-1])
    return local_tz.normalize(utc_tz.localize(utc_time))


@define(hash=True)
class ChatMessage:
    author_name: str = field()
    message: str = field()
    created: datetime = field()
    timezone: pytz.timezone = field()
    message_id = field()

    @classmethod
    def from_json(cls, chat_json: Dict[Any, Any], local_tz=pytz.timezone('Europe/Berlin')) -> ChatMessage:
        return ChatMessage(chat_json['created.account.account.name'],
                           chat_json['state.active.content'],
                           to_datetime(chat_json['created.date'], local_tz),
                           local_tz,
                           chat_json['id']
                           )

    @property
    def age(self):
        now = datetime.now(self.timezone)
        return to_relative_duration(now - self.created)


@define
class DirectChat:
    chat_account: ChatAccount = field()

    @classmethod
    def from_json(cls, chat_json: Dict[Any, Any]):
        return DirectChat(ChatAccount.from_json(chat_json['account']))
