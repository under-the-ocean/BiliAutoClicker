from flask import Flask, request, jsonify, render_template, flash, redirect, url_for, session
from flask_bcrypt import Bcrypt
import sqlite3
import json
from datetime import datetime, date, timedelta
import os
from functools import wraps
import re  # 新增：用于正则表达式处理

# 初始化Flask应用
app = Flask(__name__, template_folder='templates')
app.secret_key = 'wefhe3rhg443t654yt34t4v4478fb7344783tw737bt7w46t43794s64t6fbvseru8tr4y6437478'  # 生产环境请修改为随机字符串
bcrypt = Bcrypt(app)

# 确保templates目录存在
if not os.path.exists('templates'):
    os.makedirs('templates')

# 新增：确保logs目录存在
if not os.path.exists('logs'):
    os.makedirs('logs')

# ------------------- 核心配置 -------------------
ROLES = {
    'admin': '管理员',    # 全权限（修改配置、审核申请等）
    'viewer': '普通用户'  # 仅查看和提交申请
}
LOGIN_EXPIRE = timedelta(hours=2)  # 登录失效时间
APPLY_STATUS = {
    'pending': '待审核',
    'approved': '已通过',
    'rejected': '已拒绝'
}

# ------------------- 新增：任务数据处理函数 -------------------
def process_task_data(task_list):
    """
    处理任务数据为 {简化名称: taskid}，支持：
    1. 游戏简称：原神=原，崩铁=铁，绝区零=绝
    2. 自动识别任意天数（1天/3天/10天等）
    3. 自动提取上下半标识（上半/下半）
    :param task_list: 原始任务列表（含"任务ID""奖励信息""页面标题"键）
    :return: 简化后的任务字典
    """
    task_dict = {}
    for task in task_list:
        task_id = task["task_id"]
        reward_info = task.get("award_info", "")
        page_title = task.get("section_title", "")
        
        # 1. 提取游戏简称
        game_short = ""
        if "原神" in page_title:
            game_short = "原"
        elif "崩坏：星穹铁道" in page_title or "崩铁" in page_title:
            game_short = "铁"
        elif "绝区零" in page_title:
            game_short = "绝"
        
        # 2. 用正则提取关键信息：天数（数字）、上下半、任务类型（直播/投稿）
        # 匹配天数（如1/5/20等数字，后接"天"）
        day_match = re.search(r'(\d+)天', reward_info)
        day = day_match.group(1) if day_match else ""
        
        # 匹配上下半（如"上半""下半"）
        half_match = re.search(r'(上半|下半)', reward_info)
        half = half_match.group(1) if half_match else ""
        
        # 3. 识别任务类型并生成简化名
        # 直播类任务关键词
        if any(keyword in reward_info for keyword in ["直播里程碑任务", "直播任务", "每日直播任务"]):
            # 直播类任务：游戏简称+直播+天数（如"绝直播5"）
            simplified_name = f"{game_short}直播{day}"
        # 看播类任务关键词
        elif any(keyword in reward_info for keyword in ["看播里程碑", "看播"]):
            # 看播类任务：游戏简称+看播+天数（如"原看播20"）
            simplified_name = f"{game_short}看播{day}"
        # 投稿类任务
        elif "投稿" in reward_info:
            # 投稿类任务：游戏简称+投稿+天数+上下半（如"铁投稿1上""原投稿3下"）
            simplified_name = f"{game_short}投稿{day}{half}" if day else f"{game_short}投稿{half}"
        else:
            # 其他任务：保留核心信息（游戏简称+前6字）
            simplified_name = f"{game_short}{reward_info[:6]}"
        
        # 4. 去重：同简化名只保留首个taskid（可改为保留最新，需加时间判断）
        if simplified_name not in task_dict:
            task_dict[simplified_name] = task_id
    
    return task_dict

def sync_processed_tasks_to_config(processed_tasks):
    """
    将处理后的任务同步到config_tasks表
    :param processed_tasks: 处理后的任务字典 {简化名称: taskid}
    :return: (新增数量, 更新数量, 总数量)
    """
    conn = get_db_connection()
    try:
        added_count = 0
        updated_count = 0
        
        for task_key, task_value in processed_tasks.items():
            # 检查是否已存在相同task_key的任务
            existing_task = conn.execute(
                'SELECT id, task_value FROM config_tasks WHERE task_key = ?', 
                (task_key,)
            ).fetchone()
            
            if existing_task:
                # 如果存在但taskid不同，则更新
                if existing_task['task_value'] != task_value:
                    conn.execute(
                        'UPDATE config_tasks SET task_value = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                        (task_value, existing_task['id'])
                    )
                    updated_count += 1
                    print(f"🔄 更新任务: {task_key} -> {task_value}")
            else:
                # 如果不存在，则添加新任务
                conn.execute(
                    'INSERT INTO config_tasks (task_key, task_value, updated_by) VALUES (?, ?, ?)',
                    (task_key, task_value, get_anonymous_user_id())
                )
                added_count += 1
                print(f"✅ 新增任务: {task_key} -> {task_value}")
        
        conn.commit()
        total_count = conn.execute('SELECT COUNT(id) FROM config_tasks').fetchone()[0]
        return added_count, updated_count, total_count
        
    except Exception as e:
        conn.rollback()
        print(f"⚠️ 同步任务到配置表失败: {str(e)}")
        return 0, 0, 0
    finally:
        conn.close()

