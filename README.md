# nautobot-ansible-workshop — Stage 0: the disconnected baseline

The lab repository for the workshop *From Intent to Execution: Nautobot and Ansible, Better Together*.

**This is deliberately the "wrong" version.** A static inventory, `group_vars`, and a six-field survey — a setup that works and is obviously disconnected from the network's source of truth. Later stages dismantle it piece by piece:

| Stage | What it removes |
| --- | --- |
| Lab 1 | `inventory/static.ini` → Nautobot dynamic inventory |
| Lab 2 | `inventory/group_vars/` → Nautobot Config Contexts, and the survey |
| Lab 3 | one-way flow → playbooks write state back to Nautobot |
| Lab 4 | manual launch → Nautobot event fires a gated AWX workflow |

`playbooks/configure_base.yml` does **not** change across those stages. That's the point — keep it stable.

## Layout

```
nautobot-ansible-workshop/
├── ansible.cfg
├── clab/
│   └── workshop.clab.yml              # 2 × Arista cEOS
├── collections/
│   └── requirements.yml
├── inventory/
│   ├── static.ini
│   └── group_vars/
│       └── leaf.yml              # beside the inventory, NOT at repo root
├── playbooks/
│   └── configure_base.yml
└── templates/
    └── base.j2
```

> **`group_vars` placement is load-bearing.** Ansible resolves `group_vars/` relative to the inventory file's directory or the playbook's directory — never the repo root. Moved to the root, it is silently ignored and looks exactly like "my variables aren't applying."

## Quick start

### 1. Devices

```bash
docker import cEOSarm-lab-4.34.2F.tar.xz ceos:4.34.2F
sudo containerlab deploy -t clab/workshop.clab.yml
sudo containerlab inspect -t clab/workshop.clab.yml
```

Update `ansible_host` in `inventory/static.ini` to match the reported IPs.

### 2. Prove it locally — before AWX

This separates "is the playbook right?" from "can AWX reach the devices?" — two failure modes that are miserable to debug together.

```bash
ansible-galaxy collection install -r collections/requirements.yml

ansible -i inventory/static.ini leaf -m arista.eos.eos_facts -u admin -k

ansible-playbook -i inventory/static.ini playbooks/configure_base.yml -u admin -k --check --diff
```

Drop `--check` once the diff looks right.

> ⚠️ **Verify cEOS credentials.** ContainerLab cEOS nodes commonly come up `admin`/`admin`, but it varies by version and injected startup config. Confirm with `ssh admin@<node-ip>` before blaming Ansible.

### ⚠️ Seen once, cause unresolved: "Too many authentication failures"

> ```
> Failed to authenticate public key: Received SSH_MSG_DISCONNECT:
> 2:Too many authentication failures
> ```
>
> Hit once while building this; **went away on a retry after the password was re-entered**, so the real cause was never isolated. Two candidates, both plausible:
>
> 1. **A mistyped password.** Failed password attempts also count against
> `MaxAuthTries`, and can surface as "too many authentication failures."
> 2. **SSH key exhaustion.** The client offers every key in `~/.ssh` and
> `ssh-agent` before falling back to password; each offer burns one of the device's `MaxAuthTries` (OpenSSH default 6). `-k` supplies the password but does not stop keys being offered.
>
> The error text naming *public key* points at (2), but libssh error strings are not always precise about which method failed. **Try the password again first** — it's the cheaper hypothesis.
>
> **The repo already carries the (2) mitigation** — `look_for_keys = False` under `[paramiko_connection]` in `ansible.cfg`, plus `ansible_network_cli_ssh_type=paramiko` in the inventory. That's sound practice for `network_cli` regardless, so it stays, but treat it as precautionary rather than a proven fix.
>
> **If it recurs, disambiguate:**
>
> ```bash
> ssh-add -l                                   # how many keys are in play?
> SSH_AUTH_SOCK= ansible -i inventory/static.ini leaf -m arista.eos.eos_facts -u admin -k
> ```
>
> If hiding the agent is what makes it pass, it's key exhaustion.
>
> ⚠️ **`[ssh_connection] ssh_args` does NOT affect this** either way. `network_cli` uses paramiko/libssh, not OpenSSH, so `-o PubkeyAuthentication=no` there is ignored — the most common wrong turn on this error.
>
> **Lab design note:** worth pinning down before the lab guide is written. If it's key exhaustion, 60 attendees testing locally will meet it and the guide needs the workaround. If it was only a typo, the guide shouldn't carry a scary SSH section for a non-problem.

### 3. Push, then point AWX at it

```bash
git init && git add . && git commit -m "Stage 0: disconnected baseline"
gh repo create nautobot-ansible-workshop --public --source=. --push
```

Then in AWX, in this order: **Project** → **Inventory** → **Inventory Source** (*Sourced from a Project*, file `inventory/static.ini`) → **Machine Credential** → **Job Template** (playbook `playbooks/configure_base.yml`) → **Survey**.

Full walkthrough with field-by-field values: `../tutorial.md`, Stage 0d.

## Survey

Enable *Survey* on the Job Template and add these six. Every one is a fact Nautobot already knows — which is the argument the workshop makes.

| Prompt | Variable | Type | Default |
| --- | --- | --- | --- |
| Site name | `site_name` | Text | `DC1` |
| Primary NTP server | `ntp_primary` | Text | `10.0.0.1` |
| Secondary NTP server | `ntp_secondary` | Text | `10.0.0.2` |
| SNMP community | `snmp_community` | Text | `public` |
| DNS server | `dns_server` | Text | `10.0.0.53` |
| Syslog host | `syslog_host` | Text | `10.0.0.10` |

The playbook maps the flat survey answers onto the list-shaped template variables, falling back to `group_vars` when run locally without a survey. Survey answers arrive as extra_vars and outrank `group_vars` — an operator's typing beats the source of truth, which is exactly the problem being dramatized.

## Gotchas that cost real time

1. **AWX never reads files from your laptop.** Projects sync from Git. That's why the repo comes before the AWX objects.
2. **Galaxy credential.** AWX installs `collections/requirements.yml` only if the Project's Organization has a Galaxy credential attached (*Access → Organizations → Default → Galaxy Credentials*). Without it, sync succeeds, collections silently don't install, and the job dies with `couldn't resolve module/action 'arista.eos.eos_config'`.
3. **AWX pods must reach the devices.** AWX runs in Kubernetes; cEOS runs under ContainerLab — different Docker networks, no connectivity by default. Run both against the same Docker host, bridge the networks, and test from inside a pod before building AWX objects:
```bash
kubectl -n awx run nettest --rm -it --restart=Never --image=busybox -- ping -c3 172.20.20.11
```

## Lab shortcuts — do NOT carry into production

Single shared admin token · HTTP not HTTPS · no RBAC · no TLS on webhooks · `host_key_checking = False` · secrets in plain extra_vars where the workshop will use Nautobot Secrets Groups.
