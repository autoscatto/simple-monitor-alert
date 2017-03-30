#!/usr/bin/env python
__version__ = '0.1.0'

import os

import telegram
import sys
import six


from simple_monitor_alert.sma import get_var_directory, JSONFile
from simple_monitor_alert.utils.files import create_file, JSONFile

if sys.version_info >= (3,2):
    from html import escape
else:
    from cgi import escape

from simple_monitor_alert.alerts import AlertBase


SUPPORT_ALERT_IMPORT = True
DEFAULT_MESSAGE = """\
{hostname} [{level}]
<strong>{name}</strong>
    {extra_info}

    Observable: {observable_name}
    {condition_status} condition: {condition}
"""


LEVELS = {
    None: b'\xE2\x9C\x85',  # Resolved
    'info': b'\xE2\x84\xB9',
    'warning': b'\xF0\x9F\x94\xB4',
    'average': b'\xE2\x9D\x8C',
    'high': b'\xE2\x9D\x97',
    'disaster': b'\xE2\x80\xBC',
}

class Telegram(AlertBase):
    bot = None

    def init(self):
        token = self.config.get('token')
        self.bot = telegram.Bot(token)


    def send(self, subject, message, observable_name='', name='', extra_info=None, level='warning', fail=True,
             condition='', hostname=None, observable=None):
        if observable_name:
            icon = LEVELS.get(level)
            condition_status = 'Failed' if fail else 'Successful'
            level = level.upper()
            scope = locals()
            message = DEFAULT_MESSAGE.format(**{key: (escape(value) if isinstance(value, six.string_types) else value)
                                                for key, value in scope.items()})
            message = message.encode('utf-8')
            message = icon + message 
        else:
            message = '<b>{subject}</b>\n{message}'.format(subject=escape(subject), message=escape(message))
            message = message.encode('utf-8', 'ignore')
        self.bot.sendMessage(chat_id=self.config['to'], text=message.decode('utf-8'), parse_mode='html')
        return True

Alert = Telegram

if __name__ == '__main__':
    Alert(os.environ).send(sys.argv[1], sys.argv[2])
