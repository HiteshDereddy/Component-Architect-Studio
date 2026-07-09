#!/bin/bash
echo "Starting robust model download..."
while true; do
    huggingface-cli download phoenix-gurl/granite-4.1-3b-Q4_K_M-GGUF --local-dir backend/models
    if [ $? -eq 0 ]; then
        echo "Download completed successfully."
        break
    else
        echo "Download failed due to timeout. Retrying in 5 seconds..."
        sleep 5
    fi
done
