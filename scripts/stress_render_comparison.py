from __future__ import annotations

import csv
import json
import statistics
import sys
import time
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw

REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO / "render-stress-comparisons" / datetime.now().strftime("%Y%m%d-%H%M%S")
CARDS_DIR = OUT_ROOT / "cards"
OLD_DIR = OUT_ROOT / "old"
NEW_DIR = OUT_ROOT / "new"
DIFF_DIR = OUT_ROOT / "diff"
SHEET_DIR = OUT_ROOT / "sheets"
BATCH_DIR = OUT_ROOT / "batch"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.generate_all_type_comparison import (  # noqa: E402
    OldWorkspace,
    cleanup_old_modules,
    load_old_modules,
    make_diff,
    make_index,
    make_sample_art,
    make_sheet,
    save_result,
)
from arkham_card_maker import CardRenderer, RenderOptions  # noqa: E402
from arkham_card_maker.worker import BatchRenderer  # noqa: E402


@contextmanager
def quiet_render():
    """压测时屏蔽旧项目大量日志，避免计时被终端输出主导。"""
    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        yield


def common(card_type: str, name: str, **extra: Any) -> dict[str, Any]:
    data = {
        "version": "1.0",
        "language": "zh",
        "type": card_type,
        "name": name,
        "subtitle": "副标题",
        "class": "中立",
        "body": "基础正文。<br>用于压测渲染一致性。",
        "flavor": "基础风味文本。",
        "traits": ["测试", "压测"],
        "cost": 1,
        "level": 0,
        "submit_icon": ["意志"],
        "slots": "手部",
        "health": 1,
        "horror": 1,
        "victory": None,
        "picture_path": "sample-art.png",
        "encounter_group": "",
        "footer_copyright": "",
        "illustrator": "压测",
        "card_number": "999",
        "encounter_group_number": "9/9",
    }
    data.update(extra)
    return data


def rich_body() -> str:
    return """<b>粗体</b>、<i>斜体</i>、<trait>特质</trait>与普通文字混排。<br>
<font name="思源黑体" addsize="4" offset="-2">字体切换与偏移</font>，<size relative="-4"/>字号调整后继续排版。<br>
<center>居中行：<免费> <反应> <启动></center><right>右对齐行：<骷髅> <异教徒> <古神></right>
<hr/><par/>段落后文字，含&nbsp;不断行空格、Emoji 图标 🧠 📚 👊 🦶。<br>
<flavor quote="true" align="left" padding="8" flex="false">引用风味第一行。<br>引用风味第二行。</flavor>
<iblock icon="启动" gap="8">图标块第一行会产生悬挂缩进，第二行用于验证换行后的缩进是否一致。</iblock>
<column gap="18"><col weight="1">左列A<br>左列B <img src="ui-damage" width="18" height="18" offset="-2"/></col><col weight="2">右列包含更长文本，验证分栏权重、列间距和换列后的布局。</col></column>"""


def dense_body() -> str:
    parts = []
    for idx in range(1, 12):
        parts.append(
            f"<iblock icon=\"免费\" gap=\"6\">第{idx}条：<b>粗体</b>、<i>斜体</i>、<font name=\"思源黑体\" addsize=\"2\" offset=\"-1\">中文字体</font>，含 <点> 与 <祝福>。</iblock>"
        )
    return "<br>".join(parts)


