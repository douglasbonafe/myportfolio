---
title: "Predictive QA: Using Machine Learning to Anticipate Bugs Before Deploy"
description: "I built a just-in-time defect predictor, trained it on requests and Flask, and evaluated it the way it would actually be used. It works. Just not the way the sales decks say."
publishDate: 2026-11-03
lang: en
key: predictive-qa
tags:
  - QA
  - Machine Learning
  - CI/CD
  - Python
repo: https://github.com/douglasbonafe/predictive-qa
cover: /assets/blog/predictive-qa.jpg
cover_alt: "Predictive QA: ranking commits by bug risk before deploy"
---

Every QA team I've worked with has the same problem in a different costume. There's more change than there is review attention. Somebody ships a 400-line PR at 5pm on a Thursday, two people approve it in eleven minutes, and the incident review the following week says "insufficient testing" as if testing were a thing you sprinkle on.

Predictive QA is the idea that you can spend that attention better. Before a commit is deployed, score how likely it is to carry a bug, and route the risky ones to a second reviewer, a longer test suite, or a slower rollout. The research name is just-in-time (JIT) defect prediction, and it's been around since Mockus and Weiss did it at Bell Labs in 2000.

I've seen this pitched a lot lately, usually with an AUC of 0.85 on a slide and no mention of how it was measured. So I built one from scratch, ran it on two real codebases, and measured it the way a team would actually use it. The code is here: [douglasbonafe/predictive-qa](https://github.com/douglasbonafe/predictive-qa).

Short version: it works, it's cheap, and most of its power comes from something you could compute with `git diff --stat`. The longer version is more useful.

## The three pieces

Any JIT defect predictor needs labels, features and a model. The model is the least interesting part.

### Labels: which commits were bad?

You don't have a list of "commits that caused bugs". Nobody does. What you have is a list of commits that fixed something, and that's enough to work backwards.

The standard trick is SZZ, named after Śliwerski, Zimmermann and Zeller, who published it in 2005. Take a fix commit. Look at the lines it had to delete or edit. Run `git blame` on those lines in the parent version. Whoever last touched them introduced the bug.

```python
def _links_for_fix(repo, fix, max_files):
    code = [f for f in fix.files if f.deleted > 0 and is_code_file(f.path)]
    if not code or len(code) > max_files:   # big "fixes" are usually refactors
        return []
    parent = fix.parents[0]
    found = set()
    for f in code:
        ranges = deleted_ranges(repo, parent, fix.sha, f.path)   # git diff -U0 -w
        found.update(blame_lines(repo, parent, f.path, ranges))  # git blame -w --porcelain
    return [Link(s, fix.sha, fix.timestamp) for s in found]
```

It's crude. Fixes are found by keywords in the commit message, so "fix typo in README" counts, and a fix that only adds a missing null check blames nothing. Herbold and colleagues audited this in 2022 and found that only about half of the commits SZZ treats as bug fixes really are. That's the label quality the whole field works with. I keep it, and I keep reminding myself of it when I read the results.

One detail that matters later: I store *when* each bad commit was exposed, not just that it was. The timestamp of the first fix is what makes an honest evaluation possible.

### Features: what does a risky commit look like?

I used the 14 change metrics from Kamei et al. (2013), which is still the reference set. They fall into five groups:

- Size: lines added, lines deleted, size of the touched files.
- Diffusion: how many files, directories and subsystems the change spreads across, and how evenly.
- Purpose: is the commit itself a fix?
- History: how many developers have touched these files, how long since they last changed, how many prior changes.
- Experience: how many commits the author has made overall, recently, and in this subsystem.

I added one more from Rahman and Devanbu (2013): the number of earlier fixes that touched the same files. Code that keeps needing fixes tends to keep needing fixes.

All of it comes from one pass over `git log --numstat`, oldest commit first. Each commit's row is written before the running state is updated, so a commit can never see its own future. There's a test for that, because it's the kind of bug that makes everything look better and nobody notices.

