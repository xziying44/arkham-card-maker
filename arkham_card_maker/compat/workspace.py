import base64
import io
import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from ..card import Card
from ..card_creator import CardCreator
from ..resource_manager import FontManager, ImageManager


class RenderWorkspace:
    """渲染专用的最小工作区适配器。"""

    def __init__(self, workspace_path: str | os.PathLike | None = None,
                 assets_path: str | os.PathLike | None = None,
                 config: Optional[Dict[str, Any]] = None):
        package_root = Path(__file__).resolve().parents[2]
        self.assets_path = Path(assets_path) if assets_path else package_root
        self.workspace_path = Path(workspace_path or os.getcwd())
        self.config = config or {}
        self.font_manager = FontManager(font_folder=str(self.assets_path / "fonts"), lang="zh")
        self.image_manager = ImageManager(image_folder=str(self.assets_path / "images"))
        self.image_manager.set_working_directory(str(self.workspace_path))
        self.creator = CardCreator(self.font_manager, self.image_manager)
        self.card_lock = threading.Lock()

    def _get_absolute_path(self, relative_path: str) -> str:
        path = Path(relative_path)
        if path.is_absolute():
            return str(path)
        return str(self.workspace_path / path)

    def get_file_content(self, file_path: str) -> Optional[str]:
        abs_path = Path(self._get_absolute_path(file_path))
        if not abs_path.exists():
            return None
        return abs_path.read_text(encoding="utf-8")

    def get_card_base64(self, json_data: Dict[str, Any], field: str = "picture_base64"):
        picture_path = json_data.get("picture_path", None)
        picture_base64 = json_data.get(field, "")
        if isinstance(picture_base64, str) and picture_base64.strip():
            try:
                base64_data = picture_base64.split(",", 1)[1] if picture_base64.startswith("data:image/") else picture_base64
                with Image.open(io.BytesIO(base64.b64decode(base64_data))) as img:
                    return img.copy()
            except Exception as exc:
                print(f"解码base64图片数据失败: {exc}")
                return None
        if picture_path and not os.path.isabs(str(picture_path)):
            full_picture_path = self._get_absolute_path(str(picture_path))
            if os.path.exists(full_picture_path):
                return full_picture_path
        return picture_path

    @staticmethod
    def center_crop_if_larger(image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        target_width, target_height = target_size
        img_width, img_height = image.size
        if img_width <= target_width and img_height <= target_height:
            return image
        left = max((img_width - target_width) // 2, 0)
        top = max((img_height - target_height) // 2, 0)
        right = min(left + target_width, img_width)
        bottom = min(top + target_height, img_height)
        return image.crop((left, top, right, bottom))

    def _load_cardback(self, card_type: str):
        mapping = {
            "玩家卡背": "cardback/player-back.jpg",
            "遭遇卡背": "cardback/encounter-back.jpg",
            "定制卡背": "cardback/upgrade-back.png",
            "敌库卡背": "cardback/enemy-back.png",
        }
        filename = mapping.get(card_type)
        if not filename:
            return None
        cardback_path = self.assets_path / filename
        if hasattr(sys, "_MEIPASS"):
            cardback_path = Path(sys._MEIPASS) / filename
        if not cardback_path.exists():
            print(f"卡背图片不存在: {cardback_path}")
            return None
        with Image.open(cardback_path) as img:
            cardback_pil = img.copy()
        cardback_pil = self.center_crop_if_larger(cardback_pil, (739, 1049))
        return Card(cardback_pil.width, cardback_pil.height, image=cardback_pil)

    def _load_external_image_card(self, json_data: Dict[str, Any], card_type: str):
        if json_data.get("use_external_image", 0) != 1:
            return None
        external_image = self.get_card_base64(json_data, "external_image")
        if not isinstance(external_image, Image.Image):
            return None
        target_size = (739, 1049)
        if card_type in ["调查员", "调查员卡", "调查员背面", "调查员卡背", "密谋卡", "密谋卡-大画", "场景卡", "场景卡-大画"]:
            target_size = (1049, 739)
        target_w, target_h = target_size
        src_w, src_h = external_image.size
        src_ratio = src_w / src_h
        target_ratio = target_w / target_h
        if src_ratio > target_ratio:
            new_h = target_h
            new_w = int(src_ratio * new_h)
        else:
            new_w = target_w
            new_h = int(new_w / src_ratio)
        external_image = external_image.resize((new_w, new_h), Image.LANCZOS)
        left = max((new_w - target_w) // 2, 0)
        top = max((new_h - target_h) // 2, 0)
        external_image = external_image.crop((left, top, left + target_w, top + target_h))
        return Card(external_image.width, external_image.height, image=external_image)

    def generate_card_image(self, json_data: Dict[str, Any], layout_only: bool = False, silence: bool = False):
        try:
            card_type = json_data.get("type", "")
            card = self._load_cardback(card_type)
            if card is not None:
                return card
            card = self._load_external_image_card(json_data, card_type)
            if card is not None:
                return card
            language = json_data.get("language", "zh")
            self.font_manager.set_lang(language)
            with self.card_lock:
                if silence:
                    card = self.creator.create_card_bottom_map(json_data, picture_path=self.get_card_base64(json_data))
                else:
                    card = self.creator.create_card(json_data, picture_path=self.get_card_base64(json_data), layout_only=layout_only)
            if card is None:
                return None
            encounter_group = json_data.get("encounter_group", None)
            encounter_groups_dir = self.config.get("encounter_groups_dir", None)
            if encounter_group and encounter_groups_dir:
                encounter_path = self._get_absolute_path(os.path.join(encounter_groups_dir, encounter_group + ".png"))
                if os.path.exists(encounter_path):
                    with Image.open(encounter_path) as encounter_img:
                        card.set_encounter_icon(encounter_img.copy())
            illustrator = ""
            footer_copyright = ""
            encounter_group_number = ""
            card_number = ""
            if not silence:
                illustrator = json_data.get("illustrator", "")
                footer_copyright = json_data.get("footer_copyright", "") or self.config.get("footer_copyright", "")
                encounter_group_number = json_data.get("encounter_group_number", "")
                card_number = json_data.get("card_number", "")
            if card_type != "调查员小卡":
                footer_icon_name = json_data.get("footer_icon_path", "") or self.config.get("footer_icon_dir", "")
                footer_icon_font_value = json_data.get("footer_icon_font", "") or None
                footer_icon = None
                if not footer_icon_font_value and footer_icon_name:
                    footer_icon_path = self._get_absolute_path(footer_icon_name)
                    if os.path.exists(footer_icon_path):
                        with Image.open(footer_icon_path) as icon_img:
                            footer_icon = icon_img.copy()
                footer_effects = None
                footer_opacity = None
                footer_font_color = None
                if card_type == "调查员" and json_data.get("investigator_footer_type", "normal") == "big-art":
                    footer_effects = [
                        {"type": "glow", "size": 8, "spread": 22, "opacity": 36, "color": (3, 0, 0)},
                        {"type": "stroke", "size": 2, "opacity": 63, "color": (165, 157, 153)},
                    ]
                    footer_opacity = 75
                    footer_font_color = (3, 0, 0)
                card.set_footer_information(
                    illustrator,
                    footer_copyright,
                    encounter_group_number,
                    card_number,
                    footer_icon=footer_icon if not footer_icon_font_value else None,
                    footer_icon_font=footer_icon_font_value if footer_icon_font_value else None,
                    footer_effects=footer_effects,
                    footer_opacity=footer_opacity,
                    footer_font_color=footer_font_color,
                )
            return card
        except Exception as exc:
            traceback.print_exc()
            print(f"生成卡图失败: {exc}")
            return None

    def prepare_back_json(self, front_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        back_json = dict(front_json.get("back") or {})
        if not back_json:
            return None
        if "version" not in back_json:
            back_json["version"] = front_json.get("version", "2.0")
        if "language" not in back_json:
            back_json["language"] = front_json.get("language", "zh")
        back_json["is_back"] = True
        if "front_name" not in back_json and isinstance(front_json.get("name"), str):
            back_json["front_name"] = front_json.get("name")
        share_flag = back_json.get("share_front_picture", 0)
        if isinstance(share_flag, str):
            share_flag = 1 if share_flag == "1" else 0
        if share_flag:
            if front_json.get("picture_base64"):
                back_json["picture_base64"] = front_json.get("picture_base64")
            if front_json.get("picture_layout"):
                back_json["picture_layout"] = front_json.get("picture_layout")
            if not back_json.get("image_filter"):
                back_json["image_filter"] = "grayscale"
        return back_json

    def generate_double_sided_card_image(self, json_data: Dict[str, Any], layout_only: bool = False, silence: bool = False):
        front_card = self.generate_card_image(json_data, layout_only=layout_only, silence=silence)
        back_json = self.prepare_back_json(json_data)
        back_card = self.generate_card_image(back_json, layout_only=layout_only, silence=silence) if back_json else None
        return {"front": front_card, "back": back_card}
