# RRM-20 — why “diffusion models” ranks badly

## Status of this run

Run from the box on 2026-10-29, about 3:50 PM CDMX: `modal run scripts/analysis/rrm20_dump.py`, CPU only (2 cores, 32 GiB), no GPU, no reader, no Meta API. The container took 52.9 s, including 22.2 s to load the index. Modal billing for the app is **$0.0053** [V]. No Modal app or container was left running [V].

One trivial fix was needed. Inside the container the script is `/root/rrm20_dump.py`, so `Path(__file__).parents[2]` raised `IndexError` and the container crash-looped. `ROOT` now falls back to the script's own directory. The crash-looping attempt was stopped and billed $0.

The results are in `scripts/analysis/rrm20_summary.json` (68 KB, a compact view). The full dump, 1 MB `rrm20_results.json`, stays on the box and is not committed. `score_check_abs` is 0 on all 11 queries [V], so the vote/bonus split reproduces `candidate_scores`. Everything below in the Results section comes from that JSON.

## What the dump records

`scripts/analysis/rrm20_dump.py` is CPU-only. It reads `/s2/2026-10-20/index` and `index_ext` on the volume `rrm-data`. It does not import the reader, does not call Muse, and does not change scores. The request is 2 physical cores and 32 GiB, `scaledown_window=2`, no retries. The container aborts itself after 40 minutes (about $0.23 at the public list price of $0.0000131 per core-second and $0.00000222 per GiB-second).

```bash
python3 scripts/analysis/rrm20_dump.py --self-check
modal run scripts/analysis/rrm20_dump.py
modal app list
```

The self-check is local and synthetic. It checks that the vote split matches `candidate_scores` and that two well-separated point clouds form two clusters.

Eleven short queries, all under the 40-word rule, so the live ranker uses `adhoc_query`, k=100, and weights `1/(1+rank/20)`:

- diffusion models
- graph neural networks
- neural radiance fields
- transformers for time series forecasting
- denoising diffusion probabilistic models
- diffusion models image generation
- score-based generative models
- speech recognition
- attention
- transformers
- graph

For each query the JSON has:

- the graph-aligned top-100 neighbors (title, year, field, venue, L2 distance, rank weight, in-degree, out-degree)
- two clusterings of those neighbors: average-linkage on reconstructed SPECTER L2, and average-linkage on Jaccard distance of their out-neighbor sets. k in {2, 3, 4, 5} is the one with the higher mean silhouette
- per cluster, the three papers that cluster’s seeds cite most, with `weight_coverage` (share of that cluster’s seed weight that cites the paper; 1 means every seed in the cluster cites it)
- the top 30 candidates from `link_rank`, with `vote_sum`, `neighbor_bonus` (0.5 times the seed weight when the candidate is itself a neighbor), citation count, and in-degree percentile. The top 10 also list every voting neighbor
- `score_check_abs`, which is zero when that split matches `candidate_scores`
- whether `PaperLookup` would have opened an exact title instead of searching (same rule as serve: a title shorter than 4 words counts only at 1000 citations or more)
- `neighbor_token_counts` and a year summary of the neighbors
- a hub table: every paper that lands in any top 10, with how many queries put it there

Field comes from `node_meta.npz` (`field_names`). That column prefers “Computer Science” when it is present, so it will not separate two CS senses. The clusters and the titles are the sense split.

## How a score is made [I]

From `rrm/search/burst.py`, a short query:

1. Encode with the `adhoc_query` adapter. Search the IVF-PQ index (`nprobe=32`) for 100 nearest papers.
2. Drop hits that are not in `index_ext`. Weights use the rank **after** that drop.
3. A candidate’s score is the sum of the weights of seeds that cite it, plus `0.5 * weight` if the candidate is a seed.
4. Order is score, then citation count, then corpus id. Citation count does not change the score. It only breaks ties (`n_tied_at_top_score` in the JSON).

So three different failures look different in the dump:

