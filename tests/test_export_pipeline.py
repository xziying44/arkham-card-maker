from arkham_card_maker.bleeding.engine import calculate_pixel_dimensions
from arkham_card_maker.render_options import ExportBleed, ExportSize


def test_calculate_pixel_dimensions_matches_old_formula():
    assert calculate_pixel_dimensions(300, ExportBleed.THREE_MM, ExportSize.POKER_SIZE) == (821, 1121)


def test_worker_reuses_renderer_in_process(monkeypatch, tmp_path):
    import arkham_card_maker.worker as worker

    created = 0

    class FakeResult:
        def save_all(self, output_stem):
            return [str(output_stem) + ".png"]

    class FakeRenderer:
        def __init__(self, assets_path=None):
            nonlocal created
            created += 1

        def render(self, card_path, options):
            return FakeResult()

    monkeypatch.setattr(worker, "CardRenderer", FakeRenderer)
    monkeypatch.setattr(worker, "_PROCESS_RENDERER", None, raising=False)
    options = {"bleed": 0}

    worker.render_single_card(("a.card", str(tmp_path / "a"), options, None))
    worker.render_single_card(("b.card", str(tmp_path / "b"), options, None))

    assert created == 1
