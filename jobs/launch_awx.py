"""Stage 3a — launch an AWX Job Template from a Nautobot device page.

WHY A NAUTOBOT JOB AND NOT A CUSTOM LINK
----------------------------------------
A Custom Link is a templated URL: two minutes of work, and it just deep-links
the operator into AWX's launch form. Fine, but it teaches nothing about Nautobot
and leaves no record on the Nautobot side.

A Job Button runs a real Nautobot **Job** — Nautobot's own automation engine.
That matters for this workshop specifically, because the closing segment argues
that AWX is sometimes the wrong tool and Nautobot Jobs the right one. It is a
much more honest argument if attendees have actually run one.

What a Job gives you that a Custom Link does not:
  * server-side logic with the full Nautobot ORM in scope
  * a JobResult with logs, retained and searchable
  * RBAC on who may press the button
  * the ability to validate or enrich before anything reaches AWX

Verified against Nautobot 3.2.2 source:
  JobButtonReceiver, register_jobs -> exported from nautobot.apps.jobs
  subclasses implement receive_job_button(self, obj)
  logging is standard `self.logger`

CONFIGURATION (environment variables on the Nautobot worker):
  AWX_HOST           http://host.docker.internal:8013   <- NOT localhost, see below
  AWX_TOKEN          an AWX OAuth2 token
  AWX_JOB_TEMPLATE   name of the Job Template to launch

All three are written by playbooks/seed_awx.yml into
environments/creds.env, which is one of the two files
(local.env, creds.env) that nautobot-docker-compose's `x-nautobot-base` anchor
loads into nautobot, celery_worker and celery_beat. Do not invent a third env
file — nothing reads it, and the failure surfaces only when a Job Button is
clicked. Changing the file requires the containers to be RECREATED
(`invoke stop && invoke start`); `invoke restart` is docker compose restart,
which reuses the container and its original environment.

⚠️ AWX_HOST must be reachable FROM THE CELERY WORKER CONTAINER — this Job runs
there, not in the web container. Nautobot runs in docker-compose, AWX in minikube
behind a port-forward on the host, so `localhost:8013` resolves to the worker
container itself and will fail.

Use `host.docker.internal`, which requires this on BOTH the nautobot and
celery_worker services in environments/docker-compose.local.yml:

    extra_hosts:
      - "host.docker.internal:host-gateway"

Do NOT hardcode a bridge gateway such as 172.17.0.1. That is the docker0 address;
Nautobot's compose network gets its own, and which /16 it lands on depends on
Docker network creation order — measured 172.18.0.1 on the validation VM. Since
this value is stored in the Job Button config on every attendee stack, a per-host
address breaks Lab 3 on an unpredictable subset.

⚠️ The port-forward must be started with `--address 0.0.0.0`. The default binds
127.0.0.1 only, which no container can reach.

⚠️ The target Job Template needs "Prompt on launch" enabled for Variables
(`ask_variables_on_launch: true`), otherwise AWX silently discards the extra_vars
this Job sends.
"""

import os

import requests

from nautobot.apps.jobs import JobButtonReceiver, register_jobs

# Groups these jobs together in the Nautobot Jobs list.
name = "Nautobot Ansible Workshop"

DEFAULT_TIMEOUT = 15


class LaunchAWXJobTemplate(JobButtonReceiver):
    """Launch an AWX Job Template for the device whose page this button is on."""

    class Meta:
        name = "Launch AWX job for this device"
        description = (
            "Posts to the AWX API to launch a Job Template, passing this device "
            "as extra_vars. Returns the AWX job ID and a direct link."
        )

    def receive_job_button(self, obj):
        awx_host = os.getenv("AWX_HOST", "").rstrip("/")
        awx_token = os.getenv("AWX_TOKEN", "")
        template_name = os.getenv("AWX_JOB_TEMPLATE", "Configure Dynamic Group members")

        if not awx_host or not awx_token:
            self.logger.failure(
                "AWX_HOST and AWX_TOKEN must be set on the Nautobot worker. "
                "Remember AWX_HOST must be reachable from inside the Nautobot "
                "container — localhost will not work."
            )
            return

        headers = {
            "Authorization": f"Bearer {awx_token}",
            "Content-Type": "application/json",
        }

        # Look the template up by name rather than hardcoding a numeric ID, so
        # this survives a rebuilt AWX.
        self.logger.info("Looking up AWX Job Template %r", template_name)
        try:
            lookup = requests.get(
                f"{awx_host}/api/v2/job_templates/",
                params={"name": template_name},
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
            )
            lookup.raise_for_status()
        except requests.RequestException as exc:
            self.logger.failure("Could not reach AWX at %s: %s", awx_host, exc)
            return

        results = lookup.json().get("results", [])
        if len(results) != 1:
            self.logger.failure(
                "Expected exactly one AWX Job Template named %r, found %d.",
                template_name,
                len(results),
            )
            return

        template = results[0]
        template_id = template["id"]

        # Everything AWX needs to act on this specific device. The playbook can
        # use device_name directly; device_id is the Nautobot UUID, handy for
        # writing results back.
        payload = {
            "extra_vars": {
                "device_name": obj.name,
                "device_id": str(obj.pk),
                "device_location": str(obj.location.name) if obj.location else "",
                "triggered_from": "nautobot-job-button",
            }
        }

        self.logger.info("Launching AWX Job Template %s (id=%s)", template_name, template_id)
        try:
            launch = requests.post(
                f"{awx_host}/api/v2/job_templates/{template_id}/launch/",
                json=payload,
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
            )
            launch.raise_for_status()
        except requests.RequestException as exc:
            body = getattr(exc.response, "text", "")
            self.logger.failure("AWX rejected the launch: %s %s", exc, body)
            return

        job = launch.json()
        job_id = job.get("id")
        job_url = f"{awx_host}/#/jobs/playbook/{job_id}"

        self.logger.info("AWX job **%s** launched for %s: %s", job_id, obj.name, job_url)
        self.logger.info(
            "Extra vars sent: %s",
            ", ".join(f"{k}={v}" for k, v in payload["extra_vars"].items()),
        )

        # Returned values appear in the JobResult, so the operator sees the AWX
        # job id without digging through the log.
        return f"AWX job {job_id} launched for {obj.name}"


register_jobs(LaunchAWXJobTemplate)