- **Neighbors.** The nearest titles are already the wrong sense, or the 100 are a mix and no generative paper is near the query. Compare neighbor 0 with burst rank 1, and compare the specific queries (“denoising diffusion probabilistic models”, “score-based generative models”, “diffusion models image generation”) with the two-word query.
- **Votes inside a sense.** One cluster’s `weight_coverage` on a single classic paper is near 1, while the other sense splits its weight across several papers. The classic paper then wins even if its cluster is smaller.
- **Hubs.** The same high in-degree papers (the ticket names Attention, Adam, and LSTM) sit in the top 10 for queries that do not name them. The hub table’s `n_queries_in_top10` and `in_degree_percentile` are the measurement. A hub can get there because many unrelated neighbors cite it, which is the vote, not the tie-break.

“graph neural networks”, “neural radiance fields”, and “transformers for time series forecasting” are the controls. If their largest cluster covers most of the seed weight and that cluster’s winner is the paper RRM-17 showed, they escape the ambiguity by having one sense in the neighbor set. If they also show Attention / Adam / LSTM in the top 10 but not at rank 1, the hub is present and the coherent cluster still outvotes it.

## Fixes to try later, not in this change

These are proposals. They are not implemented.

1. **Divide each incoming vote by a function of in-degree** (IDF on the citation graph). This targets the hub list directly. Effort is small: one array already in memory (`in_degree`), inside `candidate_scores`. Risk: a real canonical paper is also highly cited, so GCN and Instant-NGP can fall if the divisor is too strong. First knob to sweep.
2. **Keep only the dominant neighbor cluster, then vote.** Cluster the 100 seeds (the citation-Jaccard clustering is the one that matches the vote, and it does not need PQ reconstruction). Drop the smaller senses before `gather_out`. This targets the two-word ambiguity even when neither sense is a global hub. Effort is larger than (1) and needs a stability check: a good query whose neighbors already form one cluster should be unchanged.
3. **Expand queries of one or two words before encoding**, with a fixed template or with Muse, and embed the expansion with the same `adhoc_query` adapter. Muse labels must stay out of the score, as they do today. This targets queries whose neighbor set is mixed before any voting. Effort is a second encode plus a decision for when a query is “too short”. It does not fix a neighbor set that is already the wrong sense in one tight cluster.

Evaluate any of the three on the existing RRM-3 setup in `eval/citation_recall.py`: title+abstract queries, relevant set = `index_ext` out-neighbors of the query paper, recall@100 and nDCG@10 against plain kNN, same sample of papers (`min_refs`, seed). That set does not contain the short string “diffusion models”. Add a separate short-query sheet for the eleven strings above: rank of the paper a person would name (recorded by corpus id before the run), plus how often Attention, Adam, and LSTM enter the top 10. Do not retune on the sheet and then report the same sheet as the only result.

## Results [V unless marked]

Clustering note: the cite-Jaccard clustering is not informative. Every query lands at k=5 with silhouette 0.004–0.057, one block of 96 and four singletons [V]. The embed clustering runs on PQ reconstructions whose L2 error (`reconstruct_l2_mae` 128–196) is about the size of the neighbor distances themselves (~129–195), so it is noisy [V/I]. Even so, for "diffusion models" its two groups match the two senses by title. Treat cluster sizes as indicative.

### diffusion models
Neighbors 0–4: Examining Diffusion in the Real World; Real-world diffusion dynamics based on point process ap; Network models of the diffusion of innovations; A Multidisciplinary Survey of Social Network Diffusion ; The Principles of Diffusion Models. Neighbor title tokens: `{'diffusion': 61, 'denois': 1, 'generative': 1, 'influence': 12, 'graph': 1, 'attention': 1, 'forecast': 3}`. Neighbor years: median 2016, 57 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 82 | 28.32 | Examining Diffusion in the Real Wor; Real-world diffusion dynamics based; Network models of the diffusion of  | Maximizing the spread of influence throu (0.28); Uncovering the Temporal Dynamics of Diff (0.18) |
| 1 | 18 | 7.94 | The Principles of Diffusion Models; Non-Denoising Forward-Time Diffusio; Teach Diffusion Language Models to  | Denoising Diffusion Probabilistic Models (0.65); Score-Based Generative Modeling through  (0.49) |
(k=2, silhouette 0.118)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | Maximizing the spread of influence through a social network | 7.93 | 7.93 | 0.00 | 19 | 8035 |
| 2 | Uncovering the Temporal Dynamics of Diffusion Networks | 5.39 | 5.18 | 0.22 | 13 | 547 |
| 3 | Denoising Diffusion Probabilistic Models | 5.19 | 5.19 | 0.00 | 12 | 31190 |
| 4 | Collective dynamics of ‘small-world’ networks | 4.74 | 4.74 | 0.00 | 13 | 26742 |
| 5 | Inferring networks of diffusion and influence | 4.70 | 4.70 | 0.00 | 11 | 1003 |

