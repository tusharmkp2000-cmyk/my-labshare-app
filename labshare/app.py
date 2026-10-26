"""LabShare - encrypted, chunked notes & resource library (Flask)."""
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timezone

from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_file, session, url_for)
from werkzeug.utils import secure_filename

from crypto import Vault, derive
from storage import make_store

CHUNK = 1024 * 1024  # 1 MB segments
MAX_MB = 50
ALLOWED = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "zip",
           "png", "jpg", "jpeg", "mp4"}

SECRET = os.environ.get("LABSHARE_SECRET")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not SECRET or not ADMIN_PASSWORD:
    raise RuntimeError("Set LABSHARE_SECRET and ADMIN_PASSWORD (see .env.example).")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=derive(SECRET, "session"),
    MAX_CONTENT_LENGTH=MAX_MB * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER") == "true",
)
vault = Vault(SECRET)
store = make_store()


# ---------- helpers ----------
def is_admin():
    return session.get("admin") is True


def meta_key(fid):
    return f"files/{fid}/meta.json"


def get_meta(fid):
    if not re.fullmatch(r"[0-9a-f]{12}", fid):
        abort(404)
    try:
        return json.loads(store.read(meta_key(fid)))
    except Exception:
        abort(404)


def all_meta():
    out = []
    for fid in store.list_dirs("files"):
        try:
            out.append(json.loads(store.read(meta_key(fid))))
        except Exception:
            continue  # half-written upload; ignore
    return sorted(out, key=lambda m: m["uploaded_at"], reverse=True)


def save_meta(m):
    store.write(meta_key(m["id"]), json.dumps(m).encode())


def save_chunks(fid, enc):
    parts = [enc[i:i + CHUNK] for i in range(0, len(enc), CHUNK)]
    for n, part in enumerate(parts):
        store.write(f"files/{fid}/chunk_{n:04d}", part)
    return len(parts)


def load_chunks(m):
    enc = b"".join(store.read(f"files/{m['id']}/chunk_{n:04d}") for n in range(m["chunks"]))
    if len(enc) != m["enc_size"]:
        raise RuntimeError("Reassembled size does not match - file is corrupted.")
    return enc


def count_download(m):
    m["downloads"] += 1
    save_meta(m)


@app.template_filter("fmt")
def fmt_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


@app.template_filter("hue")
def subject_hue(s):
    return int(hashlib.sha256(s.lower().encode()).hexdigest()[:4], 16) % 360


@app.context_processor
def inject():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return {"admin": is_admin(), "csrf": session["csrf"], "max_mb": MAX_MB}


@app.before_request
def csrf_check():
    if request.method == "POST":
        sent, real = request.form.get("csrf", ""), session.get("csrf", "")
        if not real or not hmac.compare_digest(real, sent):
            abort(400, "Form expired - go back, refresh and try again.")


@app.errorhandler(413)
def too_big(_):
    flash(f"File is larger than {MAX_MB} MB.", "error")
    return redirect(url_for("upload"))


# ---------- routes ----------
@app.route("/health")
def health():
    return "ok"


@app.route("/")
def home():
    q = request.args.get("q", "").strip().lower()
    subject = request.args.get("subject", "").strip()
    files = all_meta()
    subjects = sorted({m["subject"] for m in files})
    if q:
        files = [m for m in files if q in f"{m['title']} {m['subject']} {m['filename']}".lower()]
    if subject:
        files = [m for m in files if m["subject"] == subject]
    return render_template("home.html", files=files, subjects=subjects,
                           q=request.args.get("q", ""), subject=subject)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["admin"] = True
            flash("Logged in.")
            return redirect(url_for("upload"))
        flash("Wrong password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("home"))


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if not is_admin():
        return redirect(url_for("login"))
    if request.method == "POST":
        f = request.files.get("file")
        title = request.form.get("title", "").strip()[:120]
        subject = request.form.get("subject", "").strip()[:60]
        filename = secure_filename(f.filename or "") if f else ""
        if not (title and subject and filename):
            flash("Title, subject and a file are required.", "error")
            return redirect(url_for("upload"))
        if filename.rsplit(".", 1)[-1].lower() not in ALLOWED:
            flash("That file type is not allowed.", "error")
            return redirect(url_for("upload"))
        data = f.read()
        enc = vault.encrypt(data)
        fid = uuid.uuid4().hex[:12]
        try:
            chunks = save_chunks(fid, enc)
            save_meta({"id": fid, "title": title, "subject": subject, "filename": filename,
                       "size": len(data), "enc_size": len(enc), "chunks": chunks,
                       "uploaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                       "downloads": 0})
        except Exception as e:
            store.delete(f"files/{fid}")
            flash(f"Storage error: {e}", "error")
            return redirect(url_for("upload"))
        flash(f"Uploaded. Encrypted and stored as {chunks} chunk(s).")
        return redirect(url_for("home"))
    subjects = sorted({m["subject"] for m in all_meta()})
    return render_template("upload.html", subjects=subjects)


@app.route("/file/<fid>")
def details(fid):
    m = get_meta(fid)
    chunks = [c for c in store.list_keys(f"files/{fid}") if c[0].startswith("chunk_")]
    return render_template("details.html", f=m, chunks=chunks)


def _send(fid, decrypt):
    m = get_meta(fid)
    try:
        data = load_chunks(m)
        if decrypt:
            data = vault.decrypt(data)
    except Exception as e:
        flash(f"Download failed: {e}", "error")
        return redirect(url_for("details", fid=fid))
    count_download(m)
    name = m["filename"] if decrypt else m["filename"] + ".enc"
    return send_file(io.BytesIO(data), as_attachment=True, download_name=name)


@app.route("/download/<fid>")
def download(fid):
    return _send(fid, True)


@app.route("/download-enc/<fid>")
def download_enc(fid):
    return _send(fid, False)


@app.route("/delete/<fid>", methods=["POST"])
def delete(fid):
    if not is_admin():
        abort(403)
    get_meta(fid)
    store.delete(f"files/{fid}")
    flash("Deleted.")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
