# ZODIAC helm chart

Work In Progress  
  
This contains the helm chart for deploying the ZODIAC stack onto a k8s cluster. For development, this should be a set-and-forget deployment with [keel](https://keel.sh) for automatic updating of images. Individual repositories are responsible for building and pushing their images to the registry. This chart requires that a secret has been set in the `zodiac` namespace that allows for the pulling of images from the registry.

**current components:**
- hivezodiac
- orion-ui
- mcp-client
- mcp-server
- agent-api
- agent-redis
- agent-worker
- log-collector


## deploy

create the `zodiac` namespace
```bash
kubectl create namespace zodiac
```

deploy the chart from this directory

```bash
helm install zodiac . -n zodiac
```

## automatic updates

only necessary if the helm release should be automatically updated

```bash
helm repo add keel https://charts.keel.sh
helm repo update
helm install keel keel/keel --namespace zodiac --set watchNamespace=zodiac
```

## adding new applications
1. add a gitlab token as a secret to your repository with the name `ZODIAC_CI_TOKEN` (I can give you the one I created for CI on request)
2. add the following github action to the repository of your application
```yaml
name: Deploy <name of your application>

on:
  push:
    branches: ["main"]

env:
  REGISTRY: git.tu-berlin.de:5000/zodiac/zodiac-meta

  IMAGE_NAME: <name of your application>
  CONTEXT: <directory that the docker image will use>
  DOCKERFILE: <path to the dockerfile>

  BUILDX_NO_DEFAULT_ATTESTATIONS: 1

jobs:
  build-and-push-image:
    runs-on: ubuntu-latest

    permissions:
      contents: read
      packages: write
      attestations: write
      id-token: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v5
      - name: Log in to our gitlab instance
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: github worker
          password: ${{ secrets.ZODIAC_CI_TOKEN }}
      - name: Set version
        run: echo "VERSION=0.${{ github.run_number }}.0-cicd" >> $GITHUB_ENV
      - name: Build and push docker image
        id: push
        uses: docker/build-push-action@v6
        with:
          context: ${{ env.CONTEXT }}
          push: true
          file: ${{ env.DOCKERFILE }}
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ env.VERSION }}
          labels: |
            org.opencontainers.image.version=${{ env.VERSION }}
            org.opencontainers.image.revision=${{ github.sha }}

```
replace the `name` in line one and the environment variables `IMAGE_NAME`, `CONTEXT` and `DOCKERFILE` depending on your application. If one repository should build more than one dockerfile, create more than one github action.  

3. build the image once by pushing to main. The github action should run successfully. The tag should automatically be `0.1.0-cicd` or similar

4. add a deployment file to the `templates` folder here in this repository

5. move any environment variables to `values.yaml`

6. add keel annotations to your deployment file
```yaml
metadata:
  <...>
  annotations:
    keel.sh/policy: minor
    keel.sh/trigger: poll
```
(you can also look at how the other deployment files do it)

7. make sure that the container image tag is set to `0.1.0-cicd` in your deployment file
```yaml
image: "{{ .Values.meta.imageUrl }}/<application-name>:0.1.0-cicd"
```
8. uninstall and install the helm chart from the cluster
```bash
helm uninstall zodiac -n zodiac
helm install zodiac . -n zodiac
```
or upgrade the helm chart  
```bash
helm upgrade zodiac ./ZODIAC-helm -n zodiac -f ZODIAC-helm/values.yaml --rollback-on-failure --debug
```
9. if everything works, add your application to the list of applications above :)