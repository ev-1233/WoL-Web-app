# Deployment and Release Guide

## Overview

This project supports 3 distribution methods:
1. **Docker Image** - Automated builds pushed to Docker Hub
2. **Standalone Executables** - PyInstaller binaries for Linux, Windows, and macOS
3. **git source code** - For people who need to tweak code

Both are automatically built and released via GitHub Actions when you push a version tag.

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
- **Docker Hub:** https://hub.docker.com/r/ev1233/wol-gateway/tags
- **GitHub Releases:** https://github.com/ev-1233/wol-gateway/releases

Test the Docker image:
```bash
docker pull ev1233/wol-gateway:latest
docker run --rm ev1233/wol-gateway:latest python3 -c "from version import __version__; print(__version__)"
```

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