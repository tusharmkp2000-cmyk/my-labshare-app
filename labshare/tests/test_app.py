import io
import os
import re
import sys
import tempfile

os.environ.update(LABSHARE_SECRET="test-secret", ADMIN_PASSWORD="pw", DATA_DIR=tempfile.mkdtemp())
os.environ.pop("S3_BUCKET", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as labshare  # noqa: E402


def token(c, url):
    html = c.get(url).get_data(as_text=True)
    return re.search(r'name="csrf" value="(\w+)"', html).group(1)


def login(c):
    c.post("/login", data={"password": "pw", "csrf": token(c, "/login")})


def test_upload_requires_admin():
    assert labshare.app.test_client().get("/upload").status_code == 302


def test_wrong_password_and_csrf():
    c = labshare.app.test_client()
    assert c.post("/login", data={"password": "pw"}).status_code == 400
    c.post("/login", data={"password": "bad", "csrf": token(c, "/login")})
    assert c.get("/upload").status_code == 302


def test_roundtrip_chunks_search_delete():
    c = labshare.app.test_client()
    login(c)
    payload = os.urandom(2_500_000)  # more than 2 chunks
    r = c.post("/upload", data={"title": "Big", "subject": "Maths", "csrf": token(c, "/upload"),
                                "file": (io.BytesIO(payload), "big.zip")},
               content_type="multipart/form-data")
    assert r.status_code == 302
    m = labshare.all_meta()[0]
    assert m["chunks"] == 3 and m["size"] == len(payload)
    assert c.get(f"/download/{m['id']}").data == payload
    enc = c.get(f"/download-enc/{m['id']}").data
    assert enc != payload and len(enc) == m["enc_size"]
    assert labshare.get_meta(m["id"])["downloads"] == 2
    assert b"Big" in c.get("/?q=big").data and b"Big" not in c.get("/?q=zzz").data
    c.post(f"/delete/{m['id']}", data={"csrf": token(c, f"/file/{m['id']}")})
    assert labshare.all_meta() == []


def test_bad_type_and_bad_id():
    c = labshare.app.test_client()
    login(c)
    c.post("/upload", data={"title": "x", "subject": "y", "csrf": token(c, "/upload"),
                            "file": (io.BytesIO(b"hi"), "evil.exe")}, content_type="multipart/form-data")
    assert labshare.all_meta() == []
    assert c.get("/file/..%2F..%2Fetc").status_code == 404
