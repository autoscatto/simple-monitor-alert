import datetime
import os

import logging

import json

import dateutil
import dateutil.tz
import six

from simple_monitor_alert import __version__
from simple_monitor_alert.alerts import Alerts
from simple_monitor_alert.lines import ItemLine, Observable, get_observables_from_lines
from simple_monitor_alert.monitor import Monitors, log_evaluate

if six.PY2:
    from ConfigParser import ConfigParser
else:
    from configparser import ConfigParser, NoSectionError


logger = logging.getLogger('sma')

var_directory = '/var/lib/simple-monitor-alert'


def validate_write_dir(directory, log=lambda x: x):
    if os.path.lexists(directory) and os.access(directory, os.W_OK):
        return True
    if os.path.lexists(directory) and not os.path.exists(directory):
        log('{} exists but the destination does not exist. Is a broken link?'.format(directory))
        return False
    try:
        os.makedirs(directory)
    except OSError:
        log('No write permissions to the directory {}.'.format(directory))
        return False
    return False


def create_file(path, content=''):
    if not isinstance(content, six.string_types):
        content = json.dumps(content)
    if not os.path.exists(path):
        with open(path, 'w') as f:
            f.write(content)
    return path


if not validate_write_dir(var_directory, logger.warning):
    valid_candidate = False
    for candidate in [os.path.expanduser('~/.local/var/lib/simple-monitor-alert'), '/tmp/simple-monitor-alert']:
        if validate_write_dir(candidate):
            valid_candidate = True
            logger.info('Usign {} directory for var content, but {} is recommended.'.format(candidate, var_directory))
            var_directory = candidate
            break
    if not valid_candidate:
        import getpass
        OSError('{} is not writable by {} user'.format(var_directory, getpass.getuser()))

# noinspection PyTypeChecker
results_file = create_file(os.path.join(var_directory, 'results.json'), {
    'version': __version__,
    'monitors': {},  # {'since': ..., 'last_update': ...}
})


class Config(ConfigParser):
    def __init__(self, file):
        self.file = file
        super(Config, self).__init__()
        self.read(self.file)

    def get_monitor_observables(self, name):
        try:
            lines = self.items(name)
        except NoSectionError:
            return []
        lines = [ItemLine(key, value) for key, value in lines]
        return get_observables_from_lines(lines)

    def get_observable(self, monitor_name, observable_name, group_name=None):
        monitor = self.get_monitor_observables(monitor_name)
        if not monitor:
            return
        return monitor.get((observable_name, group_name), None)


class JSONFile(dict):
    def __init__(self, path, **kwargs):
        super(JSONFile, self).__init__(**kwargs)
        self.path = path
        self.read()

    def read(self):
        self.clear()
        self.update(json.load(open(self.path)))

    def write(self):
        json.dump(self, open(self.path, 'w'), sort_keys=True, indent=4, separators=(',', ': '))


class ObservableResults(JSONFile):

    @staticmethod
    def get_default_observable_result():
        return {
            'since': None, 'updated_at': None, 'fail': None, 'executions': 0, 'alerted': []
        }

    def update_observable_result(self, observable, fail, notified=False):
        result = self.get_observable_result(observable)
        result['updated_at'] = datetime.datetime.now(dateutil.tz.tzlocal()).isoformat()
        if fail != result['fail']:
            result['since'] = result['updated_at']
            result['alerted'] = []
        result['fail'] = fail
        result['executions'] += 1

    def get_observable_result(self, observable):
        monitor_name = observable.monitor.name
        if monitor_name not in self['monitors']:
            self['monitors'][monitor_name] = {}
        monitor = self['monitors'][monitor_name]
        result = monitor.get(observable.name, self.get_default_observable_result())
        monitor[observable.name] = result
        return result

    def add_alert_to_observable_result(self, observable, alert):
        result = self.get_observable_result(observable)
        if alert not in result['alerted']:
            result['alerted'].append(alert)
            return True
        return False


class SMA(object):
    def __init__(self, monitors_dir=None, alerts_dir=None, config_file=None):
        self.config = Config(config_file)
        self.results = ObservableResults(results_file)
        self.monitors = Monitors(monitors_dir, self.config)
        self.alerts = Alerts(self, alerts_dir)

    def evaluate_and_alert(self):
        observables = self.evaluate_all()
        fail_observables = [observable for (observable, result) in observables if not result]
        self.alert_all(fail_observables)

    def alert_all(self, observables, fail=True):
        for observable in observables:
            notified = self.alerts.send_alerts(observable, fail)
        self.results.write()

    def execute_all(self):
        return self.monitors.execute_all()

    def evaluate_all(self):
        observables = self.execute_all()
        for observable in observables:
            result = observable.evaluate()
            self.results.update_observable_result(observable, not result)
            log_evaluate(observable, result)
            yield observable, result
        self.results.write()