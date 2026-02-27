# ZODIAC helm chart

Work In Progress  
  
This contains the helm chart for deploying the ZODIAC stack onto a k8s cluster. For development, this should be a set-and-forget deployment with [keel](https://keel.sh) for automatic updating of images.  
Individual repositories are responsible for building and pushing their images to the registry.  
This chart requires that a secret has been set in the `zodiac` namespace that allows for the pulling of images from the registry.

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

- add a github action to the application repository to build and push images that triggers on a push to the main branch
- build the image once to test it. The tag should automatically be `0.1.0-cicd` or similar
- add the deployment file to the `templates` folder in this repository
- move environment variables to `values.yaml`
- add keel annotations to your deployment file
```yaml
metadata:
  <...>
  annotations:
    keel.sh/policy: minor
    keel.sh/trigger: poll
```
- make sure that the container image tag is set to `0.1.0-cicd`
```yaml
image: "{{ .Values.meta.imageUrl }}/<application-name>:0.1.0-cicd"
```
- run `helm upgrade zodiac . -n zodiac`