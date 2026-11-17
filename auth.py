import os, sqlite3, secrets, hashlib, hmac, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/auth",tags=["Authentication and Access Control"])
ADMIN_USERNAME=os.getenv("ADMIN_USERNAME","").strip()
ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD","")
SESSION_SECRET=os.getenv("SESSION_SECRET","")
AUTH_CONFIGURED=bool(ADMIN_USERNAME and ADMIN_PASSWORD and SESSION_SECRET)
COOKIE_NAME="recru_agent_session"
SESSION_HOURS=8
ITERATIONS=310000

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def token_hash(token):
    return hmac.new(SESSION_SECRET.encode(),token.encode(),hashlib.sha256).hexdigest()

def password_hash(password,salt=None):
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,ITERATIONS)
    return salt.hex(),digest.hex()

def verify_password(password,salt_hex,digest_hex):
    try:
        salt=bytes.fromhex(salt_hex)
        _,candidate=password_hash(password,salt)
        return hmac.compare_digest(candidate,digest_hex)
    except (ValueError,TypeError):
        return False

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS app_users(
          id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_salt TEXT NOT NULL,
          password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'recruiter',
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_sessions(
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, token_hash TEXT NOT NULL UNIQUE,
          expires_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_login_attempts(
          id INTEGER PRIMARY KEY, ip_address TEXT NOT NULL, success INTEGER NOT NULL,
          attempted_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events(
          id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT NOT NULL, role TEXT NOT NULL,
          method TEXT NOT NULL, path TEXT NOT NULL, status_code INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        """)
    if AUTH_CONFIGURED:
        with connect() as c:
            exists=c.execute("SELECT id FROM app_users WHERE username=?",(ADMIN_USERNAME,)).fetchone()
            if not exists:
                salt,digest=password_hash(ADMIN_PASSWORD)
                c.execute("INSERT INTO app_users(username,password_salt,password_hash,role,active,created_at,updated_at) VALUES(?,?,?,'admin',1,?,?)",
                  (ADMIN_USERNAME,salt,digest,stamp(),stamp()))
init()

def get_session_user(token):
    if not AUTH_CONFIGURED or not token: return None
    try: hashed=token_hash(token)
    except Exception: return None
    with connect() as c:
        row=c.execute("""SELECT u.id,u.username,u.role,u.active,s.expires_at
          FROM auth_sessions s JOIN app_users u ON u.id=s.user_id
          WHERE s.token_hash=?""",(hashed,)).fetchone()
        if not row or not row["active"] or row["expires_at"]<=stamp():
            if row: c.execute("DELETE FROM auth_sessions WHERE token_hash=?",(hashed,))
            return None
        return dict(row)

def create_session(user_id):
    token=secrets.token_urlsafe(48)
    expiry=(datetime.now(timezone.utc)+timedelta(hours=SESSION_HOURS)).isoformat()
    with connect() as c:
        c.execute("DELETE FROM auth_sessions WHERE expires_at<=?",(stamp(),))
        c.execute("INSERT INTO auth_sessions(user_id,token_hash,expires_at,created_at) VALUES(?,?,?,?)",(user_id,token_hash(token),expiry,stamp()))
    return token

def audit(user,method,path,status):
    if not user: return
    try:
        with connect() as c:
            c.execute("INSERT INTO audit_events(user_id,username,role,method,path,status_code,created_at) VALUES(?,?,?,?,?,?,?)",
              (user.get("id"),user.get("username",""),user.get("role",""),method,path,int(status),stamp()))
    except sqlite3.Error:
        pass

def set_cookie(response,token):
    response.set_cookie(COOKIE_NAME,token,max_age=SESSION_HOURS*3600,httponly=True,secure=os.getenv("AUTH_COOKIE_SECURE","").lower() in ("1","true","yes") or bool(os.getenv("RENDER")),samesite="strict",path="/")

def require_admin(request):
    user=getattr(request.state,"user",None)
    if not user or user.get("role")!="admin":
        raise HTTPException(403,"Administrator access is required.")

class LoginPayload(BaseModel):
    username:str=Field(min_length=1,max_length=100)
    password:str=Field(min_length=1,max_length=256)

class PasswordPayload(BaseModel):
    current_password:str=Field(min_length=1,max_length=256)
    new_password:str=Field(min_length=12,max_length=256)

class UserCreate(BaseModel):
    username:str=Field(min_length=3,max_length=100)
    password:str=Field(min_length=12,max_length=256)
    role:str="recruiter"

class UserUpdate(BaseModel):
    role:str|None=None
    active:bool|None=None

@router.post("/login")
def login(payload:LoginPayload,request:Request,response:Response):
    if not AUTH_CONFIGURED:
        raise HTTPException(503,"Authentication is not configured. Set ADMIN_USERNAME, ADMIN_PASSWORD, and SESSION_SECRET before using Recru Agent.")
    ip=request.client.host if request.client else "unknown"
    cutoff=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
    attempts=0
    with connect() as c:
        attempts=c.execute("SELECT COUNT(*) FROM auth_login_attempts WHERE ip_address=? AND success=0 AND attempted_at>=?",(ip,cutoff)).fetchone()[0]
    if attempts>=5: raise HTTPException(429,"Too many unsuccessful sign-in attempts. Try again in 15 minutes.")
    with connect() as c:
        row=c.execute("SELECT * FROM app_users WHERE username=? AND active=1",(payload.username.strip(),)).fetchone()
    if not row or not verify_password(payload.password,row["password_salt"],row["password_hash"]):
        with connect() as c:
            c.execute("INSERT INTO auth_login_attempts(ip_address,success,attempted_at) VALUES(?,0,?)",(ip,stamp()))
        raise HTTPException(401,"Username or password is incorrect.")
    with connect() as c:
        c.execute("INSERT INTO auth_login_attempts(ip_address,success,attempted_at) VALUES(?,1,?)",(ip,stamp()))
        c.execute("DELETE FROM auth_login_attempts WHERE attempted_at<?",(cutoff,))
    token=create_session(row["id"]); set_cookie(response,token)
    return {"user":{"id":row["id"],"username":row["username"],"role":row["role"]},"expires_in_seconds":SESSION_HOURS*3600}

@router.post("/logout")
def logout(request:Request,response:Response):
    token=request.cookies.get(COOKIE_NAME)
    if token and AUTH_CONFIGURED:
        with connect() as c: c.execute("DELETE FROM auth_sessions WHERE token_hash=?",(token_hash(token),))
    response.delete_cookie(COOKIE_NAME,path="/",httponly=True,secure=os.getenv("AUTH_COOKIE_SECURE","").lower() in ("1","true","yes") or bool(os.getenv("RENDER")),samesite="strict")
    return {"message":"Signed out."}

@router.get("/me")
def me(request:Request):
    user=getattr(request.state,"user",None)
    if not user: raise HTTPException(401,"Sign in is required.")
    return {"user":{"id":user["id"],"username":user["username"],"role":user["role"]}}

@router.post("/password")
def change_password(payload:PasswordPayload,request:Request,response:Response):
    user=getattr(request.state,"user",None)
    if not user: raise HTTPException(401,"Sign in is required.")
    with connect() as c:
        row=c.execute("SELECT * FROM app_users WHERE id=?",(user["id"],)).fetchone()
        if not row or not verify_password(payload.current_password,row["password_salt"],row["password_hash"]):
            raise HTTPException(400,"Current password is incorrect.")
        salt,digest=password_hash(payload.new_password)
        c.execute("UPDATE app_users SET password_salt=?,password_hash=?,updated_at=? WHERE id=?",(salt,digest,stamp(),user["id"]))
        c.execute("DELETE FROM auth_sessions WHERE user_id=?",(user["id"],))
    response.delete_cookie(COOKIE_NAME,path="/",httponly=True,secure=os.getenv("AUTH_COOKIE_SECURE","").lower() in ("1","true","yes") or bool(os.getenv("RENDER")),samesite="strict")
    return {"message":"Password updated. Sign in again with the new password."}

@router.get("/users")
def list_users(request:Request):
    require_admin(request)
    with connect() as c:
        data=c.execute("SELECT id,username,role,active,created_at,updated_at FROM app_users ORDER BY id").fetchall()
    return [dict(x) for x in data]

@router.post("/users")
def create_user(payload:UserCreate,request:Request):
    require_admin(request)
    if payload.role not in ("admin","recruiter","reviewer"): raise HTTPException(400,"Role must be admin, recruiter, or reviewer.")
    username=payload.username.strip()
    if not username or not username.replace("_","").replace("-","").isalnum(): raise HTTPException(400,"Username may contain letters, numbers, underscores, and hyphens only.")
    salt,digest=password_hash(payload.password)
    try:
        with connect() as c:
            cur=c.execute("INSERT INTO app_users(username,password_salt,password_hash,role,active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)",(username,salt,digest,payload.role,stamp(),stamp()))
    except sqlite3.IntegrityError:
        raise HTTPException(409,"That username already exists.")
    return {"id":cur.lastrowid,"username":username,"role":payload.role}

@router.patch("/users/{user_id}")
def update_user(user_id:int,payload:UserUpdate,request:Request):
    require_admin(request)
    if payload.role is not None and payload.role not in ("admin","recruiter","reviewer"):
        raise HTTPException(400,"Role must be admin, recruiter, or reviewer.")
    with connect() as c:
        row=c.execute("SELECT id,username,role,active FROM app_users WHERE id=?",(user_id,)).fetchone()
        if not row: raise HTTPException(404,"User not found.")
        if user_id==request.state.user["id"] and payload.active is False:
            raise HTTPException(400,"You cannot deactivate your own administrator account.")
        role=payload.role if payload.role is not None else row["role"]
        active=int(payload.active) if payload.active is not None else row["active"]
        c.execute("UPDATE app_users SET role=?,active=?,updated_at=? WHERE id=?",(role,active,stamp(),user_id))
        if not active: c.execute("DELETE FROM auth_sessions WHERE user_id=?",(user_id,))
    return {"id":user_id,"role":role,"active":bool(active)}

@router.get("/audit")
def audit_log(request:Request,limit:int=200):
    require_admin(request)
    if limit<1 or limit>500: raise HTTPException(400,"Audit limit must be between 1 and 500.")
    with connect() as c:
        data=c.execute("SELECT id,user_id,username,role,method,path,status_code,created_at FROM audit_events ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    return [dict(x) for x in data]
