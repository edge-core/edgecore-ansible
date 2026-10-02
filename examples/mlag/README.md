# MLAG provisioning example (Edge-core Enterprise Switch leaf pair)

A self-contained, variable-driven Ansible example you can copy and adapt to
provision **MLAG** on a pair of Edge-core Enterprise Switches (ECS series)
acting as leaves. It uses this project's own collection
(`ansible_network_os: edgecore.edgecos.edgecore`) and the generic
`ansible.netcommon.cli_command` module, and sends CLI line by line following the
same conventions as the rest of this project.

Everything here is **placeholder data** (lab IPs, generic names, no secrets).
Change the variables to match your site.

> MLAG command syntax can vary by switch model and firmware. Treat your device's
> CLI guide and the context-sensitive `?` help as the source of truth; adjust
> the keywords in `templates/mlag_config_lines.j2` if your model differs.

## What is MLAG?

MLAG (Multi-Chassis Link Aggregation) lets two physical switches present
themselves as one logical LAG peer to downstream devices. A dual-homed server
connects one link to each leaf; both links form a single port-channel, so the
server gets active/active bandwidth and survives the loss of either leaf. The two
leaves exchange state over a **peer-link** (here `port-channel 28`).

## Topology (sanitized)

```
            SPINE-A                         SPINE-B
              |  \                          /  |
              |   \                        /   |
   po4 (eth1/19-20) \                    / po5 (eth1/21-22)
              |      \                  /      |
         +----------+   peer-link po28   +----------+
         |  LEAF-1  |===(eth1/23-24)=====|  LEAF-2  |
         +----------+                    +----------+
            |  |  |                         |  |  |
            po1 po2 po3  (dual-homed)  po1 po2 po3
             \   |   /                   \   |   /
              SERVER-1 / SERVER-2 / SERVER-3
          (each server: one link to each leaf)
```

- **po1 / po2 / po3** — dual-homed servers (eth1/1-6), MLAG groups 1-3.
- **po4** — uplink to one spine (eth1/19-20).
- **po5** — uplink to the other spine (eth1/21-22).
- **po28** — peer-link between the two leaves (eth1/23-24).

### Per-leaf asymmetry (important)

Each leaf's two uplink port-channels reach **opposite** spines, so the MLAG
group → port-channel mapping is **swapped** between the leaves:

| MLAG group | LEAF-1 port-channel | LEAF-2 port-channel |
|------------|---------------------|---------------------|
| 1 (server) | 1                   | 1                   |
| 2 (server) | 2                   | 2                   |
| 3 (server) | 3                   | 3                   |
| 4 (uplink) | **4**               | **5**               |
| 5 (uplink) | **5**               | **4**               |

This swap lives in `host_vars/mlag_leaf01.yml` and `host_vars/mlag_leaf02.yml`
(the `port_channel` fields on groups 4 and 5). Everything else is shared.

## Files

| File | Purpose |
|------|---------|
| `inventory.yml` | The leaf pair (`mlag_leaf01`, `mlag_leaf02`) with placeholder IPs. |
| `ansible.cfg` | Points `collections_paths` at the bundled collection. |
| `group_vars/mlag_leaves.yml` | Connection settings + shared MLAG model (domain, peer-link, VLANs). |
| `host_vars/mlag_leaf01.yml` | LEAF-1 per-host data (mgmt IP + group→po mapping). |
| `host_vars/mlag_leaf02.yml` | LEAF-2 per-host data (swapped uplink mapping). |
| `templates/mlag_config_lines.j2` | Renders the CLI from the variables. |
| `site.yml` | Playbook: pre-check → render → apply line by line → save. |

## Variable → CLI mapping

| Variable | Generated CLI |
|----------|---------------|
| `mlag_vlans[*]` | `vlan database` / `VLAN <id> name <name> media ethernet` / `exit` |
| `mlag_groups[*].members` (server) | `interface <eth>` / `flowcontrol` / `no mac-learning` / `switchport allowed vlan add <native> untagged` / `switchport allowed vlan add <tagged> tagged` / `switchport native vlan <native>` / `switchport allowed vlan remove 1` / `spanning-tree spanning-disabled` / `channel-group <pc>` |
| `mlag_groups[*].members` (uplink) | adds `switchport mode trunk`, `vlan-trunking`, `no loopback-detection` |
| `mlag_peer_link.members` | `interface <eth>` / `no mac-learning` / `switchport allowed vlan add 1,<all_vlans> tagged` / `switchport mode trunk` / `spanning-tree spanning-disabled` / `no loopback-detection` / `channel-group 28` |
| `mlag_groups[*].port_channel`, `mlag_peer_link` | `interface port-channel <id>` / `description <...>` |
| `mlag_domain`, `mlag_peer_link.port_channel` | `mlag domain <name> peer-link port-channel <id>` |
| `mlag_groups[*]` | `mlag group <g> domain <name> member port-channel <pc>` |
| `mlag_mgmt_ip` (optional) | `interface vlan <mgmt> ` / `ip address <ip>` |
| `mlag_save_config` | `copy running-config startup-config` (with auto `[y/n]` answer) |

## What you must change to use this

1. **`inventory.yml`** — set `ansible_host` for each leaf to its real management IP.
2. **`group_vars/mlag_leaves.yml`** — set `ansible_user` / `ansible_password` /
   `ansible_become_password` (prefer **Ansible Vault**, see the main README
   Security section), and adjust `mlag_vlans` / `mlag_domain` as needed.
3. **`host_vars/mlag_leaf0{1,2}.yml`** — set `mlag_mgmt_ip` per leaf and confirm
   the groups 4/5 `port_channel` swap matches your cabling; adjust member ports,
   descriptions, and VLAN membership for your servers and uplinks.

## Prerequisites and collection setup

See the main project [README](../../README.md) for prerequisites (Python venv,
`ansible-core`, `ansible.netcommon`) and for how Ansible finds the
`edgecore.edgecos` collection and `ansible_network_os`. This example's
`ansible.cfg` already points `collections_paths` at the bundled `collection/`
directory, so running from this folder works out of the box within the repo.

## How to run

From this directory (`examples/mlag/`):

```bash
# 1) Syntax check (no device needed)
ansible-playbook site.yml --syntax-check

# 2) Preview the rendered CLI without changing anything
#    (reads run; connection to placeholder IPs will fail until you set real ones)
ansible-playbook site.yml --check --diff -vvv

# 3) Apply for real once inventory IPs and credentials are set
ansible-playbook site.yml
```

The playbook applies in order: VLANs → member/uplink/peer-link interfaces (with
`channel-group` binding) → port-channel descriptions → `mlag domain` + `mlag
group` bindings → optional management SVI → save.
