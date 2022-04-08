from datetime import timedelta, datetime
from unittest import TestCase

import pytz
from benedict.dicts import benedict

from chat.entity.messages import to_relative_duration, ChatMessage


class TestChatMessageDisplay(TestCase):

    def setUp(self) -> None:
        super().setUp()
        self.berlin_tz = pytz.timezone('Europe/Berlin')
        self.test_time = datetime(2022, 1, 25, 15, 10, 11, 222000)

    def test_relative_timedelta(self):
        self.assertEqual('now', to_relative_duration(timedelta()))
        self.assertEqual('-1m', to_relative_duration(timedelta(minutes=1)))
        self.assertEqual('-2m', to_relative_duration(timedelta(minutes=2)))
        self.assertEqual('-1h', to_relative_duration(timedelta(hours=1)))
        self.assertEqual('-3h', to_relative_duration(timedelta(hours=3)))
        self.assertEqual('-1d', to_relative_duration(timedelta(days=1)))
        self.assertEqual('-24d', to_relative_duration(timedelta(days=24, hours=3)))
        self.assertEqual('>1y', to_relative_duration(timedelta(days=356, hours=3)))

    def test_do_not_create_with_tz_in_constructor(self):
        self.assertEqual('LMT', datetime(2022, 1, 25, 15, 10, 11, 222000, self.berlin_tz).tzname(),
                         'we do not want this')

    def test_do_not_create_as_timezone(self):
        as_timezone = self.test_time.astimezone(self.berlin_tz)
        if 15 == as_timezone:
            self.assertEqual(self.test_time, as_timezone,
                             'special case where this might work (local tz matches target tz)')
        else:
            self.assertNotEqual(self.test_time.tzname(), as_timezone.tzname())

    def test_correct_way_creating_tz_aware_datetime(self):
        self.assertEqual('CET', self.berlin_tz.localize(self.test_time).tzname(),
                         'we DO want this')

    def test_convert_from_json(self):
        self.assertEqual(
            ChatMessage('test name', 'test message', self.berlin_tz.localize(datetime(2022, 1, 25, 15, 10, 11, 222000)),
                        self.berlin_tz, '123'),
            ChatMessage.from_json(benedict({
                'created': {'account': {'account': {'name': 'test name'}},
                            'date': '2022-01-25T14:10:11.222Z'},
                'state': {'active': {'content': 'test message'}},
                'id': '123'
            })))

    def test_message_age(self):
        message = ChatMessage('test name', 'test message', self.berlin_tz.localize(datetime.now()), self.berlin_tz,
                              '123')

        self.assertEqual('now', message.age)
