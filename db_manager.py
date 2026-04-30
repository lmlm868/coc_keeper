import sqlite3
import json

DB_PATH = "characters.db"

def init_db():
    """初始化数据库，创建玩家数据表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            data TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def get_player(pc_id):
    """根据角色ID获取档案 (JSON格式返回)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT data FROM players WHERE id = ?", (pc_id,))
    row = cursor.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None

def update_player(pc_id, data):
    """更新或创建角色档案"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO players (id, name, data) VALUES (?, ?, ?)",
                   (pc_id, data.get("base_info", {}).get("name", ""), json.dumps(data)))
    conn.commit()
    conn.close()

def list_all_players():
    """获取所有角色ID和姓名列表，方便AI进行选择"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM players")
    players = cursor.fetchall()
    conn.close()
    return [{"id": p[0], "name": p[1]} for p in players]

def delete_player(pc_id):
    """根据角色ID删除角色档案"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM players WHERE id = ?", (pc_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted