from datetime import timedelta, datetime
from unittest import TestCase

import pytz
from benedict.dicts import benedict

from chat.entity.messages import to_relative_duration, ChatMessage, to_datetime


class TestChatMessageDisplay(TestCase):
    def test_relative_timedelta(self):
        self.assertEqual('now', to_relative_duration(timedelta()))
        self.assertEqual('-1m', to_relative_duration(timedelta(minutes=1)))
        self.assertEqual('-2m', to_relative_duration(timedelta(minutes=2)))
        self.assertEqual('-1h', to_relative_duration(timedelta(hours=1)))
        self.assertEqual('-3h', to_relative_duration(timedelta(hours=3)))
        self.assertEqual('-1d', to_relative_duration(timedelta(days=1)))
        self.assertEqual('-24d', to_relative_duration(timedelta(days=24, hours=3)))
        self.assertEqual('>1y', to_relative_duration(timedelta(days=356, hours=3)))

    def test_to_date(self):
        berlin_tz = pytz.timezone('Europe/Berlin')
        test_time = berlin_tz.localize(datetime(2022, 1, 25, 15, 10, 11, 222000))
        self.assertEqual(15, test_time.hour)
        self.assertEqual(test_time,
                         to_datetime('2022-01-25T14:10:11.222Z', berlin_tz))

    def test_convert_from_json(self):
        berlin_tz = pytz.timezone('Europe/Berlin')
        self.assertEqual(
            ChatMessage('test name', 'test message', berlin_tz.localize(datetime(2022, 1, 25, 15, 10, 11, 222000)),
                        berlin_tz, '123'),
            ChatMessage.from_json(benedict({
                'created': {'account': {'account': {'name': 'test name'}},
                            'date': '2022-01-25T14:10:11.222Z'},
                'state': {'active': {'content': 'test message'}},
                'id': '123'
            })))

    def test_message_age(self):
        berlin_tz = pytz.timezone('Europe/Berlin')

        message = ChatMessage('test name', 'test message', datetime.now().astimezone(berlin_tz), berlin_tz, '123')

        self.assertEqual('now', message.age)
