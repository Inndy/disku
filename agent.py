#!/usr/bin/env python3
import argparse
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import textwrap
import uuid
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen, Request

PYTHON_VERSION = (sys.version_info.major, sys.version_info.minor)
logger = logging.getLogger(__name__)

EXIT_ERR_CONFIG = 1
EXIT_ERR_NETWORK = 2
EXIT_ERR_RESPONSE = 3
EXIT_ERR_ENV = 4

def which(prog, ext_paths=['/sbin', '/usr/sbin']):
    paths = os.getenv('PATH', os.defpath).split(os.pathsep)
    for path in paths + ext_paths:
        path = os.path.abspath(os.path.join(path, prog))
        if os.path.exists(path):
            return path

    return None

def run(cmd, *args):
    if '/' not in cmd:
        cmd = which(cmd)

    args = list(args)
    args.insert(0, cmd)

    env = dict(os.environ)
    env['LC_ALL'] = 'C'

    return subprocess.check_output(args, env=env).decode('utf8').rstrip('\n')

def parse_ip_cmd_result(output, keys=None):
    pattern = r'(?:^|[\s\r\n])(?P<key>{0}) (?P<val>[^ \n]+)(?:[\s\r\n]|$)'.format('|'.join(keys))
    return dict(m.groups() for m in re.finditer(pattern, output))

def get_route_info(ip):
    result = run('ip', '-o', '-d', 'route', 'get', ip)
    return parse_ip_cmd_result(result, ['dev', 'src', 'via'])

def get_interface(iname):
    result = run('ip', '-o', '-d', 'addr', 'show', iname)
    return parse_ip_cmd_result(result, [r'link/(?:ether|loopback|ieee802\.11)', 'inet', 'inet6'])

def find_mac_address(interface):
    if not interface:
        return None

    for k, v in interface.items():
        if k.startswith('link/'):
            return v

    return None

def collect_info(host=None, allow_external_program=False):
    route = interface = None

    # TODO: Windows? Unix-like environment without `ip` cmd?
    if allow_external_program and host and which('ip'):
        try:
            route = get_route_info(host)
            logger.debug('Got route info to host')
        except Exception as e:
            logger.warning('Can not get route info to host, err: %r', e)

        try:
            interface = get_interface(route['dev'])
            logger.debug('Got interface info')
        except Exception as e:
            interface = None
            logger.warning('Can not get interface info, err: %r', e)

    uuid_mac = ':'.join(textwrap.wrap('%.12x' % uuid.getnode(), 2))

    return {
        'route': route,
        'interface': interface,
        'hostname': socket.gethostname(),
        'platform': platform.platform(),
        'mac_address': find_mac_address(interface) or uuid_mac,
    }

def _usage_to_dict(u):
    return {'total': u.total, 'used': u.used, 'free': u.free}

def check_disk_usage(paths):
    return {path: _usage_to_dict(shutil.disk_usage(path)) for path in paths}

def main():
    log_file_path = os.getenv('DISKU_LOG_FILE')
    if log_file_path:
        log_file = open(log_file_path, 'a')
    else:
        log_file = sys.stdout

    logging.basicConfig(stream=log_file,
                        level=os.getenv('DISKU_LOG_LEVEL', 'ERROR'),
                        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S %Z')

    if PYTHON_VERSION < (3, 5):
        logger.error('Python 3.5+ required')
        sys.exit(EXIT_ERR_ENV)

    parser = argparse.ArgumentParser(description='Monitor disk usage and report to host')
    parser.add_argument('-u', '--url', required=True, help='Which host to report disk usage')
    parser.add_argument('-n', '--no-external-program', action='store_true',
                        default=False, help='Disable usage of external program'
                        ' (e.g. `ip`) to collect client info '
                        '(MAC addr, ip address, ...)\n'
                        '(External program was enabled by default)')
    parser.add_argument('paths', nargs='+', help='List of paths to check disk usage')
    parser.add_argument('-i', '--identifier', help='Unique name to help you identify '
                        'which machine triggered alarm')

    args = parser.parse_args()
    logger.debug('Parsed arg: %r', args)

    url_info = urlparse(args.url)
    if not url_info.hostname:
        url_info = urlparse('http://' + args.url)

    if url_info.scheme not in ('http', 'https'):
        logger.error('Invalid url scheme: %s', url_info.scheme)
        sys.exit(EXIT_ERR_CONFIG)

    logger.debug('Parsed URL: %r', url_info)

    try:
        host_ip = socket.gethostbyname(url_info.hostname)
    except socket.gaierror:
        logger.exception('Can not resolve hostname: %s', url_info.hostname)
        sys.exit(EXIT_ERR_NETWORK)

    client_info = collect_info(host_ip, allow_external_program=not args.no_external_program)
    client_info.update({'identifier': args.identifier})

    data = {
        'client_info': client_info,
        'disk_usage': check_disk_usage(args.paths),
    }

    logger.debug('Collected data: %r', data)

    request = Request(url=args.url,
                      data=json.dumps(data).encode('ascii'),
                      headers={
                          'Content-Type': 'application/json'
                      })

    try:
        response = urlopen(request)
    except URLError as e:
        logger.exception('Request failed: %r', e)
        sys.exit(EXIT_ERR_NETWORK)
    except ConnectionRefusedError:
        logger.exception('Can not connect to host')
        sys.exit(EXIT_ERR_NETWORK)
    except Exception as e:
        logger.exception('Unexpected exception: %r', e)
        sys.exit(EXIT_ERR_NETWORK)

    if 200 <= response.getcode() <= 299:
        logger.info('Report success with response code: %d', response.getcode())
    else:
        logger.warning('Unexptect response code: %d', response.getcode())
        sys.exit(EXIT_ERR_RESPONSE)

if __name__ == '__main__':
    logger = logging.getLogger('disku-agent')
    main()
