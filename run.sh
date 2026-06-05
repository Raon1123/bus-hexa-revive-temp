#podman build -t localhost/bus-hexa-revive-temp_bus:latest . 
podman-compose build
#podman run -d -p 8017:8501 --name bus bus-hexa-revive-temp_bus:${1}
podman-compose down
podman-compose up -d