#!/usr/bin/env python3

import io
import json
import re
import sys
import time
from contextlib import redirect_stdout, redirect_stderr
from subprocess import run, PIPE
from typing import Iterable, Sequence
from cqhttp import CQHttp
from util import argv, open, AttrDict
from tracking import solve_captcha, Tracking

bot = CQHttp('http://localhost:5700/')
api = Tracking()


def unescape(text: str) -> str:
    'Remove the escape codes.'
    escape_codes = '''
        & &amp;
        [ &#91;
        ] &#93;
        , &#44;
    '''
    escape_codes = [line.split() for line in escape_codes.strip().splitlines()]

    text = re.sub(r'\[CQ:.+?\]', '', text)
    for symbol, codes in escape_codes:
        text = text.replace(codes, symbol)
    return text


@bot.on_event('group_increase')
def new_group_member(context):
    'Send the welcome message.'
    bot.send(context, message='群地位-1', is_raw=True)


@bot.on_request('group', 'friend')
def new_friend(context):
    'Accepts friend requests.'
    return {'approve': True}


@bot.on_message()
def new_msg_wrapper(context):
    'Wraps the message event.'
    context = AttrDict(context)
    context.notified = '[CQ:at,qq=%d]' % context.self_id in context.message
    context.message = unescape(context.message)
    # print(dict(context))

    value = new_msg(context)
    if value is None:
        return
    elif isinstance(value, dict):
        return value
    else:
        return {'reply': value, 'at_sender': False}


def new_msg(context):
    'The message event handler.'
    railway_groups = [151576768]
    administrators = [1395231174]
    if context.user_id in administrators:
        parse_tracking(context)
        return parse_shell(context)
    elif context.get('group_id') in railway_groups:
        parse_tracking(context)


def parse_shell(context) -> str:
    'Provide Python and Bash shells.'
    if context.message.startswith('$'):
        proc = run(context.message[1:], shell=True, stdout=PIPE)
        return proc.stdout.decode(sys.getfilesystemencoding()).strip()

    elif context.message.startswith('>>>'):
        result = io.StringIO()
        with redirect_stdout(result), redirect_stderr(result):
            print('\n-->', eval(context.message[3:]))
        return result.getvalue().strip()

    elif context.message.startswith('//'):
        limit.power_off = not limit.power_off
        if limit.power_off:
            return '下班了，明天见~'

    elif context.message_type == 'private':
        return 'Roger'


def parse_tracking(context):
    'Provide railway shipment tracking service.'
    numbers = re.findall(r'(?a)(?<!\d)\d{7}(?!\d)', context.message)
    models = re.findall(r'(?a)(?<!\w)[A-Z]\w+(?!\w)', context.message)
    unknown = []

    if context.notified:
        for model in models:
            if model in known_models:
                numbers.append(known_models[model])
            else:
                unknown.append(model)

    if numbers or unknown:
        if limit.power_off:
            bot.send(context, '下班喽~')
            return
        if limit():
            bot.send(context, '哼，不理你了!')
            return
        roger = (
            '、'.join(unknown) + ' 是什么车哦，没见过呢' if unknown
            else '好的，知道了' if models else '好的'
        )
        bot.send(context, roger)
        for result in batch_tracking(numbers):
            bot.send(context, result)


def batch_tracking(cars: Sequence[str]) -> Iterable[str]:
    'Response railway shipment queries.'
    api.query['check_code'] = solve_captcha(api.load_captcha())
    for car in cars:
        try:
            info = api.track_car(car)
        except AssertionError as e:
            yield e.args[0]
        else:
            if info.carType:
                known_models[info.carType] = info.carNo
            yield api.explain(info)


class Limit(AttrDict):
    'Limit the request rate.'

    def __init__(self, rate=1.5, per=60):
        allowance = rate  # unit: messages
        last_check = time.monotonic()
        self.update(locals())

    def __call__(self) -> bool:
        now = time.monotonic()
        self.allowance += (now - self.last_check) / self.per * self.rate
        self.last_check = now
        if self.allowance > self.rate:
            self.allowance = self.rate  # throttle
        if self.allowance < 1:
            return True
        else:
            self.allowance -= 1
            return False


def main(database: str):
    'Load the known car models.'
    global limit
    limit = Limit()
    limit.power_off = False

    global known_models
    try:
        with open(database) as f:
            known_models = json.load(f)
    except Exception:
        known_models = {}

    bot.run(host='localhost', port=7700)
    with open(database, 'w') as f:
        json.dump(known_models, f)


if __name__ == '__main__':
    main(argv(1) or 'tracking.json')