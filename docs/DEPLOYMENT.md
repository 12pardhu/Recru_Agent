# Cloud deployment (Render)

1. Push this repository to GitHub (the project is hosted in `12pardhu/Recru_Agent`).
2. Sign in to Render and choose **New + → Blueprint**.
3. Connect the GitHub repository `12pardhu/Recru_Agent`.
4. Render detects `render.yaml`; review the service and create it.
5. After deployment, open the Render URL and confirm `/api/health` returns status `ok`.

Important: the included Render configuration is a starter deployment. The free instance's local filesystem may be ephemeral, so records may be lost on redeploy/restart. Configure a managed persistent database/storage before using operational data. Do not deploy publicly with real candidate data before adding authentication and access controls.
