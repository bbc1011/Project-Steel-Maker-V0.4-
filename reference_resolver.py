from pathlib import Path

def resolve_reference_ids(
    brickognize,
    reference_paths,
    explicit_ids=None,
):
    wanted = set(str(x) for x in (explicit_ids or []) if x)
    resolved = []

    for path in reference_paths or []:
        p = Path(path)
        if not p.exists():
            resolved.append({
                "path": path,
                "status": "missing",
            })
            continue

        try:
            result = brickognize.identify_file(p)
            best = brickognize.best_candidate(result)

            if not best or not best.get("bricklink_id"):
                resolved.append({
                    "path": path,
                    "status": "unidentified",
                })
                continue

            wanted.add(str(best["bricklink_id"]))
            resolved.append({
                "path": path,
                "status": "identified",
                "bricklink_id": best["bricklink_id"],
                "name": best.get("name"),
                "score": best.get("score"),
            })

        except Exception as exc:
            resolved.append({
                "path": path,
                "status": "error",
                "error": str(exc),
            })

    return wanted, resolved
