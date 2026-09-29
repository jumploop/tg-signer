import os
import pathlib
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Literal, TypeAlias
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

NumberingLangT: TypeAlias = Literal[
    "arabic",
    "chinese_simple",
    "chinese_traditional",
    "roman",
    "roman_lower",
    "letter_upper",
    "letter_lower",
    "greek_upper",
    "greek_lower",
    "circled",
    "parenthesized",
    "japanese_kanji",
    "japanese_kana",
    "arabic_indic",
    "devanagari",
    "hebrew",
    "tian_gan",
    "di_zhi",
    "emoji",
]

numbering_systems: Dict[int, Dict[NumberingLangT, str]] = {
    # 基础数字
    1: {
        "arabic": "1",
        "chinese_simple": "一",
        "chinese_traditional": "壹",
        "roman": "I",
        "roman_lower": "i",
        "letter_upper": "A",
        "letter_lower": "a",
        "greek_upper": "Α",  # Alpha
        "greek_lower": "α",
        "circled": "①",
        "parenthesized": "⑴",
        "japanese_kanji": "一",
        "japanese_kana": "いち",
        "arabic_indic": "١",  # Arabic numeral 1
        "devanagari": "१",  # Hindi/Sanskrit
        "hebrew": "א",  # Aleph
        "tian_gan": "甲",  # 天干
        "di_zhi": "子",  # 地支
        "emoji": "1️⃣",
    },
    2: {
        "arabic": "2",
        "chinese_simple": "二",
        "chinese_traditional": "貳",
        "roman": "II",
        "roman_lower": "ii",
        "letter_upper": "B",
        "letter_lower": "b",
        "greek_upper": "Β",  # Beta
        "greek_lower": "β",
        "circled": "②",
        "parenthesized": "⑵",
        "japanese_kanji": "二",
        "japanese_kana": "に",
        "arabic_indic": "٢",
        "devanagari": "२",
        "hebrew": "ב",  # Bet
        "tian_gan": "乙",
        "di_zhi": "丑",
        "emoji": "2️⃣",
    },
    3: {
        "arabic": "3",
        "chinese_simple": "三",
        "chinese_traditional": "叁",
        "roman": "III",
        "roman_lower": "iii",
        "letter_upper": "C",
        "letter_lower": "c",
        "greek_upper": "Γ",  # Gamma
        "greek_lower": "γ",
        "circled": "③",
        "parenthesized": "⑶",
        "japanese_kanji": "三",
        "japanese_kana": "さん",
        "arabic_indic": "٣",
        "devanagari": "३",
        "hebrew": "ג",  # Gimel
        "tian_gan": "丙",
        "di_zhi": "寅",
        "emoji": "3️⃣",
    },
    4: {
        "arabic": "4",
        "chinese_simple": "四",
        "chinese_traditional": "肆",
        "roman": "IV",
        "roman_lower": "iv",
        "letter_upper": "D",
        "letter_lower": "d",
        "greek_upper": "Δ",  # Delta
        "greek_lower": "δ",
        "circled": "④",
        "parenthesized": "⑷",
        "japanese_kanji": "四",
        "japanese_kana": "し／よん",
        "arabic_indic": "٤",
        "devanagari": "४",
        "hebrew": "ד",  # Dalet
        "tian_gan": "丁",
        "di_zhi": "卯",
        "emoji": "4️⃣",
    },
    5: {
        "arabic": "5",
        "chinese_simple": "五",
        "chinese_traditional": "伍",
        "roman": "V",
        "roman_lower": "v",
        "letter_upper": "E",
        "letter_lower": "e",
        "greek_upper": "Ε",  # Epsilon
        "greek_lower": "ε",
        "circled": "⑤",
        "parenthesized": "⑸",
        "japanese_kanji": "五",
        "japanese_kana": "ご",
        "arabic_indic": "٥",
        "devanagari": "५",
        "hebrew": "ה",  # He
        "tian_gan": "戊",
        "di_zhi": "辰",
        "emoji": "5️⃣",
    },
    6: {
        "arabic": "6",
        "chinese_simple": "六",
        "chinese_traditional": "陸",
        "roman": "VI",
        "roman_lower": "vi",
        "letter_upper": "F",
        "letter_lower": "f",
        "greek_upper": "Ζ",  # Zeta
        "greek_lower": "ζ",
        "circled": "⑥",
        "parenthesized": "⑹",
        "japanese_kanji": "六",
        "japanese_kana": "ろく",
        "arabic_indic": "٦",
        "devanagari": "६",
        "hebrew": "ו",  # Vav
        "tian_gan": "己",
        "di_zhi": "巳",
        "emoji": "6️⃣",
    },
    7: {
        "arabic": "7",
        "chinese_simple": "七",
        "chinese_traditional": "柒",
        "roman": "VII",
        "roman_lower": "vii",
        "letter_upper": "G",
        "letter_lower": "g",
        "greek_upper": "Η",  # Eta
        "greek_lower": "η",
        "circled": "⑦",
        "parenthesized": "⑺",
        "japanese_kanji": "七",
        "japanese_kana": "しち／なな",
        "arabic_indic": "٧",
        "devanagari": "७",
        "hebrew": "ז",  # Zayin
        "tian_gan": "庚",
        "di_zhi": "午",
        "emoji": "7️⃣",
    },
    8: {
        "arabic": "8",
        "chinese_simple": "八",
        "chinese_traditional": "捌",
        "roman": "VIII",
        "roman_lower": "viii",
        "letter_upper": "H",
        "letter_lower": "h",
        "greek_upper": "Θ",  # Theta
        "greek_lower": "θ",
        "circled": "⑧",
        "parenthesized": "⑻",
        "japanese_kanji": "八",
        "japanese_kana": "はち",
        "arabic_indic": "٨",
        "devanagari": "८",
        "hebrew": "ח",  # Het
        "tian_gan": "辛",
        "di_zhi": "未",
        "emoji": "8️⃣",
    },
    9: {
        "arabic": "9",
        "chinese_simple": "九",
        "chinese_traditional": "玖",
        "roman": "IX",
        "roman_lower": "ix",
        "letter_upper": "I",
        "letter_lower": "i",
        "greek_upper": "Ι",  # Iota
        "greek_lower": "ι",
        "circled": "⑨",
        "parenthesized": "⑼",
        "japanese_kanji": "九",
        "japanese_kana": "きゅう／く",
        "arabic_indic": "٩",
        "devanagari": "९",
        "hebrew": "ט",  # Tet
        "tian_gan": "壬",
        "di_zhi": "申",
        "emoji": "9️⃣",
    },
    10: {
        "arabic": "10",
        "chinese_simple": "十",
        "chinese_traditional": "拾",
        "roman": "X",
        "roman_lower": "x",
        "letter_upper": "J",
        "letter_lower": "j",
        "greek_upper": "Κ",  # Kappa
        "greek_lower": "κ",
        "circled": "⑩",
        "parenthesized": "⑽",
        "japanese_kanji": "十",
        "japanese_kana": "じゅう",
        "arabic_indic": "١٠",
        "devanagari": "१०",
        "hebrew": "י",  # Yod
        "tian_gan": "癸",
        "di_zhi": "酉",
        "emoji": "🔟",  # 10的emoji是特殊符号
    },
}

