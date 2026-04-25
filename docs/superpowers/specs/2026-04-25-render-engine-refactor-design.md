# arkham-card-maker 渲染引擎重构设计

## 目标

将 arkham-homebrew 的卡牌渲染核心从混乱的多入口架构重构为统一入口的独立项目。支持 CLI 自动化生成、多进程批量渲染，同时保证生成卡图与旧项目**像素级一致**。

## 范围

- **包含**：卡牌渲染核心（Card/CardCreator/RichTextRenderer/EnhancedDraw）、导出（出血/文字层/图像调整）、CLI 工具、多进程批量渲染
- **不包含**：Flask Web 服务、桌面/Android GUI、TTS 导出、PNP 导出、图床上传、内容包管理——这些保留在 arkham-homebrew 中

---

## 架构概览

### 旧架构问题

```
入口散落 5+ 处，调用链复杂：
  Web API → WorkspaceManager.generate_card_image()
            → CardCreator.create_card()  （第一次，画文字）
  Web API → WorkspaceManager.generate_card_image(silence=True)
            → CardCreator.create_card()  （第二次，不画文字）
  Web API → WorkspaceManager.export_card_with_params()
            → ExportHelper.export_card_auto()
              → generate_card_image() × 2  （又一次两次渲染）
              → _bleeding() → _draw_text_layer()
  
  CLI? → 不存在，只能手动调 Python 脚本
```

### 新架构

```
单一入口 CardRenderer：
  
  CardRenderer.render(card_source, options)
    ├─ CardAdapter.convert()          # 标签转换
    ├─ _preprocess_json()             # 预处理
    ├─ CardCreator.create_card(layout_only=True)
    │    ├─ 贴底图/UI/图标（正常绘制）
    │    └─ 文本布局（仅计算位置，不画到图上）
    │    └─ → text_layer_metadata
    ├─ BleedEngine.apply()            # 出血处理
    ├─ TextLayerCompositor.apply()    # 文字层叠加
    ├─ ImageAdjustments.apply()       # 饱和度/亮度/伽马
    └─ → RenderResult(front, back?)
```

### 核心收益：本轮必须消除二次渲染

旧方案：第一遍画文字提取元数据 → 第二遍画纯底图 → 出血 → 文字层重绘 → 后处理。这是旧框架受限产生的无奈之举，不应被新项目继续固化。

新方案必须把“布局计算”和“光栅化绘制”分离：`CardCreator.create_card(layout_only=True)` 仍完整执行底图、UI、图标和插画绘制，但所有文字入口只计算 `RenderItem` / `text_layer_metadata`，不把文字像素写入卡图。这样同一遍构建同时得到“未叠文字的底图”和“旧文字层元数据”，随后沿用旧 `ExportHelper._bleeding()` 与 `_draw_text_layer()` 语义完成出血后文字叠加。

风险控制方式不是保留二次渲染，而是建立旧链路金样：先用 `arkham-homebrew` 当前二次渲染生成参考图，再要求新单遍管线在默认参数、出血参数、双面背面和特殊卡类型上逐像素一致。若不一致，优先修正 `layout_only` 元数据与旧绘制路径的等价性，而不是退回二次渲染。

---

## 项目结构

