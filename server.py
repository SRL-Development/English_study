#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
英语全能学习台 —— 统一后端（账号体系 + 云端进度 + 后台管理 + 声学评测 + AI 对话）
================================================================================
本文件取代原先的 assess-proxy.py，把「账号 / 数据同步 / 后台」与「讯飞评测 / AI 对话」
合并到同一个 Flask 进程，便于在宝塔等服务器上「一个服务、一个反代」部署。

功能一览：
  1) 账号：/api/register（手机号或邮箱 + 密码）、/api/login、/api/logout、/api/me
  2) 云端进度：/api/data  GET 取回该用户进度、PUT 保存（存 SQLite，跨设备同步）
  3) 后台：/api/admin/login（独立管理员密码）、/api/admin/users（注册用户列表+学习统计）
  4) 声学评测：/assess（讯飞 ISE，密钥只在后端）
  5) AI 口语陪练：/chat（OpenAI 兼容接口流式 SSE，默认 DeepSeek）
  6) 静态托管：/ 返回 english-learning.html（或 index.html）、/admin 返回 admin.html
  7) 邮件通知：/api/register 注册成功后，向用户邮箱发送欢迎/激活邮件（阿里云邮箱 SMTP）
  8) 邮箱激活：/api/verify-email 点击邮件链接标记邮箱已验证

数据库：SQLite 文件 app.db（随服务自动创建；可通过 APP_DATA_DIR / APP_DB_PATH 指定）。

环境变量（在宝塔启动脚本或 /etc/profile.d/ 中导出）：
  ADMIN_PASSWORD  后台管理员密码（必填；未配置时后台登录接口禁用）
  IFly_APP_ID / IFly_API_KEY / IFly_API_SECRET   讯飞语音评测密钥
  LLM_API_KEY / LLM_BASE_URL / LLM_MODEL          AI 对话密钥（默认 DeepSeek）
  MAIL_SMTP_HOST / MAIL_SMTP_PORT / MAIL_USERNAME / MAIL_PASSWORD / MAIL_FROM_NAME
                                                  阿里云邮箱 SMTP 发信（注册通知邮件）
  SITE_BASE_URL   站点对外地址，用于拼接邮箱激活链接（如 https://englearner.cn）
  MAIL_SECRET     激活链接签名密钥（可选，默认复用 ADMIN_PASSWORD）

运行：
  pip install flask requests websocket-client
  python server.py            # 监听 0.0.0.0:5000
宝塔：
  网站 -> 反向代理，目标 http://127.0.0.1:5000；或把整站反代到该端口（推荐整站反代，
  这样 /、/admin、/api、/assess、/chat 全部走同源，无需跨域）。
"""

import os
import re
import json
import sqlite3
import secrets
import datetime
import tempfile
import subprocess
import threading
import base64
import hashlib
import hmac
import html
import smtplib
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote, urlparse

import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, jsonify, Response, abort, send_file,
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"), override=False)

DATA_DIR = os.path.abspath(os.environ.get("APP_DATA_DIR", "").strip() or BASE)
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.path.abspath(
    os.environ.get("APP_DB_PATH", "").strip() or os.path.join(DATA_DIR, "app.db")
)
os.makedirs(os.path.dirname(DB), exist_ok=True)
HTML = os.path.join(BASE, "english-learning.html")
HTML_FALLBACK = os.path.join(BASE, "index.html")
ADMIN_HTML = os.path.join(BASE, "admin.html")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
EMAIL_SIGNING_SECRET = os.environ.get("MAIL_SECRET", "").strip() or ADMIN_PASSWORD
WX_APP_ID = os.environ.get("WX_APP_ID", "")
WX_APP_SECRET = os.environ.get("WX_APP_SECRET", "")
TOKEN_TTL = 60 * 60 * 24 * 30  # 用户 token 有效期 30 天
MAX_PROGRESS_BYTES = 1024 * 1024
ALLOWED_ASSESS_CATEGORIES = {"read_word", "read_sentence", "read_chapter"}
try:
    APP_UTC_OFFSET_HOURS = int(os.environ.get("APP_UTC_OFFSET_HOURS", "8"))
except ValueError:
    APP_UTC_OFFSET_HOURS = 8

# 网站与接口默认同源，不需要 CORS。仅在确有独立前端域名时配置逗号分隔白名单。
CORS_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
}

# 邮件服务（阿里云邮箱 SMTP 发信）
# 阿里云「企业邮箱」SMTP：smtp.qiye.aliyun.com（端口 465，SSL）
# 阿里云「个人邮箱」SMTP：smtp.aliyun.com（端口 465，SSL，个人邮已逐步停服，建议用企业邮）
# MAIL_PASSWORD 是邮箱「客户端授权码」，不是网页登录密码（在邮箱设置里开启 SMTP 后获取）
MAIL_SMTP_HOST = os.environ.get("MAIL_SMTP_HOST", "smtp.qiye.aliyun.com")
try:
    MAIL_SMTP_PORT = int(os.environ.get("MAIL_SMTP_PORT", "465"))
except ValueError:
    MAIL_SMTP_PORT = 465
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")   # 发件邮箱，如 noreply@englearner.cn
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")   # 邮箱客户端授权码
MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "英语学习台")
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "")   # 站点对外地址，如 https://englearner.cn

# 语音合成缓存目录（TTS，给小程序提供音频 URL，替代浏览器 TTS）
TTS_CACHE = os.path.abspath(
    os.environ.get("TTS_CACHE_DIR", "").strip() or os.path.join(DATA_DIR, "tts_cache")
)
os.makedirs(TTS_CACHE, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


# ----------------------------- 数据库 -----------------------------
def db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    conn = db()
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE,
            email TEXT UNIQUE,
            nickname TEXT,
            password_hash TEXT,
            created_at TEXT,
            last_login TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS user_data(
            user_id INTEGER PRIMARY KEY,
            data TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS tokens(
            token TEXT PRIMARY KEY,
            user_id INTEGER,
            expires_at TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS admin_tokens(
            token TEXT PRIMARY KEY,
            expires_at TEXT)"""
    )
    # 兼容旧库：微信登录所需的 openid 列（可为空、唯一）
    try:
        c.execute("ALTER TABLE users ADD COLUMN openid TEXT")
    except Exception:
        pass
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_openid ON users(openid)")
    except Exception:
        pass
    # 兼容旧库：邮箱是否已验证（注册后发激活邮件，点链接标记）
    try:
        c.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()
    conn.close()


