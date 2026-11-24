# Issue tracker

Issues live in GitHub Issues: [joeytomoyama/max-planck-project](https://github.com/joeytomoyama/max-planck-project/issues).
Use the `gh` CLI with `--repo joeytomoyama/max-planck-project`.

- Read an issue: `gh issue view <n> --repo joeytomoyama/max-planck-project`
- List open issues: `gh issue list --repo joeytomoyama/max-planck-project`
- Work closes through pull requests: put `Closes #<n>` in the PR body.

## Layout

- **#9**: the spec ("Spec: Multi-participant Human-AI experiment platform (rebuild)").
- **#10-#17**: its vertical-slice tickets, each built on its own branch and merged
  into `spec-9-rebuild`, then into `main` with PR #18.
- **#19** onwards: follow-up tickets after the rebuild.
- **#1-#8**: tickets of the scrapped first attempt, closed; the old code is on the
  `qwen-attempt` branch. Ignore them.

SPEC.md wins any conflict between an issue and the spec.