DEFAULT_TIMEZONE_NAME = "Asia/Shanghai"
DEFAULT_TIMEZONE = timezone(timedelta(hours=8), name=DEFAULT_TIMEZONE_NAME)


def numbering(num: int, lang: NumberingLangT):
    try:
        return numbering_systems[num][lang]
    except KeyError:
        return str(num)


def resolve_under(
    root: str | os.PathLike[str], name: str, *, suffix: str = ""
) -> pathlib.Path:
    """把 ``name`` 解析为 ``root`` 下的直接子项,越界即抛 ``ValueError``。

    调用方多是把外部字符串(配置名 / 账号名)直接拼进路径,而部分调用方随后
    会创建或删除文件,所以 ``name`` 必须是单一路径分量。仅靠 ``resolve()``
    后的包含性断言不够:``.`` 与空串解析后就是 ``root`` 自身;``.. `` /
    ``...`` 这类名称会被 Win32 剥离尾随点与空格,变成 ``..``。
    """
    invalid = f"名称非法: {name!r}"
    if not isinstance(name, str) or not name or "\x00" in name:
        raise ValueError(invalid)
    if name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(invalid)
    if name != name.rstrip(". "):
        raise ValueError(invalid)
    if pathlib.Path(name).is_absolute() or pathlib.Path(name).drive:
        raise ValueError(invalid)
    root_path = pathlib.Path(root)
    target = root_path / f"{name}{suffix}"
    if target.resolve().parent != root_path.resolve():
        raise ValueError(invalid)
    return target