### graph neural networks
Neighbors 0–4: Graph Neural Networks: A Review of Methods and Applicat; Survey on Graph Neural Networks; A Survey on Graph Neural Networks and its Applications ; Introduction to Graph Neural Networks for Machine Learn; A survey on graph neural networks. Neighbor title tokens: `{'generative': 1, 'image': 1, 'graph': 93, 'transformer': 1, 'attention': 13}`. Neighbor years: median 2021, 3 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 99 | 36.09 | Graph Neural Networks: A Review of ; Survey on Graph Neural Networks; A Survey on Graph Neural Networks a | Semi-Supervised Classification with Grap (0.76); Inductive Representation Learning on Lar (0.64) |
| 1 | 1 | 0.17 | Fast vertex-based graph convolution | Geometric Deep Learning on Graphs and Ma (1.0); 3D comparison of hippocampal atrophy in  (1.0) |
(k=2, silhouette 0.158)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | Semi-Supervised Classification with Graph Convolutional Netw | 27.30 | 27.30 | 0.00 | 73 | 32585 |
| 2 | Inductive Representation Learning on Large Graphs | 23.11 | 23.11 | 0.00 | 61 | 18571 |
| 3 | Graph Attention Networks | 21.39 | 21.19 | 0.20 | 61 | 24705 |
| 4 | Convolutional Neural Networks on Graphs with Fast Localized  | 19.76 | 19.76 | 0.00 | 51 | 7797 |
| 5 | A Comprehensive Survey on Graph Neural Networks | 17.64 | 17.24 | 0.40 | 39 | 9578 |

### neural radiance fields
Neighbors 0–4: Neural Radiance Fields for the Real World: A Survey; Baking Neural Radiance Fields for Real-Time View Synthe; Baking Neural Radiance Fields for Real-Time View Synthe; MS-NeRF: Multi-Space Neural Radiance Fields; Neural Radiance Field-Based Visual Rendering: A Compreh. Neighbor title tokens: `{'denois': 1, 'generative': 1, 'image': 4, 'influence': 1, 'radiance': 91}`. Neighbor years: median 2023, 0 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 97 | 35.19 | Neural Radiance Fields for the Real; Baking Neural Radiance Fields for R; Baking Neural Radiance Fields for R | Instant neural graphics primitives with  (0.62); NeRF in the Wild: Neural Radiance Fields (0.52) |
| 1 | 3 | 1.06 | Mixed Spiking NeRF: Towards a More ; SaENeRF: Suppressing Artifacts in E; Coherence Awareness in Diffractive  | Representing Scenes as Neural Radiance F (0.83); Simple model of spiking neurons (0.45) |
(k=2, silhouette 0.201)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | Instant neural graphics primitives with a multiresolution ha | 22.13 | 22.13 | 0.00 | 62 | 5632 |
| 2 | Mip-NeRF: A Multiscale Representation for Anti-Aliasing Neur | 18.26 | 18.26 | 0.00 | 45 | 2711 |
| 3 | NeRF in the Wild: Neural Radiance Fields for Unconstrained P | 18.19 | 18.19 | 0.00 | 47 | 1754 |
| 4 | Representing Scenes as Neural Radiance Fields for View Synth | 16.45 | 16.45 | 0.00 | 50 | 6789 |
| 5 | Neural Sparse Voxel Fields | 16.33 | 16.33 | 0.00 | 38 | 1400 |

