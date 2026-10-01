from flask_cors import CORS
from flask import Flask, request, session, jsonify
from functools import wraps
import sqlite3
import os
from flask_apscheduler import APScheduler
from datetime import datetime

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = "my_secret_2026_parking"  # session加密密钥

# 登录校验装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"code":401,"msg":"Please log in first"}),401
        return f(*args, **kwargs)
    return decorated_function

# ---------------- 定时任务初始化 ----------------
scheduler = APScheduler()
def auto_update_parking_status():
    """定时任务：扫描预约，时间到达自动变更车位状态"""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[定时任务运行] 当前时间 {now_str}")
    conn = sqlite3.connect("parking.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # 查询所有已预约的车位记录
    cur.execute('''
        SELECT r.id, r.space_id, r.start_time, s.status
        FROM reservations r
        LEFT JOIN spaces s ON r.space_id = s.id
        WHERE s.status = 2
    ''')
    all_reservations = cur.fetchall()
    for res in all_reservations:
        try:
            # 把数据库里 "2026-09-29T00:24" 转换成datetime对象
            start_time_str = res["start_time"].replace("T", " ")
            start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
            if start_time <= now:
                # 预约时间已到，车位从2(已预约) →1(占用)
                cur.execute("UPDATE spaces SET status=1 WHERE id=?", (res["space_id"],))
                print(f"✅车位ID:{res['space_id']} 预约时间到期，变更为【占用】")
        except Exception as e:
            print(f"解析时间出错：{e}")
    conn.commit()
    conn.close()

# 每30秒跑一次
scheduler.add_job("parking_job", auto_update_parking_status, trigger="interval", seconds=30)
scheduler.init_app(app)
scheduler.start()
# ------------------------------------------------

# 数据库初始化函数，首次运行自动建表
def init_db():
    conn = sqlite3.connect("parking.db")
    conn.execute("PRAGMA foreign_keys = ON;") # 开启外键约束
    cursor = conn.cursor()
    # 车位表 spaces
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS spaces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT NOT NULL,
        status INTEGER DEFAULT 0, -- 0空闲，1占用，2已预约
        start_time TEXT
    )
    ''')
    # 用户表 user（明文密码）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'user'
    )
    ''')
    # 预约表 reservations
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        space_id INTEGER,
        user_id INTEGER,
        start_time TEXT,
        FOREIGN KEY (space_id) REFERENCES spaces(id),
        FOREIGN KEY (user_id) REFERENCES user(id)
    )
    ''')
    # 插入测试车位（不存在才插入）
    cursor.execute("SELECT COUNT(*) FROM spaces")
    count_space = cursor.fetchone()[0]
    if count_space == 0:
        demo_spaces = [
            ("A01",0),("A02",0),("A03",0),
            ("B01",0),("B02",0),("B03",0)
        ]
        cursor.executemany("INSERT INTO spaces(location,status) VALUES (?,?)", demo_spaces)
    # 插入预置账号（不存在才插入）
    cursor.execute("SELECT COUNT(*) FROM user")
    count_user = cursor.fetchone()[0]
    if count_user == 0:
        # 普通用户 user /123456
        cursor.execute("INSERT INTO user(username,password,role) VALUES (?,?,?)", ("user","123456","user"))
        # 管理员 admin /123456
        cursor.execute("INSERT INTO user(username,password,role) VALUES (?,?,?)", ("admin","123456","admin"))
    conn.commit()
    conn.close()

# 获取数据库连接
def get_db_conn():
    conn = sqlite3.connect("parking.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# ===================== 登录相关接口 =====================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    conn = sqlite3.connect("parking.db")
    conn.execute("PRAGMA foreign_keys = ON;") # 开启外键
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # 根据用户名查询用户
    cur.execute("SELECT * FROM user WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()
    # 校验用户名和明文密码
    if user and user["password"] == password:
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        return {"code":200,"msg":"success","role":user["role"]}
    else:
        return {"code":400,"msg":"Username or password error"}
# 获取当前登录用户信息
@app.route('/api/get-current-user', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({"code":200,"username":session["username"],"user_id":session["user_id"],"role":session["role"]})

# 退出登录接口
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"code":200,"msg":"Logout success"})

# 管理员：查询系统全部预约记录
@app.route('/api/all-reservations', methods=['GET'])
@login_required
def get_all_reservations():
    conn = get_db_conn()
    sql = '''
    SELECT r.*, s.location, u.username
    FROM reservations r
    LEFT JOIN spaces s ON r.space_id = s.id
    LEFT JOIN user u ON r.user_id = u.id
    '''
    rows = conn.execute(sql).fetchall()
    data = [dict(row) for row in rows]
    conn.close()
    return jsonify({"code":200,"data":data})

# ===================== 车位接口 =====================
# 获取全部车位
@app.route('/api/spaces', methods=['GET'])
@login_required
def get_spaces():
    conn = get_db_conn()
    rows = conn.execute("SELECT * FROM spaces").fetchall()
    data = [dict(row) for row in rows]
    conn.close()
    return jsonify({"code":200,"data":data})

# 管理员更新车位状态
@app.route('/api/space/update', methods=['POST'])
@login_required
def update_space():
    data = request.get_json()
    space_id = data.get("space_id")
    status = data.get("status")
    conn = get_db_conn()
    conn.execute("UPDATE spaces SET status=? WHERE id=?", (status, space_id))
    conn.commit()
    conn.close()
    return jsonify({"code":200,"msg":"Updated successfully"})

# ===================== 预约相关接口 =====================
# 提交预约
@app.route('/api/reserve', methods=['POST'])
@login_required
def reserve_space():
    data = request.get_json()
    user_id = data.get("user_id")
    space_id = data.get("space_id")
    start_time = data.get("start_time")
    conn = get_db_conn()
    # ============【校验该用户是否已有生效预约（已预约/占用都拦截）】============
    cur = conn.cursor()
    cur.execute('''
        SELECT r.* FROM reservations r
        LEFT JOIN spaces s ON r.space_id = s.id
        WHERE r.user_id = ? AND s.status IN (1,2)
    ''', (user_id,))
    exist = cur.fetchone()
    if exist:
        conn.close()
        return jsonify({"code":400,"msg":"You already have an active reservation. Cannot reserve another parking space."}),400
    # =================================================================
    # 判断车位是否空闲
    space = conn.execute("SELECT * FROM spaces WHERE id=?",(space_id,)).fetchone()
    if space is None or space["status"] !=0:
        conn.close()
        return jsonify({"code":400,"msg":"Parking space is unavailable"}),400
    # 新增预约记录，修改车位状态为已预约2
    conn.execute("INSERT INTO reservations(space_id,user_id,start_time) VALUES (?,?,?)",(space_id,user_id,start_time))
    conn.execute("UPDATE spaces SET status=2, start_time=? WHERE id=?",(start_time,space_id))
    conn.commit()
    conn.close()
    return jsonify({"code":200,"msg":"Reservation submitted successfully"})

# 取消预约
@app.route('/api/cancel-reserve', methods=['POST'])
@login_required
def cancel_reserve():
    data = request.get_json()
    user_id = data.get("user_id")
    space_id = data.get("space_id")
    conn = get_db_conn()
    conn.execute("DELETE FROM reservations WHERE space_id=? AND user_id=?",(space_id,user_id))
    conn.execute("UPDATE spaces SET status=0, start_time=null WHERE id=?",(space_id,))
    conn.commit()
    conn.close()
    return jsonify({"code":200,"msg":"Reservation cancelled successfully"})

# 查询用户预约记录
@app.route('/api/reservations', methods=['GET'])
@login_required
def get_reservations():
    user_id = request.args.get("user_id")
    conn = get_db_conn()
    sql = '''
    SELECT r.*, s.location
    FROM reservations r
    LEFT JOIN spaces s ON r.space_id = s.id
    WHERE r.user_id = ?
    '''
    rows = conn.execute(sql,(user_id,)).fetchall()
    data = [dict(row) for row in rows]
    conn.close()
    return jsonify({"code":200,"data":data})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
