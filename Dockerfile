# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy pyproject.toml
COPY pyproject.toml .

# Install Python dependencies using pyproject.toml
RUN pip install --no-cache-dir .

# Copy the rest of the MCP server files
COPY . .

EXPOSE 8000

ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000

# Run the server
CMD ["python", "diffbot_mcp_server.py"]