init_db()


def now_iso():
    return datetime.datetime.utcnow().isoformat()


def local_today():
    offset = max(-23, min(23, APP_UTC_OFFSET_HOURS))
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=offset)).date()


def was_active_today(value):
    if not value:
        return False
    try:
        stamp = datetime.datetime.fromisoformat(value)
        offset = max(-23, min(23, APP_UTC_OFFSET_HOURS))
        return (stamp + datetime.timedelta(hours=offset)).date() == local_today()
    except (TypeError, ValueError):
        return False


def text_field(data, name, *, lower=False):
    value = data.get(name, "")
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value.lower() if lower else value


def make_token(user_id):
    tok = secrets.token_hex(32)
    exp = (datetime.datetime.utcnow() + datetime.timedelta(seconds=TOKEN_TTL)).isoformat()
    conn = db()
    conn.execute("DELETE FROM tokens WHERE expires_at < ?", (now_iso(),))
    conn.execute(
        "INSERT INTO tokens(token,user_id,expires_at) VALUES(?,?,?)",
        (tok, user_id, exp),
    )
    conn.commit()
    conn.close()
    return tok


def make_admin_token():
    tok = secrets.token_hex(32)
    exp = (datetime.datetime.utcnow() + datetime.timedelta(hours=12)).isoformat()
    conn = db()
    conn.execute("DELETE FROM admin_tokens WHERE expires_at < ?", (now_iso(),))
    conn.execute(
        "INSERT INTO admin_tokens(token,expires_at) VALUES(?,?)", (tok, exp)
    )
    conn.commit()
    conn.close()
    return tok


def auth_user():
    ah = request.headers.get("Authorization", "")
    if not ah.startswith("Bearer "):
        return None
    tok = ah[7:].strip()
    conn = db()
    row = conn.execute(
        "SELECT t.user_id,t.expires_at,u.id,u.phone,u.email,u.nickname "
        "FROM tokens t JOIN users u ON u.id=t.user_id WHERE t.token=?",
        (tok,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    if datetime.datetime.fromisoformat(row["expires_at"]) < datetime.datetime.utcnow():
        conn = db()
        conn.execute("DELETE FROM tokens WHERE token=?", (tok,))
        conn.commit()
        conn.close()
        return None
    return row


def auth_admin():
    ah = request.headers.get("Authorization", "")
    if not ah.startswith("Bearer "):
        return False
    tok = ah[7:].strip()
    conn = db()
    row = conn.execute(
        "SELECT expires_at FROM admin_tokens WHERE token=?", (tok,)
    ).fetchone()
    conn.close()
    if not row:
        return False
    if datetime.datetime.fromisoformat(row["expires_at"]) < datetime.datetime.utcnow():
        conn = db()
        conn.execute("DELETE FROM admin_tokens WHERE token=?", (tok,))
        conn.commit()
        conn.close()
        return False
    return True


def calc_streak(study):
    s = 0
    cur = local_today()
    if not study.get(cur.isoformat()):
        cur = cur - datetime.timedelta(days=1)
    while study.get(cur.isoformat()):
        s += 1
        cur = cur - datetime.timedelta(days=1)
    return s


# ----------------------------- HTTP 安全与 CORS -----------------------------
@app.after_request
def _security_headers(resp):
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and origin in CORS_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), geolocation=()"
    if request.path.startswith("/api/") and request.path != "/api/tts":
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "请求内容过大（最大 8 MB）"}), 413


