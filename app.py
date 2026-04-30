import os
import json
import base64
import sqlite3
import uuid
import random
import re
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from openai import OpenAI
from zhipuai import ZhipuAI
import db_manager

# ========== TTS 降级 ==========
try:
    import tts
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("⚠️ 未找到 tts 模块，语音合成禁用")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
CORS(app)

# ========== API 密钥与客户端 ==========
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")
if not DEEPSEEK_API_KEY or not ZHIPU_API_KEY:
    raise RuntimeError("请设置 DEEPSEEK_API_KEY 和 ZHIPU_API_KEY")

DEEPSEEK_MODEL = "deepseek-v4-pro"          # DeepSeek 叙事模型
SCHEDULER_MODEL = "glm-4.7"             # 智谱调度器模型（稳定）
GLM_FAST_MODEL = "glm-4.6v"              # 智谱角色生成模型（快速响应）

deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
zhipu_client = ZhipuAI(api_key=ZHIPU_API_KEY)

# ========== 数据库初始化 ==========
CHAT_DB_PATH = "coc_chat.db"
db_manager.init_db()

def init_chat_db():
    with sqlite3.connect(CHAT_DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    print("✅ 聊天数据库初始化完成")

init_chat_db()

# ========== 会话与角色卡工具函数 ==========
def get_or_create_room_id():
    room_id = request.headers.get("X-Room-Id") or session.get("room_id")
    if not room_id:
        room_id = "default-room"
        session["room_id"] = room_id
    with sqlite3.connect(CHAT_DB_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO rooms (room_id) VALUES (?)", (room_id,))
    return room_id

def get_or_create_player_id():
    player_id = request.headers.get("X-Player-Id") or session.get("player_id")
    if not player_id:
        player_id = "player_id_0"
        session["player_id"] = player_id
    return player_id

def get_character(player_id):
    data = db_manager.get_player(player_id)
    if data is None:
        data = {
            "base_info": {
                "name": "调查员", "occupation": "无业", "age": 20,
                "gender": "未知", "era": "1920年代", "interests": "暂无", "personality": "谨慎"
            },
            "attributes": {
                "str":50,"con":50,"siz":50,"dex":50,
                "app":50,"int":50,"pow":50,"edu":50
            },
            "derived": {"hp":10,"mp":10,"san":50,"luck":50},
            "skills": {"侦查":50,"聆听":50,"图书馆使用":50,"闪避":30,"斗殴":25},
            "items": [],
            "spells": [],
            "backstory": "",
            "appearance": ""
        }
        db_manager.update_player(player_id, data)
    return data

def update_character(player_id, **kwargs):
    data = get_character(player_id)
    if 'name' in kwargs: data['base_info']['name'] = kwargs['name']
    if 'occupation' in kwargs: data['base_info']['occupation'] = kwargs['occupation']
    if 'interests' in kwargs: data['base_info']['interests'] = kwargs['interests']
    if 'personality' in kwargs: data['base_info']['personality'] = kwargs['personality']
    if 'backstory' in kwargs: data['backstory'] = kwargs['backstory']
    if 'san_delta' in kwargs: data['derived']['san'] = max(0, data['derived']['san'] + kwargs['san_delta'])
    if 'hp_delta' in kwargs: data['derived']['hp'] = max(0, data['derived']['hp'] + kwargs['hp_delta'])
    if 'luck_delta' in kwargs: data['derived']['luck'] = max(0, data['derived']['luck'] + kwargs['luck_delta'])
    if 'skills_add' in kwargs:
        for skill, val in kwargs['skills_add'].items():
            data['skills'][skill] = data['skills'].get(skill, 0) + val
    if 'items_add' in kwargs:
        data['items'].extend(kwargs['items_add'])
    if 'items_remove' in kwargs:
        for item in kwargs['items_remove']:
            if item in data['items']: data['items'].remove(item)
    db_manager.update_player(player_id, data)
    return data

# ========== 子 AI 模块 ==========
def character_generation_ai(user_request: str, era: str = "1920年代") -> dict:
    """随机生成完整的 CoC 7th 调查员角色卡（智谱），era 指定时代背景"""
    sys_msg = f"""你是一位熟练的克苏鲁的呼唤 7th 守秘人。根据要求生成完整的{era}调查员角色卡。

必须按以下 JSON 结构返回（字段名全部小写，skills 的 key 为中文技能名）：

{{
  "base_info": {{
    "name": "角色中文名",
    "occupation": "职业",
    "age": 30,
    "gender": "男/女",
    "era": "{era}",
    "interests": "兴趣爱好",
    "personality": "性格描述"
  }},
  "attributes": {{
    "str": 50, "con": 50, "siz": 50, "dex": 50,
    "app": 50, "int": 50, "pow": 50, "edu": 50
  }},
  "skills": {{
    "会计": 25, "人类学": 35, "估价": 55, "考古学": 30,
    "魅惑": 20, "攀爬": 25, "信用评级": 45, "克苏鲁神话": 0,
    "闪避": 25, "汽车驾驶": 30, "电气维修": 10, "话术": 25,
    "格斗(斗殴)": 30, "射击(手枪)": 20, "急救": 30, "历史": 45,
    "恐吓": 25, "跳跃": 20, "母语(中文)": 70, "法律": 15,
    "图书馆使用": 30, "聆听": 35, "锁匠": 5, "机械维修": 15,
    "医学": 5, "博物学": 20, "导航": 10, "神秘学": 25,
    "操作重型机械": 5, "说服": 35, "心理学": 30, "读唇": 5,
    "侦查": 40, "潜行": 25, "生存": 10, "游泳": 20,
    "投掷": 30, "追踪": 15
  }},
  "derived": {{
    "hp": 10, "mp": 12, "san": 60, "luck": 55
  }},
  "items": ["物品1", "物品2"],
  "spells": [],
  "backstory": "角色背景故事",
  "appearance": "角色外貌描述"
}}

规则：
- 时代背景为 {era}，生成的角色背景、物品、职业设定都必须符合该年代特征，不能出现该年代尚未出现的科技或事物
- attributes 八项属性用 3d6×5 或 (2d6+6)×5 的标准生成法，范围 15~90
- derived 中 hp = (con+siz)/10 向下取整，mp = pow/5，san = pow，luck 随机 3d6×5
- skills 要符合职业：比如"古董商"应有较高的估价、历史、神秘学
- items 放随身物品（2~4件），必须符合 {era} 的时代特征
- 返回严格的 JSON，不要多余的文字。"""
    try:
        resp = zhipu_client.chat.completions.create(
            model=GLM_FAST_MODEL,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_request}
            ],
            temperature=0.9,
            response_format={"type": "json_object"},
        )
        raw = json.loads(resp.choices[0].message.content)
        # 补全缺失字段，保证结构完整
        full = {
            "base_info": raw.get("base_info", {}),
            "attributes": raw.get("attributes", {
                "str":50,"con":50,"siz":50,"dex":50,
                "app":50,"int":50,"pow":50,"edu":50
            }),
            "derived": raw.get("derived", {"hp":10,"mp":10,"san":50,"luck":50}),
            "skills": raw.get("skills", {"侦查":50,"聆听":50,"图书馆使用":50}),
            "items": raw.get("items", []),
            "spells": raw.get("spells", []),
            "backstory": raw.get("backstory", ""),
            "appearance": raw.get("appearance", "")
        }
        # 确保 base_info 有所有字段
        for k in ["name","occupation","age","gender","interests","personality"]:
            full["base_info"].setdefault(k, "未知" if k != "age" else 20)
        return full
    except:
        return {
            "base_info": {"name":"调查员","occupation":"无业","age":20,"gender":"未知","interests":"暂无","personality":"谨慎"},
            "attributes": {"str":50,"con":50,"siz":50,"dex":50,"app":50,"int":50,"pow":50,"edu":50},
            "derived": {"hp":10,"mp":10,"san":50,"luck":50},
            "skills": {"侦查":50,"聆听":50,"图书馆使用":50,"闪避":30,"格斗(斗殴)":25},
            "items": [],
            "spells": [],
            "backstory": "",
            "appearance": ""
        }

