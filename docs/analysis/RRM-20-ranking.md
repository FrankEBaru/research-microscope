# RRM-20 — why “diffusion models” ranks badly

## Status of this run

The neighbor dump did not run. This environment has no `MODAL_TOKEN_ID` or `MODAL_TOKEN_SECRET` (`modal run scripts/analysis/rrm20_dump.py` stops with “Token missing”). No container was started, so the measured cost is **$0** and there is no Modal app to stop. There is no `scripts/analysis/rrm20_results.json`.

Nothing below is a measured neighbor list, vote, or in-degree. The RRM-17 titles in the ticket (Kempe et al. for “diffusion models”, GCN, Instant-NGP, Attention, and the Attention / Adam / LSTM hubs) are the observation this dump was built to explain. They are not re-measured here. [I] marks a reading of `rrm/search/burst.py`. [V] is reserved for numbers from the JSON.

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

## After the dump exists

Fill this file from `scripts/analysis/rrm20_results.json` only. For each query, state neighbor 0, burst rank 1, the largest embed cluster’s size and exemplar titles, that cluster’s top cited paper and its `weight_coverage`, and the same for the largest cite cluster. Then the hub table. The conclusion is one of: neighbor mix, vote concentration, hub bias, or a mix, each sentence tagged [V] with the field it came from, or [I] when it interprets those fields.
