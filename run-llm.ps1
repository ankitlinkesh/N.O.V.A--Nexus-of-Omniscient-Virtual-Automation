$ErrorActionPreference = "Stop"
llama-server -m "C:/AI/Models/Qwen3-VL-4B-Q4/Qwen3VL-4B-Instruct-Q4_K_M.gguf" --mmproj "C:/AI/Models/mmproj/mmproj-Qwen3VL-4B-Instruct-Q8_0.gguf" --alias qwen3-vl-4b --host 127.0.0.1 --port 8080 -ngl 99 -c 16384 --image-min-tokens 256 --image-max-tokens 1024 --jinja
