# 离线回归

在 Windows 发布包目录下执行。使用源码仓库时，先将 `assets/` 下的 `interface.json` 和 `resource/`，以及仓库根目录的 `tests/` 和 `scripts/`，复制或合并到同一份 v1.7.5 Windows 发布包。

```powershell
.\python\python.exe tests\verify_pipeline.py
# 包含上述回归，以及固定刷取7-8的截图定位和流程测试
.\python\python.exe tests\verify_main_farm.py
# 推主线：剧情完成后选下一关、无新关卡/确认无响应时停止
.\python\python.exe tests\verify_main_story.py
```

依赖为 `maafw==5.0.5`、NumPy、Pillow，放在发布包目录的 `debug/tools/` 下。可通过带有 pip 的 Python 3.12 运行 `python -m pip install --target debug/tools maafw==5.0.5 numpy pillow` 安装。测试加载发布包实际 DLL 和 pipeline，通过离线控制器执行，不连接模拟器。

每周商店回归覆盖多件和单件购买、购买结果、售罄跳过，以及同名微晶的限量判断。`shop-micro-limited.png` 由实机微晶弹窗叠加同版商店的限量标记生成，用于模拟限量档补货。

`fixtures/` 来自本次实机截图；大部分只保留相关 UI 区域。测试覆盖图像正反例、所有手动次数的真实 pipeline 执行、自然燃料减次数、燃料不足退出及促销关闭优先级。

`farm-chapters/map/stages.png` 来自用户提供的导航截图，缩放至720p画布；章节图去掉了窗口边缘。`farm-chapter-expanded/stage-detail/sweep-dialog/sweep-result.png` 为2026-10-22实机截图。刷主线测试使用真实识别器和离线控制器，覆盖第7章缩略卡展开后再次进入章节、普通难度、米德加尔特直接可见/拖动后可见/持续不可见（最多3次）、7-8精确选择及其他关卡排除，以及独立的燃料次数调整和燃料不足停止。结算回归使用真实截图验证点击标题退出，并连续执行两批；地图隐藏场景通过遮盖地区名称构造。

实机从首页连续完成两批7-8扫荡的记录见 `debug/repair-runs/20261022-221617-farm-live/result.json`（`succeeded: true`、`stopped: false`）。验证每批限制为1次，正常任务仍是最多10次；本次没有实机耗尽燃料。`debug/verify_farm_live.py` 是有实际燃料消耗的两批复测工具，不属于离线测试。

实机任务回归结果另见 `debug/final-suite.json` 和根目录修复记录。不要把被诊断工具主动停止的运行当成完整通过，应检查每个运行目录 `result.json` 中的 `stopped` 字段。

2026-10-28 推主线回归使用 ADB 截取的 `main-cleared-story.png`（已完成的 S7-17 详情仍显示“开始播放”，同时 7-18 有“新”标记）和 `main-selected-stage.png`。真实识别器与离线控制器先复现旧优先级导致的重播，再验证从剧情、确认弹窗、胜利页及关卡列表接续时只选一次下一关；选中关卡仍有“新”标记时正常进入编队，无新关卡或确认无响应时限时停止。实机完整“跳过剧情→确认→关卡结束→7-18→编队”记录见 `debug/repair-runs/20261028-223629/result.json`。验证仅将“开始行动”替换为不操作并结束任务，未开战、未消耗燃料；不代表整场战斗或后续章节已实测。