def valid_site_base(value):
    """仅允许 http(s) 站点地址进入邮件链接和页面 href。"""
    try:
        if not isinstance(value, str) or re.search(r"[\s\"'<>]", value):
            return ""
        parsed = urlparse(value)
        return value.rstrip("/") if parsed.scheme in ("http", "https") and parsed.netloc else ""
    except (TypeError, ValueError):
        return ""


# ----------------------------- 邮件通知（阿里云邮箱 SMTP） -----------------------------
def make_email_sig(uid, email):
    """生成邮箱激活链接签名（HMAC），防止链接被篡改。"""
    if not EMAIL_SIGNING_SECRET:
        raise RuntimeError("未配置 MAIL_SECRET 或 ADMIN_PASSWORD")
    raw = "%d|%s" % (uid, email)
    return hmac.new(
        EMAIL_SIGNING_SECRET.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_email_sig(uid, email, sig):
    if not EMAIL_SIGNING_SECRET:
        return False
    return hmac.compare_digest(make_email_sig(uid, email), sig or "")


def send_email(to_addr, subject, html_body, text_body=None):
    """通过阿里云邮箱 SMTP 发送邮件；未配置或发送失败仅记录日志，不影响主流程。"""
    if not (MAIL_USERNAME and MAIL_PASSWORD):
        app.logger.warning("邮件服务未配置，跳过发送 -> %s", to_addr)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = "%s <%s>" % (MAIL_FROM_NAME, MAIL_USERNAME)
        msg["To"] = to_addr
        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP_SSL(MAIL_SMTP_HOST, MAIL_SMTP_PORT, timeout=15) as server:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_USERNAME, [to_addr], msg.as_string())
        app.logger.info("邮件已发送至 %s", to_addr)
        return True
    except Exception as e:
        app.logger.error("邮件发送失败 %s: %s", to_addr, e)
        return False


