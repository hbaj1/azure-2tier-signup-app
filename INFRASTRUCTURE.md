# Azure 2-Tier Infrastructure Notes

## Resource Group
- Name: ram-demo-rg-dont-delete
- Subscription: MSDN Platforms Subscription
- Region: East US

## Virtual Network
- Name: vm-2tier-test-vnet
- Address space: 10.0.0.0/16

### Subnets
| Name | CIDR | Purpose | NAT Gateway |
|---|---|---|---|
| default | 10.0.0.0/24 | Original test subnet (DB VM lives here) | No |
| subnet-public | 10.0.1.0/24 | Jump servers | No (has public IPs directly) |
| subnet-private-app | 10.0.2.0/24 | VMSS/app tier | Yes |
| subnet-private-data | 10.0.3.0/24 | Reserved for future DB migration | Yes |

## NAT Gateway
- Name: natgw-2tier-prod
- Public IP: natgw-2tier-prod-ip
- Attached to: subnet-private-app, subnet-private-data
- Note: NAT Gateways cannot be stopped/deallocated - incurs small fixed hourly cost as long as it exists

## Virtual Machines

### vm-2tier-db
- Purpose: MySQL 8 database (self-managed, since Azure Database for MySQL Flexible Server was blocked on this subscription/region)
- Subnet: default (10.0.0.0/24)
- Private IP: 10.0.0.5
- MySQL DB: appdb, user: appuser

### NSG Rules (vm-2tier-db-nsg)
- **Current:** Allow-MySQL-From-AppSubnet - allows port 3306 (TCP) from 
  10.0.2.0/24 (subnet-private-app). Priority 200. Added when VMSS was 
  introduced, since VMSS instances have dynamic IPs, not one fixed address.
- **Retired:** Allow-MySQL-From-WebVM - allowed port 3306 only from 
  10.0.0.4/32 (the original vm-2tier-test's fixed IP). Removed after 
  vm-2tier-test was deleted (Step 8) and replaced by VMSS (Step 10).

### jump-linux
- Purpose: Jump server / bastion for accessing private subnet resources
- Subnet: subnet-public (10.0.1.0/24)
- Auth: SSH public key (vm-2tier-test_key, reused)
- Access pattern: connect with `ssh -A` (agent forwarding) from laptop, then
  `ssh azureuser@10.0.0.5` from inside jump-linux to reach vm-2tier-db privately
- Windows jump server was considered but skipped for now (kept VM count minimal)

## Storage Account
- Name: storage2tier
- Purpose: Boot diagnostics for VMs/VMSS
- Type: StorageV2, Standard, LRS
- Region: East US

## VM Scale Set (Step 10, Part B)
- Name: vmss2tierapp
- Orchestration mode: Uniform
- Image: img-2tier-signup-app-v1 (golden image)
- Size: Standard B1s
- Scaling: Autoscale, min 2 / max 5 / default 2, CPU-based (default 80%/20% thresholds)
- Subnet: subnet-private-app (10.0.2.0/24) - no public IPs
- Load balancing: None at creation - Application Gateway to be attached separately (Step 11)
- Boot diagnostics: custom storage account -> storage2tier
- Auth: SSH public key (vm-2tier-test_key, reused)
- Upgrade mode: Manual

## Golden Image
- Name: img-2tier-signup-app-v1
- Built from: vm-2tier-test (Ubuntu 24.04, nginx + gunicorn + Flask app, systemd service "signup-app")
- vm-2tier-test was deleted after capture (Step 8)

## SSH Key
- Name: vm-2tier-test_key
- Stored locally at: ~/.ssh/vm-2tier-test_key.pem
- Reused across vm-2tier-test, vm-2tier-db, jump-linux, vmss2tierapp

## App Database Connection (systemd env vars on web VM - now VMSS instances)
- DB_HOST=10.0.0.5
- DB_USER=appuser
- DB_NAME=appdb
- (DB_PASSWORD stored only on the VM's systemd service file, not committed here)

## Decisions Log
- DB access for VMSS: chose subnet-range NSG rule (10.0.2.0/24) over 
  Application Security Groups, due to time constraints while awaiting 
  trainer's input. ASGs remain a good future hardening step (more precise, 
  scoped to just VMSS instances rather than the whole subnet).