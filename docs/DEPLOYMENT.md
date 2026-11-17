# Render deployment

1. Repository: https://github.com/12pardhu/Recru_Agent
2. Render dashboard → existing Blueprint/service.
3. GitHub pushes to main trigger a deployment if auto-deploy is enabled; otherwise use Manual Deploy → Deploy latest commit.
4. Wait for deployment to finish, then check https://recru-agent.onrender.com/api/health and open the service URL.

The Render free filesystem may be ephemeral. Do not use this for operational candidate records until managed persistent storage/database and backups are configured.