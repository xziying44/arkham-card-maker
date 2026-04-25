# arkham-card-maker 渲染引擎重构实施文档

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `arkham-homebrew` 的卡图渲染链路迁移到新项目 `arkham-card-maker`，提供统一 Python API、CLI 单卡/批量渲染和多进程并发，消除旧二次渲染，并用金样测试保证像素级一致。

**Architecture:** 第一阶段就实现“单遍渲染 + 入口统一”。单卡渲染通过 `layout_only=True` 分离文字布局和文字光栅化：一次执行卡面构建得到未叠文字的底图和旧格式文字层元数据，再复用旧出血、文字层叠加和后处理语义。批量性能收益来自单卡去重渲染和多进程并发两部分。

**Tech Stack:** Python 3.11+、Pillow、numpy、click、pytest、pytest-cov；可选依赖为 requests、opencv-python。

---

## 一、审阅结论与设计修正

### 1. 设计校正结论

二次渲染必须在本轮重构中消除，这是新项目的核心收益点之一。风险不通过延期优化解决，而通过更严格的等价性门禁解决：

- 旧二次渲染链路只作为金样生成器和行为对照。
- 新主链路必须使用 `layout_only=True` 单遍构建底图和文字层元数据。
- `layout_only=True` 不等于 `FontManager.silence=True`：它不能让 `get_font_text()` 返回空串，也不能跳过影响布局/元数据的文字入口。
- `draw_centered_text()` / `draw_left_text()` / `draw_text()` 必须在 layout-only 模式下继续生成与旧路径一致的 `RenderItem`，只是禁止写入文字像素。
- `ExportHelper._draw_text_layer()` 的出血后文字重绘语义必须原样迁移，包括内联图片、EnhancedDraw 特效、描边合并、DPI 缩放和拉伸模式 resize。

### 2. 已修订设计文档

- 文件：`/Users/xziying/project/arkham/arkham-card-maker/docs/superpowers/specs/2026-04-25-render-engine-refactor-design.md`
- 修正：第一阶段必须实现 `layout_only`，消除 `create_card()` + `create_card_bottom_map()` 二次渲染。
- 修正：旧二次渲染链路保留为金样对照，不作为新 `CardRenderer` 主路径。
- 补充：旧入口和调用点清单，避免遗漏 Web、牌库导出、PNP 导出、预览和保存路径。

## 二、旧项目渲染代码地图

### 1. 必迁移核心文件

- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/create_card.py:52`：`CardCreator`，所有卡牌类型分发和卡面布局。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/Card.py:76`：`Card`，Pillow 绘制、富文本调用、文字层元数据。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/ResourceManager.py:191`：`ImageManager`，模板图、插画、内联图片解析。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/ResourceManager.py:479`：`FontManager`，字体、语言配置、文本盒缓存。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/rich_text_render/RichTextRenderer.py`：富文本布局和光栅化。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/rich_text_render/VirtualTextBox.py`：多边形文本框、换行、列布局。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/rich_text_render/HtmlTextParser.py`：HTML-like 标签解析。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/enhanced_draw.py:303`：文字特效、描边、阴影、发光。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/card_cdapter.py`：卡牌标签适配。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/ExportHelper.py:47`：导出参数、出血、文字层叠加、后处理。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/export_helper/LamaCleaner.py`：LaMa 和镜像 outpaint。

### 2. 必复刻编排语义

- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/bin/workspace_manager.py:1456`：`generate_card_image()`，处理卡背、外部图片、语言、遭遇组、页脚。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/bin/workspace_manager.py:1631`：`generate_double_sided_card_image()`，处理背面字段继承、共享正面插画、背面灰度。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/create_card.py:1857`：`create_card_bottom_map()`，静默底图生成。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/ExportHelper.py:590`：`export_card()`，单面出血导出旧链路。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/ExportHelper.py:613`：`export_double_sided_card()`，双面出血导出旧链路。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/ExportHelper.py:708`：`export_card_auto()`，旧导出统一入口。

### 3. 旧触发入口

- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/server.py:914`：`POST /api/generate-card`，预览。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/server.py:1036`：`POST /api/save-card`，保存卡图。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/server.py:1443`：`POST /api/export-deck-image`，牌库图片导出。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/server.py:1490`：`POST /api/export-deck-pdf`，牌库 PDF 导出。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/server.py:2022`：`POST /api/content-package/export-pnp`，PNP 导出。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/server.py:2340`：`POST /api/export-card`，指定参数导出。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/arkham-app/src/api/card-service.ts`：前端预览、保存、导出卡图 API 封装。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/arkham-app/src/api/tts-export-service.ts:150`：前端指定参数导出 API 封装。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/arkham-app/src/components/FormEditPanel.vue:1223`：自动生成卡图预览。
- `/Users/xziying/project/arkham/DIY工具/arkham-homebrew/arkham-app/src/components/FormEditPanel.vue:1682`：导出图片。

