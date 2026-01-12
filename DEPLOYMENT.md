# Deployment and Release Guide

## Overview

This project supports two distribution methods:
1. **Docker Image** - Automated builds pushed to Docker Hub
2. **Standalone Executables** - PyInstaller binaries for Linux, Windows, and macOS

Both are automatically built and released via GitHub Actions when you push a version tag.

## Prerequisites

### One-Time Setup

1. **Update version.py with your GitHub repository:**
   ```python
   __github_repo__ = "ev-1233/WoL-Web-app" 
   ```

2. **Set up Docker Hub:**
   - Create account at https://hub.docker.com
   - Create repository: `ev1233/wol-web-app`
   - Generate access token: Account Settings → Security → New Access Token

3. **Configure GitHub Secrets:**
   Go to: GitHub repo → Settings → Secrets and variables → Actions
   
   Add these secrets:
   - `DOCKER_USERNAME`: Your Docker Hub username
   - `DOCKER_PASSWORD`: Your Docker Hub access token

4. **Update workflow file:**
   Edit `.github/workflows/release.yml`:
   ```yaml
   env:
     DOCKER_IMAGE: yourusername/wol-gateway  # Change this!
   ```

## Making a Release

### 1. Update Version

Edit `version.py`:
```python
__version__ = "1.0.1"  # Increment version
```

Commit the change:
```bash
git add version.py
git commit -m "Bump version to 1.0.1"
git push
```

### 2. Create and Push Tag

```bash
# Create annotated tag
git tag -a v1.0.1 -m "Release v1.0.1"

# Push tag to trigger build
git push origin v1.0.1
```

### 3. Automated Build Process

GitHub Actions will automatically:
- ✅ Build executables for Linux, Windows, and macOS
- ✅ Build Docker image for amd64 and arm64
- ✅ Push to Docker Hub with tags: `:latest` and `:1.0.1`
- ✅ Create GitHub Release with downloadable executables
- ✅ Generate release notes

Monitor progress: GitHub repo → Actions tab

### 4. Verify Release

Check that everything worked:
- **Docker Hub:** https://hub.docker.com/r/yourusername/wol-gateway/tags
- **GitHub Releases:** https://github.com/yourusername/wol-gateway/releases

Test the Docker image:
```bash
docker pull yourusername/wol-gateway:latest
docker run --rm yourusername/wol-gateway:latest python3 -c "from version import __version__; print(__version__)"
```

## How Updates Work for Users

### Docker Users

When running in Docker, the container:
- ✅ Detects it's in Docker (via `is_running_in_docker()`)
- ✅ Skips Docker installation prompts
- ✅ Skips dependency installation (pre-installed in image)
- ✅ **Does NOT check for updates** (users manually pull new images)

Users update by:
```bash
docker pull yourusername/wol-gateway:latest
docker compose down && docker compose up -d
```

### Executable Users

When running the standalone executable:
- ✅ Checks GitHub for newer version on startup
- ✅ Shows update notification with download link
- ✅ **Does NOT auto-update** (user downloads manually)
- ✅ Can still install/configure Docker if desired

Users see:
```
===========================================================
🔔  UPDATE AVAILABLE!
===========================================================
  Current version: 1.0.0
  Latest version:  1.0.1

  Download: https://github.com/yourusername/wol-gateway/releases/latest
===========================================================
```

## Distribution Methods Compared

| Method | Installation | Updates | Dependencies | Best For |
|--------|-------------|---------|--------------|----------|
| **Docker** | Pull image | Manual pull | Pre-installed | Servers, consistent deployment |
| **Executable** | Download & run | Manual download | Bundled | Non-technical users, quick setup |
| **Direct** | Git clone + setup | Git pull | Auto-installed | Developers, customization |

## Testing Before Release

### Local Docker Build
```bash
cd .docker
docker build -t wol-gateway:test -f Dockerfile ..
docker run --rm -it wol-gateway:test python3 -c "from version import __version__; print(__version__)"
```

### Local PyInstaller Build
```bash
pip install pyinstaller flask
pyinstaller --onefile --name wol-gateway-test setup_wol.py
./dist/wol-gateway-test
```

## Troubleshooting

### GitHub Actions fails?
- Check Docker Hub credentials in GitHub Secrets
- Verify repository name matches in workflow file
- Check Actions tab for detailed error logs

### Docker image too large?
- Current size: ~150MB (Python slim + Flask + wakeonlan)
- Consider Alpine base if size is critical (adds complexity)

### Executables too large?
- Current size: ~50-100MB per platform
- This is normal for PyInstaller (bundles Python interpreter)
- Can't reduce significantly without compromising compatibility

### Update checker not working?
- Verify `__github_repo__` in version.py is correct
- Check internet connectivity
- API rate limits (60 requests/hour for unauthenticated)

## Version Numbering

Use semantic versioning: `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes (e.g., config file format change)
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes only

Examples:
- `v1.0.0` → Initial release
- `v1.1.0` → Added multi-server support
- `v1.1.1` → Fixed MAC address validation bug
- `v2.0.0` → Changed config file format (breaking)

## Quick Reference

```bash
# Release workflow
vim version.py              # Update version
git add version.py
git commit -m "Bump to X.Y.Z"
git push
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
# Wait for Actions to complete
```

## Security Note

The Docker image runs as root by default (required for host networking and privileged ports). If you configure it to use a port ≥ 1024, uncomment the non-root user lines in the Dockerfile.