### transformers for time series forecasting
Neighbors 0–4: Applying transformers to short-term node price forecast; A Benchmark for Electrical Load Forecasting Across Grid; Transformer training strategies for forecasting multipl; Short-Term Electricity Load Forecasting Using the Tempo; Just in Time Transformers. Neighbor title tokens: `{'generative': 1, 'graph': 1, 'transformer': 77, 'attention': 5, 'forecast': 60, 'lstm': 9}`. Neighbor years: median 2024, 9 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 79 | 30.18 | Applying transformers to short-term; A Benchmark for Electrical Load For; Transformer training strategies for | Attention is All you Need (0.47); Informer: Beyond Efficient Transformer f (0.42) |
| 1 | 21 | 6.07 | Predictive Analytics Usage for Powe; Transformer performance assessment; Prognostics & health management met | An Updated Model to Determine the Life R (0.15); IEEE Guide for Loading Mineral- Oil-Imme (0.14) |
(k=2, silhouette 0.191)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | Attention is All you Need | 14.20 | 14.20 | 0.00 | 35 | 156957 |
| 2 | Informer: Beyond Efficient Transformer for Long Sequence Tim | 12.59 | 12.59 | 0.00 | 33 | 5617 |
| 3 | Autoformer: Decomposition Transformers with Auto-Correlation | 10.18 | 10.18 | 0.00 | 28 | 3974 |
| 4 | A Time Series is Worth 64 Words: Long-term Forecasting with  | 8.72 | 8.72 | 0.00 | 24 | 3656 |
| 5 | Long Short-Term Memory | 8.51 | 8.51 | 0.00 | 21 | 78549 |

### speech recognition
Neighbors 0–4: Speech recognition by machines and humans; Telephonetic: Making Neural Language Models Robust to A; Machine Learning Methods for Signal, Image and Speech P; Enhancing continuous speech recognition with CapsNet an; A Hybrid Architecture Combining CNN, LSTM, and Attentio. Neighbor title tokens: `{'denois': 1, 'generative': 1, 'image': 1, 'transformer': 1, 'attention': 9, 'speech': 93, 'lstm': 1}`. Neighbor years: median 2021, 25 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 16 | 5.67 | Speech recognition by machines and ; Computer Speech Recognition in Psyc; Speech Recognition and Understandin | Towards increasing speech recognition er (0.23); The development of an experimental discr (0.23) |
| 1 | 82 | 30.21 | Telephonetic: Making Neural Languag; Machine Learning Methods for Signal; Enhancing continuous speech recogni | Attention is All you Need (0.32); Librispeech: An ASR corpus based on publ (0.32) |
| 2 | 2 | 0.38 | Statistical Language and Speech Pro; Why Softmax Attention Outperforms L | Comparing Stochastic Approaches to Spoke (0.54); Discriminative Training and Maximum Entr (0.54) |
(k=3, silhouette 0.091)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | Attention is All you Need | 9.84 | 9.84 | 0.00 | 26 | 156957 |
| 2 | Librispeech: An ASR corpus based on public domain audio book | 9.57 | 9.57 | 0.00 | 21 | 7760 |
| 3 | Adam: A Method for Stochastic Optimization | 7.64 | 7.64 | 0.00 | 19 | 145912 |
| 4 | Long Short-Term Memory | 7.50 | 7.50 | 0.00 | 16 | 78549 |
| 5 | wav2vec 2.0: A Framework for Self-Supervised Learning of Spe | 7.19 | 7.19 | 0.00 | 17 | 7978 |

### denoising diffusion probabilistic models
Neighbors 0–4: Computationally Efficient Diffusion Models in Medical I; Structured Denoising Diffusion Models in Discrete State; Bilateral Denoising Diffusion Models; Diffusion Models in Vision: A Survey; Denoising Diffusion Probabilistic Models. Neighbor title tokens: `{'diffusion': 91, 'denois': 34, 'score': 2, 'generative': 10, 'image': 8, 'graph': 1, 'forecast': 3}`. Neighbor years: median 2023, 1 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 99 | 36.04 | Computationally Efficient Diffusion; Structured Denoising Diffusion Mode; Bilateral Denoising Diffusion Model | Denoising Diffusion Probabilistic Models (0.87); Score-Based Generative Modeling through  (0.78) |
| 1 | 1 | 0.22 | Deep Structured Mixtures of Gaussia | A differential approach to inference in  (1.0); On the Relationship between Sum-Product  (1.0) |
(k=2, silhouette 0.167)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | Denoising Diffusion Probabilistic Models | 31.68 | 31.27 | 0.42 | 86 | 31190 |
| 2 | Score-Based Generative Modeling through Stochastic Different | 28.07 | 28.07 | 0.00 | 78 | 11470 |
| 3 | Deep Unsupervised Learning using Nonequilibrium Thermodynami | 26.37 | 26.37 | 0.00 | 72 | 9767 |
| 4 | Denoising Diffusion Implicit Models | 21.68 | 21.46 | 0.21 | 60 | 12708 |
| 5 | Diffusion Models Beat GANs on Image Synthesis | 21.63 | 21.63 | 0.00 | 61 | 11712 |

