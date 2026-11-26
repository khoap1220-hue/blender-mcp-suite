FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE blender_mcp_launcher.py ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV BLENDER_SKIP_PREFLIGHT="1"
ENTRYPOINT ["blender-mcp"]
