# Dockerfile for Claudonomous
# Build: docker build -t claudonomous .
# Run: docker run -v /project:/workspace -e ANTHROPIC_API_KEY claudonomous "task"

FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    nodejs \
    npm \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for safety
RUN useradd -m -s /bin/bash claude
USER claude
WORKDIR /home/claude

# Install claudonomous
COPY --chown=claude:claude . /home/claude/claudonomous
RUN pip install --user --no-cache-dir /home/claude/claudonomous

# Add local bin to PATH
ENV PATH="/home/claude/.local/bin:${PATH}"

# Workspace will be mounted here
WORKDIR /workspace

# Set git config for commits
RUN git config --global user.email "claude@claudonomous.local" \
    && git config --global user.name "Claudonomous"

# Entrypoint
ENTRYPOINT ["python", "-m", "claudonomous"]
CMD ["--help"]
