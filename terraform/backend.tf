# Remote State Backend Configuration
# 
# For LOCAL development: Keep this block commented out (uses local state)
# For REMOTE state: Uncomment the block below and configure via backend.hcl
#
# To enable remote state:
# 1. Run bootstrap: cd ../bootstrap && ./bootstrap.sh
# 2. Uncomment the block below
# 3. Run: terraform init -backend-config=backend.hcl -migrate-state

# terraform {
#   backend "s3" {
#     # Backend configuration provided via:
#     # terraform init -backend-config=backend.hcl
#   }
# }
