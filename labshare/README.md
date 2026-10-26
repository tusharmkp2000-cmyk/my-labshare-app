# LabShare

Notes and resource library for labs and classes. An admin uploads files; everyone can search and download them.
Each file is **encrypted (AES-256-GCM)**, **split into 1 MB chunks**, and stored on disk or in an S3-compatible bucket.

```
app.py        routes and logic        storage.py   disk / S3 backends
crypto.py     AES-256-GCM             templates/   pages        static/  CSS
setup.sh      local setup             run.sh       local start
render.yaml   Render blueprint        tests/       smoke tests
```

## Run locally
```bash
./setup.sh     # venv + packages + .env with random secrets
./run.sh       # http://localhost:5000
```

## Deploy on Render
1. Push this folder to a GitHub repo.
2. Render Dashboard > **New > Blueprint** > choose the repo > **Apply**.
3. When it is live, open the service > **Environment** and copy `ADMIN_PASSWORD`.
4. Visit your `*.onrender.com` URL > **Admin log in** > upload.

**Back up `LABSHARE_SECRET`.** It is the encryption key. If it is lost, stored files cannot be decrypted.

### Free plan
Free web services have no persistent disk, so files would vanish on restart. Use a free S3-compatible bucket
(for example Cloudflare R2) instead:
1. In `render.yaml` set `plan: free`, and delete the `disk:` block and the `DATA_DIR` variable.
2. Add env vars: `S3_BUCKET`, `S3_ENDPOINT`, `S3_KEY_ID`, `S3_SECRET`, `S3_REGION` (see `.env.example`).
Free services also sleep after inactivity, so the first visit can take about a minute.

## Notes
- Upload limit is 50 MB (`MAX_MB` in `app.py`). Allowed types are listed in `ALLOWED`.
- Test: `pip install pytest && pytest`.
- The original HDFS version is replaced by `storage.py`; the encrypt -> chunk -> reassemble flow is unchanged.
