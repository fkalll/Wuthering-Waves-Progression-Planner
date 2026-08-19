# 鸣潮养成助手（3.5 中文图鉴版）

一个使用 Python、Tkinter 和 Pillow 编写的离线桌面工具，用于查询《鸣潮》角色等级材料、五项技能材料与社区配装建议。

## 功能范围

- 收录 3.5 已实装的 56 个可选择战斗形态：52 个具名角色及漂泊者四属性。
- 使用本地角色头像卡片浏览，并可按中文名、英文别名、属性、武器和定位搜索。
- 支持“全部、冷凝、热熔、导电、气动、衍射、湮灭”属性筛选，筛选与文字搜索取交集。
- 角色等级按 1、10、20、30、40、50、60、70、80、90 档位计算，可跨多个档位。
- 五项技能使用独立的 1～10 级区间，并可选择是否计入全部技能树节点。
- 显示本地材料图标、简体中文名称、精确经验、升级贝币、促剂建议和跨越的突破节点。
- 配装页显示中文声骸套装、推荐主声骸图片、费用组合、武器、词条、共鸣效率和技能优先级。

程序运行时只读取 data 和 assets 中的本地文件，不连接数据库，不需要网络、账号登录或 OCR。

## 安装依赖

macOS/Linux：

    cd /Users/heyuhang/python-project
    .venv/bin/python -m pip install -r wuwa_planner/requirements.txt

Windows PowerShell：

    py -m pip install -r requirements.txt

Pillow 是唯一的第三方运行依赖，用于可靠加载和缩放本地 PNG。

## 运行

从项目根目录：

    .venv/bin/python wuwa_planner/main.py

进入项目目录后：

    cd wuwa_planner
    python3 main.py

Windows：

    py main.py

只校验数据和本地图片引用，不创建窗口：

    python3 main.py --check-data

## 等级与技能口径

- 角色等级：当前档位必须小于目标档位，只允许 1/10/20/…/90。
- 突破材料：只有真正跨过节点才加入。例如 10→20 不含 20 级突破，20→30 才加入。
- 角色经验：底层仍保留 1～90 精确累计经验，因此档位间做差是精确值。
- 促剂建议：先最小化溢出经验，再最小化使用数量；它是建议组合，不等于精确消耗。
- 五项技能：常态攻击、共鸣技能、共鸣回路、共鸣解放、变奏技能统一使用所选 1～10 区间。
- 技能树：10 个属性/固有技能节点独立计算，由“计入全部技能树节点”开关控制。

## 本地图片

- 角色头像：assets/characters，统一为透明 160×160 PNG。
- 材料图标：assets/materials，统一为透明 64×64 PNG。
- 推荐主声骸：assets/echoes，统一为透明 96×96 PNG。
- data/assets.json 记录每个资源键、本地路径、原始 URL、来源、日期、尺寸和权利说明。

开发期重新同步白名单资源：

    .venv/bin/python wuwa_planner/tools/sync_assets.py --download

只校验清单和现有文件：

    .venv/bin/python wuwa_planner/tools/sync_assets.py --check

资源同步脚本只在开发时联网；主程序不会自动下载或更新。

## 测试

从项目根目录执行：

    PYTHONPYCACHEPREFIX=/private/tmp/python-project-pycache .venv/bin/python -m unittest discover -s wuwa_planner -p 'test_*.py' -v

测试覆盖 56 项名单、六属性、中文名称、逐级技能、技能树、十级角色档位、突破边界、图片清单、PNG 尺寸、跨文件引用、搜索和配装字段。

## 数据与参考来源

- [《鸣潮》官方网站](https://mc.kurogames.com/)与[库街区《鸣潮》WIKI](https://wiki.kurobbs.com/mc/home)：版本范围与官方中文术语入口。
- [Encore API](https://api-v2.encore.moe/_docs/scalar)：按 ID 对齐简体中文角色、材料、声骸名称和原始图标。
- [WaveKit](https://wavekit.net/)：分阶段突破和五项技能逐级材料交叉核对。
- [Wuthering Waves Wiki — Resonator/Leveling](https://wutheringwaves.fandom.com/wiki/Resonator/Leveling)：1～90 累计经验、贝币比例与促剂经验。
- [Wuthering Waves Optimizer](https://github.com/ryanbenson/wuthering-waves-optimizer)、[wuwa-toolkit](https://github.com/MinhBN-dev/wuwa-toolkit) 与 [wuwa-damage-calculator](https://github.com/chuan-hane/wuwa-damage-calculator)：仅参考配装预设、卡片层级和筛选反馈，没有复制其实现。

配装属于社区起步建议，会受队伍、武器、共鸣链和词条影响，不是官方唯一答案。

## 图片权利与分发

角色、材料和声骸原始图片属于游戏内容，其权利归库洛游戏及相应权利方。本项目仅将其用于本地学习工具展示。

如果以后将项目打包为 ZIP、macOS App 或 Windows EXE 并提供给其他人，应在分发前自行确认这些图片的再分发权利。开源代码许可证不自动授予游戏素材版权。本项目没有收入官方 Logo、宣传海报、壁纸、音视频或字体。

## Windows 打包注意

打包时至少需要 main.py、calculator.py、data_loader.py、data、assets 和 Pillow。PyInstaller 必须在 Windows 上生成 Windows EXE，不能直接把 macOS App 改成 EXE。

本轮未执行 App、EXE 或 ZIP 打包。

## 暂未实现

- 已有材料库存扣减和低阶材料合成
- 单项技能使用不同等级
- 武器养成材料
- 伤害模拟、队伍自动配装和账号读取
- OCR、数据库和运行时自动更新
