# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# The package sources must be present for pip to build the project, so copy them
# before installing rather than only pyproject.toml
COPY pyproject.toml README.md diffbot_mcp_server.py ./
COPY diffbot_mcp ./diffbot_mcp

# Install the server and its pinned dependencies
RUN pip install --no-cache-dir .

# Copy the rest of the MCP server files
COPY . .

EXPOSE 8000

ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000

# Run the server
CMD ["python", "diffbot_mcp_server.py"]
