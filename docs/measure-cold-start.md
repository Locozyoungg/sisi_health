# Cold-start measurement (spec 5.1: <3s on a low-end reference device)

Phase 2 ships the budget procedurally; the measurement itself needs a real
device or emulator (assumption A17) and runs as part of Phase 8 hardening.

## Procedure (adb, device attached)

```bash
adb shell am force-stop com.sisi.health
# 5 runs, report the median
for i in 1 2 3 4 5; do
  adb shell am start -W -n com.sisi.health/.MainActivity \
    | grep TotalTime
done
```

`TotalTime` is the full launch (process start → first frame). Budget: median
< 3000 ms on a reference low-end device (2 GB RAM class, e.g. Tecno Spark-class).

## Why the budget is structurally safe already

- Application.onCreate schedules two WorkManager jobs and creates one
  NotificationChannel — no network, no DB open, no crypto on the launch path.
- The DB (SQLCipher) opens lazily on first diary access.
- Release builds are R8-minified; Compose runs without reflection at runtime.