def get_recent_page_info(limit=50):
    """
    获取最近的页面信息用于任务处理
    :param limit: 获取的记录数量
    :return: 页面信息列表
    """
    conn = get_db_connection()
    try:
        results = conn.execute('''
            SELECT task_id, section_title, award_info, extract_time, created_at 
            FROM page_info 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        
        return [dict(res) for res in results]
    except Exception as e:
        print(f"⚠️ 获取页面信息失败: {str(e)}")
        return []
    finally:
        conn.close()

def auto_process_tasks_after_upload():
    """
    在页面信息上传后自动处理任务
    """
    try:
        print("🔄 开始自动处理任务数据...")
        
        # 获取最近的页面信息
        page_info_list = get_recent_page_info(limit=50)
        
        if not page_info_list:
            print("⚠️ 没有可处理的页面信息数据")
            return False, "没有可处理的页面信息数据"
        
        # 处理任务数据
        processed_tasks = process_task_data(page_info_list)
        
        if not processed_tasks:
            print("⚠️ 任务数据处理失败或无有效数据")
            return False, "任务数据处理失败或无有效数据"
        
        # 同步到配置表
        added_count, updated_count, total_count = sync_processed_tasks_to_config(processed_tasks)
        
        result_message = f"自动处理完成！新增: {added_count}, 更新: {updated_count}, 总任务数: {total_count}"
        print(f"✅ {result_message}")
        
        # 记录处理结果
        if added_count > 0 or updated_count > 0:
            print("📋 处理结果:")
            for name, task_id in sorted(processed_tasks.items()):
                print(f"  {name}: {task_id}")
        
        return True, result_message
        
    except Exception as e:
        error_message = f'自动任务处理失败：{str(e)}'
        print(f"❌ {error_message}")
        return False, error_message

# ------------------- 数据库配置 -------------------
def get_db_connection():
    """创建并返回数据库连接（支持UTF-8编码）"""
    conn = sqlite3.connect('config.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 支持字典式访问
    conn.execute('PRAGMA encoding = "UTF-8"')
    return conn

def migrate_database(conn):
    """数据库迁移：添加缺失的列"""
    try:
        # 检查 device_stats 表是否有 device_name 列
        cursor = conn.execute("PRAGMA table_info(device_stats)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'device_name' not in columns:
            print("🔄 添加 device_name 列到 device_stats 表")
            conn.execute('ALTER TABLE device_stats ADD COLUMN device_name TEXT')
        
        # 检查 reward_results 表是否有所有需要的列
        cursor = conn.execute("PRAGMA table_info(reward_results)")
        columns = [column[1] for column in cursor.fetchall()]
        
        required_columns = ['device_name', 'total_tasks', 'task_id', 'status', 
                           'response_code', 'message', 'task_timestamp', 'upload_time']
        
        for col in required_columns:
            if col not in columns:
                print(f"🔄 添加 {col} 列到 reward_results 表")
                if col in ['total_tasks', 'response_code']:
                    conn.execute(f'ALTER TABLE reward_results ADD COLUMN {col} INTEGER')
                else:
                    conn.execute(f'ALTER TABLE reward_results ADD COLUMN {col} TEXT')
        
        # 新增：检查 page_info 表是否存在
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='page_info'")
        if not cursor.fetchone():
            print("🔄 创建 page_info 表")
            conn.execute('''
                CREATE TABLE page_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    section_title TEXT,
                    award_info TEXT,
                    extract_time TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        
        conn.commit()
        print("✅ 数据库迁移完成")
    except Exception as e:
        print(f"⚠️ 数据库迁移错误: {str(e)}")

def init_db():
    """初始化数据库：创建所有必要的表和默认用户"""
    conn = get_db_connection()
    try:
        # 1. 用户表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # 2. 修改申请表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS modify_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apply_user_id INTEGER NOT NULL,
                apply_username TEXT NOT NULL,
                apply_type TEXT NOT NULL,
                apply_data TEXT NOT NULL,
                apply_desc TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                approve_user_id INTEGER,
                approve_username TEXT,
                approve_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (apply_user_id) REFERENCES users(id),
                FOREIGN KEY (approve_user_id) REFERENCES users(id)
            )
        ''')
        
        # 3. 基础配置表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS config_base (
                id INTEGER PRIMARY KEY DEFAULT 1,
                cookies_dir TEXT NOT NULL DEFAULT 'autowatch_cookies',
                reward_base_url TEXT NOT NULL DEFAULT 'https://www.bilibili.com/blackboard/era-award-exchange.html',
                reward_claim_selector TEXT NOT NULL DEFAULT '//*[@id="app"]/div/div[3]/section[2]/div[1]',
                max_reload_attempts INTEGER NOT NULL DEFAULT 3,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER,
                FOREIGN KEY (updated_by) REFERENCES users(id),
                UNIQUE(id)
            )
        ''')
        
        # 4. 任务ID表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS config_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_key TEXT NOT NULL UNIQUE,
                task_value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER,
                FOREIGN KEY (updated_by) REFERENCES users(id)
            )
        ''')
        
        # 5. 客户端统计表 - 修复：添加 device_name 列
        conn.execute('''
            CREATE TABLE IF NOT EXISTS device_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                device_name TEXT,
                first_access DATE DEFAULT CURRENT_DATE,
                last_access TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 1,
                UNIQUE(device_id)
            )
        ''')
        
        # 6. 每日访问表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                access_date DATE DEFAULT CURRENT_DATE,
                access_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(device_id, access_date)
            )
        ''')
        
        # 7. 奖励结果表 - 修复：确保所有需要的列都存在
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reward_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT NOT NULL,
                total_tasks INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                response_code INTEGER,
                message TEXT,
                task_timestamp TEXT NOT NULL,
                upload_time TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 8. 新增：页面信息表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS page_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                device_name TEXT NOT NULL,
                section_title TEXT,
                award_info TEXT,
                extract_time TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建匿名用户（用于解决NOT NULL约束问题）
        if not conn.execute('SELECT id FROM users WHERE username = "anonymous"').fetchone():
            anon_pwd_hash = bcrypt.generate_password_hash('anonymous_123').decode('utf-8')
            conn.execute('''
                INSERT INTO users (username, password_hash, role)
                VALUES (?, ?, ?)
            ''', ('anonymous', anon_pwd_hash, 'viewer'))
        
        # 创建默认管理员账号 (admin/Admin123!)
        if not conn.execute('SELECT id FROM users WHERE username = "admin"').fetchone():
            admin_pwd_hash = bcrypt.generate_password_hash('Undertheocean').decode('utf-8')
            conn.execute('''
                INSERT INTO users (username, password_hash, role)
                VALUES (?, ?, ?)
            ''', ('admin', admin_pwd_hash, 'admin'))
        
        # 初始化基础配置
        conn.execute('INSERT OR IGNORE INTO config_base (id) VALUES (1)')
        conn.commit()
        
        # 执行数据库迁移
        migrate_database(conn)
        
    except Exception as e:
        print(f"⚠️ 数据库初始化错误: {str(e)}")
    finally:
        conn.close()
    print("✅ 数据库初始化完成")

