"""사진 전달 기능.

흐름:
1) 사장님이 /photos/admin 에서 '새 앨범 만들기' → 6자리 코드 + QR 발급
2) 손님이 현장에서 QR 스캔 → /photos/p/{code} 모바일 갤러리에서 사진 열람/다운로드
3) 사장님이 해당 앨범에 사진 업로드 (드래그 업로드)
4) 7일 후 자동 만료 (album.is_expired)

사진 파일은 Supabase Storage 버킷 "photos"에 저장.
앨범 메타데이터(코드/메모/사진수/만료일)는 Supabase DB에 기록.
"""
import html as _html
import io
import logging
import re
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi import Request

from app.routers.admin import require_admin
from app.services import album
from app.services.db import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()

STORAGE_BUCKET = "photos"

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif"}
MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".heic": "image/heic",
    ".webp": "image/webp", ".gif": "image/gif",
}

_VALID_CODE_RE = re.compile(r"^[A-HJ-NP-Z2-9]{6}$")


def _check_code(code: str) -> None:
    if not _VALID_CODE_RE.match(code):
        raise HTTPException(400, "잘못된 앨범 코드입니다.")


async def _storage_list(code: str) -> list[str]:
    """Supabase Storage에서 앨범 폴더의 파일명 목록 반환."""
    _check_code(code)
    client = await get_supabase()
    try:
        items = await client.storage.from_(STORAGE_BUCKET).list(path=code)
        names = []
        for item in (items or []):
            name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
            if name:
                names.append(name)
        names.sort()
        return names
    except Exception as e:
        logger.error(f"Storage list 실패 [{code}]: {e}")
        return []


async def _public_url(client, code: str, filename: str) -> str:
    result = client.storage.from_(STORAGE_BUCKET).get_public_url(f"{code}/{filename}")
    if hasattr(result, "__await__"):
        result = await result
    return result


# ---------------- 관리자 API ----------------

@router.post("/api/albums")
async def create_album_api(memo: str = Form(""), _=Depends(require_admin)):
    al = await album.create_album(memo)
    return al


@router.post("/api/albums/{code}/upload")
async def upload_photos(
    code: str,
    files: list[UploadFile] = File(...),
    _=Depends(require_admin),
):
    al = await album.get_album(code)
    if not al:
        raise HTTPException(404, "앨범을 찾을 수 없습니다.")

    _check_code(code)
    client = await get_supabase()
    saved = 0
    KST = timezone(timedelta(hours=9))

    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S_%f")
        rand = secrets.token_hex(3)
        filename = f"{ts}_{rand}{ext}"
        data = await f.read()
        try:
            await client.storage.from_(STORAGE_BUCKET).upload(
                path=f"{code}/{filename}",
                file=data,
                file_options={
                    "content-type": MIME_MAP.get(ext, "image/jpeg"),
                    "cache-control": "3600",
                    "upsert": "false",
                },
            )
            saved += 1
        except Exception as e:
            logger.error(f"Storage upload 실패 [{code}/{filename}]: {e}")

    names = await _storage_list(code)
    await album.set_photo_count(code, len(names))
    return {"saved": saved, "photo_count": len(names)}


@router.get("/api/albums")
async def list_albums_api(_=Depends(require_admin)):
    albums = await album.list_albums()
    for al in albums:
        al["expired"] = album.is_expired(al)
    return albums


@router.get("/api/albums/{code}/photos")
async def list_photos_api(code: str, _=Depends(require_admin)):
    return await _storage_list(code)


@router.delete("/api/albums/{code}/photos/{filename}")
async def delete_photo_api(code: str, filename: str, _=Depends(require_admin)):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "잘못된 파일명입니다.")
    _check_code(code)
    client = await get_supabase()
    try:
        await client.storage.from_(STORAGE_BUCKET).remove([f"{code}/{filename}"])
    except Exception as e:
        logger.error(f"Storage delete 실패 [{code}/{filename}]: {e}")
        raise HTTPException(500, "파일 삭제 실패")

    names = await _storage_list(code)
    await album.set_photo_count(code, len(names))
    return {"deleted": filename, "photo_count": len(names)}


@router.delete("/api/albums/{code}")
async def delete_album_api(code: str, _=Depends(require_admin)):
    al = await album.get_album(code)
    if not al:
        raise HTTPException(404, "앨범을 찾을 수 없습니다.")

    _check_code(code)
    client = await get_supabase()
    names = await _storage_list(code)
    if names:
        paths = [f"{code}/{n}" for n in names]
        try:
            await client.storage.from_(STORAGE_BUCKET).remove(paths)
        except Exception as e:
            logger.error(f"Storage 폴더 삭제 실패 [{code}]: {e}")

    await album.delete_album(code)
    return {"deleted": code}


