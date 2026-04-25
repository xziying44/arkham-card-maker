from typing import Tuple

from PIL import Image, ImageColor, ImageDraw, ImageFont

from .bleeding.engine import calculate_pixel_dimensions, is_horizontal
from .enhanced_draw import EnhancedDraw
from .render_options import BleedMode, ExportSize, RenderOptions


class TextLayerCompositor:
    """文字层叠加器，复刻旧 ExportHelper._draw_text_layer。"""

    def __init__(self, font_manager, options: RenderOptions, pixel_dimensions: tuple[int, int] | None = None):
        self.font_manager = font_manager
        self.options = options
        self.pixel_dimensions = pixel_dimensions or calculate_pixel_dimensions(
            options.dpi,
            options.normalized_bleed(),
            options.normalized_size(),
        )
        self._font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def _load_font(self, font_name: str, font_size: int) -> ImageFont.FreeTypeFont:
        cache_key = (font_name, font_size)
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        try:
            font = self.font_manager.get_font(font_name, font_size)
            if font is None:
                raise ValueError(f"字体不存在: {font_name}")
            self._font_cache[cache_key] = font
            return font
        except Exception as exc:
            print(f"警告：无法加载字体 {font_name} 大小 {font_size}，使用默认字体: {exc}")
            default_font = ImageFont.load_default()
            self._font_cache[cache_key] = default_font
            return default_font

    @staticmethod
    def _normalize_color(color_value) -> Tuple[int, int, int]:
        """将颜色值转换为 RGB 三元组。"""
        if color_value is None:
            return 0, 0, 0
        if isinstance(color_value, (tuple, list)):
            if len(color_value) >= 3:
                return tuple(int(color_value[i]) for i in range(3))
        if isinstance(color_value, int):
            hex_color = f"#{color_value:06x}"
            try:
                return ImageColor.getrgb(hex_color)
            except ValueError:
                return 0, 0, 0
        if isinstance(color_value, str):
            try:
                return ImageColor.getrgb(color_value)
            except ValueError:
                return 0, 0, 0
        return 0, 0, 0

    def _prepare_effects(self, effects_config) -> list[dict]:
        """规范化特效配置。"""
        if not isinstance(effects_config, list):
            return []
        sanitized = []
        for effect in effects_config:
            if isinstance(effect, dict):
                cfg = effect.copy()
                if "color" in cfg:
                    cfg["color"] = self._normalize_color(cfg["color"])
                sanitized.append(cfg)
        return sanitized

    def apply(self, card_map: Image.Image, text_layer: list[dict] | None) -> Image.Image:
        if not text_layer:
            return card_map

        dpi_scale_factor = self.options.dpi / 300.0
        bleed = self.options.normalized_bleed()
        if self.options.normalized_bleed_mode() == BleedMode.STRETCH:
            width, height = calculate_pixel_dimensions(bleed=bleed, size=ExportSize.SIZE_61_88)
            target_width, target_height = calculate_pixel_dimensions(self.options.dpi, bleed, ExportSize.SIZE_61_88)
        else:
            width, height = calculate_pixel_dimensions(bleed=bleed, size=self.options.normalized_size())
            target_width, target_height = self.pixel_dimensions

        bleed_offset = (
            int((width - 739) / 2) * dpi_scale_factor,
            int((height - 1049) / 2) * dpi_scale_factor,
        )

        if is_horizontal(card_map):
            card_map = card_map.resize((target_height, target_width), Image.Resampling.LANCZOS)
        else:
            card_map = card_map.resize((target_width, target_height), Image.Resampling.LANCZOS)

        if is_horizontal(card_map):
            bleed_offset_x = bleed_offset[1]
            bleed_offset_y = bleed_offset[0]
        else:
            bleed_offset_x = bleed_offset[0]
            bleed_offset_y = bleed_offset[1]

        enhanced_text_items = []
        fast_text_items = []
        image_items = []

        for text_info in text_layer:
            try:
                if text_info.get("type") == "image":
                    img = text_info.get("image")
                    if img is None:
                        continue
                    x = (text_info.get("x", 0) + text_info.get("offset_x", 0)) * dpi_scale_factor + bleed_offset_x
                    y = (text_info.get("y", 0) + text_info.get("offset_y", 0)) * dpi_scale_factor + bleed_offset_y
                    new_width = max(1, int(text_info.get("width", img.size[0]) * dpi_scale_factor))
                    new_height = max(1, int(text_info.get("height", img.size[1]) * dpi_scale_factor))
                    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    image_items.append((int(x), int(y), resized_img))
                    continue

                text = text_info.get("text", "")
                x = (text_info.get("x", 0) + text_info.get("offset_x", 0)) * dpi_scale_factor + bleed_offset_x
                y = (text_info.get("y", 0) + text_info.get("offset_y", 0)) * dpi_scale_factor + bleed_offset_y
                font_name = text_info.get("font", "default")
                font_size = int(text_info.get("font_size", 12) * dpi_scale_factor)
                color = text_info.get("color", "#000000")
                opacity_value = text_info.get("opacity", 100)
                try:
                    opacity = max(0, min(100, int(opacity_value)))
                except (ValueError, TypeError):
                    opacity = 100
                effects = self._prepare_effects(text_info.get("effects"))
                border_width = int(text_info.get("border_width", 0) * dpi_scale_factor)
                border_color = text_info.get("border_color", "#FFFFFF")

                font = self._load_font(font_name, font_size)
                normalized_color = self._normalize_color(color)
                normalized_border_color = self._normalize_color(border_color)
                use_enhanced = (opacity != 100) or bool(effects)

                if use_enhanced and border_width > 0:
                    effects = [{
                        "type": "stroke",
                        "size": max(1, border_width),
                        "opacity": 100,
                        "color": normalized_border_color,
                    }] + effects

                if use_enhanced:
                    enhanced_text_items.append(((x, y), text, font, normalized_color, opacity, effects))
                else:
                    fast_text_items.append((x, y, text, font, normalized_color, border_width, normalized_border_color))
            except Exception as exc:
                print(f"警告：绘制文字时发生错误 - 文字: '{text_info.get('text', 'N/A')}', 错误: {exc}")
                continue

        if enhanced_text_items:
            drawer = EnhancedDraw(card_map)
            drawer.text_batch(enhanced_text_items)
            card_map = drawer.get_image()

        if fast_text_items:
            draw = ImageDraw.Draw(card_map)
            for x, y, text, font, fill, border_width, border_color in fast_text_items:
                if border_width > 0:
                    for dx in range(-border_width, border_width + 1):
                        for dy in range(-border_width, border_width + 1):
                            if dx != 0 or dy != 0:
                                draw.text((x + dx, y + dy), text, font=font, fill=border_color)
                draw.text((x, y), text, font=font, fill=fill)

        if image_items:
            for x, y, img in image_items:
                if img.mode == "RGBA":
                    card_map.paste(img, (x, y), img)
                else:
                    card_map.paste(img, (x, y))

        if self.options.normalized_bleed_mode() == BleedMode.STRETCH:
            if is_horizontal(card_map):
                card_map = card_map.resize((self.pixel_dimensions[1], self.pixel_dimensions[0]), Image.Resampling.LANCZOS)
            else:
                card_map = card_map.resize((self.pixel_dimensions[0], self.pixel_dimensions[1]), Image.Resampling.LANCZOS)
        return card_map
