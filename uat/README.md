# UAT Repository (scaffold)

This folder is a local scaffold for the *UAT* repository. It is intended to be
initialized as a separate git repository and pushed to your remote origin.

Recommended steps to initialize and push:

1. From the project root run the helper script:

   ./scripts/init_repos.sh --create-only

2. Add your remote and push:

   cd uat
   git remote add origin git@github.com:your-org/QuantConnect-uat.git
   git push -u origin uat

Adjust remotes and branch names to your workflow.