def build_stress_samples() -> list[tuple[str, dict[str, Any]]]:
    return [
        ("rich_event_tags", common("事件卡", "富文本事件", body=rich_body(), flavor="")),
        ("rich_asset_dense", common("支援卡", "密集标签支援", body=dense_body(), flavor="", health=2, horror=2, slots2="饰品")),
        ("rich_skill_icons", common("技能卡", "图标技能", body="<center><意志> <知识> <战力> <敏捷> <任意></center><br><flavor align=\"center\">多图标与居中文本。</flavor>", flavor="")),
        ("large_event_tags", common("大画-事件卡", "大画富文本事件", body=rich_body(), flavor="", cost=2)),
        ("large_asset_stats", common("大画-支援卡", "大画数值支援", body=dense_body(), flavor="", health=3, horror=2, victory=1)),
        ("act_column_tags", common("场景卡", "分栏场景", body=rich_body(), flavor="", threshold="5")),
        ("agenda_flavor_tags", common("密谋卡", "风味密谋", body="<flavor quote=\"true\" align=\"right\" padding=\"5\">右对齐引用风味。</flavor><par/>" + dense_body(), flavor="", threshold="6")),
        ("weakness_enemy_tags", common("敌人卡", "标签弱点敌人", body=rich_body(), flavor="", **{"class": "弱点", "weakness_type": "基础弱点", "attack": "3", "enemy_health": "4", "evade": "2", "enemy_damage": 1, "enemy_damage_horror": 1})),
    ]


def options_matrix() -> list[dict[str, Any]]:
    matrix = []
    for dpi in [150, 300, 500]:
        for bleed in [0, 2, 3]:
            for bleed_mode in ["裁剪", "拉伸"]:
                matrix.append({"dpi": dpi, "bleed": bleed, "bleed_mode": bleed_mode})
    return matrix


def render_old(card_file: Path, workspace: OldWorkspace, options: RenderOptions):
    ExportHelper = load_old_modules()
    helper = ExportHelper({
        "format": options.format,
        "size": options.size,
        "dpi": options.dpi,
        "bleed": options.bleed,
        "bleed_mode": options.bleed_mode,
        "bleed_model": options.bleed_model,
        "quality": options.quality,
        "saturation": options.saturation,
        "brightness": options.brightness,
        "gamma": options.gamma,
    }, workspace)
    return helper.export_card_auto(card_file.name)


def render_new(card_file: Path, options: RenderOptions):
    cleanup_old_modules()
    renderer = CardRenderer()
    return renderer.render(card_file, options)


def timed_call(func, *args):
    start = time.perf_counter()
    result = func(*args)
    return result, time.perf_counter() - start


def save_all_faces(result, target: Path) -> list[Path]:
    saved = save_result(result, target)
    return [Path(path) for path in saved]