### diffusion models image generation
Neighbors 0–4: SIGGRAPH 2023 Course on Diffusion Models; Diffusion models for Handwriting Generation; Synthetic data generation by diffusion models; Compositional Visual Generation with Composable Diffusi; Spatiotemporal diffusion model for satellite imagery. Neighbor title tokens: `{'diffusion': 86, 'generative': 6, 'image': 44, 'graph': 3, 'attention': 2}`. Neighbor years: median 2024, 0 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 75 | 26.77 | SIGGRAPH 2023 Course on Diffusion M; Diffusion models for Handwriting Ge; Synthetic data generation by diffus | High-Resolution Image Synthesis with Lat (0.7); Denoising Diffusion Probabilistic Models (0.6) |
| 1 | 25 | 9.48 | Spatiotemporal diffusion model for ; Pixel-wise RL on Diffusion Models: ; Fixed Point Diffusion Models | Denoising Diffusion Probabilistic Models (0.88); High-Resolution Image Synthesis with Lat (0.82) |
(k=2, silhouette 0.074)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | High-Resolution Image Synthesis with Latent Diffusion Models | 26.45 | 26.45 | 0.00 | 75 | 25228 |
| 2 | Denoising Diffusion Probabilistic Models | 24.37 | 24.37 | 0.00 | 70 | 31190 |
| 3 | Diffusion Models Beat GANs on Image Synthesis | 17.31 | 17.31 | 0.00 | 49 | 11712 |
| 4 | Deep Unsupervised Learning using Nonequilibrium Thermodynami | 16.50 | 16.50 | 0.00 | 45 | 9767 |
| 5 | Denoising Diffusion Implicit Models | 16.35 | 16.35 | 0.00 | 45 | 12708 |

### score-based generative models
Neighbors 0–4: On Maximum Likelihood Training of Score-Based Generativ; Riemannian Score-Based Generative Modeling; Algorithm- and Data-Dependent Generalization Bounds for; Score-based Generative Models for Calorimeter Shower Si; Classification via score-based generative modelling. Neighbor title tokens: `{'diffusion': 12, 'score': 36, 'generative': 79, 'graph': 2, 'transformer': 1}`. Neighbor years: median 2022, 17 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 95 | 35.27 | On Maximum Likelihood Training of S; Riemannian Score-Based Generative M; Algorithm- and Data-Dependent Gener | Score-Based Generative Modeling through  (0.53); Denoising Diffusion Probabilistic Models (0.48) |
| 1 | 5 | 0.98 | Competitive generative models with ; Using Captum to Explain Generative ; Visual Analytics for Generative Tra | Axiomatic Attribution for Deep Networks (0.42); Language Models are Few-Shot Learners (0.42) |
(k=2, silhouette 0.148)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | Score-Based Generative Modeling through Stochastic Different | 18.71 | 18.71 | 0.00 | 43 | 11470 |
| 2 | Denoising Diffusion Probabilistic Models | 16.81 | 16.81 | 0.00 | 37 | 31190 |
| 3 | Generative Modeling by Estimating Gradients of the Data Dist | 16.19 | 16.19 | 0.00 | 33 | 5510 |
| 4 | A Connection Between Score Matching and Denoising Autoencode | 15.20 | 15.20 | 0.00 | 31 | 2183 |
| 5 | Estimation of Non-Normalized Statistical Models by Score Mat | 13.74 | 13.74 | 0.00 | 26 | 1961 |