WELCOME_MAIL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>欢迎加入英语学习台</title>
<style>
  body{margin:0;background:#f4f6fb;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;}
  .card{max-width:480px;margin:32px auto;background:#fff;border-radius:14px;padding:32px 28px;box-shadow:0 6px 24px rgba(30,64,175,.08);}
  h1{color:#1e40af;font-size:22px;margin:0 0 16px;}
  p{color:#374151;line-height:1.7;font-size:15px;margin:10px 0;}
  .btn{display:inline-block;margin:18px 0;padding:12px 28px;background:#1e40af;color:#fff;border-radius:8px;text-decoration:none;font-size:15px;}
  .tip{font-size:13px;color:#6b7280;background:#f3f4f6;padding:12px;border-radius:8px;word-break:break-all;}
  .foot{font-size:12px;color:#9ca3af;margin-top:20px;}
</style>
</head>
<body>
  <div class="card">
    <h1>欢迎加入英语学习台</h1>
    <p>亲爱的 __NICKNAME__，您好！</p>
    <p>感谢您注册「英语学习台」。您的账号已创建成功，我们为您准备了日常、商务、工程、IT、医疗、金融等各行各业的英语学习资源。</p>
    <p>请点击下方按钮激活您的邮箱，以解锁云端的全部学习进度与个性化推荐：</p>
    <p><a class="btn" href="__VERIFY_URL__">激活我的邮箱</a></p>
    <p class="tip">如果按钮无法点击，请复制以下链接到浏览器打开：<br>__VERIFY_URL__</p>
    <p class="foot">本邮件由系统自动发送，请勿直接回复。若非本人操作，请忽略此邮件。</p>
  </div>
</body>
</html>"""


VERIFY_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
  body{margin:0;background:#f4f6fb;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;}
  .card{max-width:420px;margin:60px auto;background:#fff;border-radius:14px;padding:36px 28px;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.08);}
  .icon{font-size:48px;}
  h1{color:__COLOR__;font-size:22px;margin:12px 0;}
  p{color:#374151;line-height:1.7;font-size:15px;}
  .btn{display:inline-block;margin-top:20px;padding:12px 28px;background:#1e40af;color:#fff;border-radius:8px;text-decoration:none;font-size:15px;}
</style>
</head>
<body>
  <div class="card">
    <div class="icon">__ICON__</div>
    <h1>__TITLE__</h1>
    <p>__MSG__</p>
    <a class="btn" href="__SITE__">前往学习平台</a>
  </div>
</body>
</html>"""


def send_welcome_email(to_addr, nickname, verify_url):
    subject = "欢迎加入英语学习台 — 请激活您的邮箱"
    body = WELCOME_MAIL
    body = body.replace("__NICKNAME__", html.escape(nickname or "学习者"))
    body = body.replace("__VERIFY_URL__", html.escape(verify_url, quote=True))
    body = body.replace("__SITE__", SITE_BASE_URL or "英语学习台")
    send_email(to_addr, subject, body)


def verify_html(ok, msg):
    site = valid_site_base(SITE_BASE_URL) or "/"
    tpl = VERIFY_PAGE
    tpl = tpl.replace("__TITLE__", "邮箱激活成功" if ok else "邮箱激活失败")
    tpl = tpl.replace("__MSG__", html.escape(msg))
    tpl = tpl.replace("__SITE__", site)
    tpl = tpl.replace("__COLOR__", "#16a34a" if ok else "#dc2626")
    tpl = tpl.replace("__ICON__", "✅" if ok else "⚠️")
    return tpl


# ----------------------------- 账号接口 -----------------------------
@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "请求格式错误"}), 400
    phone = text_field(data, "phone")
    email = text_field(data, "email", lower=True)
    password = data.get("password") or ""
    nickname = text_field(data, "nickname")

    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        return jsonify({"error": "密码须为 8-128 位"}), 400
    if len(nickname) > 40:
        return jsonify({"error": "昵称不能超过 40 个字符"}), 400
    if not phone and not email:
        return jsonify({"error": "手机号与邮箱至少填写一项"}), 400
    if phone and not re.fullmatch(r"\d{6,20}", phone):
        return jsonify({"error": "手机号格式不正确（6-20 位数字）"}), 400
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "邮箱格式不正确"}), 400

    ph = phone or None
    em = email or None
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO users(phone,email,nickname,password_hash,created_at,last_login) "
            "VALUES(?,?,?,?,?,?)",
            (
                ph,
                em,
                nickname or None,
                generate_password_hash(password),
                now_iso(),
                now_iso(),
            ),
        )
        uid = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "该手机号或邮箱已被注册"}), 409
    conn.close()

    tok = make_token(uid)

    # 邮箱注册 → 异步发送欢迎/激活邮件（不阻塞注册响应）
    email_sent = False
    site_base = valid_site_base(SITE_BASE_URL)
    if em and site_base and EMAIL_SIGNING_SECRET:
        sig = make_email_sig(uid, em)
        verify_url = "%s/api/verify-email?uid=%d&sig=%s" % (site_base, uid, sig)
        threading.Thread(
            target=send_welcome_email, args=(em, nickname or "学习者", verify_url),
            daemon=True,
        ).start()
        email_sent = bool(MAIL_USERNAME and MAIL_PASSWORD)

    return jsonify(
        {
            "token": tok,
            "email_sent": email_sent,
            "user": {"id": uid, "phone": ph, "email": em, "nickname": nickname},
        }
    )


@app.route("/api/verify-email")
def api_verify_email():
    """邮箱激活链接：用户点击邮件中的链接后，标记邮箱已验证并展示结果页。"""
    try:
        uid = int(request.args.get("uid", ""))
        sig = request.args.get("sig", "")
    except (ValueError, TypeError):
        return verify_html(False, "链接参数无效，请重新注册获取邮件。")
    conn = db()
    u = conn.execute("SELECT id,email FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    if not u:
        return verify_html(False, "账号不存在，请确认链接是否正确。")
    if not verify_email_sig(uid, u["email"], sig):
        return verify_html(False, "验证链接已失效或不合法。")
    conn = db()
    conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    return verify_html(True, "您的邮箱已成功激活，现在可以畅享全部云端学习功能！")


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "请求格式错误"}), 400
    ident = text_field(data, "identifier")
    if "@" in ident:
        ident = ident.lower()
    password = data.get("password") or ""
    if not ident or not isinstance(password, str) or not password:
        return jsonify({"error": "请输入账号与密码"}), 400
    conn = db()
    u = conn.execute(
        "SELECT * FROM users WHERE phone=? OR email=?", (ident, ident)
    ).fetchone()
    conn.close()
    if not u or not u["password_hash"] or not check_password_hash(u["password_hash"], password):
        return jsonify({"error": "账号或密码错误"}), 401
    conn = db()
    conn.execute("UPDATE users SET last_login=? WHERE id=?", (now_iso(), u["id"]))
    conn.commit()
    conn.close()
    tok = make_token(u["id"])
    return jsonify(
        {
            "token": tok,
            "user": {
                "id": u["id"],
                "phone": u["phone"],
                "email": u["email"],
                "nickname": u["nickname"],
            },
        }
    )


