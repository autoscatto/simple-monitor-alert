import os
import importlib
import logging

from future.moves import sys

from simple_monitor_alert.monitor import get_verbose_condition

logger = logging.getLogger('sma')


DEFAULT_MESSAGE = """\
{name}
{extra_info}

Observable: {observable_name}
{condition_status} condition: {condition}
"""

class AlertBase(object):
    def __init__(self, config, section):
        self.config = config
        self.section = section
        self.init()

    def init(self):
        pass


class AlertCommand(AlertBase):
    pass


class ObservableCommunication(dict):
    alert_kwargs_keys = ('observable_name', 'name', 'extra_info', 'level', 'fail', 'condition')

    def __init__(self, observable, fail, **kwargs):
        super(ObservableCommunication, self).__init__(**kwargs)
        self.observable = observable
        self['fail'] = fail
        self['level'] = self.observable.get_line_value('level', 'warning')
        self['subject'] = '[{}] {}'.format('ERROR' if fail else 'SOLVED', observable.get_verbose_name())
        self['name'] = observable.get_verbose_name()
        self['observable_name'] = observable.name
        self['extra_info'] = observable.get_line_value('extra_info') or '(No more info available)'
        self['condition'] = get_verbose_condition(observable)
        self['message'] = self.get_message()

    def get_message(self):
        return DEFAULT_MESSAGE.format(condition_status='Failed' if self['fail'] else 'Successful', **self)

    def alert_kwargs(self):
        return {key: value for key, value in self.items() if key in self.alert_kwargs_keys}



class Alerts(list):
    def __init__(self, sma, alerts_dir):
        super(Alerts, self).__init__()
        self.sma = sma
        self.config = sma.config
        self.alerts_dir = alerts_dir
        sys.path.append(alerts_dir)
        self.valid_alerts = self.get_valid_alerts()
        self.get_alerts()

    def get_alerts_config(self):
        for section in self.config.sections():
            if self.config.has_option(section, 'alert'):
                alert = self.config.get(section, 'alert')
                if not alert in self.valid_alerts:
                    logger.warning('Invalid alert value {} for section {} in {}'.format(alert, section,
                                                                                        self.config.file))
            elif section in self.valid_alerts:
                alert = section
            else:
                continue
            yield alert, dict(self.config.items(alert)), section

    def _import_python_alert(self, alert, config, section):
        if not self.valid_alerts[alert].endswith('.py'):
            return
        module = importlib.import_module(alert)
        if getattr(module, 'SUPPORT_ALERT_IMPORT'):
            return getattr(module, 'Alert')(config, section)

    def _get_alert_command(self, alert, config, section):
        raise NotImplementedError

    def get_alerts(self):
        self.clear()
        for alert, alert_config, section in self.get_alerts_config():
            module = self._import_python_alert(alert, alert_config, section) or \
                     self._get_alert_command(alert, alert_config, section)
            self.append(module)

    def get_valid_alerts(self):
        return {os.path.splitext(f)[0]: os.path.join(self.alerts_dir, f) for f in os.listdir(self.alerts_dir)}

    def send_alerts(self, observable, fail=True):
        communication = ObservableCommunication(observable, fail)
        for alert in self:
            if alert.section in self.sma.results.get_observable_result(observable)['alerted']:
                continue
            success = alert.send(communication['subject'], communication['message'], **communication.alert_kwargs())
            if success:
                self.sma.results.add_alert_to_observable_result(observable, alert.section)
        return True