```
arkham-card-maker/
├── pyproject.toml
├── README.md
├── arkham_card_maker/
│   ├── __init__.py              # 公开 API：CardRenderer, RenderOptions, RenderResult
│   ├── engine.py                # CardRenderer 统一入口
│   ├── render_options.py        # RenderOptions, RenderResult 数据类
│   ├── card.py                  # Card 类（从 Card.py 迁移）
│   ├── card_creator.py          # CardCreator（从 create_card.py 迁移）
│   ├── card_adapter.py          # CardAdapter（从 card_cdapter.py 迁移）
│   ├── resource_manager.py      # FontManager, ImageManager（从 ResourceManager.py 迁移）
│   ├── enhanced_draw.py         # EnhancedDraw + 特效类（从 enhanced_draw.py 迁移）
│   ├── config.py                # 配置管理（TOML 解析 + CLI 合并）
│   ├── worker.py                # 多进程批量渲染
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py              # CLI 入口（click 子命令）
│   ├── render/                  # 富文本渲染子包
│   │   ├── __init__.py
│   │   ├── renderer.py          # RichTextRenderer（迁移 + layout_only 改造）
│   │   ├── parser.py            # HtmlTextParser（从 HtmlTextParser.py 迁移）
│   │   └── text_box.py          # VirtualTextBox + 数据对象（从 VirtualTextBox.py 迁移）
│   └── bleeding/                # 出血子包
│       ├── __init__.py
│       ├── lama_cleaner.py      # LamaCleaner（从 export_helper/LamaCleaner.py 迁移）
│       └── mirror.py            # 镜像出血逻辑
├── fonts/                        # 字体资源文件
├── images/                       # UI 模板与美术资源
└── tests/
    ├── test_engine.py
    ├── test_card_creator.py
    ├── test_bleeding.py
    ├── test_renderer.py
    ├── test_cli.py
    ├── test_worker.py
    └── fixtures/                 # 测试用 .card 文件和参考图片
```

---

## 核心组件详细设计

### 1. CardRenderer（统一入口）— `engine.py`

```python
class CardRenderer:
    """卡牌渲染统一入口"""
    
    def __init__(self, assets_path: str = None, config: dict = None):
        """
        assets_path: 资源目录（fonts/, images/ 的父目录）
        config: 默认渲染配置字典
        """
    
    def render(
        self,
        card_source: Union[str, Path, dict],
        options: RenderOptions = None,
    ) -> RenderResult:
        """
        渲染单张卡牌
        
        card_source:
          - str/Path: .card 文件路径
          - dict: 卡牌 JSON 数据
        options: 渲染选项，未指定则使用默认值
        
        Returns: RenderResult(front=Image, back=Image|None, metadata=dict)
        """
    
    def render_batch(
        self,
        card_sources: List[Union[str, Path, dict]],
        options: RenderOptions = None,
        workers: int = 1,
        progress_callback: Callable = None,
    ) -> List[RenderResult]:
        """
        批量渲染，支持多进程
        workers=1 时在主进程执行，>1 时使用 ProcessPoolExecutor
        """
```

### 2. RenderOptions / RenderResult — `render_options.py`

```python
@dataclass
class RenderOptions:
    dpi: int = 300
    format: str = "PNG"          # PNG | JPG
    quality: int = 95            # JPG 质量 1-100
    bleed: int = 0               # 出血 mm（0=无出血）
    bleed_mode: str = "裁剪"     # 裁剪 | 拉伸
    bleed_model: str = "镜像出血" # 镜像出血 | LaMa模型出血
    saturation: float = 1.0
    brightness: float = 1.0
    gamma: float = 1.0
    # 双面卡牌
    double_sided: bool = True    # 自动检测并渲染背面
    # LaMa 出血
    lama_base_url: str = "http://localhost:8080"
    # 工作目录（用于解析插画相对路径）
    working_dir: str = ""

@dataclass
class RenderResult:
    front: Image.Image
    back: Optional[Image.Image] = None
    metadata: dict = field(default_factory=dict)
    # metadata 包含: card_name, card_type, card_class, version 等

    def save(self, output_path: str, **kwargs):
        """保存正面到文件"""
    
    def save_all(self, output_stem: str, format: str = "PNG", **kwargs):
        """保存正反面（双面卡自动加 _a/_b 后缀）"""
```

### 3. Card 类 — `card.py`

