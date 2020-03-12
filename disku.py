import json
import logging
import os
import re
import sys
import time

import requests

def get_logger(name):
    log_file = os.getenv('DISKU_LOG_FILE')
    if log_file:
        log_handler = logging.FileHandler(log_file)
    else:
        log_handler = logging.StreamHandler(sys.stdout)

    log_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        '%Y-%m-%d %H:%M:%S %Z'
    ))

    logger = logging.getLogger(name)
    logger.setLevel(os.getenv('DISKU_LOG_LEVEL', 'ERROR'))
    logger.addHandler(log_handler)
    return logger

logger = get_logger(__name__)
logger.debug('DISKU module loaded')

class CaseInsensitiveDict(dict):
    def __repr__(self):
        return 'CaseInsensitiveDict(%r)' % super().__repr__()

    def _find_key(self, key):
        # XXX: iterate over self.keys() is slow
        lkey = key.lower()

        for k in self.keys():
            if k.lower() == lkey:
                return k

        return key

    def __lower_keys__(self):
        # FIXME: handle collisions
        return [k.lower() for k in self.keys()]

    def __contains__(self, key):
        # XXX: performance issue
        return self._find_key(key) in self.__lower_keys__()

    def __getitem__(self, key):
        return super().__getitem__(self._find_key(key))

    def __setitem__(self, key, val):
        return super().__setitem__(self._find_key(key), val)

    def __delitem__(self, key):
        return super().__delitem__(self._find_key(key))

    def get(self, key, defval=None):
        return super().get(self._find_key(key), defval)

class ConfigProxy:
    # TODO: it's read-only, what about set() and __setitem__?
    # consider implement full MutableMapping iter
    def __init__(self, src, namespace):
        # XXX: namespace will become case-insensitive too
        self.src = CaseInsensitiveDict(src)
        self.namespace = namespace

    def key(self, k):
        return '%s.%s' % (self.namespace, k)

    def __contains__(self, key):
        return self.key(k) in self.src

    def __getitem__(self, key):
        return self.src[self.key(key)]

    def get(self, key, defval=None):
        return self.src.get(self.key(key), defval)

def _find_subclass(parent, name):
    name = (name + parent.__name__).lower()

    for klass in parent.__subclasses__():
        if klass.__name__.lower() == name:
            return klass
        raise KeyError('Can not find subclass of %s (name: %s)' % (parent.__name__, name))

class BinaryOperator:
    def __init__(self, op):
        self.op = op
        # FIXME: potential code injection vulnerability
        # should we make a whitelist of allowed operators?
        # *current usage is not vulnerable
        self.f = eval('lambda l, r: l %s r' % op)

    def __call__(self, l, r):
        return self.f(l, r)

    def __repr__(self):
        return 'BinaryOperator(%r)' % self.op

def parse_size_string(s, suffixes='KMGTPEZY'):
    suffix_idx = suffixes.find(s[-1].upper())
    if suffix_idx == -1:
        return int(s)

    return int(s[:-1]) * (1024 ** (suffix_idx + 1))

def parse_time_interval(s):
    suffixes = {
        's': 1,
        'm': 60,
        'h': 60*60,
        'd': 60*60*24,
    }

    try:
        return int(s)
    except ValueError:
        pass

    re_obj = r'(?P<val>[1-9]\d*)(?P<unit>[smhd])'

    if not re.fullmatch('(?:(?:{})+|\s)+'.format(re_obj), s):
        raise ValueError('Invalid time value', s)

    t = 0
    for m in re.finditer(re_obj, s):
        val, unit = m.groups()
        t += int(val) * suffixes[unit]

    return t

