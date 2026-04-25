import enum
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image


class ExportFormat(enum.Enum):
    """导出格式。"""

    PNG = "PNG"
    JPG = "JPG"


class ExportSize(enum.Enum):
    """导出规格。"""

    SIZE_61_88 = "61mm × 88mm"
    SIZE_61_5_88 = "61.5mm × 88mm"
    SIZE_62_88 = "62mm × 88mm"
    POKER_SIZE = "63.5mm × 88.9mm (2.5″ × 3.5″)"


class ExportBleed(enum.Enum):
    """出血规格，单位 mm。"""

    NONE = 0
    TWO_MM = 2
    THREE_MM = 3


class BleedMode(enum.Enum):
    """出血模式。"""

    CROP = "裁剪"
    STRETCH = "拉伸"


class BleedModel(enum.Enum):
    """出血模型。"""

    MIRROR = "镜像出血"
    LAMA = "LaMa模型出血"


def parse_enum(value, enum_class, param_name: str):
    """解析枚举参数，兼容枚举值和枚举名。"""
    if isinstance(value, enum_class):
        return value
    try:
        return enum_class(value)
    except ValueError:
        if isinstance(value, str):
            try:
                return enum_class[value.upper()]
            except KeyError:
                pass
    valid_options = ", ".join([f"'{item.value}'" for item in enum_class])
    raise ValueError(f"无效的参数 '{param_name}': '{value}'。有效选项为: {valid_options}")


@dataclass
class RenderOptions:
    dpi: int = 300
    format: str = "PNG"
    quality: int = 95
    size: str = ExportSize.POKER_SIZE.value
    bleed: int = 0
    bleed_mode: str = "裁剪"
    bleed_model: str = "镜像出血"
    saturation: float = 1.0
    brightness: float = 1.0
    gamma: float = 1.0
    double_sided: bool = True
    lama_base_url: str = "http://localhost:8080"
    working_dir: str = ""
    assets_path: str = ""

    def normalized_format(self) -> ExportFormat:
        return parse_enum(self.format.upper(), ExportFormat, "格式")

    def normalized_bleed(self) -> ExportBleed:
        return parse_enum(int(self.bleed), ExportBleed, "出血")

    def normalized_size(self) -> ExportSize:
        return parse_enum(self.size, ExportSize, "规格")

    def normalized_bleed_mode(self) -> BleedMode:
        return parse_enum(self.bleed_mode, BleedMode, "出血模式")

    def normalized_bleed_model(self) -> BleedModel:
        return parse_enum(self.bleed_model, BleedModel, "出血模型")

    def validate(self) -> None:
        if self.dpi <= 0:
            raise ValueError("DPI 必须是正数。")
        if not 0 <= int(self.quality) <= 100:
            raise ValueError("导出质量 quality 必须在 0 到 100 之间。")
        self.normalized_format()
        self.normalized_bleed()
        self.normalized_size()
        self.normalized_bleed_mode()
        self.normalized_bleed_model()


@dataclass
class RenderResult:
    front: Image.Image
    back: Optional[Image.Image] = None
    metadata: dict = field(default_factory=dict)
    options: RenderOptions = field(default_factory=RenderOptions)

    def _save_one(self, image: Image.Image, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        export_format = self.options.normalized_format()
        dpi_info = (self.options.dpi, self.options.dpi)
        if export_format == ExportFormat.JPG:
            image.convert("RGB").save(path, format="JPEG", quality=self.options.quality, dpi=dpi_info)
        else:
            image.save(path, format="PNG", dpi=dpi_info)
        return str(path)

    def save(self, output_path: str | Path) -> str:
        return self._save_one(self.front, output_path)

    def save_all(self, output_stem: str | Path) -> list[str]:
        stem = Path(output_stem)
        suffix = ".jpg" if self.options.normalized_format() == ExportFormat.JPG else ".png"
        if self.back is None:
            path = stem if stem.suffix else stem.with_suffix(suffix)
            return [self._save_one(self.front, path)]
        front_path = stem.with_name(stem.name + "_a").with_suffix(suffix)
        back_path = stem.with_name(stem.name + "_b").with_suffix(suffix)
        return [self._save_one(self.front, front_path), self._save_one(self.back, back_path)]
