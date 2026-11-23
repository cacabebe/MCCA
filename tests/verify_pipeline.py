"""Regression tests using the real Maa recognizer and a disconnected mock controller.

Run: python/python.exe tests/verify_pipeline.py
Requires the local diagnostic dependencies in debug/tools (maafw 5.0.5, Pillow).
No ADB connection, emulator input, or game resources are used by these tests.
"""
import os,sys,json,pathlib,time,traceback
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'debug/tools'))
os.environ['MAAFW_BINARY_PATH']=str(ROOT/'runtimes/win-x64/native')
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
from PIL import Image
from maa.controller import CustomController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.custom_action import CustomAction
from maa.toolkit import Toolkit

def fixture(name):
    return np.array(Image.open(ROOT/'tests/fixtures'/f'{name}.png').convert('RGB'))[:,:,::-1].copy()

class Screen(CustomController):
    def __init__(self):
        self.reset()
        super().__init__()
    def reset(self,count=10,low=False):
        self.count=count; self.low=low; self.started=[]; self.closed=False; self.home_mode=False
        self.shop_frames = []
        self.shop_step = 0
    def connect(self): return True
    def request_uuid(self): return 'offline-regression'
    def get_features(self): return 0
    def screencap(self):
        if self.shop_frames:
            return fixture(self.shop_frames[self.shop_step][0])
        if self.home_mode: return fixture('home' if self.closed else 'promo')
        return fixture(f'fuel-low-{self.count}' if self.low else f'sweep-{self.count}')
    def click(self,x,y):
        if self.shop_frames:
            sample, target = self.shop_frames[self.shop_step]
            assert target is not None, f'Unexpected click on {sample}: {(x,y)}'
            assert abs(target[0]-x) <= 8 and abs(target[1]-y) <= 8, (sample, x, y)
            self.shop_step += 1
            return True
        if self.home_mode:
            assert 1105<=x<=1130 and 132<=y<=160, f'Unexpected home click {(x,y)}'
            self.closed=True
            return True
        if 238 <= x <= 260 and 548 <= y <= 578: self.count=max(1,self.count-1)
        elif 536 <= x <= 563 and 548 <= y <= 578: self.count=min(10,self.count+1)
        elif 940 <= x <= 1080 and 530 <= y <= 590: self.started.append(self.count)
        elif 630 <= x <= 650 and 70 <= y <= 90: self.closed=True
        else: raise AssertionError(f'Unexpected click {(x,y)}')
        return True


def verify_weekly_shop(ctx, fast):
    cases = [
        ('周购_灰域传说券列表', '周购_灰域罕见券列表', [
            ('shop-gray', (355, 250)), ('shop-ticket', (1001, 429)),
            ('shop-ticket-max', (879, 537)), ('shop-reward', (638, 647)),
            ('shop-gray', None),
        ]),
        ('周购_核对购买内容', None, [
            ('shop-blueprint', (879, 537)), ('shop-reward', (638, 647)),
            ('shop-gray', None),
        ]),
        ('周购_罕见下排蓝图列表', '周购_前往军演', [('shop-rare-sold', None)]),
        ('周购_核对购买内容', None, [
            ('shop-micro-limited', (1001, 429)), ('shop-micro-limited', (879, 537)),
            ('shop-reward', (638, 647)), ('shop-rare-sold', None),
        ]),
        ('周购_核对购买内容', None, [
            ('shop-micro-unlimited', (1027, 145)), ('shop-rare-sold', None),
        ]),
    ]
    for entry, end, frames in cases:
        ctrl.reset()
        ctrl.shop_frames = frames
        override = dict(fast)
        if end is not None:
            override[end] = {**fast[end], 'action': 'DoNothing', 'next': []}
        result = ctx.run_task(entry, override)
        assert result and result.status.succeeded and ctrl.shop_step == len(frames)-1, (entry, ctrl.shop_step)
    print('PASS: weekly shop purchases batches, single items, and limited microcrystals, and skips sold-out and unlimited offers', flush=True)

all_nodes={}
for p in (ROOT/'resource/base/pipeline').glob('*.json'):
    data=json.loads(p.read_text(encoding='utf-8-sig'))
    assert not (all_nodes.keys() & data.keys()), f'duplicate node in {p}'
    all_nodes.update(data)
interface=json.loads((ROOT/'interface.json').read_text(encoding='utf-8-sig'))
for name,node in all_nodes.items():
    roi=node.get('roi')
    if isinstance(roi,list) and len(roi)==4 and all(isinstance(n,int) for n in roi):
        x,y,w,h=roi
        assert x>=0 and y>=0 and w>=0 and h>=0 and x+w<=1280 and y+h<=720, (name,roi)
    for key in ('next','on_error','interrupt'):
        refs=node.get(key,[]); refs=[refs] if isinstance(refs,str) else refs
        for ref in refs: assert ref in all_nodes, f'{name}.{key}: missing {ref}'
active_options={name for task in interface['task'] for name in task.get('option',[])}
for option in active_options:
    group=interface['option'][option]
    for case in group['cases']:
        for name,node in case.get('pipeline_override',{}).items():
            assert name in all_nodes, f'option creates undefined node: {name}'
            for key in ('next','on_error','interrupt'):
                refs=node.get(key,[]); refs=[refs] if isinstance(refs,str) else refs
                for ref in refs: assert ref in all_nodes, f'option references missing node: {ref}'