def dice_narrative_ai(total: int, detail: str, context: str = "") -> str:
    """暗骰叙述，不透露数字"""
    sys_msg = """你是暗骰叙述引擎。根据检定结果生成一句感官描写，绝对不能出现数字。只输出一句话。"""
    prompt = f"暗骰结果：{detail}，总计 {total}。{context}"
    try:
        resp = deepseek_client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            extra_body={"thinking": {"type": "disabled"}}
        )
        return resp.choices[0].message.content.strip()
    except:
        return ""

# ========== 联网搜索 ==========
def web_search(query: str) -> str:
    if not query.strip():
        return ""
    try:
        response = zhipu_client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": query}],
            tools=[{
                "type": "web_search",
                "web_search": {
                    "search_engine": "search_pro",
                    "search_query": query,
                    "count": 3,
                }
            }],
            tool_choice="auto", stream=False
        )
        msg = response.choices[0].message
        if msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.function.name == "web_search":
                    args = json.loads(tc.function.arguments)
                    pages = args.get("webPages",{}).get("value",[]) or args.get("search_results",[])
                    if pages:
                        result = "【实时搜索结果】\n"
                        for idx, p in enumerate(pages[:3], 1):
                            title = p.get("name") or p.get("title") or "无标题"
                            snippet = p.get("snippet") or p.get("content") or ""
                            result += f"{idx}. {title}\n   {snippet}\n\n"
                        return result
        return ""
    except Exception as e:
        print(f"搜索失败: {e}")
        return ""

# ========== 骰子工具 ==========
def roll_dice(expression: str):
    pattern = r'(\d+)?d(%)?(\d+)?(?:\s*([\+\-])\s*(\d+))?'
    match = re.fullmatch(pattern, expression.strip())
    if not match:
        return None, "无效骰子表达式"
    count = int(match.group(1)) if match.group(1) else 1
    if match.group(2) == '%':
        sides = 100
    else:
        sides = int(match.group(3)) if match.group(3) else 6
    mod_op = match.group(4)
    mod = int(match.group(5)) if match.group(5) else 0
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    detail = f"{count}d{sides}=" + "+".join(map(str, rolls))
    if mod != 0:
        if mod_op == '+':
            total += mod
            detail += f"+{mod}"
        else:
            total -= mod
            detail += f"-{mod}"
    detail += f"={total}"
    return total, detail

# ========== 系统提示词 ==========

# 主守秘人 AI（只叙事，不调工具）
MAIN_SYSTEM_PROMPT = """你是克苏鲁跑团守秘人。你的核心任务是引导玩家进入洛夫克拉夫特式的恐怖世界。你会用丰富的细节来构建画面：不只是说“你走进一间屋子”，而是会说“木地板在你脚下发出不均匀的吱呀声，有几块板子明显凹陷下去，像是总有人站在那里；壁纸在墙角翻卷起来，露出下面发黑的水渍，形状像一张扭曲的脸；空气里有一股甜腐的味道，像是熟透过头的水果混着旧棉花”。你会描写光线（“煤油灯只能照亮桌子中央一小块，房间的四个角落完全沉在黑暗里，但那黑暗似乎不均匀——东北角比别处更黑，黑得像一个竖起来的井口”），描写声音（“你听到钟摆声，但你没有看到钟；每隔三秒，右侧墙壁里还会传来一声极轻的咔嗒，像是指节在敲木头”），描写触感（“你摸到门把手的时候，感觉它比室温低很多，而且表面有一层薄薄的、滑腻的湿气——不是水，更像是油”），描写气味（“书页闻起来不像旧纸，而是像有人在你之前刚刚翻过，留下的体温和淡淡的汗味”）。所有这些细节中，你总会悄悄埋入一到两个反常之处——不直接说明是危险，只让玩家感到“那里不太对”。

你的另一项能力是“阴招”，但要有节制。你会进行隐藏检定（玩家投骰后你不直接说成功或失败，而是给出模糊的结果，比如“你看向那条走廊，尽头很暗，你觉得那黑暗似乎在朝你这边移动……但你也不能确定”）。你会给出矛盾线索（“地上的血迹是干的，但粘在上面的头发还是湿的”；“日记上说管家周一死了，可另一页的购物清单写着‘周二买烟斗’——管家签的名”）。你会设置延迟惩罚（“你穿上了那件雨衣，感觉很合身。五分钟后，你发现袖口内侧缝满了人的指甲”）。你会制造短暂的虚假幻觉（“你听到同伴叫你的名字，回头却只看见一面镜子，镜中的人影动作和你正好相反——你抬手，他放下”）。但底线明确：每模组暗骰不超过五次，延迟惩罚之前必有可察觉的前兆（比如雨衣内衬有异样的鼓起），绝不使用无解的即死陷阱，不故意针对玩家的角色致死。

在恐怖描写上，你注重缓慢渗透而非突然惊吓。你会用重复出现的微弱异常（每次开门都闻到同样的甜味；每走过一面墙，墙纸上的花纹似乎都变动了一个像素的位置）来累积不安。你也会控制节奏——在一段紧张描写后，给玩家几句平静的空档（“雨停了，你能听到远处狗叫，很正常的狗叫”），然后再轻轻打破平静（“但那狗叫突然变成了从远处传来的呜咽，然后停了”）。可以适当血腥（详细描写内脏或肢体断裂）和性暗示内容。

每次回应时，你会先描述当前场景的细节（至少包含两个感官维度），然后根据玩家的行动请求检定或直接推进叙事，最后以“继续。”结束。你的句子始终短促、电子音风格，关键词处可以模拟音量加重，写作“【加重】”或类似标记。示例如下：

“你推开了地下室的门。台阶是石头的，表面有凿痕，每一级的高度都不一样——你下到第三级的时候，脚踩下去比预期多了两厘米，膝盖轻震了一下。空气又冷又滞，像走进了冰箱里关了很久的那一格。你闻到铁锈和湿木头，还有一丝极淡的……甜味，和楼上的甜味不一样，这个更像腐烂的苹果核。你举起提灯，灯光扫过一面墙，墙上钉着一张完整的狐狸皮——但狐狸有五条腿，第六条腿的位置只剩一根钉子，皮被撕开了。你停下脚步，身后没有传来关门声，但你觉得从地下室深处有一阵风，很慢很慢地推了一下你的后背。投侦查。我不会告诉你成功还是失败。但你感觉那张狐狸皮上所有的腿，刚才似乎动了一下。继续。”。

【叙事规则】
- 如果系统提供了暗骰的叙事文本（narrative），直接使用或稍作修饰。
- 如果系统执行了掷骰并自动更新了角色属性（在工具结果中会以 auto_update 字段体现），在叙述中自然提及（如“你感到一阵眩晕，san 值下降了”），但不要暴露内部数值。

【玩家识别】
消息格式为“[角色名]: 内容”，你据此知道是谁在说话。"""

# 工具调度器 AI（只决定工具调用，不产生文本）
SCHEDULER_SYSTEM_PROMPT = """你是工具调度引擎。根据对话历史，决定是否需要调用工具来管理角色卡或掷骰。
你只能通过输出 tool_calls 来调用工具，绝不能输出任何文本回复。

工具清单：
- no_action：本轮无需任何操作时调用。
- update_character_sheet：修改角色属性（必须指定player_id）。
- get_character_sheet：查询角色卡。
- create_character：创建新角色（支持random=true随机生成）。
- list_characters：查看房间内所有角色。
- roll_dice：掷骰子（expression必填，secret可选，check_type可选指定检定类型）。

规则：
1. 【创建角色】如果玩家要求"创建"、"生成"、"随机"一个调查员/角色，调用 create_character 并设置 random=true。不要调用 get_character_sheet 或其他工具。
2. 【掷骰检定】如果玩家要求掷骰检定（如"精神鉴定1d100"、"伤害2d6"等），调用 roll_dice，并设置 check_type 参数指示检定类型（san=理智检定/hp=伤害/luck=幸运/留空=普通掷骰）。系统会自动根据实际骰子结果更新角色属性，你无需再额外调用 update_character_sheet。
3. 【修改属性】如果玩家要求修改属性、获得物品、提升技能（非掷骰场景），直接调用 update_character_sheet 或 list_characters 等相应工具。
4. 【查看角色】如果玩家要求查看角色卡，调用 get_character_sheet。
5. 【空操作】如果没有任何操作需求，调用 no_action。
6. player_id 必须使用最近一条用户消息所对应的角色ID，或者从历史中找到发言者。当前发言者的 player_id 会在系统消息中给出。

重要提醒：当用户的操作涉及数据变更（创建角色、修改属性、掷骰检定），你必须调用对应的写入工具，不要只调用只读工具（如 get_character_sheet）。认真分辨用户意图，选择正确的工具。"""

