# Retrieval Evaluation Report

Date: 2026-06-26  
Pipeline: LlamaIndex VectorStoreIndex over the Asantico knowledge base

## Configuration

Embedding backend was hash, chunk size 384 with overlap 64, and top_k 4. The evaluation set holds 10 fixed queries, each labeled with the corpus file that contains the answer.

## Headline Metrics

Hit rate: 0.900  
MRR: 0.850

Hit rate is the fraction of queries where a relevant file appears anywhere in the top-k. MRR averages the reciprocal of the rank of the first relevant result, so it rewards putting the right document at position one.

## Per-Query Results

| ID | First relevant rank | Reciprocal rank | Top score | Hit |
|----|--------------------|-----------------|-----------|-----|
| Q1 | 1 | 1.0 | 0.4935 | yes |
| Q2 | 1 | 1.0 | 0.3019 | yes |
| Q3 | 1 | 1.0 | 0.1188 | yes |
| Q4 | 1 | 1.0 | 0.3327 | yes |
| Q5 | 1 | 1.0 | 0.2816 | yes |
| Q6 | 1 | 1.0 | 0.3964 | yes |
| Q7 | - | 0.0 | 0.3161 | NO |
| Q8 | 1 | 1.0 | 0.3614 | yes |
| Q9 | 2 | 0.5 | 0.2093 | yes |
| Q10 | 1 | 1.0 | 0.1638 | yes |

## Failure Analysis

Miss on Q7 (Is there a minimum charge for a dispatched job?). Expected one of ['company-policies.md'] but retrieved ['billing-workflow.md', 'tax-rules.md', 'work-order-intake.md', 'client-accounts.md']. Likely cause: lexical gap between the query and the source wording under the hash embedding.

Soft miss on Q9: relevant file found but at rank 2 rather than one, costing MRR. Retrieved order was ['client-accounts.md', 'service-trades.md', 'company-policies.md', 'work-order-intake.md'].

## Iteration Plan

Diagnose, then adjust one lever at a time, then re-evaluate. The ordered levers are: swap the hash embedding for a learned backend, expand the corpus to weeks 1 through 6, tune chunk size and overlap, add week and doc-type metadata filtering, and finally add a reranking step measured by MRR lift.
