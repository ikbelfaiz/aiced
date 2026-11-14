"""Run the S3 safety harness with S4's active-routing and post-commit rollback gates."""

import sys
from s3_rehearsal import main

if __name__ == "__main__":
    sys.argv.append("--s4")
    main()
