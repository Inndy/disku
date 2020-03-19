#!/usr/bin/env python3
import argparse
import os

template = '''\
[uwsgi]
uid = {group}
gid = {user}

plugins = python3

chdir = {dir}
python-path = {dir}
env = DISKU_LOG_LEVEL=ERROR
env = DISKU_LOG_FILE={dir}/disku.log
module = server:app

master = true

processes = 1
threads = 1
'''

parser = argparse.ArgumentParser(description='Generate uwsgi config file')

parser.add_argument('-u', '--user', help='User to run uwsgi service', default=os.getenv('USER'))
parser.add_argument('-g', '--group', help='Group to run uwsgi service', default='www-data')
parser.add_argument('-d', '--dir', help='Disku installation dir', default=os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
parser.add_argument('-o', '--out', help='Output filename', type=argparse.FileType('w'), default='disku.ini')

args = parser.parse_args()

print(template.format(user=args.user, group=args.group, dir=args.dir), end='', file=args.out)