print('PASS: pipeline and option references')

Toolkit.init_option(str(ROOT/'debug/offline-tests'),{'logging':True,'stdout_level':0})
res=Resource(); res.use_cpu()
assert res.post_bundle(str(ROOT/'resource/base')).wait().succeeded
ctrl=Screen(); assert ctrl.post_connection().wait().succeeded
tasker=Tasker(); tasker.bind(res,ctrl)

class Verify(CustomAction):
    failure=None
    def run(self,ctx,argv):
        try:
            cases=[
                ('fuel-low-1','检查燃料-红',True),
                ('fuel-low-1','检查燃料-白',False),
                ('fuel-low-1','检查燃料-红（次数为1）',True),
                ('fuel-low-2','检查燃料-红（次数为1）',False),
                ('sweep-6','检查燃料-白',True),
                ('sweep-7','检查燃料-红',True),
                ('sweep-10','扫荡_达到次数上限',True),
                ('sweep-9','扫荡_达到次数上限',False),
                ('fuel-supply','使用10燃料',True),
                ('fuel-item','使用10燃料2',True),
                ('promo','子任务_关闭星贸凭证',True),
                ('home','子任务_关闭星贸凭证',False),
                ('idle','子任务_退出待机',True),
                ('home','子任务_退出待机',False),
                ('arena-empty','模拟军演_免费次数用尽',True),
                ('arena-empty','模拟军演_刷新次数用尽',False),
            ]
            for i in range(1,4):
                cases.extend([('combat',f'ActivityExploration_CombatEnd{i}',False),('victory',f'ActivityExploration_CombatEnd{i}',True)])
            cases.extend([
                ('main-victory','主线_胜利',True),
                ('main-new-character','主线_获得角色',True),
                ('main-chapter-complete','主线_章节完成',True),
                ('main-story','主线_跳过剧情',True),
                ('main-skip-confirm','主线_跳过确认',True),
                ('main-new','主线_新关卡',True),
                ('main-hard-list','主线_新关卡',True),
                ('main-hard-four-stages','主线_新关卡',True),
                ('main-stage','主线_开始战斗',True),
                ('main-team','主线_开始行动',True),
                ('fuel-supply','主线_燃料不足',True),
            ])
            for name,node in all_nodes.items():
                if name.startswith('主线_') and node.get('recognition'):
                    cases.append(('main-combat',name,False))
            for image in ('main-victory','main-story','main-skip-confirm','main-new','main-stage','main-team','fuel-supply','home'):
                cases.append((image,'主线_获得角色',False))
            for image,node,expected in cases:
                result=ctx.run_recognition(node,fixture(image))
                assert result is not None and result.hit == expected, (image,node,expected)
            print(f'PASS: {len(cases)} visual recognition regressions',flush=True)
            # Remove animation delays only. Recognition and actions remain real pipeline code.
            fast={name:{'pre_delay':0,'post_delay':0,'pre_wait_freezes':0,'post_wait_freezes':0,'rate_limit':0,'timeout':3000} for name in all_nodes}
            fast['开始战斗']={'next':[],'pre_wait_freezes':0,'post_delay':0}
            fast['进入首页']={'next':[]}
            for index,case in enumerate(interface['option']['手动次数']['cases']):
                ctrl.reset(count=10)
                override={k:dict(v) for k,v in fast.items()}
                override['自选扫荡次数'].update(enabled=True)
                for n in range(1,11): override[f'自选-次数{n}'].update(enabled=False)
                for k,v in case['pipeline_override'].items(): override[k].update(v)
                result=ctx.run_task('自选扫荡次数',override)
                assert result and result.status.succeeded and ctrl.started==[index+1], (index+1,ctrl.started)
            print('PASS: all 10 manual counts, including reset from previous count 10',flush=True)
            ctrl.reset(count=10)
            result=ctx.run_task('扫荡次数选择',fast)
            assert result and result.status.succeeded and ctrl.started==[6], ctrl.started
            print('PASS: natural fuel reduces 10 to affordable 6',flush=True)
            ctrl.reset(count=1,low=True)
            result=ctx.run_task('扫荡次数选择',fast)
            assert result and result.status.succeeded and not ctrl.started and ctrl.closed
            print('PASS: insufficient fuel exits without starting a sweep',flush=True)
            ctrl.reset(); ctrl.home_mode=True
            # Use a fresh child context, restoring the real home navigation after the sweep tests.
            navigation={name:{'pre_delay':0,'post_delay':0,'pre_wait_freezes':0,'post_wait_freezes':0,'rate_limit':0,'timeout':3000} for name in all_nodes}
            navigation['进入首页'].update(all_nodes['进入首页'])
            result=ctx.run_task('进入首页',navigation)
            assert result and result.status.succeeded and ctrl.closed
            print('PASS: promo closes before home is accepted; no extra home click',flush=True)
            verify_weekly_shop(ctx, fast)
            return True
        except Exception:
            self.failure=traceback.format_exc(); print(self.failure,flush=True); return False

verify=Verify(); res.register_custom_action('Verify',verify)
job=tasker.post_task('__verify',{'__verify':{'action':'Custom','custom_action':'Verify'}})
started=time.monotonic()
while not job.done and time.monotonic()-started<120: time.sleep(.1)
if not job.done: tasker.post_stop().wait(); raise RuntimeError('Regression test timed out')
assert not verify.failure and job.succeeded
print('All regression tests passed.')