@app.route("/api/logout", methods=["POST"])
def api_logout():
    ah = request.headers.get("Authorization", "")
    if ah.startswith("Bearer "):
        tok = ah[7:].strip()
        conn = db()
        conn.execute("DELETE FROM tokens WHERE token=?", (tok,))
        conn.commit()
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/me", methods=["GET"])
def api_me():
    u = auth_user()
    if not u:
        return jsonify({"error": "未登录"}), 401
    return jsonify(
        {
            "user": {
                "id": u["id"],
                "phone": u["phone"],
                "email": u["email"],
                "nickname": u["nickname"],
            }
        }
    )


# ----------------------------- 云端进度接口 -----------------------------
@app.route("/api/data", methods=["GET"])
def api_data_get():
    u = auth_user()
    if not u:
        return jsonify({"error": "未登录"}), 401
    conn = db()
    row = conn.execute(
        "SELECT data FROM user_data WHERE user_id=?", (u["user_id"],)
    ).fetchone()
    conn.close()
    data = row["data"] if row and row["data"] else "{}"
    return jsonify({"data": data})


@app.route("/api/data", methods=["PUT"])
def api_data_put():
    u = auth_user()
    if not u:
        return jsonify({"error": "未登录"}), 401
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "请求格式错误"}), 400
    data = body.get("data")
    if data is None:
        # 兼容直接传对象本体
        data = request.get_data(as_text=True)
        try:
            json.loads(data)
        except Exception:
            return jsonify({"error": "数据格式错误"}), 400
    else:
        if not isinstance(data, str):
            data = json.dumps(data, ensure_ascii=False)
    if len(data.encode("utf-8")) > MAX_PROGRESS_BYTES:
        return jsonify({"error": "学习进度数据不能超过 1 MB"}), 413
    try:
        parsed = json.loads(data)
    except (TypeError, json.JSONDecodeError):
        return jsonify({"error": "数据格式错误"}), 400
    if not isinstance(parsed, dict):
        return jsonify({"error": "学习进度必须是 JSON 对象"}), 400
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO user_data(user_id,data) VALUES(?,?)",
        (u["user_id"], data),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ----------------------------- 后台接口 -----------------------------
@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    if not ADMIN_PASSWORD:
        return jsonify({"error": "后台未启用：请先配置 ADMIN_PASSWORD"}), 503
    data = request.get_json(silent=True) or {}
    pw = text_field(data, "password") if isinstance(data, dict) else ""
    if not secrets.compare_digest(pw, ADMIN_PASSWORD):
        return jsonify({"error": "管理员密码错误"}), 401
    return jsonify({"token": make_admin_token()})


@app.route("/api/admin/users", methods=["GET"])
def api_admin_users():
    if not auth_admin():
        return jsonify({"error": "未授权"}), 401
    conn = db()
    rows = conn.execute(
        "SELECT u.id,u.phone,u.email,u.nickname,u.created_at,u.last_login,"
        "u.email_verified,d.data FROM users u "
        "LEFT JOIN user_data d ON d.user_id=u.id ORDER BY u.id DESC"
    ).fetchall()
    out = []
    for u in rows:
        data = {}
        if u["data"]:
            try:
                data = json.loads(u["data"])
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        study = data.get("studyDays", {}) or {}
        mastered = data.get("mastered", {}) or {}
        if not isinstance(study, dict):
            study = {}
        if not isinstance(mastered, dict):
            mastered = {}
        out.append(
            {
                "id": u["id"],
                "phone": u["phone"] or "",
                "email": u["email"] or "",
                "nickname": u["nickname"] or "",
                "verified": bool(u["email_verified"]),
                "created_at": (u["created_at"] or "")[:19].replace("T", " "),
                "last_login": (u["last_login"] or "")[:19].replace("T", " "),
                "active_today": was_active_today(u["last_login"]),
                "days": sum(
                    1 for value in study.values()
                    if isinstance(value, (int, float)) and value > 0
                ),
                "mastered": len(mastered),
                "streak": calc_streak(study),
            }
        )
    conn.close()
    return jsonify({"users": out})


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    ah = request.headers.get("Authorization", "")
    if ah.startswith("Bearer "):
        conn = db()
        conn.execute("DELETE FROM admin_tokens WHERE token=?", (ah[7:].strip(),))
        conn.commit()
        conn.close()
    return jsonify({"ok": True})


# ----------------------------- 静态托管 -----------------------------
@app.route("/")
def index():
    p = HTML if os.path.exists(HTML) else HTML_FALLBACK
    if not os.path.exists(p):
        abort(404)
    return send_file(p)


@app.route("/admin", methods=["GET"])
@app.route("/admin.html", methods=["GET"])
def admin_page():
    if not os.path.exists(ADMIN_HTML):
        abort(404)
    return send_file(ADMIN_HTML)