def compare_one(card_file: Path, slug: str, workspace: OldWorkspace, options: RenderOptions) -> list[dict[str, Any]]:
    option_slug = f"dpi{options.dpi}_bleed{options.bleed}_{options.bleed_mode}"
    safe_option_slug = option_slug.replace("裁剪", "crop").replace("拉伸", "stretch")
    base_name = f"{slug}__{safe_option_slug}"
    row_base = {
        "slug": slug,
        "dpi": options.dpi,
        "bleed": options.bleed,
        "bleed_mode": options.bleed_mode,
        "status": "ok",
        "same": "",
        "bbox": "",
        "error": "",
        "old_seconds": "",
        "new_seconds": "",
        "speedup_old_over_new": "",
    }
    try:
        with quiet_render():
            old_result, old_seconds = timed_call(render_old, card_file, workspace, options)
            old_files = save_all_faces(old_result, OLD_DIR / f"{base_name}.png")
            new_result, new_seconds = timed_call(render_new, card_file, options)
            new_files = save_all_faces(new_result, NEW_DIR / f"{base_name}.png")
        rows = []
        if len(old_files) != len(new_files):
            row = dict(row_base)
            row.update({"status": "mismatch", "error": f"输出面数不同 old={len(old_files)} new={len(new_files)}"})
            return [row]
        for idx, (old_file, new_file) in enumerate(zip(old_files, new_files)):
            suffix = "" if len(old_files) == 1 else ("_a" if idx == 0 else "_b")
            diff_file = DIFF_DIR / f"{base_name}{suffix}.png"
            sheet_file = SHEET_DIR / f"{base_name}{suffix}.jpg"
            stat = make_diff(old_file, new_file, diff_file)
            make_sheet(f"{base_name}{suffix}", old_file, new_file, diff_file, sheet_file)
            row = dict(row_base)
            row.update({
                "face": suffix or "front",
                "same": stat["same"],
                "bbox": stat["bbox"],
                "old_size": stat["old_size"],
                "new_size": stat["new_size"],
                "old_seconds": f"{old_seconds:.6f}",
                "new_seconds": f"{new_seconds:.6f}",
                "speedup_old_over_new": f"{old_seconds / new_seconds:.4f}" if new_seconds > 0 else "",
            })
            rows.append(row)
        return rows
    except Exception as exc:
        row = dict(row_base)
        row.update({"status": "error", "error": "".join(traceback.format_exception_only(type(exc), exc)).strip()})
        (OUT_ROOT / f"{base_name}.error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        return [row]


def write_csv(path: Path, rows: list[dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row}) if rows else []
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize_speed(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") != "ok" or str(row.get("same")) != "True":
            continue
        key = (row["dpi"], row["bleed"], row["bleed_mode"])
        groups.setdefault(key, []).append(row)
    summary = []
    for (dpi, bleed, bleed_mode), group_rows in sorted(groups.items(), key=lambda item: (int(item[0][0]), int(item[0][1]), item[0][2])):
        old_values = [float(row["old_seconds"]) for row in group_rows]
        new_values = [float(row["new_seconds"]) for row in group_rows]
        old_total = sum(old_values)
        new_total = sum(new_values)
        summary.append({
            "dpi": dpi,
            "bleed": bleed,
            "bleed_mode": bleed_mode,
            "samples": len(group_rows),
            "old_total_seconds": f"{old_total:.6f}",
            "new_total_seconds": f"{new_total:.6f}",
            "old_avg_seconds": f"{statistics.mean(old_values):.6f}",
            "new_avg_seconds": f"{statistics.mean(new_values):.6f}",
            "speedup_old_over_new": f"{old_total / new_total:.4f}" if new_total > 0 else "",
        })
    return summary


def run_batch_benchmark(card_files: list[Path]) -> list[dict[str, Any]]:
    options = RenderOptions(dpi=300, bleed=0, bleed_mode="裁剪")
    batch_cards = []
    batch_source = BATCH_DIR / "source"
    batch_source.mkdir(parents=True, exist_ok=True)
    sample_art = CARDS_DIR / "sample-art.png"
    if sample_art.exists():
        (batch_source / "sample-art.png").write_bytes(sample_art.read_bytes())
    for repeat in range(5):
        for card_file in card_files:
            target = batch_source / f"r{repeat:02d}_{card_file.name}"
            target.write_text(card_file.read_text(encoding="utf-8"), encoding="utf-8")
            batch_cards.append(target)

    rows = []
    workspace = OldWorkspace(batch_source)
    old_out = BATCH_DIR / "old_seq"
    old_out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    with quiet_render():
        for card in batch_cards:
            result = render_old(card, workspace, options)
            save_all_faces(result, old_out / card.with_suffix(".png").name)
    old_seconds = time.perf_counter() - start
    rows.append({"mode": "old_sequential", "cards": len(batch_cards), "workers": 1, "seconds": f"{old_seconds:.6f}", "cards_per_second": f"{len(batch_cards) / old_seconds:.4f}"})

    for workers in [1, 4]:
        out_dir = BATCH_DIR / f"new_workers_{workers}"
        start = time.perf_counter()
        with quiet_render():
            BatchRenderer().render(batch_cards, out_dir, options, workers=workers)
        seconds = time.perf_counter() - start
        rows.append({"mode": "new_batch", "cards": len(batch_cards), "workers": workers, "seconds": f"{seconds:.6f}", "cards_per_second": f"{len(batch_cards) / seconds:.4f}", "speedup_vs_old": f"{old_seconds / seconds:.4f}"})
    return rows


def make_sample_manifest(samples: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [{"slug": slug, "type": data.get("type", ""), "name": data.get("name", ""), "body_length": len(data.get("body", ""))} for slug, data in samples]


def main():
    for directory in [CARDS_DIR, OLD_DIR, NEW_DIR, DIFF_DIR, SHEET_DIR, BATCH_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    make_sample_art(CARDS_DIR / "sample-art.png")
    samples = build_stress_samples()
    card_files = []
    for slug, data in samples:
        card_file = CARDS_DIR / f"{slug}.card"
        card_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        card_files.append(card_file)

    rows = []
    workspace = OldWorkspace(CARDS_DIR)
    for option_values in options_matrix():
        options = RenderOptions(**option_values)
        for slug, card_file in zip([item[0] for item in samples], card_files):
            result_rows = compare_one(card_file, slug, workspace, options)
            rows.extend(result_rows)
            for row in result_rows:
                print(row)

    write_csv(OUT_ROOT / "summary.csv", rows)
    speed_summary = summarize_speed(rows)
    write_csv(OUT_ROOT / "speed_summary.csv", speed_summary)
    batch_rows = run_batch_benchmark(card_files)
    write_csv(OUT_ROOT / "batch_benchmark.csv", batch_rows)
    write_csv(OUT_ROOT / "sample_manifest.csv", make_sample_manifest(samples))
    make_index(SHEET_DIR, OUT_ROOT / "comparison-index.jpg")

    total = len(rows)
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    same_rows = [row for row in ok_rows if str(row.get("same")) == "True"]
    diff_rows = [row for row in rows if row.get("status") != "ok" or str(row.get("same")) != "True"]
    unsupported_note = "当前新旧项目的 ExportBleed 枚举都只支持 0/2/3mm；1mm 属于非法配置，因此未纳入像素矩阵。"
    md = [
        "# 渲染压测对比报告",
        "",
        f"输出目录：`{OUT_ROOT}`",
        "",
        f"样本数：`{len(samples)}`；参数组合：`{len(options_matrix())}`；对图片面数行：`{total}`。",
        f"一致结果：`{len(same_rows)}/{total}`；异常或差异：`{len(diff_rows)}`。",
        "",
        unsupported_note,
        "",
        "## 产物",
        "",
        "- `summary.csv`：逐样本、逐 DPI、逐出血、逐出血模式的像素对比和单张耗时。",
        "- `speed_summary.csv`：按参数组合聚合的旧/新平均耗时与加速比。",
        "- `batch_benchmark.csv`：40 张批量生产场景的旧顺序、新顺序、新 4 进程对比。",
        "- `comparison-index.jpg`：所有对照 sheet 的总览图。",
        "- `sheets/`：每个样本/参数组合的 old/new/diff x8 对照。",
        "",
        "## 批量速度",
        "",
        "| mode | workers | cards | seconds | cards/s | speedup_vs_old |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in batch_rows:
        md.append(f"| {row.get('mode')} | {row.get('workers')} | {row.get('cards')} | {row.get('seconds')} | {row.get('cards_per_second')} | {row.get('speedup_vs_old', '')} |")
    md.extend(["", "## 差异行", "", "| slug | dpi | bleed | bleed_mode | status | same | bbox | error |", "|---|---:|---:|---|---|---|---|---|"])
    for row in diff_rows:
        md.append(f"| {row.get('slug')} | {row.get('dpi')} | {row.get('bleed')} | {row.get('bleed_mode')} | {row.get('status')} | {row.get('same')} | {row.get('bbox')} | {row.get('error', '').replace('|', '/')} |")
    if not diff_rows:
        md.append("| - | - | - | - | - | - | - | - |")
    (OUT_ROOT / "README.md").write_text("\n".join(md), encoding="utf-8")
    print(f"OUTPUT_DIR={OUT_ROOT}")


if __name__ == "__main__":
    main()