### attention
Neighbors 0–4: Hierarchical Attention Networks; Corrigendum: Attention in Psychology, Neuroscience, and; ABC: Attention with Bounded-memory Control; From Human Attention to Computational Attention: A Mult; From Human Attention to Computational Attention: A Mult. Neighbor title tokens: `{'diffusion': 1, 'generative': 1, 'image': 17, 'graph': 2, 'transformer': 5, 'attention': 84}`. Neighbor years: median 2020, 31 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 97 | 35.47 | Hierarchical Attention Networks; Corrigendum: Attention in Psycholog; ABC: Attention with Bounded-memory  | A Model of Saliency-Based Visual Attenti (0.35); Attention is All you Need (0.32) |
| 1 | 3 | 0.79 | Support for Big Data's Limiting Res; Attention! Rethinking What We Measu; Attention!: How to Interrupt, Yell, | Can We Ever Escape from Data Overload? A (0.36); Big data: the management revolution. (0.36) |
(k=2, silhouette 0.171)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | A Model of Saliency-Based Visual Attention for Rapid Scene A | 12.57 | 12.57 | 0.00 | 35 | 9439 |
| 2 | Attention is All you Need | 11.41 | 11.41 | 0.00 | 30 | 156957 |
| 3 | Deep Residual Learning for Image Recognition | 9.50 | 9.50 | 0.00 | 27 | 197995 |
| 4 | Neural Machine Translation by Jointly Learning to Align and  | 8.69 | 8.69 | 0.00 | 21 | 25562 |
| 5 | Show, Attend and Tell: Neural Image Caption Generation with  | 8.33 | 8.33 | 0.00 | 21 | 9613 |

### transformers
Neighbors 0–4: Key Point Matching with Transformers; A Two-Parameter Weibull Framework for Diagnosing Transf; Topic classification of electric vehicle consumer exper; Length-Adaptive Transformer: Train Once with Length Dro; Enhancing Transformer Training Efficiency with Dynamic . Neighbor title tokens: `{'generative': 1, 'influence': 1, 'graph': 3, 'transformer': 87, 'attention': 16, 'forecast': 3}`. Neighbor years: median 2024, 3 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 72 | 25.65 | Key Point Matching with Transformer; Length-Adaptive Transformer: Train ; Enhancing Transformer Training Effi | Attention is All you Need (0.6); BERT: Pre-training of Deep Bidirectional (0.33) |
| 1 | 20 | 7.83 | A Two-Parameter Weibull Framework f; Topic classification of electric ve; Handbook of Transformer Design and  | Attention is All you Need (0.35); BERT: Pre-training of Deep Bidirectional (0.23) |
| 2 | 8 | 2.77 | Elementary Students Learn How To En; Retraction: Design of College Engli; Retraction: Design of Network Teach | Character-level Convolutional Networks f (0.09); Recursive Deep Models for Semantic Compo (0.09) |
(k=3, silhouette 0.182)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | Attention is All you Need | 18.35 | 18.35 | 0.00 | 50 | 156957 |
| 2 | BERT: Pre-training of Deep Bidirectional Transformers for La | 10.42 | 10.42 | 0.00 | 27 | 100295 |
| 3 | Language Models are Few-Shot Learners | 7.14 | 7.14 | 0.00 | 20 | 53942 |
| 4 | Language Models are Unsupervised Multitask Learners | 6.79 | 6.79 | 0.00 | 17 | 26383 |
| 5 | An Image is Worth 16x16 Words: Transformers for Image Recogn | 5.69 | 5.69 | 0.00 | 18 | 58780 |

### graph
Neighbors 0–4: Which Algorithms Can Graph Neural Networks Learn?; Toward the Analysis of Graph Neural Networks; Graph Deep Learning: Methods and Applications; A Survey on Graph Neural Networks and its Applications ; GraphStorm: All-in-one Graph Machine Learning Framework. Neighbor title tokens: `{'diffusion': 3, 'generative': 3, 'image': 1, 'graph': 76, 'transformer': 11, 'attention': 21}`. Neighbor years: median 2023, 7 before 2018.