def resolve_within(
    root: str | os.PathLike[str], path: str | os.PathLike[str]
) -> pathlib.Path:
    """把 ``path`` 解析为 ``root`` 内的直接子项,越界即抛 ``ValueError``。

    与 :func:`resolve_under` 的差别在于允许 ``path`` 自带路径分量(前端会把
    ``<workdir>/logs/x.log`` 这类绝对路径回传),只要求最终落在 ``root`` 内;
    相对路径按 ``root`` 解析而非当前工作目录。``resolve()`` 会展开符号链接,
    所以指向 root 之外的软链同样会被拒绝。
    """
    raw = os.fspath(path)
    if not raw or "\x00" in raw:
        raise ValueError(f"路径非法: {raw!r}")
    root_path = pathlib.Path(root).resolve()
    candidate = pathlib.Path(raw).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root_path / candidate).resolve()
    if resolved.parent != root_path:
        raise ValueError(f"路径越界: {raw!r}")
    return resolved


def restrict_file_permissions(path: str | os.PathLike[str], mode: int = 0o600) -> bool:
    """把凭据文件收紧为「仅属主可读写」,返回是否实际生效。

    ``*.session_string`` / ``.openai_config.json`` 默认按进程 umask 落盘(常见
    0644),同机其他用户可直接读到账号凭据与 API Key。Windows 上 ``chmod`` 只
    影响只读位,所以这里只做 best-effort —— 权限位收紧失败不应该让登录/保存失败。
    """
    if os.name != "posix":
        return False
    try:
        os.chmod(path, mode)
    except OSError:
        return False
    return True


# 配置里的正则表达式由用户提供,而 CPython 的 ``re`` 无法中断灾难性回溯
# (匹配期间不释放 GIL,线程超时也打不断它)。三层护栏:
#   1. 限制 pattern 与待匹配文本的长度(内存 / 多项式级回溯);
#   2. 用形状检查挡掉「量词套量词」(star height >= 2),那是指数级回溯的典型形态;
#   3. 正则非法时统一抛 ValueError。
# 真正的「超时中断」需要 regex 等第三方库,此处不引入新依赖。
MAX_REGEX_PATTERN_LENGTH = 512
MAX_REGEX_SUBJECT_LENGTH = 8 * 1024


def _unbounded_quantifier_end(pattern: str, start: int) -> int | None:
    """若 ``pattern[start:]`` 以「无上限量词」开头则返回其结束下标,否则 None。

    无上限 = ``*`` / ``+`` / ``{n,}``;有上限的 ``?`` / ``{n}`` / ``{n,m}`` 不算
    —— 它们把重复次数钉死,不会产生指数级回溯。
    """
    if start >= len(pattern):
        return None
    ch = pattern[start]
    if ch in "*+":
        return start + 1
    if ch == "{":
        end = pattern.find("}", start)
        if end == -1:
            return None
        body = pattern[start + 1 : end]
        if body.endswith(",") and body[:-1].isdigit():
            return end + 1
    return None


