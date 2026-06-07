# NVR Pro — Decision Log
# Every deviation from SPEC.md, every architectural choice, every "we decided to..."
# must be logged here with a date, rationale, and who decided.
# Reference format in commits: "per DECISION-001"

---

## How to add an entry

Copy the template below, fill it in, append to this file.

```
## DECISION-XXX — [Short title]
Date: YYYY-MM-DD
Decided by: [name / "team"]
Status: ACCEPTED | SUPERSEDED | REVERTED

### Context
What situation made this decision necessary?

### Decision
What was decided?

### Rationale
Why this option over alternatives?

### Consequences
What changes as a result? What becomes harder or easier?

### Supersedes / Superseded by
[DECISION-YYY] or "n/a"
```

---

## DECISION-001 — Use RS256 (asymmetric JWT) instead of HS256

Date: 2026-06-03
Decided by: initial architecture
Status: ACCEPTED

### Context
JWT signing algorithm must be chosen at the start. Both HS256 and RS256 are common.

### Decision
Use RS256 with a 2048-bit RSA key pair generated at first boot.

### Rationale
RS256 allows any service to verify tokens using only the public key, without 
access to the signing secret. This enables future service decomposition (e.g., 
a separate media server could verify tokens without sharing the secret).
It also eliminates the risk of secret leakage through shared config.

### Consequences
Slightly more complex setup (key generation script required). 
Tokens are slightly larger. No practical performance difference at our scale.

### Supersedes / Superseded by
n/a

---

## DECISION-002 — argon2 over bcrypt for password hashing

Date: 2026-06-03
Decided by: initial architecture
Status: ACCEPTED

### Context
OWASP password storage recommendations updated in 2023.

### Decision
Use argon2-cffi with time_cost=2, memory_cost=65536, parallelism=2.

### Rationale
argon2id is the current OWASP recommendation, winning the Password Hashing 
Competition in 2015. More memory-hard than bcrypt, making GPU cracking harder.
argon2-cffi is a mature, well-maintained Python binding.

### Consequences
Requires argon2-cffi in requirements. Slightly slower hashing (intentional).
Existing systems that used bcrypt cannot migrate hashes without user re-login.

### Supersedes / Superseded by
n/a

---

## DECISION-003 — FFmpeg via direct subprocess, not ffmpeg-python

Date: 2026-06-03
Decided by: initial architecture
Status: ACCEPTED

### Context
Two Python options for FFmpeg: subprocess directly or the ffmpeg-python library.

### Decision
Use subprocess.Popen directly with explicitly built command lists.

### Rationale
ffmpeg-python adds an abstraction layer that complicates debugging when FFmpeg 
crashes (which it will, often, with RTSP streams). Direct subprocess gives us 
full control over stderr parsing, process signals, and command construction.
The FFmpeg command strings are documented and readable as-is.

### Consequences
More verbose command building code. But: complete control, easier debugging,
no dependency on a third-party FFmpeg wrapper that may not support all FFmpeg flags.

### Supersedes / Superseded by
n/a

---

## [Add new decisions below this line]
