#!/usr/bin/env python3
import sys
from bottle import *
from colorama import Fore

app = Bottle()

@app.post('/test/webhook')
def webhook():
    #print('Message: %r' % request.json, file=sys.stderr)
    print('%sMessage: %s%s' % (Fore.YELLOW, Fore.RESET, request.json['text']))

run(app, port=9999)
