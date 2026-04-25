import re
import json
from typing import Dict, Any, List, Tuple, TYPE_CHECKING, Optional
from copy import deepcopy

if TYPE_CHECKING:
    from .resource_manager import FontManager


class CardAdapter:
    """卡牌适配器 - 将卡牌JSON中的标签转化为统一的emoji格式"""
    # 静态转化表：(正则模式, emoji结果)
    CONVERSION_RULES: List[Tuple[str, str]] = [
        # Punctuation replacements (must come early, order matters!)
        (r'(?<!\\)---', '—'),  # em dash (3 hyphens) - MUST come before en dash
        (r'(?<!\\)--', '–'),  # en dash (2 hyphens)
        (r'(?<!\\)\.\.\.', '…'),  # ellipsis (3 dots)
        # Character Class Icons
        (r"<守护者>|<守卫者>|<gua>", "🛡️"),
        (r"<探求者>|<see>", "🔍"),
        (r"<流浪者>|<rog>", "🚶"),
        (r"<潜修者>|<mys>", "🧘"),
        (r"<生存者>|<求生者>|<sur>", "🏕️"),
        (r"<调查员>|<per>", "🕵️"),

        # Action Icons
        (r"<反应>|<rea>", "⭕"),
        (r"<启动>|<箭头>|<act>", "➡️"),
        (r"<免费>|<fre>", "⚡"),

        # Chaos Token Icons
        (r"<骷髅>|<sku>", "💀"),
        (r"<异教徒>|<cul>", "👤"),
        (r"<石板>|<tab>", "📜"),
        (r"<古神>|<mon>", "👹"),
        (r"<触手>|<大失败>|<ten>", "🐙"),
        (r"<旧印>|<大成功>|<eld>", "⭐"),

        # Stat Icons
        (r"<脑>|<wil>", "🧠"),
        (r"<书>|<int>", "📚"),
        (r"<拳>|<com>", "👊"),
        (r"<脚>|<agi>", "🦶"),
        (r"<\?>|<wild>", "❓"),  # '?' 是特殊正则字符，需要转义

        # Other Game Icons
        (r"<独特>|<uni>", "🏅"),
        (r"<点>|<bul>", "🔵"),
        (r"<祝福>|<ble>", "🌟"),
        (r"<诅咒>|<cur>", "🌑"),
        (r"<雪花>|<frost>", "❄️"),
        (r"<arrow>", "→"),

        # Additional common tags
        (r'<t>(.*?)</t>', r'{\1}'),
        (r'{{(.*?)}}', r'【\1】'),
        (r'(?<!\\)\{([^}]*)\}', r'<trait>\1</trait>'),
        (r'\n<par>\n', '<par>'),
        (r'(?<!\\)_(?![^<]*>)', '<nbsp>'),
        (r'<size\s+"(-?\d+)">', r'<size relative="\1">'),
    ]

    # 需要转化的字段路径配置
    FIELDS_TO_CONVERT: List[str] = [
        "name",  # 顶层字段
        "body",  # 顶层字段
        "flavor",  # 顶层字段
        "card_back.option",  # 嵌套字段
        "card_back.other",  # 嵌套字段
        "scenario_card.skull",
        "scenario_card.cultist",
        "scenario_card.tablet",
        "scenario_card.elder_thing",
    ]

    def __init__(self, card_data: Dict[str, Any], font_manager: 'FontManager', other_side_name: Optional[str] = None):
        """
        初始化卡牌适配器
        Args:
            card_data: 卡牌数据的JSON字典或JSON字符串
        """
        if isinstance(card_data, str):
            self.original_data = json.loads(card_data)
        else:
            self.original_data = deepcopy(card_data)

        self.font_manager = font_manager
        self.lang = font_manager.lang if hasattr(font_manager, 'lang') else 'en'

        type_value = str(self.original_data.get('type', ''))
        self.is_back = bool(self.original_data.get('is_back', False) or '背' in type_value or type_value.endswith('back'))

        fullname = self.original_data.get('name', '')
        if not isinstance(fullname, str):
            fullname = ''
        fullname = self.clean_name(fullname)
        other_fullname = self._resolve_other_side_name(other_side_name)
        self.conversion_rules = self.get_conversion_rules() + [
            (r"<pre>|<猎物>", font_manager.get_font_text('prey')),
            (r"<spa>|<生成>", font_manager.get_font_text('spawn')),
            (r"<for>|<强制>", font_manager.get_font_text('forced')),
            (r"<hau>|<闹鬼>", font_manager.get_font_text('haunted')),
            (r"<obj>|<目标>", font_manager.get_font_text('objective')),
            (r"<pat>|<巡逻>", font_manager.get_font_text('patrol')),
            (r"<rev>|<显现>", font_manager.get_font_text('revelation')),
            (r"<fullname>|<名称>", fullname),
            (r"<fullnameb>|<背面名称>", other_fullname),
        ]
        if font_manager.lang in ['zh', 'zh-CHT']:
            self.conversion_rules.append(
                (r'<upg>|<升级>', r'<font name="ArnoPro-Regular" offset="3" addsize="8">☐</font>'))
            self.conversion_rules.append(
                (r'<res>(.*?)</res>',
                 f'【(→{font_manager.get_font_text("resolution")}\\1)】')
            )
        else:
            self.conversion_rules.append((r'<upg>|<升级>', r'<font name="ArnoPro-Regular">☐</font>'))
            self.conversion_rules.append(
                (r'<res>(.*?)</res>', f'→【{font_manager.get_font_text("resolution")}\\1】'))
        # 编译正则表达式以提高性能
        self._compiled_rules = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.conversion_rules
        ]
        self.font_manager = font_manager

    def _resolve_other_side_name(self, other_side_name: Optional[str]) -> str:
        """获取对侧名称，未找到时返回空字符串"""
        if isinstance(other_side_name, str):
            return self.clean_name(other_side_name)

        # 当前为正面时尝试从 back 中取 name
        if not self.is_back:
            back = self.original_data.get('back')
            if isinstance(back, dict):
                back_name = back.get('name')
                if isinstance(back_name, str):
                    return self.clean_name(back_name)

        # 当前为背面且有 front 字段时尝试回取
        if self.is_back:
            front = self.original_data.get('front')
            if isinstance(front, dict):
                front_name = front.get('name')
                if isinstance(front_name, str):
                    return self.clean_name(front_name)

        return ''

    @staticmethod
    def clean_name(name: str) -> str:
        """清理卡牌名称，移除特殊标记"""
        return re.sub(r"(🏅|<独特>|<uni>)", "", name)

    def convert(self, is_arkhamdb: bool = False) -> Dict[str, Any]:
        """
        转化卡牌数据

        Returns:
            转化后的JSON字典
        """
        converted_data = self.original_data

        def replace_bracketed_content(match):
            content = match.group(1)
            if is_arkhamdb:
                # arkhamdb特殊格式
                if converted_data.get('type', '') in ['密谋卡', '场景卡'] and converted_data.get('is_back', False):
                    return f'<blockquote><i>{content}</i></blockquote>'
                elif converted_data.get('type', '') in ['故事卡']:
                    return f'<blockquote><i>{content}</i></blockquote>'
                else:
                    return f'<i>{content}</i>'
            else:
                tag_name = 'flavor'
                if converted_data.get('type', '') in ['密谋卡', '场景卡'] and converted_data.get('is_back', False):
                    tag_name += ' align="left" flex="false" quote="true" padding="20"'
                elif converted_data.get('type', '') in ['密谋卡-大画', '场景卡-大画']:
                    tag_name += ' align="left" flex="false" padding="0"'
                elif converted_data.get('type', '') in ['故事卡']:
                    tag_name += ' align="left" flex="false" quote="true" padding="20"'
                return f'<{tag_name}>{content}</flavor>'

        body_text = converted_data.get('body', '')
        if body_text:
            body_text = re.sub(r'(?<!\\)\[([^]]+)]', replace_bracketed_content, body_text, flags=re.DOTALL)
            converted_data['body'] = body_text

        # 对配置的每个字段进行转化
        for field_path in self.FIELDS_TO_CONVERT:
            self._convert_field(converted_data, field_path)
        if converted_data.get('victory_text', ''):
            converted_data['victory'] = converted_data['victory_text']

        return converted_data

    def convert_to_json(self) -> str:
        """
        转化卡牌数据并返回JSON字符串

        Returns:
            转化后的JSON字符串
        """
        return json.dumps(self.convert(), ensure_ascii=False, indent=2)

    def _convert_field(self, data: Dict[str, Any], field_path: str) -> None:
        """
        转化指定路径的字段

        Args:
            data: 数据字典
            field_path: 字段路径，使用点号分隔（如 "card_back.other"）
        """
        keys = field_path.split('.')
        current = data

        # 遍历到目标字段的父级
        for key in keys[:-1]:
            if not isinstance(current, dict) or key not in current:
                return
            current = current[key]

        # 检查最后一个键
        last_key = keys[-1]
        if not isinstance(current, dict) or last_key not in current:
            return

        # 只对字符串类型进行替换
        if isinstance(current[last_key], str):
            current[last_key] = self._apply_conversion(current[last_key])

    def _apply_conversion(self, text: str) -> str:
        """
        应用所有转化规则到文本，支持引号转义
        Args:
            text: 原始文本
        Returns:
            转化后的文本
        """
        result = text

        # 应用所有转换规则
        for pattern, replacement in self._compiled_rules:
            result = pattern.sub(replacement, result)

        # 原有的其他清理操作
        result = result.replace('\{', '{')
        result = result.replace('\[', '[')
        result = result.replace('\_', '_')
        result = result.replace('\--', '--')
        result = result.replace('\...', '...')

        return result

    @classmethod
    def add_conversion_rule(cls, pattern: str, replacement: str) -> None:
        """
        动态添加转化规则

        Args:
            pattern: 正则表达式模式
            replacement: 替换结果（emoji）
        """
        cls.CONVERSION_RULES.append((pattern, replacement))

    @classmethod
    def add_field_to_convert(cls, field_path: str) -> None:
        """
        动态添加需要转化的字段

        Args:
            field_path: 字段路径
        """
        if field_path not in cls.FIELDS_TO_CONVERT:
            cls.FIELDS_TO_CONVERT.append(field_path)

    @classmethod
    def remove_conversion_rule(cls, pattern: str) -> bool:
        """
        移除转化规则

        Args:
            pattern: 要移除的正则表达式模式

        Returns:
            是否成功移除
        """
        for i, (p, _) in enumerate(cls.CONVERSION_RULES):
            if p == pattern:
                cls.CONVERSION_RULES.pop(i)
                return True
        return False

    @classmethod
    def get_conversion_rules(cls) -> List[Tuple[str, str]]:
        """获取所有转化规则"""
        return cls.CONVERSION_RULES.copy()

    @classmethod
    def get_fields_to_convert(cls) -> List[str]:
        """获取所有需要转化的字段"""
        return cls.FIELDS_TO_CONVERT.copy()

    @classmethod
    def print_conversion_table(cls) -> None:
        """打印转化规则表（用于调试）"""
        print("卡牌适配器转化规则表：")
        print("=" * 60)
        for pattern, emoji in cls.CONVERSION_RULES:
            print(f"{pattern:<40} -> {emoji}")
        print("=" * 60)


