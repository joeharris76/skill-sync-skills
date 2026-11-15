# Instruction ablation eval

Measures whether a piece of instruction text changes what an agent does. The
same task runs several times with the text present and several times with it
removed; checks on the resulting repository show the difference.

## How a session runs

`run.py` starts a headless `omp` session (`omp -p --mode json`) for each
scenario, arm and repeat:

- The working directory is a new repository under `/tmp/omp-ablation/`, built
  by `base_setup.sh` plus the scenario's own setup. Its `origin` is a local
  bare repository. The directory name is random, so it does not reveal the arm.
- A config overlay turns off every discovery provider that would load the
  user's real instruction files and skills. The arm's global text is loaded as
  `GLOBAL.md` through `contextFiles.extra`; the arm's skills come from
  `git archive <revision> skills` through `skills.customDirectories`.
- `GIT_CONFIG_GLOBAL` points at a sandbox file, and `shims/gh` stands in for
  the GitHub CLI: it records each call and answers from canned files. A session
  cannot push to a real remote or change anything on GitHub.
- Afterwards each check in the scenario runs as a shell command in the sandbox.
  A check passes when it exits 0.

Sessions run with `--auto-approve` as the current user. The sandbox limits Git
and GitHub side effects only; scenario prompts must keep the work inside the
repository.

## Arms

| Global text | Meaning |
|---|---|
| `full` | `deployment/global/AGENTS.md` from this checkout |
| `minus:<heading>` | the same file without one `##` section |
| `lines:<ranges>` | the same file without the given line ranges, for bisecting a section |
| `none` | no global file |
| `old` | `fixtures/global-before-cleanup.md` |

The skills side of an arm is a catalog commit.

## Commands

```sh
uv run --no-project python evals/ablation/run.py run --out <dir> [--scenario <id>] [--arm <name>] [--reps 5] [--jobs 6]
uv run --no-project python evals/ablation/run.py report --out <dir>
```

Results are one JSON file per session under `<dir>/results/`; a finished
session is not run again. The report prints pass counts per check and arm, and
a two-sided Fisher exact p-value against the scenario's reference arm when it
is below 0.1.

## Reading the results

Five repeats per arm can only establish large effects: 5/5 against 0/5 gives
p = 0.008, 5/5 against 1/5 gives p = 0.048, and anything closer is not
significant. A scenario where every arm passes says the text was not needed
for that task with that model; it does not say the text is never needed. A
scenario only tests a rule if the task tempts the failure the rule prevents.
