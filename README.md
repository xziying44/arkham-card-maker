# arkham-card-maker

阿卡姆恐怖 LCG 自定义卡牌渲染引擎和 CLI。

本项目从 `arkham-homebrew` 迁移渲染核心，统一为 `CardRenderer` 入口，并在主渲染路径中使用 `layout_only=True` 单遍构建卡面底图和文字层元数据，避免旧项目 `create_card()` + `create_card_bottom_map()` 的二次渲染。

## Python API

```python
from arkham_card_maker import CardRenderer, RenderOptions

renderer = CardRenderer()
result = renderer.render("example.card", RenderOptions(bleed=0))
result.save("example.png")
```

## CLI

安装依赖后可使用：

```bash
arkham-card-maker render example.card -o example.png
arkham-card-maker batch cards/ -r --workers 4 -o export
arkham-card-maker config init
arkham-card-maker config show
```

## 验证

```bash
python3 -m compileall -q arkham_card_maker
pytest -q
```

当前实现已包含一条旧 `ExportHelper` 对照冒烟：简单事件卡在默认导出参数下，新单遍管线与旧二次渲染输出尺寸一致且逐像素无差异。