从原 `Card.py` 直接迁移，保持所有绘制方法不变：
- `paste_image`, `paste_image_with_transform`, `paste_with_multiply_blend`
- `draw_centered_text`, `draw_left_text`, `draw_text`
- `set_card_level`, `set_card_cost`, `add_submit_icon`, `add_slots`
- `set_health_and_horror`, `set_footer_information`
- `set_encounter_icon`, `set_location_icon`, `draw_scenario_card`
- `get_text_layer_metadata`, `get_upgrade_card_box_position`

改动：
- 新增 `layout_only` 属性控制文字行为
- `draw_text` / `draw_centered_text` / `draw_left_text` 在 `layout_only` 模式下仍走旧布局计算并追加 `last_render_list`，但不把文字像素写入 `self.image`
- 保留 `get_text_layer_metadata()`、`get_upgrade_card_box_position()` 的字段结构和坐标语义
- 非 `layout_only` 模式必须与旧项目绘制行为一致，便于对照和回归

### 4. CardCreator — `card_creator.py`

从原 `create_card.py` 直接迁移，每个卡牌类型的绘制方法逐方法复制：
- `create_location_card`, `create_enemy_card`, `create_treachery_card`
- `create_investigators_card`, `create_investigators_card_back`
- `create_event_card`, `create_skill_card`, `create_asset_card`
- `create_scenario_card`, `create_agenda_card`
- `create_weakness_back`, `create_upgrade_card`
- `create_story_card`, `create_action_card`, `create_scenario_reference_card`
- `create_*_large_card` 系列
- `create_mini_investigator_card`, `create_rule_card`

改动：
- 新增参数 `layout_only: bool = False`，传递给 `Card`
- `_preprocessing_json` 保持不变
- `_paste_background_image`, `_open_picture` 等辅助方法保持不变
- 保留 `self.image_mode` 临时切换逻辑，避免影响 `image_mode` 字段兼容
- `create_card()` 入口方法保持类型分发逻辑不变
- `create_card_bottom_map()` 仅作为旧链路金样/对照辅助保留，不作为新 `CardRenderer` 主路径

### 5. RichTextRenderer 改造 — `render/renderer.py`

核心改造：新增 `layout_only` 模式。该模式是消除二次渲染的关键，不是后续优化。

```python
class RichTextRenderer:
    def draw_complex_text(self, text, polygon_vertices, padding, options,
                          layout_only=False, draw_debug_frame=False):
        # 布局计算（始终执行）
        final_vbox = self.find_best_fit_font_size(...)
        render_list = final_vbox.get_render_list()
        
        if not layout_only:
            # 原有绘制逻辑不变
            self._rasterize_items(render_list, options)
            self._draw_guide_lines(final_vbox)
            self._draw_hr_lines(final_vbox)
        
        return render_list

    def draw_line(self, text, position, alignment, options,
                  layout_only=False, **kwargs):
        # 同样的 layout_only 改造
```

除新增 `layout_only` 参数与绘制分支外，所有解析、布局、字号搜索逻辑**完全不变**。`layout_only=True` 时必须返回与旧绘制路径相同的 `RenderItem[]`。

### 6. BleedEngine — `bleeding/`

```python
class BleedEngine:
    """出血处理引擎"""
    
    def __init__(self, lama_base_url: str = "http://localhost:8080"):
        self.lama_cleaner = LamaCleaner(base_url=lama_base_url)
    
    def apply(
        self,
        image: Image.Image,
        card_json: dict,
        options: RenderOptions,
        image_manager: ImageManager,
    ) -> Image.Image:
        """
        对卡图施加出血处理
        
        包含：
        1. 标准出血（UI 底图补充 + 投入图标出血）
        2. 最终出血到目标尺寸
        3. LaMa 模式下左上角优化
        """
```

代码来源：原 `ExportHelper._bleeding`、`_standard_bleeding`、`_bleeding_submit_icon`、`_call_lama_cleaner`

### 7. ImageAdjustments — `engine.py` 内部

