from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

from .engine import CardRenderer
from .render_options import RenderOptions


def render_single_card(args: tuple) -> dict:
    """子进程渲染单张卡牌并保存到文件。"""
    card_path, output_stem, options_dict, assets_path = args
    options = RenderOptions(**options_dict)
    renderer = CardRenderer(assets_path=assets_path)
    result = renderer.render(card_path, options)
    saved_files = result.save_all(output_stem)
    return {"card": str(card_path), "saved_files": saved_files}


class BatchRenderer:
    """批量渲染器。"""

    def __init__(self, renderer: CardRenderer | None = None, assets_path: str | None = None):
        self.renderer = renderer or CardRenderer(assets_path=assets_path)
        self.assets_path = assets_path

    def render(self, card_sources: Iterable[str | Path], output_dir: str | Path,
               options: RenderOptions | None = None, workers: int = 1,
               progress_callback: Callable[[dict], None] | None = None) -> list[dict]:
        options = options or RenderOptions()
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        cards = [Path(card) for card in card_sources]
        if workers <= 1:
            results = []
            for card in cards:
                local_options = RenderOptions(**{**options.__dict__, "working_dir": str(card.parent)})
                result = self.renderer.render(card, local_options)
                item = {"card": str(card), "saved_files": result.save_all(output_path / card.stem)}
                results.append(item)
                if progress_callback:
                    progress_callback(item)
            return results
        tasks = []
        for card in cards:
            option_dict = {**options.__dict__, "working_dir": str(card.parent)}
            tasks.append((str(card), str(output_path / card.stem), option_dict, self.assets_path))
        results = []
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(render_single_card, task) for task in tasks]
            for future in as_completed(futures):
                item = future.result()
                results.append(item)
                if progress_callback:
                    progress_callback(item)
        return results