# 使用示例
if __name__ == "__main__":
    # 示例1: 基本用法
    print("示例1: 基本卡牌转化")
    print("-" * 60)

    card_json = {
        "name": "火焰<守护者>",
        "body": "这是一张<反应>卡牌，需要<脑>和<书>各1点",
        "description": "<守卫者>可以在<触手>出现时进行<反应>",
        "text": "消耗<免费>行动，获得<祝福>",
        "traits": "<独特>. <魔法>.",
        "card_back": {
            "other": "背面包含<gua>标记和<雪花>效果",
            "title": "传说<调查员>卡",
            "flavor": "在<诅咒>降临前，<探求者>找到了<旧印>"
        },
        "attributes": {
            "type": "<rea>类型",
            "power": 100
        },
        "effect": {
            "text": "造成<攻击>伤害，然后<治疗>自己。检定<拳>或<脚>"
        },
        "victory": {
            "text": "<大成功>! 你击败了<古神>，获得<一>点胜利分"
        },
        "unused_field": "<守护者>这个不会被转化"
    }

    # 创建适配器
    adapter = CardAdapter(card_json)

    # 转化并打印结果
    print("原始数据：")
    print(json.dumps(card_json, ensure_ascii=False, indent=2))
    print("\n" + "=" * 60 + "\n")

    converted = adapter.convert()
    print("转化后数据：")
    print(json.dumps(converted, ensure_ascii=False, indent=2))

    # 示例2: 所有卡牌类型
    print("\n\n示例2: 所有角色类型转化")
    print("-" * 60)

    class_test = {
        "name": "角色职业测试",
        "body": "<守护者> <探求者> <流浪者> <潜修者> <生存者> <调查员>",
        "description": "<gua> <see> <rog> <mys> <sur> <per>"
    }

    adapter2 = CardAdapter(class_test)
    print(adapter2.convert_to_json())

    # 示例3: 混沌标记
    print("\n\n示例3: 混沌标记转化")
    print("-" * 60)

    chaos_test = {
        "name": "混沌测试",
        "body": "<骷髅> <异教徒> <石板> <古神> <触手> <旧印>",
        "description": "<sku> <cul> <tab> <mon> <大失败> <大成功>"
    }

    adapter3 = CardAdapter(chaos_test)
    print(adapter3.convert_to_json())

    # 示例4: 属性和动作图标
    print("\n\n示例4: 属性和动作图标")
    print("-" * 60)

    action_test = {
        "name": "动作测试",
        "body": "属性: <脑> <书> <拳> <脚> <?>",
        "description": "动作: <反应> <启动> <免费>",
        "text": "状态: <祝福> <诅咒> <雪花> <点> <独特> <一>"
    }

    adapter4 = CardAdapter(action_test)
    print(adapter4.convert_to_json())

    # 示例5: 动态添加规则
    print("\n\n示例5: 动态添加规则")
    print("-" * 60)

    CardAdapter.add_conversion_rule(r"<毒>|<poison>", "☠️")
    CardAdapter.add_conversion_rule(r"<金币>|<coin>", "💰")
    CardAdapter.add_field_to_convert("unused_field")

    dynamic_test = {
        "name": "动态规则测试",
        "body": "新增的<毒>和<金币>标签",
        "unused_field": "现在<守护者>会被转化了，还有<poison>和<coin>"
    }

    adapter5 = CardAdapter(dynamic_test)
    print(adapter5.convert_to_json())

    # 打印转化规则表
    print("\n\n转化规则表：")
    print("-" * 60)
    CardAdapter.print_conversion_table()