### Model: logistic regression, mostly

I trained logistic regression and gradient boosting on log-transformed features with balanced class weights. Nothing exotic. Logistic regression won on the data I had, and it has a real advantage in a CI tool: you can explain a score. "This commit is risky because it adds a lot of lines to files that have needed five fixes this year" is something a reviewer can act on. "The tree said 0.71" isn't.

## How you evaluate it decides everything

Here's where most demos fall apart.

The lazy way is to shuffle all commits, split 70/30, and use the labels you have today. It feels fine. It's wrong twice.

First, it trains on the future. A random split puts 2024 commits in training and 2019 commits in test. Your model learns patterns from a codebase that didn't exist yet when those test commits were written. In production, the model only ever scores tomorrow's commits with yesterday's knowledge.

Second, it leaks labels. If you train on commits from 2020 using today's SZZ output, some of them are marked buggy because of fixes that landed in 2022. At training time in 2020, you couldn't have known that.

So the evaluation in the POC does this instead:

1. Rolling, time-ordered folds. Train on the first 40% of history, test on the next 8%. Then 48% and the next 8%, and so on, five times.
2. As-of labels. A training commit counts as buggy only if its fix had already landed by the training cutoff.
3. No fresh test data. The newest 20% of history is never tested on, because its bugs haven't been found yet and almost everything in it looks clean.
4. Baselines. Every model is compared with "review the biggest commits first" and "review the smallest commits first". If the model can't beat a sort, it doesn't ship.
5. Budget metrics. AUC is reported, but the number that matters is: if your team reviews the riskiest 20% of commits, what share of the bad ones did it catch?

```python
for c in cutoffs:
    i, j = int(c * n), int((c + window) * n)
    train, test = df.iloc[:i], df.iloc[i:j]
    cutoff_ts = int(train["timestamp"].iloc[-1])
    y_train = labels_as_of(train, cutoff_ts)   # only fixes known at the cutoff
    y_test = y_final[i:j]                      # full hindsight for scoring
```

## Results on requests and Flask

