kubeseal --format=yaml --controller-name=sealed-secrets < hermes-raw-secret.yaml > hermes-sealed-secret.yaml
rm ./hermes-raw-secret.yaml
