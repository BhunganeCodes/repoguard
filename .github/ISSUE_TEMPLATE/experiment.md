---
name: Experiment
about: Record a RepoGuard experiment and its outcome
title: "[Experiment] "
labels: experiment
assignees: ""
---

## Hypothesis

What do we expect to change and why?

## Motivation

What problem or limitation motivates this experiment? Do not prescribe the
solution.

## Change

What exactly changed?

## Baseline

What was the performance or behavior before the change? When was it
measured?

## Evaluation

How was the change measured? Reference the evaluation cases used. Use the
same evaluation cases as the baseline.

## Results

What were the results of the evaluation? Report only evidence-backed
numbers.

## Decision

Was the change adopted, rejected, or revised?

## Learning

What did we learn, and how does it affect the next experiment?

## Evidence

Include the evidence that supports these claims (coverage, logs, evaluation
output paths, commit hashes). Never fabricate evidence.

## Engineering Checklist

- [ ] Baseline recorded before the change
- [ ] Same evaluation cases used for baseline and post-change runs
- [ ] Results are evidence-backed
- [ ] Decision recorded
- [ ] Documentation updated where necessary