# ------------------- 权限装饰器 -------------------
def login_required(f):
    """验证登录状态，未登录/过期则跳转登录页"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录后访问', 'error')
            return redirect(url_for('login', next=request.url))
        
        # 检查登录过期
        last_active = session.get('last_active')
        if last_active and (datetime.now() - datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S')) > LOGIN_EXPIRE:
            session.clear()
            flash('登录已过期，请重新登录', 'error')
            return redirect(url_for('login', next=request.url))
        
        # 刷新最后活跃时间
        session['last_active'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """仅管理员可访问"""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if session.get('user_role') != 'admin':
            flash('无权限访问此页面（仅管理员可操作）', 'error')
            return redirect(url_for('manage'))
        return f(*args, **kwargs)
    return decorated

# ------------------- 用户相关函数 -------------------
def get_user_by_username(username):
    """根据用户名查询用户"""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_anonymous_user_id():
    """获取匿名用户ID（用于匿名提交）"""
    conn = get_db_connection()
    user = conn.execute('SELECT id FROM users WHERE username = "anonymous"').fetchone()
    conn.close()
    return user['id'] if user else 1  # fallback到管理员ID

def update_last_login(user_id):
    """更新用户最后登录时间"""
    conn = get_db_connection()
    conn.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

# ------------------- 修改申请相关函数 -------------------
def add_modify_apply(apply_user_id, apply_username, apply_type, apply_data, apply_desc):
    """添加修改申请"""
    conn = get_db_connection()
    try:
        # 确保用户名不为空
        if not apply_username or apply_username.strip() == '':
            apply_username = '访客'
            
        conn.execute('''
            INSERT INTO modify_applications 
            (apply_user_id, apply_username, apply_type, apply_data, apply_desc)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            apply_user_id,
            apply_username,
            apply_type,
            json.dumps(apply_data),
            apply_desc or ''
        ))
        conn.commit()
        return True, "申请提交成功，等待管理员审核"
    except Exception as e:
        conn.rollback()
        return False, f"申请提交失败：{str(e)}"
    finally:
        conn.close()

def get_modify_applies(status=None, page=1, page_size=10, user_id=None):
    """获取修改申请列表（支持筛选和分页）"""
    conn = get_db_connection()
    try:
        offset = (page - 1) * page_size
        params = []
        
        # 构建查询条件
        query_sql = 'SELECT * FROM modify_applications WHERE 1=1'
        if status and status in APPLY_STATUS.keys():
            query_sql += ' AND status = ?'
            params.append(status)
        if user_id is not None:
            query_sql += ' AND apply_user_id = ?'
            params.append(user_id)
            
        # 排序和分页
        query_sql += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([page_size, offset])
        
        # 执行查询
        applies = conn.execute(query_sql, params).fetchall()
        
        # 计算总数
        count_sql = 'SELECT COUNT(id) FROM modify_applications WHERE 1=1'
        count_params = []
        if status and status in APPLY_STATUS.keys():
            count_sql += ' AND status = ?'
            count_params.append(status)
        if user_id is not None:
            count_sql += ' AND apply_user_id = ?'
            count_params.append(user_id)
            
        total = conn.execute(count_sql, count_params).fetchone()[0]
        
        # 处理结果
        apply_list = []
        for apply in applies:
            apply_dict = dict(apply)
            apply_dict['apply_data'] = json.loads(apply_dict['apply_data'])
            apply_list.append(apply_dict)
        
        total_pages = (total + page_size - 1) // page_size
        return {
            'applications': apply_list,
            'total_pages': total_pages,
            'current_page': page,
            'total': total
        }
    except Exception as e:
        print(f"⚠️ 查询申请错误: {str(e)}")
        return {'applications': [], 'total_pages': 0, 'current_page': 1, 'total': 0}
    finally:
        conn.close()

def approve_modify_apply(apply_id, approve_user_id, approve_username, is_approved):
    """审核修改申请"""
    conn = get_db_connection()
    try:
        # 查询申请
        apply = conn.execute('SELECT * FROM modify_applications WHERE id = ?', (apply_id,)).fetchone()
        if not apply:
            return False, "申请不存在"
        if apply['status'] != 'pending':
            return False, f"申请已处理（当前状态：{APPLY_STATUS[apply['status']]}）"
        
        # 更新申请状态
        status = 'approved' if is_approved else 'rejected'
        conn.execute('''
            UPDATE modify_applications 
            SET status = ?, approve_user_id = ?, approve_username = ?, approve_time = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, approve_user_id, approve_username, apply_id))
        
        # 审核通过则更新配置
        if is_approved:
            apply_data = json.loads(apply['apply_data'])
            apply_type = apply['apply_type']
            
            # 处理基础配置修改
            if apply_type == 'base_config':
                conn.execute('''
                    UPDATE config_base 
                    SET cookies_dir = ?, reward_base_url = ?, reward_claim_selector = ?, 
                        max_reload_attempts = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                    WHERE id = 1
                ''', (
                    apply_data['cookies_dir'],
                    apply_data['reward_base_url'],
                    apply_data['reward_claim_selector'],
                    int(apply_data['max_reload_attempts']),
                    approve_user_id
                ))
            
            # 处理任务修改
            elif apply_type == 'task':
                task_action = apply_data['action']
                if task_action == 'add':
                    conn.execute('''
                        INSERT INTO config_tasks (task_key, task_value, updated_by)
                        VALUES (?, ?, ?)
                    ''', (apply_data['new_task_key'], apply_data['new_task_value'], approve_user_id))
                elif task_action == 'edit':
                    conn.execute('''
                        UPDATE config_tasks 
                        SET task_key = ?, task_value = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                        WHERE id = ?
                    ''', (apply_data['new_task_key'], apply_data['new_task_value'], approve_user_id, int(apply_data['task_id'])))
                elif task_action == 'delete':
                    conn.execute('DELETE FROM config_tasks WHERE id = ?', (int(apply_data['task_id']),))
        
        conn.commit()
        return True, f"申请已{status}（{APPLY_STATUS[status]}）"
    except Exception as e:
        conn.rollback()
        return False, f"审核失败：{str(e)}"
    finally:
        conn.close()

# ------------------- 客户端统计相关函数 -------------------
def update_client_stats(device_id, device_name=None):
    """更新客户端访问统计，新增设备名参数"""
    conn = get_db_connection()
    try:
        today = date.today()
        device = conn.execute('SELECT id FROM device_stats WHERE device_id = ?', (device_id,)).fetchone()
        
        if device:
            # 更新现有设备记录
            if device_name:
                conn.execute('''
                    UPDATE device_stats 
                    SET device_name = ?, last_access = CURRENT_TIMESTAMP, access_count = access_count + 1
                    WHERE device_id = ?
                ''', (device_name, device_id))
            else:
                conn.execute('''
                    UPDATE device_stats 
                    SET last_access = CURRENT_TIMESTAMP, access_count = access_count + 1
                    WHERE device_id = ?
                ''', (device_id,))
        else:
            # 插入新设备记录
            if device_name:
                conn.execute('''
                    INSERT INTO device_stats (device_id, device_name, first_access)
                    VALUES (?, ?, ?)
                ''', (device_id, device_name, today))
            else:
                conn.execute('''
                    INSERT INTO device_stats (device_id, first_access)
                    VALUES (?, ?)
                ''', (device_id, today))
        
        # 记录每日访问
        if not conn.execute('''
            SELECT id FROM daily_access 
            WHERE device_id = ? AND access_date = ?
        ''', (device_id, today)).fetchone():
            conn.execute('''
                INSERT INTO daily_access (device_id, access_date) 
                VALUES (?, ?)
            ''', (device_id, today))
        
        conn.commit()
    except Exception as e:
        print(f"⚠️ 统计更新错误: {str(e)}")
    finally:
        conn.close()

def get_client_overview():
    """获取客户端统计概览"""
    conn = get_db_connection()
    try:
        today = date.today()
        total_devices = conn.execute('SELECT COUNT(DISTINCT device_id) FROM device_stats').fetchone()[0]
        today_active = conn.execute('''
            SELECT COUNT(DISTINCT device_id) FROM daily_access 
            WHERE access_date = ?
        ''', (today,)).fetchone()[0]
        total_access = conn.execute('SELECT SUM(access_count) FROM device_stats').fetchone()[0] or 0
        
        # 近7天趋势
        week_trend = []
        for i in range(6, -1, -1):
            target_date = today - timedelta(days=i)
            count = conn.execute('''
                SELECT COUNT(DISTINCT device_id) FROM daily_access 
                WHERE access_date = ?
            ''', (target_date,)).fetchone()[0]
            week_trend.append({'date': str(target_date), 'active_count': count})
        
        return {
            'total_devices': total_devices,
            'today_active': today_active,
            'total_access': total_access,
            'week_trend': week_trend
        }
    except Exception as e:
        print(f"⚠️ 获取概览错误: {str(e)}")
        return {'total_devices': 0, 'today_active': 0, 'total_access': 0, 'week_trend': []}
    finally:
        conn.close()

def get_client_detail_list(page=1, page_size=10):
    """获取客户端详细列表（分页）"""
    conn = get_db_connection()
    try:
        offset = (page - 1) * page_size
        devices = conn.execute('''
            SELECT device_id, device_name, first_access, last_access, access_count 
            FROM device_stats 
            ORDER BY last_access DESC 
            LIMIT ? OFFSET ?
        ''', (page_size, offset)).fetchall()
        total = conn.execute('SELECT COUNT(id) FROM device_stats').fetchone()[0]
        total_pages = (total + page_size - 1) // page_size
        
        return {
            'devices': [dict(dev) for dev in devices],
            'total_pages': total_pages,
            'current_page': page
        }
    except Exception as e:
        print(f"⚠️ 获取设备列表错误: {str(e)}")
        return {'devices': [], 'total_pages': 0, 'current_page': 1}
    finally:
        conn.close()

# ------------------- 奖励结果相关函数 -------------------
def add_reward_result(data):
    """添加奖励结果记录，支持批量添加"""
    conn = get_db_connection()
    try:
        # 如果是批量上传（客户端新格式）
        if 'results' in data and isinstance(data['results'], list):
            inserted_count = 0
            for result in data['results']:
                # 使用 INSERT OR REPLACE 确保唯一性
                conn.execute('''
                    INSERT OR REPLACE INTO reward_results 
                    (device_name, total_tasks, task_id, status, response_code, message, 
                     task_timestamp, upload_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data.get('device_name', result.get('device_name')),
                    data.get('total_tasks', len(data['results'])),
                    result.get('task_id'),
                    result.get('status'),
                    result.get('response_code'),
                    result.get('message'),
                    result.get('timestamp'),
                    data.get('upload_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                ))
                inserted_count += 1
            conn.commit()
            return True, f"成功插入 {inserted_count} 条记录"
        else:
            # 单个结果上传（旧格式）
            conn.execute('''
                INSERT OR REPLACE INTO reward_results 
                (device_name, total_tasks, task_id, status, response_code, message, 
                 task_timestamp, upload_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('device_name'),
                int(data.get('total_tasks', 1)),
                data.get('task_id'),
                data.get('status'),
                data.get('response_code'),
                data.get('message'),
                data.get('task_timestamp'),
                data.get('upload_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            ))
            conn.commit()
            return True, "成功插入 1 条记录"
    except Exception as e:
        conn.rollback()
        print(f"⚠️ 添加奖励结果错误: {str(e)}")
        return False, str(e)
    finally:
        conn.close()

def get_reward_stats(status=None):
    """获取奖励结果统计"""
    conn = get_db_connection()
    try:
        # 基础查询
        base_sql = 'SELECT * FROM reward_results'
        count_sql = 'SELECT COUNT(id) FROM reward_results'
        params = []
        
        # 状态筛选
        if status:
            base_sql += ' WHERE status = ?'
            count_sql += ' WHERE status = ?'
            params.append(status)
        
        # 总数
        total_count = conn.execute(count_sql, params).fetchone()[0]
        
        # 成功/失败数
        success_count = conn.execute(
            'SELECT COUNT(id) FROM reward_results WHERE status = "成功" OR status = "success"').fetchone()[0]
        fail_count = conn.execute(
            'SELECT COUNT(id) FROM reward_results WHERE status = "失败" OR status = "fail"').fetchone()[0]
        
        # 成功率
        success_rate = round((success_count / total_count) * 100, 1) if total_count > 0 else 0
        
        return {
            'total_count': total_count,
            'success_count': success_count,
            'fail_count': fail_count,
            'success_rate': success_rate
        }
    except Exception as e:
        print(f"⚠️ 获取奖励统计错误: {str(e)}")
        return {'total_count': 0, 'success_count': 0, 'fail_count': 0, 'success_rate': 0}
    finally:
        conn.close()

def get_reward_list(page=1, page_size=10, status=None):
    """获取奖励结果列表（分页）"""
    conn = get_db_connection()
    try:
        offset = (page - 1) * page_size
        params = []
        
        # 构建查询
        query_sql = 'SELECT * FROM reward_results'
        count_sql = 'SELECT COUNT(id) FROM reward_results'
        
        if status:
            query_sql += ' WHERE status = ?'
            count_sql += ' WHERE status = ?'
            params.append(status)
            
        query_sql += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([page_size, offset])
        
        # 执行查询
        results = conn.execute(query_sql, params).fetchall()
        total = conn.execute(count_sql, params[:1] if status else []).fetchone()[0]
        total_pages = (total + page_size - 1) // page_size
        
        return {
            'results': [dict(res) for res in results],
            'total_pages': total_pages,
            'current_page': page,
            'total_count': total
        }
    except Exception as e:
        print(f"⚠️ 获取奖励列表错误: {str(e)}")
        return {'results': [], 'total_pages': 0, 'current_page': 1, 'total_count': 0}
    finally:
        conn.close()

# ------------------- 新增：页面信息相关函数 -------------------
def add_page_info(data):
    """添加页面信息记录"""
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO page_info 
            (task_id, device_name, section_title, award_info, extract_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data.get('task_id'),
            data.get('device_name'),
            data.get('section_title'),
            data.get('award_info'),
            data.get('extract_time')
        ))
        conn.commit()
        return True, "页面信息保存成功"
    except Exception as e:
        conn.rollback()
        print(f"⚠️ 添加页面信息错误: {str(e)}")
        return False, str(e)
    finally:
        conn.close()

def get_page_info_stats():
    """获取页面信息统计"""
    conn = get_db_connection()
    try:
        # 总数
        total_count = conn.execute('SELECT COUNT(id) FROM page_info').fetchone()[0]
        
        # 不同设备的数量
        device_count = conn.execute('SELECT COUNT(DISTINCT device_name) FROM page_info').fetchone()[0]
        
        # 不同任务的数量
        task_count = conn.execute('SELECT COUNT(DISTINCT task_id) FROM page_info').fetchone()[0]
        
        return {
            'total_count': total_count,
            'device_count': device_count,
            'task_count': task_count
        }
    except Exception as e:
        print(f"⚠️ 获取页面信息统计错误: {str(e)}")
        return {'total_count': 0, 'device_count': 0, 'task_count': 0}
    finally:
        conn.close()

def get_page_info_list(page=1, page_size=10):
    """获取页面信息列表（分页）"""
    conn = get_db_connection()
    try:
        offset = (page - 1) * page_size
        
        # 执行查询
        results = conn.execute('''
            SELECT * FROM page_info 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', (page_size, offset)).fetchall()
        
        total = conn.execute('SELECT COUNT(id) FROM page_info').fetchone()[0]
        total_pages = (total + page_size - 1) // page_size
        
        return {
            'page_info': [dict(res) for res in results],
            'total_pages': total_pages,
            'current_page': page,
            'total_count': total
        }
    except Exception as e:
        print(f"⚠️ 获取页面信息列表错误: {str(e)}")
        return {'page_info': [], 'total_pages': 0, 'current_page': 1, 'total_count': 0}
    finally:
        conn.close()

# ------------------- 路由定义 -------------------
@app.route('/')
def index():
    """首页重定向到配置管理页"""
    return redirect(url_for('manage'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('请输入用户名和密码', 'error')
            return render_template('login.html')
        
        # 验证用户
        user = get_user_by_username(username)
        if not user or not bcrypt.check_password_hash(user['password_hash'], password):
            flash('用户名或密码错误', 'error')
            return render_template('login.html')
        
        # 验证是否为管理员（只有管理员需要登录）
        if user['role'] != 'admin':
            flash('仅管理员可登录', 'error')
            return render_template('login.html')
        
        # 设置session
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['user_role'] = user['role']
        session['last_active'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 更新最后登录时间
        update_last_login(user['id'])
        
        # 跳转回之前的页面
        next_page = request.args.get('next', url_for('manage'))
        return redirect(next_page)
    
    # GET请求显示登录页
    return render_template('login.html')

@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    flash('已成功退出登录', 'success')
    return redirect(url_for('manage'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """修改密码"""
    if request.method == 'POST':
        current_pwd = request.form.get('current_pwd')
        new_pwd = request.form.get('new_pwd')
        confirm_pwd = request.form.get('confirm_pwd')
        
        # 验证表单
        if not all([current_pwd, new_pwd, confirm_pwd]):
            flash('请填写所有字段', 'error')
            return render_template('change_password.html')
        
        if new_pwd != confirm_pwd:
            flash('新密码与确认密码不一致', 'error')
            return render_template('change_password.html')
        
        if len(new_pwd) < 6:
            flash('新密码长度至少6位', 'error')
            return render_template('change_password.html')
        
        # 验证当前密码
        user = get_user_by_username(session['username'])
        if not bcrypt.check_password_hash(user['password_hash'], current_pwd):
            flash('当前密码错误', 'error')
            return render_template('change_password.html')
        
        # 更新密码
        conn = get_db_connection()
        try:
            new_pwd_hash = bcrypt.generate_password_hash(new_pwd).decode('utf-8')
            conn.execute('''
                UPDATE users 
                SET password_hash = ? 
                WHERE id = ?
            ''', (new_pwd_hash, session['user_id']))
            conn.commit()
            flash('密码修改成功，请重新登录', 'success')
            return redirect(url_for('logout'))
        except Exception as e:
            conn.rollback()
            flash(f'修改失败：{str(e)}', 'error')
        finally:
            conn.close()
    
    return render_template('change_password.html')

@app.route('/manage')
def manage():
    """配置管理页面（普通用户可查看，管理员可编辑）"""
    # 获取基础配置
    conn = get_db_connection()
    base_config = conn.execute('SELECT * FROM config_base WHERE id = 1').fetchone()
    # 获取任务列表
    tasks = conn.execute('SELECT * FROM config_tasks ORDER BY id DESC').fetchall()
    conn.close()
    
    # 判断是否为管理员
    is_admin = session.get('user_role') == 'admin'
    
    return render_template(
        'manage.html',
        base_config=dict(base_config) if base_config else None,
        tasks=[dict(task) for task in tasks],
        is_admin=is_admin
    )

@app.route('/update_base_config', methods=['POST'])
@admin_required
def update_base_config():
    """管理员直接更新基础配置"""
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE config_base 
            SET cookies_dir = ?, reward_base_url = ?, reward_claim_selector = ?, 
                max_reload_attempts = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
            WHERE id = 1
        ''', (
            request.form.get('cookies_dir'),
            request.form.get('reward_base_url'),
            request.form.get('reward_claim_selector'),
            int(request.form.get('max_reload_attempts', 3)),
            session['user_id']
        ))
        conn.commit()
        flash('基础配置更新成功', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'更新失败：{str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('manage'))

@app.route('/add_task', methods=['POST'])
@admin_required
def add_task():
    """管理员添加任务"""
    task_key = request.form.get('task_key')
    task_value = request.form.get('task_value')
    
    if not task_key or not task_value:
        flash('任务标识和值不能为空', 'error')
        return redirect(url_for('manage'))
    
    conn = get_db_connection()
    try:
        # 检查重复
        if conn.execute('SELECT id FROM config_tasks WHERE task_key = ?', (task_key,)).fetchone():
            flash(f'任务标识 "{task_key}" 已存在', 'error')
            return redirect(url_for('manage'))
        
        conn.execute('''
            INSERT INTO config_tasks (task_key, task_value, updated_by)
            VALUES (?, ?, ?)
        ''', (task_key, task_value, session['user_id']))
        conn.commit()
        flash('任务添加成功', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'添加失败：{str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('manage'))

@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
@admin_required
def edit_task(task_id):
    """编辑任务"""
    # 检查任务是否存在
    conn = get_db_connection()
    task = conn.execute('SELECT * FROM config_tasks WHERE id = ?', (task_id,)).fetchone()
    conn.close()
    
    if not task:
        flash(f'任务 ID {task_id} 不存在', 'error')
        return redirect(url_for('manage'))
    
    # 处理POST提交
    if request.method == 'POST':
        new_task_key = request.form.get('task_key')
        new_task_value = request.form.get('task_value')
        
        if not new_task_key or not new_task_value:
            flash('任务标识和值不能为空', 'error')
            return render_template('edit_task.html', task=dict(task))
        
        conn = get_db_connection()
        try:
            # 检查重复（排除当前任务）
            duplicate = conn.execute('''
                SELECT id FROM config_tasks 
                WHERE task_key = ? AND id != ?
            ''', (new_task_key, task_id)).fetchone()
            
            if duplicate:
                flash(f'任务标识 "{new_task_key}" 已存在', 'error')
                return render_template('edit_task.html', task=dict(task))
            
            # 更新任务
            conn.execute('''
                UPDATE config_tasks 
                SET task_key = ?, task_value = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                WHERE id = ?
            ''', (new_task_key, new_task_value, session['user_id'], task_id))
            conn.commit()
            flash('任务更新成功', 'success')
            return redirect(url_for('manage'))
        except Exception as e:
            conn.rollback()
            flash(f'更新失败：{str(e)}', 'error')
        finally:
            conn.close()
    
    # GET请求显示编辑页
    return render_template('edit_task.html', task=dict(task))

@app.route('/delete_task/<int:task_id>')
@admin_required
def delete_task(task_id):
    """删除任务"""
    conn = get_db_connection()
    try:
        # 检查任务是否存在
        if not conn.execute('SELECT id FROM config_tasks WHERE id = ?', (task_id,)).fetchone():
            flash(f'任务 ID {task_id} 不存在', 'error')
            return redirect(url_for('manage'))
        
        conn.execute('DELETE FROM config_tasks WHERE id = ?', (task_id,))
        conn.commit()
        flash('任务删除成功', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'删除失败：{str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('manage'))

# ------------------- 新增：任务处理路由 -------------------
@app.route('/process_tasks', methods=['POST'])
@admin_required
def process_tasks():
    """处理页面信息并同步到任务配置（手动触发）"""
    try:
        success, message = auto_process_tasks_after_upload()
        
        if success:
            flash(f'手动处理完成！{message}', 'success')
        else:
            flash(f'手动处理失败：{message}', 'error')
        
    except Exception as e:
        flash(f'任务处理失败：{str(e)}', 'error')
    
    return redirect(url_for('page_info'))

@app.route('/submit_apply', methods=['POST'])
def submit_apply():
    """普通用户提交修改申请"""
    try:
        # 获取表单数据
        apply_type = request.form.get('apply_type')
        apply_data_str = request.form.get('apply_data')
        apply_desc = request.form.get('apply_desc', '').strip()
        
        # 基础验证
        if not apply_type:
            flash('申请类型不能为空', 'error')
            return redirect(url_for('manage'))
            
        if not apply_data_str:
            flash('申请数据不能为空', 'error')
            return redirect(url_for('manage'))
        
        # 解析申请数据
        try:
            apply_data = json.loads(apply_data_str)
        except json.JSONDecodeError as e:
            flash(f'申请数据格式错误: {str(e)}', 'error')
            return redirect(url_for('manage'))
        
        # 补充修改理由
        if not apply_desc and 'desc' in apply_data:
            apply_desc = apply_data['desc']
            del apply_data['desc']
            
        if not apply_desc:
            flash('修改理由不能为空', 'error')
            return redirect(url_for('manage'))
        
        # 确定申请人信息（使用匿名用户ID解决NOT NULL问题）
        if 'user_id' in session:
            apply_user_id = session['user_id']
            apply_username = session['username']
        else:
            apply_user_id = get_anonymous_user_id()
            apply_username = '访客'
        
        # 提交申请
        success, msg = add_modify_apply(
            apply_user_id=apply_user_id,
            apply_username=apply_username,
            apply_type=apply_type,
            apply_data=apply_data,
            apply_desc=apply_desc
        )
        
        flash(msg, 'success' if success else 'error')
    except Exception as e:
        print(f"申请提交异常: {str(e)}")
        flash(f'提交失败: 系统错误 - {str(e)}', 'error')
    
    return redirect(url_for('manage'))

@app.route('/applications')
def applications():
    """修改申请列表页"""
    # 获取查询参数
    status = request.args.get('status')
    page = int(request.args.get('page', 1))
    
    # 管理员查看所有申请，普通用户查看自己的申请
    user_id = session.get('user_id') if session.get('user_role') != 'admin' else None
    
    # 获取申请列表
    app_data = get_modify_applies(
        status=status,
        page=page,
        user_id=user_id
    )
    
    return render_template(
        'applications.html',
        app_data=app_data,
        current_status=status,
        apply_status=APPLY_STATUS,
        is_admin=session.get('user_role') == 'admin'
    )

@app.route('/approve_application/<int:apply_id>', methods=['POST'])
@admin_required
def approve_application(apply_id):
    """通过申请"""
    success, msg = approve_modify_apply(
        apply_id=apply_id,
        approve_user_id=session['user_id'],
        approve_username=session['username'],
        is_approved=True
    )
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('applications'))

@app.route('/reject_application/<int:apply_id>', methods=['POST'])
@admin_required
def reject_application(apply_id):
    """拒绝申请"""
    success, msg = approve_modify_apply(
        apply_id=apply_id,
        approve_user_id=session['user_id'],
        approve_username=session['username'],
        is_approved=False
    )
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('applications'))

@app.route('/client_stats')
def client_stats():
    """客户端统计页面"""
    # 获取参数
    page = int(request.args.get('page', 1))
    reward_page = int(request.args.get('reward_page', 1))
    reward_status = request.args.get('reward_status')
    
    # 获取统计数据
    overview = get_client_overview()
    detail = get_client_detail_list(page=page)
    reward_stats = get_reward_stats(status=reward_status)
    reward_data = get_reward_list(page=reward_page, status=reward_status)
    
    return render_template(
        'client_stats.html',
        overview=overview,
        detail=detail,
        reward_stats=reward_stats,
        reward_data=reward_data,
        current_status=reward_status,
        is_admin=session.get('user_role') == 'admin'
    )

# ------------------- 新增：页面信息管理路由 -------------------
@app.route('/page_info')
@login_required
def page_info():
    """页面信息管理页面"""
    # 获取参数
    page = int(request.args.get('page', 1))
    
    # 获取页面信息统计和列表
    stats = get_page_info_stats()
    page_data = get_page_info_list(page=page)
    
    return render_template(
        'page_info.html',
        stats=stats,
        page_data=page_data,
        is_admin=session.get('user_role') == 'admin'
    )

# ------------------- 客户端API -------------------
@app.route('/get_config')
def get_config():
    """供客户端获取配置，返回符合客户端预期的格式"""
    # 记录客户端访问，获取设备ID和名称
    device_id = request.headers.get('Device-ID', 'unknown')
    device_name = request.args.get('device_name')
    update_client_stats(device_id, device_name)
    
    # 获取配置
    conn = get_db_connection()
    base_config = conn.execute('SELECT * FROM config_base WHERE id = 1').fetchone()
    tasks = conn.execute('SELECT task_key, task_value FROM config_tasks').fetchall()
    conn.close()
    
    if not base_config:
        return jsonify({
            'status': 'error', 
            'message': '配置不存在'
        }), 404
    
    # 构建符合客户端预期的响应格式
    reward_task_ids = {task['task_key']: task['task_value'] for task in tasks}
    
    return jsonify({
        'status': 'success',
        'content': {
            'reward_task_ids': reward_task_ids,
            'cookies_dir': base_config['cookies_dir'],
            'reward_base_url': base_config['reward_base_url'],
            'reward_claim_selector': base_config['reward_claim_selector'],
            'max_reload_attempts': base_config['max_reload_attempts']
        }
    })

@app.route('/upload_reward_result', methods=['POST'])
def upload_reward_result():
    """供客户端上传奖励结果，支持批量上传"""
    try:
        data = request.json
        if not data:
            return jsonify({'status': 'error', 'message': '无数据'}), 400
        
        # 保存结果
        success, msg = add_reward_result(data)
        if success:
            return jsonify({
                'status': 'success', 
                'message': msg,
                'received_count': len(data.get('results', [1]))
            })
        else:
            return jsonify({
                'status': 'error', 
                'message': msg
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': str(e)
        }), 500

# ------------------- 新增：客户端API接口 -------------------
@app.route('/upload_page_info', methods=['POST'])
def upload_page_info():
    """供客户端上传页面信息"""
    try:
        data = request.json
        if not data:
            return jsonify({'status': 'error', 'message': '无数据'}), 400
        
        # 验证必要字段
        required_fields = ['task_id', 'device_name', 'section_title', 'award_info', 'extract_time']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'缺少必要字段: {field}'}), 400
        
        # 保存页面信息
        success, msg = add_page_info(data)
        if success:
            # 自动处理任务数据
            auto_success, auto_msg = auto_process_tasks_after_upload()
            
            response_data = {
                'status': 'success', 
                'message': f'{msg} | 自动处理: {auto_msg}'
            }
            
            # 如果自动处理有结果，也包含在响应中
            if auto_success:
                response_data['auto_processed'] = True
                response_data['auto_message'] = auto_msg
            else:
                response_data['auto_processed'] = False
                response_data['auto_message'] = auto_msg
                
            return jsonify(response_data)
        else:
            return jsonify({
                'status': 'error', 
                'message': msg
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': str(e)
        }), 500

@app.route('/upload_log_file', methods=['POST'])
def upload_log_file():
    """供客户端上传日志文件"""
    try:
        # 检查是否有文件上传
        if 'log_file' not in request.files:
            return jsonify({'status': 'error', 'message': '没有文件'}), 400
        
        log_file = request.files['log_file']
        if log_file.filename == '':
            return jsonify({'status': 'error', 'message': '没有选择文件'}), 400
        
        # 获取设备信息
        device_name = request.form.get('device_name', 'unknown_device')
        upload_time = request.form.get('upload_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # 生成安全的文件名
        safe_device_name = "".join(c for c in device_name if c.isalnum() or c in ('-', '_')).rstrip()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{safe_device_name}_{timestamp}_{log_file.filename}"
        file_path = os.path.join('logs', filename)
        
        # 保存文件
        log_file.save(file_path)
        
        return jsonify({
            'status': 'success', 
            'message': f'日志文件上传成功: {filename}',
            'file_path': file_path
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': f'文件上传失败: {str(e)}'
        }), 500

# ------------------- 错误处理 -------------------
@app.errorhandler(404)
def page_not_found(e):
    """404错误处理"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    """500错误处理"""
    return render_template('500.html'), 500

# ------------------- 启动程序 -------------------
if __name__ == '__main__':
    init_db()  # 初始化数据库
    print("服务器启动中...访问 http://localhost:8080")
    app.run(host='0.0.0.0', port=8088, debug=True)