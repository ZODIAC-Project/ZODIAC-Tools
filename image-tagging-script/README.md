Image Tagging Script

Purpose
- Build a Docker image from the current Git commit, push it to a registry, and update a Kubernetes YAML to reference the image by digest.

Important Note:
This script can only be used for YAML files with a single image reference. If your YAML file has multiple image references, you will need to modify the script to handle that case. (TODO: add support for multiple image references in the future or make it optional that the script updates all matching image references.)

Quick usage
- Pipe the script to bash and pass image name and k8s file:

	Curl -sSL https://git.tu-berlin.de/ZODIAC-Project/ZODIAC-Tools/-/raw/main/image-tagging-script/image_tagging_script.sh | bash -s -- myrepo/myimage path/to/deployment.yaml

Examples
- Build and update `deployment.yaml` with image `myrepo/myimage`:

	curl ... | bash -s -- myrepo/myimage deployment.yaml

Notes
- The script expects to run inside a Git repo (uses `git rev-parse`).
- You should be logged in to your Docker registry (or provide token options).
- It updates the first matching `image:` line that contains the image basename with the pushed image digest.
- After the script finishes, run `kubectl apply -f <k8s-file>` to deploy the updated manifest.

Options supported by the script (see script header for details):
- `-f, --dockerfile <path>`: use an alternate Dockerfile
- `-u, --username <user>` and `-t, --token <token>`: registry credentials
- `--token-file <path>`: read registry token from a file (safer)

Adding a Token from a File
- Create a file (e.g., `registry_token.txt`) containing your registry token.
- Run the script with the `--token-file` option:
    curl ... | bash -s -- myrepo/myimage deployment.yaml --token-file registry_token.txt