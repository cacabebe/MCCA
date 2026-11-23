"""Run the same main-story pipeline as the GUI; Ctrl+C or --stop stops it."""
import argparse
import json
import msvcrt
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'debug/tools'))
os.environ['MAAFW_BINARY_PATH'] = str(ROOT / 'runtimes/win-x64/native')
os.chdir(ROOT)
sys.stdout.reconfigure(encoding='utf-8')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stop', action='store_true')
parser.add_argument('--serial', help='ADB serial; defaults to current MCCA device')
args = parser.parse_args()
state = ROOT / 'debug/main-story'
state.mkdir(parents=True, exist_ok=True)
stop = state / 'stop'
if args.stop:
    stop.touch()
    print('Stop requested.')
    sys.exit(0)

# Prevent two standalone runners from controlling the same game.
lock = (state / 'runner.lock').open('a+b')
lock.seek(0)
try:
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
except OSError:
    sys.exit('Main-story runner is already active.')
stop.unlink(missing_ok=True)

from maa.toolkit import Toolkit
from maa.resource import Resource
from maa.controller import AdbController
from maa.tasker import Tasker
from maa.context import ContextEventSink
from PIL import Image
import numpy as np

out = state / time.strftime('%Y%m%d-%H%M%S')
out.mkdir()
Toolkit.init_option(str(out), {'logging': True, 'stdout_level': 0})
Tasker.set_stdout_level(0)
Tasker.set_debug_mode(True)
res = Resource()
res.use_cpu()
assert res.post_bundle(str(ROOT / 'resource/base')).wait().succeeded
device = json.loads((ROOT / 'config/config.json').read_text(encoding='utf-8'))['AdbDevice']
ctrl = AdbController(device['AdbPath'], args.serial or device['AdbSerial'],
                     screencap_methods=4, input_methods=1)
assert ctrl.post_connection().wait().succeeded
tasker = Tasker()
tasker.bind(res, ctrl)

class Trace(ContextEventSink):
    last = None
    def on_raw_notification(self, context, message, details):
        if message == 'Node.Action.Succeeded':
            self.last = details.get('name')
            with (out / 'events.jsonl').open('a', encoding='utf-8') as f:
                f.write(json.dumps({'time': time.time(), **details}, ensure_ascii=False) + '\n')
            if self.last != '主线_入口':
                print(self.last, flush=True)

trace = Trace()
tasker.add_context_sink(trace)
print(f'Running on {args.serial or device["AdbSerial"]}; logs: {out}', flush=True)
job = tasker.post_task('主线_入口')
reason = 'finished'
previous = None
unchanged_since = time.monotonic()
last_probe = 0
last_recovery = 0
recoveries = 0
try:
    while not job.done:
        if stop.exists():
            reason = 'user_stop'
            break
        now = time.monotonic()
        if now - last_probe >= 3:
            last_probe = now
            if ctrl.post_screencap().wait().succeeded:
                frame = ctrl.cached_image
                small = np.asarray(Image.fromarray(frame).convert('L').resize((160, 90)), dtype=np.int16)
                changed = previous is None or np.mean(np.abs(small - previous)) > 1.0
                previous = small
                if changed:
                    unchanged_since = now
                elif (now - unchanged_since >= 10 and now - last_recovery >= 60
                      and recoveries < 3 and not job.done and not stop.exists()):
                    # Upper central background, away from bottom buttons and top-right controls.
                    Image.fromarray(frame[:, :, ::-1]).save(out / f'recovery-{recoveries + 1}.png')
                    print('画面静止10秒，尝试点击两次空白处', flush=True)
                    for _ in range(2):
                        if job.done or stop.exists():
                            break
                        ctrl.post_click(round(frame.shape[1] * 0.5), round(frame.shape[0] * 0.2)).wait()
                        time.sleep(0.6)
                    recoveries += 1
                    last_recovery = time.monotonic()
                    unchanged_since = last_recovery
                    previous = None
        time.sleep(0.5)
except KeyboardInterrupt:
    reason = 'user_stop'
finally:
    if not job.done:
        tasker.post_stop().wait()
    if ctrl.post_screencap().wait().succeeded:
        Image.fromarray(ctrl.cached_image[:, :, ::-1]).save(out / 'final.png')
    result = {'reason': reason, 'succeeded': job.succeeded and reason != 'user_stop',
              'last_node': trace.last}
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