```python
class ImageAdjustments:
    """图像后处理（饱和度/亮度/伽马）"""
    
    @staticmethod
    def apply(image: Image.Image, saturation: float, brightness: float, gamma: float) -> Image.Image:
        """
        逻辑来源：原 ExportHelper._apply_image_adjustments，完全不变
        使用 PIL ImageEnhance + numpy 伽马校正
        """
```

### 8. TextLayerCompositor

```python
class TextLayerCompositor:
    """文字层叠加器"""
    
    @staticmethod
    def apply(
        card_image: Image.Image,
        text_layer_metadata: list[dict],
        dpi: int,
        bleed_mode: str,
        pixel_dimensions: tuple,
    ) -> Image.Image:
        """
        根据元数据在图像上绘制所有文字
        逻辑来源：原 ExportHelper._draw_text_layer，完全不变
        """
```

### 9. 配置管理 — `config.py`

```python
@dataclass
class AppConfig:
    render: RenderOptions = field(default_factory=RenderOptions)

    @classmethod
    def from_toml(cls, path: Union[str, Path]) -> "AppConfig":
        """从 TOML 文件加载"""
    
    @classmethod
    def from_cli_args(cls, args: dict) -> "AppConfig":
        """从 CLI 参数构建（优先级最高）"""
    
    def merge_cli(self, cli_args: dict) -> "AppConfig":
        """CLI 参数覆盖配置文件值"""
    
    def to_render_options(self) -> RenderOptions:
        """转换为渲染选项"""
```

配置文件格式 `arkham-card-maker.toml`：
```toml
[render]
dpi = 300
format = "PNG"
quality = 95
bleed = 0
bleed_mode = "裁剪"
bleed_model = "镜像出血"

[render.image]
saturation = 1.0
brightness = 1.0
gamma = 1.0

[lama]
base_url = "http://localhost:8080"
```

优先级：CLI 参数 > 配置文件 > 默认值

### 10. 多进程批量渲染 — `worker.py`

```python
def render_single_card(args: tuple) -> RenderResult:
    """
    独立进程入口函数
    每个子进程创建独立的 CardRenderer 实例
    """
    card_source, options_dict, assets_path = args
    renderer = CardRenderer(assets_path=assets_path)
    options = RenderOptions(**options_dict)
    return renderer.render(card_source, options)

class BatchRenderer:
    def render(
        self,
        card_sources: List,
        options: RenderOptions,
        workers: int = 1,
        progress_callback: Callable = None,
    ) -> List[RenderResult]:
        if workers <= 1:
            # 主进程直接渲染
            return [self.renderer.render(s, options) for s in card_sources]
        
        # 多进程：每个子进程独立加载资源
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(render_single_card, ...) 
                       for ... in card_sources]
            results = [f.result() for f in futures]
        return results
```

注意事项：
- PIL Image 不可跨进程序列化，结果通过文件传递或进程内返回
- 字体/图片资源在子进程中独立加载（文件级共享，fork COW 优化）
- `progress_callback` 在主进程收集完成事件

### 11. CLI — `cli/main.py`

基于 `click` 库，子命令风格：

```bash
# 单卡渲染
arkham-card-maker render card.card
arkham-card-maker render card.card -o output.png --dpi 500 --bleed 3
arkham-card-maker render card.card -c arkham-card-maker.toml

# 批量渲染
arkham-card-maker batch "cards/*.card" --workers 4
arkham-card-maker batch cards/ -r --workers 8 -c config.toml

# 配置管理
arkham-card-maker config init        # 生成默认配置文件
arkham-card-maker config show        # 显示当前配置
arkham-card-maker config show --toml # 输出 TOML 格式
```

