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

from fastapi import APIRouter, Cookie, Depends, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse

from app.routers.admin import require_admin
from app.services.auth import verify_session
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
    """Supabase Storage에서 앨범 폴더의 파일명 목록 반환. 조회 실패는 예외로 올린다.

    실패를 빈 목록으로 뭉개면 안 된다. 만료 정리가 조회에 실패한 앨범의
    DB 레코드만 지우고 파일은 남기는데, 코드가 사라지면 {code}/ 폴더를
    다시 찾을 단서가 없어 영구 고아 파일이 된다.
    """
    _check_code(code)
    client = await get_supabase()
    items = await client.storage.from_(STORAGE_BUCKET).list(
        path=code, options={"limit": 3000, "offset": 0}
    )
    names = []
    for item in (items or []):
        name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
        if name:
            names.append(name)
    names.sort()
    return names


async def _storage_list_safe(code: str) -> list[str]:
    """열람 화면용 — 조회가 실패해도 빈 화면으로 넘어간다."""
    try:
        return await _storage_list(code)
    except Exception as e:
        logger.error(f"Storage list 실패 [{code}]: {e}")
        return []


async def _sync_photo_count(code: str, fallback: int) -> int:
    """Storage 실제 파일 수를 DB에 반영. 조회 실패 시 기존 값을 유지한다."""
    try:
        names = await _storage_list(code)
    except Exception as e:
        logger.error(f"사진 수 갱신 실패 [{code}]: {e}")
        return fallback
    await album.set_photo_count(code, len(names))
    return len(names)


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

    count = await _sync_photo_count(code, al.get("photo_count") or 0)
    return {"saved": saved, "photo_count": count}


@router.get("/api/albums")
async def list_albums_api(_=Depends(require_admin)):
    albums = await album.list_albums()
    for al in albums:
        al["expired"] = album.is_expired(al)
    return albums


@router.get("/api/albums/{code}/photos")
async def list_photos_api(code: str, _=Depends(require_admin)):
    return await _storage_list_safe(code)


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

    al = await album.get_album(code)
    count = await _sync_photo_count(code, (al or {}).get("photo_count") or 0)
    return {"deleted": filename, "photo_count": count}


async def cleanup_expired_albums() -> int:
    """만료된 앨범의 Storage 파일과 DB 레코드를 삭제. 삭제된 앨범 수 반환."""
    expired = await album.list_expired_albums()
    if not expired:
        return 0
    client = await get_supabase()
    deleted = 0
    for al in expired:
        code = al.get("code", "")
        if not code:
            continue
        try:
            names = await _storage_list(code)
            if names:
                await client.storage.from_(STORAGE_BUCKET).remove([f"{code}/{n}" for n in names])
            await album.delete_album(code)
            deleted += 1
            logger.info(f"만료 앨범 자동 삭제: {code}")
        except Exception as e:
            logger.error(f"만료 앨범 삭제 실패 [{code}]: {e}")
    return deleted


@router.delete("/api/albums/{code}")
async def delete_album_api(code: str, _=Depends(require_admin)):
    al = await album.get_album(code)
    if not al:
        raise HTTPException(404, "앨범을 찾을 수 없습니다.")

    _check_code(code)
    client = await get_supabase()
    # 파일을 못 지운 채 DB 레코드부터 지우면 그 폴더는 다시 찾을 수 없다 → 중단하고 재시도 유도
    try:
        names = await _storage_list(code)
        if names:
            await client.storage.from_(STORAGE_BUCKET).remove([f"{code}/{n}" for n in names])
    except Exception as e:
        logger.error(f"Storage 폴더 삭제 실패 [{code}]: {e}")
        raise HTTPException(500, "사진 파일 삭제에 실패했어요. 잠시 후 다시 시도해 주세요.")

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
    _check_code(code)
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

    names = await _storage_list_safe(code)
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
async def photos_admin(asess: str | None = Cookie(default=None)):
    if not verify_session(asess):
        return RedirectResponse(url="/admin/login", status_code=302)
    return HTMLResponse(ADMIN_HTML)