class AlertCheck:
    def __init__(self, conditions):
        self.conditions = []
        if not self.parse(conditions):
            raise ValueError('Invalid condition(s): %r' % conditions)

    def parse(self, conditions):
        def parse_val(v):
            if v[-1] == '%':
                return int(v[:-1]) / 100.0
            return parse_size_string(v)

        re_cmp = re.compile(
            r'(?P<var>\w+)'       # variable name
            r'\s*'                # spaces are allowed
            r'(?P<op>[<>]=?|==)'  # compare operator
            r'\s*'                # spaces are allowed
            r'(?P<val>'           # begin value group
            r'100%|0%|[1-9]\d?%|' # percentage
            r'[1-9]\d*[KMGTP]?'   # size
            r')'                  # end value group
            )

        for cond in re.split(r'\s*,\s*', conditions):
            m = re.fullmatch(re_cmp, cond)
            if not m:
                logger.error('Can not parse condition: %s', cond)
                return False

            raw = m.group(0)
            var, op, val = m.groups()
            self.conditions.append((var, BinaryOperator(op), parse_val(val), raw))
            logger.debug('Parsed condition: %s %s %s', var, op, val)

        return True

    @staticmethod
    def validate_params(disk_usage):
        return 'used' in disk_usage and \
               'free' in disk_usage and \
               'total' in disk_usage

    def __call__(self, disk_usage):
        du = CaseInsensitiveDict(disk_usage)
        if not self.validate_params(du):
            raise ValueError('Invalid disk usage status object')
        du['used_p'] = du['used'] / du['total']
        du['free_p'] = du['free'] / du['total']

        for var, op, val, raw in self.conditions:
            if isinstance(val, float):
                var += '_p'

            if op(du.get(var), val):
                return raw

        return False

class AlertChannel:
    '''
    Abstraction class for alert channels
    '''
    _channel_cache = {}

    @classmethod
    def load(cls, config):
        name = config['disku.alert_channel']
        cached = cls._channel_cache.get(name)
        if cached:
            return cached
        try:
            klass = _find_subclass(cls, name)
        except KeyError:
            logger.error('Can not find AlertChannel sublcass: %s', name)
            raise

        instance = klass(ConfigProxy(config, name.lower()))
        instance.prepare()
        return cls._channel_cache.setdefault(name, instance)

    def __init__(self, config):
        self.config = config

    def prepare(self):
        pass

    def fire(self, message):
        raise NotImplemented()

class WebhookAlertChannel(AlertChannel):
    '''
    Webhook alert channel provider, it's made for Slack/Mattermost compatible
    webhook interface
    '''

    def prepare(self):
        try:
            self.mixin = json.loads(self.config.get('mixin', '{}'))
            logger.info('mixin: %r', self.mixin)
        except json.decoder.JSONDecodeError:
            self.mixin = {}

    def fire(self, message):
        data = dict(self.mixin)
        data.update({'text': message})
        logger.debug('webhook sent message: %r', data)

        try:
            resp = requests.post(self.config['url'], json=data)
            logger.debug('response: %r', resp)
            return resp.status_code == 200
        except Exception as e:
            logger.exception('Error during sending http request: %r', e)
            return False

class AlertBuffer:
    def __init__(self, interval, fire):
        self.interval = interval
        self.next_time = 0
        self.buffer = {}
        self.fire = fire

    def push(self, identifier, data):
        self.buffer[identifier] = data

        if time.time() >= self.next_time:
            logger.info('Flushing buffer')
            self.fire(self.buffer)
            self.buffer = {}
            self.next_time = time.time() + self.interval

def test():
    try:
        checker = AlertCheck('FREE == 100G, FREE   <\t 5G, USED     >10G, USED>95%')
        logger.info('Success!')
    except ValueError as e:
        logger.exception('Can not parse condition, error: %r', e)

    for c in checker.conditions:
        logger.info(c)

    GB = 2 ** 30

    logger.info(checker({ 'total': 100 * GB, 'used': 96 * GB, 'free': 4 * GB }))
    logger.info(checker({ 'total': 100 * GB, 'used': 90 * GB, 'free': 10 * GB }))
    logger.info(checker({ 'total': 100 * GB, 'used': 9 * GB, 'free': 91 * GB }))
    logger.info(checker({ 'total': 100 * GB, 'used': 0 * GB, 'free': 100 * GB }))

    for t in '5 10s 10m 2h 1d 24h9d 1s1m1h 1s2m3h4d'.split():
        logger.info('%-10s %d', t, parse_time_interval(t))

if __name__ == '__main__':
    test()
