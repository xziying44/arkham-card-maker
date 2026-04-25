from __future__ import annotations

import csv
import importlib
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
OLD_ROOT = Path('/Users/xziying/project/arkham/DIY工具/arkham-homebrew')
OUT_ROOT = REPO / 'render-comparisons' / datetime.now().strftime('%Y%m%d-%H%M%S')
CARDS_DIR = OUT_ROOT / 'cards'
OLD_DIR = OUT_ROOT / 'old'
NEW_DIR = OUT_ROOT / 'new'
DIFF_DIR = OUT_ROOT / 'diff'
SHEET_DIR = OUT_ROOT / 'sheets'

BASE_BODY = '测试正文。<br>这是用于渲染对比的文本。'
BASE_FLAVOR = '测试风味文本。'


def make_sample_art(path: Path) -> None:
    img = Image.new('RGBA', (900, 900), (80, 110, 140, 255))
    draw = ImageDraw.Draw(img)
    for i in range(0, 900, 30):
        color = (80 + i % 120, 120, 180, 255)
        draw.line((0, i, 900, 900 - i), fill=color, width=8)
    draw.ellipse((230, 180, 670, 620), fill=(180, 80, 60, 220), outline=(255, 240, 200, 255), width=8)
    draw.text((310, 410), 'ARKHAM', fill=(255, 255, 255, 255))
    img.save(path)


def common(card_type: str, name: str, **extra: Any) -> dict[str, Any]:
    data = {
        'version': '1.0',
        'language': 'zh',
        'type': card_type,
        'name': name,
        'subtitle': '副标题',
        'class': '中立',
        'body': BASE_BODY,
        'flavor': BASE_FLAVOR,
        'traits': ['测试', '道具'],
        'cost': 1,
        'level': 0,
        'submit_icon': ['意志'],
        'slots': '手部',
        'health': 1,
        'horror': 1,
        'victory': None,
        'picture_path': 'sample-art.png',
        'encounter_group': '',
        'footer_copyright': '',
        'illustrator': '测试',
        'card_number': '001',
        'encounter_group_number': '1/1',
    }
    data.update(extra)
    return data