@app.route("/api/health", methods=["GET"])
def api_health():
    """供宝塔、反向代理或监控做无副作用的存活检查。"""
    try:
        conn = db()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except sqlite3.Error:
        return jsonify({"status": "error", "database": "unavailable"}), 503
    return jsonify({"status": "ok", "database": "ok"})


# =====================================================================
# 以下为原 assess-proxy.py 的声学评测 / AI 对话 路由（密钥只在后端）
# =====================================================================
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

LEVEL_NAMES = {0: "零基础", 1: "初中", 2: "高中", 3: "大学"}

SYSTEM_PROMPT = """你是一位耐心、鼓励型的英语外教，正在和一位中国英语学习者用英语做口语对话练习。
用户当前英语基础：{level}（0=零基础,1=初中,2=高中,3=大学）。
当前练习场景：{scene}。
请严格遵守：
1. 主要用英语回复，句子长度与词汇难度匹配用户的基础等级（等级越低越用简单短句）。
2. 每次回复控制在 3-4 句英文以内，末尾用一句中文给出「纠错与点拨」（若用户表达有语法/用词错误请明确指出并改正，若无错误则给予鼓励与方法提示）。
3. 适当用提问引导用户继续用英语表达，保持对话自然。
4. 不要长篇大论，聚焦口语互动。"""

APP_ID = os.environ.get("IFly_APP_ID", "")
API_KEY = os.environ.get("IFly_API_KEY", "")
API_SECRET = os.environ.get("IFly_API_SECRET", "")
HOST = "ise-api.xfyun.cn"
URI = "/v2/openapi"


def build_auth_url():
    now = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    sig_origin = "host: " + HOST + "\n"
    sig_origin += "date: " + now + "\n"
    sig_origin += "GET " + URI + " HTTP/1.1"
    sig_sha = hmac.new(
        API_SECRET.encode("utf-8"), sig_origin.encode("utf-8"), hashlib.sha1
    ).digest()
    sig_b64 = base64.b64encode(sig_sha).decode("utf-8")
    auth_origin = (
        'api_key="%s", algorithm="hmac-sha1", '
        'headers="host date request-line", signature="%s"'
        % (API_KEY, sig_b64)
    )
    auth_b64 = base64.b64encode(auth_origin.encode("utf-8")).decode("utf-8")
    return "wss://%s%s?authorization=%s&date=%s&host=%s" % (
        HOST,
        URI,
        quote(auth_b64, safe=""),
        quote(now, safe=""),
        HOST,
    )


def to_pcm16k_mono(src_path):
    pcm = src_path + ".pcm"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", "-f", "s16le", pcm],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise RuntimeError("服务器未安装 ffmpeg，无法转码音频（请先安装 ffmpeg）")
    except subprocess.CalledProcessError as e:
        raise RuntimeError("音频转码失败，可能不是有效音频：" + str(e))
    return pcm