@router.get("/thumb/{code}/{filename}")
async def thumb_redirect(code: str, filename: str):
    """관리자 페이지 썸네일용 — Supabase Storage 공개 URL로 리다이렉트."""
    _check_code(code)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "잘못된 파일명입니다.")
    client = await get_supabase()
    url = await _public_url(client, code, filename)
    return RedirectResponse(url=url, status_code=302)


@router.get("/qr/{code}.png")
async def qr_png(code: str, request: Request):
    try:
        import qrcode
    except ImportError:
        raise HTTPException(500, "qrcode 라이브러리가 설치되지 않았습니다.")

    base = str(request.base_url).rstrip("/")
    url = f"{base}/photos/p/{code}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


# ---------------- 공개 갤러리 (손님용) ----------------

@router.get("/p/{code}", response_class=HTMLResponse)
async def public_gallery(code: str):
    al = await album.get_album(code)
    if not al:
        return HTMLResponse(_simple_page("앨범을 찾을 수 없어요", "코드를 다시 확인해 주세요."), status_code=404)
    if album.is_expired(al):
        return HTMLResponse(_simple_page("앨범이 만료되었어요 ⏰", "사진은 7일간만 보관돼요. 사장님께 문의해 주세요."), status_code=410)

    names = await _storage_list(code)
    if not names:
        return HTMLResponse(_simple_page("사진 준비 중이에요 📸", "잠시 후 다시 확인해 주세요."))

    client = await get_supabase()
    photo_items = []
    for fn in names:
        url = await _public_url(client, code, fn)
        photo_items.append(
            f'<a class="ph" href="{url}" download>'
            f'<img loading="lazy" src="{url}"></a>'
        )
    items = "".join(photo_items)
    memo = _html.escape(al.get("memo") or "")
    html = f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>서퍼스트 사진</title>
