"""Real OCR and disconnected-controller regression for fixed-stage farming.

Run: python/python.exe tests/verify_main_farm.py
Also runs the shared pipeline regressions. No emulator or game resources are used.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_pipeline as base

nodes = base.all_nodes


class FarmScreen(base.CustomController):
    def __init__(self):
        super().__init__()
        self.reset()

    def reset(self, hidden=False, missing=False):
        self.state = 'chapters'
        self.hidden = hidden
        self.missing = missing
        self.clicks = []
        self.swipes = []

    def connect(self): return True
    def request_uuid(self): return 'offline-main-farm'
    def get_features(self): return 0

    def screencap(self):
        frame = base.fixture('farm-' + self.state)
        if self.state == 'map' and (self.hidden or self.missing):
            # Hide only the region name; preserve the map/difficulty markers.
            frame[525:590, 830:1010] = 0
        return frame

    def click(self, x, y):
        self.clicks.append((self.state, x, y))
        if self.state == 'chapters':
            assert 490 <= x <= 760 and 640 <= y <= 720, (self.state, x, y)
            self.state = 'chapter-expanded'
        elif self.state == 'chapter-expanded':
            assert 470 <= x <= 660 and 410 <= y <= 470, (self.state, x, y)
            self.state = 'map'
        elif self.state == 'map':
            if y >= 650 and x < 100:
                pass  # Explicitly select normal difficulty.
            else:
                assert not (self.hidden or self.missing), 'Clicked hidden region'
                assert 800 <= x <= 1020 and 520 <= y <= 600, (self.state, x, y)
                self.state = 'stages'
        else:
            assert 160 <= x <= 300 and 90 <= y <= 160, (self.state, x, y)
        return True

    def swipe(self, x1, y1, x2, y2, duration):
        assert self.state == 'map'
        assert x2 < x1 and y2 < y1, 'Map must be dragged towards upper left'
        self.swipes.append((x1, y1, x2, y2))
        self.hidden = False
        return True


class VerifyFarm(base.CustomAction):
    failure = None

    def run(self, ctx, argv):
        try:
            for image, node in [
                ('farm-chapters', '刷主线_第七章'),
                ('farm-chapter-expanded', '刷主线_进入第七章'),
                ('farm-map', '刷主线_普通难度'),
                ('farm-map', '刷主线_米德加尔特'),
                ('farm-stages', '刷主线_关卡78'),
                ('fuel-supply', '刷主线_燃料不足'),
                ('farm-stage-detail', '刷主线_扫荡'),
                ('farm-stage-detail', '刷主线_扫荡结束'),
                ('farm-sweep-dialog', '刷主线_检查燃料-白'),
                ('farm-sweep-dialog', '刷主线_开始战斗'),
                ('farm-sweep-result', '刷主线_扫荡成功'),
                ('farm-sweep-result', '刷主线_扫荡成功-检查'),
            ]:
                result = ctx.run_recognition(node, base.fixture(image))
                assert result and result.hit, (image, node, result)
            stages = base.fixture('farm-stages')
            stages[80:200, 0:430] = 0
            assert not ctx.run_recognition('刷主线_关卡78', stages).hit, 'Other stages must not match'
            for image in ('main-combat', 'home', 'main-team', 'farm-stages'):
                assert not ctx.run_recognition('刷主线_向左上拖动1', base.fixture(image)).hit
                assert not ctx.run_recognition('刷主线_第七章', base.fixture(image)).hit
                assert not ctx.run_recognition('刷主线_进入第七章', base.fixture(image)).hit
            for image in ('farm-stage-detail', 'farm-sweep-dialog'):
                assert not ctx.run_recognition('刷主线_扫荡成功', base.fixture(image)).hit
            print('PASS: supplied chapter/map/stage screenshots and wrong-stage negatives', flush=True)

            fast = {name: {'pre_delay': 0, 'post_delay': 0, 'pre_wait_freezes': 0,
                           'post_wait_freezes': 0, 'rate_limit': 0, 'timeout': 200}
                    for name in nodes}
            # Stop exactly after selecting 7-8; the references contain no detail page.
            fast['刷主线_关卡78']['next'] = []
            for hidden, missing, expected_swipes in [(False, False, 0), (True, False, 1), (True, True, 3)]:
                farm.reset(hidden=hidden, missing=missing)
                result = ctx.run_task('刷主线_入口', fast)
                assert bool(result and result.status.succeeded) == (not missing), result
                assert len(farm.swipes) == expected_swipes, farm.swipes
                assert (farm.state == 'stages') == (not missing), farm.state
            print('PASS: visible region, upper-left drag recovery, bounded missing-region failure', flush=True)
            return True
        except Exception:
            self.failure = base.traceback.format_exc()
            print(self.failure, flush=True)
            return False


farm = FarmScreen()
assert farm.post_connection().wait().succeeded
tasker = base.Tasker()
tasker.bind(base.res, farm)
verify = VerifyFarm()
base.res.register_custom_action('VerifyFarm', verify)
job = tasker.post_task('__verify_farm', {'__verify_farm': {'action': 'Custom', 'custom_action': 'VerifyFarm'}})
started = base.time.monotonic()
while not job.done and base.time.monotonic() - started < 60:
    base.time.sleep(.1)
if not job.done:
    tasker.post_stop().wait()
    raise RuntimeError('Main-farm navigation regression timed out')
assert not verify.failure and job.succeeded

# Verify the independent fuel/count graph against real sweep screenshots, including
# a prior task enabling shared fuel usage. The farm must not reach those nodes.
tasker.bind(base.res, base.ctrl)
fast = {name: {'pre_delay': 0, 'post_delay': 0, 'pre_wait_freezes': 0,
               'post_wait_freezes': 0, 'rate_limit': 0, 'timeout': 1000} for name in nodes}
fast['刷主线_开始战斗']['next'] = []
fast['使用燃料界面']['enabled'] = True
for count, low, expected in [(10, False, [6]), (1, True, [])]:
    base.ctrl.reset(count=count, low=low)
    job = tasker.post_task('刷主线_扫荡次数选择', fast).wait()
    assert job.succeeded and base.ctrl.started == expected, base.ctrl.started
    if low:
        assert base.ctrl.closed
reachable, pending = set(), ['刷主线_扫荡']
while pending:
    name = pending.pop()
    if name in reachable: continue
    reachable.add(name)
    for field in ('next', 'on_error'):
        refs = nodes[name].get(field, [])
        pending.extend([refs] if isinstance(refs, str) else refs)
assert all(name.startswith('刷主线_') for name in reachable), reachable
assert '刷主线_扫荡' in nodes['刷主线_扫荡结束']['next']
print('PASS: independent natural-fuel adjustment and insufficient-fuel stop')


class SettlementScreen(base.CustomController):
    """Actual game screenshots, with clicks that reflect observed UI transitions."""
    def __init__(self):
        super().__init__()
        self.state = 'stage-detail'
        self.completed = 0

    def connect(self): return True
    def request_uuid(self): return 'offline-farm-settlement'
    def get_features(self): return 0
    def screencap(self): return base.fixture('farm-' + self.state)

    def click(self, x, y):
        if self.state == 'stage-detail':
            assert 860 <= x <= 935 and 620 <= y <= 690, (self.state, x, y)
            self.state = 'sweep-dialog'
        elif self.state == 'sweep-dialog':
            assert 960 <= x <= 1060 and 540 <= y <= 580, (self.state, x, y)
            self.state = 'sweep-result'
        elif self.state == 'sweep-result':
            # The center panel swallows clicks. Only the title/left panel closes it.
            assert 40 <= x <= 370 and 40 <= y <= 130, (self.state, x, y)
            self.completed += 1
            self.state = 'stage-detail'
        return True


class TwoBatches(base.CustomAction):
    def run(self, ctx, argv):
        if settlement.completed == 2:
            assert ctx.override_next('刷主线_扫荡结束', [])
        return True


settlement = SettlementScreen()
assert settlement.post_connection().wait().succeeded
tasker.bind(base.res, settlement)
two_batches = TwoBatches()
base.res.register_custom_action('TwoBatches', two_batches)
settlement_override = {name: {'pre_delay': 0, 'post_delay': 0, 'pre_wait_freezes': 0,
                            'post_wait_freezes': 0, 'rate_limit': 0, 'timeout': 1000}
                       for name in nodes}
settlement_override['刷主线_扫荡_达到次数上限'].update(
    recognition='TemplateMatch', template='扫荡次数1.png', roi=[200, 490, 160, 105], threshold=.98)
settlement_override['刷主线_扫荡结束'].update(action='Custom', custom_action='TwoBatches')
job = tasker.post_task('刷主线_扫荡', settlement_override)
started = base.time.monotonic()
while not job.done and base.time.monotonic() - started < 30:
    base.time.sleep(.1)
if not job.done:
    tasker.post_stop().wait()
    raise RuntimeError('Main-farm settlement regression timed out')
assert job.succeeded and settlement.completed == 2 and settlement.state == 'stage-detail'
print('PASS: real settlement screenshots, title click, automatic restart and second batch')
print('All main-farm tests passed.')
