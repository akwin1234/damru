#!/bin/bash
# Monitor redroid container stability and auto-remount binderfs

mount -t binder binder /dev/binderfs 2>/dev/null
docker rm -f damru-test-0 2>/dev/null

docker run -d --privileged --name damru-test-0 \
  -v /dev/binderfs:/dev/binderfs \
  -p 5600:5555 \
  --restart=on-failure:5 \
  redroid/redroid:14.0.0_64only-latest \
  androidboot.use_memfd=true

echo "Container started. Monitoring..."

for i in $(seq 1 18); do
  sleep 5
  STATUS=$(docker ps -a --format "{{.Status}}" --filter name=damru-test-0)
  BINDER=$(ls /dev/binderfs/ 2>/dev/null | wc -l)
  echo "[$((i*5))s] Container: $STATUS | binderfs: $BINDER files"

  if [ "$BINDER" = "0" ] || [ "$BINDER" = "" ]; then
    mount -t binder binder /dev/binderfs 2>/dev/null
    echo "  -> Remounted binderfs"
  fi
done