ADMIN_HTML = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#09090d" media="(prefers-color-scheme: dark)">
<link rel="manifest" href="/static/manifest.json">
<link rel="apple-touch-icon" href="/static/icon-192.png">
<link rel="stylesheet" href="/static/admin/surf-admin.css?v=20260825-homeclean">
<title>서퍼스트 관리자 · 사진</title>
<style>
  :root {
    --bg:#f6f8fa; --card:#ffffff; --line:#d0d7de; --txt:#1f2328; --sub:#57606a;
    --accent:#6366f1; --accent-press:#4f46e5; --field:#f6f8fa; --shadow:0 1px 3px rgba(0,0,0,.08);
    --header-bg:rgba(255,255,255,.92);
  }
  [data-theme="dark"] {
    --bg:#09090d; --card:#111116; --line:#1e2028; --txt:#e4e7ef; --sub:#6b7280;
    --accent:#818cf8; --accent-press:#6366f1; --field:#0d0f14; --shadow:none;
    --header-bg:rgba(9,9,13,.85);
  }
  * { box-sizing:border-box; }
  html { -webkit-text-size-adjust:100%; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
         background:var(--bg); color:var(--txt); font-size:17px; line-height:1.45; }
  header { background:var(--header-bg); backdrop-filter:saturate(180%) blur(12px);
           -webkit-backdrop-filter:saturate(180%) blur(12px);
           border-bottom:1px solid var(--line); position:sticky; top:0; z-index:10; }
  .htop { padding:14px 18px; display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .brand { font-size:19px; font-weight:800; }
  .brand span { color:var(--sub); font-weight:600; font-size:14px; margin-left:4px; }
  .htools { display:flex; align-items:center; gap:6px; }
  .themebtn { background:var(--field); border:1px solid var(--line); color:var(--txt);
              width:40px; height:40px; border-radius:10px; cursor:pointer; font-size:19px; padding:0;
              display:flex; align-items:center; justify-content:center; }
  .logoutbtn { color:var(--sub); font-size:13px; font-weight:600; text-decoration:none;
               padding:9px 12px; border-radius:10px; background:var(--field);
               border:1px solid var(--line); white-space:nowrap; }
  .logoutbtn:hover { color:var(--txt); }
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
  .delbtn { background:#ef4444; font-size:14px; padding:8px 14px; border-radius:8px; font-weight:700; flex-shrink:0; min-width:40px; min-height:40px; }
  .delbtn:active { background:#dc2626; }
  .thumbs { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
  .thumb { position:relative; width:80px; height:80px; flex-shrink:0; }
  .thumb img { width:100%; height:100%; object-fit:cover; border-radius:8px; display:block; border:1px solid var(--line); }
  .thumb .xbtn { position:absolute; top:-6px; right:-6px; width:40px; height:40px; border-radius:50%;
                 background:#ef4444; color:#fff; border:none; font-size:14px; font-weight:900;
                 cursor:pointer; padding:0; line-height:40px; text-align:center; }
  .thumb .xbtn:active { background:#dc2626; }
  @media (max-width:560px){
    main { padding:14px; padding-bottom: max(20px, env(safe-area-inset-bottom)); }
    .album { flex-direction:column; align-items:center; text-align:center; }
    .album .info { width:100%; }
    .delbtn { min-height:44px; }
    button { min-height:44px; }
  }
</style><script src="/static/admin/surf-admin.js"></script></head>
<body>
<div class="sf-app">
  <aside class="sf-sidebar">
    <div class="sf-brand">서퍼스트<small>운영 콘솔</small></div>
    <nav class="sf-nav" aria-label="관리자 메뉴">
      <a class="sf-nav__link" href="/admin/">홈</a>
      <a class="sf-nav__link" href="/availability/admin">예약</a>
      <a class="sf-nav__link" href="/photos/admin" aria-current="page">사진</a>
      <a class="sf-nav__link" href="/dashboard/">분석</a>
    </nav>
  </aside>
  <div class="sf-main">
    <header class="sf-topbar">
      <div class="sf-mobile-brand">서퍼스트 운영 콘솔</div>
      <div class="sf-actions">
        <button class="sf-btn sf-btn--ghost" id="themebtn" type="button">어둡게</button>
        <a class="sf-btn sf-btn--ghost" href="/admin/logout">로그아웃</a>
      </div>
    </header>
    <main class="sf-page">
      <div id="photo-delivery">
        <div class="sf-page-head">
          <div>
            <div class="sf-eyebrow">사진 전달</div>
            <h1 class="sf-page-title">현장 앨범</h1>
            <p class="sf-page-sub">앨범을 만들고 QR을 손님에게 보여주세요.</p>
          </div>
        </div>
        <section class="sf-panel album-create-panel" id="album-create-panel">
          <div class="sf-form-grid">
            <div class="sf-field sf-field--full">
              <label for="memo">앨범 메모</label>
              <input id="memo" placeholder="예: 8월 23일 오후 강습">
            </div>
            <button class="sf-btn sf-btn--primary" onclick="createAlbum()" type="button">새 앨범 만들기</button>
          </div>
        </section>
        <section class="album-list" id="list"><div class="sf-empty">불러오는 중...</div></section>
      </div>
    </main>
  </div>
</div>
<script>
const base = location.origin;
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function fmt(ts){ if(!ts) return '-'; return new Date(ts).toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }

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
  if(!albums.length){ el.innerHTML='<div class="sf-empty">아직 앨범이 없어요. 위에서 새로 만들어 보세요.</div>'; return; }
  el.innerHTML = albums.map(a=>`
    <article class="album-card ${a.expired?'is-expired':''}" id="album-${a.code}">
      <img class="album-card__qr" src="qr/${a.code}.png" alt="${esc(a.code)} QR">
      <div class="album-card__body">
        <div class="album-card__head">
          <div>
            <div class="album-code">${esc(a.code)}</div>
            <div class="album-meta">${esc(a.memo)||'(메모 없음)'} · 사진 ${a.photo_count||0}장 · ${a.expired?'만료됨':'~'+fmt(a.expires_at)}</div>
          </div>
          <button class="sf-btn sf-btn--danger delbtn" onclick="deleteAlbum('${a.code}')" type="button">삭제</button>
        </div>
        <a class="album-link" href="${base}/photos/p/${a.code}" target="_blank">${base}/photos/p/${a.code}</a>
        <div class="album-upload-status" id="upload-status-${a.code}" role="status" aria-live="polite"></div>
        <div class="drop" data-code="${a.code}">사진을 끌어다 놓거나 클릭해서 선택</div>
        <input type="file" multiple accept="image/*" style="display:none" data-code="${a.code}">
        <div id="thumbs-${a.code}"></div>
      </div>
    </article>`).join('');
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
  const status = document.getElementById(`upload-status-${code}`);
  if(drop) drop.textContent = '업로드 중...';
  if(status) status.textContent = files.length + '장 업로드 중...';
  try{
    const res = await fetch(`api/albums/${code}/upload`, {method:'POST', body:fd});
    if(!res.ok) throw new Error('upload failed');
    if(status) status.textContent = '업로드 완료';
    load();
  }catch(_err){
    if(drop) drop.textContent = '사진을 끌어다 놓거나 클릭해서 선택';
    if(status) status.textContent = '업로드 실패. 다시 시도해 주세요.';
  }
}
load();
</script>
<script>SurfAdmin.initTheme('themebtn');</script>
<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js');</script>
</body></html>"""