def has_superlinear_quantifier(pattern: str) -> bool:
    """粗判 ``pattern`` 是否存在「无上限量词套无上限量词」(star height >= 2)。

    ``(a+)+$``、``(\\d*)*``、``(a+b)+`` 这类形状在长文本上是指数级回溯,足以把
    整个事件循环卡死。这是启发式(不是完整解析),但只对「组内已有无上限量词、
    组外又叠加一个无上限量词」这一形状报警,所以不会误伤 ``(a+)?``、
    ``(\\d{2,4})+``、``(?:\\d{1,3}\\.){3}\\d{1,3}`` 这类常见写法。
    """
    # groups[i] 表示第 i 层「当前所在分组」内是否已经出现过无上限量词。
    groups: list[bool] = [False]
    in_class = False
    index = 0
    while index < len(pattern):
        ch = pattern[index]
        if ch == "\\":
            index += 2
            continue
        if in_class:
            if ch == "]":
                in_class = False
            index += 1
            continue
        if ch == "[":
            in_class = True
            index += 1
            continue
        if ch == "(":
            groups.append(False)
            index += 1
            continue
        if ch == ")":
            if len(groups) > 1:
                inner = groups.pop()
                end = _unbounded_quantifier_end(pattern, index + 1)
                if end is not None:
                    if inner:
                        return True
                    # 组整体被无上限量词重复,对父层而言也算「含无上限量词」。
                    groups[-1] = True
                    index = end
                    continue
            index += 1
            continue
        end = _unbounded_quantifier_end(pattern, index)
        if end is not None and index > 0:
            groups[-1] = True
            index = end
            continue
        index += 1
    return False


def safe_regex_search(pattern: str, text: str, *, flags: int = 0) -> re.Match | None:
    """``re.search`` 的长度受限 + 形状受限包装,返回值语义与 ``re.search`` 一致。

    正则非法、过长、或含嵌套无上限量词(可能指数级回溯)时统一抛 ``ValueError``,
    方便调用方用一处异常处理覆盖所有情况。超长的待匹配文本会被截断而不是拒绝
    —— 只影响尾部匹配,不会静默漏掉靠前的匹配结果。
    """
    if not isinstance(pattern, str):
        raise ValueError(f"正则必须是字符串: {pattern!r}")
    if len(pattern) > MAX_REGEX_PATTERN_LENGTH:
        raise ValueError(
            f"正则过长({len(pattern)} > {MAX_REGEX_PATTERN_LENGTH}),已跳过匹配"
        )
    if has_superlinear_quantifier(pattern):
        raise ValueError(
            f"正则含嵌套无上限量词,可能灾难性回溯,已跳过匹配: {pattern[:64]!r}"
        )
    subject = text if isinstance(text, str) else str(text or "")
    if len(subject) > MAX_REGEX_SUBJECT_LENGTH:
        subject = subject[:MAX_REGEX_SUBJECT_LENGTH]
    try:
        return re.search(pattern, subject, flags=flags)
    except re.error as exc:
        raise ValueError(f"正则非法: {pattern!r} ({exc})") from exc


def _load_timezone_from_file(path: str | os.PathLike[str]):
    path = pathlib.Path(path).expanduser()
    if not path.is_file():
        return None
    try:
        with path.open("rb") as fp:
            return ZoneInfo.from_file(fp)
    except (OSError, ValueError, ZoneInfoNotFoundError):
        return None


def _load_timezone(name: str | None):
    if not name:
        return None
    candidate = name.strip()
    if not candidate:
        return None
    if candidate.startswith(":"):
        candidate = candidate[1:].strip()
        if not candidate:
            return None
    if candidate.startswith(("/", ".", "~")):
        tz = _load_timezone_from_file(candidate)
        if tz is not None:
            return tz
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return None


def _get_local_timezone():
    local_tz = datetime.now().astimezone().tzinfo
    if local_tz is not None:
        return local_tz
    return None


def get_timezone():
    tz = _load_timezone(os.environ.get("TZ"))
    if tz is not None:
        return tz
    tz = _get_local_timezone()
    if tz is not None:
        return tz
    return _load_timezone(DEFAULT_TIMEZONE_NAME) or DEFAULT_TIMEZONE


def get_now():
    return datetime.now(tz=get_timezone())


class UserInput:
    def __init__(self, index: int = 1, numbering_lang: NumberingLangT = "arabic"):
        self.index = index
        self.numbering_lang = numbering_lang

    def incr(self, n: int = 1):
        self.index += n

    def decr(self, n: int = 1):
        self.index -= n

    @property
    def index_str(self):
        return f"{numbering(self.index, self.numbering_lang)}. "

    def __call__(self, prompt: str = None):
        r = input(f"{self.index_str}{prompt}")
        self.incr(1)
        return r


def print_to_user(*args, sep=" ", end="\n", flush=False, **kwargs):
    return print(*args, sep=sep, end=end, flush=flush, **kwargs)