I ran it on [psf/requests](https://github.com/psf/requests) and [pallets/flask](https://github.com/pallets/flask). Both are mature, well-reviewed Python libraries with long histories. After dropping commits that don't touch code (SZZ can't label them, and keeping them makes every model look smarter), that's 2,830 and 2,029 commits. SZZ labeled 17.7% and 20.7% of them as bug-inducing, which is inside the range Kamei reported across his projects.

Averages over five rolling folds:

| | requests | flask |
|---|---|---|
| Random order: bugs caught in top 20% of commits | 19% | 22% |
| Logistic regression: bugs caught in top 20% | 34% | 41% |
| "Biggest commit first": bugs caught in top 20% | 34% | 49% |
| AUC, logistic regression | 0.69 | 0.73 |
| AUC, biggest commit first | 0.69 | 0.77 |
| AUC, logistic regression, **shuffled split** | 0.75 | 0.81 |

Read that table twice. I did.

**The model roughly doubles what you'd catch by chance.** Reviewing the riskiest fifth of commits catches a third to two fifths of the bad ones. That's real, and for a tool that costs a few seconds in CI, it's a good trade.

**A one-line baseline does just as well.** Sorting commits by lines changed matches the model on requests and beats it on Flask. I checked what's left when you hold size constant: inside each size quartile, the model's ranking is barely better than a coin, and a model trained without the size features scores an AUC of 0.51. On these two codebases, everything beyond size is close to noise.

**The leaky split inflates AUC by 6 to 8 points.** Same model, same features, same data. Just shuffled and given hindsight. 0.81 looks like a product. 0.73 looks like a heuristic. The 0.73 is the one that will hold up in your pipeline.

## The metric trap nobody puts on the slide

There's a second family of metrics in this literature called effort-aware. Instead of "how many bad commits are in the top 20%", it asks "how many bad commits can you find by reading 20% of all changed lines". It sounds more realistic, since big commits cost more to review.

Then you run it. "Smallest commit first" finds 78% of the bad commits on requests using only 20% of the lines. Impressive, until you add the column nobody reports: to get there, you opened 85% of all commits. You didn't save review time. You just reviewed nearly everything, in a weird order.

Yang et al. (2016) showed that simple unsupervised rankers like this beat supervised models on effort-aware metrics. Huang, Xia and Lo (2017) replied that once you count how many commits a developer has to open, the picture flips. My numbers reproduce both papers in one table, which is a decent reminder that the metric is a product decision, not a technical one. Pick the budget your reviewers actually have, and measure that.

## What I'd actually deploy

Not a merge blocker. Lewis et al. ran a bug predictor across Google in 2013 and found no measurable change in developer behavior. Engineers ignored scores they couldn't act on and didn't trust. That paper should be required reading for anyone selling "AI quality gates".

What works is routing. The POC ships a GitHub Actions workflow that retrains on the repo's own history on every PR (seconds for a few thousand commits), scores the PR's commits, and writes a table to the job summary:

```
| Commit                         | Risk         | Lines    | Why                                              |
|--------------------------------|--------------|----------|--------------------------------------------------|
| `bfc8f983` add `versionchanged` | 0.61 (low)  | +67/-11  | lines added, author recent activity, file size   |
| `329c32b9` fix dev              | 0.45 (low)  | +33/-36  | author recent activity, lines added, prior fixes |
```

High risk means two things: a second reviewer is required, and the full suite runs instead of the smoke tests. It never means "this commit is wrong". The threshold is set so that about 20% of commits cross it, which is a budget a team can absorb without learning to ignore it.

And honestly, if your own `pqa evaluate` report shows the model doesn't beat "biggest commit first", ship the baseline. It's a line of bash, it's explainable in a postmortem, and it's most of the value.

## Where the real gains are

The finding that size dominates isn't a failure of ML. It's a statement about what git history contains. The log knows how big a change is and who wrote it. It doesn't know:

- how much of the changed code is covered by tests,
- whether CI was flaky on that path last week,
- how long the PR sat in review and how many comments it got,
- whether the author owns that module or is visiting,
- whether the change touches a hot path in production traces.

Those are the signals I'd add next, and they're all available in a normal company setup. Coverage diffs come out of your test runner. Review data comes from the GitHub API. Ownership comes from CODEOWNERS. Traces come from OpenTelemetry. The value of a predictive QA system scales with how much of that context you feed it, and with how honestly you measure whether it's helping.

## Try it on your repo

```bash
pip install git+https://github.com/douglasbonafe/predictive-qa
pqa mine     --repo . --out history.csv
pqa evaluate --data history.csv
pqa train    --data history.csv --model model.pkl
pqa score    --repo . --model model.pkl --range origin/main..HEAD
```

Run `evaluate` first. Look at the "biggest commit first" row before you look at the model. If you find a codebase where the model clearly wins, I want to hear about it.

## References

- Mockus, A., Weiss, D. M. *Predicting risk of software changes.* Bell Labs Technical Journal, 2000.
- Śliwerski, J., Zimmermann, T., Zeller, A. *When do changes induce fixes?* MSR 2005.
- Kamei, Y. et al. *A large-scale empirical study of just-in-time quality assurance.* IEEE TSE, 2013.
- Rahman, F., Devanbu, P. *How, and why, process metrics are better.* ICSE 2013.
- Lewis, C. et al. *Does bug prediction support human developers? Findings from a Google case study.* ICSE 2013.
- Yang, Y. et al. *Effort-aware just-in-time defect prediction: simple unsupervised models could be better than supervised models.* FSE 2016.
- Huang, Q., Xia, X., Lo, D. *Supervised vs unsupervised models: a holistic look at effort-aware just-in-time defect prediction.* ICSME 2017.
- Herbold, S. et al. *Problems with SZZ and features: an empirical study of the state of practice of defect prediction data collection.* Empirical Software Engineering, 2022.
