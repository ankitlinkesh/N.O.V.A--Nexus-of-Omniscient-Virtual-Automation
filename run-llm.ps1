# Start the local model for NOVA. -Model 4b (default) or 8b.
# The 8B plans multi-step tasks better. It fits 8 GB of VRAM with a smaller context and an 8-bit KV cache.
param([ValidateSet('4b', '8b')][string]$Model = '4b')
$ErrorActionPreference = "Stop"
if ($Model -eq '8b') {
  llama-server -m "C:/AI/Models/Qwen3-VL-8B/Qwen3VL-8B-Instruct-Q4_K_M.gguf" --mmproj "C:/AI/Models/Qwen3-VL-8B/mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf" --alias qwen3-vl-8b --host 127.0.0.1 --port 8080 -ngl 99 -c 12288 -fa on -ctk q8_0 -ctv q8_0 --image-min-tokens 256 --image-max-tokens 1024 --jinja
} else {
  llama-server -m "C:/AI/Models/Qwen3-VL-4B-Q4/Qwen3VL-4B-Instruct-Q4_K_M.gguf" --mmproj "C:/AI/Models/mmproj/mmproj-Qwen3VL-4B-Instruct-Q8_0.gguf" --alias qwen3-vl-4b --host 127.0.0.1 --port 8080 -ngl 99 -c 16384 --image-min-tokens 256 --image-max-tokens 1024 --jinja
}
