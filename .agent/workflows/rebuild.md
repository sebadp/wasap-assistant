---
description: Rebuild the wasap Docker container after code changes
---

## Steps

1. Try the standard rebuild first:

```bash
docker compose up -d --build wasap
```

2. If the build fails with "Temporary failure resolving" (DNS issue on IPv6-only hosts), use `--network host`:

// turbo
```bash
docker build --network host -t wasap-wasap .
```

3. Then bring up the services:

**Without GPU:**
```bash
docker compose up -d
```

**With GPU NVIDIA:**
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

4. Verify the container is running:

// turbo
```bash
docker compose ps
```

5. Check logs:

// turbo
```bash
docker compose logs -f wasap
```
