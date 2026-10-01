-- SQLite
-- 车位表
CREATE TABLE parking_space (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location TEXT NOT NULL,  -- 车位位置，如"A-01"
    status INTEGER DEFAULT 0  -- 0=空闲，1=占用，2=已预约
);
-- 用户表（明文密码）
CREATE TABLE user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT DEFAULT 'user'
);
-- 预约记录表
CREATE TABLE reservation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,  -- 关联用户表id
    space_id INTEGER,  -- 关联车位表id
    start_time TEXT,  -- 预约时间，如"2024-10-16 10:00"
    FOREIGN KEY (user_id) REFERENCES user(id),
    FOREIGN KEY (space_id) REFERENCES parking_space(id)
);
-- 插入3个车位
INSERT OR IGNORE INTO parking_space (id, location, status) VALUES (1,"A-01",0),(2,"A-02",0),(3,"B-01",0);
-- 预置账号：user /123456 (普通用户) ; admin /123456(管理员)
INSERT OR IGNORE INTO user(username,password,role) VALUES ('user','123456','user');
INSERT OR IGNORE INTO user(username,password,role) VALUES ('admin','123456','admin');
