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
| subnet-appgw | 10.0.4.0/24 | Application Gateway (dedicated, required by Azure) | No |

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

## VM Scale Set
- Name: vmss2tierapp
- Orchestration mode: Uniform
- Image: img-2tier-signup-app-v2 (golden image, current)
- Size: Standard B1s
- Scaling: Autoscale, min 2 / max 5 / default 2, CPU-based (default 80%/20% thresholds)
- Subnet: subnet-private-app (10.0.2.0/24) - no public IPs
- Load balancing: Application Gateway attached (Step 11) - see below
- Boot diagnostics: custom storage account -> storage2tier
- Auth: SSH public key (vm-2tier-test_key, reused)
- Upgrade mode: Manual

## Golden Image
- Name: img-2tier-signup-app-v2 (current)
- Built from: vm-2tier-test-v1 (Ubuntu 24.04, nginx + gunicorn + Flask app 
  installed in /opt/azure-2tier-signup-app, systemd service "signup-app" 
  with DB env vars baked in directly)
- vm-2tier-test-v1 was deleted after capture

### Bug found and fixed
- v1 image (built from original vm-2tier-test) was broken: app files lived 
  in /home/azureuser/, which gets wiped by `waagent -deprovision+user -force` 
  during generalization. Result: VMSS instances booted with nginx running 
  but no app/venv/gunicorn, causing 502 Bad Gateway (systemd status 203/EXEC).
- Fix: rebuilt the VM (vm-2tier-test-v1) with app in /opt/azure-2tier-signup-app 
  instead - this path survives deprovisioning since it's not tied to a user account.
- v1 image, its source VM, and the original VMSS built on it were all deleted 
  after v2 was confirmed working end-to-end (signup -> DB write verified).

## Application Gateway (Step 11-12)
- Name: appgw-2tier-prod
- Tier: Standard V2, autoscaling disabled, fixed instance count 2
- Subnet: subnet-appgw (10.0.4.0/24) - dedicated subnet, required by Azure
  (App Gateway cannot share a subnet with any other resource)
- Frontend: Public IP appgw-2tier-ip (20.232.236.118)
- Backend pool: backend-pool-vmss -> target type VMSS -> vmss2tierapp
- Backend settings: backend-settings-http, HTTP, port 80
- Health probe: probe-healthz, path /healthz, host set manually to one 
  instance's IP due to a Portal UI quirk (see note below) - in a correct 
  setup, "pick host name from backend settings: Yes" makes App Gateway 
  probe every backend pool member automatically on their own IPs; the 
  Host field only sets the HTTP Host header, not the probe destination.

### Listeners
| Name | Port | Protocol | Associated rule |
|---|---|---|---|
| listener-http | 80 | HTTP | rule-http |
| https-listener | 443 | HTTPS | rule-https |

### Rules
| Name | Listener | Backend pool | Backend settings | Priority |
|---|---|---|---|---|
| rule-http | listener-http | backend-pool-vmss | backend-settings-http | 250 |
| rule-https | https-listener | backend-pool-vmss | backend-settings-http | 115 |