def build_samples() -> list[tuple[str, dict[str, Any]]]:
    samples: list[tuple[str, dict[str, Any]]] = []
    add = samples.append
    add(('event', common('事件卡', '事件卡', class_='中立') if False else common('事件卡', '事件卡')))
    add(('skill', common('技能卡', '技能卡')))
    add(('asset', common('支援卡', '支援卡')))
    add(('large_skill', common('大画-技能卡', '大画技能卡')))
    add(('large_event', common('大画-事件卡', '大画事件卡')))
    add(('large_asset', common('大画-支援卡', '大画支援卡')))
    add(('investigator_front', common('调查员卡', '调查员卡', class_='守护者') if False else common('调查员卡', '调查员卡', **{'class': '守护者', 'attribute': [3, 3, 3, 3], 'health': 7, 'horror': 7})))
    add(('investigator_back', common('调查员卡背', '调查员卡背', **{'class': '守护者', 'card_back': {'options': []}})))
    add(('investigator_mini', common('调查员小卡', '调查员小卡')))
    add(('enemy', common('敌人卡', '敌人卡', **{'class': '中立', 'attack': '2', 'enemy_health': '3', 'evade': '2', 'enemy_damage': 1, 'enemy_damage_horror': 1})))
    add(('treachery', common('诡计卡', '诡计卡')))
    add(('location_revealed', common('地点卡', '地点卡', **{'location_type': '已揭示', 'shroud': '2', 'clues': '1'})))
    add(('location_unrevealed', common('地点卡', '未揭示地点卡', **{'location_type': '未揭示', 'shroud': '', 'clues': ''})))
    add(('upgrade', common('升级卡', '升级卡', body='□ 选项一<br>□ 选项二')))
    add(('weakness_event', common('事件卡', '弱点事件卡', **{'class': '弱点', 'weakness_type': '基础弱点'})))
    add(('weakness_asset', common('支援卡', '弱点支援卡', **{'class': '弱点', 'weakness_type': '基础弱点'})))
    add(('weakness_skill', common('技能卡', '弱点技能卡', **{'class': '弱点', 'weakness_type': '基础弱点'})))
    add(('weakness_treachery', common('诡计卡', '弱点诡计卡', **{'class': '弱点', 'weakness_type': '基础弱点'})))
    add(('weakness_enemy', common('敌人卡', '弱点敌人卡', **{'class': '弱点', 'weakness_type': '基础弱点', 'attack': '2', 'enemy_health': '3', 'evade': '2'})))
    add(('act', common('场景卡', '场景卡', **{'threshold': '3'})))
    add(('agenda', common('密谋卡', '密谋卡', **{'threshold': '4'})))
    add(('act_back', common('场景卡背', '场景卡背', **{'threshold': '3'})))
    add(('agenda_back', common('密谋卡背', '密谋卡背', **{'threshold': '4'})))
    add(('act_large', common('场景卡-大画', '场景卡大画')))
    add(('agenda_large', common('密谋卡-大画', '密谋卡大画')))
    add(('story', common('故事卡', '故事卡')))
    add(('action', common('行动卡', '行动卡', **{'action_type': 0})))
    add(('scenario_reference', common('冒险参考卡', '冒险参考卡', **{'scenario_card': {'resource_name': '', 'skull': '+1', 'cultist': '0', 'tablet': '-1', 'elder_thing': '-2'}})))
    add(('rule_mini', common('规则小卡', '规则小卡', **{'page_number': '1'})))
    add(('special_picture', common('特殊图片', '特殊图片', **{'craft_type': '原图'})))
    add(('player_back', {'type': '玩家卡背', 'name': '玩家卡背', 'language': 'zh'}))
    add(('encounter_back', {'type': '遭遇卡背', 'name': '遭遇卡背', 'language': 'zh'}))
    add(('custom_back', {'type': '定制卡背', 'name': '定制卡背', 'language': 'zh'}))
    add(('enemy_back', {'type': '敌库卡背', 'name': '敌库卡背', 'language': 'zh'}))
    # 双面卡单独测一次 CardRenderer 的 front/back 行为。
    add(('double_sided_event', common('事件卡', '双面事件正面', **{'version': '2.0', 'back': common('事件卡', '双面事件背面')})))
    return samples


