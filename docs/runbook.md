# 本地运行手册

## 1. 环境与依赖

```powershell
conda create --name travel-rag python=3.11 pip `
  --override-channels `
  -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main `
  -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r

conda activate travel-rag
python -m pip install -r requirements-cuda.txt
python -m pip install -e ".[dev]" `
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

PyTorch CUDA 轮子使用官方 CUDA 12.6 索引，其余 Python 包使用清华 PyPI 镜像。安装后执行：

项目显式依赖 `socksio==1.0.0`，用于 HTTPX 在系统配置 SOCKS 代理时建立连接；
它不会创建、修改或绕过代理。

```powershell
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
python -m pip check
```

期望识别 `torch 2.8.0+cu126`、CUDA 12.6 和 RTX 4060。

## 2. API Key

复制 `.env.example` 为 `.env`，只在本机填写：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
TAVILY_API_KEY=
```

不要把 `.env`、终端截图或 Key 提交到 GitHub。

## 3. Mock 验收

```powershell
travel-rag ingest-demo --mode mock
travel-rag demo --mock --output artifacts/demo-mock.json
travel-rag serve --mode mock
```

打开 `http://127.0.0.1:8000`。Mock 不访问 DeepSeek、Tavily 或模型下载服务。

## 4. Live 验收

```powershell
travel-rag download-models
travel-rag ingest-demo --mode local
travel-rag demo --live --output artifacts/demo-live.json
travel-rag serve --mode live
```

`download-models` 锁定 BAAI 官方 revision，只下载 Safetensors、配置和分词器，排除重复的
PyTorch `.bin` 与 ONNX 权重。运行期设置 `MODEL_LOCAL_FILES_ONLY=true`，不会再次查询模型
仓库；缺少本地模型时直接失败。Live 失败时查看 `logs/travel-rag.jsonl`；禁止通过更换模型、
切换 CPU 或启用 Mock 来掩盖错误。

## 5. 质量检查

```powershell
python -m ruff check src tests
python -m pytest
```

默认测试全部离线，不产生外部 API 调用或费用。