### NSG Rules (appgw-2tier-nsg, attached to subnet-appgw)
- Allow-HTTP-From-Internet: port 80, TCP, source Any, priority 110 
  (lets internet clients reach the gateway's listener)
- Allow-HTTPS-From-Internet: port 443, TCP, source Any, priority 115 
  (added in Step 17 - required for the HTTPS listener; without it, 
  requests to https://absariq.com silently time out at the NSG rather 
  than erroring, since the packets are dropped before reaching the gateway)
- Allow-GatewayManager: ports 65200-65535, TCP, source Internet, priority 100
  - Note: source should ideally be the GatewayManager service tag per 
    Microsoft docs, but the Portal repeatedly failed to validate/save 
    that tag for this rule - confirmed as a known Portal issue via 
    Microsoft Q&A (others hit the same error). Internet is the documented 
    community workaround. Functionally still secure since these ports 
    are certificate-protected by Azure internally regardless of NSG source.

### NSG Rule added (basicNsgvm-2tier-test-vnet-nic01, attached to VMSS NICs)
- Allow-HTTP-From-AppGW: port 80, TCP, source 10.0.4.0/24 (subnet-appgw), 
  priority 220 - lets the gateway reach the VMSS instances

### Bug found and fixed: empty backend pool
- After creating the Application Gateway and pointing its backend pool at 
  vmss2tierapp, the pool showed 0 targets and testing returned 502 Bad Gateway.
- Cause: the VMSS was in Manual upgrade mode; its 2 existing instances 
  (created before the App Gateway existed) never picked up the new backend 
  pool association automatically.
- Fix: selected both instances in vmss2tierapp -> Instances -> Upgrade. 
  This reimaged them against the current model, which included the backend 
  pool link. Backend pool then showed 2/2 healthy targets.

### Bug found and fixed: HTTPS listener wired to wrong/missing rule (Step 17)
- After adding https-listener and editing an existing rule to attach it, 
  the Portal reassigned rule-http's listener from listener-http to 
  https-listener, rather than creating a new rule - leaving listener-http 
  with no associated rule at all and https-listener sharing the old rule.
- Symptom: https://absariq.com timed out (ERR_CONNECTION_TIMED_OUT), not a 
  502 - this pointed to a network-level drop rather than an app/routing error.
- Root cause was actually two separate issues:
  1. Rule wiring - fixed by restoring rule-http's listener to listener-http, 
     then creating a genuinely new rule-https pointed at https-listener.
  2. Missing NSG rule for port 443 on subnet-appgw (see NSG section above) - 
     this was the actual cause of the timeout; the rule mix-up alone would 
     more likely have produced a 502, not a silent timeout.
- Both fixed together; https://absariq.com confirmed working with valid 
  padlock afterward.

## Verified working end-to-end
- http://20.232.236.118 (Application Gateway public IP) - Steps 11-12
- http://absariq.com - Step 15
- https://absariq.com - Steps 16-18 (ZeroSSL cert, HTTPS listener/rule, NSG fix)
- Signup/login/dashboard flow confirmed working through the gateway on all of the above

## SSH Key
- Name: vm-2tier-test_key
- Stored locally at: ~/.ssh/vm-2tier-test_key.pem
- Reused across vm-2tier-db, jump-linux, vmss2tierapp

## App Database Connection (baked into systemd service on golden image)
- DB_HOST=10.0.0.5
- DB_USER=appuser
- DB_NAME=appdb
- (DB_PASSWORD stored only on the image's systemd service file, not committed here)

## Decisions Log
- DB access for VMSS: chose subnet-range NSG rule (10.0.2.0/24) over 
  Application Security Groups, due to time constraints while awaiting 
  trainer's input. ASGs remain a good future hardening step (more precise, 
  scoped to just VMSS instances rather than the whole subnet).

## Domain & DNS (Steps 13-15, COMPLETE)
- Domain purchased: absariq.com (registrar: Namecheap)
- Azure DNS zone created: absariq.com (in ram-demo-rg-dont-delete, East US)
- Azure-assigned nameservers (from the zone's NS recordset):
  - ns1-04.azure-dns.com.
  - ns2-04.azure-dns.net.
  - ns3-04.azure-dns.org.
  - ns4-04.azure-dns.info.
- Namecheap nameservers switched to Custom DNS, set to the 4 values above.
  - Bug found and fixed: first attempt at Namecheap had -05 suffixes 
    (ns1-05, ns2-05, etc.) instead of the zone's actual -04 values - 
    a transcription mismatch that would have pointed the domain at 
    nameservers with no knowledge of the zone. Caught by cross-checking 
    Namecheap's saved values against a fresh screenshot of the Azure 
    Recordsets page, then corrected in Namecheap.
- A record created in Azure DNS zone: absariq.com (root, "@") -> A -> 
  20.232.236.118 (Application Gateway public IP)
- Propagation confirmed via nslookup; http://absariq.com verified loading 
  the app end-to-end (Step 15).

## SSL/TLS (Steps 16-18, COMPLETE)
- Certificate authority: ZeroSSL (free tier, 90-day validity)
- Domain: absariq.com
- Cert converted to PFX format for Application Gateway upload (App Gateway 
  requires PFX, not raw PEM/CRT/KEY)
- Uploaded to appgw-2tier-prod as cert name "mysslcert" on a new HTTPS 
  listener (https-listener, port 443, Basic listener type)
- Wired to backend-pool-vmss via a dedicated rule-https (see Application 
  Gateway section above for the rule-wiring bug and fix)
- SSL offload/termination: TLS terminates at the Application Gateway; 
  traffic from the gateway to VMSS instances stays plain HTTP on port 80 
  internally (standard practice, since that traffic stays inside the 
  private VNet)
- **Renewal reminder:** ZeroSSL cert is only valid 90 days from issue - 
  needs reissue/re-upload before it expires or HTTPS will break. Track 
  issue date and set a reminder ahead of expiry.

## Monitoring & Alerting (Step 19, COMPLETE)
- Alert rule name: alert-vmss-cpu-high
- Scope: vmss2tierapp
- Condition: Percentage CPU, Average aggregation, greater than 80, 
  5-minute lookback period, evaluated every 1 minute
- Action group: ag-vmss-alerts (1 email notification configured)
- Severity: Sev 2 - Warning
- Enable upon creation: Yes; Automatically resolve alerts: Yes (alert 
  clears itself once CPU drops back under threshold)
- Rationale: threshold matches the VMSS autoscale trigger (also 80% CPU), 
  so the alert and an actual scale-out event fire around the same time - 
  gives a human-visible signal alongside the automated scaling response
- Cost: ~$0.10/month

## Project Roadmap Status
All 19 planned steps complete:
1. Sample application (signup/login) - done
2. Test VM (Ubuntu, nginx + app) - done
3. Test app UI - done
4. VNet + database subnet - done
5. DB endpoint reachable from test VM - done
6. Test app with user inputs (DB read/write) - done
7. Test VM captured as reference image - done
8. Test VM destroyed - done
9. Public/private subnets, NAT Gateway, jump servers - done (Linux jump 
   server only; Windows jump server skipped to keep VM count minimal)
10. Storage account for boot diagnostics + VMSS from reference image - done
11. Application Gateway with VMSS backend pool - done
12. Tested via Application Gateway public IP - done
13. Domain purchased (absariq.com, Namecheap) - done
14. Mapped to Azure DNS zone (nameservers + A record) - done
15. Domain working over HTTP - done
16. ZeroSSL certificate issued - done
17. Application Gateway HTTPS listener + certificate - done
18. App verified working over HTTPS - done
19. Azure Monitor CPU alert with email notification - done