| embed cluster | size | seed weight | exemplars | top cited (weight_coverage) |
|---|---|---|---|---|
| 0 | 99 | 35.59 | Which Algorithms Can Graph Neural N; Toward the Analysis of Graph Neural; Graph Deep Learning: Methods and Ap | Semi-Supervised Classification with Grap (0.64); Graph Attention Networks (0.54) |
| 1 | 1 | 0.67 | Gratitude and Graph Theory in the T |  |
(k=2, silhouette 0.219)

| # | title | score | vote | bonus | voters | in-degree |
|---|---|---|---|---|---|---|
| 1 | Semi-Supervised Classification with Graph Convolutional Netw | 22.95 | 22.95 | 0.00 | 63 | 32585 |
| 2 | Graph Attention Networks | 19.44 | 19.24 | 0.20 | 53 | 24705 |
| 3 | Inductive Representation Learning on Large Graphs | 18.41 | 18.41 | 0.00 | 50 | 18571 |
| 4 | Neural Message Passing for Quantum Chemistry | 14.31 | 14.31 | 0.00 | 36 | 8377 |
| 5 | Attention is All you Need | 12.34 | 12.34 | 0.00 | 33 | 156957 |

### Hubs (papers in the top 10 of two or more of the 11 queries)

| paper | in-degree | queries in top 10 | (query, rank) |
|---|---|---|---|
| Attention is All you Need | 156957 | 5 | transformers for time series forecasting #1; speech recognition #1; attention #2; transformers #1; graph #5 |
| Denoising Diffusion Probabilistic Models | 31190 | 4 | diffusion models #3; denoising diffusion probabilistic models #1; diffusion models image generation #2; score-based generative models #2 |
| Diffusion Models Beat GANs on Image Synthesis | 11712 | 3 | denoising diffusion probabilistic models #5; diffusion models image generation #3; score-based generative models #6 |
| Score-Based Generative Modeling through Stochastic Diff | 11470 | 3 | denoising diffusion probabilistic models #2; diffusion models image generation #8; score-based generative models #1 |
| Deep Unsupervised Learning using Nonequilibrium Thermod | 9767 | 3 | denoising diffusion probabilistic models #3; diffusion models image generation #4; score-based generative models #7 |
| BERT: Pre-training of Deep Bidirectional Transformers f | 100295 | 2 | transformers for time series forecasting #9; transformers #2 |
| Long Short-Term Memory | 78549 | 2 | transformers for time series forecasting #5; speech recognition #4 |
| Semi-Supervised Classification with Graph Convolutional | 32585 | 2 | graph neural networks #1; graph #1 |
| Neural Machine Translation by Jointly Learning to Align | 25562 | 2 | speech recognition #9; attention #4 |
| High-Resolution Image Synthesis with Latent Diffusion M | 25228 | 2 | denoising diffusion probabilistic models #7; diffusion models image generation #1 |
| Graph Attention Networks | 24705 | 2 | graph neural networks #3; graph #2 |
| Inductive Representation Learning on Large Graphs | 18571 | 2 | graph neural networks #2; graph #3 |
| Denoising Diffusion Implicit Models | 12708 | 2 | denoising diffusion probabilistic models #4; diffusion models image generation #5 |
| DeepWalk: online learning of social representations | 9855 | 2 | graph neural networks #10; graph #7 |
| How Powerful are Graph Neural Networks? | 9450 | 2 | graph neural networks #9; graph #6 |
| Neural Message Passing for Quantum Chemistry | 8377 | 2 | graph neural networks #8; graph #4 |
| Convolutional Neural Networks on Graphs with Fast Local | 7797 | 2 | graph neural networks #4; graph #8 |
| Generative Modeling by Estimating Gradients of the Data | 5510 | 2 | denoising diffusion probabilistic models #6; score-based generative models #3 |
| A Connection Between Score Matching and Denoising Autoe | 2183 | 2 | denoising diffusion probabilistic models #10; score-based generative models #4 |

## Diagnosis

**"diffusion models" is a neighbor-sense mix, then vote concentration inside the larger, wrong sense. It is not hub bias.**