```python
@click.group()
def cli(): ...

@cli.command()
@click.argument("card", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), help="输出文件路径")
@click.option("--dpi", type=int, help="DPI")
@click.option("--bleed", type=int, help="出血mm")
@click.option("--format", type=click.Choice(["PNG", "JPG"]), help="输出格式")
@click.option("--quality", type=int, help="JPG质量")
@click.option("-c", "--config", type=click.Path(exists=True), help="配置文件")
def render(card, output, dpi, bleed, format, quality, config): ...

@cli.command()
@click.argument("pattern")
@click.option("-w", "--workers", type=int, default=1, help="并发进程数")
@click.option("-r", "--recursive", is_flag=True, help="递归搜索子目录")
@click.option("-o", "--output-dir", type=click.Path(), help="输出目录")
@click.option("-c", "--config", type=click.Path(exists=True), help="配置文件")
def batch(pattern, workers, recursive, output_dir, config): ...

@cli.group()
def config(): ...

@config.command("init")
@click.option("-f", "--force", is_flag=True, help="覆盖已有配置")
def config_init(force): ...

@config.command("show")
@click.option("--toml", "as_toml", is_flag=True, help="TOML格式输出")
def config_show(as_toml): ...
```

---

## 渲染管线对比

### 旧管线（二次渲染，仅作为金样对照）

```
generate_card_image(json, silence=False)
  → CardCreator.create_card()
    → 贴底图 ✓
    → 画UI ✓
    → 画文字 ✓  （实际画到图像上）
    → 返回 Card（含 last_render_list 元数据）
  → Card.get_text_layer_metadata()
  → 丢弃这张图！只用元数据

generate_card_image(json, silence=True)
  → CardCreator.create_card()
    → 贴底图 ✓
    → 画UI ✓
    → 跳过文字
    → 返回 Card（纯底图）
  
ExportHelper._bleeding(card_map.image)
  → 出血处理

ExportHelper._draw_text_layer(image, text_layer_metadata)
  → 用元数据重新画文字
```

### 新管线（一次渲染，本次实施目标）

```
CardCreator.create_card(layout_only=True)
  → 贴底图 ✓
  → 画UI ✓
  → 文本布局（仅计算，不画）→ text_layer_metadata
  → 返回 Card（底图 + 元数据）

BleedEngine.apply(card.image)
  → 出血处理

TextLayerCompositor.apply(image, text_layer_metadata)
  → 按元数据画文字
```

**性能收益**：省掉一整遍完整的图像创建/UI绘制/贴图操作；批量场景再叠加多进程并发收益。该收益是本次重构验收目标之一，不能降级为后续阶段。

---

## 迁移策略

### 原则
- **逐文件复制，不改渲染逻辑**：Card、CardCreator、RichTextRenderer 的核心计算逻辑原样迁移
- **只改组织方式**：import 路径、类名规范化、移除 Web 层耦合
- **像素级一致验证**：迁移前后用相同输入渲染，逐像素对比输出

### 文件迁移清单

| 原文件 | 新位置 | 改动 |
|--------|--------|------|
| `Card.py` | `arkham_card_maker/card.py` | 新增 `layout_only`，文字入口只计算元数据不落像素 |
| `create_card.py` | `arkham_card_maker/card_creator.py` | 新增 `layout_only` 参数；保留 `create_card_bottom_map()` 供旧链路对照；移除 `cProfile` 示例入口 |
| `card_cdapter.py` | `arkham_card_maker/card_adapter.py` | 无逻辑改动 |
| `ResourceManager.py` | `arkham_card_maker/resource_manager.py` | 移除 `bin.logger`/`bin.config_directory_manager` 依赖，保留字体/图片/语言配置/文本盒缓存行为 |
| `enhanced_draw.py` | `arkham_card_maker/enhanced_draw.py` | 无改动 |
| `ExportHelper.py` | 拆分到 `engine.py` + `bleeding/` | 枚举类 → `render_options.py`；出血逻辑 → `bleeding/`；文字层 → `engine.py` |
| `export_helper/LamaCleaner.py` | `arkham_card_maker/bleeding/lama_cleaner.py` | 无逻辑改动 |
| `rich_text_render/RichTextRenderer.py` | `arkham_card_maker/render/renderer.py` | 新增 `layout_only` 参数；布局和 `RenderItem` 生成必须等价旧路径 |
| `rich_text_render/HtmlTextParser.py` | `arkham_card_maker/render/parser.py` | 无改动 |
| `rich_text_render/VirtualTextBox.py` | `arkham_card_maker/render/text_box.py` | 无改动 |

