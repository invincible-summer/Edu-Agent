# 独立本地语义 RAG 部署与公共向量发布

Edu_Agent 的语义检索是独立运行时：不 import Paper_Agent，不复用其虚拟环境、数据库或服务。两者仅可读取同一个**只读模型权重缓存**。BM25 始终常驻；本地模型或 Chroma 故障时检索自动回退 BM25。

## 1. CPU 运行时与配置

先在 Edu_Agent 自己的虚拟环境安装 CPU PyTorch，再安装项目依赖，避免拉入 CUDA 运行时：

```bash
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch
python -m pip install -r backend/requirements.txt
```

生产 `.env` 示例：

```dotenv
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_MODEL_PATH=/opt/models/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_CACHE_DIR=/opt/model-cache/huggingface
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=32
EMBEDDING_MAX_THREADS=2
RAG_HYBRID=1
CHROMA_DIR=/opt/edu-agent/knowledge/vector_db
OMP_NUM_THREADS=2
MKL_NUM_THREADS=2
```

`EMBEDDING_MODEL_PATH` 优先于模型名称/缓存；本地 provider 强制 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1` 与 `local_files_only=True`，运行时不会下载模型。服务使用一个本地 ML 槽串行加载/编码/索引；Uvicorn 保持 `--workers 1`。模型懒加载，不做启动预热。

默认 `EMBEDDING_PROVIDER=off`。`openai` provider 继续支持 `EMBEDDING_BASE_URL/API_KEY/MODEL`。任何 provider 失败都不影响上传成功或 BM25 检索。

## 2. 公共教材向量包

公共 Git 资产目录为 `knowledge/public_vector_artifacts/`。构建器只读取固定 `public` Library namespace 的 UTF-8 文本、元数据和当前 Structured RAG chunks：

```bash
cd backend
python scripts/build_public_vector_pack.py
```

构建器输出分片 NPZ 和 `manifest.json`，记录 schema、RAG/chunker 版本、模型/指纹、维度、dtype、chunk/file 数量与 hash、分片 checksum、UTC 构建时间和 Git commit。发布前会校验 chunk ID 唯一性、文本/chunk hash、向量数量/维度/归一化、分片 checksum 和确定性随机自查询。全部通过后才原子替换旧目录；失败保留旧 artifact。

提交公共原文、`public.json`、`public.textbooks.json`、`knowledge/custom/public/**` 与 `knowledge/public_vector_artifacts/**`。禁止提交通用 `knowledge/vector_db`，其中可能包含私有账号或旧模型数据。

## 3. 云端导入

云端拉取经过验证的指定 commit 后，在重启 backend **之前**执行：

```bash
cd backend
python scripts/import_public_vector_pack.py
```

导入器会重新校验 manifest、所有分片、当前公共文本和 chunks，并确认当前配置模型的指纹/维度一致。它先构建完整 staging collection，同时复制旧 collection 中所有非公共 runtime vectors；通过数量与查询 smoke check 后原子切换 `active_collections.json`，再清理旧 collection。相同 manifest 重复导入直接跳过。任何校验或 staging 失败都不会切换现有 collection，服务仍可用 BM25。

导入成功后公共 Library 文件的 `rag_index.status` 更新为 `ready`，并记录 manifest revision、模型、维度和指纹。公共教材仍只有被 workspace/会话明确选择后才进入可见 scope。

## 4. 用户上传与资源边界

上传/解析先持久化文本与 Structured RAG chunks，状态立即为 `bm25_ready`；向量任务进入单槽后台队列，完成后变为 `ready`，失败则保持 `bm25_ready`。整本教材不会在请求/SSE 路径同步 embedding。删除和重建按 file/scope 清理，内容 hash 变化会重新 embedding；不同模型、维度、chunk schema、归一化策略或 RAG revision 使用不同 collection。

4 vCPU / 10GB 基线：单 Uvicorn worker、CPU MiniLM、batch 32、2–4 个 native CPU threads、不加载 reranker/Docling、不运行时下载模型。上线仍需在目标服务器同时运行 Paper_Agent 与 Edu_Agent，实测 RSS、swap、上传、SSE 和连续检索峰值；仓库测试不能替代该资源验收。
