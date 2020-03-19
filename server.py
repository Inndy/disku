#!/usr/bin/env python3
import argparse
import logging
import os

from bottle import *

import disku

logger = disku.get_logger('disku-server')
default_app = app = Bottle()

def load_config(config_file_path):
    if not config_file_path or not os.path.exists(config_file_path):
        return

    if config_file_path.endswith('.py'):
        app.config.load_module(config_file_path)
    else:
        app.config.load_config(config_file_path)

def init_server():
    load_config(os.path.join(os.path.dirname(__file__), 'config.ini'))
    load_config(os.getenv('DISKU_CONFIG_FILE'))

    alert_interval = disku.parse_time_interval(app.config.get('disku.alert_interval'))
    logger.debug('alert_interval = %ds', alert_interval)

    app.config['alert_checker'] = disku.AlertCheck(app.config.get('disku.alert_conditions'))
    app.config['alert_buffer'] = disku.AlertBuffer(alert_interval, fire_alerts)

def fire_alerts(buffer):
    alert_channel = disku.AlertChannel.load(app.config)
    alert_channel.fire('\n\n'.join(buffer.values()))

@app.post('/disku/report', name='reporting')
def report():
    if not request.json or \
            'client_info' not in request.json or \
            'disk_usage' not in request.json:
        response.status = 400
        return

    response.add_header('Content-Type', 'text/plain')

    client = request.json['client_info']
    client_name = client.get('identifier') or client.get('hostname')
    disk_usage = request.json['disk_usage']

    logger.info('Got report from %r, usage: %r', client, disk_usage)

    msgs = []
    for path, usage in disk_usage.items():
        try:
            cond = app.config['alert_checker'](usage)
        except ValueError as e:
            logger.exception('Error during checker, usage: %r', usage)
            continue

        if cond:
            msgs.append(app.config['disku.alert_msg'].format(
                machine=client_name,
                path=path,
                condition=cond,
                usage=usage
            ))

    if msgs:
        app.config['alert_buffer'].push(client_name, '\n'.join(msgs))

    return '\n'.join(msgs)

def get_url(route_name):
    return '%s://%s%s' % (
        request.urlparts.scheme,
        request.urlparts.netloc,
        app.get_url(route_name))

@app.get('/config')
def dump_config():
    if app.config.get('disku.debug') == 'true':
        response.add_header('Content-Type', 'text/plain')
        return '\n'.join('%s => %r' % (k, v) for k, v in app.config.items())

@app.get('/')
def index():
    response.add_header('Content-Type', 'text/plain')

    return '''\
DISKU - disk usage monitor utility
==================================

* Project home: https://github.com/Inndy/disku
* Download agent from {url_download}
* Config your agent reporting to {url_report}

Example of agent usage:

  ./agent.py -u {url_report} /
'''.format(
        url_download=get_url('download_agent'),
        url_report=get_url('reporting'),
    )

@app.get('/agent.py', name='download_agent')
def download_agent():
    return static_file('disku-agent.py', os.path.dirname(__file__), 'text/x-python')

init_server()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DISKU server')
    parser.add_argument('-b', '--bind', help='Which address to bind',
                        default='127.0.0.1')
    parser.add_argument('-p', '--port', help='Which port to bind', type=int,
                        default=8080)

    args = parser.parse_args()

    run(app, host=args.bind, port=args.port, server='waitress')
