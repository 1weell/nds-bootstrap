# v7.3 upstream-based port

Base: DS-Homebrew/nds-bootstrap 6f3d23ffedf9266badbca7ecda96c15c0f778a50.
The original RA repository began as a separate import. Sources are ported as a
snapshot. Updating to current upstream requires review; preserve licenses.

Validated in this checkout: clean Wi-Fi 0/2 builds, host suite, IGM/graphics ABI,
and ARM11 builder hash matching hardware-tested v7.3. The new NDS build was not
independently tested on hardware. Never commit Nintendo firmware, CXI, ROMs,
saves or credentials.

Upstream AI policy requires most contributed code be written by hand, manual
refinement/testing, and disclosure of AI assistance in a PR. This AI-assisted
snapshot cannot be assumed eligible as-is. Discuss with upstream and perform
required human authorship/review before proposing contributions.
https://github.com/DS-Homebrew/nds-bootstrap/blob/master/AI-GUIDELINES.md

Wi-Fi test fixtures are synthetic and omit network identifiers and captured authentication metadata.