### 必须覆盖的旧入口和调用点

- `server.py`：`/api/generate-card`、`/api/save-card`、`/api/export-card`、`/api/export-deck-image`、`/api/export-deck-pdf`、`/api/content-package/export-pnp` 是旧 Web 侧触发点。
- `bin/workspace_manager.py`：`generate_card_image()`、`generate_double_sided_card_image()`、`save_card_image()`、`save_card_image_enhanced()`、`_generate_thumbnail()`、`export_card_with_params()` 是旧渲染编排核心。
- `bin/deck_exporter.py`：导出牌库图片/PDF 时直接调用 `workspace_manager.generate_card_image()` 并读取文字层元数据。
- `bin/pnp_exporter.py`：通过 `ExportHelper.export_card_auto()` 导出 PNP 单卡图片。
- `ExportHelper.py`：`export_card()`、`export_double_sided_card()`、`export_card_auto()` 是出血导出的旧统一实现。
- `create_card.py`：`create_card()`、`create_card_bottom_map()`、全部 `create_*_card()` 类型分发和 `_preprocessing_json()` 是卡面像素逻辑。
- `Card.py`：`draw_centered_text()`、`draw_left_text()`、`draw_text()`、`get_text_layer_metadata()`、`get_upgrade_card_box_position()` 是文字层元数据来源。
- `ResourceManager.py`：`ImageManager.get_image_by_src()`、`get_card_base64()` 相关相对路径、语言配置和字体缓存会影响布局与像素。

### 不迁移的文件
- `server.py`, `app.py`, `main.py` — Flask/桌面/Android 入口
- `bin/workspace_manager.py` — 文件管理+Web编排（渲染部分已提取到 CardCreator/ExportHelper）
- `bin/deck_exporter.py`, `bin/pnp_exporter.py` — 旧项目牌库/PNP导出入口本身不迁移，但其调用到的渲染语义必须被金样覆盖
- `bin/tts_*` — TTS 相关
- `bin/gitHub_image.py`, `bin/image_uploader.py` — 图床
- `bin/content_package_manager.py` — 内容包
- `bin/card_numbering.py`, `bin/arkhamdb2card.py`, `bin/card2arkhamdb.py` — 数据转换
- `export_helper/main.py` — 独立图片批处理/圆角/出血，不属于本次卡图渲染主链路；若 CLI 后续需要批量处理普通图片再单独迁移
- `remaek_card/` — ArkhamDB 批量重制
- `ArkhamCardBuilder.py` — 内容包构建
- `create_pdf.py`, `setup.py`, `macapp.py`, `dmg_settings.py`

---

## 测试策略

### 像素级一致性验证
- 用 arkham-homebrew 和 arkham-card-maker 对同一 `.card` 文件渲染
- 使用 `PIL.ImageChops.difference()` 逐像素对比，允许 ±1 的浮点舍入误差
- 每种卡牌类型至少一个测试用例

### 单元测试
- `CardRenderer.render()` 各种输入格式（路径、字典）
- `BleedEngine` 各出血模式/模型
- `TextLayerCompositor` 文字层叠加
- `RenderOptions` 参数校验
- CLI 参数解析

### 集成测试
- 所有卡牌类型端到端渲染
- 双面卡牌正面+背面
- 多进程批量渲染正确性
- 配置文件加载与 CLI 覆盖

---

## 依赖

- **运行时**：Pillow >= 10, numpy, click, tomllib（Python 3.11+ 内置）或 tomli
- **可选**：opencv-python（EnhancedDraw 加速）、requests（LaMa 出血）
- **开发**：pytest, pytest-cov
