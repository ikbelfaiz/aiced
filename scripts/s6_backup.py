"""S5 verified backup machinery extended to Commercial-owned objects."""

import s5_backup

if "aiced_commercial" not in s5_backup.SCHEMAS:
    s5_backup.SCHEMAS.append("aiced_commercial")
backup_restore = s5_backup.backup_restore
snapshot = s5_backup.snapshot
