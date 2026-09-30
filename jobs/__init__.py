"""Nautobot Jobs for the Nautobot + Ansible workshop.

Nautobot discovers Jobs from a Git Repository that provides "jobs" by importing
the top-level `jobs/` package (verified in Nautobot 3.2.2:
`nautobot/extras/datasources/git.py` checks for a `jobs/` directory or a
`jobs.py` file at the repository root).

Since Nautobot 2.0, Jobs must be explicitly registered with `register_jobs()`.
Each module here does its own registration, so importing it is enough.

TO LOAD THESE INTO NAUTOBOT
---------------------------
Extensibility -> Git Repositories -> Add:
  Name:                 nautobot-ansible-workshop
  Remote URL:           <this repo's HTTPS clone URL>
  Provides:             jobs
Then Sync. The jobs appear under Jobs, grouped as "Nautobot Ansible Workshop", and must be
**enabled** before they can run.
"""

from . import launch_awx  # noqa: F401  (import registers the job)

__all__ = ("launch_awx",)