# 工具定义（供调度器使用）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_character_sheet",
            "description": "更新角色卡（必须指定player_id）",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_id": {"type": "string"},
                    "name": {"type": "string"},
                    "occupation": {"type": "string"},
                    "interests": {"type": "string"},
                    "personality": {"type": "string"},
                    "san_delta": {"type": "integer"},
                    "hp_delta": {"type": "integer"},
                    "skills_add": {"type": "object", "description": "如 {\"侦查\":5}"},
                    "items_add": {"type": "array", "items": {"type": "string"}},
                    "items_remove": {"type": "array", "items": {"type": "string"}},
                    "backstory": {"type": "string"}
                },
                "required": ["player_id"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_character_sheet",
            "description": "查看某个角色的完整信息",
            "parameters": {
                "type": "object",
                "properties": {"player_id": {"type": "string"}},
                "required": ["player_id"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_character",
            "description": "创建新调查员，若random=true则随机生成",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_id": {"type": "string"},
                    "name": {"type": "string"},
                    "occupation": {"type": "string"},
                    "age": {"type": "integer"},
                    "gender": {"type": "string"},
                    "interests": {"type": "string"},
                    "personality": {"type": "string"},
                    "random": {"type": "boolean", "description": "设为true进行随机生成"}
                },
                "required": ["player_id"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_characters",
            "description": "列出房间内所有调查员ID和姓名",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "roll_dice",
            "description": "掷骰子（expression如1d100,2d6），secret=true为暗骰，check_type指定检定类型（系统自动更新属性）",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "骰子表达式"},
                    "secret": {"type": "boolean", "default": False},
                    "check_type": {
                        "type": "string",
                        "enum": ["", "san", "hp", "luck"],
                        "description": "检定类型：san=理智检定（自动扣减san）、hp=伤害（自动扣减hp）、luck=幸运（自动扣减luck）、留空=普通掷骰"
                    }
                },
                "required": ["expression"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "no_action",
            "description": "空操作，本轮无数据变更时调用",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

# ========== 调度器 AI ==========
def plan_tool_calls(messages):
    """调用调度器（智谱），返回 tool_calls 列表（可能为空）"""
    try:
        resp = zhipu_client.chat.completions.create(
            model=SCHEDULER_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,                      # 极低温度
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            return msg.tool_calls, msg
        else:
            return [], msg
    except Exception as e:
        print(f"调度器错误: {e}")
        return [], None

# ========== 主叙事 AI ==========
def generate_narrative(messages):
    """调用主守秘人生成最终文本，禁止工具调用"""
    try:
        resp = deepseek_client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            tools=None,                         # 禁止工具
            temperature=0.8,
            extra_body={"thinking": {"type": "disabled"}}
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        print(f"叙事生成错误: {e}")
        return "（守秘人沉默了……）"

# ========== 核心对话 ==========
def chat_with_deepseek(room_id, player_id, user_input, search_context=""):
    # 1. 加载纯净历史
    history = load_history(room_id, player_id)
    char = get_character(player_id)
    user_msg = f"{char['base_info']['name']}: {user_input}"
    if search_context:
        user_msg = search_context + "\n" + user_msg
    history.append({"role": "user", "content": user_msg, "player_id": player_id})

    # 2. 准备调度器消息（注入当前 player_id）
    dispatch_messages = history.copy()
    dispatch_messages.insert(0, {"role": "system", "content": SCHEDULER_SYSTEM_PROMPT})
    dispatch_messages.append({
        "role": "system",
        "content": f"当前操作用户的player_id = {player_id}。请根据最新一条用户消息决定工具调用。"
    })

    # 3. 调度器决定工具调用
    tool_calls, _ = plan_tool_calls(dispatch_messages)

    # 4. 如果有工具调用，执行并追加结果
    if tool_calls:
        assistant_tool_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                } for tc in tool_calls
            ]
        }
        history.append(assistant_tool_msg)

        for tc in tool_calls:
            func_name = tc.function.name
            args = json.loads(tc.function.arguments)
            result_content = ""

            if func_name == "no_action":
                result_content = "no_action ok"
            elif func_name == "list_characters":
                chars = db_manager.list_all_players()
                result_content = json.dumps(chars, ensure_ascii=False) if chars else "[]"
            elif func_name == "get_character_sheet":
                pid = args["player_id"]
                data = get_character(pid)
                result_content = json.dumps({
                    "name": data["base_info"]["name"],
                    "occupation": data["base_info"]["occupation"],
                    "san": data["derived"]["san"],
                    "hp": data["derived"]["hp"],
                    "skills": data["skills"],
                    "items": data["items"]
                }, ensure_ascii=False)
            elif func_name == "create_character":
                pid = args["player_id"]
                if args.get("random"):
                    # 生成完整角色卡，直接替换数据库
                    full_char = character_generation_ai("随机生成一位1920年代调查员")
                    db_manager.update_player(pid, full_char)
                    result_content = f"随机角色 {full_char['base_info']['name']} 已生成"
                else:
                    data = get_character(pid)
                    updates = {k: v for k, v in args.items() if k in ["name","occupation","age","gender","interests","personality"] and v is not None}
                    data["base_info"].update(updates)
                    db_manager.update_player(pid, data)
                    result_content = f"角色 {data['base_info']['name']} 已更新"
            elif func_name == "update_character_sheet":
                pid = args.pop("player_id")
                new_data = update_character(pid, **args)
                result_content = f"{new_data['base_info']['name']} 更新 (SAN:{new_data['derived']['san']}, HP:{new_data['derived']['hp']})"
            elif func_name == "roll_dice":
                expression = args.get("expression", "1d6")
                secret = args.get("secret", False)
                check_type = args.get("check_type", "")
                total, detail = roll_dice(expression)
                if total is None:
                    result_content = f"骰子错误: {detail}"
                else:
                    res_obj = {"total": total, "detail": detail, "secret": secret}
                    # 根据 check_type 自动更新角色属性
                    if check_type and total is not None:
                        if check_type == "san":
                            new_char = update_character(player_id, san_delta=-total)
                            res_obj["auto_update"] = f"SAN -{total}"
                            res_obj["san_after"] = new_char['derived']['san']
                        elif check_type == "hp":
                            new_char = update_character(player_id, hp_delta=-total)
                            res_obj["auto_update"] = f"HP -{total}"
                            res_obj["hp_after"] = new_char['derived']['hp']
                        elif check_type == "luck":
                            new_char = update_character(player_id, luck_delta=-total)
                            res_obj["auto_update"] = f"Luck -{total}"
                            res_obj["luck_after"] = new_char['derived']['luck']
                    if secret:
                        narrative = dice_narrative_ai(total, detail, "检定")
                        res_obj["narrative"] = narrative
                    result_content = json.dumps(res_obj, ensure_ascii=False)
            else:
                result_content = f"未知工具: {func_name}"

            history.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_content
            })

    # 5. 主守秘人生成最终回复
    # 注入主守秘人系统提示词到历史开头
    narrative_messages = [{"role": "system", "content": MAIN_SYSTEM_PROMPT}] + history
    final_reply = generate_narrative(narrative_messages)
    history.append({"role": "assistant", "content": final_reply})

    # 6. 保存历史
    save_history(room_id, history)
    return final_reply

# ========== 历史管理 ==========
# 粗略估算：中文字符约 2 token，上下文字符上限
# 模型最高支持 1M tokens（约 200 万字符）
# 留出约 25% 余量给 system prompt + 工具结果
MAX_CONTEXT_CHARS = 1500000  # 约 750k tokens，为 DeepSeek 1M 窗口留有余量

