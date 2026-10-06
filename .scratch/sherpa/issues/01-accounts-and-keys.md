# 01: Accounts and keys

**What to build:** Everything needed to call external services is in place, so no later ticket is blocked on access: a personal AWS account (not an employer account), the Nebius Token Factory activation code redeemed ($25 credit), and a Tavily API key. Secrets live in a local environment file that is never committed.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Personal AWS account exists with billing alerts set (verified via CLI as user cli-admin, region us-east-1)
- [x] Nebius activation code NEBIUS-DEVPOST-GLOBAL26 redeemed and an API key created
- [x] Tavily API key created
- [x] Keys are stored in a git-ignored local environment file, and an example file lists the variable names without values (.gitignore and .env.example exist; owner fills in .env)
- [x] A call to the Nebius model list succeeds with the key (base URL https://api.tokenfactory.nebius.com/v1, 25 models listed; NVIDIA text models present, NVIDIA vision models NOT reachable by guessed ids)