class OldWorkspace:
    def __init__(self, workspace_path: Path):
        if str(OLD_ROOT) not in sys.path:
            sys.path.insert(0, str(OLD_ROOT))
        from ResourceManager import FontManager, ImageManager
        from create_card import CardCreator
        self.workspace_path = str(workspace_path)
        self.config = {}
        self.font_manager = FontManager(font_folder=str(OLD_ROOT / 'fonts'), lang='zh')
        self.image_manager = ImageManager(image_folder=str(OLD_ROOT / 'images'))
        self.image_manager.set_working_directory(str(workspace_path))
        self.creator = CardCreator(self.font_manager, self.image_manager)

    def get_file_content(self, path: str):
        return (Path(self.workspace_path) / path).read_text(encoding='utf-8')

    def get_card_base64(self, json_data, field='picture_base64'):
        picture_path = json_data.get('picture_path')
        if picture_path and not Path(picture_path).is_absolute():
            full = Path(self.workspace_path) / picture_path
            if full.exists():
                return str(full)
        return picture_path

    def center_crop_if_larger(self, image, target_size):
        target_width, target_height = target_size
        img_width, img_height = image.size
        if img_width <= target_width and img_height <= target_height:
            return image
        left = max((img_width - target_width) // 2, 0)
        top = max((img_height - target_height) // 2, 0)
        right = min(left + target_width, img_width)
        bottom = min(top + target_height, img_height)
        return image.crop((left, top, right, bottom))

    def generate_card_image(self, json_data, silence=False):
        from Card import Card
        card_type = json_data.get('type', '')
        mapping = {
            '玩家卡背': 'cardback/player-back.jpg',
            '遭遇卡背': 'cardback/encounter-back.jpg',
            '定制卡背': 'cardback/upgrade-back.png',
            '敌库卡背': 'cardback/enemy-back.png',
        }
        if card_type in mapping:
            with Image.open(OLD_ROOT / mapping[card_type]) as img:
                cardback = self.center_crop_if_larger(img.copy(), (739, 1049))
            return Card(cardback.width, cardback.height, image=cardback)
        self.font_manager.set_lang(json_data.get('language', 'zh'))
        if silence:
            card = self.creator.create_card_bottom_map(json_data, self.get_card_base64(json_data))
        else:
            card = self.creator.create_card(json_data, self.get_card_base64(json_data))
        illustrator = ''
        footer_copyright = ''
        encounter_group_number = ''
        card_number = ''
        if not silence:
            illustrator = json_data.get('illustrator', '')
            footer_copyright = json_data.get('footer_copyright', '')
            encounter_group_number = json_data.get('encounter_group_number', '')
            card_number = json_data.get('card_number', '')
        if card_type != '调查员小卡':
            card.set_footer_information(
                illustrator,
                footer_copyright,
                encounter_group_number,
                card_number,
            )
        return card


def load_old_modules():
    sys.path.insert(0, str(OLD_ROOT))
    from ExportHelper import ExportHelper
    return ExportHelper


def cleanup_old_modules():
    sys.path = [p for p in sys.path if p != str(OLD_ROOT)]
    for name in list(sys.modules):
        if name in {'ResourceManager', 'create_card', 'Card', 'ExportHelper', 'card_cdapter', 'enhanced_draw'} or name.startswith('rich_text_render') or name.startswith('export_helper'):
            sys.modules.pop(name, None)


def render_old(card_file: Path, workspace: OldWorkspace):
    ExportHelper = load_old_modules()
    helper = ExportHelper({
        'format': 'PNG',
        'size': '63.5mm × 88.9mm (2.5″ × 3.5″)',
        'dpi': 300,
        'bleed': 0,
        'bleed_mode': '裁剪',
        'bleed_model': '镜像出血',
        'quality': 95,
    }, workspace)
    return helper.export_card_auto(card_file.name)


def render_new(card_file: Path):
    cleanup_old_modules()
    sys.path.insert(0, str(REPO))
    from arkham_card_maker import CardRenderer, RenderOptions
    return CardRenderer().render(card_file, RenderOptions(bleed=0))


def save_result(result, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(result, dict):
        saved = []
        if result.get('front') is not None:
            result['front'].save(target.with_name(target.stem + '_a.png'))
            saved.append(target.with_name(target.stem + '_a.png'))
        if result.get('back') is not None:
            result['back'].save(target.with_name(target.stem + '_b.png'))
            saved.append(target.with_name(target.stem + '_b.png'))
        return saved
    if hasattr(result, 'front'):
        saved = []
        result.front.save(target.with_name(target.stem + '_a.png') if result.back else target)
        saved.append(target.with_name(target.stem + '_a.png') if result.back else target)
        if result.back:
            result.back.save(target.with_name(target.stem + '_b.png'))
            saved.append(target.with_name(target.stem + '_b.png'))
        return saved
    result.save(target)
    return [target]


def make_diff(old_path: Path, new_path: Path, diff_path: Path):
    old = Image.open(old_path).convert('RGBA')
    new = Image.open(new_path).convert('RGBA')
    if old.size != new.size:
        canvas = Image.new('RGBA', (max(old.width, new.width), max(old.height, new.height)), (0, 0, 0, 0))
        canvas.save(diff_path)
        return {'same': False, 'bbox': 'SIZE_MISMATCH', 'old_size': old.size, 'new_size': new.size}
    diff = ImageChops.difference(old, new)
    bbox = diff.getbbox()
    # 放大差异，方便肉眼看。
    visual = diff.point(lambda p: min(255, p * 8))
    visual.save(diff_path)
    return {'same': bbox is None, 'bbox': '' if bbox is None else str(bbox), 'old_size': old.size, 'new_size': new.size}


def make_sheet(name: str, old_path: Path, new_path: Path, diff_path: Path, out_path: Path):
    imgs = [Image.open(p).convert('RGBA') for p in [old_path, new_path, diff_path]]
    thumb_w, thumb_h = 260, 370
    sheet = Image.new('RGBA', (thumb_w * 3, thumb_h + 40), (245, 245, 245, 255))
    draw = ImageDraw.Draw(sheet)
    labels = ['old', 'new', 'diff x8']
    for i, img in enumerate(imgs):
        img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        x = i * thumb_w + (thumb_w - img.width) // 2
        y = 30 + (thumb_h - img.height) // 2
        sheet.paste(img, (x, y), img)
        draw.text((i * thumb_w + 8, 8), labels[i], fill=(0, 0, 0, 255))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert('RGB').save(out_path)


def make_index(sheet_dir: Path, out_path: Path):
    sheet_paths = sorted(sheet_dir.glob('*.jpg'))
    if not sheet_paths:
        return
    thumb_w, thumb_h = 390, 205
    header_h = 30
    cols = 3
    rows = (len(sheet_paths) + cols - 1) // cols
    canvas = Image.new('RGB', (cols * thumb_w, rows * (thumb_h + header_h)), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)
    for idx, sheet_path in enumerate(sheet_paths):
        img = Image.open(sheet_path).convert('RGB')
        img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        x = (idx % cols) * thumb_w
        y = (idx // cols) * (thumb_h + header_h)
        draw.rectangle([x, y, x + thumb_w - 1, y + header_h + thumb_h - 1], outline=(200, 200, 200))
        draw.text((x + 8, y + 8), sheet_path.stem, fill=(0, 0, 0))
        canvas.paste(img, (x + (thumb_w - img.width) // 2, y + header_h + (thumb_h - img.height) // 2))
    canvas.save(out_path, quality=92)


def main():
    for d in [CARDS_DIR, OLD_DIR, NEW_DIR, DIFF_DIR, SHEET_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    make_sample_art(CARDS_DIR / 'sample-art.png')
    samples = build_samples()
    rows = []
    workspace = OldWorkspace(CARDS_DIR)
    for slug, data in samples:
        card_file = CARDS_DIR / f'{slug}.card'
        card_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        row = {'slug': slug, 'type': data.get('type', ''), 'name': data.get('name', ''), 'status': 'ok', 'same': '', 'bbox': '', 'error': ''}
        try:
            old_result = render_old(card_file, workspace)
            old_files = save_result(old_result, OLD_DIR / f'{slug}.png')
            new_result = render_new(card_file)
            new_files = save_result(new_result, NEW_DIR / f'{slug}.png')
            for idx, (old_file, new_file) in enumerate(zip(old_files, new_files)):
                suffix = '' if len(old_files) == 1 else ('_a' if idx == 0 else '_b')
                diff_file = DIFF_DIR / f'{slug}{suffix}.png'
                stat = make_diff(old_file, new_file, diff_file)
                make_sheet(f'{slug}{suffix}', old_file, new_file, diff_file, SHEET_DIR / f'{slug}{suffix}.jpg')
                if idx == 0:
                    row.update({'same': stat['same'], 'bbox': stat['bbox'], 'old_size': stat['old_size'], 'new_size': stat['new_size']})
            if len(old_files) != len(new_files):
                row['status'] = 'mismatch'
                row['error'] = f'输出面数不同 old={len(old_files)} new={len(new_files)}'
        except Exception as exc:
            row['status'] = 'error'
            row['error'] = ''.join(traceback.format_exception_only(type(exc), exc)).strip()
            (OUT_ROOT / f'{slug}.error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        rows.append(row)
        print(row)
    with (OUT_ROOT / 'summary.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=sorted({k for row in rows for k in row}))
        writer.writeheader()
        writer.writerows(rows)
    make_index(SHEET_DIR, OUT_ROOT / 'comparison-index.jpg')
    md = ['# 渲染对比报告', '', f'输出目录：`{OUT_ROOT}`', '', '总览图：`comparison-index.jpg`', '', '| slug | type | status | same | bbox | error |', '|---|---|---|---|---|---|']
    for row in rows:
        md.append(f"| {row.get('slug')} | {row.get('type')} | {row.get('status')} | {row.get('same')} | {row.get('bbox')} | {row.get('error','').replace('|','/')} |")
    (OUT_ROOT / 'README.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'OUTPUT_DIR={OUT_ROOT}')


if __name__ == '__main__':
    main()