## 三、新项目目标结构

- 创建：`/Users/xziying/project/arkham/arkham-card-maker/pyproject.toml`，声明包、依赖和 CLI 入口。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/__init__.py`，导出 `CardRenderer`、`RenderOptions`、`RenderResult`。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/engine.py`，统一 API 入口。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/render_options.py`，导出参数和结果数据类。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/card.py`，迁移 `Card.py`。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/card_creator.py`，迁移 `create_card.py`。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/card_adapter.py`，迁移 `card_cdapter.py`。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/resource_manager.py`，迁移资源管理。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/enhanced_draw.py`，迁移文字特效。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/render/`，迁移富文本渲染子包。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/bleeding/`，迁移出血和 LaMa。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/compat/workspace.py`，最小工作区适配器。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/worker.py`，批量并发渲染。
- 创建：`/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/cli/main.py`，CLI。
- 复制：`/Users/xziying/project/arkham/DIY工具/arkham-homebrew/fonts/` 到新项目资源目录。
- 复制：`/Users/xziying/project/arkham/DIY工具/arkham-homebrew/images/` 到新项目资源目录。
- 复制：`/Users/xziying/project/arkham/DIY工具/arkham-homebrew/cardback/` 到新项目资源目录。

## 四、实施任务

### Task 1: 建立项目骨架和可安装包

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/pyproject.toml`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/README.md`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/__init__.py`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/tests/`

- [ ] Step 1: 检查 Python 虚拟环境

Run:
```bash
cd /Users/xziying/project/arkham/arkham-card-maker
for d in .venv venv env; do [ -d "$d" ] && echo "$d"; done
```

Expected: 如果存在虚拟环境，后续命令使用对应 `bin/python`；如果不存在，只使用当前用户环境，不做全局安装。

- [ ] Step 2: 写 `pyproject.toml`

内容包含：
```toml
[project]
name = "arkham-card-maker"
version = "0.1.0"
description = "阿卡姆恐怖 LCG 自定义卡牌渲染引擎和 CLI"
requires-python = ">=3.11"
dependencies = [
  "Pillow>=10",
  "numpy>=1.24",
  "click>=8.1",
  "requests>=2.31",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=5"]
fast = ["opencv-python>=4.8"]

[project.scripts]
arkham-card-maker = "arkham_card_maker.cli.main:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] Step 3: 写包入口

`arkham_card_maker/__init__.py`：
```python
from .engine import CardRenderer
from .render_options import RenderOptions, RenderResult