def assess_once(audio_path, text, category="read_sentence"):
    import websocket

    pcm = to_pcm16k_mono(audio_path)
    try:
        with open(pcm, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")
    finally:
        try:
            os.remove(pcm)
        except OSError:
            pass

    ws_url = build_auth_url()
    result = {}
    ready = threading.Event()

    def on_open(ws):
        data = {
            "common": {"app_id": APP_ID},
            "business": {
                "language": "en_us",
                "category": category,
                "evalue": text,
                "rst": "entirety",
                "sub": "ise",
                "aue": "raw",
                "ent": "en_word",
            },
            "data": {
                "status": 2,
                "audio": audio_b64,
                "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
            },
        }
        ws.send(json.dumps(data))

    def on_message(ws, message):
        try:
            d = json.loads(message)
            if d.get("code") != 0:
                result["error"] = d.get("message", "讯飞错误码 " + str(d.get("code")))
                return
            payload = d.get("data", {})
            xml_str = payload.get("data", "")
            try:
                xml_str = base64.b64decode(xml_str).decode("utf-8")
            except Exception:
                pass
            result["xml"] = xml_str
        except Exception as e:
            result["error"] = str(e)
        finally:
            ready.set()
            try:
                ws.close()
            except Exception:
                pass

    def on_error(ws, err):
        result["error"] = str(err)
        ready.set()

    def on_close(ws, *a):
        ready.set()

    ws = websocket.WebSocketApp(
        ws_url, on_open=on_open, on_message=on_message,
        on_error=on_error, on_close=on_close,
    )
    t = threading.Thread(target=ws.run_forever, daemon=True)
    t.start()
    ready.wait(timeout=30)

    if "xml" in result:
        return parse_ise_xml(result["xml"])
    if "error" in result:
        raise RuntimeError(result["error"])
    raise RuntimeError("评测超时或未返回结果")


def parse_ise_xml(xml_str):
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise RuntimeError("评测结果解析失败：" + str(e))

    overall = None
    for tag in ("read_sentence", "sentence", "rec_paper"):
        el = root.find(".//" + tag)
        score_value = el.get("total_score") if el is not None else None
        if score_value:
            try:
                overall = float(score_value)
                break
            except ValueError:
                pass

    words = []
    for w in root.iter("word"):
        score = w.get("total_score")
        if score is None:
            continue
        try:
            sc = float(score)
        except ValueError:
            continue
        word_text = (w.text or "").strip()
        if not word_text:
            chars = [c.get("content", "") for c in w.iter("char") if c.get("content")]
            word_text = "".join(chars)
        if word_text:
            words.append({"word": word_text, "score": sc})

    if overall is None and words:
        overall = sum(w["score"] for w in words) / len(words)
    return {"overall": overall or 0.0, "words": words}


@app.route("/assess", methods=["POST"])
def assess():
    if not (APP_ID and API_KEY and API_SECRET):
        return jsonify({"error": "服务端未配置讯飞密钥"}), 500
    f = request.files.get("audio")
    text = request.form.get("text", "")
    category = request.form.get("category", "read_sentence")
    if not f or not text:
        return jsonify({"error": "缺少 audio 或 text"}), 400
    if len(text) > 1000:
        return jsonify({"error": "评测文本不能超过 1000 个字符"}), 400
    if category not in ALLOWED_ASSESS_CATEGORIES:
        return jsonify({"error": "不支持的评测类型"}), 400
    fd, path = tempfile.mkstemp(suffix=".webm")
    os.close(fd)
    f.save(path)
    try:
        data = assess_once(path, text, category)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return ("", 204)
    if not LLM_API_KEY:
        return jsonify({"error": "服务端未配置 LLM_API_KEY"}), 500
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "请求格式错误"}), 400
    raw_message = data.get("message") or ""
    if not isinstance(raw_message, str):
        return jsonify({"error": "message 格式错误"}), 400
    message = raw_message.strip()
    history = data.get("history") or []
    scene = str(data.get("scene") or "日常交流")[:40]
    try:
        level = int(data.get("level", 1))
    except (TypeError, ValueError):
        level = 1
    if not message:
        return jsonify({"error": "缺少 message"}), 400
    if len(message) > 2000:
        return jsonify({"error": "消息不能超过 2000 个字符"}), 400
    if not isinstance(history, list):
        return jsonify({"error": "history 格式错误"}), 400

    sys_prompt = SYSTEM_PROMPT.format(level=LEVEL_NAMES.get(level, "初中"), scene=scene)
    messages = [{"role": "system", "content": sys_prompt}]
    for h in history[-10:]:
        if not isinstance(h, dict):
            continue
        role = h.get("role")
        content = h.get("content", "")
        if role in ("user", "assistant") and isinstance(content, str) and content:
            messages.append({"role": role, "content": content[:2000]})
    messages.append({"role": "user", "content": message})

    def gen():
        try:
            r = requests.post(
                LLM_BASE_URL.rstrip("/") + "/chat/completions",
                headers={
                    "Authorization": "Bearer " + LLM_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"model": LLM_MODEL, "messages": messages, "stream": True},
                stream=True,
                timeout=60,
            )
            r.raise_for_status()
            for raw in r.iter_lines(decode_unicode=False):
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore")
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break
                try:
                    obj = json.loads(payload)
                    delta = (
                        obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    )
                except Exception:
                    continue
                if delta:
                    yield "data: " + json.dumps({"delta": delta}, ensure_ascii=False) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps({"error": str(e)}, ensure_ascii=False) + "\n\n"

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ----------------------------- 微信小程序接口 -----------------------------
@app.route("/api/wxlogin", methods=["POST"])
def api_wxlogin():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "请求格式错误"}), 400
    code = text_field(data, "code")
    if not code:
        return jsonify({"error": "缺少 code"}), 400
    if not (WX_APP_ID and WX_APP_SECRET):
        return jsonify({"error": "服务端未配置 WX_APP_ID / WX_APP_SECRET"}), 500
    try:
        r = requests.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": WX_APP_ID,
                "secret": WX_APP_SECRET,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        r.raise_for_status()
        j = r.json()
    except Exception as e:
        return jsonify({"error": "微信登录接口请求失败：" + str(e)}), 502
    if j.get("errcode"):
        return jsonify({"error": "微信登录失败：" + str(j.get("errmsg", ""))}), 502
    openid = j.get("openid")
    if not openid:
        return jsonify({"error": "未获取到 openid"}), 502
    conn = db()
    u = conn.execute("SELECT * FROM users WHERE openid=?", (openid,)).fetchone()
    if not u:
        cur = conn.execute(
            "INSERT INTO users(openid,nickname,created_at,last_login) VALUES(?,?,?,?)",
            (openid, "微信用户", now_iso(), now_iso()),
        )
        uid = cur.lastrowid
        conn.commit()
        u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    else:
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now_iso(), u["id"]))
        conn.commit()
    conn.close()
    tok = make_token(u["id"])
    return jsonify(
        {
            "token": tok,
            "user": {
                "id": u["id"],
                "phone": u["phone"],
                "email": u["email"],
                "nickname": u["nickname"],
            },
        }
    )


