\# Azure 2-Tier Infrastructure Notes



\## Resource Group

\- Name: ram-demo-rg-dont-delete

\- Subscription: MSDN Platforms Subscription

\- Region: East US



\## Virtual Network

\- Name: vm-2tier-test-vnet

\- Address space: 10.0.0.0/16



\### Subnets

| Name | CIDR | Purpose | NAT Gateway |

|---|---|---|---|

| default | 10.0.0.0/24 | Original test subnet (DB VM lives here) | No |

| subnet-public | 10.0.1.0/24 | Jump servers | No (has public IPs directly) |

| subnet-private-app | 10.0.2.0/24 | Future VMSS/app tier | Yes |

| subnet-private-data | 10.0.3.0/24 | Reserved for future DB migration | Yes |



\## NAT Gateway

\- Name: natgw-2tier-prod

\- Public IP: natgw-2tier-prod-ip

\- Attached to: subnet-private-app, subnet-private-data



\## Virtual Machines

\### vm-2tier-db

\- Purpose: MySQL 8 database (self-managed, since Azure Database for MySQL Flexible Server was blocked on this subscription/region)

\- Subnet: default (10.0.0.0/24)

\- Private IP: 10.0.0.5

\- MySQL DB: appdb, user: appuser

\- NSG rule: allows port 3306 only from 10.0.0.4/32 (the original test VM's IP)



\### jump-linux

\- Purpose: Jump server / bastion for accessing private subnet resources

\- Subnet: subnet-public (10.0.1.0/24)

\- Auth: SSH public key (vm-2tier-test\_key)

\- Access pattern: SSH with agent forwarding (`ssh -A`) to reach private VMs



\## Golden Image

\- Name: img-2tier-signup-app-v1

\- Built from: vm-2tier-test (Ubuntu 24.04, nginx + gunicorn + Flask app, systemd service "signup-app")

\- vm-2tier-test was deleted after capture (Step 8)



\## SSH Key

\- Name: vm-2tier-test\_key

\- Stored locally at: \~/.ssh/vm-2tier-test\_key.pem

\- Reused across vm-2tier-test, vm-2tier-db, jump-linux



\## App Database Connection (systemd env vars on web VM)

\- DB\_HOST=10.0.0.5

\- DB\_USER=appuser

\- DB\_NAME=appdb

\- (DB\_PASSWORD stored only on the VM's systemd service file, not committed here)

## NAT Gateway (added Step 9)
- Name: natgw-2tier-prod
- Public IP: natgw-2tier-prod-ip
- Attached to: subnet-private-app, subnet-private-data
- Note: NAT Gateways cannot be stopped/deallocated - incurs small fixed hourly cost as long as it exists

## Jump Server (added Step 9)
### jump-linux
- Purpose: Bastion host for accessing private subnet resources
- Subnet: subnet-public (10.0.1.0/24)
- Auth: SSH public key (vm-2tier-test_key, reused)
- Access pattern: connect with `ssh -A` (agent forwarding) from laptop, then
  `ssh azureuser@10.0.0.5` from inside jump-linux to reach vm-2tier-db privately
- Windows jump server was considered but skipped for now (kept VM count minimal)

## Storage Account (Step 10, Part A)
- Name: storage2tier
- Purpose: Boot diagnostics for VMs/VMSS
- Type: StorageV2, Standard, LRS
- Region: East US

## Open decision (Step 10, Part B - not yet resolved)
- VMSS instances in subnet-private-app will need DB access
- Choice pending: NSG rule allowing subnet-private-app range (10.0.2.0/24) 
  vs. Application Security Groups (ASG) for more precise access control
- Current DB NSG rule only allows 10.0.0.4/32 (the now-deleted original test VM)