<style>
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif; background:#0f1419; color:#e6edf3; }}
  header {{ padding:18px 16px; text-align:center; border-bottom:1px solid #2a3441; }}
  header h1 {{ font-size:17px; margin:0 0 4px; }}
  header p {{ font-size:13px; color:#8b98a5; margin:0; }}
  .grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:6px; padding:6px; }}
  .ph img {{ width:100%; display:block; border-radius:8px; aspect-ratio:1/1; object-fit:cover; }}
  .tip {{ text-align:center; color:#8b98a5; font-size:12px; padding:16px; }}
</style></head>
<body>
<header><h1>📸 서퍼스트 사진</h1><p>{memo or '오늘도 즐거운 시간 보내셨길 바라요!'}</p></header>
<div class="grid">{items}</div>
<div class="tip">사진을 길게 누르면 저장할 수 있어요 · 7일간 보관</div>
</body></html>"""
    return HTMLResponse(html)


def _simple_page(title: str, sub: str) -> str:
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>body{{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
font-family:-apple-system,sans-serif;background:#0f1419;color:#e6edf3;text-align:center;padding:24px;}}
h1{{font-size:20px;margin:0 0 10px;}}p{{color:#8b98a5;font-size:14px;margin:0;}}</style></head>
<body><h1>{title}</h1><p>{sub}</p></body></html>"""


# ---------------- 관리자 페이지 ----------------

@router.get("/admin", response_class=HTMLResponse)
async def photos_admin(_=Depends(require_admin)):
    return HTMLResponse(ADMIN_HTML)


ADMIN_HTML = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0f1419" media="(prefers-color-scheme: dark)">
<title>서퍼스트 관리자 · 사진</title>
<style>
  :root {
    --bg:#f4f6f9; --card:#ffffff; --line:#e2e8f0; --txt:#1a2129; --sub:#64748b;
    --accent:#2563eb; --accent-press:#1d4ed8; --field:#f8fafc; --shadow:0 1px 3px rgba(0,0,0,.08);
  }
  [data-theme="dark"] {
    --bg:#0f1419; --card:#1a2129; --line:#2a3441; --txt:#e6edf3; --sub:#8b98a5;
    --accent:#2f81f7; --accent-press:#1f6feb; --field:#0f1419; --shadow:none;
  }
  * { box-sizing:border-box; }
  html { -webkit-text-size-adjust:100%; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
         background:var(--bg); color:var(--txt); font-size:17px; line-height:1.45; }
  header { background:var(--card); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:10; }
  .htop { padding:14px 18px; display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .brand { font-size:19px; font-weight:800; }
  .brand span { color:var(--sub); font-weight:600; font-size:14px; margin-left:4px; }
  .themebtn { background:var(--field); border:1px solid var(--line); color:var(--txt);
              width:42px; height:42px; border-radius:10px; cursor:pointer; font-size:20px; padding:0; }
  nav { display:flex; gap:6px; padding:0 12px 12px; overflow-x:auto; }
  nav a { flex:1; text-align:center; white-space:nowrap; text-decoration:none; color:var(--sub);
          font-size:16px; font-weight:700; padding:11px 10px; border-radius:10px; background:var(--field); border:1px solid var(--line); }
  nav a.active { color:#fff; background:var(--accent); border-color:var(--accent); }
  main { padding:18px; max-width:900px; margin:0 auto; }
  .new { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:20px; margin-bottom:22px; box-shadow:var(--shadow); }
  .new input { background:var(--field); border:1px solid var(--line); color:var(--txt); padding:13px 14px; border-radius:10px; font-size:17px; flex:1; min-width:180px; }
  button { background:var(--accent); color:#fff; border:none; padding:14px 18px; border-radius:11px; font-weight:800; cursor:pointer; font-size:17px; }
  button:active { background:var(--accent-press); }
  .album { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:18px; margin-bottom:14px; display:flex; gap:18px; align-items:flex-start; box-shadow:var(--shadow); }
  .album.expired { opacity:0.5; }
  .album .qr { width:130px; height:130px; border-radius:10px; background:#fff; flex-shrink:0; padding:6px; border:1px solid var(--line); }
  .album .info { flex:1; min-width:0; }
  .code { font-size:28px; font-weight:900; letter-spacing:3px; font-family:monospace; }
  .meta { color:var(--sub); font-size:15px; margin:8px 0; }
  .link { color:var(--accent); font-size:14px; word-break:break-all; }
  .drop { border:2px dashed var(--line); border-radius:11px; padding:18px; text-align:center; color:var(--sub); font-size:15px; margin-top:12px; cursor:pointer; }
  .drop.over { border-color:var(--accent); color:var(--accent); background:var(--field); }
  .empty { color:var(--sub); padding:28px; text-align:center; font-size:16px; background:var(--card); border:1px dashed var(--line); border-radius:14px; }
  .row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .hint { color:var(--sub); font-size:14px; margin:12px 0 0; line-height:1.6; }
  .delbtn { background:#ef4444; font-size:14px; padding:8px 14px; border-radius:8px; font-weight:700; flex-shrink:0; }
  .delbtn:active { background:#dc2626; }
  .thumbs { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
  .thumb { position:relative; width:80px; height:80px; flex-shrink:0; }
  .thumb img { width:100%; height:100%; object-fit:cover; border-radius:8px; display:block; border:1px solid var(--line); }
  .thumb .xbtn { position:absolute; top:-6px; right:-6px; width:22px; height:22px; border-radius:50%;
                 background:#ef4444; color:#fff; border:none; font-size:14px; font-weight:900;
                 cursor:pointer; padding:0; line-height:22px; text-align:center; }
  .thumb .xbtn:active { background:#dc2626; }
  @media (max-width:560px){
    main { padding:14px; padding-bottom: max(20px, env(safe-area-inset-bottom)); }
    .album { flex-direction:column; align-items:center; text-align:center; }
    .album .info { width:100%; }
    .delbtn { min-height:44px; }
    button { min-height:44px; }
  }
</style></head>
<body>
<header>
  <div class="htop">
    <div class="brand">🏄 서퍼스트<span>관리자</span></div>
    <button class="themebtn" id="themebtn" onclick="toggleTheme()" title="화면 톤 전환">🌙</button>
  </div>
  <nav>
    <a href="/admin/">🏠 홈</a>
    <a href="/availability/admin">📅 예약</a>
    <a href="/photos/admin" class="active">📸 사진</a>
  </nav>
</header>
<main>
  <div class="new">
    <div class="row">
      <input id="memo" placeholder="메모 (예: 6/4 오전 데패강 김OO님)">
      <button onclick="createAlbum()">+ 새 앨범 만들기</button>
    </div>
    <p class="hint">앨범을 만들면 QR이 나와요. 손님에게 QR을 보여주고 스캔하게 하면 끝.<br>사진은 아래 박스에 끌어다 놓으면 올라가요.</p>
  </div>
  <div id="list"><div class="empty">불러오는 중...</div></div>
</main>
<script>
const base = location.origin;
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function fmt(ts){ if(!ts) return '-'; return new Date(ts).toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }

function applyTheme(t){
  if(t==='dark'){ document.documentElement.setAttribute('data-theme','dark'); document.getElementById('themebtn').textContent='☀️'; }
  else { document.documentElement.removeAttribute('data-theme'); document.getElementById('themebtn').textContent='🌙'; }
}
function toggleTheme(){
  const cur = document.documentElement.getAttribute('data-theme')==='dark'?'dark':'light';
  const next = cur==='dark'?'light':'dark';
  try{ localStorage.setItem('dash_theme', next); }catch(e){}
  applyTheme(next);
}
(function(){ let t='light'; try{ t=localStorage.getItem('dash_theme')||'light'; }catch(e){} applyTheme(t); })();

async function createAlbum(){
  const memo = document.getElementById('memo').value;
  const fd = new FormData(); fd.append('memo', memo);
  await fetch('api/albums', {method:'POST', body:fd});
  document.getElementById('memo').value='';
  load();
}

async function load(){
  const albums = await fetch('api/albums').then(r=>r.json());
  const el = document.getElementById('list');
  if(!albums.length){ el.innerHTML='<div class="empty">아직 앨범이 없어요. 위에서 새로 만들어 보세요.</div>'; return; }
  el.innerHTML = albums.map(a=>`
    <div class="album ${a.expired?'expired':''}" id="album-${a.code}">
      <img class="qr" src="qr/${a.code}.png">
      <div class="info">
        <div class="row" style="justify-content:space-between;align-items:flex-start;flex-wrap:nowrap;">
          <div class="code">${esc(a.code)}</div>
          <button class="delbtn" onclick="deleteAlbum('${a.code}')">앨범 삭제</button>
        </div>
        <div class="meta">${esc(a.memo)||'(메모 없음)'} · 사진 ${a.photo_count||0}장 · ${a.expired?'만료됨':'~'+fmt(a.expires_at)}</div>
        <a class="link" href="${base}/photos/p/${a.code}" target="_blank">${base}/photos/p/${a.code}</a>
        <div id="thumbs-${a.code}"></div>
        <div class="drop" data-code="${a.code}">여기에 사진을 끌어다 놓거나 클릭해서 선택</div>
        <input type="file" multiple accept="image/*" style="display:none" data-code="${a.code}">
      </div>
    </div>`).join('');
  bindDrops();
  albums.forEach(a => loadThumbs(a.code));
}

async function loadThumbs(code){
  const files = await fetch(`api/albums/${code}/photos`).then(r=>r.json());
  const el = document.getElementById(`thumbs-${code}`);
  if(!el) return;
  if(!files.length){ el.innerHTML=''; return; }
  el.innerHTML = `<div class="thumbs">${files.map(fn=>`
    <div class="thumb">
      <img src="/photos/thumb/${code}/${fn}" loading="lazy">
      <button class="xbtn" onclick="deletePhoto('${code}','${fn}')">×</button>
    </div>`).join('')}</div>`;
}

async function deleteAlbum(code){
  if(!confirm('앨범 전체를 삭제할까요? 사진도 모두 사라져요.')) return;
  await fetch(`api/albums/${code}`, {method:'DELETE'});
  load();
}

async function deletePhoto(code, filename){
  await fetch(`api/albums/${code}/photos/${filename}`, {method:'DELETE'});
  loadThumbs(code);
}

function bindDrops(){
  document.querySelectorAll('.drop').forEach(drop=>{
    const code = drop.dataset.code;
    const input = document.querySelector(`input[type=file][data-code="${code}"]`);
    drop.onclick = ()=> input.click();
    input.onchange = ()=> uploadFiles(code, input.files);
    drop.ondragover = e=>{ e.preventDefault(); drop.classList.add('over'); };
    drop.ondragleave = ()=> drop.classList.remove('over');
    drop.ondrop = e=>{ e.preventDefault(); drop.classList.remove('over'); uploadFiles(code, e.dataTransfer.files); };
  });
}

async function uploadFiles(code, files){
  if(!files || !files.length) return;
  const fd = new FormData();
  for(const f of files) fd.append('files', f);
  const drop = document.querySelector(`.drop[data-code="${code}"]`);
  drop.textContent = '업로드 중...';
  await fetch(`api/albums/${code}/upload`, {method:'POST', body:fd});
  load();
}
load();
</script>
</body></html>"""