- Neighbors [V]: 61 of 100 neighbor titles contain "diffusion", but only 1 contains "denois" and 1 "generative"; 12 contain "influence". The median neighbor year is 2016 and 57 are from before 2018. Neighbors 0–3 are about diffusion of information or innovation in networks. The first generative-model neighbor is rank 4 ("The Principles of Diffusion Models").
- Senses [V]: the embed clustering splits the neighbors 82/18 by count and 28.3/7.9 by seed weight (78% vs 22%). The 82 are network or social diffusion; the 18 are generative models.
- Votes [V]: Kempe et al. gets 7.93, all of it from 19 voters in the network cluster (cluster 0) and 0 from the generative cluster (cluster 1). DDPM gets 5.19, all from 12 voters in the generative cluster, whose seed weight it covers at 0.65. So DDPM wins its own sense convincingly. It loses only because that sense holds 22% of the seed weight. Neither score has a neighbor bonus.
- Hub bias does not explain this case [V]: Kempe's in-degree (8,035) is below DDPM's (31,190). In-degree normalization would favor Kempe more, not less (see Fixes).

**Why the good queries escape it** [V]: their neighbor sets have a single sense. "graph neural networks" has 93/100 titles with "graph", 99/100 in one embed cluster, and GCN covers that cluster at 0.76. "neural radiance fields" has 91/100 with "radiance", all neighbors from 2020 on, 97/100 in one cluster, and Instant-NGP at 0.62. The more specific diffusion queries also escape: "denoising diffusion probabilistic models" (34 "denois", 99/100 in one cluster, DDPM #1 at 0.87), "diffusion models image generation" (Latent Diffusion #1, DDPM #2) and "score-based generative models" (Score SDE #1). The failure is in the two-word string's embedding neighborhood, not in voting [I].

**Hub bias is real, but it is a separate and milder problem** [V]: Attention is All you Need is in 5 of 11 top 10s and is rank 1 for "transformers for time series forecasting" and "speech recognition". Adam, LSTM and BERT also show up in queries that don't name them (Adam #3 and LSTM #4 for "speech recognition"). These are plain votes, with no bonus: many neighbors in the right sense cite the hub. In both cases the right-topic papers come right behind it (Informer #2, Librispeech #2).

Verdict: a mix. A neighbor-sense mix plus within-sense vote concentration causes the "diffusion models" failure. Hub bias causes the generic papers that sit near the top of otherwise-correct queries [I].

## Fixes ranked by expected impact on this failure (not implemented)

The rerank checks below only re-sort the dumped top 10 using the stored votes; they are not a full re-score [I].

1. **Expand very short queries (1–2 words) before encoding**, e.g. Muse or a fixed template that turns "diffusion models" into a fuller phrase, using the same `adhoc_query` adapter. Evidence [V]: the three more specific diffusion strings all give generative neighbor sets with DDPM, LDM or Score SDE at #1. Impact: high for this class of query. Effort: medium (one Muse call, which adds latency and Meta cost, plus a rule for "short"). Muse must stay out of the score.
2. **Split senses and show the split instead of a single list** (embed clustering of the 100 seeds; present the top sense per cluster, or ask the user which they meant). Evidence [V]: restricted to cluster 1, DDPM is #1 (5.19); restricted to cluster 0, Kempe is #1. Caveat [V]: keeping only the dominant cluster by weight would pick the network sense (78%), so "dominant sense" alone makes no difference here. It needs either both senses shown or a tie-break such as recency. Effort: medium-high, and PQ reconstruction is noisy (MAE ≈ the distances), so the clustering should use exact vectors or a different signal.
3. **IDF / in-degree normalization of votes**: good for hub bias, wrong for this bug. Evidence [I, re-sort of the dumped top 10]: with `score/log(e+in_degree)`, "speech recognition" #1 becomes Librispeech and "transformers for time series forecasting" #1 becomes Informer. "diffusion models" still has Kempe at #1, with DDPM pushed down. `1/sqrt` is too strong: "graph neural networks" #1 becomes Spectral Networks and "neural radiance fields" #1 becomes KiloNeRF. Effort: small. Impact on "diffusion models": none or negative.

Evaluate any of these on `eval/citation_recall.py`, plus a separate short-query sheet (see above) that isn't used for tuning.

