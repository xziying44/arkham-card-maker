import json
import os
from pathlib import Path
from typing import Any

from .bleeding.engine import BleedEngine, ImageAdjustments
from .compat.workspace import RenderWorkspace
from .compositor import TextLayerCompositor
from .render_options import RenderOptions, RenderResult


class CardRenderer:
    """卡牌渲染统一入口。"""

    def __init__(self, assets_path: str | None = None, config: dict | None = None):
        self.assets_path = assets_path
        self.config = config or {}
        self._workspace_cache: dict[tuple[str, str, str], RenderWorkspace] = {}

    def _workspace_cache_key(self, workspace_path: str | None, assets_path: str | None) -> tuple[str, str, str]:
        workspace_key = str(Path(workspace_path or os.getcwd()).resolve())
        assets_key = str(Path(assets_path).resolve()) if assets_path else ""
        config_key = json.dumps(self.config, sort_keys=True, default=str, ensure_ascii=False)
        return workspace_key, assets_key, config_key

    def _get_workspace(self, workspace_path: str | None, assets_path: str | None) -> RenderWorkspace:
        key = self._workspace_cache_key(workspace_path, assets_path)
        workspace = self._workspace_cache.get(key)
        if workspace is None:
            workspace = RenderWorkspace(workspace_path=workspace_path, assets_path=assets_path, config=self.config)
            self._workspace_cache[key] = workspace
        return workspace

    def clear_workspace_cache(self) -> None:
        self._workspace_cache.clear()

    def _load_card_source(self, card_source: str | Path | dict[str, Any]) -> tuple[dict[str, Any], Path | None]:
        if isinstance(card_source, dict):
            return dict(card_source), None
        path = Path(card_source)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), path
        if isinstance(card_source, str):
            try:
                data = json.loads(card_source)
                if isinstance(data, dict):
                    return data, None
            except Exception as exc:
                raise ValueError(f"卡牌文件不存在，且输入不是合法 JSON：{card_source}") from exc
        raise ValueError("卡牌来源必须是 .card 文件路径或字典。")

    def _render_one(self, workspace: RenderWorkspace, card_json: dict[str, Any], options: RenderOptions):
        card_json = workspace.creator._preprocessing_json(dict(card_json))
        card = workspace.generate_card_image(card_json, layout_only=True, silence=False)
        if card is None:
            raise ValueError("生成卡图失败。")
        bleed_engine = BleedEngine(options)
        card_map_image = bleed_engine.apply(card_json, card.image, workspace.image_manager)
        text_layer = card.get_text_layer_metadata()
        compositor = TextLayerCompositor(workspace.font_manager, options, (bleed_engine.pixel_width, bleed_engine.pixel_height))
        card_map_image = compositor.apply(card_map_image, text_layer)
        card_map_image = ImageAdjustments.apply(card_map_image, options.saturation, options.brightness, options.gamma)
        return card_map_image, text_layer

    def render(self, card_source: str | Path | dict[str, Any], options: RenderOptions | None = None) -> RenderResult:
        options = options or RenderOptions()
        options.validate()
        card_json, source_path = self._load_card_source(card_source)
        workspace_path = options.working_dir or (str(source_path.parent) if source_path else None)
        assets_path = options.assets_path or self.assets_path
        workspace = self._get_workspace(workspace_path, assets_path)
        front, front_metadata = self._render_one(workspace, card_json, options)
        back = None
        back_metadata = None
        if options.double_sided and card_json.get("version") == "2.0":
            back_json = workspace.prepare_back_json(card_json)
            if back_json:
                back, back_metadata = self._render_one(workspace, back_json, options)
        return RenderResult(front=front, back=back, metadata={"front_text_layer": front_metadata, "back_text_layer": back_metadata}, options=options)
