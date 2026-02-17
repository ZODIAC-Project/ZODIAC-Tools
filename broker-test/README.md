# Broker Test

Manually test if reatined messages have been correctly stored in the broker

**Optional `env` file** 
Can also be set as environment variables in your shell
```
BROKER=localhost (if port-forwarding) 
PORT=1883
TOPIC=tests/retained/test1
```

If you run the broker inside Kubernetes (minikube) port-forward the MQTT port to localhost first:
```
kubectl -n zodiac port-forward svc/hivezodiac 1883:1883
```

Publish a retained message
```
uv run send.py --message "Hello World"
```

Fetch the retained message 
```
uv run fetch.py 
```