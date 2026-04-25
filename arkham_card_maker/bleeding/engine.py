import math
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

from .lama_cleaner import LamaCleaner
from ..render_options import BleedMode, BleedModel, ExportBleed, ExportSize, RenderOptions

MM_PER_INCH = 25.4
SPECIFICATIONS = {
    ExportSize.SIZE_61_88: (61.0, 88.0),
    ExportSize.SIZE_61_5_88: (61.5, 88.0),
    ExportSize.SIZE_62_88: (62.0, 88.0),
    ExportSize.POKER_SIZE: (63.5, 88.9),
}


def calculate_pixel_dimensions(dpi: int = 300, bleed: ExportBleed = ExportBleed.TWO_MM,
                               size: ExportSize = ExportSize.SIZE_61_88) -> Tuple[int, int]:
    base_width_mm, base_height_mm = SPECIFICATIONS[size]
    total_width_mm = base_width_mm + (2 * bleed.value)
    total_height_mm = base_height_mm + (2 * bleed.value)
    return round(total_width_mm / MM_PER_INCH * dpi), round(total_height_mm / MM_PER_INCH * dpi)


def is_horizontal(image: Image.Image) -> bool:
    return image.size[0] > image.size[1]


class BleedEngine:
    """出血处理引擎，复刻旧 ExportHelper 的主流程。"""

    def __init__(self, options: RenderOptions):
        self.options = options
        self.dpi = options.dpi
        self.bleed = options.normalized_bleed()
        self.size = options.normalized_size()
        self.bleed_mode = options.normalized_bleed_mode()
        self.bleed_model = options.normalized_bleed_model()
        self.pixel_width, self.pixel_height = calculate_pixel_dimensions(self.dpi, self.bleed, self.size)
        self.lama_cleaner = LamaCleaner(options.lama_base_url)

    def _target_dimensions(self, card_json: dict) -> tuple[int, int]:
        if card_json.get("type", "") == "调查员小卡":
            total_w_mm = 41.0 + 2 * self.bleed.value
            total_h_mm = 63.0 + 2 * self.bleed.value
            return round((total_w_mm / MM_PER_INCH) * self.dpi), round((total_h_mm / MM_PER_INCH) * self.dpi)
        if self.bleed_mode == BleedMode.STRETCH:
            return calculate_pixel_dimensions(bleed=self.bleed, size=ExportSize.SIZE_61_88)
        return calculate_pixel_dimensions(bleed=self.bleed, size=self.size)

    def _call_lama_cleaner(self, image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        if self.bleed_model == BleedModel.LAMA:
            return self.lama_cleaner.outpaint_extend(image, target_width, target_height)
        return self.lama_cleaner.outpaint_mirror_extend(image, target_width, target_height)

    def _standard_bleeding(self, card_json: dict, image: Image.Image, image_manager) -> Image.Image:
        ui_name = "出血_"
        card_type = card_json.get("type", "")
        if card_json.get("class", "") == "弱点":
            ui_name += "弱点" + card_type
        elif card_type == "调查员卡背":
            ui_name += "调查员卡" + "-" + card_json.get("class", "") + "-卡背"
        elif card_type in ["场景卡", "密谋卡"] and card_json.get("is_back", False):
            ui_name += card_type + "-卡背"
        elif card_type in ["场景卡", "密谋卡"] and not card_json.get("is_back", False) and card_json.get("mirror", False):
            ui_name += card_type + "-镜像"
        else:
            ui_name += card_type
            if card_type in ["事件卡", "技能卡", "支援卡", "调查员卡"]:
                ui_name += "-" + card_json.get("class", "")
        if card_type == "地点卡":
            ui_name += "-" + card_json.get("location_type", "已揭示")
        if card_type in ["地点卡", "敌人卡"] and card_json.get("subtitle", "") != "":
            ui_name += "-副标题"
        if card_type == "调查员卡":
            ui_name += "-底图"
        ui = image_manager.get_image(ui_name) if image_manager else None
        if ui:
            card_map = self._call_lama_cleaner(image, 1087, 768) if is_horizontal(image) else self._call_lama_cleaner(image, 768, 1087)
            card_map.paste(ui, (0, 0, ui.size[0], ui.size[1]), ui)
        else:
            card_map = image
        return self._bleeding_submit_icon(card_json, card_map, image_manager)

    def _bleeding_submit_icon(self, card_json: dict, card_map: Image.Image, image_manager) -> Image.Image:
        if not image_manager or "大画" in card_json.get("type", ""):
            return card_map
        submit_index = 0
        card_class = card_json.get("class", "")
        if "submit_icon" in card_json and isinstance(card_json["submit_icon"], list):
            for icon in card_json["submit_icon"]:
                img = image_manager.get_image(f"投入-{card_class}-{icon}")
                if not img:
                    continue
                img = img.crop((0, 0, 15, img.size[1]))
                offset = 20 if card_json.get("type") == "事件卡" else 19
                card_map.paste(img, (0, 167 + submit_index * 80 + offset), img)
                submit_index += 1
        return card_map

    def apply(self, card_json: dict, image: Image.Image, image_manager=None) -> Image.Image:
        width, height = self._target_dimensions(card_json)
        card_map = image.copy()
        if card_json.get("use_external_image", 0) != 1:
            card_map = self._standard_bleeding(card_json, card_map, image_manager)
        card_map = self._call_lama_cleaner(card_map, height, width) if is_horizontal(card_map) else self._call_lama_cleaner(card_map, width, height)
        if self.bleed_model == BleedModel.LAMA and self.bleed == ExportBleed.THREE_MM:
            mask_optimized = Image.new("RGB", card_map.size, (0, 0, 0))
            draw = ImageDraw.Draw(mask_optimized)
            draw.rectangle([0, 0, 30, 30], fill=(255, 255, 255))
            card_map = self.lama_cleaner.inpaint(image=card_map, mask=mask_optimized)
        return card_map


class ImageAdjustments:
    """图像后处理。"""

    @staticmethod
    def apply(image: Image.Image, saturation: float = 1.0, brightness: float = 1.0, gamma: float = 1.0) -> Image.Image:
        if not math.isclose(saturation, 1.0):
            image = ImageEnhance.Color(image).enhance(saturation)
        if not math.isclose(brightness, 1.0):
            image = ImageEnhance.Brightness(image).enhance(brightness)
        if not math.isclose(gamma, 1.0):
            img_array = np.array(image, dtype=np.float32) / 255.0
            img_array = np.power(img_array, gamma)
            img_array = np.clip(img_array, 0, 1)
            image = Image.fromarray((img_array * 255).astype(np.uint8))
        return image