@app.route("/api/bind", methods=["POST"])
def api_bind():
    u = auth_user()
    if not u:
        return jsonify({"error": "未登录"}), 401
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "请求格式错误"}), 400
    phone = text_field(data, "phone")
    email = text_field(data, "email", lower=True)
    password = data.get("password") or ""
    if password and (not isinstance(password, str) or not 8 <= len(password) <= 128):
        return jsonify({"error": "密码须为 8-128 位"}), 400
    if not phone and not email and not password:
        return jsonify({"error": "请至少填写一项绑定信息"}), 400
    if phone and not re.fullmatch(r"\d{6,20}", phone):
        return jsonify({"error": "手机号格式不正确"}), 400
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "邮箱格式不正确"}), 400
    conn = db()
    if phone:
        ex = conn.execute(
            "SELECT id FROM users WHERE phone=? AND id!=?", (phone, u["user_id"])
        ).fetchone()
        if ex:
            conn.close()
            return jsonify({"error": "该手机号已被其他账号绑定"}), 409
    if email:
        ex = conn.execute(
            "SELECT id FROM users WHERE email=? AND id!=?", (email, u["user_id"])
        ).fetchone()
        if ex:
            conn.close()
            return jsonify({"error": "该邮箱已被其他账号绑定"}), 409
    sets, vals = [], []
    if phone:
        sets.append("phone=?"); vals.append(phone)
    email_changed = bool(email and email != (u["email"] or "").lower())
    if email_changed:
        sets.extend(["email=?", "email_verified=0"]); vals.append(email)
    if password:
        sets.append("password_hash=?"); vals.append(generate_password_hash(password))
    if sets:
        vals.append(u["user_id"])
        conn.execute(
            "UPDATE users SET " + ",".join(sets) + " WHERE id=?", vals
        )
        conn.commit()
    conn.close()

    # 新绑或更换邮箱后发送激活信；结果不阻塞绑定成功。
    email_sent = False
    site_base = valid_site_base(SITE_BASE_URL)
    if email_changed and site_base and EMAIL_SIGNING_SECRET:
        sig = make_email_sig(u["user_id"], email)
        verify_url = "%s/api/verify-email?uid=%d&sig=%s" % (
            site_base, u["user_id"], sig,
        )
        threading.Thread(
            target=send_welcome_email,
            args=(email, u["nickname"] or "学习者", verify_url),
            daemon=True,
        ).start()
        email_sent = bool(MAIL_USERNAME and MAIL_PASSWORD)
    return jsonify({"ok": True, "email_sent": email_sent})


@app.route("/api/tts", methods=["GET", "POST"])
def api_tts():
    if request.method == "GET":
        text = request.args.get("text", "")
        voice = request.args.get("voice", "en-US-AriaNeural")
    else:
        d = request.get_json(silent=True) or {}
        if not isinstance(d, dict):
            return jsonify({"error": "请求格式错误"}), 400
        text = d.get("text", "")
        voice = d.get("voice", "en-US-AriaNeural")
    if not isinstance(text, str) or not isinstance(voice, str):
        return jsonify({"error": "text 或 voice 格式错误"}), 400
    text = text.strip()
    voice = voice.strip()
    if not text:
        return jsonify({"error": "缺少 text"}), 400
    if len(text) > 1000:
        return jsonify({"error": "朗读文本不能超过 1000 个字符"}), 400
    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", voice):
        return jsonify({"error": "语音名称格式不正确"}), 400
    import asyncio

    key = hashlib.md5((voice + "|" + text).encode("utf-8")).hexdigest()
    cache_path = os.path.join(TTS_CACHE, key + ".mp3")
    if not os.path.exists(cache_path):
        tmp_path = None
        try:
            import edge_tts

            fd, tmp_path = tempfile.mkstemp(dir=TTS_CACHE, suffix=".tmp")
            os.close(fd)

            async def _synth():
                comm = edge_tts.Communicate(text, voice)
                with open(tmp_path, "wb") as f:
                    async for chunk in comm.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])

            asyncio.run(_synth())
            if not os.path.getsize(tmp_path):
                raise RuntimeError("语音服务未返回音频数据")
            os.replace(tmp_path, cache_path)
        except ImportError:
            return jsonify({"error": "服务端未安装 edge-tts，请执行 pip install edge-tts"}), 500
        except Exception as e:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            return jsonify({"error": "语音合成失败：" + str(e)}), 500
    return send_file(cache_path, mimetype="audio/mpeg", conditional=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