__all__ = ["CardRenderer", "RenderOptions", "RenderResult"]
```

- [ ] Step 4: 验证包可导入

Run:
```bash
python -c "import arkham_card_maker; print(arkham_card_maker.__all__)"
```

Expected: 输出 `['CardRenderer', 'RenderOptions', 'RenderResult']`；如果 `engine.py` 尚未创建，则该步骤放到 Task 6 后执行。

### Task 2: 复制资源和迁移纯工具模块

**Files:**
- Copy: `fonts/`, `images/`, `cardback/`
- Create: `arkham_card_maker/enhanced_draw.py`
- Create: `arkham_card_maker/card_adapter.py`
- Create: `arkham_card_maker/render/parser.py`
- Create: `arkham_card_maker/render/text_box.py`
- Create: `arkham_card_maker/render/__init__.py`

- [ ] Step 1: 复制资源目录

Run:
```bash
cd /Users/xziying/project/arkham/arkham-card-maker
cp -R /Users/xziying/project/arkham/DIY工具/arkham-homebrew/fonts ./fonts
cp -R /Users/xziying/project/arkham/DIY工具/arkham-homebrew/images ./images
cp -R /Users/xziying/project/arkham/DIY工具/arkham-homebrew/cardback ./cardback
```

Expected: `fonts/language_config.json`、`images/*.png`、`cardback/player-back.jpg` 存在。

- [ ] Step 2: 原样迁移纯工具模块

Run:
```bash
cp /Users/xziying/project/arkham/DIY工具/arkham-homebrew/enhanced_draw.py /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/enhanced_draw.py
cp /Users/xziying/project/arkham/DIY工具/arkham-homebrew/card_cdapter.py /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/card_adapter.py
mkdir -p /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/render
cp /Users/xziying/project/arkham/DIY工具/arkham-homebrew/rich_text_render/HtmlTextParser.py /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/render/parser.py
cp /Users/xziying/project/arkham/DIY工具/arkham-homebrew/rich_text_render/VirtualTextBox.py /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/render/text_box.py
```

- [ ] Step 3: 调整模块内 import

必须替换：
```python
from HtmlTextParser import ...
from rich_text_render.HtmlTextParser import ...
from rich_text_render.VirtualTextBox import ...
```

替换为：
```python
from .parser import ...
from .text_box import ...
```

- [ ] Step 4: 建立 `render/__init__.py`

```python
from .renderer import DrawOptions, RichTextRenderer, TextAlignment

__all__ = ["DrawOptions", "RichTextRenderer", "TextAlignment"]
```

### Task 3: 迁移 ResourceManager 并去除 Web 配置依赖

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/resource_manager.py`
- Test: `/Users/xziying/project/arkham/arkham-card-maker/tests/test_resource_manager.py`

- [ ] Step 1: 复制旧文件

Run:
```bash
cp /Users/xziying/project/arkham/DIY工具/arkham-homebrew/ResourceManager.py /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/resource_manager.py
```

- [ ] Step 2: 替换 `bin.logger` 和 `bin.config_directory_manager`

目标行为：
```python
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def get_resource_path(relative_path):
    base_path = Path(__file__).resolve().parent.parent
    return str(base_path / relative_path)
```

保留 `ImageManager`、`FontManager`、语言配置、字体映射、文本盒缓存逻辑。

- [ ] Step 3: 写资源加载测试

`tests/test_resource_manager.py`：
```python
from pathlib import Path

from arkham_card_maker.resource_manager import FontManager, ImageManager


def test_font_manager_loads_language_config():
    manager = FontManager(font_folder=str(Path(__file__).parents[1] / "fonts"), lang="zh")
    assert manager.get_current_config() is not None
    assert manager.get_lang_font("正文字体").name


def test_image_manager_loads_templates():
    manager = ImageManager(image_folder=str(Path(__file__).parents[1] / "images"))
    assert manager.get_image("支援卡-守护者") is not None
```

- [ ] Step 4: 运行测试

Run:
```bash
pytest tests/test_resource_manager.py -q
```

Expected: 2 passed。

### Task 4: 迁移 RichTextRenderer，保持语义不变

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/render/renderer.py`
- Modify: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/render/__init__.py`
- Test: `/Users/xziying/project/arkham/arkham-card-maker/tests/test_rich_text_renderer.py`

- [ ] Step 1: 复制旧文件

Run:
```bash
cp /Users/xziying/project/arkham/DIY工具/arkham-homebrew/rich_text_render/RichTextRenderer.py /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/render/renderer.py
```

- [ ] Step 2: 只改 import 路径

必须替换：
```python
from rich_text_render.HtmlTextParser import ...
from rich_text_render.VirtualTextBox import ...
from enhanced_draw import EnhancedDraw
```

替换为：
```python
from .parser import ...
from .text_box import ...
from ..enhanced_draw import EnhancedDraw
```

必须新增 `layout_only`，但不得改 `find_best_fit_font_size()`、`draw_complex_text()`、`draw_line()` 的布局、字号搜索和 `RenderItem` 生成逻辑。`layout_only=True` 只跳过光栅化绘制。

- [ ] Step 3: 写最小富文本测试

```python
from PIL import Image

from arkham_card_maker.render import DrawOptions, RichTextRenderer, TextAlignment
from arkham_card_maker.resource_manager import FontManager, ImageManager


def test_draw_line_returns_render_items():
    image = Image.new("RGBA", (400, 200), (255, 255, 255, 0))
    font_manager = FontManager(lang="zh")
    image_manager = ImageManager()
    renderer = RichTextRenderer(font_manager, image_manager, image, lang="zh")

    items = renderer.draw_line(
        text="测试",
        position=(200, 80),
        alignment=TextAlignment.CENTER,
        options=DrawOptions(font_name=font_manager.get_lang_font("标题字体").name, font_size=32),
    )

    assert items
```

### Task 5: 迁移 Card 和 CardCreator

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/card.py`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/card_creator.py`
- Test: `/Users/xziying/project/arkham/arkham-card-maker/tests/test_card_creator.py`

- [ ] Step 1: 复制旧文件

Run:
```bash
cp /Users/xziying/project/arkham/DIY工具/arkham-homebrew/Card.py /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/card.py
cp /Users/xziying/project/arkham/DIY工具/arkham-homebrew/create_card.py /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/card_creator.py
```

- [ ] Step 2: 修改 import 路径

`card.py` 中：
```python
from .resource_manager import FontManager, ImageManager
from .render.renderer import RichTextRenderer, DrawOptions, TextAlignment
from .render.text_box import TextObject, ImageObject, RenderItem
```

`card_creator.py` 中：
```python
from PIL import Image, ImageEnhance
from .resource_manager import FontManager, ImageManager
from .card import Card
from .card_adapter import CardAdapter
```

- [ ] Step 3: 保留旧逻辑

不得修改：
- `Card.draw_centered_text()` 非 layout-only 模式的 silence 早退。
- `Card.draw_left_text()` 非 layout-only 模式的 silence 早退。
- `Card.draw_text()` 的 `<relish>` 兼容转换。
- `Card.get_text_layer_metadata()` 的字段结构。
- `CardCreator._preprocessing_json()`。
- `CardCreator.create_card_bottom_map()` 供旧链路对照使用。
- `CardCreator.create_card()` 的类型分发。
- `layout_only=True` 时文字入口必须生成元数据但不写文字像素。

- [ ] Step 4: 写生成底图测试

```python
from arkham_card_maker.card_creator import CardCreator
from arkham_card_maker.resource_manager import FontManager, ImageManager


def test_create_card_bottom_map_restores_silence():
    font_manager = FontManager(lang="zh")
    image_manager = ImageManager()
    creator = CardCreator(font_manager, image_manager)
    data = {"type": "事件卡", "class": "中立", "name": "测试", "body": "测试正文", "traits": []}

    card = creator.create_card_bottom_map(data)

    assert card is not None
    assert font_manager.silence is False
```

- [ ] Step 5: 写 layout-only 元数据测试

```python
from arkham_card_maker.card_creator import CardCreator
from arkham_card_maker.resource_manager import FontManager, ImageManager


def test_layout_only_keeps_text_metadata_without_text_pixels():
    font_manager = FontManager(lang="zh")
    image_manager = ImageManager()
    creator = CardCreator(font_manager, image_manager)
    data = {"type": "事件卡", "class": "中立", "name": "测试", "body": "测试正文", "traits": []}

    card = creator.create_card(data, layout_only=True)
    metadata = card.get_text_layer_metadata()

    assert metadata
    assert any(item.get("text") == "测试" or item.get("text") == "测试正文" for item in metadata if item.get("type") != "image")
```

### Task 6: 实现最小工作区适配器

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/compat/workspace.py`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/compat/__init__.py`
- Test: `/Users/xziying/project/arkham/arkham-card-maker/tests/test_workspace_adapter.py`

- [ ] Step 1: 实现 `RenderWorkspace`

职责：
- 保存 `workspace_path`、`config`、`font_manager`、`image_manager`、`creator`。
- 提供 `get_file_content(path)`。
- 提供 `_get_absolute_path(path)`。
- 提供 `get_card_base64(json_data, field="picture_base64")`，复刻旧 base64/PIL/相对路径解析。
- 提供 `generate_card_image(json_data, layout_only=False, silence=False)`，从旧 `WorkspaceManager.generate_card_image()` 复制渲染相关逻辑；`silence` 仅供旧金样对照，`CardRenderer` 主路径必须传 `layout_only=True`。
- 提供 `generate_double_sided_card_image(json_data, layout_only=False, silence=False)`，从旧实现复制双面继承逻辑；新主路径必须用 layout-only 单遍生成每一面。

- [ ] Step 2: 明确不迁移职责

不得加入文件树扫描、删除/重命名文件、GitHub 图床、TTS、PNP、内容包管理。

- [ ] Step 3: 写工作区路径测试

```python
from pathlib import Path

from arkham_card_maker.compat.workspace import RenderWorkspace


def test_workspace_reads_card_file(tmp_path):
    card = tmp_path / "a.card"
    card.write_text('{"type":"事件卡","name":"测试"}', encoding="utf-8")
    workspace = RenderWorkspace(workspace_path=tmp_path)

    assert workspace.get_file_content("a.card") == '{"type":"事件卡","name":"测试"}'
```

### Task 7: 迁移出血、文字层叠加和后处理

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/render_options.py`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/bleeding/lama_cleaner.py`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/bleeding/engine.py`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/compositor.py`
- Test: `/Users/xziying/project/arkham/arkham-card-maker/tests/test_export_pipeline.py`

- [ ] Step 1: 定义 `RenderOptions` 和 `RenderResult`

保留旧枚举值：`PNG`、`JPG`、`61mm × 88mm`、`61.5mm × 88mm`、`62mm × 88mm`、`63.5mm × 88.9mm (2.5″ × 3.5″)`、`裁剪`、`拉伸`、`镜像出血`、`LaMa模型出血`。

- [ ] Step 2: 复制 `LamaCleaner.py`

Run:
```bash
mkdir -p /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/bleeding
cp /Users/xziying/project/arkham/DIY工具/arkham-homebrew/export_helper/LamaCleaner.py /Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/bleeding/lama_cleaner.py
```

- [ ] Step 3: 从 `ExportHelper.py` 迁移这些函数

- `calculate_pixel_dimensions()`
- `_call_lama_cleaner()`
- `_is_horizontal()`
- `_standard_bleeding()`
- `_bleeding_submit_icon()`
- `_bleeding()`
- `_draw_text_layer()`
- `_apply_image_adjustments()`

注意：`_draw_text_layer()` 必须保留 `ImageObject` 内联图片、EnhancedDraw 批量特效、普通文字快速路径、拉伸模式最终 resize。

- [ ] Step 4: 写参数计算测试

```python
from arkham_card_maker.render_options import ExportBleed, ExportSize
from arkham_card_maker.bleeding.engine import calculate_pixel_dimensions


def test_calculate_pixel_dimensions_matches_old_formula():
    assert calculate_pixel_dimensions(300, ExportBleed.THREE_MM, ExportSize.POKER_SIZE) == (821, 1121)
```

### Task 8: 实现 CardRenderer 统一入口

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/engine.py`
- Test: `/Users/xziying/project/arkham/arkham-card-maker/tests/test_engine.py`

- [ ] Step 1: 实现输入解析

`CardRenderer.render(card_source, options)` 支持：
- `.card` 路径。
- `dict`。
- JSON 字符串可选支持，但错误提示必须明确为中文。

- [ ] Step 2: 复刻旧导出链路

伪代码：
```python
card_json = load_card_source(card_source)
if version == "2.0" and options.double_sided:
    return render_double_sided(card_json)
return render_single(card_json)
```

单面必须等价于旧 `ExportHelper.export_card()` 的输出，但主路径只能构建一次：
```python
card_json = creator._preprocessing_json(card_json)
card = workspace.generate_card_image(card_json, layout_only=True)
card_map_image = bleed_engine.apply(card_json, card.image)
text_layer = card.get_text_layer_metadata()
card_map_image = text_layer_compositor.apply(card_map_image, text_layer)
card_map_image = image_adjustments.apply(card_map_image, options.saturation, options.brightness, options.gamma)
```

禁止在 `CardRenderer.render()` 主路径中调用一次 `generate_card_image(..., False)` 再调用一次 `generate_card_image(..., True)`。

- [ ] Step 3: 双面必须等价于旧 `ExportHelper.export_double_sided_card()`

必须保留：
- `version`、`language` 继承。
- `is_back = True`。
- `front_name` 注入。
- `share_front_picture` 时复制 `picture_base64` 和 `picture_layout`。
- 背面默认 `image_filter = "grayscale"`。

- [ ] Step 4: 写单遍调用门禁测试

用 monkeypatch 统计 `RenderWorkspace.generate_card_image()` 调用次数：单面卡 `CardRenderer.render()` 主路径只能调用 1 次，双面卡有背面时每一面各 1 次，总计最多 2 次。测试名建议：

```python
def test_renderer_does_not_call_legacy_double_render(monkeypatch):
    calls = []
    original = RenderWorkspace.generate_card_image

    def spy(self, json_data, layout_only=False, silence=False):
        calls.append({"layout_only": layout_only, "silence": silence})
        return original(self, json_data, layout_only=layout_only, silence=silence)

    monkeypatch.setattr(RenderWorkspace, "generate_card_image", spy)
    renderer.render({"type": "事件卡", "class": "中立", "name": "测试", "body": "测试正文", "traits": []})

    assert calls == [{"layout_only": True, "silence": False}]
```

- [ ] Step 4: 写保存结果方法

`RenderResult.save_all(output_stem)`：
- 单面：保存为 `<stem>.<ext>`。
- 双面：保存为 `<stem>_a.<ext>` 和 `<stem>_b.<ext>`。
- JPG：转换 RGB，使用 `quality` 和 `dpi`。
- PNG：保留 RGBA，写入 `dpi`。

### Task 9: 金样对比测试

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/tests/golden/`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/tests/test_pixel_parity.py`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/scripts/generate_old_golden.py`

- [ ] Step 1: 收集覆盖卡牌类型的 `.card` 样本

至少覆盖：调查员卡、调查员卡背、调查员小卡、支援卡、事件卡、技能卡、敌人卡、地点卡、诡计卡、弱点卡、升级卡、故事卡、行动卡、冒险参考卡、规则小卡、场景卡/密谋卡正背、大画系列、特殊图片、玩家/遭遇/定制/敌库卡背。

- [ ] Step 2: 写旧项目金样生成脚本

脚本使用旧项目 `WorkspaceManager` 和 `ExportHelper.export_card_auto()` 生成参考 PNG，不改旧代码。

- [ ] Step 3: 写逐像素对比函数

```python
from PIL import ImageChops


def assert_images_equal(actual, expected):
    assert actual.size == expected.size
    diff = ImageChops.difference(actual.convert("RGBA"), expected.convert("RGBA"))
    assert diff.getbbox() is None
```

如果必须容忍 ±1，需要输出差异像素数量、最大通道差、差异图路径，不能静默放宽。

- [ ] Step 4: 首轮只要求默认参数完全一致

默认参数：`PNG`、`dpi=300`、`bleed=0`、`bleed_mode="裁剪"`、`bleed_model="镜像出血"`、`saturation=1.0`、`brightness=1.0`、`gamma=1.0`。

### Task 10: 实现多进程批量渲染

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/worker.py`
- Test: `/Users/xziying/project/arkham/arkham-card-maker/tests/test_worker.py`

- [ ] Step 1: 实现进程函数

`render_single_card(args)` 必须是模块顶层函数，便于 macOS spawn 序列化。

- [ ] Step 2: 子进程内创建 `CardRenderer`

不要跨进程序列化 `FontManager`、`ImageManager`、`PIL.Image`。

- [ ] Step 3: 多进程结果写文件优先

批量 CLI 应让子进程直接保存输出文件，主进程收集状态，避免大量 PIL Image 回传。

- [ ] Step 4: 测试 workers=1 和 workers=2 输出一致

对同一组样本分别跑串行和并发，逐像素比较输出。

### Task 11: 实现 CLI

**Files:**
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/cli/main.py`
- Create: `/Users/xziying/project/arkham/arkham-card-maker/arkham_card_maker/cli/__init__.py`
- Test: `/Users/xziying/project/arkham/arkham-card-maker/tests/test_cli.py`

- [ ] Step 1: 单卡命令

命令：
```bash
arkham-card-maker render card.card -o output.png --dpi 300 --bleed 0
```

失败时中文提示：
```text
渲染失败：<原因>
```

- [ ] Step 2: 批量命令

命令：
```bash
arkham-card-maker batch cards/ -r --workers 4 -o out
```

输出每张卡状态，失败不吞异常，最终返回非零退出码。

- [ ] Step 3: 配置命令

命令：
```bash
arkham-card-maker config init
arkham-card-maker config show
```

配置优先级：CLI 参数 > 配置文件 > 默认值。

### Task 12: 完整验证与交付

**Files:**
- Modify: `/Users/xziying/project/arkham/arkham-card-maker/README.md`
- Modify: `/Users/xziying/project/arkham/arkham-card-maker/docs/superpowers/specs/2026-04-25-render-engine-refactor-design.md` 如发现新遗漏。

- [ ] Step 1: 运行单元测试

Run:
```bash
pytest -q
```

Expected: 全部通过。

- [ ] Step 2: 运行覆盖率

Run:
```bash
pytest --cov=arkham_card_maker --cov-report=term-missing
```

Expected: 新增业务代码覆盖率目标 80% 以上；金样脚本和资源文件不计入覆盖率。

- [ ] Step 3: 运行像素金样测试

Run:
```bash
pytest tests/test_pixel_parity.py -q
```

Expected: 默认参数下全部样本逐像素一致。

- [ ] Step 4: 运行 CLI 冒烟

Run:
```bash
arkham-card-maker render tests/fixtures/cards/event.card -o /tmp/arkham-event.png
arkham-card-maker batch tests/fixtures/cards -r --workers 2 -o /tmp/arkham-batch
```

Expected: 输出 PNG 文件存在，批量状态全部成功。

## 五、实施门禁

- 第一阶段必须实现 `layout_only` 并消除 `CardRenderer` 主路径二次渲染。
- 不得修改 `CardCreator` 中各卡牌类型坐标、字号、颜色、贴图顺序。
- 不得修改 `RichTextRenderer` 的换行、字号搜索、标签解析、渲染顺序。
- 不得只比较图片尺寸；必须做逐像素对比。
- 不得只测单面普通玩家卡；必须覆盖双面、背面共享插画、规则小卡、调查员小卡、大画、特殊图片和卡背。
- 多进程必须让每个进程独立初始化资源管理器，避免共享不可序列化对象。
- CLI 错误提示使用中文，不暴露敏感路径以外的内部堆栈，调试模式除外。

## 六、后续第二阶段候选优化

只有在第一阶段金样全部稳定后，才可以单独设计：

- 字体文本盒缓存跨进程预热。
- 图片资源只读 mmap 或进程池初始化器。
- 更细粒度的资源懒加载。
- 只针对金样稳定后的卡型做局部性能专项。

这些优化必须各自有性能基线、像素对比报告和回滚路径。
