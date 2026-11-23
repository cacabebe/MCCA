"""Real recognizer/pipeline regression for advancing past completed story stages.

Run: python/python.exe tests/verify_main_story.py (no emulator input).
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_pipeline as base


class StoryScreen(base.CustomController):
    def __init__(self):
        super().__init__()
        self.reset()

    def reset(self, state='cleared', no_new=False, stuck_confirm=False,
              cleared_battle=False):
        self.state = state
        self.no_new = no_new
        self.stuck_confirm = stuck_confirm
        self.cleared_battle = cleared_battle
        self.clicks = []
        self.selected = 0
        self.replays = 0

    def connect(self): return True
    def request_uuid(self): return 'offline-main-story'
    def get_features(self): return 0

    def screencap(self):
        name = {'cleared': 'main-cleared-story', 'selected': 'main-selected-stage',
                'story': 'main-story', 'confirm': 'main-skip-confirm',
                'victory': 'main-victory', 'team': 'main-team'}[self.state]
        if self.state == 'cleared' and self.cleared_battle:
            name = 'main-selected-stage'
        frame = base.fixture(name)
        if self.state == 'cleared' and self.no_new:
            frame[315:350, 380:420] = 0
        return frame

    def click(self, x, y):
        self.clicks.append((self.state, x, y))
        if self.state == 'cleared':
            if 380 <= x <= 420 and 315 <= y <= 350:
                assert not self.no_new
                self.selected += 1
                self.state = 'selected'
            else:
                assert 1070 <= x <= 1230 and 590 <= y <= 680, self.clicks
                self.replays += 1
                self.state = 'story'
        elif self.state == 'story':
            assert 1110 <= x <= 1210 and 18 <= y <= 62, self.clicks
            self.state = 'confirm'
        elif self.state == 'confirm':
            assert 796 <= x <= 808 and 443 <= y <= 455, self.clicks
            if not self.stuck_confirm:
                self.state = 'cleared'
        elif self.state == 'victory':
            assert 630 <= x <= 650 and 430 <= y <= 450, self.clicks
            self.state = 'cleared'
        elif self.state == 'selected':
            # A selected stage still has a New marker: never select it again.
            assert 1110 <= x <= 1260 and 620 <= y <= 700, self.clicks
            self.state = 'team'
        elif self.state == 'team':
            assert 1080 <= x <= 1240 and 620 <= y <= 700, self.clicks
        return True


class VerifyStory(base.CustomAction):
    failure = None

    def run(self, ctx, argv):
        try:
            frame = base.fixture('main-cleared-story')
            for node in ('主线_新关卡', '主线_开始播放'):
                assert ctx.run_recognition(node, frame).hit, node

            fast = {name: {'pre_delay': 0, 'post_delay': 0,
                           'pre_wait_freezes': 0, 'post_wait_freezes': 0,
                           'rate_limit': 0, 'timeout': 600}
                    for name in base.all_nodes}
            fast['主线_开始行动']['next'] = []

            # Reproduce the original priority bug against the same screenshot.
            legacy = copy.deepcopy(fast)
            order = list(base.all_nodes['主线_入口']['next'])
            order.remove('主线_开始播放')
            order.insert(order.index('主线_新关卡'), '主线_开始播放')
            legacy['主线_入口']['next'] = order
            legacy['主线_开始播放']['next'] = []
            story.reset()
            result = ctx.run_task('主线_入口', legacy)
            assert result and result.status.succeeded
            assert story.replays == 1 and story.selected == 0, story.clicks
            print('PASS: original priority reproduces S7-17 replay', flush=True)

            # Explicitly restore any fields changed by the legacy child context.
            fast['主线_入口']['next'] = base.all_nodes['主线_入口']['next']
            fast['主线_开始播放']['next'] = base.all_nodes['主线_开始播放']['next']
            for state in ('cleared', 'story', 'confirm', 'victory'):
                story.reset(state)
                result = ctx.run_task('主线_入口', fast)
                assert result and result.status.succeeded, (state, story.clicks)
                assert story.selected == 1 and story.replays == 0, story.clicks
                assert story.state == 'team', story.clicks
            print('PASS: completed story, resumed dialogue, confirmation and victory advance once', flush=True)

            for state, battle in [('story', False), ('victory', False), ('victory', True)]:
                story.reset(state, no_new=True, cleared_battle=battle)
                result = ctx.run_task('主线_入口', fast)
                assert result and result.status.failed, (state, result)
                assert story.replays == 0 and story.selected == 0, story.clicks
            print('PASS: no next stage stops without replaying or fighting again', flush=True)

            story.reset('confirm', stuck_confirm=True)
            result = ctx.run_task('主线_入口', fast)
            assert result and result.status.failed, result
            assert len(story.clicks) == 1, story.clicks
            print('PASS: unresponsive confirmation stops after one click', flush=True)
            return True
        except Exception:
            self.failure = base.traceback.format_exc()
            print(self.failure, flush=True)
            return False


story = StoryScreen()
assert story.post_connection().wait().succeeded
tasker = base.Tasker()
tasker.bind(base.res, story)
verify = VerifyStory()
base.res.register_custom_action('VerifyStory', verify)
job = tasker.post_task('__verify_story', {
    '__verify_story': {'action': 'Custom', 'custom_action': 'VerifyStory'}})
started = base.time.monotonic()
while not job.done and base.time.monotonic() - started < 60:
    base.time.sleep(.1)
if not job.done:
    tasker.post_stop().wait()
    raise RuntimeError('Main-story regression timed out')
assert not verify.failure and job.succeeded
print('All main-story regression tests passed.', flush=True)
