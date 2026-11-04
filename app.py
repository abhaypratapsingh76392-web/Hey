import os
import io
import base64
import asyncio
import zipfile
from typing import Optional

import httpx
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

GITHUB_API = "https://api.github.com"
app = FastAPI(title="GitHub Manager")

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub Manager</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh;padding:20px}
  .container{max-width:1100px;margin:0 auto}
  h1{color:#58a6ff;margin-bottom:6px;font-size:26px}
  .subtitle{color:#8b949e;margin-bottom:24px;font-size:14px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:20px}
  .card h2{font-size:16px;margin-bottom:16px;color:#f0f6fc;display:flex;align-items:center;gap:8px}
  input,textarea,select{width:100%;padding:10px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px;font-family:inherit;margin-bottom:10px}
  input:focus,textarea:focus{outline:none;border-color:#58a6ff}
  button{padding:9px 16px;background:#238636;border:1px solid #2ea043;border-radius:6px;color:#fff;font-size:13px;font-weight:600;cursor:pointer;transition:.15s}
  button:hover{background:#2ea043}
  button:disabled{opacity:.5;cursor:not-allowed}
  button.secondary{background:#21262d;border-color:#30363d;color:#c9d1d9}
  button.secondary:hover{background:#30363d}
  button.danger{background:#da3633;border-color:#f85149}
  button.danger:hover{background:#f85149}
  .row{display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap}
  .row > *{flex:1;min-width:200px}
  .toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
  .repos{display:grid;gap:8px;max-height:520px;overflow-y:auto;margin-top:12px;padding-right:4px}
  .repo{display:flex;justify-content:space-between;align-items:center;background:#0d1117;padding:12px 14px;border-radius:6px;border:1px solid #30363d;gap:10px;flex-wrap:wrap}
  .repo-info{flex:1;min-width:200px}
  .repo-name{font-size:14px;color:#58a6ff;text-decoration:none;font-weight:600}
  .repo-name:hover{text-decoration:underline}
  .repo-desc{font-size:12px;color:#8b949e;margin-top:4px}
  .badge{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600;margin-left:8px;display:inline-block}
  .badge.private{background:#6e40c9;color:#fff}
  .badge.public{background:#238636;color:#fff}
  .log{background:#0d1117;border:1px solid #30363d;padding:12px;border-radius:6px;max-height:220px;overflow-y:auto;font-family:'SF Mono',monospace;font-size:12px;color:#8b949e;white-space:pre-wrap;margin-top:10px}
  .status{padding:10px 14px;border-radius:6px;font-size:13px;margin-top:10px;line-height:1.5}
  .status.ok{background:#0d2f1a;border:1px solid #238636;color:#56d364}
  .status.err{background:#3d0e0e;border:1px solid #da3633;color:#f85149}
  .status.info{background:#1f2a3d;border:1px solid #58a6ff;color:#79c0ff}
  .radio-group{display:flex;gap:20px;margin-bottom:12px;align-items:center}
  .radio-group label{display:flex;align-items:center;gap:6px;cursor:pointer;margin:0;font-size:14px}
  .radio-group input[type=radio]{width:auto;margin:0}
  .hidden{display:none!important}
  .spinner{display:inline-block;width:14px;height:14px;border:2px solid #30363d;border-top-color:#58a6ff;border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-right:6px}
  @keyframes spin{to{transform:rotate(360deg)}}
  .search-box{position:relative;margin-bottom:10px}
  .search-box input{margin:0;padding-left:34px}
  .search-box::before{content:'🔍';position:absolute;left:12px;top:9px;font-size:14px;opacity:.6}
  .file-input-wrapper{padding:10px;background:#0d1117;border:1px dashed #30363d;border-radius:6px;margin-bottom:10px;text-align:center;font-size:13px;color:#8b949e}
  .file-input-wrapper input{padding:0;margin:0;border:none;background:none}
  small{color:#8b949e;font-size:12px}
  .counter{font-size:12px;color:#8b949e;margin-bottom:8px}
</style>
</head>
<body>
<div class="container">
  <h1>🐙 GitHub Manager</h1>
  <p class="subtitle">Manage repos • Bulk visibility • Create + Upload ZIP</p>

  <div class="card">
    <h2>🔑 GitHub Personal Access Token</h2>
    <input id="token" type="password" placeholder="ghp_... (needs 'repo' scope)">
    <div class="row">
      <button onclick="saveToken()">💾 Save & Load</button>
      <button class="secondary" onclick="clearToken()">🗑️ Clear</button>
    </div>
    <div id="tokenStatus"></div>
    <small style="display:block;margin-top:10px">Token banao: <a href="https://github.com/settings/tokens/new?scopes=repo&description=Render%20Manager" target="_blank" style="color:#58a6ff">github.com/settings/tokens/new</a> (scope: <b>repo</b>)</small>
  </div>

  <div class="card hidden" id="reposCard">
    <h2>📁 Repositories <span id="repoCount" class="counter" style="margin-left:8px"></span></h2>
    <div class="toolbar">
      <button class="secondary" onclick="loadRepos()">🔄 Refresh</button>
      <button class="secondary" onclick="bulkVisibility(true)">🔒 Make All Private</button>
      <button class="secondary" onclick="bulkVisibility(false)">🌐 Make All Public</button>
    </div>
    <div class="search-box"><input id="searchInput" placeholder="Search repos..." oninput="filterRepos()"></div>
    <div class="log hidden" id="bulkLog"></div>
    <div class="repos" id="reposList"></div>
  </div>

  <div class="card hidden" id="createCard">
    <h2>➕ Create Repo & Upload ZIP</h2>
    <input id="repoName" placeholder="Repo name (e.g. my-project)">
    <input id="repoDesc" placeholder="Description (optional)">
    <div class="radio-group">
      <label><input type="radio" name="vis" value="public" checked> 🌐 Public</label>
      <label><input type="radio" name="vis" value="private"> 🔒 Private</label>
    </div>
    <div class="file-input-wrapper">
      <input id="zipFile" type="file" accept=".zip">
    </div>
    <button onclick="createWithZip()" id="createBtn">🚀 Create & Upload</button>
    <div id="createStatus"></div>
    <small style="display:block;margin-top:10px">ZIP ka andar jo code hai wo seedha repo me chala jayega. Top-level folder auto-strip ho jayega.</small>
  </div>
</div>

<script>
let TOKEN = '';
let ALL_REPOS = [];

async function saveToken() {
  const t = document.getElementById('token').value.trim();
  if (!t) return alert('Token required');
  document.getElementById('tokenStatus').innerHTML = '<div class="status info"><span class="spinner"></span>Validating token...</div>';
  
  const res = await fetch('/api/repos', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: t})
  });
  
  if (!res.ok) {
    const e = await res.json().catch(() => ({}));
    document.getElementById('tokenStatus').innerHTML = `<div class="status err">❌ ${e.detail || 'Invalid token'}</div>`;
    return;
  }
  
  TOKEN = t;
  localStorage.setItem('gh_token', t);
  document.getElementById('tokenStatus').innerHTML = '<div class="status ok">✅ Token valid! Repos loaded.</div>';
  document.getElementById('reposCard').classList.remove('hidden');
  document.getElementById('createCard').classList.remove('hidden');
  
  ALL_REPOS = await res.json();
  renderRepos(ALL_REPOS);
}

function clearToken() {
  localStorage.removeItem('gh_token');
  TOKEN = '';
  ALL_REPOS = [];
  document.getElementById('token').value = '';
  document.getElementById('tokenStatus').innerHTML = '';
  document.getElementById('reposCard').classList.add('hidden');
  document.getElementById('createCard').classList.add('hidden');
}

async function loadRepos() {
  if (!TOKEN) return alert('Save token first');
  const res = await fetch('/api/repos', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: TOKEN})
  });
  if (!res.ok) return alert('Failed to load repos');
  ALL_REPOS = await res.json();
  renderRepos(ALL_REPOS);
}

function renderRepos(repos) {
  const list = document.getElementById('reposList');
  const count = document.getElementById('repoCount');
  count.textContent = `(${repos.length})`;
  
  if (!repos.length) {
    list.innerHTML = '<p style="color:#8b949e;padding:20px;text-align:center">No repos found</p>';
    return;
  }
  
  list.innerHTML = repos.map(r => `
    <div class="repo">
      <div class="repo-info">
        <a href="${r.html_url}" target="_blank" class="repo-name">${r.full_name}</a>
        <span class="badge ${r.private ? 'private' : 'public'}">${r.private ? '🔒 Private' : '🌐 Public'}</span>
        ${r.description ? `<div class="repo-desc">${escapeHtml(r.description)}</div>` : ''}
      </div>
      <div style="display:flex;gap:6px;">
        <button class="secondary" onclick="toggleVisibility('${r.full_name}', ${!r.private})">Make ${r.private ? 'Public' : 'Private'}</button>
        <button class="danger" onclick="deleteRepo('${r.full_name}')">🗑️</button>
      </div>
    </div>
  `).join('');
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function filterRepos() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const filtered = q ? ALL_REPOS.filter(r => r.full_name.toLowerCase().includes(q)) : ALL_REPOS;
  renderRepos(filtered);
}

async function toggleVisibility(fullName, makePrivate) {
  const [owner, repo] = fullName.split('/');
  const res = await fetch('/api/repo/visibility', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: TOKEN, owner, repo, private: makePrivate})
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({}));
    alert('Failed: ' + (e.detail || 'Unknown'));
    return;
  }
  await loadRepos();
}

async function deleteRepo(fullName) {
  if (!confirm(`Delete "${fullName}"?\n\n⚠️ This cannot be undone!`)) return;
  if (!confirm(`Really delete "${fullName}"? Type OK to confirm.`)) return;
  const [owner, repo] = fullName.split('/');
  const res = await fetch('/api/repo/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: TOKEN, owner, repo})
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({}));
    alert('Delete failed: ' + (e.detail || 'Unknown'));
    return;
  }
  await loadRepos();
}

async function bulkVisibility(makePrivate) {
  const target = makePrivate ? 'PRIVATE' : 'PUBLIC';
  if (!confirm(`Make ALL ${ALL_REPOS.length} repos ${target}?`)) return;
  
  const log = document.getElementById('bulkLog');
  log.classList.remove('hidden');
  log.textContent = `⏳ Processing ${ALL_REPOS.length} repos → ${target}...\n`;
  
  const repoList = ALL_REPOS.map(r => r.full_name);
  const chunks = [];
  for (let i = 0; i < repoList.length; i += 50) chunks.push(repoList.slice(i, i + 50));
  
  let success = 0, failed = 0;
  const errors = [];
  
  for (let i = 0; i < chunks.length; i++) {
    log.textContent += `\nBatch ${i+1}/${chunks.length} (${chunks[i].length} repos)...`;
    try {
      const res = await fetch('/api/repos/visibility-batch', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({token: TOKEN, repos: chunks[i], private: makePrivate})
      });
      const data = await res.json();
      for (const r of data.results) {
        if (r.ok) success++; else { failed++; errors.push(`${r.repo}: ${r.error}`); }
      }
      log.textContent += ` ✓ (${success}/${repoList.length})`;
    } catch (e) {
      log.textContent += ` ❌ ${e.message}`;
    }
  }
  
  log.textContent += `\n\n✅ Success: ${success}\n❌ Failed: ${failed}`;
  if (errors.length) log.textContent += '\n\n' + errors.slice(0, 20).join('\n');
  
  await loadRepos();
}

async function createWithZip() {
  const name = document.getElementById('repoName').value.trim();
  const desc = document.getElementById('repoDesc').value.trim();
  const vis = document.querySelector('input[name=vis]:checked').value;
  const zipInput = document.getElementById('zipFile');
  const status = document.getElementById('createStatus');
  const btn = document.getElementById('createBtn');
  
  if (!name) return alert('Repo name required');
  if (!zipInput.files.length) return alert('ZIP file required');
  
  const fd = new FormData();
  fd.append('token', TOKEN);
  fd.append('repo_name', name);
  fd.append('private', vis === 'private' ? 'true' : 'false');
  fd.append('description', desc);
  fd.append('zip_file', zipInput.files[0]);
  
  btn.disabled = true;
  status.innerHTML = '<div class="status info"><span class="spinner"></span>Creating repo and uploading files...</div>';
  
  try {
    const res = await fetch('/api/repo/create-with-zip', {method: 'POST', body: fd});
    const data = await res.json();
    
    if (!res.ok || data.error) {
      status.innerHTML = `<div class="status err">❌ ${data.error || 'Failed'}<br><small>${data.detail || ''}</small></div>`;
    } else {
      status.innerHTML = `<div class="status ok">✅ Repo created: <a href="${data.url}" target="_blank" style="color:#56d364">${data.repo}</a><br>📄 Files uploaded: ${data.files_uploaded}</div>`;
      document.getElementById('repoName').value = '';
      document.getElementById('repoDesc').value = '';
      zipInput.value = '';
      await loadRepos();
    }
  } catch (e) {
    status.innerHTML = `<div class="status err">❌ ${e.message}</div>`;
  } finally {
    btn.disabled = false;
  }
}

window.addEventListener('load', async () => {
  const saved = localStorage.getItem('gh_token');
  if (saved) {
    document.getElementById('token').value = saved;
    TOKEN = saved;
    try {
      const res = await fetch('/api/repos', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({token: saved})
      });
      if (res.ok) {
        ALL_REPOS = await res.json();
        document.getElementById('tokenStatus').innerHTML = '<div class="status ok">✅ Token valid! Repos loaded.</div>';
        document.getElementById('reposCard').classList.remove('hidden');
        document.getElementById('createCard').classList.remove('hidden');
        renderRepos(ALL_REPOS);
      }
    } catch(e) {}
  }
});
</script>
</body>
</html>"""


def gh_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "message": "GitHub Manager running"}


@app.get("/", response_class=HTMLResponse)
async def ui():
    return HTML_PAGE


@app.post("/api/repos")
async def list_repos(request: Request):
    data = await request.json()
    token = data.get("token", "").strip()
    if not token:
        raise HTTPException(400, "Token required")
    
    repos = []
    async with httpx.AsyncClient(timeout=30) as client:
        page = 1
        while page <= 10:  # max 1000 repos
            r = await client.get(
                f"{GITHUB_API}/user/repos",
                headers=gh_headers(token),
                params={"per_page": 100, "page": page, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
            )
            if r.status_code == 401:
                raise HTTPException(401, "Invalid token")
            if r.status_code == 403:
                raise HTTPException(403, "Rate limit or permission error")
            if r.status_code != 200:
                raise HTTPException(r.status_code, r.text)
            batch = r.json()
            if not batch:
                break
            for repo in batch:
                repos.append({
                    "full_name": repo["full_name"],
                    "name": repo["name"],
                    "html_url": repo["html_url"],
                    "private": repo["private"],
                    "description": repo.get("description"),
                })
            if len(batch) < 100:
                break
            page += 1
    
    return JSONResponse(repos)


@app.post("/api/repo/visibility")
async def change_visibility(request: Request):
    data = await request.json()
    token = data.get("token")
    owner = data.get("owner")
    repo = data.get("repo")
    private = bool(data.get("private"))
    
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.patch(
            f"{GITHUB_API}/repos/{owner}/{repo}",
            headers=gh_headers(token),
            json={"private": private},
        )
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@app.post("/api/repos/visibility-batch")
async def visibility_batch(request: Request):
    data = await request.json()
    token = data.get("token")
    repos = data.get("repos", [])
    private = bool(data.get("private"))
    
    results = []
    async with httpx.AsyncClient(timeout=30) as client:
        sem = asyncio.Semaphore(10)
        
        async def change_one(full_name: str):
            async with sem:
                try:
                    r = await client.patch(
                        f"{GITHUB_API}/repos/{full_name}",
                        headers=gh_headers(token),
                        json={"private": private},
                    )
                    if r.status_code == 200:
                        return {"repo": full_name, "ok": True}
                    return {"repo": full_name, "ok": False, "error": f"{r.status_code}: {r.text[:200]}"}
                except Exception as e:
                    return {"repo": full_name, "ok": False, "error": str(e)}
        
        tasks = [change_one(r) for r in repos]
        results = await asyncio.gather(*tasks)
    
    return {"results": results}


@app.post("/api/repo/delete")
async def delete_repo(request: Request):
    data = await request.json()
    token = data.get("token")
    owner = data.get("owner")
    repo = data.get("repo")
    
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}",
            headers=gh_headers(token),
        )
        if r.status_code not in (204, 200):
            raise HTTPException(r.status_code, r.text)
        return {"ok": True}


@app.post("/api/repo/create-with-zip")
async def create_with_zip(
    token: str = Form(...),
    repo_name: str = Form(...),
    private: bool = Form(False),
    description: str = Form(""),
    zip_file: UploadFile = File(...),
):
    headers = gh_headers(token)
    
    # Validate repo name
    if not repo_name.replace("-", "").replace("_", "").replace(".", "").isalnum():
        return JSONResponse({"error": "Invalid repo name (use letters, numbers, - _ . only)"}, 400)
    
    async with httpx.AsyncClient(timeout=120) as client:
        # 1. Get user
        r = await client.get(f"{GITHUB_API}/user", headers=headers)
        if r.status_code != 200:
            return JSONResponse({"error": "Invalid token", "detail": r.text[:200]}, 400)
        owner = r.json()["login"]
        
        # 2. Check if repo exists
        r = await client.get(f"{GITHUB_API}/repos/{owner}/{repo_name}", headers=headers)
        if r.status_code == 200:
            return JSONResponse({"error": f"Repo '{repo_name}' already exists"}, 400)
        
        # 3. Create repo
        r = await client.post(
            f"{GITHUB_API}/user/repos",
            headers=headers,
            json={
                "name": repo_name,
                "private": private,
                "description": description,
                "auto_init": True,
            },
        )
        if r.status_code != 201:
            return JSONResponse({"error": "Failed to create repo", "detail": r.text[:300]}, 400)
        repo_data = r.json()
        default_branch = repo_data.get("default_branch", "main")
        
        # 4. Read zip
        zip_bytes = await zip_file.read()
        if len(zip_bytes) > 100 * 1024 * 1024:
            return JSONResponse({"error": "ZIP too large (max 100MB)"}, 400)
        
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except Exception as e:
            return JSONResponse({"error": f"Invalid ZIP: {e}"}, 400)
        
        # 5. Build file list, skip junk
        all_entries = [
            n for n in zf.namelist()
            if not n.endswith("/")
            and not any(x in n for x in ["__MACOSX/", ".DS_Store", "__pycache__/", ".git/"])
        ]
        if not all_entries:
            return JSONResponse({"error": "No valid files in ZIP"}, 400)
        
        # 6. Strip common top-level folder if present
        first_parts = [n.split("/")[0] for n in all_entries if "/" in n]
        has_nested = [n for n in all_entries if "/" in n]
        if first_parts and len(set(first_parts)) == 1 and len(has_nested) == len(all_entries):
            prefix = first_parts[0] + "/"
            mapping = [(n, n[len(prefix):]) for n in all_entries]
        else:
            mapping = [(n, n) for n in all_entries]
        
        # 7. Get parent commit and tree
        r = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo_name}/git/ref/heads/{default_branch}",
            headers=headers,
        )
        if r.status_code != 200:
            return JSONResponse({"error": "Failed to get ref", "detail": r.text[:300]}, 400)
        parent_sha = r.json()["object"]["sha"]
        
        r = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo_name}/git/commits/{parent_sha}",
            headers=headers,
        )
        if r.status_code != 200:
            return JSONResponse({"error": "Failed to get commit", "detail": r.text[:300]}, 400)
        base_tree_sha = r.json()["tree"]["sha"]
        
        # 8. Create blobs (concurrent)
        tree_entries = []
        skipped = []
        sem = asyncio.Semaphore(8)
        
        async def make_blob(orig: str, target: str):
            async with sem:
                try:
                    content = zf.read(orig)
                except Exception as e:
                    return {"skip": True, "file": target, "error": str(e)}
                
                try:
                    r = await client.post(
                        f"{GITHUB_API}/repos/{owner}/{repo_name}/git/blobs",
                        headers=headers,
                        json={"content": base64.b64encode(content).decode(), "encoding": "base64"},
                    )
                    if r.status_code != 201:
                        return {"skip": True, "file": target, "error": r.text[:200]}
                    return {"skip": False, "entry": {
                        "path": target, "mode": "100644", "type": "blob", "sha": r.json()["sha"]
                    }}
                except Exception as e:
                    return {"skip": True, "file": target, "error": str(e)}
        
        blob_results = await asyncio.gather(*[make_blob(o, t) for o, t in mapping])
        for res in blob_results:
            if res["skip"]:
                skipped.append({"file": res["file"], "error": res["error"]})
            else:
                tree_entries.append(res["entry"])
        
        if not tree_entries:
            return JSONResponse({"error": "No files could be uploaded"}, 400)
        
        # 9. Create tree
        r = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo_name}/git/trees",
            headers=headers,
            json={"base_tree": base_tree_sha, "tree": tree_entries},
        )
        if r.status_code != 201:
            return JSONResponse({"error": "Failed to create tree", "detail": r.text[:300]}, 400)
        new_tree_sha = r.json()["sha"]
        
        # 10. Create commit
        r = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo_name}/git/commits",
            headers=headers,
            json={"message": "Initial upload from ZIP", "tree": new_tree_sha, "parents": [parent_sha]},
        )
        if r.status_code != 201:
            return JSONResponse({"error": "Failed to create commit", "detail": r.text[:300]}, 400)
        new_commit_sha = r.json()["sha"]
        
        # 11. Update ref
        r = await client.patch(
            f"{GITHUB_API}/repos/{owner}/{repo_name}/git/refs/heads/{default_branch}",
            headers=headers,
            json={"sha": new_commit_sha, "force": True},
        )
        if r.status_code != 200:
            return JSONResponse({"error": "Failed to update ref", "detail": r.text[:300]}, 400)
        
        return {
            "success": True,
            "repo": repo_data["full_name"],
            "url": repo_data["html_url"],
            "files_uploaded": len(tree_entries),
            "skipped": skipped[:20],
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