def load_history(room_id, current_player_id):
    """加载聊天记录，智能截断以保留最多上下文"""
    with sqlite3.connect(CHAT_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        # 先加载更多记录，再根据字符数截断
        rows = conn.execute(
            "SELECT role, content, player_id FROM chat_history WHERE room_id=? ORDER BY created_at DESC LIMIT 500",
            (room_id,)
        ).fetchall()
    history = []
    player_names = {}
    char_count = 0
    # 从最新消息开始遍历，确保超限时跳过的是旧消息，保留新消息
    for row in rows:
        if row["role"] == "tool":
            continue
        content = row["content"] or ""
        # 估算字符数
        estimated_chars = len(content)
        # 如果加上这条会超限，跳过（但至少保留最近 10 条）
        if char_count + estimated_chars > MAX_CONTEXT_CHARS and len(history) >= 10:
            continue
        msg = {"role": row["role"], "content": content}
        if row["role"] == "user":
            pid = row["player_id"]
            if pid not in player_names:
                pdata = db_manager.get_player(pid)
                player_names[pid] = pdata["base_info"]["name"] if pdata else "未知"
            msg["content"] = f"[{player_names[pid]}]: {content}"
            msg["player_id"] = pid
        history.append(msg)
        char_count += estimated_chars
    # 反转回时间顺序（旧→新），供后续叙事AI使用
    history.reverse()
    return history

def save_history(room_id, history):
    """只保存 user 和最终 assistant 消息，跳过 tool 和临时 assistant(tool_calls)"""
    with sqlite3.connect(CHAT_DB_PATH) as conn:
        conn.execute("DELETE FROM chat_history WHERE room_id=?", (room_id,))
        for msg in history:
            role = msg["role"]
            if role == "tool":
                continue
            if role == "assistant" and msg.get("tool_calls"):
                continue
            content = msg.get("content", "")
            # 再次清理可能混入的伪调用
            if "<｜DSML｜tool_calls>" in content:
                content = content.split("<｜DSML｜tool_calls>")[0].strip()
                if not content:
                    continue
            player_id = msg.get("player_id", "SYSTEM")
            conn.execute(
                "INSERT INTO chat_history (room_id, player_id, role, content) VALUES (?, ?, ?, ?)",
                (room_id, player_id, role, content)
            )

# ========== CoC 7th 职业数据 ==========
OCCUPATIONS = [
    {
        "id": "会计师",
        "name": "会计师",
        "skills": ["会计", "法律", "图书馆使用", "聆听", "说服", "心理学", "侦查", "信用评级"],
        "credit_range": "30-70",
        "description": "精通财务与审计的专业人士"
    },
    {
        "id": "古董商",
        "name": "古董商",
        "skills": ["会计", "估价", "历史", "图书馆使用", "博物学", "神秘学", "侦查", "信用评级"],
        "credit_range": "30-50",
        "description": "经营古董买卖的商人"
    },
    {
        "id": "考古学家",
        "name": "考古学家",
        "skills": ["估价", "考古学", "历史", "图书馆使用", "博物学", "侦查", "生存", "信用评级"],
        "credit_range": "10-40",
        "description": "发掘与研究古代文明的学者"
    },
    {
        "id": "艺术家",
        "name": "艺术家",
        "skills": ["估价", "艺术(任意)", "历史", "魅惑", "心理学", "侦查", "信用评级"],
        "credit_range": "9-50",
        "description": "从事视觉或表演艺术的创作者"
    },
    {
        "id": "作家",
        "name": "作家/记者",
        "skills": ["历史", "图书馆使用", "母语(中文)", "心理学", "侦查", "话术", "信用评级"],
        "credit_range": "9-30",
        "description": "以文字为生的撰稿人或新闻工作者"
    },
    {
        "id": "私家侦探",
        "name": "私家侦探",
        "skills": ["话术", "法律", "图书馆使用", "心理学", "侦查", "潜行", "格斗(斗殴)", "信用评级"],
        "credit_range": "20-45",
        "description": "受雇调查各类案件的独立探员"
    },
    {
        "id": "医生",
        "name": "医生",
        "skills": ["急救", "医学", "母语(中文)", "心理学", "侦查", "信用评级"],
        "credit_range": "30-80",
        "description": "持有行医执照的医疗从业者"
    },
    {
        "id": "工程师",
        "name": "工程师",
        "skills": ["电气维修", "机械维修", "操作重型机械", "图书馆使用", "攀爬", "侦查", "信用评级"],
        "credit_range": "30-60",
        "description": "设计或维护工程结构的技术专家"
    },
    {
        "id": "警官",
        "name": "警官",
        "skills": ["格斗(斗殴)", "射击(手枪)", "法律", "心理学", "侦查", "潜行", "追踪", "信用评级"],
        "credit_range": "20-40",
        "description": "维护治安的执法人员"
    },
    {
        "id": "教授",
        "name": "教授",
        "skills": ["图书馆使用", "母语(中文)", "心理学", "说服", "侦查", "信用评级"],
        "credit_range": "20-60",
        "description": "在高等教育机构任教与研究的学者"
    },
    {
        "id": "流浪汉",
        "name": "流浪汉/乞丐",
        "skills": ["话术", "聆听", "潜行", "攀爬", "跳跃", "生存", "信用评级"],
        "credit_range": "0-5",
        "description": "流落街头、仅靠微薄收入为生的人"
    },
    {
        "id": "神职人员",
        "name": "神职人员",
        "skills": ["历史", "图书馆使用", "聆听", "心理学", "说服", "神秘学", "信用评级"],
        "credit_range": "9-40",
        "description": "服务于宗教组织的牧师或僧侣"
    },
    {
        "id": "士兵",
        "name": "士兵/退役军人",
        "skills": ["格斗(斗殴)", "射击(步枪)", "潜行", "急救", "攀爬", "跳跃", "生存", "信用评级"],
        "credit_range": "9-30",
        "description": "曾在军队服役的军人"
    },
    {
        "id": "江湖艺人",
        "name": "江湖艺人",
        "skills": ["艺术(任意)", "魅惑", "话术", "聆听", "心理学", "潜行", "侦查", "信用评级"],
        "credit_range": "9-20",
        "description": "以表演或手工艺谋生的街头艺人"
    },
    {
        "id": "律师",
        "name": "律师",
        "skills": ["法律", "图书馆使用", "心理学", "说服", "话术", "侦查", "信用评级"],
        "credit_range": "30-80",
        "description": "精通法律体系、为客户提供辩护或咨询的专业人士"
    },
    {
        "id": "护士",
        "name": "护士",
        "skills": ["急救", "医学", "心理学", "侦查", "聆听", "话术", "信用评级"],
        "credit_range": "9-40",
        "description": "协助医生照料病患的医疗护理人员"
    },
    {
        "id": "摄影师",
        "name": "摄影师",
        "skills": ["艺术(任意)", "侦查", "心理学", "图书馆使用", "潜行", "话术", "信用评级"],
        "credit_range": "10-40",
        "description": "用镜头记录世界的影像艺术家或新闻摄影师"
    },
    {
        "id": "飞行员",
        "name": "飞行员",
        "skills": ["导航", "操作重型机械", "心理学", "汽车驾驶", "电气维修", "机械维修", "信用评级"],
        "credit_range": "30-70",
        "description": "驾驶飞机或飞艇的持证航空驾驶员"
    },
    {
        "id": "药剂师",
        "name": "药剂师",
        "skills": ["会计", "急救", "医学", "心理学", "图书馆使用", "话术", "信用评级"],
        "credit_range": "30-60",
        "description": "调配药物并为患者提供用药指导的药学专家"
    },
    {
        "id": "运动员",
        "name": "运动员",
        "skills": ["攀爬", "跳跃", "格斗(斗殴)", "游泳", "投掷", "追踪", "信用评级"],
        "credit_range": "9-30",
        "description": "从事体育竞技的职业运动员"
    },
    {
        "id": "业余艺术爱好者",
        "name": "业余艺术爱好者",
        "skills": ["艺术(任意)", "魅惑", "历史", "母语(中文)", "射击(手枪)", "说服", "信用评级"],
        "credit_range": "50-99",
        "description": "拥有雄厚家产、将艺术与社交作为消遣的富裕人士"
    },
    {
        "id": "猎人",
        "name": "猎人",
        "skills": ["格斗(斗殴)", "射击(步枪)", "侦查", "潜行", "生存", "追踪", "博物学", "信用评级"],
        "credit_range": "9-30",
        "description": "以狩猎为生或以此为乐的野外追踪者"
    },
    {
        "id": "推销员",
        "name": "推销员",
        "skills": ["会计", "话术", "聆听", "心理学", "说服", "魅惑", "信用评级"],
        "credit_range": "9-40",
        "description": "以口才和人际关系谋生的商品销售代表"
    },
    {
        "id": "秘书",
        "name": "秘书",
        "skills": ["会计", "图书馆使用", "母语(中文)", "心理学", "话术", "侦查", "信用评级"],
        "credit_range": "9-30",
        "description": "负责文书处理、档案管理和日常事务的行政助理"
    },
    {
        "id": "学生",
        "name": "学生",
        "skills": ["图书馆使用", "母语(中文)", "心理学", "侦查", "说服", "话术", "信用评级"],
        "credit_range": "0-10",
        "description": "在学校或大学中求学的年轻人"
    },
    {
        "id": "体力劳动者",
        "name": "体力劳动者",
        "skills": ["攀爬", "跳跃", "机械维修", "操作重型机械", "投掷", "格斗(斗殴)", "信用评级"],
        "credit_range": "0-15",
        "description": "靠体力与双手从事重劳动工作的工人"
    },
    {
        "id": "电工",
        "name": "电工",
        "skills": ["电气维修", "攀爬", "机械维修", "图书馆使用", "操作重型机械", "侦查", "信用评级"],
        "credit_range": "10-30",
        "description": "安装与维护电气系统的技术工人"
    },
    {
        "id": "机械师",
        "name": "机械师",
        "skills": ["电气维修", "机械维修", "操作重型机械", "汽车驾驶", "攀爬", "话术", "信用评级"],
        "credit_range": "10-30",
        "description": "修理与维护机械设备的技术专家"
    },
    {
        "id": "密探",
        "name": "密探",
        "skills": ["魅惑", "话术", "潜行", "心理学", "侦查", "聆听", "射击(手枪)", "信用评级"],
        "credit_range": "20-60",
        "description": "从事秘密情报搜集和渗透工作的特工人员"
    },
]

# ========== 掷骰生成角色属性 ==========
def roll_3d6_times_5():
    """3D6 x 5"""
    total = sum(random.randint(1, 6) for _ in range(3))
    return total * 5

def roll_2d6_plus_6_times_5():
    """(2D6+6) x 5"""
    total = sum(random.randint(1, 6) for _ in range(2)) + 6
    return total * 5

def roll_attributes():
    """生成全部8项属性"""
    return {
        "str": roll_3d6_times_5(),
        "con": roll_3d6_times_5(),
        "siz": roll_2d6_plus_6_times_5(),
        "dex": roll_3d6_times_5(),
        "app": roll_3d6_times_5(),
        "int": roll_2d6_plus_6_times_5(),
        "pow": roll_3d6_times_5(),
        "edu": roll_2d6_plus_6_times_5()
    }

def calculate_derived(attrs):
    """根据属性计算衍生值"""
    str_val = attrs["str"]
    con_val = attrs["con"]
    siz_val = attrs["siz"]
    dex_val = attrs["dex"]
    pow_val = attrs["pow"]
    int_val = attrs["int"]
    edu_val = attrs["edu"]

    hp = (con_val + siz_val) // 10
    san = pow_val
    mp = pow_val // 5
    luck = roll_3d6_times_5()

    # 伤害加值 (DB) 和 体格 (Build)
    str_siz = str_val + siz_val
    if str_siz <= 64:
        db = "-2"
        build = -2
    elif str_siz <= 84:
        db = "-1"
        build = -1
    elif str_siz <= 124:
        db = "0"
        build = 0
    elif str_siz <= 164:
        db = "+1D4"
        build = 1
    elif str_siz <= 204:
        db = "+1D6"
        build = 2
    elif str_siz <= 284:
        db = "+2D6"
        build = 3
    elif str_siz <= 364:
        db = "+3D6"
        build = 4
    else:
        db = "+4D6"
        build = 5

    # 移动速度 (MOV)
    mov = 8
    if str_val < siz_val and dex_val < siz_val:
        mov = 7
    if str_val > siz_val and dex_val > siz_val:
        mov = 9
    if str_val >= 90 and dex_val >= 90:
        mov = 10

    dodge = dex_val // 2
    own_language = edu_val

    return {
        "hp": hp,
        "max_hp": hp,
        "san": san,
        "max_san": san,
        "mp": mp,
        "luck": luck,
        "damage_bonus": db,
        "build": build,
        "mov": mov,
        "dodge": dodge,
        "own_language": own_language
    }

# ========== 车卡 API 路由 ==========
@app.route("/character/create")
def character_create_page():
    """车卡向导页面"""
    return render_template("create_character.html", occupations=OCCUPATIONS)

@app.route("/api/roll-attributes", methods=["POST"])
def api_roll_attributes():
    """掷骰生成八维属性"""
    attrs = roll_attributes()
    derived = calculate_derived(attrs)
    return jsonify({
        "attributes": attrs,
        "derived": derived
    })

@app.route("/api/calculate-derived", methods=["POST"])
def api_calculate_derived():
    """根据传入的属性计算衍生值"""
    data = request.get_json()
    attrs = data.get("attributes", {})
    derived = calculate_derived(attrs)
    return jsonify({"derived": derived})

@app.route("/api/save-character", methods=["POST"])
def api_save_character():
    """保存创建的角色卡"""
    data = request.get_json()
    player_id = get_or_create_player_id()

    base_info = data.get("base_info", {})
    attributes = data.get("attributes", {})
    skills = data.get("skills", {})
    items = data.get("items", [])
    backstory = data.get("backstory", "")
    appearance = data.get("appearance", "")

    derived = calculate_derived(attributes)
    # 使用用户自选幸运（如果有）或重新计算
    if "luck" in data.get("derived", {}):
        derived["luck"] = data["derived"]["luck"]

    char_data = {
        "base_info": {
            "name": base_info.get("name", "调查员"),
            "occupation": base_info.get("occupation", "无业"),
            "age": base_info.get("age", 20),
            "gender": base_info.get("gender", "未知"),
            "era": base_info.get("era", "1920年代"),
            "nationality": base_info.get("nationality", "中国"),
            "residence": base_info.get("residence", "上海"),
            "interests": base_info.get("interests", ""),
            "personality": base_info.get("personality", "")
        },
        "attributes": attributes,
        "derived": derived,
        "skills": skills,
        "items": items,
        "spells": [],
        "backstory": backstory,
        "appearance": appearance
    }

    db_manager.update_player(player_id, char_data)
    return jsonify({"success": True, "player_id": player_id, "name": char_data["base_info"]["name"]})

@app.route("/api/occupations", methods=["GET"])
def api_get_occupations():
    """获取职业列表"""
    return jsonify(OCCUPATIONS)

@app.route("/api/ai-generate-character", methods=["POST"])
def api_ai_generate_character():
    """AI 随机生成角色卡（带超时，失败降级为本地生成）"""
    import threading

    data = request.get_json(silent=True) or {}
    era = data.get("era", "1920年代")

    result_holder = {"char": None, "error": None}

    def try_ai_generate():
        try:
            full_char = character_generation_ai(f"随机生成一位{era}调查员，中文名，中国背景", era=era)
            attrs = full_char.get("attributes", {})
            if attrs:
                derived = calculate_derived(attrs)
                if "luck" in full_char.get("derived", {}):
                    derived["luck"] = full_char["derived"]["luck"]
                full_char["derived"] = derived
            result_holder["char"] = full_char
        except Exception as e:
            result_holder["error"] = str(e)

    # 启动 AI 生成线程，设置 10 秒超时
    thread = threading.Thread(target=try_ai_generate, daemon=True)
    thread.start()
    thread.join(timeout=10)

    if result_holder["char"] is not None:
        return jsonify({"success": True, "character": result_holder["char"]})

    # 降级：使用本地随机生成（带丰富预设）
    print(f"AI 生成超时或失败 ({result_holder['error']})，降级为本地随机")
    attrs = roll_attributes()
    derived = calculate_derived(attrs)

    name_pool = {
        "男": ["张明远", "李建国", "王朝阳", "赵瑞轩", "刘浩然", "陈思宇", "杨俊杰", "周志远", "吴天宇", "林文博"],
        "女": ["林婉清", "陈雨萱", "张梓涵", "李诗雨", "王若曦", "刘思琪", "赵佳怡", "周雅文", "吴梦洁", "杨雪彤"]
    }
    occ_list = [o["name"] for o in OCCUPATIONS]
    gender = random.choice(["男", "女"])
    name = random.choice(name_pool[gender])
    occupation = random.choice(occ_list)
    residence = random.choice(["上海", "北京", "广州", "重庆", "南京", "杭州", "成都", "武汉"])
    age = random.randint(22, 55)

    personality_map = {
        "会计师": "谨慎细致，一丝不苟", "古董商": "沉稳老练，目光敏锐", "考古学家": "求知若渴，不畏艰险",
        "艺术家": "感性浪漫，自由奔放", "作家/记者": "敏锐善谈，追根究底", "私家侦探": "多疑机敏，善于观察",
        "医生": "冷静沉着，救死扶伤", "工程师": "理性务实，善于分析", "警官": "正义感强，果断勇敢",
        "教授": "学识渊博，循循善诱", "流浪汉/乞丐": "世故圆滑，生存力强", "神职人员": "虔诚慈悲，信仰坚定",
        "士兵/退役军人": "纪律严明，意志坚强", "江湖艺人": "风趣幽默，随机应变"
    }

    interest_map = {
        "会计师": "财经分析、阅读", "古董商": "古玩收藏、历史研究", "考古学家": "考古发掘、文献研究",
        "艺术家": "绘画展览、音乐会", "作家/记者": "文学创作、新闻调查", "私家侦探": "悬疑小说、摄影",
        "医生": "医学研究、登山", "工程师": "机械模型、电子设备", "警官": "健身格斗、射击",
        "教授": "学术研究、书法", "流浪汉/乞丐": "街头象棋、观察路人", "神职人员": "冥想、书法抄经",
        "士兵/退役军人": "野外生存、战术训练", "江湖艺人": "杂技魔术、民俗乐器"
    }

    # 随机选择几件物品
    all_items = ["手电筒", "小刀", "笔记本", "钢笔", "急救包", "火柴/打火机", "绳索", "水壶", "指南针",
                 "地图", "照相机", "望远镜", "怀表", "撬棍", "烟斗", "钥匙串", "背包", "雨衣", "折叠铲"]
    random.shuffle(all_items)
    item_count = random.randint(2, 5)
    items = all_items[:item_count]

    # 构建技能
    skills = {
        "侦查": random.randint(30, 70), "聆听": random.randint(25, 60),
        "图书馆使用": random.randint(30, 65), "闪避": derived["dodge"],
        "格斗(斗殴)": random.randint(25, 50), "急救": random.randint(25, 50),
        "历史": random.randint(20, 60), "神秘学": random.randint(10, 40),
        "话术": random.randint(20, 50), "心理学": random.randint(20, 50),
        "潜行": random.randint(20, 40), "追踪": random.randint(10, 30),
    }
    # 加上母语
    skills["母语(中文)"] = attrs["edu"]

    fallback = {
        "base_info": {
            "name": name, "occupation": occupation, "age": age,
            "gender": gender, "era": era, "nationality": "中国", "residence": residence,
            "interests": interest_map.get(occupation, "阅读、旅行"),
            "personality": personality_map.get(occupation, "谨慎而好奇")
        },
        "attributes": attrs, "derived": derived, "skills": skills,
        "items": items, "spells": [],
        "backstory": f"{name}是一位生活在{era}的{residence}{occupation}，在长期的职业生涯中积累了丰富的经验与见识。",
        "appearance": f"{age}岁{gender}性，中等身材，{residence}口音。"
    }
    return jsonify({"success": True, "character": fallback, "fallback": True})

# ========== AI 背景故事生成 ==========
def build_attribute_description(attrs: dict) -> str:
    """根据属性数值生成中文描述"""
    desc_parts = []
    # 力量
    s = attrs.get("str", 50)
    if s >= 80: desc_parts.append(f"力量{s}（体格强壮，力能扛鼎）")
    elif s >= 60: desc_parts.append(f"力量{s}（身体结实，有一定力气）")
    elif s >= 40: desc_parts.append(f"力量{s}（体力普通）")
    else: desc_parts.append(f"力量{s}（身体瘦弱，力气不大）")
    # 体质
    s = attrs.get("con", 50)
    if s >= 80: desc_parts.append(f"体质{s}（铁打的身体，极少生病）")
    elif s >= 60: desc_parts.append(f"体质{s}（健康状况良好）")
    elif s >= 40: desc_parts.append(f"体质{s}（体质一般）")
    else: desc_parts.append(f"体质{s}（体弱多病，容易疲劳）")
    # 体型
    s = attrs.get("siz", 50)
    if s >= 80: desc_parts.append(f"体型{s}（高大魁梧）")
    elif s >= 60: desc_parts.append(f"体型{s}（身材较高大）")
    elif s >= 40: desc_parts.append(f"体型{s}（中等身材）")
    else: desc_parts.append(f"体型{s}（身材矮小）")
    # 敏捷
    s = attrs.get("dex", 50)
    if s >= 80: desc_parts.append(f"敏捷{s}（身手矫健，动作迅捷）")
    elif s >= 60: desc_parts.append(f"敏捷{s}（动作灵活）")
    elif s >= 40: desc_parts.append(f"敏捷{s}（行动正常）")
    else: desc_parts.append(f"敏捷{s}（笨手笨脚，反应迟缓）")
    # 外貌
    s = attrs.get("app", 50)
    if s >= 80: desc_parts.append(f"外貌{s}（容貌出众，令人过目不忘）")
    elif s >= 60: desc_parts.append(f"外貌{s}（相貌端正，仪表堂堂）")
    elif s >= 40: desc_parts.append(f"外貌{s}（长相普通）")
    else: desc_parts.append(f"外貌{s}（其貌不扬）")
    # 智力
    s = attrs.get("int", 50)
    if s >= 80: desc_parts.append(f"智力{s}（聪慧过人，思维敏捷）")
    elif s >= 60: desc_parts.append(f"智力{s}（头脑灵活，学习能力强）")
    elif s >= 40: desc_parts.append(f"智力{s}（智力普通）")
    else: desc_parts.append(f"智力{s}（思维迟缓，不太聪明）")
    # 意志
    s = attrs.get("pow", 50)
    if s >= 80: desc_parts.append(f"意志{s}（意志如铁，精神力量强大）")
    elif s >= 60: desc_parts.append(f"意志{s}（意志坚定，不易动摇）")
    elif s >= 40: desc_parts.append(f"意志{s}（意志力一般）")
    else: desc_parts.append(f"意志{s}（意志薄弱，容易受他人影响）")
    # 教育
    s = attrs.get("edu", 50)
    if s >= 80: desc_parts.append(f"教育{s}（学识渊博，受过良好教育）")
    elif s >= 60: desc_parts.append(f"教育{s}（有一定文化水平）")
    elif s >= 40: desc_parts.append(f"教育{s}（受过基础教育）")
    else: desc_parts.append(f"教育{s}（没读过什么书）")
    return "\n".join(desc_parts)


def ai_generate_backstory(occupation, attributes, name, gender, age, era="1920年代", field="all") -> dict:
    """调用 AI 生成背景故事的各部分内容"""
    attr_desc = build_attribute_description(attributes)

    field_prompts = {
        "appearance": "【个人描述】根据职业和属性，生成角色的外貌、气质、谈吐描述（50-100字）。",
        "ideology": "【思想与信念】生成角色的核心价值观、信仰或人生信条（30-60字）。",
        "important": "【重要之人】生成对角色影响最深的人物（家人/导师/朋友），说明关系及影响（40-80字）。",
        "place": "【意义非凡之地】生成一个对角色有特殊意义的地点，如童年故居、常去的地方等（30-60字）。",
        "treasure": "【宝贵之物】生成一件角色珍视的物品，可以是传家宝、纪念品等（30-60字）。",
        "traits": "【特质与伤疤】生成角色独特的性格特点、伤疤或心理阴影（30-60字）。",
        "backstory": "【完整背景故事】生成一个连贯的200-300字的背景故事，涵盖角色的成长经历、入行契机、以及为何开始调查超自然事件。要结合职业和属性数值。",
    }

    if field == "all":
        prompt_parts = list(field_prompts.values())
    elif field in field_prompts:
        prompt_parts = [field_prompts[field]]
    else:
        prompt_parts = [field_prompts["backstory"]]

    fields_required = list(field_prompts.keys()) if field == "all" else [field]

    sys_msg = f"""你是一位克苏鲁的呼唤 7th 角色背景创作专家。根据角色信息生成符合{era}中国背景的角色背景故事。

角色信息：
姓名：{name}
职业：{occupation}
年龄：{age}岁
性别：{gender}
时代：{era}

属性特征：
{attr_desc}

要求：
- 内容要符合角色的职业身份和属性数值（高力量的人描述为强壮，低体质的人描述为体弱多病等）
- 故事背景设定在{era}的中国
- 所有描述、物品、场景都必须符合{era}的时代特征，不能出现该年代尚未出现的科技或事物
- 例如：1920年代的通讯靠电报和信件，交通靠黄包车、火车和早期汽车
- 语气符合克苏鲁神话的阴郁、神秘基调
- 返回严格的 JSON 格式，字段名全部小写
- 不要出现现代元素（如手机、互联网等）"""

    user_prompt = "请生成以下内容（严格JSON格式）：\n" + "\n".join(prompt_parts)

    try:
        resp = zhipu_client.chat.completions.create(
            model=GLM_FAST_MODEL,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,
            response_format={"type": "json_object"},
        )
        raw = json.loads(resp.choices[0].message.content)
        # 确保返回的字段都存在
        result = {}
        for f in fields_required:
            result[f] = raw.get(f, "")
        return result
    except Exception as e:
        print(f"AI 背景生成失败: {e}")
        return {}


@app.route("/api/ai-generate-backstory", methods=["POST"])
def api_ai_generate_backstory():
    """AI 根据职业和属性自动生成角色背景故事"""
    data = request.get_json()
    occupation = data.get("occupation", "无业")
    attributes = data.get("attributes", {})
    name = data.get("name", "调查员")
    gender = data.get("gender", "未知")
    age = data.get("age", 25)
    era = data.get("era", "1920年代")
    field = data.get("field", "all")  # all / appearance / ideology / important / place / treasure / traits / backstory

    import threading

    result_holder = {"data": None, "error": None}

    def try_ai():
        try:
            result_holder["data"] = ai_generate_backstory(occupation, attributes, name, gender, age, era, field)
        except Exception as e:
            result_holder["error"] = str(e)

    thread = threading.Thread(target=try_ai, daemon=True)
    thread.start()
    thread.join(timeout=12)

    if result_holder["data"] is not None:
        return jsonify({"success": True, "data": result_holder["data"]})

    # 降级：使用模板生成
    print(f"AI 背景生成超时或失败，使用模板降级")
    fallback = generate_fallback_backstory(occupation, attributes, name, gender, age, era, field)
    return jsonify({"success": True, "data": fallback, "fallback": True})


def generate_fallback_backstory(occupation, attributes, name, gender, age, era="1920年代", field="all") -> dict:
    """本地模板降级生成背景故事"""
    str_val = attributes.get("str", 50)
    con_val = attributes.get("con", 50)
    siz_val = attributes.get("siz", 50)
    app_val = attributes.get("app", 50)
    int_val = attributes.get("int", 50)
    pow_val = attributes.get("pow", 50)
    edu_val = attributes.get("edu", 50)

    # 外貌描述
    appearance_parts = []
    # 体型
    if siz_val >= 80: appearance_parts.append("身材高大魁梧")
    elif siz_val >= 60: appearance_parts.append("身材较高")
    elif siz_val >= 40: appearance_parts.append("中等身材")
    else: appearance_parts.append("身材矮小")
    # 力量
    if str_val >= 70: appearance_parts.append("体格结实")
    elif str_val <= 35: appearance_parts.append("身形消瘦")
    # 外貌
    if app_val >= 70: appearance_parts.append("容貌出众")
    elif app_val <= 35: appearance_parts.append("其貌不扬")
    # 气质
    if int_val >= 70: appearance_parts.append("目光锐利，透着一股精明")
    elif pow_val >= 70: appearance_parts.append("眼神深邃，气质沉稳")
    elif edu_val >= 60: appearance_parts.append("举止文雅，有书卷气")
    else: appearance_parts.append("举止朴实")
    # 健康
    if con_val >= 70: appearance_parts.append("面色红润，看起来十分健康")
    elif con_val <= 35: appearance_parts.append("面色苍白，略显病态")

    appearance = f"{name}是一位{age}岁的{gender}性{occupation}。{'，'.join(appearance_parts)}。谈吐{'得体' if edu_val >= 50 else '朴实'}，{'给人一种可靠的感觉' if pow_val >= 50 else '略显拘谨'}。"

    # 思想信念
    if occupation in ["教授", "考古学家", "作家/记者"]:
        ideology = f"{name}坚信知识是人类对抗黑暗的唯一武器。他相信理性的力量可以解开一切谜题，即使面对超自然现象，也试图用科学方法寻找解释。"
    elif occupation in ["神职人员"]:
        ideology = f"{name}怀有虔诚的信仰，相信善与恶的终极对决。但他也开始怀疑，那些古老经文中描述的恐怖，是否不仅仅是寓言。"
    elif occupation in ["警官", "士兵/退役军人"]:
        ideology = f"{name}坚守着保护弱者的信念，相信秩序与正义终将战胜混乱。然而，有些罪恶超出了世俗法律的范畴。"
    elif occupation in ["私家侦探"]:
        ideology = f"{name}相信真相终会水落石出。多年的调查经验告诉他，表面之下往往隐藏着更深的秘密。"
    elif occupation in ["医生", "护士"]:
        ideology = f"{name}秉持救死扶伤的医者信念，坚信生命的价值。但医学的边界之外，有些病症并非凡药可医。"
    elif occupation in ["流浪汉/乞丐"]:
        ideology = f"{name}看尽了人世冷暖，相信活着本身就是一种胜利。街头的生存法则教会他，最大的危险往往来自看不见的地方。"
    else:
        ideology = f"{name}相信世界远比表面看到的复杂，对未知事物既怀有敬畏，又充满好奇。"

    # 重要之人
    important = f"{name}的{'导师' if edu_val >= 60 else '父亲'}是一位{'学识渊博的长者' if edu_val >= 60 else '勤劳朴实的普通人'}，在{'求学时期' if edu_val >= 60 else '幼年时期'}对他的影响至深。正是从他那里，{name}学会了{'独立思考' if int_val >= 60 else '永不放弃'}的重要性。"

    # 意义非凡之地
    place = f"{name}童年时居住的{'老宅' if edu_val < 50 else '老城区'}附近有一座{'废弃的古庙' if int_val >= 50 else '幽深的竹林'}，那里是{name}第一次感受到{'超越现实的恐惧' if pow_val < 50 else '无法解释的吸引力'}的地方。"

    # 宝贵之物
    if occupation in ["教授", "考古学家", "学生"]:
        treasure = f"一本破旧的古籍笔记本，封面上留有前任主人的神秘批注，{name}始终觉得其中隐藏着某种秘密。"
    elif occupation in ["警官", "士兵/退役军人"]:
        treasure = f"一枚旧怀表，是{name}在{'第一次执行任务' if '警官' in occupation else '战场上'}时随身携带的物品，见证过生死。"
    elif occupation in ["医生", "护士"]:
        treasure = f"一套老式手术器械，曾是{name}的{'医学导师' if occupation == '医生' else '护理长'}赠予的礼物。"
    elif occupation in ["神职人员"]:
        treasure = f"一枚古老的银质十字架/护身符，据说是从一位远行的传教士手中获得。"
    else:
        treasure = f"一件看似普通的小物件，但对{name}而言有着特殊的情感价值，始终随身携带。"

    # 特质与伤疤
    if pow_val >= 70:
        traits = f"{name}意志坚定，面对恐怖时比常人更能保持冷静。但{'一次意外中的经历' if con_val < 50 else '内心深处'}留下了不易察觉的心理阴影。"
    elif pow_val <= 35:
        traits = f"{name}容易受到惊吓，睡眠质量很差，经常做噩梦。左手上有一道{'旧伤疤' if str_val >= 50 else '天生的浅色胎记'}，不愿向人提起其来历。"
    else:
        traits = f"{name}性格谨慎，但好奇心有时会压倒理智。{'眉角' if app_val >= 50 else '右手'}上的一道旧伤疤提醒着曾经犯过的错误。"

    # 完整背景故事（根据时代调整）
    # 提取时代年份信息用于出生年份计算
    era_year_match = re.search(r'(\d{4})', era)
    if era_year_match:
        era_base_year = int(era_year_match.group(1))
    else:
        era_base_year = 1920

    backstory_occ_part = {
        "会计师": f"在{'一家外资银行' if era_base_year >= 1900 else '一家老字号钱庄'}担任会计主任，日复一日地与数字打交道。某日，在核对一笔异常账目时，发现了一串无法解释的神秘数字，这些数字似乎在多个客户的账户中反复出现。",
        "古董商": "在上海法租界经营一家古董店，专营明清瓷器与古籍。某次从一名神秘卖家手中收购了一尊来历不明的青铜雕像后，开始遭遇一连串诡异事件。",
        "考古学家": "曾参与河南殷墟的考古发掘，在挖掘过程中发现了一块刻有未知文字的石板。学界无人能解读，但{name}隐约感到这些文字与某些可怕的远古存在有关。",
        "作家/记者": f"供职于{'上海《申报》' if era_base_year <= 1940 else '当地报社'}，专门报道社会奇闻。在调查一起连环失踪案时，发现所有受害者都有一个共同点——他们都曾在深夜造访过同一条废弃的街道。",
        "私家侦探": f"在{'上海公共租界' if era_base_year <= 1940 else '当地'}经营一家小侦探社，平日里处理离婚跟踪、寻找失踪人口等案件。直到一位面色苍白的委托人带来了一个令人生畏的委托。",
        "医生": f"在{'上海仁济医院' if era_base_year <= 1940 else '当地医院'}担任外科医生，医术精湛。某夜急诊送来一名浑身布满诡异符号的患者，患者在临终前喃喃低语着令人不安的预言。",
        "警官": f"任职于{'上海法租界巡捕房' if era_base_year <= 1940 else '当地警局'}，以办案果敢著称。最近接手了一起令人不安的案件——多名失踪者在数日后安然返回，却对失踪期间的经历绝口不提。",
        "教授": "在复旦大学教授古代史，专注于中国古代神秘文化研究。一名学生在图书馆地下室发现了一卷写满奇怪符号的竹简，{name}被请去鉴定。",
    }

    default_backstory = f"{name}是来自上海的一位{occupation}，生活在{era}。"
    backstory_lead = backstory_occ_part.get(occupation, default_backstory)
    # 修复字典中 {name} 占位符未被替换的问题
    if isinstance(backstory_lead, str) and "{name}" in backstory_lead:
        backstory_lead = backstory_lead.replace("{name}", name)

    birth_year = era_base_year - age
    backstory = f"""{name}于{max(1800, birth_year)}年出生在{'一个书香门第' if edu_val >= 60 else '一户普通人家'}。此时正值{era}，{name}从小便感受到了这个时代的特殊气息。{backstory_lead}

{'自幼体弱多病，' if con_val < 40 else '从小身体还算健康，'}年少的{name}{'聪慧过人' if int_val >= 70 else '天资平平但勤奋刻苦'}，在{'学堂' if edu_val >= 50 else '生活中'}度过了平凡而充实的岁月。{('然而，一桩意外彻底改变了' + name + '的人生轨迹。' + ('一场大病之后，' + name + '开始能够看到常人看不见的东西——暗影中的低语、镜中的倒影、梦中的预兆。' if pow_val >= 70 else '一次偶然的机会，' + name + '接触到了那个隐藏在日常世界之下的恐怖真相的一角。')) if pow_val >= 50 or int_val >= 60 else name + '本以为生活会这样平静地继续下去，直到那份不请自来的命运降临在头上。'}

如今，{age}岁的{name}已经成为一名经验丰富的{occupation}，身处{era}的动荡与变革之中。但那些在岁月中积累的知识和阅历，非但没有带来安全感，反而让{name}越发意识到人类在面对宇宙真相时的渺小与无力。"""

    result = {}
    if field == "all" or field == "appearance": result["appearance"] = appearance
    if field == "all" or field == "ideology": result["ideology"] = ideology
    if field == "all" or field == "important": result["important"] = important
    if field == "all" or field == "place": result["place"] = place
    if field == "all" or field == "treasure": result["treasure"] = treasure
    if field == "all" or field == "traits": result["traits"] = traits
    if field == "all" or field == "backstory": result["backstory"] = backstory
    return result


# ========== Flask 路由 ==========
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/admin/players", methods=["GET"])
def admin_get_players():
    all_players = db_manager.list_all_players()
    result = []
    for p in all_players:
        data = db_manager.get_player(p["id"])
        if not data:
            continue
        items = [{"name": i} for i in data.get("items", [])]
        result.append({
            "session_id": p["id"],
            "name": data["base_info"].get("name", ""),
            "occupation": data["base_info"].get("occupation", ""),
            "age": data["base_info"].get("age", 0),
            "gender": data["base_info"].get("gender", ""),
            "era": data["base_info"].get("era", "1920年代"),
            "nationality": data["base_info"].get("nationality", ""),
            "residence": data["base_info"].get("residence", ""),
            "interests": data["base_info"].get("interests", ""),
            "personality": data["base_info"].get("personality", ""),
            "attributes": data.get("attributes", {}),
            "derived": data.get("derived", {}),
            "skills": data.get("skills", {}),
            "items": items,
            "spells": data.get("spells", []),
            "backstory": data.get("backstory", ""),
            "appearance": data.get("appearance", ""),
            "last_active": ""
        })
    return jsonify(result)

@app.route("/character", methods=["GET"])
def get_character_info():
    pid = get_or_create_player_id()
    data = get_character(pid)
    items = [{"name": i} for i in data.get("items", [])]
    return jsonify({
        "player_id": pid,
        "name": data["base_info"].get("name", ""),
        "occupation": data["base_info"].get("occupation", ""),
        "age": data["base_info"].get("age", 0),
        "gender": data["base_info"].get("gender", ""),
        "era": data["base_info"].get("era", "1920年代"),
        "nationality": data["base_info"].get("nationality", ""),
        "residence": data["base_info"].get("residence", ""),
        "san": data["derived"]["san"],
        "hp": data["derived"]["hp"],
        "mp": data["derived"]["mp"],
        "luck": data["derived"]["luck"],
        "max_hp": data["derived"].get("max_hp", data["derived"]["hp"]),
        "max_san": data["derived"].get("max_san", data["derived"]["san"]),
        "attributes": data.get("attributes", {}),
        "derived": data.get("derived", {}),
        "skills": data.get("skills", {}),
        "items": items,
        "spells": data.get("spells", []),
        "backstory": data.get("backstory", ""),
        "appearance": data.get("appearance", ""),
        "damage_bonus": data["derived"].get("damage_bonus", "0"),
        "build": data["derived"].get("build", 0)
    })

@app.route("/api/character/<player_id>", methods=["DELETE"])
def api_delete_character(player_id):
    """删除指定角色卡"""
    try:
        deleted = db_manager.delete_player(player_id)
        if deleted:
            return jsonify({"success": True, "message": f"角色 {player_id} 已删除"})
        else:
            return jsonify({"success": False, "message": "未找到该角色"}), 404
    except Exception as e:
        print(f"删除角色失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_input = data.get("message", "").strip()
    if not user_input:
        return jsonify({"error": "输入为空"}), 400

    room_id = get_or_create_room_id()
    player_id = get_or_create_player_id()
    search_context = web_search(user_input) if "搜索" in user_input else ""

    reply = chat_with_deepseek(room_id, player_id, user_input, search_context)

    audio_b64 = None
    if reply and TTS_AVAILABLE:
        try:
            audio_wav = tts.synthesize(reply)
            if audio_wav:
                audio_b64 = base64.b64encode(audio_wav).decode("utf-8")
        except Exception as e:
            print(f"TTS失败: {e}")

    return jsonify({"reply": reply, "audio_base64": audio_b64})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)