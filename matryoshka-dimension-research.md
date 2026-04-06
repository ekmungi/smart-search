# Matryoshka Embedding Dimension Impact on Retrieval Quality — Research Report

## 1. Snowflake Arctic Embed M v2.0: Concrete Benchmark Numbers

Arctic Embed 2.0 uses MRL at **only one truncation point: 256 dimensions** (not 384 or 512). There is no granular 384/512 table — the model was designed for two operating points: full dims and 256-dim truncation.

### nDCG@10 Scores (from Arctic-Embed 2.0 paper, Table 1)

| Model | Dims | MTEB-R (BEIR 15) | CLEF (5 langs) | MIRACL (4 langs) | MIRACL-O |
|---|---|---|---|---|---|
| Arctic-Embed 2.0-M | **768** | **0.554** | **0.534** | **0.592** | **0.552** |
| Arctic-Embed 2.0-M + MRL truncation | **256** | **0.549** | **0.522** | **0.578** | **0.545** |

### Degradation (768 → 256):
- **MTEB-R (English BEIR):** 0.554 → 0.549 = **-0.9% relative drop**
- **CLEF (multilingual):** 0.534 → 0.522 = **-2.2% relative drop**
- **MIRACL:** 0.592 → 0.578 = **-2.4% relative drop**
- **MIRACL-O:** 0.552 → 0.545 = **-1.3% relative drop**

Snowflake claims: "3x compression with ~3% degradation in quality" for the medium model, and "4x compression with <3% degradation" for the large model.

### Why only 256 and not intermediate dims?
Snowflake found that MRL with many nesting layers **substantially harms quality after scalar quantization**. Their holistic compression scheme (MRL truncation + Int4 quantization = 128 bytes/vector) works best with a single truncation target of 256.

---

## 2. Nomic Embed Text v1.5: Multi-Dimension Benchmarks

Nomic v1.5 is one of the few models reporting scores at multiple Matryoshka dimensions:

| Dimension | MTEB Score | Relative to 768d |
|-----------|-----------|-------------------|
| **768** | 62.28 | baseline |
| **256** | 61.04 | **-2.0%** |
| **64** | 56.10 | **-9.9%** |

The 512 score is not explicitly published but falls between 61-62 based on the published degradation curves.

---

## 3. General Matryoshka Dimension vs Quality (Cross-Model Findings)

### From the original MRL paper (Kusupati et al., NeurIPS 2022):
- At **50% of full size** (e.g., 768→384): quality drops **1-4 points nDCG@10**
- At **25% of full size** (e.g., 768→192): quality drops **5-10 points nDCG@10**
- MRL at 256 dims preserves **>99.5% of full-size performance** (3x reduction)
- MRL at 128 dims preserves **~99% of full-size performance** (6x reduction)
- MRL at 64 dims preserves **~98.37% of full-size performance** (12x reduction)

### From fine-tuning experiments (BGE base, RAG dataset):
- 256 dims: **95%+ performance retained**
- 128 dims: **~99% retained** (with fine-tuning)
- 64 dims: **~98.37% retained**

### From CLIP-based multimodal retrieval:
- 256 vs 512 dimensions: **<0.019 nDCG difference** across all splits

### OpenAI text-embedding-3-large:
- Truncated to 256 dims, it **outperforms** the older ada-002 at 1,536 dims on MTEB
- Going from 3,072 → 768 dims: **<10% degradation** on recall metrics

### Combined MRL + Quantization (practical deployment):
- 256-dim MRL + Scalar Quantization: **-4.6% Recall@10, -4.4% MRR@10** vs full baseline
- This achieves **70.8% infrastructure cost reduction**

---

## 4. Key Takeaway: Is 256-dim a Significant Quality Loss?

**No, for well-trained Matryoshka models, 256 dimensions is NOT a significant quality loss.**

Specifically for **snowflake-arctic-embed-m-v2.0**:
- 768 → 256 loses only **0.5-1.2 absolute nDCG@10 points** (0.9-2.4% relative)
- This is one of the best retention rates among MRL models because Snowflake applies MRL during both pretraining AND finetuning

The "sweet spot" across models appears to be **256-512 dimensions** for most retrieval tasks, where you get 3-6x memory savings with <3% quality loss.

**Important caveat**: 384 and 512 are NOT tested operating points for Arctic Embed v2.0. The model only supports 768 (full) and 256 (truncated). If you want intermediate dimensions, you would need a model that explicitly trained with those MRL targets (like Nomic v1.5 or OpenAI text-embedding-3).

---

## Sources

- [Arctic-Embed 2.0 Paper (arXiv:2412.04506)](https://arxiv.org/html/2412.04506v2)
- [Snowflake Arctic Embed M v2.0 — HuggingFace](https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0)
- [Snowflake Engineering Blog: Arctic Embed 2.0](https://www.snowflake.com/en/engineering-blog/snowflake-arctic-embed-2-multilingual/)
- [Matryoshka Representation Learning (Kusupati et al., NeurIPS 2022)](https://arxiv.org/abs/2205.13147)
- [Nomic Embed Text v1.5 — HuggingFace](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
- [Nomic Embed Matryoshka Blog](https://www.nomic.ai/news/nomic-embed-matryoshka)
- [HuggingFace Matryoshka Introduction](https://huggingface.co/blog/matryoshka)
- [Sentence Transformers Matryoshka Training](https://sbert.net/examples/sentence_transformer/training/matryoshka/README.html)
- [Snowflake Arctic Embed L v2.0 — HuggingFace](https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0)
